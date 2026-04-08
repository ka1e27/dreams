"""Heartbeat watchdog — monitors Pi 5 liveness.

If no heartbeat (HB command) is received within the timeout,
triggers an automatic emergency stop and sends an alert.
"""
import time

_last_hb_ms = 0
_timeout_ms = 3000
_triggered = False
_on_timeout = None  # Callback: called once when heartbeat is lost


def init(timeout_ms=3000, on_timeout=None):
    """Initialise watchdog.

    Args:
        timeout_ms: Time without heartbeat before triggering ESTOP.
        on_timeout: Callback function, called once when timeout fires.
    """
    global _timeout_ms, _on_timeout, _last_hb_ms
    _timeout_ms = timeout_ms
    _on_timeout = on_timeout
    _last_hb_ms = time.ticks_ms()


def feed():
    """Reset the watchdog timer. Called when a HB command is received."""
    global _last_hb_ms, _triggered
    _last_hb_ms = time.ticks_ms()
    _triggered = False


def check():
    """Check if the heartbeat has timed out. Call from main loop.

    Returns True if timed out (Pi 5 is considered dead).
    """
    global _triggered
    if _last_hb_ms == 0:
        return False
    elapsed = time.ticks_diff(time.ticks_ms(), _last_hb_ms)
    if elapsed > _timeout_ms:
        if not _triggered:
            _triggered = True
            if _on_timeout:
                _on_timeout()
        return True
    return False


def is_alive():
    """Return True if Pi 5 heartbeat is being received."""
    if _last_hb_ms == 0:
        return False
    return time.ticks_diff(time.ticks_ms(), _last_hb_ms) <= _timeout_ms


def time_since_hb():
    """Return milliseconds since last heartbeat."""
    if _last_hb_ms == 0:
        return -1
    return time.ticks_diff(time.ticks_ms(), _last_hb_ms)
