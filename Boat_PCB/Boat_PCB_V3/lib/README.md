# `Boat_PCB_V3/lib` — project-local KiCad library

Self-contained symbol + footprint library for the V3 board, so a fresh clone resolves every part with
no per-machine library setup. Assembled 2026-08-04 against **KiCad 10.0.5**.

- `dreams_v3.kicad_sym` — **59 symbols**
- `dreams_v3.pretty/` — **59 footprints**
- `dreams_v3.3dshapes/` — 2 STEP models

The pod project (`../../Pod_PCB_V3/`) and the V3.1 starter carrier (`../../Boat_PCB_V3_1/`) use this
library too: their lib tables point here through `${KIPRJMOD}/../Boat_PCB_V3/lib/`.

## V3.1 starter carrier additions (2026-10-10)

- **Flattened from stock:**
  - symbols: `RaspberryPi_Pico` (from `MCU_Module`, footprint retargeted, AGND made passive so pin 3
    is the only GND power output), `SW_Push` and `Fuse`;
  - footprints: `RaspberryPi_Pico_Common_THT`, `JST_SH_SM04B-SRSS-TB` (Qwiic), 1×3 and 2×7 pin
    headers, `SW_PUSH_6mm` and `Fuse_Littelfuse_372_D8.50mm` (TR5).
- **New footprint, `RaspberryPi_Pico_Socketed_THT`:** the common THT footprint with the courtyard
  cut down to the two 1×20 socket rows and the USB end, so flat parts can sit under a socketed Pico.
  Keep them under about 7 mm tall (8.5 mm sockets). The Pico W antenna keep-out is unchanged. The
  micro-USB receptacle outline is on F.Fab only, so pads can sit under it. Its 3D view shows the stock
  8.5 mm pin sockets with a Pico H seated in them.
- **New symbols:**
  - `Conn_Qwiic_1x04`: 1 GND, 2 3V3, 3 SDA, 4 SCL, the SparkFun / Adafruit order.
  - `Conn_RC_1x04`: 1 GND, 2 5V, 3 RX into the board, 4 TX out of it.
  - `Conn_ESC_1x03`: 1 signal, 2 not connected so an ESC's BEC can't back-feed, 3 GND.
  - `Conn_PicoLink_2x07`: the 2nd-Pico header.
  - `Conn_GY-SHT41_1x04`: the GY-SHT41-D SHT41 module (Teyleten Robot): 1 VIN, 2 GND, 3 SCL, 4 SDA.
- **New footprint, `SHT41_Module_GY-SHT41-D_1x04_P2.54mm`:** the 13.2 × 10.4 mm module on its 4-pin header,
  pins down one short edge. The V3.1 board puts it on the bottom side, hanging sensor-side down. The hole
  and sensor marks on the fab layer are estimates from product photos.
- `Pololu_D36V50F5`'s pin-name texts are keep-upright. At 270° that flips them onto the pads, so the
  V3.1 board turns keep-upright off on its own copy; the library is unchanged.

The board is **fully placed and routed**: 126 footprints on a 130.6 × 101.5 mm 4-layer board (rev D,
2026-09-28).

See [`../../../docs/v3/V3_DESIGN_BRIEF.md`](../../../docs/v3/V3_DESIGN_BRIEF.md) for the decisions,
the current budget and the layout traps found the hard way on the first attempt.

⚠ **The contents table below is as-assembled on 2026-08-04 and has drifted** (the counts above are
current). The library has since
lost the `TJA1051T` and `Conn_JST_XH_*` symbols (they resolve from stock KiCad now) and gained
`Crystal`, `MountingHole` and `Polyfuse`. The per-part warnings under "Read these before laying
out" are all still current — those are the part worth keeping.

## Rev C changes (2026-09-24)

- **`Pololu_D36V50F5` was redrawn** from Pololu's drill guide (`reg24d-drill.dxf`) and its labelled
  top-view photo. The old footprint had the lone third M2 hole at the VOUT end (Pololu puts it at the
  EN/PG end) and its header rows 0.48 mm off the hole line. Mounted the natural way, with all three
  screws, that reversed the pinout end-for-end: VIN and VRP landed on GND and the pack drove backwards
  through the regulator. The footprint is a top view; on the board it is flipped onto B.Cu for an
  underside module fitted components-away.
- **`Conn_XT60_M18` pin numbering follows the XT60 convention:** pin 1 is the notched (chamfered)
  end, which is negative, and pin 2 is the flat end, which is positive. The molded + sits at the flat
  end. The old symbol had + on pin 1, which put + on the notched end of KiCad's AMASS footprints.
  J16, the switched winch output, is now an XT60-F (female).
- **Added from the stock KiCad libraries:**
  - symbols: `D_Zener`, `LED`, `TestPoint`, `Jumper_2_Open`, `74AHCT1G125` (flattened from
    `74LVC1G125`), and a `D_Dual_CommonAnode_KKA` with pins 1/2 as cathodes and 3 as the anode
    (the PESD5V0S2BT pinout);
  - footprints: `D_SMB`, `D_DO-35`, `LED_D3.0mm`, `SOT-23-5`, a vertical DIN0207 resistor (no longer
    used: rev D lays every resistor flat), `CP_Radial_D8.0mm`, `JST_VH_B2P-VH`, a 1×2 pin header,
    `AMASS_XT60-F`, and a Keystone test point.
- **Pod tether on RS-485 (2026-09-25):**
  - `THVD2410D` was flattened from stock `Interface_UART:LTC2850xS8`, which has the same D-package
    pinout: 1 R, 2 ~RE, 3 DE, 4 D, 5 GND, 6 A, 7 B, 8 VCC.
  - `NUP2105L` (24 V dual bidirectional TVS) comes from stock `Power_Protection`, retargeted to
    `dreams_v3:SOT-23`.
  - `Conn_PodTether_1x04` pins are now GND / VPACK / A / B. Pin 2 carries the pack voltage.
- **Pod parts (2026-09-25):**
  - Flattened from stock: `ADS1115IDGS` (the existing `MSOP-10_3x3mm_P0.5mm` footprint) and
    `AP2112K-3.3`.
  - New: `Pololu_D36V6F5`, a symbol plus a footprint. The outline is approximate, since Pololu gives
    the size (0.4 × 0.5 in) but no drill drawing; check it against a module before the pod layout.
  - `Conn_Gravity_1x03`: the DFRobot sensor cable. Pin order is GND, VCC, signal; **check it against
    the cable before soldering.**
  - `Conn_DS18B20_1x03`, `Conn_Aux_1x03` and `Conn_Switch_1x02`.
  - Footprint `JST_PH_B3B-PH-K_1x03_P2.00mm_Vertical` (no longer used: the pod went to wire pads).
- **Pod wire pads (2026-09-26):**
  - `SolderWire_1x02/1x03/1x04_P2.54mm_D1.0mm`: pads only, for wires soldered straight in (22-28 AWG).
    Pad 1 is square and is GND on every pod group. No 3D model, since there is no part.
  - `CP_Radial_D6.3mm_P2.50mm` from stock, for the pod's 47 µF 50 V input can.
  - `D_Schottky`'s description no longer mentions the old 5 V tether.
- **Silkscreen fixes, kept in the library so the board copies still match it:**
  - `Pololu_D36V50F5` pin labels are 1.0 mm / 0.15 mm, the board's minimum text size (they were 0.8 mm).
  - `RaspberryPi_5_GPIO_Socket_2x20`: the `PIN1` text moved to F.Fab, because it landed on neighbouring
    pads. The square pad 1 still marks pin 1.
  - `D_DO-35`: the silk `K` is gone. The cathode band marks polarity, and the letter collided with J14.

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
