"""Export the trained maritime model to ONNX for the Pi 5, and benchmark it.

Run on a laptop/Colab. Converts ml/runs/maritime_v1/weights/best.pt →
pi5/cv/models/maritime_yolov8n.onnx (imgsz 320, simplified, fixed input),
benchmarks it with onnxruntime on CPU, and writes/updates the model card
pi5/cv/models/maritime_yolov8n_info.json with the metrics.

    python ml/export_onnx.py

The .onnx is gitignored — copy it to the Pi (scp). vision_overlay auto-detects
pi5/cv/models/maritime_yolov8n.onnx and runs it via onnxruntime.
"""
from __future__ import annotations

import datetime
import json
import shutil
import time
from pathlib import Path

WEIGHTS = Path("ml/runs/maritime_v1/weights/best.pt")
DATA = "ml/data/unified/dataset.yaml"
MODELS = Path("pi5/cv/models")
ONNX_OUT = MODELS / "maritime_yolov8n.onnx"
INFO_OUT = MODELS / "maritime_yolov8n_info.json"
IMGSZ = 320
CLASSES = ["vessel", "kayak", "buoy", "person", "dock", "debris"]


def main() -> None:
    try:
        from ultralytics import YOLO
    except ImportError:
        raise SystemExit("ultralytics not installed — pip install ultralytics")
    if not WEIGHTS.exists():
        raise SystemExit(f"{WEIGHTS} not found — train first (python ml/train.py)")

    model = YOLO(str(WEIGHTS))
    print(f"=== Exporting {WEIGHTS} → ONNX (imgsz={IMGSZ}) ===")
    exported = model.export(
        format="onnx",
        imgsz=IMGSZ,
        optimize=False,   # 'optimize' is a TorchScript-only flag; keep False for onnx
        simplify=True,    # simplify the ONNX graph
        opset=12,         # broad compatibility
        dynamic=False,    # fixed input size = faster on the Pi
    )
    MODELS.mkdir(parents=True, exist_ok=True)
    shutil.copy(exported, ONNX_OUT)
    print("  copied →", ONNX_OUT)

    # Pull metrics from a quick test-set val so the model card is populated.
    mAP50 = mAP = 0.0
    try:
        m = model.val(data=DATA, split="test", plots=False)
        mAP50, mAP = float(m.box.map50), float(m.box.map)
    except Exception as e:  # noqa: BLE001
        print("  (val for metrics skipped:", e, ")")

    cpu_fps = _benchmark_onnx(str(ONNX_OUT))
    print(f"  onnxruntime CPU: mean FPS {cpu_fps:.1f}")

    info = {
        "model": "maritime_yolov8n",
        "base": "yolov8n",
        "format": "onnx",
        "imgsz": IMGSZ,
        "classes": CLASSES,
        "trained_on": ["roboflow-maritime", "smd", "seaships"],
        "mAP50": round(mAP50, 4),
        "mAP50-95": round(mAP, 4),
        "cpu_fps_pi5": round(cpu_fps, 1),
        "exported": datetime.datetime.now().isoformat(timespec="seconds"),
        "note": "cpu_fps_pi5 here is the export-machine CPU; re-run the benchmark "
                "on the Pi for the real number.",
    }
    INFO_OUT.write_text(json.dumps(info, indent=2), encoding="utf-8")
    print("  wrote model card →", INFO_OUT)
    print("\nDeploy: scp", ONNX_OUT, "ka1e27@dreams-pi:~/D.R.E.A.M.S/pi5/cv/models/")


def _benchmark_onnx(onnx_path: str, runs: int = 100) -> float:
    try:
        import numpy as np
        import onnxruntime as ort
    except ImportError:
        print("  (onnxruntime not installed — skipping benchmark)")
        return 0.0
    sess = ort.InferenceSession(onnx_path, providers=["CPUExecutionProvider"])
    name = sess.get_inputs()[0].name
    dummy = np.random.randn(1, 3, IMGSZ, IMGSZ).astype("float32")
    for _ in range(10):  # warmup
        sess.run(None, {name: dummy})
    times = []
    for _ in range(runs):
        t0 = time.perf_counter()
        sess.run(None, {name: dummy})
        times.append(time.perf_counter() - t0)
    import numpy as np
    print(f"  mean latency: {np.mean(times) * 1000:.1f} ms")
    return 1.0 / float(np.mean(times)) if times else 0.0


if __name__ == "__main__":
    main()
