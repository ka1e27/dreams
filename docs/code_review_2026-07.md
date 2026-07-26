# D.R.E.A.M.S — Full code review (2026‑07)

Scope: the whole Pi‑5 stack (`pi5/`), the two entry points (`run_hardware.py`, `run_sim.py`),
the command‑center + waypoint‑planner UIs, and how the pieces wire together. Firmware, PCB,
and cloud were read for context but not deeply audited here.

**Overall:** this is a strong, unusually well‑documented codebase. Graceful degradation is
everywhere (no camera / no Pico / no model / no calibration all keep the server up), the
async/threading split is correct (blocking cv2/serial/ORT work is kept off the event loop),
and the vision pipeline's "layer, don't duplicate" design is genuinely good engineering. The
issues below are mostly **integration gaps** — subsystems that were built well individually
but not connected — plus optimization headroom. The most serious (obstacle avoidance never
steering the boat) is now fixed.

Legend: ✅ fixed this session · 🔧 recommended · severity in brackets.

---

## A. Correctness & integration

### ✅ A1 [Critical] Obstacle avoidance was never wired to steering
The whole premise is "avoids obstacles using computer vision," but nothing steered around
them. `pi5/cv/avoidance.py:AvoidanceLoop` — the only caller of
`Navigator.set_avoidance_override` — was **never instantiated** in `run_hardware.py` or
`run_sim.py`, and it ran a *second* YOLO detector (`BoatDetector`), duplicating the exact
inference the pipeline works hard to avoid. The pipeline detected, ranged, and prioritised
threats and only ever *pointed a camera bar* at them; `mission_alert` was computed and shown
on the dashboard but consumed by no controller.
**Fix:** rewrote `avoidance.py` into a pure, tested `reactive_avoidance()` rule; the pipeline
now pushes a steer‑away override into the navigator (bearing + range → slow & bear away,
head‑on → starboard per COLREGS), released once on clear. Wired `navigator=nav` into the
pipeline in `run_hardware.py`. Live toggle + endpoint added. See `docs/navigation_guidance.md`.

### ✅ A2 [High] Navigation had no cross‑track correction
`Navigator` steered straight at the target waypoint (`distance_and_bearing` → heading error).
That ignores cross‑track error, so wind/current pushes the boat off the line and it arrives
via a long curved path — poor for survey transects.
**Fix:** added lookahead line‑of‑sight guidance (`geo.los_course` / `cross_track_error`) with
an optional integral term (ILOS) for steady‑current rejection; `MissionManager` anchors each
leg to the previous waypoint. Legacy point‑at‑target behaviour preserved when no leg is set
(and for the existing tests). 10 new tests incl. a convergence rollout.

### ✅ A3 [High] `run_hardware.py` ignored the `navigation:` config block
`nav = Navigator(pico)` used the hard‑coded `NavConfig` defaults; every documented value in
`config.yaml`'s `navigation:` section (`arrive_radius_m`, `heading_tolerance_deg`, `update_rate_hz`,
…) was silently dead. Only `cruise_throttle` took effect, and only because a REST endpoint set
it. **Fix:** `_nav_config()` builds `NavConfig` from the block with per‑key fallback.

### ✅ A4 [Medium] Stereo left/right frames were captured sequentially
`CameraProducer` did a full `cap.read()` (grab+retrieve+decode) for the left camera, then the
right — capturing them a decode‑time apart, which adds horizontal disparity error on moving
targets (vessels). **Fix:** split into `_grab_retrieve` (grab both handles back‑to‑back to latch
the sensors near‑simultaneously, then decode both) + `_account` (the unchanged fail/reconnect
bookkeeping). Cuts the software skew to ~one grab call. (Inherent un‑genlocked sensor asynchrony
remains — that needs hardware sync.) Covered by `test_camera.py`.

### 🔧 A5 [Low] Dead / stale code after the avoidance rewrite
`pi5/cv/detector.py:BoatDetector` is now unreferenced (it only fed the old `AvoidanceLoop`).
Either delete it or repurpose it. The old top‑level `avoidance:` config block was replaced by
`vision.reactive_avoidance` — done. Consider a follow‑up to remove `detector.py`.

---

## B. Robustness

### 🔧 B1 [Low] Serial sequence‑number reuse
`PicoSerial._next_seq` wraps 1–255. A response that arrives *after* its command timed out and
the seq has since been reused could resolve the wrong future. Extremely unlikely at a 2 s
timeout and low command rate, but a monotonic 16‑bit seq (or dropping stale futures by age)
would close it.

### 🔧 B2 [Low] ENV v1.1 appendix is all‑or‑nothing
`_handle_env` only parses the enclosure‑SHT41 + elec/winch battery fields when `len(f) >= 12`.
A firmware that emits a partial appendix (6–11 fields) silently drops all of it. Parse each
optional field defensively if partial frames are ever possible.

### 🔧 B3 [Low] `asyncio.get_event_loop()` and `@app.on_event(...)` are deprecated
Used in `pico_serial`, `vision_overlay`, `pipeline`, and both entry points. They work today
(inside a running loop `get_event_loop()` returns it) but are deprecated in 3.12+/modern
FastAPI. Migrate to `asyncio.get_running_loop()` and a FastAPI `lifespan` handler when
convenient. Not urgent.

### 👍 B4 What's already robust (keep it)
- Serial self‑heals with backoff on EOF/disconnect (`_read_loop`).
- Camera auto‑reconnects per‑index with fail counting; single‑camera rigs never poll a missing
  right camera.
- Health is gathered once/second by one background task (`_start_health_loop`) and shared —
  not recomputed per WebSocket client.
- Every optional subsystem degrades to a logged warning instead of killing startup.

---

## C. Performance (Pi 5 is inference‑bound)

### ✅ C1 [Medium] ONNX Runtime ran on defaults
Both ONNX sessions (YOLO detector, water segmenter) were created with no `SessionOptions`.
**Fix:** shared `pi5/cv/ort_utils.py` sets `ORT_ENABLE_ALL` graph optimization, pins
`intra_op_num_threads` to the core count (all four A76s), and prefers XNNPACK when present.

### ✅ C2 [Medium] Stereo SGBM tuning for water
**Fix:** switched to `MODE_SGBM_3WAY` (faster on CPU), added `preFilterCap` (tames glints),
and an **optional WLS post‑filter** (fills the textureless holes water leaves in the disparity
map) gated on `camera.stereo_wls` + `opencv-contrib`. See `docs/vision_optimization.md`.

### 🔧 C3 [High‑value, hardware] Detection backend
Tuned ONNX‑CPU still tops out ~6–13 fps for YOLOv8n. For reliable real‑time detection: export
to **NCNN** (Ultralytics' recommended Pi backend, ~2–3× ONNX‑CPU, no code change) or add the
**Hailo‑8L AI HAT+** (30+ fps, frees the CPU). Documented with numbers in
`docs/vision_optimization.md`.

### 🔧 C4 [Low] Tracker association could be sturdier
`ThreatAssessor._match` is greedy nearest‑centroid within a per‑class gate — fine for a few
sparse objects, but crossing targets of the same class can swap identity. A small IoU/mutual‑
best gate (or a ByteTrack/SORT layer) would harden the approach‑vector estimate that avoidance
and radar tracking rely on.

---

## D. UI / frontend

### ✅ D1 Theme — dropped the orange
Rethemed both templates from the amber HUD to **Abyssal Indigo** (indigo chrome + sky‑cyan
data on cool ink panels), via a semantic token rename (`--amber` → `--accent`) and literal
swaps — 0 residual orange rules, verified in‑browser, no console errors.

### ✅ D2 Surfaced the new backend features
Added an **AVOID** toggle to the vision panel (flashes red while actively steering around a
threat) and a **Cross‑Track** readout to the nav telemetry (signed, S/P side, amber past 5 m,
shows AVOID during an override).

### 👍 D3 The UI was already good
Draggable/collapsible panels, `prefers-reduced-motion` support, `:focus-visible` rings, themed
scrollbars/selection, a NO‑SIGNAL placeholder, and independent stream/detect/tier FPS caps.
The design work here was polish, not rescue.

### 🔧 D4 [Low] Single 1.8k‑line template
`command_center.html` is one big file (CSS + markup + JS). Fine to serve, harder to maintain.
If it grows further, consider splitting the `<script>` into a static JS asset.

---

## E. Tests & tooling
- Suite grew **123 → 159** (added LOS, cross‑track, reactive‑avoidance, pipeline‑override,
  camera grab/account, sim‑obstacle, and motor‑trim tests). All green; `ruff` clean.
- ✅ **Simulator obstacle injection** added (`pi5/navigation/sim_obstacles.py`) — an
  `ObstacleField` + `SimAvoider` drive the *real* avoidance controller into the *real* navigator
  from ground truth, so avoidance now runs end‑to‑end in `run_sim` (DROP OBSTACLE on the map).
- ✅ **Bug‑style escape** (`AvoidanceController`) — the memoryless reactive rule orbited a hazard
  sitting dead on the goal line (reactive local minimum). The controller commits to a side and
  holds until the hazard is *passed* (bearing behind the beam, or a blind pass‑hold once sight is
  lost), so the boat now **routes around and past** a blocking obstacle to the waypoint — verified
  against the real simulator motion model for centered and offset hazards.
- ✅ `CameraProducer` grab/account state machine now has tests (`test_camera.py`).
- 🔧 Remaining gap: an end‑to‑end ONNX detector inference test (the `decode` path is unit‑tested
  with a synthetic tensor, but not a full session run).

---

## Summary of changes made this session
| Area | Change |
|---|---|
| Navigation | Lookahead LOS + ILOS guidance, cross‑track error, mission legs anchored to prev WP |
| Avoidance | Reactive steer‑away wired pipeline → navigator (was dead code); live toggle + endpoint |
| Config | `run_hardware` now reads the `navigation:` block; new `reactive_avoidance` + `stereo_wls` keys |
| Vision perf | ONNX Runtime thread/graph‑opt/XNNPACK tuning; SGBM 3‑way + preFilterCap + optional WLS |
| API/telemetry | `NavStateOut` gains `cross_track_m` / `course_deg` / `avoiding` |
| UI | Abyssal Indigo retheme (both pages); AVOID toggle + Cross‑Track readout |
| Docs | `vision_optimization.md`, `navigation_guidance.md`, this review |
| Tests | +21 (144 total, all green), ruff clean |
