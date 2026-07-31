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
    # person shifts down with the slider and bottoms out at the 0.01 floor
    # (0.25 - 0.30 would be negative), so inference runs wide open.
    assert ov._infer_conf == pytest.approx(0.01)
    ov.apply_controls({"conf": 0.90})
    # person keeps its 0.15 head start over the slider: 0.90 - 0.15 = 0.75.
    assert ov._infer_conf == pytest.approx(0.75)


# -- the CONF slider as a master control ----------------------------------- #
# Before 2026-07-29 class_conf floors were absolute, so dragging CONF changed
# nothing at all for person / swimmer / surfer / kayak — the operator saw the
# same 0.40-era boxes wherever they put the slider. They are now relative to the
# configured baseline and move with it.

def test_conf_slider_raises_a_tuned_class_floor_too():
    ov = _overlay(conf=0.40, class_conf={"person": 0.25})
    assert ov._passes_conf("person", 0.30) is True
    ov.apply_controls({"conf": 0.90})     # operator drags CONF to the top
    assert ov._passes_conf("person", 0.30) is False
    assert ov._passes_conf("person", 0.80) is True


def test_conf_slider_lowers_a_tuned_class_floor_too():
    ov = _overlay(conf=0.40, class_conf={"person": 0.25})
    assert ov._passes_conf("person", 0.15) is False
    ov.apply_controls({"conf": 0.20})     # "show me everything"
    assert ov._passes_conf("person", 0.15) is True


def test_relative_floors_keep_their_ordering_across_the_range():
    ov = _overlay(conf=0.40, class_conf={"person": 0.25, "kayak": 0.30})
    for slider in (0.15, 0.40, 0.75):
        ov.apply_controls({"conf": slider})
        f = ov.conf_floors()
        assert f["person"] < f["kayak"] <= ov._cfg.conf


def test_absolute_classes_ignore_the_slider():
    """A score that isn't a probability can't be compared to one, so 'buoy'
    keeps a fixed floor however far CONF is dragged."""
    ov = _overlay(conf=0.40, class_conf={"buoy": 0.30, "person": 0.25},
                  class_conf_absolute=["buoy"])
    ov.apply_controls({"conf": 0.90})
    assert ov.conf_floors()["buoy"] == 0.30
    assert ov.conf_floors()["person"] == 0.75
    assert ov._passes_conf("buoy", 0.35) is True    # weakest real buoy survives


def test_floors_stay_inside_a_usable_range():
    ov = _overlay(conf=0.40, class_conf={"person": 0.25})
    ov.apply_controls({"conf": 0.05})
    assert 0.0 < ov.conf_floors()["person"] <= 0.05
    ov.apply_controls({"conf": 0.95})
    assert ov.conf_floors()["person"] < 1.0


def test_controls_exposes_the_resolved_floors():
    ov = _overlay(conf=0.40, class_conf={"person": 0.25},
                  class_conf_absolute=["buoy"])
    c = ov.controls()
    assert c["conf_floors"] == {"person": 0.25}
    assert c["conf_absolute"] == ["buoy"]


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


def test_buoy_stays_more_sensitive_than_everything_else():
    """'buoy' keeps its 0.10 head start at every slider position — but it IS
    governed by the slider. It was briefly pinned absolute, which made the
    classical screen's false positives the one thing an operator couldn't filter
    out (reported from the bench 2026-07-29: "a ton of buoys in a place with no
    buoys, and they still show at 0.75")."""
    ov = _overlay(conf=0.40, class_conf={"buoy": 0.30})
    for slider in (0.40, 0.60, 0.75):
        ov.apply_controls({"conf": slider})
        assert ov.conf_floors()["buoy"] == pytest.approx(slider - 0.10)


def test_dragging_conf_up_filters_weak_buoys_out():
    ov = _overlay(conf=0.40, class_conf={"buoy": 0.30})
    assert ov._passes_conf("buoy", 0.40) is True     # a 0.40 blob at baseline
    ov.apply_controls({"conf": 0.75})
    assert ov._passes_conf("buoy", 0.40) is False    # …gone once CONF is raised
    assert ov._passes_conf("buoy", 0.70) is True     # a strong one survives


# -- the classical buoy screen's operator kill switch ---------------------- #

def test_buoy_screen_can_be_switched_off_at_runtime():
    ov = _overlay()
    ov._names = COCO_SUBSET
    ov._buoy_active = True
    assert ov.controls()["buoy_enabled"] is True
    ov.apply_controls({"buoy_enabled": False})
    assert ov.controls()["buoy_enabled"] is False
    assert ov._add_buoys(None, [("x",)]) == [("x",)]   # screen never runs
    assert "buoy" not in ov.class_names()              # and leaves the picker


def test_buoy_toggle_reports_unavailable_when_the_model_emits_buoy():
    """With a maritime model the screen isn't running at all, so 'enabled' must
    read False regardless of the operator switch — a toggle would be a lie."""
    ov = _overlay()
    ov._names = MARITIME
    ov._buoy_active = False
    c = ov.controls()
    assert c["buoy_available"] is False and c["buoy_enabled"] is False


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
