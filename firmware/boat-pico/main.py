"""Boat Pico main — async event loop tying all modules together.

Single-hull test-bench variant: propulsion is two hobby ESCs on 50 Hz PWM
(escs.py) instead of the dual-hull boat's VESC / CAN chain, and the drive rail
is 2× M18 in parallel.

This is the entry point for the Boat Pico firmware. It initialises all
hardware modules and runs the async task loop using uasyncio.

Architecture:
  - Pi 5 sends commands over USB serial (SET_HDG, SET_THR, HB, etc.)
  - Boat Pico drives two ESCs via 50 Hz PWM (GP2/GP3), reads sensors, talks
    to the underwater pod, and reports telemetry
  - Heartbeat watchdog kills motors if Pi 5 goes silent (3 s). Dumb ESCs have no
    self-timeout, so this heartbeat → estop path is the motor kill.
  - SBUS receiver provides RC override; on link loss → ESTOP

Pin map (test bench):
  GP0/GP1   — DEAD, do not use
  GP2       — Left drive ESC (50 Hz PWM)   [free header pin]
  GP3       — Right drive ESC (50 Hz PWM)  [free header pin]
  GP4/GP5   — UART1 (GPS M10Q + Pod, shared bus, 9600 baud)
  GP6       — Winch ESC (50 Hz PWM)        [free header pin]
  GP7       — SBUS receiver (PIO)          [free header pin]
  GP8/GP9   — I2C0 (BNO085 IMU at 0x4A)
  GP10      — Status NeoPixel (WS2812, 1 pixel)
  GP12/GP13 — SHT41 #A air temp/humidity (SoftI2C, J11)
  GP14/GP15 — SHT41 #B air temp/humidity (SoftI2C, J13)
  GP16      — Left  ESC telemetry RX (AM32 KISS, PIO UART 115200)
  GP17      — Hull leak left
  GP18      — Hull leak right
  GP19      — Right ESC telemetry RX (AM32 KISS, PIO UART 115200)
  GP26      — Drive battery (2× M18 parallel) ADC — 130k/10k divider (×14.0)
  GP27      — Electronics battery (1× M18) ADC — 56k/10k divider (×6.6)
  GP28      — Winch battery (1× M18) ADC — 56k/10k divider (×6.6)

Both SHT41 temp sensors are kept on their native as-built pins (GP12-15); the
drive ESCs, winch and SBUS moved to free Pico header pins (GP2/3/6/7) so nothing
collides with them. See docs/hardware_changes_v2_to_testbench.md.
"""
import uasyncio as asyncio
import time
import machine

import motor_control
import gps
import compass
import pod_uart
import sensors
import serial_handler as serial
import watchdog
import escs
import esc_telem
import sbus
import status_led


# ---- Health flags (6-char binary: GPS,IMU,P_BAT,E_BAT,MOT,POD) ----

def _health_string():
    """Build sensor health flags string."""
    flags = ""
    flags += "1" if gps.is_healthy() else "0"
    flags += "1" if compass.is_healthy() else "0"
    flags += "0" if sensors.is_prop_critical() else "1"
    flags += "0" if sensors.is_elec_critical() else "1"
    flags += "1" if (escs.max_motor_temp() < 85.0) else "0"
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
    """Pi 5 sets target heading — Pico doesn't navigate, just ACK."""
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
    """Pi 5 requests immediate telemetry. Format kept stable; the mt_l/mt_r
    motor-temp fields are always 0.0 on the test bench (dumb ESCs report none)."""
    mt_l = escs.get_motor_temp(escs.LEFT) or 0.0
    mt_r = escs.get_motor_temp(escs.RIGHT) or 0.0
    serial.send_tel_with_seq(
        seq, gps.lat, gps.lon, compass.heading, gps.speed_knots,
        sensors.prop_batt_v, sensors.prop_batt_pct, sensors.hull_status(),
        mt_l, mt_r, _health_string(),
        escs.get_current(escs.LEFT) or 0.0, escs.get_current(escs.RIGHT) or 0.0)


def _handle_poll_pod(seq):
    """Pi 5 requests pod sensor data."""
    global _pending_pod_seq
    if not pod_uart.is_healthy() and not pod_uart.pod_ok:
        serial.nak(seq, "POLL_POD", "NO_POD")
        return
    _pending_pod_seq = seq
    pod_uart.poll()


def _handle_estop():
    motor_control.estop()
    serial.alert("CRIT", "ESTOP_AUTO", "PI5_CMD")


def _handle_resume():
    motor_control.resume()


def _handle_heartbeat():
    watchdog.feed()


def _handle_set_trim(value):
    return motor_control.set_trim(value)


def _handle_cal_compass(bearing):
    return compass.calibrate_north(bearing)


def _handle_rc_override():
    motor_control.rc_override_on()
    serial.alert("INFO", "RC_ON")


def _handle_rc_release():
    motor_control.rc_override_off()
    serial.alert("INFO", "RC_OFF")


def _handle_get_status(seq):
    overrides = "NONE"
    serial.send_status(seq, _state_string(), _health_string(), overrides)


# ---- Watchdog timeout callback ----

def _on_heartbeat_lost():
    motor_control.estop()
    serial.alert("CRIT", "HB_LOST")


def _battery_alert(name, is_crit, is_low, was_warned, v, pct):
    """Emit battery alerts and return the new warned flag.

    Edge-triggered warning (only on the low→low transition); critical fires
    every cycle while the condition holds so the operator can't miss it.
    """
    if is_crit:
        serial.alert("CRIT", name + "_BATT_CRIT", "%.2f,%d" % (v, pct))
        return was_warned
    if is_low:
        if not was_warned:
            serial.alert("WARN", name + "_BATT_LOW", "%.2f,%d" % (v, pct))
        return True
    return False


# ---- Alert tracking state ----

_prop_batt_warned = False
_elec_batt_warned = False
_hull_sent_l = False
_hull_sent_r = False
_pod_lost_sent = False
_sbus_warned = False
_motor_hot_warned = False

# ESC/motor over-temperature warning threshold (°C). WARN only — an auto-ESTOP on
# overheat could strand the boat mid-water, so escalation is left to the operator.
# To make it also cut the motors, add motor_control.estop() beside the alert below.
_MOTOR_WARN_C = 80.0


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
    """Read GPS, IMU, batteries, and pod responses at ~10 Hz."""
    global _pending_pod_seq
    while True:
        try:
            # Do NOT read UART1 here — task_uart1_reader is the SOLE UART1 reader; it
            # demuxes $GP*/$GN* to gps._parse_rmc and $POD to pod_uart. A second
            # gps.read() raced it, so each stole bytes from the other and GPS fixes
            # *and* $POD frames (incl. the pod leak flag) were intermittently lost.
            compass.read()
            sensors.read_all_fast()

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
    """Read SHT41 air temp/humidity (×2) + hull leak switches at ~0.3 Hz."""
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
    """Apply motor commands at ~10 Hz. While RC override is active, source
    the throttle from SBUS channels instead of Pi 5 commands."""
    while True:
        try:
            if motor_control.is_rc_override():
                if sbus.is_link_alive():
                    chans = sbus.read_channels()
                    # Channel mapping (mode-2 stick layout):
                    #   ch1 (idx 0): right-stick X — yaw / steering
                    #   ch3 (idx 2): right-stick Y — throttle (or left-Y, configurable)
                    #   ch5 (idx 4): winch up/down
                    throttle = sbus.channel_to_pct(chans[2])
                    yaw = sbus.channel_to_pct(chans[0])
                    left = max(-100, min(100, throttle + yaw))
                    right = max(-100, min(100, throttle - yaw))
                    motor_control.set_throttle_rc(left, right)
                    motor_control.set_winch_rc(sbus.channel_to_pct(chans[4]))
                else:
                    # Lost link while in RC mode — failsafe.
                    motor_control.set_throttle_rc(0, 0)
                    motor_control.set_winch_rc(0)
            motor_control.update()
        except:
            pass
        await asyncio.sleep(0.1)


async def task_sbus():
    """Drain the SBUS PIO FIFO at ~50 Hz."""
    while True:
        try:
            sbus.poll()
        except:
            pass
        await asyncio.sleep(0.02)


async def task_esc_telem():
    """Drain the AM32 KISS telemetry RX FIFOs at ~100 Hz.

    Fast enough that a 10-byte frame never overflows the 32-byte PIO buffer even
    if the ESC streams telemetry every ~20 ms. escs.get_motor_temp()/get_current()
    read the values this parses."""
    while True:
        try:
            esc_telem.poll()
        except:
            pass
        await asyncio.sleep(0.01)


async def task_telemetry():
    """Send periodic telemetry to Pi 5."""
    while True:
        try:
            mt_l = escs.get_motor_temp(escs.LEFT) or 0.0
            mt_r = escs.get_motor_temp(escs.RIGHT) or 0.0
            serial.send_tel(
                gps.lat, gps.lon, compass.heading, gps.speed_knots,
                sensors.prop_batt_v, sensors.prop_batt_pct,
                sensors.hull_status(), mt_l, mt_r, _health_string(),
                escs.get_current(escs.LEFT) or 0.0, escs.get_current(escs.RIGHT) or 0.0)
        except:
            pass
        await asyncio.sleep(1)


async def task_telemetry_ext():
    """Send extended telemetry with the dual-battery + IMU fields.

    The v_in field carries the drive-rail voltage from the ADC (there is no VESC
    to report its own input voltage); the fault fields are always 0 (dumb ESCs)."""
    while True:
        try:
            serial.send_tel2_ext(
                sensors.prop_batt_v, sensors.prop_batt_pct,
                sensors.elec_batt_v, sensors.elec_batt_pct,
                compass.pitch, compass.roll, compass.cal_status,
                sensors.prop_batt_v,
                escs.get_fault(escs.LEFT), escs.get_fault(escs.RIGHT))
        except:
            pass
        await asyncio.sleep(2)


async def task_env_telemetry():
    """Send periodic environment data to Pi 5.

    Carries the open-air SHT41 (#A) + water + bottom, plus the ENV v1.1 appendix:
    the enclosure SHT41 (#B) and the M18 electronics / M18 winch battery rails (the
    M18 drive rail rides in TEL as batt_v)."""
    while True:
        try:
            serial.send_env(
                sensors.air_temp, sensors.air_humidity,
                pod_uart.water_temp, pod_uart.salinity_ec,
                pod_uart.light_pct, pod_uart.bottom_contact,
                sensors.air_temp2, sensors.air_humidity2,
                sensors.elec_batt_v, sensors.elec_batt_pct,
                sensors.winch_batt_v, sensors.winch_batt_pct)
        except:
            pass
        await asyncio.sleep(5)


async def task_watchdog():
    """Heartbeat + safety checks at ~1 Hz."""
    global _prop_batt_warned, _elec_batt_warned
    global _hull_sent_l, _hull_sent_r
    global _pod_lost_sent, _sbus_warned, _motor_hot_warned
    while True:
        try:
            watchdog.check()

            _prop_batt_warned = _battery_alert(
                "PROP",
                sensors.is_prop_critical(), sensors.is_prop_low(),
                _prop_batt_warned,
                sensors.prop_batt_v, sensors.prop_batt_pct)
            _elec_batt_warned = _battery_alert(
                "ELEC",
                sensors.is_elec_critical(), sensors.is_elec_low(),
                _elec_batt_warned,
                sensors.elec_batt_v, sensors.elec_batt_pct)

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

            # Motor over-temperature (edge-triggered WARN). Real ESC temps now
            # come from AM32 KISS telemetry via esc_telem; max_motor_temp() is
            # 0.0 when no telemetry is arriving, so this never false-trips.
            hot = escs.max_motor_temp()
            if hot >= _MOTOR_WARN_C:
                if not _motor_hot_warned:
                    _motor_hot_warned = True
                    serial.alert("WARN", "MOTOR_HOT", "%.0f" % hot)
            elif hot < _MOTOR_WARN_C - 5.0:
                _motor_hot_warned = False

            # SBUS link health (only matters while RC override is active)
            if motor_control.is_rc_override():
                if not sbus.is_link_alive():
                    if not _sbus_warned:
                        _sbus_warned = True
                        motor_control.estop()
                        serial.alert("CRIT", "SBUS_LOST")
                else:
                    _sbus_warned = False

            # Pod health
            if not pod_uart.is_healthy() and pod_uart.pod_ok:
                if not _pod_lost_sent:
                    _pod_lost_sent = True
                    serial.alert("WARN", "POD_LOST")
            elif pod_uart.is_healthy():
                _pod_lost_sent = False

            if pod_uart.leak_detected:
                serial.alert("CRIT", "POD_LEAK")

            # Sensor faults
            if not gps.is_healthy():
                serial.alert("WARN", "SENSOR_FAULT", "gps")
            if not compass.is_healthy():
                serial.alert("WARN", "SENSOR_FAULT", "imu")

        except:
            pass
        await asyncio.sleep(1)


# ---- Status LED ----

def _compute_led_mode():
    """Derive NeoPixel mode from current state and active alerts.

    Priority: ESTOP > CRIT > RC (with SBUS warn) > WARN > ACTIVE > IDLE.
    """
    rc, estop = motor_control.get_state()
    if estop:
        return "ESTOP"
    if (sensors.hull_leak_left or sensors.hull_leak_right
            or pod_uart.leak_detected
            or sensors.is_prop_critical() or sensors.is_elec_critical()):
        return "CRIT"
    if rc:
        if not sbus.is_link_alive():
            return "WARN"
        return "RC"
    if (sensors.is_prop_low() or sensors.is_elec_low()
            or not gps.is_healthy() or not compass.is_healthy()
            or (pod_uart.pod_ok and not pod_uart.is_healthy())):
        return "WARN"
    if watchdog.is_alive():
        return "ACTIVE"
    return "IDLE"


async def task_status_led():
    """Update the status NeoPixel at ~20 Hz."""
    while True:
        try:
            status_led.set_mode(_compute_led_mode())
            status_led.update(time.ticks_ms())
        except:
            pass
        await asyncio.sleep(0.05)


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
    print("Boat Pico v6.0-testbench (2x hobby ESC + BNO085 + 2x M18 parallel drive)")

    status_led.init()
    escs_ok = motor_control.init()
    gps.init()
    imu_ok = compass.init()
    sensors.init()
    sbus_ok = sbus.init()
    telem_ok = esc_telem.init()

    # Pod shares UART1 with GPS
    pod_uart.init(gps._uart)

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

    watchdog.init(timeout_ms=3000, on_timeout=_on_heartbeat_lost)

    print("  Drive ESCs: GP%d(L)/GP%d(R) PWM 50Hz %s" % (
        escs.LEFT_PIN, escs.RIGHT_PIN, "OK" if escs_ok else "FAIL"))
    if not escs_ok:
        print("  !! DRIVE ESC INIT FAILED — ESTOP cannot neutralise motors; do NOT arm")
    print("  Winch: GP%d PWM 50Hz" % motor_control.MW_PIN)
    print("  GPS: UART1 GP4/GP5 9600bd (M10Q)")
    print("  IMU: I2C0 GP8/GP9 addr=0x4A %s" % ("OK" if imu_ok else "FAIL"))
    if imu_ok:
        print("  I2C scan: %s" % [hex(a) for a in compass.scan_bus()])
    print("  SBUS: PIO GP%d %s" % (sbus.SBUS_PIN, "OK" if sbus_ok else "FAIL"))
    print("  ESC telem: PIO GP%d(L)/GP%d(R) 115200 %s" % (
        esc_telem.TELEM_L_PIN, esc_telem.TELEM_R_PIN, "OK" if telem_ok else "FAIL"))
    print("  Status LED: NeoPixel GP%d" % status_led.PIN)
    print("  SHT41 #A: SoftI2C GP%d/GP%d (J11)  #B: GP%d/GP%d (J13)" % (
        sensors.SHT_A_SDA, sensors.SHT_A_SCL,
        sensors.SHT_B_SDA, sensors.SHT_B_SCL))
    print("  Hull: GP17(L) GP18(R)")
    print("  Drive batt: GP26 (2xM18)  Elec batt: GP27 (M18)  Winch batt: GP28 (M18)")
    print("  Watchdog: 3000ms heartbeat timeout")
    print("Ready — waiting for Pi 5")

    tasks = [
        asyncio.create_task(task_serial_rx()),
        asyncio.create_task(task_uart1_reader()),
        asyncio.create_task(task_fast_sensors()),
        asyncio.create_task(task_slow_sensors()),
        asyncio.create_task(task_pod_poll()),
        asyncio.create_task(task_motors()),
        asyncio.create_task(task_sbus()),
        asyncio.create_task(task_esc_telem()),
        asyncio.create_task(task_telemetry()),
        asyncio.create_task(task_telemetry_ext()),
        asyncio.create_task(task_env_telemetry()),
        asyncio.create_task(task_watchdog()),
        asyncio.create_task(task_status_led()),
    ]

    # Run until the Pi requests a reflash (REFLASH → drop to REPL for mpremote)
    # or an ESC passthrough (ESC_PASS → bridge the USB-CDC to an ESC one-wire).
    # Both first stop the motors and cancel every task.
    while not serial.reflash_requested and serial.passthrough_requested is None:
        await asyncio.sleep(0.1)

    try:
        motor_control.estop()
    except:
        pass
    for t in tasks:
        t.cancel()

    if serial.passthrough_requested is not None:
        esc_id, baud = serial.passthrough_requested
        # NB: do NOT print here — stdout IS the pipe about to be handed to the ESC /
        # am32.ca, so any banner bytes corrupt the stream (and get misread as an ESC
        # reply). The Pi already has the ESC_PASS ACK as its confirmation.
        try:
            import esc_passthrough
            esc_passthrough.bridge(esc_id, baud)   # repurposes CDC; resets on exit
        except Exception as e:
            print("ESC passthrough error: %s" % e)
            machine.reset()
    else:
        print("REFLASH requested — dropping to REPL")


asyncio.run(main())
