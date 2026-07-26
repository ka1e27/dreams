"""Export eWaSR to the ONNX the D.R.E.A.M.S hybrid water screen expects.

Trains nothing — takes a pretrained eWaSR checkpoint and produces
``pi5/cv/models/water_seg.onnx``: a single-image-input, 3-class
(obstacle / water / sky) segmentation model that the Tier-1b confirmation loop
auto-loads (``vision.seg_confirm_model_path``; see ``docs/water_vision.md``).

Run on a machine (GPU box / laptop) with the eWaSR repo cloned and its deps
installed — NOT on the Pi. The Pi only receives the final ``water_seg.onnx``.

    # 1. eWaSR + a pretrained non-IMU checkpoint
    git clone https://github.com/tersekmatija/eWaSR
    pip install torch onnx onnxsim onnxruntime opencv-python
    #   download ewasr_resnet18.pth from the 0.1.0 release:
    #   https://github.com/tersekmatija/eWaSR/releases/tag/0.1.0

    # 2. export (+ optional sanity check)
    python ml/export_ewasr.py --ewasr-repo ./eWaSR \
        --weights ./eWaSR/pretrained/ewasr_resnet18.pth --self-check

    # 3. copy to the Pi
    scp pi5/cv/models/water_seg.onnx <pi>:~/D.R.E.A.M.S/pi5/cv/models/

Why the non-IMU ``ewasr_resnet18`` variant: the boat has no horizon-IMU mask
feeding the net, and the hybrid backend (``pi5/cv/segmentation.py``) feeds a
single image tensor. eWaSR's ``forward`` takes a dict ``{"image", "imu_mask"}``;
the non-IMU net never reads ``imu_mask``, so the ONNX trace prunes it and the
graph ends up with a single input — exactly what the backend wants. The IMU
variant keeps two inputs and won't load there.

Class convention (MaSTr1325 / WaSR): ``0=obstacle, 1=water, 2=sky``. This matches
``config.yaml``'s ``vision.seg_water_class: 1`` / ``seg_ignore_classes: [2]``.
If your checkpoint uses a different order, ``--self-check`` will show it (water
won't dominate on a water frame) — then adjust those two config keys.

Normalisation: ImageNet on RGB (mean .485/.456/.406, std .229/.224/.225, after
/255) — identical to the backend's ``seg_normalize: "imagenet"``.
"""
from __future__ import annotations

import argparse
import datetime
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT = REPO_ROOT / "pi5" / "cv" / "models" / "water_seg.onnx"
INFO = REPO_ROOT / "pi5" / "cv" / "models" / "water_seg_info.json"
# MaSTr1325 / WaSR index order — must line up with config seg_water_class/ignore.
CLASSES = ["obstacle", "water", "sky"]
_MEAN = [0.485, 0.456, 0.406]
_STD = [0.229, 0.224, 0.225]


def _load_state(path: Path, load_weights_fn):
    """Load a checkpoint state_dict, tolerant of common layouts."""
    if load_weights_fn is not None:
        try:
            return load_weights_fn(str(path))
        except Exception as e:  # noqa: BLE001 — fall back to a generic loader
            print(f"  wasr.utils.load_weights failed ({e}); using generic loader")
    import torch
    ckpt = torch.load(str(path), map_location="cpu")
    if isinstance(ckpt, dict):
        for key in ("model_state_dict", "state_dict", "weights", "model"):
            if key in ckpt and isinstance(ckpt[key], dict):
                ckpt = ckpt[key]
                break
    return {(k[7:] if k.startswith("module.") else k): v for k, v in ckpt.items()}


def _write_info(args) -> None:
    info = {
        "model": args.arch,
        "task": "water_segmentation",
        "format": "onnx",
        "input_size": [args.width, args.height],   # [w, h]
        "layout": "NCHW",
        "normalize": "imagenet",
        "classes": CLASSES,                         # 0=obstacle,1=water,2=sky
        "water_class": 1,
        "ignore_classes": [2],
        "source": "https://github.com/tersekmatija/eWaSR",
        "exported": datetime.datetime.now().isoformat(timespec="seconds"),
        "note": "Feeds pi5/cv/segmentation.py ONNX backend (hybrid Tier-1b). "
                "Point vision.seg_confirm_model_path at the sibling .onnx.",
    }
    INFO.write_text(json.dumps(info, indent=2), encoding="utf-8")
    print("  wrote model card →", INFO)


def _report_io(out_path: Path) -> None:
    try:
        import onnx
    except ImportError:
        return
    m = onnx.load(str(out_path))

    def shp(v):
        return [d.dim_value or d.dim_param for d in v.type.tensor_type.shape.dim]

    ins = [(i.name, shp(i)) for i in m.graph.input]
    outs = [(o.name, shp(o)) for o in m.graph.output]
    print("  ONNX inputs:  " + ", ".join(f"{n}{s}" for n, s in ins))
    print("  ONNX outputs: " + ", ".join(f"{n}{s}" for n, s in outs))
    if len(ins) != 1:
        print(f"  WARNING: {len(ins)} inputs, but the hybrid backend feeds ONE. "
              f"Use the non-IMU 'ewasr_resnet18' arch so imu_mask is pruned.")


def _self_check(out_path: Path, args) -> None:
    try:
        import cv2
        import numpy as np
        import onnxruntime as ort
    except ImportError as e:
        print(f"  self-check skipped (need onnxruntime+opencv+numpy): {e}")
        return
    sess = ort.InferenceSession(str(out_path), providers=["CPUExecutionProvider"])
    name = sess.get_inputs()[0].name
    frame = np.full((args.height, args.width, 3), (140, 90, 30), np.uint8)  # blue
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
    rgb = (rgb - np.array(_MEAN, np.float32)) / np.array(_STD, np.float32)
    blob = np.ascontiguousarray(np.transpose(rgb, (2, 0, 1))[np.newaxis, ...])
    out = np.asarray(sess.run(None, {name: blob})[0])[0]        # (C, H, W)
    if out.ndim != 3:
        print(f"  self-check: unexpected output ndim {out.ndim}; skipping split")
        return
    labels = out.argmax(axis=0)
    print("  self-check on a solid blue frame — per-class pixel share:")
    for i, c in enumerate(CLASSES):
        print(f"    {i} {c:<9} {float((labels == i).mean()) * 100:5.1f}%")
    print("  (expect 'water' to dominate. If it doesn't, your checkpoint's class "
          "order differs — set vision.seg_water_class / seg_ignore_classes to match.)")


def main() -> None:
    ap = argparse.ArgumentParser(description="Export eWaSR → pi5/cv/models/water_seg.onnx")
    ap.add_argument("--ewasr-repo", required=True, help="path to a cloned eWaSR repo")
    ap.add_argument("--weights", required=True,
                    help="eWaSR checkpoint (.pth) — the NON-IMU variant")
    ap.add_argument("--arch", default="ewasr_resnet18",
                    help="eWaSR architecture (must be single-input / non-IMU)")
    ap.add_argument("--height", type=int, default=384)
    ap.add_argument("--width", type=int, default=512)
    ap.add_argument("--num-classes", type=int, default=3)
    ap.add_argument("--opset", type=int, default=12)
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--no-simplify", action="store_true", help="skip onnxsim")
    ap.add_argument("--self-check", action="store_true",
                    help="run the exported model on a water frame and report the "
                         "per-class split (confirms class order + normalisation)")
    args = ap.parse_args()

    if "imu" in args.arch:
        raise SystemExit(f"--arch {args.arch} is an IMU (2-input) variant; the hybrid "
                         "backend feeds a single image. Use ewasr_resnet18.")

    repo = Path(args.ewasr_repo).resolve()
    if not (repo / "wasr").is_dir():
        raise SystemExit(f"--ewasr-repo {repo} is not the eWaSR repo (no wasr/ dir)")
    sys.path.insert(0, str(repo))

    try:
        import torch
        import wasr.models as M
    except ImportError as e:
        raise SystemExit(f"import failed ({e}) — run where the eWaSR repo + its deps "
                         "(torch, onnx, onnxsim) are installed")

    model_list = getattr(M, "model_list", None)
    if model_list is not None and args.arch not in model_list:
        print(f"  warning: '{args.arch}' not in eWaSR model_list {list(model_list)}")

    try:
        load_weights_fn = __import__("wasr.utils", fromlist=["load_weights"]).load_weights
    except Exception:  # noqa: BLE001
        load_weights_fn = None

    print(f"=== Building {args.arch} (num_classes={args.num_classes}) ===")
    model = M.get_model(args.arch, num_classes=args.num_classes, pretrained=False)
    state = _load_state(Path(args.weights), load_weights_fn)
    try:
        model.load_state_dict(state, strict=True)
        print("  weights loaded (strict)")
    except RuntimeError as e:
        print(f"  strict load failed ({str(e)[:120]}…) — retrying strict=False")
        res = model.load_state_dict(state, strict=False)
        print(f"    missing={len(res.missing_keys)} unexpected={len(res.unexpected_keys)}")
    model.eval()

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    # eWaSR forward takes a dict {"image","imu_mask"} passed as kwarg "x"
    # (mirrors the repo's export.py). The non-IMU net ignores imu_mask, so the
    # trace prunes it → a single ONNX input.
    dummy = {"image": torch.randn(1, 3, args.height, args.width),
             "imu_mask": torch.randn(1, args.height, args.width)}
    print(f"=== Exporting → {out_path} (opset {args.opset}, {args.width}x{args.height}) ===")
    torch.onnx.export(
        model, {"x": dummy}, f=str(out_path), opset_version=args.opset,
        output_names=["prediction", "intermediate"])

    if not args.no_simplify:
        try:
            import onnx
            import onnxsim
            m = onnx.load(str(out_path))
            m2, ok = onnxsim.simplify(m)
            if ok:
                onnx.save(m2, str(out_path))
                print("  simplified graph (onnxsim)")
            else:
                print("  onnxsim check failed — keeping unsimplified graph")
        except Exception as e:  # noqa: BLE001 — simplification is optional
            print(f"  simplify skipped ({e})")

    _write_info(args)
    _report_io(out_path)
    if args.self_check:
        _self_check(out_path, args)

    print(f"\nDeploy: scp {out_path} <pi>:~/D.R.E.A.M.S/pi5/cv/models/")
    print("On the Pi, vision.seg_confirm_model_path already points here — restart, "
          "then confirm with:  python -m pi5.scripts.benchmark_vision")


if __name__ == "__main__":
    main()
