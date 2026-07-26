"""Geographic calculation functions — distance, bearing, heading difference.

Ported from reference/Boat_pico.py hav_dist(), calc_bearing(), hdg_diff().
These are the core navigation math primitives used by the navigator and
mission manager.
"""
from __future__ import annotations

import math

EARTH_R = 6_371_000.0  # Earth radius in metres
DEG_TO_RAD = math.pi / 180.0
RAD_TO_DEG = 180.0 / math.pi


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate the great-circle distance between two points in metres.

    Uses the haversine formula. Ported directly from Boat_pico.py hav_dist().

    Args:
        lat1, lon1: Start point (decimal degrees).
        lat2, lon2: End point (decimal degrees).

    Returns:
        Distance in metres.
    """
    r1 = lat1 * DEG_TO_RAD
    r2 = lat2 * DEG_TO_RAD
    dlat = (lat2 - lat1) * DEG_TO_RAD
    dlon = (lon2 - lon1) * DEG_TO_RAD
    a = math.sin(dlat * 0.5) ** 2 + math.cos(r1) * math.cos(r2) * math.sin(dlon * 0.5) ** 2
    return EARTH_R * 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))


def bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate the initial bearing from point 1 to point 2.

    Ported from Boat_pico.py calc_bearing().

    Args:
        lat1, lon1: Start point (decimal degrees).
        lat2, lon2: End point (decimal degrees).

    Returns:
        Bearing in degrees (0–360).
    """
    r1 = lat1 * DEG_TO_RAD
    r2 = lat2 * DEG_TO_RAD
    dlon = (lon2 - lon1) * DEG_TO_RAD
    x = math.sin(dlon) * math.cos(r2)
    y = math.cos(r1) * math.sin(r2) - math.sin(r1) * math.cos(r2) * math.cos(dlon)
    return math.atan2(x, y) * RAD_TO_DEG % 360.0


def distance_and_bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> tuple[float, float]:
    """Great-circle distance (metres) and initial bearing (degrees), together.

    Numerically identical to calling haversine_distance() and bearing()
    separately — same formulas, same operand order — but shares the radian
    conversions and the cos(lat) terms both need, instead of recomputing them
    once per call. Navigator.compute_throttle() needs both every navigation
    tick (5-10 Hz), so this halves the trig calls on that hot path.

    Args:
        lat1, lon1: Start point (decimal degrees).
        lat2, lon2: End point (decimal degrees).

    Returns:
        (distance_metres, bearing_degrees). Bearing is 0-360.
    """
    r1 = lat1 * DEG_TO_RAD
    r2 = lat2 * DEG_TO_RAD
    dlat = (lat2 - lat1) * DEG_TO_RAD
    dlon = (lon2 - lon1) * DEG_TO_RAD
    cos_r1 = math.cos(r1)
    cos_r2 = math.cos(r2)

    a = math.sin(dlat * 0.5) ** 2 + cos_r1 * cos_r2 * math.sin(dlon * 0.5) ** 2
    dist = EARTH_R * 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))

    x = math.sin(dlon) * cos_r2
    y = cos_r1 * math.sin(r2) - math.sin(r1) * cos_r2 * math.cos(dlon)
    brg = math.atan2(x, y) * RAD_TO_DEG % 360.0

    return dist, brg


def heading_diff(current: float, target: float) -> float:
    """Shortest signed angle from current heading to target heading.

    Ported from Boat_pico.py hdg_diff().

    Args:
        current: Current heading (0–360).
        target: Target heading (0–360).

    Returns:
        Signed difference in degrees (-180 to +180).
        Positive means turn right, negative means turn left.
    """
    d = target - current
    if d > 180:
        d -= 360
    elif d < -180:
        d += 360
    return d


def _local_offset(lat0: float, lon0: float, lat: float, lon: float) -> tuple[float, float]:
    """Equirectangular local tangent-plane offset of (lat, lon) from an origin
    (lat0, lon0), in metres. Returns (east, north).

    Exact enough for the sub-kilometre legs a survey boat follows on rivers and
    lakes (the great-circle error over 1 km is < 1 cm), and far cheaper than a
    full geodesic — this runs every navigation tick.
    """
    d_north = (lat - lat0) * DEG_TO_RAD * EARTH_R
    d_east = (lon - lon0) * DEG_TO_RAD * EARTH_R * math.cos(lat0 * DEG_TO_RAD)
    return d_east, d_north


def cross_track_error(
    from_lat: float, from_lon: float, to_lat: float, to_lon: float,
    lat: float, lon: float,
) -> tuple[float, float, float]:
    """Signed cross-track error of a boat relative to the leg from → to.

    The cross-track error is the perpendicular distance from the boat to the
    straight track line between the two waypoints — the quantity a naive
    "point at the next waypoint" controller ignores, letting wind/current push
    the boat off the line and arrive via a long curved path.

    Args:
        from_lat, from_lon: Leg start (previous waypoint / where the leg began).
        to_lat, to_lon: Leg end (target waypoint).
        lat, lon: Current boat position.

    Returns:
        (xte_m, along_m, path_course_deg):
          * xte_m — signed cross-track error in metres, **positive when the boat
            is to the right (starboard) of the track**, negative to port.
          * along_m — distance already progressed along the leg from the start.
          * path_course_deg — compass bearing of the leg (0–360).
    """
    px, py = _local_offset(from_lat, from_lon, to_lat, to_lon)   # leg vector (E, N)
    dx, dy = _local_offset(from_lat, from_lon, lat, lon)         # boat vector (E, N)
    leg_len = math.hypot(px, py)
    if leg_len < 1e-6:
        # Degenerate leg (start == end): no track to speak of.
        return 0.0, 0.0, bearing(from_lat, from_lon, to_lat, to_lon)
    ux, uy = px / leg_len, py / leg_len          # unit along-track (E, N)
    along = dx * ux + dy * uy
    # Right-hand normal of the along-track unit vector is (uy, -ux): dotting the
    # boat offset with it is +ve when the boat sits to starboard of the track.
    xte = dx * uy - dy * ux
    path_course = math.atan2(px, py) * RAD_TO_DEG % 360.0
    return xte, along, path_course


def los_course(
    from_lat: float, from_lon: float, to_lat: float, to_lon: float,
    lat: float, lon: float, *, lookahead_m: float = 12.0,
    xte_integral: float = 0.0, integral_gain: float = 0.0,
) -> tuple[float, float]:
    """Lookahead line-of-sight (LOS) desired course for path following.

    Implements the lookahead-based LOS guidance law (Lekkas & Fossen, 2012):

        chi_d = chi_path - atan2(e + k_i * e_int, Delta)

    where ``e`` is the signed cross-track error, ``Delta`` (the lookahead
    distance) sets how aggressively the boat cuts back to the track, and the
    optional integral term ``k_i * e_int`` is the ILOS extension that cancels the
    steady cross-track bias from a constant current or wind. Steering to this
    course (instead of the raw bearing to the waypoint) drives the boat onto the
    *track line* and holds it there, eliminating the downwind drift a
    point-at-the-waypoint controller suffers.

    Returns:
        (course_deg, xte_m): the desired compass course (0–360) and the current
        signed cross-track error (so the caller can integrate it for ILOS).
    """
    xte, _along, path_course = cross_track_error(
        from_lat, from_lon, to_lat, to_lon, lat, lon)
    delta = max(0.5, float(lookahead_m))
    correction = math.atan2(xte + integral_gain * xte_integral, delta) * RAD_TO_DEG
    # +xte (boat to starboard) → subtract → steer to port, back onto the track.
    return (path_course - correction) % 360.0, xte
