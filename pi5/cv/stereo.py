"""Stereo disparity → depth using OpenCV StereoSGBM.

Loads camera intrinsics + extrinsics from a calibration .npz file written
by scripts/calibrate_stereo.py and produces a depth map (metres) for each
left-right frame pair.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class Calibration:
    """Rectification + reprojection matrices loaded from disk."""
    map_l1: np.ndarray
    map_l2: np.ndarray
    map_r1: np.ndarray
    map_r2: np.ndarray
    Q: np.ndarray  # 4×4 reprojection matrix (disparity → depth)
    baseline_m: float


def load_calibration(path: str | Path) -> Calibration | None:
    """Load a calibration .npz. Returns None if missing — caller should
    fall back to a less precise distance estimate."""
    p = Path(path)
    if not p.exists():
        logger.warning("Stereo calibration not found at %s", p)
        return None
    data = np.load(p)
    return Calibration(
        map_l1=data["map_l1"],
        map_l2=data["map_l2"],
        map_r1=data["map_r1"],
        map_r2=data["map_r2"],
        Q=data["Q"],
        baseline_m=float(data["baseline_m"]),
    )


class StereoDepth:
    """Compute disparity + depth from a rectified stereo pair."""

    def __init__(self, calib: Calibration) -> None:
        self._calib = calib
        # SGBM parameters tuned for outdoor mid-range (3–30 m). Block size
        # is intentionally generous to be robust on low-texture water.
        self._matcher = cv2.StereoSGBM_create(
            minDisparity=0,
            numDisparities=64,  # multiple of 16
            blockSize=7,
            P1=8 * 3 * 7 ** 2,
            P2=32 * 3 * 7 ** 2,
            disp12MaxDiff=1,
            uniquenessRatio=10,
            speckleWindowSize=100,
            speckleRange=32,
        )

    def compute(self, left_bgr: np.ndarray, right_bgr: np.ndarray
                ) -> tuple[np.ndarray, np.ndarray]:
        """Returns (disparity_float, depth_metres). NaN where invalid."""
        left_g = cv2.cvtColor(left_bgr, cv2.COLOR_BGR2GRAY)
        right_g = cv2.cvtColor(right_bgr, cv2.COLOR_BGR2GRAY)
        # Rectify
        rl = cv2.remap(left_g, self._calib.map_l1, self._calib.map_l2,
                       cv2.INTER_LINEAR)
        rr = cv2.remap(right_g, self._calib.map_r1, self._calib.map_r2,
                       cv2.INTER_LINEAR)
        # SGBM returns disparity * 16 as int16
        disp16 = self._matcher.compute(rl, rr)
        disp = disp16.astype(np.float32) / 16.0
        # cv2.reprojectImageTo3D returns (h, w, 3); Z = depth in calibration
        # units (metres if T was specified in metres during calibration)
        points = cv2.reprojectImageTo3D(disp, self._calib.Q)
        depth = points[:, :, 2]
        # Mask invalid depth: SGBM marks invalid disparity with a large
        # negative value, which reprojects to absurd Z.
        mask = (disp <= 0) | (depth <= 0) | (depth > 200)
        depth[mask] = np.nan
        return disp, depth

    @staticmethod
    def median_depth_in_bbox(depth: np.ndarray,
                             x1: int, y1: int, x2: int, y2: int
                             ) -> float | None:
        """Median depth inside a bbox, ignoring NaNs. None if all-NaN."""
        h, w = depth.shape
        x1 = max(0, x1); y1 = max(0, y1)
        x2 = min(w, x2); y2 = min(h, y2)
        if x2 <= x1 or y2 <= y1:
            return None
        roi = depth[y1:y2, x1:x2]
        valid = roi[~np.isnan(roi)]
        if valid.size == 0:
            return None
        return float(np.median(valid))
