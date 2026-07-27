"""Unit tests for the GPS-anchored object memory (pi5/cv/object_memory.py).

Drives ObjectMemory.observe/expire directly with synthetic detections — boat fix
+ heading + bearing-off-the-bow + stereo range — and checks it geolocates,
confirms, refines, and forgets the way the feature requires:

  * a marker only drops after N agreeing sightings (confirmation),
  * repeat sightings refine one object instead of dropping duplicates,
  * buoys/docks (PERMANENT) persist; people/boats (TRANSIENT) expire,
  * identity is a world coordinate, so looking away and back re-acquires.

Pure Python; no camera, model, or event loop.
"""
from __future__ import annotations

import pytest

from pi5.cv.object_memory import (
    Category,
    ObjectMemory,
    canonical_class,
    category_for,
)
from pi5.navigation.geo import bearing, destination_point, haversine_distance

# A calm anchorage to work from (the sim's default start).
LAT0, LON0 = 51.506726, -0.071438


def _confirm(mem, cls="buoy", *, heading=0.0, rel=0.0, dist=10.0, conf=0.9,
             boat=(LAT0, LON0), start=0.0, step=0.1):
    """Observe the same object enough times to confirm it. Returns the object."""
    obj = None
    t = start
    for _ in range(mem.confirm_sightings):
        obj = mem.observe(cls, boat[0], boat[1], heading, rel, dist, conf, now=t)
        t += step
    return obj


# --------------------------------------------------------------------------- #
# Class taxonomy
# --------------------------------------------------------------------------- #
def test_category_mapping():
    assert category_for("buoy") == Category.PERMANENT
    assert category_for("dock") == Category.PERMANENT
    assert category_for("rock") == Category.PERMANENT
    assert category_for("person") == Category.TRANSIENT
    assert category_for("boat") == Category.TRANSIENT
    assert category_for("debris") == Category.TRANSIENT
    assert category_for("water_anomaly") is None
    assert category_for("algae_bloom") is None


def test_canonical_synonyms():
    assert canonical_class("Boats") == "boat"
    assert canonical_class("VESSEL") == "boat"
    assert canonical_class("Sail-Boat") == "sailboat"
    assert canonical_class("swimmer") == "person"
    assert canonical_class("buoy") == "buoy"


# --------------------------------------------------------------------------- #
# What is / isn't remembered
# --------------------------------------------------------------------------- #
def test_unknown_class_not_remembered():
    mem = ObjectMemory()
    assert mem.observe("water_anomaly", LAT0, LON0, 0.0, 0.0, 10.0, 0.9) is None
    assert mem.all_objects() == []


def test_no_range_not_remembered():
    mem = ObjectMemory()
    assert mem.observe("buoy", LAT0, LON0, 0.0, 0.0, None, 0.9) is None
    assert mem.all_objects() == []


def test_out_of_range_ignored():
    mem = ObjectMemory(max_range_m=60.0)
    assert mem.observe("buoy", LAT0, LON0, 0.0, 0.0, 200.0, 0.9) is None


def test_low_confidence_ignored():
    mem = ObjectMemory(min_confidence=0.5)
    assert mem.observe("buoy", LAT0, LON0, 0.0, 0.0, 10.0, 0.1) is None


def test_no_gps_fix_ignored():
    mem = ObjectMemory()
    assert mem.observe("buoy", 0.0, 0.0, 0.0, 0.0, 10.0, 0.9) is None


# --------------------------------------------------------------------------- #
# Geolocation
# --------------------------------------------------------------------------- #
def test_geolocation_matches_forward_geodesic():
    # Heading 90° (east), object 30° to starboard, 25 m out → true bearing 120°.
    mem = ObjectMemory(confirm_sightings=1)
    obj = mem.observe("buoy", LAT0, LON0, 90.0, 30.0, 25.0, 0.9, now=0.0)
    exp_lat, exp_lon = destination_point(LAT0, LON0, 120.0, 25.0)
    assert obj is not None
    assert obj.lat == pytest.approx(exp_lat, abs=1e-7)
    assert obj.lon == pytest.approx(exp_lon, abs=1e-7)
    # And it really is 25 m away on the chart at compass 120°.
    assert haversine_distance(LAT0, LON0, obj.lat, obj.lon) == pytest.approx(25.0, abs=0.05)
    assert bearing(LAT0, LON0, obj.lat, obj.lon) == pytest.approx(120.0, abs=0.2)


def test_port_bearing_is_negative():
    # Heading 0°, 40° to port (−40) → true bearing 320°.
    mem = ObjectMemory(confirm_sightings=1)
    obj = mem.observe("buoy", LAT0, LON0, 0.0, -40.0, 15.0, 0.9, now=0.0)
    assert bearing(LAT0, LON0, obj.lat, obj.lon) == pytest.approx(320.0, abs=0.2)


# --------------------------------------------------------------------------- #
# Confirmation — a marker only drops after N agreeing sightings
# --------------------------------------------------------------------------- #
def test_marker_only_after_confirmation():
    mem = ObjectMemory(confirm_sightings=3)
    o1 = mem.observe("buoy", LAT0, LON0, 0.0, 0.0, 10.0, 0.9, now=0.0)
    assert o1 is not None and not o1.confirmed
    assert mem.markers() == []                      # candidate: not on the map yet
    mem.observe("buoy", LAT0, LON0, 0.0, 0.0, 10.0, 0.9, now=0.1)
    assert mem.markers() == []                      # 2 sightings: still a candidate
    o3 = mem.observe("buoy", LAT0, LON0, 0.0, 0.0, 10.0, 0.9, now=0.2)
    assert o3.confirmed                             # 3rd sighting confirms it
    assert len(mem.markers()) == 1
    assert mem.markers()[0]["class_name"] == "buoy"
    assert mem.markers()[0]["confirmed"] is True


def test_single_false_detection_never_marks():
    mem = ObjectMemory(confirm_sightings=3)
    mem.observe("buoy", LAT0, LON0, 12.0, 5.0, 8.0, 0.9, now=0.0)
    assert mem.markers() == []                      # one blip is not a buoy


# --------------------------------------------------------------------------- #
# Repeat sightings refine ONE object (verify, don't re-drop) + converge to truth
# --------------------------------------------------------------------------- #
def test_repeat_sightings_do_not_duplicate():
    mem = ObjectMemory(confirm_sightings=3)
    for i in range(10):
        mem.observe("buoy", LAT0, LON0, 0.0, 0.0, 10.0, 0.9, now=float(i))
    assert len(mem.all_objects()) == 1              # one object, not ten
    assert mem.all_objects()[0].sightings == 10


def test_estimate_converges_to_truth_as_boat_approaches():
    # A real buoy sits at a known spot. The boat approaches along a line, taking a
    # noisy fix each step (alternating bearing/range error). Closer fixes weigh
    # more (1/range^2), so the running estimate should tighten onto the truth —
    # and beat the crude first far-range fix.
    mem = ObjectMemory(confirm_sightings=3, match_radius_m=8.0)
    true_lat, true_lon = destination_point(LAT0, LON0, 20.0, 60.0)  # buoy 60 m out
    ranges = [55.0, 45.0, 35.0, 25.0, 15.0, 8.0, 5.0]
    first_err = None
    for i, boat_back in enumerate(ranges):
        # Boat sits `boat_back` m short of the buoy, on the same line (bearing 20).
        boat_lat, boat_lon = destination_point(LAT0, LON0, 20.0, 60.0 - boat_back)
        dist = haversine_distance(boat_lat, boat_lon, true_lat, true_lon)
        brg = bearing(boat_lat, boat_lon, true_lat, true_lon)
        # Deterministic sensor noise: ±1.5° bearing, ±4% range, alternating sign.
        s = 1.0 if i % 2 == 0 else -1.0
        obj = mem.observe("buoy", boat_lat, boat_lon, 0.0, brg + 1.5 * s,
                          dist * (1.0 + 0.04 * s), 0.9, now=float(i))
        if first_err is None:
            first_err = haversine_distance(obj.lat, obj.lon, true_lat, true_lon)
    assert len(mem.all_objects()) == 1
    final_err = haversine_distance(obj.lat, obj.lon, true_lat, true_lon)
    assert final_err < 2.0                 # tightened onto the real buoy
    assert final_err < first_err           # closer looks improved the estimate


def test_two_distinct_buoys_stay_separate():
    mem = ObjectMemory(confirm_sightings=2)
    # Two buoys ~40 m apart (well beyond the match gate).
    _confirm(mem, "buoy", heading=0.0, rel=0.0, dist=20.0)     # due north
    _confirm(mem, "buoy", heading=90.0, rel=0.0, dist=20.0)    # due east
    assert len(mem.all_objects()) == 2
    assert len(mem.markers()) == 2


def test_different_classes_same_spot_are_distinct():
    mem = ObjectMemory(confirm_sightings=1)
    mem.observe("buoy", LAT0, LON0, 0.0, 0.0, 10.0, 0.9, now=0.0)
    mem.observe("person", LAT0, LON0, 0.0, 0.0, 10.0, 0.9, now=0.1)
    assert len(mem.all_objects()) == 2


# --------------------------------------------------------------------------- #
# Look away and re-acquire — identity is the world coordinate
# --------------------------------------------------------------------------- #
def test_reacquire_after_looking_away():
    mem = ObjectMemory(confirm_sightings=3)
    obj = _confirm(mem, "buoy", dist=12.0, start=0.0)
    obj_id, sightings = obj.id, obj.sightings
    # Camera looks elsewhere for a while (permanent objects survive expiry)...
    for t in (5.0, 10.0, 20.0):
        mem.expire(now=t)
    assert len(mem.markers()) == 1
    # ...then sees the same buoy again: same object, more sightings, no duplicate.
    again = mem.observe("buoy", LAT0, LON0, 0.0, 0.0, 12.0, 0.9, now=25.0)
    assert again.id == obj_id
    assert again.sightings == sightings + 1
    assert len(mem.all_objects()) == 1


# --------------------------------------------------------------------------- #
# Forgetting — transient expires, permanent persists, candidates age out
# --------------------------------------------------------------------------- #
def test_transient_expires_after_ttl():
    mem = ObjectMemory(confirm_sightings=2, transient_ttl_s=30.0)
    _confirm(mem, "person", dist=8.0, start=0.0, step=0.5)
    assert len(mem.markers()) == 1
    assert mem.expire(now=20.0) == 0            # still within TTL
    assert len(mem.markers()) == 1
    assert mem.expire(now=100.0) == 1           # long gone → forgotten
    assert mem.markers() == []


def test_permanent_persists_indefinitely():
    mem = ObjectMemory(confirm_sightings=2, transient_ttl_s=30.0, permanent_ttl_s=0.0)
    _confirm(mem, "buoy", dist=10.0, start=0.0, step=0.5)
    assert mem.expire(now=100_000.0) == 0       # buoys stay charted
    assert len(mem.markers()) == 1


def test_permanent_ttl_when_configured():
    mem = ObjectMemory(confirm_sightings=1, permanent_ttl_s=60.0)
    mem.observe("buoy", LAT0, LON0, 0.0, 0.0, 10.0, 0.9, now=0.0)
    assert mem.expire(now=30.0) == 0
    assert mem.expire(now=90.0) == 1            # exceeded the configured cap


def test_unconfirmed_candidate_ages_out_fast():
    mem = ObjectMemory(confirm_sightings=3, candidate_ttl_s=10.0)
    mem.observe("buoy", LAT0, LON0, 0.0, 0.0, 10.0, 0.9, now=0.0)  # 1 sighting
    assert len(mem.all_objects()) == 1
    assert mem.expire(now=5.0) == 0
    assert mem.expire(now=20.0) == 1            # never confirmed → dropped
    assert mem.all_objects() == []


# --------------------------------------------------------------------------- #
# Queries used by the pipeline / server
# --------------------------------------------------------------------------- #
def test_known_confirmed_near():
    mem = ObjectMemory(confirm_sightings=2)
    obj = _confirm(mem, "buoy", heading=0.0, rel=0.0, dist=20.0)
    assert mem.known_confirmed_near(obj.lat, obj.lon) is True
    assert mem.known_confirmed_near(obj.lat, obj.lon, class_name="buoy") is True
    assert mem.known_confirmed_near(obj.lat, obj.lon, class_name="person") is False
    far_lat, far_lon = destination_point(obj.lat, obj.lon, 0.0, 100.0)
    assert mem.known_confirmed_near(far_lat, far_lon) is False


def test_known_confirmed_near_ignores_candidates():
    mem = ObjectMemory(confirm_sightings=3)
    obj = mem.observe("buoy", LAT0, LON0, 0.0, 0.0, 15.0, 0.9, now=0.0)  # candidate
    assert mem.known_confirmed_near(obj.lat, obj.lon) is False


def test_stats_and_clear():
    mem = ObjectMemory(confirm_sightings=1)
    mem.observe("buoy", LAT0, LON0, 0.0, 0.0, 20.0, 0.9, now=0.0)
    mem.observe("person", LAT0, LON0, 90.0, 0.0, 20.0, 0.9, now=0.1)
    st = mem.stats()
    assert st["confirmed"] == 2
    assert st["permanent"] == 1 and st["transient"] == 1
    mem.clear()
    assert mem.all_objects() == []
    assert mem.stats()["total"] == 0


def test_marker_dict_shape():
    mem = ObjectMemory(confirm_sightings=1)
    mem.observe("buoy", LAT0, LON0, 0.0, 0.0, 20.0, 0.85, now=0.0)
    m = mem.markers()[0]
    for k in ("id", "class_name", "category", "lat", "lon", "confidence",
              "distance_m", "sightings", "confirmed", "age_s"):
        assert k in m
    assert m["category"] == "permanent"


def test_max_objects_cap_keeps_confirmed_permanent():
    mem = ObjectMemory(confirm_sightings=1, max_objects=2, match_radius_m=1.0)
    # Three well-separated buoys; cap is 2 → the cap trims to the most valuable.
    for i, brg in enumerate((0.0, 90.0, 180.0)):
        mem.observe("buoy", LAT0, LON0, brg, 0.0, 30.0, 0.9, now=float(i))
    mem.expire(now=3.0)
    assert len(mem.all_objects()) == 2
