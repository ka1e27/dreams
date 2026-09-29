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
| Part | Package | KiCad? | Link |
|---|---|---|---|
| **Teensy 4.1** | THT module, 2.4"x0.7" | **Needs download** | Verified working KiCad project (schematic + PCB, tested): https://github.com/jenschr/Teensy-4.1-example — also general Teensy symbol/footprint libraries: https://github.com/XenGi/teensy_library (symbols) + https://github.com/XenGi/teensy.pretty (footprints), though confirm Teensy 4.1 coverage vs just 3.x/4.0 before relying on it |

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
