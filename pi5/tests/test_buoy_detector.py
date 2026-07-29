"""Tests for the classical buoy screen (pi5/cv/buoy_detector.py).

The shipped COCO detector has no 'buoy' class, so this module is the only thing
that emits the label on real hardware. These build synthetic water scenes rather
than mocking, so they exercise the real HSV/contour path.
"""
from __future__ import annotations

import numpy as np
import pytest

from pi5.cv.buoy_detector import (
    BuoyDetector,
    BuoyDetectorConfig,
    _covered_fraction,
    _iou,
)

cv2 = pytest.importorskip("cv2")

W, H = 640, 480
# Desaturated blue-grey: what open water actually looks like in HSV terms.
WATER_BGR = (110, 100, 95)
ORANGE_BGR = (0, 100, 255)     # a classic orange navigation buoy
GREEN_BGR = (40, 200, 40)


def _water(w: int = W, h: int = H):
    frame = np.zeros((h, w, 3), np.uint8)
    frame[:, :] = WATER_BGR
    return frame


def _with_blob(colour=ORANGE_BGR, centre=(320, 300), radius=12, w=W, h=H):
    frame = _water(w, h)
    cv2.circle(frame, centre, radius, colour, -1)
    return frame


def test_finds_an_orange_buoy_on_water():
    got = BuoyDetector().detect(_with_blob())
    assert len(got) == 1
    x1, y1, x2, y2, label, conf = got[0]
    assert label == "buoy"
    # box should bracket the blob we drew at (320, 300) r=12
    assert x1 <= 320 <= x2 and y1 <= 300 <= y2
    assert 0.0 < conf <= 1.0


def test_empty_water_yields_nothing():
    """The false-positive floor: flat water must not produce buoys."""
    assert BuoyDetector().detect(_water()) == []


def test_overlapping_yolo_box_wins_so_a_lifejacket_stays_a_person():
    """Safety property: a classified object is never relabelled as a buoy.

    An orange life jacket is exactly the colour/shape this screen looks for, so
    without suppression a CRITICAL 'person' would be shadowed by a WARNING
    'buoy' box on the same pixels.
    """
    frame = _with_blob()
    person = (300, 280, 340, 320, "person", 0.82)
    assert BuoyDetector().detect(frame, [person]) == []
    # ...and with the person elsewhere, the buoy still reports.
    elsewhere = (10, 400, 60, 460, "person", 0.82)
    assert len(BuoyDetector().detect(frame, [elsewhere])) == 1


def test_sky_and_treeline_band_is_skipped():
    """A blob above roi_top_frac (sky/bank) is ignored, not charted."""
    high = _with_blob(centre=(320, 40), radius=12)     # 40/480 = 0.08 → in the skipped band
    assert BuoyDetector().detect(high) == []


def test_streaks_are_rejected_by_aspect():
    """Sun glitter lies in long thin streaks; buoys are compact."""
    frame = _water()
    cv2.rectangle(frame, (200, 300), (320, 312), ORANGE_BGR, -1)   # 120x12 → aspect 10
    assert BuoyDetector().detect(frame) == []


def test_oversized_blob_is_rejected():
    """Own hull / dock / a glare band must not become one giant buoy."""
    big = _with_blob(centre=(320, 340), radius=100)
    assert BuoyDetector().detect(big) == []


def test_green_is_opt_in():
    frame = _with_blob(colour=GREEN_BGR)
    assert BuoyDetector().detect(frame) == []
    on = BuoyDetector(BuoyDetectorConfig(include_green=True))
    assert len(on.detect(frame)) == 1


def test_candidate_cap_is_honoured():
    frame = _water()
    for i in range(8):
        cv2.circle(frame, (60 + i * 60, 300), 10, ORANGE_BGR, -1)
    det = BuoyDetector(BuoyDetectorConfig(max_candidates=3))
    assert len(det.detect(frame)) == 3


def test_disabled_is_a_noop():
    det = BuoyDetector(BuoyDetectorConfig(enabled=False))
    assert det.detect(_with_blob()) == []


def test_confidence_stays_below_a_confident_yolo_box():
    """Scores are deliberately capped so a colour blob never outranks a real
    classification when _infer picks the primary tracked target."""
    got = BuoyDetector().detect(_with_blob())
    assert got and got[0][5] <= 0.80


def test_bad_input_degrades_quietly():
    det = BuoyDetector()
    assert det.detect(None) == []
    assert det.detect(np.zeros((4, 4, 3), np.uint8)) == []


def test_two_separated_buoys_stay_distinct():
    frame = _water()
    cv2.circle(frame, (180, 300), 12, ORANGE_BGR, -1)
    cv2.circle(frame, (460, 320), 12, ORANGE_BGR, -1)
    assert len(BuoyDetector().detect(frame)) == 2


def test_iou_helper():
    assert _iou((0, 0, 10, 10), (0, 0, 10, 10)) == pytest.approx(1.0)
    assert _iou((0, 0, 10, 10), (20, 20, 30, 30)) == 0.0
    # half-overlap: intersection 50, union 150
    assert _iou((0, 0, 10, 10), (5, 0, 15, 10)) == pytest.approx(50 / 150)


def test_covered_fraction_catches_containment_that_iou_misses():
    """The reason YOLO suppression uses containment instead of IoU.

    A life-jacket blob inside a person box: fully contained, but IoU is only the
    area ratio, so an IoU gate at 0.25 would NOT suppress it.
    """
    jacket = (100, 100, 120, 120)          # 20x20 = 400 px
    person = (80, 60, 140, 200)            # 60x140 = 8400 px
    assert _covered_fraction(jacket, person) == pytest.approx(1.0)
    assert _iou(jacket, person) < 0.25     # ...which is why IoU was wrong here
    assert _covered_fraction((0, 0, 10, 10), (20, 20, 30, 30)) == 0.0
    assert _covered_fraction((0, 0, 10, 10), (5, 0, 15, 10)) == pytest.approx(0.5)


def test_a_swimmer_in_a_life_jacket_charts_no_phantom_buoy():
    """End-to-end containment case: a small saturated blob wholly inside a large
    person box must not be reported, or ObjectMemory would chart a PERMANENT buoy
    marker on top of a person in the water."""
    frame = _with_blob(centre=(320, 300), radius=10)     # the life jacket
    person = (270, 240, 370, 420, "person", 0.71)        # much larger box
    assert BuoyDetector().detect(frame, [person]) == []


def test_partial_overlap_below_the_threshold_still_reports():
    """A real buoy merely clipping the edge of a detection is kept — suppression
    must not be so eager that it blinds the screen near any box."""
    frame = _with_blob(centre=(320, 300), radius=12)
    # box covering only the far-left sliver of the blob
    grazing = (200, 280, 312, 320, "boat", 0.6)
    assert len(BuoyDetector().detect(frame, [grazing])) == 1
