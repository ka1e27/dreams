# D.R.E.A.M.S — Battery Architecture

> **Carried onto the V3 branch for its numbers.** This describes the **V2** boat. Any
> `pi5/`, `firmware/` or other code path it names is on `main`, not here. Re-derive
> anything before using it in a V3 design — see [`v3/V3_DESIGN_BRIEF.md`](v3/V3_DESIGN_BRIEF.md).

## Milwaukee M18 Three-Domain System

**Authoritative battery reference. Supersedes all previous battery documentation
(the old 2× 6S LiPo drive / 3S Li-ion electronics / 4S LiPo winch design).**

> **ADC note:** the battery ADCs are on the **Boat Pico (RP2040, GP26/27/28, 3.3 V max)**, not the
> Pi 5 — the Pi 5 has no ADC and talks to the Pico only over USB CDC. Dividers target ≤3.18 V at the
> Pico pin.

> **Implementation status (2026-06-30):** firmware (`firmware/boat-pico/sensors.py`), the Pi 5
> simulator, the dashboards, and the docs all reflect this architecture. The **KiCad schematic
> (`Boat_PCB/Boat_PCB.kicad_sch`) still carries the old resistor values** and must be updated in
> KiCad Tool to the divider values below.

---

## Battery Domains — Three Fully Isolated Systems

| Domain | Pack count | Configuration | Voltage (nom / max / cutoff) | Load |
|---|---|---|---|---|
| DRIVE (test bench) | 2× M18 in **parallel** | Parallel | 18 V / 21 V / 15 V | Both drive ESCs + twin 2814 motors |
| ELECTRONICS | 1× M18 standalone | Single pack | 18 V / 21 V / 15 V | Pi · GPS · compass · radio · camera |
| WINCH | 1× M18 standalone | Single pack | 18 V / 21 V / 15 V | Winch ESC + 2006 motor |

> **Drive rail — test bench (2× M18 parallel).** Parallel packs share **one pack's
> voltage** (18 V nom / 21 V max) with **double the current capacity and runtime** —
> it is *not* a voltage boost. Note this is **below 6S LiPo (22 V)**: the 2814 motors
> rated ~1330 W on 6S will make proportionally less power here (lower voltage → lower
> max RPM), so expect roughly 700–1000 W/motor depending on the prop. All three domains
> are now the same single-M18 voltage. Earlier drive variants were 3× series (54 V,
> dual-hull) and 2× series (36 V, first test bench) — both superseded on this bench.

**Critical: three completely isolated domains. No shared ground between domains except the star
point on the logic PCB.**

---

## Voltage Dividers

One ADC channel per domain on the Boat Pico. Dividers target ≤3.18 V at full charge, under the
RP2040's 3.3 V limit.

| Ref | Domain | R_high | R_low | Reconstruct × | ADC pin | Full-charge V at pin |
|---|---|---|---|---|---|---|
| R_H1, R_L1 | Drive (2× parallel) | 56 kΩ | 10 kΩ | 6.6 | GP26 | 21 V → 3.18 V |
| R_H2, R_L2 | Electronics | 56 kΩ | 10 kΩ | 6.6 | GP27 | 21 V → 3.18 V |
| R_H3, R_L3 | Winch | 56 kΩ | 10 kΩ | 6.6 | GP28 | 21 V → 3.18 V |

Reconstruct × = (R_high + R_low) / R_low. Firmware multiplies the measured pin voltage by this to
recover the pack voltage (`INV_P_RATIO = INV_E_RATIO = INV_W_RATIO = 6.6` in `sensors.py`).

> **All three domains use the same 56k/10k divider** (confirmed fitted on the physical board,
> 2026-07-28) — one ratio, ×6.6, for every rail. `INV_P_RATIO` was **14.0 → 6.6** on 2026-07-28: it
> had been left at ×14 for a 130k/10k drive divider that isn't what's populated, and at ×14 a full
> 21 V pack reported **16.4 V** — under `P_WARN` (17.0) and a hair over `P_CRIT` (16.0), so a fully
> charged boat would trip return-to-home. If you ever refit a 130k/10k drive divider, set
> `INV_P_RATIO` back to 14.0 in the same commit.
>
> ⚠ `Boat_PCB.kicad_sch` still lists the pre-M18 values (drive 220k/13k, elec 100k/30k, winch
> 100k/18k), so a netlist export contradicts this table. **The board and firmware are right; the
> schematic is stale** and needs updating in KiCad. 13 k / 30 k / 18 k aren't in the on-hand resistor
> kit either.

**PCB component notes:** all resistors through-hole axial DIN0207, 1 % tolerance, 0.25 W. Add a 1 kΩ
series resistor and a 100 nF ceramic filter cap on every ADC input line.

> The elec/winch 56k/10k pair sits at 3.18 V full — only ~0.12 V under the 3.3 V ADC ceiling. This
> matches the spec as delivered; if a bench-measured M18 reads above ~20.9 V off the charger, bump
> R_high to 68 kΩ (→2.69 V full) for margin.

---

## Voltage Thresholds

Mirrored in `firmware/boat-pico/sensors.py` (drive = `P_*`, elec = `E_*`, winch = `W_*`) and, for
reference only, in `pi5/config.yaml` under `battery:`.

```
DRIVE  (2× M18 parallel): full 21.0  nominal 18.0  warn 17.0  critical 16.0 (→ RTH)   cutoff 15.0 (→ ESTOP)
ELEC   (1× M18):          full 21.0  nominal 18.0  warn 17.0  critical 16.0 (→ alert) cutoff 15.0 (→ shutdown)
WINCH  (1× M18):          full 21.0  nominal 18.0  warn 17.0  critical 16.0 (→ disable) cutoff 15.0 (→ kill)
```

All three domains are now the same single-M18 thresholds. **This threshold change is the one edit the
parallel swap *requires*** — on the old 42 V (2× series) thresholds a full 21 V parallel pack reads as
"empty" and ESTOPs on boot.

Percentage is `100 × (v − cutoff) / (full − cutoff)`, clamped 0–100.

---

## Fusing Architecture

```
DRIVE:  2× M18 parallel ─[100A ANL]─► PDB ─┬─[80A ANL]─► ESC port  (2814 motor)
                                            ├─[80A ANL]─► ESC stbd  (2814 motor)
                                            └─[80A ANL]─► tow-ESC stub (unpopulated)
ELEC:   1× M18 ─[15A blade]─► logic PCB ─► 5V UBEC → Pi 5;  12V boost → GPS · radio · sensors
WINCH:  1× M18 ─[20A blade]─► MOSFET kill ─► winch ESC ─► 2006 motor
```

> **Drive current budget (2× M18 parallel + twin 2814).** The 2814 motors can pull ~1330 W each on
> 6S — at 18–21 V that's ~63–74 A **per motor** if the VESC lets them, so two of them (~130–150 A)
> would exceed two parallel M18 packs' continuous output. **You must cap the VESC battery current per
> motor** (see below) so the pair stays within the pack. With each motor limited to ~45 A the drive
> node sees ≤ ~90 A continuous, hence the 100 A main / 80 A per-ESC ANL fuses (down from 200 A / 100 A;
> a smaller fuse actually protects the thinner parallel-pack wiring). Use High Output packs.

Per-pack overcurrent, short-circuit, and over-discharge are handled by each M18's REDLINK BMS — no
individual pack fuses required.

**Wire gauges:**

| Run | Gauge | Fuse |
|---|---|---|
| Each M18 → parallel node | 10 AWG | (BMS-protected; no pack fuse) |
| Drive parallel main | 8 AWG | 100 A ANL |
| Each ESC feed | 8 AWG | 80 A ANL |
| Electronics adapter | 18 AWG | 15 A blade |
| Winch adapter | 14 AWG | 20 A blade |

> Size each pack's lead for the pack's own share (~half the total), and the common node for the sum.
> Keep the two parallel leads the **same length/gauge** so the packs share current evenly.

---

## PDB Layout Zones

```
DRIVE INPUT   : 3× M18 adapter inputs in series → series junction → 200A ANL → drive copper pour
DRIVE OUTPUT  : XT90 → ESC port (100A ANL) · XT90 → ESC stbd (100A ANL) · XT90 → tow stub (100A, unpop.)
MONITORING    : drive 56k/10k → GP26 · elec 56k/10k → GP27 · winch 56k/10k → GP28  (all ×6.6)
PCB SLOT      : separates drive and logic copper zones
```

**No midpoint tap** — the winch has its own dedicated M18 pack. Remove any `MIDPT_22V` copper pour
from the previous PDB design.

---

## M18 Adapter Notes

- Third-party M18 slide-rail adapter plates ($8–15 each, 5 needed), or 3D-printed from Printables/Thingiverse.
- Solder domain-appropriate wire gauge directly to the adapter pads; keep adapter leads under 150 mm.
- REDLINK BMS provides per-pack protection — no per-pack fuse needed.

---

## Drive current — AM32 ESCs (no VESC on this bench)

The test bench runs **two NeutronRC 70A-G071 ESCs** (STM32G071, **AM32** firmware, 70 A) off the Pico
(50 Hz servo PWM, GP2/GP3 — `firmware/boat-pico/escs.py`), not VESCs. AM32 is *configurable* firmware —
see **`docs/esc_setup.md`** for the full config (bidirectional mode, LVC, low-RPM/stall tuning). On
current, the key facts:

- **The pack, not the ESC, is the tighter limit.** Each ESC is 70 A continuous, but two at 70 A is 140 A
  — well over a 2× M18 parallel HO-6Ah pair's ~90 A continuous. So **prop the motors so the *combined*
  draw stays under ~90 A**; each ESC's 70 A only bounds a single motor.
- **Cap it in AM32 if you can.** Newer AM32 exposes a current-limit setting — if yours does, set
  ~45 A/motor as a hard cap; otherwise the prop choice is the limit. Set the AM32 LVC for a **5S M18**
  (~3.0 V/cell ≈ 15 V), not a 6S setting. (These ESCs also output current telemetry, not wired to the
  Pico today.)
- **The pack BMS + ANL fuses are the backstop**, not a current controller: the M18 REDLINK BMS trips on
  its own overcurrent, and the **80 A per-ESC** ANL protects each 70 A-continuous ESC feed while the
  **100 A main** ANL + BMS protect the parallel pack. Use High Output packs (HO 6Ah+) — an XC pack pair
  can't feed two 2814s.
- The 2814s only reach ~1330 W at 6S; at 18–21 V they top out lower (more runtime, not more power).

> ⚠ **Reverse:** the navigator commands *negative* throttle to pivot in place and to bear away during
> avoidance. AM32 supports it, but you must **enable Bi-directional mode** in the configurator (1.0 ms
> reverse / 1.5 ms neutral / 2.0 ms forward). With it off the ESC is forward-only and reverse pulses just
> idle — the boat can't pivot or back away. Verify on the bench before first spin-up. See `docs/esc_setup.md`.

**Different-Kv motors.** The two 2814s may spin at different RPM for the same pulse. On the PWM path there
is no per-motor ERPM cap, so correct it in software: the Pi-side feed-forward trim
`navigation.motor_gain_left/right` (`config.yaml` — lower the faster motor until it tracks straight at
equal command), the firmware's `COMP_L/COMP_R` in `motor_control.py`, and the closed-loop heading control.

---

## Runtime Estimates

| Pack type | Drive (survey) | Drive (planing) | Electronics |
|---|---|---|---|
| 3× HO 12Ah drive | ~6.5 h | ~19 min | — |
| 3× HO 6Ah drive | ~3.2 h | ~10 min | — |
| 1× XC 5Ah elec | — | — | ~18 h |
| 1× HO 6Ah winch | — | — | ~4 h continuous winch |

---

## What Changed from the Previous Architecture

| Item | Previous | Now |
|---|---|---|
| Drive battery | 2× 6S LiPo in series (12S, 44.4 V nom) | 3× M18 in series (54 V nom) |
| Electronics battery | 3S Li-ion | 1× M18 standalone |
| Winch battery | 4S LiPo / 6S midpoint tap (ambiguous) | 1× M18 standalone |
| Midpoint tap | Yes — PCB copper pour | Removed |
| Drive divider | 3.3k/47k (firmware) vs 220k/13k (schematic) | 56k/10k → GP26 |
| Elec divider | 15k/100k (firmware) vs 100k/30k (schematic) | 56k/10k → GP27 |
| Winch divider | 100k/18k (schematic, unread in firmware) | 56k/10k → GP28 |
| Balance / pack-swap tracking | Required | Not needed — isolated BMS packs |

---

*June 2026 — three-domain M18 architecture. Supersedes all previous battery documentation.*
*July 2026 — test-bench drive rail switched to 2× M18 **parallel** (18 V) for the twin 2814 motors:
single-M18 thresholds, VESC current capped per motor, per-motor trim for Kv mismatch. Firmware
(`sensors.py`), `config.yaml`, and the simulator updated.*
*2026-07-28 — all three dividers confirmed fitted as 56k/10k (×6.6) on the physical board;
`INV_P_RATIO` corrected 14.0 → 6.6. The KiCad schematic still holds pre-M18 values and is the stale
copy of record.*
