"""AM32 ESC passthrough — Pi-side driver for the Boat Pico bridge.

⚠ UNTESTED / EXPERIMENTAL — see docs/esc_passthrough.md. Needs a Pico running the
matching `firmware/boat-pico/esc_passthrough.py`, and a real ESC to validate
against. Props off, boat out of the water.

The Pico can hand its USB-CDC to an ESC's one-wire signal line (AM32 config). This
tool drives that from the Pi:

  * ``enter``  — put the Pico into bridge mode for the am32.ca workflow, then get
                 out of the way. Once armed, the Pico's own /dev/ttyACM0 *is* the
                 transparent link to the ESC, so you point am32.ca (Chromium on the
                 Pi) straight at /dev/ttyACM0. No PTY, no separate linker.
  * ``probe``  — scripted: arm the bridge, send raw bytes, print the raw reply.
                 Lets us validate the one-wire link (and find the baud) without a
                 browser — the first on-Pi bring-up step.
  * ``scan``   — run ``probe`` across a list of candidate bauds and report which
                 ones get a reply (the AM32 signal-line baud isn't publicly pinned).

Stop the boat stack first (it holds /dev/ttyACM0): ``sudo systemctl stop boat`` or
kill run_hardware.py, so this tool can open the port.

Examples
--------
    python -m pi5.scripts.esc_passthrough enter  --esc left  --baud 19200
    python -m pi5.scripts.esc_passthrough probe  --esc left  --baud 19200 --hex 2f4d
    python -m pi5.scripts.esc_passthrough scan    --esc left  --hex 2f4d
"""
from __future__ import annotations

import argparse
import sys
import time

try:
    import serial  # pyserial (already a project dep via pyserial-asyncio)
except ImportError:  # pragma: no cover - runtime dep on the Pi
    serial = None

ESC_IDS = {"left": 0, "l": 0, "0": 0, "right": 1, "r": 1, "1": 1}
# Candidate signal-line bauds to try in `scan` (AM32/BLHeli one-wire configs live
# in this range; the exact value isn't publicly documented, so we sweep).
SCAN_BAUDS = [19200, 38400, 57600, 115200, 9600, 4800, 128000, 256000]
ESCAPE = b"\x00\x00\x00\x00"          # ends the Pico bridge (matches the firmware)


def _checksum(payload: str) -> int:
    cs = 0
    for ch in payload:
        cs ^= ord(ch)
    return cs


def _frame(payload: str) -> bytes:
    return ("$%s*%d\n" % (payload, _checksum(payload))).encode()


def _read_line(ser, timeout: float = 2.0) -> str:
    """Read one framed line ($...\\n) from the Pico, or '' on timeout."""
    ser.timeout = timeout
    return ser.readline().decode("ascii", "ignore").strip()


def _arm_bridge(ser, esc_id: int, baud: int, seq: int = 1) -> bool:
    """ESTOP for safety, then ESC_PASS. Returns True once the Pico ACKs ESC_PASS.

    After the ACK the Pico's CDC is a raw byte pipe to the ESC one-wire — no more
    framed protocol on this port until the bridge exits (which resets the Pico).
    """
    ser.write(_frame("ESTOP,%d" % seq))
    ser.flush()
    time.sleep(0.2)
    # Drain any telemetry/ACK backlog.
    ser.reset_input_buffer()
    ser.write(_frame("ESC_PASS,%d,%d,%d" % (seq + 1, esc_id, baud)))
    ser.flush()
    deadline = time.time() + 2.0
    while time.time() < deadline:
        line = _read_line(ser, timeout=0.5)
        if line.startswith("$ACK") and "ESC_PASS" in line:
            return True
        if "NAK" in line and "ESC_PASS" in line:
            print("Pico NAK'd ESC_PASS: %s" % line, file=sys.stderr)
            return False
    return False


def _end_bridge(ser) -> None:
    """Send the escape sequence so the Pico exits the bridge and resets."""
    try:
        ser.write(ESCAPE)
        ser.flush()
    except Exception:
        pass


def _open(port: str, timeout: float = 1.0):
    if serial is None:
        sys.exit("pyserial not installed (pip install pyserial) — required on the Pi")
    return serial.Serial(port, baudrate=115200, timeout=timeout)


# --------------------------------------------------------------------------- #
# subcommands
# --------------------------------------------------------------------------- #
def cmd_enter(args) -> int:
    ser = _open(args.port)
    if not _arm_bridge(ser, args.esc, args.baud):
        print("Failed to arm the bridge (is the Pico running the passthrough "
              "firmware? is the boat stack stopped?)", file=sys.stderr)
        return 1
    ser.close()   # hand /dev/ttyACM0 to am32.ca
    print(
        "\nBridge armed: ESC %d @ %d baud on %s.\n"
        "  → Open am32.ca in Chromium ON THE PI, Port Select %s, Connect, Read.\n"
        "  → Enable Bi-Directional, set the 5S LVC, Save (see docs/esc_setup.md).\n"
        "  → When done, disconnect am32.ca. The Pico resets itself after ~20 s idle\n"
        "    (or power-cycle it) to return to normal boat firmware.\n"
        % (args.esc, args.baud, args.port, args.port))
    return 0


def cmd_probe(args) -> int:
    payload = bytes.fromhex(args.hex) if args.hex else b""
    ser = _open(args.port)
    if not _arm_bridge(ser, args.esc, args.baud):
        print("Failed to arm the bridge.", file=sys.stderr)
        return 1
    try:
        if payload:
            ser.reset_input_buffer()
            ser.write(payload)
            ser.flush()
        time.sleep(args.wait)
        reply = ser.read(256)
        print("baud=%d  sent=%s  <-  recv(%d)=%s"
              % (args.baud, payload.hex() or "(none)", len(reply), reply.hex()))
    finally:
        _end_bridge(ser)
        ser.close()
    return 0 if payload == b"" else (0 if reply else 2)


def cmd_scan(args) -> int:
    payload = bytes.fromhex(args.hex) if args.hex else b"\x2f"  # arbitrary poke
    hits = []
    for baud in SCAN_BAUDS:
        ser = _open(args.port)
        armed = _arm_bridge(ser, args.esc, baud)
        reply = b""
        if armed:
            ser.reset_input_buffer()
            ser.write(payload)
            ser.flush()
            time.sleep(args.wait)
            reply = ser.read(256)
            _end_bridge(ser)
        ser.close()
        status = "reply %s" % reply.hex() if reply else ("no reply" if armed else "arm FAILED")
        print("  baud %-7d : %s" % (baud, status))
        if reply:
            hits.append((baud, reply))
        # The Pico resets when the bridge ends; wait for it to re-enumerate.
        time.sleep(args.reset_wait)
    if hits:
        print("\nResponsive baud(s): %s" % ", ".join(str(b) for b, _ in hits))
        return 0
    print("\nNo baud produced a reply — check wiring (a series ~1k on the ESC "
          "signal helps), ESC power, and the PIO UART (loopback test first).")
    return 2


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="AM32 ESC passthrough via the Boat Pico")
    p.add_argument("--port", default="/dev/ttyACM0", help="Pico serial port")
    sub = p.add_subparsers(dest="cmd", required=True)

    def add_common(sp):
        sp.add_argument("--esc", type=lambda v: ESC_IDS[str(v).lower()],
                        default=0, help="which ESC: left/right (or 0/1)")

    e = sub.add_parser("enter", help="arm the bridge for the am32.ca workflow")
    add_common(e)
    e.add_argument("--baud", type=int, default=19200)
    e.set_defaults(func=cmd_enter)

    pr = sub.add_parser("probe", help="arm + send raw hex + show the reply")
    add_common(pr)
    pr.add_argument("--baud", type=int, default=19200)
    pr.add_argument("--hex", default="", help="hex bytes to send, e.g. 2f4d")
    pr.add_argument("--wait", type=float, default=0.3, help="seconds to wait for a reply")
    pr.set_defaults(func=cmd_probe)

    sc = sub.add_parser("scan", help="sweep candidate bauds and report replies")
    add_common(sc)
    sc.add_argument("--hex", default="", help="hex bytes to poke with each baud")
    sc.add_argument("--wait", type=float, default=0.3)
    sc.add_argument("--reset-wait", type=float, default=3.0,
                    help="seconds to wait for the Pico to reset+re-enumerate between bauds")
    sc.set_defaults(func=cmd_scan)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
