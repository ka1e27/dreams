"""Tests for reactive obstacle avoidance — the pure steer-away rule and its
integration into the vision pipeline's navigator override."""
from __future__ import annotations

import types

import numpy as np

from pi5.cv.avoidance import AvoidanceConfig, AvoidanceController, reactive_avoidance
from pi5.cv.pipeline import SurveyVisionPipeline


# --------------------------------------------------------------------------- #
# Pure rule
# --------------------------------------------------------------------------- #
def test_none_distance_no_override():
    assert reactive_avoidance(0.0, None) is None


def test_beyond_trigger_no_override():
    cfg = AvoidanceConfig(trigger_distance_m=8.0)
    assert reactive_avoidance(0.0, 20.0, cfg) is None


def test_starboard_threat_bears_to_port():
    # Threat 30° to starboard, inside the envelope → boat bears port (right motor
    # faster than left).
    left, right = reactive_avoidance(30.0, 5.0)
    assert right > left


def test_port_threat_bears_to_starboard():
    left, right = reactive_avoidance(-30.0, 5.0)
    assert left > right


def test_head_on_passes_to_starboard():
    # Dead-ahead threat → COLREGS: alter to starboard (left motor faster).
    left, right = reactive_avoidance(0.0, 5.0)
    assert left > right


def test_closer_is_more_aggressive():
    cfg = AvoidanceConfig(trigger_distance_m=8.0, critical_distance_m=3.0)
    far = reactive_avoidance(30.0, 7.0, cfg)
    near = reactive_avoidance(30.0, 3.0, cfg)
    # Differential (steer authority) grows as the threat closes.
    assert abs(near[1] - near[0]) > abs(far[1] - far[0])


def test_output_clamped():
    cfg = AvoidanceConfig(cruise_throttle=90, max_steer=90)
    left, right = reactive_avoidance(0.0, 3.0, cfg)
    assert -100 <= left <= 100 and -100 <= right <= 100


def test_force_side_overrides_bearing():
    cfg = AvoidanceConfig()
    # Threat to starboard would normally steer port (left<right); forcing
    # starboard flips it (left>right).
    left, right = reactive_avoidance(30.0, 5.0, cfg, force_side=1)
    assert left > right


# --------------------------------------------------------------------------- #
# Bug-style controller
# --------------------------------------------------------------------------- #
def test_controller_commits_and_holds_side():
    c = AvoidanceController(AvoidanceConfig())
    o1 = c.update(0.0, 5.0, now=0.0)            # head-on → commit starboard
    assert c.avoiding and c.committed_side == 1
    assert o1[0] > o1[1]                        # steering starboard
    # Bearing flips to read starboard; memoryless reactive would steer port, but
    # the committed controller keeps turning the SAME way (no orbit-inducing flip).
    o2 = c.update(20.0, 5.0, now=0.5)
    assert o2[0] > o2[1]


def test_controller_releases_after_pass():
    c = AvoidanceController(AvoidanceConfig())
    c.update(0.0, 5.0, now=0.0)                 # commit starboard
    # Obstacle swings behind the port beam → we've passed it → release.
    assert c.update(-120.0, 5.0, now=1.0) is None
    assert not c.avoiding


def test_controller_blind_hold_then_release():
    c = AvoidanceController(AvoidanceConfig(), pass_hold_s=3.0)
    c.update(0.0, 5.0, now=0.0)                 # engage
    assert c.update(None, None, now=1.0) is not None   # sight lost — still holding
    assert c.update(None, None, now=5.0) is None       # past hold → release
    assert not c.avoiding


def test_controller_idle_when_out_of_range():
    c = AvoidanceController(AvoidanceConfig(trigger_distance_m=8.0))
    assert c.update(0.0, 20.0, now=0.0) is None
    assert not c.avoiding


# --------------------------------------------------------------------------- #
# Pipeline integration
# --------------------------------------------------------------------------- #
class FakeNavConfig:
    cruise_throttle = 40


class FakeNavigator:
    def __init__(self):
        self._config = FakeNavConfig()
        self.overrides: list[tuple[int, int]] = []

    def set_avoidance_override(self, left, right):
        self.overrides.append((left, right))


class FakeOverlay:
    def __init__(self, boxes=None):
        self.enabled = True
        self.available = True
        self._boxes = boxes or []

    def boxes(self):
        return list(self._boxes)


def _box(label, x1, y1, x2, y2, conf=0.9, dist=None):
    return (x1, y1, x2, y2, label, conf, True, dist)


def _frame(w=160, h=120):
    img = np.full((h, w, 3), (140, 90, 30), dtype=np.uint8)
    return types.SimpleNamespace(left=img, right=None, ts=0.0)


def _pipeline(overlay, nav):
    p = SurveyVisionPipeline(
        camera=None, overlay=overlay, radar=None, navigator=nav,
        config={"reactive_avoidance": {"trigger_distance_m": 8.0,
                                       "critical_distance_m": 3.0}},
        frame_width=160)
    p.segmentation_enabled = False   # force anomaly=1.0 so Tier 2/3 run
    return p


def test_pipeline_engages_avoidance_on_near_vessel():
    nav = FakeNavigator()
    # A vessel dead-ahead, ranged at 4 m (inside the 8 m trigger).
    ov = FakeOverlay([_box("vessel", 60, 40, 100, 110, 0.9, 4.0)])
    p = _pipeline(ov, nav)
    p._process(_frame(), now=100.0)
    assert p._avoiding is True
    assert nav.overrides, "navigator override was never set"
    left, right = nav.overrides[-1]
    assert (left, right) != (0, 0)
    assert p.vision_state()["avoiding"] is True


def test_pipeline_releases_override_when_clear():
    nav = FakeNavigator()
    ov = FakeOverlay([_box("vessel", 60, 40, 100, 110, 0.9, 4.0)])
    p = _pipeline(ov, nav)
    p._process(_frame(), now=100.0)
    assert p._avoiding is True
    # Threat gone; advance past the tracker's lost-TTL (3 s) so it prunes, then
    # the override is released exactly once with (0, 0).
    ov._boxes = []
    p._process(_frame(), now=110.0)
    assert p._avoiding is False
    assert nav.overrides[-1] == (0, 0)


def test_pipeline_no_avoid_for_far_vessel():
    nav = FakeNavigator()
    ov = FakeOverlay([_box("vessel", 60, 40, 100, 110, 0.9, 40.0)])  # 40 m away
    p = _pipeline(ov, nav)
    p._process(_frame(), now=100.0)
    assert p._avoiding is False


def test_avoidance_toggle_releases_override():
    nav = FakeNavigator()
    ov = FakeOverlay([_box("vessel", 60, 40, 100, 110, 0.9, 4.0)])
    p = _pipeline(ov, nav)
    p._process(_frame(), now=100.0)
    assert p._avoiding is True
    p.set_avoidance_enabled(False)
    assert p._avoiding is False
    assert nav.overrides[-1] == (0, 0)
