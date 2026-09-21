# D.R.E.A.M.S — V3

Autonomous survey catamaran: CV-based obstacle avoidance, environmental sensing, cellular telemetry
to a web dashboard.

**This branch is the V3 clean slate.** It holds the V3 carrier PCB and the design knowledge behind
it. There is no application code here yet — V3 is a from-scratch rebuild, and the V2 stack it
replaces lives on [`main`](../../tree/main).

## Layout

```
Boat_PCB/Boat_PCB_V3/     KiCad 10 project — schematic, layout, project-local library
docs/v3/                  design brief, planning material, full review log
docs/                     two V2 docs carried over for their numbers
```

**Start with [`docs/v3/V3_DESIGN_BRIEF.md`](docs/v3/V3_DESIGN_BRIEF.md)** — locked decisions, the
current budget, part choices with their reasons, and the layout traps the first attempt hit.

## The board

132 × 108.4 mm, 4 layers (JLC04161H-7628, 1 oz outer / 0.5 oz inner, ENIG). 108 footprints, fully
routed. A Teensy 4.1 carrier: VESC drive over CAN, eight sensors behind a TCA9548A I²C mux, three
isolated power domains, a fail-safe-off winch kill, and a Raspberry Pi 5 on the GPIO header.

Open the project in KiCad 10, or check it from the command line:

```bash
kicad-cli pcb drc --severity-all Boat_PCB/Boat_PCB_V3/Boat_PCB_V3.kicad_pcb
```

## Architecture

```
Raspberry Pi 5 ─ navigation, mission FSM, CV, cloud pipeline
  │ USB CDC
  └─ Teensy 4.1 ─ motors, IMU, winch, RC, sensors
       ├─ CAN ──► VESC ×2
       ├─ I²C mux ──► SHT45 ×2, BNO085, BMP390, ADXL375, BH1750, INA228 ×3
       └─ UART ×2 ──► pod board (XIAO ESP32-S3, submerged)
```

## What changed from V2

| | V2 (on `main`) | V3 |
|---|---|---|
| Boat MCU | RP2040 Pico, MicroPython | Teensy 4.1, C++/Teensyduino |
| Drive | Direct servo PWM to AM32/BLHeli ESCs | VESCs as CAN nodes via TJA1051 |
| Drive pack | 3× M18 | 12S LiPo, voltage sense only |
| Pod | RP2040 Pico | XIAO ESP32-S3 on its own board |
| Sensors | SHT41 ×2, BNO085 | SHT45 ×2, BNO085, BMP390, ADXL375, BH1750, INA228 ×3, behind a mux |

V3 contradicts V2 deliberately. Do not reconcile them — see
[`docs/v3/README.md`](docs/v3/README.md).
