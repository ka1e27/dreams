"""Tier 1 — lightweight always-on water segmentation.

The cheap screen that runs on *every* frame and decides whether the more
expensive tiers (YOLO classification, stereo depth, threat assessment) are
worth waking. It returns an anomaly score in ``[0, 1]`` — the fraction of the
frame that doesn't look like open water — plus a coarse ``WaterState`` and a
list of anomalous regions.

Model choice
------------
The design targets a lightweight INT8 TFLite semantic-segmentation model
(MobileNetV3-Small / FastSCNN) at ``models/water_seg.tflite``. That file is
**not** in the repo, and TFLite isn't a hard dependency, so this module ships a
classical-CV fallback (OpenCV HSV thresholding + edges) that needs no model and
no extra packages beyond the ``cv2``/``numpy`` the rest of ``pi5/cv`` already
pulls in. If a TFLite model *and* the ``tflite_runtime`` (or ``tensorflow``)
package are both present, ``analyze`` uses them; otherwise it logs one warning
at construction and uses the classical path. Either way the public surface —
``analyze`` → :class:`SegResult` — is identical, so :mod:`pi5.cv.pipeline`
doesn't care which backend is live.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

import cv2
import numpy as np

logger = logging.getLogger(__name__)

# Fraction of the frame that must read as non-water before Tier 2 (YOLO) is
# worth waking. The pipeline reads this via config; it's duplicated here as the
# module default so segmentation is usable standalone / in tests.
ANOMALY_TRIGGER_THRESHOLD = 0.15

# --- Classical-CV HSV bands (OpenCV H is 0-179, S/V 0-255) ----------------- #
# Open water is broadly blue → blue-green → grey. Anything well outside that is
# "anomalous". These are deliberately generous — Tier 1 only has to be a cheap
# screen, not a classifier; YOLO does the real identification downstream.
WATER_HSV_LOWER = np.array([80, 25, 25], dtype=np.uint8)
WATER_HSV_UPPER = np.array([140, 255, 235], dtype=np.uint8)
# Algae bloom — vivid greens.
ALGAE_HSV_LOWER = np.array([35, 60, 40], dtype=np.uint8)
ALGAE_HSV_UPPER = np.array([80, 255, 255], dtype=np.uint8)
# Discoloration — sediment / pollution browns, reds, ambers (low-hue warm band).
DISCOLOR_HSV_LOWER = np.array([0, 60, 40], dtype=np.uint8)
DISCOLOR_HSV_UPPER = np.array([30, 255, 255], dtype=np.uint8)

# Downscale long edge for the classical pass — Tier 1 must stay cheap at 1080p.
_ANALYZE_MAX_DIM = 320
# Minimum region area (as a fraction of frame area) to report as an anomaly box.
_MIN_REGION_FRAC = 0.004


class WaterState(Enum):
    """Coarse Tier-1 verdict on what the water looks like."""
    CLEAR = "clear"               # open water, nothing interesting
    DEBRIS = "debris"             # floating objects detected
    DISCOLORATION = "discolored"  # colour anomaly — pollution / sediment
    ALGAE = "algae_bloom"         # green bloom detected
    OBSTACLE = "obstacle"         # solid object at water level
    UNKNOWN = "unknown"           # uncertain — worth triggering YOLO


@dataclass
class SegResult:
    """Everything Tier 1 hands to the pipeline for one frame."""
    water_state: WaterState = WaterState.CLEAR
    anomaly_score: float = 0.0                       # 0..1, fraction non-water
    anomaly_regions: list[tuple[int, int, int, int]] = field(default_factory=list)
    # Component scores (0..1) — useful for the state decision + UI/debug.
    algae_score: float = 0.0
    discolor_score: float = 0.0
    edge_score: float = 0.0
    backend: str = "classical"


class WaterSegmentation:
    """Tier 1 — lightweight always-on water analysis.

    Runs on every frame; cheap enough not to bottleneck the pipeline. Uses a
    TFLite model when one is available, else a classical OpenCV fallback.
    """

    def __init__(self, model_path: str | Path | None = None,
                 anomaly_trigger_threshold: float = ANOMALY_TRIGGER_THRESHOLD) -> None:
        self.trigger_threshold = float(anomaly_trigger_threshold)
        self._interpreter = None       # tflite Interpreter when a model loads
        self._in_index = None
        self._out_index = None
        self._in_size = (0, 0)
        self.backend = "classical"
        if model_path:
            self._try_load_tflite(Path(model_path))
        if self._interpreter is None:
            logger.warning(
                "No segmentation model found (%s) — using classical CV fallback",
                model_path or "unset")

    # -- model loading ------------------------------------------------------ #
    def _try_load_tflite(self, path: Path) -> None:
        """Best-effort TFLite load. Any failure falls through to classical."""
        if not path.exists():
            return
        try:
            try:
                from tflite_runtime.interpreter import Interpreter  # type: ignore
            except ImportError:
                from tensorflow.lite import Interpreter  # type: ignore
        except ImportError as e:
            logger.warning("TFLite model present but no runtime installed (%s) — "
                           "using classical CV fallback", e)
            return
        try:
            interp = Interpreter(model_path=str(path))
            interp.allocate_tensors()
            inp = interp.get_input_details()[0]
            out = interp.get_output_details()[0]
            self._interpreter = interp
            self._in_index = inp["index"]
            self._out_index = out["index"]
            # input shape [1, H, W, 3]
            _, h, w, _ = inp["shape"]
            self._in_size = (int(w), int(h))
            self.backend = "tflite"
            logger.info("Water segmentation TFLite model loaded: %s (%dx%d)",
                        path.name, w, h)
        except Exception as e:  # noqa: BLE001 — never block startup on a bad model
            logger.warning("Failed to load segmentation model %s (%s) — "
                           "using classical CV fallback", path, e)
            self._interpreter = None

    # -- public API --------------------------------------------------------- #
    def analyze(self, frame) -> SegResult:
        """Run segmentation on a BGR frame and return a :class:`SegResult`.

        Never raises on a bad frame — degrades to a CLEAR result so the pipeline
        keeps running (a Tier-1 hiccup must not stall the whole vision stack).
        """
        if frame is None or getattr(frame, "size", 0) == 0:
            return SegResult()
        try:
            if self._interpreter is not None:
                return self._tflite_analyze(frame)
            return self._classical_analyze(frame)
        except Exception as e:  # noqa: BLE001
            logger.debug("segmentation analyze error: %s", e)
            return SegResult(water_state=WaterState.UNKNOWN, anomaly_score=0.0)

    def get_anomaly_score(self, seg_result: SegResult) -> float:
        """How anomalous is this frame (0..1)."""
        return seg_result.anomaly_score

    def get_anomaly_regions(self, seg_result: SegResult
                            ) -> list[tuple[int, int, int, int]]:
        """Bounding boxes (x1, y1, x2, y2) around anomalous areas."""
        return seg_result.anomaly_regions

    def classify_water_state(self, seg_result: SegResult) -> WaterState:
        return seg_result.water_state

    def is_triggered(self, seg_result: SegResult) -> bool:
        """True if this frame is anomalous enough to wake Tier 2."""
        return seg_result.anomaly_score >= self.trigger_threshold

    # -- classical fallback ------------------------------------------------- #
    def _downscale(self, frame) -> "tuple[np.ndarray, float]":
        """Shrink so the long edge is <= _ANALYZE_MAX_DIM. Returns (small, scale)
        where scale maps small→original coordinates."""
        h, w = frame.shape[:2]
        long_edge = max(h, w)
        if long_edge <= _ANALYZE_MAX_DIM:
            return frame, 1.0
        s = _ANALYZE_MAX_DIM / float(long_edge)
        small = cv2.resize(frame, (max(1, int(w * s)), max(1, int(h * s))),
                           interpolation=cv2.INTER_AREA)
        return small, 1.0 / s   # divide small-coords by s → original coords

    def _classical_analyze(self, frame) -> SegResult:
        """OpenCV-only water analysis — no model required.

        Water is broadly blue/blue-green; the anomaly ratio is the fraction of
        pixels *outside* that band. Green and warm bands split algae from
        sediment discoloration, and a Canny edge density flags solid obstacles.
        """
        small, scale = self._downscale(frame)
        hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
        total = float(small.shape[0] * small.shape[1])  # pixel count (H*W)

        water_mask = cv2.inRange(hsv, WATER_HSV_LOWER, WATER_HSV_UPPER)
        water_px = int(cv2.countNonZero(water_mask))
        # NOTE: measured against the pixel count (H*W), not frame.size (H*W*3) —
        # countNonZero on a single-channel mask maxes at H*W, so dividing by
        # frame.size would understate the ratio ~3x.
        anomaly_ratio = 1.0 - (water_px / total) if total else 0.0

        algae_mask = cv2.inRange(hsv, ALGAE_HSV_LOWER, ALGAE_HSV_UPPER)
        discolor_mask = cv2.inRange(hsv, DISCOLOR_HSV_LOWER, DISCOLOR_HSV_UPPER)
        algae_score = cv2.countNonZero(algae_mask) / total if total else 0.0
        discolor_score = cv2.countNonZero(discolor_mask) / total if total else 0.0

        # Edge density on the non-water region → solid-obstacle hint.
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 60, 160)
        non_water = cv2.bitwise_not(water_mask)
        obstacle_edges = cv2.bitwise_and(edges, edges, mask=non_water)
        edge_score = cv2.countNonZero(obstacle_edges) / total if total else 0.0

        regions = self._regions_from_mask(non_water, scale, total)
        state = self._decide_state(anomaly_ratio, algae_score, discolor_score,
                                   edge_score, regions)
        return SegResult(
            water_state=state,
            anomaly_score=float(min(1.0, max(0.0, anomaly_ratio))),
            anomaly_regions=regions,
            algae_score=float(algae_score),
            discolor_score=float(discolor_score),
            edge_score=float(edge_score),
            backend="classical",
        )

    @staticmethod
    def _regions_from_mask(mask, scale: float, total: float
                           ) -> list[tuple[int, int, int, int]]:
        """Contour the non-water mask into a few bounding boxes (original coords)."""
        # Close small gaps so a fragmented object becomes one region.
        kernel = np.ones((5, 5), np.uint8)
        closed = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL,
                                       cv2.CHAIN_APPROX_SIMPLE)
        min_area = _MIN_REGION_FRAC * total
        boxes: list[tuple[int, int, int, int]] = []
        for c in contours:
            if cv2.contourArea(c) < min_area:
                continue
            x, y, w, h = cv2.boundingRect(c)
            boxes.append((int(x * scale), int(y * scale),
                          int((x + w) * scale), int((y + h) * scale)))
        # Keep the largest few — the pipeline only needs a coarse hint.
        boxes.sort(key=lambda b: (b[2] - b[0]) * (b[3] - b[1]), reverse=True)
        return boxes[:8]

    @staticmethod
    def _decide_state(anomaly: float, algae: float, discolor: float,
                      edge: float, regions: list) -> WaterState:
        """Map component scores to a coarse WaterState."""
        if anomaly < 0.08 and not regions:
            return WaterState.CLEAR
        # Whichever colour band dominates the anomaly wins; else fall back to
        # geometry (edges/regions → solid obstacle vs debris) or UNKNOWN.
        if algae >= 0.12 and algae >= discolor:
            return WaterState.ALGAE
        if discolor >= 0.12 and discolor > algae:
            return WaterState.DISCOLORATION
        if edge >= 0.06 and regions:
            return WaterState.OBSTACLE
        if regions:
            return WaterState.DEBRIS
        return WaterState.UNKNOWN

    # -- TFLite path -------------------------------------------------------- #
    def _tflite_analyze(self, frame) -> SegResult:
        """Run the semantic-segmentation model and derive the same SegResult.

        Assumes a 2-class (water / non-water) or argmax-over-channels output. The
        non-water fraction becomes the anomaly score; regions come from the
        thresholded non-water mask. Colour bands (algae/discolor) are still taken
        from the classical HSV pass so the state decision stays informative.
        """
        w, h = self._in_size
        inp = cv2.resize(frame, (w, h), interpolation=cv2.INTER_LINEAR)
        rgb = cv2.cvtColor(inp, cv2.COLOR_BGR2RGB)
        blob = rgb.astype(np.float32)[np.newaxis, ...] / 255.0
        self._interpreter.set_tensor(self._in_index, blob)
        self._interpreter.invoke()
        out = np.asarray(self._interpreter.get_tensor(self._out_index))[0]
        # out is (H, W) logits/prob, or (H, W, C) — reduce to a non-water mask.
        if out.ndim == 3 and out.shape[-1] > 1:
            water_class = 0  # convention: channel 0 = water
            labels = out.argmax(axis=-1)
            non_water = (labels != water_class).astype(np.uint8) * 255
        else:
            prob = out.squeeze()
            non_water = (prob < 0.5).astype(np.uint8) * 255  # <0.5 = not water
        total = float(non_water.shape[0] * non_water.shape[1])
        anomaly_ratio = cv2.countNonZero(non_water) / total if total else 0.0

        # Colour context from the (cheap) HSV pass on the same resized input.
        hsv = cv2.cvtColor(inp, cv2.COLOR_BGR2HSV)
        algae_score = cv2.countNonZero(cv2.inRange(hsv, ALGAE_HSV_LOWER, ALGAE_HSV_UPPER)) / total
        discolor_score = cv2.countNonZero(cv2.inRange(hsv, DISCOLOR_HSV_LOWER, DISCOLOR_HSV_UPPER)) / total

        fh, fw = frame.shape[:2]
        sx, sy = fw / float(w), fh / float(h)
        regions = self._regions_from_mask(non_water, 1.0, total)
        regions = [(int(x1 * sx), int(y1 * sy), int(x2 * sx), int(y2 * sy))
                   for (x1, y1, x2, y2) in regions]
        state = self._decide_state(anomaly_ratio, algae_score, discolor_score,
                                   0.0, regions)
        return SegResult(
            water_state=state,
            anomaly_score=float(min(1.0, max(0.0, anomaly_ratio))),
            anomaly_regions=regions,
            algae_score=float(algae_score),
            discolor_score=float(discolor_score),
            backend="tflite",
        )
