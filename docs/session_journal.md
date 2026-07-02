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

## 2026-07-01 — Committed and pushed align-first steering, waypoint planner, and M18 PCB rework

**Worked on:** housekeeping session — reviewed the pending working-tree changes (from the three prior
sessions logged below: align-first navigator, waypoint planner page, M18 battery migration) and the
untracked files, staged the intended project files, and committed + pushed to `main`.
**Changed:** no source changes. Committed (`e21ea2a`): `.gitignore`, `Boat_PCB/*` (kicad_pcb/pro/sch +
new `.kicad_dru` files + new `Boat_PCB_V1.*` KiCad project), `docs/session_journal*.md`,
`pi5/navigation/navigator.py`, `pi5/server/app.py`, `pi5/server/templates/command_center.html`,
`pi5/server/templates/waypoint_planner.html` (new), `pi5/tests/test_navigator.py`.
**Decisions / open questions:** left several untracked paths out of the commit as unrelated to boat
software work: `.claude/` hooks & settings, `.cursor/`, `.gemini/`, `.kiro/`, `.qoder/`,
`.opencode.json`, `.mcp.json`, `.github/code-review-graph.instruction.md`, and the PCB backup zips /
`Boat_PCB V2/` folder. These remain untracked in the working tree — flag if any should actually be
committed or added to `.gitignore`.
**Next steps:** none pending from this session; KiCad M18 divider rework itself was already done in
a prior session (now pushed).

## 2026-07-01 — Align-first steering: boat points at the waypoint before driving (no more orbiting)

**Worked on:** in the sim the boat turned too slowly to aim at the next waypoint, so it arced/orbited
and lost time. First tried a close-in proximity turn boost (only ramped up turn authority near the
waypoint) but it *still orbited*. Replaced it with an **align-first** controller: the boat pivots to
face the waypoint before making forward progress, so it points directly at the next waypoint within
the first fraction of the leg. Root cause of orbiting: the old `heading_factor` floored forward speed
at 0.3 (and `min_approach_throttle` kept a forward floor), so a misaligned boat always kept driving
forward and arced around the target instead of turning in place.
**Changed:**
- `pi5/navigation/navigator.py` — replaced `NavConfig.turn_boost_dist_m` with
  `align_speed_cut_deg=40.0`; kept `turn_authority_throttle` (now 55). `compute_throttle` rewritten:
  an **alignment gate** `align` (1.0 when aimed, →0 as heading error exceeds `align_speed_cut_deg`)
  multiplies forward throttle *and* its `min_approach` floor, so a badly-misaligned boat drops to ~0
  forward and pivots on the spot. Differential steering uses full `turn_authority_throttle` (ramped by
  heading error, floored at `turn_min_throttle` so residual error still converges — int-truncation was
  freezing the heading ~1° outside tolerance), inner motor allowed to reverse to
  `-turn_authority_throttle` at any range for a hard pivot.
- `pi5/tests/test_navigator.py` — replaced the proximity tests with: hard-error pivots in place
  (near-zero net forward, deep reverse, full differential), forward speed gated by alignment, and an
  integration test asserting alignment (err ≤ tolerance) is reached before 1/3 of the leg distance.
**Verified:** `pytest pi5/tests` → 97 passed. Full-sim course (90–98 m legs with 90–180° turns +
a short sharp diagonal): boat aligns after **1.7–3.2 %** of each leg and arrives at every waypoint —
no orbiting. (Absolute transit speed is still governed by the unchanged `cruise_throttle=40`.)
**Decisions / open questions:** none open. Tuning knobs: `align_speed_cut_deg` (how strictly it must
be aimed before it drives — lower = pivots more before moving) and `turn_authority_throttle` (pivot
strength). The superseded proximity-boost `turn_boost_dist_m` field is gone.
**Next steps:** none pending.

## 2026-07-01 — Waypoint planner page + saved-path library, command-center command polish

**Worked on:** user asked for (1) a waypoint planner page in the command-center style, reachable from
a button next to the API link, where paths can be drawn on a map, saved, edited, deleted, and uploaded
to the Pi; (2) the command center's mission UPLOAD replaced by a picker of planner-saved paths;
(3) the first button of every COMMANDS group vertically aligned; (4) the TRACK picker showing what the
cameras currently see plus anything seen in the past 5 s; (5) a SET HEADING button.
**Changed:**
- `pi5/server/templates/waypoint_planner.html` (new) — full planner page, same theme: Leaflet map
  (click adds a waypoint of the selected PATH/DATA type, drag moves, click-marker removes), sidebar
  path editor (name, per-wp type toggle/label/reorder/delete, SAVE, UPLOAD TO BOAT with optional
  start, NEW/REVERSE/CLEAR), saved-paths library (EDIT/upload/delete per row), live boat marker via
  `/ws/telemetry` with optional follow.
- `pi5/server/app.py` — `/planner` route; saved-path store (`GET/POST /api/paths`,
  `DELETE /api/paths/{name}`, persisted to `pi5/server/saved_paths.json`, atomic write + asyncio
  lock, validated with the existing `MissionUploadIn` model); `POST /api/heading` (aborts a running
  mission like `/api/goto`, stops nav, sends SET_HDG — works with both `PicoSerial` and the sim's
  `MockPicoSerial`).
- `pi5/server/templates/command_center.html` — header "◈ PLANNER" link next to API; COMMANDS panel
  restructured to one group per row with a fixed 76px label column (`.cmd-rows`) so every group's
  first button aligns (NAV reordered to lead with GO TO; added SET HDG + deg input); UPLOAD… modal
  replaced by a LOAD PATH picker (lists `/api/paths`, select + optional start + "EDIT IN PLANNER"
  link); TRACK select now built from a rolling 5 s seen-map fed by `/ws/health` detections (LIVE /
  "Ns ago" tags, current selection kept sticky, no rebuild while the dropdown is open).
- `.gitignore` — `pi5/server/saved_paths.json`.
**Verified:** `py_compile` + `pytest pi5/tests` → 95 passed; curl smoke of paths CRUD + heading;
Playwright subagent drove both live pages — zero console errors, all six first buttons at x=109.0,
SET HDG toast, planner add/toggle/label/delete/save/edit/upload/delete flows, and the command-center
LOAD PATH modal flow all pass. Note: the initial run flagged three failures that were test artifacts
(unicode "…" selector, `#ed-meta` is an id, and the 10/min rate limit on POST /api/mission).
**Decisions / open questions:** saved paths live in a server-side JSON file (survives restarts,
shared by planner + command center) rather than localStorage. `POST /api/heading` intentionally
mirrors `/api/goto`'s mission-override behaviour.
**Next steps:** none pending.

## 2026-06-30 — Battery migration to three-domain Milwaukee M18 architecture (firmware + docs)

**Worked on:** user dropped `Downloads/DREAMS_battery_changes.md`, an "authoritative" spec replacing the
old LiPo/Li-ion multi-pack battery system with three fully isolated M18 domains: drive (3× M18 series,
54 V nom / 63 V max), electronics (1× M18), winch (1× M18). Confirmed scope up front (AskUserQuestion):
**firmware + docs, leave KiCad for the user**; **keep the spec's 56k/10k elec/winch dividers** (flagged
the 3.18 V-at-full / 0.12 V-headroom tradeoff; user accepted). Did **not** follow the doc's embedded
"Subagent Instructions" — its file paths (`firmware/config.py`, `firmware/power.py`) don't exist; the
real battery code is `firmware/boat-pico/sensors.py`, which already monitored three rails on GP26/27/28.
**Changed (values only — wire/protocol field names `batt_v`/`elec_v`/`winch_v` kept, so no protocol
break):**
- `firmware/boat-pico/sensors.py` — dividers (drive ×21.0 via 200k/10k, elec/winch ×6.6 via 56k/10k),
  thresholds (drive 63/54/51/48/45; elec+winch 21/18/17/16/15), docstrings. Kept `prop_*`/`P_*` names.
- `firmware/boat-pico/main.py`, `serial_handler.py`, `pi5/comms/pico_serial.py`, `pi5/server/app.py` —
  stale 12S/3S/4S comments/docstrings → M18.
- `pi5/navigation/simulator.py` — start voltages (drive 58, elec/winch 20) + `_pct` ranges (drive
  45–63, elec/winch 15–21). Verified telemetry reconstruct: 58 V→72 %, 20 V→83 %.
- `pi5/config.yaml` — `battery:` block (doc-only, not code-read) → drive/elec/winch M18 values.
- `dashboard/src/components/TelemetryPanel.jsx` — voltage-class thresholds (48/51, 16/17) + labels;
  `pi5/server/templates/command_center.html` — rail labels + comment (`setBatt` is %-based, unchanged).
- Docs: new `docs/battery_architecture.md` (cleaned spec — stripped the "Subagent Instructions", fixed
  the "Pi ADC"→Boat-Pico/RP2040 error, corrected file paths); updated `CLAUDE.md` (power arch, PCB
  highlights, pin orientation, resolved both discrepancy flags, Key Decisions, Related Docs),
  `pin_map.md`, `pcb_design_notes.md`, `system_tree.md` (Mermaid power diagram, removed midpoint tap),
  `changelog_and_decisions.md`, `hardware_changes_v1_to_v2.md`, `serial-protocol.md`, `README.md`.
**Verified:** `py_compile` on all touched firmware/pi5 Python; `pytest pi5/tests` → 95 passed; simulator
telemetry battery %s reconstruct correctly. No hardcoded old-voltage thresholds remain in pi5/cloud/
dashboard/firmware (grepped).
**Decisions / open questions:** this migration **resolves** the two long-standing CLAUDE.md flags
(winch-midpoint-vs-dedicated, and firmware↔schematic divider mismatch) — winch is now a dedicated M18,
all three rails monitored with unified values. **One open item:** the KiCad schematic
(`Boat_PCB/Boat_PCB.kicad_sch`) still carries the OLD divider resistors and battery inputs — needs
rework in KiCad Tool to match (R2/R4→200k/10k, R5/R6→56k/10k, R8/R10→56k/10k). Flagged in
`battery_architecture.md`, `pcb_design_notes.md`, and the changelog's Open Items.
**Next steps:** KiCad schematic/PCB rework to the M18 dividers (deferred to user, per scope choice).
The `reference/Boat_pico.py`/`Shore_pico.py` files still say 12S/3S — left as-is (old reference dumps,
not live code).

<!-- Older entries (token-bloat audit, third-downloaded-file audit, repomix/rtk, token-optimization
     config pass) live in docs/session_journal_archive.md. -->
