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

## 2026-07-26 — 5-agent code audit (fixes applied) + dashboard HTML redesign to "10/10"

**Worked on:** user asked to (a) finish the interrupted verification — 5 max-effort (Opus) agents
checking the whole stack for correctness + efficiency — and (b) lift the served HTML dashboards from
a self-rated 7/10 to a 10/10.
**Audit (5 parallel Opus agents; baseline healthy: 234 tests green, ruff clean, both Vite builds pass,
both inline `<script>`s valid).** Applied the *verified, safe* findings; rejected/​skipped the rest with
reasons:
- `pi5/navigation/navigator.py` — **CRITICAL** div-by-zero guard: `compute_throttle`'s turn-blend
  divided by `(max_heading_error_deg − heading_tolerance_deg)` unguarded while the sibling `_steer_to`
  already used `max(1.0, …)`; made them consistent.
- `pi5/server/app.py` — **event-loop unblocking**: `/ws/camera` now offloads StereoSGBM + `cv2.imencode`
  to the executor (mirrors `/video`); `/api/paths` read/write moved to `asyncio.to_thread`; `/api/pod/history`
  `limit` clamped to ≤5000 (was unbounded → OOM/DoS vector).
- `pi5/cv/wave_detector.py` — vectorised the water-mask horizon scan (per-column Python loop → numpy
  `argmax`/`where`; dormant path, ~30× when used).
- `firmware/boat-pico/main.py` — health-flag battery bits now use the real `is_prop_critical()`/
  `is_elec_critical()` predicates (were `>5.0`/`>3.0` → always "healthy"; telemetry-accuracy only).
- `cloud/api/app.py` — `list_missions` now bounded (`limit` Query ≤2000, was unbounded).
- `dashboard/src/components/BoatMap.jsx` — waypoint markers use a stable key, not the array index.
- **Rejected on verify:** the "WebSocket client-list race" (single-thread asyncio; no iteration during
  send) and the SBUS `push_thresh 8→32` one-liner (8 = autopush **bit** count = 1 byte/word; bumping it
  repacks 4 bytes/word and **breaks SBUS framing** unless the reader is redesigned — left as a real
  follow-up, not a one-liner). Skipped `threat_assessor` deque (negligible, deque-slice risk) and the
  `run_sim` ObjectMemory-config wiring (sim harness ignores `config.yaml` for *every* component — kept
  consistent).
**HTML redesign — command_center.html + waypoint_planner.html → "Abyssal Indigo v2":** used the dataviz
skill's method. New layered-glass design system (elevation/hairline/surface tokens, restrained glow as a
*signal* not decoration, `tabular-nums` on every live readout so digits don't jitter, ambient aurora
wash). Header became a real command bar (live local clock + mission-elapsed **T+** timer keyed off the
mission badge, grouped connection cluster with breathing live-dots, animated hairline scan). Section/panel
shells got glass depth + a left accent-tab header rule. Flagship upgrade: the crude rotating-border ESC
temp gauge → a proper **animated conic-sweep ring** (`@property --deg`, colour-shifts ok→warn→crit) inside
framed per-motor instrument cards; ESC current bars, status chips, buttons, dots, wave-alert + boat-health
tiles all refined. Planner brought onto the same system.
**Verified (on the Pi):** `pytest pi5/tests` **234 green**, ruff clean, firmware `py_compile` OK, both
templates' inline `<script>` pass `node --check`, dashboard Vite build clean. Booted the sim and
round-tripped the changed endpoints over real HTTP: `/api/paths` GET/POST/DELETE, `/api/pod/history?limit=
999999999` clamps (no OOM), `/` and `/planner` both 200. Rendered both templates in headless Chromium
(fonts/leaflet/monaco stubbed, canned telemetry through the real render path) and eyeballed the result —
reads as designer-grade in both. Screenshots in the session scratchpad.
**Decisions / open questions:** SBUS FIFO under-drain is still a *plausible* margin risk — wants a real
PIO redesign (pack 4 bytes/word + unpack in the reader), not the mislabelled one-liner. The headless
render falls back off Orbitron (web font hangs headless Chromium on this ARM Pi) — live page unaffected.
**Next steps:** on-bench/on-water passes still outstanding from prior entries (ESC over `/dev/ttyAMA0`,
telemetry-on-GP16 with a motor spinning, real maritime model). Nothing committed — tree left for review.

## 2026-07-26 — GPS-anchored object memory (buoys/landmarks charted on the map)

**Worked on:** new feature — the boat now **remembers where objects are on the water**. When vision
confirms a buoy (or dock/rock/person), it geolocates it and drops a marker on the GPS map; once
charted it re-verifies the coordinate on each later sighting instead of re-dropping, and doesn't tie
up the radar re-observing it — so it keeps scanning for the unknown even with known things nearby.
Permanent marks (buoys/docks/rocks) are kept; transient movers (people/boats) expire after a TTL.
**Changed:**
- `pi5/navigation/geo.py` — new `destination_point()` (forward geodesic): boat fix + true bearing +
  range → object lat/lon. The inverse of `bearing`/`haversine`. +6 tests.
- `pi5/cv/object_memory.py` (NEW) — `ObjectMemory`: geolocates detections, matches by **world
  coordinate** (survives looking away/back), confirms after N agreeing sightings (then a marker
  drops), refines with an inverse-distance²-weighted mean, and ages out transients/candidates.
  Class→category (PERMANENT vs TRANSIENT) here. +32 tests.
- `pi5/cv/pipeline.py` — feeds every ranged detection into the memory (bearing off the bow =
  `heading + bbox offset`; cameras are fixed-forward, the stepper is a *separate* radar bar), ages it
  each tick, exposes `map_objects()` + `vision_state()["object_memory"]`, and **releases the radar
  from confirmed non-CRITICAL landmarks** (`release_radar_on_known`) so it keeps scanning. +6 pipeline
  tests.
- `pi5/server/app.py` — `GET /api/map/objects`, `POST /api/map/objects/clear` (reads the pipeline's
  memory on hardware, a standalone one in sim); `configure(object_memory=…)`.
- `pi5/navigation/sim_obstacles.py` — `SimObjectMapper` feeds the memory from ground truth (the sim's
  stand-in for vision), wired into `run_sim.py`. +4 tests.
- UI: command center `command_center.html` — object marker layer polling `/api/map/objects` (cyan
  permanent / amber transient, hover label + detail popup) + **SIM MAP** DROP BUOY / DROP PERSON /
  CLEAR MARKS buttons (sim-only). React `dashboard/` — `useMapObjects` hook + `BoatMap.jsx` markers.
- `pi5/config.yaml` — new `vision.object_memory` block. Docs: `docs/object_memory.md`.
**Verified (on the Pi):** `pytest pi5/tests` **234 green** (+40), ruff clean, command-center inline
`<script>` passes `node --check`, `dashboard` Vite build clean. Booted the sim and drove the whole
lifecycle over the real endpoints twice: dropped a buoy 18 m ahead → confirmed **PERMANENT** marker
geolocated to **18.1 m / bearing 359.8°** (matches ground truth to ~0.1 m); person → **TRANSIENT**;
markers **persist after the obstacles are removed** (remembered); two buoys stay distinct (9.1 m
apart) while an out-of-cone one isn't seen; a repeat drop **refines, not duplicates**; CLEAR MARKS
wipes them. Transient TTL / permanent persistence are covered by deterministic unit tests.
**Decisions / open questions:** object memory needs **stereo range** to place a detection → no-op on a
mono rig (documented). Marker identity is the world coordinate + class; the vessel synonym set
(boat/vessel/boats) is canonicalised. Not yet exercised on-water with a real detector (bench next).
**Next steps:** on-water pass with the camera + a real buoy; tune `confirm_sightings`/`match_radius_m`
against live stereo noise; consider persisting the memory across restarts. Nothing committed — tree
left for review.
**Follow-up (independent verification pass — on the Pi):** re-verified the whole feature end to end,
nothing changed in the code. Static: `pytest pi5/tests` **234 green** (targeted object-memory/geodesic
subset **35 green**), ruff clean across all 10 touched files, command-center inline `<script>` passes
`node --check`, dashboard **Vite build clean**. Independent numerical check of the forward geodesic
(`destination_point` round-tripped against `haversine`/`bearing`): **worst distance error 0.000 cm over
77 cases** (bearings 0-359.5°, ranges 1 m-5 km), bearings back to <0.05°, +180° meridian wraps
correctly. Independent live lifecycle over the **real HTTP endpoints** (fresh sim boot): buoy dropped
18 m ahead confirmed after 3 sightings and **geolocated 0.19 m from sim ground truth**; person →
TRANSIENT; two distinct markers; repeat sightings **refined one object** (id stable, sightings 7→11,
0.04 m drift, no duplicate); markers **persisted after the obstacles were deleted**; CLEAR wiped them.
Code confirmations: the `distance_m` fed to the memory is the overlay's **stereo** value (mono
`_fallback_distance` is used only on the avoidance path) → the "mono rig = no-op" claim holds; the
hardware pipeline maps all 11 `vision.object_memory` config keys 1:1; both UIs (command center +
`BoatMap.jsx`) render markers identically (cyan permanent / amber transient) and XSS-safe. The
sim-only path the live run can't reach — **radar-release-on-known** — is covered by
`test_pipeline_radar_releases_known_buoy_keeps_scanning`. **Two benign notes (not bugs):** (1)
`run_sim.py` builds `ObjectMemory()` with defaults — consistent with the sim harness ignoring
`config.yaml` for every component; config wiring lives on the hardware path + unit tests, so a config
change is only felt in sim if `run_sim` is taught to load it. (2) `known_confirmed_near` uses a fixed
6 m radius in the radar-release check (not range-scaled), so releasing the bar may under-fire for a
landmark geolocated from a long/noisy range — conservative (keeps tracking), an on-water tuning knob.
Still nothing committed.

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

<!-- Older entries (right-view box fix + live depth view, stereo vision review + Windows camera fix, live camera assignment, commit/push housekeeping,
     align-first steering, waypoint planner page, M18 battery migration, token-bloat audit,
     third-downloaded-file audit, repomix/rtk, token-optimization config pass) live in
     docs/session_journal_archive.md. -->

