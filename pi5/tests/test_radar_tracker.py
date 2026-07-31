"""RadarTracker aiming + lock-threshold tests.

Covers the two 2026-07-29 fixes:
  * the bbox→bearing law is ABSOLUTE about the bow, not relative to wherever the
    bar currently is (the old law diverged on a fixed-forward camera and walked
    the bar into an end stop — "the stepper rotates the wrong way for tracking");
  * ``min_track_conf``, the tracker's own lock gate, separate from the overlay's
    CONF threshold.

No GPIO: a fake stepper records what it was asked to do, so these run anywhere.
"""
import pytest

from pi5.cv.radar_tracker import RadarTracker


class FakeStepper:
    """Minimal stand-in — records rotate_to calls and integrates position."""

    def __init__(self, angle: float = 0.0, min_deg: float = 0.0, max_deg: float = 360.0):
        self._angle = angle
        self.min_deg, self.max_deg = min_deg, max_deg
        self.calls: list[float] = []
        self.scanning = False

    def get_position_degrees(self) -> float:
        return self._angle

    def rotate_to(self, deg: float, speed=None) -> None:
        self.calls.append(deg)
        self._angle = max(self.min_deg, min(self.max_deg, deg))

    def status(self) -> dict:
        return {"available": True, "angle": self._angle, "mock": True,
                "limits": [self.min_deg, self.max_deg], "has_slip_ring": False,
                "invert_direction": False}

    def stop_scan(self) -> None:
        self.scanning = False

    def maybe_auto_sleep(self) -> bool:
        self.slept = True
        return True


class FakeOverlay:
    def __init__(self, boxes=(), right=()):
        self._boxes = list(boxes)
        self.right = list(right)     # right-eye boxes; empty = single-camera

    def boxes(self):
        return self._boxes

    def boxes_right(self):
        return self.right


def _box(cx, label="boat", conf=0.9, w=40):
    """A box centred on pixel ``cx``."""
    return (cx - w / 2, 100, cx + w / 2, 160, label, conf, True)


def _tracker(**kw):
    kw.setdefault("fov_deg", 75.0)
    kw.setdefault("frame_width", 640)
    kw.setdefault("sweep_min_deg", 0.0)
    kw.setdefault("sweep_max_deg", 180.0)
    # SCAN, not the SLEEP default: these tests are about hunting behaviour, and
    # no_lock_reason is deliberately suppressed outside SCAN/TRACK where it goes
    # stale.
    kw.setdefault("initial_mode", "SCAN")
    stepper = kw.pop("stepper", None) or FakeStepper()
    return RadarTracker(stepper, FakeOverlay(), **kw), stepper


# ---- the centring loop --------------------------------------------------- #
# The cameras ride ON the bar (builder, 2026-07-30), so this is a closed loop:
# nudge the bar by the target's offset from frame centre, the cameras turn with
# it, the offset shrinks. Stop inside the deadband.

def test_offset_is_zero_for_a_centred_target():
    t, _ = _tracker()
    assert t._target_offset_deg(_box(320)) == 0.0


def test_offset_at_the_frame_edges_is_half_the_fov():
    t, _ = _tracker()
    assert t._target_offset_deg(_box(640)) == 37.5      # right edge, + = starboard
    assert t._target_offset_deg(_box(0)) == -37.5       # left edge


def test_invert_tracking_mirrors_the_offset():
    t, _ = _tracker(invert_tracking=True)
    assert t._target_offset_deg(_box(640)) == -37.5
    assert t._target_offset_deg(_box(0)) == 37.5
    assert t._target_offset_deg(_box(320)) == 0.0       # centre is unmoved either way


def test_a_centred_target_commands_no_movement():
    t, stepper = _tracker()
    t._step_toward(_box(320))
    assert stepper.calls == []
    assert t._centered is True


def test_inside_the_deadband_counts_as_centred():
    t, stepper = _tracker(center_deadband_deg=5.0)
    t._step_toward(_box(340))          # ~2.3° off — within the deadband
    assert stepper.calls == []
    assert t._centered is True


def test_a_target_on_the_left_moves_the_bar_left():
    t, stepper = _tracker()
    stepper._angle = 40.0
    t._step_toward(_box(100))
    assert stepper.calls and stepper.calls[0] < 40.0


def test_a_target_on_the_right_moves_the_bar_right():
    t, stepper = _tracker()
    stepper._angle = 40.0
    t._step_toward(_box(560))
    assert stepper.calls and stepper.calls[0] > 40.0


def test_the_step_is_relative_to_wherever_the_bar_is():
    """Camera-on-bar: the same in-frame offset is the same *correction*, applied
    from whatever angle the bar currently holds."""
    t, stepper = _tracker()
    stepper._angle = 0.0
    t._step_toward(_box(480))
    first_delta = stepper.calls[-1] - 0.0
    stepper._angle = 120.0
    t._last_offset = None
    t._step_toward(_box(480))
    assert stepper.calls[-1] - 120.0 == pytest.approx(first_delta)


def test_the_loop_converges_on_a_bar_mounted_camera():
    """Simulate the real feedback: as the bar turns, the target slides toward
    frame centre. The loop must settle inside the deadband, not oscillate."""
    t, stepper = _tracker()
    cx = 600.0                                  # target starts far right
    for _ in range(40):
        box = _box(cx)
        before = stepper.get_position_degrees()
        t._step_toward(box)
        moved = stepper.get_position_degrees() - before
        # cameras ride the bar: turning right slides the target left in frame
        cx -= moved / (t.fov_deg / 2.0) * (t.frame_width / 2.0)
    assert abs(t._target_offset_deg(_box(cx))) <= t.center_deadband
    assert t._centered is True


def test_a_single_correction_is_capped():
    t, stepper = _tracker(max_step_deg=5.0, track_gain=1.0)
    stepper._angle = 0.0
    t._step_toward(_box(640))                   # asks for +37.5
    assert stepper.calls[-1] == pytest.approx(5.0)


# ---- speed curve ---------------------------------------------------------- #

def test_speed_is_lowest_at_centre_and_highest_at_the_edge():
    t, _ = _tracker(track_speed_rpm=8.0, track_speed_min_rpm=1.5)
    assert t._speed_for(0.0) == pytest.approx(1.5)
    assert t._speed_for(37.5) == pytest.approx(8.0)


def test_speed_rises_monotonically_with_the_offset():
    t, _ = _tracker(track_speed_rpm=8.0, track_speed_min_rpm=1.5)
    speeds = [t._speed_for(o) for o in (0, 5, 10, 20, 30, 37.5)]
    assert speeds == sorted(speeds)
    assert speeds[0] < speeds[-1]


def test_speed_is_symmetric_and_clamped_beyond_the_edge():
    t, _ = _tracker(track_speed_rpm=8.0, track_speed_min_rpm=1.5)
    assert t._speed_for(-20.0) == t._speed_for(20.0)
    assert t._speed_for(400.0) == pytest.approx(8.0)     # never exceeds the max


# ---- full 360, no further ------------------------------------------------- #

def test_tracking_can_reach_any_angle_in_a_full_turn():
    t, stepper = _tracker(stepper=FakeStepper(min_deg=-180.0, max_deg=180.0),
                          max_step_deg=180.0, track_gain=1.0)
    for start in (-179.0, -90.0, 0.0, 90.0, 179.0):
        stepper._angle = start
        t._last_offset = None
        t._step_toward(_box(640))
        assert -180.0 <= stepper.get_position_degrees() <= 180.0


def test_tracking_never_winds_past_one_full_turn():
    t, stepper = _tracker(stepper=FakeStepper(min_deg=-180.0, max_deg=180.0))
    stepper._angle = 175.0
    for _ in range(20):                          # keep pushing starboard
        t._last_offset = None
        t._step_toward(_box(640))
    assert stepper.get_position_degrees() == 180.0     # parks at the stop
    stepper._angle = -175.0
    for _ in range(20):
        t._last_offset = None
        t._step_toward(_box(0))
    assert stepper.get_position_degrees() == -180.0


# ---- median across both cameras ------------------------------------------- #

def test_one_camera_uses_that_camera_alone():
    t, _ = _tracker()
    assert t._target_offset_deg(_box(480)) == pytest.approx(18.75)


def test_two_cameras_median_their_box_centres():
    t, _ = _tracker()
    t.overlay = FakeOverlay([_box(480)])
    t.overlay.right = [_box(520)]                # same object, stereo disparity
    assert t._target_offset_deg(_box(480)) == pytest.approx(
        (480 + 520) / 2.0 / 320.0 * 37.5 - 37.5)


def test_a_right_box_of_a_different_class_is_not_paired():
    t, _ = _tracker()
    t.overlay = FakeOverlay([_box(480, "person")])
    t.overlay.right = [_box(520, "boat")]
    assert t._target_offset_deg(_box(480, "person")) == pytest.approx(18.75)


def test_a_right_box_at_a_different_height_is_not_paired():
    t, _ = _tracker()
    t.overlay = FakeOverlay([_box(480)])
    mate = list(_box(520))
    mate[1] += 400          # far below the left box — not the same object
    mate[3] += 400
    t.overlay.right = [tuple(mate)]
    assert t._target_offset_deg(_box(480)) == pytest.approx(18.75)


# ---- velocity feedforward ------------------------------------------------- #
# A position-only loop reacts to error already opened, so a fast target trails
# further and further behind until it leaves the frame. The tracker measures the
# target's angular rate and aims ahead of it.

def _moving_target(t, cx_series, dt=0.1):
    """Feed a sequence of box positions as successive detections.

    Timestamps are rewritten deterministically instead of sleeping, and are laid
    out so the LAST sample lands at ~now — a subsequent real _note_bearing (from
    _step_toward) then appends after them rather than before, keeping the series
    monotonic.
    """
    import time as _t
    n = len(cx_series)
    base = _t.monotonic() - (n - 1) * dt
    for i, cx in enumerate(cx_series):
        box = _box(cx)
        t._note_bearing(box, t._target_offset_deg(box))
        if t._bearing_hist:
            _, bearing = t._bearing_hist[-1]
            t._bearing_hist[-1] = (base + i * dt, bearing)
    with t._lock:
        t._target_rate = t._fit_rate()
    return t._target_rate


def test_a_stationary_target_has_no_rate():
    t, _ = _tracker()
    assert _moving_target(t, [320] * 6) == pytest.approx(0.0, abs=0.5)


def test_rate_is_positive_for_a_target_drifting_starboard():
    t, _ = _tracker()
    # 40 px per 0.1 s across a 640 px / 75° frame = 4.69°/0.1s = 46.9°/s
    rate = _moving_target(t, [320, 360, 400, 440, 480, 520])
    assert rate == pytest.approx(46.9, rel=0.05)


def test_rate_is_negative_for_a_target_drifting_port():
    t, _ = _tracker()
    assert _moving_target(t, [520, 480, 440, 400, 360, 320]) < -1.0


def test_rate_ignores_repeat_detections_of_the_same_box():
    """The tracker loop runs faster than the detector, so most ticks re-read the
    SAME box. Sampling those would read the bar's own motion as target motion —
    a feedforward loop feeding on itself."""
    t, stepper = _tracker()
    box = _box(480)
    for _ in range(8):
        stepper._angle += 5.0            # bar slews; detection is unchanged
        t._note_bearing(box, t._target_offset_deg(box))
    assert len(t._bearing_hist) == 1
    assert t._target_rate == 0.0


def test_rate_is_measured_on_bearing_not_pixels():
    """Bar turns, target stationary in the world: the box slides across the
    frame, but the bearing — and so the rate — must stay put."""
    t, stepper = _tracker()
    import time as _t
    base = _t.monotonic()
    for i in range(6):
        # bar turns +5° per sample; target holds a fixed world bearing, so its
        # in-frame offset shrinks by exactly the same 5°.
        stepper._angle = i * 5.0
        cx = 320 + (30.0 - i * 5.0) / 37.5 * 320.0
        box = _box(cx)
        t._note_bearing(box, t._target_offset_deg(box))
        ts, bearing = t._bearing_hist[-1]
        t._bearing_hist[-1] = (base + i * 0.1, bearing)
    with t._lock:
        t._target_rate = t._fit_rate()
    assert t._target_rate == pytest.approx(0.0, abs=1.0)


STARBOARD_RUN = [140, 180, 220, 260, 300]     # drifting right, ~47°/s
PORT_RUN = [500, 460, 420, 380, 340]          # drifting left


def test_lead_pushes_the_step_ahead_of_a_moving_target():
    t, stepper = _tracker(lead_seconds=0.5)
    _moving_target(t, STARBOARD_RUN)
    assert t._target_rate > 10.0
    t._step_toward(_box(380))             # motion continues, clear of the deadband
    with_lead = stepper.calls[-1]

    t2, s2 = _tracker(lead_seconds=0.0)   # identical, feedforward off
    _moving_target(t2, STARBOARD_RUN)
    t2._step_toward(_box(380))
    assert with_lead > s2.calls[-1]       # aimed further ahead


def test_lead_is_signed_with_the_direction_of_travel():
    t, stepper = _tracker(lead_seconds=0.5)
    _moving_target(t, PORT_RUN)
    assert t._target_rate < -10.0
    t._step_toward(_box(380))             # still offset to starboard of centre

    t2, s2 = _tracker(lead_seconds=0.0)
    _moving_target(t2, PORT_RUN)
    t2._step_toward(_box(380))
    assert stepper.calls[-1] < s2.calls[-1]   # pulled back toward port


def test_a_fast_target_crossing_centre_is_not_treated_as_settled():
    """Offset ~0 with the target sailing through is exactly where a
    position-only loop stops dead and loses it."""
    t, stepper = _tracker(lead_seconds=0.5)
    _moving_target(t, [160, 200, 240, 280, 310])
    assert t._target_rate > 10.0
    t._step_toward(_box(320))             # dead centre, still moving fast
    assert t._centered is False
    assert stepper.calls                   # …and it kept moving


def test_a_slow_target_at_centre_still_settles():
    t, stepper = _tracker(lead_seconds=0.5)
    _moving_target(t, [318, 319, 320, 320, 321])   # essentially parked
    t._step_toward(_box(321))
    assert t._centered is True
    assert stepper.calls == []


# ---- speed follows the rate too ------------------------------------------- #

def test_rate_raises_the_slew_speed_near_centre():
    """Scaling speed on error alone gives a fast target crossing the middle the
    SLOWEST bar exactly when it needs the quickest."""
    t, _ = _tracker(track_speed_rpm=8.0, track_speed_min_rpm=1.5)
    assert t._speed_for(0.0, 0.0) == pytest.approx(1.5)
    assert t._speed_for(0.0, 40.0) > 5.0


def test_speed_never_exceeds_the_motor_limit():
    t, stepper = _tracker(track_speed_rpm=8.0)
    stepper.max_speed_rpm = 10.0
    assert t._speed_for(0.0, 600.0) == pytest.approx(10.0)


def test_rpm_for_rate_converts_degrees_per_second():
    t, _ = _tracker(velocity_speed_margin=1.0)
    assert t._rpm_for_rate(360.0) == pytest.approx(60.0)   # 360°/s = 60 rpm
    assert t._rpm_for_rate(-60.0) == pytest.approx(10.0)   # sign-independent


def test_rate_history_resets_when_the_target_is_lost():
    t, _ = _tracker(lost_timeout_s=0.0)
    _moving_target(t, [320, 360, 400, 440, 480, 520])
    assert t._target_rate != 0.0
    t.set_mode("TRACK")
    t.overlay = FakeOverlay([])
    t._last_seen = 0.0
    t._do_track()
    assert t._target_rate == 0.0          # don't lead on a rate we can't confirm


# ---- divergence backstop -------------------------------------------------- #

def test_a_diverging_offset_names_a_probable_direction_fault():
    """A wrong DIR polarity makes this loop diverge — the offset grows with every
    correction. Warn and name the likely cause; three bench sessions went to
    diagnosing this from the outside."""
    t, _ = _tracker()
    for cx in (330, 360, 400, 450, 500, 550, 600, 630):   # steadily worse
        t._step_toward(_box(cx))
    assert "wrong way" in t._track_warning


def test_a_target_beyond_the_motors_reach_is_named_as_such():
    """Same symptom — offset growing — but the opposite fix, so the message has
    to distinguish them."""
    t, stepper = _tracker()
    stepper.max_speed_rpm = 1.0                 # ~6°/s, hopelessly slow
    _moving_target(t, [320, 400, 480, 560, 620])
    for cx in (400, 460, 520, 580, 630, 638):
        t._step_toward(_box(cx))
    assert "faster than the bar can slew" in t._track_warning


def test_a_converging_target_raises_no_warning():
    t, _ = _tracker()
    for cx in (600, 560, 500, 440, 380, 330):       # offset shrinking each tick
        t._step_toward(_box(cx))
    assert t._track_warning == ""


def test_the_startup_transient_is_not_mistaken_for_divergence():
    """The offset legitimately opens up before the rate estimate has filled its
    window. Warning there abandoned targets the bar could easily hold."""
    t, _ = _tracker()
    t._step_toward(_box(400))
    t._step_toward(_box(500))
    t._step_toward(_box(620))
    assert t._track_warning == ""



def test_center_points_at_the_bow_not_the_axis_zero():
    t, stepper = _tracker(bow_deg=90.0)
    t.center()
    assert t._goto == 90.0


# ---- lock threshold ------------------------------------------------------- #

def test_default_threshold_locks_onto_anything():
    t, _ = _tracker()
    t.overlay = FakeOverlay([_box(320, conf=0.11)])
    assert t._best_target() is not None


def test_threshold_rejects_weak_targets():
    t, _ = _tracker(min_track_conf=0.5)
    t.overlay = FakeOverlay([_box(320, conf=0.31)])
    assert t._best_target() is None


def test_threshold_keeps_the_best_qualifying_target():
    t, _ = _tracker(min_track_conf=0.5)
    t.overlay = FakeOverlay([_box(100, conf=0.40), _box(500, conf=0.80),
                             _box(300, conf=0.60)])
    best = t._best_target()
    assert best is not None and best[5] == 0.80


def test_set_min_track_conf_clamps_and_reports():
    t, _ = _tracker()
    assert t.set_min_track_conf(2.0) == 1.0
    assert t.set_min_track_conf(-1.0) == 0.0
    assert t.set_min_track_conf(0.65) == 0.65
    assert t.status()["track_conf"] == 0.65


def test_raising_the_threshold_drops_a_now_unqualified_lock():
    """The operator must see the bar release immediately, not after the 3 s
    lost-timeout."""
    t, _ = _tracker()
    t._target_locked = True
    t._target_info = {"label": "boat", "conf": 0.42}
    t.set_min_track_conf(0.60)
    assert t.status()["target_locked"] is False
    assert t.status()["target"] is None


def test_raising_the_threshold_keeps_a_still_good_lock():
    t, _ = _tracker()
    t._target_locked = True
    t._target_info = {"label": "boat", "conf": 0.88}
    t.set_min_track_conf(0.60)
    assert t.status()["target_locked"] is True


def test_threshold_applies_to_the_operator_chosen_class_too():
    t, _ = _tracker(min_track_conf=0.5)
    t.set_track_class("kayak")
    t.overlay = FakeOverlay([_box(320, label="kayak", conf=0.33)])
    assert t._best_target() is None
    t.overlay = FakeOverlay([_box(320, label="kayak", conf=0.77)])
    assert t._best_target() is not None


# ---- TRACK-only pin ------------------------------------------------------- #
# "It just kept scanning even while I was in frame" (bench 2026-07-30). TRACK was
# never sticky: a dropout longer than lost_timeout_s dropped it back to SCAN, and
# the vision pipeline resumed SCAN on its own whenever threat assessment went
# quiet. The operator had no way to say "stop sweeping, just track".

def test_auto_rescan_is_on_by_default():
    t, _ = _tracker()
    assert t.status()["auto_rescan"] is True


def test_pin_keeps_track_mode_through_a_dropout():
    t, _ = _tracker(lost_timeout_s=0.0)
    t.set_auto_rescan(False)
    t.overlay = FakeOverlay([])          # target vanishes
    t._last_seen = 0.0                   # …and has been gone a while
    t._do_track()
    assert t.status()["mode"] == "TRACK"
    assert t.status()["target_locked"] is False   # honest: holding, not locked


def test_without_the_pin_a_dropout_still_falls_back_to_scan():
    t, _ = _tracker(lost_timeout_s=0.0)
    t.set_mode("TRACK")
    t.overlay = FakeOverlay([])
    t._last_seen = 0.0
    t._do_track()
    assert t.status()["mode"] == "SCAN"


def test_pin_ignores_an_automatic_scan_from_the_pipeline():
    t, _ = _tracker()
    t.set_auto_rescan(False)
    t.set_mode("SCAN", automatic=True)
    assert t.status()["mode"] == "TRACK"


def test_an_operator_scan_releases_the_pin():
    t, _ = _tracker()
    t.set_auto_rescan(False)
    t.set_mode("SCAN")                   # operator pressed SCAN
    assert t.status()["mode"] == "SCAN"
    assert t.status()["auto_rescan"] is True


def test_pin_drops_a_stale_pipeline_class_lock():
    """A pipeline pin that outlives its object narrows the tracker to a class
    that's no longer in view — everything else becomes invisible to it."""
    t, _ = _tracker()
    t.set_track_class("buoy", automatic=True)
    assert t.status()["track_class"] == "buoy"
    t.set_auto_rescan(False)
    assert t.status()["track_class"] == ""      # back to priority_classes


def test_an_operator_class_pick_outranks_the_pipeline():
    t, _ = _tracker()
    t.set_track_class("person")                  # operator picked it
    t.set_track_class("buoy", automatic=True)    # pipeline tries to retarget
    assert t.status()["track_class"] == "person"


# ---- why isn't it locked? ------------------------------------------------- #

def test_no_lock_reason_names_the_confidence_floor():
    t, _ = _tracker(min_track_conf=0.75)
    t.overlay = FakeOverlay([_box(320, "person", 0.42)])
    assert t._best_target() is None
    r = t.status()["no_lock_reason"]
    assert "person" in r and "0.42" in r and "0.75" in r


def test_no_lock_reason_names_the_class_mismatch():
    t, _ = _tracker()
    t.overlay = FakeOverlay([_box(320, "sports ball", 0.9)])
    assert t._best_target() is None
    r = t.status()["no_lock_reason"]
    assert "sports ball" in r and "person" in r     # seeing X, want Y


def test_no_lock_reason_for_an_empty_frame():
    t, _ = _tracker()
    t.overlay = FakeOverlay([])
    assert t._best_target() is None
    assert t.status()["no_lock_reason"] == "nothing detected"


def test_no_lock_reason_clears_once_locked():
    t, _ = _tracker()
    t.overlay = FakeOverlay([_box(320, "person", 0.9)])
    t._best_target()
    t._target_locked = True
    assert t.status()["no_lock_reason"] == ""


def test_class_matching_is_case_insensitive():
    t, _ = _tracker()
    t.overlay = FakeOverlay([_box(320, "Person", 0.9)])
    assert t._best_target() is not None


def test_status_exposes_the_aiming_configuration():
    t, _ = _tracker(bow_deg=90.0, invert_tracking=True, min_track_conf=0.3)
    s = t.status()
    assert s["bow_deg"] == 90.0
    assert s["invert_tracking"] is True
    assert s["track_conf"] == 0.3
