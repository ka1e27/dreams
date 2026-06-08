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

## 2026-06-08 — Radar-bar stepper control (A4988 on Pi 5 GPIO, not the Pico)

**Worked on:** implemented `~/Downloads/DREAMS_stepper_instruction (1).md` — A4988-driven
NEMA-17 radar-bar pan, coordinated with the YOLO vision overlay. The user's **revised** instruction
moved the stepper from the Boat Pico to the **Pi 5 GPIO header** (the first Pico draft, `(1).md`'s
predecessor, collided GP18-21 with the hull-leak sensors / SHT41 re-pin mess — the Pi-5 approach
sidesteps all of that).
**Deliberate divergence (flagged, not silently resolved):** driving Pi 5 GPIO breaks the
"**Pi 5 uses only USB — no GPIO**" locked decision in `CLAUDE.md`. The user chose this explicitly;
I implemented it and documented it in `docs/pin_map.md` rather than editing the locked-decisions doc.
**Key engineering call:** stepper stepping is **blocking** (`time.sleep` per pulse). Running it from
an asyncio task would freeze the whole FastAPI server, so the **RadarTracker owns a single daemon
thread** that is the sole motion authority; HTTP endpoints only flip thread-safe flags. Mirrors the
repo's existing graceful-degradation pattern (camera/overlay/psutil): no `gpiozero`/`lgpio` →
StepperMotor runs in **mock mode** (position tracking + real timing, no pin toggles), so `run_sim.py`
and the test suite still work on Windows.
**New:**
- `pi5/cv/stepper.py` — `StepperMotor` (A4988): enable/disable/sleep/wake, trapezoidal-ramped `step`,
  `rotate_degrees`/`rotate_to` (travel-clamped, 0-180° w/o slip ring), `scan`/`scan_async`/`stop_scan`
  (daemon-thread sweep w/ `threading.Event`), absolute position tracking, auto-sleep, `cleanup()`.
- `pi5/cv/radar_tracker.py` — `RadarTracker`: SCAN/TRACK/HOLD/SLEEP on one daemon thread; reads
  detection boxes from the overlay (`boxes()`) and slews to centre a priority target (boat/person)
  via bbox→bearing; reverts to SCAN after `lost_timeout_s`. Defensive: no overlay → just SCANs.
- `pi5/cv/stepper_test.py` — standalone bench test (`python3 pi5/cv/stepper_test.py`), 9 checks, ASCII
  output (Windows console safe). All 9 pass in mock mode.
**Changed:**
- `pi5/cv/vision_overlay.py` — added public `boxes()` accessor (raw xyxy boxes) for the tracker.
- `pi5/server/app.py` — `configure(stepper=, radar=)`; `GET /stepper/status` + `POST /stepper/command`
  (SCAN/STOP/GOTO/CENTER/SLEEP/WAKE/TRACK/HOLD — non-blocking, route to the tracker; available:false
  off-Pi); `_gather_health()` now carries `stepper_angle`/`stepper_state`/`stepper_target_locked`.
- `run_hardware.py` — build StepperMotor + RadarTracker from `stepper:` config, inject, start the
  tracker thread on startup / `radar.stop()` (joins thread + GPIO cleanup) on shutdown. Never blocks startup.
- `pi5/config.yaml` — new `stepper:` block (pins 23/24/25/8, 3200 steps/rev, sweep 0-180, FOV 75,
  priority_classes, initial_mode=SLEEP).
- `pi5/server/templates/command_center.html` — new RADAR BAR panel: SVG compass rose w/ animated
  needle + sweep sector, live angle / mode / lock readouts (from `/ws/health`), SCAN/TRACK/STOP/CENTER
  /WAKE/SLEEP/GOTO buttons (→ `/stepper/command`). Added a 5th grid row.
- `docs/pin_map.md` — new "Radar-bar stepper — Pi 5 GPIO (A4988)" subsection (pin table + boot-state
  caveat); softened the "no GPIO" claim to "no GPIO **for sensors**".
**Verified (sim/Windows):** `py_compile` OK; `ruff check pi5 run_hardware.py` clean; **95 tests pass**;
bench test **9/9** (mock); StepperMotor + RadarTracker smoke-tested (rotate/clamp/scan/stop); endpoint
handlers exercised directly (status, SCAN/GOTO ok, bad-cmd→400, GOTO-no-value→400); booted `run_sim`
and confirmed `/health` carries stepper_* = null, `/stepper/status` → available:false, and `/command`
serves the radar panel + JS hooks. **All GPIO/motor behaviour is Pi-only and UNTESTED on hardware.**
**Boot-state caveat for the user:** GPIO25 (ENABLE) is LOW at boot → coils briefly energised before
software runs; consider an external pull-up if boot quiescent current matters (noted in pin_map.md).
Set `stepper.has_slip_ring: true` only once the slip ring is installed (unlocks full 360°).
**Next steps:** uncommitted (offer). On the Pi: `pip install lgpio gpiozero`, set A4988 VREF≈0.67 V, run
`python3 pi5/cv/stepper_test.py` with the bar free, then drive it from `/command`. Possible follow-up:
let RadarTracker reuse the avoidance detector if avoidance is later wired into run_hardware.

## 2026-06-08 — Implemented dual-SHT41 firmware (re-pin to as-built board)

**Worked on:** user confirmed part = Teyleten **GY-SHT41-D** breakout (×3) and chose **"re-pin
firmware to board"** (PCB is fabricated; firmware adapts). Implemented the temp-sensor firmware to
match the as-built board and documented the conflicts.
**Changed / new:**
- `firmware/boat-pico/sht41.py` (new) — bus-agnostic `SHT41` class (Sensirion SHT4x): 0x44, cmd 0xFD
  high-precision, 6-byte read, CRC8 (poly 0x31), tick→°C/%RH conversion, degrade-safe.
- `firmware/boat-pico/sensors.py` — dropped DHT11 (GP16, not on board). Added two SHT41s on
  **SoftI2C**: #A GP12/13 (J11), #B GP14/15 (J13). SoftI2C because HW I²C0 is held by the BNO085
  (GP8/9). Exposes `air_temp/air_humidity` (A) + `air_temp2/air_humidity2` (B). `read_all_slow()` now
  reads both SHT41s + hull. (`send_env` keeps `%d` → truncates the float to int; bumping ENV to
  `%.1f` to keep SHT41 precision is an optional protocol change, not done.)
- `firmware/boat-pico/main.py` — updated pin-map docstring, `task_slow_sensors` doc, boot prints; added
  a loud as-built-conflict warning print. **Did NOT touch vesc/motor_control/sbus** (safety-critical).
- `docs/pin_map.md` — GP12-15 rows now show SHT41 (board); GP16 = unused; added an "⚠ As-built board
  divergence (GP12–GP16)" callout + two SoftI2C rows in the bus summary with conflict notes.
**⚠ Unresolved blockers (flagged, not fixed):** GP12/13=VESC UART0, GP14=winch PWM, GP15=SBUS still
claim those pins in firmware; on the board they're the temp connectors. VESC/winch/SBUS are mis-pinned
for this board and must be relocated off GP12-15 before the boat can drive AND read temps together —
but the board's winch connector (J8/J9 both pins on GND) and SBUS input have no valid pins (known board
errors). So a full re-pin is blocked on hardware decisions / likely a board respin.
**Board/cabling (part b) — for the fabbed board:** connector pin order is reversed vs the module
(board J11/J13 = [SDA,SCL,GND,V+]; GY-SHT41-D = [VDD,GND,SDA,SCL]) → needs a **crossover cable**
(module VDD→board pin4, GND→pin3, SDA→pin1, SCL→pin2). And **don't use board pin4 (VSYS≈5 V)** for VDD
unless the module is confirmed regulated+level-shifted — feed VDD from 3.3 V (Pico pin36, currently
unconnected) since RP2040 GPIO isn't 5 V-tolerant.
**Verified (Windows):** py_compile OK (sht41/sensors/main); `ruff check pi5` clean; 95 tests pass.
Firmware runtime is Pi/Pico-only (SoftI2C + SHT41 reads untested on hardware).
**Next steps:** user to decide VESC/winch/SBUS relocation (or board respin); bench-test SHT41 reads
once GP12-15 are freed; optionally extend ENV telemetry to carry sensor #2.

## 2026-06-08 — Reviewed temp-sensor wiring (J11/J13) against schematic; flagged SHT41 issues

**Worked on:** user said the two "Temp + Humidity Sensor" connectors will be **SHT41** (I²C, 4-pin),
asked to check the wiring. Re-exported the netlist (`kicad-cli sch export netlist --format kicadsexpr`,
no net labels in sch) and traced J11/J13.
**Findings (verified from netlist):**
- **J11** (0.1″ hdr): pin1→GP12 (I2C0 SDA), pin2→GP13 (I2C0 SCL), pin3→GND, pin4→**VSYS ≈5 V**.
- **J13** (JST-XH): pin1→GP14 (I2C1 SDA, shared w/ J10 IMU + J7 GPS hdr), pin2→GP15 (I2C1 SCL, shared),
  pin3→GND, pin4→**VSYS ≈5 V**.
- GOOD: pin pairs are HW-I²C-legal and SDA/SCL not swappable (RP2040 muxing); two 0x44 SHT41 on
  separate buses (I2C0 + I2C1) is the correct topology for the fixed address.
- ⚠ **5 V V+**: SHT41 abs-max 3.6 V; Pico 3V3-OUT (pin36) is unconnected. Bare SHT41 would be damaged.
  Only OK if using a breakout with onboard 3.3 V LDO + level shift.
- ⚠ **No I²C pull-ups** on any of GP12/13/14/15 (only Pico+connector on each net).
- ✗ **Firmware/docs mismatch**: `sensors.py` + `pin_map.md` describe one **DHT11 (1-wire) on GP16**,
  but GP16 is unconnected in the sch and there's no DHT11 — same sch-vs-firmware divergence flagged
  2026-06-01. To use as wired, firmware needs `I2C(0,sda=12,scl=13)` + `I2C(1,sda=14,scl=15)`, SHT4x
  cmd 0xFD @ 0x44.
**Part confirmed by user:** Teyleten Robot **GY-SHT41-D** breakout (×3), I²C, "3.3–5 V".
**NEW critical finding — connector pinout is reversed vs the module:** GY-SHT41-D pin order is
`VDD·GND·SDA·SCL` (power on pins 1–2), but the PCB connectors put **signals on pins 1–2, power on
pins 3–4**. A straight 1:1 cable would feed module VDD (≤5 V) onto GP12/GP14 → fries the Pico. Fix by
re-assigning the connector footprint to `VDD·GND·SDA·SCL` (target: pin1=3V3, pin2=GND, pin3=SDA GP12/14,
pin4=SCL GP13/15) OR a crossover cable (riskier).
**Power:** still route V+ to **3V3 (Pico pin 36, currently unconnected)**, NOT VSYS(5 V) — RP2040 GPIO
not 5 V-tolerant; couldn't confirm an onboard regulator/level-shifter on the cheap GY board (the
"level-shifted 3–5 V" claim is Adafruit's, blended in by search). 3.3 V is safe either way.
**Pull-ups:** GY modules usually carry onboard 10 k pull-ups → board's lack of them likely moot (verify
2 resistors on module). J13 bus shared w/ J10/J7 → parallel pull-ups ≈3.3 k, still OK.
**Decisions / open questions:** did NOT edit firmware/docs/sch yet — offered to (a) rewrite pin_map.md +
sensors.py to dual-I²C SHT4x (I2C0=GP12/13, I2C1=GP14/15, addr 0x44, cmd 0xFD), (b) spec the schematic
footprint reorder + 3V3 rail. PCB-rework approach (footprint vs crossover cable) is the user's call.
**Next steps:** await user go-ahead on (a)/(b); the footprint reorder + 3V3 reroute are the gating
hardware fixes before any SHT41 can be plugged in safely.

## 2026-06-08 — Self-healing serial read loop + hide Sim Speed on hardware

**Worked on:** user hit a tight error loop on push: `Read loop error: device reports readiness to
read but returned no data (device disconnected or multiple access on port?)` repeating ~every 100 ms;
also asked to drop the Sim Speed control on hardware.
**Cause:** `PicoSerial._read_loop` caught the disconnect exception, slept 0.1 s, and retried the SAME
dead connection forever — never reconnecting (and `... multiple access on port` suggests it can also
fire if a 2nd process, e.g. a manual `deploy_pico.py`, grabs the port while run_hardware holds it).
**Changed:**
- `pi5/comms/pico_serial.py` — read loop self-heals: on any read error it closes the streams and
  re-opens with backoff (0.5→5 s), and treats an empty read as a disconnect. Added `_open_streams()` /
  `_close_streams()`; `connect()` uses them. So a Pico reset/reflash/port-contention recovers cleanly
  instead of spamming.
- `pi5/server/static/index.html` — wrapped the Sim Speed row+slider in `#simSpeedControl` and hide it
  when `/api/sim/speed` returns null (hardware mode, `_sim is None`). Other control sliders stay.
**Verified (sim/Windows):** ruff clean; PicoSerial imports with new helpers; 95 tests pass; dashboard
serves with `#simSpeedControl`; `/api/sim/speed` returns 1.5 in sim (control visible). The reconnect
path is Pi-only (sim uses MockPicoSerial, no read loop) — reasoned, not runtime-tested.
**Note for user:** don't run a manual `deploy_pico.py` while `run_hardware.py` is up — two processes on
/dev/ttyACM0 is itself a cause of that error. Stop run_hardware first, or use the command center push.
**Next steps:** uncommitted at write time (committing now).

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
