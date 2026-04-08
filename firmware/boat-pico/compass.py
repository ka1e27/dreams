"""QMC5883P compass driver over I2C.

Extracted from reference/Boat_pico.py init_compass() and read_compass().
The QMC5883P is at I2C address 0x2C (not the usual 0x0D for QMC5883L).

Pin assignments:
  - SDA: GP8
  - SCL: GP9
  - Freq: 100kHz
"""
from machine import I2C, Pin
import math
import time

QMC_ADDR = 0x2C
RAD_TO_DEG = 180.0 / math.pi

_i2c = None

# Calibration offsets
_x_off = 0
_y_off = 0
_hdg_off = 130  # Default heading offset from reference code

# Parsed state
heading = 0.0

# Health tracking
_fail_count = 0
_FAIL_THRESHOLD = 10
_last_read_ms = 0
_TIMEOUT_MS = 5000


def init():
    """Initialise I2C and configure the QMC5883P. Returns True on success."""
    global _i2c, _fail_count
    try:
        _i2c = I2C(0, sda=Pin(8), scl=Pin(9), freq=100000)
    except:
        return False
    try:
        # Control register 1: continuous mode, 200Hz, 2G range, 512 OSR
        _i2c.writeto_mem(QMC_ADDR, 0x09, b'\x3d')
        # SET/RESET period register
        _i2c.writeto_mem(QMC_ADDR, 0x0a, b'\x01')
        _fail_count = 0
        return True
    except:
        _fail_count += 1
        return False


def read():
    """Read compass heading from the QMC5883P. Call from main loop (~10Hz)."""
    global heading, _fail_count, _last_read_ms
    if _i2c is None:
        _fail_count += 1
        return
    try:
        data = _i2c.readfrom_mem(QMC_ADDR, 0x01, 6)
        x = data[0] | (data[1] << 8)
        y = data[2] | (data[3] << 8)
        # Convert unsigned to signed 16-bit
        if x > 32767:
            x -= 65536
        if y > 32767:
            y -= 65536
        # Apply hard-iron offsets
        x -= _x_off
        y -= _y_off
        # Calculate heading
        h = math.atan2(y, x) * RAD_TO_DEG
        if h < 0:
            h += 360.0
        heading = (h - _hdg_off) % 360.0
        _fail_count = 0
        _last_read_ms = time.ticks_ms()
    except:
        _fail_count += 1


def calibrate_north(true_bearing):
    """Set the heading offset so that the current reading matches true_bearing.

    Args:
        true_bearing: The known true bearing (0–359.9°) the boat is currently facing.

    Returns:
        (success, new_hdg_off) tuple.
    """
    global _hdg_off
    if not (0 <= true_bearing < 360):
        return False, _hdg_off
    raw_hdg = (heading + _hdg_off) % 360.0
    _hdg_off = (raw_hdg - true_bearing) % 360.0
    return True, _hdg_off


def get_hdg_off():
    """Return the current heading offset."""
    return _hdg_off


def is_healthy():
    """Return True if compass is producing valid readings."""
    if _fail_count >= _FAIL_THRESHOLD:
        return False
    if _last_read_ms == 0:
        return False
    return time.ticks_diff(time.ticks_ms(), _last_read_ms) <= _TIMEOUT_MS


def scan_bus():
    """Scan I2C bus and return list of detected addresses."""
    if _i2c is None:
        return []
    try:
        return _i2c.scan()
    except:
        return []
