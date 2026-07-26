"""End-to-end simulator avoidance: an obstacle field drives the real reactive
rule into the real navigator override, and the sim-kinematics boat routes around
an obstacle sitting on its track while still reaching the waypoint."""
from __future__ import annotations

import math

from pi5.navigation.geo import haversine_distance
from pi5.navigation.navigator import NavConfig, Navigator
from pi5.navigation.sim_obstacles import ObstacleField, SimAvoider, SimObstacle

A = (51.5000, -0.0714)          # leg start
B = (51.5010, -0.0714)          # waypoint ~111 m due north


class RecordingNav:
    """Captures the last override the avoider pushed."""
    def __init__(self):
        self.override = (0, 0)

    def set_avoidance_override(self, left, right):
        self.override = (left, right)


# --------------------------------------------------------------------------- #
# ObstacleField sensor model
# --------------------------------------------------------------------------- #
def test_nearest_bearing_sign_starboard():
    # Heading north; obstacle ~20 m NNE (ahead + east) → to starboard → +rel.
    field = ObstacleField([SimObstacle(51.50018, -0.071255, 3.0)])
    rel, edge, _ = field.nearest_ahead(51.5000, -0.0714, 0.0)
    assert rel > 0


def test_nearest_bearing_sign_port():
    # Obstacle ~20 m NNW (ahead + west) → to port → −rel.
    field = ObstacleField([SimObstacle(51.50018, -0.071545, 3.0)])
    rel, edge, _ = field.nearest_ahead(51.5000, -0.0714, 0.0)
    assert rel < 0


def test_obstacle_behind_not_seen():
    # Obstacle due south while heading north → outside the forward FOV.
    field = ObstacleField([SimObstacle(51.4990, -0.0714, 3.0)], fov_deg=160.0)
    assert field.nearest_ahead(51.5000, -0.0714, 0.0) is None


def test_out_of_range_not_seen():
    field = ObstacleField([SimObstacle(51.5100, -0.0714, 3.0)], sensor_range_m=40.0)
    assert field.nearest_ahead(51.5000, -0.0714, 0.0) is None   # ~1.1 km away


# --------------------------------------------------------------------------- #
# SimAvoider engage / release
# --------------------------------------------------------------------------- #
def test_avoider_engages_and_releases():
    nav = RecordingNav()
    field = ObstacleField([SimObstacle(51.50018, -0.0714, 3.0)])  # ~9 m ahead (edge)
    av = SimAvoider(field, nav)
    # Within the trigger envelope → engages.
    assert av.update(51.50010, -0.0714, 0.0, now=0.0) is True
    assert av.avoiding and nav.override != (0, 0)
    # Remove the obstacle. The bug-controller holds the committed maneuver briefly
    # to finish the pass, then releases exactly once with (0, 0).
    field.clear()
    assert av.update(51.50010, -0.0714, 0.0, now=1.0) is True     # still in pass-hold
    assert av.update(51.50010, -0.0714, 0.0, now=10.0) is False   # past pass_hold_s
    assert not av.avoiding and nav.override == (0, 0)


# --------------------------------------------------------------------------- #
# Full closed loop: LOS nav + avoidance + sim kinematics
# --------------------------------------------------------------------------- #
def test_boat_routes_around_obstacle_on_track():
    cfg = NavConfig()
    nav = Navigator(pico=None, config=cfg)
    # Obstacle sitting on the straight A→B track, ~halfway.
    obs = SimObstacle((A[0] + B[0]) / 2, -0.0714, radius_m=4.0)
    field = ObstacleField([obs])
    avoider = SimAvoider(field, nav)

    max_speed_mps, max_turn_dps, dt = 1.5, 30.0, 0.1
    DEG, R = math.pi / 180.0, 6_371_000.0
    lat, lon, hdg = A[0], A[1], 0.0
    min_center = 1e9
    arrived = False
    t = 0.0
    for _ in range(8000):                       # up to 800 s
        # Same control the sim's nav loop runs: avoidance override wins, else LOS.
        # Feed the avoider simulated time so its bug-escape pass-hold is on the
        # sim clock, not wall time.
        avoider.update(lat, lon, hdg, now=t)
        if nav._avoid_left != 0 or nav._avoid_right != 0:
            left, right = nav._avoid_left, nav._avoid_right
        else:
            left, right, dist, brg, err, arrived = nav.compute_throttle(
                lat, lon, hdg, B[0], B[1], A[0], A[1])
            if arrived:
                break
        min_center = min(min_center, haversine_distance(lat, lon, obs.lat, obs.lon))
        speed = (left + right) / 2.0 / 100.0 * max_speed_mps
        hdg = (hdg + (left - right) / 200.0 * max_turn_dps * dt) % 360.0
        d = speed * dt
        hr = hdg * DEG
        lat += d * math.cos(hr) / R / DEG
        lon += d * math.sin(hr) / (R * math.cos(lat * DEG)) / DEG
        t += dt

    # Never entered the obstacle disc...
    assert min_center > obs.radius_m, f"collided (min center dist {min_center:.1f} m)"
    # ...and — with the bug-style escape — routed past it to the waypoint.
    assert arrived, "boat did not reach the waypoint after avoiding"
