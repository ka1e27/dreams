"""Tests for DetectionOverlay's buoy fallback gate and per-class confidence floors.

These cover the wiring rather than inference: whether the classical buoy screen
turns itself on/off correctly for a given model, and whether a lowered per-class
threshold actually survives to the box filter.
"""
from __future__ import annotations

import pytest

from pi5.cv.vision_overlay import DetectionConfig, DetectionOverlay

COCO_SUBSET = {0: "person", 8: "boat", 32: "sports ball"}
MARITIME = {0: "vessel", 1: "kayak", 2: "buoy", 3: "person", 4: "dock", 5: "debris"}


def _overlay(**cfg) -> DetectionOverlay:
    """An overlay with no camera — __init__ only stores the reference."""
    return DetectionOverlay(None, DetectionConfig(**cfg))


# -- buoy fallback gate ---------------------------------------------------- #

def test_fallback_switches_on_for_a_model_with_no_buoy_class():
    ov = _overlay()
    ov._names = COCO_SUBSET
    ov._buoy_active = ov._buoy is not None and "buoy" not in ov._label_set()
    assert ov._buoy_active is True


def test_fallback_switches_off_when_the_model_emits_buoy_itself():
    """Dropping in a real maritime model must silence the classical screen so
    the two never double-report the same object."""
    ov = _overlay()
    ov._names = MARITIME
    ov._buoy_active = ov._buoy is not None and "buoy" not in ov._label_set()
    assert ov._buoy_active is False


def test_fallback_can_be_disabled_by_config():
    ov = _overlay(buoy_fallback=False)
    assert ov._buoy is None
    ov._names = COCO_SUBSET
    ov._buoy_active = ov._buoy is not None and "buoy" not in ov._label_set()
    assert ov._buoy_active is False


def test_label_set_handles_dict_and_list_names():
    ov = _overlay()
    ov._names = COCO_SUBSET
    assert ov._label_set() == {"person", "boat", "sports ball"}
    ov._names = ["Person", "BUOY"]
    assert ov._label_set() == {"person", "buoy"}


def test_add_buoys_is_a_noop_while_inactive():
    ov = _overlay()
    ov._buoy_active = False
    dets = [(0, 0, 10, 10, "person", 0.9)]
    assert ov._add_buoys(None, dets) is dets


def test_buoy_appears_in_the_track_picker_only_when_active():
    ov = _overlay()
    ov._names = COCO_SUBSET
    ov._buoy_active = True
    assert "buoy" in ov.class_names()
    ov._buoy_active = False
    assert "buoy" not in ov.class_names()


# -- per-class confidence floors ------------------------------------------- #

def test_infer_conf_is_the_most_permissive_floor():
    ov = _overlay(conf=0.40, class_conf={"person": 0.25})
    assert ov._infer_conf == 0.25


def test_infer_conf_without_overrides_is_the_global_conf():
    assert _overlay(conf=0.40)._infer_conf == 0.40


def test_infer_conf_follows_a_runtime_conf_change():
    """The CONF slider mutates _cfg.conf via apply_controls; a cached floor
    would go stale and silently re-raise the threshold we lowered."""
    ov = _overlay(conf=0.40, class_conf={"person": 0.25})
    ov.apply_controls({"conf": 0.10})
    assert ov._infer_conf == 0.10          # slider now the most permissive
    ov.apply_controls({"conf": 0.90})
    assert ov._infer_conf == 0.25          # person floor still honoured


def test_lowered_class_keeps_a_faint_box_that_others_lose():
    ov = _overlay(conf=0.40, class_conf={"person": 0.25})
    assert ov._passes_conf("person", 0.30) is True     # swimmer survives
    assert ov._passes_conf("boat", 0.30) is False      # everything else does not
    assert ov._passes_conf("boat", 0.55) is True


def test_class_conf_matching_is_case_insensitive():
    ov = _overlay(conf=0.40, class_conf={"Person": 0.25})
    assert ov._passes_conf("person", 0.30) is True


def test_below_every_floor_is_still_dropped():
    ov = _overlay(conf=0.40, class_conf={"person": 0.25})
    assert ov._passes_conf("person", 0.20) is False


def test_weak_buoys_survive_the_confidence_filter():
    """The classical screen scores 0.35-0.80. At the global 0.40 the weakest real
    buoys would be dropped, so config gives 'buoy' its own 0.30 floor."""
    ov = _overlay(conf=0.40, class_conf={"buoy": 0.30})
    assert ov._passes_conf("buoy", 0.35) is True     # weakest possible score
    assert ov._passes_conf("buoy", 0.29) is False


def test_buoy_survives_the_conf_slider_being_dragged_up():
    """Dragging CONF to 0.9 must not silently switch buoy detection off."""
    ov = _overlay(conf=0.40, class_conf={"buoy": 0.30})
    ov.apply_controls({"conf": 0.90})
    assert ov._passes_conf("buoy", 0.40) is True


# -- _add_buoys against the real detector ---------------------------------- #

def _lake_with_buoy():
    """A synthetic water scene with one orange blob, via the real cv2 path."""
    np = pytest.importorskip("numpy")
    cv2 = pytest.importorskip("cv2")
    f = np.zeros((480, 640, 3), np.uint8)
    f[:, :] = (110, 100, 95)
    cv2.circle(f, (400, 320), 13, (0, 100, 255), -1)
    return f


def test_add_buoys_appends_a_real_buoy():
    ov = _overlay()
    ov._names = COCO_SUBSET
    ov._buoy_active = True
    out = ov._add_buoys(_lake_with_buoy(), [])
    assert [d[4] for d in out] == ["buoy"]


def test_add_buoys_keeps_existing_detections_alongside():
    ov = _overlay()
    ov._buoy_active = True
    person = (10, 400, 60, 460, "person", 0.8)
    out = ov._add_buoys(_lake_with_buoy(), [person])
    assert person in out
    assert "buoy" in [d[4] for d in out]


def test_a_sub_threshold_yolo_box_does_not_suppress_a_buoy():
    """Regression: suppression must only consider boxes that will survive the
    per-class floor. A boat at 0.32 (floor 0.40) gets dropped by _infer, so it
    must not take a real buoy down with it."""
    ov = _overlay(conf=0.40)
    ov._buoy_active = True
    weak = (360, 280, 450, 370, "boat", 0.32)      # covers the blob, but too weak
    out = ov._add_buoys(_lake_with_buoy(), [weak])
    assert "buoy" in [d[4] for d in out]


def test_a_confident_overlapping_box_still_suppresses_the_buoy():
    """The safety rule must still hold for boxes that DO survive the floor."""
    ov = _overlay(conf=0.40)
    ov._buoy_active = True
    strong = (360, 280, 450, 370, "person", 0.85)
    out = ov._add_buoys(_lake_with_buoy(), [strong])
    assert "buoy" not in [d[4] for d in out]
