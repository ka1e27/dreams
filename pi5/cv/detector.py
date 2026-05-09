"""YOLOv8-nano boat detector.

Uses ultralytics YOLO with the COCO-pretrained nano weights and filters
to a single class (default: 8 = "boat"). Detection is invoked on a single
BGR frame at a time; the caller is responsible for throttling rate.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class Detection:
    x1: int
    y1: int
    x2: int
    y2: int
    confidence: float
    class_id: int

    @property
    def cx(self) -> float:
        return (self.x1 + self.x2) / 2.0

    @property
    def cy(self) -> float:
        return (self.y1 + self.y2) / 2.0


class BoatDetector:
    """Wraps a YOLOv8-nano model and filters to one class."""

    def __init__(self, class_id: int = 8, conf_threshold: float = 0.4,
                 weights: str = "yolov8n.pt") -> None:
        self._class_id = class_id
        self._conf = conf_threshold
        # Defer the heavy ultralytics import so unit tests / sim mode
        # without YOLO installed don't crash on module import.
        try:
            from ultralytics import YOLO  # type: ignore
        except ImportError as e:
            logger.warning("ultralytics not installed; boat detection disabled (%s)", e)
            self._model = None
            return
        try:
            self._model = YOLO(weights)
        except Exception as e:
            logger.warning("YOLO model load failed: %s", e)
            self._model = None

    @property
    def available(self) -> bool:
        return self._model is not None

    def detect(self, frame_bgr: np.ndarray) -> list[Detection]:
        """Run detection and return any boats above the confidence threshold."""
        if self._model is None:
            return []
        try:
            results = self._model(frame_bgr, verbose=False)
        except Exception as e:
            logger.error("YOLO inference error: %s", e)
            return []
        out: list[Detection] = []
        for r in results:
            boxes = getattr(r, "boxes", None)
            if boxes is None:
                continue
            xyxy = boxes.xyxy.cpu().numpy() if hasattr(boxes.xyxy, "cpu") else boxes.xyxy
            conf = boxes.conf.cpu().numpy() if hasattr(boxes.conf, "cpu") else boxes.conf
            cls = boxes.cls.cpu().numpy() if hasattr(boxes.cls, "cpu") else boxes.cls
            for i in range(len(xyxy)):
                cid = int(cls[i])
                if cid != self._class_id:
                    continue
                c = float(conf[i])
                if c < self._conf:
                    continue
                x1, y1, x2, y2 = (int(v) for v in xyxy[i])
                out.append(Detection(x1, y1, x2, y2, c, cid))
        return out
