"""Validate the trained maritime model on the test split + CPU benchmark.

Run on a laptop/Colab. Loads ml/runs/maritime_v1/weights/best.pt, evaluates on
the test set (confusion matrix + PR/F1 curves are written by ultralytics into
the run dir), saves a few sample detections, benchmarks CPU inference at
imgsz=320 (a Pi-5 proxy), and prints pass/fail against the acceptance
thresholds in ml/README.md.

    python ml/validate.py
"""
from __future__ import annotations

import time
from pathlib import Path

WEIGHTS = Path("ml/runs/maritime_v1/weights/best.pt")
DATA = "ml/data/unified/dataset.yaml"
SAMPLES = Path("ml/validation_samples")

# (class name, min mAP50). Plus a global FPS floor below.
THRESHOLDS = {"vessel": 0.70, "kayak": 0.50, "buoy": 0.60, "person": 0.65}
MIN_CPU_FPS_320 = 8.0


def main() -> None:
    try:
        from ultralytics import YOLO
    except ImportError:
        raise SystemExit("ultralytics not installed — pip install ultralytics")
    if not WEIGHTS.exists():
        raise SystemExit(f"{WEIGHTS} not found — train first (python ml/train.py)")

    model = YOLO(str(WEIGHTS))

    # --- Test-set metrics (writes confusion matrix + PR/F1 curves to the run dir) ---
    print("=== Test-set validation ===")
    metrics = model.val(data=DATA, split="test", plots=True)
    names = metrics.names if hasattr(metrics, "names") else {}
    per_class_ap50: dict[str, float] = {}
    try:
        box = metrics.box
        print(f"  mAP50:    {box.map50:.4f}")
        print(f"  mAP50-95: {box.map:.4f}")
        for i, ap50 in enumerate(getattr(box, "ap50", []) or []):
            nm = names.get(i, str(i))
            per_class_ap50[nm] = float(ap50)
            print(f"    {nm}: AP50={ap50:.4f}")
    except Exception as e:  # noqa: BLE001
        print("  (per-class metrics unavailable:", e, ")")

    # --- Sample detections ---
    SAMPLES.mkdir(parents=True, exist_ok=True)
    test_imgs = sorted(Path("ml/data/unified/test/images").glob("*"))[:12]
    if test_imgs:
        model.predict(source=[str(p) for p in test_imgs], save=True,
                      project=str(SAMPLES.parent), name=SAMPLES.name, exist_ok=True,
                      imgsz=320, conf=0.4, verbose=False)
        print(f"  sample detections → {SAMPLES}")

    # --- CPU inference benchmark @ imgsz 320 (Pi-5 proxy) ---
    print("\n=== CPU inference benchmark (imgsz=320) ===")
    cpu_fps = _benchmark_cpu(YOLO, str(WEIGHTS))
    print(f"  mean FPS (CPU): {cpu_fps:.1f}")

    # --- Pass/fail ---
    print("\n=== Acceptance thresholds ===")
    all_ok = True
    for cls, thr in THRESHOLDS.items():
        ap = per_class_ap50.get(cls)
        ok = ap is not None and ap > thr
        all_ok &= ok
        got = f"{ap:.3f}" if ap is not None else "n/a"
        print(f"  [{'PASS' if ok else 'FAIL'}] {cls} mAP50 > {thr}  (got {got})")
    ok_fps = cpu_fps > MIN_CPU_FPS_320
    all_ok &= ok_fps
    print(f"  [{'PASS' if ok_fps else 'FAIL'}] CPU FPS > {MIN_CPU_FPS_320} @ imgsz 320  (got {cpu_fps:.1f})")
    print("\nRESULT:", "ALL PASS — export with ml/export_onnx.py" if all_ok
          else "some thresholds FAILED — more data/epochs may be needed")


def _benchmark_cpu(YOLO, weights: str, runs: int = 50) -> float:
    import numpy as np
    model = YOLO(weights)
    dummy = (np.random.rand(640, 640, 3) * 255).astype("uint8")
    for _ in range(5):  # warmup
        model.predict(dummy, imgsz=320, device="cpu", verbose=False)
    t0 = time.perf_counter()
    for _ in range(runs):
        model.predict(dummy, imgsz=320, device="cpu", verbose=False)
    dt = (time.perf_counter() - t0) / runs
    return 1.0 / dt if dt > 0 else 0.0


if __name__ == "__main__":
    main()
