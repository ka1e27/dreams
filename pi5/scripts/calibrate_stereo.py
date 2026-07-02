"""Stereo calibration script.

Captures checkerboard image pairs from both cameras, runs OpenCV's standard
intrinsic + extrinsic calibration, and writes the rectification maps and
reprojection matrix to a .npz consumed by pi5/cv/stereo.py.

Usage:
    python -m pi5.scripts.calibrate_stereo --left 0 --right 2 --rows 6 --cols 9 \
        --square 0.025 --width 1920 --height 1080 --fourcc YUY2 \
        --out pi5/cv/calibration.npz --baseline 0.32

--rows/--cols are INNER corners (where black squares meet), not the square
count — a checkerboard with 9x6 squares per side has 8x5 inner corners.
Miscounting this is the most common reason no green corners ever appear.

--width/--height/--fourcc should match pi5/config.yaml's camera settings so
the calibration is done on the same feed the runtime will actually see.

Press SPACE to capture a frame pair when the checkerboard is detected in
both views, ESC to finish and run the calibration solve.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import cv2
import numpy as np


def _open(index: int, width: int, height: int, fourcc: str) -> cv2.VideoCapture:
    """Open a capture device with explicit backend + format, mirroring
    pi5/cv/camera.py so calibration sees the same feed the runtime will."""
    if sys.platform.startswith("linux"):
        cap = cv2.VideoCapture(index, cv2.CAP_V4L2)
        if fourcc:
            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*fourcc[:4]))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    else:
        cap = cv2.VideoCapture(index, cv2.CAP_DSHOW)
        # DirectShow negotiates (W,H,FourCC) as one pin format — size first,
        # then FourCC, then re-apply size in case FourCC reset the pin.
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        if fourcc:
            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*fourcc[:4]))
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    try:
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    except Exception:  # noqa: BLE001
        pass
    return cap


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
    ap.add_argument("--width", type=int, default=1920)
    ap.add_argument("--height", type=int, default=1080)
    ap.add_argument("--fourcc", default="YUY2",
                    help="pixel format to request (YUY2/MJPG/''); should match "
                         "camera.yaml so calibration matches the runtime feed")
    ap.add_argument("--detect-scale", type=float, default=0.5,
                    help="downscale factor for chessboard search (speeds up "
                         "detection at high resolution; corners are refined "
                         "back at full res)")
    args = ap.parse_args()

    pattern = (args.cols, args.rows)
    objp = np.zeros((args.rows * args.cols, 3), np.float32)
    objp[:, :2] = np.mgrid[0:args.cols, 0:args.rows].T.reshape(-1, 2)
    objp *= args.square

    cap_l = _open(args.left, args.width, args.height, args.fourcc)
    cap_r = _open(args.right, args.width, args.height, args.fourcc)
    if not cap_l.isOpened() or not cap_r.isOpened():
        print("Failed to open one or both cameras", file=sys.stderr)
        return 1

    find_flags = (cv2.CALIB_CB_ADAPTIVE_THRESH | cv2.CALIB_CB_FAST_CHECK
                  | cv2.CALIB_CB_NORMALIZE_IMAGE)
    subpix_criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.01)

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

        # Search for the board on a downscaled copy — full-res corner search
        # is the main cost at 1920x1080 and made the preview feel frozen.
        scale = args.detect_scale if args.detect_scale > 0 else 1.0
        if scale != 1.0:
            gl_small = cv2.resize(gl, None, fx=scale, fy=scale)
            gr_small = cv2.resize(gr, None, fx=scale, fy=scale)
        else:
            gl_small, gr_small = gl, gr
        found_l, corners_l = cv2.findChessboardCorners(gl_small, pattern, find_flags)
        found_r, corners_r = cv2.findChessboardCorners(gr_small, pattern, find_flags)
        if found_l:
            corners_l = corners_l / scale
            cv2.cornerSubPix(gl, corners_l, (11, 11), (-1, -1), subpix_criteria)
        if found_r:
            corners_r = corners_r / scale
            cv2.cornerSubPix(gr, corners_r, (11, 11), (-1, -1), subpix_criteria)
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
