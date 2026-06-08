# D.R.E.A.M.S — Autonomous Survey Boat
## Context File for Claude Code Agents

This is the master context document for the D.R.E.A.M.S autonomous survey catamaran project.
Read this before touching any file in the repo.

> **Naming:** the project is named **D.R.E.A.M.S**, but the working directory on disk is
> `COE 2 Autonomous Boat/`. There is no `D.R.E.A.M.S/` directory — paths below are relative to the
> repo root (the `COE 2 Autonomous Boat/` folder).

---

## Session Journal — read at start, write at end (REQUIRED)

`docs/session_journal.md` is a running log of what each Claude Code session worked on. It exists so a
fresh chat can pick up where the last one left off.

1. **At the start of every session:** read `docs/session_journal.md` (entries are newest-first) to
   understand recent work, open questions, and next steps before doing anything else.
2. **At the end of every session** — or once you've finished a meaningful chunk of work — **append a
   new entry to the top** of the journal (under the `New entries below this line` marker) using the
   template in that file. Keep it short and factual: what changed, why, what's left.

This is the narrative of in-progress work. Locked decisions and the architecture-of-record still live
in `docs/changelog_and_decisions.md` — don't duplicate them in the journal.

---

## What This Project Is

An autonomous catamaran survey boat that navigates rivers and lakes, avoids obstacles using
computer vision, collects environmental sensor data (salinity, temperature, depth), and streams
everything to the cloud in real time. Missions can be planned, uploaded, and monitored remotely
through a web dashboard. The full software stack runs in a simulator on a laptop before any
hardware is attached.

---

## Architecture at a Glance

```
┌─────────────────────────────────────────────────┐
│             Raspberry Pi 5 (4/8GB)              │
│  Python 3 · FastAPI · asyncio · USB cameras     │
│  Navigation logic, mission FSM, cloud pipeline  │
│  USB CDC to Boat Pico · SIM7600 cellular        │
└────────────────┬────────────────────────────────┘
                 │ USB CDC (115200)
     ┌───────────┴───────────┐
     │     Boat Pico (A1)    │  RP2040 · MicroPython
     │  motors, GPS, IMU,    │
     │  winch, RC, sensors   │
     └───────────────────────┘
            │ UART0 (GP12/13)         │ UART1 (GP4/5)
     ┌──────┴──────┐           ┌───────┴────────┐
     │  VESC Master│           │   Pod Pico     │ underwater, via slip ring
     └──────┬──────┘           └────────────────┘
            │ CAN-forward
     ┌──────┴──────┐
     │  VESC Slave │   (two brushless motors, one per hull)
     └─────────────┘

Pi 5 USB peripherals (NO GPIO/UART/I2C/SPI on the 40-pin header):
  USB-A (1) → Boat Pico (CDC ACM → /dev/ttyACM0)
  USB-A (2) → Left USB camera  (cv2.VideoCapture(0))
  USB-A (3) → Right USB camera (cv2.VideoCapture(1), stereo pair, 120mm baseline)
  USB-A (4) → SIM7600G-H 4G HAT, OR a USB-TTL HC-12 dongle (emergency backup)
  USB-C     → 5V power in (from the 3S logic-domain buck)
  Internal  → Pi 5 onboard WiFi (dock/dev link)
```

Navigation logic runs on the Pi 5. The Boat Pico is a low-level executor. All sensors live on the
Boat Pico or the Pod Pico — the Pi 5 only talks USB.

---

## Hardware — What's Actually on the PCBs

The KiCad 10 project lives in the repo (schematic format version `20260306`, generator `eeschema`):

- `Boat_PCB/Boat_PCB.kicad_sch` — the main carrier/breakout board (source of truth for the Boat Pico
  wiring). Detailed component list in `docs/pcb_design_notes.md`.

### Boat_PCB highlights
| Group | Refs | Notes |
|-------|------|-------|
| Compute | A1 | RaspberryPi_Pico |
| Batteries | BT1 3S (XT60), BT2 6S (XT60), BT3 6S (XT60), BT4 4S (XT30) | BT2+BT3 in series = 12S drive rail |
| Fuses | F1 (ATO blade), F2/F3/F4 (off-board) | |
| Battery dividers | R2/R4 (12S), R5/R6 (3S), R8/R10 (4S winch) | See discrepancy note below |
| Drive output | J4/J5 (XT90, VESC L/R), J6 (XT60, "6s output") | |
| VESC comms | J2 ("CAN chain", 7-pin) → Pico UART0 GP12/13 | |
| Winch | J8 (4S power), J9 (PWM, GP14) | |
| Sensors | J7 (GPS+compass), J10 (IMU), J11/J13 (DHT11), J12 (LED), J15/J16 (hull leak) | |

### No HC-12 on the boat PCB
The HC-12 radio is **not** on either PCB and is no longer part of the old Shore-Pico architecture.
It is retained only as an **optional emergency backup link**, plugged into a Pi 5 USB-A port as a
USB-TTL dongle (alternative to the SIM7600). The primary shore link is SIM7600 cellular; WiFi is used
at the dock. See `docs/pin_map.md` and the project `README.md`.

---

## Pin Maps

The authoritative pin maps live in **`docs/pin_map.md`**, generated from the Boat Pico and Pod Pico
`main.py` docstrings. Do not duplicate them here — edit `docs/pin_map.md` and the firmware docstrings
together. Quick orientation only:

- **Boat Pico:** GP0/GP1 dead. GP4/5 UART1 (GPS M10Q + Pod, shared 9600). GP8/9 I²C0 (BNO085 @ 0x4A).
  GP10 status NeoPixel. GP12/13 UART0 (VESC master, 115200). GP14 winch PWM. GP15 SBUS (PIO).
  GP16 DHT11. GP17/18 hull leak. GP26 ADC propulsion 12S, GP27 ADC electronics 3S, **GP28 spare**.
- **Pod Pico:** GP0/1 UART to Boat Pico (slip ring). GP17 EC drive, GP20 leak, GP21 bottom contact,
  GP22 pressure, GP26 water-temp NTC, GP27 EC sense, GP28 light.

> ⚠ **Known discrepancy — battery dividers / GP28.** The `Boat_PCB` schematic uses **220k/13k** (12S),
> **100k/30k** (3S), and **100k/18k** from BT4 (4S winch) to **GP28 ADC2**. The current firmware
> (`firmware/boat-pico/sensors.py`) instead uses **3.3k/47k** (12S) and **15k/100k** (3S), monitors
> only those two rails, and leaves **GP28 unread ("spare")**. The PCB's 4S-winch sense circuit is not
> yet implemented in firmware. Resolving this is out of scope for the docs; it's flagged here.

---

## Serial Protocol: Pi 5 ↔ Boat Pico

The full protocol spec (v1.0) is in **`docs/serial-protocol.md`** — frame format
`$<payload>*<xor_checksum>\n` at 115200 8N1 over USB CDC, with SEQ-numbered commands
(SET_HDG, SET_THR, SET_WINCH, ESTOP/RESUME, HB heartbeat, POLL_POD, GET_STATUS, …) and unsolicited
responses (ACK/NAK, TEL @1s, ENV @5s, POD_DATA, STATUS, ALERT). See that file for the authoritative
field layouts and alert codes. Do not restate it here.

---

## Repo Structure

```
COE 2 Autonomous Boat/            ← repo root (project name: D.R.E.A.M.S)
├── CLAUDE.md                     ← this file
├── README.md
├── CONTRIBUTING.md
├── pyproject.toml                ← Ruff + pytest config
├── run_sim.py                    ← simulator entry point
├── firmware/
│   ├── boat-pico/                ← RP2040, MicroPython (Boat Pico)
│   │   ├── main.py               ← entry point + pin-map docstring
│   │   ├── vesc.py               ← UART0 VESC control (GP12/13)
│   │   ├── motor_control.py      ← VESC duty + winch PWM (GP14)
│   │   ├── compass.py            ← BNO085 I²C0 driver (GP8/9)
│   │   ├── gps.py                ← u-blox M10Q UART1 (GP4/5)
│   │   ├── sensors.py            ← battery ADCs, DHT11, hull leak
│   │   ├── sbus.py               ← PIO SBUS receiver (GP15)
│   │   ├── pod_uart.py           ← Pod poll/response over shared UART1
│   │   ├── serial_handler.py     ← USB CDC Pi 5 protocol
│   │   ├── watchdog.py           ← Pi 5 heartbeat → auto-ESTOP
│   │   └── status_led.py         ← WS2812 NeoPixel (GP10)
│   └── pod-pico/                 ← RP2040, MicroPython (underwater pod)
│       ├── main.py
│       ├── sensors.py            ← EC probe, NTC, pressure, light, bottom contact
│       ├── leak_detect.py        ← pod leak sensor (GP20)
│       └── uart_responder.py     ← UART0 poll-response (GP0/1)
├── pi5/
│   ├── comms/                    ← network.py, pico_serial.py, pod_bridge.py, protocol.py
│   ├── cv/                       ← camera.py, stereo.py, detector.py, avoidance.py
│   ├── navigation/               ← navigator.py, mission_manager.py, geo.py, simulator.py
│   ├── server/                   ← app.py, auth.py, models.py, rate_limit.py, static/
│   ├── data/                     ← cloud data uploader (offline buffer)
│   ├── scripts/                  ← stereo calibration, pico deploy utilities
│   ├── services/                 ← systemd unit files
│   ├── tests/                    ← pytest unit tests
│   ├── config.yaml               ← mode: simulator | hardware
│   └── requirements.txt
├── dashboard/                    ← React + Vite + Leaflet + Recharts
├── cloud/
│   ├── api/                      ← FastAPI + SQLAlchemy + PostGIS
│   ├── map-viewer/               ← React heatmap / mission-playback viewer
│   └── docker-compose.yml        ← PostGIS for local dev
├── docs/
│   ├── pin_map.md                ← authoritative pin maps
│   ├── serial-protocol.md        ← authoritative serial protocol (v1.0)
│   ├── system_tree.md            ← Mermaid system diagram
│   ├── changelog_and_decisions.md
│   ├── hardware_changes_v1_to_v2.md
│   ├── pcb_design_notes.md
│   └── adr/                      ← ADR-001 … ADR-005
├── deploy/                       ← HTTPS / hosting setup
└── Boat_PCB/                     ← KiCad 10 project (main board)
```

---

## Simulation-First Development

`pi5/config.yaml` carries a `mode:` flag (`simulator` or `hardware`). In simulator mode,
`pi5/navigation/simulator.py` mocks GPS, the Pico serial link, and motion, so the Pi 5 software stack
runs on a Windows laptop with no hardware attached.

```bash
python run_sim.py                      # run the navigation stack in simulator mode
cd cloud && docker compose up -d       # PostGIS for the cloud API
cd dashboard && npm run dev            # React dashboard
```

---

## Software Stack

| Layer | Technology |
|-------|-----------|
| Boat / Pod Pico firmware | MicroPython + uasyncio |
| Pi 5 navigation | Python 3 + asyncio |
| Pi 5 server | FastAPI + WebSocket |
| Dashboard | React + Vite + Leaflet + Recharts |
| Cloud API | FastAPI + SQLAlchemy + PostGIS |
| Cloud hosting | Docker → Railway or Fly.io |
| Database | PostgreSQL + PostGIS |
| Computer vision | OpenCV StereoSGBM + YOLOv8-nano, stereo USB cameras |
| Remote access | Tailscale VPN (SSH to Pi 5 over cellular) |
| Connectivity | SIM7600 4G LTE (primary), Pi 5 WiFi (dock), HC-12 USB (emergency backup) |

---

## Power Architecture

```
BT2 (6S) ──┐
            ├── series ──► 12S drive rail (50.4V) ── J4 → VESC left  (XT90)
BT3 (6S) ──┘                                       └─ J5 → VESC right (XT90)
                                                    └─ J6 "6s output" (XT60)

BT1 (3S Li-ion) ──► Logic rail (12.6V) → 5V buck → Pi 5 (USB-C)
                                        → 3.3V → Boat Pico, sensors

BT4 (4S LiPo)   ──► Winch ESC (J8, XT30)
```

> ⚠ **Known discrepancy — winch power source.** This project carries both a dedicated **BT4 (4S)**
> winch pack *and* a **J6 "6s output"** connector, and `docs/system_tree.md` depicts a **6S midpoint
> tap → winch ESC**. The earlier reference docs claimed "BT4 is dedicated; never tap the 12S
> midpoint," which conflicts with the midpoint tap shown in `system_tree.md`. The intended winch
> supply is unresolved — flagged here, not fixed.

---

## Key Decisions (Locked)

| Decision | Reason |
|----------|--------|
| Pi 5 uses only USB — no GPIO | All sensors on the Picos; Pi 5 is just the brain |
| USB cameras, not CSI | Simpler wiring, no HAT; stereo pair on standard USB |
| HC-12 demoted to USB backup | Removed from the PCB; kept only as an emergency USB-TTL link |
| BNO085 (not QMC5883P) | Full 9-DOF IMU at I²C 0x4A with onboard fusion |
| VESC via UART0 (not CAN HAT) | VESC master on GP12/13; slave reached via COMM_FORWARD_CAN |
| Simulation-first dev | Full stack testable without any hardware |
| THT passive components | Owner preference for reworkability |

---

## Related Docs

- `docs/pin_map.md` — authoritative pin assignments (both Picos + Pi 5 USB)
- `docs/serial-protocol.md` — Pi 5 ↔ Boat Pico protocol (v1.0)
- `docs/system_tree.md` — Mermaid system/power diagram
- `docs/pcb_design_notes.md` — Boat_PCB component breakdown
- `docs/hardware_changes_v1_to_v2.md` — V1 → V2 hardware delta
- `docs/changelog_and_decisions.md` — locked decisions + active work items
- `docs/adr/` — architecture decision records (001–005)
