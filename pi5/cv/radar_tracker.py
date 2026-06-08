"""Radar-bar tracker — coordinates the stepper with YOLO detections.

Owns the radar bar's motion on a **single daemon thread** so the blocking
stepper pulse train never touches the asyncio event loop. The FastAPI
endpoints only set the mode / a goto target (cheap, thread-safe); this loop is
the sole caller that actually drives the motor — which keeps the stepper's lock
uncontended and avoids two writers fighting over STEP.

Modes:
    SCAN   — continuous sweep between the configured limits, hunting for targets
    TRACK  — locked onto a detected priority target, keeping it centred in frame
    HOLD   — energised, stationary (auto-sleeps after the stepper's idle window)
    SLEEP  — motor in zero-current sleep

Tracking is best-effort: if no detection overlay is wired (or it exposes no
boxes), the tracker simply SCANs. Bearing is derived from a target's horizontal
position in the frame and the camera's horizontal FOV.
"""
from __future__ import annotations

import logging
import threading
import time

logger = logging.getLogger(__name__)

SCAN, TRACK, HOLD, SLEEP = "SCAN", "TRACK", "HOLD", "SLEEP"


class RadarTracker:
    def __init__(self, stepper, overlay=None, *,
                 sweep_min_deg: float = 0.0, sweep_max_deg: float = 180.0,
                 scan_speed_rpm: float = 3.0, track_speed_rpm: float = 8.0,
                 fov_deg: float = 75.0, frame_width: int = 640,
                 priority_classes: list[str] | None = None,
                 lost_timeout_s: float = 3.0, initial_mode: str = SLEEP) -> None:
        self.stepper = stepper
        self.overlay = overlay
        self.sweep_min = float(sweep_min_deg)
        self.sweep_max = float(sweep_max_deg)
        self.scan_speed = float(scan_speed_rpm)
        self.track_speed = float(track_speed_rpm)
        self.fov_deg = float(fov_deg)
        self.frame_width = int(frame_width)
        self.priority = set(priority_classes or ["boat", "person"])
        self.lost_timeout_s = float(lost_timeout_s)

        self._mode = initial_mode
        self._goto: float | None = None
        self._target_locked = False
        self._last_seen = 0.0
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # -- public, thread-safe command surface ------------------------------- #
    def set_mode(self, mode: str) -> None:
        mode = mode.upper()
        if mode not in (SCAN, TRACK, HOLD, SLEEP):
            raise ValueError("unknown mode %r" % mode)
        with self._lock:
            self._mode = mode
            if mode != TRACK:
                self._target_locked = False

    def goto(self, degrees: float) -> None:
        """Queue an absolute move; switches to HOLD so the loop executes it."""
        with self._lock:
            self._goto = float(degrees)
            self._mode = HOLD
            self._target_locked = False

    def center(self) -> None:
        self.goto(0.0)

    def wake(self) -> None:
        with self._lock:
            self._mode = HOLD

    def status(self) -> dict:
        s = self.stepper.status() if self.stepper is not None else {"available": False}
        with self._lock:
            mode = self._mode
            locked = self._target_locked
        # While scanning the stepper reports SCANNING; otherwise mirror our mode.
        state = "SCANNING" if mode == SCAN else mode
        return {
            "available": s.get("available", False),
            "mock": s.get("mock"),
            "angle": s.get("angle"),
            "state": state,
            "mode": mode,
            "target_locked": locked,
            "limits": s.get("limits"),
            "has_slip_ring": s.get("has_slip_ring"),
        }

    # -- lifecycle --------------------------------------------------------- #
    def start(self) -> None:
        if self.stepper is None:
            logger.warning("RadarTracker has no stepper — not starting")
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="radar-tracker", daemon=True)
        self._thread.start()
        logger.info("RadarTracker started (mode=%s, sweep=[%.0f,%.0f])",
                    self._mode, self.sweep_min, self.sweep_max)

    def stop(self) -> None:
        self._stop.set()
        t = self._thread
        if t is not None and t.is_alive():
            t.join(timeout=3.0)
        if self.stepper is not None:
            self.stepper.cleanup()

    # -- control loop (daemon thread) -------------------------------------- #
    def _run(self) -> None:
        while not self._stop.is_set():
            with self._lock:
                mode, goto = self._mode, self._goto
                self._goto = None
            try:
                if mode == SLEEP:
                    self._ensure_not_scanning()
                    self.stepper.sleep()
                    time.sleep(0.1)
                elif mode == HOLD:
                    self._ensure_not_scanning()
                    if goto is not None:
                        self.stepper.rotate_to(goto, self.track_speed)
                    else:
                        self.stepper.maybe_auto_sleep()
                    time.sleep(0.05)
                elif mode == SCAN:
                    self._do_scan()
                elif mode == TRACK:
                    self._do_track()
            except Exception as e:  # noqa: BLE001 — a motion glitch must not kill the loop
                logger.error("radar tracker loop error: %s", e)
                time.sleep(0.2)

    def _ensure_not_scanning(self) -> None:
        if self.stepper.scanning:
            self.stepper.stop_scan()

    def _do_scan(self) -> None:
        if not self.stepper.scanning:
            self.stepper.scan_async(self.sweep_min, self.sweep_max, self.scan_speed)
        target = self._best_target()
        if target is not None:
            self.stepper.stop_scan()
            with self._lock:
                self._mode = TRACK
                self._target_locked = True
                self._last_seen = time.monotonic()
        time.sleep(0.1)

    def _do_track(self) -> None:
        self._ensure_not_scanning()
        target = self._best_target()
        if target is not None:
            with self._lock:
                self._target_locked = True
                self._last_seen = time.monotonic()
            angle = self._bearing_for(target)
            self.stepper.rotate_to(angle, self.track_speed)
        elif (time.monotonic() - self._last_seen) > self.lost_timeout_s:
            with self._lock:
                self._target_locked = False
                self._mode = SCAN
        time.sleep(0.1)

    # -- detection helpers ------------------------------------------------- #
    def _boxes(self) -> list[tuple]:
        """Latest detection boxes from the overlay, or [] if unavailable."""
        if self.overlay is None:
            return []
        getter = getattr(self.overlay, "boxes", None)
        if getter is None:
            return []
        try:
            return getter() or []
        except Exception:  # noqa: BLE001
            return []

    def _best_target(self):
        """Highest-confidence box whose label is a priority class, else None.

        Box layout matches DetectionOverlay: (x1, y1, x2, y2, label, conf, hl).
        """
        best = None
        best_conf = -1.0
        for box in self._boxes():
            try:
                label, conf = box[4], float(box[5])
            except (IndexError, TypeError, ValueError):
                continue
            if label in self.priority and conf > best_conf:
                best, best_conf = box, conf
        return best

    def _bearing_for(self, box) -> float:
        """Map a box's horizontal frame position to an absolute bar angle."""
        x1, x2 = box[0], box[2]
        center = self.frame_width / 2.0
        target_x = (x1 + x2) / 2.0
        offset_deg = (target_x - center) / center * (self.fov_deg / 2.0)
        return self.stepper.get_position_degrees() + offset_deg
