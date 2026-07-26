"""Water-current estimation from GPS drift vs commanded through-water motion.

The boat has no water-speed sensor (no DVL/pitot), so the current vector is
estimated as::

    current = GPS_ground_velocity  -  expected_through_water_velocity

Ground velocity is a low-pass-filtered finite difference of GPS fixes.
Through-water velocity comes from a simple thrust->speed model projected along
the boat heading. The resulting current is smoothed again (it changes slowly).

Output is **set** (the compass direction the current flows *toward*, 0-360) and
**drift** (its speed, m/s) — the mariner's terms. The raw (east, north) vector
is exposed for the station-keeping feedforward.

Design follows the set-and-drift / Fossen guidance approach used on small ASVs
(compare GPS SOG/COG to the through-water velocity, filter, subtract). It is a
first-order estimate — good enough to hold station and to display, not a DVL.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from .geo import _local_offset  # (east, north) metres from an origin


@dataclass
class CurrentConfig:
    # Through-water speed model: v = a*|thr| + b*thr^2  (thr = mean fwd cmd, -1..1).
    # Defaults are a gentle small-catamaran curve; calibrate per boat (see docs).
    thrust_a: float = 0.35
    thrust_b: float = 0.15
    vel_lpf: float = 0.35      # low-pass alpha on GPS ground velocity (0..1)
    cur_lpf: float = 0.06      # slower low-pass on the current estimate itself
    min_dt: float = 0.2        # skip ticks closer than this (s) — GPS quantised
    max_dt: float = 5.0        # gap longer than this (s) -> restart the diff
    # Below this ground speed heading/thrust are unreliable, so the ground track
    # IS essentially the current (we're being pushed) -> don't subtract a model.
    min_speed_valid: float = 0.15


class CurrentEstimator:
    """Rolling estimate of the water-current vector. Feed it one GPS tick at a
    time via :meth:`update`; read :attr:`vector` / :meth:`result`."""

    def __init__(self, cfg: CurrentConfig | None = None) -> None:
        self.cfg = cfg or CurrentConfig()
        self._last: tuple[float, float, float] | None = None  # (t, lat, lon)
        self.vE = 0.0
        self.vN = 0.0        # filtered ground velocity (m/s, east/north)
        self.cE = 0.0
        self.cN = 0.0        # filtered current estimate (m/s, east/north)
        self._have = False

    def reset(self) -> None:
        self._last = None
        self._have = False
        self.vE = self.vN = self.cE = self.cN = 0.0

    def water_velocity(self, throttle_frac: float, heading_deg: float) -> tuple[float, float]:
        """Expected through-water velocity (east, north) m/s from the thrust
        model, projected along the heading. ``throttle_frac`` is the mean forward
        command in [-1, 1] (e.g. (left+right)/2 / 100)."""
        t = max(-1.0, min(1.0, throttle_frac))
        mag = self.cfg.thrust_a * abs(t) + self.cfg.thrust_b * t * t
        if t < 0:
            mag = -mag
        h = math.radians(heading_deg)
        return mag * math.sin(h), mag * math.cos(h)  # (E, N): 0deg heading = +N

    def update(self, t: float, lat: float, lon: float,
               heading_deg: float, throttle_frac: float) -> tuple[float, float]:
        """Fold one GPS/heading/throttle sample. Returns (set_deg, drift_ms)."""
        if self._last is None:
            self._last = (t, lat, lon)
            return self.result()
        t0, la0, lo0 = self._last
        dt = t - t0
        if dt < self.cfg.min_dt:
            return self.result()
        if dt > self.cfg.max_dt:
            # Stale — restart the difference rather than integrate a huge jump.
            self._last = (t, lat, lon)
            return self.result()

        dE, dN = _local_offset(la0, lo0, lat, lon)
        a = self.cfg.vel_lpf
        self.vE = a * (dE / dt) + (1 - a) * self.vE
        self.vN = a * (dN / dt) + (1 - a) * self.vN
        self._last = (t, lat, lon)

        # current = ground velocity - modelled through-water velocity. The model
        # is 0 at 0 throttle, so a coasting boat correctly reads current = ground
        # track; a boat actively HOLDING station (stationary over ground but
        # thrusting to cancel the current) correctly reads current = -water. The
        # compass gives heading even at zero speed, so no low-speed special-case.
        wE, wN = self.water_velocity(throttle_frac, heading_deg)
        mE, mN = self.vE - wE, self.vN - wN

        c = self.cfg.cur_lpf
        self.cE = c * mE + (1 - c) * self.cE
        self.cN = c * mN + (1 - c) * self.cN
        self._have = True
        return self.result()

    def result(self) -> tuple[float, float]:
        """(set_deg, drift_ms): direction the current flows toward, and speed."""
        drift = math.hypot(self.cE, self.cN)
        set_deg = math.degrees(math.atan2(self.cE, self.cN)) % 360.0
        return set_deg, drift

    @property
    def vector(self) -> tuple[float, float]:
        """Current estimate as (east, north) m/s."""
        return self.cE, self.cN

    @property
    def valid(self) -> bool:
        return self._have
