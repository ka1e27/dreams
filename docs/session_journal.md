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

## 2026-07-28 — Applied the pin-map audit to code: winch → GP21, stepper 8× fix, divider ratio

**Worked on:** pulled `e27ee7f` (the Boat_PCB V2 netlist audit below) and applied the three items it
had flagged but left unfixed in code.

**Changed:**
- `firmware/boat-pico/motor_control.py` — winch PWM **GP6 → GP21** (`MW_PIN`). The board routes the
  winch signal to GP21 (J8.1 + J9.1 in parallel); GP6 is the MCP2515's `~INT`, so the old pin drove
  the CAN chip, not the winch ESC. GP21 was unused by firmware, making this the **only** one of the
  five CAN-contested pins (GP2/3/4/6/7) that a pin move can resolve.
- `pi5/cv/stepper.py`, `pi5/config.yaml`, `pi5/cv/stepper_test.py`, `run_hardware.py` —
  `steps_per_rev` **3200 → 400**. The A4988 is half step (MS1 high off the Pi's 3V3, MS2/MS3
  hard-grounded), not 1/16. Verified: a commanded 10° pan now moves 9.9°, not 80°. It also fixes an
  8× *overspeed* — the pulse train ran at 8× the commanded rpm, so the motor was likely skipping
  steps rather than tracking. Docstring rewritten: RESET is tied to SLEEP on the board (so
  `reset_pin` stays null), plus the auto-sleep-resets-the-translator drift caveat and the
  VDD-comes-from-the-Pi dependency.
- `firmware/boat-pico/sensors.py` — **`INV_P_RATIO` 14.0 → 6.6.** User confirmed the physical board
  has **56k/10k fitted on all three** dividers, so every rail reconstructs at ×6.6. At ×14.0 a full
  21 V drive pack reported 16.4 V — under `P_WARN` (17.0), a hair over `P_CRIT` (16.0) — i.e. return-
  to-home on a full battery. Verified all three rails now report 21.00/18.00/17.00/16.00 V exactly
  and trip WARN/CRIT at the right pack voltages.
- Docs synced: `docs/pin_map.md`, `CLAUDE.md`, `docs/battery_architecture.md`,
  `docs/pcb_design_notes.md`, `docs/PROJECT_CONTEXT.md`, `docs/hardware_changes_v2_to_testbench.md`,
  and the `main.py`/`sensors.py`/`esc_telem.py` docstrings. Also fixed a stale row the pulled pin map
  still carried: the PIO buses table listed ESC telemetry on GP19 (the hull-leak connector) after the
  table above it had already moved it to GP11.

**Verified (on the Pi):** `pytest pi5/tests` **293 green**, ruff clean, firmware `py_compile` OK, sim
boots with `/` and `/planner` 200. A static pin-claim sweep over the Boat Pico firmware shows **zero
collisions** and matches `docs/pin_map.md` exactly (GP2/3, 4/5, 7, 8/9, 10, 11, 12–15, 16, 19/20, 21,
26–28 claimed; GP6/17/18/22 free).

**Decisions / open questions:** the audit's "as-built" divider values (×17.92/×4.33/×6.56) came from
the **KiCad netlist, which is the stale copy** — the populated board is 56k/10k throughout. Docs now
say so in all five places and flag the KiCad edit as the outstanding task; 13k/30k/18k aren't in the
on-hand resistor kit, which corroborates they were never fitted. That also **voids the GP27
over-range warning** (4.15 V into a 3.3 V pin) from the previous entry. Nothing committed — tree left
for review.

**Next steps:** unchanged from the entry below except the three items now closed — still open: route
the MCP2515 `~CS`, free GP5 before expecting CAN or GPS to work, fit the 100 nF ADC caps + I²C
pull-ups, update the six divider values in KiCad, reposition the R9/R11/R2 reference texts, re-export
the gerbers under version control.

---

## 2026-07-28 — Boat_PCB V2 netlist audit; pin maps rebuilt from the board; hull leak + ESC telem realigned

**Worked on:** full wiring double-check of `Boat_PCB V2` against the KiCad netlist, then updating every
pin map to match reality. Verified three ways: an S-expression parse of `Boat_PCB.kicad_pcb`, a raw
regex extraction, and `kicad-cli sch export netlist` from the schematic. DRC + ERC run with
`kicad-cli` 10.0.5. Board files were unchanged by the 18 commits pulled from origin, so the audit
holds against current `single-hull-test-bench`.

**Changed:**
- `firmware/boat-pico/sensors.py` — hull leak **GP17/GP18 → GP19/GP20** to match the board's actual
  J16/J15 connectors. On V2, GP17/GP18 are the BNO085's RST/INT on J5, so the old pins were reading
  the IMU's control lines, not leak contacts. Docstring now flags that the quoted divider values are
  the M18 *target*, not what's fitted.
- `firmware/boat-pico/esc_telem.py` — right ESC telemetry **GP19 → GP11**. GP19 is the J16 hull-leak
  connector; a leak switch shorts to GND and would have held the telemetry line low. GP11/GP16 are
  the only unconnected pins on V2, so both taps are now clash-free — all four inputs fit.
- `docs/pin_map.md` — Boat Pico table was missing **ten pins** (GP2/3/6/7/11/16/19/20/21/22). Added
  them plus a verified `Board (V2)` column, a full connector index, the divider-mismatch table, and
  the missing-pull-up / 5 V-on-sensor-connectors warnings. Corrected the stepper section: it claimed
  1/16 microstepping but MS2/MS3 are grounded → **half step**.
- `docs/pcb_design_notes.md` — described a board that doesn't exist (BT2/BT3, F1–F4, XT90 outputs
  J4/J5, DHT11, IMU on J10, "no Pi 5 on this board"). Rebuilt from the netlist; added the CAN
  interface, A4988, DRC/ERC status. It also mislabelled R9 as a leak pull-up.
- `CLAUDE.md` — quick-orientation pin list, Boat_PCB highlights table, architecture diagram.
- `docs/esc_telemetry.md`, `docs/esc_setup.md`, `docs/am32_config.md`, `pi5/scripts/am32_config.py` —
  GP19 → GP11 for the right telemetry tap.
- `firmware/pod-pico/main.py` — docstring was missing GP22 (pressure ADC), which `sensors.py` uses.

**Decisions / open questions:**
- **`pi5/cv/stepper.py` has an 8× error and is NOT yet fixed.** It assumes 1/16 microstepping
  (`steps_per_rev = 3200`) but the board is half step (400). A commanded 10° pan travels 80° and blows
  through the soft limits. One-line fix, left for a deliberate change.
- **Three hard board faults, all inherited from V1:** MCP2515 `~CS` (U1.16) tied to GND (SPI can't
  frame transactions); Pico **GP5 tied to GND** (kills UART1 RX / GPS, and GP4 sits on the MCP2515's
  `SO` output — two drivers on one net); A4988 VDD has no on-board supply, fed only from the Pi's 3V3
  via J3 pad 2.
- **GP2/3/4/6/7 conflict is unresolved and unresolvable by pin moves** — the V2 board commits them to
  the MCP2515, this branch drives ESCs/winch/SBUS/GPS on them, and no free pins remain.
- **Silkscreen swap:** R9's and R11's reference text sit over each other's footprints (verified
  geometrically — 6.32 mm offsets vs. 5.08 mm elsewhere). Fit 1 kΩ at the pad printed "R11" and 10 kΩ
  at "R9". R2's label has drifted over J4.
- **J3's pad numbering is transposed** (odd/even rows shifted one position), so schematic pad *N* =
  Pi pin *N∓1*. Confirmed by 6/6 power-pin alignment and by matching `stepper.py`'s BCM numbers.
  Reading Pi pins off the schematic pad numbers gives a wrong — and alarming — answer.
- Dividers still pre-M18: drive ×17.92 (firmware expects ×14.0), elec ×4.33 (expects ×6.6, and
  over-range on an M18 at 4.15 V into a 3.3 V pin). Fitting 56k/10k on all three gives ×6.6 exactly;
  then set `INV_P_RATIO = 6.6`. Also no ADC filter caps and no I²C pull-ups anywhere.

**Next steps:** fix `stepper.py`'s `steps_per_rev`; rework the three dividers + add the 100 nF ADC
caps and I²C pull-ups; route `~CS` and free GP5 before expecting CAN or GPS to work; reposition the
three reference texts and annotate the mounting holes MH1–MH4; re-export the gerbers (those in
`Boat_PCB V2/` predate the current `.kicad_pcb`) and get them under version control.

---

## 2026-07-28 — Buoy detection was dead on hardware; inference thread budget; health-loop forks; dashboard safety UI

**Worked on:** `/goal` — three max-effort passes: make the stack cheaper on the Pi, *verify* buoy +
person-in-water detection, and fix the dashboard's buttons/clutter. Pass 1 = 4 parallel Opus audits
(read-only, so they added no CPU load); pass 2 = 3 fresh Opus agents re-reviewing my own diff; pass 3 =
verification on the Pi. Everything ran under a 1 Hz `EXT5V`/throttle watchdog with heavy commands pinned
to 2 cores (`nice -n 15 taskset -c 0,1`).

**Headline: the boat could not detect a buoy at all.** The active detector is
`pi5/cv/models/yolov8n_ncnn_model` — generic **COCO, 80 classes, no `buoy`**. `maritime_yolov8n_info.json`
is a placeholder (`mAP50: 0.0`) and its weights are absent, so *nothing* ever emitted the label that
`threat_assessor` grades WARNING and `object_memory` charts as a PERMANENT marker. The entire
"confirm a buoy → drop a GPS marker" feature (docs/object_memory.md) was only ever exercised by the
sim's ground-truth `SimObjectMapper`. The existing buoy/person tests pass because `FakeOverlay` injects
detections — YOLO never runs in them. `water_seg.onnx` is also absent, so Tier-1b hybrid seg is off.

**Changed:**
- `pi5/cv/buoy_detector.py` (NEW) — classical colour/shape buoy screen: one HSV threshold pass +
  contour filter (saturation / solidity / area / aspect), **measured 0.62–0.96 ms/frame** on this Pi
  (640×480→1280×720, ripple noise) vs ~30 ms for a YOLO pass. Emits the same
  `(x1,y1,x2,y2,label,conf)` tuples, so boxes/distance/radar/threat/map all work unchanged.
  **Suppression uses containment, not IoU** — an orange life jacket is a small blob *inside* a large
  `person` box where IoU is tiny, so an IoU gate would have charted a phantom PERMANENT buoy on a
  swimmer. Green is off by default (sunlit foliage) and the top 35% of frame is skipped (sky/treeline).
- `pi5/cv/vision_overlay.py` — `class_conf` per-class confidence floors (backend runs at the lowest
  floor, each box then filtered by its own class) so a distant swimmer survives at 0.25 without
  flooding other classes; `buoy_fallback` that **auto-disables when the loaded model emits `buoy`
  itself**; `_infer_conf` is a property (the CONF slider mutates `_cfg.conf`, so a cached copy went stale).
- `pi5/cv/threat_assessor.py` — `swimmer` was graded **INFO, i.e. not tracked at all**, while
  `object_memory` canonicalises it to `person`. Added it plus jetski/raft/canoe/paddleboard as CRITICAL.
- `pi5/cv/cpu_budget.py` (NEW) + `ncnn_detector`/`onnx_detector`/`ort_utils`/`segmentation` — inference
  no longer pins **all four** Pi 5 cores. Measured (yolov8n@320, NCNN, median of 15): 1 thread 27.9 ms /
  2 → 18.4 / 3 → 19.2 / 4 → 17.7. Thread 2 gets ~96% of the speed-up; **the 4-thread pass drove this Pi's
  sticky throttle flags `0x0` → `0x50000` (under-voltage occurred + throttling occurred)**. Since
  `detect_max_fps: 15` is a 66.7 ms budget, even one thread clears the cap with 2.4× headroom — the extra
  threads bought latency nobody consumes and cost a brown-out. Default is now cores−2; override via
  `camera.detection.num_threads` / `vision.seg_num_threads`.
- `pi5/server/app.py` — the 1 Hz health loop forked **7 `vcgencmd` subprocesses every second, forever**
  (604,800/day). Temp + ARM clock now come from sysfs (~37 µs for both), the 4 voltage rails are sampled
  every 10 s, and `get_throttled` still forks every tick because it *is* the under-voltage alarm.
  Measured 7 → 1.4 forks/s, child CPU **2.5 → 0.5 ms/s**, tick wall time 19.2 → 2.7 ms. During an
  **active** throttle (`_throttled_now`, live bits 0-3 only — the sticky 16-19 bits latch until reboot)
  it spends the fork on `measure_clock arm` so the operator never sees a masked clock while debugging.
- `pi5/server/templates/command_center.html` — removed two **duplicated live-handler** control groups
  from COMMANDS (VISION SEG/YOLO/AVOID and RADAR BAR CENTER/SCAN/STOP); both existed twice, and only
  the surviving copies are the ones `renderVision()` actually keeps in sync. Replaced **every** native
  `window.confirm()` with an in-page `#mConfirm` dialog (a browser can suppress native dialogs
  permanently — unacceptable for ABORT / CLEAR E-STOP / DELETE clip / CLEAR MARKS / ARM PASSTHROUGH /
  ESC WRITE). Added a real focus trap + focus restore + ESC-to-close to back up the new
  `role=dialog aria-modal=true` (aria-modal without a trap is a promise the page was breaking). Put a
  deliberate gap between E-STOP and CLEAR E-STOP. Moved CLEAR MARKS out of the sim-only group — the
  buoy screen charts real markers on hardware now. Added `min-width:0` + 1200/820 px breakpoints for the
  8-group camera bar and `pointer:coarse` tap targets for dockside tablet use.

**Verified (on the Pi):** `pytest pi5/tests` **293 green** (from 247, **+46**), ruff clean, firmware
`py_compile` OK, inline `<script>` passes `node --check`, div balance 304/304, no undefined onclick
handlers. Proved the detection chain on the **live** backend, not a mock: ncnn loads (80 COCO classes) →
fallback auto-activates → `_raw_detect` returned `('buoy', 0.681)` boxed on the target →
`threat_level_for` = WARNING → `category_for` = PERMANENT. Sim booted, `/` and `/planner` 200, `/ws/health`
frames carry correct `temp_c` / `clock_mhz` (tracked 1500↔2400 MHz) / decoded throttle / volts, and
`sysfs` vs `vcgencmd` cross-checked (clock delta 0.0 MHz over 6 samples).

**Pass-2 reviewers found 4 real bugs in my own changes — all fixed:** (1) the volts cache guard used
`_volts_cache is not None`, but off a Pi the reading legitimately *is* None, so it re-forked 4 probes
every tick — worse than before; now keyed off a separate `_volts_sampled` flag. (2) Buoy suppression ran
against *unfiltered* YOLO boxes, so a sub-threshold box (boat @ 0.32 vs its 0.40 floor) could kill a buoy
and then be dropped itself, leaving the operator with neither. (3) `x1`/`y1` weren't clamped to the frame.
(4) The segmentation model silently inherited the new thread count — now explicit via config.
**Rejected:** the per-client telemetry-recompute "MED" finding (~300 µs/s with 1–2 dashboards; not worth
the staleness risk), a raw-BGR recorder pre-roll (+330 MB on a 4 GB Pi — worse than the JPEG ring), and a
claim that `scaling_cur_freq` systematically masks throttling (6 back-to-back samples showed *exact*
agreement with `measure_clock arm` at both 1500 and 2400 MHz; the RPi cpufreq driver queries the
firmware). The concern was still addressed via the throttle-aware fallback above.

**Decisions / open questions:** the classical screen is a **stopgap, not a substitute for a trained
model** — it finds red/orange/yellow buoys by colour, so it will miss unlit black/green marks and wants
on-water tuning of `min_sat` / `roi_top_frac`. Charting a buoy as a *map marker* still needs **stereo
range**, so a mono rig detects and grades buoys but won't place them. This Pi now carries sticky
`0x50000` flags from the thread benchmark — the 27 W PSU swap from the 2026-07-27 entry is still
outstanding and still recommended. Nothing committed — tree left for review.

**Next steps:** on-water pass with a real buoy + camera to tune the colour gates; train/export the
maritime model so the fallback can switch itself off; still-open UI ideas the reviewer and I both rated
low priority (auto-refreshing DIAGNOSTICS instead of 3 manual poll buttons, folding TRIM/ESC into one
DRIVE settings modal).

## 2026-07-27 — Pi 5 power-off during camera record/replay = computer-USB brown-out

**Worked on:** the on-camera hardware pass flagged last session. User reported the Pi 5 **fully powered
off** twice — once while recording, once while replaying a clip — and asked why.
**Root cause: a 5 V brown-out from underpowering.** The bench Pi 5 was powered from the user's **computer
USB port** (~0.5–0.9 A @ 5 V); a Pi 5 needs 5 A/25 W and pulls 1.5–2.5 A+ under the always-on CV stack +
both USB cameras. `vcgencmd pmic_read_adc` showed `EXT5V` idling at only ~5.0 V *with the software
stopped* (no headroom). Recording adds a **VP8 software encode** (`pi5/cv/recorder.py:337`, `VP80`)
across all cores; replay is a cheap static serve (`pi5/server/app.py:1643`) but the CV pipeline still
runs under it — either tips total draw past the port's limit → PMIC undervoltage cutoff → instant off.
Active Cooler fitted + 49 °C idle → thermal ruled out. No code bug.
**Why the crashes left no logs:** journald was volatile (`/var/log/journal` empty, logs in tmpfs) and
rsyslog absent → wiped on reboot.
**Changed (system state, NOT the repo):**
- Enabled **persistent journald** — drop-in `/etc/systemd/journald.conf.d/99-persistent.conf`
  (`Storage=persistent`; machine-id dir now present) so a future hard-off is captured in
  `journalctl -b -1 -k`.
- Added `~/pi_power_monitor.py` (off-repo) — a black-box logger sampling EXT5V/Vcore/temp/throttle to
  `~/pi_power_monitor.csv` with **fsync per line**, so a brown-out preserves readings to the last second.
**Fix given to user:** power the Pi from a real **5 V/5 A USB-C PSU** (official 27 W); do **not** set
`usb_max_current_enable=1` on a weak supply (removes the USB safety cap → worse brown-outs).
**Decisions / open questions:** on the deployed boat the Pi runs off the **M18 → 5 V UBEC**, which faces
the same CV+record peak — offered to switch the recorder **VP8 → MJPG** (cameras already emit MJPG,
near-zero CPU) or trim record fps/res to widen the power margin. **Awaiting user go-ahead**; no code
touched this session.
**Next steps:** user swaps to the 27 W PSU + re-runs record/replay (optionally under
`~/pi_power_monitor.py` to confirm `EXT5V` stays ~5.1 V flat); then decide on the MJPG recorder change
for the boat's UBEC budget.

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
**Dashboard:** folded into the **CAMERA panel** (not a separate box, per follow-up) — a control bar with
a SENTRY arm toggle, manual REC/STOP, a live `● REC` overlay on the feed, and a **RECORDINGS** button
that opens an **ESC-settings-style modal** (`#mRec`): a player beside a severity-coloured clip list
(critical/warning/manual, timestamp, duration, size) with **fullscreen / download / delete** footer
actions. Serve endpoint returns inline (`accept-ranges: bytes` → seeking; download via `<a download>`).
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
**Follow-up (recording duration):** a clip was getting cut off at the ~90 s hard cap while a threat was
still in frame. Reworked the stop logic so a sentry clip now records **until the threat clears** — it
runs on while `note_event` keeps firing and stops only `retrigger_extend_s` (8 s) after the last
sighting; `max_clip_s` (now 300 s) is a per-**segment** cap that **rolls over** into a new file instead
of stopping mid-event, so a persistent threat is never cut off (files stay bounded + prunable). +1 test
(`test_persistent_threat_records_until_it_clears`); verified on the sim (recorded continuously through a
sustained avoidance, stopped ~8 s after the threat went away → one 16.8 s clip).
**Follow-up (retention):** added age-based cleanup — clips older than `max_age_days` (default **14**) are
deleted, alongside the existing `max_clips` count cap. Pruned on every save, at `Recorder` construction,
and hourly by the server feed (`prune_old()`), so stale clips go even with no new recordings. Age comes
from the clip's metadata `started` (falls back to file mtime); `0` keeps forever. Config
`recording.max_age_days`; +2 tests.
**Follow-up (favorites):** a clip can be **favorited** (★) to pin it — favorites are exempt from both the
age sweep and the count cap (but can still be deleted explicitly). `favorite` bool in the clip metadata;
`Recorder.set_favorite()` + `POST /api/recordings/{name}/favorite`; the recordings modal footer got a
FAVORITE toggle and rows show a ★. +2 tests; verified the endpoint + guard on the sim.

<!-- Older entries (right-view box fix + live depth view, stereo vision review + Windows camera fix, live camera assignment, commit/push housekeeping,
     align-first steering, waypoint planner page, M18 battery migration, token-bloat audit,
     third-downloaded-file audit, repomix/rtk, token-optimization config pass) live in
     docs/session_journal_archive.md. -->

