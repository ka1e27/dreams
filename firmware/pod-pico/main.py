"""Pod Pico main — async loop for underwater sensor pod.

Reads sensors continuously and responds to POLL commands from
the Boat Pico over UART.

Pin map:
  GP0/GP1  — UART0 (link to Boat Pico through slip ring, 9600 baud)
  GP17     — EC drive pin (digital out, pulsed)
  GP20     — Leak detection sensor (pull-up, active low)
  GP21     — Bottom contact switch (pull-up, active low)
  GP25     — Onboard LED (heartbeat indicator)
  GP26     — Temperature NTC (ADC0)
  GP27     — EC probe ADC (ADC1)
  GP28     — Light sensor (ADC2)
"""
from machine import Pin
import uasyncio as asyncio
import time

import sensors
import leak_detect
import uart_responder

led = Pin(25, Pin.OUT, value=1)


async def task_sensors():
    """Read all sensors at ~5Hz."""
    while True:
        try:
            sensors.read_all()
            leak_detect.read()
        except:
            pass
        await asyncio.sleep(0.2)


async def task_uart():
    """Check for POLL commands and respond."""
    while True:
        try:
            polled = uart_responder.read()
            if polled:
                led.toggle()
        except:
            pass
        await asyncio.sleep(0.05)


async def task_status():
    """Print local status periodically for debug."""
    cycle = 0
    while True:
        if cycle >= 24:
            cycle = 0
            lk = " LEAK!" if leak_detect.leak_detected else ""
            btm = " BTM" if sensors.bottom_contact else ""
            print("  T:%.1fC EC:%.0fuS L:%d%%%s%s" % (
                sensors.water_temp, sensors.salinity_ec,
                sensors.light_pct, btm, lk))
        else:
            cycle += 1
        await asyncio.sleep(0.2)


async def main():
    """Initialise hardware and start async tasks."""
    print("Sensor Pod v5.0")
    print("  UART: GP0/GP1 9600bd")
    print("  Temp: GP26  EC: GP17(drive)/GP27(adc)  Light: GP28")
    print("  Bottom: GP21  Leak: GP20")
    print("  EC: simple drive, %dR series, K=%.0f/m" % (
        sensors.EC_SERIES, sensors.EC_CELL_K))

    sensors.init()
    leak_detect.init()
    uart_responder.init(sensors, leak_detect)

    print("Ready — waiting for polls")

    await asyncio.gather(
        task_sensors(),
        task_uart(),
        task_status(),
    )

asyncio.run(main())
