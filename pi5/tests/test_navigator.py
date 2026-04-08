"""Tests for the Navigator — throttle computation and waypoint arrival."""

from pi5.navigation.navigator import NavConfig, Navigator


class TestComputeThrottle:
    """Test Navigator.compute_throttle() — the pure navigation logic."""

    def setup_method(self):
        self.config = NavConfig(
            arrive_radius_m=5.0,
            cruise_throttle=40,
            heading_tolerance_deg=10.0,
            max_heading_error_deg=90.0,
            turn_min_throttle=15,
        )
        # We only test compute_throttle which is a pure function,
        # so we don't need a real PicoSerial
        self.nav = Navigator(pico=None, config=self.config)

    def test_arrived_within_radius(self):
        left, right, dist, brg, err, arrived = self.nav.compute_throttle(
            51.5067, -0.0714,  # Current pos
            0.0,               # Heading
            51.5067, -0.0714,  # Target (same point)
        )
        assert arrived is True
        assert left == 0
        assert right == 0

    def test_straight_ahead_both_motors_equal(self):
        # Target is due north, heading is north → straight ahead
        left, right, dist, brg, err, arrived = self.nav.compute_throttle(
            51.5000, -0.0714,  # Current pos
            0.0,               # Heading north
            51.5100, -0.0714,  # Target north
        )
        assert arrived is False
        assert left == 40  # cruise_throttle
        assert right == 40
        assert abs(err) < 1.0  # Nearly zero heading error

    def test_target_to_the_right(self):
        # Heading north (0°), target is to the east → need right turn
        # Bearing to east point ≈ 90°, heading error ≈ +90°
        left, right, dist, brg, err, arrived = self.nav.compute_throttle(
            51.5000, -0.0800,  # Current pos
            0.0,               # Heading north
            51.5000, -0.0600,  # Target east
        )
        assert arrived is False
        # Right turn: left motor should be faster than right
        assert left >= right

    def test_target_to_the_left(self):
        # Heading north (0°), target is to the west → need left turn
        left, right, dist, brg, err, arrived = self.nav.compute_throttle(
            51.5000, -0.0600,
            0.0,
            51.5000, -0.0800,
        )
        assert arrived is False
        # Left turn: right motor should be faster than left
        assert right >= left

    def test_within_heading_tolerance_goes_straight(self):
        # Small error (< 10°) → go straight, both equal
        # Target is almost due north with tiny eastward offset
        left, right, dist, brg, err, arrived = self.nav.compute_throttle(
            51.5000, -0.0714,
            0.0,  # Heading north
            51.5100, -0.0713,  # Almost due north
        )
        assert arrived is False
        assert left == self.config.cruise_throttle
        assert right == self.config.cruise_throttle

    def test_minimum_turn_throttle_clamp(self):
        # 180° error → maximum blend, inner motor goes to -turn_min
        left, right, dist, brg, err, arrived = self.nav.compute_throttle(
            51.5000, -0.0714,
            180.0,  # Heading south
            51.5100, -0.0714,  # Target north (180° error)
        )
        assert arrived is False
        # One motor should be clamped to -turn_min_throttle
        assert min(left, right) >= -self.config.turn_min_throttle

    def test_distance_reported_correctly(self):
        left, right, dist, brg, err, arrived = self.nav.compute_throttle(
            51.5000, -0.0714,
            0.0,
            51.5100, -0.0714,
        )
        # ~1.1km north
        assert 1000 < dist < 1200

    def test_far_away_not_arrived(self):
        left, right, dist, brg, err, arrived = self.nav.compute_throttle(
            51.5000, -0.0714,
            0.0,
            52.0000, -0.0714,
        )
        assert arrived is False
        assert dist > 50000  # ~55km

    def test_just_outside_radius(self):
        # 6m north of target (radius is 5m)
        # 6m ≈ 0.000054° latitude
        left, right, dist, brg, err, arrived = self.nav.compute_throttle(
            51.5000 + 0.000054, -0.0714,
            180.0,  # Heading south toward target
            51.5000, -0.0714,
        )
        assert arrived is False

    def test_just_inside_radius(self):
        # 3m north of target (radius is 5m)
        # 3m ≈ 0.000027° latitude
        left, right, dist, brg, err, arrived = self.nav.compute_throttle(
            51.5000 + 0.000027, -0.0714,
            0.0,
            51.5000, -0.0714,
        )
        assert arrived is True
