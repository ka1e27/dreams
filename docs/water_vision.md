# Water-based vision — Tier-1 segmentation options

Tier 1 of the survey vision pipeline (`pi5/cv/segmentation.py`) is the cheap,
always-on "is this open water or something worth waking YOLO for?" screen. It
returns an **anomaly score** (fraction of the frame that isn't open water), a
coarse `WaterState`, and anomalous regions. This doc covers the backend choices
and how to drop a real maritime water-segmentation model in.

## The three backends

`WaterSegmentation` auto-selects a backend from `vision.seg_model_path`'s
extension. All three produce an identical `SegResult`, so the rest of the
pipeline (`pipeline.py`, the dashboard, the radar) is backend-agnostic.

| Backend | Trigger | Deps | Pi 5 CPU speed | Notes |
|---|---|---|---|---|
| **classical** | no model file | none (cv2/numpy) | **≫ 15 fps** (~2–5 ms/frame) | HSV water band + Canny edges. Robust enough as a screen; struggles in strong glare/haze. **This is what hits the 15 fps target on a CPU-only Pi.** |
| **onnx** | `*.onnx` | `onnxruntime` (already a dep) | ~2–8 fps at 384×512 | A real semantic-seg net (water/obstacle/sky). Much better in glare/haze/reflections. Too slow for 15 fps on the CPU alone — use when accuracy matters, drop `tier1_max_fps`, or add an accelerator. |
| **tflite** | `*.tflite` | `tflite_runtime`/`tensorflow` | model-dependent | Same idea for a TFLite export. |

**Recommendation:** run the **hybrid** (below) — keep the classical screen as the
15 fps always-on tier and add eWaSR as a slow confirmation pass. The tiering
architecture already assumes the cheap screen gates the expensive work, so you
don't need a DNN running at 15 fps.

## Hybrid mode (recommended) — classical screen + eWaSR spot-check

This keeps the guaranteed 15 fps CPU screen *and* gets eWaSR's accuracy, without
either blocking the other:

- **Tier-1 (primary, `seg_model_path` empty):** the classical HSV screen runs on
  every frame at `tier1_max_fps` (15) and drives the real-time YOLO gate. Fast,
  responsive, never stalls.
- **Tier-1b (confirmation, `seg_confirm_model_path`):** eWaSR runs on a **separate
  slow loop** (`seg_confirm_max_fps`, ~1–2 Hz) in a worker thread, so its ~200 ms
  inference never touches the 15 fps loop. Its verdict is published into the
  pipeline and used two ways:
  1. It becomes the **authoritative `water_state`** shown on the dashboard (eWaSR
     classifies water/obstacle/algae far better than HSV).
  2. It can **wake YOLO on an obstacle the HSV screen missed** — but **only ever
     *adds* a trigger, never suppresses one** (fail-safe: a survey boat should
     over-wake rather than miss a hazard). A verdict older than `seg_confirm_ttl_s`
     is ignored.

Config:

```yaml
vision:
  seg_model_path: ""                                  # classical primary (15 fps)
  seg_confirm_model_path: "pi5/cv/models/water_seg.onnx"  # eWaSR spot-check
  seg_confirm_max_fps: 2
  seg_confirm_ttl_s: 3
  seg_water_class: 1        # eWaSR: 0=obstacle, 1=water, 2=sky
  seg_ignore_classes: [2]   # drop sky from the anomaly ratio
  seg_normalize: "imagenet"
```

With no model file at `seg_confirm_model_path`, the hybrid is simply off and you
get the pure classical screen — nothing else to change. On a Pi 5 CPU the eWaSR
pass sits around 2–8 fps, which is fine at the 1–2 Hz spot-check cadence; a Hailo
accelerator (ONNX-native) would let you raise it.

### Why not a Coral Edge TPU for this?
Coral runs only INT8 TFLite compiled for the Edge TPU (not ONNX), can't execute
eWaSR's transformer/refinement ops (they'd fall back to CPU), has no official Pi 5
support, and its `pycoral` runtime is stuck on Python 3.6–3.9 (this project is on
3.14). The **Hailo AI HAT+** is the right accelerator for the Pi 5 — first-party
support, ingests ONNX directly, and would accelerate both eWaSR *and* the YOLO
detector.

## Recommended library / models

The maritime CV community's standard for water/obstacle segmentation is the
**WaSR family** (Water Segmentation and Refinement), benchmarked on MaSTr1325 /
MODS and the MaCVi workshop challenges:

- **eWaSR** — *embedded-compute-ready* WaSR. ~10× less inference time than WaSR
  with comparable accuracy; designed specifically for real-time use on embedded
  hardware and **exportable to ONNX with no custom ops**. This is the best fit
  for the boat. Repo: <https://github.com/tersekmatija/ewasr>
  (paper: <https://pmc.ncbi.nlm.nih.gov/articles/PMC10303570/>).
- **WaSR** — the original/reference PyTorch model, higher accuracy but heavier.
  Repo: <https://github.com/lojzezust/WaSR>
- Any lightweight 2–3 class water segmentation net (MobileNetV3 / FastSCNN
  backbone) exported to ONNX also works — the loader only assumes an NCHW input
  and a class-map (or water-probability) output.

Output convention assumed by default: **3 classes, `0=obstacle, 1=water, 2=sky`**
(`seg_water_class: 1`, `seg_ignore_classes: [2]` so sky doesn't inflate the
anomaly score). A binary water-probability output (`(1,1,H,W)` or `(1,H,W)`,
values in `[0,1]`) is also handled — water = prob ≥ 0.5.

## Wiring an ONNX model in

1. Export eWaSR to the exact ONNX this backend expects with the helper script —
   run it on a GPU box / laptop with the [eWaSR repo](https://github.com/tersekmatija/eWaSR)
   cloned and its deps installed:

   ```bash
   git clone https://github.com/tersekmatija/eWaSR
   pip install torch onnx onnxsim onnxruntime opencv-python
   # download ewasr_resnet18.pth from the 0.1.0 release (non-IMU variant):
   #   https://github.com/tersekmatija/eWaSR/releases/tag/0.1.0
   python ml/export_ewasr.py --ewasr-repo ./eWaSR \
       --weights ./eWaSR/pretrained/ewasr_resnet18.pth --self-check
   ```

   It writes `pi5/cv/models/water_seg.onnx` (+ a tracked `water_seg_info.json`
   model card), forces the single-input `ewasr_resnet18` variant, uses the
   `1×3×384×512` static shape and ImageNet normalisation this backend matches,
   and `--self-check` confirms the class order (water should dominate a water
   frame). For a non-eWaSR model, export any 2–3 class seg net to ONNX with a
   **static input shape** instead.
2. Copy it to the Pi: `scp pi5/cv/models/water_seg.onnx <pi>:~/D.R.E.A.M.S/pi5/cv/models/`.
   The `.onnx`/`.pt` weights are gitignored; the `_info.json` card is tracked.
   *(To instead **replace** the fast screen entirely rather than run the hybrid,
   put the path in `seg_model_path` — not recommended on a CPU-only Pi.)*
3. Set the class knobs in `pi5/config.yaml → vision:` if your model differs from
   the WaSR convention (see the Hybrid mode block above for the full set):

   ```yaml
   vision:
     seg_confirm_model_path: "pi5/cv/models/water_seg.onnx"
     seg_water_class: 1        # output index that means "water"
     seg_ignore_classes: [2]   # e.g. sky — excluded from the anomaly ratio
     seg_normalize: "imagenet" # or "01" for plain /255 models
     # seg_input_size: [512, 384]  # only if the model exports dynamic axes
   ```

4. Restart. Startup logs `Water segmentation ONNX model loaded: … (WxH, water_class=…)`
   and `pipeline started (seg=classical, confirm=onnx, …)`. If the file/runtime is
   missing or the graph fails, it logs one warning and the hybrid stays off — the
   classical screen always runs.

## Verifying speed

Run the benchmark on the **Pi 5** (laptop numbers don't represent the target):

```bash
python -m pi5.scripts.benchmark_vision
```

It reports Tier-1 FPS per backend, YOLO detect FPS, and the stereo-depth cost, so
you can confirm the 15 fps water screen + high-but-lower detect rate on the real
hardware and pick `imgsz` / `tier1_max_fps` / `stereo_downscale` accordingly.
