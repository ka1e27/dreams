"""Motor control via ESC PWM signals.

Extracted from reference/Boat_pico.py. Drives left, right, and winch motors
through ESCs using 50Hz PWM with duty_u16 values.

Pin assignments:
  - Left motor:  GP6
  - Right motor: GP7
  - Winch motor: GP14

Note: GP0/GP1 are dead — do not use.
"""
from machine import Pin, PWM

# ESC PWM duty_u16 values (50Hz servo-style signal)
STOP_PWM = 4915
MIN_PWM = 3277
MAX_PWM = 6553
FWD_RANGE = MAX_PWM - STOP_PWM  # 1638
REV_RANGE = STOP_PWM - MIN_PWM  # 1638

# Pin assignments
ML_PIN = 6
MR_PIN = 7
MW_PIN = 14

# Pulley compensation ratios (mechanical asymmetry)
PULLEY_L = 18.0 / 27.0
PULLEY_R = 15.0 / 30.0
COMP_L = PULLEY_R / PULLEY_L
COMP_R = 1.0

# Runtime state
_ml = None
_mr = None
_mw = None
_trim = 0.0
_throttle_mult = 1.0
_rc_override = False
_estop_active = False

# Current commanded speeds (-100 to 100)
_ml_spd = 0
_mr_spd = 0
_mw_spd = 0


def init():
    """Initialise PWM on all motor pins. Call once at startup."""
    global _ml, _mr, _mw
    try:
        _ml = PWM(Pin(ML_PIN)); _ml.freq(50)
        _mr = PWM(Pin(MR_PIN)); _mr.freq(50)
        _mw = PWM(Pin(MW_PIN)); _mw.freq(50)
        _set_pwm(_ml, 0)
        _set_pwm(_mr, 0)
        _set_pwm(_mw, 0)
    except Exception as e:
        print("motor_control init error: %s" % e)


def _set_pwm(motor, spd):
    """Convert speed percentage to ESC duty_u16 and apply."""
    if motor is None:
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
        motor.duty_u16(duty)
    except:
        pass


def set_throttle(left, right):
    """Set left and right motor speeds (-100 to 100).

    Applies pulley compensation, trim, and throttle multiplier.
    Rejected if RC override or ESTOP is active.
    Returns (success, reason).
    """
    global _ml_spd, _mr_spd
    if _rc_override:
        return False, "RC_ACTIVE"
    if _estop_active:
        return False, "ESTOP"
    if not (-100 <= left <= 100 and -100 <= right <= 100):
        return False, "RANGE"
    _ml_spd = left
    _mr_spd = right
    return True, None


def set_winch(speed):
    """Set winch motor speed (-100 to 100). Positive = down, negative = up.

    Rejected if RC override or ESTOP is active.
    Returns (success, reason).
    """
    global _mw_spd
    if _rc_override:
        return False, "RC_ACTIVE"
    if _estop_active:
        return False, "ESTOP"
    if not (-100 <= speed <= 100):
        return False, "RANGE"
    _mw_spd = speed
    return True, None


def update():
    """Apply current speeds to motor PWM outputs. Call from main loop (~10Hz)."""
    if _rc_override or _estop_active:
        return
    eff_l = int(_ml_spd * _throttle_mult * (COMP_L + _trim))
    eff_r = int(_mr_spd * _throttle_mult * (COMP_R - _trim))
    _set_pwm(_ml, eff_l)
    _set_pwm(_mr, eff_r)
    _set_pwm(_mw, _mw_spd)


def estop():
    """Emergency stop — kill all motors immediately."""
    global _estop_active, _ml_spd, _mr_spd, _mw_spd
    _estop_active = True
    _ml_spd = 0
    _mr_spd = 0
    _mw_spd = 0
    _set_pwm(_ml, 0)
    _set_pwm(_mr, 0)
    _set_pwm(_mw, 0)


def resume():
    """Re-enable motor commands after an ESTOP."""
    global _estop_active
    _estop_active = False


def is_estopped():
    """Return True if ESTOP is active."""
    return _estop_active


def rc_override_on():
    """Enter RC passthrough mode — deinit PWM so RC receiver takes over."""
    global _rc_override, _ml, _mr, _mw, _ml_spd, _mr_spd, _mw_spd
    _ml_spd = 0
    _mr_spd = 0
    _mw_spd = 0
    try:
        if _ml: _ml.deinit()
        if _mr: _mr.deinit()
        if _mw: _mw.deinit()
    except:
        pass
    Pin(ML_PIN, Pin.IN)
    Pin(MR_PIN, Pin.IN)
    Pin(MW_PIN, Pin.IN)
    _ml = None
    _mr = None
    _mw = None
    _rc_override = True


def rc_override_off():
    """Exit RC passthrough — re-init PWM."""
    global _rc_override, _ml, _mr, _mw
    try:
        _ml = PWM(Pin(ML_PIN)); _ml.freq(50)
        _mr = PWM(Pin(MR_PIN)); _mr.freq(50)
        _mw = PWM(Pin(MW_PIN)); _mw.freq(50)
        _set_pwm(_ml, 0)
        _set_pwm(_mr, 0)
        _set_pwm(_mw, 0)
    except Exception as e:
        print("rc_override_off error: %s" % e)
    _rc_override = False


def is_rc_override():
    """Return True if RC override is active."""
    return _rc_override


def set_trim(value):
    """Set motor trim (-0.5 to 0.5). Returns (success, comp_l, comp_r)."""
    global _trim
    if not (-0.5 <= value <= 0.5):
        return False, 0, 0
    _trim = value
    return True, COMP_L + _trim, COMP_R - _trim


def get_trim():
    """Return (trim, comp_l, comp_r)."""
    return _trim, COMP_L + _trim, COMP_R - _trim


def set_throttle_mult(mult):
    """Set throttle multiplier (0.0–1.0) for thermal throttling."""
    global _throttle_mult
    _throttle_mult = max(0.0, min(1.0, mult))


def get_speeds():
    """Return current commanded speeds (left, right, winch)."""
    return _ml_spd, _mr_spd, _mw_spd


def get_state():
    """Return (rc_override, estop_active) for status reporting."""
    return _rc_override, _estop_active
