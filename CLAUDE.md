# D.R.E.A.M.S V3

Autonomous survey catamaran, being rebuilt from scratch. **There is no application code yet.**
What exists is the V3 hardware design and the knowledge behind it. The software gets written here.

**Contents:** [1 Repo map](#1-repo-map) · [2 System overview](#2-system-overview) ·
[3 Open decisions](#3-open-decisions-ask-first) · [4 Rules for every change](#4-rules-for-every-change) ·
[5 Carrier firmware reference](#5-carrier-rev-e-firmware-reference) ·
[6 V3.1 firmware reference](#6-v31-starter-carrier-firmware-reference) · [7 Tooling](#7-tooling) ·
[8 Raspberry Pi 5 notes](#8-raspberry-pi-5-notes) · [9 V2 archive](#9-v2-archive-v2-final)

## 1. Repo map

| Path | What it is |
|---|---|
| `Boat_PCB/Boat_PCB_V3/` | The carrier (V3, rev E): KiCad 10 schematic and layout |
| `Boat_PCB/Boat_PCB_V3_1/` | V3.1 starter carrier (interim): Pi 5 + one Pico 2, 10S pack, CAN, RC, GPS, Qwiic, pod tether. Notes in `docs/v3/V3_1_STARTER_CARRIER.md` |
| `Boat_PCB/Pod_PCB_V3/` | The pod board, test phase: schematic and rev B layout |
| `Boat_PCB/lib/` | The `dreams_v3` KiCad library (symbols, footprints, 3D models) all three boards share; per-part notes in its README |
| `Boat_PCB/CLAUDE.md` | Board baselines, layout constraints, locked copper, ordering. **Read it before changing a board** |
| `docs/v3/V3_DESIGN_BRIEF.md` | **Read first.** Locked hardware decisions, current budget, part choices, layout traps |
| `docs/v3/README.md` | Index of the other design docs, and the V2 ↔ V3 contrast table |
| `docs/v3/V3_MECHANICAL.md` | Hull, bridge, outdrive and water-sampling design (Matthew's rev D proposal). The design tools are on the `feature/mechanical-rev-d` branch, not `main` |
| `website/` | The public site, https://ka1e27.github.io/dreams/. Its own notes are in `website/CLAUDE.md` |
| `CONTRIBUTING.md` | Branches, commit style, pre-push checks |

## 2. System overview

**Terms used in this file:**

| Term | Means |
|---|---|
| **Carrier** | The V3 carrier board, rev E (`Boat_PCB_V3`): Pi 5, Pico A and Pico B |
| **V3.1** | The interim starter carrier (`Boat_PCB_V3_1`): Pi 5 and one Pico 2. Its pin map differs from the carrier's |
| **Pod** | The pod board (`Pod_PCB_V3`): a XIAO ESP32-S3 on the winch tether |
| **Pico A, Pico B** | The carrier's control MCU (U1) and sensor MCU (U14), both Raspberry Pi Pico 2 (RP2350) |
| **12S pack** | The drive pack. The carrier only senses its voltage |
| **Electronics pack** | 15–21 V. The pod tether carries it |
| **Winch pack** | Powers the winch ESC through the P-FET kill |

The system, as the carrier wires it:

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

## 3. Open decisions: ask first

These are not decided. Ask the user before building on an assumption about any of them:

- **Pico firmware structure:** how each Pico splits its work between its two cores and the PIO. The
  board fixes which Pico does what; nothing else is decided.
- **Pi ↔ Pico A protocol over the header UART, and the Pico A ↔ Pico B link** (which also carries
  Pico B's traffic to and from the Pi): not defined yet. Nor is which of SBUS and the Pi link gets
  Pico A's hardware UART0 (the other runs on a PIO UART).
- **Pod firmware:** the planning record assumed MicroPython on the ESP32-S3. Nothing has been
  written.

## 4. Rules for every change

### 4.1 This repo is public: keep damaging information out

Git keeps everything: a file deleted later is still in the history and in old pull requests. Treat
every commit as public. Before committing, read the diff and keep all of the following out of code,
docs, journals, commit messages and PR text:

- **Secrets:** API keys, tokens, passwords, private or SSH keys, Wi-Fi credentials, Tailscale keys,
  hostnames or IPs, and real server URLs with credentials. Use placeholders in committed config, and
  put real values in `.env` (git-ignored) or on the device.
- **Personal info:** phone numbers, home or shipping addresses, personal emails, student IDs. The
  public addresses are the project's Gmail (DREAMSboatproject@gmail.com, official since 2026-10-14)
  and the team's Northeastern ones; only those appear on the site.
- **Partners and sponsors:** never write the name of anyone we talked to (at CRWA, the Port of
  Oakland, sponsors): say "our CRWA contact". Naming the organization is fine, as a contact or
  partner, and so is a general point it made: "the Port of Oakland and CRWA both told us they still
  send divers down for sediment samples" is OK. Their documents, decks and meeting notes stay out of
  the repo; `docs/presentations/` is git-ignored for that reason. No sponsor discounts, quotes or deal
  terms until Kyle announces them.
- **Money:** no budgets, spending or what anything cost us. Public catalog prices for parts are fine.
- **Photos:** strip location (EXIF/GPS) data before committing a phone photo.
  `website/tools/build_images.py` re-encodes images, which drops it. Don't commit original phone
  photos.
- **Third-party files:** only add datasheets, vendor CAD models or libraries if their license allows
  sharing.

If something on this list turns up in a change, or seems to be needed, stop and ask Kyle before
committing.

### 4.2 Weekly updates: document your work

The team posts weekly updates on https://ka1e27.github.io/dreams/updates.html. The page reads
`website/UPDATES.md` live. After meaningful work anywhere in this repo (boat hardware, PCBs,
firmware, CAD, testing, sponsors, the site), add to it before finishing:

1. **Pull first** (`git pull`). Matthew and the others edit this file too.
2. **Find the week:** `## Week of <Mon> <day>, <year>`, using the Monday. If it's missing, add it at
   the top, just under the instructions comment. Newest week first.
3. **One short bullet per project:** `- **Name:** what was built, tested, decided or broken.` Use the
   name of the person you're working with (Kyle unless told otherwise). Kyle wants these very short,
   so fold later work on the same project into its bullet instead of adding more.
4. **Write for the public:** true and specific, no hype. Follow §4.1. Don't say who wrote the code
   or mention AI tools.
5. **Only add.** Never rewrite other people's bullets.
6. **Commit it with your other changes.** Pushing `main` publishes it.

For the full story with photos, add `website/updates/<YYYY-MM-DD>.md` (the week's Monday); the week
then gets its own page. The format and the photo pipeline are in `website/CLAUDE.md`.

### 4.3 Don't port V2 values

V3 differs from V2 on MCU, drive, sensors, dividers and pinout by design. Porting a V2 *idea* is
fine. Don't copy a V2 pin number, divider ratio, protocol field or threshold into V3 without
re-deriving it. That is the mistake to avoid. Reading V2: §9.

### 4.4 Branches, commits and board changes

- Branching, commit style and pre-push checks are in [`CONTRIBUTING.md`](CONTRIBUTING.md).
- When a commit touches a board, put the change against that board's numbers in the commit message.
  The baselines are in `Boat_PCB/CLAUDE.md`.

## 5. Carrier (rev E): firmware reference

### 5.1 Safety and power rules

- **Never power the Pi from the carrier and from USB-C at the same time.** The Pololu buck isn't
  reverse-current tolerant, and the Pi's header 5 V pins become outputs when USB-C is attached. This
  is unsolved in hardware, so for now it's a build rule (brief §4).
- **The +3V3 rail is Pico A's 3V3 pin** (keep the load under 300 mA), as it was the Teensy's. Pico B's
  3V3 pin is left open, so two regulator outputs are never tied. So fit Pico A whenever Pico B runs:
  the sensors, pull-ups and RS-485 transceiver Pico B talks to are powered from Pico A.
- **The winch kill is fail-safe OFF, and its net name reads backwards.** Driving `WINCH_KILL`
  (Pico A GP9) **high** turns the winch *on*: a BSS138 pulls the high-side P-FET's gate down. Low,
  floating, or Pico A held in reset all leave the winch off, because a 4.7k pulls the net to ground
  and a 10k holds the P-FET gate at its source.
- **The pod tether carries pack voltage, not 5 V.** J2 pin 2 is the electronics pack (15–21 V)
  through F1, and the pod regulates its own 5 V. A pod board built for 5 V in will be destroyed by it.
- **The hull leak probes are excited, not biased.** Pico A's ADC1 and ADC2 (GP27, GP28) read the
  probes through 100k pull-ups that hang off GP22 (`LEAK_EXC`). Drive GP22 high only while
  sampling, then back low: a probe held at DC corrodes. A dry probe reads near 3.3 V; water pulls it
  toward ground.
- **Keep any new pull-down at 8.2k or less.** The RP2350's input leakage (erratum E9) means a
  pull-down above 8.2k can't hold a pin low against it. That is why R36 (`WINCH_KILL`) and R62
  (`TETHER_DE`) are 4.7k, not 10k.

### 5.2 Pi ↔ Pico links

- **The Pi talks to the Picos over its header, not USB.**
  - Pins 2 and 4 take +5 V from the carrier.
  - The Pi's UART0 (GPIO14 TX, GPIO15 RX; header pins 8 and 10, `/dev/ttyAMA0` with
    `dtparam=uart0=on`) runs to Pico A's UART0 (GP17 RX, GP16 TX), 3.3 V at both ends, through a 1k
    in each line (R66, R67). Those keep either end from back-powering the other through its pins,
    e.g. a Pico running on a laptop's USB while the Pi is off.
  - Pico B reaches the Pi through Pico A over their link.
  - GPIO23 and GPIO24 (pins 16 and 18) high reset Pico A and Pico B: each turns on a BSS138 (Q3, Q4)
    across that Pico's reset button. R64 and R65 (100k) hold the gates low while the Pi is off,
    booting or unplugged, so the Picos never wait on the Pi.
  - No other GPIO is connected.
- **The Picos' USB cables are optional.** Running without them leaves the Pi's USB ports for cameras
  and the modem, but either Pico can still be plugged into the Pi, to flash it or to run its link
  over USB CDC instead of (or as well as) the header. That's safe with the board powered: VBUS isn't
  connected on the carrier, so the cable's 5 V reaches VSYS only through the Pico's own diode, and
  the carrier's +5V comes in through D10/D11. Which link the firmware uses is its choice.
- **Pico A ↔ Pico B link:** Pico A's UART1 (GP20/GP21) to Pico B's PIO UART (GP10/GP11). It also
  carries Pico B's traffic to and from the Pi.

### 5.3 The two Picos

Two Pico 2s, one job each. Pico A (U1, next to the Pi header) is the control MCU, Pico B (U14) the
sensor MCU. Both are socketed under the carrier, USB ends toward the Pi's USB ports, and get VSYS
from +5V through a B5819W (D10, D11). SW1 and SW2 (underside, right edge) reset A and B: hold that
Pico's BOOTSEL and tap its reset for the UF2 bootloader (the Pi can pulse the resets too, §5.2).

**Pico A (U1): control**

| Pin | Use |
|---|---|
| GP0 | Winch ESC PWM |
| GP1 | SBUS (a UART0 RX pin, see §5.4) |
| GP2–GP8 | A4988 DIR, STEP, SLEEP, MS3, MS2, MS1, EN |
| GP9 | Winch kill (`WINCH_KILL`, high = winch on) |
| GP10 | WS2812 data (PIO, through U12) |
| GP11 | 5 V power-good |
| GP14 / GP15 | CAN RX / TX (can2040) |
| GP16 / GP17 | Pi link TX / RX (UART0) |
| GP20 / GP21 | Pico B link TX / RX (UART1) |
| GP22 | Leak excite (`LEAK_EXC`) |
| ADC0 (GP26) | 12S pack divider |
| ADC1 / ADC2 (GP27 / GP28) | Leak L / R |
| Free | GP12, GP13, GP18, GP19 |

**Pico B (U14): sensors**

| Pin | Use |
|---|---|
| GP4 / GP5 | GPS (UART1 TX / RX) |
| GP6 | BMP390 INT |
| GP7 | INA228 ALERT |
| GP8 / GP9 | BNO085 INT / RST |
| GP10 / GP11 | Pico A link TX / RX (PIO UART) |
| GP12 / GP13 | I²C0 SDA / SCL to the TCA9548A |
| GP14 | Mux reset |
| GP16 / GP17 | Pod RS-485 (UART0) |
| GP18 | RS-485 DE |
| GP19 / GP20 | ADXL375 INT1 / INT2 |
| Free | Its ADC pins, and GP0–GP3, GP15, GP21, GP22 |

### 5.4 Buses and sensing

- **CAN runs on the PIO with can2040** (Pico A GP14 RX, GP15 TX, through the TJA1051T/3).
  - There is no MCP2515 on purpose (re-confirmed 2026-10-13).
  - On the RP2350, can2040 needs Pico SDK 2.0 or later. It is GPLv3, so Pico A's firmware is GPL
    once it links it.
  - J3 is 1 CANH, 2 CANL, 3 GND, like V3.1's J3/J4. V2's CAN plug was 1 GND, 2 CANH, 3 CANL, so
    re-pin a V2 cable before plugging it in.
- **SBUS is the manual override.** Its 5 V branch is fused loosely on purpose so it can't
  nuisance-trip. It goes to Pico A's GP1, which is a UART0 RX pin, but UART0 also carries the Pi link
  on GP16/GP17 and can't take both: run SBUS or the Pi link on a PIO UART. Either way, invert SBUS
  in the GPIO block (`gpio_set_inover`).
- **The pod link is half-duplex RS-485, not a UART.** Pico B's UART0 (GP16 TX, GP17 RX) runs through
  a THVD2410 (U13) onto J2 pins 3/4 (A/B). GP18 drives the transceiver's DE and ~RE (high =
  transmit); left alone, a 4.7k holds it in receive. The carrier end is terminated (120 Ω), so the
  pod end needs its own transceiver and a 120 Ω terminator too.
- **Pack voltages:**
  - **12S pack:** the carrier senses voltage only on the 12S drive rail: one ADC divider, no shunt,
    no INA228. The divider (220k/13k) reads on Pico A's ADC0 (GP26), with C4 at the pin (brief §3).
    If you want drive current, get it from the VESCs over CAN.
  - **Electronics and winch packs:** their voltages come from the INA228s (VBUS, on each shunt's
    load side): U10 at 0x41 and U11 at 0x44, both on mux channel 6. There are no ADC dividers on
    those packs any more.

### 5.5 Mounting

Each Pico hangs about 15 mm under the carrier on its sockets, more with a USB plug in, so mount the
carrier at least 20 mm off its base. The Picos' USB ends face the board's bottom edge, under the Pi's
USB ports: plug in a short right-angle micro-USB cable when you need one.

## 6. V3.1 starter carrier: firmware reference

`Boat_PCB/Boat_PCB_V3_1/` gets the boat moving before the carrier: the Pi 5 and the D36V50F5 stay,
and one Raspberry Pi Pico 2 replaces the Teensy. The carrier moved to two Picos as well (rev E,
2026-10-13), and **the two boards' pin maps differ**. The full pin map, connectors and bring-up
checks are in `docs/v3/V3_1_STARTER_CARRIER.md`. What the firmware has to respect:

| Function | Pins | Rule |
|---|---|---|
| Firmware | | C++ (Arduino-Pico or the Pico SDK) |
| Power | J1, ADC0 (GP26) | One 10S Li-ion pack (30–42 V) powers everything through J1. Pack voltage through 100k/7.5k: V_pack = V_adc × 14.33 |
| Pod power | J5, GP19 | The pod gets 15 V from J5, never the pack. GP19 high switches it off; low (the default) is on |
| CAN | GP10 RX, GP11 TX | On the PIO with can2040, through a TJA1051T/3 |
| RS-485 to the pod | GP0 TX, GP1 RX (UART0), GP2 DE + ~RE | Drive GP2 high to transmit |
| RC | GP8 TX, GP9 RX (UART1) | For SBUS, invert RX on GP9 in the GPIO block |
| GPS | GP6 TX, GP7 RX (PIO UART) | Its compass is on I²C0 |
| I²C0 | GP4 / GP5 | The GPS compass, the SHT41 module on the underside (0x44, 3.3 V only: it has no regulator) and the Qwiic TMP119 (0x48) |
| Leak probes | GP18 excite, ADC1 (GP27), ADC2 (GP28) | Excited, as on the carrier: drive GP18 high only while sampling |
| ESC PWM | Winch GP16, drive L/R GP14/GP15 | The headers' middle pin is open, so an ESC's BEC can't back-feed the 5 V rail |
| Pi | | The Pi header carries power only, and the Pi reaches the Pico over USB. Never power the Pi from the board and from its USB-C at the same time |

## 7. Tooling

- **KiCad 10.0.5.** `kicad-cli.exe` and a `python.exe` that can `import pcbnew` are both in
  `C:\Program Files\KiCad\10.0\bin\`. Use those to answer layout questions rather than reading the
  s-expressions; the `.kicad_pcb` alone is 2.5 MB. The check commands, the per-board baselines
  (every board is at ERC 0, DRC 0, 0 unconnected, parity 0) and the layout rules are in
  `Boat_PCB/CLAUDE.md`.
- **Python:** ruff config lives in `pyproject.toml`.

## 8. Raspberry Pi 5 notes

Learned during V2 bring-up, still true of the platform:

- Don't `pip install ultralytics` on the Pi. It pulls in torch plus about 2.5 GB of CUDA wheels
  that are useless there. Run detection through `onnxruntime` with an exported `.onnx` model.
- `/tmp` is a 2 GB tmpfs, so big pip installs fail with `OSError 28` even when the disk is empty.
  Use `TMPDIR=~/piptmp pip install --no-cache-dir …`.
- A server bound to `0.0.0.0` is reached from a laptop at `http://<pi-ip>:<port>/` (get the IP with
  `hostname -I`), not at localhost.

## 9. V2 archive (`v2-final`)

The V2 boat is frozen at the tag `v2-final`: RP2040 Picos on MicroPython, the Pi 5 stack (navigation,
stereo CV, a FastAPI command center), React dashboards, the cloud pipeline, the V2 board and about
forty docs. Nothing was deleted. The rule for using it is §4.3; the V2 ↔ V3 contrast table is in
`docs/v3/README.md`.

```bash
git show v2-final:pi5/navigation/navigator.py   # read one file
git checkout v2-final -- pi5/navigation/        # bring a directory back into the tree
git worktree add ../dreams-v2 v2-final          # full V2 checkout beside this one
```
