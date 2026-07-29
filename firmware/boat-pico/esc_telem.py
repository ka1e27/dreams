"""AM32 / KISS ESC telemetry receiver (two ESCs) using PIO UART RX.

⚠ UNTESTED / EXPERIMENTAL — no hardware yet, same status as esc_passthrough.py.
See docs/esc_telemetry.md for the on-Pi bring-up + validation plan.

The NeutronRC 70A-G071 (AM32) ESCs each have a **telemetry (TX) pad** that emits
the KISS/BLHeli-standard ESC telemetry frame — one-way, ESC → Pico, standard
(non-inverted) 3.3 V UART at 115200 8N1. `escs.py` drives the motors as plain
50 Hz servo PWM and its telemetry accessors are stubbed; this module fills them in
so the dashboard gets per-motor temperature + current (and the firmware regains a
motor-overheat check the VESC used to provide).

KISS telemetry frame — 10 bytes, 16-bit values big-endian:
    [0]    temperature      °C
    [1:3]  voltage          centivolts (÷100 = V)
    [3:5]  current          centiamps  (÷100 = A)
    [5:7]  consumption      mAh
    [7:9]  eRPM             ÷100 (× (2/poles) = mechanical RPM)
    [9]    CRC-8            poly 0x07 over bytes [0:9]

Both hardware UARTs are taken (UART0 free pins collide, UART1 = GPS+Pod), so —
like sbus.py — we bit-bang a UART RX in PIO. The one lesson learned from sbus.py:
its RX FIFO is only 8 bytes (`push_thresh=8`), which is *smaller than a 10-byte
telem frame*, so a frame arriving between polls overflows and stalls the SM. Here
we pack **4 bytes per FIFO word (`push_thresh=32`) → a 32-byte buffer**, which
comfortably holds a whole frame between drains. (The same fix would harden sbus.py.)

Pin assignment (free Pico header pins, hand-tapped on the bench like GP2/3/6/7):
    Left  ESC TX → GP16   (was the unused DHT11 pin)
    Right ESC TX → GP11
Change TELEM_L_PIN / TELEM_R_PIN if you tap different pins.

GP16 and GP11 are the only two pins left unconnected on Boat_PCB V2, so neither
collides with a board net — but for the same reason neither is routed to a
connector: solder the ESC telemetry leads directly to the Pico pins.

Right ESC telemetry was moved GP19 -> GP11 on 2026-07-28. GP19 is the board's
"Hull Leak Left" connector (J16); a leak switch there shorts to GND and would
have held the telemetry line low. Hull leak now reads GP19/GP20 to match the
board's connectors (see sensors.py and docs/pin_map.md).

Bench-verify items (documented in docs/esc_telemetry.md):
  1. AM32 must actually *emit* telemetry in servo-PWM mode — enable the telemetry
     / auto-telemetry option in am32.ca. If a build only sends telem under DShot,
     this PWM path stays empty (frames_ok stays 0).
  2. PIO byte order out of the 32-bit shift (see _BYTE_ORDER_LE) — flip if the
     first captured frames never pass CRC but a byte-reversed copy would.
  3. Drain cadence — task_esc_telem polls at 100 Hz; frames_ok/crc_fail in stats()
     confirm the FIFO isn't overflowing.
"""
import time

try:
    from machine import Pin
    from rp2 import asm_pio, PIO, StateMachine
    _PIO_OK = True
except ImportError:  # host import for py_compile / tests
    _PIO_OK = False

# Motor IDs — match escs.py so escs can delegate straight through.
LEFT = 0
RIGHT = 1

TELEM_L_PIN = 16
TELEM_R_PIN = 11   # moved off GP19 — that's the J16 hull-leak connector on Boat_PCB V2
BAUD = 115200

# PIO state-machine ids: SBUS uses SM 0 (PIO0). Put telem on PIO1 (SM 4/5) so the
# two PIO programs live in separate blocks and never contend for instruction slots.
_SM_L = 4
_SM_R = 5

# If the first on-hardware frames never pass CRC, try flipping this — it selects
# whether the 32-bit PIO word unpacks first-byte-first (True) or reversed.
_BYTE_ORDER_LE = True

_FRAME_LEN = 10
_FRESH_MS = 500

# Sanity envelope for a CRC-passing frame (rejects the ~1/256 false-CRC on
# mis-aligned data). A 2× M18 rail is ~15–21 V; boat motors well under 300 A.
_TEMP_MAX = 200
_VOLT_MAX_CV = 6000      # 60.00 V
_CURR_MAX_CA = 30000     # 300.00 A


if _PIO_OK:
    @asm_pio(autopush=True, push_thresh=32, fifo_join=PIO.JOIN_RX,
             in_shiftdir=PIO.SHIFT_RIGHT)
    def _uart_rx():
        # Standard 8N1 UART RX, idle HIGH (non-inverted). SM clock = 8 × baud.
        wrap_target()
        wait(0, pin, 0)          # start bit: line goes LOW
        nop()[11]                # 1.5 bit-times → centre of data bit 0
        set(x, 7)
        label("bit_loop")
        in_(pins, 1)
        nop()[6]                 # 8 cycles per bit
        jmp(x_dec, "bit_loop")
        wrap()                   # ignore stop bit; wait for next start


class _Esc:
    __slots__ = ("buf", "temp_c", "voltage_v", "current_a",
                 "consumption_mah", "erpm", "last_ms", "ok")

    def __init__(self):
        self.buf = bytearray()
        self.temp_c = 0.0
        self.voltage_v = 0.0
        self.current_a = 0.0
        self.consumption_mah = 0
        self.erpm = 0
        self.last_ms = 0
        self.ok = False


_esc = {LEFT: _Esc(), RIGHT: _Esc()}
_sm = {LEFT: None, RIGHT: None}
_stats = {"frames_ok": 0, "crc_fail": 0}


def _crc8(data):
    """KISS/BLHeli telemetry CRC-8 (poly 0x07, MSB-first, init 0)."""
    crc = 0
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = ((crc << 1) ^ 0x07) & 0xFF if (crc & 0x80) else (crc << 1) & 0xFF
    return crc


def init():
    """Create both telemetry RX state machines. Returns True if both start."""
    global _sm
    if not _PIO_OK:
        return False
    ok = True
    for mid, pin, sm_id in ((LEFT, TELEM_L_PIN, _SM_L), (RIGHT, TELEM_R_PIN, _SM_R)):
        try:
            sm = StateMachine(sm_id, _uart_rx, freq=BAUD * 8,
                              in_base=Pin(pin, Pin.IN, Pin.PULL_UP))
            sm.active(1)
            _sm[mid] = sm
        except Exception as e:  # noqa: BLE001
            print("esc_telem init error (motor %d): %s" % (mid, e))
            _sm[mid] = None
            ok = False
    return ok


def _unpack_word(word):
    """A 32-bit PIO word → 4 bytes in wire order."""
    if _BYTE_ORDER_LE:
        return (word & 0xFF, (word >> 8) & 0xFF,
                (word >> 16) & 0xFF, (word >> 24) & 0xFF)
    return ((word >> 24) & 0xFF, (word >> 16) & 0xFF,
            (word >> 8) & 0xFF, word & 0xFF)


def _accept(e, f):
    """Store a CRC-valid, in-range frame."""
    e.temp_c = float(f[0])
    e.voltage_v = ((f[1] << 8) | f[2]) / 100.0
    e.current_a = ((f[3] << 8) | f[4]) / 100.0
    e.consumption_mah = (f[5] << 8) | f[6]
    e.erpm = ((f[7] << 8) | f[8]) * 100
    e.last_ms = time.ticks_ms()
    e.ok = True


def _extract(e):
    """Pull complete frames out of a reassembled byte buffer (sliding CRC)."""
    buf = e.buf
    while len(buf) >= _FRAME_LEN:
        if (_crc8(buf[0:9]) == buf[9]
                and buf[0] <= _TEMP_MAX
                and ((buf[1] << 8) | buf[2]) <= _VOLT_MAX_CV
                and ((buf[3] << 8) | buf[4]) <= _CURR_MAX_CA):
            _accept(e, buf[0:_FRAME_LEN])
            _stats["frames_ok"] += 1
            del buf[0:_FRAME_LEN]
        else:
            _stats["crc_fail"] += 1
            del buf[0]
    # Cap growth if we never sync (bad wiring / wrong baud).
    if len(buf) > 64:
        del buf[0:len(buf) - 16]


def poll():
    """Drain both RX FIFOs and parse frames. Call from a ~100 Hz task."""
    for mid in (LEFT, RIGHT):
        sm = _sm[mid]
        if sm is None:
            continue
        try:
            e = _esc[mid]
            while sm.rx_fifo():
                b0, b1, b2, b3 = _unpack_word(sm.get())
                e.buf.append(b0)
                e.buf.append(b1)
                e.buf.append(b2)
                e.buf.append(b3)
            _extract(e)
        except Exception:  # noqa: BLE001
            pass


# ---- Accessors (escs.py delegates its stubbed telemetry to these) ----

def is_fresh(motor_id, max_age_ms=_FRESH_MS):
    e = _esc.get(motor_id)
    if e is None or not e.ok:
        return False
    return time.ticks_diff(time.ticks_ms(), e.last_ms) <= max_age_ms


def temperature(motor_id):
    return _esc[motor_id].temp_c if is_fresh(motor_id) else None


def current(motor_id):
    return _esc[motor_id].current_a if is_fresh(motor_id) else None


def voltage(motor_id):
    return _esc[motor_id].voltage_v if is_fresh(motor_id) else None


def erpm(motor_id):
    return _esc[motor_id].erpm if is_fresh(motor_id) else None


def max_temp():
    """Hottest fresh ESC temperature, or 0.0 if no telemetry (never trips)."""
    hot = 0.0
    for mid in (LEFT, RIGHT):
        if is_fresh(mid):
            t = _esc[mid].temp_c
            if t > hot:
                hot = t
    return hot


def stats():
    """(frames_ok, crc_fail) — for on-bench validation via docs/esc_telemetry.md."""
    return dict(_stats)
