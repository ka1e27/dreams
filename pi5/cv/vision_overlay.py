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

# BGR colours (OpenCV). Amber for highlighted classes, muted teal for the rest.
_COLOR_HIGHLIGHT = (0, 165, 255)
_COLOR_NORMAL = (200, 200, 120)


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
        self._fps: float = 0.0
        self.enabled: bool = self._cfg.enabled

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
                    self._boxes, self._detections, self._fps = [], [], 0.0
                    continue
                interval = 1.0 / max(0.5, self._cfg.detect_max_fps)
                now = time.monotonic()
                if last_run and now - last_run < interval:
                    continue  # rate-capped — drop this frame, keep the queue drained
                boxes, dets = await loop.run_in_executor(None, self._infer, frame.left)
                self._boxes, self._detections = boxes, dets
                if last_run:
                    dt = time.monotonic() - last_run
                    if dt > 0:
                        inst = 1.0 / dt
                        self._fps = inst if self._fps == 0 else 0.8 * self._fps + 0.2 * inst
                last_run = time.monotonic()
        finally:
            self._camera.unsubscribe(q)

    def _infer(self, frame_bgr) -> tuple[list[tuple], list[dict]]:
        try:
            results = self._model(frame_bgr, imgsz=self._cfg.imgsz,
                                   conf=self._cfg.conf, verbose=False)
        except Exception as e:  # noqa: BLE001
            logger.error("overlay inference error: %s", e)
            return [], []
        boxes: list[tuple] = []
        dets: list[dict] = []
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
            boxes.append((x1, y1, x2, y2, label, conf, label in highlight))
            dets.append({"label": label, "confidence": round(conf, 3)})
        return boxes, dets

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
        return frame
