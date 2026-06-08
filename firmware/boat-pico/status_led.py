"""Status NeoPixel on GP10 — single WS2812 indicating boat state.

Modes (set externally via set_mode; priority is decided by the caller):
  ESTOP   — red, fast blink (5 Hz)
  CRIT    — red, slow blink (1 Hz)
  RC      — cyan, solid
  WARN    — yellow, blink (2 Hz)
  ACTIVE  — green, breathing
  IDLE    — blue, slow breath
  BOOT    — dim white, solid
"""
import math
import machine
import neopixel


PIN = 10

_np = None
_mode = "BOOT"
_brightness = 0.4  # global cap — WS2812s are very bright

_RED    = (255, 0, 0)
_GREEN  = (0, 255, 0)
_BLUE   = (0, 0, 255)
_CYAN   = (0, 255, 255)
_YELLOW = (255, 180, 0)
_WHITE  = (255, 255, 255)
_OFF    = (0, 0, 0)


def init(pin=PIN):
    global _np
    _np = neopixel.NeoPixel(machine.Pin(pin), 1)
    _np[0] = _OFF
    _np.write()


def set_mode(mode):
    global _mode
    _mode = mode


def get_mode():
    return _mode


def _scale(rgb, k):
    return (int(rgb[0] * k), int(rgb[1] * k), int(rgb[2] * k))


def _blink(now_ms, hz):
    period = int(1000 / hz)
    return (now_ms % period) < (period // 2)


def _breathe(now_ms, period_ms):
    phase = (now_ms % period_ms) / period_ms
    return 0.5 * (1.0 - math.cos(2 * math.pi * phase))


def update(now_ms):
    if _np is None:
        return
    m = _mode
    if m == "ESTOP":
        c = _RED if _blink(now_ms, 5) else _OFF
    elif m == "CRIT":
        c = _RED if _blink(now_ms, 1) else _OFF
    elif m == "RC":
        c = _CYAN
    elif m == "WARN":
        c = _YELLOW if _blink(now_ms, 2) else _OFF
    elif m == "ACTIVE":
        k = 0.3 + 0.7 * _breathe(now_ms, 2000)
        c = _scale(_GREEN, k)
    elif m == "IDLE":
        k = 0.2 + 0.5 * _breathe(now_ms, 3500)
        c = _scale(_BLUE, k)
    else:  # BOOT or unknown
        c = _scale(_WHITE, 0.3)
    _np[0] = _scale(c, _brightness)
    _np.write()
