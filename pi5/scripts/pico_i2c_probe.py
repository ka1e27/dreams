#!/usr/bin/env python3
"""Probe the Boat Pico's I2C buses and its GPIO pads from the Pi — no meter, no disassembly.

Written to answer "is my IMU working?", which on this board splits into three
separate questions: is the device *present*, is it on the bus the *firmware*
talks to, and is the pad it lands on *electrically alive*. This board has
answered "no" to a different one of those each time.

Runs on the Pi and drives the Pico's **raw REPL** over USB CDC, so it never
executes `main.py`. That matters: `status_led.py` drives GP10 into a hard short,
and `main.py`'s own boot probe of the IMU is looking at the wrong bus entirely.

    python -m pi5.scripts.pico_i2c_probe map    # pad health — run this first
    python -m pi5.scripts.pico_i2c_probe scan   # who answers on each bus
    python -m pi5.scripts.pico_i2c_probe watch  # ~30 s: is the bus flapping?
    python -m pi5.scripts.pico_i2c_probe imu    # bring the BNO085 up, read heading

INTERRUPTING THE FIRMWARE. `main.py` has ten bare `except:` blocks in its asyncio
task loops, every one of which swallows KeyboardInterrupt. A single Ctrl-C almost
always lands inside a task and is eaten, so `_raw_repl` spams it until one lands
in the scheduler and propagates out of `asyncio.run()`. Usually the first burst.

MEASURED 2026-07-30. **Pads 12/13/14 are a genuine hard short** — the documented
2026-07-29 solder blob across GP9 / GND / GP10, which kills I2C0 (GP9 = SCL0) and
the status NeoPixel (GP10). It reproduces on every single run.

**GP14/GP15/GP17 are a different animal: an intermittent bus hang, not a bridge.**
In one session `map` returned three different states minutes apart, with nothing
physically touched in between:

    GP14 low  + GP15 low,  GP17 high    bus dead — 0/60 samples released over 15 s
    GP14 high + GP15 high, GP17 low     bus FINE — 0x44 and 0x4B both answer, 40/40
    GP14 high + GP15 low,  GP17 high    bus dead

A solder bridge cannot migrate between pins, so this is not solder. Three tells:

  * **SCL alone held low is clock stretching** — the signature of a hung slave, not
    a short to GND. (Both lines low is the same hang caught mid-byte.)
  * **Both hangs immediately followed a large read** — a 128-byte SoftI2C attempt,
    then a 267-byte hardware read. Short transactions run for ages without trouble.
  * Pulsing `~RST` (GP17) does **not** free a stuck SCL, and while GP17 itself read
    low the BNO still answered — so GP17 does not gate the chip the way J5.7 implies.

Leading cause, already on the board's to-do list: **this bus has no pull-up
resistors fitted** (`docs/pin_map.md` — "no pull-ups — fit 2.2 kOhm"). Three
connectors hang off it (J5 + J7 + J13), so the only pull-ups present are whatever
the plugged-in breakouts happen to carry, working against all that trace
capacitance. That produces exactly this behaviour: fine for short transfers,
corrupting on long bursts, with a confused slave then holding the bus until it
self-recovers. Compounding it, the SHT41 on J13 is fed VSYS **5 V against a 3.6 V
absolute max**, and a 5 V-referenced part pulling this bus high also exceeds the
RP2040's input limits.

WHERE THE IMU ACTUALLY LIVES. Two firmware/board mismatches, independent of all the
above — `compass.py` cannot work even on a perfectly behaved bus:

  * **Bus.** `compass.init()` does `I2C(0, sda=Pin(8), scl=Pin(9))`. The board
    wires the IMU's I2C to **GP14/GP15** (`docs/pin_map.md` — J5.4/J5.3), i.e.
    SoftI2C #B, shared with the SHT41. GP8/GP9 go to J7, and GP9 is hard-shorted.
  * **Address.** `BNO_ADDR = 0x4A`. This module answers at **0x4B** (ADR pulled
    high); 0x4A returns ENODEV.

Positively identified as a genuine BNO08x, not merely an address that ACKs: its
267-byte boot advertisement on channel 0 decodes to the ASCII SHTP service list
`SHTP / control / executable / device / sensorhub`.

⚠ Long reads. `_read_shtp_packet` re-reads the whole packet in one transaction.
That 267-byte advertisement **times out on SoftI2C at 100 kHz** but reads cleanly
on **hardware I2C1 at 400 kHz** — GP14/GP15 are the native I2C1 pair. Note
`sensors.py` already owns those pins as SoftI2C for the SHT41, so a port must have
the two drivers **share one bus object**, not open two. Draining the advertisement
is not required before `SET_FEATURE`; the BNO08x also sets the header's
continuation bit if you prefer chunked reads.
"""
import sys
import time

import serial

PORT = "/dev/ttyACM0"

# Physical Pico pad -> signal, for the run of pads around GND pads 13/18/23.
PADS = {
    11: "GP8", 12: "GP9", 13: "GND", 14: "GP10", 15: "GP11", 16: "GP12",
    17: "GP13", 18: "GND", 19: "GP14", 20: "GP15", 21: "GP16", 22: "GP17",
    23: "GND", 24: "GP18", 25: "GP19", 26: "GP20",
}

ROLES = {
    "GP8": "I2C0 SDA (firmware) / J7.4", "GP9": "I2C0 SCL (firmware) / J7.3",
    "GP10": "status NeoPixel (J12)", "GP11": "ESC telem R (PIO)",
    "GP12": "SoftI2C #A SDA (J11)", "GP13": "SoftI2C #A SCL (J11)",
    "GP14": "SoftI2C #B SDA - J5.4 IMU / J13", "GP15": "SoftI2C #B SCL - J5.3 IMU / J13",
    "GP16": "ESC telem L (PIO)", "GP17": "BNO085 ~RST (J5.7)",
    "GP18": "BNO085 ~INT (J5.8)", "GP19": "hull leak L (J16)", "GP20": "hull leak R (J15)",
}


def _raw_repl(port=PORT, bursts=60):
    """Open the port and wrestle the Pico into raw REPL. Returns the Serial."""
    s = serial.Serial(port, 115200, timeout=0.1)
    for i in range(bursts):
        s.write(b"\x03" * 12)
        s.flush()
        time.sleep(0.05)
        s.write(b"\x03\x01")
        s.flush()
        time.sleep(0.15)
        if b"raw REPL" in s.read(8192):
            return s
    s.close()
    raise RuntimeError("could not interrupt the firmware after %d bursts" % bursts)


def run(code, timeout=30.0, port=PORT):
    """Exec a snippet in the Pico's raw REPL. Returns (stdout, stderr)."""
    s = _raw_repl(port)
    try:
        s.write(code.encode() + b"\x04")
        s.flush()
        buf = b""
        deadline = time.time() + timeout
        while time.time() < deadline and buf.count(b"\x04") < 2:
            buf += s.read(512)
        s.write(b"\x02")
        s.flush()
        time.sleep(0.1)
    finally:
        s.close()
    if buf.startswith(b"OK"):
        buf = buf[2:]
    parts = buf.split(b"\x04")
    return parts[0].decode(errors="replace"), (
        parts[1].decode(errors="replace") if len(parts) > 1 else "")


# --- Pico-side snippets -----------------------------------------------------

_MAP = """
from machine import Pin
import time
pads = %r
for pad in sorted(pads):
    sig = pads[pad]
    if sig == "GND":
        print("%%3d GND - - -" %% pad); continue
    gp = int(sig[2:])
    p = Pin(gp, Pin.IN); time.sleep_ms(2); f = p.value()
    p = Pin(gp, Pin.IN, Pin.PULL_DOWN); time.sleep_ms(2); d = p.value()
    p = Pin(gp, Pin.IN, Pin.PULL_UP); time.sleep_ms(2); u = p.value()
    Pin(gp, Pin.IN)
    print("%%3d %%s %%d %%d %%d" %% (pad, sig, f, d, u))
"""

_SCAN = """
from machine import Pin, SoftI2C
names = {0x44:"SHT41", 0x45:"SHT41-alt", 0x4A:"BNO085", 0x4B:"BNO085 (ADR high)",
         0x28:"BNO055", 0x68:"MPU6xxx", 0x6A:"LSM6DS", 0x0D:"QMC5883"}
def show(tag, scl, sda):
    try:
        a = SoftI2C(scl=Pin(scl), sda=Pin(sda), freq=100000).scan()
    except Exception as e:
        print("%-26s GP%-2d/GP%-2d  ERR %r" % (tag, sda, scl, e)); return
    if not a:
        print("%-26s GP%-2d/GP%-2d  EMPTY" % (tag, sda, scl)); return
    print("%-26s GP%-2d/GP%-2d  %s" % (tag, sda, scl,
          ", ".join("0x%02X (%s)" % (x, names.get(x, "?")) for x in a)))
show("SoftI2C #B  J5/J7/J13", 15, 14)
show("SoftI2C #A  J11", 13, 12)
try:
    from machine import I2C
    print("%-26s GP%-2d/GP%-2d  %s" % ("hw I2C0  J7 (firmware)", 8, 9,
          [hex(x) for x in I2C(0, sda=Pin(8), scl=Pin(9), freq=100000).scan()]))
except Exception as e:
    print("%-26s GP%-2d/GP%-2d  ERR %r" % ("hw I2C0  J7 (firmware)", 8, 9, e))
"""

_WATCH = """
from machine import Pin, I2C
import time
SIGS = ((14, "GP14 SDA J5.4"), (15, "GP15 SCL J5.3"),
        (17, "GP17 RST J5.7"), (18, "GP18 INT J5.8"))
N = 45
low = {}
for g, _ in SIGS:
    low[g] = 0
seen = {0x44: 0, 0x4B: 0}
prev = None
changes = 0
print("round  GP14 GP15 GP17 GP18  SHT41 BNO   (1 = released/healthy)")
for i in range(N):
    st = []
    for g, _ in SIGS:
        p = Pin(g, Pin.IN, Pin.PULL_UP)
        time.sleep_ms(3)
        v = p.value()
        Pin(g, Pin.IN)
        st.append(v)
        if v == 0:
            low[g] += 1
    try:
        a = I2C(1, sda=Pin(14), scl=Pin(15), freq=400000).scan()
    except Exception:
        a = []
    for k in seen:
        if k in a:
            seen[k] += 1
    key = (tuple(st), 0x44 in a, 0x4B in a)
    if key != prev:
        changes += 1
        print("%5d   %d    %d    %d    %d     %s     %s   <-- CHANGE"
              % (i, st[0], st[1], st[2], st[3],
                 "Y" if 0x44 in a else "n", "Y" if 0x4B in a else "n"))
        prev = key
    time.sleep_ms(600)
print("")
for g, lab in SIGS:
    print("  %-16s held low %2d/%d" % (lab, low[g], N))
print("  SHT41 0x44 answered %2d/%d" % (seen[0x44], N))
print("  BNO   0x4B answered %2d/%d" % (seen[0x4B], N))
print("  distinct states: %d -> %s" % (changes,
      "INTERMITTENT - see the map hint" if changes > 1 else "stable"))
"""


_IMU = """
from machine import Pin, I2C
import sys, time
sys.path.insert(0, "/")
ADDR = 0x4B
# Hardware I2C1 at 400 kHz: GP14/GP15 are the native I2C1 pair, and this is the
# only configuration measured able to read the 267-byte boot advertisement.
def fresh():
    return I2C(1, sda=Pin(14), scl=Pin(15), freq=400000)
bus = fresh()
found = bus.scan()
print("bus GP14/GP15 scan:", [hex(a) for a in found])
if ADDR not in found:
    print("BNO08x not at 0x%02X - bus is hung or the module is out; run watch" % ADDR)
else:
    try:
        h = bus.readfrom(ADDR, 4)
        ln = ((h[1] & 0x7f) << 8) | h[0]
        print("SHTP header %s -> len=%d chan=%d" % (" ".join("%02X" % x for x in h), ln, h[2]))
        if 4 < ln < 400:
            adv = bus.readfrom(ADDR, ln)
            txt = "".join(chr(c) if 32 <= c < 127 else "." for c in adv)
            print("advertisement: %r" % txt[4:88])
    except Exception as e:
        print("advertisement read failed (%r) - continuing; draining is optional" % e)
        bus = fresh()
    import compass
    compass.BNO_ADDR = ADDR      # driver hardcodes 0x4A; this module is 0x4B
    compass._i2c = bus           # driver hardcodes hw I2C0 on GP8/GP9 (dead)
    ok = compass._enable_feature(compass.SH2_ROTATION_VECTOR, 20000)
    if not ok:
        compass._i2c = bus = fresh()
        time.sleep_ms(50)
        ok = compass._enable_feature(compass.SH2_ROTATION_VECTOR, 20000)
    print("SET_FEATURE Rotation Vector @50Hz:", ok)
    got = 0
    for i in range(40):
        time.sleep_ms(100)
        try:
            compass.read()
        except Exception as e:
            print("read() exc %r" % e)
            break
        if compass._last_read_ms and got < 15:
            got += 1
            print("hdg=%6.1f  pitch=%6.1f  roll=%6.1f  cal=%d  healthy=%s"
                  % (compass.heading, compass.pitch, compass.roll,
                     compass.cal_status, compass.is_healthy()))
    if not got:
        print("no Rotation Vector reports (fail_count=%d)" % compass._fail_count)
        print("if SET_FEATURE was False the bus hung mid-write - run watch")
"""


def cmd_map():
    out, err = run(_MAP % PADS)
    print("Pico pad health — float / pull-down / pull-up (internal ~50 kOhm)\n")
    print("pad  sig    fl pd pu  verdict                          role")
    shorts = []
    for line in out.strip().splitlines():
        f = line.split()
        if len(f) < 5:
            continue
        pad, sig = f[0], f[1]
        if sig == "GND":
            print("%3s  %-5s  -- -- --  (ground pad)" % (pad, sig))
            continue
        fl, pd, pu = int(f[2]), int(f[3]), int(f[4])
        if pu == 0:
            verdict = "*** SHORTED LOW ***"
            shorts.append(sig)
        elif fl == 1 and pd == 1:
            verdict = "externally pulled HIGH"
        elif fl == 0 and pu == 1:
            verdict = "clean / floating"
        else:
            verdict = "float=%d pd=%d pu=%d" % (fl, pd, pu)
        print("%3s  %-5s   %d  %d  %d  %-32s %s"
              % (pad, sig, fl, pd, pu, verdict, ROLES.get(sig, "")))
    if err.strip():
        print("\n--- stderr ---\n" + err)
    print("\nshorted: %s" % (", ".join(shorts) if shorts else "none"))
    hung = [s for s in shorts if s in ("GP14", "GP15", "GP17", "GP18")]
    if hung:
        print(
            "\n%s carry the IMU (J5) and SHT41 #B (J13). Do NOT read this as a solder\n"
            "bridge — over one session the held-low line moved between GP14, GP15 and\n"
            "GP17 with nothing touched, and a bridge cannot migrate. SCL held low on its\n"
            "own is a slave stretching the clock, i.e. a hung device.\n"
            "Run `watch` to see it flap, then in order of likelihood:\n"
            "  1. fit the **2.2 kOhm pull-ups** to 3V3 on GP14/GP15. They were never\n"
            "     fitted (docs/pin_map.md); the only pull-ups on this bus are whatever\n"
            "     the breakouts carry, across three connectors' capacitance. This is the\n"
            "     documented fix and it matches the symptom (long bursts corrupt).\n"
            "  2. unplug J13 (SHT41 #B) and re-run `watch` -> its 5 V supply exceeds the\n"
            "     part's 3.6 V max and a 5 V-referenced pull-up abuses the RP2040 too.\n"
            "  3. reseat J5 / check its crimps -> every wandering pin is a J5 signal.\n"
            "  4. only if a line stays low across a power cycle with J5 AND J13 unplugged\n"
            "     is it board-side; then meter pads 19/20 to the GND at pad 18."
            % "/".join(hung)
        )
    return 0


def cmd_watch():
    """Sample the J5 signals and the bus repeatedly — the intermittency test."""
    out, err = run(_WATCH, timeout=90.0)
    print(out, end="")
    if err.strip():
        print("--- stderr ---\n" + err)
    return 0


def cmd_scan():
    out, err = run(_SCAN)
    print(out, end="")
    if err.strip():
        print("--- stderr ---\n" + err)
    return 0


def cmd_imu():
    out, err = run(_IMU, timeout=45.0)
    print(out, end="")
    if err.strip():
        print("--- stderr ---\n" + err)
    return 0


CMDS = {"map": cmd_map, "scan": cmd_scan, "watch": cmd_watch, "imu": cmd_imu}


def main(argv):
    if len(argv) != 2 or argv[1] not in CMDS:
        print(__doc__)
        print("usage: pico_i2c_probe.py {%s}" % "|".join(CMDS))
        return 2
    # main.py calls asyncio.run(main()) at module level, so there is no re-entry
    # point once it has been interrupted — it has to be re-executed from scratch.
    print("NOTE: this stops the Pico firmware. Restart it with a power cycle or\n"
          "      `import machine; machine.soft_reset()` at the REPL.\n")
    return CMDS[argv[1]]()


if __name__ == "__main__":
    sys.exit(main(sys.argv))
