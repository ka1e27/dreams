# V3 design brief — carry-forward for the redesign

Everything the V3 redesign needs to start from, distilled from the 18-section review log that
tracked the first attempt. That log is **not** in the working tree any more; it is in git history
at `docs/v3/v3_review_2026-08-05.md` if you need the blow-by-blow.

> **The fence still applies.** The boat on the bench is **V2 / RP2040**. V3 disagrees with it on
> MCU, drive and sensors *by design*. Never reconcile V3 against the V2 pin map, protocol docs or
> firmware — copying a V2 value into V3 without re-deriving it is the specific error this
> separation exists to catch. Those documents are not on this branch; they are on `main`. See
> [`README.md`](README.md).

---

## 1. Locked decisions

| | V3 | Why |
|---|---|---|
| Boat MCU | **Teensy 4.1**, C++/Teensyduino | Pin count and the concurrency model; full rewrite from MicroPython |
| Drive | **VESCs as CAN nodes** (IDs 1, 2) via **TJA1051** | No MCP2515 — the Teensy has native CAN |
| Drive pack | **12S LiPo**, voltage sense only | No shunt, no current sensing on this rail (see §3) |
| Pod | **Seeed XIAO ESP32-S3** on its **own board** | Moved off the carrier; tether is 2× UART + 2× power |
| Sensors | SHT45 ×2, BNO085, BMP390, ADXL375, BH1750, 3× INA228 | All behind a **TCA9548A** mux on one Teensy I²C bus |
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
| Winch | **20 A** | 20 A blade fuse, 14 AWG adapter (`docs/battery_architecture.md`) |
| Electronics pack | 15 A fuse; real load ≈ **2 A** | Pololu D36V50F5 buck + A4988 stepper |
| `+5V` rail | **5.5 A** | The D36V50F5's ceiling |
| Pod branch (F1) | **0.75 A hold** | Bel Fuse 0ZRE PTC |
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
  and the drive domain exceeds that. Three of them, one per domain.
- **Drive rail is voltage-only.** No shunt, no INA228 on 12S. An INA228 with nothing across
  Vin+/Vin− measures nothing, so the whole chain came out — 7 components and a 4-wire harness.
  The 12S rail has exactly one sense path: the ADC divider.
- **Shunts:** electronics **10 mΩ** (R32), winch **2 mΩ** (R33). Both 4-terminal — Kelvin sense
  pads tap the *small* pads, never the current pads.
- **SHT45, not SHT41.** V2 fed an SHT41 5 V against a 3.6 V absolute max. Do not repeat that.
- **Dividers 68k/10k, not 56k/10k.** 56k/10k gives 3.18 V nominal at a 21 V pack but **3.46 V at
  5 % worst case — over a 3.3 V ADC rail.** 68k/10k gives 2.69 V nominal, 2.74 V at 1 % worst case,
  17 % headroom. Specify **1 %** parts.
- **Series resistors on every net that leaves the board.** 330 Ω on WS2812 data, 1 k on each hull
  leak probe, 1 k on SBUS. Series, *not* a divider — a divider sized for a 5 V receiver drops a
  3.3 V receiver below V<sub>IH</sub>.
- **Specify passives properly in Value:** `100nF 50V X7R`, `22pF 50V C0G`, `1 %`. A generic disc
  could be Y5V and lose 80 % of its capacitance over temperature and DC bias.

**Library.** `Boat_PCB/Boat_PCB_V3/lib/` already holds a built `dreams_v3` symbol library, 29
footprints and the 3D models — reuse it. Most parts come from stock KiCad libraries; the ones that
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

## 5. Where the rest lives

| | |
|---|---|
| [`README.md`](README.md) | The V2/V3 fence — read before touching anything |
| [`V3_PCB_SESSION_CONTEXT.md`](V3_PCB_SESSION_CONTEXT.md) | Original design intent and the open questions |
| [`DREAMS_V3_parts_footprints.md`](DREAMS_V3_parts_footprints.md) | BOM with sourcing links |
| [`../battery_architecture.md`](../battery_architecture.md) | Pack topology, fusing, thresholds |
| [`v3_review_2026-08-05.md`](v3_review_2026-08-05.md) | The full 18-section log this brief distils |
| `main` | Everything V2 — the Pi stack, the firmware, the pin map, the old board |
