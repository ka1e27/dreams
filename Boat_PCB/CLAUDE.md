# Boat_PCB: notes for KiCad sessions

The three V3 boards and the library they share. The repo-wide rules in the root `CLAUDE.md` (§4)
apply here too, and the firmware-facing pin maps are there (§5 carrier, §6 V3.1).

**Contents:** [Boards and baselines](#boards-and-baselines) · [Checks](#checks) ·
[Carrier](#carrier-rev-f) · [V3.1](#v31-starter-carrier-rev-a) · [Pod](#pod-rev-b) ·
[Shared library](#shared-library) · [Ordering boards](#ordering-boards)

## Boards and baselines

| Board | Folder | Rev | Baseline as of | Size | Footprints | ERC | DRC | Unconnected | Parity |
|---|---|---|---|---|---|---|---|---|---|
| Carrier | `Boat_PCB_V3/` | F, 10S power, narrowed | 2026-10-15 | 122.1 × 95.5 mm | 140; 8 on the underside: U15, D12, D13, D5, both Picos, SW1, SW2 | 0 | 0 | 0 | 0 |
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
- **One board-copy tweak:** A2's pin-name texts are left-justified 1.35 mm right of its pins with
  keep-upright off; at rot 0 on top the library's place puts them on the pads.
- **ERC 0:** unused pins carry no-connect flags. The tied-pin and power-pin conflicts were fixed with
  pin types in the project library.

### Placement (rev E: Teensy → two Picos)

- The power block, the left half and the top and bottom connector rows kept their rev D places and
  copper.
- Under the Pi, Pico A's socket rows sat at x 82.3 and 100.08, Pico B's at 104.0 and 121.78, pads
  from y 42.74 to 91.0 (8.5 mm further left since the board was narrowed, below).
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
- **U6 (the BMP390 breakout) came off** later the same day, with its tracks. Mux CH2 and Pico B
  GP6 are free; its area went to J1 and J4 when the board was condensed (next section).
- **J18** (4S backup, JST-VH) on the underside: its plug goes in from below. Nowhere on top near
  A2 clears A2's underside courtyard, and Q1's heatsink keep-out (x 48.1–63.7, y 10.9–27.6, on
  User.Comments) rules out the free top area by the winch. The condensing moved it, and the
  narrowing brought it to the top side at the left edge (next sections).

### Placement (rev F, condensed: 2026-10-15)

With U6 gone, the bottom edge came up 6 mm (101.5 → 95.5 mm, 6% less area). The width is set by
the Pi and the three XT60s, so it stays.

- **The bottom strip** (J5–J10, the names above them, R45–R48) moved up 6.0 mm (the resistors
  5.4 mm). J10 also moved 3.6 mm left, off Pico A's pad rows, and R53 moved with it.
- **A1** moved up 1.9 mm. Its top pin row (y 73.85) can't come closer to A2 underneath, which
  leaves 0.2 mm between A1's courtyard and the JST row. So "STEPPER" stands vertical between J5
  and J6, and J5's reference is on the back.
- **J1 (GPS) and J4 (SHT45 external) left the bottom-right corner.** The Pi's USB jacks hang
  over that corner, so nothing over 10 mm tall can go there. Both went to U6's old spot, turned
  90°: J1 at x 40.5–47.3 / y 51.3–69.8, J4 at x 47.8–54.6 / y 53.8–67.3. R49/R50 (the GPS series
  resistors) stayed between the Pico rows, so GPS_TX_EXT/RX_EXT run across. The narrowing moved
  both connectors again, to the right edge.
- **Around them:** F3 and C32 sit under A2's edge (F3's pads clear it by 1 mm) and U12 sits over A2
  (SMD only there). F2 sits right above the resistor row, R55 below J4, C16 beside U7, and
  R39/R57/R56 are stacked above R47.
- **J18** (underside) had its pins at (45.49, 75.25) and (49.45, 75.25), under the gap between J1
  and the resistor row, the only underside spot with no top through-hole leads inside its body.
- **MH3/MH4** are in the new bottom corners at y 91.8. SW2 moved above the right Pi standoff
  (y 56.2–65.8) and SW1 into SW2's old spot, which leaves room for MH3. The Picos' USB ends now
  sit at the bottom edge.
- **Copper:** everything that touched a moved part was re-routed. Freerouting did most of it; the
  maze router did CH4_SDA/SCL, IMU_BOOTN, +15V to A1, J18 to D13 and the two reset links.
  Tracks went 4105 → 4439 mm and vias 119 → 141.

### Placement (rev F, narrowed: 2026-10-15)

J1 and J4 sat mid-board while the strip right of Pico B held only the reset buttons, and J18 sat
underneath in the middle. Every cable connector is now on an edge, and the board is 8.5 mm narrower
(130.6 → 122.1 mm, 6.5% less area). Q1's heatsink keep-out (x 48.1–63.7) is what stops it there.

- **The Pi block moved 8.5 mm left** with its own copper: the Pi, J12, both Picos, everything under
  the Pi, the top-edge row above it (J3, F1, J2, MH2) and the right edge (SW1, SW2, MH3). J12's
  courtyard now starts at x 65.8 and the Pi's outline at 65.33. Pico A's socket rows are at x 73.8
  and 91.58, Pico B's at 95.5 and 113.28.
- **J1 (GPS) and J4 (SHT45 external)** went into the strip right of Pico B, turned 90°: J1 at
  x 115.0–121.8 / y 15.0–33.5, J4 at y 34.0–47.5. The strip is under the Pi but above its jack zone.
  Their names are printed between them and Pico B's pins, and their refs inside the bodies.
- **J18 (4S backup)** came to the top side at the left edge, x 0.3–9.9 / y 43.6–52.6, + on the upper
  pin. MH1 moved 0.3 mm down, to y 56.3, to clear it.
- **J11** (the 10S tap) slid 5.7 mm left along the top edge, next to J16, and JP1 (CAN TERM) sits
  between it and J3. The winch_sw pour gave up its corner under J11 (x 56.2–63.8, y < 10.5). J11's
  divider, R7 and R8, moved under the Pi beside C24 (x 84–94, y 12–33).
- **The old J1/J4 spot** holds the IMU and light-sensor pull-ups R43, R44, R39, R55 and R54 in one
  column (x 42.8–55.1, y 51.3–67.6). R56 took R55's old spot, and R47 and R57 stand beside R53 above
  J9.
- **The bottom row** closed up toward J10: J7 moved 1.5 mm left, J8 4.2 mm and J9 8.2 mm. Their refs
  went inside the bodies so the names still fit above them.
- **Elsewhere:** C31 sits beside C30 and R31 mid-board beside R36. D9 didn't move.
- **Copper:** the Pi block's own tracks moved with it. Everything that crossed into it, or touched a
  moved part, was re-routed: Freerouting did most of it, and the maze router did J18's 1 mm feed,
  the env-sensor and INA228 I²C pairs, LEAK_L and STEP_MS1. Tracks went 4439 → 4213 mm and vias
  141 → 134.
- **PACK_RAW's net class:** the HV_12S creepage class (0.6 mm) still matched the rev E name
  `/12S_RAW`, so the renamed tap net had fallen back to Default. The pattern is `/PACK_RAW` now.
- **A2 (the 5 V module) is on the top side now** (Kyle: close the empty patch over it). Face-down
  underneath, it left a 25 × 25 mm patch on top where nothing with leads could go. It keeps the same
  square (x 14.3–40.0 / y 46.5–72.2), unflipped, components up, pins on the left: VOUT at the top
  (y 53.0), then GND, VIN (y 60.6), VRP and EN/PG at the bottom (y 65.7), with the lone M2 hole at the
  EN/PG end as the library's top view has it. D13 (the backup diode) and D5 (the 5 V TVS) moved
  underneath it, U12 took F3's old spot, F3 (turned 90°) went into J18's old spot and D7 sits beside
  R58. The test points TP2, TP4 and TP3 (GND, 3V3, 5V) moved into the open column beside C26
  (x 43, y 28–36), so the left edge holds only J18. The In2 +5V tab under C32 now runs to x 52 for
  F3's +5V pad.
- **A2, A1 and U15 have 3D models now:** simple stand-ins in the shared library (its README), so
  renders show the modules instead of empty outlines.
- **Copper after A2 moved:** D12 to A2's VIN, D13 to VIN and J18 to D13 are maze runs at 1.0 mm;
  Freerouting did the rest. Tracks are now 4209 mm, with 142 vias.

### Copper you can't see from the top

- The pod fuse F1's feed is a 0.8 mm track on In2 along y 1.6 above the top-edge connectors. Since
  rev F it carries **+15V**, not the pack: U15's VOUT runs up the left edge on B.Cu (x 1.3) and
  along y 13.5 to a via at (19.9, 13.5) on that track. The old link from the +VELEC via at
  (15.0, 15.84) is gone.
- The +VELEC trunk (B.Cu) jogs from (16.16, 27.64) to D12's anode. D12's cathode (+VLOGIC) runs on
  B.Cu down to A2's VIN pins, 1.0 mm, re-done when A2 moved to the top.
- J18's +VBACKUP is a 1.0 mm track from J18 pin 2 at the left edge, under A2, to D13 underneath it
  (one via). D13's cathode sits right beside A2's VIN pins.
- The In2 +5V zone has a strip under both Picos' USB ends for D10/D11. Since the condensing, its
  notch over A1 ends at y 72 (A1 pin 2 is +3V3), and the old F3 block (x 34–56, y 76–86.5) is
  +3V3 again (R55), with a tab left for C32's +5V pad. Since the narrowing it also covers x 52–64,
  y 12–34.5, under Q1's heatsink area: its old neck to J12's 5V pins now runs under J12's pin
  field, so the Pi's 5 V comes in from the side as well.

### Locked copper: keep it if you re-route

- The rev D power block.
- That In2 track to F1.
- The D10/D11 +5V stubs.
- U2's A0/A1 GND via.
- The PICO_B_RUN lane past the right Pi standoff.
- Rev D's fan-outs at U4, U7, U8, U10, U11 and U13.
- The hand-routed (maze) runs of CH3_SDA/SCL, CH4_SDA/SCL, CH6_SDA/SCL, LEAK_L and STEP_MS1, re-done
  when the board was narrowed. IMU_INT, IMU_BOOTN, INA_ALERT and STEP_EN are router copper.
- The whole Pi link: PI_TX, PI_RX, PICO_A_TX, PICO_A_RX, PI_RST_A/B, Q3/Q4's GND vias and their
  drain runs to PICO_A_RUN and PICO_B_RUN.
- CAN_TX, re-routed round R66/R67.
- Rev F's hand-placed power runs: the +VELEC jog to D12 and the +VLOGIC return, C1 to U15's VIN,
  U15's +15V to C25 (B.Cu down x 9.4), C25 to A1's VMOT, up the left edge to the In2 via, and
  J18 to D13 (re-done from the left edge when the board was narrowed). They thread between
  through-hole pads with about 0.3 mm to spare, so a router won't find them again. The condensing
  re-routed the reset buttons' links (maze) too.

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
