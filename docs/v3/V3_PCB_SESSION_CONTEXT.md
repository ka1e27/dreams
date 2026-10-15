> **Planning record, stored verbatim.** This was written outside this repo during the August 2026
> V3 PCB-planning session, before the board was laid out. The text below the rule is unmodified. If
> it disagrees with [`V3_DESIGN_BRIEF.md`](V3_DESIGN_BRIEF.md) or the KiCad files, those win.
>
> It was written in the V2 era, so some names need translating:
>
> - `DREAMS_MASTER_CONTEXT.md` ("the master doc") is V2's `docs/PROJECT_CONTEXT.md`.
> - "Boat Pico", `firmware/boat-pico/*.py` and `vesc.py` are V2 code.
>
> All of that is archived at tag `v2-final`. For example, run
> `git show v2-final:docs/PROJECT_CONTEXT.md`. `DREAMS_V3_parts_footprints.md` sits beside this file.
>
> On its open items:
>
> - **The GPS footprint (3) is closed.** The module connects by cable to a JST-XH connector, J1.
> - **The pod tether voltage (4) is closed, and the pod plan below is superseded (2026-09-25).**
>   - The tether carries 15 V from the carrier's U15 (since rev F, 2026-10-14; it was the
>     electronics pack, 15–21 V, before), and the pod makes its own 5 V with a buck.
>   - The link is one RS-485 pair, not a raw UART.
>   - The sensor set is a DFRobot test-phase list.
>   - See [`V3_DESIGN_BRIEF.md`](V3_DESIGN_BRIEF.md) §5 and `Boat_PCB/Pod_PCB_V3/`.
> - **The BMP390 below came off in rev F (2026-10-14).** Its surface baseline for the pod's pressure depth isn't
>   needed: depth comes from the fish-finder sonar.
> - **The Teensy below is superseded (2026-10-13).** Rev E of the carrier runs two Raspberry Pi
>   Pico 2s instead: Pico A for control (CAN on the PIO, SBUS, winch, stepper, LED, leak, pack ADC),
>   Pico B for sensors (the I²C mux, GPS, the pod RS-485). So the Teensy concurrency model (1) no
>   longer applies; how each Pico uses its two cores is the firmware's first call now. The Pi talks
>   to Pico A over a UART on its header and can reset either Pico (Q3, Q4); Pico B reaches the Pi
>   through Pico A, so the Picos' USB cables are optional. Pin maps are in `CLAUDE.md`.

---

# D.R.E.A.M.S — V3 PCB Session Context
### For Claude Code — supplements `DREAMS_MASTER_CONTEXT.md`, does not replace it

> This file captures decisions made in a PCB-planning session that **are not yet reflected** in
> `DREAMS_MASTER_CONTEXT.md`. Where the two conflict, this file wins for anything V3-related —
> the master doc's Boat Pico / CAN / Pod sections describe the V2 (RP2040) architecture.
> Full BOM + footprint sourcing lives in `DREAMS_V3_parts_footprints.md` — treat that as the
> authoritative parts list, this file as the "why" and "what's still open."

---

## What changed vs. the master doc

**Boat Pico → Teensy 4.1.** Full firmware rewrite from MicroPython to C++/Teensyduino.
Rationale: the V2 board was completely pin-saturated (every UART-capable/flexible GPIO already
spoken for by GPS/I2C/SHT41/winch/CAN), and RP2350B's improved pin count wasn't chosen — Teensy
4.1 was picked instead for 8 hardware UART ports + native FlexCAN. This means **every existing
`firmware/boat-pico/*.py` module gets reimplemented in C++**, not ported — see library mapping
below.

**CAN — MCP2515 dropped.** Teensy 4.1 has native on-chip FlexCAN (3 controllers), so the MCP2515
SPI-CAN bridge from the V2/RP2040 plan is no longer needed. Only the **TJA1051 transceiver**
remains, wired directly to Teensy's CAN TX/RX pins. Boat Pico becomes a real third CAN node
(talking to VESC IDs 1 and 2 directly) instead of relaying through a VESC master via
`COMM_FORWARD_CAN` — the master/slave VESC scheme in the current `vesc.py` goes away entirely.
Physical wiring: Teensy taps in as a **short stub off the existing VESC1↔VESC2 CAN run** (JST-XH
connector), not a daisy-chain-through. Termination stays at the two VESCs, unchanged.

**Pod — MCU and power architecture both changed.**
- MCU: Seeed XIAO RP2040 → **Seeed XIAO ESP32-S3** (same 21×17.5mm footprint, 11 GPIO with 9
  ADC-capable vs. RP2040's 4). Driven by wanting the pod smaller — this is a from-scratch board,
  not a V2 Pod Pico revision.
- Power: **tether is now 2× UART + 2× power** (not UART + local battery). No separate LDO needed —
  the XIAO ESP32-S3 has its own onboard regulator and accepts 5V directly on its 5V/VBUS pin (pin
  14), same concept as a Pi Pico's VSYS. Only addition: a schottky diode in series between the
  tether's 5V line and that pin, per Seeed's own guidance, since the pin is shared with the board's
  USB/charge circuitry and needs backfeed protection.
- All pod sensor logic (`sensors.py`, `leak_detect.py`, `uart_responder.py`) is conceptually
  unchanged — same EC probe / NTC / photoresistor / bottom-contact / pressure transducer / leak
  contact / LED — just needs porting to the ESP32-S3's pin numbering and MicroPython port.

**New sensors added to the Boat Carrier PCB** (none of these exist in the V2 BOM):
- BNO085 IMU, 2× SHT45 (upgraded from SHT41 — same DFN-4 footprint/pinout/addr, better accuracy)
- BMP390 (barometric reference — intended to improve the pod pressure transducer's depth
  calculation via a surface baseline, not yet wired into firmware logic)
- ADXL375 accelerometer (±200g, upgraded from ADXL345 — same LGA-14 footprint family, headroom
  for real hull-slam events without clipping)
- BH1750FVI-TR ambient light sensor
- 3× INA228 current sense, one per M18 domain (upgraded from INA226 — **this was a correctness
  fix, not a nice-to-have**: INA226 is only rated to 36V common-mode, the drive domain runs up to
  63V max, so INA226 would have been out of spec on that channel)
- TCA9548A I2C mux to consolidate all of the above onto one Teensy I2C bus

**Fabrication approach:** leadless packages (BNO085, SHT45 ×2, BMP390, ADXL375) will be hand-done
via hot air rework + solder paste + stencil at Northeastern's EXP Makerspace Electronics Bench.
Leaded packages (TJA1051, TCA9548A, INA228) get hand-soldered with an iron as usual.

---

## Still open — not yet decided

1. **Firmware concurrency model for the Teensy rewrite** — millis()-scheduled `loop()` vs.
   TeensyThreads (closer analog to the current one-`uasyncio`-task-per-module structure). This is
   an architectural decision that shapes how every rewritten module gets written; nothing has been
   started yet pending this call.
2. **CAN bus physical splice point** — depends on where things land on the new board layout;
   doesn't affect termination (stays at the two VESCs either way).
3. **M10-25Q GPS module footprint** — no verified KiCad library found; will need manual measurement
   once the part is physically in hand.
4. Pod tether power voltage — 5V recommended but not finalized (affects diode voltage rating only,
   no separate regulator needed now).

---

## Reference files
- `DREAMS_MASTER_CONTEXT.md` — full V2 system architecture (still accurate for anything not listed
  above: hull fabrication, mission FSM, cloud/dashboard, RC/safety, connectivity, etc.)
- `DREAMS_V3_parts_footprints.md` — full BOM with KiCad footprint availability + external
  symbol/footprint links (SnapEDA, community GitHub repos) for every new/changed part
