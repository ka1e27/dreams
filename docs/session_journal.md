# D.R.E.A.M.S — Session Journal

A running log of what each Claude Code session worked on. **Read this top-to-bottom at the start
of every session** to understand recent work, then **append a new entry at the end of the session**
describing what you did.

- Newest entries go at the **top** (just under this header), so the most recent context is read first.
- Keep entries short and factual — what changed and why, not a transcript.
- This is a *narrative* of work-in-progress. For locked decisions and the architecture-of-record,
  see `docs/changelog_and_decisions.md`; for hardware deltas, `docs/hardware_changes_v1_to_v2.md`.
  Don't duplicate those here — link to them.
- **This file holds only the 5 most recent entries.** When appending pushes the count past 5, move
  the oldest entry (or entries) to the top of `docs/session_journal_archive.md`'s entry list, keeping
  it newest-first there too. The archive isn't read automatically at session start — only pull from
  it if you need context on something specific from further back.

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

<!-- New entries below this line, newest first. Keep at most 5 — move older ones to
     docs/session_journal_archive.md. -->

## 2026-07-07 — Stereo calibration 0.5m vs 0.32m — ROOT CAUSE & FIX

**Worked on:** user reported stereo calibration finding 0.5m baseline instead of actual 0.32m. Diagnosed and resolved.
**Changed:**
- `pi5/config.yaml` line 156 — `fourcc: "YUY2"` → `"MJPG"` (Camera 2 only supports MJPG at 1920×1080; codify the actual format)
- Identified root cause: Camera 0 negotiated YUY2, but Camera 2 fell back to MJPG (doesn't support YUY2 at 1920×1080)
- Mismatched formats → MJPG artifacts → inconsistent corner detection → wrong T solved by stereoCalibrate
**ROOT CAUSE:**
- `pi5/config.yaml` line 156 set `fourcc: "YUY2"`
- Camera 0: accepted YUY2 ✓
- Camera 2: refused YUY2 @ 1920×1080, silently fell back to MJPG ✗
- Calibration script also defaulted to `--fourcc YUY2`, so it captured left-camera (YUY2) vs right-camera (MJPG) mismatch
- Different formats → different image artifacts → corners detected at different positions → stereoCalibrate solved for wrong T
**Fix (two parts):**
1. Re-run calibration with matched format: `python -m pi5.scripts.calibrate_stereo --baseline 0.32 --square 0.024 --width 1920 --height 1080 --fourcc MJPG --out pi5/cv/calibration.npz`
2. Update `pi5/config.yaml` line 156: `fourcc: "MJPG"` (codify what Camera 2 actually uses; eliminates fallback mismatch)
**Result:** ✓ FIXED baseline. Calibration printed `Baseline (||T||): 0.3163 m  (expected ~0.32)` — **1.2% error, excellent**. `pi5/cv/calibration.npz` baseline is correct.
**New issue found (ROOT CAUSE OF 2.25× DEPTH ERROR):** still have format mismatch! Camera 0 refuses MJPG @ 1920×1080 and reverts to YUY2, while Camera 2 uses MJPG. This breaks corner detection again → wrong focal length in K → wrong Q → 2.25× depth error. The two cameras have **incompatible format support at 1920×1080** (Camera 0 wants YUY2, Camera 2 wants MJPG).
**Fix attempted:** updated config to 1280×720 with YUY2.
**New blocker:** Camera 0 refuses to downscale — stays at 1920×1080 while Camera 2 accepted 1280×720. Cameras now at different resolutions (breaks stereo).
**Root cause:** Camera 0 likely only supports 1920×1080 (no binning modes), or driver won't allow resolution changes via OpenCV.
**Current status:** stereo calibration impossible — cameras must be same resolution + same format.
**Root cause (Windows-specific):** DirectShow backend (Windows) doesn't expose lower resolution modes that V4L2 (Linux) does. Camera 0 likely supports 1280×720 binning on Linux but DirectShow only advertises 1920×1080 modes, so Windows OpenCV can't request the lower res.
**Decision:** use WSL2 (Windows Subsystem for Linux 2) for calibration instead of separate Linux machine. WSL2 has better USB support than Docker and V4L2 works properly.
**Calibration on WSL2 (final command):**
```bash
python3 -m pi5.scripts.calibrate_stereo --baseline 0.32 --square 0.024 \
    --width 1920 --height 1080 --fourcc YUY2 \
    --rows 7 --cols 10 --left 0 --right 2 \
    --out pi5/cv/calibration.npz
```
Checkerboard: 7×10 inner corners (8×11 squares). Cameras: left=0, right=2. Resulting `calibration.npz` shared between WSL2 and Windows, usable on both platforms.

## 2026-07-06 — Three-tier vision pipeline (water seg → threat assessment → radar)

**Worked on:** built the three-tier survey vision pipeline from
`DREAMS_vision_pipeline_instruction`. The instruction is a generic template that overlapped heavily
with code that already exists (YOLO detection, per-box stereo distance, and radar tracking are all
already wired via `DetectionOverlay` + `RadarTracker`). Confirmed two reconciliations with the user
before building: (1) **layer on the existing overlay** — do NOT run a second YOLO (Pi is
inference-bound); (2) **in-memory + WebSocket** for threat/survey output — no cloud DB or `pico.write`
exists in the runtime, and the framed serial protocol has no THREAT command.
**Changed:**
- `pi5/cv/segmentation.py` (NEW) — Tier 1 `WaterSegmentation`: classical OpenCV HSV/edge fallback
  (no model needed) + a TFLite path if `water_seg.tflite` + a tflite runtime are present. Returns
  `SegResult` (water_state, anomaly_score, anomaly_regions). Fixed the template's `frame.size` bug
  (measures against H·W pixel count, not H·W·3).
- `pi5/cv/threat_assessor.py` (NEW) — `ThreatLevel`/`THREAT_LEVELS`, `TrackedObject`, `ThreatAssessor`:
  nearest-centroid identity across frames, approach-vector detection (APPROACHING/STATIC/RECEDING),
  priority ordering, `should_engage_tracking`, `get_mission_alert`.
- `pi5/cv/pipeline.py` (NEW) — `SurveyVisionPipeline` coordinator: own async loop subscribing to the
  camera; Tier 1 seg **gates** the existing overlay's YOLO (with a cooldown hold so it doesn't
  flicker); reads `overlay.boxes()` (label+conf+distance already there) as Tier 2/3; drives the
  **existing** `RadarTracker` via `set_track_class`/`set_mode` (never rewrites it); `vision_state()`,
  `threats()`, `annotate()` (water-state banner, anomaly bar, tier dots, threat highlight).
- `pi5/server/app.py` — `configure(pipeline=)` + `_pipeline` global; `vision` block in the health
  WS payload; `GET /vision/status`, `GET /vision/threats`, `POST /vision/{yolo,segmentation}/toggle`;
  `_mjpeg_stream` now calls `pipeline.annotate()` on the left view; `/api/camera` `detection_enabled`
  now routes to `pipeline.set_yolo_enabled` (pipeline owns `overlay.enabled` when gating).
- `run_hardware.py` — constructs `SurveyVisionPipeline`, injects via `configure`, starts it after the
  overlay and stops it before, all degrade-gracefully.
- `pi5/config.yaml` — new `vision:` block (thresholds, `gate_yolo_on_anomaly`, threat_tracking,
  survey_logging).
- `pi5/server/templates/command_center.html` — new "◈ VISION PIPELINE" `.section` panel (water state,
  anomaly bar, 3 tier dots, SEG/YOLO toggle buttons with high-CPU ⚠ warning, primary-threat readout,
  survey counter); `renderVision(h.vision)` in `renderHealth`; CRITICAL threat folded into the
  existing `showBanner` chain (auto-dismisses beyond 50 m). **Follow-up:** merged the camera-feed
  control bar (`.cam-ctl`: SOURCE / DEV L·R / DETECT / TRACK / DET FPS / IMG / CONF / QUALITY /
  STREAM FPS) out of the CAMERA FEED section and into this panel, renamed "◈ VISION & CAMERA
  CONTROL" — one unified control area; CAMERA FEED is now just the live image. All element IDs
  preserved so the JS is unchanged; verified div balance + no duplicate IDs.
- `pi5/tests/test_vision_pipeline.py` (NEW) — 20 tests (segmentation, threat assessor, pipeline
  engage/disengage, endpoints shape). Built as pytest, not the standalone script the instruction
  sketched, to fit the repo.
**Decisions / open questions:**
- **`pi5/cv/camera.py` deliberately NOT modified** — the instruction said to replace a `model(frame)`
  call there, but `camera.py` is only the `CameraProducer`; YOLO lives in `vision_overlay.py`. The
  real integration point is `run_hardware.py` + `app.py`.
- **Behaviour change to flag:** with `vision.gate_yolo_on_anomaly: true` (default) the pipeline now
  owns `overlay.enabled`, so detection boxes appear only when Tier 1 sees an anomaly (real tiering,
  saves CPU on clear water). Set it `false` to restore always-on YOLO.
- **Deferred:** Pico mission-alert over serial — needs a new THREAT command in
  `firmware/boat-pico/serial_handler.py` + `docs/serial-protocol.md` (instruction said don't touch
  `firmware/`). CloudUploader isn't wired into `run_hardware.py`, so survey rows only increment an
  in-memory counter today; `pipeline._push_survey` is ready to call `uploader.add_reading` if one is
  injected later. No `water_seg.tflite` model exists — classical fallback is live.
**Verified:** `py_compile` all files; `ruff check` clean; `pytest pi5/tests` → **117 passed** (97 prior
+ 20 new); import/wiring smoke test (config accepts `pipeline=`, 4 `/vision/*` routes registered);
end-to-end through the FastAPI `TestClient` — `/vision/status`, `/vision/threats`, and both toggle endpoints
return correct shapes and flip state. Not yet run against a live camera.
**Next steps:** run `run_hardware.py` on the Pi with cameras, confirm the VISION panel populates, the
SEG/YOLO toggles work, and a real vessel/person triggers the threat banner + radar TRACK. If always-on
detection boxes are preferred over tiering, set `vision.gate_yolo_on_anomaly: false`. Consider wiring
a `CloudUploader` + a serial THREAT command if survey persistence / FSM alerts are wanted.

## 2026-07-01 — Per-object distance on detection boxes (stereo depth)

**Worked on:** user asked for each detected object's bounding box to show its distance (e.g. next to
a detected person). Built on the just-fixed stereo pipeline (`StereoDepth`, `calibration.npz`).
**Changed:**
- `pi5/cv/vision_overlay.py` — `DetectionOverlay.__init__` gains an optional `stereo: StereoDepth`
  param. `_infer(frame_bgr, right_bgr=None)` now runs one `StereoDepth.compute()` disparity pass per
  inference cycle (not per box) when a stereo pair + calibration are available, then looks up each
  box's `median_depth_in_bbox()`; box tuples grew an 8th field `distance_m` (`None` if unavailable —
  confirmed backward-compatible with `radar_tracker.py`/`primary_target()`, which only read indices
  0–6). `_loop` now passes `frame.right` through to `_infer` alongside `frame.left`. `draw()` renders
  `"person 87% 3.2m"` when distance is known, else the old `"person 87%"`. `detections()` /
  `primary_target()` dicts gained a `distance_m` key.
- `run_hardware.py` — loads `pi5/cv/calibration.npz` at startup (only if a right camera is configured)
  and constructs a `StereoDepth`, passed into `DetectionOverlay(..., stereo=stereo_depth)`. Degrades
  gracefully: no calibration file or no right camera → no distance column, never a crash.
**Decisions / open questions:** this adds one `StereoSGBM.compute()` per inference cycle (capped by
`detect_max_fps`, default 8/s) on top of YOLO — real CPU cost at 1920×1080. Flagged to the user as a
performance tradeoff; if the feed feels sluggish, lower `detect_max_fps` or `imgsz` in `config.yaml`.
**Verified:** `py_compile` on both files; `pytest pi5/tests` → 97 passed (no test referenced the old
7-tuple box shape by length, only by index, so the added field is safe).
**Next steps:** user to restart `run_hardware.py` and confirm distances show up on the left camera feed
for detected people/boats.

## 2026-07-01 — Fixed right-view box misalignment; added live stereo depth view

**Worked on:** after calibration completed, user reported (1) no depth showing anywhere when running
`run_hardware.py`, and (2) detection boxes on the RIGHT camera view looked misaligned.
**Findings (before changing anything):**
- (2) is NOT a bug — `pi5/server/app.py`'s `_mjpeg_stream` already had a comment explaining detection
  only ever runs on the LEFT frame (Pi is inference-bound, no second YOLO pass), and the same box
  coordinates were being drawn on the right view too — at a 320mm baseline, nearby objects have real
  parallax shift, so the boxes visibly sat in the wrong place on that view. Confirmed via
  `AskUserQuestion`: user wants boxes hidden on the right view rather than a second inference pass.
- (1) is because the depth pipeline (`pi5/cv/avoidance.py`'s `AvoidanceLoop` + `StereoDepth`) was never
  actually wired into `run_hardware.py` — it's fully-built dead code, never constructed/started. The
  only place calibration got loaded was the unused `/ws/camera?cam=disparity` WebSocket route, which
  nothing in the UI ever called. Confirmed via `AskUserQuestion`: user wants a live depth *view* in the
  UI (not full obstacle-avoidance wiring, which would double YOLO inference cost on this hardware).
**Changed:**
- `pi5/server/app.py` — `_mjpeg_stream`/`/video`: detection overlay boxes now draw on the LEFT view
  only (right view streams clean). Added `_get_stereo_depth()` (lazy-loads `pi5/cv/calibration.npz` +
  builds a `StereoDepth` once, shared across viewers, sticky-fails if the file's missing) and a new
  `cam=disparity` option that computes live `StereoSGBM` disparity → `COLORMAP_TURBO` colormap per
  frame (falls back to left if no right camera or no calibration).
- `pi5/server/templates/command_center.html` — new "◈ DEPTH" button next to LEFT/RIGHT in the camera
  SOURCE control (disabled when no right camera, same as RIGHT); `setCam()`/device-swap/rescan call
  sites updated to treat `disparity` like `right` for the "needs a right camera" fallback logic;
  `cam-det` (detection readout) now shows only on the left view, matching the new server behaviour.
**Decisions / open questions:** did NOT wire `AvoidanceLoop` into `run_hardware.py` — that remains
unused dead code (`pi5/cv/avoidance.py`, `pi5/cv/detector.py`'s `BoatDetector`) with its own
`config.yaml` `avoidance:` block already defined but unread. If real steer-away obstacle avoidance is
wanted later, that's the next piece — it needs a second YOLO pass (BoatDetector loads its own model
separately from the command-center's `DetectionOverlay`), so evaluate inference cost on the target
hardware first.
**Next steps:** restart `run_hardware.py`, click ◈ DEPTH in the command center, confirm the colormap
looks sane (near=one color, far=another) — if it's flat/uniform, the calibration solve may need
redoing with more/varied checkerboard positions.

## 2026-07-01 — Stereo vision review + Windows camera resolution fix (DSHOW FOURCC/size ordering)

**Worked on:** user asked about stereo vision (confirmed StereoSGBM pipeline exists), calibration setup with 320mm baseline, and why camera 0 wasn't setting to 640×480 on Windows startup (stayed at native 1920×1080; camera 2 was fine).
**Changed:**
- `pi5/cv/camera.py` — `_open()`: explicit `cv2.CAP_DSHOW` backend on Windows; added default-vs-actual resolution debug logging. **Root-cause fix:** on Windows, FOURCC was being set *before* width/height — DirectShow negotiates the capture pin as one combined (W, H, FourCC) mode, and if that exact combo isn't a discrete mode on the camera, DSHOW silently keeps native resolution instead of erroring (this is what camera 0's log showed: `fourcc=?` empty, stuck at 1920x1080). Fixed by setting width/height *first* on Windows, then FOURCC, then re-applying width/height after (in case setting FOURCC reset the pin). Linux/V4L2 path unchanged (V4L2 wants FOURCC pinned first).
**Findings:**
- Stereo vision complete: `pi5/cv/stereo.py` (StereoSGBM), `pi5/cv/camera.py` (dual USB), `pi5/scripts/calibrate_stereo.py` (calibration).
- Calibration command: `python -m pi5.scripts.calibrate_stereo --baseline 0.32 --square 0.025 --out pi5/cv/calibration.npz` (9×6 checkerboard, ≥10 pairs, 320mm baseline).
**Decisions / open questions:** the FOURCC/size-ordering fix did NOT resolve camera 0 being stuck at 1920x1080 (device 0 likely has no 640×480 mode via DirectShow at all — 1080p-only camera). Rather than chase a swap/format issue, **user decided to run both cameras at their native 1920×1080** instead of forcing 640×480.
**Changed (this follow-up):**
- `pi5/config.yaml` — `camera.width`/`camera.height` → `1920`/`1080` (both cameras use native res now); added a note that uncompressed YUY2 at 1080p30 needs USB 3.0 bandwidth per camera, fall back to `fourcc: "MJPG"` if frames stall; `camera.baseline_m` → `0.32` (was stale at `0.12`; corrected to match the user's actual measured 320mm stereo baseline — this is informational only, the real depth math comes from the calibration `.npz`).
**Next steps:** restart the camera producer to pick up 1920×1080; run `pi5.scripts.calibrate_stereo --baseline 0.32` to generate `pi5/cv/calibration.npz` (checkerboard, ≥10 pairs) now that both cameras share the same resolution. Watch USB bandwidth/fps with YUY2 at 1080p on both cameras simultaneously — may need MJPG or a powered USB 3.0 hub.
**Follow-up fix:** `calibrate_stereo.py` crashed on `cv2.imshow` with "function is not implemented... Rebuild the library with Windows, GTK+... support" — caused by `opencv-python-headless` (no GUI support) being installed in the user site-packages (`AppData\Roaming\...`), shadowing the full `opencv-python` (GUI-capable) install in system site-packages, since user site-packages take precedence. Fixed by `pip uninstall -y opencv-python-headless`. If some other dependency reinstalls the headless variant later, this will recur — worth checking `pi5/requirements.txt` doesn't pull it in transitively.
**Follow-up fix #2:** after that, calibration ran but showed low framerate and no green checkerboard corners. `pi5/scripts/calibrate_stereo.py` — added `_open()` mirroring `pi5/cv/camera.py`'s explicit `CAP_DSHOW`/width-before-fourcc-before-width-again ordering (script was previously using plain `cv2.VideoCapture(index)` with no format hints, so Windows negotiated a slow default mode); added `--width/--height/--fourcc` args (defaults 1920/1080/YUY2, matching `config.yaml`) so calibration runs on the same feed the runtime sees; added `--detect-scale` (default 0.5) — chessboard search now runs on a downscaled copy with `cornerSubPix` refinement back at full res, since full-res search at 1080p was the main perceived-freeze cause; added `CALIB_CB_FAST_CHECK`/`ADAPTIVE_THRESH`/`NORMALIZE_IMAGE` flags. Also flagged in the updated usage docstring: `--rows`/`--cols` are *inner corners* (where black squares meet), not square count — miscounting this is the likely reason no corners were detected at all (e.g. `--rows 8 --cols 11` only correct if the board truly has 8×11 inner corners, not 8×11 squares).
**Next steps:** user to recount actual checkerboard inner corners and re-run with `--width 1920 --height 1080 --fourcc YUY2` added to the command.
**Follow-up (calibration completed):** user ran the fixed calibration script successfully — verified `pi5/cv/calibration.npz` exists (24 MB, freshly written). Confirmed the depth pipeline is already fully wired end-to-end: `pi5/server/app.py:574` loads the calibration and constructs `StereoDepth`, which `pi5/cv/avoidance.py` already calls via `median_depth_in_bbox()` to get real-world obstacle distance — no code changes needed there.
**Next steps:** (1) sanity-check the calibration solve's printed baseline (`Baseline (||T||): ...`) was close to 0.32 m — if far off, recapture with more/varied checkerboard positions; (2) restart `run_hardware.py` so `app.py` picks up the new `.npz` (loaded once at startup); (3) real-world test — point cameras at something at a known distance and confirm a detected bbox reports roughly the right depth in logs/command center, not `None`.

## 2026-07-01 — Live camera assignment: pick which connected camera is LEFT/RIGHT + rescan

**Worked on:** user asked to be able to assign any connected USB camera as the left or right eye and
to refresh the list when new cameras are plugged in. Previously the indices were hardcoded in
`config.yaml` and changing them needed a restart.
**Changed:**
- `pi5/cv/camera.py` — `scan_devices()` (blocking; Linux scans /dev/video* with a grab test that
  filters UVC metadata-only nodes and reads names from sysfs, elsewhere probes indices 0..7);
  `CameraConfig.right_device` now nullable (single-camera rig, stereo off);
  `CameraProducer.set_devices(left, right)` swaps devices live — the swap is queued and applied by
  the capture loop itself (it owns the VideoCapture handles, so no mid-read races), failed opens fall
  through to the existing auto-reconnect; plus `device_map` / `active_devices()` accessors.
- `pi5/server/app.py` — `GET /api/camera/devices` (rescan on every call = the refresh; devices held
  open are reported in_use, an assigned-but-dead device is still listed) and
  `POST /api/camera/devices {left, right|null}` (validates, live-swaps, persists to
  `pi5/server/camera_devices.json` atomically); `_camera_state()` now includes left/right indices.
- `run_hardware.py` — restores the persisted assignment on startup (overrides config.yaml); also
  fixed the `right_device` default mismatch (was 1, config.yaml says 2).
- `pi5/server/templates/command_center.html` — camera bar gains DEV L / DEV R selects (R has NONE),
  SET (apply + toast with per-camera not-responding status) and ⟳ RESCAN buttons; the CAM-N tag now
  shows the real assigned device index instead of hardcoded CAM-0/CAM-1.
- `pi5/config.yaml` comment + `.gitignore` (`camera_devices.json`).
**Verified:** ruff + 97 pytest pass; real-webcam end-to-end on this laptop: `scan_devices` found 3
devices, live swap left↔right mid-stream delivered frames from the new devices, single-camera mode
works; curl of both endpoints (validation, persistence) against a harness server; sim mode returns
`available:false` / 503 gracefully; Playwright drove the live UI — selects populate, RESCAN toasts,
SET swaps and enables the RIGHT view button, zero console errors. Note: an earlier stale sim server
from a previous session was still holding port 8000 serving old code — killed it.
**Decisions / open questions:** persistence is a server-side JSON next to `saved_paths.json` (same
atomic-write pattern) rather than rewriting config.yaml, so YAML comments survive. The React
`dashboard/` app was left untouched — the command center is the UI in active use.
**Next steps:** none pending.

<!-- Older entries (commit/push housekeeping, align-first steering, waypoint planner page, M18 battery migration, token-bloat audit,
     third-downloaded-file audit, repomix/rtk, token-optimization config pass) live in
     docs/session_journal_archive.md. -->
