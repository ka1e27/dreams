"""Vision benchmark harness — measure the pipeline's per-stage cost.

Run this on the **Pi 5** (laptop/desktop numbers do not represent the target
hardware) to confirm the FPS budget the vision stack is tuned for:

  * Tier-1 water segmentation  → target **≥ 15 fps** (the always-on water screen)
  * YOLO object detection      → a lower-but-high rate (bounded by imgsz)
  * Stereo depth               → the per-detection distance cost, at each
                                 ``camera.stereo_downscale`` factor

It times each stage in isolation (each stage runs alone, so these are ceilings —
the live pipeline runs them concurrently across the 4 Pi cores). Stages whose
optional deps/models are missing are skipped, not errors.

Usage:
    python -m pi5.scripts.benchmark_vision                  # synthetic frames
    python -m pi5.scripts.benchmark_vision --source camera  # a real camera grab
    python -m pi5.scripts.benchmark_vision --frames 60 --warmup 5
"""
from __future__ import annotations

import argparse
import statistics
import sys
import time
from pathlib import Path

import numpy as np
import yaml

REPO = Path(__file__).resolve().parents[2]
CONFIG_PATH = REPO / "pi5" / "config.yaml"


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _load_config() -> dict:
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        print(f"config.yaml not found at {CONFIG_PATH} — using defaults")
        return {}


def _synthetic(w: int, h: int) -> np.ndarray:
    """A random BGR frame. Inference/threshold timing is content-independent, so
    this is representative for wall-clock timing at the configured resolution."""
    return np.random.randint(0, 256, (h, w, 3), dtype=np.uint8)


def _camera_grab(cfg: dict) -> "tuple[np.ndarray | None, np.ndarray | None]":
    """Grab one (left, right) BGR pair from the configured devices, else Nones."""
    import cv2
    cam = cfg.get("camera", {})
    backend = cv2.CAP_V4L2 if sys.platform.startswith("linux") else cv2.CAP_DSHOW

    def grab(idx):
        cap = cv2.VideoCapture(idx, backend)
        if not cap.isOpened():
            return None
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, cam.get("width", 1920))
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, cam.get("height", 1080))
        for _ in range(5):
            cap.grab()
        ok, frame = cap.read()
        cap.release()
        return frame if ok else None

    left = grab(cam.get("left_device", 0))
    right = grab(cam.get("right_device", 2)) if cam.get("right_device") is not None else None
    return left, right


def _time_it(fn, frames: int, warmup: int) -> dict:
    for _ in range(max(0, warmup)):
        fn()
    samples = []
    for _ in range(max(1, frames)):
        t0 = time.perf_counter()
        fn()
        samples.append(time.perf_counter() - t0)
    ms = sorted(t * 1000.0 for t in samples)
    mean = statistics.mean(samples)
    return {
        "mean_ms": statistics.mean(ms),
        "median_ms": statistics.median(ms),
        "p95_ms": ms[min(len(ms) - 1, int(0.95 * len(ms)))],
        "fps": (1.0 / mean) if mean > 0 else float("inf"),
    }


def _row(name: str, r: dict, target: "float | None" = None) -> str:
    verdict = ""
    if target is not None:
        verdict = "  PASS" if r["fps"] >= target else f"  BELOW {target:g}fps"
    return (f"  {name:<28} {r['fps']:7.1f} fps   "
            f"mean {r['mean_ms']:6.1f} ms   p95 {r['p95_ms']:6.1f} ms{verdict}")


# --------------------------------------------------------------------------- #
# Stage benchmarks
# --------------------------------------------------------------------------- #
def bench_segmentation(cfg: dict, frame: np.ndarray, frames: int, warmup: int) -> None:
    from pi5.cv.segmentation import WaterSegmentation

    vision = cfg.get("vision", {})
    print("\nTIER-1 WATER SEGMENTATION  (target >= 15 fps)")

    classical = WaterSegmentation(model_path=None)
    r = _time_it(lambda: classical.analyze(frame), frames, warmup)
    print(_row("classical (HSV/edge)", r, target=15.0))

    model_path = vision.get("seg_model_path")
    if model_path and Path(model_path).exists():
        model = WaterSegmentation(model_path, config=vision)
        if model.backend != "classical":
            r = _time_it(lambda: model.analyze(frame), frames, warmup)
            print(_row(f"model ({model.backend})", r, target=15.0))
        else:
            print(f"  model at {model_path} did not load — see startup warning")
    else:
        print(f"  (no seg model at {model_path or 'unset'} — classical only)")


def bench_detection(cfg: dict, frame: np.ndarray, frames: int, warmup: int) -> None:
    cam = cfg.get("camera", {})
    det = cam.get("detection", {})
    imgsz = int(det.get("imgsz", 320))
    conf = float(det.get("conf", 0.40))
    print("\nYOLO OBJECT DETECTION  (lower-but-high; bounded by imgsz)")

    maritime = REPO / "pi5" / "cv" / "models" / "maritime_yolov8n.onnx"
    if maritime.exists():
        try:
            from pi5.cv.onnx_detector import OnnxYolo
            onnx = OnnxYolo(str(maritime), conf=conf)
            if onnx.available:
                r = _time_it(lambda: onnx.infer(frame), frames, warmup)
                print(_row(f"onnx maritime (imgsz={onnx.imgsz})", r))
                return
        except Exception as e:  # noqa: BLE001
            print(f"  onnx backend unavailable: {e}")

    model_name = det.get("model", "yolov8n.pt")
    try:
        from ultralytics import YOLO
    except ImportError:
        print("  ultralytics not installed and no maritime .onnx — skipped")
        return
    try:
        model = YOLO(model_name)
    except Exception as e:  # noqa: BLE001
        print(f"  YOLO load failed ({model_name}): {e}")
        return
    r = _time_it(
        lambda: model(frame, imgsz=imgsz, conf=conf, verbose=False),
        frames, warmup)
    print(_row(f"ultralytics {model_name} (imgsz={imgsz})", r))


def bench_stereo(cfg: dict, left: np.ndarray, right: np.ndarray,
                 frames: int, warmup: int) -> None:
    cam = cfg.get("camera", {})
    calib_path = cam.get("calibration_path", "pi5/cv/calibration.npz")
    print("\nSTEREO DEPTH  (per-detection distance cost)")
    try:
        from pi5.cv.stereo import StereoDepth, load_calibration
    except Exception as e:  # noqa: BLE001
        print(f"  stereo module unavailable: {e}")
        return
    calib = load_calibration(calib_path)
    if calib is None:
        print(f"  (no calibration at {calib_path} — stereo distance disabled)")
        return
    configured = float(cam.get("stereo_downscale", 0.5))
    factors = sorted({1.0, configured}, reverse=True)
    for s in factors:
        depth = StereoDepth(calib, downscale=s)
        r = _time_it(lambda d=depth: d.compute(left, right), frames, warmup)
        tag = "full res" if s == 1.0 else f"downscale={s:g}"
        marker = "  <- configured" if s == configured else ""
        print(_row(f"SGBM ({tag})", r) + marker)


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main() -> None:
    ap = argparse.ArgumentParser(description="Benchmark the vision pipeline stages.")
    ap.add_argument("--source", choices=["synthetic", "camera"], default="synthetic",
                    help="frame source (default: synthetic random frames)")
    ap.add_argument("--frames", type=int, default=40, help="timed iterations per stage")
    ap.add_argument("--warmup", type=int, default=5, help="untimed warmup iterations")
    ap.add_argument("--width", type=int, default=None, help="override frame width")
    ap.add_argument("--height", type=int, default=None, help="override frame height")
    args = ap.parse_args()

    cfg = _load_config()
    cam = cfg.get("camera", {})
    w = args.width or int(cam.get("width", 1920))
    h = args.height or int(cam.get("height", 1080))

    left = right = None
    if args.source == "camera":
        left, right = _camera_grab(cfg)
        if left is not None:
            h, w = left.shape[:2]
    if left is None:
        left = _synthetic(w, h)
        right = _synthetic(w, h)
    if right is None:
        right = _synthetic(w, h)

    print("=" * 68)
    print(f"D.R.E.A.M.S vision benchmark  ({args.source} frames @ {w}x{h}, "
          f"{args.frames} iters, {args.warmup} warmup)")
    print(f"Platform: {sys.platform}  Python {sys.version.split()[0]}")
    print("Run this ON THE PI 5 — other machines don't represent the target.")
    print("=" * 68)

    bench_segmentation(cfg, left, args.frames, args.warmup)
    bench_detection(cfg, left, args.frames, args.warmup)
    bench_stereo(cfg, left, right, args.frames, args.warmup)
    print("\nDone. Tier-1 >= 15 fps and detection in the high single digits means "
          "the water screen and detector meet target.\n")


if __name__ == "__main__":
    main()
