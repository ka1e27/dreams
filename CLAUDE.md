# D.R.E.A.M.S — Autonomous Survey Boat

Autonomous catamaran that surveys rivers and lakes: CV-based obstacle avoidance, environmental
sensing (salinity, temperature, depth), cellular telemetry to a web dashboard. The full Pi-side stack
runs in a simulator with no hardware attached.

Repo root on this machine is `Python/D.R.E.A.M.S/`. Older docs and `pi5/services/dreams.service`
still say `COE 2 Autonomous Boat/` — same project, stale name.

---

## Session journal (project convention)

`docs/session_journal.md` is the handoff log between sessions — newest-first, capped at 5 entries,
overflow moves to `docs/session_journal_archive.md`. Read it at session start; append an entry when
you finish a meaningful chunk of work. Locked decisions belong in `docs/changelog_and_decisions.md`,
not here.

---

## Architecture

```
Raspberry Pi 5 ─ Python 3 · FastAPI · asyncio
  navigation, mission FSM, CV, cloud pipeline
  │ USB CDC 115200 (/dev/ttyACM0)
  └─ Boat Pico (A1) ─ RP2040 · MicroPython
       motors, IMU, winch, RC, sensors
       │ 50 Hz PWM GP2/GP3        │ UART1 GP4/5 @ 9600
       ├─ AM32 ESCs (L + R)       └─ Pod Pico (underwater, via slip ring)
```

Navigation runs on the Pi; the Boat Pico is a low-level executor. Sensors live on the Picos with
**two exceptions on the Pi's 40-pin header**: the radar-bar A4988 stepper, and the GPS.

Pi 5 USB: Boat Pico, left camera (`VideoCapture(0)`), right camera (`VideoCapture(1)`, stereo,
120 mm baseline), SIM7600G-H 4G HAT (or HC-12 USB-TTL as emergency backup). USB-C is 5 V in.

| Layer | Stack |
|---|---|
| Pico firmware | MicroPython + uasyncio |
| Pi navigation / server | Python 3 asyncio, FastAPI + WebSocket |
| Dashboard | React + Vite + Leaflet + Recharts |
| Cloud | FastAPI + SQLAlchemy + PostGIS, Docker → Railway/Fly.io |
| CV | OpenCV StereoSGBM + YOLOv8-nano |
| Remote | Tailscale over cellular |

---

## Critical gotchas

These are as-built hardware facts that contradict the schematic, the firmware, or both. They are not
derivable from reading the code — check here before debugging anything that "should work".

**GP9 and GP10 are hard-shorted to GND** on the built board — one solder blob across Pico pads
12/13/14. Consequences: I²C0 is dead (GP9 = SCL0, held low), so `compass.py` needs moving to SoftI2C
on GP14/15 where J7's compass pins actually land; the status NeoPixel on GP10 is dead, and
`status_led.py` has been driving into a short since the board was built. GP9 is also J7.3 / UART1 RX,
which is why the GPS had to move to the Pi.

**GPS is on the Pi, not the Pico** (2026-07-29). u-blox M10 TX → GPIO15, `/dev/ttyAMA0`, **38400** —
*not* the 9600 in `firmware/boat-pico/gps.py`. Read by `pi5/comms/gps_nmea.py` and injected into
`pico.telemetry` via `PicoSerial.set_external_position`. Heading still comes from the Pico compass.
Needs `dtoverlay=uart0`. ⚠ Shares GPIO14/15 with `pi5/scripts/am32_config.py` — unplug the GPS to
flash an ESC.

**Boat_PCB V2 collides with the test-bench firmware.** The board fits an MCP2515 + TJA1051 on
GP2/3/4/6/7 for the VESC/CAN architecture, but this branch drives ESCs as direct servo PWM on GP2/GP3
with SBUS on GP7. GP0/GP1 are dead, so there is no free pin to move them to. Three things *were*
realigned to the board (2026-07-28): hull leak → GP19/20, ESC telemetry → GP16/GP11, winch PWM
GP6 → GP21 (GP6 is the MCP2515 `~INT`).

**Battery dividers are 56k/10k (×6.6) on all three rails** — drive → GP26, electronics → GP27,
winch → GP28. Firmware matches (`INV_P_RATIO = INV_E_RATIO = INV_W_RATIO = 6.6`). `INV_P_RATIO` was
14.0 until 2026-07-28, which made a full 21 V pack report 16.4 V and trip return-to-home. The KiCad
schematic still carries pre-M18 values (220k/13k, 100k/30k, 100k/18k) — **the board is right, KiCad
is stale**.

Other as-built defects: U1 `~CS` is tied to GND (SPI can't frame) and Y1/C1/C2 are unset, so CAN is
non-functional as fitted; J2 has no 120 Ω termination; J3's footprint has the **odd/even rows
transposed** (schematic pad *N* = Pi pin *N∓1*); J7/J11/J13 supply **5 V** to an SHT41 rated 3.6 V
max; no I²C pull-ups on any of the three buses; no ADC filter caps.

**Throttle is gated.** Both drive ESCs must be confirmed bi-directional before throttle is released —
the navigator commands reverse for pivots and avoidance. AM32 bi-directional mode ON, 5S LVC. See
`docs/esc_setup.md`.

---

## Power

Three fully isolated Milwaukee M18 domains, no shared ground except a single star point on the logic
PCB. Per-pack overcurrent is handled by each pack's REDLINK BMS, so there are no individual pack
fuses; on V2 all fuses are off-board. There is no 12S-midpoint tap — the winch is a standalone pack.

```
2× M18 parallel ─► DRIVE (18V nom / 21V max) ─[100A ANL]─┬─[80A]─► ESC L (GP2) → 2814
                                                          ├─[80A]─► ESC R (GP3) → 2814
1× M18 ─► ELECTRONICS ─[15A]─► 5V UBEC → Pi 5 · 3.3V → Pico, sensors
1× M18 ─► WINCH ─[20A]─► MOSFET kill → winch ESC (GP21, J8/J9)
```

Test bench runs 2× M18 in **parallel** — double current and runtime, *not* more voltage. The ~90 A
pack pair is the tighter limit, not the 70 A ESCs. Kv mismatch is trimmed via
`navigation.motor_gain_*` and firmware `COMP_L`/`COMP_R`.

---

## Locked decisions

| Decision | Reason |
|---|---|
| Pi 5 is USB-first, GPIO only where forced | Sensors live on the Picos; stepper and GPS are the exceptions |
| USB cameras, not CSI | No HAT, standard USB stereo pair |
| HC-12 demoted to USB backup | Off the PCB; SIM7600 is the primary link, WiFi at the dock |
| BNO085 (not QMC5883P) | 9-DOF with onboard fusion @ 0x4A |
| Simulation-first | Full stack testable with no hardware |
| THT passives | Reworkability |
| 3-domain M18 | Isolated, hot-swappable, BMS-protected |

---

## Running it

```bash
python run_sim.py                      # navigation stack, simulator mode
python run_hardware.py                 # Pi 5 hardware entry point; degrades off-Pi
cd cloud && docker compose up -d       # PostGIS
cd dashboard && npm run dev            # React dashboard
```

`pi5/config.yaml` carries the `mode:` flag (`simulator` | `hardware`). Off-Pi, the stepper falls back
to mock mode — the dashboard will show the bar panning while no pulse reaches the A4988. `gpiozero`
and `lgpio` are `aarch64`-gated in `pi5/requirements.txt` and are required on the Pi for real motion.

Tests: `python -m pytest pi5/tests -q`.

---

## Where truth lives

Don't restate these here — edit them, and keep the firmware docstrings in sync.

| Doc | Authority |
|---|---|
| `docs/pin_map.md` | Pin assignments, both Picos + Pi (generated from `main.py` docstrings) |
| `docs/serial-protocol.md` | Pi ↔ Pico framing `$<payload>*<xor>\n`, commands, ACK/NAK, alert codes |
| `docs/battery_architecture.md` | Dividers, thresholds, fusing, runtimes |
| `firmware/boat-pico/sensors.py` | Authoritative battery thresholds |
| `docs/pcb_design_notes.md` | Boat_PCB component breakdown |
| `docs/esc_setup.md` · `docs/esc_am32_conversion.md` | ESC config; AM32 conversion is planned, not started |
| `docs/object_memory.md` | GPS-anchored buoy/landmark memory |
| `docs/changelog_and_decisions.md` | Architecture of record |
