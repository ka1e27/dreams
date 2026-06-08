"""Merge the staged maritime datasets into one unified YOLO dataset.

Runs on a laptop/Colab. Reads ml/data/raw/ (see download_datasets.py), remaps
every source's class ids to the 6 standard D.R.E.A.M.S classes, drops
background-only and duplicate images, splits 70/20/10, oversamples rare classes
in the train split, writes ml/data/unified/ + dataset.yaml, and saves a stats
report (counts, class distribution chart, resolution + objects/image stats).

    python ml/data/prepare_dataset.py
"""
from __future__ import annotations

import hashlib
import json
import random
import shutil
from collections import Counter
from pathlib import Path

RAW = Path("ml/data/raw")
OUT = Path("ml/data/unified")
SEED = 42
SPLITS = {"train": 0.70, "val": 0.20, "test": 0.10}
IMG_EXTS = {".jpg", ".jpeg", ".png", ".bmp"}
OVERSAMPLE_CAP = 5  # never duplicate a single image more than this many times

CLASSES = ["vessel", "kayak", "buoy", "person", "dock", "debris"]


def _load_remap() -> dict:
    f = RAW / "remap.json"
    if f.exists():
        return json.loads(f.read_text(encoding="utf-8"))
    return {"classes": CLASSES, "roboflow": {}, "smd": {}, "seaships": {}}


def _source_names(dataset_dir: Path) -> list[str] | None:
    """Read class names from a source's data.yaml / classes.txt, if present."""
    for yml in list(dataset_dir.rglob("data.yaml")) + list(dataset_dir.rglob("*.yaml")):
        try:
            import yaml
            d = yaml.safe_load(yml.read_text(encoding="utf-8"))
            names = d.get("names")
            if isinstance(names, dict):
                return [names[k] for k in sorted(names)]
            if isinstance(names, list):
                return names
        except Exception:  # noqa: BLE001
            continue
    ct = dataset_dir / "classes.txt"
    if ct.exists():
        return [ln.strip() for ln in ct.read_text(encoding="utf-8").splitlines() if ln.strip()]
    return None


def _id_map(source_key: str, names: list[str] | None, remap: dict) -> dict[int, int | None]:
    """source class id → standard id (or None to drop).

    If the source provides names, map name→standard via the remap table. With no
    names we assume the labels are already in the standard id space (identity).
    """
    table = {k.lower(): v for k, v in (remap.get(source_key) or {}).items()}
    if not names:
        return {i: i for i in range(len(CLASSES))}
    out: dict[int, int | None] = {}
    for sid, name in enumerate(names):
        if name.lower() in table:
            out[sid] = table[name.lower()]
        else:
            print(f"  [warn] {source_key}: unmapped class '{name}' → defaulting to vessel(0)")
            out[sid] = 0
    return out


def _find_label(img: Path) -> Path | None:
    cands = [
        img.parent.parent / "labels" / (img.stem + ".txt"),  # images/ ↔ labels/
        img.with_suffix(".txt"),                              # alongside the image
        img.parent / "labels" / (img.stem + ".txt"),
    ]
    for c in cands:
        if c.exists():
            return c
    return None


def _remap_label(lines: list[str], idmap: dict[int, int | None]) -> list[str]:
    out = []
    for ln in lines:
        parts = ln.split()
        if len(parts) < 5:
            continue
        try:
            sid = int(float(parts[0]))
        except ValueError:
            continue
        std = idmap.get(sid, 0)
        if std is None:
            continue
        out.append(" ".join([str(std)] + parts[1:]))
    return out


def collect() -> list[tuple[Path, list[str]]]:
    """Return [(image_path, remapped_label_lines)] across all sources, deduped,
    background-only images dropped."""
    remap = _load_remap()
    seen_hashes: set[str] = set()
    pool: list[tuple[Path, list[str]]] = []
    source_dirs = {
        "roboflow": RAW / "roboflow",
        "smd": RAW / "smd",
        "seaships": RAW / "seaships",
    }
    for key, root in source_dirs.items():
        if not root.exists():
            continue
        # roboflow nests per-project dirs; treat each as its own name space.
        project_dirs = [p for p in root.iterdir() if p.is_dir()] if key == "roboflow" else [root]
        for proj in project_dirs:
            idmap = _id_map(key, _source_names(proj), remap)
            imgs = [p for p in proj.rglob("*") if p.suffix.lower() in IMG_EXTS]
            kept = 0
            for img in imgs:
                lbl = _find_label(img)
                if lbl is None:
                    continue
                lines = _remap_label(lbl.read_text(encoding="utf-8").splitlines(), idmap)
                if not lines:          # background-only → drop
                    continue
                h = hashlib.md5(img.read_bytes()).hexdigest()
                if h in seen_hashes:   # duplicate image → drop
                    continue
                seen_hashes.add(h)
                pool.append((img, lines))
                kept += 1
            print(f"  {key}/{proj.name}: kept {kept} labelled images")
    return pool


def _split(pool: list) -> dict[str, list]:
    random.Random(SEED).shuffle(pool)
    n = len(pool)
    n_train = int(n * SPLITS["train"])
    n_val = int(n * SPLITS["val"])
    return {
        "train": pool[:n_train],
        "val": pool[n_train:n_train + n_val],
        "test": pool[n_train + n_val:],
    }


def _oversample(train: list) -> list:
    """Duplicate images containing rare classes so class counts even out."""
    per_class = Counter()
    for _, lines in train:
        for ln in lines:
            per_class[int(ln.split()[0])] += 1
    if not per_class:
        return train
    target = max(per_class.values())
    extra: list = []
    for img, lines in train:
        classes = {int(ln.split()[0]) for ln in lines}
        rarest = min((per_class[c] for c in classes), default=target)
        if rarest <= 0:
            continue
        reps = min(OVERSAMPLE_CAP, int(target / rarest)) - 1
        extra.extend([(img, lines)] * max(0, reps))
    print(f"  oversampling: +{len(extra)} duplicated train items "
          f"(class counts before: {dict(per_class)})")
    return train + extra


def write_split(name: str, items: list) -> None:
    img_dir = OUT / name / "images"
    lbl_dir = OUT / name / "labels"
    img_dir.mkdir(parents=True, exist_ok=True)
    lbl_dir.mkdir(parents=True, exist_ok=True)
    for i, (img, lines) in enumerate(items):
        stem = f"{name}_{i:06d}"
        shutil.copy(img, img_dir / (stem + img.suffix.lower()))
        (lbl_dir / (stem + ".txt")).write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_dataset_yaml() -> None:
    names = "\n".join(f"  {i}: {n}" for i, n in enumerate(CLASSES))
    (OUT / "dataset.yaml").write_text(
        f"path: {OUT.as_posix()}\n"
        "train: train/images\nval: val/images\ntest: test/images\n\n"
        f"nc: {len(CLASSES)}\nnames:\n{names}\n", encoding="utf-8")
    print("  wrote", OUT / "dataset.yaml")


def stats_report(splits: dict[str, list]) -> None:
    report = {"splits": {}, "classes": CLASSES}
    class_totals = Counter()
    resolutions: list[tuple[int, int]] = []
    obj_counts: list[int] = []
    try:
        import cv2
    except ImportError:
        cv2 = None
    for name, items in splits.items():
        cc = Counter()
        for img, lines in items:
            obj_counts.append(len(lines))
            for ln in lines:
                cc[int(ln.split()[0])] += 1
                class_totals[int(ln.split()[0])] += 1
            if cv2 is not None and name == "train" and len(resolutions) < 2000:
                im = cv2.imread(str(img))
                if im is not None:
                    resolutions.append((im.shape[1], im.shape[0]))
        report["splits"][name] = {"images": len(items),
                                  "by_class": {CLASSES[c]: cc[c] for c in range(len(CLASSES))}}
        print(f"  {name}: {len(items)} images, classes={ {CLASSES[c]: cc[c] for c in cc} }")
    report["avg_objects_per_image"] = round(sum(obj_counts) / max(1, len(obj_counts)), 2)
    if resolutions:
        ws = [w for w, _ in resolutions]
        hs = [h for _, h in resolutions]
        report["resolution"] = {"w_min": min(ws), "w_max": max(ws),
                                 "h_min": min(hs), "h_max": max(hs)}
    (OUT / "stats.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("  avg objects/image:", report["avg_objects_per_image"])

    # Class-distribution bar chart.
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        plt.figure(figsize=(8, 4))
        plt.bar(CLASSES, [class_totals[i] for i in range(len(CLASSES))], color="#ff8c00")
        plt.title("Class distribution (all splits)")
        plt.ylabel("instances")
        plt.tight_layout()
        plt.savefig(OUT / "class_distribution.png", dpi=110)
        plt.close()
        print("  wrote", OUT / "class_distribution.png")
    except Exception as e:  # noqa: BLE001
        print("  [warn] chart skipped:", e)


def main() -> None:
    print("=== prepare unified maritime dataset ===")
    if OUT.exists():
        shutil.rmtree(OUT)
    pool = collect()
    if not pool:
        print("No labelled images found under ml/data/raw/. Run download_datasets.py first "
              "and stage SMD/SeaShips manually.")
        return
    print(f"Total unique labelled images: {len(pool)}")
    splits = _split(pool)
    splits["train"] = _oversample(splits["train"])
    for name, items in splits.items():
        write_split(name, items)
    write_dataset_yaml()
    stats_report(splits)
    print("\nDone →", OUT, "\nNext: python ml/data/augment.py  (optional)  then  python ml/train.py")


if __name__ == "__main__":
    main()
