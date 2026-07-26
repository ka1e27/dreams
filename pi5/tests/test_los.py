"""Tests for line-of-sight (LOS) path following — cross-track error, the LOS
guidance law, and the Navigator's leg-based steering that nulls drift."""

import math

from pi5.navigation.geo import cross_track_error, haversine_distance, los_course
from pi5.navigation.navigator import NavConfig, Navigator

# A short northbound leg near the sim start. ~1.1 km of latitude.
A = (51.5000, -0.0714)
B = (51.5100, -0.0714)


class TestCrossTrackError:
    def test_on_track_is_zero(self):
        # A point directly between A and B sits on the track line.
        xte, along, course = cross_track_error(*A, *B, 51.5050, -0.0714)
        assert abs(xte) < 0.5           # within half a metre
        assert 0.0 < along < haversine_distance(*A, *B)
        assert abs(course - 0.0) < 1.0 or abs(course - 360.0) < 1.0

    def test_starboard_is_positive(self):
        # East of a northbound leg → to the right (starboard) → xte > 0.
        xte, _, _ = cross_track_error(*A, *B, 51.5050, -0.0710)
        assert xte > 0

    def test_port_is_negative(self):
        # West of a northbound leg → to the left (port) → xte < 0.
        xte, _, _ = cross_track_error(*A, *B, 51.5050, -0.0718)
        assert xte < 0

    def test_magnitude_reasonable(self):
        # ~0.0004° lon at 51.5°N ≈ 27 m east of the line.
        xte, _, _ = cross_track_error(*A, *B, 51.5050, -0.0714 + 0.0004)
        expected = 0.0004 * (math.pi / 180) * 6_371_000 * math.cos(51.505 * math.pi / 180)
        assert abs(xte - expected) < 2.0


class TestLosCourse:
    def test_on_track_follows_path_course(self):
        course, xte = los_course(*A, *B, 51.5050, -0.0714, lookahead_m=12.0)
        assert abs(xte) < 0.5
        assert abs(((course - 0.0 + 180) % 360) - 180) < 1.0   # ~0° (north)

    def test_starboard_steers_to_port(self):
        # Boat to starboard of a northbound leg should be told to steer to port
        # (a course west of north, i.e. slightly less than 360/0).
        course, xte = los_course(*A, *B, 51.5050, -0.0705, lookahead_m=12.0)
        assert xte > 0
        # course wraps just below 360 (i.e. between 270 and 360 for a left turn).
        assert 270 < course < 360

    def test_larger_error_steers_harder(self):
        near, _ = los_course(*A, *B, 51.5050, -0.07138, lookahead_m=12.0)
        far, _ = los_course(*A, *B, 51.5050, -0.0710, lookahead_m=12.0)
        # Both steer to port (<360); the further-off boat turns more (lower course).
        assert far < near < 360


class TestNavigatorLos:
    def setup_method(self):
        self.nav = Navigator(pico=None, config=NavConfig())

    def test_leg_steers_back_toward_track(self):
        # Heading due north, but drifted east of the track → LOS must command a
        # port (left) correction: right motor faster than left.
        left, right, dist, brg, err, arrived = self.nav.compute_throttle(
            51.5050, -0.0705, 0.0, *B, *A)
        assert not arrived
        assert err < 0            # steer left / port
        assert right >= left

    def test_no_leg_is_legacy_bearing(self):
        # Without a leg start, steering falls back to bearing-to-target (err ~0
        # when already pointed at the target).
        left, right, dist, brg, err, arrived = self.nav.compute_throttle(
            51.5050, -0.0714, 0.0, *B)
        assert abs(err) < 1.0
        assert left == right      # straight ahead

    def test_converges_onto_track(self):
        """Kinematic rollout: a boat that starts offset from the track should be
        driven onto it (cross-track error shrinks well below the start offset)."""
        cfg = NavConfig()
        nav = Navigator(pico=None, config=cfg)
        max_speed_mps, max_turn_dps, dt = 1.5, 30.0, 0.1
        DEG, R = math.pi / 180.0, 6_371_000.0
        # Start on the A latitude but ~20 m east of the track, heading north.
        lat, lon, hdg = 51.5000, -0.0714 + 0.00029, 0.0
        start_xte = abs(cross_track_error(*A, *B, lat, lon)[0])
        assert start_xte > 15
        min_xte = start_xte
        for _ in range(4000):
            left, right, dist, brg, err, arrived = nav.compute_throttle(
                lat, lon, hdg, *B, *A)
            if arrived:
                break
            min_xte = min(min_xte, abs(nav._last_xte))
            speed = (left + right) / 2.0 / 100.0 * max_speed_mps
            hdg = (hdg + (left - right) / 200.0 * max_turn_dps * dt) % 360.0
            d = speed * dt
            hr = hdg * DEG
            lat += d * math.cos(hr) / R / DEG
            lon += d * math.sin(hr) / (R * math.cos(lat * DEG)) / DEG
        # The boat should have captured the track line to within a couple of metres.
        assert min_xte < 3.0, f"never captured track (min xte {min_xte:.1f} m)"
