"""Persistent, GPS-anchored memory of objects seen on the water.

Where :mod:`pi5.cv.threat_assessor` tracks objects *in the image* (pixel
centroids, frame to frame, for pointing the radar and steering away), this module
remembers them *on the map*. It answers a different question — "what stationary
things are out here and exactly where are they?" — and its answer survives the
camera looking away and back, because identity here is a **world coordinate**,
not a bounding box.

The flow (mirrors how a lookout builds a mental chart):

1. **Sight.** Each frame, a detection's class + stereo range + bearing-off-the-bow
   is turned into a world position: ``geo.destination_point(boat_fix, heading +
   bearing, range)``. That's a single noisy fix.
2. **Confirm.** Fixes that land near an existing object of the same class are
   folded into it (inverse-distance-weighted mean, so closer/steadier looks pull
   the estimate in); fixes that match nothing start a *candidate*. An object is
   **confirmed** only after ``confirm_sightings`` agreeing looks — that's when a
   marker drops on the map, so one false box never plants a phantom buoy.
3. **Verify, don't re-drop.** Once confirmed, every later sighting just refines
   the stored coordinate (step 2 again). The boat can go back to scanning for new
   things; the known object stays put on the chart and doesn't re-trigger a lock.
4. **Forget the impermanent.** Buoys, docks, rocks — stationary navigation marks —
   are ``PERMANENT`` and kept. People, boats, debris — things that move or drift —
   are ``TRANSIENT`` and expire ``transient_ttl_s`` after they were last seen, so
   a swimmer who has left doesn't haunt the map. Unconfirmed candidates age out
   fast (``candidate_ttl_s``) so noise doesn't accumulate.

Pure Python + :mod:`pi5.navigation.geo` — no camera, model, OpenCV or event loop,
so it unit-tests directly (see ``tests/test_object_memory.py``).
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum

from ..navigation.geo import destination_point, haversine_distance

logger = logging.getLogger(__name__)


class Category(str, Enum):
    """Whether an object is worth keeping once it's out of sight.

    ``str`` mixin so ``.value`` serialises straight into JSON for the map layer.
    """
    PERMANENT = "permanent"   # stationary navigation marks — keep them charted
    TRANSIENT = "transient"   # movers/drifters — forget a while after last seen


# Canonicalise synonymous labels so one physical object doesn't fragment across
# a model's label variants (COCO "boat" vs a maritime model's "vessel"/"Boats").
_CANON = {
    "boats": "boat",
    "vessel": "boat",
    "sail-boat": "sailboat",
    "buoys": "buoy",
    "swimmer": "person",
}

# Class → category. Stationary marks are PERMANENT (charted for good); anything
# that moves or drifts is TRANSIENT (expires after it's gone). A class in NEITHER
# set is *not remembered* — we only map things we can meaningfully place.
_PERMANENT_CLASSES = {"buoy", "dock", "bridge", "rock", "wreck", "pier",
                      "piling", "marker", "beacon"}
_TRANSIENT_CLASSES = {"person", "surfer", "kayak", "boat", "sailboat",
                      "debris", "jetski", "raft", "canoe", "paddleboard"}


def canonical_class(name: str) -> str:
    """Lower-cased, synonym-folded class label."""
    c = (name or "").strip().lower()
    return _CANON.get(c, c)


def category_for(name: str) -> "Category | None":
    """Category for a class label, or ``None`` if it isn't something we remember."""
    c = canonical_class(name)
    if c in _PERMANENT_CLASSES:
        return Category.PERMANENT
    if c in _TRANSIENT_CLASSES:
        return Category.TRANSIENT
    return None


@dataclass
class MapObject:
    """One remembered object, anchored to a world coordinate."""
    id: int
    class_name: str                 # canonical label (e.g. "buoy")
    category: Category
    lat: float                      # current best-estimate position
    lon: float
    confidence: float = 0.0         # best detection confidence seen
    distance_m: float | None = None  # range at the most recent sighting
    sightings: int = 0
    confirmed: bool = False
    first_seen: float = 0.0         # wall-clock (time.time) — for the UI age
    last_seen: float = 0.0          # wall-clock of the most recent sighting
    # Inverse-distance-weighted position accumulators (closer looks weigh more).
    _sw: float = field(default=0.0, repr=False)
    _sw_lat: float = field(default=0.0, repr=False)
    _sw_lon: float = field(default=0.0, repr=False)
    _last_mono: float = field(default=0.0, repr=False)  # monotonic — for TTL

    def to_dict(self) -> dict:
        now = time.time()
        return {
            "id": self.id,
            "class_name": self.class_name,
            "category": self.category.value,
            "lat": round(self.lat, 7),
            "lon": round(self.lon, 7),
            "confidence": round(self.confidence, 3),
            "distance_m": (round(self.distance_m, 1)
                           if self.distance_m is not None else None),
            "sightings": self.sightings,
            "confirmed": self.confirmed,
            "age_s": round(max(0.0, now - self.first_seen), 1) if self.first_seen else 0.0,
            "last_seen_s": round(max(0.0, now - self.last_seen), 1) if self.last_seen else 0.0,
        }


class ObjectMemory:
    """Confirms, geolocates and ages a set of :class:`MapObject`.

    Feed it one call per detection via :meth:`observe`; call :meth:`expire` once
    per frame to age things out. :meth:`markers` returns the confirmed objects for
    the map. All distances are metres, bearings compass degrees (0-360).
    """

    def __init__(self, *,
                 confirm_sightings: int = 3,
                 match_radius_m: float = 6.0,
                 match_radius_frac: float = 0.08,
                 match_radius_max_m: float = 25.0,
                 transient_ttl_s: float = 45.0,
                 candidate_ttl_s: float = 12.0,
                 permanent_ttl_s: float = 0.0,
                 max_range_m: float = 60.0,
                 min_confidence: float = 0.30,
                 max_objects: int = 200) -> None:
        self.confirm_sightings = max(1, int(confirm_sightings))
        self.match_radius_m = float(match_radius_m)
        self.match_radius_frac = float(match_radius_frac)
        self.match_radius_max_m = float(match_radius_max_m)
        self.transient_ttl_s = float(transient_ttl_s)
        self.candidate_ttl_s = float(candidate_ttl_s)
        # 0 (or negative) = keep permanent objects for the whole session.
        self.permanent_ttl_s = float(permanent_ttl_s)
        self.max_range_m = float(max_range_m)
        self.min_confidence = float(min_confidence)
        self.max_objects = int(max_objects)
        self._objects: list[MapObject] = []
        self._next_id = 1

    # -- observation -------------------------------------------------------- #
    def observe(self, class_name: str, boat_lat: float, boat_lon: float,
                boat_heading_deg: float, rel_bearing_deg: float,
                distance_m: float | None, confidence: float = 1.0,
                now: float | None = None) -> "MapObject | None":
        """Fold one detection into the memory.

        Args:
            class_name: Detected class label (case-insensitive; synonyms folded).
            boat_lat, boat_lon: Boat GPS fix (decimal degrees).
            boat_heading_deg: Boat compass heading (0-360, 0 = north).
            rel_bearing_deg: Object bearing off the bow, **+ starboard / − port**
                (what ``pipeline._avoidance_bearing`` derives from the bbox).
            distance_m: Stereo range to the object in metres. Required — an object
                with no range can't be placed, so ``None`` is ignored.
            confidence: Detection confidence (0-1).
            now: Monotonic timestamp (``time.monotonic()`` if omitted) — used only
                for TTL/expiry, so tests can drive it deterministically.

        Returns:
            The created/updated :class:`MapObject`, or ``None`` if the detection
            wasn't remembered (unknown class, no range, out of range, low conf,
            or no GPS fix).
        """
        cat = category_for(class_name)
        if cat is None:
            return None
        if distance_m is None or distance_m <= 0.0 or distance_m > self.max_range_m:
            return None
        if confidence < self.min_confidence:
            return None
        if boat_lat is None or boat_lon is None or (not boat_lat and not boat_lon):
            return None

        mono = time.monotonic() if now is None else float(now)
        wall = time.time()
        cls = canonical_class(class_name)
        true_bearing = (float(boat_heading_deg) + float(rel_bearing_deg)) % 360.0
        obj_lat, obj_lon = destination_point(
            boat_lat, boat_lon, true_bearing, distance_m)

        obj = self._match(cls, obj_lat, obj_lon, distance_m)
        if obj is None:
            obj = MapObject(
                id=self._next_id, class_name=cls, category=cat,
                lat=obj_lat, lon=obj_lon, confidence=float(confidence),
                distance_m=float(distance_m), first_seen=wall)
            self._next_id += 1
            self._objects.append(obj)

        # Inverse-distance-squared weight: a fix taken from 5 m away is far more
        # trustworthy than one from 40 m (stereo range error grows with range),
        # so it pulls the running mean harder.
        w = 1.0 / max(1.0, float(distance_m)) ** 2
        obj._sw += w
        obj._sw_lat += w * obj_lat
        obj._sw_lon += w * obj_lon
        obj.lat = obj._sw_lat / obj._sw
        obj.lon = obj._sw_lon / obj._sw

        obj.sightings += 1
        obj.confidence = max(obj.confidence, float(confidence))
        obj.distance_m = float(distance_m)
        obj.category = cat
        obj.last_seen = wall
        obj._last_mono = mono
        if not obj.confirmed and obj.sightings >= self.confirm_sightings:
            obj.confirmed = True
            logger.info("Map object CONFIRMED: %s #%d at %.6f,%.6f (%d sightings)",
                        obj.class_name, obj.id, obj.lat, obj.lon, obj.sightings)
        return obj

    def _match(self, cls: str, lat: float, lon: float,
               distance_m: float) -> "MapObject | None":
        """Nearest same-class object within the (range-scaled) spatial gate."""
        gate = min(self.match_radius_max_m,
                   self.match_radius_m + self.match_radius_frac * float(distance_m))
        best, best_d = None, gate
        for o in self._objects:
            if o.class_name != cls:
                continue
            d = haversine_distance(lat, lon, o.lat, o.lon)
            if d <= best_d:
                best, best_d = o, d
        return best

    # -- ageing ------------------------------------------------------------- #
    def expire(self, now: float | None = None) -> int:
        """Drop objects past their TTL. Returns how many were removed.

        * Unconfirmed candidates: ``candidate_ttl_s`` (noise ages out fast).
        * Confirmed TRANSIENT (people/boats/debris): ``transient_ttl_s``.
        * Confirmed PERMANENT (buoys/docks/rocks): kept, unless
          ``permanent_ttl_s`` > 0 and exceeded.
        """
        mono = time.monotonic() if now is None else float(now)
        keep: list[MapObject] = []
        removed = 0
        for o in self._objects:
            age = mono - o._last_mono
            if not o.confirmed:
                ttl = self.candidate_ttl_s
            elif o.category == Category.TRANSIENT:
                ttl = self.transient_ttl_s
            else:  # confirmed PERMANENT
                ttl = self.permanent_ttl_s if self.permanent_ttl_s > 0 else None
            if ttl is not None and age > ttl:
                removed += 1
                continue
            keep.append(o)
        self._objects = keep
        self._enforce_cap()
        return removed

    def _enforce_cap(self) -> None:
        """Bound memory size, sacrificing the least valuable first (unconfirmed,
        then transient, then oldest)."""
        if len(self._objects) <= self.max_objects:
            return
        self._objects.sort(key=lambda o: (
            o.confirmed,
            o.category == Category.PERMANENT,
            o._last_mono,
        ), reverse=True)
        self._objects = self._objects[:self.max_objects]

    # -- queries ------------------------------------------------------------ #
    def known_confirmed_near(self, lat: float, lon: float, *,
                             class_name: str | None = None,
                             radius_m: float | None = None) -> bool:
        """Is there a confirmed object near (lat, lon)?

        Used by the pipeline to decide it needn't lock the radar onto a landmark
        it has already charted — freeing the sensor to keep scanning for the
        unknown even with known things nearby. Optionally restricted to one class.
        """
        r = self.match_radius_m if radius_m is None else float(radius_m)
        cls = canonical_class(class_name) if class_name else None
        for o in self._objects:
            if not o.confirmed:
                continue
            if cls is not None and o.class_name != cls:
                continue
            if haversine_distance(lat, lon, o.lat, o.lon) <= r:
                return True
        return False

    def markers(self) -> list[dict]:
        """Confirmed objects (the ones on the map), permanent first then newest."""
        confirmed = [o for o in self._objects if o.confirmed]
        confirmed.sort(key=lambda o: (o.category == Category.PERMANENT, o.last_seen),
                       reverse=True)
        return [o.to_dict() for o in confirmed]

    def all_objects(self) -> list[MapObject]:
        """Everything currently held, candidates included (for tests/debug)."""
        return list(self._objects)

    def stats(self) -> dict:
        """Compact counts for the vision-state snapshot."""
        confirmed = [o for o in self._objects if o.confirmed]
        return {
            "total": len(self._objects),
            "confirmed": len(confirmed),
            "permanent": sum(1 for o in confirmed if o.category == Category.PERMANENT),
            "transient": sum(1 for o in confirmed if o.category == Category.TRANSIENT),
        }

    def clear(self) -> None:
        self._objects = []
