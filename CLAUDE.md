# D.R.E.A.M.S V3

Autonomous survey catamaran, being rebuilt from scratch. **There is no application code yet.**
What exists is the V3 hardware design and the knowledge behind it. The software gets written here.

## What is here

| | |
|---|---|
| `Boat_PCB/Boat_PCB_V3/` | V3 carrier board: KiCad 10 schematic, layout, project-local library in `lib/` |
| `Boat_PCB/Pod_PCB_V3/` | V3 pod board, test phase: schematic and rev B layout. Uses the carrier's `lib/` |
| `Boat_PCB/Boat_PCB_V3_1/` | V3.1 starter carrier (interim): Pi 5 + one Pico 2, 10S pack, CAN, RC, GPS, Qwiic, pod tether. Uses the carrier's `lib/`; notes in `docs/v3/V3_1_STARTER_CARRIER.md` |
| `docs/v3/V3_DESIGN_BRIEF.md` | **Read first.** Locked hardware decisions, current budget, part choices, layout traps |
| `docs/v3/README.md` | Index of the other design docs, and the V2 ↔ V3 contrast table |

## The system, as the board wires it

```
Raspberry Pi 5 ─ navigation, mission logic, CV, cloud link      Python (not yet written)
  │ UART0 on the GPIO header to Pico A · GPIO23/GPIO24 reset Pico A / Pico B · USB cables optional
  ├─ Pico A (U1, Pico 2) ─ control                              C++ (not yet written)
  │    ├─ CAN on the PIO (can2040) via TJA1051T/3 ─► VESC ×2, node IDs 1 and 2
  │    ├─ GP1 ──────────────► SBUS receiver (UART0 RX or a PIO UART, see below)
  │    ├─ PWM ──────────────► winch ESC, behind the P-FET kill
  │    ├─ STEP/DIR ─────────► A4988 radar-bar stepper
  │    └─ GPIO / ADC ───────► WS2812 status LED · hull leak L/R · 12S pack divider
  ├─ Pico B (U14, Pico 2) ─ sensors                             C++ (not yet written)
  │    ├─ I²C0 via TCA9548A ─► SHT45 ×2, BNO085, BMP390, ADXL375, BH1750, INA228 ×2; GPS compass on ch 7
  │    ├─ UART1 ────────────► GPS (M10-25Q)
  │    └─ RS-485 (UART0) ───► pod tether (XIAO ESP32-S3, own board), through U13
  └─ Pico A ↔ Pico B: a UART link (A's UART1, B's PIO UART); Pico B reaches the Pi through it

Pod ─ XIAO ESP32-S3 on the winch tether, Boat_PCB/Pod_PCB_V3 (test phase, freshwater)
  ├─ RS-485 (UART0, D6/D7, DE on D3) ─► back up the tether to Pico B
  ├─ I²C via ADS1115 (0x48) ─► pH · TDS (isolated) · dissolved O2 (fit later) · depth (pressure)
  ├─ ADC (D0) ───────────────► turbidity, relative only
  ├─ 1-Wire (D1) ────────────► DS18B20 water temperature
  └─ GPIO ───────────────────► leak probe (D2) · bottom contact (D8) · status LED (D9) · aux (D10)
```

These are still open. Ask the user before building on an assumption about any of them:

- **Pico firmware structure:** how each Pico splits its work between its two cores and the PIO. The board
  fixes which Pico does what; nothing else is decided.
- **Pi ↔ Pico A protocol over the header UART, and the Pico A ↔ Pico B link** (which also carries
  Pico B's traffic to and from the Pi): not defined yet. Nor is which of SBUS and the Pi link gets
  Pico A's hardware UART0 (the other runs on a PIO UART).
- **Pod firmware:** the planning record assumed MicroPython on the ESP32-S3. Nothing has been
  written.

## Hardware facts the software has to respect

- **Never power the Pi from the carrier and from USB-C at the same time.** The Pololu buck isn't
  reverse-current tolerant, and the Pi's header 5 V pins become outputs when USB-C is attached. This
  is unsolved in hardware, so for now it's a build rule (brief §4).
- **The Pi talks to the Picos over its header, not USB.** Pins 2 and 4 take +5 V from the carrier.
  The Pi's UART0 (GPIO14 TX, GPIO15 RX; header pins 8 and 10, `/dev/ttyAMA0` with `dtparam=uart0=on`)
  runs to Pico A's UART0 (GP17 RX, GP16 TX), 3.3 V at both ends, through a 1k in each line (R66,
  R67). Those keep either end from back-powering the other through its pins, e.g. a Pico running on
  a laptop's USB while the Pi is off. Pico B reaches the Pi through Pico A over their link. GPIO23
  and GPIO24 (pins 16 and 18) high reset Pico A and Pico B: each turns on a BSS138 (Q3, Q4) across
  that Pico's reset button. R64 and R65 (100k) hold the gates low while the Pi is off, booting or
  unplugged, so the Picos never wait on the Pi. No other GPIO is connected.
- **The Picos' USB cables are optional.** Running without them leaves the Pi's USB ports for cameras
  and the modem, but either Pico can still be plugged into the Pi, to flash it or to run its link
  over USB CDC instead of (or as well as) the header. That's safe with the board powered: VBUS isn't
  connected on the carrier, so the cable's 5 V reaches VSYS only through the Pico's own diode, and
  the carrier's +5V comes in through D10/D11. Which link the firmware uses is its choice.
- **Two Pico 2s, one job each.** Pico A (U1, next to the Pi header) is the control MCU, Pico B (U14)
  the sensor MCU. Both are socketed under the carrier, USB ends toward the Pi's USB ports, and get
  VSYS from +5V through a B5819W (D10, D11). SW1 and SW2 (underside, right edge) reset A and B: hold
  that Pico's BOOTSEL and tap its reset for the UF2 bootloader (the Pi can pulse the resets too, see
  above). Pin maps:
  - **Pico A:** GP0 winch ESC PWM · GP1 SBUS · GP2–GP8 A4988 DIR, STEP, SLEEP, MS3, MS2, MS1, EN ·
    GP9 winch kill · GP10 WS2812 data (PIO, through U12) · GP11 5 V power-good · GP14/GP15 CAN RX/TX
    (can2040) · GP16/GP17 Pi link TX/RX (UART0) · GP20/GP21 Pico B link TX/RX (UART1) · GP22 leak
    excite · ADC0 12S pack · ADC1/ADC2 leak L/R. GP12, GP13, GP18 and GP19 are free.
  - **Pico B:** GP4/GP5 GPS (UART1 TX/RX) · GP6 BMP390 INT · GP7 INA228 ALERT · GP8/GP9 BNO085
    INT/RST · GP10/GP11 link TX/RX (PIO UART) · GP12/GP13 I²C0 SDA/SCL to the TCA9548A · GP14 mux
    reset · GP16/GP17 pod RS-485 (UART0) · GP18 RS-485 DE · GP19/GP20 ADXL375 INT1/INT2. Its ADC pins
    and GP0–GP3, GP15, GP21, GP22 are free.
- **The +3V3 rail is Pico A's 3V3 pin** (keep the load under 300 mA), as it was the Teensy's. Pico B's
  3V3 pin is left open, so two regulator outputs are never tied. So fit Pico A whenever Pico B runs:
  the sensors, pull-ups and RS-485 transceiver Pico B talks to are powered from Pico A.
- **Mounting.** Each Pico hangs about 15 mm under the carrier on its sockets, more with a USB plug
  in, so mount the carrier at least 20 mm off its base. The Picos' USB ends face the board's bottom
  edge, under the Pi's USB ports: plug in a short right-angle micro-USB cable when you need one.
- **The RP2350's input leakage (erratum E9) is why two pull-downs are 4.7k.** A pull-down above
  8.2k can't hold a pin low against it, so R36 (`WINCH_KILL`) and R62 (`TETHER_DE`) are 4.7k, not
  10k. Keep any new pull-down at 8.2k or less.
- **The winch kill is fail-safe OFF, and its net name reads backwards.** Driving `WINCH_KILL`
  (Pico A GP9) **high** turns the winch *on*: a BSS138 pulls the high-side P-FET's gate down. Low,
  floating, or Pico A held in reset all leave the winch off, because a 4.7k pulls the net to ground
  and a 10k holds the P-FET gate at its source.
- **The carrier senses voltage only on the 12S drive rail:** one ADC divider, no shunt, no INA228.
  If you want drive current, get it from the VESCs over CAN.
- **Electronics and winch pack voltages come from the INA228s** (VBUS, on each shunt's load side):
  U10 at 0x41 and U11 at 0x44, both on mux channel 6. There are no ADC dividers on those packs any
  more. The 12S divider (220k/13k) reads on Pico A's ADC0 (GP26), with C4 at the pin (brief §3).
- **SBUS is the manual override.** Its 5 V branch is fused loosely on purpose so it can't
  nuisance-trip. It goes to Pico A's GP1, which is a UART0 RX pin, but UART0 also carries the Pi link
  on GP16/GP17 and can't take both: run SBUS or the Pi link on a PIO UART. Either way, invert SBUS
  in the GPIO block (`gpio_set_inover`).
- **CAN runs on the PIO with can2040** (Pico A GP14 RX, GP15 TX, through the TJA1051T/3). There is
  no MCP2515 on purpose (re-confirmed 2026-10-13). On the RP2350 can2040 needs Pico SDK 2.0 or later.
  It is GPLv3, so Pico A's firmware is GPL once it links it. J3 is 1 CANH, 2 CANL, 3 GND, like V3.1's
  J3/J4. V2's CAN plug was 1 GND, 2 CANH, 3 CANL, so re-pin a V2 cable before plugging it in.
- **The pod tether carries pack voltage, not 5 V.** J2 pin 2 is the electronics pack (15–21 V)
  through F1, and the pod regulates its own 5 V. A pod board built for 5 V in will be destroyed by it.
- **The pod link is half-duplex RS-485, not a UART.** Pico B's UART0 (GP16 TX, GP17 RX) runs through
  a THVD2410 (U13) onto J2 pins 3/4 (A/B). GP18 drives the transceiver's DE and ~RE (high =
  transmit); left alone, a 4.7k holds it in receive. The carrier end is terminated (120 Ω), so the
  pod end needs its own transceiver and a 120 Ω terminator too.
- **The hull leak probes are excited, not biased.** Pico A's ADC1 and ADC2 (GP27, GP28) read the
  probes through 100k pull-ups that hang off GP22 (`LEAK_EXC`). Drive GP22 high only while
  sampling, then back low: a probe held at DC corrodes. A dry probe reads near 3.3 V; water pulls it
  toward ground.

## V3.1 starter carrier (interim board)

`Boat_PCB/Boat_PCB_V3_1/` gets the boat moving before the full V3 carrier: the Pi 5 and the
D36V50F5 stay, and one Raspberry Pi Pico 2 replaces the Teensy. The full V3 carrier moved to two
Picos as well (rev E, 2026-10-13); its pin maps are above, and the two boards' maps differ. Pin map,
connectors and bring-up checks are in `docs/v3/V3_1_STARTER_CARRIER.md`. What the firmware has to
respect:

- **One 10S Li-ion pack (30–42 V) powers everything** through J1. The pack voltage reads on ADC0
  (GP26) through 100k/7.5k: V_pack = V_adc × 14.33.
- **The pod gets 15 V from J5, never the pack.** GP19 high switches it off; low (the default) is on.
- **Pico firmware is C++** (Arduino-Pico or the Pico SDK). CAN runs on the PIO with can2040: RX GP10,
  TX GP11, through a TJA1051T/3.
- **RS-485 to the pod:** UART0 (GP0 TX, GP1 RX), DE and ~RE on GP2. Drive GP2 high to transmit.
- **RC on UART1** (GP8 TX, GP9 RX). For SBUS, invert RX on GP9 in the GPIO block.
- **GPS on a PIO UART** (GP6 TX, GP7 RX). Its compass shares I²C0 (GP4/GP5) with the SHT41 module on
  the underside (0x44, 3.3 V only: it has no regulator) and the Qwiic TMP119 (0x48).
- **Leak probes are excited from GP18**, as on V3: drive it high only while sampling ADC1 (GP27) and
  ADC2 (GP28).
- **ESC PWM:** winch on GP16, drive L/R on GP14/GP15. The headers' middle pin is open, so an ESC's
  BEC can't back-feed the 5 V rail.
- **The Pi header carries power only**, and the Pi reaches the Pico over USB. Never power the Pi from
  the board and from its USB-C at the same time.

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

Carrier baseline as of 2026-10-13 (rev E with the Pi link, 130.6 × 101.5 mm, 137 footprints, 5 on the
underside: A2, both Picos, SW1, SW2). When a commit touches a board, put the change against that board's numbers in
the commit message.

- **DRC: 0 violations, 0 unconnected.**
- **Schematic parity: 0.** Every footprint carries its `dreams_v3:` library ID. *Update footprints
  from library* still resets per-pad edits, and 10 footprints have them. There are solid zone
  connections on the XT60s, Q1, C2, C26, R33, D4 and J12's GND pads 25 and 30, and leftover
  overrides on the U11 sense pins. Re-apply them after any footprint update.
- **ERC: 0.** Unused pins carry no-connect flags. The tied-pin and power-pin conflicts were fixed
  with pin types in the project library.
- **Rev E layout (Teensy → two Picos).** The power block, the left half and the top and bottom
  connector rows kept their rev D places and copper. Under the Pi, Pico A's socket rows sit at x 82.3
  and 100.08, Pico B's at 104.0 and 121.78, pads from y 42.74 to 91.0. Each Pico footprint keeps the
  Pico W antenna keep-out between its rows at y 40.9–49.9: no copper on any layer there. Between Pico A's
  rows on top sit U2, its decap, C4 (at ADC0) and 8 pull-ups. Between Pico B's rows sit 10 pull-ups.
  R53 stands upright above J10.
- **Copper you can't see from the top.** The +VELEC feed to the pod fuse F1 is a 0.8 mm track on In2,
  from the power block's via at (15.0, 15.84) along y 1.6 above the top-edge connectors. The In2
  +5V zone has a strip under both Picos' USB ends for D10/D11. Locked copper: the rev D power block,
  that In2 track, the D10/D11 +5V stubs, U2's A0/A1 GND via, the PICO_B_RUN lane past the right Pi
  standoff, rev D's fan-outs at U4, U7, U8, U10, U11 and U13, and the hand-routed (maze) runs of
  IMU_INT, CH4_SDA/SCL, CH6_SDA, INA_ALERT, STEP_EN and the whole Pi link (PI_TX, PI_RX, PICO_A_TX,
  PICO_A_RX, PI_RST_A/B, Q3/Q4's GND vias and their drain runs to PICO_A_RUN and PICO_B_RUN), plus
  CAN_TX, re-routed round R66/R67. Keep them if you re-route. Q3, Q4, R64 and R65 sit above Pico B,
  on the R62/R38 column. R66 and R67 stand upright between J12 and C15, the only room on the UART's
  path. Pico A's GP12/GP13 pins are walled in by the J12-to-Pico tracks, which is why the Pi link
  uses GP16/GP17.

Pod baseline as of 2026-09-29 (rev B, 48 × 63 mm), same commands on
`Boat_PCB/Pod_PCB_V3/Pod_PCB_V3.*`: **DRC 0, 0 unconnected, parity 0, ERC 0.** One per-pad edit:
U5's GND pad 3 connects solid to the pour, because the neighbouring traces starve its thermal
spokes. Re-apply it after a footprint update.

V3.1 baseline as of 2026-10-12 (rev A, 98 × 67 mm, 2 layers, 75 footprints, 21 on the underside), same commands on
`Boat_PCB/Boat_PCB_V3_1/Boat_PCB_V3_1.*`: **DRC 0, 0 unconnected, parity 0, ERC 0.** No per-pad
edits. One board-copy tweak: U1 sits underneath, which leaves its pin-name texts upside down, so they're
turned to 0° with left/right justification swapped and keep-upright off (keep-upright moves them onto
the pads). Re-apply it after a footprint update. Three runs of copper are hand-routed
and locked: the +5V feed round the socket's left end (1.3 mm, both layers), the pack input
(XT60 → F1 → Q1), and a 0.35 mm GND link from Pico pin 23 round the antenna keep-out to pin 18
(signals otherwise wall pin 23 in). Keep them if you re-route.

**Ordering boards.** PCBWay makes them. Each of the three boards carries PCBWay's order-number marker,
the text "WayWayWay" on the back silkscreen: pick "Specify a location" for the product number at
checkout and PCBWay prints it there. Upload a zip of the gerber and drill export (each board's
`gerbers/` folder is git-ignored, so regenerate it from the board before an order).

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

## Weekly updates: document your work

The team posts weekly updates on the website: https://ka1e27.github.io/dreams/updates.html. They live in `website/UPDATES.md` in this repo, and the page reads that file live.

After meaningful work here (PCBs, firmware, CAD, tests, the site), add to it before finishing:

1. Under the current week's `## Week of <Mon> <day>, <year>` heading in `website/UPDATES.md` (the Monday; add it at the top if missing), add one short bullet per change: `- **Name:** what was built, tested, decided or broken.`
2. Write for the public: true and specific. Follow "Keep damaging information out of the repo" below. Don't say who wrote the code or mention AI tools.
3. Only add, never rewrite teammates' bullets. Commit it with your other changes; pushing `main` publishes it.

For the full story with photos, add `website/updates/<YYYY-MM-DD>.md` too; the week then gets its own page. `website/CLAUDE.md` has the full format and the site's own notes.

## Keep damaging information out of the repo

This repo is public, and git keeps everything: a file deleted later is still in the history and in old pull requests. Treat every commit as public. Before committing, read the diff and keep all of the following out of code, docs, journals, commit messages and PR text:

- **Secrets:** API keys, tokens, passwords, private or SSH keys, Wi-Fi credentials, Tailscale keys, hostnames or IPs, and real server URLs with credentials. Use placeholders in committed config, and put real values in `.env` (git-ignored) or on the device.
- **Personal info:** phone numbers, home or shipping addresses, personal emails, student IDs. The public addresses are the project's Gmail (DREAMSboatproject@gmail.com, official since 2026-10-14) and the team's Northeastern ones.
- **Partners and sponsors:** never write the name of anyone we talked to (at CRWA, the Port of Oakland, sponsors): say "our CRWA contact". Naming the organization is fine, as a contact or partner, and so is a general point it made. Their documents, decks and meeting notes stay out of the repo; `docs/presentations/` is git-ignored for that reason. No sponsor discounts, quotes or deal terms.
- **Money:** no budgets, spending or what anything cost us. Public catalog prices for parts are fine.
- **Photos:** strip location (EXIF/GPS) data before committing a phone photo.
- **Third-party files:** only add datasheets, vendor CAD models or libraries if their license allows sharing.

If something on this list turns up in a change, or seems to be needed, stop and ask Kyle before committing.
