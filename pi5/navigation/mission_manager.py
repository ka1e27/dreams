"""Mission manager — load, execute, pause, resume, abort missions.

Ported from reference/Boat_pico.py task_mission() and the mission command
handling. Runs on the Pi 5 and orchestrates waypoint navigation, pod
deployment, and sampling.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path

from ..comms.pico_serial import PicoSerial
from ..comms.pod_bridge import PodBridge, PodReading
from .geo import haversine_distance
from .navigator import Navigator

logger = logging.getLogger(__name__)


class WaypointType(Enum):
    """Waypoint types — data points deploy the pod, path points pass through."""
    DATA = auto()
    PATH = auto()


class MissionPhase(Enum):
    """Current phase of mission execution at a data waypoint."""
    TRANSIT = auto()
    WINCH_DOWN = auto()
    SAMPLING = auto()
    WINCH_UP = auto()
    COMPLETE = auto()


@dataclass
class Waypoint:
    """A single mission waypoint."""
    lat: float
    lon: float
    wp_type: WaypointType = WaypointType.DATA
    max_time_s: int = 300
    label: str = ""
    speed: int | None = None  # Override cruise throttle for this leg


@dataclass
class MissionConfig:
    """Mission execution parameters (loaded from config.yaml)."""
    winch_down_speed: int = 50
    winch_up_speed: int = -50
    descent_rate_m_per_s: float = 0.10
    winch_up_margin: float = 1.5
    bottom_confirm_count: int = 3
    sample_interval_s: float = 5.0
    bottom_lost_confirm: int = 3
    min_bottom_samples: int = 2
    pod_poll_interval_s: float = 2.0
    default_sample_timeout_s: int = 300


@dataclass
class MissionState:
    """Current mission execution state — exposed for telemetry."""
    name: str = ""
    running: bool = False
    paused: bool = False
    current_wp: int = 0
    total_wps: int = 0
    phase: MissionPhase = MissionPhase.TRANSIT
    est_depth_m: float = 0.0
    sample_count: int = 0
    elapsed_s: float = 0.0


class MissionManager:
    """Orchestrates mission execution: waypoint sequencing, pod deployment, sampling."""

    def __init__(
        self,
        pico: PicoSerial,
        navigator: Navigator,
        pod: PodBridge,
        config: MissionConfig | None = None,
    ) -> None:
        self._pico = pico
        self._nav = navigator
        self._pod = pod
        self._config = config or MissionConfig()

        self.state = MissionState()
        self._waypoints: list[Waypoint] = []
        self._profile_data: list[PodReading] = []
        self._task: asyncio.Task[None] | None = None
        self._abort_event = asyncio.Event()
        self._pause_event = asyncio.Event()
        self._pause_event.set()  # Not paused initially

        # Callbacks
        self._on_mission_complete: asyncio.Event = asyncio.Event()
        self._on_wp_arrived: list = []

    @property
    def waypoints(self) -> list[Waypoint]:
        """Return loaded waypoints."""
        return self._waypoints

    def load_from_json(self, path: str | Path) -> bool:
        """Load a mission from a JSON file.

        Expected format matches reference/waypoints.json missions:
        {
            "name": "...",
            "waypoints": [
                {"lat": ..., "lon": ..., "type": "data"|"path",
                 "max_time": 300, "label": "..."}
            ]
        }
        """
        try:
            with open(path) as f:
                data = json.load(f)
        except Exception as e:
            logger.error("Failed to load mission file %s: %s", path, e)
            return False

        return self.load_from_dict(data)

    def load_from_dict(self, data: dict) -> bool:
        """Load a mission from a dictionary."""
        wps_raw = data.get("waypoints", [])
        if not wps_raw:
            logger.error("Mission has no waypoints")
            return False

        wps: list[Waypoint] = []
        for i, wp_data in enumerate(wps_raw):
            lat = wp_data.get("lat")
            lon = wp_data.get("lon")
            if lat is None or lon is None:
                logger.error("Waypoint %d missing lat/lon", i)
                return False
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                logger.error("Waypoint %d has invalid coordinates: %.6f, %.6f", i, lat, lon)
                return False

            wp_type_str = wp_data.get("type", "data")
            wp_type = WaypointType.PATH if wp_type_str == "path" else WaypointType.DATA

            wps.append(Waypoint(
                lat=lat,
                lon=lon,
                wp_type=wp_type,
                max_time_s=wp_data.get("max_time", self._config.default_sample_timeout_s),
                label=wp_data.get("label", ""),
                speed=wp_data.get("speed"),
            ))

        self._waypoints = wps
        self.state.name = data.get("name", "Unnamed")
        self.state.total_wps = len(wps)
        self.state.current_wp = 0
        logger.info("Loaded mission '%s' with %d waypoints (%d data, %d path)",
                     self.state.name, len(wps),
                     sum(1 for w in wps if w.wp_type == WaypointType.DATA),
                     sum(1 for w in wps if w.wp_type == WaypointType.PATH))
        return True

    def load_waypoints_file(self, path: str | Path, mission_key: str) -> bool:
        """Load a specific mission from a waypoints.json file.

        This handles the full waypoints.json format with home and missions dict.
        """
        try:
            with open(path) as f:
                data = json.load(f)
        except Exception as e:
            logger.error("Failed to load waypoints file %s: %s", path, e)
            return False

        missions = data.get("missions", {})
        if mission_key not in missions:
            logger.error("Mission '%s' not found. Available: %s",
                         mission_key, list(missions.keys()))
            return False

        return self.load_from_dict(missions[mission_key])

    async def start(self) -> None:
        """Start executing the loaded mission."""
        if not self._waypoints:
            logger.error("No waypoints loaded")
            return
        if self.state.running:
            logger.warning("Mission already running")
            return

        self.state.running = True
        self.state.paused = False
        self.state.current_wp = 0
        self._abort_event.clear()
        self._on_mission_complete.clear()
        self._pause_event.set()

        self._task = asyncio.create_task(self._mission_loop())
        logger.info("Mission '%s' started with %d waypoints",
                     self.state.name, len(self._waypoints))

    def pause(self) -> None:
        """Pause the mission. Boat holds position."""
        if self.state.running and not self.state.paused:
            self.state.paused = True
            self._pause_event.clear()
            self._nav.stop_nav()
            logger.info("Mission paused at WP %d", self.state.current_wp)

    def resume_mission(self) -> None:
        """Resume a paused mission."""
        if self.state.running and self.state.paused:
            self.state.paused = False
            self._pause_event.set()
            logger.info("Mission resumed at WP %d", self.state.current_wp)

    def abort(self, reason: str = "ABORTED") -> None:
        """Abort the mission immediately."""
        self._abort_event.set()
        self._nav.stop_nav()
        self.state.running = False
        self.state.paused = False
        logger.info("Mission aborted: %s", reason)

    async def wait_complete(self, timeout: float | None = None) -> bool:
        """Wait for the mission to complete. Returns False on timeout."""
        try:
            await asyncio.wait_for(self._on_mission_complete.wait(), timeout)
            return True
        except asyncio.TimeoutError:
            return False

    async def return_to_home(self, home_lat: float, home_lon: float) -> None:
        """Abort current mission and navigate to a home position."""
        if self.state.running:
            self.abort("RTH")
            # Wait for mission loop to clean up
            if self._task:
                try:
                    await asyncio.wait_for(self._task, 5.0)
                except (asyncio.TimeoutError, asyncio.CancelledError):
                    pass

        self._waypoints = [Waypoint(lat=home_lat, lon=home_lon, wp_type=WaypointType.PATH, label="Home")]
        self.state.name = "Return to Home"
        self.state.total_wps = 1
        await self.start()

    async def _mission_loop(self) -> None:
        """Main mission execution loop."""
        try:
            for idx, wp in enumerate(self._waypoints):
                if self._abort_event.is_set():
                    break

                self.state.current_wp = idx
                self.state.phase = MissionPhase.TRANSIT
                self.state.est_depth_m = 0.0
                self.state.sample_count = 0

                # Wait if paused
                await self._pause_event.wait()

                # Navigate to waypoint
                logger.info("Transit to WP %d/%d: %.6f, %.6f [%s] %s",
                            idx, len(self._waypoints),
                            wp.lat, wp.lon,
                            "DATA" if wp.wp_type == WaypointType.DATA else "PATH",
                            wp.label)
                self._nav.goto(wp.lat, wp.lon)

                # Wait for arrival
                while not self._abort_event.is_set():
                    await self._pause_event.wait()
                    arrived = await self._nav.wait_arrived(timeout=1.0)
                    if arrived:
                        break

                if self._abort_event.is_set():
                    break

                # Path waypoints — just pass through
                if wp.wp_type == WaypointType.PATH:
                    logger.info("Path WP %d passed: %s", idx, wp.label)
                    continue

                # Data waypoint — hold position and deploy pod
                logger.info("Data WP %d reached: %s — deploying pod", idx, wp.label)
                self._nav.hold(wp.lat, wp.lon)
                self._profile_data.clear()

                await self._run_data_waypoint(wp)

            # Mission complete
            if not self._abort_event.is_set():
                logger.info("Mission '%s' complete — %d waypoints", self.state.name, len(self._waypoints))
                self.state.phase = MissionPhase.COMPLETE

        except asyncio.CancelledError:
            logger.info("Mission task cancelled")
        except Exception as e:
            logger.error("Mission error: %s", e)
        finally:
            self._nav.stop_nav()
            try:
                await self._pico.set_winch(0)
            except Exception:
                pass
            self.state.running = False
            self._on_mission_complete.set()

    async def _run_data_waypoint(self, wp: Waypoint) -> None:
        """Execute the full data collection sequence at a waypoint.

        Phases: WINCH_DOWN → SAMPLING → WINCH_UP
        """
        cfg = self._config

        # Phase 1: Winch down
        self.state.phase = MissionPhase.WINCH_DOWN
        logger.info("Winch down at WP %d", self.state.current_wp)
        try:
            await self._pico.set_winch(cfg.winch_down_speed)
        except Exception as e:
            logger.error("Winch down failed: %s", e)
            return

        winch_start = time.monotonic()
        bottom_count = 0

        while not self._abort_event.is_set():
            await self._pause_event.wait()
            elapsed = time.monotonic() - winch_start
            self.state.est_depth_m = elapsed * cfg.descent_rate_m_per_s
            self.state.elapsed_s = elapsed

            # Poll pod for bottom contact
            reading = await self._pod.poll_once()
            if reading and reading.bottom_contact:
                bottom_count += 1
                if bottom_count >= cfg.bottom_confirm_count:
                    logger.info("Bottom confirmed at %.2fm after %.1fs",
                                self.state.est_depth_m, elapsed)
                    break
            else:
                bottom_count = 0

            # Safety timeout
            if elapsed > wp.max_time_s:
                logger.warning("Winch down timeout at %.2fm", self.state.est_depth_m)
                break

            await asyncio.sleep(cfg.pod_poll_interval_s)

        # Stop winch
        try:
            await self._pico.set_winch(0)
        except Exception:
            pass

        if self._abort_event.is_set():
            return

        # Phase 2: Sampling at bottom
        self.state.phase = MissionPhase.SAMPLING
        sample_start = time.monotonic()
        self.state.sample_count = 0
        bottom_lost_count = 0

        logger.info("Sampling at WP %d, max %ds", self.state.current_wp, wp.max_time_s)

        while not self._abort_event.is_set():
            await self._pause_event.wait()
            elapsed = time.monotonic() - sample_start
            self.state.elapsed_s = elapsed

            # Take a sample
            reading = await self._pod.poll_once()
            if reading:
                self.state.sample_count += 1
                self._profile_data.append(reading)
                logger.debug("Sample %d: T=%.1f EC=%.1f L=%d BTM=%s",
                             self.state.sample_count,
                             reading.water_temp, reading.salinity_ec,
                             reading.light_pct, reading.bottom_contact)

                # Check bottom contact
                if not reading.bottom_contact:
                    bottom_lost_count += 1
                    if (bottom_lost_count >= cfg.bottom_lost_confirm
                            and self.state.sample_count >= cfg.min_bottom_samples):
                        logger.info("Contact lost after %d samples", self.state.sample_count)
                        break
                else:
                    bottom_lost_count = 0

            # Safety timeout
            if elapsed >= wp.max_time_s:
                logger.info("Sample timeout after %d samples, %.0fs",
                            self.state.sample_count, elapsed)
                break

            await asyncio.sleep(cfg.sample_interval_s)

        if self._abort_event.is_set():
            return

        # Phase 3: Winch up
        self.state.phase = MissionPhase.WINCH_UP
        winch_down_elapsed = time.monotonic() - winch_start - (time.monotonic() - sample_start)
        raise_time = max(winch_down_elapsed, 5.0) * cfg.winch_up_margin

        logger.info("Winch up at WP %d, estimated %.1fs", self.state.current_wp, raise_time)
        try:
            await self._pico.set_winch(cfg.winch_up_speed)
        except Exception as e:
            logger.error("Winch up failed: %s", e)
            return

        up_start = time.monotonic()
        while not self._abort_event.is_set():
            if time.monotonic() - up_start >= raise_time:
                break
            await asyncio.sleep(0.5)

        try:
            await self._pico.set_winch(0)
        except Exception:
            pass

        logger.info("WP %d complete — %d samples, %.2fm depth",
                     self.state.current_wp, self.state.sample_count, self.state.est_depth_m)

    def get_profile_data(self) -> list[PodReading]:
        """Return profile data collected at the current/last data waypoint."""
        return list(self._profile_data)
