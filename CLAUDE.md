# D.R.E.A.M.S V3

Autonomous survey catamaran, being rebuilt from scratch. **There is no application code yet.**
What exists is the V3 hardware design and the knowledge behind it. The software gets written here.

## What is here

| | |
|---|---|
| `Boat_PCB/Boat_PCB_V3/` | V3 carrier board: KiCad 10 schematic, layout, project-local library in `lib/` |
| `docs/v3/V3_DESIGN_BRIEF.md` | **Read first.** Locked hardware decisions, current budget, part choices, layout traps |
| `docs/v3/README.md` | Index of the other design docs, and the V2 ↔ V3 contrast table |

## The system, as the board wires it

```
Raspberry Pi 5 ─ navigation, mission logic, CV, cloud link      Python (not yet written)
  │ USB CDC
  └─ Teensy 4.1 ─ real-time I/O                                 C++/Teensyduino (not yet written)
       ├─ CAN via TJA1051 ──► VESC ×2, node IDs 1 and 2
       ├─ I²C via TCA9548A ─► SHT45 ×2, BNO085, BMP390, ADXL375, BH1750, INA228 ×2; GPS compass on ch 7
       ├─ UART ─────────────► GPS (M10-25Q) · pod tether (XIAO ESP32-S3, own board) · SBUS receiver
       ├─ PWM ──────────────► winch ESC, behind the P-FET kill
       ├─ STEP/DIR ─────────► A4988 radar-bar stepper
       └─ GPIO / ADC ───────► WS2812 status LED · hull leak L/R · pack voltage dividers
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
- **Pack dividers are 68k/10k at 1 %**, not V2's 56k/10k (brief §3).
- **SBUS is the manual override.** Its 5 V branch is fused loosely on purpose so it can't
  nuisance-trip.

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
kicad-cli sch erc --severity-all --format json -o erc.json Boat_PCB_V3.kicad_sch
kicad-cli pcb drc --severity-all --schematic-parity --format json -o drc.json Boat_PCB_V3.kicad_pcb
```

Baseline as of 2026-09-23. When a commit touches the board, put the change against these numbers
in the commit message.

- **DRC: 107 violations, 0 unconnected.**
  - 29 `track_width` errors. About 21 of them are the winch width rule firing on Kelvin and divider
    taps that are meant to be thin (brief §4).
  - 60 `silk_overlap` and 18 `silk_over_copper` warnings.
- **Schematic parity: 154.** None of the 108 footprints carry the `dreams_v3:` library prefix the
  schematic uses, and some Datasheet/Description fields aren't synced. Before you run *Update PCB
  from Schematic* to clear them, check whether it would replace footprints: that would reset any
  per-pad edits, such as solid zone connections on the power pads.
- **ERC: 70.**
  - 58 are unused pins with no no-connect flag: 30 on the Pi header, 24 on the Teensy, 4 on the buck
    and the BMP390.
  - The other 12 are power-pin typing on those symbols, plus three undriven inputs: Teensy PROGRAM
    and ON_OFF, and the buck's EN.

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
