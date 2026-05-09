"""GPS NMEA parser for UART1 — currently a u-blox M10Q.

Reads $GPRMC / $GNRMC sentences. Wire-compatible with the previous generic
NMEA module; M10Q swap is just a hardware change plus an optional UBX
configuration burst at boot to silence sentences we don't use.

Pin assignments:
  - GPS TX → Pico RX: GP5
  - GPS RX ← Pico TX: GP4
  - Baud: 9600

Note: the Pod Pico shares this UART. Sentence routing happens in main.py's
task_uart1_reader (lines starting with $GP/$GN go here, $POD lines go to
pod_uart).
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


# ---- M10Q configuration helpers (UBX-CFG-VALSET) ----
#
# We keep RMC + GGA enabled and silence GLL, GSV, GSA, VTG. This frees a
# meaningful chunk of the 9600-baud UART (which is also shared with the
# pod) and shaves CPU off the parser.
#
# UBX frame: 0xB5 0x62 | class | id | len_lo len_hi | payload | ck_a ck_b
# CFG-VALSET: class=0x06 id=0x8A. Each item is keyId (4 bytes LE) + value.
# Setting NMEA-output-rate keys to 0 disables the sentence on UART1.

_UBX_KEYS_DISABLE = (
    0x209100CA,  # CFG-MSGOUT-NMEA_ID_GLL_UART1
    0x209100C5,  # CFG-MSGOUT-NMEA_ID_GSA_UART1
    0x209100CF,  # CFG-MSGOUT-NMEA_ID_GSV_UART1
    0x209100B1,  # CFG-MSGOUT-NMEA_ID_VTG_UART1
)


def _ubx_checksum(payload):
    a = 0
    b = 0
    for x in payload:
        a = (a + x) & 0xff
        b = (b + a) & 0xff
    return a, b


def _send_ubx(cls, msg_id, payload):
    if _uart is None:
        return
    n = len(payload)
    body = bytes((cls, msg_id, n & 0xff, (n >> 8) & 0xff)) + bytes(payload)
    a, b = _ubx_checksum(body)
    frame = bytes((0xB5, 0x62)) + body + bytes((a, b))
    try:
        _uart.write(frame)
    except:
        pass


def _configure_m10q():
    """Disable unused NMEA sentences. Best-effort — no ACK parsing."""
    # CFG-VALSET: version=0, layer=1 (RAM only), reserved=0,0
    header = bytes((0x00, 0x01, 0x00, 0x00))
    items = b''
    for key in _UBX_KEYS_DISABLE:
        items += bytes((
            key & 0xff, (key >> 8) & 0xff,
            (key >> 16) & 0xff, (key >> 24) & 0xff,
            0x00,  # value: 0 = disable
        ))
    _send_ubx(0x06, 0x8A, header + items)


def init():
    """Initialise GPS UART. Call once at startup."""
    global _uart
    try:
        _uart = UART(1, baudrate=9600, tx=Pin(4), rx=Pin(5))
    except Exception as e:
        print("gps init error: %s" % e)
        return
    # Give the M10Q a moment to be ready, then push the disable burst.
    try:
        time.sleep_ms(200)
        _configure_m10q()
    except:
        pass


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
