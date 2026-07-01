# D.R.E.A.M.S — Changelog & Locked Decisions

Quick reference for Claude Code agents picking up mid-project.
Grounded in `Boat_PCB/Boat_PCB.kicad_sch` and the `firmware/` + `pi5/` source files.

---

## Current Architecture (as Built)

- **Brain:** Raspberry Pi 5 (USB only — no GPIO) + Boat Pico (motor/sensor executor) + Pod Pico
  (underwater).
- **Connectivity:** SIM7600G-H 4G LTE (primary) + Pi 5 WiFi (dock). HC-12 retained only as an
  optional emergency USB-TTL backup dongle — it is gone from the PCB and the old Shore-Pico scheme.
- **Cameras:** 2× USB cameras on Pi 5 USB-A (stereo pair). No CSI cameras.
- **IMU:** BNO085 at I²C 0x4A (GP8/9). Not QMC5883P.
- **VESC comms:** UART0 (GP12/13) from Boat Pico to VESC master; slave via CAN-forward. No MCP2515 HAT.
- **Batteries:** three fully isolated **Milwaukee M18** domains — drive (3× M18 series, 54 V nom),
  electronics (1× M18), winch (1× M18). Supersedes the old 12S-LiPo / 3S-Li-ion / 4S-winch design.
  Firmware + docs updated; KiCad schematic rework pending. See `docs/battery_architecture.md`.
- **Winch power:** dedicated 1× M18 pack (no drive-midpoint tap).

---

## Added Since V1

### Hardware (confirmed in `Boat_PCB/Boat_PCB.kicad_sch`)
- BT4: dedicated 4S LiPo for the winch (XT30 horizontal connector)
- J2: 7-pin "CAN chain" connector — Boat Pico UART0 to VESC master
- J7: 6-pin JST-SH "GPS + Compass" — combined GPS UART + IMU I²C
- J10: 5-pin "IMU" header — BNO085 (replaces QMC5883P)
- J8/J9: winch ESC power and PWM-signal connectors
- R8/R10 + C7: 4S winch battery-monitoring divider wired to GP28 ADC2 *(not yet read by firmware)*
- BT2 + BT3: two 6S LiPo inputs for the 12S series drive rail
- BT1: 3S Li-ion electronics pack
- Pi 5 (external, not on the PCB) with USB CDC to the Boat Pico

### Software
- `pi5/comms/pico_serial.py` + `pi5/comms/protocol.py` — USB serial protocol (SEQ-numbered, XOR-framed)
- `pi5/navigation/` — `navigator.py`, `mission_manager.py`, `geo.py`, `simulator.py` (nav FSM on Pi 5)
- `pi5/cv/` — stereo USB camera pipeline (`camera.py`, `stereo.py`, `detector.py`, `avoidance.py`)
- `pi5/comms/network.py` — WiFi / SIM7600 cellular management
- `pi5/server/` — FastAPI + WebSocket telemetry server
- `dashboard/` — React + Vite + Leaflet dashboard
- `cloud/api/` + `cloud/map-viewer/` — PostGIS backend + heatmap viewer
- Simulation mode (`pi5/config.yaml: mode: simulator`, run via `run_sim.py`)

---

## Removed Since V1

- HC-12 as the primary radio and the Shore-Pico architecture — HC-12 survives only as an optional
  USB-TTL backup on the Pi 5; the PCB has no HC-12 connector
- Single-pack battery system — replaced by three isolated M18 domains (drive 3× M18, electronics
  1× M18, winch 1× M18). The interim 3S-logic / 12S-drive / 4S-winch LiPo design is also retired.
- QMC5883P compass — replaced by BNO085
- NEO-6M GPS — replaced by u-blox M10Q
- PWM ESC control for propulsion — replaced by UART to VESC (winch still uses PWM)

---

## Unchanged from V1

- Boat Pico as low-level controller (MicroPython + uasyncio)
- GP0/GP1 dead on the Boat Pico — do not assign
- GP17/GP18 hull-leak detection (active-low pull-up)
- GP4/GP5 GPS UART1 shared with the Pod
- Winch time-based depth (AS5600 encoder still dead, not replaced)
- Bottom-contact microswitch (Pod Pico GP21)
- XOR-checksum frame format (reused in the USB serial protocol)
- Mission concept: TRANSIT → WINCH → SAMPLE

---

## Locked Decisions — Do Not Revisit

| Decision | What it means |
|----------|--------------|
| Pi 5 uses USB only | No GPIO, SPI, or I²C on the Pi 5 40-pin header. |
| USB cameras (not CSI) | `cv2.VideoCapture(0)` and `(1)`. No Pi Camera, no CSI HAT. |
| HC-12 is USB-backup only | No HC-12 on the PCB; primary shore comms = SIM7600 / WiFi. |
| M18 three-domain batteries | Isolated drive (3× M18 series) / electronics (1× M18) / winch (1× M18); no midpoint tap. |
| BNO085 at 0x4A (not QMC5883P) | `compass.py` talks BNO085; old calibration offsets are invalid. |
| VESC via UART0 GP12/13 | VESC master receives UART; slave via COMM_FORWARD_CAN. |
| THT passives only | Owner preference. No SMD resistors or caps on the boards. |
| No MCP2515 HAT | Pi 5 does not talk CAN; the Boat Pico's UART drives the VESC. |
| Simulation-first | All code must work in simulator mode before touching hardware. |

---

## Active Work Items

1. KiCad PCB layout — `Boat_PCB` schematic complete, layout in progress.
2. `vesc.py` firmware — UART command set being finalized.
3. KiCad schematic — rework battery inputs and dividers to the M18 three-domain design
   (200k/10k → GP26, 56k/10k → GP27, 56k/10k → GP28); firmware + docs already migrated.
4. Port of Oakland partnership — email sent, awaiting engineering contact.

### Done since the earlier draft
- `compass.py` rewritten for BNO085 ✅
- `pi5/cv/` stereo camera pipeline ✅
- FastAPI server + WebSocket (`pi5/server/`) ✅
- React dashboard (`dashboard/`) ✅
- Simulation mode (`pi5/navigation/simulator.py`, `run_sim.py`) ✅
- M18 three-domain battery migration — firmware (`sensors.py`), simulator, dashboards, and docs ✅
  (KiCad schematic rework still pending)

---

## Open Items / Known Discrepancies

- **KiCad schematic lags the M18 migration.** Firmware, the simulator, the dashboards, and the docs
  now use the M18 three-domain design (drive 200k/10k → GP26, elec 56k/10k → GP27, winch 56k/10k →
  GP28; all three rails monitored). `Boat_PCB/Boat_PCB.kicad_sch` still carries the old battery
  inputs and divider resistors — rework it in KiCad Tool to match `docs/battery_architecture.md`.

### Resolved
- ~~Battery dividers & GP28~~ — firmware now monitors all three rails with unified M18 divider values;
  the old firmware↔schematic mismatch no longer exists (only the schematic rework remains).
- ~~Winch supply (dedicated vs midpoint tap)~~ — winch is now a dedicated standalone M18 pack; the
  drive-midpoint tap is removed.
