"""Tests for SimObjectMapper — the simulator's ground-truth feeder for the
GPS-anchored object memory (pi5/navigation/sim_obstacles.py).

Confirms that dropping a labelled obstacle in the sim field and running the
mapper builds the same confirm→map→forget behaviour the boat gets from vision,
with the marker landing on the obstacle's true position.
"""
from __future__ import annotations

from pi5.cv.object_memory import ObjectMemory
from pi5.navigation.geo import destination_point, haversine_distance
from pi5.navigation.sim_obstacles import ObstacleField, SimObjectMapper

LAT0, LON0 = 51.506726, -0.071438


def _noiseless_mapper(field, mem):
    return SimObjectMapper(field, mem, range_noise_frac=0.0, bearing_noise_deg=0.0)


def test_mapper_confirms_buoy_at_true_position():
    field = ObstacleField()
    b_lat, b_lon = destination_point(LAT0, LON0, 0.0, 25.0)   # buoy 25 m due north
    field.add(b_lat, b_lon, radius_m=1.0, label="buoy")
    mem = ObjectMemory(confirm_sightings=3)
    mapper = _noiseless_mapper(field, mem)
    for i in range(3):
        assert mapper.update(LAT0, LON0, 0.0, now=float(i)) == 1
    markers = mem.markers()
    assert len(markers) == 1
    m = markers[0]
    assert m["class_name"] == "buoy" and m["category"] == "permanent"
    assert haversine_distance(m["lat"], m["lon"], b_lat, b_lon) < 0.5


def test_mapper_ignores_generic_obstacle_label():
    field = ObstacleField()
    o_lat, o_lon = destination_point(LAT0, LON0, 0.0, 20.0)
    field.add(o_lat, o_lon, radius_m=4.0, label="obstacle")  # not a mapped class
    mem = ObjectMemory(confirm_sightings=1)
    mapper = _noiseless_mapper(field, mem)
    for i in range(3):
        mapper.update(LAT0, LON0, 0.0, now=float(i))
    assert mem.markers() == []


def test_mapper_out_of_fov_not_seen():
    field = ObstacleField()
    # Buoy due east while the boat looks north → outside the forward cone.
    b_lat, b_lon = destination_point(LAT0, LON0, 90.0, 25.0)
    field.add(b_lat, b_lon, radius_m=1.0, label="buoy")
    mem = ObjectMemory(confirm_sightings=1)
    mapper = _noiseless_mapper(field, mem)
    assert mapper.update(LAT0, LON0, 0.0, now=0.0) == 0
    assert mem.markers() == []


def test_mapper_person_expires_but_buoy_stays():
    field = ObstacleField()
    b_lat, b_lon = destination_point(LAT0, LON0, -10.0, 20.0)
    p_lat, p_lon = destination_point(LAT0, LON0, 10.0, 15.0)
    field.add(b_lat, b_lon, radius_m=1.0, label="buoy")
    field.add(p_lat, p_lon, radius_m=1.0, label="person")
    mem = ObjectMemory(confirm_sightings=2, transient_ttl_s=20.0, permanent_ttl_s=0.0)
    mapper = _noiseless_mapper(field, mem)
    for i in range(2):
        mapper.update(LAT0, LON0, 0.0, now=float(i))
    assert {m["class_name"] for m in mem.markers()} == {"buoy", "person"}
    # The person leaves the field; the buoy stays put.
    field.obstacles = [o for o in field.obstacles if o.label == "buoy"]
    mapper.update(LAT0, LON0, 0.0, now=100.0)   # long after → person forgotten
    classes = {m["class_name"] for m in mem.markers()}
    assert classes == {"buoy"}
