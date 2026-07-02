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
        # Right turn: left motor faster → boat pivots right
        assert left >= right

    def test_target_to_the_left(self):
        # Heading north (0°), target is to the west → need left turn
        left, right, dist, brg, err, arrived = self.nav.compute_throttle(
            51.5000, -0.0600,
            0.0,
            51.5000, -0.0800,
        )
        assert arrived is False
        # Left turn: right motor faster → boat pivots left
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

    def test_hard_error_pivots_in_place(self):
        # 180° error → the boat should pivot on the spot: forward speed gated to
        # ~0 and a strong differential (inner motor reversing hard).
        left, right, dist, brg, err, arrived = self.nav.compute_throttle(
            51.5000, -0.0714,
            180.0,  # Heading south
            51.5100, -0.0714,  # Target north (180° error)
        )
        assert arrived is False
        # Near-zero net forward push, motors near-antisymmetric (a spin).
        assert abs(left + right) <= 4
        # Inner motor reverses hard for the pivot.
        assert min(left, right) < -self.config.turn_min_throttle
        # Differential is close to full turn authority.
        assert abs(left - right) >= self.config.turn_authority_throttle

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

    def _fwd_at_error(self, hdg, tgt_lat, tgt_lon):
        """Return the net forward push (left+right)/2 for a far waypoint at the
        given heading, so distance scaling is saturated and only the alignment
        gate varies the forward speed."""
        left, right, *_ = self.nav.compute_throttle(
            51.5000, -0.0714, hdg, tgt_lat, tgt_lon,
        )
        return (left + right) / 2.0

    def test_forward_speed_gated_by_alignment(self):
        # Aligned → full cruise; large error → forward push collapses toward
        # zero so the boat pivots in place before driving. Both waypoints are
        # ~1km away, so distance scaling is identical and only alignment differs.
        aligned_fwd = self._fwd_at_error(0.0, 51.5100, -0.0714)      # dead ahead
        misaligned_fwd = self._fwd_at_error(0.0, 51.5000, -0.0586)   # 90° to east
        assert aligned_fwd == self.config.cruise_throttle
        assert misaligned_fwd < 0.25 * self.config.cruise_throttle

    def test_aligns_before_one_third_of_leg(self):
        # Integration: from a fresh goto with a 90° error, the boat must be
        # pointed at the waypoint (error within tolerance) before it has
        # travelled one third of the initial leg distance.
        import math

        from pi5.navigation.geo import haversine_distance

        # Simple kinematic rollout mirroring the simulator's motion model.
        max_speed_mps = 1.5
        max_turn_dps = 30.0
        dt = 0.1
        lat, lon, hdg = 51.5000, -0.0714, 0.0        # heading north
        tgt_lat, tgt_lon = 51.5000, -0.0714 + 0.0013  # ~90 m due east → 90° error
        start_dist = haversine_distance(lat, lon, tgt_lat, tgt_lon)
        DEG = math.pi / 180.0
        R = 6371000.0
        aligned_dist = None
        for _ in range(6000):  # up to 600 s
            left, right, dist, brg, err, arrived = self.nav.compute_throttle(
                lat, lon, hdg, tgt_lat, tgt_lon)
            if abs(err) <= self.config.heading_tolerance_deg and aligned_dist is None:
                aligned_dist = start_dist - dist  # distance travelled toward WP
                break
            speed = (left + right) / 2.0 / 100.0 * max_speed_mps
            hdg = (hdg + (left - right) / 200.0 * max_turn_dps * dt) % 360.0
            d = speed * dt
            hr = hdg * DEG
            lat += d * math.cos(hr) / R / DEG
            lon += d * math.sin(hr) / (R * math.cos(lat * DEG)) / DEG
        assert aligned_dist is not None, "boat never aligned"
        assert aligned_dist < start_dist / 3.0, (
            f"aligned after {aligned_dist:.1f}m of a {start_dist:.1f}m leg"
        )
