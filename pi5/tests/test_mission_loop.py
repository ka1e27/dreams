"""Tests for the MissionManager async FSM (_mission_loop / _run_data_waypoint).

These complement test_mission_manager.py (which covers loading/validation).
Here we run the real mission loop with fake collaborators (PicoSerial,
Navigator, PodBridge) and tiny timing config so the TRANSIT → WINCH_DOWN →
SAMPLING → WINCH_UP phases execute in milliseconds.
"""
from __future__ import annotations

import asyncio

import pytest

from pi5.comms.pod_bridge import PodReading
from pi5.navigation.mission_manager import (
    MissionConfig,
    MissionManager,
    MissionPhase,
)


class FakePico:
    """Records winch commands; throttle is a no-op (Navigator is faked)."""

    def __init__(self) -> None:
        self.winch_calls: list[int] = []

    async def set_winch(self, speed: int):
        self.winch_calls.append(speed)
        return None

    async def set_throttle(self, left: int, right: int):
        return None


class FakeNav:
    """Stand-in for Navigator: records goto/hold/stop_nav, drives arrival."""

    def __init__(self) -> None:
        self.goto_calls: list[tuple[float, float]] = []
        self.hold_calls: list[tuple[float, float]] = []
        self.stop_nav_count = 0
        self.arrive = True       # whether wait_arrived reports arrival
        self.arrive_delay = 0.0  # delay before responding

    def goto(self, lat: float, lon: float,
             from_lat: float | None = None, from_lon: float | None = None) -> None:
        self.goto_calls.append((lat, lon))

    def hold(self, lat: float, lon: float) -> None:
        self.hold_calls.append((lat, lon))

    def stop_nav(self) -> None:
        self.stop_nav_count += 1

    async def wait_arrived(self, timeout=None) -> bool:
        if self.arrive_delay:
            await asyncio.sleep(self.arrive_delay)
        return self.arrive


class FakePod:
    """Returns phase-appropriate readings so each data-WP phase terminates fast.

    WINCH_DOWN  → bottom_contact True  (bottom confirmed → stop descent)
    SAMPLING    → bottom_contact False (contact lost → stop sampling)
    WINCH_UP    → pressure_depth_m 0.0 (at surface → done)
    """

    def __init__(self, phase_getter) -> None:
        self._phase = phase_getter
        self.poll_count = 0

    async def poll_once(self) -> PodReading | None:
        self.poll_count += 1
        phase = self._phase()
        if phase == MissionPhase.WINCH_DOWN:
            return _reading(bottom=True, depth=2.0)
        if phase == MissionPhase.SAMPLING:
            return _reading(bottom=False, depth=2.0)
        if phase == MissionPhase.WINCH_UP:
            return _reading(bottom=False, depth=0.0)
        return None


def _reading(bottom: bool, depth: float) -> PodReading:
    return PodReading(
        timestamp=0.0,
        water_temp=12.0,
        salinity_ec=1.5,
        light_pct=50,
        bottom_contact=bottom,
        leak_detected=False,
        pressure_depth_m=depth,
    )


def _fast_config() -> MissionConfig:
    """Config that makes every phase converge on the first poll, with ~no sleeps."""
    return MissionConfig(
        winch_down_speed=50,
        winch_up_speed=-50,
        descent_rate_m_per_s=0.10,
        bottom_confirm_count=1,
        sample_interval_s=0.001,
        bottom_lost_confirm=1,
        min_bottom_samples=1,
        pod_poll_interval_s=0.001,
        default_sample_timeout_s=10,
    )


def _build():
    pico = FakePico()
    nav = FakeNav()
    mm = MissionManager(pico, nav, pod=None, config=_fast_config())
    pod = FakePod(lambda: mm.state.phase)
    mm._pod = pod
    return mm, pico, nav, pod


@pytest.mark.asyncio
async def test_mission_runs_path_and_data_waypoints_to_completion():
    mm, pico, nav, pod = _build()
    ok = mm.load_from_dict({
        "name": "test",
        "waypoints": [
            {"lat": 51.500, "lon": -0.070, "type": "path", "label": "p"},
            {"lat": 51.510, "lon": -0.070, "type": "data", "max_time": 10, "label": "d"},
        ],
    })
    assert ok is True

    await mm.start()
    done = await mm.wait_complete(timeout=5.0)

    assert done is True
    assert mm.state.running is False
    assert mm.state.phase == MissionPhase.COMPLETE
    # Both waypoints were navigated to; the data WP also entered hold.
    assert len(nav.goto_calls) == 2
    assert nav.hold_calls == [(51.510, -0.070)]
    # Winch went down (50), stopped (0), up (-50), stopped (0) at least.
    assert 50 in pico.winch_calls
    assert -50 in pico.winch_calls
    # At least one sample was captured during the SAMPLING phase.
    assert len(mm.get_profile_data()) >= 1


@pytest.mark.asyncio
async def test_data_waypoint_visits_all_phases():
    mm, pico, nav, pod = _build()
    mm.load_from_dict({
        "name": "one-data",
        "waypoints": [{"lat": 51.51, "lon": -0.07, "type": "data", "max_time": 10}],
    })

    await mm.start()
    done = await mm.wait_complete(timeout=5.0)

    assert done is True
    # The pod was polled across the descent/sampling/ascent phases.
    assert pod.poll_count >= 3
    assert mm.state.est_depth_m == 0.0  # returned to surface


@pytest.mark.asyncio
async def test_abort_stops_a_running_mission():
    mm, pico, nav, pod = _build()
    nav.arrive = False        # never "arrive" → mission stays in TRANSIT
    nav.arrive_delay = 0.01
    mm.load_from_dict({
        "name": "abort",
        "waypoints": [{"lat": 51.51, "lon": -0.07, "type": "data"}],
    })

    await mm.start()
    await asyncio.sleep(0.05)  # let it reach the transit wait-loop
    assert mm.state.running is True
    mm.abort("test-abort")

    done = await mm.wait_complete(timeout=5.0)
    assert done is True
    assert mm.state.running is False
    assert nav.stop_nav_count >= 1


@pytest.mark.asyncio
async def test_pause_blocks_progress_then_resume_completes():
    mm, pico, nav, pod = _build()
    nav.arrive = False        # hold in transit until we resume
    nav.arrive_delay = 0.01
    mm.load_from_dict({
        "name": "pause",
        "waypoints": [{"lat": 51.50, "lon": -0.07, "type": "path"}],
    })

    await mm.start()
    await asyncio.sleep(0.03)
    mm.pause()
    assert mm.state.paused is True

    # While paused, the mission must not complete.
    completed_while_paused = await mm.wait_complete(timeout=0.2)
    assert completed_while_paused is False

    # Resume and allow arrival → mission finishes.
    nav.arrive = True
    mm.resume_mission()
    assert mm.state.paused is False
    done = await mm.wait_complete(timeout=5.0)
    assert done is True
    assert mm.state.running is False


@pytest.mark.asyncio
async def test_return_to_home_runs_single_home_waypoint():
    mm, pico, nav, pod = _build()
    await mm.return_to_home(51.5074, -0.0700)
    done = await mm.wait_complete(timeout=5.0)

    assert done is True
    assert mm.state.name == "Return to Home"
    assert nav.goto_calls[-1] == (51.5074, -0.0700)


@pytest.mark.asyncio
async def test_start_with_no_waypoints_is_a_noop():
    mm, pico, nav, pod = _build()
    await mm.start()
    assert mm.state.running is False
    assert mm._task is None


def test_skip_site_only_arms_during_winch_or_sampling():
    mm, pico, nav, pod = _build()
    # Not running → no effect.
    mm.skip_site()
    assert not mm._skip_site_event.is_set()

    # Running but in TRANSIT → still no effect.
    mm.state.running = True
    mm.state.phase = MissionPhase.TRANSIT
    mm.skip_site()
    assert not mm._skip_site_event.is_set()

    # Running and sampling → arms the skip event.
    mm.state.phase = MissionPhase.SAMPLING
    mm.skip_site()
    assert mm._skip_site_event.is_set()
