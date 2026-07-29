# Hardware Changes: V2 Dual-Hull → Single-Hull Test Bench

> **Status: firmware implemented on branch `single-hull-test-bench`.** The Boat Pico firmware
> changes described here are done on that branch (new `escs.py`; edits to `motor_control.py`,
> `sbus.py`, `sensors.py`, `main.py`); no PCB/KiCad changes are made (same board). Nothing on `main`
> changes — the dual-hull catamaran (V2) remains the architecture-of-record in
> `docs/changelog_and_decisions.md`.

## Why

Before building the full-strength dual-hull catamaran with VESC-driven brushless motors, the owner
wants a cheaper, simpler single-hull test bench to validate steering, navigation, and the rest of the
software stack on real hardware. It reuses the same Boat_PCB board (no new KiCad files) and the same
firmware/Pi 5 stack — only the drive-motor path and the drive battery domain differ.

## Summary Table

| Component | V2 Dual-Hull (production) | Single-Hull Test Bench |
|-----------|---------------------------|-------------------------|
| Hull | Two hulls (catamaran) | One hull |
| Drive motors | 2× full-strength brushless, one per hull | 2× smaller brushless (bench-test power level), both mounted at the stern |
| Steering | Differential thrust, port/starboard hull | Differential thrust, port/starboard motor (same math) |
| ESCs | 2× VESC (master + CAN-forwarded slave) | 2× standard hobby ESCs (no VESC, no CAN chain) |
| ESC comms | UART0 (GP12/13) → VESC master; slave via `COMM_FORWARD_CAN` | Direct 50 Hz servo-style PWM, one Pico GPIO per ESC (**GP2 left, GP3 right**) |
| Winch signal | GP14 PWM | **GP21 PWM** (GP14 → GP6 → GP21; GP21 is the board's J8/J9 winch net) |
| SBUS RC | GP15 (PIO) | **GP7 (PIO)** (moved off GP15) |
| Air temp/humidity | 2× SHT41 (GP12/13 J11, GP14/15 J13) | **2× SHT41 — kept** on GP12–15 |
| Drive battery | 3× Milwaukee M18 in series (54 V nom / 63 V max) | 2× Milwaukee M18 in series (36 V nom / 42 V max) |
| Electronics battery | 1× M18 (unchanged) | 1× M18 (unchanged) |
| Winch battery | 1× M18 (unchanged) | 1× M18 (unchanged) |
| PCB | Boat_PCB (production) | **Same Boat_PCB** — no new board (ESC/winch/SBUS taps on the Pico breakout header) |
| Everything else (GPS, IMU, sensors, Pi 5 stack, mission FSM, serial protocol) | as documented in `CLAUDE.md` | **Unchanged** |

---

## Drive Motors: VESC/CAN-chain → Standalone ESCs on Direct PWM

The production board reaches the VESC master over UART0 (GP12/13, `firmware/boat-pico/vesc.py`),
which then forwards duty-cycle commands to the VESC slave over the VESCs' own CAN bus
(`COMM_FORWARD_CAN`). Standard hobby ESCs don't speak that protocol at all — they just want a
50 Hz servo-style PWM signal (~1.0–2.0 ms pulse, 1.5 ms = stop), which is exactly the pattern the
Boat Pico already uses for the winch (`firmware/boat-pico/motor_control.py`, `machine.PWM`,
`STOP_PWM = 4915`, `MIN_PWM = 3277`, `MAX_PWM = 6553`, 16-bit `duty_u16`).

**Plan:** drop the VESC UART/CAN protocol for this variant and drive both ESCs directly with the same
`machine.PWM` pattern used for the winch — one GPIO per motor.

**Differential-steering math is unchanged.** The pulley-compensation trim in `motor_control.py`
(`COMP_L`/`COMP_R`, `_trim`) exists to correct for the catamaran's asymmetric pulley ratios
(18:27 vs 15:30). The test bench has two identical motors on one hull with no pulley asymmetry, so
`COMP_L = COMP_R = 1.0` and `_trim` stays at its default. The `-100..+100` percent throttle inputs
from `SET_THR` and the serial-protocol dispatch path (`serial_handler.py` → `on_set_thr()` →
`motor_control.set_throttle()`) don't change at all — only the last step (percent → VESC UART duty vs.
percent → PWM `duty_u16`) differs.

### GPIO pins — the ESCs move to free header pins, and both SHT41s stay put

The obvious idea was to reuse the freed VESC pins (GP12/GP13) for the two ESCs. That **doesn't work
on this board** once you keep the temp sensors. The as-built `Boat_PCB.kicad_sch` routes GP12–15 to
the two SHT41 temp/humidity connectors — GP12/13 → J11 ("SHT41 #A"), GP14/15 → J13 ("SHT41 #B"), on
bit-banged SoftI2C (verified by tracing the schematic; this is the "as-built divergence" already
flagged in `docs/pin_map.md`, where the dual-hull firmware's VESC/winch/SBUS claims on GP12–15 never
matched the fabricated board). Since this variant **keeps both SHT41 sensors**, GP12–15 belong to
them, and the propulsion/winch/SBUS signals move to free Pico GPIO instead:

| Signal | Test-bench pin | RP2040 detail |
|--------|----------------|---------------|
| Left drive ESC | **GP2** | PWM slice 1, channel A |
| Right drive ESC | **GP3** | PWM slice 1, channel B (shares slice 1 with GP2 — same 50 Hz, independent duty, which is all two ESCs need) |
| Winch ESC | **GP21** | PWM slice 2, channel B. Moved GP14 → GP6 → **GP21** on 2026-07-28: GP21 is where `Boat_PCB V2` actually routes the winch signal (J8.1 + J9.1 in parallel), while GP6 is the MCP2515's `~INT`. The one relocated signal that *does* have a board connector |
| SBUS RC | **GP7** | PIO state machine (moved off GP15; PIO runs on any GPIO) |
| SHT41 #A | GP12 / GP13 | SoftI2C, J11 — unchanged |
| SHT41 #B | GP14 / GP15 | SoftI2C, J13 — unchanged |

GP2/GP3/GP7 are unconnected on the schematic (no connector), so on the test bench you **tap them
directly on the Pico's breakout header** — fine for a bench rig, where the ESC/SBUS signal wires are
hand-run anyway. The winch is the exception: **GP21 plugs into J8 (or J9)** on the board. This also happens to *resolve* the dual-hull GP12–15 conflict for this
build: the temp sensors get their native pins and nothing else contends for them.

**MCP2515 aside:** `Boat_PCB.kicad_sch` has a placed `MCP2515-I_P` (U1) CAN-controller symbol that
contradicts the "no MCP2515 HAT" decision in `docs/changelog_and_decisions.md`. Traced it — **all 18
pins are unwired**, a placed-but-never-connected footprint. It touches nothing, so it's irrelevant
here (worth deleting from the schematic eventually).

### Firmware changes (done on `single-hull-test-bench`)

- **New `firmware/boat-pico/escs.py`** — dual hobby-ESC PWM driver on GP2/GP3, mirroring the winch
  PWM block (`machine.PWM(Pin(2))`/`Pin(3)`, `.freq(50)`, `.duty_u16(...)`, same
  `STOP_PWM`/`MIN_PWM`/`MAX_PWM` pulse mapping). Exposes `LEFT`/`RIGHT`, `LEFT_PIN`/`RIGHT_PIN`,
  `init()` (returns success), `ready()`, `set_duty()`, `stop()`, plus VESC-shaped telemetry **stubs**
  (`get_motor_temp`→None, `get_fault`→0, `max_motor_temp`→0.0, `poll_rx`/`request_values_round_robin`
  →no-op) so `main.py`'s telemetry code runs unchanged.
- **`motor_control.py`** — imports `escs` instead of `vesc`; `init()`/`update()`/`estop()` drive the
  ESCs via `escs.*`; winch PWM `MW_PIN` `14` → `6` → **`21`**; `COMP_L = COMP_R = PULLEY_L = PULLEY_R = 1.0`
  (single hull, no pulley asymmetry). `init()` now returns whether the drive ESCs came up, so the
  ESTOP/watchdog kill path's health is observable. Steering math + `set_throttle`/RC/ESTOP gates
  otherwise unchanged.
- **`sbus.py`** — `SBUS_PIN` `15` → `7` (PIO). No other change.
- **`sensors.py`** — drive-rail constants updated (see battery section). **Both SHT41 sensors kept**
  on GP12–15 exactly as before (`SoftI2C`/`sht41` retained). This is the *only* firmware file where
  the "keep both SHT41" decision shows up as a no-change vs. the dual-hull sensor code.
- **`main.py`** — imports `escs` instead of `vesc`; VESC telemetry task removed; motor-overheat /
  ESC-fault handling in the watchdog removed (no telemetry from dumb ESCs); TEL2/`v_in` now carries
  the drive-rail ADC voltage; startup now prints drive-ESC `OK`/`FAIL` with a "do NOT arm" warning on
  failure; docstring pin map + startup prints updated.
- `vesc.py` is left in the tree but is **no longer imported** on this branch.
- **No changes** to `serial_handler.py`, `watchdog.py`, `gps.py`, `compass.py`, `pod_uart.py`, or any
  Pi 5 / navigation / server / cloud code — none of that is aware of VESC vs. plain ESC.

---

## Drive Battery: 3× M18 Series → 2× M18 Series

> ⚠ **This section is historical — superseded.** The bench drive rail is now **2× M18 in PARALLEL**
> (18 V nom / 21 V max, single-pack thresholds), not 2× in series, and all three dividers are
> **56 k/10 k (×6.6)** with `INV_P_RATIO = 6.6`. The 36 V / ×14.0 numbers below describe the earlier
> series bench. Current spec: `docs/battery_architecture.md`.

Test bench uses a lower-power drive rail: **2× Milwaukee M18 packs in series** instead of 3.

| | Production (3× M18) | Test bench (2× M18) |
|---|---|---|
| Nominal | 54 V | 36 V |
| Max | 63 V | 42 V |
| Cutoff (empty) | 45 V | 30 V |
| Warn / Crit | 51 V / 48 V | 34 V / 32 V |
| Divider (GP26) | 200 kΩ / 10 kΩ (×21.0) | 130 kΩ / 10 kΩ (×14.0) |
| ADC at max pack V | 63 / 21.0 = 3.00 V | 42 / 14.0 = 3.00 V |

**Divider math:** the reconstruction ratio is `(R_high + R_low) / R_low`, so 130 kΩ/10 kΩ = ×14.0
(not ×13.0 — 120 kΩ/10 kΩ would be ×13.0). ×14.0 was chosen so 42 V max lands at exactly 3.00 V on the
Pico pin — the *same* conservative ceiling the production 200 kΩ/10 kΩ divider gives at 63 V — with
comfortable headroom under the 3.3 V ADC rail. The existing 1 kΩ series filter + 100 nF cap on the ADC
input carry over unchanged. Thresholds scale per-pack from the production values (21/15/17/16 V × 2).

**Firmware change (done on `single-hull-test-bench`):** `firmware/boat-pico/sensors.py` — drive-rail
inverse ratio constant `INV_P_RATIO` `21.0` → `14.0`, and the full/empty/warn/crit constants to the
2×-series values above (`P_FULL=42`, `P_EMPTY=30`, `P_WARN=34`, `P_CRIT=32`). Electronics (GP27) and
winch (GP28) dividers and thresholds are untouched — both stay at 1× M18 (56 kΩ/10 kΩ, ×6.6).

---

## What Stays the Same

- Same Boat_PCB — no new KiCad schematic/PCB files, no new connectors. Still two drive motors
  (both at the stern for differential steering); the change is swapping the two VESCs for two plain
  hobby ESCs and driving them from Pico PWM instead of UART/CAN.
- GPS (u-blox M10Q, UART1 GP4/5), IMU (BNO085, I²C0 GP8/9), status NeoPixel (GP10), hull-leak
  switches (GP17/18), **both SHT41 air temp/humidity sensors (GP12–15, J11/J13)**, and
  electronics/winch battery monitoring (GP27/28) — all unchanged.
- Full Pi 5 stack: navigation, mission FSM, computer vision, cloud pipeline, web dashboard, serial
  protocol framing (`$payload*checksum\n`) — none of it is aware of the drive-motor swap.
- Differential-steering throttle math and the `SET_THR`/`SET_HDG` command path.
- Simulator-first workflow (`run_sim.py`) is unaffected; this only matters once real hardware is
  wired up.

## Open Items / Follow-ups

1. **Wire the three header-tapped signals to the Pico breakout header** (they have no PCB connector):
   left ESC → GP2, right ESC → GP3, SBUS → GP7. The winch is on **GP21 = J8/J9**, a real connector.
   GP12–15 keep their J11/J13 SHT41 connectors.
2. **Verify the ESC pulse range before first spin-up.** `escs.py` reuses the winch's 1.0–2.0 ms /
   50 Hz mapping (`STOP_PWM`/`MIN_PWM`/`MAX_PWM`). Not all hobby ESCs share it — some are
   forward-only or use a different neutral. Confirm against the chosen ESCs' datasheet and bench-test
   arming + direction before putting props in the water.
3. **ESC arming sequence.** Many hobby ESCs require a neutral-then-hold at power-on to arm.
   `escs.init()` sends neutral immediately; confirm the specific ESCs arm cleanly on that, or add an
   arming delay/beep-wait if needed.
4. **Battery build:** 2× M18 in series on the drive rail with a 130 kΩ/10 kΩ divider to GP26.
5. **Safety re-check:** dumb ESCs hold their last PWM if commands stop (no VESC-style self-timeout).
   The heartbeat watchdog → `estop()` → neutral-PWM path is the only motor kill — verify the 3 s
   heartbeat timeout actually neutralises the ESCs on the bench. `main.py` prints the drive-ESC
   init result at startup; a `FAIL` there means the kill path can't drive the ESCs — do not arm.
6. `docs/pin_map.md` is the authoritative pin map generated from the firmware docstrings; it still
   describes the production board, so regenerate/annotate it for the test-bench pinout if this branch
   is kept long-term.
7. Not in scope here, but worth fixing on `main` eventually: the unwired MCP2515 placeholder in
   `Boat_PCB.kicad_sch` (delete if unused) and the dual-hull GP12–15 VESC/winch/SBUS-vs-SHT41
   firmware mismatch (this branch sidesteps it by moving those signals to GP2/3/6/7).
