# D.R.E.A.M.S — Battery Architecture

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
| DRIVE | 3× M18 in series | Series chain | 54 V / 63 V / 45 V | Both drive ESCs + motors |
| ELECTRONICS | 1× M18 standalone | Single pack | 18 V / 21 V / 15 V | Pi · GPS · compass · radio · camera |
| WINCH | 1× M18 standalone | Single pack | 18 V / 21 V / 15 V | Winch ESC + 2006 motor |

**Critical: three completely isolated domains. No shared ground between domains except the star
point on the logic PCB.**

---

## Voltage Dividers

One ADC channel per domain on the Boat Pico. Dividers target ≤3.18 V at full charge, under the
RP2040's 3.3 V limit.

| Ref | Domain | R_high | R_low | Reconstruct × | ADC pin | Full-charge V at pin |
|---|---|---|---|---|---|---|
| R_H1, R_L1 | Drive (3× series) | 200 kΩ | 10 kΩ | 21.0 | GP26 | 63 V → 3.00 V |
| R_H2, R_L2 | Electronics | 56 kΩ | 10 kΩ | 6.6 | GP27 | 21 V → 3.18 V |
| R_H3, R_L3 | Winch | 56 kΩ | 10 kΩ | 6.6 | GP28 | 21 V → 3.18 V |

Reconstruct × = (R_high + R_low) / R_low. Firmware multiplies the measured pin voltage by this to
recover the pack voltage (`INV_P_RATIO = 21.0`, `INV_E_RATIO = INV_W_RATIO = 6.6` in `sensors.py`).

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
DRIVE  (3× M18 series):  full 63.0  nominal 54.0  warn 51.0  critical 48.0 (→ RTH)  cutoff 45.0 (→ ESTOP)
ELEC   (1× M18):         full 21.0  nominal 18.0  warn 17.0  critical 16.0 (→ alert) cutoff 15.0 (→ shutdown)
WINCH  (1× M18):         full 21.0  nominal 18.0  warn 17.0  critical 16.0 (→ disable) cutoff 15.0 (→ kill)
```

Percentage is `100 × (v − cutoff) / (full − cutoff)`, clamped 0–100.

---

## Fusing Architecture

```
DRIVE:  3× M18 series ─[200A ANL]─► PDB ─┬─[100A ANL]─► ESC port
                                          ├─[100A ANL]─► ESC stbd
                                          └─[100A ANL]─► tow-ESC stub (unpopulated)
ELEC:   1× M18 ─[15A blade]─► logic PCB ─► 5V UBEC → Pi 5;  12V boost → GPS · radio · sensors
WINCH:  1× M18 ─[20A blade]─► MOSFET kill ─► winch ESC ─► 2006 motor
```

Per-pack overcurrent, short-circuit, and over-discharge are handled by each M18's REDLINK BMS — no
individual pack fuses required.

**Wire gauges:**

| Run | Gauge | Fuse |
|---|---|---|
| Drive series main | 6 AWG (testing) / 4 AWG (full perf) | 150 A / 200 A ANL |
| Each ESC feed | 8 AWG | 100 A ANL |
| Electronics adapter | 18 AWG | 15 A blade |
| Winch adapter | 14 AWG | 20 A blade |

---

## PDB Layout Zones

```
DRIVE INPUT   : 3× M18 adapter inputs in series → series junction → 200A ANL → drive copper pour
DRIVE OUTPUT  : XT90 → ESC port (100A ANL) · XT90 → ESC stbd (100A ANL) · XT90 → tow stub (100A, unpop.)
MONITORING    : drive 200k/10k → GP26 · elec 56k/10k → GP27 · winch 56k/10k → GP28
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

## VESC Current Limits by M18 Pack Type

Set in VESC Tool before first run; match to the weakest pack in the series chain.

```
XC 5Ah  : 20 A   (testing only)
HO 6Ah  : 45 A
HO 12Ah : 70 A
MAX     : 88 A   (full performance, proper LiPo only)
```

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
| Drive divider | 3.3k/47k (firmware) vs 220k/13k (schematic) | 200k/10k → GP26 |
| Elec divider | 15k/100k (firmware) vs 100k/30k (schematic) | 56k/10k → GP27 |
| Winch divider | 100k/18k (schematic, unread in firmware) | 56k/10k → GP28 |
| Balance / pack-swap tracking | Required | Not needed — isolated BMS packs |

---

*June 2026 — three-domain M18 architecture. Supersedes all previous battery documentation.*
