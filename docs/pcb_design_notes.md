# PCB Design Notes

The repo contains one KiCad 10 project (schematic format version `20260306`, generator `eeschema`):

- `Boat_PCB/Boat_PCB.kicad_sch` — the main Boat Pico carrier/breakout board (source of truth).

All information below is extracted directly from that schematic file.

---

# Boat_PCB

Source of truth: `Boat_PCB/Boat_PCB.kicad_sch`.

## Board Overview

A carrier/breakout board hosting the Boat Pico (RP2040), with:
- Battery power inputs (3S, 12S via 2×6S, 4S)
- Per-pack fusing
- Voltage-divider circuits for ADC battery monitoring
- Peripheral connectors for the Boat Pico's sensors and motors
- No Pi 5 on this board — the Pi 5 connects via USB only

---

## Component Reference List

### Microcontroller
| Ref | Part | Footprint |
|-----|------|-----------|
| A1 | RaspberryPi_Pico | `Module:RaspberryPi_Pico_Common_Unspecified` |

Pico access headers:
- J3: `Conn_02x20_Odd_Even` — main 2×20 Pico socket
- J14: `Conn_01x20_Socket` — left column breakout
- J17: `Conn_01x20_Socket` — right column breakout

---

### Batteries
| Ref | Value | Footprint |
|-----|-------|-----------|
| BT1 | 3s (electronics) | `AMASS_XT60-M_1x02_P7.20mm_Vertical` |
| BT2 | 6s | `AMASS_XT60-M_1x02_P7.20mm_Vertical` |
| BT3 | 6s | `AMASS_XT60-M_1x02_P7.20mm_Vertical` |
| BT4 | 4s (winch) | `AMASS_XT30PW-M_1x02_P2.50mm_Horizontal` |

BT2 + BT3 in series = 12S drive rail.

---

### Fuses
| Ref | Value | Footprint |
|-----|-------|-----------|
| F1 | Fuse (electronics) | `Fuse:Fuse_Blade_ATO_directSolder` |
| F2 | Fuse (12S) | no footprint — off-board |
| F3 | Fuse (12S) | no footprint — off-board |
| F4 | Fuse | no footprint set yet |

---

### Resistors (all THT)
**Footprint for all:** `Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal`
**Symbol:** `Device:R`

| Ref | Value | Function |
|-----|-------|----------|
| R2 | 220k | 12S divider R_top |
| R4 | 13k | 12S divider R_bot → GP26 |
| R5 | 100k | 3S divider R_top |
| R6 | 30k | 3S divider R_bot → GP27 |
| R8 | 100k | 4S winch divider R_top |
| R10 | 18k | 4S winch divider R_bot → GP28 |
| R1 | 10k | 12S ADC series filter resistor |
| R3 | 1k | 3S ADC series filter resistor |
| R7 | 1k | 4S ADC series filter resistor |
| R9 | 1k | Leak sense pull-up |

### Voltage-Divider Calculations (as drawn on the PCB)
| Rail | R_top/R_bot | Ratio | Max input | ADC max |
|------|-------------|-------|-----------|---------|
| 12S | R2/R4 (220k/13k) | 17.92 | 50.4V | 2.81V |
| 3S | R5/R6 (100k/30k) | 4.33 | 12.6V | 2.91V |
| 4S winch | R8/R10 (100k/18k) | 6.56 | 16.8V | 2.56V |

> ⚠ **Firmware uses different dividers.** `firmware/boat-pico/sensors.py` is coded for **3.3k/47k**
> (12S, GP26) and **15k/100k** (3S, GP27), and leaves **GP28 unread (spare)** — so the PCB's 4S winch
> sense (R8/R10 → GP28) is not implemented in code, and the 12S/3S divider values above do not match
> the firmware. This mismatch is unresolved; it is documented in
> `docs/hardware_changes_v1_to_v2.md` and `docs/changelog_and_decisions.md`.

All sense taps: after fuse, before bulk cap. Divider grounds meet at a star point near Pico GND.

---

### Capacitors (all THT)

**Polarized electrolytics (bulk):**
| Ref | Footprint | Rail |
|-----|-----------|------|
| C1 | `CP_Radial_D10.0mm_P5.00mm` | 12S bulk |
| C2 | `CP_Radial_D10.0mm_P5.00mm` | 12S bulk |
| C5 | `CP_Radial_D8.0mm_P3.50mm` | 3S bulk |
| C7 | `CP_Radial_D8.0mm_P3.50mm` | 4S bulk |

**Ceramic disc (100nF, ADC filter / general):**
| Ref | Footprint | Rail |
|-----|-----------|------|
| C3 | `C_Disc_D5.0mm_W2.5mm_P5.00mm` | 12S filter |
| C4 | `C_Disc_D5.0mm_W2.5mm_P5.00mm` | 3S filter |
| C6 | `C_Disc_D5.0mm_W2.5mm_P5.00mm` | 4S filter |
| C8 | `C_Disc_D5.0mm_W2.5mm_P5.00mm` | general |

---

### Power Output Connectors
| Ref | Value | Footprint | Function |
|-----|-------|-----------|----------|
| J4 | 12s output | `AMASS_XT90PW-M_1x02_P10.90mm_Horizontal` | VESC left |
| J5 | 12s output | `AMASS_XT90PW-M_1x02_P10.90mm_Horizontal` | VESC right |
| J6 | 6s output | `AMASS_XT60IPW-M_1x03_P7.20mm_Horizontal` | Midpoint / aux |
| J8 | Winch ESC | `JST_XH_S2B-XH-A_1x02_P2.50mm_Horizontal` | 4S power to winch ESC |

### Signal Connectors
| Ref | Value | Footprint | Pico pins |
|-----|-------|-----------|-----------|
| J2 | CAN chain | `PinHeader_1x07_P2.54mm_Vertical` | GP12/13 UART0 to VESC |
| J7 | GPS + Compass | `JST_SH_SM06B-SRSS-TB_1x06-1MP_P1.00mm_Horizontal` | GP4/5 UART1, GP8/9 I²C0 |
| J9 | Winch ESC RC | `PinHeader_1x02_P2.54mm_Vertical` | GP14 PWM |
| J10 | IMU | `PinHeader_1x05_P2.54mm_Vertical` | GP8/9 I²C0 (BNO085) |
| J11 | Temp + Humidity Sensor | `PinHeader_1x04_P2.54mm_Vertical` | GP16 DHT11 |
| J12 | led | `JST_XH_B3B-XH-A_1x03_P2.50mm_Vertical` | GP10 NeoPixel |
| J13 | Temp + Humidity Sensor | `JST_XH_B4B-XH-A_1x04_P2.50mm_Vertical` | GP16 DHT11 (alt) |
| J15 | Hull Leak 20 | `JST_XH_B2B-XH-A_1x02_P2.50mm_Vertical` | GP18 (starboard) |
| J16 | *(Value field blank in schematic)* | `JST_XH_B2B-XH-A_1x02_P2.50mm_Vertical` | GP17 (port) — intended "Hull Leak 19" |
| J1 | Conn_02x06_Odd_Even | `PinHeader_2x06_P2.54mm_Vertical` | SIM7600 / expansion |

> Note: J16's Value field is currently blank in the schematic; based on its footprint and pin
> assignment it is the port hull-leak connector (GP17). Set its Value to "Hull Leak 19" to match J15.

---

## What Is NOT on Boat_PCB

- No MCP2515 CAN chip or HAT
- No HC-12 radio module or connector (HC-12 is only an optional Pi 5 USB dongle)
- No Raspberry Pi 5 (connects via USB cable only)
- No CSI camera connectors
- No GPS module directly (GPS is external, on J7, to the u-blox M10Q)

---

## JLCPCB Notes

- 2-layer FR4, 1.6mm
- THT components throughout — no SMD
- High-current pads (J4, J5 XT90 power) need wide copper pours
- Order 5–10 boards minimum for a price break
- Turnaround: 5–7 days standard
