"""UART poll-response handler for the underwater sensor pod.

Listens for $POLL*cs\\n commands from the Boat Pico and responds with
sensor data in the format: $POD,temp,ec,light_pct,bottom,leak*cs\\n

Pin assignments:
  - TX: GP0
  - RX: GP1
  - Baud: 9600
"""
from machine import Pin, UART
import time

_uart = None
_rx_buf = bytearray(64)
_rx_pos = 0

# Reference to sensor and leak modules (set by init)
_sensors = None
_leak = None


def _xor_cs(s):
    """XOR checksum over a string."""
    c = 0
    for ch in s:
        c ^= ord(ch)
    return c


def init(sensors_module, leak_module):
    """Initialise UART and set sensor module references.

    Args:
        sensors_module: The sensors module (provides water_temp, salinity_ec, etc.)
        leak_module: The leak_detect module (provides leak_detected flag)
    """
    global _uart, _sensors, _leak
    _sensors = sensors_module
    _leak = leak_module
    try:
        _uart = UART(0, baudrate=9600, tx=Pin(0), rx=Pin(1))
    except Exception as e:
        print("uart_responder init error: %s" % e)


def _send_response():
    """Build and send a POD response with current sensor data."""
    if _uart is None or _sensors is None:
        return
    btm = 1 if _sensors.bottom_contact else 0
    lk = 1 if (_leak is not None and _leak.leak_detected) else 0
    msg = "POD,%.1f,%.1f,%d,%d,%d" % (
        _sensors.water_temp, _sensors.salinity_ec,
        _sensors.light_pct, btm, lk)
    _uart.write("$%s*%d\n" % (msg, _xor_cs(msg)))


def read():
    """Read incoming bytes and respond to POLL commands.

    Call this frequently from the main loop.
    """
    global _rx_pos
    if _uart is None:
        return
    found = False
    while _uart.any():
        b_data = _uart.read(1)
        if not b_data:
            break
        ch = b_data[0]
        if ch == 0x0A:  # newline — end of frame
            if _rx_pos > 4:
                try:
                    line = _rx_buf[:_rx_pos].decode('utf-8', 'ignore').strip()
                    if line and line[0] == '$' and '*' in line:
                        payload, cs_str = line[1:].rsplit('*', 1)
                        if payload == "POLL" and _xor_cs(payload) == int(cs_str):
                            found = True
                except:
                    pass
            _rx_pos = 0
        elif ch == 0x24:  # '$' — start of frame
            _rx_pos = 0
            _rx_buf[0] = ch
            _rx_pos = 1
        elif _rx_pos < 64:
            _rx_buf[_rx_pos] = ch
            _rx_pos += 1

    if found:
        _send_response()
    return found
