"""Three-tier survey vision pipeline — the coordinator.

    Tier 1  WaterSegmentation   — cheap, always-on; screens every frame.
    Tier 2  DetectionOverlay    — YOLO classification (already wired for the
                                   /video feed); the pipeline *gates* it on the
                                   Tier-1 anomaly trigger instead of running a
                                   second model.
    Tier 3  ThreatAssessor      — distance + approach vector + priority, drives
                                   the existing RadarTracker and raises alerts.

Design note — why this layers instead of owning its own YOLO
------------------------------------------------------------
The repo already runs one YOLO pass per frame inside
:class:`pi5.cv.vision_overlay.DetectionOverlay` (with per-box stereo distance),
and :class:`pi5.cv.radar_tracker.RadarTracker` already slews the stepper onto
priority-class detections. Instantiating a *second* YOLO + StereoDepth here (as
a literal reading of the design doc would) would double inference cost on the
Pi 5 — the one resource the hardware is short on. So this pipeline **consumes**
the overlay's detections (`overlay.boxes()`), adds the genuinely new Tier-1
segmentation and Tier-3 threat assessment, and commands the *existing* radar via
its real interface (`set_track_class` / `set_mode`). It never rewrites the
tracker or runs a second detector.

Tiering is realised by gating the overlay: when segmentation is on and the frame
reads as clear, YOLO is idled (with a cooldown hold so it doesn't flicker); an
anomaly wakes it. Turning segmentation off forces YOLO on every frame (the
high-CPU configuration the operator is warned about). See ``vision_state()`` for
the flags the dashboard reflects.
"""
from __future__ import annotations

import asyncio
import datetime
import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING

from .avoidance import AvoidanceConfig, AvoidanceController
from .segmentation import ANOMALY_TRIGGER_THRESHOLD, WaterSegmentation, WaterState
from .threat_assessor import ThreatAssessor, ThreatLevel, threat_level_for

if TYPE_CHECKING:
    from .threat_assessor import TrackedObject

logger = logging.getLogger(__name__)

# BGR colours matching the command-center HUD (amber/cyan/red/blue).
_C_CRITICAL = (59, 59, 255)     # red
_C_WARNING = (46, 176, 255)     # amber
_C_INFO = (255, 176, 0)         # blue-ish / cyan
_C_HUD = (0, 212, 255)          # cyan
_C_TEXT = (230, 230, 230)


class SurveyVisionPipeline:
    """Coordinates the three tiers on top of the existing camera + overlay + radar."""

    def __init__(self, camera, overlay=None, radar=None, *,
                 config: dict | None = None, seg: WaterSegmentation | None = None,
                 pico=None, uploader=None, navigator=None,
                 fov_deg: float = 75.0, frame_width: int = 1920) -> None:
        cfg = config or {}
        self._camera = camera
        self._overlay = overlay          # EXISTING DetectionOverlay — Tier 2 source
        self._radar = radar              # EXISTING RadarTracker — do NOT rewrite
        self._pico = pico                # for GPS (telemetry) + future alert hook
        self._uploader = uploader        # optional CloudUploader; no-op if None
        self._navigator = navigator      # optional Navigator — reactive avoidance
        self.fov_deg = float(cfg.get("fov_degrees", fov_deg))
        self._frame_width = int(frame_width)
        self._frame_height = 0

        self.trigger_threshold = float(
            cfg.get("anomaly_trigger_threshold", ANOMALY_TRIGGER_THRESHOLD))
        self.yolo_cooldown_frames = int(cfg.get("yolo_cooldown_frames", 5))
        self._gate_yolo = bool(cfg.get("gate_yolo_on_anomaly", True))
        self._tier1_max_fps = float(cfg.get("tier1_max_fps", 20.0))

        tt = cfg.get("threat_tracking", {}) or {}
        self._tracking_enabled = bool(tt.get("enabled", True))
        self._clear_timeout_s = float(tt.get("clear_timeout_s", 5.0))
        self.seg = seg or WaterSegmentation(
            cfg.get("seg_model_path"), self.trigger_threshold, config=cfg)

        # Hybrid confirmation (Tier-1b): an optional higher-accuracy DNN water
        # model (eWaSR) run on a *separate slow loop* so it never blocks the fast
        # 15 fps classical screen. It refines the reported water_state and can
        # wake YOLO on obstacles the HSV screen misses (fail-safe: it only *adds*
        # triggers, never suppresses them). Off entirely unless a real model
        # loads — two classical screens would be pointless.
        self._confirm_max_fps = float(cfg.get("seg_confirm_max_fps", 2.0))
        self._confirm_ttl_s = float(cfg.get("seg_confirm_ttl_s", 3.0))
        self._confirm_seg = None
        confirm_path = cfg.get("seg_confirm_model_path")
        if confirm_path and Path(confirm_path).exists():
            cseg = WaterSegmentation(confirm_path, self.trigger_threshold, config=cfg)
            if cseg.backend != "classical":
                self._confirm_seg = cseg
            else:
                logger.info("Confirm seg model %s loaded no DNN backend — hybrid "
                            "spot-check disabled (classical screen only)", confirm_path)
        self.threat = ThreatAssessor(
            approach_detection_frames=int(tt.get("approach_detection_frames", 5)),
            approach_size_threshold=float(tt.get("approach_size_threshold", 1.10)),
            track_warning_if_approaching=bool(tt.get("track_warning_if_approaching", True)),
            mission_alert_distance_m=float(tt.get("mission_alert_distance_m", 30.0)),
        )

        # Reactive obstacle avoidance — pushes a steer-away override into the
        # navigator when the primary threat enters the avoidance envelope. Only
        # active when a navigator is wired (hardware mode). Distance comes from
        # stereo depth when available, else a coarse monocular bbox-size proxy.
        ra = cfg.get("reactive_avoidance", {}) or {}
        self.avoidance_enabled = bool(ra.get("enabled", True))
        nav_cruise = int(getattr(getattr(navigator, "_config", None),
                                 "cruise_throttle", 40))
        self._avoid_cfg = AvoidanceConfig(
            trigger_distance_m=float(ra.get("trigger_distance_m", 8.0)),
            critical_distance_m=float(ra.get("critical_distance_m", 3.0)),
            cruise_throttle=int(ra.get("cruise_throttle", nav_cruise)),
            max_steer=int(ra.get("max_steer", 65)),
            head_on_deg=float(ra.get("head_on_deg", 8.0)),
            min_forward_frac=float(ra.get("min_forward_frac", 0.2)),
        )
        # Bug-style controller: commits to a side and passes the hazard instead of
        # orbiting it. Forward-only sensing here (the camera can't see behind), so
        # it leans on the blind pass-hold once a threat leaves the forward view.
        self._avoid_ctrl = AvoidanceController(
            self._avoid_cfg,
            pass_hold_s=float(ra.get("pass_hold_s", 6.0)),
            pass_bearing_deg=float(ra.get("pass_bearing_deg", 110.0)))
        self._avoiding = False
        sl = cfg.get("survey_logging", {}) or {}
        self._survey_min_conf = float(sl.get("min_confidence", 0.6))
        self._survey_min_anomaly = float(sl.get("min_anomaly_score", 0.20))
        self._survey_min_interval_s = float(sl.get("min_interval_s", 5.0))

        # Operator toggles (mirrored to the dashboard).
        self.segmentation_enabled = True
        self.yolo_enabled = bool(getattr(overlay, "enabled", True)) if overlay else True

        # Runtime state.
        self._task: asyncio.Task[None] | None = None
        self._confirm_task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()
        self._confirm_result = None       # latest SegResult from the DNN spot-check
        self._confirm_t = 0.0             # time.monotonic() of that result
        self._yolo_hold = 0
        self._engaged = False
        self._tracked_class: str | None = None
        self._last_threat_t = 0.0
        self._fps = 0.0
        self._last_run = 0.0
        self._survey_count = 0
        self._last_survey_t: dict[str, float] = {}
        self._mission_alert: dict | None = None
        # Latest snapshot for the annotate() overlay + WS payload.
        self._water_state = WaterState.CLEAR
        self._anomaly_score = 0.0
        self._anomaly_regions: list[tuple[int, int, int, int]] = []
        self._primary: "TrackedObject | None" = None
        self._detections_count = 0
        self._tier2_active = False
        self._tier3_active = False

    # -- lifecycle ---------------------------------------------------------- #
    async def start(self) -> None:
        self._stop.clear()
        self._task = asyncio.create_task(self._loop())
        if self._confirm_seg is not None:
            self._confirm_task = asyncio.create_task(self._confirm_loop())
        logger.info("Survey vision pipeline started (seg=%s, confirm=%s, gate_yolo=%s)",
                    self.seg.backend,
                    self._confirm_seg.backend if self._confirm_seg else "off",
                    self._gate_yolo)

    async def stop(self) -> None:
        self._stop.set()
        for task in (self._task, self._confirm_task):
            if task is not None:
                try:
                    await task
                except Exception:  # noqa: BLE001
                    pass
        # Never leave a stale steer-away override latched on the navigator.
        if self._avoiding and self._navigator is not None:
            try:
                self._navigator.set_avoidance_override(0, 0)
            except Exception:  # noqa: BLE001
                pass
            self._avoiding = False
        self._avoid_ctrl.reset()

    # -- operator toggles --------------------------------------------------- #
    def set_segmentation_enabled(self, enabled: bool) -> bool:
        self.segmentation_enabled = bool(enabled)
        return self.segmentation_enabled

    def set_yolo_enabled(self, enabled: bool) -> bool:
        self.yolo_enabled = bool(enabled)
        if not self.yolo_enabled and self._overlay is not None:
            self._overlay.enabled = False
        return self.yolo_enabled

    def set_avoidance_enabled(self, enabled: bool) -> bool:
        """Enable/disable reactive obstacle avoidance. Turning it off releases any
        active steer-away override back to the navigator immediately."""
        self.avoidance_enabled = bool(enabled)
        if not self.avoidance_enabled and self._avoiding:
            self._avoiding = False
            self._avoid_ctrl.reset()
            if self._navigator is not None:
                try:
                    self._navigator.set_avoidance_override(0, 0)
                except Exception as e:  # noqa: BLE001
                    logger.debug("avoidance release failed: %s", e)
        return self.avoidance_enabled

    # -- main loop ---------------------------------------------------------- #
    async def _loop(self) -> None:
        loop = asyncio.get_event_loop()
        q = self._camera.subscribe()
        try:
            while not self._stop.is_set():
                try:
                    frame = await asyncio.wait_for(q.get(), timeout=2.0)
                except asyncio.TimeoutError:
                    continue
                interval = 1.0 / max(1.0, self._tier1_max_fps)
                now = time.monotonic()
                if self._last_run and now - self._last_run < interval:
                    continue
                try:
                    await loop.run_in_executor(None, self._process, frame, now)
                except Exception as e:  # noqa: BLE001 — never let a frame kill the loop
                    logger.debug("pipeline process error: %s", e)
                if self._last_run:
                    dt = time.monotonic() - self._last_run
                    if dt > 0:
                        inst = 1.0 / dt
                        self._fps = inst if self._fps == 0 else 0.8 * self._fps + 0.2 * inst
                self._last_run = time.monotonic()
        finally:
            self._camera.unsubscribe(q)

    async def _confirm_loop(self) -> None:
        """Slow, decoupled DNN (eWaSR) spot-check. Its own camera subscription
        and rate cap (``seg_confirm_max_fps``, ~1-2 Hz) so a ~200 ms segmentation
        inference never stalls the fast 15 fps classical loop. Publishes the
        latest verdict into ``self._confirm_result`` for ``_process`` to fold in."""
        loop = asyncio.get_event_loop()
        q = self._camera.subscribe()
        last = 0.0
        try:
            while not self._stop.is_set():
                try:
                    frame = await asyncio.wait_for(q.get(), timeout=2.0)
                except asyncio.TimeoutError:
                    continue
                if not self.segmentation_enabled:
                    continue
                interval = 1.0 / max(0.1, self._confirm_max_fps)
                now = time.monotonic()
                if last and now - last < interval:
                    continue
                try:
                    res = await loop.run_in_executor(
                        None, self._confirm_seg.analyze, frame.left)
                    self._confirm_result = res
                    self._confirm_t = time.monotonic()
                except Exception as e:  # noqa: BLE001 — a spot-check hiccup is harmless
                    logger.debug("confirm seg error: %s", e)
                last = time.monotonic()
        finally:
            self._camera.unsubscribe(q)

    def _confirm_fresh(self, now: float) -> bool:
        """True if the DNN spot-check verdict is recent enough to trust."""
        return (self._confirm_result is not None and self._confirm_t > 0.0
                and (now - self._confirm_t) <= self._confirm_ttl_s)

    def _process(self, frame, now: float) -> None:
        """One analysis pass (runs in an executor — blocking cv2 work)."""
        fw = frame.left.shape[1] if frame.left is not None else self._frame_width
        self._frame_width = fw
        if frame.left is not None:
            self._frame_height = frame.left.shape[0]

        # TIER 1 — segmentation (or pass-through when disabled).
        if self.segmentation_enabled:
            seg = self.seg.analyze(frame.left)
            self._water_state = seg.water_state
            self._anomaly_score = seg.anomaly_score
            self._anomaly_regions = seg.anomaly_regions
        else:
            # Seg off → treat every frame as anomalous so YOLO can run freely.
            seg = None
            self._water_state = WaterState.UNKNOWN
            self._anomaly_score = 1.0
            self._anomaly_regions = []

        triggered = self._anomaly_score >= self.trigger_threshold

        # Hybrid Tier-1b: fold in a fresh DNN (eWaSR) spot-check. It's the
        # authoritative water_state for the UI, and can wake YOLO on an obstacle
        # the fast HSV screen missed — but it only *adds* triggers (fail-safe: a
        # survey boat should over-wake rather than miss a hazard).
        if self.segmentation_enabled and self._confirm_fresh(now):
            cres = self._confirm_result
            self._water_state = cres.water_state
            if cres.anomaly_score >= self.trigger_threshold:
                triggered = True

        # TIER 2 gate — wake YOLO on a trigger, hold it for the cooldown window.
        if self.yolo_enabled and triggered:
            self._yolo_hold = self.yolo_cooldown_frames
        want_yolo = self.yolo_enabled and (not self._gate_yolo or self._yolo_hold > 0)
        self._yolo_hold = max(0, self._yolo_hold - 1)
        if self._overlay is not None:
            self._overlay.enabled = want_yolo and self._overlay.available
        self._tier2_active = bool(want_yolo)

        # Read Tier-2 output from the existing overlay (no second inference).
        detections = self._detections_from_overlay() if want_yolo else []
        self._detections_count = len(detections)

        # TIER 3 — threat assessment + tracking, only when we have detections.
        self._tier3_active = False
        if self._tracking_enabled and want_yolo and detections:
            self._tier3_active = True
            gps = self._current_gps()
            self._primary = self.threat.update(detections, gps, now=now)
            self._mission_alert = self.threat.get_mission_alert()
            self._drive_radar(now)
            self._log_survey(detections, now)
        else:
            # No detections this frame — let the assessor age out, disengage.
            self._primary = self.threat.update([], self._current_gps(), now=now)
            self._mission_alert = self.threat.get_mission_alert()
            self._drive_radar(now)

        # Reactive avoidance rides on whatever the primary threat is now.
        self._drive_avoidance(now)

    # -- tier 2 bridge ------------------------------------------------------ #
    def _detections_from_overlay(self) -> list[dict]:
        """Convert the overlay's latest boxes into threat-assessor detections.

        Overlay box tuple: (x1,y1,x2,y2,label,conf,highlight,distance_m|None).
        """
        if self._overlay is None:
            return []
        out: list[dict] = []
        for b in self._overlay.boxes():
            try:
                x1, y1, x2, y2, label, conf = b[0], b[1], b[2], b[3], b[4], b[5]
                dist = b[7] if len(b) > 7 else None
            except (IndexError, TypeError):
                continue
            out.append({
                "class_name": label,
                "confidence": float(conf),
                "distance_m": dist,
                "bbox": (int(x1), int(y1), int(x2), int(y2)),
            })
        return out

    def _current_gps(self) -> "tuple[float | None, float | None]":
        tel = getattr(self._pico, "telemetry", None)
        if tel is None:
            return (None, None)
        lat, lon = getattr(tel, "lat", 0.0), getattr(tel, "lon", 0.0)
        if not lat and not lon:
            return (None, None)
        return (lat, lon)

    # -- tier 3 actions ----------------------------------------------------- #
    def _drive_radar(self, now: float) -> None:
        """Engage/disengage the existing RadarTracker for the primary threat.

        Engage = point the bar at the threat's class (the tracker re-acquires the
        best box of that class itself). On clear, return to SCAN after the
        configured timeout — matching 'hold, then resume scan'.
        """
        if self._radar is None or not self._tracking_enabled:
            return
        primary = self._primary
        engage = self.threat.should_engage_tracking(primary)
        if engage and primary is not None:
            self._last_threat_t = now
            if not self._engaged or self._tracked_class != primary.class_name:
                try:
                    self._radar.set_track_class(primary.class_name)
                    self._radar.set_mode("TRACK")
                except Exception as e:  # noqa: BLE001
                    logger.debug("radar engage failed: %s", e)
                self._engaged = True
                self._tracked_class = primary.class_name
                logger.info("Tracking engaged: %s (%s, %.1fm)",
                            primary.class_name, primary.approach_vector,
                            primary.distance_m or -1.0)
        elif self._engaged and (now - self._last_threat_t) > self._clear_timeout_s:
            try:
                self._radar.set_track_class("")   # back to auto priority
                self._radar.set_mode("SCAN")
            except Exception as e:  # noqa: BLE001
                logger.debug("radar disengage failed: %s", e)
            self._engaged = False
            self._tracked_class = None
            logger.info("Threat cleared — radar resuming SCAN")

    def _drive_avoidance(self, now: float) -> None:
        """Push a steer-away override into the navigator for the primary threat.

        The override only replaces waypoint steering while a hazard is inside the
        avoidance envelope; when it clears we release the override exactly once
        (set 0,0) so we don't fight the navigator every frame. Distance prefers
        stereo depth and falls back to a coarse monocular bbox-size proxy, so
        avoidance still works on a single-camera rig (less precisely).
        """
        nav = self._navigator
        if nav is None or not self.avoidance_enabled:
            return
        p = self._primary
        bearing = distance = None
        if p is not None and p.threat_level >= ThreatLevel.WARNING:
            distance = (p.distance_m if p.distance_m is not None
                        else self._fallback_distance(p.bbox))
            bearing = self._avoidance_bearing(p.bbox)
        override = self._avoid_ctrl.update(bearing, distance, now)
        if override is not None:
            if not self._avoiding:
                side = "STBD" if self._avoid_ctrl.committed_side > 0 else "PORT"
                logger.info("AVOID engage (%s): %s → L=%d R=%d", side,
                            p.class_name if p is not None else "?",
                            override[0], override[1])
            self._avoiding = True
            try:
                nav.set_avoidance_override(override[0], override[1])
            except Exception as e:  # noqa: BLE001
                logger.debug("avoidance override failed: %s", e)
        elif self._avoiding:
            self._avoiding = False
            try:
                nav.set_avoidance_override(0, 0)
                logger.info("AVOID clear — hazard passed, steering to navigator")
            except Exception as e:  # noqa: BLE001
                logger.debug("avoidance release failed: %s", e)

    def _avoidance_bearing(self, bbox) -> float:
        """Threat bearing relative to the bow (deg, +starboard) from its position
        in the forward camera frame. Assumes the detection camera looks ahead."""
        center = self._frame_width / 2.0
        if center <= 0:
            return 0.0
        cx = (bbox[0] + bbox[2]) / 2.0
        return (cx - center) / center * (self.fov_deg / 2.0)

    def _fallback_distance(self, bbox) -> float | None:
        """Very rough monocular range from bbox height (assumes a ~3 m tall
        target), used only when stereo depth is unavailable. None if unusable."""
        h = self._frame_height or self._frame_width  # something sane
        bh = max(1, bbox[3] - bbox[1])
        if h <= 0:
            return None
        return 3.0 * (h / bh)

    def _log_survey(self, detections: list[dict], now: float) -> None:
        """Count INFO/SURVEY-level detections and (optionally) upload them.

        CRITICAL/WARNING go to the threat system, not the survey log. Rate-limited
        per class so a persistent dock doesn't spam the buffer every frame.
        """
        if self._anomaly_score < self._survey_min_anomaly:
            return
        lat, lon = self._current_gps()
        for det in detections:
            cls = det["class_name"]
            if threat_level_for(cls) not in (ThreatLevel.INFO, ThreatLevel.SURVEY):
                continue
            if det["confidence"] < self._survey_min_conf:
                continue
            last = self._last_survey_t.get(cls, 0.0)
            if now - last < self._survey_min_interval_s:
                continue
            self._last_survey_t[cls] = now
            self._survey_count += 1
            self._push_survey(cls, det, lat, lon)

    def _push_survey(self, cls: str, det: dict, lat, lon) -> None:
        """Best-effort push to the CloudUploader, if one is wired. No-op otherwise."""
        if self._uploader is None or lat is None or lon is None:
            return
        try:
            from ..data.uploader import ReadingPayload
            self._uploader.add_reading(ReadingPayload(
                timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                lat=lat, lon=lon,
                depth_m=det.get("distance_m"),
            ))
        except Exception as e:  # noqa: BLE001 — logging is a nice-to-have
            logger.debug("survey upload skipped: %s", e)

    # -- introspection for the server -------------------------------------- #
    def vision_state(self) -> dict:
        """Snapshot for the health WebSocket / dashboard vision panel."""
        p = self._primary
        primary = None
        if p is not None and p.threat_level >= ThreatLevel.WARNING:
            primary = {
                "class_name": p.class_name,
                "threat_level": p.threat_level.name,
                "distance_m": round(p.distance_m, 1) if p.distance_m is not None else None,
                "approach_vector": p.approach_vector,
                "confidence": round(p.confidence, 3),
                "bearing_deg": self._bearing_for(p.bbox),
            }
        return {
            "water_state": self._water_state.value,
            "anomaly_score": round(self._anomaly_score, 3),
            "tier1_fps": round(self._fps, 1),
            "tier2_active": self._tier2_active,
            "tier3_active": self._tier3_active,
            "primary_threat": primary,
            "tracking_engaged": self._engaged,
            "tracked_object": self._tracked_class,
            "tracked_distance_m": primary["distance_m"] if primary else None,
            "detections_count": self._detections_count,
            "yolo_enabled": self.yolo_enabled,
            "segmentation_enabled": self.segmentation_enabled,
            "avoidance_enabled": self.avoidance_enabled,
            "avoiding": self._avoiding,
            "survey_logged": self._survey_count,
            "seg_backend": self.seg.backend,
            "confirm": self._confirm_snapshot(),
            "mission_alert": self._mission_alert,
        }

    def _confirm_snapshot(self) -> "dict | None":
        """DNN spot-check status for the dashboard, or None if hybrid is off."""
        if self._confirm_seg is None:
            return None
        cres = self._confirm_result
        if cres is None:
            return {"backend": self._confirm_seg.backend, "water_state": None,
                    "anomaly_score": None, "age_s": None, "fresh": False}
        age = time.monotonic() - self._confirm_t
        return {
            "backend": self._confirm_seg.backend,
            "water_state": cres.water_state.value,
            "anomaly_score": round(cres.anomaly_score, 3),
            "age_s": round(age, 1),
            "fresh": age <= self._confirm_ttl_s,
        }

    def threats(self) -> list[dict]:
        """Current CRITICAL/WARNING threats with class, distance, bearing."""
        out = []
        for o in self.threat.active_threats():
            d = o.to_dict()
            d["bearing_deg"] = self._bearing_for(o.bbox)
            out.append(d)
        return out

    def _bearing_for(self, bbox) -> float | None:
        """Absolute bar angle that points at a bbox centre (deg), or None if no
        radar. Uses the live frame width + camera FOV + the bar's current angle."""
        try:
            cx = (bbox[0] + bbox[2]) / 2.0
            center = self._frame_width / 2.0
            offset = (cx - center) / center * (self.fov_deg / 2.0)
            base = 0.0
            if self._radar is not None and self._radar.stepper is not None:
                base = self._radar.stepper.get_position_degrees()
            return round(base + offset, 1)
        except Exception:  # noqa: BLE001
            return None

    # -- drawing ------------------------------------------------------------ #
    def annotate(self, frame):
        """Draw the Tier-1/Tier-3 HUD extras onto a BGR frame in place.

        Complements DetectionOverlay.draw() (which draws the YOLO boxes + lock
        reticle): here we add the water-state banner, the anomaly bar, the tier
        indicators, and a coloured highlight on the primary threat.
        """
        import cv2
        h, w = frame.shape[:2]
        fs = max(0.45, h / 720 * 0.6)

        # Water-state banner, bottom-left.
        ws = self._water_state.value.upper()
        label = "WATER: %s" % ("CLEAR" if ws == "CLEAR" else ws.replace("_", " "))
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, fs, 1)
        y0 = h - 10
        cv2.rectangle(frame, (8, y0 - th - 8), (8 + tw + 10, y0 + 4), (10, 19, 22), -1)
        col = _C_HUD if ws == "CLEAR" else _C_WARNING
        cv2.putText(frame, label, (12, y0 - 2), cv2.FONT_HERSHEY_SIMPLEX, fs,
                    col, 1, cv2.LINE_AA)

        # Anomaly bar, top-right.
        bar_w, bar_h = int(w * 0.18), max(6, int(h * 0.012))
        bx, by = w - bar_w - 12, 12
        cv2.rectangle(frame, (bx, by), (bx + bar_w, by + bar_h), (60, 60, 60), 1)
        fill = int(bar_w * min(1.0, self._anomaly_score))
        fcol = _C_WARNING if self._anomaly_score >= self.trigger_threshold else _C_HUD
        if fill > 0:
            cv2.rectangle(frame, (bx, by), (bx + fill, by + bar_h), fcol, -1)
        cv2.putText(frame, "ANOMALY %.0f%%" % (self._anomaly_score * 100),
                    (bx, by + bar_h + int(14 * fs)), cv2.FONT_HERSHEY_SIMPLEX,
                    fs * 0.8, fcol, 1, cv2.LINE_AA)

        # Tier indicators — three dots (T1 always on, T2 amber, T3 red).
        dots = [(True, _C_HUD), (self._tier2_active, _C_WARNING),
                (self._tier3_active, _C_CRITICAL)]
        for i, (on, dc) in enumerate(dots):
            cx = bx + 8 + i * 22
            cy = by + bar_h + int(30 * fs)
            cv2.circle(frame, (cx, cy), 6, dc if on else (50, 50, 50), -1)

        # Primary-threat highlight.
        p = self._primary
        if p is not None and p.threat_level >= ThreatLevel.WARNING:
            x1, y1, x2, y2 = p.bbox
            tcol = _C_CRITICAL if p.threat_level == ThreatLevel.CRITICAL else _C_WARNING
            cv2.rectangle(frame, (x1, y1), (x2, y2), tcol, 3)
            arrow = {"APPROACHING": "^", "RECEDING": "v", "STATIC": "="}.get(
                p.approach_vector, "")
            dtxt = ("%.1fm" % p.distance_m) if p.distance_m is not None else "?m"
            tag = "%s %s %s" % (p.class_name.upper(), dtxt, arrow)
            cv2.putText(frame, tag, (x1, max(14, y1 - 8)),
                        cv2.FONT_HERSHEY_SIMPLEX, fs, tcol, 2, cv2.LINE_AA)
        return frame
