# Vision system optimization — Pi 5

How to get the most out of the survey vision stack on the Raspberry Pi 5 (4× Cortex‑A76,
no discrete GPU). Covers detection throughput, stereo depth quality on water, water
segmentation, and the threading model. Companion to `docs/water_vision.md` (model sourcing)
and `docs/navigation_guidance.md` (how threats become avoidance).

The Pi 5 is **inference‑bound**, not IO‑bound — the single scarcest resource is CPU time for
YOLO + StereoSGBM. Every recommendation here is about spending that budget well.

---

## 1. YOLO detection throughput

The overlay (`pi5/cv/vision_overlay.py`) runs one detector, backend chosen by model path:
ONNX Runtime for a `.onnx`, else Ultralytics for a `.pt`. Ranked best → simplest on the Pi 5:

| Backend | Setup | YOLOv8n @ 320² (rough Pi 5 CPU) | Notes |
|---|---|---|---|
| **Hailo‑8L** (AI HAT+, 13 TOPS) | HailoRT + `.hef` export | **30+ fps** | Real‑time; frees the CPU entirely. Best option if you can add the HAT. |
| **NCNN** (ARM‑optimised) | `yolo export format=ncnn`, point `camera.detection.model` at the `_ncnn_model` dir | ~2–3× tuned ONNX‑CPU | Ultralytics' recommended Pi backend. FP16; INT8 not well supported. |
| **ONNX Runtime (INT8)** | quantize the `.onnx` (static/dynamic) | ~**13 fps**, ~77 ms | Best pure‑CPU‑Python path; ~30 % pruning + INT8 published on Pi 5. |
| **ONNX Runtime (FP32, tuned)** | `pi5/cv/ort_utils.py` (already wired) | ~6–10 fps | Graph opt = ALL, `intra_op_num_threads` = 4, XNNPACK if present. |
| Ultralytics `.pt` (torch) | default `yolov8n.pt` | ~2–5 fps | Heaviest; fine for a demo, replace for missions. |

**What's already done in code**

- `ort_utils.ort_session_options()` sets `ORT_ENABLE_ALL` graph optimization and pins
  `intra_op_num_threads` to the core count — used by both the detector and the segmenter.
- `ort_utils.ort_providers()` prefers `XnnpackExecutionProvider` when the installed
  onnxruntime build ships it.
- `imgsz` defaults to **320** — the sweet spot. It is the real FPS lever (cost ∝ imgsz²);
  `detect_max_fps` is only an upper cap. 416/640 see smaller/farther targets at
  proportional cost. Adjustable live from the command center (IMG selector).
- Detection is **gated** by the Tier‑1 water screen (`gate_yolo_on_anomaly`) so YOLO idles
  over open water and only wakes on an anomaly — the biggest single CPU saving underway.

**Do next, in order of payoff**

1. Add the **Hailo‑8L AI HAT+** if the mission needs reliable ≥15 fps detection. Everything
   else is squeezing a CPU that a $70 accelerator makes moot.
2. Otherwise **export to NCNN** and point the config at it — no code change (Ultralytics
   infers the format from the path).
3. If staying on ONNX‑CPU, **quantize to INT8** (see `ml/export_onnx.py`); ~2× throughput.
4. Keep `imgsz` at 320 unless you have FPS headroom; drop to 256 to buy frames.

Sources: [Ultralytics Raspberry Pi guide](https://docs.ultralytics.com/guides/raspberry-pi/),
[Quantized YOLOv8/11 on Pi 5 (13 fps INT8)](https://www.researchgate.net/publication/399780145),
[YOLO on Pi 5 CPU comparison](https://medium.com/@fsimsek/real-time-object-detection-on-raspberry-pi-5-yolov11-vs-yolov8-under-cpu-only-constraints-ee912d65a0c2).

---

## 2. Stereo depth on water

Water is the **worst case** for block matching: textureless, specular, semi‑transparent, and
full of moving reflections. Raw StereoSGBM leaves large invalid holes on the surface and
noisy blobs from glints.

**What's already done (`pi5/cv/stereo.py`)**

- **Downscale** (`camera.stereo_downscale`, default 0.5): SGBM cost ≈ O(W·H·numDisparities),
  so half‑res is ~4× cheaper; depth stays metric because `Q` and the disparity range are
  rescaled exactly. Mid‑range (3–30 m) accuracy is essentially unchanged.
- **3‑way mode** (`STEREO_SGBM_MODE_SGBM_3WAY`): markedly faster than full `HH` on the Pi 5
  CPU at a small quality cost — the right trade for a real‑time boat.
- **`preFilterCap = 63`**: tames specular glints off the water before matching.
- **Optional WLS post‑filter** (`camera.stereo_wls`, needs `opencv-contrib-python`): runs a
  second (right) matcher and a left↔right consistency check to **fill and smooth the
  textureless holes** — exactly the failure mode on water. ~2× matching cost, so it's off by
  default; enable it on a rig with FPS headroom (or drop `stereo_downscale` / stereo FPS to
  pay for it). Degrades gracefully to a warning if `cv2.ximgproc` is missing.

**Tuning knobs if depth is still noisy**

- Raise `uniquenessRatio` (10 → 15) to reject ambiguous water matches.
- Raise `speckleWindowSize` / lower `speckleRange` to kill glint speckle.
- Depth is only trusted 3–30 m here; beyond that a 120 mm baseline gives too little
  disparity — lean on detection bbox size + the monocular fallback instead.

**Don't over‑rely on stereo for the horizon.** For open‑water hazard ranging, detection +
segmentation (below) are more reliable than SGBM on the water surface itself. Reserve stereo
for ranging *solid objects* (vessels, buoys, docks) that have texture.

Sources: [OpenCV disparity WLS post‑filtering tutorial](https://docs.opencv.org/3.4/d3/d14/tutorial_ximgproc_disparity_filtering.html),
[ximgproc `createDisparityWLSFilter`](https://github.com/opencv/opencv_contrib/blob/master/modules/ximgproc/tutorials/disparity_filtering.markdown).

---

## 3. Water / obstacle segmentation (Tier 1)

The always‑on Tier‑1 screen (`pi5/cv/segmentation.py`) decides whether the expensive tiers
are worth waking. The classical HSV/edge backend is the only one that sustains 15 fps on the
Pi 5 CPU; it is deliberately a *cheap screen*, not a classifier.

For accuracy in glare/haze, drop in a **maritime segmentation DNN** as the hybrid confirmer
(`vision.seg_confirm_model_path`) — it runs on a separate slow loop (~1–2 Hz) so it never
stalls the fast screen, and only ever *adds* triggers (fail‑safe). Recommended families,
all water/obstacle/sky segmenters trained on maritime data:

- **WaSR / eWaSR** — the reference USV obstacle segmenters, trained on **MaSTr1325** and
  benchmarked on **MODS**. eWaSR is the efficient variant meant for edge inference. Export to
  ONNX and set `seg_water_class = 1`, `seg_ignore_classes = [2]` (0=obstacle, 1=water, 2=sky).
- Any 2–3 class water‑segmentation net exported to ONNX/TFLite works — the reducer in
  `WaterSegmentation._seg_mask` handles logits, label maps, and single‑probability outputs.

On a Hailo/Coral accelerator you can promote a DNN segmenter to the *primary* Tier‑1 screen
and raise `tier1_max_fps`.

Datasets/models: MaSTr1325, MODS, USVInland, WaSR/eWaSR (see `docs/water_vision.md`).

---

## 4. Threading & latency

The architecture already keeps CPU‑bound work off the asyncio event loop — preserve this:

- One `CameraProducer` owns both `VideoCapture` handles; every consumer (video stream, YOLO
  overlay, Tier‑1 pipeline, DNN confirmer) attaches a **bounded (maxsize=2) queue** and the
  producer drops the oldest frame when a consumer lags. No consumer can back‑pressure capture.
- `cap.read()`, YOLO inference, SGBM, and JPEG encode all run in the default thread‑pool
  executor (`run_in_executor`) — cv2/onnxruntime release the GIL, so capture, inference and
  encode overlap instead of serializing.
- Each stage has an **independent rate cap** (`detect_max_fps`, `tier1_max_fps`, `stream_fps`)
  so a slow stage never throttles a fast one, and frames are dropped, not queued.

Rules of thumb: never call a blocking cv2/ORT op directly in an async handler; keep queues
bounded and drop‑oldest; and cap each stage so the sum of inference budgets fits the frame
period you actually need for control (avoidance runs fine at 4–8 Hz).
