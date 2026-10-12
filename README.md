# D.R.E.A.M.S

Autonomous survey catamaran: CV-based obstacle avoidance, environmental sensing, and cellular
telemetry to a web dashboard.

## Status: V3, starting from scratch

V3 is a ground-up rebuild on new hardware. The carrier PCB is designed and fully routed. **None of
the software has been written yet.** This repo is the clean base it will be written on.

The V2 boat is archived, not deleted. The whole V2 stack is frozen at the tag
[`v2-final`](../../tree/v2-final): RP2040 firmware, the Pi 5 navigation and CV code, the
dashboards, the cloud pipeline, and the V2 board with its docs.

## Layout

```
Boat_PCB/Boat_PCB_V3/     KiCad 10 project: schematic, layout, project-local library
Boat_PCB/Pod_PCB_V3/      the pod board (XIAO ESP32-S3 on the winch tether)
Boat_PCB/Boat_PCB_V3_1/   V3.1 starter carrier: Pi 5 + one Pico 2, an interim board
docs/v3/                  design brief, planning record, BOM, V3.1 notes
CLAUDE.md                 working notes for Claude Code
```

**V3.1 starter carrier (2026-10-10):** an interim board to get the boat moving before the full V3
carrier. It keeps the Pi 5 and the 5 V buck, uses one Raspberry Pi Pico 2 instead of the Teensy, and
runs from one 10S Li-ion pack. It has a CAN chain for the VESCs, RC input, GPS, an on-board SHT41,
a Qwiic port for the TMP119, hull leak probes, ESC headers and the pod tether, on a 98 × 67 mm 2-layer
board. See [`docs/v3/V3_1_STARTER_CARRIER.md`](docs/v3/V3_1_STARTER_CARRIER.md).

**Start with [`docs/v3/V3_DESIGN_BRIEF.md`](docs/v3/V3_DESIGN_BRIEF.md)** for the locked
decisions, the current budget, part choices with their reasons, and the layout traps the first
attempt hit.

## Architecture

```
Raspberry Pi 5 ─ navigation, mission logic, CV, cloud link        Python (not yet written)
  │ USB CDC        the GPIO header carries +5 V from the carrier and nothing else
  └─ Teensy 4.1 ─ real-time I/O                                   C++/Teensyduino (not yet written)
       ├─ CAN via TJA1051 ──► VESC ×2 (node IDs 1, 2) for drive
       ├─ I²C via TCA9548A ─► SHT45 ×2, BNO085, BMP390, ADXL375, BH1750, INA228 ×2
       ├─ UART ─────────────► GPS (M10-25Q) · pod tether · SBUS RC receiver
       ├─ PWM ──────────────► winch ESC, behind a fail-safe-OFF high-side P-FET kill
       ├─ STEP/DIR ─────────► A4988 radar-bar stepper
       └─ GPIO / ADC ───────► WS2812 status LED · hull leak L/R · 12S pack divider
```

The pod is a Seeed XIAO ESP32-S3 on its own board, in `Boat_PCB/Pod_PCB_V3/`. It hangs off the
tether, which carries one RS-485 pair and the electronics pack voltage; the pod makes its own 5 V.

## The board

130.6 × 101.5 mm, 4 layers (JLC04161H-7628, 1 oz outer / 0.5 oz inner, ENIG), 126 footprints, fully
routed (rev D). There are three isolated power domains:

- **Drive:** 12S LiPo, voltage sense only.
- **Electronics:** M18 → 5 V buck → Pi and Teensy. The pod takes the pack voltage through F1.
- **Winch:** M18 → P-FET kill → ESC.

Pack fusing is off-board. On the board, PTCs guard the pod feed (F1) and the LED and SBUS 5 V
outputs (F2, F3).

Open the project in KiCad 10, or check it from the command line:

```bash
kicad-cli sch erc --severity-all Boat_PCB/Boat_PCB_V3/Boat_PCB_V3.kicad_sch
kicad-cli pcb drc --severity-all --schematic-parity Boat_PCB/Boat_PCB_V3/Boat_PCB_V3.kicad_pcb
```

## What changed from V2

| | V2 (`v2-final`) | V3 |
|---|---|---|
| Boat MCU | RP2040 Pico, MicroPython | Teensy 4.1, C++/Teensyduino |
| Drive | Direct servo PWM to AM32/BLHeli ESCs | VESCs as CAN nodes via TJA1051 |
| Drive pack | Milwaukee M18 | 12S LiPo, voltage sense only |
| Pod | RP2040 Pico | XIAO ESP32-S3 on its own board |
| Sensors | SHT41 ×2, BNO085 | SHT45 ×2, BNO085, BMP390, ADXL375, BH1750, INA228 ×2, behind a mux |

V3 contradicts V2 on purpose. Don't try to reconcile the two. See
[`docs/v3/README.md`](docs/v3/README.md).
