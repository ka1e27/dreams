"""Tier 3 — threat assessment.

Turns the per-frame detections (class, confidence, stereo distance, bbox) into
*persistent* tracked objects, works out whether each is getting closer, and
decides which one — if any — the radar bar should slew onto. It is the policy
layer between "YOLO saw a vessel" and "point the cameras at it".

Threat model
------------
Each detected class maps to a :class:`ThreatLevel`:

* ``CRITICAL`` — always track, always alert the mission layer (vessel, person,
  kayak, and the COCO fallback label ``boat``).
* ``WARNING``  — track only if it's approaching (debris, buoy).
* ``INFO``     — log only, never track (dock, algae bloom, discoloration).
* ``SURVEY``   — environmental data for the map, never track (water anomaly).

Object identity across frames is maintained by nearest-centroid matching within
a per-class gate, so ``size_history`` (and therefore the approach vector) tracks
a single physical object rather than "whatever the biggest vessel box was this
frame".
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import IntEnum

logger = logging.getLogger(__name__)


class ThreatLevel(IntEnum):
    """Higher value = more urgent. IntEnum so levels sort naturally."""
    SURVEY = 0
    INFO = 1
    WARNING = 2
    CRITICAL = 3


# Class label → threat level. Covers the maritime ONNX classes
# (vessel/kayak/buoy/person/dock/debris) plus the COCO fallback ('boat',
# 'person') and the Tier-1 water-state pseudo-classes.
THREAT_LEVELS: dict[str, ThreatLevel] = {
    # CRITICAL — always track, alert mission layer
    "vessel":        ThreatLevel.CRITICAL,   # approaching boat
    "boat":          ThreatLevel.CRITICAL,   # COCO fallback label for vessel
    "person":        ThreatLevel.CRITICAL,   # person in water
    "kayak":         ThreatLevel.CRITICAL,   # small craft, hard to see
    # WARNING — track if moving toward the boat
    "debris":        ThreatLevel.WARNING,    # large floating debris
    "buoy":          ThreatLevel.WARNING,    # navigation marker
    # INFO — log only, no tracking
    "dock":          ThreatLevel.INFO,       # stationary structure
    "algae_bloom":   ThreatLevel.INFO,       # water-quality anomaly
    "discoloration": ThreatLevel.INFO,       # pollution / sediment
    # SURVEY — log to the survey map, no tracking
    "water_anomaly": ThreatLevel.SURVEY,     # environmental data
}

APPROACHING, STATIC, RECEDING = "APPROACHING", "STATIC", "RECEDING"


def threat_level_for(class_name: str) -> ThreatLevel:
    """Threat level for a class label; unknown labels default to INFO."""
    return THREAT_LEVELS.get(class_name, ThreatLevel.INFO)


@dataclass
class TrackedObject:
    """A single physical object followed across frames."""
    class_name: str
    threat_level: ThreatLevel
    bbox: tuple[int, int, int, int]            # (x1, y1, x2, y2)
    confidence: float
    distance_m: float | None                   # from stereo depth, None if unknown
    apparent_size: float                       # bbox area in pixels
    size_history: list[float] = field(default_factory=list)  # recent apparent sizes
    approach_vector: str = STATIC              # APPROACHING / STATIC / RECEDING
    first_seen: float = 0.0
    last_seen: float = 0.0
    gps_lat: float | None = None
    gps_lon: float | None = None

    @property
    def center(self) -> tuple[float, float]:
        x1, y1, x2, y2 = self.bbox
        return ((x1 + x2) / 2.0, (y1 + y2) / 2.0)

    def to_dict(self) -> dict:
        return {
            "class_name": self.class_name,
            "threat_level": self.threat_level.name,
            "bbox": list(self.bbox),
            "confidence": round(self.confidence, 3),
            "distance_m": round(self.distance_m, 1) if self.distance_m is not None else None,
            "approach_vector": self.approach_vector,
            "gps_lat": self.gps_lat,
            "gps_lon": self.gps_lon,
        }


class ThreatAssessor:
    """Maintains tracked objects and decides what to track / alert on."""

    def __init__(self, *,
                 approach_detection_frames: int = 5,
                 approach_size_threshold: float = 1.10,
                 track_warning_if_approaching: bool = True,
                 mission_alert_distance_m: float = 30.0,
                 lost_ttl_s: float = 3.0,
                 match_gate_px: float = 160.0,
                 history_len: int = 10) -> None:
        self.approach_frames = int(approach_detection_frames)
        self.approach_threshold = float(approach_size_threshold)
        self.track_warning_if_approaching = bool(track_warning_if_approaching)
        self.mission_alert_distance_m = float(mission_alert_distance_m)
        self.lost_ttl_s = float(lost_ttl_s)
        self.match_gate_px = float(match_gate_px)
        self.history_len = int(history_len)
        self._objects: list[TrackedObject] = []

    # -- update ------------------------------------------------------------- #
    def update(self, detections: list[dict],
               gps: "tuple[float | None, float | None] | None" = None,
               now: float | None = None) -> TrackedObject | None:
        """Fold this frame's detections into the tracked set.

        ``detections`` items are dicts with keys ``label``/``class_name``,
        ``confidence``, ``distance_m`` (may be None), and ``bbox`` (x1,y1,x2,y2).
        Returns the current primary threat (or None) for convenience.
        """
        t = time.monotonic() if now is None else float(now)
        gps_lat, gps_lon = (gps or (None, None))

        matched_ids: set[int] = set()
        for det in detections:
            cls = det.get("class_name") or det.get("label")
            bbox = det.get("bbox")
            if not cls or bbox is None:
                continue
            level = threat_level_for(cls)
            x1, y1, x2, y2 = (int(v) for v in bbox)
            area = float(max(0, x2 - x1) * max(0, y2 - y1))
            conf = float(det.get("confidence", 0.0))
            dist = det.get("distance_m")
            dist = float(dist) if dist is not None else None
            cx, cy = (x1 + x2) / 2.0, (y1 + y2) / 2.0

            obj = self._match(cls, cx, cy, matched_ids)
            if obj is None:
                obj = TrackedObject(
                    class_name=cls, threat_level=level, bbox=(x1, y1, x2, y2),
                    confidence=conf, distance_m=dist, apparent_size=area,
                    first_seen=t, last_seen=t, gps_lat=gps_lat, gps_lon=gps_lon)
                self._objects.append(obj)
            else:
                obj.bbox = (x1, y1, x2, y2)
                obj.confidence = conf
                obj.distance_m = dist
                obj.apparent_size = area
                obj.threat_level = level
                obj.last_seen = t
                obj.gps_lat, obj.gps_lon = gps_lat, gps_lon
            matched_ids.add(id(obj))
            obj.size_history.append(area)
            if len(obj.size_history) > self.history_len:
                obj.size_history = obj.size_history[-self.history_len:]
            obj.approach_vector = self._approach_vector(obj)

        # Prune objects not seen recently.
        self._objects = [o for o in self._objects
                         if (t - o.last_seen) <= self.lost_ttl_s]
        return self.get_primary_threat()

    def _match(self, cls: str, cx: float, cy: float,
               used: set[int]) -> TrackedObject | None:
        """Nearest same-class object within the centroid gate, else None."""
        best, best_d = None, self.match_gate_px
        for o in self._objects:
            if o.class_name != cls or id(o) in used:
                continue
            ox, oy = o.center
            d = ((ox - cx) ** 2 + (oy - cy) ** 2) ** 0.5
            if d <= best_d:
                best, best_d = o, d
        return best

    # -- approach vector ---------------------------------------------------- #
    def is_approaching(self, obj: TrackedObject) -> bool:
        """Apparent size growing over the recent window → getting closer."""
        h = obj.size_history
        if len(h) < self.approach_frames:
            return False
        recent = sum(h[-3:]) / 3.0
        earlier = sum(h[-6:-3]) / 3.0 if len(h) >= 6 else sum(h[:3]) / 3.0
        return earlier > 0 and recent > earlier * self.approach_threshold

    def _approach_vector(self, obj: TrackedObject) -> str:
        h = obj.size_history
        if len(h) < self.approach_frames:
            return STATIC
        recent = sum(h[-3:]) / 3.0
        earlier = sum(h[-6:-3]) / 3.0 if len(h) >= 6 else sum(h[:3]) / 3.0
        if earlier <= 0:
            return STATIC
        ratio = recent / earlier
        if ratio > self.approach_threshold:
            return APPROACHING
        if ratio < (1.0 / self.approach_threshold):
            return RECEDING
        return STATIC

    # -- decisions ---------------------------------------------------------- #
    def should_engage_tracking(self, obj: TrackedObject | None) -> bool:
        """Should the radar bar slew onto this object?

        CRITICAL always; WARNING only if it's approaching (and enabled). INFO /
        SURVEY never.
        """
        if obj is None:
            return False
        if obj.threat_level == ThreatLevel.CRITICAL:
            return True
        if (obj.threat_level == ThreatLevel.WARNING
                and self.track_warning_if_approaching):
            return obj.approach_vector == APPROACHING
        return False

    def _priority(self, obj: TrackedObject) -> tuple:
        """Sort key (higher = track first): level, then approaching, then near,
        then confident. Distance unknown sorts as far."""
        approaching = 1 if obj.approach_vector == APPROACHING else 0
        near = -(obj.distance_m if obj.distance_m is not None else 1e9)
        return (int(obj.threat_level), approaching, near, obj.confidence)

    def get_primary_threat(self) -> TrackedObject | None:
        """Highest-priority CRITICAL/WARNING object, or None.

        Only CRITICAL and WARNING objects are candidates (INFO/SURVEY are
        log-only). Ordering: CRITICAL+APPROACHING > CRITICAL > WARNING+APPROACHING
        > WARNING, then nearer, then more confident.
        """
        candidates = [o for o in self._objects
                      if o.threat_level >= ThreatLevel.WARNING]
        if not candidates:
            return None
        return max(candidates, key=self._priority)

    def get_mission_alert(self) -> dict | None:
        """Alert payload for the mission layer when a CRITICAL threat is within
        the alert distance, else None."""
        primary = self.get_primary_threat()
        if primary is None or primary.threat_level != ThreatLevel.CRITICAL:
            return None
        d = primary.distance_m
        if d is None or d > self.mission_alert_distance_m:
            return None
        return {
            "class_name": primary.class_name,
            "distance_m": round(d, 1),
            "threat_level": primary.threat_level.name,
            "approach_vector": primary.approach_vector,
        }

    # -- accessors ---------------------------------------------------------- #
    def active_threats(self) -> list[TrackedObject]:
        """All current CRITICAL/WARNING objects, highest priority first."""
        return sorted(
            [o for o in self._objects if o.threat_level >= ThreatLevel.WARNING],
            key=self._priority, reverse=True)

    def all_objects(self) -> list[TrackedObject]:
        return list(self._objects)

    def clear(self) -> None:
        self._objects = []
