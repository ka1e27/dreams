"""Onboard sensor reads — battery, DHT11, NTC motor temps, hull leak.

Extracted from reference/Boat_pico.py read_batt(), read_dht(),
read_mtemp(), read_hull().

Pin assignments:
  - Battery ADC:     GP26 (ADC0)
  - Motor temp left:  GP27 (ADC1)
  - Motor temp right: GP28 (ADC2)
  - DHT11:           GP16
  - Hull leak left:  GP17
  - Hull leak right: GP18
"""
from machine import Pin, ADC
import math
import time

try:
    import dht
except:
    dht = None

# Battery constants (voltage divider)
B_RATIO = 15.0 / 115.0
INV_B_RATIO = 1.0 / B_RATIO
B_FULL = 16.8
B_EMPTY = 13.2
B_WARN = 14.0
B_CRIT = 13.6
B_RANGE = B_FULL - B_EMPTY

# NTC thermistor constants
TH_NOM = 10000
TH_B = 3950
TH_R = 10000
INV_T_NOM = 1.0 / 298.15
INV_B_COEFF = 1.0 / TH_B

# Motor temperature thresholds
MT_WARN = 70
MT_CRIT = 85

# Hardware handles
_batt_adc = None
_mt_l_adc = None
_mt_r_adc = None
_dht_sensor = None
_hull_l = None
_hull_r = None

# Sensor readings
batt_v = 0.0
batt_pct = 0
air_temp = 0
air_humidity = 0
mt_left = 0.0
mt_right = 0.0
hull_leak_left = False
hull_leak_right = False


def init():
    """Initialise all onboard sensor hardware."""
    global _batt_adc, _mt_l_adc, _mt_r_adc, _dht_sensor, _hull_l, _hull_r
    try:
        _batt_adc = ADC(26)
    except:
        pass
    try:
        _mt_l_adc = ADC(27)
        _mt_r_adc = ADC(28)
    except:
        pass
    if dht is not None:
        try:
            _dht_sensor = dht.DHT11(Pin(16))
        except:
            pass
    try:
        _hull_l = Pin(17, Pin.IN, Pin.PULL_UP)
        _hull_r = Pin(18, Pin.IN, Pin.PULL_UP)
    except:
        pass


def _ntc_temp(adc):
    """Read NTC thermistor temperature from an ADC pin.

    Uses Steinhart-Hart equation with B-parameter model.
    Returns temperature in °C or None on error.
    """
    total = 0
    for _ in range(8):
        total += adc.read_u16()
    raw = total >> 3
    if raw < 100 or raw > 65400:
        return None
    resistance = TH_R * raw / (65535.0 - raw)
    if resistance <= 0:
        return None
    steinhart = math.log(resistance / TH_NOM) * INV_B_COEFF + INV_T_NOM
    if steinhart <= 0:
        return None
    return 1.0 / steinhart - 273.15


def read_battery():
    """Read battery voltage and percentage."""
    global batt_v, batt_pct
    if _batt_adc is None:
        return
    try:
        total = 0
        for _ in range(16):
            total += _batt_adc.read_u16()
        batt_v = (total / 16.0 / 65535.0 * 3.3) * INV_B_RATIO
        batt_pct = max(0, min(100, int((batt_v - B_EMPTY) / B_RANGE * 100)))
    except:
        pass


def read_dht():
    """Read air temperature and humidity from DHT11."""
    global air_temp, air_humidity
    if _dht_sensor is None:
        return
    try:
        _dht_sensor.measure()
        air_temp = _dht_sensor.temperature()
        air_humidity = _dht_sensor.humidity()
    except:
        pass


def read_motor_temps():
    """Read motor NTC thermistors."""
    global mt_left, mt_right
    if _mt_l_adc is None:
        return
    try:
        left = _ntc_temp(_mt_l_adc)
        if left is not None:
            mt_left = left
    except:
        pass
    if _mt_r_adc is not None:
        try:
            right = _ntc_temp(_mt_r_adc)
            if right is not None:
                mt_right = right
        except:
            pass


def read_hull():
    """Read hull leak sensors."""
    global hull_leak_left, hull_leak_right
    if _hull_l is not None:
        hull_leak_left = _hull_l.value() == 0
    if _hull_r is not None:
        hull_leak_right = _hull_r.value() == 0


def read_all_fast():
    """Read fast sensors — battery only. Call at ~10Hz."""
    read_battery()


def read_all_slow():
    """Read slow sensors — DHT, motor temps, hull. Call at ~0.3Hz."""
    read_dht()
    read_motor_temps()
    read_hull()


def is_battery_critical():
    """Return True if battery is below critical voltage."""
    return batt_v > 3.0 and batt_v <= B_CRIT


def is_battery_low():
    """Return True if battery is below warning level."""
    return batt_v > 3.0 and batt_v <= B_WARN


def is_motor_critical():
    """Return True if either motor is above critical temperature."""
    return max(mt_left, mt_right) >= MT_CRIT


def is_motor_hot():
    """Return True if either motor is above warning temperature."""
    return max(mt_left, mt_right) >= MT_WARN


def hull_status():
    """Return hull status string: 'DRY', 'L!', 'R!', or 'L!R!'."""
    s = ""
    if hull_leak_left:
        s += "L!"
    if hull_leak_right:
        s += "R!"
    return s if s else "DRY"


def both_hulls_leaking():
    """Return True if both hull sensors detect water."""
    return hull_leak_left and hull_leak_right
