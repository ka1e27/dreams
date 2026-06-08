"""Maritime-specific augmentation for the unified train split.

Runs on a laptop/Colab. For each image in ml/data/unified/train it writes one
augmented copy (suffix `_aug`), roughly doubling the effective train size, with
water/lighting effects YOLOv8's built-in augmentation doesn't cover (sun glare,
haze, brightness/colour shifts, salt-spray noise/blur) plus safe geometric ones
(horizontal flip, ±15° rotation, scale). Bounding boxes are transformed with the
image via Albumentations' YOLO bbox params.

Deliberately NOT applied: vertical flip / >15° rotation — boats don't appear
upside-down or sideways. Mosaic is left to YOLOv8 (on by default in train.py).

    python ml/data/augment.py [--per-image N]
"""
from __future__ import annotations

import argparse
import random
from pathlib import Path

TRAIN = Path("ml/data/unified/train")
IMG_EXTS = {".jpg", ".jpeg", ".png", ".bmp"}


def _pipeline():
    import albumentations as A
    # min_visibility drops boxes that augmentation pushes mostly out of frame.
    return A.Compose([
        A.HorizontalFlip(p=0.5),
        A.Rotate(limit=15, border_mode=0, p=0.5),                 # ±15° only
        A.RandomScale(scale_limit=0.2, p=0.4),
        A.RandomBrightnessContrast(brightness_limit=0.3, contrast_limit=0.3, p=0.6),
        A.HueSaturationValue(hue_shift_limit=10, sat_shift_limit=25,
                             val_shift_limit=20, p=0.5),           # time-of-day colour
        A.OneOf([
            A.RandomSunFlare(flare_roi=(0, 0, 1, 0.5), src_radius=120, p=1.0),  # glare on water
            A.RandomFog(fog_coef_lower=0.1, fog_coef_upper=0.4, p=1.0),         # haze/distance
        ], p=0.4),
        A.OneOf([
            A.GaussNoise(var_limit=(10, 50), p=1.0),              # salt spray
            A.MotionBlur(blur_limit=5, p=1.0),
            A.OpticalDistortion(distort_limit=0.1, p=1.0),        # water-surface distortion
        ], p=0.3),
    ], bbox_params=A.BboxParams(format="yolo", label_fields=["class_labels"],
                                min_visibility=0.3))


def _read_yolo(label: Path):
    boxes, labels = [], []
    if not label.exists():
        return boxes, labels
    for ln in label.read_text(encoding="utf-8").splitlines():
        p = ln.split()
        if len(p) >= 5:
            labels.append(int(float(p[0])))
            boxes.append([float(x) for x in p[1:5]])
    return boxes, labels


def _write_yolo(label: Path, boxes, labels) -> None:
    lines = [" ".join([str(c)] + [f"{v:.6f}" for v in b]) for c, b in zip(labels, boxes)]
    label.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-image", type=int, default=1, help="augmented copies per image")
    args = ap.parse_args()

    try:
        import cv2
    except ImportError:
        print("opencv (cv2) required — pip install opencv-python")
        return
    try:
        pipe = _pipeline()
    except ImportError:
        print("albumentations required — pip install albumentations")
        return

    img_dir = TRAIN / "images"
    lbl_dir = TRAIN / "labels"
    if not img_dir.exists():
        print("No train split at", img_dir, "— run prepare_dataset.py first.")
        return

    originals = [p for p in img_dir.iterdir()
                 if p.suffix.lower() in IMG_EXTS and "_aug" not in p.stem]
    random.seed(42)
    made = 0
    for img_path in originals:
        image = cv2.imread(str(img_path))
        if image is None:
            continue
        boxes, labels = _read_yolo(lbl_dir / (img_path.stem + ".txt"))
        if not boxes:
            continue
        for k in range(args.per_image):
            try:
                out = pipe(image=image, bboxes=boxes, class_labels=labels)
            except Exception:  # noqa: BLE001 — skip an image that won't transform
                continue
            if not out["bboxes"]:
                continue
            stem = f"{img_path.stem}_aug{k}"
            cv2.imwrite(str(img_dir / (stem + img_path.suffix.lower())), out["image"])
            _write_yolo(lbl_dir / (stem + ".txt"), out["bboxes"], out["class_labels"])
            made += 1
    print(f"Augmented {made} images into {img_dir} (from {len(originals)} originals).")


if __name__ == "__main__":
    main()
