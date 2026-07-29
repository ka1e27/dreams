"""Standalone bench test for the radar-bar StepperMotor — run on the Pi 5.

    python3 pi5/cv/stepper_test.py

Steps the motor through every driver function and prints PASS/FAIL for each.
Off a Pi (no gpiozero/lgpio) the driver runs in mock mode: the logic/position
tests still pass, but nothing physically moves — useful for a dry run before
wiring. Not imported by the server; safe to run any time the bar is free.
"""
from __future__ import annotations

import sys
import time

try:                                   # works as `python3 pi5/cv/stepper_test.py`
    from stepper import StepperMotor
except ImportError:                    # ...and as `python -m pi5.cv.stepper_test`
    from pi5.cv.stepper import StepperMotor

_passed = 0
_failed = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global _passed, _failed
    mark = "PASS" if ok else "FAIL"
    if ok:
        _passed += 1
    else:
        _failed += 1
    print("  [%s] %s%s" % (mark, name, (" -- " + detail) if detail else ""))


def approx(a: float, b: float, tol: float = 0.2) -> bool:
    return abs(a - b) <= tol


def main() -> int:
    print("=== StepperMotor bench test ===")
    m = StepperMotor(steps_per_rev=400, max_speed_rpm=10, auto_sleep_s=5,
                     min_deg=0, max_deg=180)
    print("  config: steps/rev=%d max_rpm=%.0f auto_sleep=%.0fs limits=[%.0f,%.0f] mock=%s"
          % (m.steps_per_rev, m.max_speed_rpm, m.auto_sleep_s, m.min_deg, m.max_deg, m.mock))
    if m.mock:
        print("  (mock mode -- no GPIO backend; verifying logic + timing only)")
    else:
        print("  (real GPIO -- WATCH THE BAR: it should physically move during"
              " steps 2-8 below)")

    # 1. init / enable / disable
    try:
        m.enable()
        m.disable()
        check("enable/disable -- no exceptions", True)
    except Exception as e:  # noqa: BLE001
        check("enable/disable -- no exceptions", False, str(e))

    # 2. rotate 90deg CW
    m.reset_position()
    m.rotate_degrees(90, direction=1)
    a = m.get_position_degrees()
    print("    angle after +90deg: %.2fdeg" % a)
    check("rotate 90deg CW", approx(a, 90.0))

    # 3. rotate 90deg CCW -> back to 0deg
    m.rotate_degrees(90, direction=-1)
    a = m.get_position_degrees()
    print("    angle after -90deg: %.2fdeg" % a)
    check("rotate 90deg CCW returns to 0deg", approx(a, 0.0))

    # 4. full 0->180 sweep
    m.scan(0, 180, speed_rpm=8)
    a = m.get_position_degrees()
    print("    angle after sweep: %.2fdeg" % a)
    check("0->180deg sweep completes", approx(a, 180.0))

    # 5. position tracking: 45deg x 4 == 180deg
    m.reset_position()
    for _ in range(4):
        m.rotate_degrees(45, direction=1)
    a = m.get_position_degrees()
    print("    angle after 4x45deg: %.2fdeg" % a)
    check("position tracking (4x45deg==180deg)", approx(a, 180.0))

    # 6. limit clamp (no slip ring -> can't exceed 180deg)
    m.rotate_to(270)
    a = m.get_position_degrees()
    check("travel clamp <=180deg (no slip ring)", a <= 180.0 + 0.2, "got %.1fdeg" % a)

    # 7. auto-sleep after the idle window
    m.center(speed_rpm=8)
    m.enable()
    print("    waiting %.0fs for auto-sleep..." % (m.auto_sleep_s + 1))
    time.sleep(m.auto_sleep_s + 1)
    slept = m.maybe_auto_sleep()
    check("auto-sleep after idle", slept and m._asleep)

    # 8. wake then step
    m.wake()
    before = m.get_position_degrees()
    m.rotate_degrees(10, direction=1)
    check("wake + step", (not m._asleep) and not approx(m.get_position_degrees(), before, 0.05))

    # 9. cleanup
    try:
        m.cleanup()
        check("cleanup releases GPIO", True)
    except Exception as e:  # noqa: BLE001
        check("cleanup releases GPIO", False, str(e))

    print("=== %d passed, %d failed ===" % (_passed, _failed))

    # The checks above pass on software step-counting alone — they cannot tell
    # whether the shaft actually turned. Make the verdict say which it was so a
    # mock run is never mistaken for a working motor.
    if m.mock:
        on_pi = sys.platform.startswith("linux")
        print("")
        print("  !! MOCK MODE: NO GPIO WAS DRIVEN. The motor was never told to")
        print("     move; the PASSes above only verify the math/timing, not motion.")
        if on_pi:
            print("     You're on Linux (a Pi?) but gpiozero/lgpio wasn't usable, so")
            print("     this is almost certainly why your stepper isn't moving. Fix:")
            print("       sudo apt install python3-lgpio")
            print("       pip install gpiozero lgpio   # into the env running this")
            print("     then re-run -- the config line above should read mock=False.")
            print("=== VERDICT: NOT VERIFIED ON HARDWARE (mock on a Pi) ===")
            return 2
        print("     (Expected off-Pi: this was a dry run. Run it on the Pi to move"
              " the motor.)")
        return 0 if _failed == 0 else 1

    # Real GPIO path: pins really toggled. If the bar still didn't move, it's
    # electrical, and this test cannot detect that -- point at the usual causes.
    print("")
    print("  Real GPIO was driven. If the bar PHYSICALLY MOVED, you're good.")
    print("  If it did NOT move (a passing test can't tell), check, in order:")
    print("    1. RESET pin -- must be HIGH. Jumper A4988 RESET->SLEEP, or set")
    print("       stepper.reset_pin in config.yaml. (Most common cause.)")
    print("    2. VMOT -- 8-35 V motor supply present, ~100 uF cap across VMOT/GND.")
    print("    3. VREF -- current-limit pot not turned to zero.")
    print("    4. Coil wiring -- each pair (1A/1B, 2A/2B) not split/swapped.")
    return 0 if _failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
