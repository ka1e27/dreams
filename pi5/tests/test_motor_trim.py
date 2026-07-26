"""Per-motor thrust trim for mismatched (different-Kv) motors."""

from pi5.navigation.navigator import NavConfig, Navigator


def _nav(gl=1.0, gr=1.0):
    return Navigator(pico=None, config=NavConfig(motor_gain_left=gl, motor_gain_right=gr))


def test_trim_noop_at_unity():
    nav = _nav(1.0, 1.0)
    assert nav._trim(40, 40) == (40, 40)
    assert nav._trim(-30, 55) == (-30, 55)


def test_trim_biases_faster_motor_down():
    # Right motor spins hotter (higher Kv) → trim its gain down so equal command
    # (40, 40) sends less to the right, cancelling the crab.
    nav = _nav(1.0, 0.85)
    left, right = nav._trim(40, 40)
    assert left == 40
    assert right == 34            # 40 * 0.85


def test_trim_clamps_to_motor_range():
    nav = _nav(1.5, 1.5)
    left, right = nav._trim(90, -90)
    assert left == 100 and right == -100     # 135 / -135 clamped
