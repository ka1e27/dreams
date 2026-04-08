"""Waypoint-following navigator.

Ported from reference/Boat_pico.py task_navigate(). Calculates
bearing and distance to the target waypoint and generates throttle
commands for the Boat Pico.

The Pi 5 runs this at ~5Hz and sends SET_THR commands over serial.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from ..comms.pico_serial import PicoSerial, Telemetry
from .geo import bearing, haversine_distance, heading_diff

logger = logging.getLogger(__name__)


@dataclass
class NavConfig:
    """Navigation tuning parameters."""
    arrive_radius_m: float = 5.0
    hold_drift_m: float = 8.0
    cruise_throttle: int = 40
    heading_tolerance_deg: float = 10.0
    max_heading_error_deg: float = 90.0
    turn_min_throttle: int = 15
    update_rate_hz: float = 5.0


@dataclass
class NavState:
    """Current navigation state — exposed for telemetry and the dashboard."""
    target_lat: float | None = None
    target_lon: float | None = None
    distance_m: float = 0.0
    bearing_deg: float = 0.0
    heading_error: float = 0.0
    throttle_left: int = 0
    throttle_right: int = 0
    arrived: bool = False
    active: bool = False


class Navigator:
    """Calculates throttle commands to steer toward a target waypoint.

    Usage:
        nav = Navigator(pico, config)
        nav.goto(lat, lon)
        await nav.start()    # runs in background
        ...
        nav.stop_nav()
    """

    def __init__(self, pico: PicoSerial, config: NavConfig | None = None) -> None:
        self._pico = pico
        self._config = config or NavConfig()
        self.state = NavState()

        # Hold position (station-keeping)
        self._hold_lat: float | None = None
        self._hold_lon: float | None = None
        self._holding = False

        # Obstacle avoidance override (set by CV module later)
        self._avoid_left: int = 0
        self._avoid_right: int = 0

        self._task: asyncio.Task[None] | None = None
        self._on_arrived: asyncio.Event = asyncio.Event()

    def goto(self, lat: float, lon: float) -> None:
        """Set a target waypoint and begin navigating."""
        self.state.target_lat = lat
        self.state.target_lon = lon
        self.state.arrived = False
        self.state.active = True
        self._holding = False
        self._on_arrived.clear()
        logger.info("NAV goto %.6f, %.6f", lat, lon)

    def hold(self, lat: float, lon: float) -> None:
        """Enter station-keeping mode at a position."""
        self._hold_lat = lat
        self._hold_lon = lon
        self._holding = True
        self.state.active = False
        logger.info("NAV hold at %.6f, %.6f", lat, lon)

    def stop_nav(self) -> None:
        """Stop all navigation. Motors will be set to zero."""
        self.state.active = False
        self.state.target_lat = None
        self.state.target_lon = None
        self._holding = False
        self.state.throttle_left = 0
        self.state.throttle_right = 0

    def set_avoidance_override(self, left: int, right: int) -> None:
        """Set obstacle avoidance throttle override (from CV module).

        When non-zero, these values replace the navigator's throttle output.
        Set both to 0 to cancel the override.
        """
        self._avoid_left = left
        self._avoid_right = right

    async def wait_arrived(self, timeout: float | None = None) -> bool:
        """Block until the current waypoint is reached.

        Returns True if arrived, False if timed out.
        """
        try:
            await asyncio.wait_for(self._on_arrived.wait(), timeout)
            return True
        except asyncio.TimeoutError:
            return False

    def compute_throttle(
        self, lat: float, lon: float, hdg: float,
        tgt_lat: float, tgt_lon: float
    ) -> tuple[int, int, float, float, float, bool]:
        """Pure function: compute throttle given current and target position.

        Returns (left, right, distance, brg, error, arrived).
        """
        cfg = self._config
        dist = haversine_distance(lat, lon, tgt_lat, tgt_lon)
        brg = bearing(lat, lon, tgt_lat, tgt_lon)
        err = heading_diff(hdg, brg)

        if dist < cfg.arrive_radius_m:
            return 0, 0, dist, brg, err, True

        # Proportional steering — same algorithm as Boat_pico.py task_navigate
        if abs(err) < cfg.heading_tolerance_deg:
            blend = 0.0
        else:
            blend = min(
                (abs(err) - cfg.heading_tolerance_deg)
                / (cfg.max_heading_error_deg - cfg.heading_tolerance_deg),
                1.0,
            )

        spd = cfg.cruise_throttle
        if err >= 0:
            left = spd
            right = int(spd * (1.0 - 2.0 * blend))
        else:
            left = int(spd * (1.0 - 2.0 * blend))
            right = spd

        # Clamp minimum turn speed
        if left < -cfg.turn_min_throttle:
            left = -cfg.turn_min_throttle
        if right < -cfg.turn_min_throttle:
            right = -cfg.turn_min_throttle

        return left, right, dist, brg, err, False

    async def _nav_loop(self) -> None:
        """Background navigation loop — runs at update_rate_hz."""
        interval = 1.0 / self._config.update_rate_hz
        while True:
            try:
                tel = self._pico.telemetry

                # Station-keeping: if drifted too far, re-engage nav
                if self._holding and not self.state.active:
                    if self._hold_lat is not None:
                        drift = haversine_distance(
                            tel.lat, tel.lon, self._hold_lat, self._hold_lon
                        )
                        if drift > self._config.hold_drift_m:
                            self.goto(self._hold_lat, self._hold_lon)
                            logger.info("HOLD reacquire, drift=%.1fm", drift)

                if self.state.active and self.state.target_lat is not None:
                    left, right, dist, brg, err, arrived = self.compute_throttle(
                        tel.lat, tel.lon, tel.heading,
                        self.state.target_lat, self.state.target_lon,
                    )

                    self.state.distance_m = dist
                    self.state.bearing_deg = brg
                    self.state.heading_error = err

                    if arrived:
                        self.state.arrived = True
                        self.state.active = False
                        self.state.throttle_left = 0
                        self.state.throttle_right = 0
                        self._on_arrived.set()
                        logger.info("NAV arrived at %.6f, %.6f",
                                    self.state.target_lat, self.state.target_lon)
                        try:
                            await self._pico.set_throttle(0, 0)
                        except Exception:
                            pass
                    else:
                        # Apply obstacle avoidance override if active
                        if self._avoid_left != 0 or self._avoid_right != 0:
                            left = self._avoid_left
                            right = self._avoid_right

                        self.state.throttle_left = left
                        self.state.throttle_right = right
                        try:
                            await self._pico.set_throttle(left, right)
                        except Exception as e:
                            logger.error("SET_THR failed: %s", e)
                else:
                    # Not navigating — ensure motors are stopped
                    if self.state.throttle_left != 0 or self.state.throttle_right != 0:
                        self.state.throttle_left = 0
                        self.state.throttle_right = 0
                        try:
                            await self._pico.set_throttle(0, 0)
                        except Exception:
                            pass

            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error("Nav loop error: %s", e)

            await asyncio.sleep(interval)

    async def start(self) -> None:
        """Start the background navigation loop."""
        self._task = asyncio.create_task(self._nav_loop())

    async def stop(self) -> None:
        """Stop the navigation loop and zero motors."""
        self.stop_nav()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        try:
            await self._pico.set_throttle(0, 0)
        except Exception:
            pass
