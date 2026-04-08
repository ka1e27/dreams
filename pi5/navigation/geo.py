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
