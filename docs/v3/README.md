# `docs/v3/` — V3 hardware planning. Fenced off from the bench on purpose.

Everything in this directory describes **Boat_PCB V3**, a board that **does not exist as hardware
yet**. It is a clean-sheet redesign, not a revision of the board under test.

**The boat on the bench is V2 / RP2040 Pico.** If you are debugging, flashing, measuring, or
spinning a motor, nothing in this directory applies to you — and none of it is on this branch.
The V2 authorities live on `main`:

| For | Read on `main` |
|---|---|
| As-built hardware facts, gotchas, power | `CLAUDE.md` (root) |
| Pin assignments (both Picos + Pi) | `docs/pin_map.md` |
| Pi ↔ Pico framing, commands, alerts | `docs/serial-protocol.md` |
| Battery thresholds | `firmware/boat-pico/sensors.py` |
| ESC config + the bi-directional gate | `docs/esc_setup.md` |
| What happened recently | `docs/session_journal.md` |

```bash
git show main:docs/pin_map.md          # read one
git checkout main -- docs/pin_map.md   # bring one back
```

## Why this needs a fence

V3 and V2 disagree on the things most likely to get someone hurt. These are **not** discrepancies to
reconcile — they are two different boards:

| | V2 — on the bench, live | V3 — planned, no hardware |
|---|---|---|
| Boat MCU | RP2040 Pico, MicroPython (`firmware/boat-pico/*.py`) | Teensy 4.1, C++/Teensyduino — full rewrite |
| Drive | **Direct servo PWM, GP19/GP20** — AM32 left, BLHeli-32 right, throttle held at zero by `escs.BIDIR_CONFIRMED` | VESCs as CAN nodes (IDs 1 and 2) via TJA1051, no MCP2515 |
| Pod MCU | RP2040 Pod Pico | Seeed XIAO ESP32-S3, from-scratch board |
| Pod tether | UART through slip ring | 2× UART + 2× power, schottky into the XIAO's 5V pin |
| Sensors | SHT41 ×2 (one dead), BNO085 with floating strap pins | SHT45 ×2, BNO085, BMP390, ADXL375, BH1750, 3× INA228, all behind a TCA9548A mux |

The trap: V3 assumes **VESC-over-CAN propulsion**, which the bench does not have and has never had on
this branch. A "fix" that moves bench throttle toward CAN, or that treats the V3 sensor set as
present, would break a working test bench and walk straight through the ESC safety gate that exists
because a mis-configured ESC already ran away once (see `docs/session_journal.md`, 2026-07-31).

Likewise, the bench BNO085's problem is **four floating strap pins on the module** — a wiring job. It
is not solved by anything in the V3 mux design.

## Files here

- **`V3_DESIGN_BRIEF.md` — start here.** Locked decisions, the current budget, part choices with
  their reasons, and the layout mistakes the first attempt made.
- `V3_PCB_SESSION_CONTEXT.md` — the decisions and the "why," plus what is still open (Teensy
  concurrency model, CAN splice point, GPS footprint, tether voltage).
- `DREAMS_V3_parts_footprints.md` — the BOM, with KiCad library availability and sourcing links.

Removed from the tree, still in git history: `v3_review_2026-08-05.md` (the 18-section log of
the first V3 attempt, distilled into the brief) and `kicad_library_status.md` (a 2026-08-04
survey of what ships with KiCad, now that the library is built and committed).

Both were written outside this repo and are stored **verbatim**, with only a scope banner prepended.
They refer to a `DREAMS_MASTER_CONTEXT.md`, which is this repo's **`docs/PROJECT_CONTEXT.md`**. Note
that `PROJECT_CONTEXT.md` is itself partly stale for the bench — it still describes VESC propulsion
and GPS on the Pico, both of which changed in late July 2026. `CLAUDE.md` is the more current V2
summary.

## Status of the V3 KiCad files

`Boat_PCB/Boat_PCB_V3/` is **tracked**: schematic, layout, project settings, the custom design
rules (`.kicad_dru`) and the project symbol/footprint libraries. KiCad backups (`*.bak`,
`*.prestack`), fabrication exports and DRC reports are gitignored — regenerate them from the
design files.

`Boat_PCB/Boat_PCB_V2.kicad_*` is still **not tracked**. Committing the V2 board remains a
separate decision.

## What adding these files changed

Nothing outside this directory except one scoping row in `CLAUDE.md`'s "Where truth lives" table. No
V2 doc, firmware module, or test was edited. CI (`.github/workflows/ci.yml`) builds and tests only
`pi5/`, `cloud/api/`, `dashboard/`, and `cloud/map-viewer/` — no job or test reads `docs/`, so these
files cannot affect the suite.
