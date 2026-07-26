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
    """Compute disparity + depth from a rectified stereo pair.

    ``downscale`` (0 < s <= 1) runs the expensive SGBM + reprojection on a
    downscaled copy of the rectified pair. StereoSGBM cost is ~O(W·H·numDisp),
    so at 1080p it dominates the whole inference budget (hundreds of ms on a
    Pi 5) — running it at half resolution is ~4× cheaper and mid-range depth
    (3–30 m) is essentially unaffected. Depth stays metrically correct because
    the reprojection matrix is rescaled for the smaller image (``Q[:, :3] /= s``,
    an exact coordinate change, see ``compute``), and the disparity search range
    is scaled with it. The returned maps are upsampled back to full resolution
    so callers (bbox depth lookup, the /video disparity view) are unchanged.
    Pass ``downscale=1.0`` to reproduce the original full-resolution path.
    """

    def __init__(self, calib: Calibration, downscale: float = 0.5,
                 wls: bool = False) -> None:
        self._calib = calib
        self._scale = float(min(1.0, max(0.1, downscale)))
        # Scale the disparity search range with the image: max real-world
        # disparity in the downscaled image shrinks by the same factor, so
        # searching the full 64 there would waste cycles (and overrun the frame).
        num_disp = max(16, int(round(64 * self._scale / 16.0)) * 16)
        # Reprojection matrix for the downscaled image. Feeding downscaled
        # (x', y', d') = s·(x, y, d) through Q' = Q·diag(1/s,1/s,1/s,1) yields
        # exactly the same metric 3-D point as the full-res (x, y, d) through Q.
        self._q_scaled = calib.Q.astype(np.float64).copy()
        if self._scale != 1.0:
            self._q_scaled[:, 0:3] /= self._scale
        block = 7
        # SGBM parameters tuned for outdoor mid-range (3–30 m). Block size is
        # intentionally generous to be robust on low-texture water; the 3-way
        # mode is markedly faster than full HH on the Pi 5 CPU at a small quality
        # cost, and preFilterCap tames specular glints off the water surface.
        self._matcher = cv2.StereoSGBM_create(
            minDisparity=0,
            numDisparities=num_disp,  # multiple of 16, scaled to the image
            blockSize=block,
            P1=8 * 3 * block ** 2,
            P2=32 * 3 * block ** 2,
            disp12MaxDiff=1,
            preFilterCap=63,
            uniquenessRatio=10,
            speckleWindowSize=100,
            speckleRange=32,
            mode=cv2.StereoSGBM_MODE_SGBM_3WAY,
        )

        # Optional WLS post-filter (opencv-contrib ximgproc). Water is the worst
        # case for block matching — textureless, specular, semi-transparent — so
        # raw SGBM leaves large invalid holes there. The WLS filter fills and
        # smooths the disparity using a left↔right consistency check + a
        # confidence map guided by the left image, which is exactly the fix for
        # low-texture/occluded regions. It runs a second (right) matcher, so it
        # roughly doubles matching cost; off by default, enable via config on a
        # rig that can spare the cycles (or at a lower stereo FPS).
        self._wls = None
        self._right_matcher = None
        if wls:
            try:
                self._right_matcher = cv2.ximgproc.createRightMatcher(self._matcher)
                self._wls = cv2.ximgproc.createDisparityWLSFilter(self._matcher)
                self._wls.setLambda(8000.0)
                self._wls.setSigmaColor(1.5)
                logger.info("Stereo WLS disparity filter enabled")
            except AttributeError:
                logger.warning("stereo_wls requested but cv2.ximgproc is missing "
                               "(install opencv-contrib-python) — WLS disabled")
                self._wls = None
                self._right_matcher = None

    def compute(self, left_bgr: np.ndarray, right_bgr: np.ndarray
                ) -> tuple[np.ndarray, np.ndarray]:
        """Returns (disparity_float, depth_metres) at full frame size. NaN
        where invalid. SGBM/reprojection run at ``downscale`` resolution."""
        left_g = cv2.cvtColor(left_bgr, cv2.COLOR_BGR2GRAY)
        right_g = cv2.cvtColor(right_bgr, cv2.COLOR_BGR2GRAY)
        full_h, full_w = left_g.shape[:2]
        # Rectify at full resolution (remap maps are full-res), then downscale
        # the rectified grayscale pair before the costly matching step.
        rl = cv2.remap(left_g, self._calib.map_l1, self._calib.map_l2,
                       cv2.INTER_LINEAR)
        rr = cv2.remap(right_g, self._calib.map_r1, self._calib.map_r2,
                       cv2.INTER_LINEAR)
        if self._scale != 1.0:
            small = (max(1, int(full_w * self._scale)),
                     max(1, int(full_h * self._scale)))
            rl = cv2.resize(rl, small, interpolation=cv2.INTER_AREA)
            rr = cv2.resize(rr, small, interpolation=cv2.INTER_AREA)
        # SGBM returns disparity * 16 as int16
        disp16 = self._matcher.compute(rl, rr)
        if self._wls is not None and self._right_matcher is not None:
            # Right→left disparity for the left↔right consistency check, then
            # WLS-filter the left disparity guided by the left image. Filling the
            # textureless water holes is the whole point of running the extra pass.
            disp16_r = self._right_matcher.compute(rr, rl)
            disp16 = self._wls.filter(disp16, rl, disparity_map_right=disp16_r)
        disp = disp16.astype(np.float32) / 16.0
        # cv2.reprojectImageTo3D returns (h, w, 3); Z = depth in calibration
        # units (metres if T was specified in metres during calibration).
        points = cv2.reprojectImageTo3D(disp, self._q_scaled)
        depth = np.ascontiguousarray(points[:, :, 2])  # contiguous for resize
        # Mask invalid depth: SGBM marks invalid disparity with a large
        # negative value, which reprojects to absurd Z.
        mask = (disp <= 0) | (depth <= 0) | (depth > 200)
        depth[mask] = np.nan
        if self._scale != 1.0:
            # Upsample both maps back to full frame size so callers that index
            # with full-res bbox coordinates keep working unchanged. NEAREST
            # avoids blending NaNs and disparity discontinuities; disparity is
            # rescaled back to full-resolution pixel units for the depth view.
            depth = cv2.resize(depth, (full_w, full_h),
                               interpolation=cv2.INTER_NEAREST)
            disp = cv2.resize(disp, (full_w, full_h),
                              interpolation=cv2.INTER_NEAREST) / self._scale
        return disp, depth

    @staticmethod
    def median_depth_in_bbox(depth: np.ndarray,
                             x1: int, y1: int, x2: int, y2: int
                             ) -> float | None:
        """Median depth inside a bbox, ignoring NaNs. None if all-NaN."""
        h, w = depth.shape
        x1 = max(0, x1)
        y1 = max(0, y1)
        x2 = min(w, x2)
        y2 = min(h, y2)
        if x2 <= x1 or y2 <= y1:
            return None
        roi = depth[y1:y2, x1:x2]
        valid = roi[~np.isnan(roi)]
        if valid.size == 0:
            return None
        return float(np.median(valid))
