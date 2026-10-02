# D.R.E.A.M.S V3

Autonomous survey catamaran, being rebuilt from scratch. **There is no application code yet.**
What exists is the V3 hardware design and the knowledge behind it. The software gets written here.

## What is here

| | |
|---|---|
| `Boat_PCB/Boat_PCB_V3/` | V3 carrier board: KiCad 10 schematic, layout, project-local library in `lib/` |
| `Boat_PCB/Pod_PCB_V3/` | V3 pod board, test phase: schematic and rev A layout. Uses the carrier's `lib/` |
| `docs/v3/V3_DESIGN_BRIEF.md` | **Read first.** Locked hardware decisions, current budget, part choices, layout traps |
| `docs/v3/README.md` | Index of the other design docs, and the V2 ↔ V3 contrast table |
| `docs/v3/session_journal.md` | What recent sessions did and left open. **Read at session start** (below) |

## Session journal: read at start, write at end

`docs/v3/session_journal.md` logs what each Claude Code session worked on, newest first, so a new
chat can pick up where the last one stopped. **Read it at the start of every session**, before
changing anything. **Add an entry at the top** when you finish a meaningful chunk of work, using the
template in the file. It holds the 5 newest entries; move older ones to
`docs/v3/session_journal_archive.md`. Locked decisions belong in the design brief, not the journal.

## The system, as the board wires it

```
Raspberry Pi 5 ─ navigation, mission logic, CV, cloud link      Python (not yet written)
  │ USB CDC
  └─ Teensy 4.1 ─ real-time I/O                                 C++/Teensyduino (not yet written)
       ├─ CAN via TJA1051 ──► VESC ×2, node IDs 1 and 2
       ├─ I²C via TCA9548A ─► SHT45 ×2, BNO085, BMP390, ADXL375, BH1750, INA228 ×2; GPS compass on ch 7
       ├─ UART ─────────────► GPS (M10-25Q) · SBUS receiver
       ├─ RS-485 (Serial8) ─► pod tether (XIAO ESP32-S3, own board), through U13
       ├─ PWM ──────────────► winch ESC, behind the P-FET kill
       ├─ STEP/DIR ─────────► A4988 radar-bar stepper
       └─ GPIO / ADC ───────► WS2812 status LED · hull leak L/R · 12S pack divider

Pod ─ XIAO ESP32-S3 on the winch tether, Boat_PCB/Pod_PCB_V3 (test phase, freshwater)
  ├─ RS-485 (UART0, D6/D7, DE on D3) ─► back up the tether to the Teensy
  ├─ I²C via ADS1115 (0x48) ─► pH · TDS (isolated) · dissolved O2 (fit later) · depth (pressure)
  ├─ ADC (D0) ───────────────► turbidity, relative only
  ├─ 1-Wire (D1) ────────────► DS18B20 water temperature
  └─ GPIO ───────────────────► leak probe (D2) · bottom contact (D8) · status LED (D9) · aux (D10)
```

These are still open. Ask the user before building on an assumption about any of them:

- **Teensy concurrency model:** a `millis()`-scheduled `loop()`, or TeensyThreads.
- **Pi ↔ Teensy protocol over USB CDC:** not defined yet.
- **Pod firmware:** the planning record assumed MicroPython on the ESP32-S3. Nothing has been
  written.

## Hardware facts the software has to respect

- **Never power the Pi from the carrier and from USB-C at the same time.** The Pololu buck isn't
  reverse-current tolerant, and the Pi's header 5 V pins become outputs when USB-C is attached. This
  is unsolved in hardware, so for now it's a build rule (brief §4).
- **The Pi header carries power only.** Pins 2 and 4 take +5 V from the carrier, and no GPIO is
  connected. Everything the Pi controls goes through the Teensy.
- **The winch kill is fail-safe OFF, and its net name reads backwards.** Driving `WINCH_KILL`
  **high** turns the winch *on*: a BSS138 pulls the high-side P-FET's gate down. Low, floating, or a
  Teensy held in reset all leave the winch off, because a 10k pulls the net to ground and another
  10k holds the P-FET gate at its source.
- **The carrier senses voltage only on the 12S drive rail:** one ADC divider, no shunt, no INA228.
  If you want drive current, get it from the VESCs over CAN.
- **Electronics and winch pack voltages come from the INA228s** (VBUS, on each shunt's load side):
  U10 at 0x41 and U11 at 0x44, both on mux channel 6. There are no ADC dividers on those packs any
  more. The 12S divider (220k/13k) reads on pin 17 (A3); pins 14 and 15 are free (brief §3).
- **SBUS is the manual override.** Its 5 V branch is fused loosely on purpose so it can't
  nuisance-trip.
- **The pod tether carries pack voltage, not 5 V.** J2 pin 2 is the electronics pack (15–21 V)
  through F1, and the pod regulates its own 5 V. A pod board built for 5 V in will be destroyed by it.
- **The pod link is half-duplex RS-485, not a UART.** Serial8 (TX8 pin 35, RX8 pin 34) runs through
  a THVD2410 (U13) onto J2 pins 3/4 (A/B). Call `Serial8.transmitterEnable(37)` so pin 37 drives the
  transceiver's DE and ~RE; left alone, a 10k holds it in receive. The carrier end is terminated
  (120 Ω), so the pod end needs its own transceiver and a 120 Ω terminator too.
- **The hull leak probes are excited, not biased.** Pins 40 and 41 (A16/A17) read the probes
  through 100k pull-ups that hang off pin 39 (`LEAK_EXC`). Drive pin 39 high only while sampling,
  then back low: a probe held at DC corrodes. A dry probe reads near 3.3 V; water pulls it toward
  ground.

## V2 is archived at `v2-final`

The V2 boat is frozen at the tag `v2-final`: RP2040 Picos on MicroPython, the Pi 5 stack (navigation,
stereo CV, a FastAPI command center), React dashboards, the cloud pipeline, the V2 board and about
forty docs. Nothing was deleted.

```bash
git show v2-final:pi5/navigation/navigator.py   # read one file
git checkout v2-final -- pi5/navigation/        # bring a directory back into the tree
git worktree add ../dreams-v2 v2-final          # full V2 checkout beside this one
```

**V2 values are not V3 values.** V3 differs from V2 on MCU, drive, sensors, dividers and pinout by
design. Porting a V2 *idea* is fine. Don't copy a V2 pin number, divider ratio, protocol field or
threshold into V3 without re-deriving it. That is the mistake to avoid.

## Tooling

**KiCad 10.0.5.** `kicad-cli.exe` and a `python.exe` that can `import pcbnew` are both in
`C:\Program Files\KiCad\10.0\bin\`. Use those to answer layout questions rather than reading the
s-expressions; the `.kicad_pcb` alone is 2.5 MB.

```bash
KC="/c/Program Files/KiCad/10.0/bin/kicad-cli.exe"   # not on PATH
"$KC" sch erc --severity-all --format json -o erc.json Boat_PCB/Boat_PCB_V3/Boat_PCB_V3.kicad_sch
"$KC" pcb drc --severity-all --schematic-parity --format json -o drc.json Boat_PCB/Boat_PCB_V3/Boat_PCB_V3.kicad_pcb
```

Carrier baseline as of 2026-09-28 (rev D, 130.6 × 101.5 mm). When a commit touches a board, put the
change against that board's numbers in the commit message.

- **DRC: 0 violations, 0 unconnected.** Rev C's one warning (A2's bottom-side outline on C28's GND
  pad) went away with the rev D placement.
- **Schematic parity: 0.** Every footprint carries its `dreams_v3:` library ID. *Update footprints
  from library* still resets per-pad edits, and 10 footprints have them. There are solid zone
  connections on the XT60s, Q1, C2, C26, R33, D4 and J12's GND pads 25 and 30, and leftover
  overrides on the U11 sense pins. Re-apply them after any footprint update.
- **ERC: 0.** Unused pins carry no-connect flags. The tied-pin and power-pin conflicts were fixed
  with pin types in the project library.

Pod baseline as of 2026-09-26 (rev A, 48 × 63 mm), same commands on
`Boat_PCB/Pod_PCB_V3/Pod_PCB_V3.*`: **DRC 0, 0 unconnected, parity 0, ERC 0.** One per-pad edit:
C3's GND pad connects solid to the pour, because the neighbouring traces starve its thermal spokes.
Re-apply it after a footprint update.

**Python:** ruff config lives in `pyproject.toml`.

## Raspberry Pi 5 notes (learned during V2 bring-up, still true of the platform)

- Don't `pip install ultralytics` on the Pi. It pulls in torch plus about 2.5 GB of CUDA wheels
  that are useless there. Run detection through `onnxruntime` with an exported `.onnx` model.
- `/tmp` is a 2 GB tmpfs, so big pip installs fail with `OSError 28` even when the disk is empty.
  Use `TMPDIR=~/piptmp pip install --no-cache-dir …`.
- A server bound to `0.0.0.0` is reached from a laptop at `http://<pi-ip>:<port>/` (get the IP with
  `hostname -I`), not at localhost.

## Conventions

Branching, commit style and pre-push checks are in [`CONTRIBUTING.md`](CONTRIBUTING.md).
