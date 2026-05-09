"""SBUS receiver decoder using PIO.

SBUS protocol:
  - 100,000 baud, 8E2, inverted
  - 25-byte frame: 0x0F header, 22 channel bytes (16 × 11-bit packed),
    flags byte, 0x00 footer
  - Frame interval ~14 ms (high-speed) or ~21 ms

Both Pico hardware UARTs are taken (UART0 = VESC, UART1 = GPS+Pod), so we
use PIO. The state machine bit-bangs an inverted UART RX at 100 kbaud and
pushes raw bytes to its FIFO. Python reads the FIFO, inverts each byte
(SBUS line polarity), and assembles them into 25-byte frames.

Pin assignment:
  - SBUS RX → Pico GP15 (direct, no external inverter required)
"""
import time

try:
    from machine import Pin
    from rp2 import asm_pio, PIO, StateMachine
    _PIO_OK = True
except ImportError:
    # Allows host-side import for tests without raising
    _PIO_OK = False

SBUS_PIN = 15
SBUS_BAUD = 100_000

# Frame layout
HEADER = 0x0F
FOOTER = 0x00
FRAME_LEN = 25

# Flags byte bit positions
FLAG_CH17 = 1 << 0
FLAG_CH18 = 1 << 1
FLAG_FRAME_LOST = 1 << 2
FLAG_FAILSAFE = 1 << 3

# Decoded state
_channels = [1024] * 16  # mid-stick default
_failsafe = True
_frame_lost = True
_last_frame_ms = 0


if _PIO_OK:
    @asm_pio(autopush=True, push_thresh=8, fifo_join=PIO.JOIN_RX,
             in_shiftdir=PIO.SHIFT_RIGHT)
    def _sbus_pio():
        # Inverted SBUS line idles LOW. Start bit is HIGH, data 0 = HIGH,
        # data 1 = LOW. We sample raw bits here and invert in software.
        # State machine clock is set to 8 × baud = 800 kHz.
        wrap_target()
        # Wait for start bit (line goes HIGH on inverted UART).
        wait(1, pin, 0)
        # Wait 1.5 bit times to land in the middle of bit 0.
        nop()[11]
        # Read 8 data bits (LSB first).
        set(x, 7)
        label("bit_loop")
        in_(pins, 1)
        # 8 cycles per bit (we already used 1 for in_, so wait 7 more)
        nop()[6]
        jmp(x_dec, "bit_loop")
        # autopush flushes 8 bits to the RX FIFO. Skip parity + stop bits
        # by simply waiting for the next start bit.
        wrap()


_sm = None


def init():
    """Spin up the PIO state machine. Returns True on success."""
    global _sm
    if not _PIO_OK:
        return False
    try:
        _sm = StateMachine(
            0, _sbus_pio,
            freq=SBUS_BAUD * 8,
            in_base=Pin(SBUS_PIN, Pin.IN, Pin.PULL_DOWN),
        )
        _sm.active(1)
        return True
    except Exception as e:
        print("sbus init error: %s" % e)
        return False


def _decode_frame(buf):
    """Decode a 25-byte SBUS frame into 16 × 11-bit channels and flags.

    Channels are packed LSB-first across the 22 channel bytes.
    """
    global _failsafe, _frame_lost, _last_frame_ms
    if len(buf) != FRAME_LEN:
        return False
    if buf[0] != HEADER or buf[24] != FOOTER:
        return False
    bits = 0
    val = 0
    ch = 0
    for i in range(1, 23):
        val |= (buf[i] & 0xff) << bits
        bits += 8
        while bits >= 11 and ch < 16:
            _channels[ch] = val & 0x07ff
            val >>= 11
            bits -= 11
            ch += 1
    flags = buf[23]
    _frame_lost = bool(flags & FLAG_FRAME_LOST)
    _failsafe = bool(flags & FLAG_FAILSAFE)
    _last_frame_ms = time.ticks_ms()
    return True


_rx_bytes = bytearray()


def poll():
    """Drain the PIO RX FIFO and decode any complete SBUS frames.

    Call from a fast async task (~50 Hz). Re-syncs on the 0x0F header
    if framing is lost.
    """
    if _sm is None:
        return
    try:
        while _sm.rx_fifo():
            raw = _sm.get() & 0xff
            # Bytes from PIO are inverted; flip back to actual SBUS values.
            b = (~raw) & 0xff
            _rx_bytes.append(b)
        # Cap buffer growth — SBUS frames are 25 bytes; we only need to
        # re-sync once we're carrying enough lookahead that something has
        # gone wrong. Doing rfind/del on every poll iteration above 64
        # bytes burned cycles for no benefit.
        if len(_rx_bytes) > 128:
            idx = _rx_bytes.rfind(bytes((HEADER,)))
            if idx > 0:
                del _rx_bytes[:idx]
            else:
                _rx_bytes.clear()
        # Try to extract frames
        while len(_rx_bytes) >= FRAME_LEN:
            if _rx_bytes[0] != HEADER:
                # Slide one byte and re-look
                del _rx_bytes[0]
                continue
            frame = bytes(_rx_bytes[:FRAME_LEN])
            if _decode_frame(frame):
                del _rx_bytes[:FRAME_LEN]
            else:
                del _rx_bytes[0]
    except:
        pass


# ---- Public state ----

def read_channels():
    """Return the most recent 16 channel values (each 0–2047, ~172–1811 valid)."""
    return list(_channels)


def is_failsafe():
    """Return True if the receiver reports failsafe (TX off, link lost)."""
    return _failsafe


def is_frame_lost():
    """Return True if the most recent frame had the frame-lost flag."""
    return _frame_lost


def is_link_alive(max_age_ms=200):
    """Return True if a frame was decoded recently and failsafe isn't set."""
    if _failsafe:
        return False
    if _last_frame_ms == 0:
        return False
    return time.ticks_diff(time.ticks_ms(), _last_frame_ms) <= max_age_ms


# ---- SBUS → throttle helpers ----

# SBUS channel value range (raw): 172 (low) – 992 (mid) – 1811 (high)
SBUS_LOW = 172
SBUS_MID = 992
SBUS_HIGH = 1811
SBUS_HALF = SBUS_HIGH - SBUS_MID  # ≈ 819


def channel_to_pct(ch_value):
    """Map an 11-bit SBUS channel value to -100..+100."""
    delta = ch_value - SBUS_MID
    if delta > SBUS_HALF:
        delta = SBUS_HALF
    elif delta < -SBUS_HALF:
        delta = -SBUS_HALF
    return int(delta * 100 / SBUS_HALF)


def channel_is_high(ch_value, threshold=1500):
    """For 2- or 3-position switches: True if channel is in the upper position."""
    return ch_value >= threshold
