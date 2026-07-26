"""Reactive obstacle avoidance — turn a detected threat's bearing + distance
into a steer-away throttle override for the navigator.

This is the layer that actually keeps the boat off obstacles. The three-tier
vision pipeline (``pi5.cv.pipeline``) already detects, ranges and prioritises
threats; when the primary threat is inside the avoidance envelope it calls
:func:`reactive_avoidance` and pushes the result into
``Navigator.set_avoidance_override`` — which overrides the waypoint steering
until the threat clears. No second YOLO pass, no extra camera subscription: it
rides on the detections the pipeline already has.

Behaviour (a light, deterministic potential-field-style rule):

  * Beyond ``trigger_distance_m`` → ``None`` (no override; hold course).
  * Inside it → slow down (more the closer it is) and steer *away* from the
    threat's bearing. Threat to starboard → bear to port, and vice-versa.
  * A near head-on threat is passed to starboard, the COLREGS convention for
    two power-driven vessels meeting head-on (Rule 14).
  * Close to ``critical_distance_m`` the turn is hard enough to drive the inner
    motor into reverse, so the catamaran can pivot clear even from a standstill.

Kept pure and side-effect free so it is unit-testable without any hardware.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class AvoidanceConfig:
    """Tuning for the reactive steer-away rule."""
    # Threat range (m) at which avoidance begins nudging the boat off course.
    trigger_distance_m: float = 8.0
    # Range (m) at which avoidance goes full-authority (hard turn, deep slow-down).
    critical_distance_m: float = 3.0
    # Forward throttle used when the path is clear / at the trigger edge.
    cruise_throttle: int = 40
    # Maximum differential steer applied at full severity.
    max_steer: int = 65
    # |bearing| below this (deg) counts as head-on → pass to starboard (COLREGS).
    head_on_deg: float = 8.0
    # Fraction of cruise the boat still keeps at full severity. A small floor
    # (not 0) is deliberate: it makes the boat *arc* around an obstacle rather
    # than stop dead — stopping lets the path-following pull it straight back at
    # the obstacle (a reactive local minimum), so it can stall in front of a
    # dead-ahead hazard. 0 = may fully stop (most conservative, but can stall).
    min_forward_frac: float = 0.2


def reactive_avoidance(
    bearing_deg: float | None, distance_m: float | None,
    cfg: AvoidanceConfig | None = None, *, force_side: int | None = None,
) -> tuple[int, int] | None:
    """Steer-away throttle pair ``(left, right)`` for a threat, or ``None``.

    Args:
        bearing_deg: Threat bearing relative to the bow, degrees, **+ starboard
            / − port**. ``None`` (bearing unknown) is treated as head-on.
        distance_m: Threat range in metres. ``None`` or beyond the trigger range
            returns ``None`` (no avoidance).
        cfg: :class:`AvoidanceConfig` tuning (defaults if omitted).
        force_side: If given, override the side the boat bears off to
            (``+1`` = starboard, ``-1`` = port) instead of deciding it from the
            bearing. Used by :class:`AvoidanceController` to *commit* to one side
            so the boat doesn't flip-flop and orbit a hazard.

    Returns:
        ``(left, right)`` throttle in [-100, 100] to override the navigator with,
        or ``None`` when the threat is out of range and course should be held.
    """
    cfg = cfg or AvoidanceConfig()
    if distance_m is None or distance_m > cfg.trigger_distance_m:
        return None

    span = max(0.1, cfg.trigger_distance_m - cfg.critical_distance_m)
    severity = (cfg.trigger_distance_m - distance_m) / span
    severity = max(0.0, min(1.0, severity))

    # Slow down as the threat nears; near critical the boat can crawl/stop.
    frac = 1.0 - (1.0 - cfg.min_forward_frac) * severity
    fwd = cfg.cruise_throttle * frac
    turn = cfg.max_steer * severity

    # Decide which way to bear off. A committed side (force_side) wins; otherwise:
    # threat to starboard → turn to port; to port → turn to starboard; near
    # head-on → starboard (COLREGS Rule 14).
    if force_side is not None:
        steer_starboard = force_side > 0
    else:
        brg = 0.0 if bearing_deg is None else float(bearing_deg)
        steer_starboard = brg < 0 or abs(brg) < cfg.head_on_deg
    if steer_starboard:
        left, right = fwd + turn, fwd - turn      # bow swings to starboard
    else:
        left, right = fwd - turn, fwd + turn      # bow swings to port

    left = int(max(-100, min(100, round(left))))
    right = int(max(-100, min(100, round(right))))
    return left, right


class AvoidanceController:
    """Stateful "bug"-style wrapper around :func:`reactive_avoidance`.

    Memoryless reactive avoidance keeps the boat off a hazard but can *orbit* one
    that sits dead on the line to the goal: it bears off, the hazard leaves the
    forward view, the override releases, path-following pulls straight back at it,
    and the cycle repeats (a reactive local minimum). This controller breaks that
    the way boundary-following "bug" planners do:

    * **Commit to a side.** On first engagement it locks the turn direction (the
      side the reactive rule chose) and holds it — no per-frame flip-flopping as
      the bearing wanders.
    * **Pass, then release.** It stays engaged until the hazard has been *passed*,
      not merely until it leaves the sensor envelope: either the bearing swings
      behind the beam on the far side of the turn (``pass_bearing_deg`` — used
      when the sensor can still see it, e.g. the sim's 360° obstacle tracking), or
      sight is lost and a short blind hold (``pass_hold_s``) carries the boat past
      before it releases. Once released the hazard is behind, so path-following
      resumes toward the goal instead of back into the obstacle.

    This makes the boat *route around* a blocking obstacle and continue to the
    waypoint, rather than holding off it forever. Feed it the primary hazard's
    ``(bearing, distance)`` each tick (``None`` when nothing is sensed).
    """

    def __init__(self, cfg: AvoidanceConfig | None = None, *,
                 pass_bearing_deg: float = 110.0, pass_hold_s: float = 6.0) -> None:
        self.cfg = cfg or AvoidanceConfig()
        self.pass_bearing_deg = float(pass_bearing_deg)
        self.pass_hold_s = float(pass_hold_s)
        self._side = 0            # committed turn side: +1 starboard, -1 port
        self._active = False
        self._last_seen_t = 0.0

    @property
    def avoiding(self) -> bool:
        return self._active

    @property
    def committed_side(self) -> int:
        return self._side

    def reset(self) -> None:
        self._active = False
        self._side = 0

    def update(self, bearing_deg: float | None, distance_m: float | None,
               now: float) -> tuple[int, int] | None:
        """One tick. Returns the steer-away ``(left, right)`` override, or ``None``
        to hand steering back to the navigator."""
        cfg = self.cfg
        in_env = distance_m is not None and distance_m <= cfg.trigger_distance_m

        if not self._active:
            if not in_env:
                return None
            # Engage + commit to the side the reactive rule would pick now.
            brg = 0.0 if bearing_deg is None else float(bearing_deg)
            self._side = 1 if (brg < 0 or abs(brg) < cfg.head_on_deg) else -1
            self._active = True
            self._last_seen_t = now

        if in_env:
            self._last_seen_t = now
            # Passed? Hazard has swung behind the beam on the far side of the turn.
            if bearing_deg is not None:
                b = float(bearing_deg)
                if ((self._side == 1 and b <= -self.pass_bearing_deg)
                        or (self._side == -1 and b >= self.pass_bearing_deg)):
                    self.reset()
                    return None
            return reactive_avoidance(bearing_deg, distance_m, cfg,
                                      force_side=self._side)

        # Sight lost. Hold the committed maneuver briefly to finish the pass, then
        # release. The blind steer is forward-dominant (low severity) so the boat
        # carries past on its committed heading instead of spinning in place.
        if (now - self._last_seen_t) > self.pass_hold_s:
            self.reset()
            return None
        blind_dist = cfg.critical_distance_m + 0.85 * (
            cfg.trigger_distance_m - cfg.critical_distance_m)
        return reactive_avoidance(None, blind_dist, cfg, force_side=self._side)
