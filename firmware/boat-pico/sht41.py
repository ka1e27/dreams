"""SHT41 temperature / humidity driver (Sensirion SHT4x family).

Two GY-SHT41-D breakout modules are fitted (see docs/pin_map.md). Each SHT41
has a *fixed* I2C address of 0x44, so the two sensors must live on two
*separate* I2C buses — they cannot share one bus.

This driver is bus-agnostic: construct it with an already-initialised
machine.I2C object, so the caller owns the pin assignment and bus number.
Replaces the previous single DHT11 on GP16 (the boat PCB has no DHT11).

Protocol (SHT4x):
  - Address 0x44 (fixed, not configurable).
  - Measure: write one command byte, wait for the conversion, then read 6
    bytes: [T_hi, T_lo, T_crc, RH_hi, RH_lo, RH_crc].
  - High-precision measure command = 0xFD (max conversion ~8.3 ms).
  - T_degC = -45 + 175 * t_ticks / 65535
    RH_pct = -6  + 125 * rh_ticks / 65535   (clamped to 0..100)
  - CRC8 over each value pair: poly 0x31, init 0xFF.
"""
import time

ADDR = 0x44
CMD_MEASURE_HIGH = 0xFD   # high precision (also 0xF6 med, 0xE0 low)
CMD_SOFT_RESET = 0x94


def _crc8(data):
    """Sensirion CRC8 — poly 0x31, init 0xFF."""
    crc = 0xFF
    for b in data:
        crc ^= b
        for _ in range(8):
            if crc & 0x80:
                crc = ((crc << 1) ^ 0x31) & 0xFF
            else:
                crc = (crc << 1) & 0xFF
    return crc


class SHT41:
    """One SHT41 on a given I2C bus (fixed address 0x44)."""

    def __init__(self, i2c, addr=ADDR):
        self.i2c = i2c
        self.addr = addr
        self.temp_c = 0.0
        self.humidity = 0.0
        self.ok = False          # True after a CRC-valid measurement

    def reset(self):
        """Soft-reset the sensor (best effort)."""
        if self.i2c is None:
            return
        try:
            self.i2c.writeto(self.addr, bytes([CMD_SOFT_RESET]))
            time.sleep_ms(2)
        except:
            pass

    def present(self):
        """Return True if the sensor ACKs on the bus."""
        if self.i2c is None:
            return False
        try:
            return self.addr in self.i2c.scan()
        except:
            return False

    def measure(self):
        """Trigger one high-precision read; update temp_c / humidity / ok.

        Returns True on a CRC-valid sample, False otherwise (ok mirrors this).
        """
        if self.i2c is None:
            self.ok = False
            return False
        try:
            self.i2c.writeto(self.addr, bytes([CMD_MEASURE_HIGH]))
            time.sleep_ms(10)            # >= 8.3 ms conversion time
            raw = self.i2c.readfrom(self.addr, 6)
        except:
            self.ok = False
            return False
        if len(raw) != 6:
            self.ok = False
            return False
        # Reject the sample if either CRC fails (bad cabling / noise).
        if _crc8(raw[0:2]) != raw[2] or _crc8(raw[3:5]) != raw[5]:
            self.ok = False
            return False
        t_ticks = (raw[0] << 8) | raw[1]
        rh_ticks = (raw[3] << 8) | raw[4]
        self.temp_c = -45.0 + 175.0 * t_ticks / 65535.0
        rh = -6.0 + 125.0 * rh_ticks / 65535.0
        self.humidity = 0.0 if rh < 0 else (100.0 if rh > 100 else rh)
        self.ok = True
        return True
