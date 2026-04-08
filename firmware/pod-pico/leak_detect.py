"""Pod leak detection sensor.

Monitors a leak sensor inside the pod housing. When water is detected,
sets an alert flag that is included in poll responses.

Pin assignment:
  - Leak sensor: GP20 (pull-up, active low — water bridges the contacts)
"""
from machine import Pin

_sensor = None
leak_detected = False
_consecutive_count = 0
_CONFIRM_THRESHOLD = 3  # Require 3 consecutive reads to confirm leak


def init():
    """Initialise leak detection pin."""
    global _sensor
    try:
        _sensor = Pin(20, Pin.IN, Pin.PULL_UP)
    except:
        pass


def read():
    """Read leak sensor. Call from main loop.

    Uses debouncing: requires 3 consecutive positive reads to confirm
    a leak, reducing false positives from vibration or splash.
    """
    global leak_detected, _consecutive_count
    if _sensor is None:
        return
    if _sensor.value() == 0:  # Water detected (active low)
        _consecutive_count += 1
        if _consecutive_count >= _CONFIRM_THRESHOLD:
            leak_detected = True
    else:
        _consecutive_count = 0
        # Once detected, leak flag stays set until pod is physically
        # inspected and firmware is reset. This is intentional safety.
