"""Tests for water-current estimation and current-aware station-keeping."""
import math

from pi5.navigation.current_estimator import CurrentConfig, CurrentEstimator
from pi5.navigation.navigator import NavConfig, Navigator

# ~small local moves; 1 deg lat ~= 111 km, so tiny deltas = metres.
LAT0, LON0 = 40.0, -70.0
M_PER_DEG_LAT = 111_320.0


def _step(lat, lon, dE, dN):
    """Advance a lat/lon by (east, north) metres."""
    dlat = dN / M_PER_DEG_LAT
    dlon = dE / (M_PER_DEG_LAT * math.cos(math.radians(lat)))
    return lat + dlat, lon + dlon


def test_water_velocity_projection():
    est = CurrentEstimator(CurrentConfig(thrust_a=0.4, thrust_b=0.0))
    # Heading east (90), full throttle → water velocity almost purely +East.
    vE, vN = est.water_velocity(1.0, 90.0)
    assert vE > 0.35 and abs(vN) < 1e-6


def test_estimates_pure_drift_when_idle():
    """Throttle 0, boat carried east at 0.5 m/s → estimator recovers set≈090, drift≈0.5."""
    est = CurrentEstimator(CurrentConfig(vel_lpf=1.0, cur_lpf=1.0))
    lat, lon = LAT0, LON0
    set_deg = drift = 0.0
    for i in range(30):
        t = i * 1.0
        set_deg, drift = est.update(t, lat, lon, heading_deg=0.0, throttle_frac=0.0)
        lat, lon = _step(lat, lon, 0.5, 0.0)  # +0.5 m/s east
    assert abs(drift - 0.5) < 0.1
    assert abs(((set_deg - 90.0 + 180) % 360) - 180) < 8  # ~090 (flows east)


def test_near_zero_current_when_motion_matches_model():
    """Boat moves exactly per the thrust model (heading north) → tiny drift."""
    cfg = CurrentConfig(thrust_a=0.5, thrust_b=0.0, vel_lpf=1.0, cur_lpf=1.0,
                        min_speed_valid=0.05)
    est = CurrentEstimator(cfg)
    lat, lon = LAT0, LON0
    drift = 1.0
    for i in range(30):
        t = i * 1.0
        # heading north (0), throttle 1.0 → model says 0.5 m/s north; move that.
        _, drift = est.update(t, lat, lon, heading_deg=0.0, throttle_frac=1.0)
        lat, lon = _step(lat, lon, 0.0, 0.5)
    assert drift < 0.12


def test_station_keep_points_into_current():
    """With a known current and the boat on-station, station-keeping should
    command a course INTO the current (opposing it) and non-zero throttle."""
    nav = Navigator.__new__(Navigator)          # bypass async pico wiring
    nav._config = NavConfig()
    nav._hold_lat, nav._hold_lon = LAT0, LON0
    # Inject an eastward current (flows toward +E) into the estimator.
    nav._current = CurrentEstimator()
    nav._current.cE, nav._current.cN = 0.30, 0.0
    nav._current._have = True
    # Boat sits exactly on the hold point, heading north.
    left, right = nav.station_keep(LAT0, LON0, hdg=0.0)
    # It must fight the current (non-zero command).
    assert left != 0 or right != 0
    # Required water velocity is -current = due West → target course ~270°.
    # From heading 0, that's a hard left turn: right motor should lead (right>left).
    assert right >= left


def test_station_keep_idle_when_on_station_no_current():
    nav = Navigator.__new__(Navigator)
    nav._config = NavConfig()
    nav._hold_lat, nav._hold_lon = LAT0, LON0
    nav._current = CurrentEstimator()           # zero current, not valid yet
    left, right = nav.station_keep(LAT0, LON0, hdg=0.0)
    assert (left, right) == (0, 0)
