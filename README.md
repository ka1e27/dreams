# D.R.E.A.M.S

Autonomous survey catamaran: CV-based obstacle avoidance, environmental sensing, and cellular
telemetry to a web dashboard.

**Website:** https://ka1e27.github.io/dreams/ (the boat, the build log and weekly updates). Its source is in [`website/`](website/).

## Status: V3, starting from scratch

V3 is a ground-up rebuild on new hardware. The carrier PCB is designed and fully routed. **None of
the software has been written yet.** This repo is the clean base it will be written on.

The V2 boat is archived, not deleted. The whole V2 stack is frozen at the tag
[`v2-final`](../../tree/v2-final): RP2040 firmware, the Pi 5 navigation and CV code, the
dashboards, the cloud pipeline, and the V2 board with its docs.

## Layout

```
Boat_PCB/Boat_PCB_V3/     KiCad 10 project: schematic and layout of the V3 carrier
Boat_PCB/Pod_PCB_V3/      the pod board (XIAO ESP32-S3 on the winch tether)
Boat_PCB/Boat_PCB_V3_1/   V3.1 starter carrier: Pi 5 + one Pico 2, an interim board
Boat_PCB/lib/             the dreams_v3 KiCad library all three boards share
docs/v3/                  design brief, planning record, BOM, V3.1 notes
CLAUDE.md                 working notes for Claude Code
```

**V3.1 starter carrier (2026-10-10):** an interim board to get the boat moving before the full V3
carrier. It keeps the Pi 5 and the 5 V buck, uses one Raspberry Pi Pico 2 instead of the full board's two, and
runs from one 10S Li-ion pack. It has a CAN chain for the VESCs, RC input, GPS, an on-board SHT41,
a Qwiic port for the TMP119, hull leak probes, ESC headers and the pod tether, on a 98 × 67 mm 2-layer
board. See [`docs/v3/V3_1_STARTER_CARRIER.md`](docs/v3/V3_1_STARTER_CARRIER.md).

**Start with [`docs/v3/V3_DESIGN_BRIEF.md`](docs/v3/V3_DESIGN_BRIEF.md)** for the locked
decisions, the current budget, part choices with their reasons, and the layout traps the first
attempt hit.

## Architecture

```
Raspberry Pi 5 ─ navigation, mission logic, CV, cloud link        Python (not yet written)
  │ UART on the GPIO header to Pico A, plus a reset line to each Pico
  ├─ Pico A (Pico 2) ─ control                                    C++ (not yet written)
  │    ├─ CAN via TJA1051T/3 ─► VESC ×2 (node IDs 1, 2) for drive, on the PIO (can2040)
  │    ├─ UART ─────────────► SBUS RC receiver
  │    ├─ PWM ──────────────► winch ESC, behind a fail-safe-OFF high-side P-FET kill
  │    ├─ STEP/DIR ─────────► A4988 radar-bar stepper
  │    └─ GPIO / ADC ───────► WS2812 status LED · hull leak L/R · 12S pack divider
  └─ Pico B (Pico 2) ─ sensors                                    C++ (not yet written)
       ├─ I²C via TCA9548A ─► SHT45 ×2, BNO085, BMP390, ADXL375, BH1750, INA228 ×2
       └─ UART ─────────────► GPS (M10-25Q) · pod tether (RS-485)
```

The two Picos sit in sockets under the carrier, with a UART link between them. The Pi talks to
Pico A over a UART on its GPIO header, and Pico B reaches the Pi through Pico A, so USB cables are
optional. Without them the Pi's USB ports stay free for cameras and the modem; with them, either Pico
can be flashed or run its link over USB instead. The Picos replaced the Teensy 4.1 in rev E
(2026-10-13).

The pod is a Seeed XIAO ESP32-S3 on its own board, in `Boat_PCB/Pod_PCB_V3/`. It hangs off the
tether, which carries one RS-485 pair and the electronics pack voltage; the pod makes its own 5 V.

## The board

130.6 × 101.5 mm, 4 layers (JLC04161H-7628, 1 oz outer / 0.5 oz inner, ENIG), 137 footprints, fully
routed (rev E). There are three isolated power domains:

- **Drive:** 12S LiPo, voltage sense only.
- **Electronics:** M18 → 5 V buck → Pi and both Picos. The pod takes the pack voltage through F1.
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
| Boat MCU | RP2040 Pico, MicroPython | Two Pico 2s (RP2350), C++, a new pin map |
| Drive | Direct servo PWM to AM32/BLHeli ESCs | VESCs as CAN nodes via TJA1051 |
| Drive pack | Milwaukee M18 | 12S LiPo, voltage sense only |
| Pod | RP2040 Pico | XIAO ESP32-S3 on its own board |
| Sensors | SHT41 ×2, BNO085 | SHT45 ×2, BNO085, BMP390, ADXL375, BH1750, INA228 ×2, behind a mux |

V3 contradicts V2 on purpose. Don't try to reconcile the two. See
[`docs/v3/README.md`](docs/v3/README.md).

## Sponsors

[PCBWay](https://www.pcbway.com/) sponsors the project's circuit boards.
