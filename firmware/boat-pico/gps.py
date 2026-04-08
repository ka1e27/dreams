"""GPS NMEA parser for UART1.

Extracted from reference/Boat_pico.py _process_line() GPS parsing.
Reads $GPRMC / $GNRMC sentences from the GPS module.

Pin assignments:
  - GPS TX → Pico RX: GP5
  - GPS RX ← Pico TX: GP4
  - Baud: 9600
"""
from machine import UART, Pin
import time

_uart = None
_buf = bytearray(128)
_pos = 0

# Parsed state
lat = 0.0
lon = 0.0
speed_knots = 0.0
fix_valid = False
last_fix_ms = 0

# Health tracking
_fail_count = 0
_FAIL_THRESHOLD = 10
_STALE_MS = 3000


def init():
    """Initialise GPS UART. Call once at startup."""
    global _uart
    try:
        _uart = UART(1, baudrate=9600, tx=Pin(4), rx=Pin(5))
    except Exception as e:
        print("gps init error: %s" % e)


def _parse_rmc(line):
    """Parse a $GPRMC or $GNRMC sentence and update state."""
    global lat, lon, speed_knots, fix_valid, last_fix_ms, _fail_count
    try:
        parts = line.split(',')
        if len(parts) < 8:
            return
        if parts[2] != 'A':
            fix_valid = False
            return
        # Latitude: DDMM.MMMM
        raw = float(parts[3])
        deg = int(raw / 100)
        lat_val = deg + (raw - deg * 100) / 60.0
        if parts[4] == 'S':
            lat_val = -lat_val
        # Longitude: DDDMM.MMMM
        raw = float(parts[5])
        deg = int(raw / 100)
        lon_val = deg + (raw - deg * 100) / 60.0
        if parts[6] == 'W':
            lon_val = -lon_val
        # Speed
        spd_val = float(parts[7]) if parts[7] else 0.0

        lat = lat_val
        lon = lon_val
        speed_knots = spd_val
        fix_valid = True
        last_fix_ms = time.ticks_ms()
        _fail_count = 0
    except:
        _fail_count += 1


def _process_byte(b):
    """Feed one byte into the line buffer. Parse complete lines."""
    global _pos
    if b == 0x0A:  # newline
        if _pos > 0:
            try:
                line = _buf[:_pos].decode('utf-8', 'ignore').strip()
                if line and (line[:4] in ('$GPR', '$GNR')):
                    _parse_rmc(line)
            except:
                pass
        _pos = 0
    elif b == 0x24:  # '$' — start of sentence
        _pos = 0
        _buf[0] = b
        _pos = 1
    elif _pos < 128:
        _buf[_pos] = b
        _pos += 1


def read():
    """Read all available bytes from GPS UART and parse them.

    Call this frequently from the main loop (~10Hz).
    """
    if _uart is None:
        return
    while _uart.any():
        chunk = _uart.read()
        if not chunk:
            break
        for b in chunk:
            _process_byte(b)


def is_valid():
    """Return True if we have a recent valid fix."""
    if not fix_valid:
        return False
    if last_fix_ms == 0:
        return True
    return time.ticks_diff(time.ticks_ms(), last_fix_ms) <= _STALE_MS


def is_stale():
    """Return True if the last fix is older than the stale threshold."""
    if last_fix_ms == 0:
        return True
    return time.ticks_diff(time.ticks_ms(), last_fix_ms) > _STALE_MS


def is_healthy():
    """Return True if the GPS is producing valid fixes."""
    return fix_valid and _fail_count < _FAIL_THRESHOLD and not is_stale()
