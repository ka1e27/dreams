"""Boat Pico main — async event loop tying all modules together.

This is the entry point for the Boat Pico firmware. It initialises all
hardware modules and runs the async task loop using uasyncio.

Architecture:
  - Pi 5 sends commands over USB serial (SET_HDG, SET_THR, HB, etc.)
  - Boat Pico reads sensors, drives motors, and reports telemetry
  - Heartbeat watchdog kills motors if Pi 5 goes silent

Pin map:
  GP0/GP1  — DEAD, do not use
  GP4/GP5  — UART1 (GPS + Pod, 9600 baud)
  GP6      — Left motor ESC PWM
  GP7      — Right motor ESC PWM
  GP8/GP9  — I2C0 (QMC5883P compass at 0x2C)
  GP12/GP13 — UART0 (HC-12 radio — legacy, unused in new arch)
  GP14     — Winch motor ESC PWM
  GP16     — DHT11
  GP17     — Hull leak left
  GP18     — Hull leak right
  GP26     — Battery ADC
  GP27     — Motor temp left ADC
  GP28     — Motor temp right ADC
"""
import uasyncio as asyncio
import time

import motor_control
import gps
import compass
import pod_uart
import sensors
import serial_handler as serial
import watchdog


# ---- Health flags (6-char binary: GPS,CMP,BAT,DHT,MOT,POD) ----

def _health_string():
    """Build sensor health flags string."""
    flags = ""
    flags += "1" if gps.is_healthy() else "0"
    flags += "1" if compass.is_healthy() else "0"
    flags += "1" if (sensors.batt_v > 3.0) else "0"
    flags += "1" if (sensors.air_temp > 0 or sensors.air_humidity > 0) else "0"
    flags += "1" if (not sensors.is_motor_critical()) else "0"
    flags += "1" if pod_uart.is_healthy() else "0"
    return flags


def _state_string():
    """Return current operational state."""
    rc, estop = motor_control.get_state()
    if estop:
        return "ESTOP"
    if rc:
        return "RC"
    return "ACTIVE" if watchdog.is_alive() else "IDLE"


# ---- Command handlers (wired to serial_handler callbacks) ----

def _handle_set_hdg(heading):
    """Pi 5 sets target heading — Pico doesn't navigate, just ACK.

    In this architecture the Pi 5 calculates bearing and sends SET_THR
    directly. SET_HDG is reserved for future use or heading-hold mode.
    For now, just acknowledge it.
    """
    if not (0 <= heading < 360):
        return False, "RANGE"
    return True, None


def _handle_set_thr(left, right):
    """Pi 5 commands motor throttle directly."""
    return motor_control.set_throttle(left, right)


def _handle_set_winch(speed):
    """Pi 5 commands winch speed."""
    return motor_control.set_winch(speed)


_pending_pod_seq = None


def _handle_req_tel(seq):
    """Pi 5 requests immediate telemetry."""
    serial.send_tel_with_seq(
        seq, gps.lat, gps.lon, compass.heading, gps.speed_knots,
        sensors.batt_v, sensors.batt_pct, sensors.hull_status(),
        sensors.mt_left, sensors.mt_right, _health_string())


def _handle_poll_pod(seq):
    """Pi 5 requests pod sensor data. Trigger a poll and save seq for response."""
    global _pending_pod_seq
    if not pod_uart.is_healthy() and not pod_uart.pod_ok:
        serial.nak(seq, "POLL_POD", "NO_POD")
        return
    _pending_pod_seq = seq
    pod_uart.poll()


def _handle_estop():
    """Emergency stop."""
    motor_control.estop()
    serial.alert("CRIT", "ESTOP_AUTO", "PI5_CMD")


def _handle_resume():
    """Resume after ESTOP."""
    motor_control.resume()


def _handle_heartbeat():
    """Heartbeat received from Pi 5."""
    watchdog.feed()


def _handle_set_trim(value):
    """Set motor trim."""
    return motor_control.set_trim(value)


def _handle_cal_compass(bearing):
    """Calibrate compass north."""
    return compass.calibrate_north(bearing)


def _handle_rc_override():
    """Enter RC passthrough mode."""
    motor_control.rc_override_on()
    serial.alert("INFO", "RC_ON")


def _handle_rc_release():
    """Exit RC passthrough mode."""
    motor_control.rc_override_off()
    serial.alert("INFO", "RC_OFF")


def _handle_get_status(seq):
    """Return full status."""
    overrides = "NONE"  # Safety overrides not managed by Pico in new arch
    serial.send_status(seq, _state_string(), _health_string(), overrides)


# ---- Watchdog timeout callback ----

def _on_heartbeat_lost():
    """Called when Pi 5 heartbeat times out."""
    motor_control.estop()
    serial.alert("CRIT", "HB_LOST")


# ---- Alert tracking state ----

_batt_warned = False
_hull_sent_l = False
_hull_sent_r = False
_mt_throttled = False
_pod_lost_sent = False


# ---- Async tasks ----

async def task_serial_rx():
    """Read and process commands from Pi 5 over USB serial."""
    while True:
        try:
            serial.read_usb()
        except:
            pass
        await asyncio.sleep(0.02)


async def task_fast_sensors():
    """Read GPS, compass, battery at ~10Hz. Poll pod periodically."""
    global _pending_pod_seq
    while True:
        try:
            gps.read()
            compass.read()
            sensors.read_battery()

            # Check for pending pod response
            if _pending_pod_seq is not None and pod_uart.is_healthy():
                d = pod_uart.get_data()
                serial.send_pod_data(
                    _pending_pod_seq, d["water_temp"], d["salinity_ec"],
                    d["light_pct"], d["bottom"], d["leak"])
                _pending_pod_seq = None
        except:
            pass
        await asyncio.sleep(0.1)


async def task_slow_sensors():
    """Read DHT, motor temps, hull leak at ~0.3Hz."""
    while True:
        try:
            sensors.read_all_slow()
        except:
            pass
        await asyncio.sleep(3)


async def task_pod_poll():
    """Periodically poll the pod for sensor data."""
    while True:
        try:
            pod_uart.poll()
        except:
            pass
        await asyncio.sleep(5)


async def task_motors():
    """Apply motor commands at ~10Hz."""
    while True:
        try:
            motor_control.update()
        except:
            pass
        await asyncio.sleep(0.1)


async def task_telemetry():
    """Send periodic telemetry to Pi 5."""
    while True:
        try:
            serial.send_tel(
                gps.lat, gps.lon, compass.heading, gps.speed_knots,
                sensors.batt_v, sensors.batt_pct, sensors.hull_status(),
                sensors.mt_left, sensors.mt_right, _health_string())
        except:
            pass
        await asyncio.sleep(1)


async def task_env_telemetry():
    """Send periodic environment data to Pi 5."""
    while True:
        try:
            serial.send_env(
                sensors.air_temp, sensors.air_humidity,
                pod_uart.water_temp, pod_uart.salinity_ec,
                pod_uart.light_pct, pod_uart.bottom_contact)
        except:
            pass
        await asyncio.sleep(5)


async def task_watchdog():
    """Check heartbeat and safety conditions at ~1Hz."""
    global _batt_warned, _hull_sent_l, _hull_sent_r
    global _mt_throttled, _pod_lost_sent
    while True:
        try:
            # Heartbeat watchdog
            watchdog.check()

            # Battery alerts
            if sensors.is_battery_critical():
                serial.alert("CRIT", "BATT_CRIT",
                             "%.2f,%d" % (sensors.batt_v, sensors.batt_pct))
            elif sensors.is_battery_low() and not _batt_warned:
                _batt_warned = True
                serial.alert("WARN", "BATT_LOW",
                             "%.2f,%d" % (sensors.batt_v, sensors.batt_pct))
            elif not sensors.is_battery_low():
                _batt_warned = False

            # Hull leak alerts
            if sensors.hull_leak_left and not _hull_sent_l:
                _hull_sent_l = True
                serial.alert("CRIT", "HULL_LEAK", "LEFT")
            elif not sensors.hull_leak_left:
                _hull_sent_l = False
            if sensors.hull_leak_right and not _hull_sent_r:
                _hull_sent_r = True
                serial.alert("CRIT", "HULL_LEAK", "RIGHT")
            elif not sensors.hull_leak_right:
                _hull_sent_r = False
            if sensors.both_hulls_leaking():
                motor_control.estop()
                serial.alert("CRIT", "HULL_LEAK", "BOTH")

            # Motor temperature alerts
            if sensors.is_motor_critical():
                mx = max(sensors.mt_left, sensors.mt_right)
                side = "LEFT" if sensors.mt_left >= sensors.mt_right else "RIGHT"
                motor_control.estop()
                serial.alert("CRIT", "MOTOR_OVERHEAT", "%s,%.0f" % (side, mx))
            elif sensors.is_motor_hot():
                if not _mt_throttled:
                    _mt_throttled = True
                    mx = max(sensors.mt_left, sensors.mt_right)
                    side = "LEFT" if sensors.mt_left >= sensors.mt_right else "RIGHT"
                    serial.alert("WARN", "MOTOR_HOT", "%s,%.0f" % (side, mx))
                    motor_control.set_throttle_mult(0.5)
            elif _mt_throttled:
                _mt_throttled = False
                motor_control.set_throttle_mult(1.0)
                serial.alert("INFO", "MOTOR_COOL",
                             "%.0f" % max(sensors.mt_left, sensors.mt_right))

            # Pod health
            if not pod_uart.is_healthy() and pod_uart.pod_ok:
                if not _pod_lost_sent:
                    _pod_lost_sent = True
                    serial.alert("WARN", "POD_LOST")
            elif pod_uart.is_healthy():
                _pod_lost_sent = False

            # Pod leak
            if pod_uart.leak_detected:
                serial.alert("CRIT", "POD_LEAK")

            # Sensor faults
            if not gps.is_healthy():
                serial.alert("WARN", "SENSOR_FAULT", "gps")
            if not compass.is_healthy():
                serial.alert("WARN", "SENSOR_FAULT", "compass")

        except:
            pass
        await asyncio.sleep(1)


# ---- UART1 shared reader (GPS + Pod on same bus) ----

async def task_uart1_reader():
    """Read UART1 and route lines to GPS parser or Pod parser."""
    _buf = bytearray(128)
    _pos = 0
    uart = gps._uart
    if uart is None:
        return
    while True:
        try:
            while uart.any():
                chunk = uart.read()
                if not chunk:
                    break
                for b in chunk:
                    if b == 0x0A:
                        if _pos > 0:
                            try:
                                line = _buf[:_pos].decode('utf-8', 'ignore').strip()
                                if line:
                                    # Route to appropriate parser
                                    if line[:4] in ('$GPR', '$GNR'):
                                        gps._parse_rmc(line)
                                    elif line[:4] == '$POD':
                                        pod_uart.process_line(line)
                            except:
                                pass
                        _pos = 0
                    elif b == 0x24:
                        _pos = 0
                        _buf[0] = b
                        _pos = 1
                    elif _pos < 128:
                        _buf[_pos] = b
                        _pos += 1
        except:
            pass
        await asyncio.sleep(0.05)


# ---- Main ----

async def main():
    """Initialise hardware and start all async tasks."""
    print("Boat Pico v5.0 (Pi 5 controlled)")

    # Init hardware
    motor_control.init()
    gps.init()
    compass_ok = compass.init()
    sensors.init()

    # Pod shares UART1 with GPS
    pod_uart.init(gps._uart)

    # Wire serial command handlers
    serial.on_set_hdg = _handle_set_hdg
    serial.on_set_thr = _handle_set_thr
    serial.on_set_winch = _handle_set_winch
    serial.on_req_tel = _handle_req_tel
    serial.on_poll_pod = _handle_poll_pod
    serial.on_estop = _handle_estop
    serial.on_resume = _handle_resume
    serial.on_heartbeat = _handle_heartbeat
    serial.on_set_trim = _handle_set_trim
    serial.on_cal_compass = _handle_cal_compass
    serial.on_rc_override = _handle_rc_override
    serial.on_rc_release = _handle_rc_release
    serial.on_get_status = _handle_get_status

    # Init watchdog (3s timeout)
    watchdog.init(timeout_ms=3000, on_timeout=_on_heartbeat_lost)

    # Print startup info
    print("  Motors: GP6(L) GP7(R) GP14(W)")
    print("  GPS: UART1 GP4/GP5 9600bd")
    print("  Compass: I2C0 GP8/GP9 addr=0x2C %s" % ("OK" if compass_ok else "FAIL"))
    if compass_ok:
        addrs = compass.scan_bus()
        print("  I2C scan: %s" % [hex(a) for a in addrs])
    print("  DHT11: GP16")
    print("  Hull: GP17(L) GP18(R)")
    print("  Battery: GP26  Motor temps: GP27(L) GP28(R)")
    print("  Watchdog: 3000ms heartbeat timeout")
    print("  Pulley L:%.3f R:%.3f" % (
        motor_control.PULLEY_L, motor_control.PULLEY_R))
    print("Ready — waiting for Pi 5")

    # Start all tasks
    await asyncio.gather(
        task_serial_rx(),
        task_uart1_reader(),
        task_fast_sensors(),
        task_slow_sensors(),
        task_pod_poll(),
        task_motors(),
        task_telemetry(),
        task_env_telemetry(),
        task_watchdog(),
    )

asyncio.run(main())
