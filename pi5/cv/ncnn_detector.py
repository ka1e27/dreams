"""NCNN YOLOv8 inference backend — the fastest CPU path on the Raspberry Pi 5.

NCNN is Tencent's hand-tuned ARM inference engine; on a Pi 5 it runs YOLOv8n
roughly 2-3x faster than onnxruntime+XNNPACK at the same imgsz (Ultralytics'
own Raspberry Pi benchmark recommends it). This loads an Ultralytics NCNN export
directory (``yolov8n_ncnn_model/`` containing ``model.ncnn.param`` +
``model.ncnn.bin`` + ``metadata.yaml``) through the lightweight ``ncnn`` Python
package — **no torch / ultralytics at runtime**, matching the ONNX path's
footprint. It reuses ``onnx_detector``'s letterbox + numpy decode so the boxes,
labels, tracking reticle and radar all behave identically whichever backend is
active.

Degrades to ``available == False`` if the ``ncnn`` package or the model files are
missing, exactly like the ONNX backend, so the server still runs (just without
detection).
"""
from __future__ import annotations

import logging
import os

import numpy as np

from .onnx_detector import MARITIME_CLASSES, decode, letterbox

logger = logging.getLogger(__name__)


def _find(dir_path: str, suffix: str) -> str | None:
    try:
        for f in os.listdir(dir_path):
            if f.endswith(suffix):
                return os.path.join(dir_path, f)
    except OSError:
        return None
    return None


def _load_meta(dir_path: str) -> tuple[list[str], int, str, str]:
    """Read Ultralytics' metadata.yaml (names dict + imgsz) from the export dir.

    Returns (names, imgsz, in_name, out_name). Falls back to the maritime class
    list + 320 + in0/out0 if the file is absent or unparseable."""
    names: list[str] = list(MARITIME_CLASSES)
    imgsz = 320
    meta = os.path.join(dir_path, "metadata.yaml")
    try:
        import yaml
        with open(meta, encoding="utf-8") as f:
            d = yaml.safe_load(f) or {}
        nm = d.get("names")
        if isinstance(nm, dict):
            names = [nm[k] for k in sorted(nm, key=int)]
        elif isinstance(nm, list):
            names = list(nm)
        isz = d.get("imgsz")
        if isinstance(isz, (list, tuple)):
            imgsz = int(isz[0])
        elif isz:
            imgsz = int(isz)
    except (OSError, ValueError, KeyError, TypeError, ImportError) as e:
        logger.debug("ncnn metadata read failed (%s): %s", meta, e)
    return names, imgsz, "in0", "out0"


class NcnnYolo:
    """Minimal YOLOv8 NCNN runner. Mirrors OnnxYolo's interface so
    vision_overlay is backend-agnostic."""

    def __init__(self, model_dir: str, names: list[str] | None = None,
                 conf: float = 0.40, iou: float = 0.45) -> None:
        self.model_dir = model_dir
        self.conf = float(conf)
        self.iou = float(iou)
        self.net = None
        self.names, self.imgsz, self._in, self._out = _load_meta(model_dir)
        if names:
            self.names = list(names)
        param = _find(model_dir, ".param")
        bin_ = _find(model_dir, ".bin")
        if not (param and bin_):
            logger.warning("NCNN model files not found in %s", model_dir)
            return
        try:
            import ncnn  # heavy/optional — deferred
        except ImportError as e:
            logger.warning("ncnn not installed — NCNN detector off (%s)", e)
            return
        try:
            net = ncnn.Net()
            # Use all 4 Pi cores; light threads for the small yolov8n graph.
            net.opt.num_threads = 4
            net.opt.use_vulkan_compute = False
            net.load_param(param)
            net.load_model(bin_)
            self.net = net
            logger.info("NCNN detector loaded: %s (imgsz=%d, %d classes)",
                        os.path.basename(model_dir), self.imgsz, len(self.names))
        except Exception as e:  # noqa: BLE001 — degrade, never crash startup
            logger.warning("NCNN load failed (%s): %s", model_dir, e)
            self.net = None

    @property
    def available(self) -> bool:
        return self.net is not None

    def infer(self, frame_bgr, conf: float | None = None) -> list[tuple]:
        """Run detection on a BGR frame → [(x1,y1,x2,y2,label,conf), ...]."""
        if self.net is None:
            return []
        try:
            import cv2
            import ncnn
            h, w = frame_bgr.shape[:2]
            canvas, ratio, pad_x, pad_y = letterbox(frame_bgr, self.imgsz)
            rgb = cv2.cvtColor(canvas, cv2.COLOR_BGR2RGB)
            mat_in = ncnn.Mat.from_pixels(
                rgb, ncnn.Mat.PixelType.PIXEL_RGB, self.imgsz, self.imgsz)
            mat_in.substract_mean_normalize([0.0, 0.0, 0.0],
                                            [1 / 255.0, 1 / 255.0, 1 / 255.0])
            ex = self.net.create_extractor()
            ex.input(self._in, mat_in)
            ret, mat_out = ex.extract(self._out)
            if ret != 0:
                return []
            out = np.array(mat_out)          # (4+nc, N) for yolov8
            if out.ndim == 2:
                out = out[np.newaxis, ...]   # -> (1, 4+nc, N) for decode()
            return decode(out, self.names,
                          conf if conf is not None else self.conf, self.iou,
                          ratio, pad_x, pad_y, w, h)
        except Exception as e:  # noqa: BLE001 — a bad frame must not kill the loop
            logger.error("NCNN inference error: %s", e)
            return []
