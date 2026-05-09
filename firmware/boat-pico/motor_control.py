"""Motor control — VESC over UART for propulsion, PWM ESC for the winch.

Propulsion:
  - Left + right motors driven by two VESCs: master on UART0 (GP12/GP13),
    slave reached via CAN forward through the master.
  - Throttle range -100..+100 percent maps to duty -1.0..+1.0 after applying
    pulley compensation, trim, and the thermal throttle multiplier.

Winch:
  - Standard hobby ESC on GP14, 50 Hz PWM. Unchanged from the prior design.
  - Spool can be swapped mechanically to repurpose the winch as a fishing
    reel; firmware behavior is identical regardless.

RC override:
  - rc_override_on()/off() flips a software flag. While active, main.py's
    motor task feeds SBUS channel values directly into set_throttle() and
    set_winch() instead of using navigator commands. Prior firmware
    deinit-ed the PWM pins so a receiver could hijack them — that doesn't
    work with VESCs over UART, so the path is now Pico-mediated.

Note: GP0/GP1 are dead — do not use.
"""
from machine import Pin, PWM
import vesc

# ---- Winch PWM (unchanged) ----
STOP_PWM = 4915
MIN_PWM = 3277
MAX_PWM = 6553
FWD_RANGE = MAX_PWM - STOP_PWM  # 1638
REV_RANGE = STOP_PWM - MIN_PWM  # 1638

MW_PIN = 14

# Pulley compensation (applies to propulsion only)
PULLEY_L = 18.0 / 27.0
PULLEY_R = 15.0 / 30.0
COMP_L = PULLEY_R / PULLEY_L
COMP_R = 1.0

# Runtime state
_mw = None
_trim = 0.0
_throttle_mult = 1.0
_rc_active = False
_estop_active = False

# Current commanded speeds (-100..100)
_ml_spd = 0
_mr_spd = 0
_mw_spd = 0


def init():
    """Initialise winch PWM and the VESC UART. Call once at startup."""
    global _mw
    try:
        _mw = PWM(Pin(MW_PIN))
        _mw.freq(50)
        _set_winch_pwm(0)
    except Exception as e:
        print("motor_control init error (winch): %s" % e)
    try:
        vesc.init()
        # Send a zero-duty so the VESCs know we're alive immediately.
        vesc.set_duty(vesc.LEFT, 0.0)
        vesc.set_duty(vesc.RIGHT, 0.0)
    except Exception as e:
        print("motor_control init error (vesc): %s" % e)


def _set_winch_pwm(spd):
    """Convert -100..100 to ESC duty_u16 and apply to the winch."""
    if _mw is None:
        return
    if spd > 100:
        spd = 100
    elif spd < -100:
        spd = -100
    if spd >= 0:
        duty = STOP_PWM + FWD_RANGE * spd // 100
    else:
        duty = STOP_PWM + REV_RANGE * spd // 100
    try:
        _mw.duty_u16(duty)
    except:
        pass


def set_throttle(left, right):
    """Set propulsion motor speeds (-100..100). Returns (success, reason).

    Pi 5's commanded throttle path. Rejected during RC override or ESTOP.
    The SBUS forwarder uses set_throttle_rc() to bypass the RC gate.
    """
    global _ml_spd, _mr_spd
    if _rc_active:
        return False, "RC_ACTIVE"
    if _estop_active:
        return False, "ESTOP"
    if not (-100 <= left <= 100 and -100 <= right <= 100):
        return False, "RANGE"
    _ml_spd = left
    _mr_spd = right
    return True, None


def set_winch(speed):
    """Set winch speed (-100..100). Positive = down/deploy, negative = up.

    Pi 5's commanded path. Rejected during RC override or ESTOP. The SBUS
    forwarder uses set_winch_rc() to bypass the RC gate.
    """
    global _mw_spd
    if _rc_active:
        return False, "RC_ACTIVE"
    if _estop_active:
        return False, "ESTOP"
    if not (-100 <= speed <= 100):
        return False, "RANGE"
    _mw_spd = speed
    return True, None


def set_throttle_rc(left, right):
    """SBUS forwarder entry point — bypasses the RC gate. ESTOP still wins."""
    global _ml_spd, _mr_spd
    if _estop_active:
        return
    _ml_spd = max(-100, min(100, int(left)))
    _mr_spd = max(-100, min(100, int(right)))


def set_winch_rc(speed):
    """SBUS forwarder entry for winch — bypasses the RC gate."""
    global _mw_spd
    if _estop_active:
        return
    _mw_spd = max(-100, min(100, int(speed)))


def update():
    """Apply commanded speeds to VESC + winch PWM. Call from main loop (~10 Hz).

    Streaming this at 10 Hz keeps the VESCs' own command-timeout watchdog
    fed; if Pico goes silent for ~1 s the VESCs cut motor current.
    """
    if _estop_active:
        return
    eff_l = _ml_spd * _throttle_mult * (COMP_L + _trim)
    eff_r = _mr_spd * _throttle_mult * (COMP_R - _trim)
    # Convert percent to duty -1.0..+1.0
    duty_l = max(-1.0, min(1.0, eff_l / 100.0))
    duty_r = max(-1.0, min(1.0, eff_r / 100.0))
    try:
        vesc.set_duty(vesc.LEFT, duty_l)
        vesc.set_duty(vesc.RIGHT, duty_r)
    except:
        pass
    _set_winch_pwm(_mw_spd)


def estop():
    """Emergency stop — kill all motors immediately."""
    global _estop_active, _ml_spd, _mr_spd, _mw_spd
    _estop_active = True
    _ml_spd = 0
    _mr_spd = 0
    _mw_spd = 0
    try:
        vesc.set_duty(vesc.LEFT, 0.0)
        vesc.set_duty(vesc.RIGHT, 0.0)
    except:
        pass
    _set_winch_pwm(0)


def resume():
    """Re-enable motor commands after an ESTOP."""
    global _estop_active
    _estop_active = False


def is_estopped():
    return _estop_active


def rc_override_on():
    """Enter RC passthrough mode. main.py's motor task will read SBUS and
    forward channel values into set_throttle/set_winch."""
    global _rc_active, _ml_spd, _mr_spd, _mw_spd
    _ml_spd = 0
    _mr_spd = 0
    _mw_spd = 0
    _rc_active = True


def rc_override_off():
    """Exit RC passthrough mode."""
    global _rc_active, _ml_spd, _mr_spd, _mw_spd
    _ml_spd = 0
    _mr_spd = 0
    _mw_spd = 0
    _rc_active = False


def is_rc_override():
    return _rc_active


def set_trim(value):
    """Set motor trim (-0.5..0.5). Returns (success, comp_l, comp_r)."""
    global _trim
    if not (-0.5 <= value <= 0.5):
        return False, 0, 0
    _trim = value
    return True, COMP_L + _trim, COMP_R - _trim


def get_trim():
    return _trim, COMP_L + _trim, COMP_R - _trim


def set_throttle_mult(mult):
    """Set throttle multiplier (0.0–1.0) for thermal throttling."""
    global _throttle_mult
    _throttle_mult = max(0.0, min(1.0, mult))


def get_speeds():
    return _ml_spd, _mr_spd, _mw_spd


def get_state():
    return _rc_active, _estop_active
