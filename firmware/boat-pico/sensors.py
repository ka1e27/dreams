"""Onboard hull sensors — dual battery, DHT11, hull leak.

Motor temperatures used to live here as NTC thermistors on GP27/GP28; that
job moved to the VESCs (queried over UART by `vesc.py`). The freed ADCs
now monitor a second battery.

Pin assignments:
  - Propulsion battery (12S LiPo) ADC: GP26 (ADC0)
      — voltage divider sized so 50.4 V → ≤ 3.3 V at the Pico pin
  - Electronics battery (3S Li-ion) ADC: GP27 (ADC1)
      — uses the legacy 15 / (15+100) divider; 12.6 V → 1.64 V
  - DHT11:           GP16
  - Hull leak left:  GP17
  - Hull leak right: GP18
  - GP28 (ADC2):     spare
"""
from machine import Pin, ADC

try:
    import dht
except:
    dht = None

# ---- Propulsion battery (12S LiPo) ----
# Divider: 3.3 kΩ low / 47 kΩ high → ratio ≈ 1/15.24 (50.4 V → 3.31 V)
P_RATIO = 3.3 / 50.3
INV_P_RATIO = 1.0 / P_RATIO
P_FULL = 50.4   # 4.20 V × 12
P_EMPTY = 39.6  # 3.30 V × 12 LVC
P_WARN = 42.0   # 3.50 V × 12
P_CRIT = 39.6
P_RANGE = P_FULL - P_EMPTY

# ---- Electronics battery (3S Li-ion) ----
# Reuse legacy 15 / (15+100) divider. 12.6 V → 1.64 V.
E_RATIO = 15.0 / 115.0
INV_E_RATIO = 1.0 / E_RATIO
E_FULL = 12.6   # 4.20 V × 3
E_EMPTY = 9.0   # 3.00 V × 3
E_WARN = 9.9    # 3.30 V × 3
E_CRIT = 9.6    # 3.20 V × 3
E_RANGE = E_FULL - E_EMPTY

# ---- Hardware handles ----
_prop_adc = None
_elec_adc = None
_dht_sensor = None
_hull_l = None
_hull_r = None

# ---- Sensor readings ----
prop_batt_v = 0.0
prop_batt_pct = 0
elec_batt_v = 0.0
elec_batt_pct = 0
air_temp = 0
air_humidity = 0
hull_leak_left = False
hull_leak_right = False


def init():
    """Initialise all onboard sensor hardware."""
    global _prop_adc, _elec_adc, _dht_sensor, _hull_l, _hull_r
    try:
        _prop_adc = ADC(26)
    except:
        pass
    try:
        _elec_adc = ADC(27)
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


def _read_battery_voltage(adc, inv_ratio):
    """Return the voltage at the battery side of a divider, averaged 16x."""
    if adc is None:
        return 0.0
    total = 0
    for _ in range(16):
        total += adc.read_u16()
    return (total / 16.0 / 65535.0 * 3.3) * inv_ratio


def read_prop_battery():
    """Read propulsion (12S LiPo) battery voltage and percentage."""
    global prop_batt_v, prop_batt_pct
    try:
        prop_batt_v = _read_battery_voltage(_prop_adc, INV_P_RATIO)
        prop_batt_pct = max(0, min(100,
                                   int((prop_batt_v - P_EMPTY) / P_RANGE * 100)))
    except:
        pass


def read_elec_battery():
    """Read electronics (3S Li-ion) battery voltage and percentage."""
    global elec_batt_v, elec_batt_pct
    try:
        elec_batt_v = _read_battery_voltage(_elec_adc, INV_E_RATIO)
        elec_batt_pct = max(0, min(100,
                                   int((elec_batt_v - E_EMPTY) / E_RANGE * 100)))
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


def read_hull():
    """Read hull leak sensors."""
    global hull_leak_left, hull_leak_right
    if _hull_l is not None:
        hull_leak_left = _hull_l.value() == 0
    if _hull_r is not None:
        hull_leak_right = _hull_r.value() == 0


def read_all_fast():
    """Read fast sensors — both batteries. Call at ~10 Hz."""
    read_prop_battery()
    read_elec_battery()


def read_all_slow():
    """Read slow sensors — DHT, hull. Call at ~0.3 Hz."""
    read_dht()
    read_hull()


# ---- Battery state predicates ----

def is_prop_critical():
    """Propulsion battery below LVC. Guard against ADC = 0 (sensor unplugged)."""
    return prop_batt_v > 5.0 and prop_batt_v <= P_CRIT


def is_prop_low():
    """Propulsion battery below warning level."""
    return prop_batt_v > 5.0 and prop_batt_v <= P_WARN


def is_elec_critical():
    """Electronics battery below LVC — Pi 5 about to brown out."""
    return elec_batt_v > 3.0 and elec_batt_v <= E_CRIT


def is_elec_low():
    """Electronics battery below warning level."""
    return elec_batt_v > 3.0 and elec_batt_v <= E_WARN


def hull_status():
    """Return 'DRY', 'L!', 'R!', or 'L!R!'."""
    s = ""
    if hull_leak_left:
        s += "L!"
    if hull_leak_right:
        s += "R!"
    return s if s else "DRY"


def both_hulls_leaking():
    return hull_leak_left and hull_leak_right
