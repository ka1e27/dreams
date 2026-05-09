"""Stereo calibration script.

Captures checkerboard image pairs from both cameras, runs OpenCV's standard
intrinsic + extrinsic calibration, and writes the rectification maps and
reprojection matrix to a .npz consumed by pi5/cv/stereo.py.

Usage:
    python -m pi5.scripts.calibrate_stereo \
        --left 0 --right 1 \
        --rows 6 --cols 9 --square 0.025 \
        --out pi5/cv/calibration.npz \
        --baseline 0.12

Press SPACE to capture a frame pair when the checkerboard is detected in
both views, ESC to finish and run the calibration solve.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import cv2
import numpy as np


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--left", type=int, default=0)
    ap.add_argument("--right", type=int, default=1)
    ap.add_argument("--rows", type=int, default=6, help="inner corners per col")
    ap.add_argument("--cols", type=int, default=9, help="inner corners per row")
    ap.add_argument("--square", type=float, default=0.025,
                    help="checkerboard square size in metres")
    ap.add_argument("--out", default="pi5/cv/calibration.npz")
    ap.add_argument("--baseline", type=float, required=True,
                    help="measured stereo baseline in metres (informational; "
                         "the solver derives the actual T vector)")
    args = ap.parse_args()

    pattern = (args.cols, args.rows)
    objp = np.zeros((args.rows * args.cols, 3), np.float32)
    objp[:, :2] = np.mgrid[0:args.cols, 0:args.rows].T.reshape(-1, 2)
    objp *= args.square

    cap_l = cv2.VideoCapture(args.left)
    cap_r = cv2.VideoCapture(args.right)
    if not cap_l.isOpened() or not cap_r.isOpened():
        print("Failed to open one or both cameras", file=sys.stderr)
        return 1

    obj_points: list[np.ndarray] = []
    img_points_l: list[np.ndarray] = []
    img_points_r: list[np.ndarray] = []
    image_size: tuple[int, int] | None = None

    print("SPACE = capture pair when corners are green; ESC = solve & save")

    while True:
        ok_l, fl = cap_l.read()
        ok_r, fr = cap_r.read()
        if not (ok_l and ok_r):
            continue
        if image_size is None:
            image_size = (fl.shape[1], fl.shape[0])
        gl = cv2.cvtColor(fl, cv2.COLOR_BGR2GRAY)
        gr = cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY)
        found_l, corners_l = cv2.findChessboardCorners(gl, pattern)
        found_r, corners_r = cv2.findChessboardCorners(gr, pattern)
        prev_l = fl.copy()
        prev_r = fr.copy()
        if found_l:
            cv2.drawChessboardCorners(prev_l, pattern, corners_l, found_l)
        if found_r:
            cv2.drawChessboardCorners(prev_r, pattern, corners_r, found_r)
        cv2.putText(prev_l, f"pairs: {len(obj_points)}", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        cv2.imshow("left", prev_l)
        cv2.imshow("right", prev_r)
        k = cv2.waitKey(1) & 0xff
        if k == 27:  # ESC
            break
        if k == 32 and found_l and found_r:  # SPACE
            obj_points.append(objp.copy())
            img_points_l.append(corners_l)
            img_points_r.append(corners_r)
            print(f"captured pair #{len(obj_points)}")

    cap_l.release()
    cap_r.release()
    cv2.destroyAllWindows()

    if len(obj_points) < 10:
        print(f"only {len(obj_points)} pairs — need at least 10", file=sys.stderr)
        return 2

    print("Calibrating left camera...")
    _, K_l, D_l, _, _ = cv2.calibrateCamera(obj_points, img_points_l,
                                            image_size, None, None)
    print("Calibrating right camera...")
    _, K_r, D_r, _, _ = cv2.calibrateCamera(obj_points, img_points_r,
                                            image_size, None, None)
    print("Stereo calibration...")
    flags = cv2.CALIB_FIX_INTRINSIC
    _, _, _, _, _, R, T, _, _ = cv2.stereoCalibrate(
        obj_points, img_points_l, img_points_r,
        K_l, D_l, K_r, D_r, image_size, flags=flags
    )
    print(f"Baseline (||T||): {float(np.linalg.norm(T)):.4f} m  (expected ~{args.baseline})")
    R1, R2, P1, P2, Q, _, _ = cv2.stereoRectify(
        K_l, D_l, K_r, D_r, image_size, R, T
    )
    map_l1, map_l2 = cv2.initUndistortRectifyMap(K_l, D_l, R1, P1,
                                                 image_size, cv2.CV_16SC2)
    map_r1, map_r2 = cv2.initUndistortRectifyMap(K_r, D_r, R2, P2,
                                                 image_size, cv2.CV_16SC2)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez(out_path,
             map_l1=map_l1, map_l2=map_l2,
             map_r1=map_r1, map_r2=map_r2,
             Q=Q,
             baseline_m=float(np.linalg.norm(T)),
             K_l=K_l, D_l=D_l, K_r=K_r, D_r=D_r, R=R, T=T)
    print(f"Wrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
