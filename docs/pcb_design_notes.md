# PCB Design Notes

The repo contains one KiCad 10 project (schematic format version `20260306`, generator `eeschema`):

- `Boat_PCB/Boat_PCB.kicad_sch` — the main Boat Pico carrier/breakout board (source of truth).

All information below is extracted directly from that schematic file.

---

# Boat_PCB

Source of truth: `Boat_PCB/Boat_PCB.kicad_sch`.

## Board Overview

A carrier/breakout board hosting the Boat Pico (RP2040), with:
- Two battery inlets: BT1 (XT60, silkscreened "3s" — electronics) and BT4 (XT60, "4s" — VMOT)
- A Pololu 36 V→5 V step-down module (J1) generating the VSYS 5 V rail
- Voltage-divider circuits for ADC battery monitoring (three rails)
- An **MCP2515 + TJA1051 CAN interface** (U1/U2/Y1) for the VESC architecture
- A **Pololu A4988 stepper driver** (A2) for the radar-bar pan axis, driven from Pi GPIO
- A **full Raspberry Pi 5 40-pin header** (J3) plus two 1×20 breakout sockets (J14/J17)
- Peripheral connectors for the Boat Pico's sensors

> **⚠ Corrected 2026-07-28 against the `Boat_PCB V2` netlist.** This file previously described a
> pre-CAN board with BT2/BT3, fuses F1–F4, XT90 drive outputs J4/J5, a DHT11 and an IMU on J10 —
> **none of which exist on V2**. Tables below are now taken from the KiCad netlist (cross-checked
> with `kicad-cli sch export netlist`). Per-pin assignments live in `docs/pin_map.md`, which is
> authoritative; this file is the component/footprint breakdown.
>
> **The Pi 5 is on this board.** It mates to J3 and drives the A4988 over GPIO — a divergence from
> the "Pi 5 uses only USB — no GPIO" locked decision in `CLAUDE.md`.
>
> **Battery dividers are 56k/10k (×6.6) on all three rails as populated**, matching firmware. The
> *schematic* still carries pre-M18 values (drive 220k/13k, elec 100k/30k, winch 100k/18k), so a
> netlist export will disagree with the board — the board is right. See "Voltage-Divider
> Calculations" below and `docs/battery_architecture.md`.

---

## Component Reference List

### Microcontroller & modules
| Ref | Part | Footprint |
|-----|------|-----------|
| A1 | RaspberryPi_Pico | `Module:Raspberry pico no antenna` |
| A2 | Pololu_Breakout_A4988 | `Module:Pololu_Breakout-16_15.2x20.3mm` |

**Correction:** J3/J14/J17 are **not** Pico headers. The Pico solders directly to A1's own 40 pads.
J3 is the **Raspberry Pi 5** 40-pin header, and J14/J17 break the *Pi's* pins back out — not the
Pico's. No Pico pin reaches J14 or J17.

---

### CAN interface
| Ref | Part | Footprint | Wiring |
|-----|------|-----------|--------|
| U1 | MCP2515-I_P | `MCP2515-I_P:DIP254P762X432-18` | SCK=GP2, SI=GP3, SO=GP4, ~INT=GP6, ~RESET=GP7 (+R11), VDD=3V3 |
| U2 | TJA1051T-3 | `Package_SO:SOIC-8_3.9x4.9mm_P1.27mm` | TXD/RXD ↔ U1, VCC=VSYS 5 V, VIO=3V3, S=GND (normal mode), CANH/CANL → J2 |
| Y1 | Crystal | `Crystal:Crystal_HC49-4H_Vertical` | With C1/C2 load caps — ⚠ frequency unset |

U2's wiring is correct: the `-3` variant's VIO on 3V3 level-shifts to the Pico, VCC on 5 V, and STB
tied low for normal mode.

> ⚠ **U1 pin 16 (`~CS`) is tied to GND.** Chip select must return high to frame each SPI
> transaction; held low, the MCP2515 will not respond at all. This is a hard fault and it is
> inherited from V1. Route `~CS` to a free GPIO (GP11 is the only unrouted one) before expecting CAN
> to work.
>
> ⚠ **Pico GP5 is tied to GND** (A1 pad 7 on the GND net). ERC flags it as
> `pin_to_pin: Bidirectional / Power output`. GP5 is UART1 RX in firmware, so the GPS link cannot
> work as wired. GP4, the matching TX, is on U1's `SO` output — two drivers on one net.

---

### Batteries
| Ref | Value | Footprint | Feeds |
|-----|-------|-----------|-------|
| BT1 | 3s (electronics) | `AMASS_XT60-M_1x02_P7.20mm_Vertical` | J1 buck V<sub>IN</sub>, C5/C6, R5 divider → GP27 |
| BT4 | 4s (motor) | `AMASS_XT60-M_1x02_P7.20mm_Vertical` | A2 VMOT, C7/C8, J6, R8 divider → GP28 |

**BT2 and BT3 do not exist on V2** — the 2×6S-in-series 12S drive rail is gone. Drive motor power
is now entirely off-board; J4 is only a 2-pin voltage-sense tap. Both silkscreen values ("3s", "4s")
predate the M18 migration and are misleading — see the divider warning above.

---

### Fuses

**None on V2.** There are no fuse footprints in the netlist; F1–F4 from the previous revision are
gone. All overcurrent protection is off-board, with per-pack short/over-discharge handled by each
M18's REDLINK BMS. See `docs/battery_architecture.md` for the external fusing plan.

---

### Resistors (all THT)
**Footprint for all:** `Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal`
**Symbol:** `Device:R`

| Ref | Schematic value | Function | **Actually fitted** |
|-----|-------|----------|--------------|
| R2 | 220k | Drive divider R_top (from J4 tap) | **56K** ✅ |
| R4 | 13k | Drive divider R_bot → GP26 | **10K** ✅ |
| R5 | 100k | Electronics divider R_top (from BT1) | **56K** ✅ |
| R6 | 30k | Electronics divider R_bot → GP27 | **10K** ✅ |
| R8 | 100k | Winch divider R_top (from BT4/VMOT) | **56K** ✅ |
| R10 | 18k | Winch divider R_bot → GP28 | **10K** ✅ |
| R3 | 1k | GP26 ADC series resistor | 1K (keep) |
| R7 | 1k | GP27 ADC series resistor | 1K (keep) |
| R9 | 1k | GP28 ADC series resistor | 1K (keep) |
| R1 | 10k | Pull-up for J1's open-drain `PG` output → GP22 (top end sits on the A4988 VDD/MS1 net, i.e. Pi 3V3) | 10K (keep) |
| R11 | 10k | MCP2515 `~RESET` pull-up: GP7 → 3V3 | 10K (keep) |

> ⚠ **R9 is not a leak-sense pull-up** (this file previously said so). The hull-leak inputs have
> no external resistors at all — firmware uses the RP2040's internal pull-ups. R9 is the GP28 ADC
> series resistor, and R11 (absent from the old table) is the MCP2515 reset pull-up.
>
> ⚠ **Silkscreen swap.** The reference text for R9 and R11 is placed over the wrong footprint —
> each label sits nearer its neighbour's body than its own (6.32 mm offset vs. the 5.08 mm the other
> resistors use). When populating, fit **1 kΩ** at the pad printed *"R9→R11"* position — concretely:
> the 1 kΩ goes in the divider cluster with R5–R8/R10, and the 10 kΩ goes to the isolated footprint
> beside the MCP2515. R2's label has likewise drifted over J4. Reposition all three reference texts
> before the next fab run.
>
> **13k, 30k and 18k are not in the on-hand resistor kit** — corroborating that they were never
> fitted, and that the schematic values are the stale ones. Also add: **120 Ω** ×1 (CAN termination across J2 CANH/CANL, if
> this board is a bus end node), **1.5 kΩ** ×2 (GP8/GP9 I²C pull-ups at 400 kHz), **2.2 kΩ** ×2
> (GP14/GP15, three devices), **4.7 kΩ** ×2 (GP12/GP13), and **10 kΩ** ×1 (A4988 `~ENABLE` pull-up
> to the VDD/MS1 net, for a disabled-at-boot default).

### Voltage-Divider Calculations

**As populated — 56k/10k on all three rails** (confirmed by the builder, 2026-07-28), against an M18
pack (15 V empty / 18 V nom / 21 V max):

| Domain | R_top/R_bot | Ratio | 15 V (empty) | 18 V (nom) | 21 V (full) | Firmware |
|--------|-------------|-------|--------------|------------|-------------|----------|
| Drive → GP26 | R2/R4 (56k/10k) | 6.6 | 2.27 V | 2.73 V | 3.18 V | `INV_P_RATIO` = 6.6 ✓ |
| Electronics → GP27 | R5/R6 (56k/10k) | 6.6 | 2.27 V | 2.73 V | 3.18 V | `INV_E_RATIO` = 6.6 ✓ |
| Winch → GP28 | R8/R10 (56k/10k) | 6.6 | 2.27 V | 2.73 V | 3.18 V | `INV_W_RATIO` = 6.6 ✓ |

Every rail sits at 3.18 V full — 0.12 V under the 3.3 V ADC ceiling — and reconstructs at one shared
ratio. Divider drain is 318 µA per rail at 21 V; the 56k dissipates 5.7 mW, trivial for a 1/4 W part.
`INV_P_RATIO` was corrected **14.0 → 6.6** on 2026-07-28 (at ×14.0 a full 21 V drive pack reported
16.4 V, tripping `P_CRIT`/return-to-home on a full battery).

> ⚠ **What the schematic says instead.** `Boat_PCB.kicad_sch` still carries the pre-M18 values, so a
> netlist export computes ratios that match neither the board nor the firmware:
>
> | Rail | Schematic R_top/R_bot | Ratio | ADC at 18 V | ADC at 21 V | If it *were* fitted |
> |------|-------------|-------|-------------|-------------|--------|
> | Drive → GP26 | R2/R4 (220k/13k) | 17.92 | 1.00 V | 1.17 V | reads 37 % of true at ×6.6 |
> | Electronics → GP27 | R5/R6 (100k/30k) | 4.33 | **4.15 V** ⚠ | **4.85 V** ⚠ | **over-range** (3.3 V limit) |
> | Winch → GP28 | R8/R10 (100k/18k) | 6.56 | 2.74 V | 3.20 V | fine — 0.7 % off |
>
> R5/R6 were sized for a 3S LiPo (12.6 V → 2.91 V), which is what BT1's silkscreen still says — had
> they actually been fitted, GP27 would be over-range across the whole M18 range (R7's 1 kΩ would hold
> clamp current to ~1.2 mA, so the pin should survive, but the reading would clip). **Update these six
> values in KiCad** so the schematic, board and firmware finally agree.

> ⚠ **The ADC filters are incomplete.** R3/R7/R9 are 1 kΩ series resistors with **no capacitor to
> ground** — V2 dropped the old C3/C4 and never replaced them, so they filter nothing. Fit **100 nF
> from each of GP26/GP27/GP28 to GND** to form the RC (1.6 kHz corner) and to supply the RP2040
> sample-and-hold charge locally. Without them, expect jitter from the 5 V buck and the A4988 chopper
> coupling onto a high-impedance node, plus a systematic offset — and a real chance of tripping
> `P_CRIT` / `W_CRIT` on noise rather than on actual voltage.

All sense taps are ahead of the bulk caps. Divider grounds meet at a star point near Pico GND.

---

### Capacitors (all THT)

**Polarized electrolytics (bulk):**
| Ref | Footprint | Rail |
|-----|-----------|------|
| C5 | `CP_Radial_D10.0mm_P5.00mm` | BT1 electronics rail bulk |
| C7 | `CP_Radial_D10.0mm_P5.00mm` | VMOT bulk — this is the electrolytic Pololu asks you to add across the A4988's motor supply |

**Ceramic disc:**
| Ref | Footprint | Net | Purpose |
|-----|-----------|-----|---------|
| C1 | `C_Disc_D3.0mm_W1.6mm_P2.50mm` | `U1-OSC1` | **Y1 crystal load cap** — ⚠ value unset |
| C2 | `C_Disc_D3.0mm_W1.6mm_P2.50mm` | `U1-OSC2` | **Y1 crystal load cap** — ⚠ value unset |
| C6 | `C_Disc_D5.0mm_W2.5mm_P5.00mm` | BT1 rail | HF decoupling |
| C8 | `C_Disc_D5.0mm_W2.5mm_P5.00mm` | VMOT | HF decoupling |
| C9 | `C_Disc_D5.0mm_W2.5mm_P5.00mm` | 3V3 | Rail decoupling |
| C10 | `C_Disc_D5.0mm_W2.5mm_P5.00mm` | 3V3 | Rail decoupling |
| C11 | `C_Disc_D5.0mm_W2.5mm_P5.00mm` | VSYS | Rail decoupling |

**C3 and C4 do not exist on V2.** They were the ADC filter caps; C1/C2 were repurposed as crystal
load caps for the MCP2515. That leaves **no capacitor on any ADC node** — see the divider warning
above. Three 100 nF need adding at GP26/GP27/GP28.

> ⚠ **C1/C2 and Y1 are a BOM blocker.** The crystal's frequency is unset (value is literally
> `"Crystal"`) and C1/C2 are `"C"`. The MCP2515 needs a specified f<sub>OSC</sub> (8, 16 or 20 MHz)
> with matched load caps (typically 22–27 pF), and the CAN bit-timing registers in firmware must be
> computed for whichever you pick. Get this wrong and the oscillator either won't start or runs
> off-frequency — no CAN communication at all.
>
> Note the plug-in-transient role belongs to **C5 and C7** (the bulk electrolytics), not to any
> 100 nF ceramic. A 100 nF at 3.3 V stores ~0.5 µJ and cannot buffer a hot-plug event.

---

### Power Connectors
| Ref | Value | Footprint | Function |
|-----|-------|-----------|----------|
| J6 | 4s output | `AMASS_XT60-M_1x02_P7.20mm_Vertical` | VMOT pass-through (GND / VMOT) |
| J1 | *(Pololu 36V→5V module)* | `Module:Pololu 36v5vstepdown` | 7,8 = V<sub>IN</sub> · 1,2 = 5 V out (VSYS) · 3–6 = GND · 12 = `PG` → GP22 |

**No XT90 drive outputs on V2.** J4/J5 as XT90 VESC feeds are gone. J4 is now a 2-pin JST-XH
labelled "12s Tap" carrying only a voltage sense line into R2. Motor power is distributed off-board.

### Signal Connectors
| Ref | Value | Footprint | Pico / Pi pins |
|-----|-------|-----------|----------------|
| J2 | *(CAN out)* | `JST_XH_B3B-XH-A_1x03_P2.50mm_Vertical` | GND / CANH / CANL — via U2, **not** direct to the Pico |
| J7 | GPS + Compass | `JST_XH_B6B-XH-A_1x06_P2.50mm_Vertical` | GP14/15 I²C-B, GP9/GP8 I²C0, VSYS **5 V**, GND |
| J5 | IMU (14,15 I²C · 17,18 RST/INT) | `JST_XH_B10B-XH-A_1x10_P2.50mm_Vertical` | 3V3, GND, GP15, GP14, GP17, GP18 (4 pins n/c) |
| J8 | Winch ESC | `JST_XH_B2B-XH-A_1x02_P2.50mm_Vertical` | GP21 / GND — **signal only**, not power |
| J9 | Winch ESC RC | `PinSocket_1x02_P2.54mm_Vertical` | GP21 / GND — parallel with J8 |
| J11 | Temp + Humidity, External | `JST_XH_B4B-XH-A_1x04_P2.50mm_Vertical` | GP12/GP13 I²C-A, GND, VSYS **5 V** — **SHT41**, not DHT11 |
| J12 | led | `JST_XH_B3B-XH-A_1x03_P2.50mm_Vertical` | GND, **GP10**, VSYS — value says "GPIO 12" but it's wired to GP10 |
| J13 | Temp + Humidity, Internal | `PinHeader_1x04_P2.54mm_Vertical` | GP14/GP15 I²C-B, GND, VSYS **5 V** — **SHT41** |
| J15 | Hull Leak Right | `JST_XH_B2B-XH-A_1x02_P2.50mm_Vertical` | GND / **GP20** |
| J16 | Hull Leak Left | `JST_XH_B2B-XH-A_1x02_P2.50mm_Vertical` | GND / **GP19** |
| J18 | Stepper Motor | `JST_XH_B4B-XH-A_1x04_P2.50mm_Vertical` | 1B / 1A / 2A / 2B from A2 |
| J4 | 12s Tap | `JST_XH_B2B-XH-A_1x02_P2.50mm_Vertical` | R2 → GP26 divider / GND |
| J3 | Raspberry Pi 5 connector | `Module:Raspberry Pi  Mounting` (2×20, 2.54 mm) | Full Pi 40-pin header — see the row-transposition note below |
| J14 / J17 | Conn_01x20_Socket | `PinSocket_1x20_P2.54mm_Vertical` | Pi header breakouts: J14 = even pins reversed, J17 = odd pins in order |

**J10 does not exist on V2.** The IMU is on **J5** (10-pin), which additionally brings out the
BNO085's RST and INT on GP17/GP18. J16's Value field is no longer blank — it reads "Hull Leak Left".

> ⚠ **J3's pad numbering is transposed.** The footprint puts odd pads on one row and even on the
> other, but shifted one position relative to the `Conn_02x20_Odd_Even` symbol — so schematic pad *N*
> lands on Pi header pin *N∓1*. All six power/ground pins align only under the swap (0 conflicts vs.
> 6 without it), and the four A4988 signals then match `pi5/cv/stepper.py`'s BCM numbers exactly.
> **Never read Pi pin assignments off the schematic pad numbers** — use the table in
> `docs/pin_map.md`.
>
> ⚠ **J7/J11/J13 hand out 5 V** (VSYS) while J5 hands out 3V3, and J5/J7/J13 share one I²C bus.
> SHT41 silicon is 3.6 V absolute max. **J5 pin 1 is the only 3V3 connector pin on the whole board.**
>
> ⚠ **J2 has no 120 Ω termination** and no ESD protection, despite leaving the board.

---

## What Is NOT on Boat_PCB


- No HC-12 radio module or connector (HC-12 is only an optional Pi 5 USB dongle)
- No CSI camera connectors
- No GPS module directly (GPS is external, on J7, to the u-blox M10Q)
- No fuses (all off-board on V2)
- No XT90 drive outputs, and no 12S rail — motor power is distributed off-board
- No DHT11 (replaced by two SHT41 on J11/J13), and no J10
- No 120 Ω CAN termination, no ADC filter caps, no I²C pull-ups

> **The Pi 5 *is* on this board.** The previous version of this list said "No Raspberry Pi 5
> (connects via USB cable only)." That is wrong for V2: J3 mates the Pi's full 40-pin header, the Pi
> drives the A4988 over GPIO23/24/25/8, and the Pi's 3V3 (header pin 1) is the *only* supply for the
> A4988's VDD. The board and the Pi are electrically coupled in both directions — J3 pads 1 and 3 are
> the Pi's 5 V pins wired to VSYS, so populating J1 **and** connecting USB-C parallels two 5 V
> supplies. See `docs/pin_map.md`.

### Mounting holes

Four `MountingHole_3.2mm_M3_DIN965_Pad`, all still annotated `REF**`. This is what produces the
seven footprint warnings in DRC (three `duplicate_footprints` + four `extra_footprint`). Annotate
them MH1–MH4 to clear it.

### DRC / ERC status (2026-07-28, KiCad 10.0.5)

- **DRC: clean electrically** — 0 unconnected pads, 0 clearance or track-width violations. Rules are
  0.25 mm clearance / 0.2 mm min track / 0.5 mm via, comfortably inside JLCPCB standard. No severities
  were downgraded. Routing is generous: 0.75 mm signal, 1.25–4.0 mm power, filled GND pour on B.Cu.
- **DRC warnings:** 4 library-link (custom footprints not in the library config) + the 7 mounting-hole
  issues above.
- **ERC: 14 errors, 9 warnings.** Most are artifacts of using passive connector symbols for power
  sources (`power_pin_not_driven` on VSYS, VMOT, and A2's VDD — all genuinely fed, respectively by J1,
  BT4, and the Pi through J3). The two that are **real** are GP5-to-GND and the missing `~CS` route.
  `A1` pins 33 (AGND) and 35 (ADC_VREF) reporting unconnected is benign — both are internally tied on
  the Pico module.
- Custom libraries (`Module`, `MCP2515-I_P`) are not in the library config, so footprints can't be
  re-linked from a fresh checkout. The `.kicad_pcb` has them embedded, so the board is still
  fabricable.

---

## JLCPCB Notes

- 2-layer FR4, 1.62 mm; F.Cu = signal, B.Cu = `PWR+GND` with a filled GND pour
- **Mostly** THT — but **U2 (TJA1051T-3) is SOIC-8 SMD**, so the "no SMD" note no longer holds.
  U1 is DIP-18, everything else is through-hole.
- High-current paths are the XT60 pads (BT1, BT4, J6) and the VSYS rail. Existing copper: 1.25 mm
  narrowest on VSYS (~2.6 A at 10 °C rise), up to 4.0 mm on VMOT. Widen VSYS if you intend to power
  a Pi 5 through the header.
- Order 5–10 boards minimum for a price break
- Turnaround: 5–7 days standard

> ⚠ **The gerbers in `Boat_PCB V2/` are stale** — exported 2026-07-20, while `Boat_PCB.kicad_pcb` was
> modified 2026-07-23. Re-export before ordering. Note also that the gerber folder and all eight
> `Boat_PCB V*.zip` archives are **untracked in git**, so fabrication outputs aren't version
> controlled.
