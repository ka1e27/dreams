"""Colour-and-shape buoy finder — supplies the class the COCO model can't.

The shipped detector is a generic COCO ``yolov8n`` (``pi5/cv/models/yolov8n_ncnn_model``).
Its 80 classes include ``person`` and ``boat`` but there is **no buoy** — so on
real hardware nothing ever emits the label that ``threat_assessor`` grades
WARNING and ``object_memory`` charts as a PERMANENT map marker. The whole
"confirm a buoy → drop a GPS marker" feature is therefore dead on the water even
though every downstream layer supports it; only the simulator's ground-truth
``SimObjectMapper`` was exercising it. A trained maritime model (``ml/``) would
fix this properly, but none exists yet (``maritime_yolov8n_info.json`` is a
placeholder with ``mAP50: 0.0``).

A navigation buoy is the easiest thing on a lake to find *without* a neural net:
a small, compact, strongly **saturated** orange / red / yellow object against
desaturated blue-grey water. This finds them with one HSV threshold pass plus a
contour filter — a **measured 0.6-1.0 ms** per frame on a Pi 5 core (640x480 to
1280x720, ripple noise present), against ~30 ms for a YOLO forward pass — and
returns the same ``(x1, y1, x2, y2, label, conf)`` tuples the
YOLO backends produce, so boxes, the distance column, the radar bar, threat
grading and the GPS map markers all work unchanged.

Two deliberate safety properties:

* **A candidate overlapping an existing YOLO box is dropped.** A person in an
  orange life jacket must stay a CRITICAL ``person`` and must never be relabelled
  as a WARNING ``buoy``. YOLO always wins the pixel.
* **Green is off by default** and the top of the frame is skipped. Sunlit foliage
  on the bank is saturated green and is the dominant false positive on a river;
  red/orange/yellow is both the standard buoy colouring and the least
  foliage-like.

Because a buoy grades WARNING, a false positive costs a map marker at worst —
it is only tracked if it is actually approaching, and never steers the boat on
its own.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class BuoyDetectorConfig:
    """Tuning for the classical buoy screen. Defaults are deliberately
    conservative — a missed buoy costs a map marker, a false one costs trust."""

    enabled: bool = True
    proc_width: int = 320        # downscale width for the mask pass (cost ∝ pixels)
    min_sat: int = 90            # HSV S floor: open water sits well below this
    min_val: int = 60            # HSV V floor: rejects dark reflections/shadow
    include_green: bool = False  # green buoys exist, but so does sunlit foliage
    roi_top_frac: float = 0.35   # ignore the top N of the frame (sky + treeline)
    min_area_px: int = 12        # min contour area at proc scale
    max_area_frac: float = 0.06  # reject large blobs (own hull, dock, glare band)
    min_solidity: float = 0.55   # contour area / bbox area — buoys are convex-ish
    min_aspect: float = 0.35     # w/h bounds: buoys are roughly round, not streaks
    max_aspect: float = 2.80
    max_candidates: int = 6      # cap work downstream; keeps the strongest
    # Drop a candidate when this fraction of it already lies inside a YOLO box
    # (containment, not IoU — see _covered_fraction).
    overlap_suppress: float = 0.50
    dedupe_iou: float = 0.25     # merge candidates that overlap each other
    label: str = "buoy"


# OpenCV hue is 0-179 (not 0-359). Red wraps the origin so it needs two bands.
_BAND_RED_LOW = (0, 18)
_BAND_RED_HIGH = (168, 179)
_BAND_YELLOW = (19, 33)
_BAND_GREEN = (40, 85)


def _intersection(a: tuple[float, float, float, float],
                  b: tuple[float, float, float, float]) -> float:
    """Area of overlap between two xyxy boxes (0 if disjoint)."""
    ix1, iy1 = max(a[0], b[0]), max(a[1], b[1])
    ix2, iy2 = min(a[2], b[2]), min(a[3], b[3])
    iw, ih = ix2 - ix1, iy2 - iy1
    return float(iw * ih) if iw > 0 and ih > 0 else 0.0


def _area(b: tuple[float, float, float, float]) -> float:
    return max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])


def _iou(a: tuple[float, float, float, float],
         b: tuple[float, float, float, float]) -> float:
    """Intersection-over-union of two xyxy boxes."""
    inter = _intersection(a, b)
    if inter <= 0:
        return 0.0
    union = _area(a) + _area(b) - inter
    return float(inter / union) if union > 0 else 0.0


def _covered_fraction(box: tuple[float, float, float, float],
                      other: tuple[float, float, float, float]) -> float:
    """How much of ``box`` lies inside ``other`` (0-1).

    Deliberately NOT IoU. The case that matters is *containment*: an orange life
    jacket is a small blob inside a much larger ``person`` box, and a life jacket
    is exactly what this screen looks for. IoU between a small box and a large one
    containing it is tiny (area ratio), so an IoU gate would let the phantom buoy
    through and chart a PERMANENT marker on top of a swimmer. Asking "is most of
    this blob already inside something the model classified?" is the question we
    actually mean.
    """
    a = _area(box)
    return _intersection(box, other) / a if a > 0 else 0.0


class BuoyDetector:
    """Finds saturated compact blobs on water and calls them buoys.

    Stateless between frames: every call is an independent screen, so there is
    nothing to reset and no history to grow. Temporal stability is
    ``ObjectMemory``'s job — it already requires N agreeing sightings before a
    marker is charted, which filters the occasional one-frame blob.
    """

    def __init__(self, cfg: BuoyDetectorConfig | None = None) -> None:
        self.cfg = cfg or BuoyDetectorConfig()

    def detect(self, frame_bgr, existing: list[tuple] | None = None) -> list[tuple]:
        """Screen a BGR frame → ``[(x1, y1, x2, y2, label, conf), ...]``.

        ``existing`` is the YOLO detection list for this same frame; any
        candidate overlapping one of those boxes is dropped so a real classified
        object is never relabelled as a buoy.
        """
        cfg = self.cfg
        if not cfg.enabled or frame_bgr is None:
            return []
        try:
            import cv2
            h, w = frame_bgr.shape[:2]
            if h < 8 or w < 8:
                return []

            # --- downscale: the mask pass costs pixels, and a buoy big enough to
            # matter survives 320 px easily.
            scale = min(1.0, cfg.proc_width / float(w))
            if scale < 1.0:
                pw, ph = int(round(w * scale)), int(round(h * scale))
                small = cv2.resize(frame_bgr, (pw, ph), interpolation=cv2.INTER_AREA)
            else:
                pw, ph, small = w, h, frame_bgr

            # --- skip the sky/treeline band entirely: less work AND fewer
            # foliage false positives. y_off maps rows back to full frame.
            y_off = int(ph * max(0.0, min(0.9, cfg.roi_top_frac)))
            roi = small[y_off:, :]
            if roi.shape[0] < 4:
                return []

            hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
            mask = self._colour_mask(hsv, cv2)

            # --- clean up: open kills single-pixel speckle (sun glitter on
            # ripples), close fills the gaps a specular highlight punches in the
            # middle of a buoy.
            k = np.ones((3, 3), np.uint8)
            mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, k, iterations=1)
            mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, k, iterations=1)

            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL,
                                           cv2.CHAIN_APPROX_SIMPLE)
            if not contours:
                return []

            inv = 1.0 / scale if scale > 0 else 1.0
            max_area = cfg.max_area_frac * float(pw * ph)
            cands: list[tuple] = []
            for c in contours:
                area = float(cv2.contourArea(c))
                if area < cfg.min_area_px or area > max_area:
                    continue
                bx, by, bw, bh = cv2.boundingRect(c)
                if bw <= 0 or bh <= 0:
                    continue
                aspect = bw / float(bh)
                if not (cfg.min_aspect <= aspect <= cfg.max_aspect):
                    continue
                solidity = area / float(bw * bh)
                if solidity < cfg.min_solidity:
                    continue
                # Mean saturation inside the blob drives the confidence: a
                # vivid buoy scores high, a washed-out ripple barely passes.
                sat = float(hsv[by:by + bh, bx:bx + bw, 1].mean())
                conf = self._score(sat, solidity)
                # back to full-frame coords (undo the ROI offset + downscale)
                x1 = int(round(bx * inv))
                y1 = int(round((by + y_off) * inv))
                x2 = int(round((bx + bw) * inv))
                y2 = int(round((by + bh + y_off) * inv))
                # Clamp all four edges, not just the far ones — the arithmetic
                # should keep these in frame, but a future change to the
                # downscale/ROI transform must not be able to emit a box
                # outside the image.
                cands.append((max(0, x1), max(0, y1), min(x2, w), min(y2, h),
                              cfg.label, conf))

            if not cands:
                return []
            # Strongest first, then cap — downstream cost is per box.
            cands.sort(key=lambda t: t[5], reverse=True)
            cands = cands[:cfg.max_candidates]
            return self._suppress_overlaps(cands, existing)
        except Exception as e:  # noqa: BLE001 — a bad frame must not kill the loop
            logger.debug("buoy screen failed: %s", e)
            return []

    # -- internals ---------------------------------------------------------- #
    def _colour_mask(self, hsv, cv2):
        """Binary mask of saturated buoy-coloured pixels."""
        cfg = self.cfg
        bands = [_BAND_RED_LOW, _BAND_RED_HIGH, _BAND_YELLOW]
        if cfg.include_green:
            bands.append(_BAND_GREEN)
        mask = None
        for lo, hi in bands:
            m = cv2.inRange(hsv,
                            np.array([lo, cfg.min_sat, cfg.min_val], np.uint8),
                            np.array([hi, 255, 255], np.uint8))
            mask = m if mask is None else cv2.bitwise_or(mask, m)
        return mask

    @staticmethod
    def _score(sat: float, solidity: float) -> float:
        """Pseudo-confidence in a deliberately modest band.

        Kept below the ~0.9 a confident YOLO box reaches so a colour blob never
        outranks a real classification when ``_infer`` picks the primary target.
        """
        s = min(1.0, max(0.0, (sat - 90.0) / 130.0))       # 90→0, 220→1
        g = min(1.0, max(0.0, (solidity - 0.55) / 0.40))   # .55→0, .95→1
        return round(0.35 + 0.45 * (0.65 * s + 0.35 * g), 3)

    def _suppress_overlaps(self, cands: list[tuple],
                           existing: list[tuple] | None) -> list[tuple]:
        """Drop candidates already explained by a YOLO box, then de-overlap.

        Two different metrics on purpose:

        * against YOLO — **containment** (``_covered_fraction``). A classified
          object keeps its label, and this holds even when the blob is entirely
          inside a much bigger box (life jacket inside a ``person``), which an IoU
          test would miss.
        * against each other — **IoU**, the ordinary case: stop one buoy
          fragmenting into several boxes when a specular highlight splits its mask.

        Suppressing a real buoy that happens to sit inside a large vessel box is
        the accepted cost: it is re-detected once the vessel moves, and
        ``ObjectMemory`` needs several agreeing sightings before charting anything.
        A phantom PERMANENT marker on a swimmer would persist for the session.
        """
        yolo = [(b[0], b[1], b[2], b[3]) for b in (existing or [])]
        kept: list[tuple] = []
        for c in cands:
            box = (c[0], c[1], c[2], c[3])
            if any(_covered_fraction(box, y) > self.cfg.overlap_suppress
                   for y in yolo):
                continue
            if any(_iou(box, (k[0], k[1], k[2], k[3])) > self.cfg.dedupe_iou
                   for k in kept):
                continue
            kept.append(c)
        return kept
