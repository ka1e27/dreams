"""Onboard hull sensors — triple battery, air temp/humidity (SHT41 ×2), hull leak.

Single-hull test-bench variant. Motor temperatures used to live here as NTC
thermistors on GP27/GP28; that job moved off-board (the VESCs reported temp on the
dual-hull boat). The freed ADCs now monitor the electronics and winch batteries.

Air temp/humidity is two Sensirion **SHT41** I2C modules, KEPT on this variant on
their native as-built pins (the drive ESCs / SBUS moved to free Pico header pins
instead, and the winch to GP21 where the board actually wires it — see
docs/hardware_changes_v2_to_testbench.md). Both SHT41s share the
fixed address 0x44, so each sits on its own bit-banged SoftI2C bus:

  - SHT41 #A → J11 (GP12 SDA / GP13 SCL)   → `air_temp`  / `air_humidity`
  - SHT41 #B → J13 (GP14 SDA / GP15 SCL)   → `air_temp2` / `air_humidity2`

SoftI2C is used because I2C0 (GP8/GP9) is owned by the BNO085 (compass.py). Unlike
the dual-hull firmware — where GP12-15 collided with VESC/winch/SBUS — on this
variant nothing else touches GP12-15, so both SHT41s run without a pin clash.

Battery architecture — three fully isolated Milwaukee M18 domains (see
docs/battery_architecture.md). The DRIVE rail on this test-bench variant is
2× M18 in PARALLEL (18 V nom / 21 V max) — same voltage as one pack, double the
current capacity, for the twin 2814 drive motors. ADCs are on this Boat Pico
(RP2040, 3.3 V), not the Pi 5.

Pin assignments:
  - Drive battery (2× M18 parallel, 18 V nom / 21 V max) ADC: GP26 (ADC0)
      — divider 56k/10k → ×6.6; 21 V → 3.18 V
  - Electronics battery (1× M18, 18 V nom / 21 V max) ADC: GP27 (ADC1)
      — divider 56k/10k → ×6.6; 21 V → 3.18 V
  - Winch battery (1× M18, 18 V nom / 21 V max) ADC: GP28 (ADC2)
      — divider 56k/10k → ×6.6; 21 V → 3.18 V
  - SHT41 #A:        GP12 (SDA) / GP13 (SCL)   [SoftI2C, J11]  — open air
  - SHT41 #B:        GP14 (SDA) / GP15 (SCL)   [SoftI2C, J13]  — electronics enclosure
  - (no hull leak — see below)

⚠ HULL LEAK SENSING REMOVED 2026-07-30. GP19/GP20 (J16/J15) are now the two drive
ESC signal outputs (`escs.py`) — the board gives GP2/GP3 to the MCP2515, so
propulsion had to move onto real connectors. This module must NOT touch GP19/GP20:
`sensors.init()` runs *after* `motor_control.init()`, so configuring them as
pull-up inputs would fight the ESC PWM already running on them.

The pod's leak sensor (`pod_uart.leak_detected`) is unaffected and remains the
boat's leak alarm. `hull_status()` now reports `--` (no sensor) instead of `DRY`,
so telemetry does not assert a dry hull it can no longer measure.
Hull leak had moved GP17/GP18 -> GP19/GP20 on 2026-07-28 to match the Boat_PCB V2
connectors; that assignment is now retired entirely.

All three dividers are 56k/10k on the physical board (confirmed by the builder,
2026-07-28), so every rail reconstructs at the same x6.6 and INV_P_RATIO was
changed 14.0 -> 6.6 to match. NOTE: the KiCad schematic/netlist still carries the
pre-M18 values (drive 220k/13k, elec 100k/30k, winch 100k/18k) — the board is
right and the schematic is stale, so trust these constants over a netlist export
until KiCad is updated. See docs/battery_architecture.md.
"""
from machine import Pin, ADC, SoftI2C
import sht41

# ---- Drive battery (2× M18 PARALLEL, 18 V nominal) ----
# Two M18 packs in parallel = one pack's voltage (18 V nom / 21 V max / 15 V
# cutoff), double the current. Thresholds are therefore a SINGLE M18's — the same
# as the elec/winch domains. (This is the change that matters: on the old 2×
# series 42 V thresholds a full 21 V parallel pack would read as "empty" and
# ESTOP instantly.) INV_P_RATIO must match the PHYSICAL drive divider, which is
# 56k/10k like the other two domains — all three rails reconstruct at the same
# ×6.6 and sit at 3.18 V full, just under the 3.3 V ADC ceiling.
# `prop_*` names kept for wire/protocol compatibility.
INV_P_RATIO = 6.6     # 56k/10k, same as elec/winch (was 14.0 for the old 130k/10k)
P_FULL = 21.0   # 1× M18 full (packs in parallel share this voltage)
P_EMPTY = 15.0  # cutoff → % floor
P_WARN = 17.0
P_CRIT = 16.0   # → return to home
P_RANGE = P_FULL - P_EMPTY

# ---- Electronics battery (1× M18) ----
# Divider 56k high / 10k low → reconstruct ×(56+10)/10 = 6.6. 21 V → 3.18 V.
INV_E_RATIO = 6.6
E_FULL = 21.0   # full
E_EMPTY = 15.0  # cutoff → % floor
E_WARN = 17.0
E_CRIT = 16.0   # → alert operator
E_RANGE = E_FULL - E_EMPTY

# ---- Winch battery (1× M18) ----
# Divider 56k high / 10k low → reconstruct ×6.6, identical to the elec domain.
# Now a dedicated standalone M18 pack — no more 4S LiPo / 12S midpoint tap.
INV_W_RATIO = 6.6
W_FULL = 21.0   # full
W_EMPTY = 15.0  # cutoff → % floor
W_WARN = 17.0
W_CRIT = 16.0   # → disable winch
W_RANGE = W_FULL - W_EMPTY

# ---- Air temp/humidity (two SHT41 on separate SoftI2C buses) ----
# Kept on their native as-built pins; the drive ESCs / winch / SBUS moved to free
# Pico header pins on this variant so GP12-15 are free for the temp sensors.
SHT_A_SDA = 12
SHT_A_SCL = 13
SHT_B_SDA = 14
SHT_B_SCL = 15
SHT_FREQ = 100_000   # 100 kHz — comfortable for bit-banged I2C + cabling

# ---- Hardware handles ----
_prop_adc = None
_elec_adc = None
_winch_adc = None
_sht_a = None
_sht_b = None

# ---- Sensor readings ----
prop_batt_v = 0.0
prop_batt_pct = 0
elec_batt_v = 0.0
elec_batt_pct = 0
winch_batt_v = 0.0    # M18 winch pack (GP28 ADC2)
winch_batt_pct = 0
air_temp = 0.0        # SHT41 #A (J11) — open air
air_humidity = 0.0
air_temp2 = 0.0       # SHT41 #B (J13) — electronics enclosure
air_humidity2 = 0.0


def init():
    """Initialise all onboard sensor hardware."""
    global _prop_adc, _elec_adc, _winch_adc, _sht_a, _sht_b
    try:
        _prop_adc = ADC(26)
    except:
        pass
    try:
        _elec_adc = ADC(27)
    except:
        pass
    try:
        _winch_adc = ADC(28)
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
    # No hull-leak pins here any more: GP19/GP20 (J16/J15) carry the drive ESC
    # PWM now, and this runs after motor_control.init() has already started it.


def _read_battery_voltage(adc, inv_ratio):
    """Return the voltage at the battery side of a divider, averaged 16x."""
    if adc is None:
        return 0.0
    total = 0
    for _ in range(16):
        total += adc.read_u16()
    return (total / 16.0 / 65535.0 * 3.3) * inv_ratio


def read_prop_battery():
    """Read drive (2× M18 series) battery voltage and percentage."""
    global prop_batt_v, prop_batt_pct
    try:
        prop_batt_v = _read_battery_voltage(_prop_adc, INV_P_RATIO)
        prop_batt_pct = max(0, min(100,
                                   int((prop_batt_v - P_EMPTY) / P_RANGE * 100)))
    except:
        pass


def read_elec_battery():
    """Read electronics (1× M18) battery voltage and percentage."""
    global elec_batt_v, elec_batt_pct
    try:
        elec_batt_v = _read_battery_voltage(_elec_adc, INV_E_RATIO)
        elec_batt_pct = max(0, min(100,
                                   int((elec_batt_v - E_EMPTY) / E_RANGE * 100)))
    except:
        pass


def read_winch_battery():
    """Read winch (1× M18) battery voltage and percentage from GP28."""
    global winch_batt_v, winch_batt_pct
    try:
        winch_batt_v = _read_battery_voltage(_winch_adc, INV_W_RATIO)
        winch_batt_pct = max(0, min(100,
                                    int((winch_batt_v - W_EMPTY) / W_RANGE * 100)))
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


def read_all_fast():
    """Read fast sensors — all three battery rails. Call at ~10 Hz."""
    read_prop_battery()
    read_elec_battery()
    read_winch_battery()


def read_all_slow():
    """Read slow sensors — SHT41 air temp/humidity ×2. Call at ~0.3 Hz."""
    read_temp_humidity()


# ---- Battery state predicates ----

def is_prop_critical():
    """Drive battery below cutoff. Guard against ADC = 0 (sensor unplugged)."""
    return prop_batt_v > 5.0 and prop_batt_v <= P_CRIT


def is_prop_low():
    """Drive battery below warning level."""
    return prop_batt_v > 5.0 and prop_batt_v <= P_WARN


def is_elec_critical():
    """Electronics battery below LVC — Pi 5 about to brown out."""
    return elec_batt_v > 3.0 and elec_batt_v <= E_CRIT


def is_elec_low():
    """Electronics battery below warning level."""
    return elec_batt_v > 3.0 and elec_batt_v <= E_WARN


def hull_status():
    """Return '--' — the hull leak switches no longer exist.

    GP19/GP20 became the drive ESC outputs on 2026-07-30, so there is nothing to
    read. This deliberately does NOT return 'DRY': that would assert a dry hull
    on a boat with no hull sensor. '--' is the TEL "no sensor" value (see
    docs/serial-protocol.md) and the Pi treats it as "not a leak" rather than as
    a leak. The pod leak sensor is unaffected — see pod_uart.leak_detected.
    """
    return "--"
