"""Tests for the dashboard's manual (WASD) override.

The mixing is pure and easy; the parts worth real coverage are the ones that
stop the boat when nobody is driving it any more — the dead-man timeout, the
priority over autonomous modes, and the hand-back rules.
"""
from __future__ import annotations

import asyncio

import pytest

from pi5.navigation.navigator import NavConfig, Navigator


class _Tel:
    def __init__(self, lat: float = 0.0, lon: float = 0.0, heading: float = 0.0) -> None:
        self.lat = lat
        self.lon = lon
        self.heading = heading


class FakePico:
    def __init__(self) -> None:
        self.telemetry = _Tel()
        self.throttle_calls: list[tuple[int, int]] = []

    async def set_throttle(self, left: int, right: int):
        self.throttle_calls.append((left, right))
        return None


def _nav(**cfg) -> Navigator:
    return Navigator(pico=FakePico(), config=NavConfig(update_rate_hz=50, **cfg))


class TestMix:
    """manual_mix() — surge/yaw -> (left, right), scaled by the speed cap."""

    def test_ahead_is_symmetric(self):
        nav = _nav()
        nav.enable_manual(True)
        nav.set_manual_speed(100)
        nav.manual_input(1.0, 0.0)
        assert nav.manual_mix() == (100, 100)

    def test_astern_is_negative(self):
        nav = _nav()
        nav.enable_manual(True)
        nav.set_manual_speed(100)
        nav.manual_input(-1.0, 0.0)
        assert nav.manual_mix() == (-100, -100)

    def test_pure_yaw_pivots_in_place(self):
        """A/D with no W/S must counter-rotate — that needs bidirectional ESCs."""
        nav = _nav()
        nav.enable_manual(True)
        nav.set_manual_speed(100)
        nav.manual_input(0.0, 1.0)
        left, right = nav.manual_mix()
        assert left == -right
        assert left > 0            # starboard turn: left ahead, right astern

    def test_speed_cap_scales_output(self):
        nav = _nav()
        nav.enable_manual(True)
        nav.set_manual_speed(40)
        nav.manual_input(1.0, 0.0)
        assert nav.manual_mix() == (40, 40)

    def test_zero_speed_cap_means_no_motion(self):
        nav = _nav()
        nav.enable_manual(True)
        nav.set_manual_speed(0)
        nav.manual_input(1.0, 1.0)
        assert nav.manual_mix() == (0, 0)

    def test_combined_input_clamps_without_distorting_the_turn(self):
        """W+D at full speed must not saturate one side and straighten the turn.

        Naive addition gives (200, 0) -> clamped (100, 0), which is a *different*
        manoeuvre. Scaling the pair preserves the ratio.
        """
        nav = _nav()
        nav.enable_manual(True)
        nav.set_manual_speed(100)
        nav.manual_input(1.0, 1.0)
        left, right = nav.manual_mix()
        assert max(abs(left), abs(right)) == 100
        assert (left, right) == (100, 0)

    def test_inputs_are_clamped(self):
        nav = _nav()
        nav.enable_manual(True)
        nav.set_manual_speed(100)
        nav.manual_input(9.0, -9.0)
        assert nav.manual_mix() == (0, 100)

    def test_speed_is_clamped_to_0_100(self):
        nav = _nav()
        assert nav.set_manual_speed(500) == 100
        assert nav.set_manual_speed(-5) == 0

    def test_input_ignored_when_disarmed(self):
        nav = _nav()
        nav.set_manual_speed(100)
        nav.manual_input(1.0, 0.0)
        assert nav.manual_mix() == (0, 0)


class TestArming:
    def test_arming_cancels_active_navigation(self):
        nav = _nav()
        nav.goto(1.0, 2.0)
        assert nav.state.active is True
        nav.enable_manual(True)
        assert nav.state.active is False
        assert nav.state.target_lat is None

    def test_arming_starts_stopped_and_stale(self):
        """Arming must not inherit a stale command and lurch."""
        nav = _nav()
        nav.enable_manual(True)
        assert nav.manual_mix() == (0, 0)

    def test_goto_hands_control_back(self):
        nav = _nav()
        nav.enable_manual(True)
        nav.manual_input(1.0, 0.0)
        nav.goto(1.0, 2.0)
        assert nav.state.manual is False
        assert nav.state.active is True

    def test_hold_hands_control_back(self):
        nav = _nav()
        nav.enable_manual(True)
        nav.hold(1.0, 2.0)
        assert nav.state.manual is False

    def test_disarm_zeroes_the_stick(self):
        nav = _nav()
        nav.enable_manual(True)
        nav.set_manual_speed(100)
        nav.manual_input(1.0, 1.0)
        nav.enable_manual(False)
        assert nav.manual_mix() == (0, 0)


@pytest.mark.asyncio
class TestLoop:
    async def _run(self, nav: Navigator, ticks: float = 0.12) -> None:
        await nav.start()
        await asyncio.sleep(ticks)
        await nav.stop()

    async def test_fresh_input_drives_the_motors(self):
        nav = _nav()
        pico = nav._pico
        nav.enable_manual(True)
        nav.set_manual_speed(50)
        nav.manual_input(1.0, 0.0)
        await self._run(nav)
        assert (50, 50) in pico.throttle_calls

    async def test_dead_man_zeroes_when_input_goes_quiet(self):
        """The whole safety story: no input for MANUAL_TIMEOUT_S -> motors off."""
        nav = _nav()
        pico = nav._pico
        nav.MANUAL_TIMEOUT_S = 0.02          # keep the test fast
        nav.enable_manual(True)
        nav.set_manual_speed(100)
        nav.manual_input(1.0, 0.0)
        await nav.start()
        await asyncio.sleep(0.01)            # still fresh
        assert (100, 100) in pico.throttle_calls
        await asyncio.sleep(0.10)            # now stale
        await nav.stop()
        assert pico.throttle_calls[-1] == (0, 0)
        assert nav.state.manual_stale is True

    async def test_never_moves_without_any_input(self):
        """Arming alone must not move the boat, even at full speed cap."""
        nav = _nav()
        pico = nav._pico
        nav.enable_manual(True)
        nav.set_manual_speed(100)
        await self._run(nav)
        assert all(c == (0, 0) for c in pico.throttle_calls)

    async def test_manual_outranks_station_keeping(self):
        nav = _nav()
        pico = nav._pico
        nav.hold(0.0, 0.0)
        nav.enable_manual(True)              # arming must win over the hold
        nav.set_manual_speed(100)
        nav.manual_input(-1.0, 0.0)
        await self._run(nav)
        assert (-100, -100) in pico.throttle_calls
        assert nav.state.station_keeping is False

    async def test_motor_trim_is_applied(self):
        """Manual must use the same Kv trim as the autonomous path."""
        nav = _nav(motor_gain_left=1.0, motor_gain_right=0.5)
        pico = nav._pico
        nav.enable_manual(True)
        nav.set_manual_speed(100)
        nav.manual_input(1.0, 0.0)
        await self._run(nav)
        assert (100, 50) in pico.throttle_calls
