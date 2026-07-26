"""Shared onnxruntime tuning for CPU inference on the Raspberry Pi 5.

The Pi 5 is a 4-core Cortex-A76 with no discrete GPU, so every ONNX model in the
vision stack (the YOLO detector and the water-segmentation net) runs on the CPU
execution provider. Two knobs matter there and onnxruntime does **not** pick good
defaults for a small edge box:

* **Graph optimisation** — ``ORT_ENABLE_ALL`` fuses ops and folds constants,
  which is a free single-digit-percent speed-up and lower memory.
* **Thread count** — pinning ``intra_op_num_threads`` to the core count keeps all
  four A76 cores busy on the single inference instead of onnxruntime's
  conservative default, roughly halving latency for a YOLOv8n forward pass.

Both are wrapped here so the detector and the segmenter share one tuned config.
Everything is best-effort: if a knob isn't supported it's skipped, never fatal.

For a further ~2-3× over tuned ONNX-CPU, export the model to **NCNN**
(``yolo export format=ncnn`` — Ultralytics' recommended Pi backend) or offload to
a **Hailo-8L** on the Pi 5 AI HAT+ (real-time 30 fps+). See ``docs/vision_optimization.md``.
"""
from __future__ import annotations

import os


def _cpu_threads() -> int:
    """Physical core count to hand onnxruntime (Pi 5 = 4). Clamped to [1, 8]."""
    n = os.cpu_count() or 4
    return max(1, min(8, int(n)))


def ort_session_options(ort):
    """Tuned ``SessionOptions`` for CPU inference on the Pi 5."""
    opts = ort.SessionOptions()
    try:
        opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    except Exception:  # noqa: BLE001 — older onnxruntime may lack the enum
        pass
    try:
        opts.intra_op_num_threads = _cpu_threads()
        opts.inter_op_num_threads = 1
        opts.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
    except Exception:  # noqa: BLE001
        pass
    return opts


def ort_providers(ort) -> list:
    """Preferred CPU-side execution providers, best available first.

    XNNPACK (ARM-optimised kernels) is used when the installed onnxruntime build
    ships it, else the plain CPU provider — both are pure-CPU, so this never
    silently needs a GPU/accelerator.
    """
    available = set(ort.get_available_providers())
    providers: list = []
    if "XnnpackExecutionProvider" in available:
        providers.append("XnnpackExecutionProvider")
    providers.append("CPUExecutionProvider")
    return providers
