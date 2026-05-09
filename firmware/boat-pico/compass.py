"""BNO085 9-axis IMU driver — heading + pitch/roll over I2C.

Replaces the previous QMC5883P magnetometer-only driver. The BNO085
contains a Hillcrest/CEVA SH-2 sensor-fusion engine, so we get a tilt-
compensated heading directly instead of doing the math on a raw mag.

We speak the SH-2 / SHTP protocol over I2C and only enable a single
feature report (Rotation Vector). Everything else — calibration, soft/hard
iron, bias estimation — is handled inside the BNO085 itself.

I2C wiring (unchanged from QMC5883P):
  - SDA: GP8
  - SCL: GP9
  - Bus freq: 400 kHz (BNO085 supports up to 400 kHz I2C)
  - Default address: 0x4A (0x4B if the ADR pin is pulled high)

Public surface — kept identical to the prior QMC5883P driver so main.py
doesn't have to change:
  init() / read() / is_healthy() / calibrate_north(true_bearing) / scan_bus()

Additional state exposed for telemetry: pitch, roll, cal_status (0–3).
"""
from machine import I2C, Pin
import math
import time
import struct

BNO_ADDR = 0x4A
RAD_TO_DEG = 180.0 / math.pi

# SHTP channel numbers
CH_COMMAND = 0
CH_EXECUTABLE = 1
CH_CONTROL = 2
CH_REPORTS = 3
CH_WAKE_REPORTS = 4
CH_GYRO_INT = 5

# SH-2 control / report IDs
SHTP_REPORT_SET_FEATURE = 0xFD
SH2_ROTATION_VECTOR = 0x05  # full fusion: yaw/pitch/roll w/ accuracy
SH2_GAME_ROTATION_VECTOR = 0x08  # no magnetometer; falls back if mag is bad

# Q-point scaling for Rotation Vector quaternion outputs
Q14_SCALE = 1.0 / (1 << 14)
Q12_SCALE = 1.0 / (1 << 12)

_i2c = None

# Calibration offset applied in software — BNO085 handles the heavy
# soft/hard-iron calibration internally; this is just for "true north" trim.
_hdg_off = 0.0

# Parsed state
heading = 0.0
pitch = 0.0
roll = 0.0
cal_status = 0  # 0–3 from rotation vector accuracy

# Health tracking
_fail_count = 0
_FAIL_THRESHOLD = 10
_last_read_ms = 0
_TIMEOUT_MS = 5000

# SHTP sequence number per channel (we only send on CH_CONTROL)
_seq_control = 0


def _i2c_write(buf):
    """Write a SHTP packet. Returns True on success."""
    if _i2c is None:
        return False
    try:
        _i2c.writeto(BNO_ADDR, buf)
        return True
    except:
        return False


def _i2c_read(n):
    """Read n bytes. Returns bytes or None on failure."""
    if _i2c is None:
        return None
    try:
        return _i2c.readfrom(BNO_ADDR, n)
    except:
        return None


def _send_shtp(channel, payload):
    """Build a SHTP header and ship a packet."""
    global _seq_control
    n = len(payload) + 4  # +4 for header
    seq = _seq_control & 0xff
    if channel == CH_CONTROL:
        _seq_control = (_seq_control + 1) & 0xff
    header = bytes((n & 0xff, (n >> 8) & 0x7f, channel, seq))
    return _i2c_write(header + bytes(payload))


def _read_shtp_packet():
    """Read one SHTP packet. Returns (channel, payload_bytes) or None."""
    # Header: length_lo, length_hi (top bit = continuation), channel, seq
    hdr = _i2c_read(4)
    if hdr is None or len(hdr) < 4:
        return None
    length = ((hdr[1] & 0x7f) << 8) | hdr[0]
    if length == 0 or length == 0xffff:
        return None
    if length < 4:
        return None
    channel = hdr[2]
    rest = length - 4
    if rest <= 0:
        return (channel, b'')
    # Re-read the full packet now that we know the length (BNO085 sends
    # header again on each read, so we ask for length total).
    full = _i2c_read(length)
    if full is None or len(full) < length:
        return None
    return (full[2], bytes(full[4:length]))


def _enable_feature(report_id, interval_us):
    """Turn on a sensor feature at the given report interval."""
    payload = bytearray(17)
    payload[0] = SHTP_REPORT_SET_FEATURE
    payload[1] = report_id
    # bytes 2–4: feature flags / sensitivity (zero is fine)
    # bytes 5–8: report interval in microseconds, little-endian
    iv = interval_us & 0xffffffff
    payload[5] = iv & 0xff
    payload[6] = (iv >> 8) & 0xff
    payload[7] = (iv >> 16) & 0xff
    payload[8] = (iv >> 24) & 0xff
    # remaining bytes zero
    return _send_shtp(CH_CONTROL, payload)


def init():
    """Initialise I2C and configure the BNO085. Returns True on success."""
    global _i2c, _fail_count
    try:
        _i2c = I2C(0, sda=Pin(8), scl=Pin(9), freq=400000)
    except:
        return False
    # Probe — a successful I2C scan finding 0x4A is enough sanity here.
    try:
        addrs = _i2c.scan()
    except:
        return False
    if BNO_ADDR not in addrs:
        return False
    # The BNO085 ships an "advertisement" packet at boot; drain whatever's
    # waiting before configuring features.
    for _ in range(8):
        if _read_shtp_packet() is None:
            break
    # Enable Rotation Vector at 50 Hz (20 ms = 20_000 us).
    ok = _enable_feature(SH2_ROTATION_VECTOR, 20_000)
    if ok:
        _fail_count = 0
    return ok


def _quat_to_euler(qw, qx, qy, qz):
    """Quaternion → (yaw, pitch, roll) in degrees, NED-ish.

    Yaw is taken as rotation about Z (heading). For a deck-mounted IMU this
    matches what the boat needs; tilt about X/Y becomes pitch/roll.
    """
    # Yaw (Z)
    siny_cosp = 2.0 * (qw * qz + qx * qy)
    cosy_cosp = 1.0 - 2.0 * (qy * qy + qz * qz)
    yaw = math.atan2(siny_cosp, cosy_cosp)
    # Pitch (Y)
    sinp = 2.0 * (qw * qy - qz * qx)
    if sinp > 1.0:
        sinp = 1.0
    elif sinp < -1.0:
        sinp = -1.0
    pitch_r = math.asin(sinp)
    # Roll (X)
    sinr_cosp = 2.0 * (qw * qx + qy * qz)
    cosr_cosp = 1.0 - 2.0 * (qx * qx + qy * qy)
    roll_r = math.atan2(sinr_cosp, cosr_cosp)
    return yaw * RAD_TO_DEG, pitch_r * RAD_TO_DEG, roll_r * RAD_TO_DEG


def _parse_rotation_vector(report):
    """Parse a SH-2 Rotation Vector input report into yaw/pitch/roll/accuracy.

    Report layout (after the 5-byte timebase header that comes in front
    of report blocks — caller is responsible for stripping that):
      [0]  report id (0x05)
      [1]  sequence number
      [2]  status (bits 0–1: accuracy 0–3)
      [3]  delay
      [4-5] qx (q14, signed)
      [6-7] qy (q14, signed)
      [8-9] qz (q14, signed)
      [10-11] qw (q14, signed)
      [12-13] accuracy (q12, radians)
    """
    global heading, pitch, roll, cal_status, _last_read_ms, _fail_count
    if len(report) < 14:
        _fail_count += 1
        return False
    if report[0] != SH2_ROTATION_VECTOR:
        return False
    accuracy = report[2] & 0x03
    qx = struct.unpack('<h', report[4:6])[0] * Q14_SCALE
    qy = struct.unpack('<h', report[6:8])[0] * Q14_SCALE
    qz = struct.unpack('<h', report[8:10])[0] * Q14_SCALE
    qw = struct.unpack('<h', report[10:12])[0] * Q14_SCALE
    yaw, p, r = _quat_to_euler(qw, qx, qy, qz)
    if yaw < 0:
        yaw += 360.0
    heading = (yaw - _hdg_off) % 360.0
    pitch = p
    roll = r
    cal_status = accuracy
    _last_read_ms = time.ticks_ms()
    _fail_count = 0
    return True


# Input-report packets on CH_REPORTS start with a 5-byte timebase header
# we ignore: [base delta hi/lo/lo/lo, base delta status]. The first byte
# 0xFB is the timebase marker.

def _consume_reports(payload):
    """Walk a CH_REPORTS payload and dispatch known reports."""
    if not payload:
        return
    i = 0
    # Some firmwares prefix the first input-report with a 5-byte timebase.
    if payload[0] == 0xFB and len(payload) > 5:
        i = 5
    while i < len(payload):
        rid = payload[i]
        # Known report sizes
        if rid == SH2_ROTATION_VECTOR:
            block = payload[i:i + 14]
            if not _parse_rotation_vector(block):
                return
            i += 14
        else:
            # Unknown — bail rather than misalign
            return


def read():
    """Pull pending packets from the BNO085 and update state.

    Call from the main loop (~10 Hz). With Rotation Vector running at
    50 Hz, each call typically harvests several pending reports.
    """
    global _fail_count
    if _i2c is None:
        _fail_count += 1
        return
    # Drain a few packets per call to keep up with the report rate.
    for _ in range(4):
        pkt = _read_shtp_packet()
        if pkt is None:
            return
        channel, payload = pkt
        if channel == CH_REPORTS or channel == CH_WAKE_REPORTS:
            _consume_reports(payload)


def calibrate_north(true_bearing):
    """Set the heading offset so the current heading matches true_bearing.

    Args:
        true_bearing: known true bearing the boat is currently facing (0–359.9°).

    Returns:
        (success, new_hdg_off)
    """
    global _hdg_off
    if not (0 <= true_bearing < 360):
        return False, _hdg_off
    raw_hdg = (heading + _hdg_off) % 360.0
    _hdg_off = (raw_hdg - true_bearing) % 360.0
    return True, _hdg_off


def get_hdg_off():
    return _hdg_off


def is_healthy():
    """True if the BNO085 is producing valid reports recently."""
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
