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

## 2026-06-08 — Non-blocking Pico serial read (likely fixes HB timeout AND REFLASH)

**On-Pi test results:** standalone `deploy_pico.py` worked from a clean REPL (all 11 files copied, Pico
reset). Camera confirmed **640x480 @ 30 fps mjpg=True** (fps fix works); right cam absent as expected
(single camera). BUT `run_hardware.py` startup deploy still failed `could not enter raw repl` — so
REFLASH-while-running was NOT dropping the firmware to the REPL.
**Diagnosis:** `serial_handler.read_usb()` did `sys.stdin.buffer.read(64)` — a BLOCKING read that waits
for 64 bytes. Heartbeats (~10 B) and the REFLASH frame (~12 B) never fill 64 B promptly, so they sit
unprocessed → HB ACKs arrive too late (watchdog ESTOPs = the original HB-timeout symptom) and REFLASH
never registers. This one bug likely explains BOTH the HB timeouts and the REFLASH no-op.
**Fixed (firmware):**
- `serial_handler.py` — `read_usb()` now non-blocking: `select.poll(sys.stdin)` + read 1 byte at a
  time while data is available. Added `import select` + a module `_stdin_poll`.
- `main.py` — replaced `asyncio.gather(...)` with `create_task(...)` + a monitor loop that waits on
  `serial.reflash_requested`, then `motor_control.estop()`, cancels all tasks, and returns → drops to
  the REPL (more reliable than raising SystemExit inside a gathered task). Reverted the SystemExit in
  task_serial_rx.
**Verified (Windows):** py_compile OK for both; deploy_pico ruff clean. Runtime is Pi-only.
**CRITICAL next step for user:** the firmware currently ON the Pico still has the blocking read + the
old (non-working) REFLASH, so REFLASH can't install the fix — they must deploy this updated firmware
once more from a clean REPL (BOOTSEL+uf2 wipe, or Thonny stop + remove main.py, then
`python pi5/scripts/deploy_pico.py`). After that: HB should stay alive (boat functional) and boot
auto-deploy via REFLASH should work.

## 2026-06-07 — Cooperative REFLASH so auto-deploy actually works

**Worked on:** the boot auto-deploy was failing — `mpremote.transport.TransportError: could not enter
raw repl`. Diagnosed + fixed.
**Root cause:** the Boat Pico firmware's `task_serial_rx`→`read_usb()` loop continuously reads
`sys.stdin.buffer` (the USB-CDC command channel). That swallows mpremote's Ctrl-C/Ctrl-A REPL-entry
handshake, so mpremote can't take the port **while the firmware is running** — which it always is by
deploy time. No `kbd_intr(-1)` / `boot.py`; it's the raw stdin reads. So you can't mpremote-reflash a
running Pico over the shared USB CDC. (User chose: build cooperative REFLASH.)
**Changed (firmware):**
- `serial_handler.py` — new `reflash_requested` flag + `REFLASH` command (ACK then set flag).
- `main.py` — `task_serial_rx` polls the flag; on set it `motor_control.estop()` then `raise
  SystemExit` to exit the asyncio loop to the bare REPL (frees the USB CDC for mpremote).
**Changed (deploy + docs):**
- `pi5/scripts/deploy_pico.py` — `_request_repl()` writes `$REFLASH,0*91` over pyserial and waits
  1.5 s before the mpremote copy; best-effort (degrades if port busy / pyserial missing).
- `docs/serial-protocol.md` — added §3.13 REFLASH.
**Boot chain now:** run_hardware → deploy sends REFLASH → firmware stops+drops to REPL → mpremote cp +
reset → fresh firmware → Pi connects.
**CRITICAL one-time step:** the Pico currently runs OLD firmware (no REFLASH → NAKs, keeps eating
stdin), so mpremote still fails until the REFLASH-aware firmware is installed once by hand. Reliable
path: BOOTSEL + drag MicroPython .uf2 (wipes filesystem/old main.py) → clean REPL → run
`python pi5/scripts/deploy_pico.py` once. Then boot auto-deploy works.
**Verified (Windows):** ruff clean; serial_handler.py + main.py py_compile OK; REFLASH frame/checksum
correct ($REFLASH,0*91); `_request_repl` degrades cleanly without a port; 95 tests pass. UNTESTED on
hardware: whether `raise SystemExit` cleanly drops uasyncio to the REPL (fallback = manual wipe).
**Next steps:** uncommitted (offered). Bench-test the REFLASH drop on the Pi.

## 2026-06-07 — Camera 10→30 fps (MJPG) + view on-Pico code from command center

**Worked on:** camera was stuck at 10 fps though the sensor does 30; user also couldn't see what code
is actually on the Boat Pico.
**FPS fix:** root cause = producer captured at `camera.fps: 10` and didn't request MJPG; the new
stream cap was 15. Changed:
- `pi5/config.yaml` — `camera.fps` 10→30, added `use_mjpg: true`, `stream_fps` 15→30.
- `pi5/cv/camera.py` — `_open()` requests MJPG fourcc before resolution (far faster over USB, needed
  for 30 fps; OpenCV falls back if unsupported), sets `BUFFERSIZE=1`, logs negotiated WxH@fps.
  `CameraConfig` gained `use_mjpg` (default true), default fps 30.
- `run_hardware.py` — passes `use_mjpg` through.
Capture now 30, stream publishes up to 30 (still live-adjustable via the STREAM FPS slider).
**View on-Pico code:** 
- `pi5/server/app.py` — new `GET /pico/file?name=` reads a file off the Pico via `mpremote cat`
  (same brief serial handoff as /pico/files; path-traversal guarded). Hardware-only.
- `command_center.html` — "⤓ view on pico" button loads the selected file's real contents into the
  Monaco editor so the operator can see exactly what's running (then edit/re-push).
**Verified (sim/Windows):** ruff clean; `/pico/file` → hardware-only notice in sim; traversal → 400;
button+handler present; 95 tests pass. Camera fps only confirmable on the Pi with the real camera.
**Caveat:** view/files/push briefly release the serial link (Pico watchdog ESTOPs ~1-2s, then
reconnects) — fine when not actively driving.
**Next steps:** uncommitted (offered).

## 2026-06-07 — Incorporated vision (detection overlay) + adjustable FPS/camera + configurable model

**Worked on:** pulled vision from the external `ka1e27/D.R.E.A.M.S-Vision-Test` repo into the command
center, researched a marine detection library, made FPS/camera settings adjustable.
**Findings:** the vision-test repo is a dual-thread FastAPI dashboard (capture thread at camera rate +
separate rate-capped YOLO thread → decoupled stream/detect FPS, boxes drawn on the feed, live /control
knobs). No turnkey "marine" pip library exists — practical path is Ultralytics YOLO (already our dep)
with maritime-trained weights (SeaShips / MASTR1325 / Singapore Maritime Dataset / Roboflow Marine
Surveillance / TPH-YOLOv5). User chose: configurable weights, default COCO, drop-in maritime .pt.
**Changed / new:**
- `pi5/cv/vision_overlay.py` (new) — `DetectionOverlay`: subscribes to the shared CameraProducer (NOT
  a 2nd VideoCapture), runs YOLO on a rate-capped asyncio task with inference in a thread executor,
  keeps latest boxes + inference-FPS, `draw()` overlays them, runtime `apply_controls()`. Model path +
  target/highlight classes configurable; degrades to None if ultralytics/model missing.
- `pi5/server/app.py` — inject `_overlay` + `_jpeg_quality`/`_stream_fps_cap` via configure(); `/video`
  now draws boxes on a copy, caps publish rate, uses runtime JPEG quality (stream FPS decoupled from
  detect FPS); `/health` adds `detect_fps`/`detections`; new `GET/POST /api/camera` (detection on/off,
  detect_max_fps, conf, jpeg_quality, stream_fps).
- `run_hardware.py` — build DetectionOverlay from `camera.detection` config, start after camera /
  stop on shutdown; pass overlay + jpeg_quality + stream_fps to configure.
- `pi5/config.yaml` — `camera.detection` block (model/imgsz/conf/detect_max_fps/classes) +
  `stream_fps`/`jpeg_quality`, with maritime-model + NCNN docs.
- `pi5/server/templates/command_center.html` — vision control bar under the feed (DETECT toggle,
  DET-FPS / CONF / QUALITY / STREAM-FPS sliders) + `cam-det` readout (detect fps · detected classes)
  fed from /ws/health; wired to /api/camera (debounced POST).
**Verified (sim/Windows):** ruff clean; imports resolve; `/api/camera` GET/POST apply quality+fps;
`/health` carries detect fields (null in sim — no overlay); `draw()` renders boxes; 6 controls present;
95 tests pass. Real YOLO only runs on the Pi (camera + ultralytics; auto-downloads yolov8n.pt once).
**Next steps:** uncommitted (offered). On the Pi: run_hardware → boxes on /command; swap to a maritime
.pt in config to specialise. Possible follow-up: reuse the overlay detector for AvoidanceLoop (avoid a
2nd model load) if/when avoidance is wired into run_hardware.

## 2026-06-07 — Auto-deploy Boat Pico firmware on Pi boot

**Worked on:** user wants the Pico's Python firmware uploaded on Pi boot (Pico is on USB). This also
addresses the HB-timeout — a Pico without current firmware can't ACK heartbeats.
**Changed / new:**
- `pi5/scripts/deploy_pico.py` (new) — copies `firmware/boat-pico/*.py` to the Pico via mpremote and
  resets it. CLI: `--port`, `--no-reset`. Reads port from config.yaml. Batch copy with per-file
  fallback. Invokes mpremote as **`python -m mpremote`** (via `sys.executable`) so it works under
  systemd's minimal PATH (bare `mpremote` console script wouldn't be found).
- `pi5/scripts/__init__.py` (new) — makes scripts importable so run_hardware can call `deploy()`.
- `run_hardware.py` — on startup, if `serial.deploy_on_start` (default true), deploys firmware +
  waits 2.5s for reboot BEFORE opening the serial link (port must be free for mpremote). Wrapped so a
  deploy failure never blocks startup. Added `import asyncio`.
- `pi5/config.yaml` — new `serial.deploy_on_start: true`.
- `pi5/services/dreams.service` (new) — systemd unit: runs run_hardware.py on boot (After
  network-online, ExecStartPre sleep 5 for USB enumerate). Paths/User are placeholders to edit.
**Boot chain:** power on → systemd → run_hardware → upload firmware + reset Pico → wait → connect +
heartbeat → serve /command.
**Verified (Windows):** ruff clean; deploy_pico finds all 11 boat-pico files; run_hardware imports the
deploy fn; deploy() degrades cleanly (mpremote present here but no /dev/ttyACM0 → fails gracefully,
returns False). Real upload is Pi-only.
**User setup:** `pip install mpremote`; `sudo cp pi5/services/dreams.service /etc/systemd/system/`
(edit paths) → `systemctl enable --now dreams`. deploy_on_start re-uploads every start (set false for
firmware dev).
**Next steps:** uncommitted along with the pod-light changes (offered). Bench-test on the Pi:
firmware should upload, HB timeout should clear once the Pico runs current firmware.

## 2026-06-07 — Pod Pico status light on the Command Center (+ HB-timeout explainer)

**Worked on:** added a POD link light to `/command`; explained the `Timeout on HB` warning.
**Changed:**
- `pi5/server/app.py` `_gather_health()` — added `pod_ok` / `pod_leak` / `pod_age_s`, read from the
  existing `PodBridge` (`_pod.pod_ok` + `_pod.latest.leak_detected`/`timestamp`). Degrades to None if
  no pod bridge.
- `pi5/server/templates/command_center.html` — new POD dot in the header (green=responding,
  amber=responding+leak, red=not responding); leak also raises a prioritised red banner
  ("POD LEAK DETECTED"). Reworked the banner logic to prioritise leak > thermal > throttle.
**Verified (sim):** ruff clean; `/health` → `pod_ok:true, pod_leak:false, pod_age_s:1.3` after a poll;
page has `dot-pod`.
**HB-timeout answer (for the record):** `Timeout on HB seq=N (attempt 3/3)` = the Pi sent a heartbeat
and got no `ACK` back within 2s × 3 retries. Firmware *does* ACK HB (`serial_handler.py:194`), so it
means the Boat Pico isn't replying: Pico not running main.py / wrong or busy `/dev/ttyACM0` (only one
process can own it) / framing-checksum-baud mismatch / Pico reset. The Pico side mirrors this — its
3s watchdog ESTOPs (`CRIT HB_LOST`) if HBs stop. Diagnose: `ls /dev/ttyACM*`, `sudo fuser
/dev/ttyACM0`, `mpremote connect /dev/ttyACM0 repl` to see boot prints; ensure nothing else holds the
port while `run_hardware.py` runs.
**Next steps:** uncommitted (offered). Bench-test run_hardware.py + resolve the HB link on the Pi.

## 2026-06-07 — Added run_hardware.py (real Pico + camera entry point)

**Worked on:** user has a real Pico + camera on the Pi and asked how to use them. Confirmed the gap I'd
flagged: `run_sim.py` was the ONLY runner (mock Pico, no camera). README says "set `mode: hardware`"
but no such key exists in config.yaml and nothing reads it. The `configure()` plumbing already accepts
a `camera=` producer — it was just never instantiated.
**Changed:** `run_hardware.py` (new, top-level) — hardware counterpart to run_sim.py. Wires a real
`PicoSerial(port,baud)` (+ `connect()` + `start_heartbeat()`) and a real `CameraProducer` into
`configure(..., simulator=None, camera=camera)`, then serves the app. Loads `pi5/config.yaml` for
serial/camera/server/heartbeat with sane fallbacks. Degrades gracefully: camera open failure →
`server_app._camera=None` (NO-SIGNAL placeholder); Pico connect failure → logs, keeps serving. On
startup connects Pico + heartbeat (watchdog ESTOPs if heartbeats stop = safe), starts nav + pod;
shutdown reverses it.
**Result on the Pi:** `/command` shows the LIVE camera (MJPEG), real parsed Pico telemetry + working
commands + Push-to-Pico, and real vcgencmd/psutil health — vs the simulator's placeholders.
**Verified (Windows):** ruff clean; module imports cleanly (main() guarded). **NOT testable here** —
no real serial/camera on this box; the connect/camera-open path only runs on the Pi. Mirrors the
working run_sim wiring.
**Pi prereqs documented for user:** `pip install -r pi5/requirements.txt`; `dialout`+`video` groups;
check `/dev/ttyACM0` + `/dev/video0`; single camera is fine (stereo off).
**Next steps:** uncommitted along with the health-metrics changes (offered to commit). Real next step
is bench-testing run_hardware.py on the Pi; also `/pico/push` reconnect still untested on hardware.

## 2026-06-07 — More health metrics on the Command Center

**Worked on:** user asked for more health status points on `/command`.
**Changed:**
- `pi5/server/app.py` `_gather_health()` — added swap, uptime, process count, load average (1/5/15),
  and live network throughput (↓/↑ KB/s, computed from a delta against a new `_net_prev` module
  global). All inside the existing psutil try/except so they degrade to None if psutil is missing.
- `pi5/server/templates/command_center.html` — new SWAP bar + vgrid rows (LOAD, UPTIME, PROCS,
  NET ↓/↑, SDRAM V alongside CORE V); added `fmtUptime()`/`fmtRate()` JS formatters; each field
  shows N/A when its source is unavailable.
**Verified (sim):** ruff clean; `/health` returns the new fields with real values (uptime, procs,
swap, net rates populate after the 2nd sample); all 7 new element ids present in the page. On the Pi,
load avg + voltages will be real (Windows shows emulated load 0.00).
**Next steps:** uncommitted (offered). Still open: hardware `/pico/push` test; real hardware entry
point (live camera + Pico).

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
