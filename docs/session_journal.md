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
