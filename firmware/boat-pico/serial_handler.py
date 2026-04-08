"""Serial protocol handler for Pi 5 ↔ Boat Pico communication.

Implements the protocol defined in docs/serial-protocol.md.
Parses commands from Pi 5 over USB serial, dispatches to handlers,
sends responses and unsolicited telemetry/alerts.

Transport: USB CDC (/dev/ttyACM0 on Pi 5 side), 115200 baud.
Frame format: $<payload>*<checksum>\n
"""
import sys
import time

# Command handlers — set by main.py after importing modules
on_set_hdg = None
on_set_thr = None
on_set_winch = None
on_req_tel = None
on_poll_pod = None
on_estop = None
on_resume = None
on_heartbeat = None
on_set_trim = None
on_cal_compass = None
on_rc_override = None
on_rc_release = None
on_get_status = None

# Internal state
_rx_buf = bytearray(256)
_rx_pos = 0


def _checksum(payload):
    """XOR checksum over payload string."""
    cs = 0
    for ch in payload:
        cs ^= ord(ch)
    return cs


def _send(payload):
    """Frame and send a message over USB serial (stdout)."""
    cs = _checksum(payload)
    msg = "$%s*%d\n" % (payload, cs)
    sys.stdout.write(msg)


def ack(seq, cmd, *args):
    """Send an ACK response."""
    parts = ["ACK", str(seq), cmd]
    parts.extend(str(a) for a in args)
    _send(",".join(parts))


def nak(seq, cmd, reason):
    """Send a NAK response."""
    _send("NAK,%d,%s,%s" % (seq, cmd, reason))


def send_tel(lat, lon, heading, speed, batt_v, batt_pct, hull,
             mt_l, mt_r, health):
    """Send unsolicited telemetry (TEL). Seq=0."""
    _send("TEL,0,%.6f,%.6f,%.1f,%.1f,%.1f,%d,%s,%.0f,%.0f,%s" % (
        lat, lon, heading, speed, batt_v, batt_pct, hull,
        mt_l, mt_r, health))


def send_tel_with_seq(seq, lat, lon, heading, speed, batt_v, batt_pct, hull,
                      mt_l, mt_r, health):
    """Send telemetry with a specific sequence number (response to REQ_TEL)."""
    _send("TEL,%d,%.6f,%.6f,%.1f,%.1f,%.1f,%d,%s,%.0f,%.0f,%s" % (
        seq, lat, lon, heading, speed, batt_v, batt_pct, hull,
        mt_l, mt_r, health))


def send_env(air_t, air_h, water_t, water_ec, water_light, bottom):
    """Send unsolicited environment telemetry (ENV). Seq=0."""
    _send("ENV,0,%d,%d,%.1f,%.1f,%d,%d" % (
        air_t, air_h, water_t, water_ec, water_light,
        1 if bottom else 0))


def send_pod_data(seq, water_t, ec, light, bottom, leak):
    """Send pod sensor data response."""
    _send("POD_DATA,%d,%.1f,%.1f,%d,%d,%d" % (
        seq, water_t, ec, light,
        1 if bottom else 0, 1 if leak else 0))


def send_status(seq, state, health, overrides):
    """Send status response."""
    _send("STATUS,%d,%s,%s,%s" % (seq, state, health, overrides))


def alert(severity, code, detail=""):
    """Send an unsolicited alert. Seq=0."""
    if detail:
        _send("ALERT,0,%s,%s,%s" % (severity, code, detail))
    else:
        _send("ALERT,0,%s,%s" % (severity, code))


def _dispatch(payload):
    """Parse a validated payload and dispatch to the appropriate handler."""
    parts = payload.split(",")
    if len(parts) < 2:
        return
    cmd = parts[0]
    try:
        seq = int(parts[1])
    except:
        return

    if cmd == "SET_HDG" and len(parts) >= 3:
        try:
            hdg = float(parts[2])
            if on_set_hdg:
                ok, reason = on_set_hdg(hdg)
                if ok:
                    ack(seq, "SET_HDG", "%.1f" % hdg)
                else:
                    nak(seq, "SET_HDG", reason)
            else:
                nak(seq, "SET_HDG", "NO_HANDLER")
        except:
            nak(seq, "SET_HDG", "PARSE")

    elif cmd == "SET_THR" and len(parts) >= 4:
        try:
            left = int(parts[2])
            right = int(parts[3])
            if on_set_thr:
                ok, reason = on_set_thr(left, right)
                if ok:
                    ack(seq, "SET_THR", left, right)
                else:
                    nak(seq, "SET_THR", reason)
            else:
                nak(seq, "SET_THR", "NO_HANDLER")
        except:
            nak(seq, "SET_THR", "PARSE")

    elif cmd == "SET_WINCH" and len(parts) >= 3:
        try:
            speed = int(parts[2])
            if on_set_winch:
                ok, reason = on_set_winch(speed)
                if ok:
                    ack(seq, "SET_WINCH", speed)
                else:
                    nak(seq, "SET_WINCH", reason)
            else:
                nak(seq, "SET_WINCH", "NO_HANDLER")
        except:
            nak(seq, "SET_WINCH", "PARSE")

    elif cmd == "REQ_TEL":
        if on_req_tel:
            on_req_tel(seq)
        else:
            nak(seq, "REQ_TEL", "NO_HANDLER")

    elif cmd == "POLL_POD":
        if on_poll_pod:
            on_poll_pod(seq)
        else:
            nak(seq, "POLL_POD", "NO_HANDLER")

    elif cmd == "ESTOP":
        if on_estop:
            on_estop()
        ack(seq, "ESTOP")

    elif cmd == "RESUME":
        if on_resume:
            on_resume()
        ack(seq, "RESUME")

    elif cmd == "HB":
        if on_heartbeat:
            on_heartbeat()
        ack(seq, "HB")

    elif cmd == "SET_TRIM" and len(parts) >= 3:
        try:
            trim = float(parts[2])
            if on_set_trim:
                ok, comp_l, comp_r = on_set_trim(trim)
                if ok:
                    ack(seq, "SET_TRIM", "%.3f" % trim,
                        "L=%.3f" % comp_l, "R=%.3f" % comp_r)
                else:
                    nak(seq, "SET_TRIM", "RANGE")
            else:
                nak(seq, "SET_TRIM", "NO_HANDLER")
        except:
            nak(seq, "SET_TRIM", "PARSE")

    elif cmd == "CAL_COMPASS" and len(parts) >= 3:
        try:
            bearing = float(parts[2])
            if on_cal_compass:
                ok, offset = on_cal_compass(bearing)
                if ok:
                    ack(seq, "CAL_COMPASS", "%.1f" % bearing,
                        "HDG_OFF=%.1f" % offset)
                else:
                    nak(seq, "CAL_COMPASS", "RANGE")
            else:
                nak(seq, "CAL_COMPASS", "NO_HANDLER")
        except:
            nak(seq, "CAL_COMPASS", "PARSE")

    elif cmd == "RC_OVERRIDE":
        if on_rc_override:
            on_rc_override()
        ack(seq, "RC_OVERRIDE")

    elif cmd == "RC_RELEASE":
        if on_rc_release:
            on_rc_release()
        ack(seq, "RC_RELEASE")

    elif cmd == "GET_STATUS":
        if on_get_status:
            on_get_status(seq)
        else:
            nak(seq, "GET_STATUS", "NO_HANDLER")

    else:
        nak(seq, cmd, "UNKNOWN")


def process_byte(b):
    """Feed one byte from USB serial into the frame parser.

    Handles the $payload*checksum\\n framing.
    """
    global _rx_pos
    if b == 0x0A:  # newline — end of frame
        if _rx_pos > 4:
            try:
                line = _rx_buf[:_rx_pos].decode('utf-8', 'ignore').strip()
                if line and line[0] == '$' and '*' in line:
                    body = line[1:]  # strip '$'
                    payload, cs_str = body.rsplit('*', 1)
                    if _checksum(payload) == int(cs_str):
                        _dispatch(payload)
            except:
                pass
        _rx_pos = 0
    elif b == 0x24:  # '$' — start of frame
        _rx_pos = 0
        _rx_buf[0] = b
        _rx_pos = 1
    elif _rx_pos < 256:
        _rx_buf[_rx_pos] = b
        _rx_pos += 1


def read_usb():
    """Read available bytes from USB serial (stdin) and process them.

    Call this frequently from the main loop.
    """
    try:
        data = sys.stdin.buffer.read(64)
        if data:
            for b in data:
                process_byte(b)
    except:
        pass
