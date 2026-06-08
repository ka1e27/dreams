"""Onboard hull sensors — dual battery, air temp/humidity (SHT41 ×2), hull leak.

Motor temperatures used to live here as NTC thermistors on GP27/GP28; that
job moved to the VESCs (queried over UART by `vesc.py`). The freed ADCs
now monitor a second battery.

Air temp/humidity is now two Sensirion **SHT41** I2C modules (was a single
DHT11 on GP16, which the as-built Boat PCB does not have). Both SHT41s share
the fixed address 0x44, so each sits on its own bus:

  - SHT41 #A → J11 (GP12 SDA / GP13 SCL)   → `air_temp`  / `air_humidity`
  - SHT41 #B → J13 (GP14 SDA / GP15 SCL)   → `air_temp2` / `air_humidity2`

These use bit-banged ``SoftI2C``: the hardware I2C0 controller is already
owned by the BNO085 on GP8/GP9 (compass.py), and I2C1's pins clash with the
firmware's winch/SBUS assignments (see the warning below).

⚠ As-built pin conflict — GP12/GP13 are VESC UART0, GP14 is the winch PWM and
  GP15 is the SBUS input in vesc.py / motor_control.py / sbus.py. On the
  fabricated board the temp connectors J11/J13 occupy those pins, so those
  three modules are mis-pinned for this board and must be relocated off
  GP12-15 before the temp sensors can run without a pin clash. See
  docs/pin_map.md → "As-built board divergence".

Pin assignments:
  - Propulsion battery (12S LiPo) ADC: GP26 (ADC0)
      — voltage divider sized so 50.4 V → ≤ 3.3 V at the Pico pin
  - Electronics battery (3S Li-ion) ADC: GP27 (ADC1)
      — uses the legacy 15 / (15+100) divider; 12.6 V → 1.64 V
  - SHT41 #A:        GP12 (SDA) / GP13 (SCL)   [SoftI2C, J11]
  - SHT41 #B:        GP14 (SDA) / GP15 (SCL)   [SoftI2C, J13]
  - Hull leak left:  GP17
  - Hull leak right: GP18
  - GP28 (ADC2):     spare
"""
from machine import Pin, ADC, SoftI2C
import sht41

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

# ---- Air temp/humidity (two SHT41 on separate SoftI2C buses) ----
SHT_A_SDA = 12
SHT_A_SCL = 13
SHT_B_SDA = 14
SHT_B_SCL = 15
SHT_FREQ = 100_000   # 100 kHz — comfortable for bit-banged I2C + cabling

# ---- Hardware handles ----
_prop_adc = None
_elec_adc = None
_sht_a = None
_sht_b = None
_hull_l = None
_hull_r = None

# ---- Sensor readings ----
prop_batt_v = 0.0
prop_batt_pct = 0
elec_batt_v = 0.0
elec_batt_pct = 0
air_temp = 0.0        # SHT41 #A (J11)
air_humidity = 0.0
air_temp2 = 0.0       # SHT41 #B (J13)
air_humidity2 = 0.0
hull_leak_left = False
hull_leak_right = False


def init():
    """Initialise all onboard sensor hardware."""
    global _prop_adc, _elec_adc, _sht_a, _sht_b, _hull_l, _hull_r
    try:
        _prop_adc = ADC(26)
    except:
        pass
    try:
        _elec_adc = ADC(27)
    except:
        pass
    # SHT41 #A (J11) — bit-banged so it doesn't fight the BNO085 on I2C0.
    try:
        bus_a = SoftI2C(scl=Pin(SHT_A_SCL), sda=Pin(SHT_A_SDA), freq=SHT_FREQ)
        _sht_a = sht41.SHT41(bus_a)
        _sht_a.reset()
    except:
        _sht_a = None
    # SHT41 #B (J13).
    try:
        bus_b = SoftI2C(scl=Pin(SHT_B_SCL), sda=Pin(SHT_B_SDA), freq=SHT_FREQ)
        _sht_b = sht41.SHT41(bus_b)
        _sht_b.reset()
    except:
        _sht_b = None
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


def read_temp_humidity():
    """Read both SHT41 air temp/humidity sensors.

    `air_temp`/`air_humidity` track sensor A (J11); `air_temp2`/`air_humidity2`
    track sensor B (J13). A failed/CRC-bad read leaves the last value in place.
    """
    global air_temp, air_humidity, air_temp2, air_humidity2
    if _sht_a is not None and _sht_a.measure():
        air_temp = _sht_a.temp_c
        air_humidity = _sht_a.humidity
    if _sht_b is not None and _sht_b.measure():
        air_temp2 = _sht_b.temp_c
        air_humidity2 = _sht_b.humidity


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
    """Read slow sensors — SHT41 air temp/humidity ×2, hull. Call at ~0.3 Hz."""
    read_temp_humidity()
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
