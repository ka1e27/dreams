# `docs/v3/`: V3 hardware design knowledge

This folder covers the V3 carrier board in `Boat_PCB/Boat_PCB_V3/`, the pod board in
`Boat_PCB/Pod_PCB_V3/` (brief §5), and the reasons they are built the way they are.

| File | What it is |
|---|---|
| **[`V3_DESIGN_BRIEF.md`](V3_DESIGN_BRIEF.md)** | **Start here.** Locked decisions, the current budget, part choices with their reasons, and the layout mistakes the first attempt made |
| [`V3_1_STARTER_CARRIER.md`](V3_1_STARTER_CARRIER.md) | The V3.1 starter carrier (`Boat_PCB/Boat_PCB_V3_1/`): an interim Pi 5 + Pico 2 board. Power, pin map, connectors, bring-up checks |
| [`V3_PCB_SESSION_CONTEXT.md`](V3_PCB_SESSION_CONTEXT.md) | Design intent from the August 2026 planning session, and what it left open |
| [`DREAMS_V3_parts_footprints.md`](DREAMS_V3_parts_footprints.md) | The BOM as planned, with sourcing links |
| [`../../Boat_PCB/Boat_PCB_V3/lib/README.md`](../../Boat_PCB/Boat_PCB_V3/lib/README.md) | Per-part warnings for the project library: the BMP390 breakout, the ADXL375 pinout, the BNO085 straps |

The two planning files were written outside this repo. They are stored verbatim under a scope note.
If they disagree with the brief or the KiCad files, the brief and the KiCad files win.

## V2 is archived, not deleted

The V2 boat is frozen at tag `v2-final`: RP2040 Picos, MicroPython firmware, the Pi 5 stack,
dashboards, the V2 board and every V2 doc.

```bash
git show v2-final:docs/pin_map.md          # read a V2 file
git checkout v2-final -- docs/pin_map.md   # bring one back into the tree
git worktree add ../dreams-v2 v2-final     # full V2 checkout beside this one
```

Also there: `docs/v3/v3_review_2026-08-05.md`, the 18-section log of the first V3 attempt that the
brief distils, and `docs/v3/kicad_library_status.md`, a 2026-08-04 survey of which parts ship with
KiCad.

## Do not reconcile V3 against V2

V3 contradicts V2 on purpose, and the contradictions are in the places most likely to hurt
someone. These are two different boats, not discrepancies to fix.

| | V2 (`v2-final`) | V3 |
|---|---|---|
| Boat MCU | RP2040 Pico, MicroPython | Teensy 4.1, C++/Teensyduino, a full rewrite |
| Drive | Direct servo PWM to AM32/BLHeli ESCs | VESCs as CAN nodes (IDs 1 and 2) via TJA1051, no MCP2515 |
| Drive pack | Milwaukee M18 | 12S LiPo, voltage sense only |
| Pod | RP2040 Pico, UART through a slip ring | XIAO ESP32-S3 on its own board (`Boat_PCB/Pod_PCB_V3/`); the tether is one RS-485 pair plus pack-voltage power |
| Sensors | SHT41 ×2, BNO085 | SHT45 ×2, BNO085, BMP390, ADXL375, BH1750, INA228 ×2, all behind a TCA9548A |
| Pack voltage | 56k/10k (×6.6) dividers into the Pico's ADC | Electronics and winch through the INA228s; the 12S rail through one 220k/13k, 1 % divider into the Teensy's ADC |
| Pi 5 GPIO | Drove the radar-bar stepper | Carries +5 V only; the stepper moved to the Teensy |

Copying a V2 pin number, divider ratio, protocol field or threshold into V3 without re-deriving it
is exactly the mistake this separation exists to catch.

V2's firmware held throttle at zero until both ESCs were confirmed bi-directional. That gate went
in after a misconfigured ESC ran away on the bench on 2026-07-31. V3 doesn't inherit any of it,
because the drive hardware is different. Its safety interlocks have to be designed again.
