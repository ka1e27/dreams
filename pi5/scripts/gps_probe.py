#!/usr/bin/env python3
"""Bench-test the GPS — find out whether the module is alive and whether its
NMEA actually reaches the Boat Pico.

Four modes, cheapest first:

    python -m pi5.scripts.gps_probe boat        # what the running firmware sees
    python -m pi5.scripts.gps_probe pins        # which Pico GPIO (if any) has a live serial line
    python -m pi5.scripts.gps_probe uart        # open UART1 on the Pico and dump/parse NMEA
    python -m pi5.scripts.gps_probe soft        # PIO soft-UART RX — listens on ANY pin
    python -m pi5.scripts.gps_probe host        # sniff a USB-TTL adapter on the Pi

`boat` is read-only. The Pico modes need the REPL, so they ask the firmware to
drop out with a ``$REFLASH`` frame (which estops the motors first — see
`deploy_pico._request_repl`) and restart it afterwards unless ``--no-restart``.

`soft` bit-bangs 8N1 in PIO, reusing the same program as `esc_telem.py` / `sbus.py`
at the GPS baud. Use it on a pin the hardware UART can't receive on — GP8, say,
which is a UART1 *TX* pin and cannot be an RX.

J7 *IS* THE GPS UART — THE FIRMWARE IS ON THE WRONG PINS (2026-07-29)
---------------------------------------------------------------------
`gps.init` opens **UART1 on GP4 (TX) / GP5 (RX)**, but J7 lands on **GP8/GP9**,
which is the RP2040's *other* UART1 pin pair (TX GP4/GP8/GP20/GP24, RX
GP5/GP9/GP21/GP25). `docs/pin_map.md` lists GP8/GP9 as I2C0 only; they are
dual-function, and J7's pins 3/4 are the GPS serial link:

    J7 "GPS + Compass" (6-pin JST-XH)   1 = GP14 (SDA-B)   4 = GP8  -- UART1 TX
                                        2 = GP15 (SCL-B)   5 = VSYS -- 5 V!
                                        3 = GP9  -- UART1 RX   6 = GND

So the board-side fix is `UART(1, tx=Pin(8), rx=Pin(9))` in `gps.init` — no
rewiring. GP4/GP5 reach no connector at all (GP4 -> U1.15 MCP2515 SO; GP5 -> the
GND net in the schematic, though it measures floating on the built board).

Measured on the live bench board, for reference:
  * **GP9 (= J7.3, the GPS TX line) is shorted to GND.** A PIO capture returned
    5356 bytes of pure 0x00 — one endless start bit, which is a held-low pin, not
    data. Its own internal pull-up cannot lift it. Nothing can be received until
    that short is cleared; suspect a solder bridge between Pico pads 12 (GP9) and
    13 (GND), which are adjacent, since the schematic has no such tie.
  * GP8 (= J7.4) reads driven high with zero edges — a pull-up, not a transmitter.
  * GP4 and GP5 both read floating, so a jumper into GP5 works if you want to
    bypass J7 (see WIRING).
  * Zero serial edges on all 18 safe GPIOs -> nothing reaching the Pico anywhere.

WIRING to bypass J7 entirely (3 jumpers, for `uart --pin 5`)
-----------------------------------------------------------
    GPS TX   ->  Pico GP5   (pin 7)
    GPS GND  ->  Pico GND   (pin 8)
    GPS VCC  ->  Pico 3V3   (pin 36)  or VSYS/5 V (pin 39) if the module needs 5 V
  Leave the GPS RX pin disconnected — this probe only listens.

A cold-start fix needs a clear view of the sky and can take 30-90 s (longer
indoors — most modules never fix through a roof). `uart`/`host` tell you the
difference between "no data at all" (wiring/power) and "data but no fix yet"
(antenna/sky), which is the whole point of testing it on the bench.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time

try:
    import serial
except ImportError:  # pragma: no cover
    serial = None

from pi5.scripts.deploy_pico import _default_port, _request_repl

_MPREMOTE = [sys.executable, "-m", "mpremote"]

# UART1's pin options are fixed by the RP2040 mux: RX on GP5/GP9/GP21/GP25, TX on
# GP4/GP8/GP20/GP24. Map each RX pin to the TX pin it shares a connector group with,
# so `--pin 9` drives GP8 (J7.4) rather than GP4, which reaches no connector.
UART1_TX_FOR_RX = {5: 4, 9: 8, 21: 20, 25: 24}
UART1_RX_PINS = tuple(UART1_TX_FOR_RX)

# Pins the `pins` scan may reconfigure as inputs. Deliberately excludes GP2/GP3
# (drive ESC PWM), GP21 (winch PWM) and GP10 (NeoPixel) so nothing that drives a
# motor or LED is touched, plus GP0/GP1 which are dead on this board.
SCAN_PINS = (4, 5, 6, 7, 8, 9, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 22)

BAUD_CANDIDATES = (9600, 38400, 57600, 115200, 4800)


# ---------------------------------------------------------------- NMEA reporting

def _nmea_report(raw: bytes, baud: int) -> bool:
    """Print a verdict on a captured byte stream. Returns True if NMEA was seen."""
    print("  %d bytes captured" % len(raw))
    if not raw:
        print("  VERDICT: nothing at all — module unpowered, TX not connected, "
              "or wired to a different pin.")
        return False

    lines = [ln.strip() for ln in raw.split(b"\n")]
    sentences = [ln.decode("ascii", "replace") for ln in lines if ln.startswith(b"$")]
    if not sentences:
        printable = sum(32 <= b < 127 or b in (10, 13) for b in raw)
        print("  sample: %r" % raw[:80])
        print("  VERDICT: bytes arriving but no '$' sentence (%d%% printable) — "
              "almost certainly the wrong baud (tried %d) or an inverted/noisy line."
              % (100 * printable // len(raw), baud))
        return False

    kinds: dict[str, int] = {}
    for s in sentences:
        kinds[s[1:6]] = kinds.get(s[1:6], 0) + 1
    print("  sentences: %s" % ", ".join("%s x%d" % kv for kv in sorted(kinds.items())))

    fix_q = sats = None
    status = None
    lat = lon = None
    for s in sentences:
        f = s.split(",")
        if f[0][3:] == "GGA" and len(f) > 7:
            fix_q = f[6] or fix_q
            sats = f[7] or sats
        elif f[0][3:] == "RMC" and len(f) > 6:
            status = f[2] or status
            if f[2] == "A":
                lat, lon = _dm_to_deg(f[3], f[4]), _dm_to_deg(f[5], f[6])

    print("  fix quality=%s  sats=%s  RMC status=%s"
          % (fix_q or "?", sats or "?", status or "?"))
    if status == "A" and lat is not None:
        print("  VERDICT: GPS WORKING — fix at %.6f, %.6f" % (lat, lon))
    else:
        print("  VERDICT: module is ALIVE and talking, but has NO FIX yet. "
              "Wiring is good; give it sky view and 30-90 s (indoors it may never fix).")
    return True


def _dm_to_deg(raw: str, hemi: str) -> float | None:
    """NMEA DDMM.MMMM -> signed decimal degrees."""
    try:
        v = float(raw)
    except (TypeError, ValueError):
        return None
    deg = int(v / 100)
    out = deg + (v - deg * 100) / 60.0
    return -out if hemi in ("S", "W") else out


# --------------------------------------------------------------------- Pico side

def _pico_exec(code: str, timeout: float = 90.0) -> str:
    """Run a snippet on the Pico via mpremote and return its stdout."""
    try:
        proc = subprocess.run([*_MPREMOTE, "connect", _PORT, "exec", code],
                              capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        sys.exit("mpremote not found — run it from the project venv "
                 "(.venv/bin/python -m pi5.scripts.gps_probe ...)")
    except subprocess.TimeoutExpired:
        sys.exit("mpremote timed out talking to %s" % _PORT)
    if proc.returncode != 0:
        sys.exit("mpremote failed: %s" % (proc.stderr or proc.stdout).strip())
    return proc.stdout


def _restart_firmware() -> None:
    print("\nRestarting the firmware…")
    subprocess.run([*_MPREMOTE, "connect", _PORT, "reset"],
                   capture_output=True, text=True, timeout=30)
    time.sleep(2.0)
    print("  firmware restarted (it was stopped to free the REPL)")


_PINS_SNIPPET = """
import time
from machine import Pin
for n in {pins}:
    p = Pin(n, Pin.IN, Pin.PULL_UP); time.sleep_ms(3); pu = p.value()
    p = Pin(n, Pin.IN, Pin.PULL_DOWN); time.sleep_ms(3); pd = p.value()
    last = p.value(); edges = 0; highs = 0; total = 0
    t_end = time.ticks_add(time.ticks_ms(), {ms})
    while time.ticks_diff(t_end, time.ticks_ms()) > 0:
        v = p.value(); total += 1; highs += v
        if v != last:
            edges += 1; last = v
    if pu == 0 and pd == 0:
        state = 'SHORTED TO GND'
    elif pu == 1 and pd == 1:
        state = 'driven high'
    else:
        state = 'floating'
    print('GP%-3d %-15s edges=%-7d high=%5.1f%%' % (n, state, edges, 100.0*highs/total))
    Pin(n, Pin.IN, None)
"""

_UART_SNIPPET = """
import time
from machine import UART, Pin
u = UART(1, baudrate={baud}, tx=Pin({tx}), rx=Pin({pin}))
buf = b''
t_end = time.ticks_add(time.ticks_ms(), {ms})
while time.ticks_diff(t_end, time.ticks_ms()) > 0:
    if u.any():
        c = u.read()
        if c:
            buf += c
    time.sleep_ms(5)
print('BYTES', len(buf))
print(repr(buf))
"""

# 8N1 idle-high RX in PIO, clocked at 8x baud — the same program esc_telem.py uses
# for the AM32 taps, and the same LSB-first unpack of each 32-bit push.
_SOFT_SNIPPET = """
import time
from machine import Pin
from rp2 import asm_pio, PIO, StateMachine

@asm_pio(autopush=True, push_thresh=32, fifo_join=PIO.JOIN_RX,
         in_shiftdir=PIO.SHIFT_RIGHT)
def rx():
    wrap_target()
    wait(0, pin, 0)
    nop()[11]
    set(x, 7)
    label('bit')
    in_(pins, 1)
    nop()[6]
    jmp(x_dec, 'bit')
    wrap()

sm = StateMachine(4, rx, freq={baud} * 8, in_base=Pin({pin}, Pin.IN, Pin.PULL_UP))
sm.active(1)
buf = bytearray()
t_end = time.ticks_add(time.ticks_ms(), {ms})
while time.ticks_diff(t_end, time.ticks_ms()) > 0:
    while sm.rx_fifo():
        w = sm.get()
        buf += bytes((w & 0xFF, (w >> 8) & 0xFF, (w >> 16) & 0xFF, (w >> 24) & 0xFF))
    time.sleep_ms(5)
sm.active(0)
print('BYTES', len(buf))
print(repr(bytes(buf)))
"""


def mode_pins(args: argparse.Namespace) -> None:
    pins = _wanted_pins(args)
    print("Scanning Pico GPIOs for a live serial line (%.1f s each, ~%.0f s total)."
          % (args.secs, args.secs * len(pins)))
    print("A GPS emitting NMEA shows hundreds/thousands of edges and idles high.\n")
    _request_repl(_PORT)
    out = _pico_exec(_PINS_SNIPPET.format(pins=pins, ms=int(args.secs * 1000)),
                     timeout=args.secs * len(pins) + 60)
    print(out.rstrip())
    live = [ln for ln in out.splitlines() if "edges=" in ln
            and int(ln.split("edges=")[1].split()[0]) > 20]
    print("\n%s" % ("Live serial line found on: %s" % ", ".join(ln.split()[0] for ln in live)
                    if live else "No serial activity on any scanned pin — nothing is "
                                "transmitting to the Pico."))
    if not args.no_restart:
        _restart_firmware()


def _wanted_pins(args: argparse.Namespace) -> list[int]:
    """--pins 8,9 narrows the scan; default is every safe pin."""
    if not args.pins:
        return list(SCAN_PINS)
    want = [int(p) for p in args.pins.replace(" ", "").split(",") if p]
    bad = [p for p in want if p not in SCAN_PINS]
    if bad:
        sto = ", ".join("GP%d" % p for p in bad)
        sys.exit("refusing to reconfigure %s — not in the safe scan list (ESC/winch/"
                 "NeoPixel outputs and the dead GP0/GP1 are excluded on purpose)." % sto)
    return want


def _soft_or_hw(args: argparse.Namespace, snippet: str, label: str) -> bytes:
    """Run a capture snippet on the Pico and return the raw bytes it echoed."""
    _request_repl(_PORT)
    out = _pico_exec(snippet, timeout=args.secs + 60)
    raw = b""
    for line in out.splitlines():
        if line.startswith(("b'", 'b"')):
            raw = eval(line)          # noqa: S307 - repr() of bytes from our own snippet
    print("[%s]" % label)
    return raw


def mode_soft(args: argparse.Namespace) -> None:
    print("PIO soft-UART RX on GP%d, %d baud, %.0f s.\n"
          "(Any pin works here — use this for GP8, which cannot be a hardware UART RX.)\n"
          % (args.pin, args.baud, args.secs))
    raw = _soft_or_hw(args, _SOFT_SNIPPET.format(baud=args.baud, pin=args.pin,
                                                 ms=int(args.secs * 1000)),
                      "PIO rx GP%d @ %d" % (args.pin, args.baud))
    if raw and not raw.strip(b"\x00"):
        print("  %d bytes, ALL ZERO — the line is being held LOW, so PIO saw one endless\n"
              "  start bit. That's a grounded pin, not a transmitter." % len(raw))
    else:
        _nmea_report(raw, args.baud)
    if not args.no_restart:
        _restart_firmware()


def mode_uart(args: argparse.Namespace) -> None:
    if args.pin not in UART1_RX_PINS:
        sys.exit("GP%d cannot be UART1 RX on the RP2040 — pick one of %s, or use "
                 "`soft` mode, which receives on any pin."
                 % (args.pin, "/".join("GP%d" % p for p in UART1_RX_PINS)))
    tx = args.tx if args.tx is not None else UART1_TX_FOR_RX[args.pin]
    print("Listening on Pico UART1: rx=GP%d, tx=GP%d, %d baud, %.0f s.\n"
          % (args.pin, tx, args.baud, args.secs))
    raw = _soft_or_hw(args, _UART_SNIPPET.format(baud=args.baud, pin=args.pin, tx=tx,
                                                 ms=int(args.secs * 1000)),
                      "UART1 rx GP%d @ %d" % (args.pin, args.baud))
    if raw and not raw.strip(b"\x00"):
        print("  %d bytes, ALL ZERO — GP%d is being held LOW, so the UART saw an endless\n"
              "  stream of framing errors. That's a grounded pin, not a transmitter."
              % (len(raw), args.pin))
    else:
        _nmea_report(raw, args.baud)
    if not args.no_restart:
        _restart_firmware()


# --------------------------------------------------------------------- host side

def mode_host(args: argparse.Namespace) -> None:
    if serial is None:
        sys.exit("pyserial not installed")
    bauds = BAUD_CANDIDATES if args.baud == 0 else (args.baud,)
    print("Sniffing %s for NMEA (%s).\n" % (args.port, "auto-baud" if len(bauds) > 1
                                            else "%d baud" % bauds[0]))
    for baud in bauds:
        print("-- %d baud" % baud)
        try:
            with serial.Serial(args.port, baud, timeout=0.2) as s:
                raw = b""
                t0 = time.time()
                while time.time() - t0 < args.secs:
                    raw += s.read(4096)
        except serial.SerialException as e:
            sys.exit("could not open %s: %s" % (args.port, e))
        if _nmea_report(raw, baud) or len(bauds) == 1:
            return
    print("\nNo NMEA at any baud — check power and that you have the module's TX "
          "(not RX) on the adapter's RX.")


def mode_boat(args: argparse.Namespace) -> None:
    """Read the firmware's own telemetry: does the boat think the GPS is healthy?"""
    if serial is None:
        sys.exit("pyserial not installed")
    print("Listening to the firmware on %s for %.0f s.\n" % (_PORT, args.secs))
    with serial.Serial(_PORT, 115200, timeout=0.2) as s:
        raw = b""
        t0 = time.time()
        while time.time() - t0 < args.secs:
            raw += s.read(4096)

    frames = [ln.strip().decode("ascii", "replace")
              for ln in raw.split(b"\n") if ln.strip().startswith(b"$")]
    if not frames:
        print("  No frames at all — the firmware is NOT running (the Pico is sitting at\n"
              "  the REPL). Nothing is reading the GPS. Start it with:\n"
              "      %s -m mpremote connect %s reset" % (sys.executable, _PORT))
        return

    tel = [f for f in frames if f.startswith("$TEL,")]
    gps_alerts = [f for f in frames if "SENSOR_FAULT,gps" in f]
    print("  %d frames (%d TEL), %d GPS SENSOR_FAULT alerts" % (len(frames), len(tel),
                                                                len(gps_alerts)))
    if tel:
        f = tel[-1].split("*")[0].split(",")
        health = f[11] if len(f) > 11 else "??????"
        print("  latest TEL: lat=%s lon=%s speed=%s health=%s (GPS bit = %s)"
              % (f[2], f[3], f[5], health, health[0] if health else "?"))
        if health[:1] == "1":
            print("  VERDICT: firmware reports the GPS HEALTHY with a fix.")
            return
    print("  VERDICT: firmware sees no GPS fix. Run `pins` to find out whether any\n"
          "  NMEA reaches the Pico at all, then `uart` once GPS TX is on GP5.")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mode", nargs="?", default="boat",
                    choices=("boat", "pins", "uart", "soft", "host"))
    ap.add_argument("--port", default=None, help="Pico CDC port (default: config.yaml)")
    ap.add_argument("--pin", type=int, default=5, help="Pico RX pin (default 5)")
    ap.add_argument("--tx", type=int, default=None,
                    help="uart mode: TX pin (default: the RX pin's UART1 partner)")
    ap.add_argument("--pins", default=None,
                    help="pins mode: comma-separated subset to scan, e.g. 8,9")
    ap.add_argument("--baud", type=int, default=9600,
                    help="GPS baud; 0 = try 9600/38400/57600/115200/4800 (host mode)")
    ap.add_argument("--secs", type=float, default=None, help="capture seconds")
    ap.add_argument("--no-restart", action="store_true",
                    help="leave the firmware stopped after pins/uart")
    args = ap.parse_args(argv)

    global _PORT
    if args.mode == "host":
        args.port = args.port or "/dev/ttyUSB0"
        _PORT = args.port
    else:
        _PORT = args.port or _default_port()

    if args.secs is None:
        args.secs = 1.3 if args.mode == "pins" else 12.0

    {"boat": mode_boat, "pins": mode_pins, "uart": mode_uart,
     "soft": mode_soft, "host": mode_host}[args.mode](args)


if __name__ == "__main__":
    main()
