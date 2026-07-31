"""Low-level A4988 bring-up test — bypasses StepperMotor and the tracker.

Diagnostic for the "holds position but never rotates" case. Drives STEP/DIR/
ENABLE/SLEEP directly with wide (100 us) pulses at 1 Hz so a human can watch the
shaft advance one step at a time. Nothing here ramps, threads, or auto-sleeps.

Run it with the main stack STOPPED (it needs the GPIO pins):

    pkill -f run_hardware.py
    .venv/bin/python pi5/cv/stepper_lowlevel_test.py

What each outcome means:

  * shaft ticks ~0.9 deg per printed step, 20 steps = ~18 deg of travel
        -> STEP reaches the driver, coils are paired correctly. The fault is
           further up (tracker speed, soft limits, or mechanical coupling).
  * shaft buzzes / vibrates / twitches but nets no rotation
        -> COIL PAIRING is wrong at J18. The A4988's two channels must each get
           one whole coil: J18 pins 1+2 (1B, 1A) = one coil, pins 3+4 (2A, 2B) =
           the other. Split a coil across both channels and you get exactly this.
           Unplug the motor and ohm the wires: a coil pair reads a few ohms,
           wires from different coils read open.
  * shaft stays rock solid and silent, but resists being turned by hand
        -> the coils are energised (so VMOT + ENABLE + SLEEP are all good) but
           the phase never advances: STEP is not reaching A2 pin 15 (the STEP pin
           on the carrier's logic row, between SLEEP and DIR). **This is the live
           fault on this board** — confirmed 2026-07-29 with 800 pulses and zero
           rotation. Don't diagnose it at 1 Hz: a detent snap on energise looks
           like "a step or two landed". Use `stepper_probe.py burst` instead, then
           meter J14.13 and A2.15 to place the break.
  * shaft spins freely with no resistance at all
        -> no coil current: VMOT missing (BT4, the winch pack's inlet) or the
           carrier isn't seated.
"""
from __future__ import annotations

import sys
import time

PULSE_US = 100          # 100x the A4988's 1 us minimum — rules out a short pulse
STEPS = 20              # 20 x 0.9 deg = 18 deg per direction at half step
STEP_INTERVAL_S = 1.0   # slow enough to watch each individual step

STEP_PIN, DIR_PIN, ENABLE_PIN, SLEEP_PIN = 23, 24, 25, 8


def main() -> int:
    try:
        from gpiozero import OutputDevice
    except Exception as e:  # noqa: BLE001
        print("gpiozero unavailable (%s) — cannot drive real GPIO." % e)
        print("See pi5/requirements.txt for the install recipe.")
        return 2

    try:
        step = OutputDevice(STEP_PIN, initial_value=False)
        dirp = OutputDevice(DIR_PIN, initial_value=False)
        en = OutputDevice(ENABLE_PIN, initial_value=True)    # 1 = disabled
        slp = OutputDevice(SLEEP_PIN, initial_value=False)   # 0 = asleep
    except Exception as e:  # noqa: BLE001
        print("Could not claim the pins (%s)." % e)
        print("Is run_hardware.py still running? Stop it first: pkill -f run_hardware.py")
        return 2

    try:
        print("=== A4988 low-level test ===")
        print("pins: STEP=%d DIR=%d ENABLE=%d SLEEP=%d | pulse=%dus | %d steps/dir @ %.1fs"
              % (STEP_PIN, DIR_PIN, ENABLE_PIN, SLEEP_PIN, PULSE_US, STEPS, STEP_INTERVAL_S))

        slp.value = 1                 # wake: releases ~SLEEP and (tied) ~RESET
        time.sleep(0.005)             # charge pump settle, 5x the datasheet 1ms
        en.value = 0                  # energise
        print("\ncoils ENERGISED — the shaft should now resist being turned.")
        print("holding 3s (feel for warmth + holding torque)...")
        time.sleep(3.0)

        for direction, label in ((1, "CW"), (0, "CCW")):
            dirp.value = direction
            time.sleep(0.001)         # DIR setup, >200ns
            print("\n--- %s: %d steps of 0.9 deg (%.1f deg total) ---"
                  % (label, STEPS, STEPS * 0.9))
            for i in range(1, STEPS + 1):
                step.value = 1
                time.sleep(PULSE_US / 1_000_000.0)
                step.value = 0
                print("  step %2d/%d  (cumulative %.1f deg)" % (i, STEPS, i * 0.9),
                      flush=True)
                time.sleep(STEP_INTERVAL_S)

        print("\ndone — releasing coils.")
        return 0
    except KeyboardInterrupt:
        print("\ninterrupted — releasing coils.")
        return 1
    finally:
        # Always de-energise, even on error: coils left energised cook the motor.
        try:
            en.value = 1      # disable
            slp.value = 0     # sleep
            for d in (step, dirp, en, slp):
                d.close()
        except Exception:  # noqa: BLE001
            pass


if __name__ == "__main__":
    sys.exit(main())
