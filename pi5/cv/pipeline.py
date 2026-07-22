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
from typing import TYPE_CHECKING

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
                 pico=None, uploader=None,
                 fov_deg: float = 75.0, frame_width: int = 1920) -> None:
        cfg = config or {}
        self._camera = camera
        self._overlay = overlay          # EXISTING DetectionOverlay — Tier 2 source
        self._radar = radar              # EXISTING RadarTracker — do NOT rewrite
        self._pico = pico                # for GPS (telemetry) + future alert hook
        self._uploader = uploader        # optional CloudUploader; no-op if None
        self.fov_deg = float(cfg.get("fov_degrees", fov_deg))
        self._frame_width = int(frame_width)

        self.trigger_threshold = float(
            cfg.get("anomaly_trigger_threshold", ANOMALY_TRIGGER_THRESHOLD))
        self.yolo_cooldown_frames = int(cfg.get("yolo_cooldown_frames", 5))
        self._gate_yolo = bool(cfg.get("gate_yolo_on_anomaly", True))
        self._tier1_max_fps = float(cfg.get("tier1_max_fps", 20.0))

        tt = cfg.get("threat_tracking", {}) or {}
        self._tracking_enabled = bool(tt.get("enabled", True))
        self._clear_timeout_s = float(tt.get("clear_timeout_s", 5.0))
        self.seg = seg or WaterSegmentation(
            cfg.get("seg_model_path"), self.trigger_threshold)
        self.threat = ThreatAssessor(
            approach_detection_frames=int(tt.get("approach_detection_frames", 5)),
            approach_size_threshold=float(tt.get("approach_size_threshold", 1.10)),
            track_warning_if_approaching=bool(tt.get("track_warning_if_approaching", True)),
            mission_alert_distance_m=float(tt.get("mission_alert_distance_m", 30.0)),
        )
        sl = cfg.get("survey_logging", {}) or {}
        self._survey_min_conf = float(sl.get("min_confidence", 0.6))
        self._survey_min_anomaly = float(sl.get("min_anomaly_score", 0.20))
        self._survey_min_interval_s = float(sl.get("min_interval_s", 5.0))

        # Operator toggles (mirrored to the dashboard).
        self.segmentation_enabled = True
        self.yolo_enabled = bool(getattr(overlay, "enabled", True)) if overlay else True

        # Runtime state.
        self._task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()
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
        logger.info("Survey vision pipeline started (seg=%s, gate_yolo=%s)",
                    self.seg.backend, self._gate_yolo)

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            try:
                await self._task
            except Exception:  # noqa: BLE001
                pass

    # -- operator toggles --------------------------------------------------- #
    def set_segmentation_enabled(self, enabled: bool) -> bool:
        self.segmentation_enabled = bool(enabled)
        return self.segmentation_enabled

    def set_yolo_enabled(self, enabled: bool) -> bool:
        self.yolo_enabled = bool(enabled)
        if not self.yolo_enabled and self._overlay is not None:
            self._overlay.enabled = False
        return self.yolo_enabled

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

    def _process(self, frame, now: float) -> None:
        """One analysis pass (runs in an executor — blocking cv2 work)."""
        fw = frame.left.shape[1] if frame.left is not None else self._frame_width
        self._frame_width = fw

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
            "survey_logged": self._survey_count,
            "seg_backend": self.seg.backend,
            "mission_alert": self._mission_alert,
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
