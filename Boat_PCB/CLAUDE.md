# Boat_PCB: notes for KiCad sessions

The three V3 boards and the library they share. The repo-wide rules in the root `CLAUDE.md` (§4)
apply here too, and the firmware-facing pin maps are there (§5 carrier, §6 V3.1).

**Contents:** [Boards and baselines](#boards-and-baselines) · [Checks](#checks) ·
[Carrier](#carrier-rev-f) · [V3.1](#v31-starter-carrier-rev-a) · [Pod](#pod-rev-b) ·
[Shared library](#shared-library) · [Ordering boards](#ordering-boards)

## Boards and baselines

| Board | Folder | Rev | Baseline as of | Size | Footprints | ERC | DRC | Unconnected | Parity |
|---|---|---|---|---|---|---|---|---|---|
| Carrier | `Boat_PCB_V3/` | F, 10S power | 2026-10-14 | 130.6 × 101.5 mm | 141; 8 on the underside: A2, U15, D12, J18, both Picos, SW1, SW2 | 0 | 0 | 0 | 0 |
| V3.1 starter carrier | `Boat_PCB_V3_1/` | A | 2026-10-12 | 98 × 67 mm, 2 layers | 75; 21 on the underside | 0 | 0 | 0 | 0 |
| Pod | `Pod_PCB_V3/` | B | 2026-09-29 | 48 × 63 mm | | 0 | 0 | 0 | 0 |

## Checks

`kicad-cli.exe` is in `C:\Program Files\KiCad\10.0\bin\` (KiCad 10.0.5), with a `python.exe` that
can `import pcbnew`. Run from the repo root; the same commands work on
`Boat_PCB/Pod_PCB_V3/Pod_PCB_V3.*` and `Boat_PCB/Boat_PCB_V3_1/Boat_PCB_V3_1.*`:

```bash
KC="/c/Program Files/KiCad/10.0/bin/kicad-cli.exe"   # not on PATH
"$KC" sch erc --severity-all --format json -o erc.json Boat_PCB/Boat_PCB_V3/Boat_PCB_V3.kicad_sch
"$KC" pcb drc --severity-all --schematic-parity --format json -o drc.json Boat_PCB/Boat_PCB_V3/Boat_PCB_V3.kicad_pcb
```

When a commit touches a board, put the change against that board's numbers in the commit message.

**Per-pad edits and board-copy tweaks:** *Update footprints from library* resets them. Each board's
section below lists its own; re-apply them after any footprint update.

## Carrier (rev F)

### Library and ERC

- **Schematic parity 0:** every footprint carries its `dreams_v3:` library ID.
- **Per-pad edits (10 footprints):** solid zone connections on the XT60s, Q1, C2, C26, R33, D4 and
  J12's GND pads 25 and 30, and leftover overrides on the U11 sense pins.
- **ERC 0:** unused pins carry no-connect flags. The tied-pin and power-pin conflicts were fixed with
  pin types in the project library.

### Placement (rev E: Teensy → two Picos)

- The power block, the left half and the top and bottom connector rows kept their rev D places and
  copper.
- Under the Pi, Pico A's socket rows sit at x 82.3 and 100.08, Pico B's at 104.0 and 121.78, pads
  from y 42.74 to 91.0.
- Each Pico footprint keeps the Pico W antenna keep-out between its rows at y 40.9–49.9: no copper
  on any layer there.
- Between Pico A's rows on top sit U2, its decap, C4 (at ADC0) and 8 pull-ups. Between Pico B's rows
  sit 10 pull-ups.
- R53 stands upright above J10.
- Q3, Q4, R64 and R65 sit above Pico B, on the R62/R38 column.
- R66 and R67 stand upright between J12 and C15, the only room on the UART's path.
- Pico A's GP12/GP13 pins are walled in by the J12-to-Pico tracks, which is why the Pi link uses
  GP16/GP17.

### Placement (rev F: 10S power)

Nothing moved; four parts were added. Each sits in the only spot that clears every courtyard and
through-hole pad (a placement search, `fpsearch.py` in the rev F pipeline, checked the whole board):

- **U15** (Pololu D36V6F15, +15V) on the underside at the left edge: pins down x 3.5 from y 35.0
  (SHDN, VIN, GND, VOUT), body to the east over C1's leads.
- **D12** (B360B) on the underside at (19.5, 31.75), beside the old trunk, anode north.
- **D13** (B360B) on top at (24.6, 58.05), right of A2's pin labels, cathode north.
- **J18** (4S backup, JST-VH) on the underside at (33.5, 81.0): its plug goes in from below. Nowhere
  on top near A2 clears A2's underside courtyard, and Q1's heatsink keep-out (x 48.1–63.7,
  y 10.9–27.6, on User.Comments) rules out the free top area by the winch.

### Copper you can't see from the top

- The pod fuse F1's feed is a 0.8 mm track on In2 along y 1.6 above the top-edge connectors. Since
  rev F it carries **+15V**, not the pack: U15's VOUT runs up the left edge on B.Cu (x 1.3) and
  along y 13.5 to a via at (19.9, 13.5) on that track. The old link from the +VELEC via at
  (15.0, 15.84) is gone.
- The +VELEC trunk (B.Cu) now jogs from (16.16, 27.64) to D12's anode, and D12's cathode returns to
  (18.68, 39.51) under the GND via at (17.5, 33.7) and round D8. From there down to A2's VIN pins it
  is +VLOGIC.
- J18's +VBACKUP runs on B.Cu up to two vias at (26.0, 62.6) and (26.0, 63.9), then on top to D13.
- The In2 +5V zone has a strip under both Picos' USB ends for D10/D11.

### Locked copper: keep it if you re-route

- The rev D power block.
- That In2 track to F1.
- The D10/D11 +5V stubs.
- U2's A0/A1 GND via.
- The PICO_B_RUN lane past the right Pi standoff.
- Rev D's fan-outs at U4, U7, U8, U10, U11 and U13.
- The hand-routed (maze) runs of IMU_INT, CH4_SDA/SCL, CH6_SDA, INA_ALERT and STEP_EN.
- The whole Pi link: PI_TX, PI_RX, PICO_A_TX, PICO_A_RX, PI_RST_A/B, Q3/Q4's GND vias and their
  drain runs to PICO_A_RUN and PICO_B_RUN.
- CAN_TX, re-routed round R66/R67.
- Rev F's hand-placed power runs: the +VELEC jog to D12 and the +VLOGIC return, C1 to U15's VIN,
  U15's +15V to C25 (B.Cu down x 9.4) and up the left edge to the In2 via, and J18 to D13. They thread
  between through-hole pads with about 0.3 mm to spare, so a router won't find them again.

## V3.1 starter carrier (rev A)

- **No per-pad edits.**
- **One board-copy tweak:** U1 sits underneath, which leaves its pin-name texts upside down, so
  they're turned to 0° with left/right justification swapped and keep-upright off (keep-upright moves
  them onto the pads). Re-apply it after a footprint update.
- **Locked copper (three hand-routed runs): keep them if you re-route.**
  - The +5V feed round the socket's left end (1.3 mm, both layers).
  - The pack input (XT60 → F1 → Q1).
  - A 0.35 mm GND link from Pico pin 23 round the antenna keep-out to pin 18 (signals otherwise wall
    pin 23 in).

## Pod (rev B)

- **One per-pad edit:** U5's GND pad 3 connects solid to the pour, because the neighbouring traces
  starve its thermal spokes. Re-apply it after a footprint update.

## Shared library

All three boards use the `dreams_v3` library in `lib/` (symbols, footprints, 3D models) through
`${KIPRJMOD}/../lib`. Per-part warnings are in [`lib/README.md`](lib/README.md).

## Ordering boards

PCBWay makes them. Each of the three boards carries PCBWay's order-number marker, the text
"WayWayWay" on the back silkscreen: pick "Specify a location" for the product number at checkout and
PCBWay prints it there. Upload a zip of the gerber and drill export (each board's `gerbers/` folder is
git-ignored, so regenerate it from the board before an order).
