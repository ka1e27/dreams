"""Maritime YOLOv8n fine-tuning.

Run on a laptop with a GPU, or Google Colab (free T4 works). Do NOT run on the
Pi 5 — far too slow. Starts from COCO-pretrained yolov8n weights and fine-tunes
on the unified maritime dataset (ml/data/unified/dataset.yaml).

    python ml/train.py
    python ml/train.py --epochs 100 --batch 16
    python ml/train.py --resume        # resume an interrupted run
"""
from __future__ import annotations

import argparse
from pathlib import Path

DATA = "ml/data/unified/dataset.yaml"
PROJECT = "ml/runs"
NAME = "maritime_v1"


def main() -> None:
    ap = argparse.ArgumentParser(description="Fine-tune YOLOv8n for maritime detection")
    ap.add_argument("--epochs", type=int, default=100)
    ap.add_argument("--batch", type=int, default=16, help="reduce to 8 if GPU OOM")
    ap.add_argument("--imgsz", type=int, default=640, help="train at 640; infer at 320 on the Pi")
    ap.add_argument("--device", default="0", help="GPU id, or 'cpu'")
    ap.add_argument("--resume", action="store_true")
    args = ap.parse_args()

    try:
        from ultralytics import YOLO
    except ImportError:
        raise SystemExit("ultralytics not installed — pip install ultralytics")

    if args.resume:
        ckpt = Path(PROJECT) / NAME / "weights" / "last.pt"
        if not ckpt.exists():
            raise SystemExit(f"--resume: no checkpoint at {ckpt}")
        model = YOLO(str(ckpt))
        results = model.train(resume=True)
    else:
        if not Path(DATA).exists():
            raise SystemExit(f"{DATA} not found — run ml/data/prepare_dataset.py first")
        model = YOLO("yolov8n.pt")  # COCO-pretrained
        results = model.train(
            data=DATA,
            epochs=args.epochs,
            imgsz=args.imgsz,
            batch=args.batch,
            patience=20,            # early stopping
            save=True,
            save_period=10,         # checkpoint every 10 epochs
            device=args.device,
            workers=4,
            project=PROJECT,
            name=NAME,
            exist_ok=True,
            # On-the-fly augmentation (on top of ml/data/augment.py).
            hsv_h=0.015, hsv_s=0.7, hsv_v=0.4,
            degrees=15.0, translate=0.1, scale=0.5,
            flipud=0.0,             # never flip vertically
            fliplr=0.5,
            mosaic=1.0,
            # Transfer learning — freeze the first 10 layers (backbone) to keep
            # COCO knowledge while the head adapts to maritime classes.
            freeze=10,
            pretrained=True,
        )

    # Summary.
    best = Path(PROJECT) / NAME / "weights" / "best.pt"
    print("\n=== Training summary ===")
    print("  best weights:", best)
    try:
        box = results.box  # ultralytics metrics object
        print(f"  mAP50:    {box.map50:.4f}")
        print(f"  mAP50-95: {box.map:.4f}")
        names = results.names if hasattr(results, "names") else {}
        for i, ap50 in enumerate(getattr(box, "ap50", []) or []):
            print(f"    {names.get(i, i)}: AP50={ap50:.4f}")
    except Exception as e:  # noqa: BLE001 — metrics shape varies by version
        print("  (metrics object not available:", e, ")")
    if best.exists():
        print(f"  model size: {best.stat().st_size / 1e6:.1f} MB")
    print("\nNext: python ml/validate.py   then   python ml/export_onnx.py")


if __name__ == "__main__":
    main()
