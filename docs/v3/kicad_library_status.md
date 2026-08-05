# V3 KiCad library status — verified against the local install

> Checked against **KiCad 10.0.5** as installed on this machine
> (`C:\Program Files\KiCad\10.0\share\kicad\`), on 2026-08-04. This **supersedes the "KiCad?" column
> in `DREAMS_V3_parts_footprints.md`**, which was written off-machine and is wrong in four rows — it
> tells you to download symbols that already ship with KiCad.
>
> Scope: V3 only. See [`README.md`](README.md) — none of this applies to the V2 bench.

Your global `sym-lib-table` / `fp-lib-table` contain **no custom entries** (stock template only), and
the V2 schematic was built almost entirely from stock libs (`power`, `Device`, `Connector`,
`Connector_Generic`, `Interface_CAN_LIN`, `MCU_Module`, `Driver_Motor`). V3 can stay on that footing
for most of the BOM.

## Fully covered by stock KiCad — nothing to download

| Part | Symbol | Footprint |
|---|---|---|
| TJA1051T | `Interface_CAN_LIN:TJA1051T` | `Package_SO:SOIC-8_3.9x4.9mm_P1.27mm` |
| TCA9548A (TSSOP-24) | `Interface_Expansion:TCA9548APWR` | `Package_SO:TSSOP-24_4.4x7.8mm_P0.65mm` |
| INA228 ×3 | `Sensor_Energy:INA228` | `Package_SO:HVSSOP-10-1EP_3x3mm_P0.5mm_EP1.83x1.89mm` ⚠ |
| SHT45 ×2 | `Sensor_Humidity:SHT4x` | `Sensor_Humidity:Sensirion_DFN-4_1.5x1.5mm_P0.8mm_SHT4x_NoCentralPad` |
| Schottky (SOD-123) | `Device:D_Schottky` | `Diode_SMD:D_SOD-123` |
| Pod tether / CAN stub | `Connector:Conn_01x04_*` | `Connector_JST:JST_XH_B4B-XH-A_1x04_P2.50mm_Vertical` |
| Dividers, filters, LEDs, thermistor, switches, headers | `Device:*`, `Connector*` | `Resistor_*`, `Capacitor_*`, `LED_*` |

⚠ **INA228 footprint needs one check.** TI's DGS (VSSOP-10) package — confirm whether your ordered
part has the exposed thermal pad that this `-1EP` footprint provides. If not, use a bare VSSOP-10.

The four rows the parts doc gets wrong are TJA1051T, TCA9548A, INA228 and SHT45 — all four listed as
"symbol needs download", all four stock. There is even a footprint named for the SHT4x specifically.

## Vendored into the project library

Rather than referencing stock libs, the parts above were **copied into
`Boat_PCB_V3/lib/`** so a fresh clone resolves everything with no per-machine setup. See
[`lib/README.md`](../../Boat_PCB/Boat_PCB_V3/lib/README.md) for per-file provenance and licensing.

`dreams_v3.kicad_sym` — 7 symbols: `ADXL375`, `TJA1051T`, `TCA9548APWR`, `INA228`, `INA226` (parent
only — see below), `SHT4x`, `Teensy4.1`.
`dreams_v3.pretty/` — 10 footprints. Every symbol's Footprint property was retargeted to
`dreams_v3:` and all 7 references verified to resolve to a file on disk.

Validated with `kicad-cli sym export svg` (all 7 parse and render) and `kicad-cli fp upgrade` (all
footprints in current KiCad 10 format — the Teensy one arrived in legacy KiCad-5 `(module …)` form).

⚠ **`INA226` is in the library and must not be placed.** `INA228` inherits from it via `extends`, so
it cannot be removed. The INA226 is 36 V common-mode max — out of spec for the 63 V drive domain,
which is exactly why V3 moved to the INA228. Its Description field carries a DO-NOT-PLACE warning.

## Supply rails, M18 XT60 inputs and divider wiring (2026-08-05)

45 components; 13 named nets, verified out of the exported netlist. **Zero unnamed nets gained a
second node**, so nothing is joined by accident.

| Net | Pins | Members |
|---|---|---|
| `GND` | 58 | all grounds incl. every divider bottom and cap return |
| `+3V3` | 23 | sensor supplies, pull-ups, Teensy/Pi/XIAO 3V3 |
| `+5V` | 10 | **A2.1/A2.2 (source)**, U3 VCC, J12 ×2, J2, J6, J7, U1, U12 |
| `+VELEC` | 5 | J13.1, A2 VIN ×2, C1.1, R3.1 |
| `+VWINCH` | 3 | J14.1, C2.1, R5.1 |
| `12S_RAW` | 3 | J11.2, C3.1, R7.1 |
| `ELEC_SENSE` | 3 | R3.2, R4.1, **R11.1** |
| `WINCH_SENSE` | 3 | R5.2, R6.1, **R12.1** |
| `S12_SENSE` | 3 | R7.2, R8.1, **R14.1** |
| `DRIVE_SENSE` | 3 | R1.2, R2.1, **R13.1** |
| `ELEC_ADC` | 2 | R11.2, C5.1 |
| `WINCH_ADC` | 2 | R12.2, C6.1 |
| `S12_ADC` | 2 | R14.2, C4.1 |
| `DRIVE_ADC` | 2 | R13.2, C7.1 |
| `I2C_SDA` / `I2C_SCL` | 2 each | R9/R10 pull-ups to U2's upstream bus |
| `+VDRIVE` | 1 | R1.1 only — no drive connector requested yet |

### M18 pack inputs

`J13` **XT60 M18 ELECTRONICS** and `J14` **XT60 M18 WINCH**, board-side male
(`AMASS_XT60-M_1x02_P7.20mm_Vertical`) to match V2. Pin 1 = `+`, pin 2 = `-`. Each pack feeds its own
rail, bulk cap and divider; the electronics rail also feeds **A2's VIN**, which is what generates +5V.

Bulk caps set as asked: **C1 = 470 µF 35 V (elec)**, **C2 = 470 µF 35 V (winch)**. C3 stays the 12S
100 V cap with capacitance still TBD.

### 1 k series resistors on every battery sense (added 2026-08-05)

**R11–R14 (1 k)** sit between each divider tap and its ADC pin. V2 carried **three 1 k resistors**,
one per battery domain — that pattern was missing here and the user caught it. Each sense chain is now:

```
rail ──[56k]──┬──[1k]──┬── ADC pin
              │        │
            [10k]   [100nF]
              │        │
             GND      GND
```

The 100 nF also **moved to the ADC side** of the series resistor, which is where it belongs:

- **The RC filter is the 1 k × 100 nF pair** — 100 µs, ≈1.6 kHz corner. With the cap on the divider
  node instead, the time constant came from the divider's Thévenin resistance (56k∥10k ≈ 8.5 kΩ,
  ~850 µs) and varied with the divider ratio.
- It gives the SAR **sampling capacitor a local charge reservoir**, so the conversion doesn't have to
  pull charge through 8.5 kΩ.
- The 1 k **limits current into the ADC input clamp diodes** if the tap ever goes out of range. With
  the cap directly on the divider node there was no series protection at all.

Four now rather than V2's three, because V3 adds the 12S tap as a fourth sensed rail.

### Supply voltages, chosen per datasheet

| Part | Pin | Rail | Datasheet range |
|---|---|---|---|
| U2 TCA9548A | VCC | 3V3 | 1.65–5.5 V |
| **U3 TJA1051T/3** | **VCC** | **5V** | 4.5–5.5 V — required |
| **U3 TJA1051T/3** | **VIO** | **3V3** | logic side |
| U4 BNO085 | VDD, VDDIO | 3V3 | 1.8–3.6 V |
| U5 ADXL375 | Vs, Vdd_I/O | 3V3 | 2.0–3.6 / 1.7–3.6 V |
| U6 BMP390 breakout | VIN | 3V3 | 3–5 V (onboard regulator) |
| U7 BH1750FVI | VCC | 3V3 | 2.4–3.6 V |
| **U8 SHT45** | **VDD** | **3V3** | 1.08–**3.6 V max** |
| U9–U11 INA228 | VS | 3V3 | 2.7–5.5 V |
| A1 A4988 | VDD | 3V3 | 3–5.5 V logic |
| J1 M10-25Q | V | 3V3 | u-blox M10 + QMC5883L are 3.3 V |
| A2 D36V50F5 | VOUT | **5V (source)** | — |

⚠ **U3 was the plain `TJA1051T` and is now `TJA1051T-3`.** The plain part is 5 V-logic only; its RXD
would push 5 V into the Teensy 4.1, which is **not 5 V tolerant**. The /3 variant adds `VIO` on pin 5
(was NC) for a 3.3 V logic side. **V2 already used the /3 part** — vendoring the plain one into V3 was
a regression introduced here, now corrected.

⚠ **SHT45 must never see 5 V** — 3.6 V absolute max. V2 shipped 5 V to J7/J11/J13 against an SHT41
with the same limit; that is why every sensor rail here is explicit rather than inferred.

### Left for you

- **Sense nodes have no ADC pin yet.** `ELEC_SENSE`, `WINCH_SENSE`, `S12_SENSE` and `DRIVE_SENSE` each
  have divider top, divider bottom and filter cap — but no Teensy pin. Which ADC each lands on is a
  pinout decision.
- **`+VDRIVE` has one member (R1.1).** Only elec and winch XT60s were asked for; the drive domain has
  no connector, so its divider is unterminated at the top.
- **A1 `VMOT`** (stepper motor supply) is unconnected — it needs a motor rail, not a logic one.

## Power symbols placed — GND / +5V / +3V3 (2026-08-05)

**57 power symbols** (`#PWR001`–`#PWR057`) placed directly on every matching pin. Power symbols have
their pin at (0,0) with zero length, so placing one on a pin's connection point connects it — no wires
needed. Each is rotated so its graphic points away from the part.

Resulting nets, read back out of the exported netlist:

| Net | Pins | Parts |
|---|---|---|
| `GND` | **45** | A1 A2 J1–J12 U1–U12 (all but the caps/resistors) |
| `+5V` | **7** | J12 (×2), J2, J6, J7, U1, U12 |
| `+3V3` | **7** | J12 (×2), J4, U1, U12 |

Net count fell 338 → 284 as pins merged, and **no other net gained a second node** — so nothing was
tied together by accident.

**Two grounds were caught that literal name-matching missed:** `U8` SHT45's ground pin is named
**`VSS`** (Sensirion's convention, and it is that part's only ground), and `U4` BNO085 has **`GNDIO`**.
Both are now on `GND`. Leaving a sensor's only ground floating would have been a real defect.

**Deliberately NOT swept onto a rail** — each of these needs a design decision, not a name match:

- `VDD` / `VCC` / `VS` / `VDDIO` / `VDD_I/O` (A1, U2, U3, U4, U5, U7, U8, U9–U11) — supply pins whose
  voltage is a choice. The SHT45 is 3.3 V max; V2 already shipped 5 V to J7/J11/J13 against an SHT41
  rated 3.6 V.
- `U6` **`3V0`** — that is the BMP390 breakout's own 3.0 V regulator **output**, not an input.
- `U9/U10/U11` **`VBUS`** — the INA228's bus-voltage **sense** input, not a supply.
- `J1` **`V`**, and every `VIN` (A2, J11, U1, U6), plus `VMOT`, `VBAT`, `VUSB`, `VOUT`, `VRP`.

⚠ **One GND net does not remove the star-point requirement.** `CLAUDE.md` records the three M18
domains as *"fully isolated … no shared ground except a single star point on the logic PCB"*. A single
`GND` net in the netlist is correct — the sense dividers must reference logic ground for the ADC to
mean anything — but **the isolation has to be enforced in copper**, by routing those domain returns to
one point rather than dropping a single pour. The netlist will not warn you.

## Raspberry Pi added — J12 (2026-08-05)

Stock KiCad has **no Pi 5 symbol or footprint** — only Compute Modules and Picos. So:

- **Footprint** `RaspberryPi_5_GPIO_Socket_2x20`, derived from the built V2 board (it was `J3`,
  `Module:Raspberry Pi  Mounting`): 40 pads on 2.54 mm / 1.0 mm drill, plus 4 mounting holes at
  **49 × 58 mm** — exactly the Pi pattern. Holes are **non-plated 3.2 mm**, the same call made for the
  Pololu. Note the Pi's own mounting holes *are* grounded on the Pi PCB, so if you deliberately want a
  chassis-ground path through the standoffs, these need to go back to plated.

### ⚠ FIXED: the V2 odd/even column transposition

`CLAUDE.md` lists among V2's as-built defects: *"J3's footprint has the odd/even rows transposed
(schematic pad N = Pi pin N∓1)"*. The footprint was extracted from that board, so **it carried the
defect in**. It is now corrected:

| | Odd pins (1,3…39) | Even pins (2,4…40) |
|---|---|---|
| V2 (wrong) | X = −47.70 (inner) | X = −50.24 (outer) |
| **V3 (fixed)** | **X = −50.24 (outer)** | **X = −47.70 (inner)** |

A **`PIN1` silkscreen marker** was added beside pad 1 so this cannot silently regress again — the
original defect was invisible in the schematic and only showed up as wiring problems.

**Mounting orientation:** the Pi sits **above the carrier, upside down, fan/header side facing the
PCB**, so its male GPIO pins come down into this socket. That means the carrier needs a **female 2×20
socket**, not a pin header — the footprint name now says so.

⚠ **Verify pin 1's physical corner once before fab.** The relative fix (columns swapped) is what was
asked for and is done, but absolute handedness depends on which way round the Pi is fitted above the
board, and that is a placement decision this footprint can't encode.
- **Symbol** `RaspberryPi_GPIO_2x20`, from `Connector_Generic:Conn_02x20_Odd_Even` with **all 40 pins
  named** — `3V3`, `5V`, `GND`, and `GPIOn` with primary alternate function (`GPIO2_SDA1`,
  `GPIO14_TXD`, `GPIO10_MOSI`, `GPIO8_CE0`, `GPIO0_ID_SD`, …). Pinout verified against the published
  GPIO connector table; the 40-pin layout is unchanged from Model B+ through Pi 5.

**What the header is actually for on V3.** Navigation and CV stay on the Pi; the Teensy is the
real-time executor. So this is mainly the 5 V feed from `A2` plus a UART/I²C link. Two things worth
carrying forward: in the V2 bench the **GPS sat on GPIO15** (`/dev/ttyAMA0` @ 38400) and the **A4988
stepper on the Pi header** — in V3 both move to the Teensy, so those pins are free.

⚠ **Power budget.** A Pi 5 alone can draw **5 A**. `A2` is rated 5.5 A typical at 36 V in. If the Pi
shares that rail with the Teensy, sensors and the LED, the margin is thin — and V2's journal already
records 34 `Undervoltage detected!` events on the Pi. Worth sizing deliberately rather than assuming.

## Connectors — typed and named per function (2026-08-05)

The four generic `Conn_JST_XH_1x0N` symbols were replaced with function-specific symbols carrying
real pin names, so a net can't be mis-landed on "Pin_3".

| Ref | Symbol | Pin names |
|---|---|---|
| J1 | `Conn_GPS_M10_1x06` | 1 TX · 2 RX · 3 GND · 4 V · 5 SCL · 6 SDA |
| J2 | `Conn_PodTether_1x04` | 1 GND · 2 5V · 3 TX · 4 RX |
| J3 | `Conn_CAN_1x03` | 1 CANH · 2 CANL · 3 GND |
| J4 | `Conn_SHT45_Ext_1x04` | 1 GND · 2 3V3 · 3 SDA · 4 SCL |
| J5 | `Conn_Stepper_1x04` | 1 1A · 2 1B · 3 2A · 4 2B |
| J6 | `Conn_StatusLED_1x03` | 1 GND · 2 5V · 3 DIN |
| J7 | `Conn_SBUS_1x03` | 1 GND · 2 5V · 3 SBUS |
| J8 / J9 | `Conn_HullLeak_1x02` | 1 GND · 2 LEAK |
| J10 | `Conn_WinchESC_1x02` | 1 GND · 2 PWM |
| J11 | `Conn_12S_Tap_1x02` | 1 GND · 2 VIN |

**Pin-order convention**, applied consistently and taken from the V2 board where documented:

- **2-pin:** 1 = GND, 2 = signal. This is V2's own convention — `docs/session_journal_archive.md`
  records the hull-leak JST-XHs as "wired 1 = GND, 2 = signal, i.e. exactly an ESC servo lead".
- **3-pin:** 1 = GND, 2 = 5V, 3 = signal — standard servo/RC lead order.
- **4-pin:** 1 = GND, 2 = power, 3/4 = signals.
- CAN keeps CANH/CANL on pins 1–2 so the twisted pair stays adjacent.

⚠ The **order** is a convention I applied, not something read off hardware — only J1's order came
from the user. Reversing any connector is a pin-name edit, no footprint change. Pins are left
electrically `passive`, matching KiCad's generic connectors, so ERC won't demand power flags on every
shell.

Two notes carried into the symbol descriptions: `Conn_Stepper_1x04` warns that 1A/1B are one coil and
2A/2B the other (swapping across pairs won't turn the motor), and `Conn_StatusLED_1x03` warns that
V2's status LED sat on GP10, which is hard-shorted to GND — don't repeat that.

## Authored locally

| Part | Symbol | Footprint |
|---|---|---|
| ADXL375 | `lib/dreams_v3.kicad_sym` → `ADXL375` | `dreams_v3:LGA-14_3x5mm_P0.8mm_LayoutBorder1x6y` |

Derived programmatically from KiCad's own `Sensor_Motion:ADXL343` (same 3×5×1 mm 14-lead LGA family),
so the pin geometry and s-expression syntax come from a reviewed source rather than being typed by
hand.

### ✅ VERIFIED against the datasheet (2026-08-05)

Checked pin-by-pin against **ADXL375 Rev. B, page 6, Table 5** (user-supplied PDF, text extracted with
`pypdf`). **All 14 pins match** the derived symbol exactly:

| 1 | 2 | 3 | 4 | 5 | 6 | 7 |
|---|---|---|---|---|---|---|
| VDD I/O | GND | RESERVED | GND | GND | VS | CS |

| 8 | 9 | 10 | 11 | 12 | 13 | 14 |
|---|---|---|---|---|---|---|
| INT1 | INT2 | NC | RESERVED | SDO/ALT ADDRESS | SDA/SDI/SDIO | SCL/SCLK |

The derivation from the ADXL343 was sound — no discrepancy. This closes the largest open risk in the
library.

⚠ **The two RESERVED pins are not interchangeable, and the symbol can't tell you that.** Per Table 5,
**pin 3 must connect to VS or be left open**, while **pin 11 must connect to GND or be left open**.
Both are just labelled `RES` in the KiCad symbol. Tying pin 3 to ground is a real wiring error the
schematic will not flag — the warning is now in the symbol's Description field.

## Must be sourced externally — not available locally

All resolved except the GPS module — user-supplied SnapEDA exports were merged 2026-08-04.

| Part | Symbol | Footprint | Note |
|---|---|---|---|
| Teensy 4.1 | ✅ `dreams_v3:Teensy4.1` | ✅ `dreams_v3:Teensy41` (67 pads) | From [XenGi/teensy_library](https://github.com/XenGi/teensy_library) + [teensy.pretty](https://github.com/XenGi/teensy.pretty), **MIT**. The parts doc's caution about 4.1 coverage is resolved. |
| Seeed XIAO ESP32-S3 | ✅ `dreams_v3:XIAO_ESP32_S3` (14) | ✅ `dreams_v3:MODULE_XIAO_ESP32_S3` (14 THT) | SnapEDA matched pair. fabcloud's 39-pad dual-mount footprint kept as an alternate. |
| BNO085 | ✅ `dreams_v3:BNO085` (28) | ✅ `dreams_v3:LGA-28_5.2x3.8mm_P0.5mm` | Symbol SnapEDA; footprint is KiCad's KLC-reviewed pattern. SnapEDA's `IC_BNO085` verified **equivalent** — identical topology, numbering and pin-1 position; KiCad's pads ~0.1 mm longer, better for hot-air fillet. |
| BMP390 | ✅ `dreams_v3:BMP390` (8) | ✅ `dreams_v3:BMP390` (8 THT) | ⚠ **This is the breakout board, not the chip** — see below. |
| BH1750FVI-TR | ✅ `dreams_v3:BH1750FVI-TR` (6) | ✅ `dreams_v3:XDCR_BH1750FVI-TR` (6 SMD) | Bare WSOF-6 chip. Needs a clear optical path — it is a *light* sensor. |
| M10-25Q GPS module | ✅ `dreams_v3:Conn_JST_XH_1x06` | ✅ `dreams_v3:JST_XH_B6B-XH-A_1x06_P2.50mm_Vertical` | **Goes on a JST-XH connector, not on the board** — so the parts doc's "no verified library, measure by hand" item is closed. 6-pin assumes VCC/GND/TX/RX + SDA/SCL for the onboard QMC5883L; verify against your module. |

### V2 audit — what was missing, and what was added (2026-08-04)

Read the V2 schematic (44 real components) and carried across everything V3 lacked. Library is now
**21 symbols / 24 footprints**; the schematic holds **42 components**, all with footprints assigned.

| From V2 | V3 |
|---|---|
| `J11` Temp+Humidity **External** (JST-XH 4-pin) | **J4** — external SHT45 on a connector, as requested |
| `J13` Temp+Humidity Internal (pin header) | on-board `U8` SHT45 |
| `J12` LED GPIO 12 (3-pin) | **J6** status LED |
| `J15`/`J16` Hull Leak L/R (2-pin) | **J8**/**J9** — restored; the test bench had repurposed these as ESC signals |
| `J18` Stepper Motor (4-pin) | **J5** + **A1** A4988 driver |
| `J8` Winch ESC (2-pin) | **J10** |
| `J4` **12s Tap** (2-pin) | **J11** |
| `J2` unlabeled 3-pin | **J7** — read as the SBUS RC receiver (RC override is in the V3 carry-over list) |
| `A2` Pololu A4988 | **A1** |
| `J1` (2x06) w/ `Module:Pololu 36v5vstepdown` | **A2** — see below |
| `J5` IMU (10-pin) | on-board `U4` BNO085 |
| `J7` GPS+Compass (6-pin) | **J1** |
| `U1` MCP2515 + `Y1` Crystal | dropped — Teensy has native FlexCAN |
| `A1` Pico, `J3` Pi hdr, `J14`/`J17` 1x20 sockets | replaced by the Teensy module |
| `BT1`/`BT4`/`J6` XT60 battery + output | not carried — V3 power domains differ |

**Two Pololu parts existed in V2, so both were added:** the **A4988** stepper carrier (`A1`, symbol
and footprint both stock) and the **5 V / 5 A / 36 V-in step-down** (`A2`).

### The Pololu step-down — identified as the D36V50F5 (item #4091)

Confirmed from [pololu.com/product/4091](https://www.pololu.com/product/4091): **5 V out, 5.5 A
typical at 36 V in, input range 5.5–50 V, 1″ square, 12 pins in 2 rows of 6 on a 0.1″ grid, three
0.086″ (M2) mounting holes.** That matches the V2-derived land pattern exactly — 12 pins on 2.54 mm
pitch plus three 2.2 mm-drill holes — so the V2 footprint is correct and is now named
`dreams_v3:Pololu_D36V50F5`.

All 12 pins are named from the **as-built layout the user read off the board** (2026-08-05). Pololu's
product page lists the rows as `VIN EN PG GND VOUT VRP` / `VIN — — GND VOUT VRP`, which is **wrong for
this part** — there are no unconnected pins, and there are four GND pins, not two:

| | col 1 | col 2 | col 3 | col 4 | col 5 | col 6 |
|---|---|---|---|---|---|---|
| Row 1 | VOUT | GND | GND | VIN | VRP | **EN** |
| Row 2 | VOUT | GND | GND | VIN | VRP | **PG** |

Mapped onto the footprint's odd/even pad numbering (each column is a consecutive odd/even pair):

| Pad | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Name | VOUT | VOUT | GND | GND | GND | GND | VIN | VIN | VRP | VRP | EN | PG |

Electrical types set accordingly — `power_out` on VOUT/VRP, `power_in` on VIN/GND, `input` on EN,
`open_collector` on PG. Four GND pins plus doubled VOUT/VIN/VRP carry the current; **EN and PG are the
only single pins.** VRP is reverse-protected VIN.

**Col 6 is resolved (2026-08-05): EN is the outer pin, PG the inner.** Col 6 was the only ambiguous
column — every other one carries the same signal on both rows, so row order cannot matter there.

The footprint geometry agrees independently. Its three mounting holes sit at (−21.10, 0.20), (0, 0)
and (0, 21.10), so the module body extends toward **−x**; that makes **x = +1.37 the outer column**
(board edge, away from the body) and x = −1.17 the inner one. Odd pads are the outer column, so
**pad 11 = EN, pad 12 = PG**. No pin mapping is left open on this part.

Note the input range is **5.5–50 V**, not 36 V — 36 V is where the 5.5 A figure is specified. The M18
electronics domain at ~21 V is comfortably inside range.

### Footprint provenance

The step-down's footprint existed **nowhere but inside the V2 `.kicad_pcb`** — nothing local, nothing
in stock KiCad, and the community `tannewt/kicad-pololu` repo is empty (LICENSE + README only). It was
extracted from the V2 board, stripped of board-level net/placement data, upgraded to KiCad 10 format,
and is now **`Pololu_5V_5A_StepDown_2x06`**: 12 pins on 2.54 mm pitch, odd/even down two rows, plus
three 2.2 mm mounting holes 21.1 mm apart.

The part is **user-confirmed as 5 V / 5 A / 36 V max in with a 2×6 header**, which makes that 2×6 land
pattern correct — and explains itself: 12 pins for roughly 5 signals means VIN/GND/VOUT are
paralleled across several pins, because one 1.0 mm-drill pin cannot carry 5 A.

Two caveats recorded in the footprint's own `descr`:

- **Pin names are unassigned.** Pads are just 1–12; the symbol is a 2×6 module symbol carried from
  V2's `Conn_02x06_Odd_Even`. Pololu document the pin *set* as PG / EN / VIN / GND / VOUT (+ a second
  GND) but publish the physical order only as silkscreen and as vector art in the dimension diagram —
  no extractable text. Read the order off the board to name them.
- **Exact part number unconfirmed.** Pololu's D24V50F5 matches electrically (5 V, 5 A, up to 38 V in)
  but its documentation describes *five pads in one row*, not a 2×6. Confirm the P/N before fab.

An unmerged KiCad PR ([#1535](https://github.com/KiCad/kicad-footprints/pull/1535), alive on the
[GitLab mirror](https://gitlab.com/kicad/libraries/kicad-footprints/-/tree/github/fork/jstjst/pololu_DCDC))
does carry real Pololu footprints, but only for the **D24V5Fx / D24V10Fx / D24V22Fx** families — the
2.5 A-and-below parts, single 1×5 row. Those were fetched, found to be the wrong family, and removed.

**GPS connector** is now a dedicated symbol `Conn_GPS_M10_1x06` with real pin names in your wiring
order: **1=TX 2=RX 3=GND 4=V 5=SCL 6=SDA** (SCL/SDA being the onboard QMC5883L compass), rather than
generic Pin_1..6.

### Passives added

**Battery dividers use the as-built 56k/10k (÷6.6)**, one pair per isolated M18 domain — R1/R2 drive,
R3/R4 electronics, R5/R6 winch. Deliberately **not** the values in the V2 KiCad schematic (220k/13k,
100k/30k, 100k/18k), which `CLAUDE.md` records as stale: the board is right, KiCad is wrong.

**12S tap divider: R7 220k / R8 13k = 17.9×.** At a 12S Li-ion maximum of 50.4 V that reads 2.81 V,
inside the Teensy's 3.3 V ADC with headroom to 59 V. ⚠ **This assumes "12S" means 12 cells ≈ 50.4 V
max.** If the tap is actually the 3×M18 series stack the V3 doc calls 63 V max, 220k/13k gives 3.52 V
and **over-ranges the ADC** — use 220k/12k (19.3×, 3.26 V at 63 V) instead.

**Capacitors:** C1/C2 are the 35 V radial electrolytics carried from V2 (same
`CP_Radial_D10.0mm_P5.00mm` body as V2's C5/C7). C3 is the 12S high-voltage cap at **100 V** — rated
roughly 2× the 50.4 V rail, on the larger `CP_Radial_D12.5mm` body since a 100 V can does not fit the
D10 footprint. C4–C7 are 100 nF ADC filter caps, one per divider tap.

⚠ **Capacitance values are unset (`uF TBD`).** V2's schematic recorded no capacitance for any of its
9 capacitors — only footprints — so there was nothing to copy. Fill these in.

**R9/R10 (4.7k) are an unrequested addition: I²C pull-ups on the upstream TCA9548A bus.** `CLAUDE.md`
records V2 shipping with *no pull-ups on any of its three buses*, which cost a long IMU debugging arc
and was only fixed by hand-soldering 2.2 kΩ resistors onto GP14/GP15. **Each downstream mux channel
you use needs its own pair too** — only the upstream pair is placed. Delete them if you'd rather
handle this differently.

### The 12S tap — confirmed for V3 (2026-08-04)

`CLAUDE.md` states "There is no 12S-midpoint tap — the winch is a standalone pack." That describes
the **V2 test bench**. V2's schematic already carried `J4 "12s Tap"` (2-pin JST-XH), and the user has
confirmed **V3 will have a 12S tap** — so it is placed as `J11`, with divider R7/R8 and the 100 V
cap C3.

The divider maths above still assumes **12S ≈ 50.4 V max** (12 cells × 4.2 V). That is what "12S"
normally means and it is consistent with a midpoint tap on the series drive stack. If the tap sits
higher up the stack, recheck R8 against the 3.3 V ADC ceiling.

### Schematic populated

All **16 parts** are placed in `Boat_PCB_V3.kicad_sch` — **unwired**, grouped by role on an A1 sheet
with headings: compute & bus (U1–U3), sensors (U4–U9), current sense (U10–U12, one per M18 domain),
connectors (J1–J3), and the pod XIAO (U13). A2 was tried first and overflowed by 1.7 mm with no room
for nets.

Verified: `kicad-cli sch export netlist` resolves all 16 references (J1–J3, U1–U13) with no
unresolved libsource; the sheet renders to PDF; and a pairwise bounding-box check found no symbol
overlaps and nothing outside the sheet.

⚠ **U13 (XIAO ESP32-S3) belongs on the separate Pod PCB**, not the carrier. It is placed here for
reference because the V3 project currently has one schematic. Move it to its own sheet or project
when the pod board starts.

### ⚠ The BMP390 part is a breakout board — this changes the fabrication plan

The SnapEDA "BMP390" is a **module**: 8 through-hole pads on 2.54 mm pitch
(VIN · 3V0 · GND · SCL · SDO · SDA · CS · INT), body ~23.5 × 14 mm. SnapEDA's own Description says
"10-WFLGA", which is the *chip's* package — that mislabel is why it first read as a pin-count error.

Consequence: **`V3_PCB_SESSION_CONTEXT.md` lists the BMP390 among the leadless packages going down
via hot air + paste + stencil. That is no longer accurate** — it is a THT header part now. The
stencil list is BNO085, SHT45 ×2 and ADXL375.

If you later want it on-board instead, order the bare **BMP390L** — the long-availability version and
the one actually stocked as a component — and source a land pattern from `bst-bmp390l-ds001.pdf`.
Nothing in the library covers Bosch's LGA-10.

⚠ **Correction to the parts doc's Teensy link.** It gives
`github.com/jenschr/Teensy-4.1-example` as a "verified working KiCad project." That repo implements
the bare **MIMXRT1062DVJ6B** (BGA196) chip a Teensy contains — it has no Teensy *module* symbol or
footprint, so it is the wrong source for a board the Teensy plugs into. XenGi's libraries, listed
there as the secondary option, are the correct source and do cover 4.1.

**Why these were not authored locally:** land patterns for leadless parts must come from the
datasheet's recommended pattern. These are being placed with stencil + hot air, where pad size and
paste ratio decide whether the joint forms — invented geometry produces an unbuildable board. For
BMP390 and BH1750 no local land pattern exists at all, and for BH1750 the pin numbering could not be
established from any reachable source. A verified SnapEDA / Ultra Librarian export gives a correct
symbol *and* footprint in minutes and is the better input here.

## Registering the local library

Not done yet — **KiCad was running** (PID 36132, project open, live `.lck` files) when this was
written, and the project lib tables are exactly what KiCad rewrites from the Manage Libraries dialog.
With KiCad closed, add to a project-local `sym-lib-table` beside `Boat_PCB_V3.kicad_pro`:

```
(sym_lib_table
  (version 7)
  (lib (name "dreams_v3")(type "KiCad")(uri "${KIPRJMOD}/lib/dreams_v3.kicad_sym")(options "")(descr "D.R.E.A.M.S V3 project symbols"))
)
```

`${KIPRJMOD}` keeps it relative, so the library moves with the repo. Add a matching `fp-lib-table`
pointing at `${KIPRJMOD}/lib/dreams_v3.pretty` once there are footprints to put in it. Keeping this
project-local rather than global means a fresh clone works with no per-machine setup — which is how
V2 stayed portable.
