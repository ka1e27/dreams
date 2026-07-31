"""Static pin prober for the A4988 control lines — for metering with a DMM.

Companion to stepper_lowlevel_test.py. That test tells you whether the motor
*responds*; this one tells you whether a signal physically *arrives*.

Use it for the "coils hold but the shaft never advances" case, which means the
driver is powered, awake, out of reset and enabled, but the phase isn't moving —
i.e. STEP is not getting from the Pi to the A4988.

Each line is driven to a steady HIGH (3.3 V) for a fixed window so you can probe
both ends with a multimeter. ~ENABLE is held HIGH (driver disabled) the whole
time so the coils stay cold while you work.

Run with the main stack STOPPED:

    pkill -f run_hardware.py
    .venv/bin/python pi5/cv/stepper_probe.py pins       # START HERE — no meter needed
    .venv/bin/python pi5/cv/stepper_probe.py            # walk all four lines
    .venv/bin/python pi5/cv/stepper_probe.py step 60    # just STEP, for 60s
    .venv/bin/python pi5/cv/stepper_probe.py power 120  # hold ENERGISED, meter the rails
    .venv/bin/python pi5/cv/stepper_probe.py burst      # 400 pulses/dir — did it ROTATE?
    .venv/bin/python pi5/cv/stepper_probe.py find       # hunt a mis-wired STEP, no meter

**Start with `power` if the shaft spins freely and silently.** That symptom means no
coil current at all, in which case the four signal lines below are *not* the fault —
it is the A4988 or its motor output path. `power` parks the driver awake + energised
and walks the rail checks in order.

Established by measurement on 2026-07-29, so don't re-derive it:

  * All four Pi pins swing 0 V / 3.3 V at the pad — the Pi side is good.
  * The driver software emits exact pulse counts in the right control order
    (~SLEEP high -> ~ENABLE low -> DIR -> pulses) and is not in mock mode.
  * **VMOT is present at 15.53 V**, measured through the Pico: VMOT is the same
    rail the Pico watches on GP28 (VMOT -> R8 100k -> R9 1k -> Pico pad 34).
  * With ~ENABLE asserted and 400 pulses sent, **the VMOT rail did not move
    (±3 mV)** — so the A4988 draws no motor current whatsoever.
  * A4988 VDD really is the Pi's 3V3. J3's footprint transposes odd/even rows, and
    for *even* pads that means pad 2 -> Pi header pin 1; odd pads go +1, which is
    why STEP pad 15 -> pin 16. ~RESET (A2.13) and ~SLEEP (A2.14) resolve to **one
    net in the schematic**, so that tie is by design — but this board has diverged
    from its schematic three times already, so still verify it with a meter.

**Then run `pins`.** It is the cheapest test in this file and it is the one that
actually found the fault on 2026-07-29: it characterises each control line
electrically (internal pull-down, internal pull-up, driven low, driven high) and
reads the *pad* level back with ``pinctrl`` each time. That distinguishes a
floating net from one an external source is holding, which no amount of
"drive it and hope" can. Result that session:

    GPIO23 STEP     lo / hi / lo / hi   clean, floating
    GPIO24 DIR      hi / hi / hi / hi   STUCK HIGH -- hard short to a 3V3 source
    GPIO25 ~ENABLE  lo / hi / lo / hi   clean, floating
    GPIO8  ~SLEEP   lo / hi / lo / hi   clean, floating

DIR reads high *while the Pi actively drives it low*, so it is a low-impedance
tie, not a weak pull-up. DIR is J3 pad 17; pad 18 sits 2.54 mm away in the same
row and mates with Pi header pin 17 = **3V3** — which is also the net that feeds
A4988 VDD and MS1 (J3 pad 2). Consequence: ``stepper.py`` drives DIR low on every
move and at construction (``OutputDevice(24, initial_value=False)``), so it has
been loading the A4988's own supply whenever BT4 was connected. Powering VMOT
with VDD unstable is a documented way to destroy the output stage.

⚠ Note ``pinctrl`` -- not lgpio -- is used for the read-back on purpose. Reading a
line claimed as an *output* through the gpio chardev returns the value you wrote,
not the voltage on the pad, so it cannot see contention at all.

``pins`` doubles as a **which-carrier-is-this** test, which is how the dead A4988
was picked back out of a pair of physically identical boards on 2026-07-29 with no
meter. Three signatures, measured on this hardware:

    empty socket / good carrier   DIR  lo / hi / lo / hi
    the dead one, before it died  DIR  hi / hi / hi / hi   hard tie to 3V3
    the dead one, after it died   DIR  lo / lo / lo / hi   few-kOhm pull-down

The tell for the dead carrier is **pullup=lo on DIR while STEP/~ENABLE/~SLEEP stay
clean**: the Pi's internal ~50 kOhm pull-up can no longer lift the pin. A healthy
CMOS input is >1 MOhm both ways, and a board-side fault would not single out DIR.

⚠ ``pins`` **cannot detect an open net** — a broken wire reads exactly like a
healthy floating one. It rules out shorts, not breaks. Use ``burst`` for that:
visible rotation is the only honest test of the STEP path.

The open STEP net (2026-07-29, the live fault)
----------------------------------------------
With a *working* carrier fitted the driver holds with real torque, chip and motor
warm together, but **800 pulses produce zero rotation** — so every rail, both coil
outputs, ~ENABLE, ~SLEEP and the ~RESET tie are good and exactly one signal has
never functioned. The first bring-up (2026-06-08) already said "PASS but no
motion", so this is a **build defect, not a failure**: the board was hand-built
(``Boat_PCB.kicad_pcb`` has no nets at all) and one STEP wire is missing or misplaced.

Solved from the schematic geometry, the STEP net is a **three-way node**:

    A2.15 (STEP)  ---  J3.15  ---  J14.13

``J14`` is a 1x20 **socket**, so that midpoint is reachable with a jumper — no
soldering, and no need to get at Pi header pin 16 under the mated Pi. Same rule for
the other lines: Pi odd pins appear on ``J17.k = Pi pin 2k-1``, even pins on
``J14.k = Pi pin 2(21-k)``. Hold STEP high (``stepper_probe.py step 240``) and take
**two** readings to bisect the net:

    J14.13    A2.15 STEP   meaning
    3.3 V     3.3 V        net is good -> the carrier's STEP input or its socket
                           contact is the fault; reseat, then swap carriers
    3.3 V     0 V          break between J14/J3 and the carrier
                           -> jumper J14.13 to the carrier's STEP pin
    0 V       0 V          break at J3 pad 15 or the Pi mate; the board side of
                           the net is dead -> jumper a different free Pi GPIO from
                           J14/J17 to the STEP pin and set stepper.step_pin

Before reaching for the meter run ``find``: if that STEP wire landed on the *wrong
Pi pin* rather than being missing, some other GPIO is driving A2.15 and the scan
will find it in about a minute with nothing but your eyes.

Probe points (Boat_PCB V2, verified against the netlist):

    signal    BCM      Pi header pin    A4988 (A2) pin
    STEP      GPIO23   16               STEP
    DIR       GPIO24   18               DIR
    ~ENABLE   GPIO25   22               ~ENABLE
    ~SLEEP    GPIO8    24               ~SLEEP (tied to ~RESET on this board)

Measure each against GND (header pin 6/9/14/20). Interpretation:

  * Pi header pin reads 3.3 V AND the A4988 pin reads 3.3 V
        -> that net is good.
  * Pi header pin reads 3.3 V but the A4988 pin reads ~0 V
        -> BROKEN NET. An open joint at J3, a lifted pad, or a cracked trace
           between the header and A2. If the A4988 pin also reads ~0 V with
           nothing driving it, check for a short to GND.
  * Pi header pin itself reads ~0 V
        -> the Pi isn't driving it: wrong pin, or another process holds the line
           (stop run_hardware.py), or the pin is damaged.

Remember J3's footprint has its odd/even rows transposed relative to the
schematic symbol, so trust the "Pi header pin" column above and NOT the
schematic pad numbers. See docs/pin_map.md.
"""
from __future__ import annotations

import subprocess
import sys
import time

# name -> (BCM, Pi header pin, A4988 pin label, active level note)
LINES = {
    "step": (23, 16, "STEP", "pulse input"),
    "dir": (24, 18, "DIR", "direction"),
    "enable": (25, 22, "~ENABLE", "active-LOW"),
    "sleep": (8, 24, "~SLEEP (+~RESET)", "active-LOW"),
}
DEFAULT_HOLD_S = 20.0
DEFAULT_POWER_HOLD_S = 120.0

# burst mode: dense enough that every landed pulse is visible rotation. 400 half
# steps x 0.9 deg = one full revolution per direction, so travel measures the hit
# rate directly (degrees / 360). 50 Hz starts from rest without ramping.
BURST_PULSES = 400
BURST_RATE_HZ = 50.0
BURST_PULSE_S = 100e-6          # 100x the A4988's 1 us minimum
DEG_PER_STEP = 0.9              # half step on this board — MS1 high, MS2/MS3 low

# find mode: shorter per pin, since it runs ~20 of them. 100 pulses = 90 deg,
# unmistakable on a bare shaft, and 100 Hz (15 rpm) still starts from rest.
FIND_PULSES = 100
FIND_RATE_HZ = 100.0

# BCM -> Pi 5 40-pin header position. Used to name a hit physically, and to work
# out its J14/J17 breakout pad so a fix can be a jumper rather than a solder job.
HEADER_PIN = {
    2: 3, 3: 5, 4: 7, 14: 8, 15: 10, 17: 11, 18: 12, 27: 13, 22: 15, 23: 16,
    24: 18, 10: 19, 9: 21, 25: 22, 11: 23, 8: 24, 7: 26, 0: 27, 1: 28, 5: 29,
    6: 31, 12: 32, 13: 33, 19: 35, 16: 36, 26: 37, 20: 38, 21: 40,
}

# Pins find mode must not touch, with the reason shown to the user.
FIND_SKIP = {
    24: "DIR — this test needs it",
    25: "~ENABLE — this test needs it",
    8: "~SLEEP/~RESET — this test needs it",
    14: "GPS UART TXD0 (dtoverlay=uart0)",
    15: "GPS UART RXD0 — the module drives this line",
}

# Ordered rail checks for the "no coil current at all" case. Cheapest and most
# likely first, so you stop as soon as you find it.
POWER_CHECKS = (
    ("1. Motor plugged into J18?",
     "Look first — an unplugged or open coil gives exactly this symptom.",
     "Then UNPLUG it and ohm the wires: one coil = a few ohms; a wire from one\n"
     "     coil to the other = open. 4 wires = 2 pairs. An open winding is a dead motor."),
    ("2. VREF (current limit)",
     "trimpot wiper / REF pin, against GND — expect roughly 0.3-0.8 V",
     "~0 V means the current limit is turned all the way down, so the coils get\n"
     "     no current and the shaft spins freely. Turn it up slowly.\n"
     "     I_coil = VREF / (8 x Rsense); Rsense is 0.068-0.1 ohm on most carriers."),
    ("3. VMOT at the A4988's OWN pin 8",
     "expect ~15.5 V (that is what the rail measures at J6/BT4)",
     "15.5 V at J6 but ~0 V at the chip = the carrier is not seated, or a joint\n"
     "     on the VMOT pin is open. This is common with socketed carriers."),
    ("4. VDD at the A4988's OWN pin 2",
     "expect 3.3 V — it is fed only from the Pi's 3V3 (header pin 1 via J3)",
     "0 V here and the chip is unpowered, so nothing can work. Check J3 is fully\n"
     "     mated and that pad is not lifted."),
    ("5. ~RESET (A2.13) vs ~SLEEP (A2.14)",
     "BOTH must read 3.3 V right now — this mode holds ~SLEEP high for you",
     "~SLEEP 3.3 V but ~RESET 0 V = the on-board tie between them is broken.\n"
     "     A low RESET makes the A4988 ignore every STEP pulse with no error at\n"
     "     all — the classic 'powered but never moves'. Fix: jumper A2.13 to\n"
     "     A2.14, or set stepper.reset_pin in config.yaml to a free BCM pin and\n"
     "     wire it to A2.13."),
    ("6. MS1 / MS2 / MS3",
     "MS1 ~3.3 V (via R1 10k to VDD), MS2 and MS3 ~0 V = half step, 400 steps/rev",
     "If these disagree with steps_per_rev: 400 in config.yaml, every move is\n"
     "     scaled wrong — but that would still MOVE, so it is not this fault."),
)


def _pinctrl(*args: str) -> str:
    """Run ``pinctrl`` and return stdout. Raises if the tool is missing."""
    return subprocess.run(("pinctrl",) + args, capture_output=True, text=True,
                          check=True).stdout


def _pad_level(bcm: int) -> str:
    """The *pad* level of a pin, as reported by pinctrl ('hi' or 'lo').

    Deliberately not lgpio: the gpio chardev reports the value written to an
    output line rather than the voltage actually on the pad, so it is blind to a
    pin being held by something else on the board.
    """
    out = _pinctrl("get", str(bcm))
    return "hi" if out.rsplit("|", 1)[-1].split("//")[0].strip() == "hi" else "lo"


def _jtap(bcm: int) -> str:
    """Where a BCM pin surfaces on the board's Pi-header breakout sockets.

    J17 carries the Pi's odd pins in order, J14 the even pins reversed — so every
    Pi GPIO has a socket hole on this board, which is what makes a jumper fix
    possible without getting under the mated Pi.
    """
    pin = HEADER_PIN.get(bcm)
    if pin is None:
        return "not on the header"
    if pin % 2:
        return "J17.%d" % ((pin + 1) // 2)
    return "J14.%d" % (21 - pin // 2)


def _repark() -> None:
    """Latch ~ENABLE disabled + ~SLEEP asleep with pinctrl, and say so.

    gpiozero releases every pin on exit, and the board's 10 kOhm ~ENABLE pull-up
    was never fitted (docs/pcb_design_notes.md), so a script that just exits
    leaves ~ENABLE floating with VMOT live — the driver can come up energised on
    an undefined phase. pinctrl latches persist, so this closes that window.
    """
    try:
        _pinctrl("set", "25", "op", "dh")     # ~ENABLE high = disabled
        _pinctrl("set", "8", "op", "dl")      # ~SLEEP low = asleep
        print("  re-parked: ~ENABLE disabled, ~SLEEP asleep (latched via pinctrl).")
    except (FileNotFoundError, subprocess.CalledProcessError) as e:
        print("  ⚠ could not re-park with pinctrl (%s) — unplug BT4 before walking"
              " away, ~ENABLE is floating." % e)


def _classify(pd: str, pu: str, dl: str, dh: str) -> str:
    if pd == "lo" and pu == "hi" and dl == "lo" and dh == "hi":
        return "OK      floating when idle, follows the Pi cleanly"
    if pd == "hi" and dl == "hi":
        return "SHORTED held HIGH even while driven low -> low-impedance tie to a 3V3 source"
    if pu == "lo" and dh == "lo":
        return "SHORTED held LOW even while driven high -> tied to GND"
    if pd == "hi" and dl == "lo":
        return "PULLED  an external pull-up the Pi can still override (resistive, not a short)"
    return "ODD     unexpected pattern — record it before changing anything"


def _pins(settle_s: float = 0.15) -> None:
    """Characterise each control line: internal pull-down/up, then driven both ways.

    Cheap, safe and non-destructive — nothing is left energised. This is the test
    that found DIR shorted to 3V3; run it before reaching for a meter.
    """
    print("=" * 78)
    print("  A4988 CONTROL-LINE CHARACTERISATION  (pad level read back via pinctrl)")
    print("=" * 78)
    print("  interpretation:")
    print("    pulldown=lo pullup=hi and follows drive  -> floating, healthy")
    print("    pulldown=hi AND drive-low still reads hi -> hard short to 3V3")
    print("    pullup=lo   AND drive-high still reads lo -> hard short to GND\n")
    print("  %-8s %-16s %-9s %-8s %-10s %-11s %s"
          % ("BCM", "signal", "pulldown", "pullup", "drive-low", "drive-high", "verdict"))

    verdicts: dict[str, str] = {}
    for name, (bcm, _header, label, _note) in LINES.items():
        readings = []
        for mode in ("ip pd", "ip pu", "op dl", "op dh"):
            _pinctrl("set", str(bcm), *mode.split())
            time.sleep(settle_s)
            readings.append(_pad_level(bcm))
        pd, pu, dl, dh = readings
        verdict = _classify(pd, pu, dl, dh)
        verdicts[name] = verdict
        print("  GPIO%-4d %-16s %-9s %-8s %-10s %-11s %s"
              % (bcm, label, pd, pu, dl, dh, verdict))
        # Leave every line high-Z rather than driving into a possible short.
        _pinctrl("set", str(bcm), "ip", "pn")

    print("\n  all four lines left as high-Z inputs — nothing is energised.")
    bad = [n for n, v in verdicts.items() if not v.startswith("OK")]
    if bad:
        print("  ⚠ %s did NOT come back clean. A shorted control line can drag the"
              % ", ".join(n.upper() for n in bad))
        print("    A4988's own VDD around (DIR sits next to the VDD/MS1 net on J3),")
        print("    so fix it before fitting a replacement driver.")
    else:
        print("  all four lines are electrically clean — the fault is past the header.")


def _probe(OutputDevice, name: str, hold_s: float) -> None:
    bcm, header, a4988, note = LINES[name]
    print("\n" + "=" * 62)
    print("  %s  ->  BCM GPIO%d  ->  Pi header pin %d  ->  A2 %s  (%s)"
          % (name.upper(), bcm, header, a4988, note))
    print("=" * 62)
    print("  driving HIGH for %.0fs — probe BOTH ends against GND now:" % hold_s)
    print("    header pin %-2d  expect 3.3 V" % header)
    print("    A4988 %-16s expect 3.3 V  (0 V here = broken net)" % a4988)
    dev = OutputDevice(bcm, initial_value=True)
    try:
        for remaining in range(int(hold_s), 0, -1):
            print("    HIGH  %2ds remaining ..." % remaining, end="\r", flush=True)
            time.sleep(1.0)
        print("    HIGH  done.                    ")
        # A low reading afterwards confirms the meter was on a live net, not a
        # floating one that merely looked high.
        dev.value = 0
        print("  now driving LOW for 3s — the same points should read ~0 V")
        time.sleep(3.0)
    finally:
        dev.close()


def _power(OutputDevice, hold_s: float) -> None:
    """Hold the driver awake + energised so the rails can be metered at rest.

    Unlike the per-line probes this asserts ~ENABLE **low** on purpose: the
    coils should be drawing current, which is exactly what we're trying to
    confirm. Nothing steps, so every reading is static and easy to take.
    """
    print("=" * 68)
    print("  A4988 POWER / ENABLE RAIL CHECK")
    print("=" * 68)
    print("  Symptom this is for: shaft silent, spins freely by hand, no holding")
    print("  torque -> no coil current. The Pi pins and the driver software have")
    print("  already been proven good, so the fault is at the A4988 itself.\n")

    step = OutputDevice(23, initial_value=False)
    dirp = OutputDevice(24, initial_value=False)
    slp = OutputDevice(8, initial_value=True)      # 1 = awake (and RESET, via the tie)
    en = OutputDevice(25, initial_value=True)      # start disabled
    try:
        time.sleep(0.005)                          # charge pump settle
        en.value = 0                               # energise
        print("  driver is now AWAKE (~SLEEP high) and ENERGISED (~ENABLE low).")
        print("  the shaft SHOULD resist being turned. work through these in order:\n")
        for title, expect, meaning in POWER_CHECKS:
            print("  %s" % title)
            print("     measure : %s" % expect)
            print("     if bad  : %s\n" % meaning)
        print("  holding for %.0fs — Ctrl-C when you're done." % hold_s)
        for remaining in range(int(hold_s), 0, -1):
            print("    ENERGISED  %3ds remaining ..." % remaining, end="\r", flush=True)
            time.sleep(1.0)
        print("    ENERGISED  done.                      ")
    finally:
        # Always de-energise: coils left energised with no motion cook the motor.
        en.value = 1
        slp.value = 0
        for d in (step, dirp, en, slp):
            d.close()
        print("  released — coils de-energised, driver asleep.")
        _repark()


def _pulse_train(step, pulses: int, rate_hz: float) -> float:
    """Send `pulses` rising edges on an already-claimed STEP line. Returns seconds."""
    gap = max(0.0, 1.0 / rate_hz - BURST_PULSE_S)
    t0 = time.monotonic()
    for _ in range(pulses):
        step.value = 1
        time.sleep(BURST_PULSE_S)
        step.value = 0
        time.sleep(gap)
    return time.monotonic() - t0


def _burst(OutputDevice, pulses: int) -> None:
    """Dense STEP burst — the only honest test of whether pulses reach the chip.

    A 1 Hz walk is ambiguous: the rotor snapping to a detent on energise and
    relaxing on release looks exactly like "a couple of steps landed". Sending a
    full revolution's worth removes the ambiguity — either the shaft turns or the
    STEP path is broken.
    """
    print("=" * 68)
    print("  A4988 DENSE STEP BURST")
    print("=" * 68)
    print("  MARK THE SHAFT first (tape or a pen line) so partial travel counts.")
    print("  %d pulses per direction at %.0f Hz, %.0f us wide."
          % (pulses, BURST_RATE_HZ, BURST_PULSE_S * 1e6))
    print("  if every pulse lands: %.0f deg = %.2f revolution(s) per direction.\n"
          % (pulses * DEG_PER_STEP, pulses * DEG_PER_STEP / 360.0))

    step = OutputDevice(23, initial_value=False)
    dirp = OutputDevice(24, initial_value=False)
    slp = OutputDevice(8, initial_value=True)      # awake (+ ~RESET via the tie)
    en = OutputDevice(25, initial_value=True)      # start disabled
    try:
        time.sleep(0.005)                          # charge pump settle
        en.value = 0
        print("  energised — the shaft should resist by hand. watch it now.\n")
        time.sleep(1.0)
        for direction, label in ((1, "CW"), (0, "CCW")):
            dirp.value = direction
            time.sleep(0.001)                      # DIR setup, >200 ns
            el = _pulse_train(step, pulses, BURST_RATE_HZ)
            print("  %-4s %d pulses sent in %.2f s (%.1f Hz actual)"
                  % (label, pulses, el, pulses / el))
            time.sleep(1.0)
        print("\n  How far did the shaft travel?")
        print("    ~%.0f deg each way -> every pulse landed, the STEP path is GOOD"
              % (pulses * DEG_PER_STEP))
        print("    partial travel     -> intermittent STEP contact; hit rate = deg / %.0f"
              % (pulses * DEG_PER_STEP))
        print("    dead still         -> STEP never arrives. Meter J14.13 and the")
        print("                          carrier's STEP pin (see the module docstring).")
    finally:
        en.value = 1
        slp.value = 0
        for d in (step, dirp, en, slp):
            d.close()
        print("\n  released — coils de-energised.")
        _repark()


def _find(OutputDevice, only: list[int] | None = None) -> None:
    """Hunt for a STEP wire that landed on the wrong Pi pin. No meter needed.

    The board was hand-built from a schematic with no net labels, so a misplaced
    STEP wire is as likely as a missing one. If some *other* GPIO is wired to
    A2.15, driving it moves the motor — so walk every free header pin and watch.

    Each candidate is characterised first and driven **only if it reads cleanly
    floating**, so the scan can never fight something the board is driving.
    """
    cands = only if only else [23] + [p for p in sorted(HEADER_PIN)
                                      if p not in FIND_SKIP and p != 23]
    print("=" * 74)
    print("  HUNT FOR A MIS-WIRED STEP LINE  (%d candidate pins)" % len(cands))
    print("=" * 74)
    print("  Premise: ~ENABLE, ~SLEEP, ~RESET, VMOT, VDD and both coils are proven")
    print("  good, and GPIO23 produces no rotation — so the STEP wire is missing or")
    print("  on the wrong pin. This drives each free header pin in turn.\n")
    print("  WATCH THE SHAFT. Each pin gets %d pulses = %.0f deg of travel if it is"
          % (FIND_PULSES, FIND_PULSES * DEG_PER_STEP))
    print("  the real STEP line. Note the GPIO number on screen when it moves.")
    print("  GPIO23 goes first as the baseline — it should do nothing.\n")
    for bcm, why in sorted(FIND_SKIP.items()):
        print("    skipping GPIO%-2d  %s" % (bcm, why))
    print()

    dirp = OutputDevice(24, initial_value=False)
    slp = OutputDevice(8, initial_value=True)
    en = OutputDevice(25, initial_value=True)
    driven, skipped = [], []
    try:
        time.sleep(0.005)
        en.value = 0
        print("  energised. starting in 3s ...\n")
        time.sleep(3.0)
        for bcm in cands:
            # Characterise before driving: only a cleanly floating pin is safe.
            readings = []
            for mode in ("ip pd", "ip pu"):
                _pinctrl("set", str(bcm), *mode.split())
                time.sleep(0.12)
                readings.append(_pad_level(bcm))
            _pinctrl("set", str(bcm), "ip", "pn")
            if readings != ["lo", "hi"]:
                skipped.append(bcm)
                print("  GPIO%-2d  %-9s SKIP — not floating (pd=%s pu=%s), something"
                      " else holds it" % (bcm, _jtap(bcm), readings[0], readings[1]))
                continue
            print("  GPIO%-2d  %-9s header pin %-2d  -> %d pulses ..."
                  % (bcm, _jtap(bcm), HEADER_PIN[bcm], FIND_PULSES), end="", flush=True)
            dev = OutputDevice(bcm, initial_value=False)
            try:
                _pulse_train(dev, FIND_PULSES, FIND_RATE_HZ)
            finally:
                dev.close()
                _pinctrl("set", str(bcm), "ip", "pn")
            driven.append(bcm)
            print(" done")
            time.sleep(1.5)
        print("\n  swept %d pins (%d skipped as non-floating)." % (len(driven), len(skipped)))
        print("  If the shaft moved on some pin, re-run to confirm:")
        print("      stepper_probe.py find --pins <that pin>")
        print("  then set stepper.step_pin in pi5/config.yaml and jumper its breakout")
        print("  pad to the carrier's STEP pin.")
        print("  If NOTHING moved on any pin, the STEP wire is simply absent — meter")
        print("  J14.13 and A2.15 to place the break, then jumper it.")
    finally:
        en.value = 1
        slp.value = 0
        for d in (dirp, en, slp):
            d.close()
        print("\n  released — coils de-energised.")
        _repark()


def main(argv: list[str]) -> int:
    which = (argv[1].lower() if len(argv) > 1 else "all")
    if which not in ("all", "power", "pins", "burst", "find") and which not in LINES:
        print("usage: stepper_probe.py [all|pins|power|burst|find|%s] [seconds]"
              % "|".join(LINES))
        print("       burst [pulses]   dense STEP train — did the shaft ROTATE?")
        print("       find  [--pins N[,N]]  hunt a mis-wired STEP line, no meter")
        return 2

    # --pins for find mode: an explicit list re-confirms a single suspect quickly.
    only: list[int] = []
    if "--pins" in argv:
        i = argv.index("--pins")
        if i + 1 >= len(argv):
            print("--pins needs a comma-separated list of BCM numbers")
            return 2
        try:
            only = [int(p) for p in argv[i + 1].split(",") if p.strip()]
        except ValueError:
            print("--pins takes BCM numbers, e.g. --pins 12,16")
            return 2
        bad = [p for p in only if p in FIND_SKIP or p not in HEADER_PIN]
        if bad:
            print("refusing %s — %s" % (bad, "in use by this test, or not on the header"))
            return 2

    # pins mode needs only pinctrl, so it runs before the gpiozero import — it is
    # also the mode you want when gpiozero is what you suspect.
    if which == "pins":
        try:
            _pins()
            return 0
        except FileNotFoundError:
            print("pinctrl not found — it ships with Raspberry Pi OS (raspi-utils).")
            return 2
        except subprocess.CalledProcessError as e:
            print("pinctrl failed (%s) — run as a user in the gpio group." % e)
            return 2
        except KeyboardInterrupt:
            print("\ninterrupted.")
            return 1

    try:
        from gpiozero import OutputDevice
    except Exception as e:  # noqa: BLE001
        print("gpiozero unavailable (%s) — see pi5/requirements.txt" % e)
        return 2

    # burst and find both energise on purpose, like power mode, so they run before
    # the "park ~ENABLE high" guard below and return straight after.
    if which in ("burst", "find"):
        try:
            if which == "burst":
                pulses = int(argv[2]) if len(argv) > 2 and argv[2].isdigit() else BURST_PULSES
                _burst(OutputDevice, pulses)
            else:
                _find(OutputDevice, only)
            return 0
        except KeyboardInterrupt:
            print("\ninterrupted — coils released.")
            _repark()
            return 1
        except FileNotFoundError:
            print("pinctrl not found — it ships with Raspberry Pi OS (raspi-utils).")
            return 2
        except Exception as e:  # noqa: BLE001
            print("\ncould not claim the pins (%s) — is run_hardware.py running?" % e)
            return 2

    # power mode owns ~ENABLE (it energises deliberately), so it runs before the
    # "park ~ENABLE high" guard below and returns straight after.
    if which == "power":
        hold_s = float(argv[2]) if len(argv) > 2 else DEFAULT_POWER_HOLD_S
        try:
            _power(OutputDevice, hold_s)
            return 0
        except KeyboardInterrupt:
            print("\ninterrupted — coils released.")
            return 1
        except Exception as e:  # noqa: BLE001
            print("\ncould not claim the pins (%s) — is run_hardware.py running?" % e)
            return 2

    hold_s = float(argv[2]) if len(argv) > 2 else DEFAULT_HOLD_S

    # Park ~ENABLE HIGH (disabled) so the coils stay cold while probing. Skipped
    # when ENABLE is itself the line under test.
    parked = None
    try:
        if which != "enable":
            parked = OutputDevice(25, initial_value=True)
            print("~ENABLE parked HIGH (driver disabled, coils cold).")
    except Exception as e:  # noqa: BLE001
        print("Could not claim GPIO25 (%s). Is run_hardware.py running?" % e)
        print("Stop it first: pkill -f run_hardware.py")
        return 2

    try:
        names = list(LINES) if which == "all" else [which]
        for n in names:
            _probe(OutputDevice, n, hold_s)
        print("\nall done.")
        return 0
    except KeyboardInterrupt:
        print("\ninterrupted.")
        return 1
    except Exception as e:  # noqa: BLE001
        print("\nfailed to claim a pin (%s) — is run_hardware.py running?" % e)
        return 2
    finally:
        if parked is not None:
            parked.close()


if __name__ == "__main__":
    sys.exit(main(sys.argv))
