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
from pi5.cv.segmentation import WaterSegmentation, WaterState
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
    def __init__(self):
        self.stepper = FakeStepper()
        self.modes = []
        self.track_classes = []

    def set_mode(self, m):
        self.modes.append(m)

    def set_track_class(self, c):
        self.track_classes.append(c)


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


def test_bearing_uses_stepper_angle_and_fov():
    radar = FakeRadar()  # stepper at 30 deg
    p = _pipeline(FakeOverlay(), radar)
    # bbox centred → zero offset → bearing == current angle
    assert p._bearing_for((70, 0, 90, 20)) == pytest.approx(30.0, abs=0.5)
    # bbox at right edge → positive offset up to +fov/2
    b = p._bearing_for((150, 0, 160, 20))
    assert b > 30.0
