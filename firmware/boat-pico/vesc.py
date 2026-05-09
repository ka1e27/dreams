"""VESC UART driver — drives the master VESC and forwards to a slave over CAN.

The Pico talks to the master VESC over UART0 (GP12/GP13) at 115200 baud.
Commands for the slave VESC are wrapped in COMM_FORWARD_CAN and routed by
the master to the slave's CAN ID.

Packet framing (short packets, ≤256 byte payload):
  [0x02][len][payload...][CRC16-XMODEM hi][CRC16-XMODEM lo][0x03]

Pin assignments:
  - VESC TX  → Pico RX: GP13
  - VESC RX  ← Pico TX: GP12
"""
from machine import UART, Pin
import struct
import time

# Motor IDs used by motor_control
LEFT = 0   # Master VESC (talks directly over UART)
RIGHT = 1  # Slave VESC (reached via CAN forward through master)

# CAN IDs — slave VESC must be configured to this CAN ID in VESC Tool
SLAVE_CAN_ID = 1

# VESC command IDs
COMM_GET_VALUES = 4
COMM_SET_DUTY = 5
COMM_SET_CURRENT = 6
COMM_FORWARD_CAN = 34

# UART config
_BAUD = 115200
_TX_PIN = 12
_RX_PIN = 13

# Hardware handle
_uart = None

# Last-read telemetry per motor: (motor_temp_c, fet_temp_c, current_a,
# duty, rpm, v_in, fault_code, ts_ms)
_values = {LEFT: None, RIGHT: None}


# ---- CRC-16/XMODEM (poly 0x1021, init 0x0000) ----

_CRC_TABLE = bytes((  # high byte
    0x00, 0x10, 0x20, 0x30, 0x40, 0x50, 0x60, 0x70,
    0x81, 0x91, 0xa1, 0xb1, 0xc1, 0xd1, 0xe1, 0xf1,
))


def _crc16(buf):
    crc = 0
    for b in buf:
        crc = ((crc << 8) & 0xffff) ^ _crc_lut[((crc >> 8) ^ b) & 0xff]
    return crc & 0xffff


def _build_crc_lut():
    lut = []
    for i in range(256):
        c = i << 8
        for _ in range(8):
            if c & 0x8000:
                c = ((c << 1) & 0xffff) ^ 0x1021
            else:
                c = (c << 1) & 0xffff
        lut.append(c)
    return lut


_crc_lut = _build_crc_lut()


# ---- Frame I/O ----

def _send_packet(payload):
    """Wrap payload in a VESC short-packet frame and write to UART.

    Builds the frame in-place into a single bytearray to avoid per-call
    object thrash; this runs at 10 Hz × 2 motors on a constrained MCU.
    """
    if _uart is None:
        return
    n = len(payload)
    if n > 255:
        return  # long packets not used in this firmware
    crc = _crc16(payload)
    frame = bytearray(n + 5)
    frame[0] = 0x02
    frame[1] = n
    frame[2:2 + n] = payload
    frame[n + 2] = (crc >> 8) & 0xff
    frame[n + 3] = crc & 0xff
    frame[n + 4] = 0x03
    try:
        _uart.write(frame)
    except:
        pass


def _wrap_forward_can(can_id, inner):
    """Wrap an inner VESC command for forwarding over CAN to the slave."""
    return bytes((COMM_FORWARD_CAN, can_id)) + bytes(inner)


def _send_vesc_command(motor_id, comm_id, raw_value):
    """Pack a fixed-size VESC command and dispatch to LEFT or RIGHT."""
    inner = struct.pack('>Bi', comm_id, raw_value)
    if motor_id == LEFT:
        _send_packet(inner)
    else:
        _send_packet(_wrap_forward_can(SLAVE_CAN_ID, inner))


# ---- Public API ----

def init():
    """Open UART0 to the master VESC. Call once at startup."""
    global _uart
    try:
        _uart = UART(0, baudrate=_BAUD, tx=Pin(_TX_PIN), rx=Pin(_RX_PIN),
                     timeout=20, timeout_char=2)
    except Exception as e:
        print("vesc init error: %s" % e)
        _uart = None


def set_duty(motor_id, duty):
    """Command duty cycle on a motor.

    Args:
        motor_id: LEFT or RIGHT.
        duty: float in -1.0..1.0 (positive = forward).
    """
    if duty > 1.0:
        duty = 1.0
    elif duty < -1.0:
        duty = -1.0
    _send_vesc_command(motor_id, COMM_SET_DUTY, int(duty * 100000.0))


def set_current(motor_id, amps):
    """Command motor current in amps. Useful for fishing-winch torque mode
    later; the propulsion loop uses set_duty."""
    _send_vesc_command(motor_id, COMM_SET_CURRENT, int(amps * 1000.0))


def request_values(motor_id):
    """Send a GET_VALUES request. Response is parsed by poll_rx()."""
    inner = bytes((COMM_GET_VALUES,))
    if motor_id == LEFT:
        _send_packet(inner)
    else:
        _send_packet(_wrap_forward_can(SLAVE_CAN_ID, inner))


# ---- Response parsing ----
# COMM_GET_VALUES response payload (firmware ≥ 3.40), big-endian, after the
# command byte:
#   int16  temp_fet      / 10
#   int16  temp_motor    / 10
#   int32  current_motor / 100
#   int32  current_in    / 100
#   int32  id            / 100
#   int32  iq            / 100
#   int16  duty          / 1000
#   int32  rpm           / 1
#   int16  v_in          / 10
#   int32  amp_hours     / 10000
#   int32  amp_hours_chg / 10000
#   int32  watt_hours    / 10000
#   int32  watt_hours_chg/ 10000
#   int32  tachometer
#   int32  tach_abs
#   uint8  fault_code

def _parse_values_payload(payload, motor_id):
    """Parse the COMM_GET_VALUES response and stash it in _values."""
    if len(payload) < 1 or payload[0] != COMM_GET_VALUES:
        return
    try:
        # Slice past the command byte
        p = payload[1:]
        # Pull just the fields we care about; fixed offsets
        fet_temp = struct.unpack('>h', p[0:2])[0] / 10.0
        motor_temp = struct.unpack('>h', p[2:4])[0] / 10.0
        current_motor = struct.unpack('>i', p[4:8])[0] / 100.0
        # Skip current_in (4), id (4), iq (4) — 12 bytes
        duty = struct.unpack('>h', p[20:22])[0] / 1000.0
        rpm = struct.unpack('>i', p[22:26])[0]
        v_in = struct.unpack('>h', p[26:28])[0] / 10.0
        # Skip 4 × int32 (amp/watt hours) — 16 bytes, then 2 × int32 tach — 8 bytes
        fault_code = p[52] if len(p) > 52 else 0
    except:
        return
    _values[motor_id] = (motor_temp, fet_temp, current_motor,
                         duty, rpm, v_in, fault_code, time.ticks_ms())


_rx_buf = bytearray(512)
_rx_pos = 0


def poll_rx():
    """Drain UART RX buffer and parse any complete VESC packets.

    Currently only COMM_GET_VALUES responses are parsed. Call from a
    background task at ~5 Hz alongside request_values().
    """
    global _rx_pos
    if _uart is None:
        return
    try:
        while _uart.any():
            chunk = _uart.read()
            if not chunk:
                break
            for b in chunk:
                if _rx_pos < len(_rx_buf):
                    _rx_buf[_rx_pos] = b
                    _rx_pos += 1
        # Scan for complete frames: [0x02][len][payload][crc_hi][crc_lo][0x03]
        i = 0
        while i + 4 < _rx_pos:
            if _rx_buf[i] == 0x02:
                ln = _rx_buf[i + 1]
                end = i + 2 + ln + 3
                if end > _rx_pos:
                    break
                if _rx_buf[end - 1] == 0x03:
                    payload = bytes(_rx_buf[i + 2:i + 2 + ln])
                    crc_recv = (_rx_buf[end - 3] << 8) | _rx_buf[end - 2]
                    if _crc16(payload) == crc_recv:
                        # Heuristic: forwarded responses come back with no
                        # extra wrapping in basic VESC FW, so we can't tell
                        # which motor responded. We rotate which we asked
                        # last; see task in main.py. Default to LEFT.
                        _parse_values_payload(payload, _last_request_id)
                    i = end
                    continue
            i += 1
        if i > 0:
            # Shift remaining bytes down
            remaining = _rx_pos - i
            for k in range(remaining):
                _rx_buf[k] = _rx_buf[i + k]
            _rx_pos = remaining
    except:
        pass


_last_request_id = LEFT


def request_values_round_robin():
    """Alternate GET_VALUES between LEFT and RIGHT. Call at ~5 Hz."""
    global _last_request_id
    _last_request_id = RIGHT if _last_request_id == LEFT else LEFT
    request_values(_last_request_id)


def get_motor_temp(motor_id):
    """Return last-known motor temperature in °C, or None if no telemetry yet."""
    v = _values.get(motor_id)
    return v[0] if v else None


def get_fet_temp(motor_id):
    v = _values.get(motor_id)
    return v[1] if v else None


def get_current(motor_id):
    v = _values.get(motor_id)
    return v[2] if v else None


def get_v_in(motor_id):
    v = _values.get(motor_id)
    return v[5] if v else None


def get_fault(motor_id):
    v = _values.get(motor_id)
    return v[6] if v else 0


def is_telemetry_fresh(motor_id, max_age_ms=2000):
    v = _values.get(motor_id)
    if v is None:
        return False
    return time.ticks_diff(time.ticks_ms(), v[7]) <= max_age_ms


def max_motor_temp():
    """Return the higher of the two motor temps (or 0 if neither known)."""
    l = get_motor_temp(LEFT) or 0.0
    r = get_motor_temp(RIGHT) or 0.0
    return max(l, r)
