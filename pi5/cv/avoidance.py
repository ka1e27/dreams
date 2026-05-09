"""Boat-avoidance loop — combine YOLO detection with stereo depth and
push a steer-away override into the navigator.

Loop runs as a background asyncio task. Each iteration:
  1. Pull the most recent stereo frame from the camera producer
  2. Run YOLO on the left image, filter to boats
  3. For each boat, compute median depth inside its bbox
  4. Pick the closest threat. If closer than min_distance_m, compute a
     steer-away throttle pair and call Navigator.set_avoidance_override(...)
  5. Otherwise clear the override

The throttle pair leans the boat away from the threat's image-x position:
threat to the left → steer right (slow left motor), threat to the right →
steer left (slow right motor). Severity scales with how close the threat
is relative to crit_distance_m.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from .camera import CameraProducer
from .detector import BoatDetector
from .stereo import StereoDepth

logger = logging.getLogger(__name__)


@dataclass
class AvoidanceConfig:
    min_distance_m: float = 5.0
    crit_distance_m: float = 2.0
    cruise_throttle: int = 40
    update_rate_hz: float = 4.0


class AvoidanceLoop:
    def __init__(self, navigator, camera: CameraProducer,
                 detector: BoatDetector, stereo: StereoDepth | None,
                 cfg: AvoidanceConfig | None = None) -> None:
        self._nav = navigator
        self._camera = camera
        self._detector = detector
        self._stereo = stereo
        self._cfg = cfg or AvoidanceConfig()
        self._task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()

    async def start(self) -> None:
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            await self._task

    async def _loop(self) -> None:
        interval = 1.0 / max(0.5, self._cfg.update_rate_hz)
        q = self._camera.subscribe()
        try:
            while not self._stop.is_set():
                try:
                    frame = await asyncio.wait_for(q.get(), timeout=2.0)
                except asyncio.TimeoutError:
                    continue
                self._process(frame)
                await asyncio.sleep(interval)
        finally:
            self._camera.unsubscribe(q)

    def _process(self, frame) -> None:
        boats = self._detector.detect(frame.left)
        if not boats:
            self._nav.set_avoidance_override(0, 0)
            return

        # Compute distance for each boat. Without stereo we fall back to a
        # bbox-height heuristic (assumes a typical 3 m visible boat profile).
        threats: list[tuple[float, float]] = []  # (distance_m, cx_normalized)
        if self._stereo is not None and frame.right is not None:
            _, depth = self._stereo.compute(frame.left, frame.right)
            for b in boats:
                d = self._stereo.median_depth_in_bbox(depth, b.x1, b.y1,
                                                     b.x2, b.y2)
                if d is None:
                    continue
                cx_norm = (b.cx / max(1, frame.left.shape[1])) - 0.5
                threats.append((d, cx_norm))
        else:
            h_img = max(1, frame.left.shape[0])
            for b in boats:
                bbox_h = max(1, b.y2 - b.y1)
                # Rough monocular distance: assumes target ~3 m tall and
                # a vertical FOV around 50° (pinhole ≈ f_y * H_real / h_px).
                # Treat (image_h / bbox_h) as a proxy for distance ratio.
                d = 3.0 * (h_img / bbox_h)
                cx_norm = (b.cx / max(1, frame.left.shape[1])) - 0.5
                threats.append((d, cx_norm))

        if not threats:
            self._nav.set_avoidance_override(0, 0)
            return

        threats.sort(key=lambda t: t[0])
        d, cx_norm = threats[0]

        if d > self._cfg.min_distance_m:
            self._nav.set_avoidance_override(0, 0)
            return

        # Severity: 1.0 at crit_distance_m, fading to 0 at min_distance_m.
        span = max(0.001, self._cfg.min_distance_m - self._cfg.crit_distance_m)
        severity = 1.0 - max(0.0, (d - self._cfg.crit_distance_m) / span)
        severity = max(0.0, min(1.0, severity))

        base = self._cfg.cruise_throttle
        # Throttle scaled down by severity — full evasive close to crit.
        spd = int(base * (1.0 - 0.5 * severity))
        # Steer away from the threat's image-x position.
        # cx_norm > 0 → threat on right → turn left (right motor faster)
        steer = int(60 * severity * (-1 if cx_norm > 0 else 1))
        left = max(-100, min(100, spd - steer))
        right = max(-100, min(100, spd + steer))
        logger.info("Boat avoid: d=%.1fm cx=%.2f sev=%.2f L=%d R=%d",
                    d, cx_norm, severity, left, right)
        self._nav.set_avoidance_override(left, right)
