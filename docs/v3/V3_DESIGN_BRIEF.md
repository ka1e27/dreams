# V3 design brief — carry-forward for the redesign

Everything the V3 redesign needs to start from, distilled from the 18-section review log that
tracked the first attempt. That log is **not** in the working tree any more. If you need the
blow-by-blow, run `git show v2-final:docs/v3/v3_review_2026-08-05.md`.

> **The fence still applies.** V2, the RP2040 boat archived at tag `v2-final`, disagrees with V3
> on MCU, drive and sensors *by design*. Never reconcile V3 against the V2 pin map, protocol docs
> or firmware. Copying a V2 value into V3 without re-deriving it is the specific error this
> separation exists to catch. See [`README.md`](README.md).

---

## 1. Locked decisions

| | V3 | Why |
|---|---|---|
| Boat MCU | **Two Raspberry Pi Pico 2s** (RP2350), C++. Pico A (U1) runs control, Pico B (U14) the sensors | Replaced the Teensy 4.1 in rev E (2026-10-13), after V3.1 tried one Pico. Two give 52 GPIO and 6 ADC. The Pi talks to Pico A over a UART on its GPIO header and can reset either Pico (Q3, Q4); Pico B reaches the Pi over the UART link that joins the two. USB cables are optional (to flash a Pico, or to run its link over USB instead), so the Pi's USB ports can stay free for cameras and the modem |
| Drive | **VESCs as CAN nodes** (IDs 1, 2) via **TJA1051T/3** | No MCP2515: CAN runs on Pico A's PIO (can2040). The /3 part keeps the logic side at 3.3 V |
| Drive pack | **12S LiPo**, voltage sense only | No shunt, no current sensing on this rail (see §3) |
| Pod | **Seeed XIAO ESP32-S3** on its **own board** | Moved off the carrier; tether is one **RS-485 pair** + 2× power. The link runs half duplex through a ±70 V fault-protected THVD2410 (U13). The power pair carries the **electronics pack voltage** (15–21 V), and the pod makes its own 5 V |
| Sensors | SHT45 ×2, BNO085, BMP390, ADXL375, BH1750, 2× INA228 | All behind a **TCA9548A** mux on Pico B's I²C0 |
| Power | **3 isolated domains** — drive / electronics / winch | Per-pack BMS protection; fusing is off-board |
| Winch kill | **High-side P-FET, fail-safe OFF** | Gate pulled to source by R34; de-energised = open |
| Passives | **THT** | Reworkability, by builder preference |
| Stackup | 4-layer **JLC04161H-7628**, 1.6 mm, ENIG | **In1 = GND, In2 = PWR** |

**Why In1 is ground:** the L1→L2 prepreg is only 0.21 mm, so F.Cu sits tight against In1. That is
the whole reason for the layer order — it only pays off if In1 stays unbroken (see §4).

⚠ Inner layers are **0.5 oz** at JLCPCB, outer are 1 oz. An inner trace carries roughly half what
an outer trace of the same width does. This caught the first attempt more than once.

---

## 2. Current budget

Sizing comes from IPC-2221: `A = (I / (k·ΔT^0.44))^(1/0.725)`, `W = A / (1.378 × oz)`,
k = 0.048 external, **0.024 internal**.

| Rail | Current | Source of the number |
|---|---|---|
| Winch | **20 A** | 20 A blade fuse, 14 AWG adapter (V2's `docs/battery_architecture.md`, at `v2-final`) |
| Electronics pack | 15 A fuse; real load ≈ **2 A** | Pololu D36V50F5 buck + A4988 stepper |
| `+5V` rail | **5.5 A** | The D36V50F5's ceiling |
| `+3V3` rail | **0.3 A** | Pico A's 3V3 pin (the RT6150 on the Pico, shared with the RP2350 itself) |
| Pod branch (F1) | **0.40 A hold**, fed from `+VELEC` | Bel Fuse 0ZRE0040FF1A PTC. At pack voltage the pod draws ≈ 0.13 A, and the smaller part trips faster on a tether short. Since rev E the feed runs on In2: 0.8 mm along the top edge, ≈ 0.6 A at a 10 °C rise on 0.5 oz |
| LED branch (F2) | **1.25 A hold** | " |
| SBUS branch (F3) | **0.75 A hold** | Deliberately loose — the RC link is the manual override and must never nuisance-trip |
| Drive | 100 A main / 80 A per ESC | **Off-board**, ANL fuses |

Those PTC figures are **hold**, not trip. Size the copper to hold current.

**The 20 A winch path cannot be a track.** At 20 A on 1 oz outer copper:

| | ΔT |
|---|---|
| 2.5 mm track | ~276 °C |
| 4 mm track | 127 °C |
| 8 mm pour, one outer layer | 41 °C |
| **8 mm pour, both outer layers, via-stitched** | **13 °C** |

Budget 20+ stitching vias at 1.0/0.6 (~1 A each). Keep the winch **return** off the 0.5 oz inner
plane too — take it J14 GND → J16 GND on the outer pours.

---

## 3. Part choices worth preserving

- **INA228, not INA226.** A correctness fix, not an upgrade: INA226 is rated to 36 V common-mode
  and the drive domain exceeds that. Two are fitted, on electronics and winch. The drive one went
  out with the drive shunt chain (next point).
- **Drive rail is voltage-only.** No shunt, no INA228 on 12S. An INA228 with nothing across
  Vin+/Vin− measures nothing, so the whole chain came out — 7 components and a 4-wire harness.
  The 12S rail has exactly one sense path: the ADC divider.
- **Shunts:** electronics **10 mΩ** (R32), winch **2 mΩ** (R33). Both 4-terminal — Kelvin sense
  pads tap the *small* pads, never the current pads.
- **SHT45, not SHT41.** V2 fed an SHT41 5 V against a 3.6 V absolute max. Do not repeat that.
- **Pack voltages.** The electronics and winch packs are read by their INA228s: VBUS is tied to the
  load side of each shunt, so the chip reports voltage and current at 20 bits. The 68k/10k ADC
  dividers that duplicated those readings came out in the 2026-09-28 parts review, along with their
  1 k series resistors and filter caps. The 12S rail keeps its divider, 220k/13k, 2.81 V at 50.4 V,
  with C4 at the ADC pin. Size any new divider the same way, for the worst case at 1 %: V2's
  56k/10k gave 3.46 V at 5 % worst case on a 21 V pack, over a 3.3 V ADC rail.
- **Series resistors on every net that leaves the board.** 330 Ω on WS2812 data, 1 k on each hull
  leak probe, 1 k on SBUS. Series, *not* a divider — a divider sized for a 5 V receiver drops a
  3.3 V receiver below V<sub>IH</sub>.
- **Specify passives properly in Value:** `100nF 50V X7R`, `22pF 50V C0G`, `1 %`. A generic disc
  could be Y5V and lose 80 % of its capacitance over temperature and DC bias.

**Library.** `Boat_PCB/Boat_PCB_V3/lib/` already holds a built `dreams_v3` symbol library, 34
footprints and the 3D models. Reuse it. Most parts come from stock KiCad libraries; the ones that
needed downloading were **TCA9548A, BNO085 and INA228**.

---

## 4. Mistakes not to repeat

Each of these was found the hard way on the first attempt.

**Pour the 20 A path, don't track it.** The first routing pass ignored the requirement above and
ran `SH_WINCH_P` as a single 2.5 mm track. See §2 for the numbers.

**Thermal relief throttles high-current pads.** KiCad's default is 0.5 mm spokes on every zone. Four
of those is ~2 mm of copper — fine for a signal pad, catastrophic for 20 A. Set high-current pads to
**solid** individually; leave thermal relief on the rest or the board becomes unsolderable by hand.

**Q1's pin order dictates the floorplan.** A TO-220 P-FET is **G-D-S**, so with the pack entering
from the left, `+VWINCH` has to cross the drain's path to reach the source on the right. Place Q1
rotated (S-D-G) so the source faces the incoming pour, or put the output connector beyond the
source. Getting this wrong makes the drain pour unroutable on the outer layers, and the bottom side
is unavailable because it carries the winch ground return.

**Keep signals off the In1 ground plane.** The first attempt routed 8 nets (235 mm, one of them
110 mm) through it, slotting the return path for everything on F.Cu above. Once the outer layers are
dense these cannot be moved — it has to be right the first time.

**Decoupling only works within ~3 mm.** Caps were added specifically to fix "no decoupling on any
IC" and then placed 6–20 mm from the pins they serve, which gives most of the benefit back.

**ADC filter caps belong at the MCU pin.** They were placed with the divider resistors at the board
edge, 44–53 mm from the Teensy's ADC pins. Everything coupled onto that run is unfiltered and the
sampler has no local charge reservoir.

**Bulk caps at the Pi must clear the Pi.** C30/C31 belong at `J12`'s 5 V pins — but the Pi sits
8–11 mm above on its socket, and a D10 radial electrolytic is ~12–16 mm tall. Choose a low-profile
or SMD bulk cap at design time, not at layout time.

**Netclass track widths are NOT DRC constraints.** They are only defaults for newly drawn tracks.
Under-width power routing is invisible unless you write an explicit `track_width` rule in the
`.kicad_dru`. Judge a power net by tracing the widest path from source to load, not by eyeballing.

**Give Kelvin and divider taps their own nets.** A shunt's sense taps are electrically the same node
as the power path, so a width rule scoped by netclass fires on taps that are *meant* to be thin —
~21 of 29 errors were false on the first attempt. Name them (`WINCH_SH_SENSE_P/N`, `WINCH_DIV_TAP`)
so the rule stays strict and stays actionable.

**Route CAN as an actual pair.** CANH and CANL ended up on different layers for most of their run,
one leg crossing the power plane, with a 35 mm length mismatch.

**Other traps carried over from V2:** no I²C pull-ups on any bus; a BNO085 with floating strap pins;
a pod schottky fitted backwards; the XIAO's 3V3 regulator output tied to the carrier's +3V3. All
were found and fixed once — check them again.

⚠ **USB-C backfeed is still unsolved.** The Pololu buck is not reverse-current tolerant and the
Pi's header 5 V pins become outputs whenever USB-C is attached. A series schottky is not viable
(≈0.45 V and >1 W at Pi currents, and the Pi 5 wants ≥4.75 V). The real fix is an ideal-diode /
ORing controller. Until then it is a **build rule: power the Pi from the buck, or from USB-C, never
both.**

---

## 5. The pod (test phase)

Schematic and rev B layout: `Boat_PCB/Pod_PCB_V3/`. It shares the carrier's `lib/`. The pod
rides the winch tether and profiles the water column to about 20 m. This round is for testing in
freshwater, so it uses cheap hobby sensors rather than lab-grade ones.

**Board (rev B, 2026-09-29).** 48 × 63 mm, 2 layers, GND poured on both sides. It's built for hand
assembly. The resistors lie flat on the 10.16 mm footprint the carrier uses, the caps are 5 mm discs,
and the XIAO and the Pololu buck sit on headers. No parts sit under either module, so each can be
soldered straight down or socketed.

- **No connectors.** Every off-board wire solders straight into a 1.0 mm pad on a 2.54 mm pitch
  (22–28 AWG). Cut the DFRobot Gravity cables and solder them in.
- **Square pad = GND on every group.** The front is too dense to label every pad, so the pin legend
  is on the back silkscreen, which is also the side you solder the wires on.
- **Where things are.** Tether pads J1 on the top edge. The XIAO's USB-C faces the left edge. The
  right edge, top to bottom: AUX, PRESS, DO, TDS, pH (J10, J6, J4, J3, J2). The bottom edge: TURB,
  TEMP, LEAK, BOTTOM (J5, J7, J8, J9). The AIN assignment below is unchanged.
- **Rev B is a re-placement of rev A, not a redesign.** Same 54 footprints, outline and netlist.
  The right-edge groups sit on one 8.47 mm pitch, the bottom groups on equal gaps, and the twelve
  upright resistors and caps stand in one row on a 3.4 mm pitch. The AP2112's caps are now within
  3 mm of its pins (rev A had them about 10 mm away), and the back legend is on a grid, with a
  label at every pad.
- **No test points.** Probe GND and 5V on any sensor pad group, 3V3 on TEMP or AUX, and the tether
  voltage on J1.

**Bench bring-up.** USB powers only the XIAO: D3 stops USB from back-feeding the 5 V rail. The
sensors, ADC and transceiver need 12–21 V on J1. Don't exceed 24 V, the SMBJ24A's standoff voltage.

**Tether and power.**
- **Power:** the carrier's J2 sends the electronics pack (15–21 V) through F1 (0.40 A PTC). At pack
  voltage the pod draws about 0.1 A.
- **Pod input:** a Schottky and an SMBJ24A protect it, then a Pololu D36V6F5 buck makes 5 V. An
  AP2112K-3.3 feeds the ADC, transceiver and pull-ups. The XIAO keeps its own 3V3; the two 3.3 V
  rails are never tied.
- **Link:** half-duplex RS-485 through a THVD2410 at each end, 120 Ω at each end, and a 24 V TVS at
  each connector.

**Sensors.** Prices are as listed on 2026-09-25.

| Measure | Part | Price | Read by |
|---|---|---|---|
| pH | DFRobot SEN0161-V2 | $39.50 | ADS1115 AIN0 |
| Conductivity | DFRobot SEN0244 TDS, 0–1000 ppm, through a DFR0504 isolator ($19.90) | $11.80 | ADS1115 AIN1 |
| Dissolved O₂ | DFRobot SEN0237-A: connector fitted, sensor bought later | $169 | ADS1115 AIN2 |
| Depth | DFRobot SEN0257, 0–1 MPa, divided 4.5 → 3.0 V | $15.90 | ADS1115 AIN3 |
| Turbidity | DFRobot SEN0189, relative only, divided | $9.90 | XIAO ADC (D0) |
| Temperature | DS18B20 waterproof probe | $6.90 | 1-Wire (D1) |

**Traps.**
- The conductivity sensor's AC excitation corrupts the pH reading unless it's isolated. DFRobot says
  so explicitly.
- The SEN0189's top isn't waterproof, and DFRobot labels the SEN0257 "non-immersible". Both mount
  through the end cap with only the tip or port wet.
- None of the pH, TDS and temperature probes publish a depth rating. Test shallow first.
- The galvanic DO probe needs water flow, so it reads low when parked at depth. It also needs fresh
  electrolyte monthly.
- Lab-grade upgrades, if the test data justify them: Atlas EZO pH/EC/DO/RTD on isolated carriers,
  the Renke RS-ZD-N01 turbidity sensor ($116, RS-485, 0–50 NTU range, 20 m), and a Blue Robotics
  Bar30 for depth ($90).

---

## 6. Where the rest lives

| | |
|---|---|
| [`README.md`](README.md) | The V2/V3 fence — read before touching anything |
| [`V3_PCB_SESSION_CONTEXT.md`](V3_PCB_SESSION_CONTEXT.md) | Original design intent and the open questions |
| [`DREAMS_V3_parts_footprints.md`](DREAMS_V3_parts_footprints.md) | BOM with sourcing links |
| `v2-final:docs/battery_architecture.md` | V2's pack topology, fusing and M18 thresholds. These are V2 numbers, so re-derive them |
| `v2-final:docs/v3/v3_review_2026-08-05.md` | The full 18-section log this brief distils |
| tag `v2-final` | Everything V2: the Pi stack, the firmware, the pin map, the old board |
