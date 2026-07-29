"""Live detection overlay for the command-center camera feed.

Subscribes to the shared CameraProducer and runs an Ultralytics YOLO model on
the latest frame at a capped rate (inference runs off the event loop in a
thread executor, since it's blocking/CPU-bound). It keeps a latest-boxes list
that the /video MJPEG stream draws onto each frame, plus an inference-FPS
estimate. Detection rate is decoupled from the video stream so inference never
throttles the feed — the dual-thread idea from the D.R.E.A.M.S vision test,
adapted to our async CameraProducer (one camera owner, many subscribers).

The model is configurable via config.yaml ``camera.detection.model``: it
defaults to COCO ``yolov8n.pt`` (detects boat, person, …). Drop in a
maritime-trained ``.pt`` — e.g. one trained on SeaShips / MASTR1325 / the
Singapore Maritime Dataset, or exported from a Roboflow maritime model — to
specialise for vessels and buoys. No code change: ultralytics infers the
format from the path, so an NCNN export dir works too.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from .buoy_detector import BuoyDetector, BuoyDetectorConfig

if TYPE_CHECKING:
    from .stereo import StereoDepth

logger = logging.getLogger(__name__)

# Auto-preferred maritime model: if this exists and the config still points at
# the COCO default, the overlay uses it (onnxruntime backend) without any config
# edit. Trained + exported by the ml/ pipeline (see ml/README.md).
_MARITIME_ONNX = Path(__file__).parent / "models" / "maritime_yolov8n.onnx"

# BGR colours (OpenCV). Amber for highlighted classes, muted teal for the rest,
# cyan for the locked/tracked target reticle.
_COLOR_HIGHLIGHT = (0, 165, 255)
_COLOR_NORMAL = (200, 200, 120)
_COLOR_TRACK = (255, 208, 0)


@dataclass
class DetectionConfig:
    enabled: bool = True
    model: str = "yolov8n.pt"
    imgsz: int = 416
    conf: float = 0.40
    detect_max_fps: float = 8.0
    target_classes: list[str] = field(default_factory=list)            # empty = keep all
    highlight_classes: list[str] = field(default_factory=lambda: ["boat", "person"])
    track_class: str = ""    # lock the tracker to this one class; "" = auto (any highlight)
    # Per-class confidence floors, e.g. {"person": 0.25}. The model runs at the
    # LOWEST floor present and each box is then filtered by its own class's
    # threshold, so a hard-to-see swimmer can be kept at 0.25 without flooding
    # every other class with low-confidence boxes. Case-insensitive.
    # Also how the classical buoy screen is kept out of the CONF slider's way —
    # its score is a quality proxy, not a probability. See config.yaml.
    class_conf: dict[str, float] = field(default_factory=dict)
    # Cores the inference session may use. 0/None = auto (leave headroom for the
    # rest of the stack — see pi5/cv/cpu_budget.py for why 4 is the wrong choice).
    num_threads: int = 0
    # Classical colour/shape buoy screen — supplies the 'buoy' class the COCO
    # model has no weights for. Auto-disables if the loaded model already emits
    # a 'buoy' label (i.e. a real maritime model was dropped in).
    buoy_fallback: bool = True
    buoy_cfg: "BuoyDetectorConfig | None" = None


class DetectionOverlay:
    """Runs YOLO on the camera producer and exposes boxes + controls."""

    def __init__(self, camera, cfg: DetectionConfig | None = None,
                 stereo: "StereoDepth | None" = None) -> None:
        self._camera = camera
        self._cfg = cfg or DetectionConfig()
        self._stereo = stereo       # cv.stereo.StereoDepth, or None (no distance column)
        self._task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()
        self._model = None          # ultralytics YOLO (.pt path)
        self._onnx = None           # onnx_detector.OnnxYolo (.onnx path)
        self._names: dict | list = {}
        # (x1,y1,x2,y2,label,conf,highlight,distance_m|None) — distance_m is only
        # populated when a stereo pair + calibration are available.
        self._boxes: list[tuple] = []
        self._detections: list[dict] = []      # [{label, confidence, distance_m}] for the UI
        self._primary: tuple | None = None     # the box we mark as "tracked"
        self._fps: float = 0.0
        self.enabled: bool = self._cfg.enabled
        self.track_marker: bool = True         # draw a lock reticle on the primary
        # Classical buoy screen. Built eagerly (it is stateless and costs
        # nothing idle) but only *run* when the loaded model can't emit 'buoy' —
        # see _load_model, which flips _buoy_active.
        self._buoy = (BuoyDetector(self._cfg.buoy_cfg or BuoyDetectorConfig())
                      if self._cfg.buoy_fallback else None)
        self._buoy_active: bool = False
        # Lowest per-class floor: the backend must run at least this permissive
        # or a class with a reduced threshold would be dropped before we see it.
        self._class_conf = {k.lower(): float(v) for k, v in
                            (self._cfg.class_conf or {}).items()}

    # -- model -------------------------------------------------------------- #
    def _resolve_model_path(self) -> str:
        """Effective model path. Prefer the maritime ONNX when present and the
        config still has the COCO default; an explicit config value always wins."""
        cfg = (self._cfg.model or "").strip()
        if _MARITIME_ONNX.exists() and cfg in ("", "yolov8n.pt"):
            return str(_MARITIME_ONNX)
        return cfg or "yolov8n.pt"

    def _load_backend(self) -> None:
        """Pick the inference backend: onnxruntime for an .onnx model (no torch
        needed), else ultralytics for a .pt. Sets self._onnx / self._model and
        self._names. Falls back to yolov8n.pt if the .onnx can't be loaded."""
        path = self._resolve_model_path()
        self._cfg.model = path

        # NCNN export directory (fastest CPU path on the Pi 5 — ~2-3x ONNX). An
        # Ultralytics `..._ncnn_model/` dir with .param/.bin, run via the ncnn
        # package (no torch). Same interface as OnnxYolo, so it reuses the slot.
        if os.path.isdir(path) and any(
                f.endswith(".param") for f in os.listdir(path)):
            try:
                from .ncnn_detector import NcnnYolo
                nc = NcnnYolo(path, conf=self._cfg.conf,
                              num_threads=self._cfg.num_threads)
            except Exception as e:  # noqa: BLE001
                nc = None
                logger.warning("NCNN backend import failed: %s", e)
            if nc is not None and nc.available:
                self._onnx = nc
                self._names = dict(enumerate(nc.names))
                logger.info("Using NCNN model: %s (%d classes, imgsz=%d)",
                            os.path.basename(path.rstrip("/")), len(nc.names), nc.imgsz)
                return
            logger.warning("NCNN unavailable — falling back to ONNX/.pt")

        if path.lower().endswith(".onnx"):
            try:
                from .onnx_detector import OnnxYolo
                onnx = OnnxYolo(path, conf=self._cfg.conf,
                                num_threads=self._cfg.num_threads)
            except Exception as e:  # noqa: BLE001
                onnx = None
                logger.warning("ONNX backend import failed: %s", e)
            if onnx is not None and onnx.available:
                self._onnx = onnx
                self._names = dict(enumerate(onnx.names))
                logger.info("Using maritime ONNX model: %s (%d classes, imgsz=%d)",
                            os.path.basename(path), len(onnx.names), onnx.imgsz)
                return
            logger.warning("Maritime ONNX unavailable — falling back to yolov8n.pt")
            path = "yolov8n.pt"
            self._cfg.model = path

        try:
            from ultralytics import YOLO  # heavy; deferred so import stays light
        except ImportError as e:
            logger.warning("ultralytics not installed — detection overlay off (%s)", e)
            return
        try:
            self._model = YOLO(path)
            self._names = getattr(self._model, "names", {}) or {}
            logger.info("Using ultralytics model: %s", path)
        except Exception as e:  # noqa: BLE001 — degrade, never crash startup
            logger.warning("YOLO load failed (%s): %s", path, e)
            self._model = None

    def _load_model(self) -> None:
        """Load the backend, then decide whether the buoy fallback is needed.

        The classical screen exists only because the shipped COCO model has no
        ``buoy`` class. If a real maritime model is dropped in, it emits ``buoy``
        itself and the fallback switches off — so the two never double-report the
        same object and there is no config edit to remember.
        """
        self._load_backend()
        self._buoy_active = self._buoy is not None and "buoy" not in self._label_set()
        if self._buoy_active:
            logger.info("Buoy fallback ON — loaded model has no 'buoy' class "
                        "(%d classes); using the colour/shape screen.",
                        len(self._label_set()))
        elif self._buoy is not None:
            logger.info("Buoy fallback OFF — the loaded model emits 'buoy' itself.")

    def _label_set(self) -> set[str]:
        """Lowercased class labels the loaded model can emit."""
        names = self._names
        values = names.values() if isinstance(names, dict) else (names or [])
        return {str(n).lower() for n in values}

    # -- lifecycle ---------------------------------------------------------- #
    async def start(self) -> None:
        loop = asyncio.get_event_loop()
        # Load (and possibly auto-download) the model off the event loop.
        await loop.run_in_executor(None, self._load_model)
        if not self.available:
            self.enabled = False
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            try:
                await self._task
            except Exception:  # noqa: BLE001
                pass

    # -- accessors ---------------------------------------------------------- #
    @property
    def available(self) -> bool:
        return self._model is not None or self._onnx is not None

    @property
    def detect_fps(self) -> float:
        return round(self._fps, 1)

    def detections(self) -> list[dict]:
        return list(self._detections)

    def boxes(self) -> list[tuple]:
        """Latest raw boxes (x1,y1,x2,y2,label,conf,highlight) for consumers
        that need geometry — e.g. radar_tracker.RadarTracker."""
        return list(self._boxes)

    def primary_target(self) -> dict | None:
        """The single object being tracked (highest-confidence highlight class),
        or None. Used for the command-center tracking readout. The same box gets
        a lock reticle in draw(); the radar tracker independently slews to it."""
        p = self._primary
        if not p:
            return None
        x1, y1, x2, y2, label, conf = p[0], p[1], p[2], p[3], p[4], p[5]
        distance_m = p[7] if len(p) > 7 else None
        return {
            "label": label,
            "confidence": round(float(conf), 3),
            "distance_m": round(distance_m, 1) if distance_m is not None else None,
            "cx": (x1 + x2) // 2,
            "cy": (y1 + y2) // 2,
            "x1": x1, "y1": y1, "x2": x2, "y2": y2,
        }

    @property
    def _infer_conf(self) -> float:
        """Threshold to run the backend at: the most permissive floor in play.

        Derived, not cached — the CONF slider mutates ``_cfg.conf`` at runtime
        (apply_controls), so a stored copy would go stale and silently re-raise
        the floor on a class we deliberately lowered.
        """
        if not self._class_conf:
            return self._cfg.conf
        return min([self._cfg.conf, *self._class_conf.values()])

    def class_names(self) -> list[str]:
        """Sorted unique class labels the loaded model can emit (for the UI's
        target picker). Empty until a model is loaded."""
        names = self._names
        vals = names.values() if isinstance(names, dict) else names
        labels = {str(v) for v in vals}
        if self._buoy_active:
            # The classical screen emits this label even though the model can't,
            # so the operator can pick it in the TRACK picker.
            labels.add(self._buoy.cfg.label if self._buoy else "buoy")
        return sorted(labels)

    def controls(self) -> dict:
        return {
            "detection_enabled": self.enabled,
            "detect_max_fps": self._cfg.detect_max_fps,
            "conf": round(self._cfg.conf, 2),
            "imgsz": self._onnx.imgsz if self._onnx is not None else self._cfg.imgsz,
            "model": self._cfg.model,
            "backend": (("ncnn" if type(self._onnx).__name__ == "NcnnYolo" else "onnx")
                        if self._onnx is not None else ("ultralytics" if self._model else None)),
            "model_loaded": self.available,
            "detect_fps": self.detect_fps,
            "track_class": self._cfg.track_class,    # "" = auto
            "classes": self.class_names(),           # available labels for the picker
        }

    def apply_controls(self, updates: dict) -> dict:
        """Apply partial runtime updates (from POST /api/camera)."""
        if "detection_enabled" in updates:
            self.enabled = bool(updates["detection_enabled"]) and self.available
        if "detect_max_fps" in updates:
            try:
                self._cfg.detect_max_fps = max(0.5, min(30.0, float(updates["detect_max_fps"])))
            except (TypeError, ValueError):
                pass
        if "conf" in updates:
            try:
                self._cfg.conf = max(0.05, min(0.95, float(updates["conf"])))
            except (TypeError, ValueError):
                pass
        if "imgsz" in updates:
            # The real lever on inference speed: smaller = faster (detection FPS
            # is bound by how long _infer takes, NOT by detect_max_fps, which is
            # only an upper cap). YOLO needs a multiple of the stride (32).
            try:
                v = max(160, min(640, int(updates["imgsz"])))
                self._cfg.imgsz = max(32, int(round(v / 32)) * 32)
            except (TypeError, ValueError):
                pass
        if "track_class" in updates:
            # Which single class the lock reticle / primary target follows.
            # "" or "AUTO" → auto (highest-confidence highlight class).
            tc = str(updates["track_class"] or "").strip()
            self._cfg.track_class = "" if tc.upper() == "AUTO" else tc
        return self.controls()

    # -- detection loop ----------------------------------------------------- #
    async def _loop(self) -> None:
        loop = asyncio.get_event_loop()
        q = self._camera.subscribe()
        last_run = 0.0
        try:
            while not self._stop.is_set():
                try:
                    frame = await asyncio.wait_for(q.get(), timeout=2.0)
                except asyncio.TimeoutError:
                    continue
                if not self.enabled or not self.available:
                    self._boxes, self._detections, self._primary, self._fps = [], [], None, 0.0
                    continue
                interval = 1.0 / max(0.5, self._cfg.detect_max_fps)
                now = time.monotonic()
                if last_run and now - last_run < interval:
                    continue  # rate-capped — drop this frame, keep the queue drained
                boxes, dets, primary = await loop.run_in_executor(
                    None, self._infer, frame.left, frame.right)
                self._boxes, self._detections, self._primary = boxes, dets, primary
                if last_run:
                    dt = time.monotonic() - last_run
                    if dt > 0:
                        inst = 1.0 / dt
                        self._fps = inst if self._fps == 0 else 0.8 * self._fps + 0.2 * inst
                last_run = time.monotonic()
        finally:
            self._camera.unsubscribe(q)

    def _raw_detect(self, frame_bgr) -> list[tuple]:
        """Backend-agnostic detection → [(x1,y1,x2,y2,label,conf), ...].

        ONNX (onnxruntime) when a maritime .onnx is loaded, else ultralytics.
        Both return the same plain tuples; highlight/target/primary logic lives
        in _infer so it's identical across backends.
        """
        if self._onnx is not None:
            out = self._onnx.infer(frame_bgr, self._infer_conf)
            return self._add_buoys(frame_bgr, out)
        results = self._model(frame_bgr, imgsz=self._cfg.imgsz,
                              conf=self._infer_conf, verbose=False)
        names = self._names
        out: list[tuple] = []
        for box in getattr(results[0], "boxes", []) or []:
            cid = int(box.cls[0])
            conf = float(box.conf[0])
            if isinstance(names, dict):
                label = names.get(cid, str(cid))
            else:
                label = names[cid] if cid < len(names) else str(cid)
            x1, y1, x2, y2 = (int(v) for v in box.xyxy[0])
            out.append((x1, y1, x2, y2, label, conf))
        return self._add_buoys(frame_bgr, out)

    def _add_buoys(self, frame_bgr, dets: list[tuple]) -> list[tuple]:
        """Append classical buoy candidates to a YOLO detection list.

        Runs on the same frame and at the same rate as inference (so it is
        already capped by ``detect_max_fps``), and costs a measured 0.6-1.0 ms
        against ~30 ms for the forward pass. ``dets`` is passed in so an overlapping classified
        object keeps its label — see BuoyDetector._suppress_overlaps.
        """
        if not self._buoy_active or self._buoy is None:
            return dets
        # Suppress against only the boxes that will actually survive _infer's
        # per-class floor. Otherwise a sub-threshold box (say boat @ 0.32 when
        # boat's floor is 0.40) could suppress a buoy and then be dropped itself,
        # leaving the operator with neither detection. `dets` is still returned
        # whole — _infer does the real filtering.
        keepers = [d for d in dets if self._passes_conf(str(d[4]).lower(), d[5])]
        found = self._buoy.detect(frame_bgr, keepers)
        return dets + found if found else dets

    def _passes_conf(self, label_l: str, conf: float) -> bool:
        """Per-class confidence floor, falling back to the global threshold.

        The backend already ran at the lowest floor of any class, so this is
        where a class without a reduced threshold gets held to the strict value.
        """
        return conf >= self._class_conf.get(label_l, self._cfg.conf)

    def _infer(self, frame_bgr, right_bgr=None) -> tuple[list[tuple], list[dict], tuple | None]:
        try:
            raw = self._raw_detect(frame_bgr)
        except Exception as e:  # noqa: BLE001
            logger.error("overlay inference error: %s", e)
            return [], [], None

        # Distance column: one stereo disparity pass per inference (not per
        # box) when a stereo pair + calibration are available. Skipped
        # entirely if there's no right camera or no calibration.npz loaded.
        depth = None
        if self._stereo is not None and right_bgr is not None and raw:
            try:
                _, depth = self._stereo.compute(frame_bgr, right_bgr)
            except Exception as e:  # noqa: BLE001 — boxes still draw, just no distance
                logger.debug("distance compute failed: %s", e)
                depth = None

        boxes: list[tuple] = []
        dets: list[dict] = []
        primary: tuple | None = None
        primary_conf = -1.0
        # Case-insensitive class matching so a maritime model's "Sail-Boat" /
        # "Person" resolve against lowercase config lists just like COCO labels.
        target = {c.lower() for c in self._cfg.target_classes}
        highlight = {c.lower() for c in self._cfg.highlight_classes}
        track_cls = (self._cfg.track_class or "").strip()
        track_cls_l = track_cls.lower()
        for x1, y1, x2, y2, label, conf in raw:
            label_l = label.lower()
            if target and label_l not in target:
                continue
            # Per-class floor: the backend ran at the most permissive threshold
            # so a low-floor class (e.g. a distant swimmer) survives to here;
            # every other class is held to the strict global conf.
            if not self._passes_conf(label_l, conf):
                continue
            # Highlight the configured classes; when a specific track class is
            # chosen, highlight it too so the picked target is always visible.
            is_hl = label_l in highlight or (track_cls != "" and label_l == track_cls_l)
            distance_m = (self._stereo.median_depth_in_bbox(depth, x1, y1, x2, y2)
                         if depth is not None else None)
            entry = (x1, y1, x2, y2, label, conf, is_hl, distance_m)
            boxes.append(entry)
            dets.append({
                "label": label,
                "confidence": round(conf, 3),
                "distance_m": round(distance_m, 1) if distance_m is not None else None,
            })
            # The tracked object: if the operator picked a class, lock onto the
            # highest-confidence box of THAT class; otherwise fall back to the
            # highest-confidence highlight-class box (what radar_tracker uses).
            is_candidate = (label_l == track_cls_l) if track_cls else is_hl
            if is_candidate and conf > primary_conf:
                primary, primary_conf = entry, conf
        return boxes, dets, primary

    # -- drawing ------------------------------------------------------------ #
    def draw(self, frame):
        """Draw the latest boxes onto a BGR frame in place. Caller passes a copy."""
        boxes = self._boxes
        if not boxes:
            return frame
        import cv2
        h = frame.shape[0]
        base = max(1, round(h / 480))
        fs = max(0.45, h / 720 * 0.6)
        for box in boxes:
            x1, y1, x2, y2, label, conf, hl = box[0], box[1], box[2], box[3], box[4], box[5], box[6]
            distance_m = box[7] if len(box) > 7 else None
            color = _COLOR_HIGHLIGHT if hl else _COLOR_NORMAL
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, base + 1 if hl else base)
            text = ("%s %.0f%% %.1fm" % (label, conf * 100, distance_m)
                    if distance_m is not None else "%s %.0f%%" % (label, conf * 100))
            (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, fs, 1)
            cv2.rectangle(frame, (x1, y1 - th - 6), (x1 + tw + 4, y1), color, -1)
            cv2.putText(frame, text, (x1 + 2, y1 - 4),
                        cv2.FONT_HERSHEY_SIMPLEX, fs, (0, 0, 0), 1, cv2.LINE_AA)
        if self.track_marker and self._primary is not None:
            self._draw_reticle(frame, self._primary, base, fs, cv2)
        return frame

    @staticmethod
    def _draw_reticle(frame, box, base, fs, cv2) -> None:
        """Draw a cyan lock reticle (corner brackets + centre cross) on the
        tracked target so the operator can see what the tracker is following."""
        x1, y1, x2, y2 = box[0], box[1], box[2], box[3]
        cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
        col = _COLOR_TRACK
        th = base + 1
        # corner brackets — a fraction of the shorter side, clamped to a sane span
        leg = max(8, min((x2 - x1), (y2 - y1)) // 4)
        for (ox, sx) in ((x1, 1), (x2, -1)):
            for (oy, sy) in ((y1, 1), (y2, -1)):
                cv2.line(frame, (ox, oy), (ox + sx * leg, oy), col, th)
                cv2.line(frame, (ox, oy), (ox, oy + sy * leg), col, th)
        # centre crosshair
        g = max(4, leg // 2)
        cv2.line(frame, (cx - g, cy), (cx + g, cy), col, th)
        cv2.line(frame, (cx, cy - g), (cx, cy + g), col, th)
        tag = "TRACK %s" % box[4]
        cv2.putText(frame, tag, (x1, y2 + int(18 * max(0.6, fs))),
                    cv2.FONT_HERSHEY_SIMPLEX, fs, col, 1, cv2.LINE_AA)
