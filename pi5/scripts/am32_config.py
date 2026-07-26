#!/usr/bin/env python3
"""Configure an AM32 ESC from the Raspberry Pi — no browser, no USB adapter.

Talks the AM32 one-wire bootloader protocol directly over the Pi's GPIO UART, so
you can read/change settings (bi-directional, telemetry, LVC, direction, timing,
protections, …) on the bench without am32.ca (Chromium's Web Serial won't list the
Pi's GPIO UART) and without a USB-TTL linker. Protocol transcribed from the AM32
bootloader source (am32-firmware/AM32-bootloader, bootloader/main.c): 19200 8N1,
CRC-16 poly 0xA001.

This module is used two ways:
  * as a CLI (``python -m pi5.scripts.am32_config read | set …``), and
  * as a library by the dashboard server (``pi5/server/app.py`` → the ESC editor
    modal in ``command_center.html``). The field registry below (`FIELDS`) is the
    single source of truth for both — the UI renders straight from `decode_eeprom`.

WIRING (the ESC config line is one-wire / half-duplex; the Pi UART is two):
    ESC signal ─────────────┬──────── Pi pin 10  (GPIO15 / RXD0)     direct
                            └─[~1kΩ]── Pi pin 8   (GPIO14 / TXD0)     via resistor
    ESC GND  ─────────────────────────  Pi pin 6   (GND)
  3.3 V both sides — no level shifter. Use the ESC's *signal* pad (normally on
  Pico GP2/GP3); move the ESC you want to configure here, then back after. Props off.

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
    python -m pi5.scripts.am32_config set KEY=VALUE …      # any editable field (see `read`)

Only the flags/keys you pass are changed (read-modify-write; everything else preserved).
"""
from __future__ import annotations

import argparse

try:
    import serial
except ImportError:  # pragma: no cover
    serial = None

DEFAULT_PORT = "/dev/ttyAMA0"
BAUD = 19200
SETTINGS_LEN = 176        # safe superset of AM32 settings; write-back preserves the page

# deviceInfo FLASH_SIZE_CODE -> SET_ADDRESS 16-bit value for the EEPROM region
FLASH_MAP = {0x1F: ("32K", 0x7C00), 0x35: ("64K", 0xF800), 0x2B: ("128K", 0x7E00)}

# ---- Pi wiring + one-time setup, surfaced verbatim in the dashboard ----------
WIRING = [
    ("ESC signal", "Pi pin 10  ·  GPIO15 / RXD0", "direct"),
    ("ESC signal", "Pi pin 8   ·  GPIO14 / TXD0", "via ~1 kΩ series resistor"),
    ("ESC ground", "Pi pin 6   ·  GND", "common ground"),
]
WIRING_NOTE = ("3.3 V both sides — no level shifter. Use the ESC's SIGNAL pad "
               "(normally on Pico GP2 left / GP3 right). Move the ESC you want to "
               "configure onto these Pi pins, then back to the Pico afterward. "
               "Props OFF, boat out of the water.")
SETUP_CMDS = [
    "sudo dtoverlay uart0",
    "sudo systemctl stop serial-getty@ttyAMA10.service",
    "sudo chown root:dialout /dev/ttyAMA0 && sudo chmod 660 /dev/ttyAMA0",
]


class Am32Error(Exception):
    """Any read/write/handshake failure — carries a human message for the API."""


# --------------------------------------------------------------------------- #
# Field registry — the single source of truth (classic AM32 EEPROM layout,
# https://wiki.am32.ca/development/Open-ESC-EEPROM-Format.html). The four writable
# offsets used here that matter most (17 dir, 18 bidir, 31 telem, 36/37 LVC) were
# read/write-verified on a real NeutronRC 70A-G071; the rest are the documented
# canonical offsets. Writes are read-modify-write, so untouched bytes are preserved.
# --------------------------------------------------------------------------- #
class _Field:
    def __init__(self, key, off, kind, label, group, *, base=0.0, scale=1.0,
                 unit="", vmin=None, vmax=None, ui_step=None, editable=True,
                 important=False, warn_when=None, help=""):
        self.key, self.off, self.kind, self.label, self.group = key, off, kind, label, group
        self.base, self.scale, self.unit = base, scale, unit
        self.vmin, self.vmax = vmin, vmax
        self.ui_step = ui_step if ui_step is not None else scale
        self.editable, self.important = editable, important
        self.warn_when, self.help = warn_when, help  # warn_when: bool value flagged as risky


FIELDS = [
    # --- INFO (read-only identity / motor descriptors) ---
    _Field("name",     (5, 17), "text", "ESC Name",     "info", editable=False),
    _Field("firmware", (3, 5),  "fw",   "Firmware",     "info", editable=False),
    _Field("boot",     0,       "boot", "Config Status", "info", editable=False),
    _Field("motor_kv", 26, "num", "Motor KV", "info", scale=40, unit="KV", editable=False),
    _Field("poles",    27, "num", "Motor Poles", "info", editable=False),

    # --- DRIVE (boat-critical — the navigator commands reverse to pivot/avoid) ---
    _Field("bidir", 18, "bool", "Bi-Directional", "drive", important=True, warn_when=False,
           help="ON = center-neutral instant reverse (1.5 ms neutral). REQUIRED: the "
                "navigator commands negative throttle to pivot and to bear away. OFF ⇒ "
                "reverse pulses just idle and the boat can't turn in place or back off."),
    _Field("rc_car_rev", 38, "bool", "RC Car Reversing", "drive", warn_when=True,
           help="Keep OFF for the boat. It adds brake-on-first-reverse + double-tap to "
                "change direction (for RC cars); the boat needs immediate proportional "
                "reverse, which plain Bi-Directional already gives."),
    _Field("dir_reversed", 17, "bool", "Direction Reversed", "drive",
           help="Flip if a forward command spins THIS hull backward, so forward "
                "command → forward thrust on both hulls."),
    _Field("telemetry", 31, "bool", "30 ms Telemetry", "drive", important=True,
           help="ON streams KISS temp+current to the dashboard. Needs the ESC's TX pad "
                "wired to Pico GP16 (L) / GP19 (R). See docs/esc_telemetry.md."),

    # --- PROTECT (battery + fault behaviour) ---
    _Field("lvc_enable", 36, "bool", "Low-Voltage Cutoff", "protect",
           help="Per-ESC pack cutoff backstop (the firmware also watches pack V on GP26)."),
    _Field("lvc_cell_v", 37, "num", "LVC Threshold", "protect",
           base=2.5, scale=0.01, unit="V/cell", vmin=2.5, vmax=3.6, ui_step=0.05,
           help="~3.0 V/cell for the 5S (2× M18 parallel) drive rail. Match the pack cutoff."),
    _Field("stuck_prot", 22, "bool", "Stuck-Rotor Protect", "protect",
           help="Relax / OFF for a survey boat — a prop loading up in weeds shouldn't "
                "trip a restart mid-mission."),
    _Field("stall_prot", 29, "bool", "Stall Protection", "protect"),
    _Field("brake_stop", 28, "bool", "Brake on Stop", "protect",
           help="OFF lets the prop freewheel at neutral (differential steering); braking "
                "wastes energy and fights the turn."),

    # --- TUNE (drivetrain feel) ---
    _Field("sinusoidal", 19, "bool", "Sinusoidal Startup", "tune",
           help="ON = smoother, quieter low-speed starts under a big boat prop."),
    _Field("timing", 23, "num", "Timing Advance", "tune",
           scale=7.5, unit="°", vmin=0, vmax=30, ui_step=7.5,
           help="Raise if low-speed startup is rough (larger low-Kv props often want more)."),
    _Field("startup_pow", 25, "num", "Startup Power", "tune",
           unit="%", vmin=50, vmax=150, ui_step=5),
    _Field("pwm_khz", 24, "num", "PWM Frequency", "tune",
           unit="kHz", vmin=8, vmax=48, ui_step=1),
    _Field("comp_pwm", 20, "bool", "Complementary PWM", "tune"),
    _Field("var_pwm", 21, "bool", "Variable PWM Freq", "tune"),
    _Field("beep_vol", 30, "num", "Beacon Volume", "tune", vmin=0, vmax=11, ui_step=1),
]
_BY_KEY = {f.key: f for f in FIELDS}
GROUPS = [("drive", "Drive"), ("protect", "Protection"), ("tune", "Tuning"), ("info", "ESC Info")]


def _to_bool(v) -> bool:
    if isinstance(v, str):
        return v.strip().lower() in ("1", "on", "true", "yes", "y")
    return bool(v)


def _decimals(step: float) -> int:
    if step >= 1 and float(step).is_integer():
        return 0
    return 1 if step >= 0.1 else 2


def _decode_field(f: _Field, e) -> dict:
    d = {"key": f.key, "label": f.label, "group": f.group, "kind": f.kind,
         "editable": f.editable, "important": f.important, "help": f.help}
    if f.kind == "text":
        raw = bytes(e[f.off[0]:f.off[1]]).split(b"\x00")[0]
        try:
            val = raw.decode("ascii", "ignore").strip() or "(unnamed)"
        except Exception:  # noqa: BLE001
            val = "(unnamed)"
        d.update(value=val, display=val, raw=list(raw))
        return d
    if f.kind == "fw":
        val = "%d.%d" % (e[f.off[0]], e[f.off[0] + 1])
        d.update(value=val, display="v" + val, raw=[e[f.off[0]], e[f.off[0] + 1]])
        return d
    if f.kind == "boot":
        ok = e[f.off] == 1
        d.update(value=ok, display="Configured" if ok else "UNCONFIGURED",
                 raw=e[f.off], kind="boot")
        return d
    if f.kind == "bool":
        val = bool(e[f.off])
        d.update(value=val, display="ON" if val else "OFF", raw=e[f.off])
        if f.warn_when is not None:
            d["warn_when"] = f.warn_when          # lets the UI recompute warn on toggle
            if val is f.warn_when:
                d["warn"] = True
        return d
    # numeric
    raw = e[f.off]
    val = round(f.base + raw * f.scale, 3)
    dec = _decimals(f.ui_step)
    d.update(value=val, raw=raw, unit=f.unit, min=f.vmin, max=f.vmax, step=f.ui_step,
             display=("%.*f%s" % (dec, val, (" " + f.unit) if f.unit else "")))
    return d


def decode_eeprom(e) -> list[dict]:
    """Turn a raw EEPROM page into the ordered list of field descriptors the API/UI use."""
    return [_decode_field(f, e) for f in FIELDS]


def _encode_one(buf: bytearray, key: str, value) -> bool:
    """Apply one change to `buf` in place. Return True if a byte actually changed.
    Raise Am32Error on unknown/non-editable key or out-of-range value."""
    f = _BY_KEY.get(key)
    if f is None:
        raise Am32Error("unknown setting %r" % key)
    if not f.editable:
        raise Am32Error("%s is read-only" % f.label)
    if f.kind == "bool":
        raw = 1 if _to_bool(value) else 0
    else:  # numeric
        try:
            v = float(value)
        except (TypeError, ValueError):
            raise Am32Error("%s must be a number" % f.label)
        if f.vmin is not None and v < f.vmin - 1e-9:
            raise Am32Error("%s must be ≥ %g%s" % (f.label, f.vmin, f.unit and " " + f.unit))
        if f.vmax is not None and v > f.vmax + 1e-9:
            raise Am32Error("%s must be ≤ %g%s" % (f.label, f.vmax, f.unit and " " + f.unit))
        raw = max(0, min(255, round((v - f.base) / f.scale)))
    if buf[f.off] == raw:
        return False
    buf[f.off] = raw
    return True


def apply_changes(buf: bytearray, changes: dict) -> list[str]:
    """Apply a {key: value} dict to an EEPROM buffer in place. Returns the keys that
    actually changed. Validates every key/value first (all-or-nothing on validation)."""
    trial = bytearray(buf)
    changed = [k for k, v in changes.items() if _encode_one(trial, k, v)]
    buf[:] = trial
    return changed


def default_mock_eeprom() -> bytearray:
    """A realistic 'configured NeutronRC' EEPROM page for simulator / demo mode."""
    e = bytearray(SETTINGS_LEN)
    e[0] = 1                      # boot: configured
    e[3], e[4] = 2, 15           # firmware v2.15
    e[5:5 + 12] = b"NeutronRC G0".ljust(12, b"\x00")
    e[17] = 0    # dir reversed off
    e[18] = 1    # bidirectional ON
    e[19] = 1    # sinusoidal startup ON
    e[20] = 1    # complementary PWM ON
    e[21] = 0    # variable PWM off
    e[22] = 1    # stuck-rotor protect ON
    e[23] = 2    # timing 15°
    e[24] = 24   # 24 kHz
    e[25] = 100  # startup power 100%
    e[26] = 55   # 2200 KV
    e[27] = 14   # 14 poles
    e[28] = 0    # brake on stop off
    e[29] = 1    # stall protect ON
    e[30] = 5    # beacon volume
    e[31] = 1    # 30 ms telemetry ON
    e[36] = 1    # LVC enabled
    e[37] = 50   # 3.0 V/cell
    e[38] = 0    # RC car reversing off
    return e


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
        raise Am32Error("pyserial not installed (pip install pyserial)")
    try:
        return serial.Serial(port, BAUD, timeout=0.6)
    except Exception as e:  # noqa: BLE001
        raise Am32Error("could not open %s: %s — is uart0 enabled and the ESC in its "
                        "bootloader? (power-cycle the ESC just before reading)" % (port, e))


def _handshake(ser):
    """Return (eeprom_addr16, flash_label) or raise Am32Error with a clear message."""
    gi = _greeting(ser)
    if not (len(gi) >= 5 and gi[:3] == b"471"):
        raise Am32Error("no AM32 bootloader greeting (%s) — check the ESC is powered and "
                        "in its bootloader (power-cycle it), signal on pin 10, TX via ~1k "
                        "on pin 8, common GND." % (gi.hex() or "-"))
    label, addr = FLASH_MAP.get(gi[4], (None, None))
    if addr is None:
        raise Am32Error("unknown flash-size code 0x%02x — add it to FLASH_MAP" % gi[4])
    return addr, label


# --------------------------------------------------------------------------- #
# High-level library API (used by the dashboard server)
# --------------------------------------------------------------------------- #
def read_settings(port: str = DEFAULT_PORT) -> dict:
    """Read the ESC and return {flash, boot_configured, fields, raw_hex}. Raises Am32Error."""
    ser = _connect(port)
    try:
        addr, label = _handshake(ser)
        e = _read_flash(ser, addr, SETTINGS_LEN)
    finally:
        try:
            ser.close()
        except Exception:  # noqa: BLE001
            pass
    if e is None:
        raise Am32Error("read failed (bad CRC or no response) — try again after power-cycling the ESC")
    return {"flash": label, "boot_configured": e[0] == 1,
            "fields": decode_eeprom(e), "raw_hex": bytes(e).hex()}


def write_settings(port: str, changes: dict) -> dict:
    """Read-modify-write only the given {key: value} settings; read back and verify.
    Returns {flash, changed, fields}. Raises Am32Error on any failure."""
    if not changes:
        raise Am32Error("no changes given")
    ser = _connect(port)
    try:
        addr, label = _handshake(ser)
        before = _read_flash(ser, addr, SETTINGS_LEN)
        if before is None:
            raise Am32Error("read failed — not writing")
        if before[0] != 0x01:
            raise Am32Error("boot byte != 0x01 — refusing to write (safety)")
        new = bytearray(before)
        changed = apply_changes(new, changes)     # validates + mutates
        if not changed:
            return {"flash": label, "changed": [], "fields": decode_eeprom(before)}
        err = _write_flash(ser, addr, new)
        if err:
            raise Am32Error("WRITE FAILED: %s" % err)
        after = _read_flash(ser, addr, SETTINGS_LEN)
        if after is None:
            raise Am32Error("verify read failed")
    finally:
        try:
            ser.close()
        except Exception:  # noqa: BLE001
            pass
    # confirm each requested offset landed
    verified = [k for k in changed if after[_BY_KEY[k].off] == new[_BY_KEY[k].off]]
    if set(verified) != set(changed):
        raise Am32Error("verify mismatch (changed=%s verified=%s)" % (changed, verified))
    return {"flash": label, "changed": changed, "fields": decode_eeprom(after)}


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _show(e) -> None:
    for d in decode_eeprom(e):
        flag = "  ⚠" if d.get("warn") else ""
        print("  %-16s: %s%s" % (d["label"], d["display"], flag))


def cmd_read(args) -> int:
    try:
        r = read_settings(args.port)
    except Am32Error as e:
        print(e)
        return 2
    print("AM32 ESC (%s flash) current settings:" % r["flash"])
    for d in r["fields"]:
        flag = "  ⚠" if d.get("warn") else ""
        print("  %-16s: %s%s" % (d["label"], d["display"], flag))
    return 0


def _parse_set_args(args) -> dict:
    """Collect the legacy --flags and any KEY=VALUE positionals into a changes dict."""
    changes: dict = {}
    if args.bidir:
        changes["bidir"] = args.bidir
    if args.telemetry:
        changes["telemetry"] = args.telemetry
    if args.dir_reversed:
        changes["dir_reversed"] = args.dir_reversed
    if args.lvc is not None:
        if args.lvc == "off":
            changes["lvc_enable"] = "off"
        else:
            changes["lvc_enable"] = "on"
            changes["lvc_cell_v"] = args.lvc
    for kv in args.kv or []:
        if "=" not in kv:
            raise Am32Error("expected KEY=VALUE, got %r" % kv)
        k, v = kv.split("=", 1)
        changes[k.strip()] = v.strip()
    return changes


def cmd_set(args) -> int:
    try:
        changes = _parse_set_args(args)
        if not changes:
            print("no settings given (use --bidir/--telemetry/--lvc/… or KEY=VALUE)")
            return 2
        r = write_settings(args.port, changes)
    except Am32Error as e:
        print(e)
        return 2
    if not r["changed"]:
        print("no changes needed / already set")
        return 0
    print("after (changed: %s — verified):" % ", ".join(r["changed"]))
    for d in r["fields"]:
        if d["key"] in r["changed"]:
            print("  %-16s: %s" % (d["label"], d["display"]))
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Configure an AM32 ESC over the Pi GPIO UART.")
    p.add_argument("--port", default=DEFAULT_PORT, help="serial port (default %s)" % DEFAULT_PORT)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("read", help="read and print the ESC settings").set_defaults(func=cmd_read)
    s = sub.add_parser("set", help="change settings (read-modify-write, only what you pass)")
    s.add_argument("--bidir", choices=["on", "off"])
    s.add_argument("--telemetry", choices=["on", "off"])
    s.add_argument("--dir-reversed", dest="dir_reversed", choices=["on", "off"])
    s.add_argument("--lvc", help="'off' or a per-cell cutoff voltage, e.g. 3.0")
    s.add_argument("kv", nargs="*", metavar="KEY=VALUE",
                   help="any editable field, e.g. sinusoidal=on timing=15 pwm_khz=24")
    s.set_defaults(func=cmd_set)
    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
