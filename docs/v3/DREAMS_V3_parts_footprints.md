> **Planning record, stored verbatim.** This is the BOM as written during the August 2026 V3
> PCB-planning session, before the library was built. The text below the rule is unmodified.
>
> The "KiCad?" and "Link" columns are now history. Every part resolves from the project library or
> from stock KiCad; see
> [`Boat_PCB_V3/lib/README.md`](../../Boat_PCB/Boat_PCB_V3/lib/README.md).
>
> If this disagrees with [`V3_DESIGN_BRIEF.md`](V3_DESIGN_BRIEF.md) or the KiCad files, those win.
> For example, the board fits **two** INA228s, not three, and the GPS lands on a JST-XH cable
> connector.
>
> **The POD PCB section is superseded (2026-09-25).** The tether carries pack voltage, so the pod
> has a Pololu buck and a 3.3 V LDO rather than "no external LDO". The link is RS-485 through a
> THVD2410, and the sensors are a DFRobot test-phase set. See
> [`V3_DESIGN_BRIEF.md`](V3_DESIGN_BRIEF.md) §5 and `Boat_PCB/Pod_PCB_V3/`.

---

# D.R.E.A.M.S V3 — Parts & Footprint Reference
### For KiCad layout — Boat Carrier PCB + Pod PCB
### Rev 3 — includes KiCad library availability + external links

> **Key:** "In KiCad" = standard generic footprint already ships with KiCad (Package_SO, Package_LGA,
> Connector_JST, etc. libraries) — no download needed, though you'll still enter pin names yourself
> for generic symbols. "Needs download" = manufacturer-specific symbol/footprint/3D model, link given.
> SnapEDA (snapeda.com) requires a free account to export, but browsing/viewing is public.

---

## BOAT CARRIER PCB

### Core compute

> **Updated 2026-10-13 (rev E):** the Teensy 4.1 below was replaced by two Raspberry Pi Pico 2s. Fit:
> 2× Raspberry Pi Pico 2 (the H version has the headers on), 4× 1×20 female header, 8.5 mm (one pair
> per Pico, soldered to the carrier's underside), 2× B5819W (D10, D11, SOD-123), 2× 6 mm tact switch
> (SW1, SW2). The project library has all of them (`RaspberryPi_Pico_Socketed_THT`, `D_SOD-123`,
> `SW_PUSH_6mm`). The original line is kept for the record. The Pi's reset lines to the Picos (same
> day) add 2× BSS138 (Q3, Q4, `SOT-23`) and 2× 100k 1 % axial (R64, R65), and its UART adds 2× 1k 1 %
> axial standing upright (R66, R67, `R_Axial_DIN0207_L6.3mm_D2.5mm_P2.54mm_Vertical`). All are already in
> the library.

| Part | Package | KiCad? | Link |
|---|---|---|---|
| ~~**Teensy 4.1**~~ (replaced in rev E) | THT module, 2.4"x0.7" | **Needs download** | Verified working KiCad project (schematic + PCB, tested): https://github.com/jenschr/Teensy-4.1-example — also general Teensy symbol/footprint libraries: https://github.com/XenGi/teensy_library (symbols) + https://github.com/XenGi/teensy.pretty (footprints), though confirm Teensy 4.1 coverage vs just 3.x/4.0 before relying on it |

### Parts already on hand (2026-10-13)

Bought for V2's CAN circuit. Use them before ordering more:

| Part | Qty | Where it goes |
|---|---|---|
| NXP **TJA1051T/3,118** CAN transceiver, SO-8 | 3 | V3 U3 and V3.1 U4; one spare |
| Rubycon **35ZLH470MEFC10X16**, 470 µF 35 V, 10 × 16 mm, 5 mm leads | 5 | V3 C1, C2, C25 and C26 (C25 went from 100 µF to 470 µF to use one); one spare. Not V3.1's C1: its 10S pack reaches 42 V |
| Microchip **MCP2515-I/P** CAN controller, DIP-18 | 3 | Spare: V3 and V3.1 run CAN on can2040 |
| ECS **ECS-80-20-4X** crystal, 8 MHz, 20 pF | 4 | Spare: they were for the MCP2515 |

### CAN bus
| Part | Package | KiCad? | Link |
|---|---|---|---|
| **TJA1051T** (SOIC-8) or **TJA1051TK** (HVSON-8) | SOIC-8 / HVSON-8 | Generic footprint in KiCad; **symbol needs download** for correct pin names | SOIC-8 variant: https://www.snapeda.com/parts/TJA1051T/3/1J/NXP%20USA%20Inc./view-part/ — HVSON-8 variant: https://www.snapeda.com/parts/TJA1051TK/3,118/NXP%20Semiconductors/view-part/ |
| 120Ω termination resistors | 0805 or THT axial | **In KiCad** (Resistor_SMD / Resistor_THT libraries) | — |

### I2C sensor bus
| Part | Package | KiCad? | Link |
|---|---|---|---|
| **TCA9548A** (I2C mux) | TSSOP-24 | Generic footprint in KiCad; **symbol needs download** | https://www.snapeda.com/parts/TCA9548APWR/Texas%20Instruments/view-part/ |
| **BNO085** (IMU) | LGA-28 | **Needs download** — LGA pad grid is part-specific, not a generic match | SnapEDA: https://www.snapeda.com/parts/BNO085/CEVA%20Technologies,%20Inc./view-part/ — also Ultra Librarian: https://app.ultralibrarian.com/details/c30a88bc-bf3a-11ec-9033-0a34d6323d74/CEVA/BNO085 |
| **SHT45** x2 | DFN-4 | **Needs download** | https://www.snapeda.com/parts/SHT45-AD1B-R3/Sensirion/view-part/ (or the -R2 variant, same part different reel size) |
| **BMP390** (barometric ref) | LGA-10 (WLCSP) | **Needs download** | https://www.snapeda.com/parts/BMP390/Bosch/view-part/ |
| **ADXL375** (accelerometer, +/-200g) | LGA-14 | **Needs download** — one SnapEDA listing flagged "exact symbol not available," so verify before relying on it, or build the symbol manually from the datasheet pinout (same as ADXL345's) | https://www.snapeda.com/parts/ADXL375BCCZ-RL7/Analog%20Devices/view-part/ |
| **BH1750FVI-TR** (ambient light) | WSOF-6 | **Needs download** | https://www.snapeda.com/parts/BH1750FVI-TR/Rohm/view-part/ |
| **INA228** x3 (current sense) | VSSOP-10 | Generic footprint in KiCad; **symbol needs download** | Search "INA228" on snapeda.com (the bare-chip part page, not the EVM eval-board page) |

### GPS + compass
| Part | Package | KiCad? | Link |
|---|---|---|---|
| **M10-25Q** GPS module (u-blox M10 + patch antenna, onboard QMC5883L) | Breakout module header | **No verified library found** — likely needs a manually-built footprint matched to the specific vendor's pin pitch/hole pattern once the part is in hand | — |

### Battery sense, hull, winch (carried over — all standard KiCad parts)
| Part | Package | KiCad? |
|---|---|---|
| Divider resistors, filter resistors/caps | THT axial, ceramic disc | **In KiCad** |
| Hull-leak switches, winch PWM header | 2/3-pin header | **In KiCad** |

### Pod tether interface
| Part | Package | KiCad? |
|---|---|---|
| 4-conductor JST-XH connector | JST-XH 4-pin | **In KiCad** (Connector_JST library) |

---

## POD PCB

### Core compute
| Part | Package | KiCad? | Link |
|---|---|---|---|
| **Seeed XIAO ESP32-S3** | 21x17.5mm module | **Needs download** | SnapEDA: https://www.snapeda.com/parts/XIAO%20ESP32%20S3/Seeed%20Studio/view-part/ — also community footprint file: https://gitlab.fabcloud.org/ricardo.marques/kicad/-/blob/master/fab.pretty/SeeedStudio_XIAO_ESP32S3.kicad_mod |

### Power regulation
| Part | Package | KiCad? | Link |
|---|---|---|---|
| **No external LDO needed** — XIAO ESP32-S3 has an onboard regulator, feed 5V directly into its 5V/VBUS pin (pin 14) | — | — | — |
| Schottky diode (protection, in series between tether 5V and the XIAO's 5V pin) | SOD-123 or similar | **In KiCad** | Seeed's own docs require this — that pin is shared with USB/charge circuitry, diode prevents backfeed |

### Pod sensors (all standard/generic — no external library needed)
| Part | Interface | KiCad? |
|---|---|---|
| EC/salinity probe interface, NTC thermistor, photoresistor, bottom-contact switch, pressure transducer divider, leak contact, status LED | Digital/ADC, THT | **In KiCad** — all generic passives/connectors/LEDs |

### Tether interface
| Part | Package | KiCad? |
|---|---|---|
| 4-conductor JST-XH connector | JST-XH 4-pin | **In KiCad** |

---

## Remaining open item
1. **CAN bus termination placement** — depends on where you physically splice the Teensy stub into the VESC1-VESC2 wire; termination stays at the two VESCs regardless, no change needed there
