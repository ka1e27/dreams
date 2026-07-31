"""Unit tests for the three-tier vision pipeline.

Covers Tier 1 (classical water segmentation), Tier 3 (threat assessment +
approach vectors + tracking policy), and the pipeline coordinator's bridge to
the existing overlay/radar (detection conversion, radar engage/disengage,
vision-state snapshot). No camera, model, or event loop is required — the
pipeline's per-frame `_process` is driven directly with synthetic frames.
"""
from __future__ import annotations

import types

import numpy as np
import pytest

from pi5.cv.pipeline import SurveyVisionPipeline
from pi5.cv.segmentation import SegResult, WaterSegmentation, WaterState
from pi5.cv.threat_assessor import (
    APPROACHING,
    RECEDING,
    ThreatAssessor,
    ThreatLevel,
    threat_level_for,
)


# --------------------------------------------------------------------------- #
# Test doubles
# --------------------------------------------------------------------------- #
def _img(color_bgr, w=160, h=120):
    return np.full((h, w, 3), color_bgr, dtype=np.uint8)


def _frame(img):
    return types.SimpleNamespace(left=img, right=None, ts=0.0)


class FakeStepper:
    def __init__(self):
        self._angle = 30.0

    def get_position_degrees(self):
        return self._angle


class FakeRadar:
    def __init__(self, bow_deg=90.0, bar_deg=None):
        self.stepper = FakeStepper()
        self.bow_deg = bow_deg
        # Default the bar to the bow, i.e. boresight 0 — the cameras ride the
        # bar, so "where is the bar pointing" is now part of every bearing and
        # tests need an unambiguous baseline.
        self.stepper._angle = bow_deg if bar_deg is None else bar_deg
        self.modes = []
        self.track_classes = []
        # Every pipeline-driven command must be flagged automatic, so the
        # tracker can let operator intent (a manual pin, TRACK-only) outrank it.
        self.mode_automatic = []
        self.class_automatic = []

    def set_mode(self, m, *, automatic=False):
        self.modes.append(m)
        self.mode_automatic.append(automatic)

    def set_track_class(self, c, *, automatic=False):
        self.track_classes.append(c)
        self.class_automatic.append(automatic)


class FakeOverlay:
    def __init__(self, boxes=None):
        self.enabled = True
        self.available = True
        self._boxes = boxes or []

    def boxes(self):
        return list(self._boxes)


def _box(label, x1, y1, x2, y2, conf=0.9, dist=None):
    # DetectionOverlay tuple: (x1,y1,x2,y2,label,conf,highlight,distance_m)
    return (x1, y1, x2, y2, label, conf, True, dist)


class FakePico:
    """Minimal pico stand-in exposing a .telemetry with lat/lon/heading."""
    def __init__(self, lat=51.506726, lon=-0.071438, heading=0.0):
        self.telemetry = types.SimpleNamespace(lat=lat, lon=lon, heading=heading)


# --------------------------------------------------------------------------- #
# Tier 1 — water segmentation (classical fallback)
# --------------------------------------------------------------------------- #
def test_segmentation_no_model_uses_classical():
    seg = WaterSegmentation(model_path=None)
    assert seg.backend == "classical"


def test_clear_blue_water_is_clear():
    seg = WaterSegmentation()
    res = seg.analyze(_img((140, 90, 30)))  # mid blue → inside the water band
    assert res.water_state == WaterState.CLEAR
    assert res.anomaly_score < 0.15
    assert not seg.is_triggered(res)


def test_green_frame_reads_as_algae():
    seg = WaterSegmentation()
    res = seg.analyze(_img((40, 180, 40)))  # vivid green
    assert res.anomaly_score > 0.5
    assert res.water_state == WaterState.ALGAE
    assert seg.is_triggered(res)


def test_anomaly_regions_found_for_blob():
    seg = WaterSegmentation()
    img = _img((140, 90, 30))
    img[40:90, 60:120] = (250, 250, 250)  # bright white blob = non-water
    res = seg.analyze(img)
    assert len(res.anomaly_regions) >= 1
    x1, y1, x2, y2 = res.anomaly_regions[0]
    assert x2 > x1 and y2 > y1


def test_analyze_bad_frame_degrades():
    seg = WaterSegmentation()
    assert seg.analyze(None).water_state == WaterState.CLEAR


# --- ONNX seg-output reducer (no model needed — pure numpy) ----------------- #
def test_seg_mask_all_water_nchw_logits():
    # (1, C=3, H=2, W=2); channel 1 (water) wins everywhere → no non-water.
    out = np.zeros((1, 3, 2, 2), np.float32)
    out[0, 1] = 1.0
    nw, ig = WaterSegmentation._seg_mask(out, (2, 2), water_class=1,
                                         ignore_classes=set())
    assert nw.shape == (2, 2)
    assert int((nw > 0).sum()) == 0
    assert ig is None


def test_seg_mask_non_water_and_ignored_sky():
    # Pixel classes: [[water, obstacle], [sky, water]] with sky ignored.
    out = np.zeros((1, 3, 2, 2), np.float32)
    out[0, 1, 0, 0] = 1.0   # water
    out[0, 0, 0, 1] = 1.0   # obstacle → non-water
    out[0, 2, 1, 0] = 1.0   # sky → ignored
    out[0, 1, 1, 1] = 1.0   # water
    nw, ig = WaterSegmentation._seg_mask(out, (2, 2), water_class=1,
                                         ignore_classes={2})
    assert int((nw > 0).sum()) == 1        # only the obstacle pixel
    assert ig is not None and int((ig > 0).sum()) == 1  # only the sky pixel


def test_seg_mask_water_probability_map():
    # (1, H, W) single water-probability channel; water = prob >= 0.5.
    out = np.array([[[0.9, 0.1], [0.2, 0.8]]], np.float32)
    nw, ig = WaterSegmentation._seg_mask(out, (2, 2), water_class=1,
                                         ignore_classes=set())
    assert int((nw > 0).sum()) == 2        # the two < 0.5 pixels
    assert ig is None


# --------------------------------------------------------------------------- #
# Tier 3 — threat assessment
# --------------------------------------------------------------------------- #
def test_threat_level_mapping():
    assert threat_level_for("vessel") == ThreatLevel.CRITICAL
    assert threat_level_for("boat") == ThreatLevel.CRITICAL
    assert threat_level_for("buoy") == ThreatLevel.WARNING
    assert threat_level_for("dock") == ThreatLevel.INFO
    assert threat_level_for("water_anomaly") == ThreatLevel.SURVEY
    assert threat_level_for("something_unknown") == ThreatLevel.INFO


def test_vessel_is_primary_and_engages():
    ta = ThreatAssessor()
    det = [{"class_name": "vessel", "confidence": 0.9,
            "distance_m": 12.0, "bbox": (100, 100, 200, 200)}]
    primary = ta.update(det, now=1.0)
    assert primary is not None
    assert primary.class_name == "vessel"
    assert ta.should_engage_tracking(primary) is True


def test_info_class_never_primary_or_engaged():
    ta = ThreatAssessor()
    det = [{"class_name": "dock", "confidence": 0.9,
            "distance_m": 5.0, "bbox": (0, 0, 50, 50)}]
    primary = ta.update(det, now=1.0)
    assert primary is None
    assert ta.should_engage_tracking(None) is False


def test_critical_outranks_warning():
    ta = ThreatAssessor()
    det = [
        {"class_name": "buoy", "confidence": 0.95, "distance_m": 5.0,
         "bbox": (10, 10, 40, 40)},
        {"class_name": "vessel", "confidence": 0.5, "distance_m": 40.0,
         "bbox": (300, 300, 360, 360)},
    ]
    primary = ta.update(det, now=1.0)
    assert primary.class_name == "vessel"  # CRITICAL beats a closer WARNING


def test_approach_vector_detected():
    ta = ThreatAssessor(approach_detection_frames=5, approach_size_threshold=1.10)
    size = 40
    vec = None
    for i in range(8):
        size = int(size * 1.15)  # growing bbox → approaching
        det = [{"class_name": "vessel", "confidence": 0.9, "distance_m": None,
                "bbox": (100, 100, 100 + size, 100 + size)}]
        primary = ta.update(det, now=float(i))
        vec = primary.approach_vector
    assert vec == APPROACHING


def test_receding_vector_detected():
    ta = ThreatAssessor(approach_detection_frames=5, approach_size_threshold=1.10)
    size = 200
    vec = None
    for i in range(8):
        size = int(size * 0.85)  # shrinking bbox → receding
        det = [{"class_name": "vessel", "confidence": 0.9, "distance_m": None,
                "bbox": (100, 100, 100 + size, 100 + size)}]
        primary = ta.update(det, now=float(i))
        vec = primary.approach_vector
    assert vec == RECEDING


def test_warning_engages_only_if_approaching():
    ta = ThreatAssessor(approach_detection_frames=3, approach_size_threshold=1.10)
    # static buoy — should not engage
    for i in range(6):
        det = [{"class_name": "buoy", "confidence": 0.9, "distance_m": 20.0,
                "bbox": (100, 100, 150, 150)}]
        primary = ta.update(det, now=float(i))
    assert ta.should_engage_tracking(primary) is False


def test_mission_alert_within_distance():
    ta = ThreatAssessor(mission_alert_distance_m=30.0)
    ta.update([{"class_name": "vessel", "confidence": 0.9, "distance_m": 20.0,
                "bbox": (100, 100, 200, 200)}], now=1.0)
    alert = ta.get_mission_alert()
    assert alert is not None and alert["class_name"] == "vessel"

    ta2 = ThreatAssessor(mission_alert_distance_m=30.0)
    ta2.update([{"class_name": "vessel", "confidence": 0.9, "distance_m": 80.0,
                 "bbox": (100, 100, 200, 200)}], now=1.0)
    assert ta2.get_mission_alert() is None


def test_stale_objects_pruned():
    ta = ThreatAssessor(lost_ttl_s=3.0)
    ta.update([{"class_name": "vessel", "confidence": 0.9, "distance_m": 10.0,
                "bbox": (0, 0, 50, 50)}], now=1.0)
    assert len(ta.all_objects()) == 1
    ta.update([], now=10.0)  # long gap → pruned
    assert len(ta.all_objects()) == 0


# --------------------------------------------------------------------------- #
# Pipeline coordinator
# --------------------------------------------------------------------------- #
def _pipeline(overlay, radar):
    return SurveyVisionPipeline(
        camera=None, overlay=overlay, radar=radar,
        config={"threat_tracking": {"clear_timeout_s": 5.0}},
        frame_width=160)


def test_detections_from_overlay_conversion():
    ov = FakeOverlay([_box("vessel", 10, 20, 110, 120, 0.8, 15.0)])
    p = _pipeline(ov, FakeRadar())
    dets = p._detections_from_overlay()
    assert dets == [{"class_name": "vessel", "confidence": 0.8,
                     "distance_m": 15.0, "bbox": (10, 20, 110, 120)}]


def test_pipeline_engages_radar_on_vessel():
    ov = FakeOverlay([_box("vessel", 40, 40, 120, 120, 0.9, 10.0)])
    radar = FakeRadar()
    p = _pipeline(ov, radar)
    p.segmentation_enabled = False  # force anomaly=1.0 so Tier 2/3 run
    p._process(_frame(_img((140, 90, 30))), now=100.0)
    assert "TRACK" in radar.modes
    assert "vessel" in radar.track_classes
    st = p.vision_state()
    assert st["tracking_engaged"] is True
    assert st["primary_threat"]["class_name"] == "vessel"


def test_pipeline_resumes_scan_after_threat_clears():
    ov = FakeOverlay([_box("vessel", 40, 40, 120, 120, 0.9, 10.0)])
    radar = FakeRadar()
    p = _pipeline(ov, radar)
    p.segmentation_enabled = False
    p._process(_frame(_img((140, 90, 30))), now=100.0)
    assert "TRACK" in radar.modes
    # threat gone; advance past the clear timeout
    ov._boxes = []
    p._process(_frame(_img((140, 90, 30))), now=106.0)
    assert radar.modes[-1] == "SCAN"
    assert p.vision_state()["tracking_engaged"] is False


def test_pipeline_radar_commands_are_flagged_automatic():
    """Threat assessment must not be able to override an operator who has pinned
    the bar (manual class pick, or TRACK-only). The tracker enforces that on the
    `automatic` flag, so the pipeline has to actually set it."""
    ov = FakeOverlay([_box("vessel", 40, 40, 120, 120, 0.9, 10.0)])
    radar = FakeRadar()
    p = _pipeline(ov, radar)
    p.segmentation_enabled = False
    p._process(_frame(_img((140, 90, 30))), now=100.0)
    ov._boxes = []
    p._process(_frame(_img((140, 90, 30))), now=106.0)
    assert radar.modes and all(radar.mode_automatic)
    assert radar.track_classes and all(radar.class_automatic)


def test_confirm_spotcheck_wakes_yolo_on_clear_water():
    # Classical screen reads clear blue water (no trigger), but a fresh eWaSR-style
    # confirm verdict flags an anomaly → YOLO must wake (fail-safe hybrid gate),
    # and the DNN verdict is the authoritative water_state. Use a real monotonic
    # stamp so vision_state()'s freshness check (which reads the live clock) agrees.
    import time as _time
    ov = FakeOverlay([_box("vessel", 40, 40, 120, 120, 0.9, 10.0)])
    p = _pipeline(ov, FakeRadar())
    p._confirm_seg = types.SimpleNamespace(backend="onnx")   # hybrid "on"
    p._confirm_result = SegResult(water_state=WaterState.OBSTACLE, anomaly_score=0.9)
    now = _time.monotonic()
    p._confirm_t = now
    p._process(_frame(_img((140, 90, 30))), now=now)         # clear-water frame
    assert p._tier2_active is True                            # woken by the confirm
    st = p.vision_state()
    assert st["water_state"] == "obstacle"                    # DNN verdict wins
    assert st["confirm"]["backend"] == "onnx" and st["confirm"]["fresh"] is True


def test_confirm_stale_verdict_ignored():
    # A confirm verdict older than the TTL must not override the classical screen.
    ov = FakeOverlay([])
    p = _pipeline(ov, FakeRadar())
    p._confirm_seg = types.SimpleNamespace(backend="onnx")
    p._confirm_result = SegResult(water_state=WaterState.OBSTACLE, anomaly_score=0.9)
    p._confirm_t = 100.0
    p._process(_frame(_img((140, 90, 30))), now=200.0)       # far past ttl (3 s)
    assert p.vision_state()["water_state"] == "clear"        # classical stands


def test_hybrid_off_without_model():
    # No confirm model configured → confirm snapshot is None, classical only.
    p = _pipeline(FakeOverlay(), FakeRadar())
    assert p._confirm_seg is None
    assert p.vision_state()["confirm"] is None


def test_vision_state_has_expected_keys():
    p = _pipeline(FakeOverlay(), FakeRadar())
    st = p.vision_state()
    for key in ("water_state", "anomaly_score", "tier1_fps", "tier2_active",
                "tier3_active", "primary_threat", "tracking_engaged",
                "yolo_enabled", "segmentation_enabled", "survey_logged"):
        assert key in st


def test_toggles():
    p = _pipeline(FakeOverlay(), FakeRadar())
    assert p.set_segmentation_enabled(False) is False
    assert p.set_yolo_enabled(False) is False
    assert p._overlay.enabled is False  # disabling YOLO idles the overlay


def test_bearing_is_measured_about_the_bow_and_fov():
    radar = FakeRadar(bow_deg=90.0)   # bar at the bow → boresight 0
    p = _pipeline(FakeOverlay(), radar)
    # bbox centred → zero offset → bearing == the bow angle
    assert p._bearing_for((70, 0, 90, 20)) == pytest.approx(90.0, abs=0.5)
    # bbox at right edge → positive offset up to +fov/2
    assert p._bearing_for((150, 0, 160, 20)) > 90.0


def test_bearing_follows_the_bar_because_the_cameras_ride_it():
    """The cameras pan with the bar, so the pixel offset is relative to the BAR.
    A centred box means "straight down the bar", and the reported bearing has to
    move with it — otherwise a target held at bar +90° reads as dead ahead."""
    radar = FakeRadar(bow_deg=0.0, bar_deg=0.0)
    p = _pipeline(FakeOverlay(), radar)
    centred = (70, 0, 90, 20)
    assert p._bearing_for(centred) == pytest.approx(0.0, abs=0.5)
    radar.stepper._angle = 90.0                      # bar swings to starboard
    assert p._bearing_for(centred) == pytest.approx(90.0, abs=0.5)
    radar.stepper._angle = -45.0
    assert p._bearing_for(centred) == pytest.approx(-45.0, abs=0.5)


def test_hull_mounted_cameras_ignore_the_bar_angle():
    """cameras_on_bar=False restores the fixed-boresight behaviour."""
    radar = FakeRadar(bow_deg=0.0, bar_deg=0.0)
    p = _pipeline(FakeOverlay(), radar)
    p._cameras_on_bar = False
    centred = (70, 0, 90, 20)
    before = p._bearing_for(centred)
    radar.stepper._angle = 120.0
    assert p._bearing_for(centred) == before


# --------------------------------------------------------------------------- #
# Object memory — geolocation + confirmation + expiry through the pipeline
# --------------------------------------------------------------------------- #
from pi5.navigation.geo import destination_point, haversine_distance  # noqa: E402


def _mem_pipeline(overlay, *, pico, config=None):
    cfg = {"threat_tracking": {"clear_timeout_s": 5.0}}
    if config:
        cfg.update(config)
    return SurveyVisionPipeline(
        camera=None, overlay=overlay, radar=FakeRadar(), config=cfg,
        pico=pico, fov_deg=75.0, frame_width=160)


def test_pipeline_confirms_and_maps_buoy():
    # A centred buoy box (0° off the bow) at 20 m, boat heading 90° (east): after
    # confirm_sightings frames a marker should drop 20 m due east of the boat.
    pico = FakePico(heading=90.0)
    ov = FakeOverlay([_box("buoy", 70, 50, 90, 70, 0.9, 20.0)])  # centred in 160px
    p = _mem_pipeline(ov, pico=pico,
                      config={"object_memory": {"confirm_sightings": 3}})
    p.segmentation_enabled = False  # force YOLO on so detections flow
    for i in range(3):
        p._process(_frame(_img((140, 90, 30))), now=100.0 + i)
    objs = p.map_objects()
    assert len(objs) == 1
    o = objs[0]
    assert o["class_name"] == "buoy" and o["confirmed"] is True
    exp_lat, exp_lon = destination_point(pico.telemetry.lat, pico.telemetry.lon,
                                         90.0, 20.0)
    assert haversine_distance(o["lat"], o["lon"], exp_lat, exp_lon) < 1.0
    assert p.vision_state()["object_memory"]["permanent"] == 1


def test_geolocation_accounts_for_the_bar_angle():
    """With the cameras on the bar, a marker must land where the bar is looking.
    Boat heading 90° (east), bar swung 90° to starboard, centred box at 20 m →
    the object is due SOUTH (180°), not east. Ignoring the bar angle would plant
    the marker 90° out — and the same bearing steers avoidance."""
    pico = FakePico(heading=90.0)
    ov = FakeOverlay([_box("buoy", 70, 50, 90, 70, 0.9, 20.0)])
    cfg = {"threat_tracking": {"clear_timeout_s": 5.0},
           "object_memory": {"confirm_sightings": 3}}
    p = SurveyVisionPipeline(
        camera=None, overlay=ov, radar=FakeRadar(bow_deg=0.0, bar_deg=90.0),
        config=cfg, pico=pico, fov_deg=75.0, frame_width=160)
    p.segmentation_enabled = False
    for i in range(3):
        p._process(_frame(_img((140, 90, 30))), now=100.0 + i)
    o = p.map_objects()[0]
    exp_lat, exp_lon = destination_point(pico.telemetry.lat, pico.telemetry.lon,
                                         180.0, 20.0)
    assert haversine_distance(o["lat"], o["lon"], exp_lat, exp_lon) < 1.0


def test_pipeline_no_marker_before_confirmation():
    pico = FakePico()
    ov = FakeOverlay([_box("buoy", 70, 50, 90, 70, 0.9, 15.0)])
    p = _mem_pipeline(ov, pico=pico,
                      config={"object_memory": {"confirm_sightings": 4}})
    p.segmentation_enabled = False
    for i in range(2):  # fewer than confirm_sightings
        p._process(_frame(_img((140, 90, 30))), now=200.0 + i)
    assert p.map_objects() == []          # candidate, not yet on the map


def test_pipeline_transient_person_expires():
    pico = FakePico()
    ov = FakeOverlay([_box("person", 70, 50, 90, 70, 0.9, 10.0)])
    p = _mem_pipeline(ov, pico=pico, config={"object_memory": {
        "confirm_sightings": 2, "transient_ttl_s": 30.0}})
    p.segmentation_enabled = False
    for i in range(2):
        p._process(_frame(_img((140, 90, 30))), now=300.0 + i)
    assert len(p.map_objects()) == 1      # person charted (briefly)
    ov._boxes = []                        # person leaves the frame
    p._process(_frame(_img((140, 90, 30))), now=400.0)  # past the TTL
    assert p.map_objects() == []          # forgotten


def test_pipeline_maps_dock_but_not_water_anomaly():
    # A dock is INFO for threat-tracking (never a "threat") but a PERMANENT map
    # landmark — the memory is independent of the threat gate, so it's charted.
    # A water_anomaly is a survey pseudo-class and never a mappable object.
    pico = FakePico()
    ov = FakeOverlay([_box("dock", 70, 50, 90, 70, 0.9, 12.0),
                      _box("water_anomaly", 10, 10, 30, 30, 0.9, 12.0)])
    p = _mem_pipeline(ov, pico=pico,
                      config={"object_memory": {"confirm_sightings": 1}})
    p.segmentation_enabled = False
    p._process(_frame(_img((140, 90, 30))), now=500.0)
    objs = p.map_objects()
    assert [o["class_name"] for o in objs] == ["dock"]


def test_pipeline_radar_releases_known_buoy_keeps_scanning():
    # An APPROACHING buoy normally locks the radar (WARNING + approaching). Once
    # it's confirmed on the map, the pipeline should stop locking the radar onto
    # it so the bar keeps scanning — while an unknown one still gets tracked.
    pico = FakePico(heading=0.0)
    ov = FakeOverlay()
    radar = FakeRadar()
    p = SurveyVisionPipeline(
        camera=None, overlay=ov, radar=radar,
        config={"threat_tracking": {"clear_timeout_s": 5.0,
                                     "approach_detection_frames": 3},
                "object_memory": {"confirm_sightings": 3}},
        pico=pico, fov_deg=75.0, frame_width=160)
    p.segmentation_enabled = False
    # Drive an approaching buoy (growing, centred box → same map spot each frame).
    size = 20
    for i in range(6):
        size = int(size * 1.25)
        cx1, cx2 = 80 - size // 2, 80 + size // 2
        ov._boxes = [_box("buoy", cx1, 60, cx2, 60 + size, 0.9, 12.0)]
        p._process(_frame(_img((140, 90, 30))), now=600.0 + i)
    st = p.vision_state()
    assert st["object_memory"]["permanent"] == 1     # buoy got charted
    # It is known now → the pipeline must not be engaged/tracking it.
    assert st["tracking_engaged"] is False
