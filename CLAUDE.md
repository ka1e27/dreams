# D.R.E.A.M.S — V3 branch

**This branch is a clean slate for V3.** It carries the hardware design and the design knowledge,
and no application code. If you are looking for the running boat stack — the Pi 5 navigation code,
the firmware, the dashboard, the cloud pipeline — it is not here. It is on `main`.

```
git show main:pi5/server/app.py        # read a file from the old stack
git checkout main -- pi5/              # bring a subsystem back if V3 needs it
```

Nothing was lost. ~35,000 lines of V2-era code and ~8,500 lines of V2-specific documentation were
removed from this branch only, and every commit is still on `main`.

---

## What is here

| | |
|---|---|
| `Boat_PCB/Boat_PCB_V3/` | The V3 carrier board — schematic, layout, project-local symbol/footprint library |
| `docs/v3/V3_DESIGN_BRIEF.md` | **Start here.** Locked decisions, current budget, part choices, and the layout mistakes the first attempt made |
| `docs/v3/` | The rest of the V3 planning material — original design intent, BOM, the V2/V3 fence |
| `docs/battery_architecture.md` | Carried over from V2 — pack topology and the current figures the brief cites |
| `docs/changelog_and_decisions.md` | Carried over from V2 — architecture of record |

---

## V3 at a glance

```
Raspberry Pi 5 ─ navigation, CV, cloud pipeline        (to be written)
  │ USB CDC
  └─ Teensy 4.1 ─ C++/Teensyduino                      (to be written)
       ├─ CAN via TJA1051 ──► VESC ×2 (node IDs 1, 2)
       ├─ TCA9548A I²C mux ──► SHT45 ×2, BNO085, BMP390, ADXL375, BH1750, INA228 ×3
       ├─ winch kill ──► high-side P-FET, fail-safe OFF
       └─ UART ×2 + power ──► pod board (XIAO ESP32-S3, separate PCB)
```

Three isolated power domains: **drive** (12S LiPo, voltage sense only), **electronics**
(M18 → 5 V buck → Pi), **winch** (M18 → P-FET kill → ESC). Fusing is off-board.

---

## Two things that will bite you

**V2 values are not V3 values.** V3 disagrees with the old board on MCU, drive and sensors by
design. The V2 documents that used to sit alongside these — `pin_map.md`, `serial-protocol.md`,
`pcb_design_notes.md`, the firmware — describe a *different boat*. They are on `main` if you need
them, but copying a number out of them into V3 without re-deriving it is the specific mistake this
branch exists to avoid. `docs/v3/README.md` has the full contrast table.

**Read `V3_DESIGN_BRIEF.md` section 4 before laying out anything.** The first V3 attempt got a
routed board and then the review found the 20 A winch path running on a 2.5 mm track, thermal
relief throttling high-current pads, signals slotting the ground plane, and decoupling placed
6–20 mm from the pins it served. Those are all written down so they do not happen twice.

---

## Tooling

KiCad 10. `kicad-cli` and a `pcbnew`-capable Python both live in `C:\Program Files\KiCad\10.0\bin\`.

```bash
kicad-cli pcb drc --severity-all --format json -o drc.json Boat_PCB_V3.kicad_pcb
kicad-cli sch erc --severity-all Boat_PCB_V3.kicad_sch
```

Current board state: 107 DRC violations, 0 unconnected, 0 schematic-parity violations. Of the 29
`track_width` errors, roughly 21 are the winch width rule firing on Kelvin and divider taps that
are meant to be thin — see brief §4.
