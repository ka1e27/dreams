"""Pod UART bridge — poll/response forwarding to underwater sensor pod.

The Pod Pico is connected to Boat Pico's UART1 (shared with GPS).
This module sends POLL commands and parses POD responses.

The pod responds with: $POD,temp,ec,light_pct,bottom,leak,pressure_depth_m*cs\n

Pin assignments (shared with GPS on UART1):
  - TX: GP4
  - RX: GP5
  - Baud: 9600
"""
import time

# Pod data
water_temp = -999.0
salinity_ec = 0.0
light_pct = 0
bottom_contact = False
leak_detected = False
pressure_depth_m = 0.0

# State
pod_ok = False
last_response_ms = 0
_TIMEOUT_MS = 10000
_POLL_INTERVAL_MS = 5000
_last_poll_ms = 0

# Reference to shared GPS UART (set by init)
_uart = None


def init(uart):
    """Set the UART reference. Shares UART1 with GPS module.

    Args:
        uart: The machine.UART instance (UART1) also used by gps.py.
    """
    global _uart
    _uart = uart


def _xor_cs(s):
    """XOR checksum over a string."""
    c = 0
    for ch in s:
        c ^= ord(ch)
    return c


def poll():
    """Send a POLL command to the pod. Call periodically from main loop."""
    global _last_poll_ms
    if _uart is None:
        return
    now = time.ticks_ms()
    if time.ticks_diff(now, _last_poll_ms) < _POLL_INTERVAL_MS:
        return
    _last_poll_ms = now
    try:
        msg = "POLL"
        _uart.write("$%s*%d\n" % (msg, _xor_cs(msg)))
    except:
        pass


def process_line(line):
    """Parse a $POD response line. Called by the shared UART reader.

    Args:
        line: Raw line string starting with '$'.

    Returns:
        True if this was a valid POD message, False otherwise.
    """
    global water_temp, salinity_ec, light_pct, bottom_contact
    global pod_ok, last_response_ms, leak_detected, pressure_depth_m
    if not line or len(line) < 5:
        return False
    if line[1:4] != 'POD':
        return False
    try:
        if '*' not in line:
            return False
        payload, cs_str = line[1:].rsplit('*', 1)
        cs_calc = 0
        for ch in payload:
            cs_calc ^= ord(ch)
        if cs_calc != int(cs_str):
            return False
        parts = payload.split(',')
        if len(parts) >= 5:
            water_temp = float(parts[1])
            salinity_ec = float(parts[2])
            light_pct = int(parts[3])
            bottom_contact = parts[4] == '1'
            if len(parts) >= 6:
                leak_detected = parts[5] == '1'
            if len(parts) >= 7:
                pressure_depth_m = float(parts[6])
            pod_ok = True
            last_response_ms = time.ticks_ms()
            return True
    except:
        pass
    return False


def is_healthy():
    """Return True if pod is responding within timeout."""
    if not pod_ok:
        return False
    if last_response_ms == 0:
        return False
    return time.ticks_diff(time.ticks_ms(), last_response_ms) <= _TIMEOUT_MS


def is_stale():
    """Return True if pod data is older than timeout."""
    if last_response_ms == 0:
        return True
    return time.ticks_diff(time.ticks_ms(), last_response_ms) > _TIMEOUT_MS


def get_data():
    """Return current pod sensor readings as a dict."""
    return {
        "water_temp": water_temp,
        "salinity_ec": salinity_ec,
        "light_pct": light_pct,
        "bottom": bottom_contact,
        "leak": leak_detected,
        "pressure_depth_m": pressure_depth_m,
        "ok": pod_ok
    }
