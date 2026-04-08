"""Tests for navigation math — haversine distance, bearing, heading difference.

Validates against known reference values and edge cases.
"""
import math
import pytest

from pi5.navigation.geo import bearing, haversine_distance, heading_diff


class TestHaversineDistance:
    """Test haversine_distance()."""

    def test_same_point_is_zero(self):
        assert haversine_distance(51.5, -0.1, 51.5, -0.1) == 0.0

    def test_known_distance_london_to_paris(self):
        # London (51.5074, -0.1278) to Paris (48.8566, 2.3522)
        dist = haversine_distance(51.5074, -0.1278, 48.8566, 2.3522)
        # Should be ~343 km
        assert 340_000 < dist < 346_000

    def test_short_distance_within_dock(self):
        # Two points in St Katharine's Dock (~60m apart)
        dist = haversine_distance(51.506726, -0.071438, 51.506902, -0.071008)
        assert 30 < dist < 60

    def test_equator_one_degree_longitude(self):
        # 1 degree of longitude at equator ≈ 111.32 km
        dist = haversine_distance(0, 0, 0, 1)
        assert 111_000 < dist < 112_000

    def test_north_pole_to_south_pole(self):
        # Half the circumference ≈ 20,003 km
        dist = haversine_distance(90, 0, -90, 0)
        assert 20_000_000 < dist < 20_050_000

    def test_symmetry(self):
        d1 = haversine_distance(51.5, -0.1, 48.8, 2.3)
        d2 = haversine_distance(48.8, 2.3, 51.5, -0.1)
        assert abs(d1 - d2) < 0.01

    def test_negative_coordinates(self):
        # Sydney to Auckland
        dist = haversine_distance(-33.8688, 151.2093, -36.8485, 174.7633)
        assert 2_100_000 < dist < 2_200_000


class TestBearing:
    """Test bearing()."""

    def test_due_north(self):
        # Point directly north → bearing ≈ 0°
        brg = bearing(51.5, -0.1, 52.5, -0.1)
        assert brg < 1.0 or brg > 359.0

    def test_due_east(self):
        # Point directly east → bearing ≈ 90°
        brg = bearing(0, 0, 0, 1)
        assert 89.0 < brg < 91.0

    def test_due_south(self):
        # Point directly south → bearing ≈ 180°
        brg = bearing(52.5, -0.1, 51.5, -0.1)
        assert 179.0 < brg < 181.0

    def test_due_west(self):
        # Point directly west → bearing ≈ 270°
        brg = bearing(0, 1, 0, 0)
        assert 269.0 < brg < 271.0

    def test_northeast(self):
        brg = bearing(51.5, -0.1, 52.0, 0.5)
        assert 30 < brg < 60

    def test_result_range(self):
        # Bearing should always be 0–360
        for lat2, lon2 in [(52, 1), (50, -2), (53, -0.1), (51, 0.1)]:
            brg = bearing(51.5, -0.1, lat2, lon2)
            assert 0 <= brg < 360


class TestHeadingDiff:
    """Test heading_diff()."""

    def test_same_heading(self):
        assert heading_diff(90, 90) == 0.0

    def test_right_turn_small(self):
        # Current 90°, target 120° → +30° (turn right)
        assert heading_diff(90, 120) == pytest.approx(30.0)

    def test_left_turn_small(self):
        # Current 120°, target 90° → -30° (turn left)
        assert heading_diff(120, 90) == pytest.approx(-30.0)

    def test_wrap_clockwise(self):
        # Current 350°, target 10° → +20° (shortest path is right)
        assert heading_diff(350, 10) == pytest.approx(20.0)

    def test_wrap_counterclockwise(self):
        # Current 10°, target 350° → -20° (shortest path is left)
        assert heading_diff(10, 350) == pytest.approx(-20.0)

    def test_exactly_180(self):
        result = heading_diff(0, 180)
        assert abs(result) == pytest.approx(180.0)

    def test_large_right_turn(self):
        # Current 0°, target 170° → +170°
        assert heading_diff(0, 170) == pytest.approx(170.0)

    def test_large_left_turn(self):
        # Current 0°, target 190° → -170° (shorter to go left)
        assert heading_diff(0, 190) == pytest.approx(-170.0)

    def test_range_always_minus180_to_180(self):
        for current in range(0, 360, 15):
            for target in range(0, 360, 15):
                d = heading_diff(current, target)
                assert -180 <= d <= 180
