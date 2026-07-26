# D.R.E.A.M.S — Autonomous Survey Boat · Project Context

> **Purpose of this file.** A single, self-contained briefing on the whole project, meant to be
> pasted into a Claude chat *project page* as durable context. It synthesizes the repo's authoritative
> docs (`CLAUDE.md`, `docs/pin_map.md`, `docs/battery_architecture.md`, `docs/serial-protocol.md`,
> `docs/changelog_and_decisions.md`, the ADRs) plus the current code and git state. Where those docs
> disagree with the code, the code and the notes below win — divergences are called out explicitly.
>
> **Naming.** The project is **D.R.E.A.M.S**. The working directory / repo root on disk is
> `COE 2 Autonomous Boat/`. There is no `D.R.E.A.M.S/` folder; all paths are relative to the repo root.
> The GitHub repo is `ka1e27/D.R.E.A.M.S`.

---

## 1. What this is

An autonomous **catamaran survey boat** that navigates rivers and lakes, avoids obstacles with
real-time computer vision, collects environmental data (salinity/EC, temperature, depth/pressure,
light), and streams everything to the cloud over 4G cellular. Missions are planned, uploaded, and
monitored remotely from a live web dashboard. The **entire software stack runs in a simulator on a
laptop** before any hardware is attached (simulation-first is a locked principle).

Two hulls, two brushless drive motors (one per hull) for **differential steering**, plus a winch that
lowers an instrumented underwater **pod** on a tether through a slip ring.

---

## 2. Compute architecture at a glance

Three tiers: an intelligent **brain** (Pi 5) and two real-time **executors** (RP2040 Picos).

```
┌───────────────────────────────────────────────────────────┐
│ CLOUD:  FastAPI + SQLAlchemy + PostGIS (Docker) + MapViewer │  ← post-mission heatmaps / playback
└───────────────────────────────┬───────────────────────────┘
                                 │ HTTPS (Caddy auto-TLS)
┌───────────────────────────────┴───────────────────────────┐
│ RASPBERRY PI 5 (Linux, Python 3.11+, asyncio)              │
│  Navigation engine · Mission FSM · CV pipeline (stereo +   │
│  YOLO) · FastAPI + WebSocket server + Command Center UI ·  │
│  Cloud uploader (offline buffer) · network mgmt            │
│  Talks ONLY over USB (no sensor GPIO*)                     │
└───────────────────────────────┬───────────────────────────┘
                                 │ USB CDC @115200 (/dev/ttyACM0)
┌───────────────────────────────┴───────────────────────────┐
│ BOAT PICO (RP2040, MicroPython + uasyncio)                 │
│  Motor control · GPS · IMU · batteries · SBUS RC · winch · │
│  hull-leak · watchdog · status LED · pod UART bridge       │
└──────┬──────────────────────────────────┬─────────────────┘
       │ UART0 → VESC master (CAN→slave)   │ UART1 (shared) → GPS + Pod
┌──────┴───────┐                    ┌──────┴───────────────────────────┐
│ 2× VESC ESC  │                    │ POD PICO (RP2040, underwater)     │
│ (brushless)  │                    │  EC/salinity · water temp · light │
└──────────────┘                    │  · bottom contact · pressure ·    │
                                     │  leak — over slip-ring UART        │
                                     └───────────────────────────────────┘
```

*\*One deliberate exception to "Pi 5 uses only USB": the **radar-bar pan stepper** (A4988) is driven
from Pi 5 GPIO — see §5.4.*

**Division of labor:** navigation, vision, mission logic, and all networking live on the **Pi 5**. The
**Boat Pico** is a low-level executor — it drives motors and reads sensors on command and streams
telemetry. All sensors physically hang off the Picos; the Pi 5 only sees them as serial telemetry.

---

## 3. Repository layout

```
COE 2 Autonomous Boat/            ← repo root (project = D.R.E.A.M.S)
├── CLAUDE.md                     ← master agent context (read first when coding)
├── README.md                     ← product-facing overview
├── run_sim.py                    ← simulator entry point (no hardware)
├── run_hardware.py               ← hardware entry point (real Pi 5 + Pico + cameras)
├── pyproject.toml                ← Ruff + pytest config
├── firmware/
│   ├── boat-pico/                ← RP2040 MicroPython (motor/sensor executor)
│   └── pod-pico/                 ← RP2040 MicroPython (underwater pod)
├── pi5/
│   ├── navigation/               ← navigator, mission_manager, geo, simulator
│   ├── comms/                    ← pico_serial, protocol, pod_bridge, network
│   ├── cv/                       ← camera, stereo, detector, avoidance, pipeline,
│   │                               segmentation, threat_assessor, vision_overlay,
│   │                               radar_tracker, stepper, calibration.npz
│   ├── server/                   ← app.py (FastAPI), auth, models, rate_limit,
│   │                               templates/command_center.html (primary UI)
│   ├── data/                     ← cloud uploader (local JSON buffer)
│   ├── scripts/                  ← stereo calibration, pico deploy
│   ├── services/                 ← systemd units
│   ├── tests/                    ← pytest
│   └── config.yaml               ← mode: simulator | hardware, + all runtime config
├── dashboard/                    ← React + Vite + Leaflet + Recharts (SECONDARY / scaffolding)
├── cloud/
│   ├── api/                      ← FastAPI + SQLAlchemy + PostGIS ingest/query API
│   ├── map-viewer/               ← React heatmap / mission-playback viewer
│   └── docker-compose.yml        ← PostGIS + API for local dev
├── deploy/                       ← Caddy reverse-proxy / HTTPS setup
├── docs/                         ← see §16 for the doc index
└── Boat_PCB/                     ← KiCad 10 project (main carrier board)
```

---

## 4. Hardware bill of materials (key items)

- Raspberry Pi 5 (4 GB or 8 GB)
- 2× Raspberry Pi Pico (RP2040) — Boat Pico + Pod Pico
- 2× VESC-based ESC (one per drive motor; master on UART, slave daisy-chained over CAN)
- 2× brushless outrunner drive motors (IP-rated), one per hull
- Standard hobby ESC for the **winch** (50 Hz PWM), on a swappable spool (survey pod ↔ fishing reel)
- Waveshare **SIM7600G-H** 4G HAT + IoT data SIM (primary link)
- 2× USB wide-angle cameras (**stereo pair**, ~120 mm baseline) — obstacle avoidance + depth
- **BNO085** 9-axis IMU (I²C, sensor-fused heading + tilt) — replaced the old QMC5883P
- **u-blox M10Q** GPS (NMEA over UART) — replaced the old NEO-6M
- SBUS RC receiver (FrSky / Radiomaster) for manual override
- HC-12 433 MHz radio — **emergency backup link only** (USB-TTL dongle; not on the PCB)
- 2× Sensirion **SHT41** temp/humidity (air + enclosure) — replaced the DHT11
- Pod sensors: EC/salinity probe, NTC water-temp thermistor, photoresistor, bottom-contact
  microswitch, submersible pressure transducer, leak contact
- 5× Milwaukee **M18** packs across three isolated domains (see §6)
- 4-conductor slip ring for the underwater pod tether
- 3D-printed PLA catamaran hull sealed with marine epoxy
- Custom `Boat_PCB` carrier board (KiCad)

---

## 5. Pin maps & board (authoritative: `docs/pin_map.md`)

### 5.1 Boat Pico (RP2040, MicroPython)
- **GP0/GP1** — DEAD, do not use (hardware-specific to this Pico module).
- **GP4/GP5** — UART1, shared GPS (u-blox M10Q) **+** Pod Pico bus @ 9600 8N1; `main.py`'s
  `task_uart1_reader` routes lines by `$GP*` vs `$POD` prefix.
- **GP8/GP9** — I²C0, BNO085 IMU @ 0x4A, 400 kHz.
- **GP10** — WS2812 status NeoPixel.
- **GP12/GP13, GP14/GP15** — on the **as-built board** these are the two **SHT41** temp/humidity
  connectors (J11, J13) via bit-banged SoftI2C. ⚠ See the divergence note below.
- **GP16** — unused (was DHT11, not populated).
- **GP17/GP18** — hull-leak switches (port/starboard, active-low pull-up).
- **GP26/GP27/GP28** — ADC battery sense: drive / electronics / winch (see §6).

### 5.2 ⚠ As-built board divergence (GP12–GP15) — an open item on `main`
The fabricated `Boat_PCB` wires GP12–15 to the two SHT41 connectors (verified from the schematic
netlist), and `sensors.py` matches that. **But the firmware also still claims those pins for three
other modules that were never relocated:** `vesc.py` wants UART0 on **GP12/GP13**, `motor_control.py`
wants winch PWM on **GP14**, `sbus.py` wants SBUS on **GP15**. VESC/winch/SBUS **cannot** coexist with
the temp sensors on GP12–15. This is unresolved on `main`. (The `single-hull-test-bench` branch fixes
it for that variant by moving ESCs/winch/SBUS to free header pins — see §14.)

### 5.3 Pod Pico (RP2040, underwater, on the tether)
- **GP0/GP1** — UART0 to the Boat Pico over the slip ring @ 9600 8N1 (`$POLL` → `$POD,…`).
- **GP17** — EC-probe drive (pulsed high during a read). **GP27** — EC sense.
- **GP26** — water-temp NTC (10 kΩ, B=3950). **GP28** — light (photoresistor).
- **GP20** — pod-housing leak (active-low). **GP21** — bottom-contact microswitch.
- **GP22** — submersible pressure transducer (0.5–4.5 V → 0–15 psi via divider). **GP25** — LED.

### 5.4 Raspberry Pi 5 — USB topology + the one GPIO exception
Every sensor hangs off USB; the 40-pin header is otherwise just a power tap. USB map:
`USB-A(1)` → Boat Pico (`/dev/ttyACM0`); `USB-A(2)` → left camera `VideoCapture(0)`; `USB-A(3)` →
right camera `VideoCapture(1)`; `USB-A(4)` → SIM7600 (or USB-TTL HC-12); `USB-C` → 5 V power from the
electronics-pack UBEC; internal WiFi via NetworkManager/`nmcli`.

**Exception — radar-bar pan stepper (A4988) on Pi 5 GPIO** (`pi5/cv/stepper.py`, `config.yaml →
stepper:`). This is the *first and only* thing to drive Pi 5 GPIO directly — a deliberate divergence
from the "USB only" rule, made because the Boat Pico is out of free pins and the bar is tightly coupled
to the camera/vision stack. BCM pins: GPIO23 STEP, GPIO24 DIR, GPIO25 ENABLE (active-low), GPIO8 SLEEP
(active-low); RESET must be held HIGH (jumper to SLEEP by default). 1/16 microstepping fixed in
hardware. Runs in a no-op **mock** mode when gpiozero/lgpio is absent (laptop/simulator), so it never
affects the sim.

### 5.5 The PCB (`Boat_PCB/`, KiCad 10)
`Boat_PCB.kicad_sch` is the source-of-truth for the Boat Pico wiring (schematic format `20260306`).
Notable: a placed **MCP2515 CAN-controller symbol exists but is completely unwired** (a
placed-but-never-connected footprint — it contradicts the "no MCP2515" decision but affects nothing;
should be deleted eventually). THT passives only (owner preference). **The KiCad schematic still
carries the *old* pre-M18 battery divider resistor values** and needs reworking to match
`docs/battery_architecture.md` — this is the main outstanding hardware doc/schematic lag.

---

## 6. Power — three isolated Milwaukee M18 domains (authoritative: `docs/battery_architecture.md`)

Three **fully isolated** M18 domains, no shared ground except a single star point on the logic PCB.
This supersedes all earlier LiPo/Li-ion designs. Per-pack overcurrent/short/over-discharge is handled
by each M18's REDLINK BMS, so no per-pack fuses.

| Domain | Packs | Nominal / Max / Cutoff | Divider → ADC | Reconstruct × | Load |
|---|---|---|---|---|---|
| **DRIVE** | 3× M18 in series | 54 V / 63 V / 45 V | 200 kΩ/10 kΩ → GP26 | ×21.0 (63 V→3.00 V) | both VESCs + motors |
| **ELECTRONICS** | 1× M18 | 18 V / 21 V / 15 V | 56 kΩ/10 kΩ → GP27 | ×6.6 (21 V→3.18 V) | Pi 5, Picos, GPS, IMU, radio, cameras |
| **WINCH** | 1× M18 | 18 V / 21 V / 15 V | 56 kΩ/10 kΩ → GP28 | ×6.6 | winch ESC + motor |

Thresholds (in `firmware/boat-pico/sensors.py`, mirrored for reference in `config.yaml`):
drive warn 51 / crit 48 (→RTH) / cutoff 45 (→ESTOP); elec & winch warn 17 / crit 16 / cutoff 15.
Percentage = `100 × (v − cutoff) / (full − cutoff)`, clamped 0–100.

Fusing: drive 200 A ANL main → 100 A ANL per ESC; electronics 15 A blade; winch 20 A blade (via a
MOSFET kill). **No 12S-midpoint tap** — the winch is a dedicated standalone pack (the old
midpoint-vs-dedicated ambiguity is resolved). Runtime (3× HO 12 Ah drive): ~6.5 h survey / ~19 min
planing; 1× XC 5 Ah electronics ~18 h.

---

## 7. Propulsion & motor control (as on `main`)

- **Drive:** two VESC ESCs. The Boat Pico talks to the **master** over UART0 (GP12/13, 115200) using
  the VESC binary packet protocol (`COMM_SET_DUTY`, CRC16-XMODEM framing); the **slave** is reached by
  wrapping commands in `COMM_FORWARD_CAN` so the master relays them over the VESCs' own CAN bus. VESC
  telemetry (motor temp, RPM, `v_in`, fault codes) is polled back and surfaced in telemetry + alerts.
- **Differential steering:** `SET_THR` sets left/right throttle (−100..+100). `motor_control.py`
  applies pulley compensation (`COMP_L`/`COMP_R`, correcting the catamaran's 18:27 vs 15:30 pulley
  ratios), a trim offset, and a thermal throttle multiplier before commanding duty.
- **Winch:** a plain hobby ESC on **GP14**, 50 Hz servo PWM (`STOP=4915 / MIN=3277 / MAX=6553` in the
  16-bit `duty_u16` domain). Positive = deploy/down, negative = retract/up.
- **Safety gates:** throttle commands are rejected during ESTOP or RC override; the VESC's own ~1 s
  command-timeout is fed by a 10 Hz duty stream.

---

## 8. Serial protocol — Pi 5 ↔ Boat Pico (v1.0, authoritative: `docs/serial-protocol.md`)

- **Frame:** `$<payload>*<xor_checksum>\n` (ASCII), USB CDC @ 115200 8N1. Payload is
  `<MSG_TYPE>,<SEQ>,<fields…>`; SEQ 0–255 wraps and pairs a command with its ACK/NAK; unsolicited
  messages use SEQ=0.
- **Pi 5 → Pico commands:** `SET_HDG`, `SET_THR`, `SET_WINCH`, `REQ_TEL`, `POLL_POD`, `ESTOP`,
  `RESUME`, `HB` (heartbeat), `SET_TRIM`, `CAL_COMPASS`, `RC_OVERRIDE`, `RC_RELEASE`, `GET_STATUS`,
  `REFLASH` (drop to REPL for firmware update).
- **Pico → Pi 5:**
  - `ACK`/`NAK` (NAK reasons: RANGE, PARSE, RC_ACTIVE, ESTOP, TIMEOUT, NO_POD, UNKNOWN)
  - `TEL` @1 s — lat, lon, heading, speed, drive batt V/%, hull state, motor temps L/R, 6-bit health
    flags (GPS, IMU, drive-batt, elec-batt, motor-temp, POD — per the `main.py` health string
    `GPS,IMU,P_BAT,E_BAT,MOT,POD`)
  - `TEL2`/extended @2 s — drive + electronics batt V/%, pitch/roll, IMU cal, drive-rail voltage,
    fault codes
  - `ENV` @5 s — air temp/humidity, water temp, EC, light, bottom contact; v1.1 appendix adds
    enclosure temp/humidity + electronics & winch batt V/%
  - `POD_DATA` (reply to POLL_POD), `STATUS` (reply to GET_STATUS), `ALERT` (unsolicited)
- **Alerts:** `CRIT` (HB_LOST, BATT_CRIT, HULL_LEAK, MOTOR_OVERHEAT, POD_LEAK, ESTOP_AUTO),
  `WARN` (BATT_LOW, MOTOR_HOT, SENSOR_FAULT, POD_LOST), `INFO` (MOTOR_COOL, RC_ON/OFF).
- **Timing:** command timeout 2 s (retransmit ≤3×); heartbeat 1 s; **watchdog 3 s → auto-ESTOP**;
  pod poll 5 s.

---

## 9. Software stack

### 9.1 Boat Pico firmware (`firmware/boat-pico/`)
| Module | Responsibility |
|---|---|
| `main.py` | Async event loop; wires all modules; task scheduler; startup banner + pin map docstring |
| `serial_handler.py` | USB CDC protocol parse/dispatch + telemetry/alert emit |
| `motor_control.py` | Propulsion duty (differential + trim + thermal) and winch PWM; ESTOP/RC gates |
| `vesc.py` | UART0 VESC master driver; slave via `COMM_FORWARD_CAN`; GET_VALUES telemetry parse |
| `gps.py` | u-blox M10Q NMEA parser (UART1 @ 9600); `$G*RMC` → lat/lon/speed |
| `compass.py` | BNO085 IMU driver (I²C0); fused heading + pitch/roll |
| `sensors.py` | 3× battery ADCs, 2× SHT41 (SoftI2C), hull-leak switches |
| `sbus.py` | PIO SBUS receiver (inverted 100 kbd 8E2); 16 channels; RC override / link-loss ESTOP |
| `pod_uart.py` | Shared-UART1 bridge to the Pod Pico (poll/parse) |
| `watchdog.py` | Pi 5 heartbeat monitor → auto-ESTOP on 3 s timeout |
| `status_led.py` | WS2812 mode indicator (ESTOP/CRIT/RC/WARN/ACTIVE/IDLE/BOOT) |
| `sht41.py` | SHT41 SoftI2C driver |

### 9.2 Pod Pico firmware (`firmware/pod-pico/`)
`main.py` (async loop + LED heartbeat), `sensors.py` (water temp, EC, light, bottom contact,
pressure), `leak_detect.py` (debounced leak sensor), `uart_responder.py` (`$POLL` → `$POD,…` reply).

### 9.3 Pi 5 software (`pi5/`)
**navigation/** — `navigator.py` (waypoint steerer, ~5 Hz, **align-first**: heading error gates
forward speed, pivot in place until aligned, then distance-based throttle ramp; avoids orbiting);
`mission_manager.py` (mission FSM, below); `geo.py` (haversine/bearing); `simulator.py` (virtual boat
implementing the same PicoSerial interface).
**comms/** — `pico_serial.py` (async serial I/O, dataclasses for Telemetry/Environment/PodData/Alert),
`protocol.py` (frame encode/decode + XOR checksum), `pod_bridge.py` (pod polling + health),
`network.py` (WiFi/cellular selection + gating cloud uploads).
**cv/** — see §10.
**server/** — `app.py` (FastAPI: REST `/api/status|mission|goto|estop`, WebSocket `/ws/telemetry`
@1 Hz + `/ws/camera` JPEG; wired via `configure()`), `auth.py` (X-API-Key), `models.py` (Pydantic
schemas), `rate_limit.py`, `templates/command_center.html` (primary UI).
**data/** — `uploader.py` (buffers readings + GPS track to local JSON, uploads on interval, flushes
backlog when the network returns).

### 9.4 Mission FSM & entry points
Mission phases: **TRANSIT → WINCH_DOWN → SAMPLING → WINCH_UP → COMPLETE** (deploy the pod to the
seafloor on bottom-contact/timeout, sample at intervals, retract, advance to the next waypoint).
- `run_sim.py` — simulator mode; injects a mock Pico + `BoatSimulator`; serves FastAPI on :8000. No
  hardware needed.
- `run_hardware.py` — production; reads `config.yaml`, wires the real `PicoSerial`, `CameraProducer`,
  and `SurveyVisionPipeline`; degrades gracefully if a camera or the Pico is missing.
Both call `app.configure()` and run the same server; only the component wiring differs.

---

## 10. Computer vision — three-tier survey pipeline (`pi5/cv/pipeline.py`)

Layered on top of the existing detection overlay + radar tracker (it does **not** run a second YOLO):
- **Tier 1 — water segmentation** (`segmentation.py`): cheap, always-on anomaly screen (classical
  OpenCV HSV/edge fallback by default; optional TFLite model if present). Flags debris/oil/algae.
- **Tier 2 — YOLO detection** (`detector.py` / `vision_overlay.py`): YOLOv8-nano, **gated on the
  Tier-1 anomaly trigger** (with hysteresis) to save CPU when the water is clear.
- **Tier 3 — threat assessment** (`threat_assessor.py`): rates detections by distance + approach
  vector; CRITICAL (vessel/person/kayak) always tracks, WARNING (debris/buoy) tracks if approaching,
  INFO/SURVEY are logged; drives the **radar tracker** (`radar_tracker.py` → pan stepper) and raises
  mission alerts when a critical threat closes within a configured distance.
- **Stereo depth** (`stereo.py`, `calibration.npz`): StereoSGBM disparity gives real per-object
  distance (the bounding-box distance labels, e.g. `person 87% 3.2m`) and a live depth view. Baseline
  ~0.32 m; calibrated on WSL2/Linux (Windows DirectShow can't set matching camera modes — a documented
  gotcha). `avoidance.py` can turn depth into a steer-away throttle override.
Config under `config.yaml → vision:` (anomaly threshold, YOLO cooldown/gating, threat tracking,
survey logging).

---

## 11. Web UI, dashboard, cloud

- **Command Center** (`pi5/server/templates/command_center.html`) — the **primary, actively used**
  operator UI, served straight from the Pi 5. Live telemetry, Leaflet map + click-to-place waypoint
  planner, camera feed (LEFT/RIGHT/DEPTH), object-track/radar viz, boat-health panel, ESTOP/RTH,
  camera L/R assignment + rescan, manual radar-bar pan. Amber+cyan monospace sci-fi theme. The
  standalone React `dashboard/` was merged into this and is now secondary/scaffolding.
- **Cloud** (`cloud/`) — FastAPI + SQLAlchemy + **PostGIS** in Docker Compose. Endpoints:
  `POST/GET /api/v1/readings` (batch georeferenced sensor ingest ≤500/req; bbox+time spatial query),
  `POST/GET /api/v1/track` (GPS track for playback), `GET /api/v1/missions` (list). Two spatially
  indexed tables: `sensor_readings`, `mission_tracks`.
- **Map Viewer** (`cloud/map-viewer/`) — separate React+Vite app for **post-mission** heatmaps and
  mission playback (not live).
- **Deploy** (`deploy/`) — Caddy reverse proxy on the Pi 5 with zero-config Let's Encrypt TLS; proxies
  `/api/*` and `/ws/*` to FastAPI (:8000) and serves static dashboard files; HSTS + security headers;
  `tls internal` for local dev.

---

## 12. Connectivity

SIM7600G-H **4G LTE is the primary link** for autonomous missions; **Pi 5 WiFi** at the dock/bench;
`network.mode` = `wifi | cellular | auto` (auto prefers WiFi, falls back to cellular). **Tailscale
VPN** for SSH from anywhere. **HC-12 433 MHz** survives only as an optional emergency USB-TTL backup
dongle — it is *not* on the PCB and is not part of the old Shore-Pico scheme (both retired).

---

## 13. How to run / develop

Simulation-first — the whole stack runs on a laptop with no hardware:
```bash
python run_sim.py                      # navigation stack in simulator mode (serves :8000)
cd cloud && docker compose up -d       # PostGIS + cloud API for local dev
cd dashboard && npm run dev            # React dashboard (optional; command center is primary)
```
Hardware: set `mode: hardware` in `pi5/config.yaml`, flash the Picos (`pi5/scripts/deploy_pico.sh`),
pick a `network.mode`, then `python run_hardware.py`. Tests: `pytest pi5/tests`; lint: Ruff
(`pyproject.toml`). Firmware sanity check on a laptop: `python -m py_compile firmware/boat-pico/*.py`
(the `machine`/`rp2` imports are MicroPython-only, so compile-checking is the practical laptop test).

---

## 14. Current state — branches & recent work

Architecture-of-record lives on **`main`**. Two other branches are active:

| Branch | What it is |
|---|---|
| **`main`** | Production/reference. VESC propulsion, 3× M18 drive, GP12–15 SHT41 (with the unresolved VESC/winch/SBUS pin conflict, §5.2). Latest work: three-tier vision pipeline + threat tracking; stereo depth (per-object distance, live depth view); live camera L/R assignment; align-first steering + waypoint planner; M18 three-domain battery migration. |
| **`single-hull-test-bench`** | A **firmware-only variant** for a simpler single-hull bench rig to validate the stack on real hardware before the full catamaran. Drops VESC/CAN for **two standard hobby ESCs on 50 Hz PWM**; drive rail **2× M18** (not 3×, divider 130 k/10 k → ×14.0). **Keeps both SHT41s** on GP12–15, so propulsion/winch/SBUS move to **free Pico header pins: left ESC GP2, right ESC GP3, winch GP6, SBUS GP7** — which also sidesteps the §5.2 conflict. New `firmware/boat-pico/escs.py`; `motor_control.py`/`sbus.py`/`sensors.py`/`main.py` edited. Committed locally, **not pushed**. Spec: `docs/hardware_changes_v2_to_testbench.md`. |
| **`radar-bar-stepper`** | Earlier branch that introduced the radar-bar pan stepper + command-center health UI. Its tip predates the M18 migration (commit messages still say 12S/4S/3S), so treat it as older/divergent; the stepper itself is documented on `main` in `docs/pin_map.md`. |

### Known discrepancies / open items
1. **KiCad schematic lags the M18 migration** — firmware/simulator/dashboards/docs use the M18
   dividers (200k/10k, 56k/10k ×2); `Boat_PCB.kicad_sch` still has the old resistor values. Rework
   pending.
2. **GP12–15 pin conflict on `main`** (§5.2) — VESC/winch/SBUS vs SHT41. Unresolved on `main`;
   resolved on the test-bench branch by relocating to GP2/3/6/7.
3. **Unwired MCP2515** placeholder in the schematic — delete when convenient.
4. **Stale mentions of DHT11** in `README.md` / `docs/system_tree.md` — the real hardware is 2× SHT41
   (per `sensors.py` + `docs/pin_map.md`).
5. Hobby-ESC arming sequence + pulse range must be bench-verified before the test bench spins motors
   (dumb ESCs hold last PWM — the watchdog→ESTOP→neutral path is the only motor kill).

---

## 15. Locked decisions — do not revisit

| Decision | Meaning |
|---|---|
| Pi 5 uses USB only | No sensor GPIO/SPI/I²C on the Pi 5 header (sole exception: the radar-bar stepper, §5.4). |
| USB cameras, not CSI | `cv2.VideoCapture(0)`/`(1)`; no Pi Camera / CSI HAT. |
| HC-12 = USB backup only | Not on the PCB; primary shore link is SIM7600 / WiFi. |
| 3-domain M18 batteries | Isolated drive (3× series) / electronics / winch; no midpoint tap. |
| BNO085 @ 0x4A (not QMC5883P) | `compass.py` drives a BNO085; old cal offsets invalid. |
| VESC via UART0 GP12/13 | Master over UART; slave via `COMM_FORWARD_CAN`; no MCP2515 HAT / Pi CAN. |
| THT passives only | Owner preference; no SMD on the boards. |
| Simulation-first | Everything must work in simulator mode before touching hardware. |

---

## 16. Doc index (where the detail lives)

| Doc | Contents |
|---|---|
| `CLAUDE.md` | Master agent context; session-journal protocol; MCP knowledge-graph usage |
| `docs/pin_map.md` | Authoritative Boat/Pod Pico pin maps + Pi 5 USB topology + radar-bar stepper |
| `docs/battery_architecture.md` | M18 three-domain reference (dividers, thresholds, fusing, runtimes) |
| `docs/serial-protocol.md` | Pi 5 ↔ Boat Pico protocol v1.0 (frames, commands, telemetry, alerts) |
| `docs/changelog_and_decisions.md` | Locked decisions, added/removed since V1, open discrepancies |
| `docs/hardware_changes_v1_to_v2.md` | V1 → V2 hardware delta |
| `docs/hardware_changes_v2_to_testbench.md` | Single-hull test-bench variant spec (branch) |
| `docs/pcb_design_notes.md` | Boat_PCB component breakdown |
| `docs/system_tree.md` | Mermaid system/power diagram (note: still shows DHT11) |
| `docs/adr/ADR-001…005` | Serial protocol · firmware modularization · Pi 5 nav layering · web dashboard/API · cloud pipeline |
| `docs/session_journal.md` | Running log of recent sessions (newest-first, capped at 5; older in `_archive`) |

### Working conventions (from `CLAUDE.md`)
- **Session journal:** read `docs/session_journal.md` at the start of a session; append a newest-first
  entry at the end. Locked decisions go in `changelog_and_decisions.md`, not the journal.
- **Knowledge graph:** the repo has a `code-review-graph` MCP server — prefer its tools
  (`semantic_search_nodes`, `query_graph`, `get_impact_radius`, `detect_changes`) over blind
  Grep/Glob when exploring or reviewing.
- **Tooling:** Ruff + pytest (`pyproject.toml`); firmware is MicroPython (compile-check on a laptop).
