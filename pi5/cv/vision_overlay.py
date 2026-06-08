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
import time
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

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


class DetectionOverlay:
    """Runs YOLO on the camera producer and exposes boxes + controls."""

    def __init__(self, camera, cfg: DetectionConfig | None = None) -> None:
        self._camera = camera
        self._cfg = cfg or DetectionConfig()
        self._task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()
        self._model = None
        self._names: dict | list = {}
        self._boxes: list[tuple] = []          # (x1,y1,x2,y2,label,conf,highlight)
        self._detections: list[dict] = []      # [{label, confidence}] for the UI
        self._primary: tuple | None = None     # the box we mark as "tracked"
        self._fps: float = 0.0
        self.enabled: bool = self._cfg.enabled
        self.track_marker: bool = True         # draw a lock reticle on the primary

    # -- model -------------------------------------------------------------- #
    def _load_model(self):
        try:
            from ultralytics import YOLO  # heavy; deferred so import stays light
        except ImportError as e:
            logger.warning("ultralytics not installed — detection overlay off (%s)", e)
            return None
        try:
            model = YOLO(self._cfg.model)
            logger.info("Detection overlay model loaded: %s", self._cfg.model)
            return model
        except Exception as e:  # noqa: BLE001 — degrade, never crash startup
            logger.warning("YOLO load failed (%s): %s", self._cfg.model, e)
            return None

    # -- lifecycle ---------------------------------------------------------- #
    async def start(self) -> None:
        loop = asyncio.get_event_loop()
        # Load (and possibly auto-download) the model off the event loop.
        self._model = await loop.run_in_executor(None, self._load_model)
        self._names = getattr(self._model, "names", {}) or {}
        if self._model is None:
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
        return self._model is not None

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
        return {
            "label": label,
            "confidence": round(float(conf), 3),
            "cx": (x1 + x2) // 2,
            "cy": (y1 + y2) // 2,
            "x1": x1, "y1": y1, "x2": x2, "y2": y2,
        }

    def controls(self) -> dict:
        return {
            "detection_enabled": self.enabled,
            "detect_max_fps": self._cfg.detect_max_fps,
            "conf": round(self._cfg.conf, 2),
            "imgsz": self._cfg.imgsz,
            "model": self._cfg.model,
            "model_loaded": self._model is not None,
            "detect_fps": self.detect_fps,
        }

    def apply_controls(self, updates: dict) -> dict:
        """Apply partial runtime updates (from POST /api/camera)."""
        if "detection_enabled" in updates:
            self.enabled = bool(updates["detection_enabled"]) and self._model is not None
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
                if not self.enabled or self._model is None:
                    self._boxes, self._detections, self._primary, self._fps = [], [], None, 0.0
                    continue
                interval = 1.0 / max(0.5, self._cfg.detect_max_fps)
                now = time.monotonic()
                if last_run and now - last_run < interval:
                    continue  # rate-capped — drop this frame, keep the queue drained
                boxes, dets, primary = await loop.run_in_executor(None, self._infer, frame.left)
                self._boxes, self._detections, self._primary = boxes, dets, primary
                if last_run:
                    dt = time.monotonic() - last_run
                    if dt > 0:
                        inst = 1.0 / dt
                        self._fps = inst if self._fps == 0 else 0.8 * self._fps + 0.2 * inst
                last_run = time.monotonic()
        finally:
            self._camera.unsubscribe(q)

    def _infer(self, frame_bgr) -> tuple[list[tuple], list[dict], tuple | None]:
        try:
            results = self._model(frame_bgr, imgsz=self._cfg.imgsz,
                                   conf=self._cfg.conf, verbose=False)
        except Exception as e:  # noqa: BLE001
            logger.error("overlay inference error: %s", e)
            return [], [], None
        boxes: list[tuple] = []
        dets: list[dict] = []
        primary: tuple | None = None
        primary_conf = -1.0
        names = self._names
        target = set(self._cfg.target_classes)
        highlight = set(self._cfg.highlight_classes)
        for box in getattr(results[0], "boxes", []) or []:
            cid = int(box.cls[0])
            conf = float(box.conf[0])
            if isinstance(names, dict):
                label = names.get(cid, str(cid))
            else:
                label = names[cid] if cid < len(names) else str(cid)
            if target and label not in target:
                continue
            x1, y1, x2, y2 = (int(v) for v in box.xyxy[0])
            is_hl = label in highlight
            entry = (x1, y1, x2, y2, label, conf, is_hl)
            boxes.append(entry)
            dets.append({"label": label, "confidence": round(conf, 3)})
            # The tracked object = highest-confidence highlight-class box. This
            # matches what radar_tracker treats as its priority target.
            if is_hl and conf > primary_conf:
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
        for x1, y1, x2, y2, label, conf, hl in boxes:
            color = _COLOR_HIGHLIGHT if hl else _COLOR_NORMAL
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, base + 1 if hl else base)
            text = "%s %.0f%%" % (label, conf * 100)
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
