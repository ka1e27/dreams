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

## 2026-07-26 — Designer-grade ESC Settings editor (dashboard) + endpoints + tests

**Worked on:** finished the interrupted ESC-config UI. A prior session had refactored
`am32_config.py` into a library (`FIELDS` registry, `read/write_settings`, `decode_eeprom`, mock EEPROM,
wiring/setup constants) explicitly *"for the dashboard ESC editor"* — but the server endpoints and the
actual editor were never built; the modal was still the old "arm am32.ca passthrough" stub. Built the
whole thing and verified it on the Pi.
**Changed:**
- `pi5/server/app.py` — new `POST /api/esc/read`, `POST /api/esc/write`, `GET /api/esc/meta` (+ a
  persistent `_esc_mock` sim buffer). Hardware path runs `am32_config.read/write_settings` in a
  threadpool (blocking pyserial) and refuses during a running mission; sim path serves + mutates the
  mock so the editor is fully usable with no hardware. 400 (bad key/value) vs 502 (link/verify) split.
- `pi5/scripts/am32_config.py` — `_decode_field` now emits `warn_when` for bool fields so the UI
  recomputes the amber "risky state" live on toggle (the registry itself already existed).
- `pi5/server/templates/command_center.html` — replaced the passthrough stub with a full
  **⚡ ESC SETTINGS** modal rendered straight from the field registry: grouped Drive/Protection/Tuning/
  Info sections, real toggle switches + range sliders + info chips, ★ important flags, amber warn rows
  (⚠ + reason) that flip live, dirty/"EDITED" tracking with a sticky Read / Revert / Write action bar
  (Write sends only changed keys, server-verified), and a **Wiring & Setup** tab with the pin table +
  copy-paste one-time `uart0` commands + doc links + the am32.ca passthrough demoted to an Advanced
  collapsible. New `⚡ ESC SETTINGS` button in COMMANDS→DRIVE; ⚙ MOTORS renamed ⚙ TRIM and links to it.
  All device-derived text set via textContent (no innerHTML).
- `pi5/tests/test_am32_config.py` (NEW, 21 tests) — decode/scaling/warn-flags/encode-validate/
  all-or-nothing/round-trip on the library the endpoints call.
- Docs: `docs/am32_config.md` + `docs/esc_setup.md` now present the dashboard editor as the easiest
  setup path (same GPIO-UART backend as the CLI).
**Verified on the Pi:** `pytest pi5/tests` **194 green** (+21), ruff clean, the inline `<script>` passes
`node --check`. Booted the sim and hit the live endpoints via curl — meta/read/write, sim-write
persistence, warn-flip (bidir OFF → warn), and 400s on out-of-range/unknown/empty. Rendered the modal
with a faithful chromium harness (real CSS + markup + render fns + live payload): the Settings tab, the
edited+warn state, and the Wiring tab all read as designer-grade.
**Decisions / open questions:** the underlying `am32_config` read/write was already hardware-proven on
the NeutronRC G071; only the new FastAPI/threadpool wrapper is unexercised on metal — wants one on-bench
pass over `/dev/ttyAMA0`. Web-font (Orbitron) fetch hangs headless chromium on this ARM Pi, so the render
harness strips it (live page is unaffected).
**Next steps:** on-bench — wire an ESC to the Pi UART, open ⚡ ESC SETTINGS, Read/Write a real ESC end to
end; then the outstanding telemetry-on-GP16 check (motor spinning). Nothing committed — tree left for review.

## 2026-07-26 — CV overlay fixed (no model → COCO ONNX), MJPG 720p, HUD de-conflict, auto-exposure

**Worked on:** user reported the command-center CV showed **no bounding boxes**, the top-right
"avoidance"/anomaly HUD was covered by the DET/FPS readouts, and asked for a **higher MJPG resolution**.
Run on the Pi with both Arducam 8MP USB cameras live; "don't come back until it works."
**Root cause (no boxes):** `DetectionOverlay` could load **no model** — `torch`/`ultralytics` aren't
installed and there was no `maritime_yolov8n.onnx` (only its `_info.json`), so `available=False` and it
never drew. onnxruntime 1.28 IS installed (the repo's intended lightweight backend).
**Changed:**
- `pi5/cv/models/yolov8n.onnx` (+ tracked `yolov8n_info.json`, COCO 80 classes) — exported generic COCO
  yolov8n → ONNX (imgsz 320) in a throwaway **disk-backed** venv (torch overflowed the 2 GB `/tmp` tmpfs;
  built under `/`, then deleted), so the runtime `.venv` stays torch-free. `.onnx` is gitignored (like the
  maritime slot). `pi5/config.yaml` `detection.model` → this path (onnxruntime backend).
- `pi5/config.yaml` camera → `fourcc: MJPG`, `1280x720` (was YUY2 640×480). Both cams advertise MJPG to
  1920×1080@30 / 1280×720@30; measured **~16–18 fps** dual-cam through the producer on the bench
  (auto-exposure-limited indoors; approaches 30 in bright light — not decode/USB-bound).
- `pi5/cv/camera.py` — force **auto-exposure** (V4L2 aperture-priority=3) on every `_open`. UVC exposure
  persists on the device across processes; a stray manual setting was blacking out the feed (this was why
  the first live grab was near-black). Best-effort, Linux/V4L2 only.
- `pi5/server/templates/command_center.html` — moved `.cam-det` from top-right → **bottom-right** (above
  `.cam-fps`), freeing the top-right for the baked ANOMALY bar + tier dots. Corner ownership now: TL
  tag/track, TR anomaly, BL water, BR det/fps.
**Verified on the Pi (cameras live):** COCO ONNX detects person+boat on stock images and **chair/tv/laptop
live**; the real `/video` endpoint draws boxes + the uncovered HUD at 1280×720; 3-tier gating turns YOLO
on via the land-scene anomaly (0.78). Before/after HUD screenshot confirms the de-conflict. `pytest
pi5/tests` **164 green**, ruff clean.
**Decisions / open questions:** COCO yolov8n is a bench/demo detector — swap a trained maritime model in
(`ml/`, drop `pi5/cv/models/maritime_yolov8n.onnx`, auto-preferred). The `.onnx` is gitignored, so a fresh
checkout needs it regenerated (`ml/export_onnx.py`) or the overlay falls back to the uninstalled `.pt`.
**Next steps:** train/drop the maritime model; optionally bump capture to 1080p if CPU headroom allows;
NCNN/Hailo for higher detect FPS. Nothing committed — working tree left for the user to review.
**Follow-up (maritime model hunt — negative result, kept COCO):** surveyed HF + Roboflow + GitHub for a
drop-in maritime detector. Findings: (a) openly-downloadable ones are **satellite/SAR** (mayrajeo,
DefendIntelligence, Mahadih534, torchgeo Sentinel-2, geobase) — wrong perspective for a surface boat;
(b) `dima806/*` is image-classification, not detection; (c) the good surface-level multi-class ones are
**gated** (`cazzz307` HF-login; Roboflow "Marine Surveillance" boat/buoy/kayak/vessel needs an API key).
Best candidate **`alimkacar/argus-maritime-yolov8s`** (ungated, classes boat/sailboat/vessel/buoy/person,
inshore surface imagery, claimed mAP50 0.97) was downloaded + tested: it was **trained on a FORKED
ultralytics** (`train_args` has `cls_remap`/`distill_model`/`tracktrack`/`end2end`) and yields ~0.003
class-confidence under STANDARD ultralytics/ONNX inference across all preprocessing (RGB/BGR/imagenet) —
i.e. only its fork's forward decodes it, so it is **unusable with this repo's standard `onnx_detector`**
(would detect nothing). Verified my method is sound by running the working COCO model on the same images
(boat1 harbour → 2 boats; boat4 buoy → "boat" 0.75; boat2 sailboat → mislabeled "kite"; boat3 marina →
missed). Conclusion: no free, ungated, surface-level, standard-decoder maritime model exists to drop in
now. The auto-detect slot (`pi5/cv/models/maritime_yolov8n.onnx`) is ready — the reliable route to a real
one is a Roboflow "Marine Surveillance" export trained/exported with **standard** ultralytics via `ml/`
(needs a free Roboflow key), or the user drops in any standard-ultralytics maritime `.onnx`. **Note:**
COCO/YOLOv8 weights are Ultralytics **AGPL-3.0** — fine for research/personal use; matters only if
D.R.E.A.M.S is ever distributed as a network service. Kept COCO in place (detects boat+person well).
**Follow-up 2 (big autonomy + UI push — cameras/Pico/left-ESC on the bench; 3 research agents + 1 UI
agent):**
- **Current-aware station-keeping** (`pi5/navigation/current_estimator.py` NEW + `navigator.py`): estimate
  the water current as *GPS ground velocity − modelled through-water velocity* (thrust model
  `v=a|thr|+b·thr²`), low-pass filtered → **set/drift** on `/api/status`. Stay/HOLD mode now **actively
  noses into the current** (required through-water vel = desired-ground-vel − current) instead of
  drift-then-reacquire. Sim (new `/api/sim/current` + simulator current): recovers 090°/0.35 m/s exactly,
  **holds ≤0.4 m**. Config `navigation.current_*`/`sk_*`; NavState/NavStateOut extended; +5 tests. ILOS
  still handles transit current.
- **Incoming-wave detection → capsize avoidance** (`pi5/cv/wave_detector.py` NEW, wired into
  `pipeline.py`): horizon-from-gradient + sparse LK optical-flow looming → severity/bearing/TTC with a
  persistence state machine, ~3 ms/frame live. **Bow-into-wave** override (turn to face + ease throttle,
  yields to obstacle avoidance) + HUD horizon line/chevron + `vision.wave` telemetry. `vision.wave_detection`
  config; +4 tests. (No IMU pitch yet — noted.)
- **YOLO speed** (`pi5/cv/ncnn_detector.py` NEW + `vision_overlay.py`): NCNN backend via the `ncnn` pkg
  (no torch), identical decode. **Clean Pi-5 benchmark: NCNN 34 fps vs ONNX 18 @ imgsz 320 (1.96×)** — the
  earlier "NCNN slower" was training CPU contention. Shipped **COCO yolov8n as an NCNN export**
  (`pi5/cv/models/yolov8n_ncnn_model/`, gitignored; `.onnx` kept as fallback); `detect_max_fps` 10→15.
- **Maritime+person model — trained but NOT shipped.** Used the user's Roboflow key to pull
  `udea/proyecto-de-grado-unvpl` v6 (CC BY 4.0: Boats/Sail-Boat/Kayak/Person/Buoy/Rock/wreck/Dock/…), trained
  yolov8n on the Pi CPU (subset, imgsz 320). It **plateaued at mAP50≈0.21** and — critically — **missed
  people** on test images (COCO detects them cleanly), because the small Pi-subset fine-tune degraded COCO's
  person head. Decision: **ship COCO** (detects boats+people = the requirement) via NCNN; the maritime
  slot + threat map + case-insensitive labels are all ready for a properly-trained model (full dataset/GPU,
  or frozen-backbone). `threat_assessor` extended (boats/sail-boat/surfer/rock/wreck/bridge, case-insensitive).
- **UI redesign + ESC tab** (`command_center.html`, via a design agent using the dataviz skill): new
  **PROPULSION·ESC** panel (per-motor temp radial gauges + current bars, threshold-coloured), **WAVE ALERT**
  readout, **CURRENT & STATION-KEEP** vector — all wired to the real payload fields; existing ids/JS/drag-grid
  preserved; scripts pass `node --check`. Verified layout via a static render (chromium can't screenshot the
  full live page on this ARM Pi — MJPEG stream hangs it; live server serves `/`=200 and `/video` draws the
  wave-HUD + boxes).
- **Verified:** `pytest pi5/tests` **173 green**, ruff clean, firmware py_compiles, both template `<script>`
  blocks pass `node --check`, NCNN COCO detects person/boat live (backend=ncnn), Pico streaming TEL/ENV on
  `/dev/ttyACM0`. Docs: `docs/current_and_wave_features.md`. **Committed + pushed** this follow-up.

## 2026-07-25 — Full on-Pi review (9 agents) + ESC KISS telemetry (temp + current)

**Worked on:** first review actually **run on the Pi** (prior 3 sessions were Windows/static-only).
Then built per-motor ESC telemetry end-to-end at the user's request.
**Review (executed):** baseline healthy — `pytest pi5/tests` **164 green**, ruff clean, firmware
py_compiles, both Vite builds pass. 9 parallel subsystem agents + own pass on scripts/services/CI/deploy.
Findings relayed to user; **nothing auto-fixed**. Headline:
- **CRITICAL firmware (verified by hand):** (S2) `serial_handler._send()` `sys.stdout.write` is
  unguarded — a hung Pi fills the USB TX buffer, stalls the single asyncio loop, watchdog never ESTOPs
  (read path IS guarded, write path isn't). (S1) UART1 double-drain — `gps.read()` in `task_fast_sensors`
  (main.py:209) races `task_uart1_reader`, shredding GPS **and** `$POD` leak frames; fix = delete line 209.
- **HIGH:** pod-leak only alerts (no ESTOP/decision); single-hull hull-leak ESTOP needs *both* sensors so
  never fires; watchdog ESTOP is one-shot under `except: pass`.
- **MED:** cloud `list_missions` unbounded; server blocking file IO in async save/delete; `pod_bridge`
  `_pod_ok` not cleared on parse error; uploader overflow truncation; `detector.py` dead; doc rot
  (`main.py`/`pin_map.md` "2× M18 series"→parallel; pin_map still production board); orphaned
  `mission:`/`pod:`/`logging:` config; Caddyfile only proxies /api+/ws.
- **Rejected on verify:** rate-limiter "race" (no `await` in critical section → atomic single-worker) and
  SBUS S3 "9 cycles/bit" (it's 8, correct). *But* SBUS uses an 8-byte PIO FIFO < a 25-byte frame → likely
  under-drains too (bench-check).
**ESC telemetry (built; runs in sim; UNTESTED on hardware):** new `firmware/boat-pico/esc_telem.py` — PIO
UART RX ×2 (**GP16** L / **GP19** R), KISS 10-byte frames (CRC-8, big-endian), **32-byte FIFO**
(`push_thresh=32` — the fix SBUS lacks). `escs.py` telemetry stubs now delegate to it; `main.py` inits +
100 Hz drain task + edge-triggered `MOTOR_HOT` WARN (80 °C, WARN-only by choice — one-liner to ESTOP).
Current appended to `TEL` as `curr_l,curr_r` (backward-compat v1.1 appendix) → `pico_serial`
(parse-if-present) → server model/status dict → command center + `TelemetryPanel.jsx`. Simulator emits
synthetic load-based temp/current. Fixed the "series"→"parallel" doc rot in `main.py`/`sensors`/`simulator`
while here. Docs: new `docs/esc_telemetry.md` (+ `esc_setup.md`, `serial-protocol.md §4.1`).
**Verified:** 164 tests still green, ruff clean, firmware compiles, KISS parser unit-checked
(CRC/scaling/resync/reject); **booted the sim on the Pi** — a `goto` drove the boat and `/api/status`
showed `curr 12.0/3.2 A`, `temp 45/37 °C` tracking throttle.
**Decisions / open questions:** ESC telem has 3 bench unknowns (AM32 emitting telem in PWM mode; PIO byte
order `_BYTE_ORDER_LE`; drain cadence via `esc_telem.stats()`) — see the doc. Review fixes NOT applied —
awaiting user's pick.
**Next steps:** (1) fix S1 (1-line) + S2 (writer-queue) — top safety value; (2) bench-validate ESC telem
per `docs/esc_telemetry.md`; (3) regen stale `pin_map.md`; (4) pi5/cloud one-liners. Nothing committed.
**Follow-up (2026-07-26) — on-bench ESC bring-up with a real NeutronRC G071 + 4S:**
- **ESC passthrough bench-tested → found + fixed real bugs.** Arming the Pico bridge stranded the Pico
  (needed power-cycles). Root causes fixed in `firmware/boat-pico/esc_passthrough.py`: `stdin.read(64)`
  blocks until 64 bytes (rp2 `select.poll` on USB-CDC is unreliable) → drain byte-at-a-time; added a
  **hardware `machine.WDT(8s)`** so a hang self-recovers (also the only HW WDT in the firmware now);
  moved its PIO SMs 0/4→6/7 (collided with SBUS SM0 + esc_telem SM4/5); dropped the `ESC_PASS: bridging`
  print in `main.py` that leaked into the CDC as a false "reply". Still not functionally validated for
  am32.ca-through-Pico (poll/read + half-duplex link unproven) — WDT just makes iterating safe.
- **am32.ca can't see the Pi's GPIO UART** (Chromium Web Serial lists USB serial only), so the browser
  path is out without a USB-TTL adapter (user has none). **Pivoted to a CLI configurator.**
- **NEW `pi5/scripts/am32_config.py` — WORKS.** AM32 one-wire bootloader protocol over the Pi's GPIO
  UART (transcribed from AM32-bootloader `main.c`: 19200, CRC16 0xA001, SET_ADDRESS/READ/SET_BUFFER/
  PROG_FLASH). Enabled `uart0` (`/dev/ttyAMA0`, GPIO14/15) at runtime + stopped the serial getty. Read
  the ESC (name "NeutronRC G0", 64K, flash code 0x35 → EEPROM at 0xf800), then **wrote + read-back-verified
  bidirectional (byte 18=1) + 30ms telemetry (byte 31=1)**. `read` + `set --bidir/--telemetry/--lvc`.
  Doc `docs/am32_config.md`; `esc_setup.md` updated (Pi-GPIO path now the recommended bench route).
- **Telemetry still 0 on GP16.** Traced AM32 firmware: serial telem is emitted on the **MCU's PB6**
  (USART1 115200 8N1 open-drain) and the transmit sits in the commutation path → **likely only streams
  while a motor is spinning**. No motor connected, so `esc_telem` correctly sees 0 bytes. Left for the
  user to finish: motor (props off) + throttle, and confirm GP16 is on the ESC's actual telemetry pad (PB6).
**Committed + pushed** as `c70a8f0`. Then **fixed the two firmware safety criticals** (deployed to the
Pico + verified telemetry still flows with valid checksums): **S1** — removed the racing `gps.read()` from
`task_fast_sensors` so `task_uart1_reader` is the sole UART1 reader (it demuxes GPS + `$POD`; the double
read was shredding GPS fixes and the pod leak frame). **S2** — `serial_handler._send()` now writes
byte-at-a-time behind a `POLLOUT` poll (`_stdout_poll`) and drops the rest of a frame under back-pressure,
so a Pi that stops draining the CDC can no longer wedge the asyncio loop and starve the heartbeat
watchdog. S1/S2 changes (`main.py`, `serial_handler.py`) + this note uncommitted.

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

<!-- Older entries (right-view box fix + live depth view, stereo vision review + Windows camera fix, live camera assignment, commit/push housekeeping,
     align-first steering, waypoint planner page, M18 battery migration, token-bloat audit,
     third-downloaded-file audit, repomix/rtk, token-optimization config pass) live in
     docs/session_journal_archive.md. -->

