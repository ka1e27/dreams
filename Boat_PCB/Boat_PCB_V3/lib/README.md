# `Boat_PCB_V3/lib` — project-local KiCad library

Self-contained symbol + footprint library for the V3 board, so a fresh clone resolves every part with
no per-machine library setup. Assembled 2026-08-04 against **KiCad 10.0.5**.

- `dreams_v3.kicad_sym` — **21 symbols**
- `dreams_v3.pretty/` — **24 footprints**
- `dreams_v3.3dshapes/` — 2 STEP models

**42 components are placed in `Boat_PCB_V3.kicad_sch`** (unwired, grouped by role on an A1 sheet):
U1–U12, A1–A2, J1–J11, R1–R10, C1–C7. Verified: `kicad-cli sch export netlist` resolves all 42 with a
footprint on every one and no unresolved libsource, the sheet renders to PDF, and a pairwise
bounding-box check finds no overlaps and nothing off-sheet.

See [`../../../docs/v3/kicad_library_status.md`](../../../docs/v3/kicad_library_status.md) for the V2
audit that drove the part list, the divider maths, and the open questions.

**The PCB is still empty.** `Boat_PCB_V3.kicad_pcb` is 79 bytes. Populating a board from a schematic
is a GUI action — open the project and run **Tools → Update PCB from Schematic** (F8). `kicad-cli`
does not expose it.

Registered via project-local `sym-lib-table` / `fp-lib-table` beside `Boat_PCB_V3.kicad_pro`, using
`${KIPRJMOD}`-relative paths so the library travels with the repo.

**Validation performed:** every symbol renders under `kicad-cli sym export svg` (11/11); every
footprint is in current KiCad 10 format via `kicad-cli fp upgrade`, parses, and has balanced
s-expressions; every symbol's Footprint property was checked to resolve to a file present in
`dreams_v3.pretty/`; every 3D model reference was checked to resolve.

## Contents

| Symbol | Pins | Footprint targeted | Source |
|---|---|---|---|
| `Teensy4.1` | 67 | `Teensy41` | XenGi (MIT) |
| `XIAO_ESP32_S3` | 14 | `MODULE_XIAO_ESP32_S3` | SnapEDA |
| `BNO085` | 28 | `LGA-28_5.2x3.8mm_P0.5mm` | symbol SnapEDA, footprint KiCad stock |
| `BMP390` | 8 | `BMP390` | SnapEDA — **breakout board, see below** |
| `BH1750FVI-TR` | 6 | `XDCR_BH1750FVI-TR` | SnapEDA |
| `ADXL375` | 14 | `LGA-14_3x5mm_P0.8mm_LayoutBorder1x6y` | derived from KiCad `ADXL343` |
| `TJA1051T` | 8 | `SOIC-8_3.9x4.9mm_P1.27mm` | KiCad stock |
| `TCA9548APWR` | 24 | `TSSOP-24_4.4x7.8mm_P0.65mm` | KiCad stock |
| `INA228` | (inherits) | `HVSSOP-10-1EP_3x3mm_P0.5mm_EP1.83x1.89mm` | KiCad stock |
| `INA226` | 10 | same | KiCad stock — **do not place, see below** |
| `SHT4x` | 4 | `Sensirion_DFN-4_1.5x1.5mm_P0.8mm_SHT4x_NoCentralPad` | KiCad stock |
| `Conn_JST_XH_1x06` | 6 | `JST_XH_B6B-XH-A_1x06_P2.50mm_Vertical` | KiCad stock, renamed |
| `Conn_JST_XH_1x04` | 4 | `JST_XH_B4B-XH-A_1x04_P2.50mm_Vertical` | KiCad stock, renamed |
| `Conn_JST_XH_1x03` | 3 | `JST_XH_B3B-XH-A_1x03_P2.50mm_Vertical` | KiCad stock, renamed |

The three connectors are `Connector_Generic:Conn_01x0N` renamed for clarity, each pre-assigned to its
JST-XH size: **1x06 = GPS** (M10-25Q on a cable), **1x04 = pod tether**, **1x03 = CAN stub**.

⚠ **Confirm the GPS connector pin count and order against your actual module.** 6-pin assumes
VCC/GND/TX/RX + SDA/SCL for the onboard QMC5883L compass. Changing size is a footprint swap only —
3/4/5/6/7-pin JST-XH are all in stock KiCad.

Also present, not targeted by any symbol: `D_SOD-123` (schottky), plus two alternates below.

## Read these before laying out

**`BMP390` is a BREAKOUT BOARD, not the bare chip.** 8 through-hole pads on 2.54 mm pitch —
VIN · 3V0 · GND · SCL · SDO · SDA · CS · INT — body about 23.5 × 14 mm. SnapEDA labels its
Description "10-WFLGA", which is the *chip's* package and is misleading. **This part is not on the
stencil/hot-air list** that `V3_PCB_SESSION_CONTEXT.md` puts it on. If you switch to direct-solder
you need the bare **BMP390L** (the long-availability version, the one actually stocked) and a land
pattern from `bst-bmp390l-ds001.pdf` — nothing here covers the LGA-10.

**`INA226` — do not place.** It exists only because `INA228` inherits from it via `extends`;
deleting it breaks the INA228. INA226 is 36 V common-mode max, out of spec for the 63 V drive
domain — the documented reason V3 moved to the INA228.

**`ADXL375` pinout is derived, not read from the datasheet.** Built from KiCad's reviewed
`Sensor_Motion:ADXL343` (same 3×5×1 mm 14-lead LGA family). Analog Devices and Adafruit both state
the ADXL375 shares the ADXL345's silicon and LGA footprint. **Verify all 14 pins against the ADXL375
datasheet before fab.**

**`BNO085` — strap the interface pins deliberately.** V2 lost a long debugging arc to floating
MOSI/ADDR, CS, PS0 and PS1 on a BNO085 module: reads worked, the address ACKed, and every payload
write was refused. PS1=0/PS0=0 selects I²C; ADDR to GND gives 0x4A. Also verify pin 1 / orientation
against the datasheet.

**`BH1750FVI-TR` needs a clear optical path.** It is an ambient light sensor in a bare WSOF-6 — it
cannot be buried under an enclosure or conformal coating and still mean anything.

**INA228 package variant.** The footprint is `HVSSOP-10-1EP` (15 pads: 10 pins + split thermal pad).
Confirm the part you order actually has the exposed pad; if it is a bare VSSOP-10, swap the footprint.

## Two parts have alternate footprints

**XIAO ESP32-S3** — the symbol targets SnapEDA's `MODULE_XIAO_ESP32_S3` (14 THT pads, 2.54 mm, matched
to the symbol's own numbering). `SeeedStudio_XIAO_ESP32S3` from fabcloud is also present: 39 pads,
**dual-mount** (a THT and an SMD pad per pin), so it supports surface-mounting the module flush as
well as a header. Switch to it if you want the flush option — the extra pads share nets with their
THT twins.

**BNO085** — the symbol targets KiCad's KLC-reviewed `LGA-28_5.2x3.8mm_P0.5mm`. SnapEDA's `IC_BNO085`
is also present and was verified equivalent: identical topology (LEFT 2–5, RIGHT 16–19, TOP 1/28–20,
BOTTOM 6–15), identical numbering, same pin-1 position, same 0.5 mm pitch. KiCad's pads are about
0.1 mm longer, giving more fillet to form and inspect under hot air, which is why it is the default.

## Provenance and licensing

| Item | Source | License |
|---|---|---|
| `BNO085`, `BMP390`, `BH1750FVI-TR`, `XIAO_ESP32_S3` symbols; `IC_BNO085`, `BMP390`, `XDCR_BH1750FVI-TR`, `MODULE_XIAO_ESP32_S3` footprints; both STEP models | SnapEDA exports (user-supplied) | per SnapEDA terms |
| `Teensy4.1` symbol | [XenGi/teensy_library](https://github.com/XenGi/teensy_library) | MIT (© 2015 Ricardo Band) |
| `Teensy41` footprint | [XenGi/teensy.pretty](https://github.com/XenGi/teensy.pretty) | MIT (© 2015 Ricardo Band) |
| `SeeedStudio_XIAO_ESP32S3` footprint | `gitlab.fabcloud.org/ricardo.marques/kicad` | **not stated** — check before redistributing |
| `TJA1051T`, `TCA9548APWR`, `INA228`, `INA226`, `SHT4x` symbols + 8 footprints | KiCad 10.0.5 stock libraries | CC-BY-SA-4.0 + KiCad library exception |
| `ADXL375` symbol | derived from KiCad `Sensor_Motion:ADXL343` | CC-BY-SA-4.0 + KiCad library exception |

KiCad's library exception permits use in a design without licensing the design under CC-BY-SA. The
copied library files themselves remain under their original terms.

## 3D models

`IC_BNO085` and `XDCR_BH1750FVI-TR` point at `${KIPRJMOD}/lib/dreams_v3.3dshapes/`; both STEP files
are present. The nine stock footprints use `${KICAD10_3DMODEL_DIR}` and resolve from the install.

Two were repaired: the fabcloud XIAO footprint referenced a **Seeed XIAO-nRF52840** model — the wrong
module, complete with a 180° rotation tuned for it — and that reference was removed, since a wrong
model silently misleads mechanical fit checks. `Teensy41` pointed at an undefined `${KICAD_USER_DIR}`
and was retargeted to `${KIPRJMOD}/lib/dreams_v3.3dshapes/Teensy_4.1_Assembly.STEP`; drop XenGi's
19 MB STEP there if you want it. `BMP390`, `MODULE_XIAO_ESP32_S3` and `SeeedStudio_XIAO_ESP32S3` have
no model — SnapEDA did not ship one for those.

## Nothing left to source

The **M10-25Q GPS** no longer needs a module footprint — it lands on a **JST-XH connector**
(`Conn_JST_XH_1x06` / `J1`) and connects by cable, so the parts doc's "measure it by hand once in
hand" item is closed.

Two open items are verifications, not downloads:

1. **ADXL375 pinout** — check all 14 pins against the datasheet (symbol is derived from ADXL343).
2. **INA228 package** — confirm the exposed thermal pad, or swap to a bare VSSOP-10.

Plus the GPS connector pin count noted above.
