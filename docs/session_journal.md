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

## 2026-07-21 — Commit/push three-tier survey vision pipeline

**Worked on:** reviewed a pile of pending working-tree changes (from a prior session) and committed/pushed the intended ones; left tool clutter untracked.
**Changed:**
- `pi5/cv/pipeline.py`, `pi5/cv/segmentation.py`, `pi5/cv/threat_assessor.py` (new) — three-tier survey vision: Tier 1 cheap water-segmentation anomaly screen (classical OpenCV HSV/edge fallback, optional TFLite model), Tier 2 existing YOLO overlay now gated on the Tier-1 anomaly trigger, Tier 3 threat assessor turning detections into distance/approach-vector radar tracking + mission alerts.
- `pi5/tests/test_vision_pipeline.py` (new) — unit tests for the pipeline.
- `pi5/config.yaml` — added `vision:` block (seg model path, anomaly threshold, YOLO cooldown/gating, threat_tracking and survey_logging sub-configs).
- `pi5/server/app.py`, `pi5/server/templates/command_center.html`, `run_hardware.py` — wired the vision pipeline into the server/UI and hardware runner.
- `Boat_PCB/Boat_PCB.kicad_sch`, `Boat_PCB/Boat_PCB.kicad_pcb` — carried forward schematic/layout edits from the M18 three-domain battery migration (already decided in prior sessions; see `docs/battery_architecture.md`).
- Left untracked and did NOT commit: PCB export zip duplicates (`Boat_PCB/Boat_PCB V1.zip`, `V2*.zip`, `V2/`) and various editor/AI-tool config dirs (`.cursor/`, `.gemini/`, `.kiro/`, `.qoder/`, `.opencode.json`) — user chose "only commit real project changes" when asked.
**Decisions / open questions:** `.claude/` (hooks, settings, skills) and `.mcp.json` were also left untracked per the user's choice — worth a follow-up decision on whether Claude Code project config should be versioned in this repo.
**Next steps:** if the vision pipeline needs the optional TFLite model (`pi5/cv/models/water_seg.tflite`), it isn't in the repo yet — classical fallback is active by default. Confirm the KiCad schematic resistor-divider values now match `docs/battery_architecture.md` (previous entries flagged the schematic as carrying old values).

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

<!-- Older entries (stereo vision review + Windows camera fix, live camera assignment, commit/push housekeeping,
     align-first steering, waypoint planner page, M18 battery migration, token-bloat audit,
     third-downloaded-file audit, repomix/rtk, token-optimization config pass) live in
     docs/session_journal_archive.md. -->
