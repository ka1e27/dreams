"""Drive ESCs — two standard hobby ESCs on 50 Hz servo PWM (single-hull test bench).

Test-bench variant of the propulsion driver. Replaces the VESC / CAN-chain
propulsion (`vesc.py`, unused on this branch) with two dumb hobby ESCs — one per
stern motor — driven directly by the Pico as 50 Hz servo-style PWM, the same
signal the winch ESC already uses. Differential steering is computed upstream in
`motor_control.py` exactly as before; this module only turns a -1.0..+1.0 duty
into an ESC pulse and drives the pin.

Pins:
  - Left  ESC  → GP2 (free RP2040 GPIO, PWM slice 1 ch A)
  - Right ESC  → GP3 (free RP2040 GPIO, PWM slice 1 ch B)

The as-built Boat PCB routes GP12-15 to the two SHT41 temp connectors (J11/J13),
which this variant KEEPS, so propulsion moves to free Pico header pins instead of
reusing the old VESC UART0 pins (GP12/GP13). GP2/GP3 have no PCB connector — the
test bench taps them directly on the Pico breakout header. Both drive ESCs share
PWM slice 1 (channels A/B): same 50 Hz frequency, independent duty — which is
exactly what two ESCs need. See docs/hardware_changes_v2_to_testbench.md.

Test-bench ESCs: NeutronRC 70A-G071 (STM32G071, AM32 firmware, 2-8S). AM32 is
configurable firmware, not a "dumb" ESC — it auto-detects the 50 Hz servo PWM
signal this module sends, and it supports a REVERSIBLE (bidirectional) mode, so
the negative-throttle pivots/avoidance the navigator commands actually reverse
the inner motor. See docs/esc_setup.md for the required AM32 configuration.

⚠ Safety: the ESC holds the last pulse if commands stop (AM32's own signal-loss
  behaviour aside). The primary safety net is the Pico's heartbeat watchdog
  (watchdog.py, 3 s) → motor_control.estop() → this module drives both ESCs back
  to neutral.

Servo-PWM pulse range (shared with the winch ESC), with AM32 bidirectional mode:
  1.0 ms = full reverse, 1.5 ms = neutral/stop, 2.0 ms = full forward, at 50 Hz.
⚠ Reverse only works with AM32 **Bi-directional mode enabled** (docs/esc_setup.md).
  With it off the ESC is forward-only and a <1.5 ms pulse just idles — the boat
  then can't pivot in place or reverse to bear away. Confirm before first spin-up.

Note: GP0/GP1 are dead — do not use.
"""
from machine import Pin, PWM

import esc_telem

# Motor IDs — kept identical to vesc.py so motor_control.py stays a drop-in.
LEFT = 0
RIGHT = 1

# ESC signal pins (free Pico header pins; GP12-15 are the SHT41 temp sensors)
LEFT_PIN = 2
RIGHT_PIN = 3

# 50 Hz servo PWM in the duty_u16 domain (same mapping as the winch ESC in
# motor_control.py). 65535 counts per 20 ms period → ~3.277 counts / µs.
STOP_PWM = 4915                 # ~1.5 ms neutral
MIN_PWM = 3277                  # ~1.0 ms full reverse
MAX_PWM = 6553                  # ~2.0 ms full forward
FWD_RANGE = MAX_PWM - STOP_PWM  # 1638
REV_RANGE = STOP_PWM - MIN_PWM  # 1638

# PWM handles per motor
_pwm = {LEFT: None, RIGHT: None}


def init():
    """Create both ESC PWM channels at 50 Hz and arm them at neutral.

    Returns True only if BOTH channels initialised. A False return means at
    least one ESC has no PWM handle, so set_duty()/stop() — including the ESTOP
    kill path — cannot drive it. The caller must surface that (and not arm),
    since a dumb ESC has no self-timeout to fall back on.
    """
    global _pwm
    for mid, pin in ((LEFT, LEFT_PIN), (RIGHT, RIGHT_PIN)):
        try:
            p = PWM(Pin(pin))
            p.freq(50)
            _pwm[mid] = p
        except Exception as e:
            print("escs init error (motor %d): %s" % (mid, e))
            _pwm[mid] = None
    # Send neutral so the ESCs arm on a valid stop pulse immediately.
    set_duty(LEFT, 0.0)
    set_duty(RIGHT, 0.0)
    return ready()


def ready():
    """True iff both ESC PWM channels are live (i.e. the kill path can drive them)."""
    return _pwm[LEFT] is not None and _pwm[RIGHT] is not None


def _duty_to_pwm(duty):
    """Map duty -1.0..+1.0 to an ESC pulse in the duty_u16 domain."""
    if duty > 1.0:
        duty = 1.0
    elif duty < -1.0:
        duty = -1.0
    if duty >= 0:
        return STOP_PWM + int(FWD_RANGE * duty)
    return STOP_PWM + int(REV_RANGE * duty)


def set_duty(motor_id, duty):
    """Drive one ESC. `duty` in -1.0..+1.0 (positive = forward)."""
    p = _pwm.get(motor_id)
    if p is None:
        return
    try:
        p.duty_u16(_duty_to_pwm(duty))
    except:
        pass


def stop():
    """Neutral both ESCs immediately."""
    set_duty(LEFT, 0.0)
    set_duty(RIGHT, 0.0)


# ---- Telemetry -------------------------------------------------------------
# AM32 ESCs emit KISS telemetry on their TX pad; esc_telem.py receives it (PIO
# UART RX) and these accessors delegate to it, so main.py's VESC-shaped telemetry
# / watchdog / health-string / LED code lights up unchanged. When no telemetry is
# wired or arriving, the getters return None / 0.0 (the old "dumb ESC" behaviour),
# so nothing false-trips. esc_telem.init() / poll() are driven from main.py.

def get_motor_temp(motor_id):
    """ESC/FET temperature (°C) from KISS telemetry, or None if none fresh."""
    return esc_telem.temperature(motor_id)


def get_fet_temp(motor_id):
    # KISS telemetry reports a single temperature; expose it as both.
    return esc_telem.temperature(motor_id)


def get_current(motor_id):
    """Motor current (A) from KISS telemetry, or None if none fresh."""
    return esc_telem.current(motor_id)


def get_v_in(motor_id):
    """ESC-sensed rail voltage (V) from KISS telemetry, or None if none fresh."""
    return esc_telem.voltage(motor_id)


def get_fault(motor_id):
    # KISS telemetry carries no discrete fault code; 0 = no fault reported.
    return 0


def max_motor_temp():
    """Hottest fresh ESC temperature, or 0.0 when no telemetry (never trips)."""
    return esc_telem.max_temp()


def is_telemetry_fresh(motor_id, max_age_ms=2000):
    return esc_telem.is_fresh(motor_id, max_age_ms)


def poll_rx():
    """Drain the telemetry RX FIFOs (delegates to esc_telem.poll())."""
    esc_telem.poll()


def request_values(motor_id):
    """No-op: KISS telemetry is streamed by the ESC, not requested."""
    pass


def request_values_round_robin():
    """No-op: KISS telemetry is streamed by the ESC, not requested."""
    pass
