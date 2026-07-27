"""Simulated obstacle field — lets reactive avoidance be exercised end-to-end in
``run_sim.py`` without a camera.

On the boat, obstacles are detected by the vision pipeline (stereo range + YOLO
bearing) and fed to :func:`pi5.cv.avoidance.reactive_avoidance`, which pushes a
steer-away override into the navigator. In the simulator there are no cameras, so
this module plays the sensor's role from ground truth: it holds obstacles as
lat/lon discs, computes the nearest one ahead of the boat (range + relative
bearing), and drives the *same* avoidance rule into the *same* navigator override
— so what you watch the sim boat do is the real avoidance control loop, not a
mock of it.
"""
from __future__ import annotations

import random
import time
from dataclasses import dataclass

from ..cv.avoidance import AvoidanceConfig, AvoidanceController, reactive_avoidance
from .geo import distance_and_bearing, heading_diff


@dataclass
class SimObstacle:
    """A circular obstacle on the water (a moored boat, a buoy, a rock)."""
    lat: float
    lon: float
    radius_m: float = 4.0
    label: str = "obstacle"

    def to_dict(self) -> dict:
        return {"lat": self.lat, "lon": self.lon,
                "radius_m": self.radius_m, "label": self.label}


class ObstacleField:
    """A set of simulated obstacles + the sensor model that ranges them.

    ``sensor_range_m`` and ``fov_deg`` model a forward-looking sensor: only
    obstacles within range and within ±fov/2 of the bow are "seen" (an obstacle
    behind the boat can't be detected by a forward camera, and shouldn't trigger
    avoidance). Range is measured to the obstacle's *edge* (centre distance minus
    radius), matching what a depth sensor returns off its surface.
    """

    def __init__(self, obstacles: "list[SimObstacle] | None" = None,
                 cfg: AvoidanceConfig | None = None,
                 sensor_range_m: float = 40.0, fov_deg: float = 160.0) -> None:
        self.obstacles: list[SimObstacle] = list(obstacles or [])
        self.cfg = cfg or AvoidanceConfig()
        self.sensor_range_m = float(sensor_range_m)
        self.fov_deg = float(fov_deg)

    # -- field management --------------------------------------------------- #
    def add(self, lat: float, lon: float, radius_m: float = 4.0,
            label: str = "obstacle") -> SimObstacle:
        o = SimObstacle(lat=float(lat), lon=float(lon),
                        radius_m=float(radius_m), label=str(label))
        self.obstacles.append(o)
        return o

    def clear(self) -> None:
        self.obstacles.clear()

    def as_dicts(self) -> list[dict]:
        return [o.to_dict() for o in self.obstacles]

    # -- sensor model ------------------------------------------------------- #
    def nearest_ahead(self, lat: float, lon: float, heading: float
                      ) -> "tuple[float, float, SimObstacle] | None":
        """Nearest visible obstacle → ``(rel_bearing_deg, edge_distance_m, obs)``.

        ``rel_bearing_deg`` is signed relative to the bow (+ starboard / − port);
        ``edge_distance_m`` is range to the obstacle's edge (>= 0). Returns None
        when nothing is within range and field of view.
        """
        best: "tuple[float, float, SimObstacle] | None" = None
        for o in self.obstacles:
            dist, brg = distance_and_bearing(lat, lon, o.lat, o.lon)
            rel = heading_diff(heading, brg)          # + = obstacle to starboard
            edge = dist - o.radius_m
            if edge > self.sensor_range_m:
                continue
            if abs(rel) > self.fov_deg / 2.0:
                continue
            if best is None or edge < best[1]:
                best = (rel, max(0.0, edge), o)
        return best

    def avoidance_override(self, lat: float, lon: float, heading: float
                           ) -> "tuple[int, int] | None":
        """Steer-away throttle for the nearest visible obstacle, or None.

        Thin adapter onto :func:`reactive_avoidance` — the exact rule the vision
        pipeline uses on hardware — so the sim avoids obstacles the same way the
        boat does. Returns None when nothing is close enough to act on.
        """
        near = self.nearest_ahead(lat, lon, heading)
        if near is None:
            return None
        rel, edge, _obs = near
        return reactive_avoidance(rel, edge, self.cfg)


class SimAvoider:
    """Drives an :class:`ObstacleField` into a navigator's avoidance override,
    with the bug-style :class:`~pi5.cv.avoidance.AvoidanceController` so the boat
    routes *around and past* a blocking obstacle instead of orbiting it.

    While engaged it tracks the committed obstacle with a full 360° bearing (not
    the narrow forward FOV used to *find* new hazards), so the controller's
    "passed behind the beam" release fires cleanly. Releases the override exactly
    once (``0, 0``) on clear so it never fights the navigator frame-by-frame.
    """

    def __init__(self, field: ObstacleField, navigator,
                 controller: AvoidanceController | None = None) -> None:
        self._field = field
        self._nav = navigator
        self._ctrl = controller or AvoidanceController(field.cfg)
        self._committed: SimObstacle | None = None
        self._override_active = False

    @property
    def avoiding(self) -> bool:
        return self._ctrl.avoiding

    def _observe(self, o: SimObstacle, lat: float, lon: float, heading: float
                 ) -> "tuple[float, float]":
        """(relative bearing, edge distance) to a specific obstacle — full 360°,
        no FOV cull, so a committed hazard stays tracked as it passes abeam."""
        dist, brg = distance_and_bearing(lat, lon, o.lat, o.lon)
        return heading_diff(heading, brg), max(0.0, dist - o.radius_m)

    def update(self, lat: float, lon: float, heading: float,
               now: float | None = None) -> bool:
        """Recompute + apply the override for the current pose. Returns whether an
        override is currently active."""
        now = time.monotonic() if now is None else float(now)
        bearing = distance = None
        obs = None
        if (self._ctrl.avoiding and self._committed is not None
                and self._committed in self._field.obstacles):
            # Keep watching the obstacle we committed to (all the way around).
            obs = self._committed
            bearing, distance = self._observe(obs, lat, lon, heading)
        else:
            # Idle (or the committed obstacle vanished): look for a new hazard
            # ahead through the narrow engagement FOV.
            near = self._field.nearest_ahead(lat, lon, heading)
            if near is not None:
                bearing, distance, obs = near

        override = self._ctrl.update(bearing, distance, now)
        if override is not None:
            self._committed = obs
            self._override_active = True
            self._nav.set_avoidance_override(override[0], override[1])
            return True
        self._committed = None
        if self._override_active:
            self._override_active = False
            self._nav.set_avoidance_override(0, 0)
        return False


class SimObjectMapper:
    """Feeds an :class:`~pi5.cv.object_memory.ObjectMemory` from ground truth —
    the simulator counterpart to the vision pipeline geolocating detections.

    On hardware the pipeline turns YOLO boxes + stereo range into geolocated
    sightings; the sim has no camera, so this "sees" the obstacle field through a
    forward sensor cone, adds a little deterministic range/bearing noise (so
    confirmation and the inverse-distance-weighted averaging behave like the real
    noisy sensor rather than snapping to a perfect point), and observes each
    visible obstacle into the memory under its label. The result is the *same*
    ObjectMemory the boat builds on the water — so what you watch appear on the
    command-center map is the real confirm/refine/forget logic, not a mock.

    An obstacle whose label isn't a remembered class (e.g. the generic
    "obstacle" the DROP OBSTACLE button drops) is simply ignored by the memory —
    drop a "buoy" or "person" to exercise the map.
    """

    def __init__(self, field: ObstacleField, memory, *,
                 sensor_range_m: float = 45.0, fov_deg: float = 75.0,
                 range_noise_frac: float = 0.04, bearing_noise_deg: float = 1.2,
                 seed: int = 1234) -> None:
        self._field = field
        self._mem = memory
        self.sensor_range_m = float(sensor_range_m)
        self.fov_deg = float(fov_deg)
        self.range_noise_frac = float(range_noise_frac)
        self.bearing_noise_deg = float(bearing_noise_deg)
        self._rng = random.Random(seed)

    def update(self, lat: float, lon: float, heading: float,
               now: float | None = None) -> int:
        """Observe every visible obstacle into the memory, then age it. Returns
        the number of observations fed this tick."""
        now = time.monotonic() if now is None else float(now)
        fed = 0
        for o in self._field.obstacles:
            # Range to the obstacle *centre* — the memory maps where the object
            # is, not its near edge (which is what avoidance ranges to).
            dist, brg = distance_and_bearing(lat, lon, o.lat, o.lon)
            rel = heading_diff(heading, brg)
            if dist > self.sensor_range_m or abs(rel) > self.fov_deg / 2.0:
                continue
            r = max(0.1, dist * (1.0 + self._rng.uniform(-1.0, 1.0)
                                 * self.range_noise_frac))
            b = rel + self._rng.uniform(-1.0, 1.0) * self.bearing_noise_deg
            if self._mem.observe(o.label, lat, lon, heading, b, r,
                                 confidence=0.9, now=now) is not None:
                fed += 1
        self._mem.expire(now)
        return fed
