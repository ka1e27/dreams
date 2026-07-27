"""Regression tests for ThreatAssessor track association.

Covers the nearest-neighbour matching in ``_match`` — previously exercised only
indirectly through the vision-pipeline tests. Locks in the squared-distance
comparison (an object must fold into the *nearest* same-class track within the
gate, not merely the first one found).
"""
from __future__ import annotations

from pi5.cv.threat_assessor import ThreatAssessor


def _det(cx: float, cy: float, cls: str = "person", conf: float = 0.9) -> dict:
    """A detection dict for a 20x20 box centered at (cx, cy)."""
    return {
        "class_name": cls,
        "confidence": conf,
        "distance_m": None,
        "bbox": (cx - 10, cy - 10, cx + 10, cy + 10),
    }


def test_match_picks_nearest_same_class_within_gate():
    ta = ThreatAssessor(match_gate_px=160.0)

    # Two well-separated tracks: A@(10,10) and B@(250,10) — 240px apart, beyond
    # the 160px gate, so they stay distinct.
    ta.update([_det(10, 10), _det(250, 10)], now=0.0)
    assert len(ta._objects) == 2

    # One detection at (100,10): 90px from A, 150px from B (both inside the gate).
    # It must update A (the nearer) and spawn no third track.
    ta.update([_det(100, 10)], now=0.1)
    assert len(ta._objects) == 2, "nearest match should update A, not spawn a track"

    centers = sorted(o.center[0] for o in ta._objects)
    assert abs(centers[0] - 100) < 1.0   # A moved 10 -> 100
    assert abs(centers[1] - 250) < 1.0   # B unchanged


def test_far_detection_beyond_gate_spawns_new_track():
    ta = ThreatAssessor(match_gate_px=160.0)
    ta.update([_det(10, 10)], now=0.0)
    assert len(ta._objects) == 1

    # 300px away — outside the gate — so a new track, not a match.
    ta.update([_det(310, 10)], now=0.1)
    assert len(ta._objects) == 2
