"""Underwater sensor pod — EC probe, NTC thermistor, light sensor.

Extracted from reference/Pod_pico.py. Reads water temperature (NTC),
electrical conductivity (simple 2-electrode probe with drive pin),
and ambient light level.

Pin assignments:
  - Temperature NTC: GP26 (ADC0)
  - EC drive pin:    GP17 (digital out, pulsed)
  - EC ADC:          GP27 (ADC1)
  - Light sensor:    GP28 (ADC2)
  - Bottom contact:  GP21 (pull-up, active low)
  - Pressure sensor: GP22 (ADC, submersible pressure transducer)
"""
from machine import Pin, ADC
import math
import time

# NTC thermistor constants
TH_NOM = 10000
TH_B = 3950
TH_R = 10000
INV_T_NOM = 1.0 / 298.15
INV_B = 1.0 / TH_B

# EC probe constants
EC_CELL_K = 1000.0
EC_SERIES = 4700  # Series resistor in ohms

# Pressure sensor constants
# Sensor outputs 0.5V at 0 psi, 4.5V at max psi (typically 15 psi for shallow water)
# Voltage divider scales 4.5V → 3.3V range for Pico ADC
PRESSURE_MAX_PSI = 15.0
PRESSURE_V_MIN = 0.5
PRESSURE_V_MAX = 4.5
# 1 psi = 0.703 metres of water head
PSI_TO_METRES = 0.703

# Hardware handles
_temp_adc = None
_ec_adc = None
_ec_drive = None
_light_adc = None
_bottom_btn = None
_pressure_adc = None

# Sensor readings
water_temp = -999.0
salinity_ec = 0.0
light_raw = 0
light_pct = 0
bottom_contact = False
pressure_depth_m = 0.0


def init():
    """Initialise all sensor hardware."""
    global _temp_adc, _ec_adc, _ec_drive, _light_adc, _bottom_btn, _pressure_adc
    try:
        _temp_adc = ADC(26)
    except:
        pass
    try:
        _ec_adc = ADC(27)
        _ec_drive = Pin(17, Pin.OUT, value=0)
    except:
        pass
    try:
        _light_adc = ADC(28)
    except:
        pass
    try:
        _bottom_btn = Pin(21, Pin.IN, Pin.PULL_UP)
    except:
        pass
    try:
        _pressure_adc = ADC(22)
    except:
        pass


def read_temp():
    """Read water temperature from NTC thermistor.

    Uses Steinhart-Hart B-parameter equation. 8-sample average.
    Sets water_temp to -999.0 on error.
    """
    global water_temp
    if _temp_adc is None:
        water_temp = -999.0
        return
    try:
        total = 0
        for _ in range(8):
            total += _temp_adc.read_u16()
        raw = total >> 3
        if raw < 100 or raw > 65400:
            water_temp = -999.0
            return
        resistance = TH_R * raw / (65535.0 - raw)
        if resistance <= 0:
            water_temp = -999.0
            return
        steinhart = math.log(resistance / TH_NOM) * INV_B + INV_T_NOM
        if steinhart <= 0:
            water_temp = -999.0
            return
        water_temp = 1.0 / steinhart - 273.15
    except:
        water_temp = -999.0


def read_ec():
    """Read electrical conductivity from 2-electrode probe.

    Drives one electrode HIGH for 15ms, reads voltage across series resistor,
    then turns off to reduce plating. 16-sample average.
    """
    global salinity_ec
    if _ec_adc is None or _ec_drive is None:
        salinity_ec = 0.0
        return
    try:
        _ec_drive.value(1)
        time.sleep_ms(15)
        total = 0
        for _ in range(16):
            total += _ec_adc.read_u16()
        _ec_drive.value(0)
        raw = total >> 4
        voltage = raw / 65535.0 * 3.3
        if voltage > 3.2:
            # Open circuit (air) — no water
            salinity_ec = 0.0
        elif voltage < 0.05:
            salinity_ec = 99999.0
        else:
            r_water = EC_SERIES * voltage / (3.3 - voltage)
            salinity_ec = EC_CELL_K * 10000.0 / r_water if r_water > 0.1 else 99999.0
    except:
        salinity_ec = 0.0


def read_light():
    """Read ambient light level. 8-sample average."""
    global light_raw, light_pct
    if _light_adc is None:
        light_raw = 0
        light_pct = 0
        return
    try:
        total = 0
        for _ in range(8):
            total += _light_adc.read_u16()
        light_raw = total >> 3
        light_pct = light_raw * 100 // 65535 if light_raw > 0 else 0
    except:
        light_raw = 0
        light_pct = 0


def read_bottom():
    """Read bottom contact switch (active low, pull-up)."""
    global bottom_contact
    if _bottom_btn is None:
        bottom_contact = False
        return
    bottom_contact = _bottom_btn.value() == 0


def read_pressure():
    """Read depth from submersible pressure transducer.

    Converts raw ADC to PSI, then to metres of water. 8-sample average.
    Assumes voltage divider scales sensor output to 0–3.3V Pico ADC range.
    """
    global pressure_depth_m
    if _pressure_adc is None:
        pressure_depth_m = 0.0
        return
    try:
        total = 0
        for _ in range(8):
            total += _pressure_adc.read_u16()
        raw = total >> 3
        voltage = raw / 65535.0 * 3.3
        # Map sensor voltage to PSI (linear 0.5V–4.5V → 0–max PSI)
        if voltage < PRESSURE_V_MIN:
            pressure_depth_m = 0.0
            return
        psi = (voltage - PRESSURE_V_MIN) / (PRESSURE_V_MAX - PRESSURE_V_MIN) * PRESSURE_MAX_PSI
        pressure_depth_m = max(0.0, psi * PSI_TO_METRES)
    except:
        pressure_depth_m = 0.0


def read_all():
    """Read all sensors. Call from main loop."""
    read_temp()
    read_ec()
    read_light()
    read_bottom()
    read_pressure()
