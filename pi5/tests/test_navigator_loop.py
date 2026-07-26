"""Tests for the Navigator background async loop (_nav_loop / start / stop).

These complement test_navigator.py (which covers the pure compute_throttle).
Here we drive the real asyncio loop with a fake PicoSerial and assert on the
throttle commands it emits and the NavState transitions.
"""
from __future__ import annotations

import asyncio
import time

import pytest

from pi5.navigation.navigator import NavConfig, Navigator


class _Tel:
    """Minimal stand-in for comms.pico_serial.Telemetry."""

    def __init__(self, lat: float = 0.0, lon: float = 0.0, heading: float = 0.0) -> None:
        self.lat = lat
        self.lon = lon
        self.heading = heading


class FakePico:
    """Records throttle commands; exposes a mutable .telemetry like PicoSerial."""

    def __init__(self) -> None:
        self.telemetry = _Tel()
        self.throttle_calls: list[tuple[int, int]] = []
        self.throttle_event = asyncio.Event()

    async def set_throttle(self, left: int, right: int):
        self.throttle_calls.append((left, right))
        self.throttle_event.set()
        return None


class FailPico(FakePico):
    """Like FakePico but set_throttle always raises (to test error handling)."""

    async def set_throttle(self, left: int, right: int):
        raise ConnectionError("serial down")


async def _wait_for(predicate, timeout: float = 2.0, interval: float = 0.005) -> bool:
    """Poll predicate() until true or timeout. Returns whether it became true."""
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if predicate():
            return True
        await asyncio.sleep(interval)
    return False


# Current position / target ~1.1 km due north — heading already north → straight.
_CUR = (51.5000, -0.0714)
_TGT_NORTH = (51.5100, -0.0714)


@pytest.mark.asyncio
async def test_nav_loop_emits_throttle_toward_target():
    pico = FakePico()
    pico.telemetry = _Tel(_CUR[0], _CUR[1], 0.0)
    nav = Navigator(pico, NavConfig(update_rate_hz=200.0, cruise_throttle=40))
    nav.goto(*_TGT_NORTH)

    await nav.start()
    try:
        await asyncio.wait_for(pico.throttle_event.wait(), 2.0)
    finally:
        await nav.stop()

    # First command is straight-ahead cruise on both motors.
    assert pico.throttle_calls[0] == (40, 40)
    assert nav.state.distance_m > 1000


@pytest.mark.asyncio
async def test_nav_loop_arrival_sets_event_and_zeros_motors():
    pico = FakePico()
    pico.telemetry = _Tel(_CUR[0], _CUR[1], 0.0)
    nav = Navigator(pico, NavConfig(update_rate_hz=200.0, arrive_radius_m=5.0))
    nav.goto(*_CUR)  # already at the target

    await nav.start()
    try:
        arrived = await nav.wait_arrived(timeout=2.0)
    finally:
        await nav.stop()

    assert arrived is True
    assert nav.state.arrived is True
    assert nav.state.active is False
    assert (0, 0) in pico.throttle_calls


@pytest.mark.asyncio
async def test_hold_actively_station_keeps():
    pico = FakePico()
    # Boat far from the hold point → active station-keeping should drive it back
    # (current-aware hold, not the old "drift then convert to a goto" ping-pong).
    pico.telemetry = _Tel(_CUR[0], _CUR[1], 0.0)
    nav = Navigator(pico, NavConfig(update_rate_hz=200.0, hold_drift_m=8.0))
    nav.hold(*_TGT_NORTH)
    assert nav.state.active is False

    await nav.start()
    try:
        keeping = await _wait_for(lambda: nav.state.station_keeping, timeout=2.0)
        drove = await _wait_for(
            lambda: any(lc != 0 or rc != 0 for (lc, rc) in pico.throttle_calls),
            timeout=2.0)
        held_lat = nav._hold_lat  # retained (still holding, not a one-shot goto)
    finally:
        await nav.stop()

    assert keeping is True
    assert drove is True
    assert held_lat == _TGT_NORTH[0]
    assert nav.state.active is False


@pytest.mark.asyncio
async def test_avoidance_override_replaces_throttle():
    pico = FakePico()
    pico.telemetry = _Tel(_CUR[0], _CUR[1], 0.0)
    nav = Navigator(pico, NavConfig(update_rate_hz=200.0))
    nav.goto(*_TGT_NORTH)
    nav.set_avoidance_override(-20, 30)

    await nav.start()
    try:
        await _wait_for(lambda: (-20, 30) in pico.throttle_calls, timeout=2.0)
    finally:
        await nav.stop()

    assert (-20, 30) in pico.throttle_calls


@pytest.mark.asyncio
async def test_idle_loop_zeroes_lingering_throttle():
    pico = FakePico()
    nav = Navigator(pico, NavConfig(update_rate_hz=200.0))
    # Not active, not holding, but a stale non-zero throttle is on record.
    nav.state.throttle_left = 40
    nav.state.throttle_right = 40

    await nav.start()
    try:
        await asyncio.wait_for(pico.throttle_event.wait(), 2.0)
    finally:
        await nav.stop()

    assert pico.throttle_calls[0] == (0, 0)
    assert nav.state.throttle_left == 0


@pytest.mark.asyncio
async def test_nav_loop_survives_set_throttle_failure():
    pico = FailPico()
    pico.telemetry = _Tel(_CUR[0], _CUR[1], 0.0)
    nav = Navigator(pico, NavConfig(update_rate_hz=200.0, cruise_throttle=40))
    nav.goto(*_TGT_NORTH)

    await nav.start()
    try:
        # State is updated before the (failing) serial write, and the loop
        # must keep running despite the exception.
        updated = await _wait_for(lambda: nav.state.throttle_left == 40, timeout=2.0)
        assert updated is True
        assert nav._task is not None and not nav._task.done()
    finally:
        await nav.stop()


@pytest.mark.asyncio
async def test_wait_arrived_times_out_when_not_arriving():
    pico = FakePico()
    pico.telemetry = _Tel(_CUR[0], _CUR[1], 0.0)
    nav = Navigator(pico, NavConfig(update_rate_hz=200.0))
    nav.goto(*_TGT_NORTH)  # far away → never arrives

    await nav.start()
    try:
        arrived = await nav.wait_arrived(timeout=0.05)
    finally:
        await nav.stop()

    assert arrived is False
