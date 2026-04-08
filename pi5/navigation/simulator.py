"""Virtual boat simulator for testing without hardware.

Simulates a boat with position, heading, and speed. Responds to
throttle commands the same way the real Pico + motors would, and
generates fake GPS/compass telemetry through the same PicoSerial
interface.

Usage:
    sim = BoatSimulator(start_lat=51.506726, start_lon=-0.071438)
    pico = sim.create_mock_pico()
    nav = Navigator(pico)
    ...
    sim.start()
"""
from __future__ import annotations

import asyncio
import math
import time
import logging
from dataclasses import dataclass

from ..comms.pico_serial import PicoSerial, Telemetry, Environment, PodData, Alert
from ..comms.protocol import ParsedFrame
from .geo import EARTH_R, DEG_TO_RAD, RAD_TO_DEG

logger = logging.getLogger(__name__)


@dataclass
class SimConfig:
    """Simulator tuning parameters."""
    # Maximum speed in metres/second at 100% throttle
    max_speed_mps: float = 1.5
    # Heading change rate in degrees/second at full differential steering
    max_turn_rate_dps: float = 30.0
    # Simulated battery drain (volts per metre travelled)
    batt_drain_v_per_m: float = 0.0005
    # Update rate
    update_rate_hz: float = 10.0


class BoatSimulator:
    """Simulates a virtual boat for testing navigation and mission logic."""

    def __init__(
        self,
        start_lat: float = 51.506726,
        start_lon: float = -0.071438,
        start_heading: float = 0.0,
        config: SimConfig | None = None,
    ) -> None:
        self._config = config or SimConfig()

        # Boat state
        self.lat = start_lat
        self.lon = start_lon
        self.heading = start_heading
        self.speed_mps = 0.0
        self.batt_v = 16.8

        # Throttle input (set by commands)
        self._thr_left = 0
        self._thr_right = 0
        self._winch_speed = 0
        self._estopped = False
        self._rc_override = False

        # Simulated pod
        self._pod_water_temp = 15.0
        self._pod_ec = 3500.0
        self._pod_light = 50
        self._pod_bottom = False

        # Track
        self._track: list[tuple[float, float, float]] = []

        self._task: asyncio.Task[None] | None = None

    def create_mock_pico(self) -> MockPicoSerial:
        """Create a MockPicoSerial that routes commands to this simulator."""
        return MockPicoSerial(self)

    def _move(self, dt: float) -> None:
        """Advance the simulation by dt seconds."""
        if self._estopped or self._rc_override:
            self.speed_mps = 0.0
            return

        cfg = self._config

        # Average throttle → forward speed
        avg_thr = (self._thr_left + self._thr_right) / 2.0
        target_speed = (avg_thr / 100.0) * cfg.max_speed_mps
        # Simple acceleration model
        self.speed_mps += (target_speed - self.speed_mps) * min(dt * 2.0, 1.0)

        # Differential throttle → heading change
        diff = self._thr_right - self._thr_left
        turn_rate = (diff / 200.0) * cfg.max_turn_rate_dps
        self.heading = (self.heading + turn_rate * dt) % 360.0

        # Move forward along heading
        dist = self.speed_mps * dt
        if abs(dist) > 0.001:
            hdg_rad = self.heading * DEG_TO_RAD
            # Approximate lat/lon displacement
            dlat = dist * math.cos(hdg_rad) / EARTH_R * RAD_TO_DEG
            dlon = dist * math.sin(hdg_rad) / (
                EARTH_R * math.cos(self.lat * DEG_TO_RAD)
            ) * RAD_TO_DEG
            self.lat += dlat
            self.lon += dlon
            self.batt_v -= abs(dist) * cfg.batt_drain_v_per_m

        self._track.append((self.lat, self.lon, time.time()))

    async def _sim_loop(self) -> None:
        """Background simulation loop."""
        dt = 1.0 / self._config.update_rate_hz
        while True:
            self._move(dt)
            await asyncio.sleep(dt)

    async def start(self) -> None:
        """Start the simulation."""
        self._task = asyncio.create_task(self._sim_loop())
        logger.info("Simulator started at %.6f, %.6f hdg=%.0f",
                     self.lat, self.lon, self.heading)

    async def stop(self) -> None:
        """Stop the simulation."""
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    def get_track(self) -> list[tuple[float, float, float]]:
        """Return the position track as [(lat, lon, timestamp), ...]."""
        return list(self._track)

    def plot_track(self) -> None:
        """Plot the boat's track on a matplotlib figure."""
        try:
            import matplotlib.pyplot as plt
        except ImportError:
            logger.error("matplotlib not installed — pip install matplotlib")
            return

        if not self._track:
            logger.warning("No track data to plot")
            return

        lats = [p[0] for p in self._track]
        lons = [p[1] for p in self._track]

        fig, ax = plt.subplots(1, 1, figsize=(10, 8))
        ax.plot(lons, lats, "b-", linewidth=1, alpha=0.7, label="Track")
        ax.plot(lons[0], lats[0], "go", markersize=10, label="Start")
        ax.plot(lons[-1], lats[-1], "rs", markersize=10, label="Current")
        ax.set_xlabel("Longitude")
        ax.set_ylabel("Latitude")
        ax.set_title("Simulated Boat Track")
        ax.legend()
        ax.set_aspect("equal")
        ax.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.show()


class MockPicoSerial:
    """A PicoSerial-compatible mock backed by the BoatSimulator.

    Drop-in replacement for PicoSerial — the Navigator, MissionManager,
    and PodBridge all work with this without knowing it's simulated.
    """

    def __init__(self, sim: BoatSimulator) -> None:
        self._sim = sim
        self.connected = True

        # Callbacks (same interface as PicoSerial)
        self._on_telemetry = None
        self._on_environment = None
        self._on_alert = None
        self._on_pod_data = None

        self._hb_task: asyncio.Task[None] | None = None

    @property
    def telemetry(self) -> Telemetry:
        """Build telemetry from simulator state."""
        s = self._sim
        batt_pct = max(0, min(100, int((s.batt_v - 13.2) / (16.8 - 13.2) * 100)))
        return Telemetry(
            lat=s.lat,
            lon=s.lon,
            heading=s.heading,
            speed_knots=s.speed_mps * 1.94384,  # m/s to knots
            batt_v=s.batt_v,
            batt_pct=batt_pct,
            hull="DRY",
            mt_left=45.0,
            mt_right=44.0,
            health="111111",
        )

    @property
    def environment(self) -> Environment:
        """Build environment from simulator state."""
        s = self._sim
        return Environment(
            air_temp=20,
            air_humidity=60,
            water_temp=s._pod_water_temp,
            water_ec=s._pod_ec,
            water_light=s._pod_light,
            bottom_contact=s._pod_bottom,
        )

    def on_telemetry(self, callback):
        self._on_telemetry = callback

    def on_environment(self, callback):
        self._on_environment = callback

    def on_alert(self, callback):
        self._on_alert = callback

    def on_pod_data(self, callback):
        self._on_pod_data = callback

    async def connect(self) -> None:
        self.connected = True

    async def disconnect(self) -> None:
        self.connected = False

    async def set_throttle(self, left: int, right: int) -> ParsedFrame:
        self._sim._thr_left = left
        self._sim._thr_right = right
        return ParsedFrame(msg_type="ACK", seq=0, fields=["SET_THR", str(left), str(right)], raw="")

    async def set_winch(self, speed: int) -> ParsedFrame:
        self._sim._winch_speed = speed
        return ParsedFrame(msg_type="ACK", seq=0, fields=["SET_WINCH", str(speed)], raw="")

    async def set_heading(self, heading: float) -> ParsedFrame:
        return ParsedFrame(msg_type="ACK", seq=0, fields=["SET_HDG", "%.1f" % heading], raw="")

    async def request_telemetry(self) -> ParsedFrame:
        t = self.telemetry
        return ParsedFrame(msg_type="TEL", seq=0, fields=[
            str(t.lat), str(t.lon), str(t.heading), str(t.speed_knots),
            str(t.batt_v), str(t.batt_pct), t.hull, str(t.mt_left),
            str(t.mt_right), t.health,
        ], raw="")

    async def poll_pod(self) -> ParsedFrame:
        s = self._sim
        return ParsedFrame(msg_type="POD_DATA", seq=0, fields=[
            str(s._pod_water_temp), str(s._pod_ec), str(s._pod_light),
            "1" if s._pod_bottom else "0", "0",
        ], raw="")

    async def emergency_stop(self) -> ParsedFrame:
        self._sim._estopped = True
        self._sim._thr_left = 0
        self._sim._thr_right = 0
        return ParsedFrame(msg_type="ACK", seq=0, fields=["ESTOP"], raw="")

    async def resume(self) -> ParsedFrame:
        self._sim._estopped = False
        return ParsedFrame(msg_type="ACK", seq=0, fields=["RESUME"], raw="")

    async def send_heartbeat(self) -> ParsedFrame:
        return ParsedFrame(msg_type="ACK", seq=0, fields=["HB"], raw="")

    async def set_trim(self, value: float) -> ParsedFrame:
        return ParsedFrame(msg_type="ACK", seq=0, fields=["SET_TRIM", str(value)], raw="")

    async def calibrate_compass(self, bearing: float) -> ParsedFrame:
        return ParsedFrame(msg_type="ACK", seq=0, fields=["CAL_COMPASS", str(bearing)], raw="")

    async def rc_override(self) -> ParsedFrame:
        self._sim._rc_override = True
        return ParsedFrame(msg_type="ACK", seq=0, fields=["RC_OVERRIDE"], raw="")

    async def rc_release(self) -> ParsedFrame:
        self._sim._rc_override = False
        return ParsedFrame(msg_type="ACK", seq=0, fields=["RC_RELEASE"], raw="")

    async def get_status(self) -> ParsedFrame:
        state = "ESTOP" if self._sim._estopped else "ACTIVE"
        return ParsedFrame(msg_type="STATUS", seq=0, fields=[state, "111111", "NONE"], raw="")

    async def start_heartbeat(self, interval: float = 1.0) -> None:
        pass  # No-op in simulator

    async def stop_heartbeat(self) -> None:
        pass
