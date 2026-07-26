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

## 2026-07-25 — Deep review: LOS nav, obstacle avoidance wired, vision perf, Abyssal Indigo UI

**Worked on:** user asked for an extremely thorough review + make it run *great*, research-backed
vision/nav optimization, and a non-orange UI redesign. This session's changes were **run + tested**
(venv pytest: 123→144 green, ruff clean, sim booted and probed live in-browser). Full write-up in
`docs/code_review_2026-07.md`.
**Changed:**
- **Obstacle avoidance was dead code** — `AvoidanceLoop` (ran a *duplicate* YOLO) was never
  instantiated and the pipeline never steered around threats. Rewrote `pi5/cv/avoidance.py` into a
  pure, tested `reactive_avoidance()` rule (bearing+range → slow & bear away; head-on → starboard per
  COLREGS); `pi5/cv/pipeline.py` now pushes a steer-away override into the navigator (wired
  `navigator=nav` in `run_hardware.py`). Live **AVOID** toggle + `POST /vision/avoidance/toggle`.
- **Navigation:** added lookahead **LOS + ILOS** guidance and cross-track error to
  `pi5/navigation/geo.py`; `Navigator.compute_throttle` steers to the LOS course when a leg start is
  given (legacy point-at-target kept for no-leg + old tests); `MissionManager` anchors each leg to the
  previous waypoint. New `test_los.py` (10 tests incl. convergence rollout) + `test_avoidance.py` (11).
- **Config gap:** `run_hardware.py` ignored the whole `navigation:` block — added `_nav_config()`.
  New config keys: `navigation.los_*`, `camera.stereo_wls`, `vision.reactive_avoidance` (replaced the
  stale top-level `avoidance:` block).
- **Vision perf:** new `pi5/cv/ort_utils.py` (ONNX Runtime graph-opt=ALL + 4-thread + XNNPACK) used by
  the detector and segmenter; `pi5/cv/stereo.py` SGBM 3-way + preFilterCap + optional WLS disparity
  filter for textureless water (`opencv-contrib`, graceful fallback).
- **UI:** rethemed `command_center.html` + `waypoint_planner.html` from amber → **Abyssal Indigo**
  (0 residual orange, verified in-browser, no console errors); added AVOID toggle + Cross-Track
  telemetry readout. `NavStateOut` gains `cross_track_m`/`course_deg`/`avoiding`.
- **Docs:** `docs/vision_optimization.md`, `docs/navigation_guidance.md`, `docs/code_review_2026-07.md`.
**Follow-up (same session — user asked for tasks 1 & 2 + a drive-battery change):**
- **Stereo sync (review A4):** `CameraProducer` now grabs both handles back-to-back then decodes both
  (`_grab_retrieve` + `_account`), cutting stereo capture skew from a decode-time to ~one grab
  (`test_camera.py`).
- **Sim obstacle injection:** new `pi5/navigation/sim_obstacles.py` (`ObstacleField` + `SimAvoider`)
  drives the real reactive rule into the real navigator from ground truth; wired into `run_sim.py`
  (~4 Hz task) + `GET/POST/DELETE /api/sim/obstacles` + a **DROP OBSTACLE** map button. Avoidance now
  runs end-to-end in sim, and faithfully shows the reactive **local-minimum** limit (a hazard dead on
  the goal line is orbited, not passed — collision-free but no progress; documented, VFH/bug planner is
  the upgrade). Gave `min_forward_frac` a 0.2 default so the boat arcs vs stalls.
- **Drive battery → 2× M18 PARALLEL (18 V)** for the twin 2814 motors (was 2× series 36 V): firmware
  `sensors.py` thresholds → single-M18 (21/15/17/16), `INV_P_RATIO` kept 14.0 (existing 130k/10k divider
  reads 21 V→1.5 V correctly — no resistor rework; 56k/10k+6.6 optional). Updated `config.yaml`,
  `simulator.py` (drive now ~20.5 V/91 %, verified live), `docs/battery_architecture.md`, `CLAUDE.md`.
  Gotcha documented: 2× parallel = 18 V is **below 6S (22 V)**, so the 2814s make less than their
  1330 W/6S rating; cap VESC **battery** current per motor (~45 A on HO 6Ah) so the two don't overdraw
  the pair. Added `navigation.motor_gain_left/right` per-motor trim for the different-Kv 2814s
  (`Navigator._trim`, tested); the heading loop nulls the residual crab.
**Follow-up 2 (same session — user asked for the bug escape + confirmed plain ESCs):**
- **Bug-style escape** (`pi5/cv/avoidance.py:AvoidanceController`): wraps the memoryless reactive rule
  with commit-to-a-side + pass-detection (bearing behind the beam when tracked, or a blind `pass_hold_s`
  when sight is lost). `reactive_avoidance` gained `force_side`. Wired into `SimAvoider` (tracks the
  committed obstacle 360° so release is exact) and `pipeline._drive_avoidance`. Result: the boat now
  **routes past** a dead-centered blocking obstacle to the waypoint (was orbiting) — verified against the
  real `BoatSimulator` motion model (centered + offset, minsep ~8.8 m vs 4 m radius, arrives). New config
  `vision.reactive_avoidance.pass_bearing_deg/pass_hold_s`; +5 controller tests.
- **Drive = ESCs off the Pico (no VESC), identified as NeutronRC 70A-G071 (AM32).** Firmware already does
  plain PWM ESCs (`firmware/boat-pico/escs.py`, GP2/GP3, 50 Hz servo PWM) — no code change; the -1..1→
  1.0-2.0 ms mapping already matches AM32 bidirectional mode. These are AM32 (STM32G071) crawler/robot
  ESCs, NOT "dumb": configurable firmware with current telemetry + protections, so I corrected the earlier
  VESC/dumb-ESC framing. New **`docs/esc_setup.md`** — the required AM32 config: **Bi-directional mode ON**
  (else reverse pulses idle and the boat can't pivot/back away — the navigator commands negative throttle),
  5S LVC, low-RPM-power-protect OFF, stall/brake tuning, current limit ~45 A/motor if the AM32 build has it.
  The pack (~90 A HO-6Ah pair) is the tighter limit vs the 70 A ESCs. Updated `escs.py` docstring,
  `docs/battery_architecture.md`, `CLAUDE.md`. Kv trim via `motor_gain_*` + firmware `COMP_L/COMP_R`.
Suite now **164 green**, ruff clean.
**Follow-up 3 (same session — user asked to build the AM32 passthrough to test on the Pi later):**
- **AM32 ESC passthrough through the Pico** — configure the drive ESCs in place (no USB linker), like
  FC BLHeli/AM32 passthrough. `firmware/boat-pico/esc_passthrough.py`: a **PIO half-duplex one-wire UART**
  on GP2/GP3 + a transparent USB-CDC↔ESC bridge; entered via a new `ESC_PASS,<esc>,<baud>` serial command
  (mirrors the REFLASH pattern — stops motors, cancels tasks, hands over the CDC, `machine.reset()` on
  exit). Pi driver `pi5/scripts/esc_passthrough.py` (`enter` for the am32.ca workflow — am32.ca connects
  straight to /dev/ttyACM0; `probe`/`scan` for scripted bring-up + baud discovery). Doc
  `docs/esc_passthrough.md` with the ordered validation plan (PIO UART loopback → baud scan → am32.ca).
  **⚠ UNTESTED — no hardware yet.** Firmware py_compiles, Pi script ruff-clean. Research: AM32 signal-line
  is a BLHeli-derived one-wire link (am32.ca "Arduino PC Link" ref); baud not publicly pinned → parameterised
  + `scan` sweeps it. Risky bits (PIO timing, half-duplex turnaround, baud, bootloader-entry) isolated +
  flagged for on-Pi iteration.
- **User plans to install Claude Code on the Pi** to run the hardware-in-the-loop validation (real Pico +
  ESC). That closes most of the "verify on Pi later" gaps (camera FPS, serial link, and this passthrough).
- **⚙ MOTORS button** added to the command center (COMMANDS→DRIVE) → a Motor Configuration modal:
  per-motor **trim** (fully working — `GET/POST /api/nav/motor-trim`, browser-verified) + **ESC config**
  (arms the AM32 passthrough via `POST /api/esc/passthrough` → sends ESC_PASS, drops the link; hardware-only,
  400s cleanly in sim). `PicoSerial.esc_passthrough()` added. All browser-verified, no console errors.
**Decisions / open questions:** ILOS gain defaults to 0 (field-tune on a flowing river). WLS off by
default. `pi5/cv/detector.py` orphaned — candidate for deletion. Bug escape handles one blocking obstacle
at a time; dense multi-obstacle fields still want VFH/DWA. ESC passthrough is unvalidated scaffolding.
**Next steps:** (1) **on-Pi validation of the ESC passthrough** — PIO UART loopback → baud scan → am32.ca
(see `docs/esc_passthrough.md`); (2) flash AM32 ≥v1.99 + enable Bi-directional mode + bench-verify reverse
before first spin-up; (3) end-to-end ONNX detector test + measure real vision FPS on the Pi; (4) YOLO→NCNN
or Hailo-8L; (5) confirm drive divider / whether to fit 56k/10k. Nothing committed — working tree left for
the user to review.

## 2026-07-24 — Whole-project multi-agent review + efficiency/design pass

**Worked on:** user asked for a full review of the whole D.R.E.A.M.S codebase — make it efficient and
the UIs designer-grade. Ran 9 directory-partitioned review agents in parallel. Nothing could be
executed (no Python/Node/ruff in this Windows session), so ALL edits are **static-review-only** — run
`pytest pi5/tests`, the two Vite builds, and the on-Pi checks below before trusting them.
**Changed (highlights):**
- `cloud/api` — SRID insert bug fixed (`ST_SetSRID(ST_MakePoint,4326)`); 6 DB routes `async def`→`def`
  (sync `Session` was blocking the event loop); `init_db` now creates `postgis`+`btree_gist` before
  `create_all` (the GiST index over timestamp+geometry needs btree_gist); indexes on `mission_name`
  and `(mission_name,timestamp)`; `pool_pre_ping`; non-root Dockerfile + HEALTHCHECK.
- `pi5/comms` — ALERT 2-field detail no longer truncated; pod poll loop survives a link-down; bounded
  nmcli wifi-connect. `pi5/data/uploader` — offline-buffer race fixed (pop-before-await) + blocking
  saves → `asyncio.to_thread`. `pi5/server/app` — 7 vcgencmd probes `gather`ed; ws pump guard;
  `_pico_port_lock` around the /pico reflash endpoints.
- `pi5/navigation` — **fixed a real pause/resume deadlock** (`pause()` cleared the nav target via
  `stop_nav()` but `resume_mission()` never re-issued `goto()`/`hold()` → hung forever); added a
  bit-identical `distance_and_bearing()` to halve per-tick trig; removed dead `_on_wp_arrived`.
- `pi5/cv/segmentation` — fixed the `_seg_mask` NCHW channel-axis heuristic (the 2 new NCHW tests were
  RED; real eWaSR (1,3,384,512) preserved) and routed the TFLite path through the same config-driven
  reducer (was hardcoded `water_class=0`, inverting eWaSR-convention models). A review agent verified
  the 2026-07-24 stereo-downscale rescaled-Q and `blobFromImage` changes are metrically/geometrically
  CORRECT.
- Front-end — `command_center.html`/`waypoint_planner.html` polish (WCAG-AA contrast, focus-visible,
  reduced-motion, responsive Pico terminal; **no `<script>` touched**; visually QA'd in a browser).
  React `dashboard/` + `cloud/map-viewer/` code+design passes (re-render/leak/race fixes, Leaflet CSS
  self-hosted for field/offline use, canvas heatmap, componentized styling). `ml/` — determinism
  (`sorted()`+seeds), hardlinked dataset copies, dead-import removal.
- Cross-cutting — health-flag byte 4 relabelled **DHT→E_BAT** across `app.py`, `command_center.html`,
  and `serial-protocol.md` (firmware truth = electronics battery; the React dashboard was already
  correct); `run_hardware` `stream_fps` default 15→30; CI `head_commit.modified` path filters removed
  (they never matched → cloud/dashboard/map-viewer jobs silently skipped on push).
**Decisions / open questions:** **Firmware was audited REVIEW-ONLY (no edits)** — safety-critical and
untestable here. Real items to fix + bench-test: **S1** UART1 is drained by two tasks → `$POD` (incl.
leak) frames can be lost; **S2** a blocking USB `stdout.write` can freeze the loop so the software
watchdog never ESTOPs, and there's no hardware WDT; **S3** the SBUS PIO samples 9 cycles/bit not 8 →
RC override may never decode (verify on a scope); **S4** on this single-hull branch a one-hull leak
only WARNs (doesn't ESTOP). Did NOT modernize `on_event`→`lifespan` (risky without a runtime).
**Next steps:** on the Pi/laptop — `pytest pi5/tests` (the 2 seg tests should now be GREEN), `python
run_sim.py` and exercise **pause/resume mid-transit and mid-DATA-waypoint** (the changed uncovered
path), then `npm run dev` both UIs for a visual pass; then triage the firmware S1–S4 safety findings.

## 2026-07-24 — Vision pipeline: full audit + efficiency pass (15 fps water target)

**Worked on:** user asked to fully check + optimize the vision code, find a water-vision library, and
hit ~15 fps Tier-1 water detection with YOLO at a lower-but-high rate. Audited all of `pi5/cv/*` + the
server MJPEG path statically (no Python interpreter/WSL available in this session — see caveat).
**Root bottleneck found + fixed:** `StereoDepth.compute()` ran SGBM + `reprojectImageTo3D` at full
1080p *inside* `vision_overlay._infer`, so every inference with a detection present collapsed detect
FPS to ~1-2/s (this was the exact tradeoff flagged in the 2026-07-01 archive entry).
**Changed:**
- `pi5/cv/stereo.py` — `StereoDepth(calib, downscale=0.5)`: rectify at full res, then run SGBM +
  reproject on a downscaled pair (~4× cheaper) with a **rescaled Q** (`Q[:, :3] /= s`, an exact
  coordinate change → depth stays metrically correct) and a scale-matched disparity range; upsample
  disp/depth back to full res so callers (bbox lookup, `/video?cam=disparity`) are unchanged.
  `downscale=1.0` reproduces the old path exactly.
- `pi5/cv/onnx_detector.py` — YOLO preproc now uses `cv2.dnn.blobFromImage` (one C++ call: swapRB +
  /255 + HWC→NCHW) instead of manual cvtColor/astype/transpose copies. Geometry unchanged (letterbox
  still applied first).
- `pi5/cv/segmentation.py` — added an **ONNX water-seg backend** (onnxruntime, already a dep — no new
  package) alongside the classical + TFLite paths, auto-selected by file extension. Handles WaSR/eWaSR-
  style `(1,C,H,W)`/`(1,H,W,C)` class maps and single water-probability outputs; `seg_water_class` /
  `seg_ignore_classes` / `seg_normalize` / `seg_input_size` are config-driven. Classical path (and its
  tests) untouched. New `_seg_mask` reducer has 3 unit tests.
- `pi5/config.yaml` — `stereo_downscale: 0.5`; `vision.tier1_max_fps 20→15` (the water target);
  detection `imgsz 416→320`, `detect_max_fps 8→10` (keeps YOLO high but under the 15 fps screen);
  seg model default `.tflite→.onnx` + the new seg knobs, documented.
- `run_hardware.py` — passes `camera.stereo_downscale` into `StereoDepth`.
- `pi5/scripts/benchmark_vision.py` (new) — per-stage FPS harness (Tier-1 seg / YOLO / stereo at each
  downscale) for the Pi. `docs/water_vision.md` (new) — backend guide + eWaSR/WaSR recommendation.
**Decisions / open questions:**
- **Not executed/verified here** — no Python, WSL, conda, or ruff in this Windows session (the
  2026-07-23 Py 3.14.4 env is gone). All edits are static-review only. Run `pytest pi5/tests` and
  `python -m pi5.scripts.benchmark_vision` **on the Pi** to confirm. On a Pi 5 *CPU*, the classical
  screen easily does 15 fps; a full seg DNN (eWaSR) does not — it's wired as an optional accuracy/
  accelerator path, documented as such.
- `pi5/cv/avoidance.py` + `detector.py` (`BoatDetector`) are **dead code** — never instantiated by
  `run_hardware.py` (the pipeline + threat_assessor + radar are the live obstacle path). Left in place;
  flagged as a consolidation candidate.
**Next steps:** on the Pi — `pytest pi5/tests`, then `benchmark_vision.py`; tune `imgsz` /
`tier1_max_fps` / `stereo_downscale` to the measured numbers. Optionally export an eWaSR model to
`pi5/cv/models/water_seg.onnx` (see `docs/water_vision.md`) if HSV isn't robust enough in glare.

**Follow-on (same session): hybrid Tier-1 (classical 15 fps screen + eWaSR spot-check).** User asked
to "run eWaSR instead" and whether a Coral M.2 would work. Verified (web): Coral is a poor fit —
INT8-TFLite-only (not ONNX), can't run eWaSR's transformer ops, no official Pi 5 support, pycoral
stuck on Py 3.6-3.9 (repo is 3.14); **Hailo AI HAT+ is the right accelerator** (ONNX-native, 1st-party
Pi 5). Also: eWaSR on the Pi CPU is ~2-8 fps, so it can't be the 15 fps primary. User chose the
**hybrid**, which I built:
- `pi5/cv/pipeline.py` — added `_confirm_seg` (optional DNN water model) on a **separate slow async
  loop** (`_confirm_loop`, `seg_confirm_max_fps` ~2 Hz) so its ~200 ms inference never stalls the fast
  15 fps classical loop. A fresh verdict (within `seg_confirm_ttl_s`) becomes the authoritative
  `water_state` and can wake YOLO on obstacles HSV missed — **fail-safe: only ever ADDS triggers**.
  `vision_state()` gains a `confirm` block. Hybrid is **off unless a real DNN model loads** (two
  classical screens would be pointless), so existing behaviour/tests are unchanged.
- `pi5/config.yaml` — `seg_model_path` now **empty** (classical primary); new `seg_confirm_model_path`
  (`…/water_seg.onnx`), `seg_confirm_max_fps: 2`, `seg_confirm_ttl_s: 3`. (Supersedes this entry's
  earlier "seg_model_path default → .onnx" bullet.)
- `pi5/tests/test_vision_pipeline.py` — +3 hybrid tests (confirm wakes YOLO on clear water; stale
  verdict ignored; hybrid off without a model). `docs/water_vision.md` — hybrid section + Coral-vs-Hailo.
- `ml/export_ewasr.py` (new) — one-command eWaSR→ONNX exporter producing
  `pi5/cv/models/water_seg.onnx` (+ tracked `water_seg_info.json`). Confirmed against the eWaSR repo
  (tersekmatija/eWaSR): forces the single-input `ewasr_resnet18` variant (IMU variant is 2-input and
  won't load), mirrors their `torch.onnx.export(model, {"x": {"image","imu_mask"}}, opset=12,
  output_names=["prediction","intermediate"])` (non-IMU prunes imu_mask → 1 input), ImageNet norm,
  MaSTr1325 class order 0=obstacle/1=water/2=sky (matches config). `--self-check` runs onnxruntime on a
  water frame to confirm class order. Weights from the 0.1.0 GitHub release; run on a GPU box, scp the
  .onnx to the Pi. Decided **Hailo AI HAT+** over Coral if acceleration is wanted (Coral = INT8-TFLite
  only, no ONNX, no transformer ops, pycoral stuck on Py 3.6-3.9).
**Still needs the Pi:** run `ml/export_ewasr.py` on a GPU box, scp `water_seg.onnx` to the Pi, then
`pytest pi5/tests` + `benchmark_vision.py` to confirm. I did not fetch/train the model (no GPU/Python
here, and shouldn't download weights unprompted).

## 2026-07-23 — Verified the waypoint-driving sim already works (no code changes)

**Worked on:** user asked whether a viewable sim of the boat driving waypoints could be created. It
already exists end-to-end — confirmed it rather than building anything new.
**Verified:** started `run_sim.py`, POSTed a 4-point PATH loop near the dock (`/api/mission?start=true`),
and polled `/api/status`. The boat pivoted in place to each bearing (align-first `Navigator`), drove the
leg, and advanced WP 0→1→2, ranging ~58 m from start; server stopped cleanly after. Deps present
(Py 3.14.4, fastapi 0.135.3, uvicorn 0.44.0).
**Notes for next time:**
- Viewable UI = command center at `http://localhost:8000/` (Leaflet map, pulsing boat marker, track +
  waypoint pins, `/ws/telemetry`). Draw/upload routes at `/planner`; sample missions in
  `reference/waypoints.json`. Sim mode runs dev-mode auth (no API key needed).
- Polling `/api/telemetry` and `/api/mission` every tick trips `rate_limit.py` (HTTP 429) — poll the
  bundled `/api/status` at ≥2–3 s spacing instead.
- DATA waypoints stall on the winch-down/sample/winch-up sequence (up to ~5 min each) — use PATH
  waypoints or `POST /api/sim/speed` to watch it drive a route quickly.
**Next steps:** none pending. Offered the user an optional zero-setup standalone animation (self-contained
HTML canvas / matplotlib playback); build only if they ask. No repo files changed this session.

## 2026-07-21 — Single-hull test bench variant: spec + firmware (branch `single-hull-test-bench`)

**Worked on:** user wants a single-hull "test bench" boat (two stern motors, differential steering, standard hobby ESCs instead of the VESC/CAN chain, 2× M18 series drive instead of 3×) to validate the stack on real hardware before the full catamaran. Produced a spec doc, then implemented the Boat Pico firmware on a new branch `single-hull-test-bench` (branched off `main`; `main` untouched). Mid-implementation the user chose to **keep both SHT41 air-temp sensors**, which forced a pin-plan revision (below).
**Final pin plan (test bench):** left ESC **GP2**, right ESC **GP3** (PWM slice 1 A/B — same 50 Hz, independent duty), winch **GP6** (was GP14), SBUS **GP7** (was GP15), **both SHT41s kept on GP12–15** (J11/J13, native as-built pins). Reason: a PCB net-trace confirmed the as-built board routes GP12–15 to the two SHT41 SoftI2C connectors, so propulsion/winch/SBUS move to free Pico header pins (GP2/3/6/7 have no connector — hand-wired taps on a bench rig). This also sidesteps the long-standing dual-hull GP12–15 VESC/winch/SBUS-vs-SHT41 as-built conflict.
**Changed (on branch `single-hull-test-bench`, committed locally, not pushed):**
- `firmware/boat-pico/escs.py` (new) — dual hobby-ESC PWM driver on GP2/GP3, 50 Hz, reusing the winch pulse mapping (STOP 4915 / MIN 3277 / MAX 6553, `duty_u16`). Exposes `LEFT`/`RIGHT`/`LEFT_PIN`/`RIGHT_PIN`/`init` (returns success)/`ready`/`set_duty`/`stop` plus VESC-shaped telemetry **stubs** (temp→None, fault→0, `max_motor_temp`→0.0, poll/request→no-op) so `main.py` telemetry code runs unchanged.
- `firmware/boat-pico/motor_control.py` — imports `escs` not `vesc`; `init/update/estop` drive ESCs; winch `MW_PIN` 14→6; `COMP_L=COMP_R=PULLEY_L=PULLEY_R=1.0` (single hull); `init()` returns ESC-up status. Steering math + RC/ESTOP gates unchanged.
- `firmware/boat-pico/sbus.py` — `SBUS_PIN` 15→7 (PIO).
- `firmware/boat-pico/sensors.py` — drive divider `INV_P_RATIO` 21.0→**14.0** (130k/10k; 42 V→3.00 V — same margin as the production 200k/10k at 63 V), `P_FULL/EMPTY/WARN/CRIT`=42/30/34/32. **Both SHT41s kept** (SoftI2C init unchanged); only battery constants + docstrings changed.
- `firmware/boat-pico/main.py` — imports `escs`; removed `task_vesc_telemetry` + its task-list entry; removed watchdog motor-overheat/VESC-fault blocks and `_mt_throttled`/`_vesc_fault_sent` state; TEL2 `v_in` now carries `sensors.prop_batt_v`; startup prints drive-ESC OK/FAIL with a "do NOT arm" warning; docstring pin map updated. `vesc.py` left in tree but no longer imported.
- `docs/hardware_changes_v2_to_testbench.md` (new) — full spec, revised for the keep-both-SHT41 pin plan. All five firmware files pass `python -m py_compile`.
**Decisions / open questions:**
- Ran an adversarial multi-lens verification Workflow (6 review lenses → per-finding refute pass, 14 agents) on the *first* (pre-SHT41-revision) firmware. Confirmed + fixed two real issues: (1) a stale ×13.0/3.23 V divider figure in a `sensors.py` docstring (correct is ×14.0/3.00 V); (2) `escs.init()` swallowed PWM-init failure silently — fixed with a success return + `ready()` + a `main()` FAIL banner. NB: the verification predates the pin move to GP2/3, but both fixes carried forward unchanged.
- Confirmed the `MCP2515-I_P` symbol in `Boat_PCB.kicad_sch` is placed but **completely unwired**; irrelevant here, worth deleting from the schematic eventually.
- **Safety note:** dumb ESCs hold last PWM (no VESC-style self-timeout); the heartbeat-watchdog→estop→neutral path is the only motor kill. Must be bench-verified before water testing.
**Next steps:** (1) branch is committed locally but **not pushed** — user chose local-only; (2) `docs/pin_map.md` still describes the production board — regenerate/annotate for the GP2/3/6/7 test-bench pinout if this branch is kept; (3) before first spin-up, verify the chosen hobby ESCs' arming sequence + pulse range vs the reused winch mapping, and wire the four relocated signals to the Pico breakout header (open items in the new doc).

**Follow-on (same session): whole-project context doc.** User asked for "a comprehensive document of everything going on in this project" for a Claude chat project page. Wrote `docs/PROJECT_CONTEXT.md` — a self-contained briefing synthesized from CLAUDE.md, pin_map, battery_architecture, serial-protocol, changelog_and_decisions, the ADRs, and the current code/git state (gathered via parallel Explore agents). Covers: compute architecture, repo layout, BOM, pin maps (incl. the Pi 5 radar-bar stepper GPIO exception and the GP12–15 as-built conflict), M18 power, VESC propulsion, serial protocol, full software-module inventory, the three-tier vision pipeline, UI/cloud/deploy, connectivity, run instructions, locked decisions, and a branch/open-items status section. Written while checked out on `single-hull-test-bench`, but it presents **`main` as the architecture-of-record** and the two branches (this one + the older `radar-bar-stepper`) as variants. Doc is **uncommitted** and lives on the current branch — decide whether it belongs on `main`. A verification agent fact-checked it against the repo (main-vs-branch attribution, battery values, pins, protocol, FSM, cloud endpoints, file paths) and found **one error, now fixed**: the 4th TEL health flag is the electronics battery (`E_BAT`), not DHT/temp — corrected to match the `main.py` health string `GPS,IMU,P_BAT,E_BAT,MOT,POD`. Everything else verified accurate.

<!-- Older entries (right-view box fix + live depth view, stereo vision review + Windows camera fix, live camera assignment, commit/push housekeeping,
     align-first steering, waypoint planner page, M18 battery migration, token-bloat audit,
     third-downloaded-file audit, repomix/rtk, token-optimization config pass) live in
     docs/session_journal_archive.md. -->
