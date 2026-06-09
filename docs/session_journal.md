# D.R.E.A.M.S — Session Journal

A running log of what each Claude Code session worked on. **Read this top-to-bottom at the start
of every session** to understand recent work, then **append a new entry at the end of the session**
describing what you did.

- Newest entries go at the **top** (just under this header), so the most recent context is read first.
- Keep entries short and factual — what changed and why, not a transcript.
- This is a *narrative* of work-in-progress. For locked decisions and the architecture-of-record,
  see `docs/changelog_and_decisions.md`; for hardware deltas, `docs/hardware_changes_v1_to_v2.md`.
  Don't duplicate those here — link to them.

### Entry template (copy this)

```
## YYYY-MM-DD — <short title>

**Worked on:** one or two sentences on the goal.
**Changed:**
- `path/to/file` — what and why
**Decisions / open questions:** anything left unresolved or flagged for next time.
**Next steps:** what a future session should pick up.
```

---

<!-- New entries below this line, newest first. -->

## 2026-06-08 — IMX219 "~16 fps at 1080p": diagnosed (camera mode) + unblocked the event loop

**Reported:** the Arducam 8MP IMX219 streams ~16 fps; user expects a reliable 30 fps at 1080p.
**Diagnosis (two stacked causes, ranked):**
1. **Most likely root cause — the camera is *delivering* ~15 fps; the 30 fps request is ignored.**
   `cap.set(CAP_PROP_FPS, 30)` is only a request. USB camera modules commonly advertise **1080p MJPG
   @ 15 fps / 720p @ 30 fps** — the IMX219 *sensor* does 1080p30 but the module's UVC bridge often
   doesn't. 16 fps ≈ a 15-fps mode (× the streamer's 0.9 timing tolerance). Alt: at 1080p OpenCV may
   fall back to **YUYV** and ~1 Gbit/s of raw 1080p30 won't fit USB 2.0. `camera.py` already logs the
   negotiated `WxH @ fps` + WARNINGs on this — that startup line is the smoking gun. Confirm with
   `v4l2-ctl -d /dev/video0 --list-formats-ext`; if 1080p MJPG lists only 15 fps it's a hardware
   ceiling → use **1280×720 @ 30** or **1640×1232 @ 30** (binned, near-full FOV). Also: committed
   `config.yaml` is still **640×480** — 1080p needs `camera.width/height` bumped first.
2. **Real software bottleneck (fixed this session) — capture + JPEG encode both blocked the single
   asyncio event loop**, so they serialized instead of overlapping; at 1080p (~10–25 ms each) the
   *published* stream sagged below the *capture* rate even when the camera could deliver more.
**Changed:**
- `pi5/cv/camera.py` — `_loop()` now runs `cap.read()` (grab + MJPEG→BGR decode) via
  `loop.run_in_executor(None, cap.read)` for both L/R, so a 1080p decode no longer freezes the loop.
- `pi5/server/app.py` — `_mjpeg_stream()` runs `cv2.imencode()` via `run_in_executor` (captures
  `img`/`quality` as default args to avoid late-binding). cv2 releases the GIL in read()/imencode(),
  so both genuinely parallelize now. (YOLO inference was already offloaded — `vision_overlay.py:236`.)
**Verified (sim/Windows):** ruff clean on `pi5 run_hardware.py`; py_compile OK; **95 tests pass**;
booted `run_sim` — `/health`, `/command`, `/video` all 200. The offload's real effect is Pi-only (the
sim has no camera, so `_mjpeg_stream` takes the placeholder branch and never hits the edited line).
**Next steps:** uncommitted (offer). On the Pi: read the camera startup log line (or run `v4l2-ctl
--list-formats-ext`) to see what the module actually negotiates at 1080p. If it's 15 fps MJPG, drop to
720p30 / 1640×1232. The executor offload removes the software ceiling so the stream can match whatever
the camera delivers — it does **not** override a 15-fps camera mode.

## 2026-06-08 — "stepper_test.py prints PASS but motor doesn't move": honest verdict + A4988 RESET

**Worked on:** user reported `pi5/cv/stepper_test.py` prints PASS on every check but the A4988-driven
NEMA-17 (1/16 microstep) doesn't physically move. Diagnosed the misleading PASS and applied both fixes.
**Root cause of the misleading PASS:** the test validates *software bookkeeping*, not motion. Every
"rotate" check reads `get_position_degrees()`, derived from `self._position_steps`, which `step()`
increments **unconditionally** (`stepper.py`) regardless of whether any pin toggles — and the pin writes
go through `_w()`, a silent no-op when the device is `None` (mock mode). So PASS proves the math, not the
motor. A disconnected/dead driver, a wiring fault, or full mock mode all still printed "9 passed".
**The two real causes (the printed `mock=` line decides which):** (a) `mock=True` → no GPIO touched;
`gpiozero`/`lgpio` not importable (neither is in `pi5/requirements.txt`) — install them. (b) `mock=False`
→ electrical; most likely the **A4988 RESET pin floating** (RESET *and* SLEEP are both active-LOW and both
must be HIGH to step; the driver drove SLEEP but never RESET), then VMOT/VREF/coil wiring.
**Changed:**
- `pi5/cv/stepper_test.py` — final verdict is now honest: on `mock=True`+Linux it prints "NOT VERIFIED ON
  HARDWARE" + the lgpio/gpiozero install fix and **returns 2** (mock on a Pi = broken, not a dry run);
  off-Pi mock stays a pass (documented dry run); on real GPIO it prints a "watch the bar" note up front
  and, if it didn't move, the RESET→VMOT→VREF→coil checklist. PASS can no longer be mistaken for motion.
- `pi5/cv/stepper.py` — added optional `reset_pin` (default `None`). When set, the driver claims it and
  holds RESET **HIGH** (released) in `enable()` + at init, and frees it in `cleanup()`. Module docstring
  now documents the RESET-must-be-HIGH gotcha and the two wiring options (jumper RESET↔SLEEP, or dedicate
  a Pi GPIO). `None` = RESET jumpered to SLEEP on the board (recommended, no extra pin).
- `run_hardware.py` — passes `reset_pin=step_cfg.get("reset_pin", None)`.
- `pi5/config.yaml` — new `stepper.reset_pin: null` with the must-be-HIGH explanation.
- `docs/pin_map.md` — added the RESET row to the A4988 table + a prominent RESET/VMOT/VREF caveat.
**Verified (Windows):** ruff clean; py_compile OK; **95 tests pass**; bench test 9/9 mock and the new
verdict prints the off-Pi dry-run message + exits 0 (would exit 2 on a Pi in mock mode).
**Next steps:** on the Pi, re-run `python3 pi5/cv/stepper_test.py` and read the verdict — if it says
mock-on-a-Pi, install lgpio/gpiozero; if real GPIO and still no motion, jumper A4988 RESET→SLEEP (or set
`stepper.reset_pin`) and check VMOT/VREF. Uncommitted (offer).

## 2026-06-08 — IMX219 camera stuck at 5 fps (force V4L2) + detection boxes on BOTH views

**Worked on:** two requests for the Arducam 8MP **Sony IMX219** fixed-focus camera — (1) it runs at
only ~5 fps, (2) draw the YOLO detection boxes on the **right** camera view as well as the left.
**FPS diagnosis (5 fps = full 8MP):** the IMX219 is a raw sensor (no onboard JPEG); its native mode is
3280×2464, which over USB is ~5 fps. The symptom = the camera ignored our 640×480/MJPG `cap.set()` and
stayed in full-res. Root cause: OpenCV's **default capture backend** often won't apply the FOURCC +
resolution switch, so the mode never changes.
**Changed:**
- `pi5/cv/camera.py` — `_open()` now forces the **V4L2 backend on Linux** (`cv2.VideoCapture(dev,
  cv2.CAP_V4L2)`) so the MJPG + 640×480 set actually takes and the sensor drops to its fast binned mode;
  non-Linux (sim/dev) keeps the default backend. Reads back negotiated **WxH + fps** and logs a loud
  **WARNING** when fps is well below requested or the resolution differs (points the user at
  `v4l2-ctl --list-formats-ext`). Added `import sys`.
- `pi5/config.yaml` — documented the IMX219 modes in the `camera:` block (native 8MP ≈ 5 fps; fast
  binned 640×480 / 1280×720 @ 30+ / 1640×1232 @ 30) + the V4L2-backend note and the v4l2-ctl check.
- `pi5/server/app.py` — `_mjpeg_stream()` now draws the overlay boxes + reticle on **whichever view is
  shown (left AND right)**, not left-only. No second inference (the Pi is inference-bound) — the
  left-frame boxes are drawn on the right view at the same coords, offset by the stereo disparity.
  Updated the `_mjpeg_stream`/`/video` docstrings.
- `pi5/server/templates/command_center.html` — the ◎ TRACKING badge now shows on both views (was
  gated to `camView === 'left'`), matching the reticle that's now drawn on both.
**Verified (sim/Windows):** ruff clean on `pi5 run_hardware.py`; py_compile OK; **95 tests pass**;
booted `run_sim` — `/health`, `/command`, and `/video?cam=right` all 200; camera module imports.
**UNTESTED (Pi-only):** the V4L2 fps fix needs the real IMX219 — on the Pi, confirm the camera log line
shows the requested mode (e.g. `640x480 @ 30 fps`) instead of `3280x2464 @ 5`; if it still warns, run
`v4l2-ctl -d /dev/video0 --list-formats-ext` and set `camera.width/height/fps` to a listed MJPG mode.
Boxes on the right view are also Pi-only (sim has no camera); right-view boxes carry the stereo offset.
**Next steps:** uncommitted (offer). Bench-verify on the Pi.

## 2026-06-08 — Move Pico terminal to page bottom + choose which CV target to track

**Worked on:** two command-center requests — (1) move the PICO TERMINAL panel to the bottom of the
page, (2) add a way to choose which detected class the computer vision locks onto.
**Layout (1):** reordered the `.app` grid so the terminal is the last panel (header → camera/health →
boat health → radar → commands → **pico terminal**); `grid-template-rows` is now
`auto 1fr auto auto auto 1fr` — the terminal keeps its `1fr` so it still scrolls internally (the prior
scroll fix is intact). Moved the panel markup; the `@media` stack rule still covers `.pico-inner`.
**Target picker (2) — one control drives BOTH the overlay reticle and the radar bar:**
- `pi5/cv/vision_overlay.py` — `DetectionConfig.track_class` ("" = AUTO). `_infer()` now locks the
  primary target onto the chosen class (and highlights it amber) when set, else keeps the old behavior
  (highest-conf highlight class). `controls()` exposes `track_class` + `classes` (model labels for the
  picker); `apply_controls()` accepts `track_class` (treats ""/"AUTO" as auto). New `class_names()`.
- `pi5/cv/radar_tracker.py` — `set_track_class(label)` (thread-safe); `_best_target()` filters to the
  chosen class when set, else `priority_classes`; `status()` reports `track_class`.
- `pi5/server/app.py` — `POST /api/camera` also calls `_radar.set_track_class()` when `track_class` is
  in the payload, so picking a class retargets the bar too (guarded; never 500s). `_camera_state()`
  already merges `controls()`, so the picker fields flow to the UI.
- `pi5/server/templates/command_center.html` — TRACK `<select>` in the camera control bar (next to
  DETECT); `populateTrackClasses()` fills it from `controls().classes` (falls back to a maritime+COCO
  seed so it's usable in sim/before a model loads), preserves selection; change handler POSTs
  `track_class` + toasts.
- `run_hardware.py` + `pi5/config.yaml` — plumb/document a default `camera.detection.track_class: ""`.
**Verified (sim/Windows):** ruff clean on `pi5 run_hardware.py`; py_compile OK; **95 tests pass**;
functional check — overlay picks person under AUTO, switches to boat / buoy when chosen (and highlights
it), reverts on AUTO; radar `_best_target` follows the chosen class and `status.track_class` updates.
Booted `run_sim`: `/command` serves the TRACK picker + `populateTrackClasses` and the terminal panel is
last; `POST /api/camera {track_class:boat}` returns 200 (sim has no overlay/radar, so it's a graceful
no-op). **Real lock-on/bar-slew behavior is Pi-only (camera + YOLO + stepper) and UNTESTED on hardware.**
**Next steps:** uncommitted (offer). On the Pi: with a model + a target in frame, confirm the TRACK
picker changes the cyan reticle/◎TRACKING badge to the chosen class and that the radar bar slews to it.

## 2026-06-08 — Maritime YOLOv8 fine-tuning pipeline (ml/) + ONNX inference backend on the Pi

**Worked on:** implemented `~/Downloads/DREAMS_maritime_ml_instruction.md` — a laptop/Colab pipeline
that trains a 6-class maritime YOLOv8n (vessel/kayak/buoy/person/dock/debris), exports ONNX, and an
onnxruntime inference path on the Pi.
**Two deliberate divergences (instruction written against a simplified repo model; flagged, not applied
verbatim):**
- The instruction says *modify `pi5/cv/camera.py`* to use the model — but `camera.py` is purely the
  capture producer; detection lives in **`pi5/cv/vision_overlay.py`**. Integrated there; left camera.py
  alone (also respects the "server untouched" spirit).
- "*Use onnxruntime instead of ultralytics*" — added a real native onnxruntime backend
  (`pi5/cv/onnx_detector.py`: letterbox + pure-numpy decode + per-class NMS) used for `.onnx` models,
  with the existing **ultralytics path kept as the `.pt` fallback**. Honors the lightweight-Pi intent
  (no torch needed for the maritime model) without rewriting the proven box/track pipeline.
**New (ml/ — runs on laptop/Colab, NOT the Pi):** `ml/README.md`, `ml/data/download_datasets.py`
(Roboflow SDK + SMD/SeaShips staging + per-source class remap→6 std ids), `ml/data/prepare_dataset.py`
(merge/remap/dedup-by-hash/drop-empty/split 70-20-10/oversample/stats+chart/dataset.yaml),
`ml/data/augment.py` (Albumentations maritime aug: glare/fog/colour/noise/hflip/±15°; never vflip),
`ml/train.py` (freeze-10 transfer-learn from COCO), `ml/validate.py` (test mAP + CPU-FPS benchmark +
threshold pass/fail), `ml/export_onnx.py` (best.pt→onnx imgsz320 simplify opset12, writes model card +
onnxruntime benchmark), `ml/colab_train.ipynb`.
**New (Pi):** `pi5/cv/onnx_detector.py` (OnnxYolo + standalone `decode()`); `pi5/cv/models/
maritime_yolov8n_info.json` (tracked placeholder card; .onnx itself gitignored).
**Changed:**
- `pi5/cv/vision_overlay.py` — backend selection: auto-prefer `pi5/cv/models/maritime_yolov8n.onnx`
  when present (else configured `.pt`); `_raw_detect()` is backend-agnostic and `_infer()` does the
  shared highlight/target/primary logic; `controls()` reports `backend`; logs the model on load;
  graceful fallback to yolov8n.pt if the .onnx can't load.
- `pi5/requirements.txt` — `onnxruntime>=1.17`. `.gitignore` — ml data/runs/samples + `*.onnx`/`*.pt`
  weights (keep `*_info.json`). `pi5/config.yaml` — `highlight_classes`/`priority_classes` now cover
  both COCO ('boat','person') and maritime ('vessel','kayak') so either model highlights/tracks right;
  documented the auto-detect.
**Untouched per instruction:** CLAUDE.md, firmware/, pi5/server/, KiCad, run_sim.py (and camera.py).
**Verified (sim/Windows):** ruff clean on `pi5 run_hardware.py` + all `ml/*.py` (notebook excluded —
Colab `!`-magics aren't standard-lintable); py_compile all; model-card + ipynb JSON parse; **95 tests
pass**; **ONNX `decode()` unit-tested** with a synthetic YOLOv8 tensor → correct class + box mapped back
through the letterbox (256,176,384,304), and it handles both (1,C,N)/(1,N,C) orientations; model
resolver falls back to yolov8n.pt when no .onnx present; `run_sim` still serves `/health`+`/command` 200.
**UNTESTED (needs a GPU/Colab + the Pi):** the whole training run, real ONNX export, and onnxruntime
inference on hardware (no model trained yet — overlay runs COCO yolov8n until `maritime_yolov8n.onnx` is
dropped in).
**Next steps:** uncommitted (offer). Run the pipeline on Colab (set ROBOFLOW_API_KEY; confirm the
Roboflow workspace/project/version slugs + each source's class names against `remap.json`), export,
`scp` the .onnx to `pi5/cv/models/`, then verify on the Pi that vision_overlay logs "Using maritime
ONNX model" and the command-center boxes/tracking show maritime classes.

## 2026-06-08 — Detect FPS "stuck at ~4": it's inference-bound; added live IMG-size control

**Reported:** detection FPS sits ~4 and doesn't rise when DET FPS is set higher.
**Diagnosis (not a bug):** `detect_max_fps` is an **upper cap**, not a target. `vision_overlay._loop`
runs YOLO back-to-back and only `continue`s (drops a frame) when frames arrive faster than the cap —
there's no path that speeds inference up. ~4 fps = yolov8n @ imgsz 416 on the Pi 5 **CPU**; any cap ≥4
is a no-op. The real lever is inference size (`imgsz`), which was fixed at startup and not live-tunable.
**Changed:**
- `pi5/cv/vision_overlay.py` — `apply_controls()` now accepts `imgsz` (clamp 160–640, snap to a
  multiple of 32 as YOLO requires). Applies on the next frame, no model reload. `controls()` already
  surfaced `imgsz`, so `GET/POST /api/camera` carry it with no app.py change.
- `pi5/server/templates/command_center.html` — added an **IMG** dropdown (256/320/416/512/640) by
  DET FPS, wired to `/api/camera` (loads from `c.imgsz`, posts on change), default 416; added an ⓘ
  hint on DET FPS that it's a cap. Compact `.imgsel` style.
**Guidance given:** lower IMG (416→320 ≈ 1.7× faster) and/or export to **NCNN** (`camera.detection.model`
already accepts an `_ncnn_model` dir, ~2× on ARM) → ~8–12 fps; 320 + NCNN is the practical sweet spot.
**Verified (sim/Windows):** imgsz clamp/snap unit-tested (all /32, 160–640, junk ignored), ruff clean,
py_compile OK; booted `run_sim`, `/command` renders the IMG control + JS hooks, `/api/camera` responds
(sim has no overlay so keeps the 416 default). Real detect-FPS gain is Pi-only (CPU/model bound).
**Next steps:** uncommitted at write time (offered to commit/push to main).

## 2026-06-08 — Move the web server from port 8080 → 8000

**Worked on:** user asked to run the server on 8000 instead of 8080. Changed the port everywhere it
appears so it stays consistent (server + reverse proxy + dashboard dev proxy).
**Changed:**
- `pi5/config.yaml` — `server.port: 8000` (read by `run_hardware.py`).
- `run_sim.py` — hardcoded `uvicorn.run(port=8000)` + startup banner/docstring.
- `run_hardware.py` — fallback default `server_cfg.get("port", 8000)`.
- `deploy/Caddyfile` — `/api/*` and `/ws/*` reverse_proxy → `localhost:8000`.
- `dashboard/vite.config.js` — dev-proxy `/api` + `/ws` targets → `localhost:8000`.
**Verified (sim/Windows):** booted `run_sim`, `/health` 200 on `http://localhost:8000`, nothing on
8080. Command center is now at `http://<host>:8000/command`. (KiCad files contain `8080` only as
coincidental UUID hex — left alone.)
**Next steps:** uncommitted at write time (offered to commit/push to main).

## 2026-06-08 — Boat health panel: 3 battery rails (12S/4S/3S), dual air/enclosure T+RH, L/R hull

**Worked on:** follow-up to the BOAT HEALTH panel — user wants three battery statuses (12S/4S/3S),
two temp+humidity sensors (one in the electronics enclosure, one open air), and separate left/right
hull-dry indicators.
**Data-flow finding:** TEL's `batt_v` was already the **12S propulsion** rail; the **3S** was read in
firmware but only sent on `TEL2` (which the Pi never parses); the **4S winch** was **never read**
(GP28 = "spare"); SHT41 **#B** was read into `air_temp2/air_humidity2` but never sent; the TEL `hull`
string already encodes L/R. So: extend the already-parsed **ENV** message (not TEL2), add the 4S read,
and decode hull in the UI.
**Key call:** extended **ENV → v1.1** by **appending** six fields (enclosure SHT41 temp/humidity, 3S
v/%, 4S v/%) so it stays **backward compatible** — v1.0 firmware omits them, the parser reads them only
when `len(fields) >= 12` (verified both ways). 12S stays in TEL.
**Changed:**
- `firmware/boat-pico/sensors.py` — added a **4S winch** read on **GP28** (PCB BT4 100k/18k divider →
  `winch_batt_v/pct`); `read_all_fast()` now reads all three rails. Flagged the divider as provisional
  (prop/elec use different dividers in firmware — the known discrepancy).
- `firmware/boat-pico/serial_handler.py` — `send_env()` appends `enc_t,enc_h,elec_v,elec_pct,winch_v,
  winch_pct` (defaults keep v1.0 callers working).
- `firmware/boat-pico/main.py` — `task_env_telemetry` passes SHT41 #B + elec + winch; pin-map docstring
  + boot prints updated (GP28 = 4S, #A air / #B enclosure).
- `pi5/comms/pico_serial.py` — `Environment` gains `enc_temp/enc_humidity/elec_batt_v/elec_batt_pct/
  winch_batt_v/winch_batt_pct` (sentinels -999/-1/0); `_handle_env` parses fields 6–11 when present.
- `pi5/navigation/simulator.py` — sim now has 3 rails (12S 50.4 drains as it drives, 3S 12.4, 4S 16.2)
  + an enclosure SHT41 (warmer/drier than air); MockPico `telemetry` batt% fixed to the **12S** range,
  `environment` emits the v1.1 fields.
- `pi5/server/app.py` — `_boat_health()` adds `elec_v/pct`, `winch_v/pct`, `enc_temp/humidity`, and
  `hull_left`/`hull_right` (decoded from the TEL hull code).
- `pi5/server/templates/command_center.html` — BOAT HEALTH retiled: **12S DRIVE / 4S WINCH / 3S ELEC**
  (each V·% + bar, colour by %), **HULL·LEFT / HULL·RIGHT** (DRY/WET), **AIR** + **ENCLOSURE** T/RH,
  plus heading/speed/motors/GPS/water. New `setBatt()`/`setHull()` helpers; N/A on ≤0.5 V / -999.
- `docs/serial-protocol.md` — documented the ENV v1.1 appendix (+ a v1.0/v1.1 example pair).
**Verified (sim/Windows):** `ruff check pi5 run_hardware.py` clean (firmware is MicroPython — bare
`except`/`machine` imports, not in the lint target); `py_compile` OK on firmware + pi5; **95 tests pass**;
ENV round-trip unit-checked (v1.1 parses all 12 fields, v1.0 6-field keeps defaults). Booted `run_sim`:
`/health.boat` shows 12S 50.4 V/100 %, 4S 16.2 V/87 %, 3S 12.4 V/94 %, hull L/R DRY/DRY, air 19 °C/47 %,
enclosure 24.4 °C/28 %; `/command` renders all new tiles. **Firmware 4S read + dual-SHT41 send are
Pi/Pico-only and UNTESTED on hardware** (and the SHT41 GP12-15 pin conflict from the prior entry still
gates real temp reads).
**Next steps:** uncommitted (offer). On hardware: bench-calibrate the GP28 4S divider; confirm ENV v1.1
arrives and the three rails read sane; resolve the SHT41 re-pin before the enclosure/air temps are real.

## 2026-06-08 — Command-center: camera L/R switch, object-track viz, boat health, manual stepper pan 0–360

**Worked on:** four user-requested command-center features — (1) switch between left/right
cameras, (2) show tracking of a YOLO-detected object, (3) surface the boat/Pico health, (4) manual
stepper pan left/right locking anywhere 0–360°.
**Key engineering call (stepper):** decoupled *wrapping* from *travel range* in `StepperMotor`.
`has_slip_ring` now only gates taking the short way across the 0°/360° seam (the one thing a cable
can't survive); travel limits are independent. With no slip ring the bar is a **linear axis with
hard stops** — so it reaches a full 0–360° manually but never winds >1 turn. This also fixes a
latent mod-360 bug: position is now tracked **unwrapped** when not wrapping, so jogging left off the
360° end no longer strands the count at 0. Auto-scan SCAN keeps its own narrower sweep range.
**Changed:**
- `pi5/cv/stepper.py` — `_wrap` (= has_slip_ring) separate from `min_deg`/`max_deg`; `step()` wraps
  mod-rev only when `_wrap`, else clamps the count to `[min,max]` steps; `get_position_degrees()`
  unwrapped when linear. Manual range now 0–360 by default.
- `pi5/cv/radar_tracker.py` — `jog(delta)` (relative pan → HOLD goto); `status()` adds `target`
  ({label,conf} when locked) and `sweep` (auto-scan range, distinct from the manual `limits`);
  records the locked target in SCAN/TRACK.
- `pi5/cv/vision_overlay.py` — tracks a **primary target** (highest-conf highlight class); `draw()`
  paints a cyan lock reticle (corner brackets + crosshair + "TRACK label") on it; `primary_target()`
  accessor for the UI/health.
- `pi5/cv/camera.py` — `has_right` property (is a 2nd camera open?).
- `pi5/server/app.py` — `/video?cam=left|right` (overlay drawn on left only; right falls back to
  left); `_camera_state()` adds `right_present`; `_gather_health()` adds `track`, `stepper_target`,
  and a `boat` block (`_boat_health()`: link, battery, hull, motor temps, GPS/hdg/spd, decoded
  6-flag health string, ENV sensors, last alert); `JOG` added to `/stepper/command`.
- `pi5/server/templates/command_center.html` — SOURCE ◄LEFT/RIGHT► toggle + on-feed ◎TRACKING badge;
  new **BOAT HEALTH** panel (battery bar, hull, heading/speed, motor temps, GPS, water/air, 6 sensor
  flag chips, last-alert line; hull-leak now also raises the red banner); radar panel gains a MANUAL
  ◄LEFT / step / RIGHT► jog group + tracked-target readout; LOCK-TO accepts 0–360. Rose sweep sector
  now shades `sweep` not `limits`. Added a 6th grid row.
- `pi5/config.yaml` — `stepper.manual_min_degrees`/`manual_max_degrees` (0/360) split from `sweep_*`;
  clarified `has_slip_ring` = wrap-only.
- `run_hardware.py` — stepper built with the manual range (0–360); RadarTracker keeps the sweep range.
- `docs/pin_map.md` — documented the two travel ranges + the wrap/no-wrap distinction and cable caveat.
**Deliberate divergence (flagged):** the prior session said full 360° needs a slip ring. The user
explicitly asked for 0–360 manual control; implemented it **safely** (linear, hard-stopped, no wrap)
and flagged the ≤1-turn cable wind in `config.yaml` + `pin_map.md` rather than silently capping it.
**Verified (sim/Windows):** `ruff check pi5 run_hardware.py` clean; `py_compile` OK; **95 tests pass**;
stepper bench **9/9** (mock); a 0–360 mock run reached 270/350/360 and jogged −20 off the 360° end to
339.97 (old bug would strand at 0), clamps at 0/360. Booted `run_sim`: `/health` carries `boat`
(batt 16.8 V/100 %, hull DRY, all 6 flags OK, water temp/EC) with `track`/`stepper_*` = null (no
overlay/radar in sim); `/api/camera` → `right_present:false`; `/stepper/command JOG` →
hardware-only; bad command → 400; `/video?cam=right` streams the placeholder; `/command` serves all
new panels/JS. **All GPIO/motor/camera/YOLO behaviour is Pi-only and UNTESTED on hardware.**
**Next steps:** uncommitted (offer). On the Pi: with two cameras, verify the RIGHT button; with a
maritime/COCO model + a target in frame, confirm the lock reticle + ◎TRACKING badge and that the bar
slews under TRACK; bench the manual jog across the full 0–360 with the bar free. If a slip ring is
fitted, set `has_slip_ring: true` (re-enables short-way wrap).

## 2026-06-08 — Radar-bar stepper control (A4988 on Pi 5 GPIO, not the Pico)

**Worked on:** implemented `~/Downloads/DREAMS_stepper_instruction (1).md` — A4988-driven
NEMA-17 radar-bar pan, coordinated with the YOLO vision overlay. The user's **revised** instruction
moved the stepper from the Boat Pico to the **Pi 5 GPIO header** (the first Pico draft, `(1).md`'s
predecessor, collided GP18-21 with the hull-leak sensors / SHT41 re-pin mess — the Pi-5 approach
sidesteps all of that).
**Deliberate divergence (flagged, not silently resolved):** driving Pi 5 GPIO breaks the
"**Pi 5 uses only USB — no GPIO**" locked decision in `CLAUDE.md`. The user chose this explicitly;
I implemented it and documented it in `docs/pin_map.md` rather than editing the locked-decisions doc.
**Key engineering call:** stepper stepping is **blocking** (`time.sleep` per pulse). Running it from
an asyncio task would freeze the whole FastAPI server, so the **RadarTracker owns a single daemon
thread** that is the sole motion authority; HTTP endpoints only flip thread-safe flags. Mirrors the
repo's existing graceful-degradation pattern (camera/overlay/psutil): no `gpiozero`/`lgpio` →
StepperMotor runs in **mock mode** (position tracking + real timing, no pin toggles), so `run_sim.py`
and the test suite still work on Windows.
**New:**
- `pi5/cv/stepper.py` — `StepperMotor` (A4988): enable/disable/sleep/wake, trapezoidal-ramped `step`,
  `rotate_degrees`/`rotate_to` (travel-clamped, 0-180° w/o slip ring), `scan`/`scan_async`/`stop_scan`
  (daemon-thread sweep w/ `threading.Event`), absolute position tracking, auto-sleep, `cleanup()`.
- `pi5/cv/radar_tracker.py` — `RadarTracker`: SCAN/TRACK/HOLD/SLEEP on one daemon thread; reads
  detection boxes from the overlay (`boxes()`) and slews to centre a priority target (boat/person)
  via bbox→bearing; reverts to SCAN after `lost_timeout_s`. Defensive: no overlay → just SCANs.
- `pi5/cv/stepper_test.py` — standalone bench test (`python3 pi5/cv/stepper_test.py`), 9 checks, ASCII
  output (Windows console safe). All 9 pass in mock mode.
**Changed:**
- `pi5/cv/vision_overlay.py` — added public `boxes()` accessor (raw xyxy boxes) for the tracker.
- `pi5/server/app.py` — `configure(stepper=, radar=)`; `GET /stepper/status` + `POST /stepper/command`
  (SCAN/STOP/GOTO/CENTER/SLEEP/WAKE/TRACK/HOLD — non-blocking, route to the tracker; available:false
  off-Pi); `_gather_health()` now carries `stepper_angle`/`stepper_state`/`stepper_target_locked`.
- `run_hardware.py` — build StepperMotor + RadarTracker from `stepper:` config, inject, start the
  tracker thread on startup / `radar.stop()` (joins thread + GPIO cleanup) on shutdown. Never blocks startup.
- `pi5/config.yaml` — new `stepper:` block (pins 23/24/25/8, 3200 steps/rev, sweep 0-180, FOV 75,
  priority_classes, initial_mode=SLEEP).
- `pi5/server/templates/command_center.html` — new RADAR BAR panel: SVG compass rose w/ animated
  needle + sweep sector, live angle / mode / lock readouts (from `/ws/health`), SCAN/TRACK/STOP/CENTER
  /WAKE/SLEEP/GOTO buttons (→ `/stepper/command`). Added a 5th grid row.
- `docs/pin_map.md` — new "Radar-bar stepper — Pi 5 GPIO (A4988)" subsection (pin table + boot-state
  caveat); softened the "no GPIO" claim to "no GPIO **for sensors**".
**Verified (sim/Windows):** `py_compile` OK; `ruff check pi5 run_hardware.py` clean; **95 tests pass**;
bench test **9/9** (mock); StepperMotor + RadarTracker smoke-tested (rotate/clamp/scan/stop); endpoint
handlers exercised directly (status, SCAN/GOTO ok, bad-cmd→400, GOTO-no-value→400); booted `run_sim`
and confirmed `/health` carries stepper_* = null, `/stepper/status` → available:false, and `/command`
serves the radar panel + JS hooks. **All GPIO/motor behaviour is Pi-only and UNTESTED on hardware.**
**Boot-state caveat for the user:** GPIO25 (ENABLE) is LOW at boot → coils briefly energised before
software runs; consider an external pull-up if boot quiescent current matters (noted in pin_map.md).
Set `stepper.has_slip_ring: true` only once the slip ring is installed (unlocks full 360°).
**Next steps:** uncommitted (offer). On the Pi: `pip install lgpio gpiozero`, set A4988 VREF≈0.67 V, run
`python3 pi5/cv/stepper_test.py` with the bar free, then drive it from `/command`. Possible follow-up:
let RadarTracker reuse the avoidance detector if avoidance is later wired into run_hardware.

## 2026-06-08 — Implemented dual-SHT41 firmware (re-pin to as-built board)

**Worked on:** user confirmed part = Teyleten **GY-SHT41-D** breakout (×3) and chose **"re-pin
firmware to board"** (PCB is fabricated; firmware adapts). Implemented the temp-sensor firmware to
match the as-built board and documented the conflicts.
**Changed / new:**
- `firmware/boat-pico/sht41.py` (new) — bus-agnostic `SHT41` class (Sensirion SHT4x): 0x44, cmd 0xFD
  high-precision, 6-byte read, CRC8 (poly 0x31), tick→°C/%RH conversion, degrade-safe.
- `firmware/boat-pico/sensors.py` — dropped DHT11 (GP16, not on board). Added two SHT41s on
  **SoftI2C**: #A GP12/13 (J11), #B GP14/15 (J13). SoftI2C because HW I²C0 is held by the BNO085
  (GP8/9). Exposes `air_temp/air_humidity` (A) + `air_temp2/air_humidity2` (B). `read_all_slow()` now
  reads both SHT41s + hull. (`send_env` keeps `%d` → truncates the float to int; bumping ENV to
  `%.1f` to keep SHT41 precision is an optional protocol change, not done.)
- `firmware/boat-pico/main.py` — updated pin-map docstring, `task_slow_sensors` doc, boot prints; added
  a loud as-built-conflict warning print. **Did NOT touch vesc/motor_control/sbus** (safety-critical).
- `docs/pin_map.md` — GP12-15 rows now show SHT41 (board); GP16 = unused; added an "⚠ As-built board
  divergence (GP12–GP16)" callout + two SoftI2C rows in the bus summary with conflict notes.
**⚠ Unresolved blockers (flagged, not fixed):** GP12/13=VESC UART0, GP14=winch PWM, GP15=SBUS still
claim those pins in firmware; on the board they're the temp connectors. VESC/winch/SBUS are mis-pinned
for this board and must be relocated off GP12-15 before the boat can drive AND read temps together —
but the board's winch connector (J8/J9 both pins on GND) and SBUS input have no valid pins (known board
errors). So a full re-pin is blocked on hardware decisions / likely a board respin.
**Board/cabling (part b) — for the fabbed board:** connector pin order is reversed vs the module
(board J11/J13 = [SDA,SCL,GND,V+]; GY-SHT41-D = [VDD,GND,SDA,SCL]) → needs a **crossover cable**
(module VDD→board pin4, GND→pin3, SDA→pin1, SCL→pin2). And **don't use board pin4 (VSYS≈5 V)** for VDD
unless the module is confirmed regulated+level-shifted — feed VDD from 3.3 V (Pico pin36, currently
unconnected) since RP2040 GPIO isn't 5 V-tolerant.
**Verified (Windows):** py_compile OK (sht41/sensors/main); `ruff check pi5` clean; 95 tests pass.
Firmware runtime is Pi/Pico-only (SoftI2C + SHT41 reads untested on hardware).
**Next steps:** user to decide VESC/winch/SBUS relocation (or board respin); bench-test SHT41 reads
once GP12-15 are freed; optionally extend ENV telemetry to carry sensor #2.

## 2026-06-08 — Reviewed temp-sensor wiring (J11/J13) against schematic; flagged SHT41 issues

**Worked on:** user said the two "Temp + Humidity Sensor" connectors will be **SHT41** (I²C, 4-pin),
asked to check the wiring. Re-exported the netlist (`kicad-cli sch export netlist --format kicadsexpr`,
no net labels in sch) and traced J11/J13.
**Findings (verified from netlist):**
- **J11** (0.1″ hdr): pin1→GP12 (I2C0 SDA), pin2→GP13 (I2C0 SCL), pin3→GND, pin4→**VSYS ≈5 V**.
- **J13** (JST-XH): pin1→GP14 (I2C1 SDA, shared w/ J10 IMU + J7 GPS hdr), pin2→GP15 (I2C1 SCL, shared),
  pin3→GND, pin4→**VSYS ≈5 V**.
- GOOD: pin pairs are HW-I²C-legal and SDA/SCL not swappable (RP2040 muxing); two 0x44 SHT41 on
  separate buses (I2C0 + I2C1) is the correct topology for the fixed address.
- ⚠ **5 V V+**: SHT41 abs-max 3.6 V; Pico 3V3-OUT (pin36) is unconnected. Bare SHT41 would be damaged.
  Only OK if using a breakout with onboard 3.3 V LDO + level shift.
- ⚠ **No I²C pull-ups** on any of GP12/13/14/15 (only Pico+connector on each net).
- ✗ **Firmware/docs mismatch**: `sensors.py` + `pin_map.md` describe one **DHT11 (1-wire) on GP16**,
  but GP16 is unconnected in the sch and there's no DHT11 — same sch-vs-firmware divergence flagged
  2026-06-01. To use as wired, firmware needs `I2C(0,sda=12,scl=13)` + `I2C(1,sda=14,scl=15)`, SHT4x
  cmd 0xFD @ 0x44.
**Part confirmed by user:** Teyleten Robot **GY-SHT41-D** breakout (×3), I²C, "3.3–5 V".
**NEW critical finding — connector pinout is reversed vs the module:** GY-SHT41-D pin order is
`VDD·GND·SDA·SCL` (power on pins 1–2), but the PCB connectors put **signals on pins 1–2, power on
pins 3–4**. A straight 1:1 cable would feed module VDD (≤5 V) onto GP12/GP14 → fries the Pico. Fix by
re-assigning the connector footprint to `VDD·GND·SDA·SCL` (target: pin1=3V3, pin2=GND, pin3=SDA GP12/14,
pin4=SCL GP13/15) OR a crossover cable (riskier).
**Power:** still route V+ to **3V3 (Pico pin 36, currently unconnected)**, NOT VSYS(5 V) — RP2040 GPIO
not 5 V-tolerant; couldn't confirm an onboard regulator/level-shifter on the cheap GY board (the
"level-shifted 3–5 V" claim is Adafruit's, blended in by search). 3.3 V is safe either way.
**Pull-ups:** GY modules usually carry onboard 10 k pull-ups → board's lack of them likely moot (verify
2 resistors on module). J13 bus shared w/ J10/J7 → parallel pull-ups ≈3.3 k, still OK.
**Decisions / open questions:** did NOT edit firmware/docs/sch yet — offered to (a) rewrite pin_map.md +
sensors.py to dual-I²C SHT4x (I2C0=GP12/13, I2C1=GP14/15, addr 0x44, cmd 0xFD), (b) spec the schematic
footprint reorder + 3V3 rail. PCB-rework approach (footprint vs crossover cable) is the user's call.
**Next steps:** await user go-ahead on (a)/(b); the footprint reorder + 3V3 reroute are the gating
hardware fixes before any SHT41 can be plugged in safely.

## 2026-06-08 — Self-healing serial read loop + hide Sim Speed on hardware

**Worked on:** user hit a tight error loop on push: `Read loop error: device reports readiness to
read but returned no data (device disconnected or multiple access on port?)` repeating ~every 100 ms;
also asked to drop the Sim Speed control on hardware.
**Cause:** `PicoSerial._read_loop` caught the disconnect exception, slept 0.1 s, and retried the SAME
dead connection forever — never reconnecting (and `... multiple access on port` suggests it can also
fire if a 2nd process, e.g. a manual `deploy_pico.py`, grabs the port while run_hardware holds it).
**Changed:**
- `pi5/comms/pico_serial.py` — read loop self-heals: on any read error it closes the streams and
  re-opens with backoff (0.5→5 s), and treats an empty read as a disconnect. Added `_open_streams()` /
  `_close_streams()`; `connect()` uses them. So a Pico reset/reflash/port-contention recovers cleanly
  instead of spamming.
- `pi5/server/static/index.html` — wrapped the Sim Speed row+slider in `#simSpeedControl` and hide it
  when `/api/sim/speed` returns null (hardware mode, `_sim is None`). Other control sliders stay.
**Verified (sim/Windows):** ruff clean; PicoSerial imports with new helpers; 95 tests pass; dashboard
serves with `#simSpeedControl`; `/api/sim/speed` returns 1.5 in sim (control visible). The reconnect
path is Pi-only (sim uses MockPicoSerial, no read loop) — reasoned, not runtime-tested.
**Note for user:** don't run a manual `deploy_pico.py` while `run_hardware.py` is up — two processes on
/dev/ttyACM0 is itself a cause of that error. Stop run_hardware first, or use the command center push.
**Next steps:** uncommitted at write time (committing now).

## 2026-06-08 — Non-blocking Pico serial read (likely fixes HB timeout AND REFLASH)

**On-Pi test results:** standalone `deploy_pico.py` worked from a clean REPL (all 11 files copied, Pico
reset). Camera confirmed **640x480 @ 30 fps mjpg=True** (fps fix works); right cam absent as expected
(single camera). BUT `run_hardware.py` startup deploy still failed `could not enter raw repl` — so
REFLASH-while-running was NOT dropping the firmware to the REPL.
**Diagnosis:** `serial_handler.read_usb()` did `sys.stdin.buffer.read(64)` — a BLOCKING read that waits
for 64 bytes. Heartbeats (~10 B) and the REFLASH frame (~12 B) never fill 64 B promptly, so they sit
unprocessed → HB ACKs arrive too late (watchdog ESTOPs = the original HB-timeout symptom) and REFLASH
never registers. This one bug likely explains BOTH the HB timeouts and the REFLASH no-op.
**Fixed (firmware):**
- `serial_handler.py` — `read_usb()` now non-blocking: `select.poll(sys.stdin)` + read 1 byte at a
  time while data is available. Added `import select` + a module `_stdin_poll`.
- `main.py` — replaced `asyncio.gather(...)` with `create_task(...)` + a monitor loop that waits on
  `serial.reflash_requested`, then `motor_control.estop()`, cancels all tasks, and returns → drops to
  the REPL (more reliable than raising SystemExit inside a gathered task). Reverted the SystemExit in
  task_serial_rx.
**Verified (Windows):** py_compile OK for both; deploy_pico ruff clean. Runtime is Pi-only.
**CRITICAL next step for user:** the firmware currently ON the Pico still has the blocking read + the
old (non-working) REFLASH, so REFLASH can't install the fix — they must deploy this updated firmware
once more from a clean REPL (BOOTSEL+uf2 wipe, or Thonny stop + remove main.py, then
`python pi5/scripts/deploy_pico.py`). After that: HB should stay alive (boat functional) and boot
auto-deploy via REFLASH should work.

## 2026-06-07 — Cooperative REFLASH so auto-deploy actually works

**Worked on:** the boot auto-deploy was failing — `mpremote.transport.TransportError: could not enter
raw repl`. Diagnosed + fixed.
**Root cause:** the Boat Pico firmware's `task_serial_rx`→`read_usb()` loop continuously reads
`sys.stdin.buffer` (the USB-CDC command channel). That swallows mpremote's Ctrl-C/Ctrl-A REPL-entry
handshake, so mpremote can't take the port **while the firmware is running** — which it always is by
deploy time. No `kbd_intr(-1)` / `boot.py`; it's the raw stdin reads. So you can't mpremote-reflash a
running Pico over the shared USB CDC. (User chose: build cooperative REFLASH.)
**Changed (firmware):**
- `serial_handler.py` — new `reflash_requested` flag + `REFLASH` command (ACK then set flag).
- `main.py` — `task_serial_rx` polls the flag; on set it `motor_control.estop()` then `raise
  SystemExit` to exit the asyncio loop to the bare REPL (frees the USB CDC for mpremote).
**Changed (deploy + docs):**
- `pi5/scripts/deploy_pico.py` — `_request_repl()` writes `$REFLASH,0*91` over pyserial and waits
  1.5 s before the mpremote copy; best-effort (degrades if port busy / pyserial missing).
- `docs/serial-protocol.md` — added §3.13 REFLASH.
**Boot chain now:** run_hardware → deploy sends REFLASH → firmware stops+drops to REPL → mpremote cp +
reset → fresh firmware → Pi connects.
**CRITICAL one-time step:** the Pico currently runs OLD firmware (no REFLASH → NAKs, keeps eating
stdin), so mpremote still fails until the REFLASH-aware firmware is installed once by hand. Reliable
path: BOOTSEL + drag MicroPython .uf2 (wipes filesystem/old main.py) → clean REPL → run
`python pi5/scripts/deploy_pico.py` once. Then boot auto-deploy works.
**Verified (Windows):** ruff clean; serial_handler.py + main.py py_compile OK; REFLASH frame/checksum
correct ($REFLASH,0*91); `_request_repl` degrades cleanly without a port; 95 tests pass. UNTESTED on
hardware: whether `raise SystemExit` cleanly drops uasyncio to the REPL (fallback = manual wipe).
**Next steps:** uncommitted (offered). Bench-test the REFLASH drop on the Pi.

## 2026-06-07 — Camera 10→30 fps (MJPG) + view on-Pico code from command center

**Worked on:** camera was stuck at 10 fps though the sensor does 30; user also couldn't see what code
is actually on the Boat Pico.
**FPS fix:** root cause = producer captured at `camera.fps: 10` and didn't request MJPG; the new
stream cap was 15. Changed:
- `pi5/config.yaml` — `camera.fps` 10→30, added `use_mjpg: true`, `stream_fps` 15→30.
- `pi5/cv/camera.py` — `_open()` requests MJPG fourcc before resolution (far faster over USB, needed
  for 30 fps; OpenCV falls back if unsupported), sets `BUFFERSIZE=1`, logs negotiated WxH@fps.
  `CameraConfig` gained `use_mjpg` (default true), default fps 30.
- `run_hardware.py` — passes `use_mjpg` through.
Capture now 30, stream publishes up to 30 (still live-adjustable via the STREAM FPS slider).
**View on-Pico code:** 
- `pi5/server/app.py` — new `GET /pico/file?name=` reads a file off the Pico via `mpremote cat`
  (same brief serial handoff as /pico/files; path-traversal guarded). Hardware-only.
- `command_center.html` — "⤓ view on pico" button loads the selected file's real contents into the
  Monaco editor so the operator can see exactly what's running (then edit/re-push).
**Verified (sim/Windows):** ruff clean; `/pico/file` → hardware-only notice in sim; traversal → 400;
button+handler present; 95 tests pass. Camera fps only confirmable on the Pi with the real camera.
**Caveat:** view/files/push briefly release the serial link (Pico watchdog ESTOPs ~1-2s, then
reconnects) — fine when not actively driving.
**Next steps:** uncommitted (offered).

## 2026-06-07 — Incorporated vision (detection overlay) + adjustable FPS/camera + configurable model

**Worked on:** pulled vision from the external `ka1e27/D.R.E.A.M.S-Vision-Test` repo into the command
center, researched a marine detection library, made FPS/camera settings adjustable.
**Findings:** the vision-test repo is a dual-thread FastAPI dashboard (capture thread at camera rate +
separate rate-capped YOLO thread → decoupled stream/detect FPS, boxes drawn on the feed, live /control
knobs). No turnkey "marine" pip library exists — practical path is Ultralytics YOLO (already our dep)
with maritime-trained weights (SeaShips / MASTR1325 / Singapore Maritime Dataset / Roboflow Marine
Surveillance / TPH-YOLOv5). User chose: configurable weights, default COCO, drop-in maritime .pt.
**Changed / new:**
- `pi5/cv/vision_overlay.py` (new) — `DetectionOverlay`: subscribes to the shared CameraProducer (NOT
  a 2nd VideoCapture), runs YOLO on a rate-capped asyncio task with inference in a thread executor,
  keeps latest boxes + inference-FPS, `draw()` overlays them, runtime `apply_controls()`. Model path +
  target/highlight classes configurable; degrades to None if ultralytics/model missing.
- `pi5/server/app.py` — inject `_overlay` + `_jpeg_quality`/`_stream_fps_cap` via configure(); `/video`
  now draws boxes on a copy, caps publish rate, uses runtime JPEG quality (stream FPS decoupled from
  detect FPS); `/health` adds `detect_fps`/`detections`; new `GET/POST /api/camera` (detection on/off,
  detect_max_fps, conf, jpeg_quality, stream_fps).
- `run_hardware.py` — build DetectionOverlay from `camera.detection` config, start after camera /
  stop on shutdown; pass overlay + jpeg_quality + stream_fps to configure.
- `pi5/config.yaml` — `camera.detection` block (model/imgsz/conf/detect_max_fps/classes) +
  `stream_fps`/`jpeg_quality`, with maritime-model + NCNN docs.
- `pi5/server/templates/command_center.html` — vision control bar under the feed (DETECT toggle,
  DET-FPS / CONF / QUALITY / STREAM-FPS sliders) + `cam-det` readout (detect fps · detected classes)
  fed from /ws/health; wired to /api/camera (debounced POST).
**Verified (sim/Windows):** ruff clean; imports resolve; `/api/camera` GET/POST apply quality+fps;
`/health` carries detect fields (null in sim — no overlay); `draw()` renders boxes; 6 controls present;
95 tests pass. Real YOLO only runs on the Pi (camera + ultralytics; auto-downloads yolov8n.pt once).
**Next steps:** uncommitted (offered). On the Pi: run_hardware → boxes on /command; swap to a maritime
.pt in config to specialise. Possible follow-up: reuse the overlay detector for AvoidanceLoop (avoid a
2nd model load) if/when avoidance is wired into run_hardware.

## 2026-06-07 — Auto-deploy Boat Pico firmware on Pi boot

**Worked on:** user wants the Pico's Python firmware uploaded on Pi boot (Pico is on USB). This also
addresses the HB-timeout — a Pico without current firmware can't ACK heartbeats.
**Changed / new:**
- `pi5/scripts/deploy_pico.py` (new) — copies `firmware/boat-pico/*.py` to the Pico via mpremote and
  resets it. CLI: `--port`, `--no-reset`. Reads port from config.yaml. Batch copy with per-file
  fallback. Invokes mpremote as **`python -m mpremote`** (via `sys.executable`) so it works under
  systemd's minimal PATH (bare `mpremote` console script wouldn't be found).
- `pi5/scripts/__init__.py` (new) — makes scripts importable so run_hardware can call `deploy()`.
- `run_hardware.py` — on startup, if `serial.deploy_on_start` (default true), deploys firmware +
  waits 2.5s for reboot BEFORE opening the serial link (port must be free for mpremote). Wrapped so a
  deploy failure never blocks startup. Added `import asyncio`.
- `pi5/config.yaml` — new `serial.deploy_on_start: true`.
- `pi5/services/dreams.service` (new) — systemd unit: runs run_hardware.py on boot (After
  network-online, ExecStartPre sleep 5 for USB enumerate). Paths/User are placeholders to edit.
**Boot chain:** power on → systemd → run_hardware → upload firmware + reset Pico → wait → connect +
heartbeat → serve /command.
**Verified (Windows):** ruff clean; deploy_pico finds all 11 boat-pico files; run_hardware imports the
deploy fn; deploy() degrades cleanly (mpremote present here but no /dev/ttyACM0 → fails gracefully,
returns False). Real upload is Pi-only.
**User setup:** `pip install mpremote`; `sudo cp pi5/services/dreams.service /etc/systemd/system/`
(edit paths) → `systemctl enable --now dreams`. deploy_on_start re-uploads every start (set false for
firmware dev).
**Next steps:** uncommitted along with the pod-light changes (offered). Bench-test on the Pi:
firmware should upload, HB timeout should clear once the Pico runs current firmware.

## 2026-06-07 — Pod Pico status light on the Command Center (+ HB-timeout explainer)

**Worked on:** added a POD link light to `/command`; explained the `Timeout on HB` warning.
**Changed:**
- `pi5/server/app.py` `_gather_health()` — added `pod_ok` / `pod_leak` / `pod_age_s`, read from the
  existing `PodBridge` (`_pod.pod_ok` + `_pod.latest.leak_detected`/`timestamp`). Degrades to None if
  no pod bridge.
- `pi5/server/templates/command_center.html` — new POD dot in the header (green=responding,
  amber=responding+leak, red=not responding); leak also raises a prioritised red banner
  ("POD LEAK DETECTED"). Reworked the banner logic to prioritise leak > thermal > throttle.
**Verified (sim):** ruff clean; `/health` → `pod_ok:true, pod_leak:false, pod_age_s:1.3` after a poll;
page has `dot-pod`.
**HB-timeout answer (for the record):** `Timeout on HB seq=N (attempt 3/3)` = the Pi sent a heartbeat
and got no `ACK` back within 2s × 3 retries. Firmware *does* ACK HB (`serial_handler.py:194`), so it
means the Boat Pico isn't replying: Pico not running main.py / wrong or busy `/dev/ttyACM0` (only one
process can own it) / framing-checksum-baud mismatch / Pico reset. The Pico side mirrors this — its
3s watchdog ESTOPs (`CRIT HB_LOST`) if HBs stop. Diagnose: `ls /dev/ttyACM*`, `sudo fuser
/dev/ttyACM0`, `mpremote connect /dev/ttyACM0 repl` to see boot prints; ensure nothing else holds the
port while `run_hardware.py` runs.
**Next steps:** uncommitted (offered). Bench-test run_hardware.py + resolve the HB link on the Pi.

## 2026-06-07 — Added run_hardware.py (real Pico + camera entry point)

**Worked on:** user has a real Pico + camera on the Pi and asked how to use them. Confirmed the gap I'd
flagged: `run_sim.py` was the ONLY runner (mock Pico, no camera). README says "set `mode: hardware`"
but no such key exists in config.yaml and nothing reads it. The `configure()` plumbing already accepts
a `camera=` producer — it was just never instantiated.
**Changed:** `run_hardware.py` (new, top-level) — hardware counterpart to run_sim.py. Wires a real
`PicoSerial(port,baud)` (+ `connect()` + `start_heartbeat()`) and a real `CameraProducer` into
`configure(..., simulator=None, camera=camera)`, then serves the app. Loads `pi5/config.yaml` for
serial/camera/server/heartbeat with sane fallbacks. Degrades gracefully: camera open failure →
`server_app._camera=None` (NO-SIGNAL placeholder); Pico connect failure → logs, keeps serving. On
startup connects Pico + heartbeat (watchdog ESTOPs if heartbeats stop = safe), starts nav + pod;
shutdown reverses it.
**Result on the Pi:** `/command` shows the LIVE camera (MJPEG), real parsed Pico telemetry + working
commands + Push-to-Pico, and real vcgencmd/psutil health — vs the simulator's placeholders.
**Verified (Windows):** ruff clean; module imports cleanly (main() guarded). **NOT testable here** —
no real serial/camera on this box; the connect/camera-open path only runs on the Pi. Mirrors the
working run_sim wiring.
**Pi prereqs documented for user:** `pip install -r pi5/requirements.txt`; `dialout`+`video` groups;
check `/dev/ttyACM0` + `/dev/video0`; single camera is fine (stereo off).
**Next steps:** uncommitted along with the health-metrics changes (offered to commit). Real next step
is bench-testing run_hardware.py on the Pi; also `/pico/push` reconnect still untested on hardware.

## 2026-06-07 — More health metrics on the Command Center

**Worked on:** user asked for more health status points on `/command`.
**Changed:**
- `pi5/server/app.py` `_gather_health()` — added swap, uptime, process count, load average (1/5/15),
  and live network throughput (↓/↑ KB/s, computed from a delta against a new `_net_prev` module
  global). All inside the existing psutil try/except so they degrade to None if psutil is missing.
- `pi5/server/templates/command_center.html` — new SWAP bar + vgrid rows (LOAD, UPTIME, PROCS,
  NET ↓/↑, SDRAM V alongside CORE V); added `fmtUptime()`/`fmtRate()` JS formatters; each field
  shows N/A when its source is unavailable.
**Verified (sim):** ruff clean; `/health` returns the new fields with real values (uptime, procs,
swap, net rates populate after the 2nd sample); all 7 new element ids present in the page. On the Pi,
load avg + voltages will be real (Windows shows emulated load 0.00).
**Next steps:** uncommitted (offered). Still open: hardware `/pico/push` test; real hardware entry
point (live camera + Pico).

## 2026-06-07 — Added a buttons-only COMMANDS panel to /command

**Worked on:** user found `/docs` (Swagger) too verbose ("I just want them to send commands"). Added a
clean command panel to the Command Center instead of touching Swagger.
**Changed:** `pi5/server/templates/command_center.html` — new bottom **COMMANDS** panel (grid row added:
`auto 1fr 1fr auto`) with grouped buttons that POST to `/api/*` and toast the result:
- SAFETY: E-STOP, CLEAR E-STOP · MISSION: START/PAUSE/RESUME/SKIP/ABORT + UPLOAD… (modal w/ name +
  waypoints JSON + start-now checkbox) · NAV: lat/lon inputs + GO TO, RTH.
- JS: `postApi()` → `cmd()`, `sendGoto()`, `sendMission()`, `openModal/closeModal`; reuses existing
  `apiHeaders()` (X-API-Key/?key=) and `toast()`. Added `.cbtn`/`.cmd-bar`/`.modal` CSS.
**Note:** these hit the same endpoints `/docs` exposes — they move the boat for real (E-STOP/ABORT act
immediately). The static dashboard `/` already had equivalent buttons; this brings them to the HUD.
**Verified (sim):** panel + JS present in page; POST /api/{estop,resume,goto,mission,mission/start}
all respond correctly (mission upload loaded the waypoint).
**Next steps:** uncommitted along with the nav buttons + scroll fix below — offered to commit all
together. Still open: hardware `/pico/push` test; a real hardware entry point (live camera + Pico).

## 2026-06-07 — Command-center nav buttons + Pico-monitor scroll fix

**Worked on:** cross-page nav buttons, fixed the Pico terminal growing the layout, explained the API page.
**Changed:**
- `pi5/server/static/index.html` (`/`) — added a top-right `.topnav` with **Command Center** (amber)
  + **API** (`/docs`) buttons.
- `pi5/server/templates/command_center.html` (`/command`) — header links restyled as buttons
  (**Dashboard** `/`, **API** `/docs`); **fixed the Pico monitor scroll**: the `.pico-inner` grid row
  was `auto`-sized so the terminal's content drove layout and pushed the SEND/CLEAR bar down. Pinned
  `grid-template-rows:minmax(0,1fr)`, added `min-height:0` to `.editor-col`/`.mon-col`, made `.term`
  `flex:1 1 0;min-height:0;overflow-y:auto`, and `flex-shrink:0` on both bars. Now lines scroll inside
  the monitor and the bars stay pinned.
**Left alone:** `dashboard/` and `cloud/map-viewer/` are Vite SPA shells (`<div id=root>`) on separate
dev servers — relative links would resolve to the dev server, not the Pi. Cross-links there belong in
the React components with the Pi's absolute URL (offered, not done).
**API page note (for the user's follow-up):** `/docs` is FastAPI's auto-generated Swagger UI (also
`/redoc`, `/openapi.json`); content derives from route decorators + docstrings in `app.py` and the
Pydantic models in `models.py`. WebSockets don't appear (OpenAPI limitation); `/` and `/command` are
`include_in_schema=False`. Extend by adding a model → route with `response_model=` + docstring + auth.
**Verified:** sim served, `/` and `/command` both 200 with nav markup present. (Scroll fix is a
CSS-only layout change — not browser-screenshotted.)
**Next steps:** not committed yet (offered). Still open: hardware test of `/pico/push` reconnect;
a real hardware entry point (live camera + real PicoSerial) — `run_sim.py` is the only runner.

## 2026-06-07 — Fixed /ws/health reconnect-loop when psutil is missing

**Worked on:** user reported "only the static dashboard opens" + the Pi showing a connection
open→close loop after the [[command-center]] commit (25c9234).
**Diagnosis (reproduced):** two things. (1) The command center is at **`/command`**, not `/` — `/` is
still the old static dashboard, so that's all they saw. (2) The open/close loop = `psutil` not
installed in their runtime: `_gather_health()` did a bare `import psutil`, which raised ImportError,
which `ws_health` caught by *exiting* → socket closed on connect → the page's auto-reconnect retried
every 2s → loop. (`/health` GET would also 500.) psutil was added to requirements last commit but not
yet `pip install`ed on their host (this Windows box has it; they're on the Pi / another venv).
**Changed:** `pi5/server/app.py` —
- `_gather_health()` now wraps the psutil block in try/except and degrades to None (UI shows N/A),
  same contract the vcgencmd fields already use off-Pi. A missing optional source must never raise.
- `/ws/health` loop catches per-tick errors and emits `{"error": ...}` while keeping the socket open,
  so no health failure can ever cause a reconnect loop.
**Verified:** monkeypatched psutil to ImportError → `_gather_health()` returns a clean dict (all None);
restarted sim, `/ws/health` holds open 4s. ruff clean.
**User action still needed:** `pip install -r pi5/requirements.txt` (psutil) in the venv that serves
the page for real CPU/RAM/disk numbers; open `/command` not `/`. Monaco/fonts are CDN — editor pane
needs internet on first load.
**Next steps:** not committed yet (offered). Still pending from prior entry: hardware test of
`/pico/push` reconnect.

## 2026-06-07 — Built the /command "command center" HUD (camera + Pi health + Pico terminal)

**Worked on:** implemented `~/Downloads/DREAMS_dashboard_update.md` — a single-page naval-HUD command
center served from the Pi 5 FastAPI app, combining MJPEG camera, Pi 5 health, and a Pico terminal.
**Key deviation from the instruction (it was written against a simpler mental model of the repo):**
applying it verbatim would have broken the running stack three ways, so I reused existing owners
instead of opening hardware twice —
- **Camera:** `/video` MJPEG **subscribes to the existing `CameraProducer` (`_camera`)** and
  re-encodes `frame.left` at JPEG q60; it does NOT open a second `VideoCapture(0)` (that would contend
  with the CV pipeline). No camera → streams a near-black placeholder JPEG; UI shows "NO SIGNAL".
- **Pico:** `/ws/pico` streams *parsed* frames (TEL/ENV/ALERT) off the existing `PicoSerial` (`_pico`)
  and dispatches real protocol commands (SET_THR/SET_WINCH/ESTOP/…); it does NOT open a second serial
  reader. Per the user's call, kept the **"Push to Pico" button**: `POST /pico/push` releases the port
  (heartbeats stop → Pico watchdog ESTOPs = safe), runs `mpremote fs cp :main.py` + reset, then
  reconnects. Hardware-only; refuses while a mission runs unless `?force=true`.
- **Route:** served at **`/command`** (per user) — left `/` (static/index.html) untouched.
- **Auth:** new endpoints reuse `auth.require_api_key`; `/video` + WS auth via `?key=` (an `<img>`
  can't send headers). `/health` left open as a liveness probe. Added tiny `auth.key_valid()` helper.
**Changed:**
- `pi5/server/app.py` — new: `/command`, `/health`, `/ws/health`, `/video`, `/ws/pico`,
  `/pico/files`, `/pico/push`, an asyncio health-gather loop (vcgencmd via async subprocess, psutil),
  MJPEG helpers, Pico command dispatch. All degrade cleanly off-Pi / in sim.
- `pi5/server/templates/command_center.html` (new) — self-contained HUD (Orbitron + IBM Plex Mono,
  Monaco editor from CDN, amber/cyan theme, scanline camera overlay, WS auto-reconnect w/ backoff).
- `pi5/server/auth.py` — added `key_valid()` (public wrapper for query-param routes).
- `pi5/requirements.txt` — added `psutil>=5.9`; noted `mpremote` as a Pi-side CLI dep.
**Verified (simulator, Windows):** `python run_sim.py`, then exercised every endpoint — `/health`
returns psutil data + N/A for Pi-only vcgencmd fields; `/command` serves 22 KB; `/video` streams valid
MJPEG placeholder frames; `/ws/health` + `/ws/pico` stream; `SET_THR 20 20`→ACK, unknown/badarg
commands error cleanly; `/pico/{files,push}` refuse gracefully in sim. `ruff check pi5` clean,
`pytest pi5/tests` 95 passed.
**Decisions / open questions:** the firmware-push handoff (`disconnect → mpremote → connect +
start_heartbeat`) is **untested on real hardware** — assumes the standard PicoSerial lifecycle; verify
on the Pi. Monaco loads from CDN (needs internet on first load). Not committed yet.
**Next steps:** hardware test of `/pico/push` reconnect; consider wiring `_camera`/health into the
hardware startup path; decide if `/command` should eventually replace `/`.

## 2026-06-07 — Committed and pushed the V2 working tree

**Worked on:** "is everything pushed?" → it wasn't (local main was even with origin, but a large
uncommitted/untracked V2 tree remained). Scanned for secrets, excluded junk, then committed + pushed.
**Secret scan:** clean — all matches were API-key *handling* (var names, FastAPI deps) and config
templates with empty values (`api_key: ""`, set via env var). No real secrets committed.
**Changed:**
- `.gitignore` — added KiCad local/temp artifacts (`*.lck`, `~*.lck`, `*.kicad_prl`, `.history/`,
  `fp-info-cache`, `*-backups/`) so they're never committed.
- Committed `14294ac` and pushed to `origin/main`: CLAUDE.md, the V2 docs set
  (changelog_and_decisions, hardware_changes_v1_to_v2, pcb_design_notes, session_journal),
  `Boat_PCB/` (kicad_pcb/pro/sch + report.txt), `firmware/boat-pico/status_led.py`, the two new
  Pi5 loop tests, edits to cloud/api, pin_map, main.py, network.py, stereo.py, run_sim.py, and the
  `docs/wiring_diagram.html` deletion. Also committed `.claude/hooks/journal_reminder.ps1`
  (settings.local.json stays gitignored).
**Excluded deliberately:** KiCad lock files, `Boat_PCB-backups/*.zip`, `Boat_PCB/.history/`,
`Boat_PCB.kicad_prl` — local/regenerable artifacts.
**Next steps:** this journal entry itself is committed in a follow-up. The two flagged hardware
discrepancies (battery dividers/GP28, winch power source) remain open.

## 2026-06-01 — Reviewed firmware/docs wiring against the Boat_PCB schematic

**Worked on:** verified the documented Pico pinout (`docs/pin_map.md`, firmware docstrings,
CLAUDE.md) against the actual `Boat_PCB/Boat_PCB.kicad_sch`.
**Method:** the schematic has zero net labels (connectivity is purely geometric), so exported a real
netlist with `kicad-cli sch export netlist --format kicadsexpr` (KiCad 10 at
`~/AppData/Local/Programs/KiCad/10.0/bin/kicad-cli.exe`) and parsed pin-to-pin nets from that.
**Findings — schematic disagrees with docs on almost every peripheral** (only GP10, GP26, GP27 match):
- GP0/GP1: docs say "DEAD", schematic wires them to a **Raspberry Pi 5 40-pin header (J3)** as a
  hardwired UART (Pi pins 8/10 ↔ Pico GP1/GP0) + 5V share — contradicts the "Pi 5 USB-only, no GPIO"
  locked decision. J3 is paralleled across the Pico sockets J14/J17 pin-for-pin.
- VESC/CAN-chain connector J2 is on **GP2–GP6**, not GP12/13. GP12/13 → J11 (Temp+Humidity/DHT).
- GP8/9 → J7 GPS+Compass (docs say I²C0 IMU). GP14/15 → shared bus across J7/J10(IMU)/J13.
- Hull leak is on **GP19/GP20** (J16/J15); docs assign GP17/18 — which are **unconnected**. GP16 also
  unconnected though docs assign it to DHT11.
- **GP28 IS wired** (4S-winch divider R8 100k/R10 18k → R9 → GP28), despite docs calling it "spare".
- Dividers: schematic = 220k/13k (12S), 100k/30k (3S), 100k/18k (4S) — the schematic side of the
  known divider discrepancy ([[battery-divider-discrepancy]] firmware uses 3.3k/47k, 15k/100k).
- **Winch wiring looks broken:** BT4 (4S) → fused → **J6 (valued "6s output")**, while J8 "Winch ESC"
  and J9 "Winch ESC RC" have **both pins on GND** (no +supply/signal). Concrete instance of the
  unresolved winch-power flag — likely a real error.
- Sensor power = VSYS (fed from Pi5 5V via J3.2/3.4); Pico 3V3-OUT (pin36) unconnected — possible
  3.3V-part-on-5V supply concern.
**Decisions / open questions:** did NOT edit any docs — this is a doc-vs-schematic conflict the user
must adjudicate (which is source of truth?). Bus *roles* (SDA/SCL, TX/RX) were inferred from pin
position; the pin→connector connections are exact from the netlist.
**Next steps:** user to decide — regenerate `docs/pin_map.md` from the schematic, or produce a
`docs/pin_map_vs_schematic.md` discrepancy doc. Confirm J8/J9 winch by reading raw schematic symbols.
Note: the exported `boat_netlist.net` was a scratch artifact and was deleted.

## 2026-06-01 — Added the session journal mechanism

**Worked on:** set up a way for each Claude session to record what it did so future chats can pick up
where the last one left off.
**Changed:**
- `docs/session_journal.md` (new) — this file; running newest-first log with an entry template.
- `CLAUDE.md` — added a "Session Journal — read at start, write at end (REQUIRED)" section near the
  top instructing every agent to read this file first and append an entry when finishing.
- `.claude/hooks/journal_reminder.ps1` (new) — Stop hook script; blocks the first stop with a
  reminder to update this journal, allows the re-entrant stop (no loop).
- `.claude/settings.local.json` — wired the script in as a `Stop` hook (exec form, PowerShell).
  Note: this file is gitignored, so the hook is personal to this machine, not shared with teammates.
**Decisions / open questions:** journal stays a *narrative* of in-progress work; locked decisions
remain in `docs/changelog_and_decisions.md`. Enforcement hook lives in local (personal) settings —
move to a committed `.claude/settings.json` if the team should share it.
**Next steps:** future sessions — read this file first, append your entry last. Nothing in this
session is committed yet (journal + CLAUDE.md + hook sit alongside the uncommitted V2 work).

---

## 2026-06-01 — Context snapshot of uncommitted work (summarized from git, not done this session)

> Recorded so the next chat understands the current working-tree state. These changes were already
> present (uncommitted) when the journal was created; descriptions are inferred from `git status` /
> `git diff --stat`, so verify against the diff before relying on the "why."

**In the working tree, not yet committed:**
- **New docs (untracked):** `docs/changelog_and_decisions.md`, `docs/hardware_changes_v1_to_v2.md`,
  `docs/pcb_design_notes.md`, and `CLAUDE.md` — the V2 hardware/architecture documentation set.
- **`docs/wiring_diagram.html` deleted** (~917 lines) — replaced by the Mermaid `system_tree.md` and
  the new pcb/pin docs.
- **`Boat_PCB/` (untracked):** KiCad 10 project for the main carrier board.
- **Firmware:** `firmware/boat-pico/status_led.py` (new, WS2812 NeoPixel on GP10) and ~45 new lines in
  `firmware/boat-pico/main.py`.
- **Tests (untracked):** `pi5/tests/test_mission_loop.py`, `pi5/tests/test_navigator_loop.py`.
- **Smaller edits:** `cloud/api/{app,database,models}.py`, `pi5/comms/network.py`, `pi5/cv/stereo.py`,
  `run_sim.py`, `docs/pin_map.md`.

**Open items carried forward** (see `docs/changelog_and_decisions.md` and CLAUDE.md discrepancy notes):
- Battery-divider / GP28 mismatch between the `Boat_PCB` schematic and `firmware/boat-pico/sensors.py`.
- Unresolved winch power source (dedicated BT4 4S vs. J6 "6s output" / 12S midpoint tap).
**Next steps:** decide whether to commit the V2 docs + journal together; resolve the two flagged
hardware discrepancies.
