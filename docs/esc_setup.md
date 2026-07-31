# Drive ESC setup — AM32 (left) + BLHeli-32 (right)

> **⚠ 2026-07-30 — the two drive ESCs are no longer identical, and they moved pins.**
>
> | | pin / connector | ESC | firmware | motor | telemetry |
> |---|---|---|---|---|---|
> | **Left** | GP19 · J16 | NeutronRC 70A-G071 | **AM32** | Badass 2814-**1560 kv** | GP16 |
> | **Right** | GP20 · J15 | FlashHobby FH-70A | **BLHeli-32** | Badass 2320-**1630 kv** | GP11 |
>
> They were on GP2/GP3, which belong to the MCP2515 on `Boat_PCB V2` and reach no connector;
> J16/J15 are the ex-hull-leak connectors (1 = GND, 2 = signal). **Hull leak sensing is gone** —
> see `docs/pin_map.md`. Both ESCs take the same 1.0/1.5/2.0 ms 50 Hz signal, so the firmware
> drives them identically — but **each is configured in its own tool** and the two families do
> not share defaults. Configure both **before first spin-up**.

## 🔴 The bi-directional gate — read this first

**Throttle is blocked in firmware until both ESCs are confirmed bi-directional.** A fresh flash
ships with `escs.BIDIR_CONFIRMED = {LEFT: False, RIGHT: False}`, every `SET_THR` returns
`NAK … ESC_UNSAFE`, and both ESCs are pinned at the 1.5 ms neutral pulse. This is deliberate.

### Why — the 2026-07-31 bench incident

`escs.py` maps duty 0.0 to a 1.5 ms pulse and calls it "neutral". **That is only true in
bi-directional / 3D mode.** A stock **normal-mode** ESC reads the identical 1.5 ms as **~50 %
throttle**. On the bench the right ESC (BLHeli-32, never configured):

1. sat inert at first — 1.5 ms at power-up is "throttle high", so it **refused to arm**, which read
   as a dead motor and sent the whole investigation looking at wiring;
2. **armed** the instant a `-100` command produced 1.000 ms — its *throttle zero*;
3. then ran on at ~50 % when the sweep returned to 1.5 ms "neutral", and **kept running through
   `SET_THR 0,0` and through `ESTOP`**, because both of those are that same 1.5 ms.

Only an explicit `-100` stopped it. So on a mis-set ESC, **every stop this firmware can express —
neutral, `escs.stop()`, `motor_control.estop()`, the heartbeat watchdog — commands half throttle.**
With props on and in the water, hitting E-STOP would drive the boat forward.

### Why the gate is all-or-nothing

There is **no pulse width that stops both kinds at once**:

| pulse | 3D / bi-directional ESC | normal-mode ESC |
|---|---|---|
| **1.5 ms** | stop ✅ | **~50 % throttle** ❌ |
| **1.0 ms** | **full reverse** ❌ | stop ✅ |

A mixed pair therefore has no safe state at all, which is why one unconfirmed ESC blocks the whole
drive train rather than just its own channel.

### Clearing it

1. Configure **both** ESCs (AM32 "Bi-Directional" ON; BLHeli-32 "3D Mode" ON **and** throttle range
   calibrated to 1000–2000 µs). If the right ESC turns out to be BLHeli**_S**, stock firmware has no
   3D mode at all — reflash with Bluejay or it can never reverse and never has a valid stop.
2. Verify in the config tool by **reading the setting back**, not by watching the motor.
3. Set both entries in `firmware/boat-pico/escs.py` to `True` and redeploy.
4. Boot banner should then read `Drive ESC mode: bi-directional CONFIRMED on both — throttle enabled`.

Tests covering the gate: `pi5/tests/test_esc_bidir_gate.py`.

## Left ESC — NeutronRC 70A-G071 (AM32)

The left drive motor runs on a **NeutronRC 70A-G071** (STM32G071, AM32 firmware,
2–8S, 70 A, current-telemetry output). The Boat Pico drives it as 50 Hz servo PWM on GP19
(`firmware/boat-pico/escs.py`). Unlike a plain hobby ESC, AM32 is **configurable firmware** — these
settings matter for a slow boat drivetrain that reverses, and a few of the drone defaults are wrong
for this use. Configure it with the AM32 web/desktop configurator (via the
USB-linker) **before first spin-up**.

> These are sold "for crawler / robot drivetrain", and the vendor recommends **AM32 firmware
> ≥ v1.99** for drivetrain use — flash that first. Exact setting names vary slightly by AM32
> version; cross-check the [AM32 wiki](https://github.com/AlkaMotors/AM32-MultiRotor-ESC-firmware/wiki).

## Required

| Setting | Value | Why |
|---|---|---|
| **Bi-Directional** | **ON** (checkbox) | The navigator commands *negative* throttle to pivot in place and to bear away during avoidance. Bi-Directional makes 1.5 ms = neutral, <1.5 ms = reverse, >1.5 ms = forward — exactly what `escs.py` sends. **Off = forward-only**: reverse pulses just idle, so the boat can't pivot or back away. |
| **RC Car Reversing** | **OFF** | That mode adds brake-on-first-reverse + double-tap-to-change-direction (for RC cars). The boat needs *immediate* proportional reverse on command, so leave it off — plain Bi-Directional gives center-neutral instant reverse. |
| **Input protocol** | Servo PWM (auto) | AM32 auto-detects the 50 Hz servo signal; no DShot needed for this Pico PWM path. |
| **Low-voltage cutoff** | ~3.0 V/cell, **5 cells** (≈15 V) | The drive rail is 2× M18 **parallel** = one 5S M18 (18 V nom / 15 V cutoff). Match the ESC LVC to the pack cutoff as a per-ESC backstop (the firmware also watches pack voltage on GP26). Do **not** set a 6S/8S cutoff. |
| **Reversed** (per motor) | as needed | If a forward command spins a hull backward, tick "Reversed" for that ESC so forward command → forward thrust on both hulls. |

### How to enable it (AM32 web configurator)

You configure **each ESC individually** (the NeutronRC "USB TO ESC" linker connects one at a time).

1. **Prop off.** Plug the ESC's signal/ground into the NeutronRC USB-linker, linker → PC via USB-C
   (install the CH340 VCP driver if the port doesn't appear). Main drive battery *not* needed to
   change settings — only to bench-test motion afterward.
2. Open **https://am32.ca/configurator** in **Chrome or Edge** (needs Web Serial).
3. **Port Select** (top-right) → pick the CH340 serial port → **Connect** → **Read**.
4. Tick **Bi-Directional** ON. Confirm **RC Car Reversing** is OFF. Set **Low Voltage Cut-Off** to
   3.0 V/cell and cell count 5. (Also apply the "recommended" tuning below.)
5. **Save Config / Apply.** Then repeat 1–5 for the **second ESC**.
6. Bench-verify (still prop off, now with drive battery + Pico running): on init the firmware holds
   1.5 ms neutral so the motor stays stopped; command a small **forward**, then a small **reverse**,
   and confirm the motor actually reverses. Fix per-motor "Reversed" and set `motor_gain_*` so equal
   command tracks straight.

### Can I program them from the Pi instead of a laptop?

AM32 is configured over the ESC's **signal wire** using a one-wire (half-duplex) serial protocol —
the USB "linker" is just a CH340 USB-serial adapter on that wire. So:

- **From the dashboard — easiest, recommended.** The command center has a full **ESC Settings** editor
  (COMMANDS → DRIVE → **⚡ ESC SETTINGS**, or ⚙ TRIM → *Open ESC Settings*). Wire the ESC to the Pi's
  UART as below (the modal's **Wiring & Setup** tab shows the pinout + the one-time `uart0` commands with
  copy buttons), press **Read ESC**, toggle/slide the settings, then **Write Changes** (read-modify-write
  + read-back verified). It renders straight from `am32_config`'s field registry, so bi-directional,
  telemetry, LVC, direction and the drivetrain tuning below are all one click. Boat-critical settings are
  flagged (★) and risky states glow amber. In the simulator it serves a demo ESC so you can explore it
  with no hardware. Backed by the same GPIO-UART path as the CLI below.
- **From the CLI — `pi5/scripts/am32_config.py` (PROVEN).** Same wiring; move the ESC **signal** wire off
  Pico GP2 to the Pi's UART (pin 10 RX direct, pin 8 TX via ~1 kΩ, GND pin 6), enable `uart0`, and this
  script reads/sets bidirectional/telemetry/LVC/… over the one-wire bootloader — **no browser, no
  adapter.** Settings only (not firmware flashing). Full guide + one-time UART setup in
  **`docs/am32_config.md`**.
- **USB linker on a Pi USB port — also works.** Plug the NeutronRC "USB TO ESC" (or any CH340
  USB-serial) into a Pi USB-A port and run `am32.ca` in **Chromium on the Pi desktop**. (Note:
  Chromium's Web Serial only lists **USB** ports, so it will *not* see the GPIO UART above — a USB
  adapter is required for the browser path.) Also flashes firmware, which the CLI tool doesn't.
- **Through the Pico as an AM32 passthrough — scaffolded (experimental).** GP2/GP3 already reach the
  ESC signals, so the Pico can bridge the Pi↔Pico USB-CDC onto the ESC one-wire, like Betaflight/ArduPilot
  BLHeli/AM32 passthrough — reconfigure the ESCs **in place, no unplugging**, even in the field. A first
  implementation now exists (`firmware/boat-pico/esc_passthrough.py`, `pi5/scripts/esc_passthrough.py`)
  but is **not yet hardware-validated** — see **`docs/esc_passthrough.md`** for the bring-up/validation
  plan. Until those steps pass, use the USB linker (option 2).

## Recommended for a boat drivetrain (review the drone defaults)

| Setting | Suggested | Why |
|---|---|---|
| **Low-RPM power protect** | OFF / minimum | Drone default cuts power at low RPM; a survey boat cruises and idles at low RPM and would stutter. |
| **Stuck/stall protection** | relaxed | A prop loading up (weeds, a nudge) shouldn't trip a restart mid-mission. |
| **Brake on stop** | OFF | Let the prop freewheel at neutral; braking wastes energy and fights the differential steering. |
| **Sinusoidal startup** | ON | Smoother, quieter low-speed starts under a big prop load than damped-light. |
| **Motor timing** | tune up if rough | Larger boat props at low KV often want more advance than the drone default; raise if startup is rough. |
| **Current limit** | ~45 A/motor *if available* | Newer AM32 exposes a current limit. If yours does, cap each motor so the pair stays within a 2× M18 parallel pack (~90 A). If not, prop-size for it — see below. |
| **Current telemetry** | **enable it** | The TX pad emits KISS telemetry (temp + current). Now wired: ESC **TX → GP16 (L) / GP11 (R)**, received by `esc_telem.py` → per-motor temp/current on the dashboard + a motor-overheat WARN. Turn on the telemetry / auto-telemetry option in am32.ca so it streams in servo-PWM mode. Full bring-up: **`docs/esc_telemetry.md`**. |

## Current management (the pack is the tighter limit)

Even at 70 A/ESC, **the pack — not the ESC — is the limit**: two motors at 70 A is 140 A, over a
2× M18 parallel HO-6Ah pair's ~90 A continuous. So:

- **Prop the motors so the *combined* draw stays under ~90 A.** If AM32's current limit is available,
  set ~45 A/motor as a hard cap; otherwise the prop choice is the limit.
- The **100 A main / 80 A per-ESC ANL fuses** + the **M18 REDLINK BMS** are the backstop.
- 2× parallel is ~18 V — **below 6S (22 V)** — so these 2814s make less than their 1330 W/6S rating.

See `docs/battery_architecture.md` for the full drive-rail spec.

## Right ESC — FlashHobby FH-70A (BLHeli-32)

Same 50 Hz servo signal on GP20, but configured in **BLHeli-32 Suite / BLHeliSuite32**, not the AM32
tool. The settings map across, with different names:

| BLHeli-32 setting | Value | AM32 equivalent / why |
|---|---|---|
| **3D Mode** | **ON** | This is BLHeli's name for bidirectional. Same reason as AM32 "Bi-Directional": 1.5 ms = neutral, <1.5 ms = reverse. **Off = forward-only** and the boat cannot pivot in place or back away. |
| **Throttle calibration** | **1000–2000 µs** | AM32 auto-detects the servo range; BLHeli-32 generally does **not**. Calibrate it or neutral/end-points will not line up with `escs.py`, which is hard-coded to 1000/1500/2000 µs. |
| **Motor Direction** | set so positive duty = **forward thrust** | AM32's "Reversed". The two firmwares do not agree on default spin direction — expect to flip this one, not both. |
| **Low RPM Power Protect** | **OFF** | A boat spends its life at low RPM under load; this drone-oriented limiter cuts power exactly there. |
| **Low Voltage Protection** | ~3.0 V/cell, **5 cells** (≈15 V) | Match the AM32 side and the M18 pack cutoff. |
| **Telemetry** | **ON, continuous/auto** | `esc_telem.py` expects a streamed KISS frame. BLHeli-32 can be set to answer only on DShot request — that yields no telemetry on this PWM path. |
| **Brake on Stop / Damped** | OFF | Avoid braking a prop against water on every neutral. |

> BLHeli-32 is closed-source and its configurator needs the ESC's own passthrough or a USB linker.
> If this ESC turns out to be BLHeli_S (not _32), it has **no 3D mode on stock firmware** — reflash
> it with **Bluejay** and enable bidirectional there, or the right motor will never reverse.

> ### ⚠ There is no Pi-side tool for this ESC, and there cannot easily be one
>
> BLHeli_32 is closed source and was **discontinued in 2024**; `esc-configurator` supports only
> BLHeli_S, Bluejay and AM32, so there is no open implementation of the _32 settings protocol to
> build against. `am32_config.py` and `esc_passthrough.py` are **AM32-only** and will not configure
> this ESC. Setting 3D mode here means **BLHeliSuite32 + a USB linker**, by hand.
>
> **The recommended alternative is to convert this ESC to AM32** — its MCU (STM32F051) is a
> supported AM32 target (`FLASHHOBBY_F051`), which puts both ESCs on one firmware, makes
> `am32_config.py` work on it, and enables telemetry. It needs SWD access, but **no ST-Link** — the
> Pi 5 can act as the programmer via OpenOCD, which is already installed. Full procedure:
> **`docs/esc_am32_conversion.md`**.

## Kv mismatch — ⚠ these motors are genuinely different

Not a small manufacturing spread any more: **2814-1560 kv (left) vs 2320-1630 kv (right)**, so the
right motor runs ~4.5 % faster at the same pulse.

This is trimmed in the firmware only — **`motor_control.COMP_R = 0.957`** (= 1560/1630), with
`COMP_L = 1.0` as the reference. **Leave `navigation.motor_gain_left/right` at 1.0** in
`pi5/config.yaml`: setting both would compensate the same mismatch twice.

Kv only equalises *no-load* rpm. Different frames (2814 vs 2320) have different torque constants and
prop loading, so treat 0.957 as a starting point and tune `COMP_R` on the bench — run both at a fixed
throttle and match erpm from the ESC telemetry. The closed-loop heading control nulls the residual crab.

## First-spin checklist

1. Props **off**. Left: flash AM32 ≥ v1.99, Bi-directional ON + LVC (5S). Right: BLHeli-32
   3D Mode ON, throttle calibrated 1000–2000 µs, LVC (5S), telemetry continuous.
2. **Read both settings back in the config tool**, then set `escs.BIDIR_CONFIRMED` → `True` for each
   and redeploy. Until you do, throttle is blocked (`NAK … ESC_UNSAFE`) — see the gate section above.
3. Confirm the boot banner reports `Drive ESCs: GP19(L,AM32,...)/GP20(R,BLHeli32,...) PWM 50Hz OK`
   **and** `Drive ESC mode: bi-directional CONFIRMED on both`.
4. Arm at neutral (the firmware sends a 1.5 ms stop pulse on init) — confirm both ESCs arm and stay
   stopped. An ESC that instead beeps continuously is still in normal mode: 1.5 ms is ~50 % throttle
   to it and it is refusing to arm. Stop and fix the mode — do **not** "wake it" with a low pulse,
   which is exactly what armed it into a runaway on 2026-07-31.
5. Command small **forward** then small **reverse** throttle; confirm both spin the right way and
   *reverse*. Expect to flip direction on the BLHeli side only.
6. Match rpm at a fixed throttle via ESC telemetry; adjust `COMP_R` from 0.957 as measured.
7. Props on, in water. Verify the Pico watchdog kills to neutral when heartbeats stop (pull the Pi
   link) — and confirm the motors actually **stop**, rather than settling to a steady hum.

> ⚠ **No hull leak alarm any more.** J15/J16 are these ESC signals now, so a swamped hull will not
> be detected — only the pod's leak sensor remains. Factor that into wet testing.
