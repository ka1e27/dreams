"""onnxruntime YOLOv8 inference backend — for the maritime model on the Pi 5.

This runs an exported YOLOv8 ``.onnx`` (see ``ml/export_onnx.py``) through
**onnxruntime** on the CPU, with no PyTorch / ultralytics needed at inference
time — the lightweight footprint the maritime-ML instruction targets. It
implements YOLOv8's letterbox preprocessing, the forward pass, and the
postprocessing (decode + per-class NMS) in numpy, and returns the same
``(x1, y1, x2, y2, label, conf)`` tuples that ``vision_overlay`` already builds
from the ultralytics path — so detection boxes, the tracking reticle, and the
radar tracker all work unchanged whichever backend is active.

It degrades to ``available == False`` (model = None) if onnxruntime or the model
file is missing, mirroring how the ultralytics path degrades, so the server
still runs — just without detection.

Class names come from (in order): an explicit ``names`` argument, a sibling
``<stem>_info.json`` ``classes`` list (written by the export step), else the six
standard maritime classes.
"""
from __future__ import annotations

import json
import logging
import os

import numpy as np

logger = logging.getLogger(__name__)

# The 6 maritime classes the ml/ pipeline trains on (order = class id).
MARITIME_CLASSES = ["vessel", "kayak", "buoy", "person", "dock", "debris"]


def _load_names(model_path: str, names: list[str] | None) -> list[str]:
    if names:
        return list(names)
    info = os.path.splitext(model_path)[0] + "_info.json"
    try:
        with open(info, encoding="utf-8") as f:
            classes = json.load(f).get("classes")
        if classes:
            return list(classes)
    except (OSError, ValueError, json.JSONDecodeError):
        pass
    return list(MARITIME_CLASSES)


def letterbox(img, size: int, color: int = 114):
    """Resize keeping aspect ratio and pad to a square ``size`` (YOLOv8 style).

    Returns (canvas, ratio, pad_x, pad_y). ``ratio`` and the pads are needed to
    map detections back onto the original frame.
    """
    import cv2
    h, w = img.shape[:2]
    r = min(size / h, size / w)
    nh, nw = int(round(h * r)), int(round(w * r))
    resized = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_LINEAR)
    canvas = np.full((size, size, 3), color, dtype=np.uint8)
    pad_x = (size - nw) // 2
    pad_y = (size - nh) // 2
    canvas[pad_y:pad_y + nh, pad_x:pad_x + nw] = resized
    return canvas, r, pad_x, pad_y


def _nms(boxes: np.ndarray, scores: np.ndarray, iou_thr: float) -> list[int]:
    """Greedy NMS in numpy. boxes: (N,4) xyxy. Returns kept indices."""
    if len(boxes) == 0:
        return []
    x1, y1, x2, y2 = boxes[:, 0], boxes[:, 1], boxes[:, 2], boxes[:, 3]
    areas = (x2 - x1).clip(min=0) * (y2 - y1).clip(min=0)
    order = scores.argsort()[::-1]
    keep: list[int] = []
    while order.size > 0:
        i = int(order[0])
        keep.append(i)
        if order.size == 1:
            break
        rest = order[1:]
        xx1 = np.maximum(x1[i], x1[rest])
        yy1 = np.maximum(y1[i], y1[rest])
        xx2 = np.minimum(x2[i], x2[rest])
        yy2 = np.minimum(y2[i], y2[rest])
        inter = (xx2 - xx1).clip(min=0) * (yy2 - yy1).clip(min=0)
        iou = inter / (areas[i] + areas[rest] - inter + 1e-9)
        order = rest[iou <= iou_thr]
    return keep


def decode(output: np.ndarray, names: list[str], conf: float, iou: float,
           ratio: float, pad_x: float, pad_y: float,
           orig_w: int, orig_h: int) -> list[tuple]:
    """Decode a raw YOLOv8 ONNX output into (x1,y1,x2,y2,label,conf) tuples.

    Pure numpy (no onnxruntime/torch/cv2), so it is unit-testable with a
    synthetic tensor. Accepts output shaped (1, 4+nc, N) or (1, N, 4+nc).
    """
    preds = output[0] if output.ndim == 3 else output
    # Orient to (N, 4+nc): YOLOv8 exports (4+nc, N) with 4+nc < N.
    if preds.shape[0] < preds.shape[1]:
        preds = preds.T
    if preds.shape[1] < 5:
        return []
    xywh = preds[:, :4]
    cls_scores = preds[:, 4:]
    cls_ids = cls_scores.argmax(axis=1)
    confs = cls_scores.max(axis=1)
    keep = confs >= conf
    if not np.any(keep):
        return []
    xywh, cls_ids, confs = xywh[keep], cls_ids[keep], confs[keep]
    # xywh (centre) → xyxy in letterboxed space, then undo the letterbox.
    cx, cy, w, h = xywh[:, 0], xywh[:, 1], xywh[:, 2], xywh[:, 3]
    x1 = (cx - w / 2 - pad_x) / ratio
    y1 = (cy - h / 2 - pad_y) / ratio
    x2 = (cx + w / 2 - pad_x) / ratio
    y2 = (cy + h / 2 - pad_y) / ratio
    x1 = x1.clip(0, orig_w)
    x2 = x2.clip(0, orig_w)
    y1 = y1.clip(0, orig_h)
    y2 = y2.clip(0, orig_h)
    boxes = np.stack([x1, y1, x2, y2], axis=1)
    # Per-class NMS (offset-free; just group by class id).
    out: list[tuple] = []
    for c in np.unique(cls_ids):
        m = cls_ids == c
        cb, cs = boxes[m], confs[m]
        for idx in _nms(cb, cs, iou):
            bx = cb[idx]
            label = names[int(c)] if int(c) < len(names) else str(int(c))
            out.append((int(bx[0]), int(bx[1]), int(bx[2]), int(bx[3]),
                        label, float(cs[idx])))
    return out


class OnnxYolo:
    """Minimal YOLOv8 ONNX runner (onnxruntime CPU). Mirrors the box format the
    ultralytics path produces so ``vision_overlay`` is backend-agnostic."""

    def __init__(self, model_path: str, names: list[str] | None = None,
                 conf: float = 0.40, iou: float = 0.45,
                 num_threads: int | None = None) -> None:
        self.model_path = model_path
        self.num_threads = num_threads
        self.names = _load_names(model_path, names)
        self.conf = float(conf)
        self.iou = float(iou)
        self.session = None
        self.input_name = "images"
        self.imgsz = 320
        if not os.path.exists(model_path):
            logger.warning("ONNX model not found: %s", model_path)
            return
        try:
            import onnxruntime as ort  # heavy/optional — deferred
        except ImportError as e:
            logger.warning("onnxruntime not installed — ONNX detector off (%s)", e)
            return
        try:
            from .ort_utils import ort_providers, ort_session_options
            self.session = ort.InferenceSession(
                model_path, sess_options=ort_session_options(ort, num_threads),
                providers=ort_providers(ort))
            inp = self.session.get_inputs()[0]
            self.input_name = inp.name
            # input shape is [1, 3, H, W]; H may be a string if dynamic.
            dims = inp.shape
            if len(dims) == 4 and isinstance(dims[2], int):
                self.imgsz = int(dims[2])
            logger.info("ONNX detector loaded: %s (imgsz=%d, %d classes)",
                        os.path.basename(model_path), self.imgsz, len(self.names))
        except Exception as e:  # noqa: BLE001 — degrade, never crash startup
            logger.warning("onnxruntime session load failed (%s): %s", model_path, e)
            self.session = None

    @property
    def available(self) -> bool:
        return self.session is not None

    def infer(self, frame_bgr, conf: float | None = None) -> list[tuple]:
        """Run detection on a BGR frame → [(x1,y1,x2,y2,label,conf), ...]."""
        if self.session is None:
            return []
        try:
            import cv2
            h, w = frame_bgr.shape[:2]
            canvas, ratio, pad_x, pad_y = letterbox(frame_bgr, self.imgsz)
            # blobFromImage does BGR→RGB (swapRB), /255 scale, and HWC→NCHW in
            # one C++ call — no intermediate float copies or numpy transpose.
            # canvas is already imgsz², so size is a no-op (no distortion).
            blob = cv2.dnn.blobFromImage(
                canvas, scalefactor=1.0 / 255.0,
                size=(self.imgsz, self.imgsz), swapRB=True, crop=False)
            out = self.session.run(None, {self.input_name: blob})[0]
            return decode(np.asarray(out), self.names,
                          conf if conf is not None else self.conf, self.iou,
                          ratio, pad_x, pad_y, w, h)
        except Exception as e:  # noqa: BLE001 — a bad frame must not kill the loop
            logger.error("ONNX inference error: %s", e)
            return []
