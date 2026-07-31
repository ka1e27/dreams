"""StepperMotor DIR-polarity tests (``invert_direction``).

Runs in the driver's mock mode, so the pin writes are captured through ``_w``
rather than a real A4988 — the point under test is which level lands on DIR for
a given commanded direction, and that the position accounting is *not* mirrored
along with it.
"""
from pi5.cv.stepper import StepperMotor


def _motor(**kw):
    """A pinless motor — every _w() is a no-op, so only bookkeeping is exercised."""
    kw.setdefault("steps_per_rev", 400)
    kw.setdefault("auto_sleep_s", 1e6)
    m = StepperMotor(**kw)
    m.mock = True                    # never touch GPIO even on a Pi
    m._step = m._dir = m._enable = m._sleep = m._reset = None
    return m


class _Pin:
    """Stand-in for a gpiozero OutputDevice that just records levels."""

    def __init__(self):
        self.value = 0
        self.history: list[int] = []

    def __setattr__(self, name, val):
        if name == "value":
            self.__dict__.setdefault("history", []).append(int(val))
        object.__setattr__(self, name, val)


def _motor_with_dir_pin(invert: bool):
    m = StepperMotor(steps_per_rev=400, auto_sleep_s=1e6, max_deg=360.0,
                     invert_direction=invert)
    m.mock = True
    dir_pin = _Pin()
    m._step = _Pin()
    m._dir = dir_pin
    m._enable = _Pin()
    m._sleep = _Pin()
    m._reset = None
    m._asleep = False
    m._enabled = True
    return m, dir_pin


def test_default_polarity_is_unchanged():
    m, dir_pin = _motor_with_dir_pin(invert=False)
    m.step(2, direction=1, delay_us=1)
    assert dir_pin.history[-1] == 1
    m.step(2, direction=-1, delay_us=1)
    assert dir_pin.history[-1] == 0


def test_invert_direction_flips_the_dir_pin():
    m, dir_pin = _motor_with_dir_pin(invert=True)
    m.step(2, direction=1, delay_us=1)
    assert dir_pin.history[-1] == 0
    m.step(2, direction=-1, delay_us=1)
    assert dir_pin.history[-1] == 1


def test_invert_direction_does_not_mirror_position_accounting():
    """The pin flips, the bookkeeping does not — 90° must stay the same physical
    place, reached by turning the other way."""
    plain, _ = _motor_with_dir_pin(invert=False)
    inverted, _ = _motor_with_dir_pin(invert=True)
    for m in (plain, inverted):
        m.step(10, direction=1, delay_us=1)
    assert plain.get_position_degrees() == inverted.get_position_degrees()
    assert plain.get_position_degrees() == 9.0     # 10 steps × 0.9°


def test_status_reports_the_polarity():
    assert _motor(invert_direction=True).status()["invert_direction"] is True
    assert _motor().status()["invert_direction"] is False


def test_mock_mode_tolerates_no_pins():
    """Off-Pi (mock) the flag must be inert, not crash on a None DIR device."""
    m = _motor(invert_direction=True)
    m.step(4, direction=1, delay_us=1)
    assert m.get_position_degrees() == 3.6
