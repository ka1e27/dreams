#!/usr/bin/env python3
"""Configure an AM32 ESC from the Raspberry Pi — no browser, no USB adapter.

Talks the AM32 one-wire bootloader protocol directly over the Pi's GPIO UART, so
you can read/change settings (bi-directional, telemetry, LVC, direction) on the
bench without am32.ca (Chromium's Web Serial won't list the Pi's GPIO UART) and
without a USB-TTL linker. Protocol transcribed from the AM32 bootloader source
(am32-firmware/AM32-bootloader, bootloader/main.c): 19200 8N1, CRC-16 poly 0xA001.

WIRING (the ESC config line is one-wire / half-duplex; the Pi UART is two):
    ESC signal ─────────────┬──────── Pi pin 10  (GPIO15 / RXD0)     direct
                            └─[~1kΩ]── Pi pin 8   (GPIO14 / TXD0)     via resistor
    ESC GND  ─────────────────────────  Pi pin 6   (GND)
  3.3 V both sides — no level shifter. Use the ESC's *signal* pad (normally on
  Pico GP2); move it here for config, then back to GP2 after. Props off.

ONE-TIME Pi 5 SETUP (pins 8/10 aren't a UART by default; this enables /dev/ttyAMA0):
    sudo dtoverlay uart0                                  # enable uart0 on GPIO14/15
    sudo systemctl stop serial-getty@ttyAMA10.service    # free it from the login console
    sudo chown root:dialout /dev/ttyAMA0 && sudo chmod 660 /dev/ttyAMA0
  (Runtime-only; to persist across reboots add `dtoverlay=uart0` to
   /boot/firmware/config.txt and disable the serial console in raspi-config.)

USAGE:
    python -m pi5.scripts.am32_config read
    python -m pi5.scripts.am32_config set --bidir on --telemetry on
    python -m pi5.scripts.am32_config set --lvc 3.0        # 3.0 V/cell cutoff
    python -m pi5.scripts.am32_config set --lvc off --dir-reversed off

Only the flags you pass are changed (read-modify-write; everything else preserved).
"""
from __future__ import annotations

import argparse
import sys

try:
    import serial
except ImportError:  # pragma: no cover
    serial = None

DEFAULT_PORT = "/dev/ttyAMA0"
BAUD = 19200
SETTINGS_LEN = 176        # safe superset of AM32 settings; write-back preserves the page

# EEPROM byte offsets (wiki: Open-ESC-EEPROM-Format)
OFF = {"dir_reversed": 17, "bidir": 18, "telemetry": 31, "lvc_en": 36, "lvc_thresh": 37}
# deviceInfo FLASH_SIZE_CODE -> SET_ADDRESS 16-bit value for the EEPROM region
FLASH_MAP = {0x1F: ("32K", 0x7C00), 0x35: ("64K", 0xF800), 0x2B: ("128K", 0x7E00)}


def crc16(data) -> int:
    ret = 0
    for b in data:
        xb = b
        for _ in range(8):
            if (xb & 1) ^ (ret & 1):
                ret = (ret >> 1) ^ 0xA001
            else:
                ret >>= 1
            xb >>= 1
    return ret & 0xFFFF


def _framed(p) -> bytes:
    c = crc16(p)
    return bytes(p) + bytes([c & 0xFF, (c >> 8) & 0xFF])


def _txrx(ser, payload, resp_len) -> bytes:
    """Send a framed command; strip the one-wire TX echo; return the response."""
    ser.reset_input_buffer()
    ser.write(payload)
    ser.flush()
    return ser.read(len(payload) + resp_len)[len(payload):]


def _greeting(ser) -> bytes:
    msg = bytes([0] * 8 + [0x0D, 0x42, 0x4C, 0x48, 0x65, 0x6C, 0x69, 0xF4, 0x7D])
    ser.reset_input_buffer()
    ser.write(msg)
    ser.flush()
    return ser.read(len(msg) + 9)[len(msg):]


def _set_address(ser, addr16) -> bool:
    r = _txrx(ser, _framed([0xFF, 0x00, (addr16 >> 8) & 0xFF, addr16 & 0xFF]), 1)
    return len(r) >= 1 and r[0] == 0x30


def _read_flash(ser, addr16, n) -> bytearray | None:
    if not _set_address(ser, addr16):
        return None
    r = _txrx(ser, _framed([0x03, n & 0xFF]), n + 3)
    if len(r) < n + 3 or crc16(r[:n]) != (r[n] | (r[n + 1] << 8)):
        return None
    return bytearray(r[:n])


def _write_flash(ser, addr16, data) -> str | None:
    if not _set_address(ser, addr16):
        return "SET_ADDRESS failed"
    sb = _framed([0xFE, 0x00, 0x00, len(data) & 0xFF])     # SET_BUFFER — no ACK
    ser.reset_input_buffer()
    ser.write(sb)
    ser.flush()
    ser.read(len(sb))                                       # consume echo
    payload = bytes(data) + bytes([crc16(data) & 0xFF, (crc16(data) >> 8) & 0xFF])
    ser.reset_input_buffer()
    ser.write(payload)
    ser.flush()
    resp = ser.read(len(payload) + 1)[len(payload):]
    if not (resp and resp[0] == 0x30):
        return "payload not ACKed (%s)" % (resp.hex() or "-")
    r = _txrx(ser, _framed([0x01, 0x00]), 1)               # PROG_FLASH
    if not (r and r[0] == 0x30):
        return "PROG_FLASH not ACKed (%s)" % (r.hex() or "-")
    return None


def _connect(port):
    if serial is None:
        sys.exit("pyserial not installed (pip install pyserial)")
    try:
        return serial.Serial(port, BAUD, timeout=0.6)
    except Exception as e:  # noqa: BLE001
        sys.exit("could not open %s: %s\nIs the ESC in its bootloader and the UART set up? "
                 "See the one-time setup in this file's header." % (port, e))


def _handshake(ser):
    """Return (eeprom_addr16, flash_label) or exit with a clear message."""
    gi = _greeting(ser)
    if not (len(gi) >= 5 and gi[:3] == b"471"):
        sys.exit("no AM32 bootloader greeting (%s).\n  * ESC powered and in its bootloader?\n"
                 "  * signal wire on pin 10, TX via ~1k on pin 8, common GND?" % (gi.hex() or "-"))
    label, addr = FLASH_MAP.get(gi[4], (None, None))
    if addr is None:
        sys.exit("unknown flash-size code 0x%02x — add it to FLASH_MAP" % gi[4])
    return addr, label


def _show(e):
    lvc = "off" if not e[OFF["lvc_en"]] else "%.2f V/cell" % (2.5 + e[OFF["lvc_thresh"]] * 0.01)
    print("  name          : %r" % bytes(e[5:17]).split(b"\x00")[0])
    print("  boot byte     : 0x%02x %s" % (e[0], "(configured)" if e[0] == 1 else "(unconfigured)"))
    print("  direction rev : %s" % ("on" if e[OFF["dir_reversed"]] else "off"))
    print("  bi-directional: %s" % ("ON" if e[OFF["bidir"]] else "off"))
    print("  telemetry 30ms: %s" % ("ON" if e[OFF["telemetry"]] else "off"))
    print("  LVC           : %s" % lvc)


def cmd_read(args) -> int:
    ser = _connect(args.port)
    addr, label = _handshake(ser)
    e = _read_flash(ser, addr, SETTINGS_LEN)
    ser.close()
    if e is None:
        print("read failed")
        return 2
    print("AM32 ESC (%s flash) current settings:" % label)
    _show(e)
    return 0


def cmd_set(args) -> int:
    onoff = {"on": 1, "off": 0}
    ser = _connect(args.port)
    addr, label = _handshake(ser)
    before = _read_flash(ser, addr, SETTINGS_LEN)
    if before is None:
        print("read failed — not writing")
        return 2
    if before[0] != 0x01:
        print("boot byte != 0x01 — refusing to write (safety)")
        return 2
    new = bytearray(before)
    if args.bidir:
        new[OFF["bidir"]] = onoff[args.bidir]
    if args.telemetry:
        new[OFF["telemetry"]] = onoff[args.telemetry]
    if args.dir_reversed:
        new[OFF["dir_reversed"]] = onoff[args.dir_reversed]
    if args.lvc is not None:
        if args.lvc == "off":
            new[OFF["lvc_en"]] = 0
        else:
            v = float(args.lvc)
            new[OFF["lvc_en"]] = 1
            new[OFF["lvc_thresh"]] = max(0, min(255, round((v - 2.5) * 100)))
    if new == before:
        print("no changes requested / already set")
        return 0
    print("current:")
    _show(before)
    print("writing...")
    err = _write_flash(ser, addr, new)
    if err:
        print("WRITE FAILED: %s" % err)
        return 2
    after = _read_flash(ser, addr, SETTINGS_LEN)
    ser.close()
    if after is None:
        print("verify read failed")
        return 2
    print("after:")
    _show(after)
    # bootloader rewrites byte 2 (its version); ignore it in the compare
    changed = [k for k, o in OFF.items() if after[o] != before[o]]
    print("\nchanged: %s  (verified)" % (", ".join(changed) or "none"))
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Configure an AM32 ESC over the Pi GPIO UART.")
    p.add_argument("--port", default=DEFAULT_PORT, help="serial port (default %s)" % DEFAULT_PORT)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("read", help="read and print the ESC settings").set_defaults(func=cmd_read)
    s = sub.add_parser("set", help="change settings (read-modify-write, only the flags given)")
    s.add_argument("--bidir", choices=["on", "off"])
    s.add_argument("--telemetry", choices=["on", "off"])
    s.add_argument("--dir-reversed", dest="dir_reversed", choices=["on", "off"])
    s.add_argument("--lvc", help="'off' or a per-cell cutoff voltage, e.g. 3.0")
    s.set_defaults(func=cmd_set)
    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
