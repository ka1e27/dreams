# Drive ESC setup — NeutronRC 70A-G071 (AM32)

The test-bench drive motors run on two **NeutronRC 70A-G071** ESCs (STM32G071, AM32 firmware,
2–8S, 70 A, current-telemetry output). The Boat Pico drives them as 50 Hz servo PWM on GP2/GP3
(`firmware/boat-pico/escs.py`). Unlike a plain hobby ESC, AM32 is **configurable firmware** — these
settings matter for a slow boat drivetrain that reverses, and a few of the drone defaults are wrong
for this use. Configure both ESCs identically with the AM32 web/desktop configurator (via the
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

- **Directly from the Pi's GPIO UART — yes, PROVEN (`pi5/scripts/am32_config.py`).** Temporarily move
  the ESC **signal** wire off Pico GP2 to the Pi's UART (pin 10 RX direct, pin 8 TX via ~1 kΩ, GND
  pin 6), enable `uart0`, and this script reads/sets bidirectional/telemetry/LVC over the one-wire
  bootloader — **no browser, no adapter.** Settings only (not firmware flashing). Full guide +
  one-time UART setup in **`docs/am32_config.md`**. This is now the recommended bench path.
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
| **Current telemetry** | **enable it** | The TX pad emits KISS telemetry (temp + current). Now wired: ESC **TX → GP16 (L) / GP19 (R)**, received by `esc_telem.py` → per-motor temp/current on the dashboard + a motor-overheat WARN. Turn on the telemetry / auto-telemetry option in am32.ca so it streams in servo-PWM mode. Full bring-up: **`docs/esc_telemetry.md`**. |

## Current management (the pack is the tighter limit)

Even at 70 A/ESC, **the pack — not the ESC — is the limit**: two motors at 70 A is 140 A, over a
2× M18 parallel HO-6Ah pair's ~90 A continuous. So:

- **Prop the motors so the *combined* draw stays under ~90 A.** If AM32's current limit is available,
  set ~45 A/motor as a hard cap; otherwise the prop choice is the limit.
- The **100 A main / 80 A per-ESC ANL fuses** + the **M18 REDLINK BMS** are the backstop.
- 2× parallel is ~18 V — **below 6S (22 V)** — so these 2814s make less than their 1330 W/6S rating.

See `docs/battery_architecture.md` for the full drive-rail spec.

## Kv mismatch

The two 2814s may spin at slightly different RPM for the same pulse. Correct it in software (there's no
per-motor ERPM cap on the PWM path): the Pi-side trim `navigation.motor_gain_left/right` in
`pi5/config.yaml` (lower the faster motor until it tracks straight at equal command), plus the firmware
`COMP_L/COMP_R` in `motor_control.py`, and the closed-loop heading control nulls the residual crab.

## First-spin checklist

1. Props **off**. Flash AM32 ≥ v1.99, set Bi-directional ON + LVC (5S) on **both** ESCs.
2. Arm at neutral (the firmware sends a 1.5 ms stop pulse on init) — confirm both ESCs arm and stay stopped.
3. Command small **forward** then small **reverse** throttle; confirm both spin the right way and *reverse*.
4. Fix per-motor direction; set `motor_gain_*` so equal command tracks straight.
5. Props on, in water. Verify the Pico watchdog kills to neutral when heartbeats stop (pull the Pi link).
