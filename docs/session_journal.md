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

## 2026-07-26 — Camera recording + Tesla-style sentry mode + Recordings dashboard section

**Worked on:** `/goal` — record the camera to the Pi, auto-record critical moments like Tesla Sentry,
and a dashboard spot to browse/play clips (make it look good).
**New `pi5/cv/recorder.py` (`Recorder`):** rolling pre-roll ring (JPEG-encoded, memory-bounded) so an
event clip includes the run-up; manual start/stop; `note_event(reason)` sentry trigger (debounced,
seeded from pre-roll, extends while the event persists up to a hard cap); auto-stop via `tick`; writes
browser-playable **VP8/WebM** (fourcc probe → mp4v fallback) + a JSON sidecar; retention cap; path-
traversal-safe list/serve/delete. All OpenCV work is synchronous here; the server drives it via
`asyncio.to_thread`. +6 unit tests.
**Server (`app.py`):** an always-on background feed task subscribes to the camera (or synthesises a
telemetry-HUD frame in sim, so the feature is demoable with no camera), buffers pre-roll while sentry
is armed, evaluates sentry triggers (~3 Hz: CRITICAL vision threat / hull leak / pod leak) and ticks
the recorder — all off the event loop. Endpoints: `GET /api/recordings` (status + clips), `POST
/api/recordings/start|stop`, `POST /api/recordings/sentry`, `DELETE /api/recordings/{name}`, and
`GET /api/recordings/{name}` (served with `?key=` like `/video`, for the `<video>` tag). Wired into
`run_sim.py` (+ sim reactive-avoidance now raises a sentry event) and `run_hardware.py` (config-driven);
`recording:` block added to `config.yaml`; clips gitignored.
**Dashboard:** a new full-width **RECORDINGS** section — SENTRY arm toggle, manual REC/STOP, a live
`● REC` pill, and a player + scrollable clip list (severity-coloured cards: critical/warning/manual,
timestamp, duration, size; click to play inline, ✕ to delete). Matches the Abyssal-Indigo design system.
**Verified (on the Pi):** `pytest pi5/tests` **242 green** (+6), ruff clean, inline `<script>` passes
`node --check`, dashboard Vite build clean. Drove the whole lifecycle over real HTTP: manual clip
(29 frames / 2.9 s / valid 49 KB WebM) → served 200 `video/webm` → deleted; armed sentry, drove the
boat into a dropped obstacle → **auto-clip fired with pre-roll** (`critical-threat:obstacle`), extended
while avoiding (620 frames / 62 s / 1.2 MB), finalised, served. The RECORDINGS section + JS render in
the served page.
**Decisions / open questions:** H.264 needs a HW encoder that isn't present here, so clips are VP8/WebM
(universal browser playback). Sim has no camera → the feed synthesises a HUD frame; on hardware it
records the live left camera. Sentry triggers are CRITICAL-threat / hull-leak / pod-leak (operator
estop left out). Not yet exercised with a real camera on the Pi.
**Next steps:** on-camera hardware pass; optional clip thumbnails; maybe a download button beside inline play.


## 2026-07-26 — Recursive improvement pass (5 rounds): CV/server perf, dashboard a11y, dead-code + tests

**Worked on:** `/goal` — recursively hunt codebase + efficiency improvements, research-driven, ≥5
iterations; user also invited a big HTML overhaul (rated the dashboard 7/10). Ran 5 verified rounds off
a clean baseline (234 tests green, ruff clean, both Vite builds pass). Verified every audit finding by
hand first — **rejected more than I applied.** Each round committed separately + pushed.
**R1 — discovery + research:** 3 parallel Opus audit agents (cv / navigation+comms / server) + web
research on modern control-room/ECDIS dashboards and numpy/OpenCV/asyncio efficiency.
**R2 — CV perf:** `threat_assessor._match` compares squared centroid distances (no per-candidate sqrt
each frame; monotonic); `size_history` trimmed in place (`del h[:-n]`) not rebuilt; `object_memory.stats()`
one pass not four. Rejected: `size_history`→deque (breaks the slice reads in `_approach_vector`), the
(0,0) GPS guard "bug" (deliberate sentinel), `_enforce_cap` "every frame" (already early-returns).
**R3 — server perf:** `_gather_health` ran psutil (`disk_usage` statvfs + `/proc`) on the event loop
every 1 s → extracted `_gather_psutil_stats()` + `asyncio.to_thread` (also unblocks the `/ws/health`
cold-start); `/api/camera/devices` POST write offloaded. Verified end-to-end against a real
`_gather_health()` call (psutil 7.2.2). Rejected the TEL/ENV "partial field" findings (the `>=12` gates
match the protocol's all-or-nothing v1.1 appendix) and the module-load `asyncio.Lock` nit (fine on 3.10+).
Also rejected on nav: the WINCH_UP `skip_site` "bug" — the winch *must* fully retrieve the pod before
moving on, so ignoring skip during ascent is intentionally safer.
**R4 — dashboard a11y (NOT a blind rewrite):** measured the existing design first — **every text token
passes WCAG AA on all four surfaces** (muted 5.3–6.4, crit 4.7–5.7), and global
`prefers-reduced-motion` + `:focus-visible` + a semantically-valid palette are already present. It's
objectively strong; "7/10" is subjective and **I could not render on this ARM Pi** (headless chromium is
killed in the sandbox; user declined the Chrome tool this session), so a blind restyle of a tuned design
wasn't defensible. Applied verifiable wins: `role=alert`/`aria-live` on the estop banner + toast (were
silent to screen readers) and `aria-label` on the 8 unlabeled sliders.
**R5 — simplification + tests:** removed genuinely-dead `ThreatAssessor.is_approaching` (0 callers;
superseded by `_approach_vector`); the graph's other 76 "dead" hits are framework/dispatch false
positives (`require_api_key` Depends, ASGI middleware, `MockPicoSerial`, argparse `cmd_*`) and were left
alone. Added `test_threat_assessor.py` (nearest-track association, previously covered only indirectly).
**Verified (on the Pi):** `pytest pi5/tests` **236 green** (+2), ruff clean, both templates' inline
`<script>` pass `node --check`, dashboard Vite build clean; booted the sim and confirmed `/` still 200
with the new aria attributes.
**Decisions / open questions:** the *visual* overhaul is the one open item — the design is objectively
AA-clean and I can't render it here, so the next step needs the user to view `localhost:8000` and name
specific visual directions (colours / density / typography), or enable a browser tool.
**Next steps:** (unchanged) on-bench/on-water ESC + telemetry passes; optional user-directed dashboard
restyle.


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

<!-- Older entries (right-view box fix + live depth view, stereo vision review + Windows camera fix, live camera assignment, commit/push housekeeping,
     align-first steering, waypoint planner page, M18 battery migration, token-bloat audit,
     third-downloaded-file audit, repomix/rtk, token-optimization config pass) live in
     docs/session_journal_archive.md. -->

