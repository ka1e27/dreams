"""The drive-ESC bi-directional (3D) mode safety gate — firmware/boat-pico/escs.py.

Why this gate exists (bench incident, 2026-07-31): `escs.py` maps duty 0.0 to a
1.5 ms pulse and calls it "neutral", which is only true for an ESC in
bi-directional / 3D mode. A stock **normal-mode** ESC reads that same 1.5 ms as
~50 % throttle, so it refuses to arm at power-up and — once armed via its true
zero (1.000 ms) — treats every "stop" the firmware can express as half throttle.
That includes `escs.stop()`, `motor_control.estop()` and the heartbeat watchdog,
i.e. every safety path on the boat commands the motor to spin.

These tests run the **real firmware modules** on CPython with `machine` stubbed,
so they check the shipped code rather than a reimplementation.
"""
from __future__ import annotations

import importlib
import pathlib
import sys
import types

import pytest

FW = pathlib.Path(__file__).resolve().parents[2] / "firmware" / "boat-pico"


class _FakePWM:
    """Records what was actually written to the pin — the thing under test."""

    def __init__(self, pin):
        self.pin = pin
        self.writes: list[int] = []
        self._freq = 0

    def freq(self, hz=None):
        if hz is None:
            return self._freq
        self._freq = hz

    def duty_u16(self, v=None):
        if v is None:
            return self.writes[-1] if self.writes else 0
        self.writes.append(v)


@pytest.fixture
def fw():
    """Import the real escs + motor_control with MicroPython bits stubbed out."""
    machine = types.ModuleType("machine")
    machine.Pin = lambda n, *a, **k: n
    machine.PWM = _FakePWM
    esc_telem = types.ModuleType("esc_telem")
    for name in ("temperature", "current", "voltage", "erpm"):
        setattr(esc_telem, name, lambda *a, **k: None)
    esc_telem.max_temp = lambda *a, **k: 0.0
    esc_telem.is_fresh = lambda *a, **k: False

    saved = {k: sys.modules.get(k) for k in ("machine", "esc_telem", "escs", "motor_control")}
    sys.modules["machine"] = machine
    sys.modules["esc_telem"] = esc_telem
    sys.modules.pop("escs", None)
    sys.modules.pop("motor_control", None)
    sys.path.insert(0, str(FW))
    try:
        escs = importlib.import_module("escs")
        motor_control = importlib.import_module("motor_control")
        escs.init()
        yield escs, motor_control
    finally:
        sys.path.remove(str(FW))
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v


def _confirm(escs, left=True, right=True):
    escs.BIDIR_CONFIRMED[escs.LEFT] = left
    escs.BIDIR_CONFIRMED[escs.RIGHT] = right


# ---- the shipped default ---------------------------------------------------


def test_ships_unconfirmed_so_a_fresh_flash_cannot_arm(fw):
    """Fail-safe default: neither ESC is trusted until someone says so."""
    escs, _ = fw
    assert escs.bidir_ok() is False
    assert set(escs.unconfirmed()) == {"LEFT/AM32", "RIGHT/BLHeli32"}


def test_gate_is_all_or_nothing(fw):
    """One good ESC does not make a mixed pair safe — there is no shared stop pulse."""
    escs, _ = fw
    _confirm(escs, left=True, right=False)
    assert escs.bidir_ok() is False
    assert escs.unconfirmed() == ["RIGHT/BLHeli32"]
    _confirm(escs, left=False, right=True)
    assert escs.bidir_ok() is False
    assert escs.unconfirmed() == ["LEFT/AM32"]


# ---- the hard floor in set_duty -------------------------------------------


@pytest.mark.parametrize("duty", [-1.0, -0.5, -0.05, 0.05, 0.5, 1.0])
def test_unconfirmed_emits_only_neutral(fw, duty):
    escs, _ = fw
    pwm = escs._pwm[escs.LEFT]
    pwm.writes.clear()
    escs.set_duty(escs.LEFT, duty)
    assert pwm.writes == [escs.STOP_PWM]


def test_unconfirmed_never_emits_the_arming_pulse(fw):
    """The regression that matters: 1.000 ms is what armed the BLHeli-32."""
    escs, _ = fw
    for mid in (escs.LEFT, escs.RIGHT):
        escs._pwm[mid].writes.clear()
    for duty in (d / 20.0 for d in range(-20, 21)):
        escs.set_duty(escs.LEFT, duty)
        escs.set_duty(escs.RIGHT, duty)
    for mid in (escs.LEFT, escs.RIGHT):
        assert escs.MIN_PWM not in escs._pwm[mid].writes
        assert set(escs._pwm[mid].writes) == {escs.STOP_PWM}


def test_confirmed_passes_the_real_pulse_through(fw):
    escs, _ = fw
    _confirm(escs)
    pwm = escs._pwm[escs.LEFT]
    for duty, expect in ((0.0, escs.STOP_PWM), (1.0, escs.MAX_PWM), (-1.0, escs.MIN_PWM)):
        pwm.writes.clear()
        escs.set_duty(escs.LEFT, duty)
        assert pwm.writes == [expect]


def test_init_arms_at_neutral_even_when_unconfirmed(fw):
    """init() must still park the ESCs at a defined pulse, not leave them floating."""
    escs, _ = fw
    assert escs._pwm[escs.LEFT].writes[-1] == escs.STOP_PWM
    assert escs._pwm[escs.RIGHT].writes[-1] == escs.STOP_PWM


# ---- the command paths -----------------------------------------------------


def test_set_throttle_naks_with_esc_unsafe(fw):
    escs, mc = fw
    assert mc.set_throttle(30, 30) == (False, "ESC_UNSAFE")
    assert mc.get_speeds()[:2] == (0, 0)


def test_zero_throttle_is_refused_too(fw):
    """0 is not a stop for a normal-mode ESC, so it must not be treated as harmless."""
    _, mc = fw
    assert mc.set_throttle(0, 0) == (False, "ESC_UNSAFE")


def test_sbus_path_cannot_route_around_the_gate(fw):
    escs, mc = fw
    mc.set_throttle_rc(80, 80)
    assert mc.get_speeds()[:2] == (0, 0)


def test_estop_still_outranks_the_gate(fw):
    """ESTOP must keep its own distinct reason — it is the more urgent diagnosis."""
    escs, mc = fw
    mc.estop()
    assert mc.set_throttle(10, 10) == (False, "ESTOP")
    mc.resume()


def test_confirmed_restores_normal_throttle(fw):
    escs, mc = fw
    _confirm(escs)
    assert mc.set_throttle(40, -20) == (True, None)
    assert mc.get_speeds()[:2] == (40, -20)
    mc.set_throttle(0, 0)


def test_update_drives_esc_when_confirmed(fw):
    escs, mc = fw
    _confirm(escs)
    mc.set_throttle(100, 0)
    escs._pwm[escs.LEFT].writes.clear()
    mc.update()
    assert escs._pwm[escs.LEFT].writes[-1] > escs.STOP_PWM
    mc.set_throttle(0, 0)


def test_update_is_inert_while_unconfirmed(fw):
    escs, mc = fw
    _confirm(escs)
    mc.set_throttle(100, 100)          # get a non-zero command latched in
    _confirm(escs, left=False, right=False)   # ...then lose confirmation
    for mid in (escs.LEFT, escs.RIGHT):
        escs._pwm[mid].writes.clear()
    mc.update()
    for mid in (escs.LEFT, escs.RIGHT):
        assert set(escs._pwm[mid].writes) == {escs.STOP_PWM}
