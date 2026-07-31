"""Drive ESCs — two standard hobby ESCs on 50 Hz servo PWM (single-hull test bench).

Test-bench variant of the propulsion driver. Replaces the VESC / CAN-chain
propulsion (`vesc.py`, unused on this branch) with two dumb hobby ESCs — one per
stern motor — driven directly by the Pico as 50 Hz servo-style PWM, the same
signal the winch ESC already uses. Differential steering is computed upstream in
`motor_control.py` exactly as before; this module only turns a -1.0..+1.0 duty
into an ESC pulse and drives the pin.

Pins (2026-07-30 — moved off GP2/GP3, which the board does not free):
  - Left  ESC  → GP19  [J16, ex-"Hull Leak Left",  PWM slice 1 ch B]
  - Right ESC  → GP20  [J15, ex-"Hull Leak Right", PWM slice 2 ch A]

**These were the two hull-leak connectors.** On `Boat_PCB V2` the MCP2515 CAN
interface owns GP2/3/4/6/7, so the old GP2/GP3 drive-ESC assignment collided with
the board and had no connector behind it — the bench tapped the Pico header
directly. J16/J15 are JST-XH 2-pin wired **pin 1 = GND, pin 2 = signal**, which is
exactly an ESC servo signal lead, so propulsion now lands on real connectors.

⚠ **Hull leak sensing is gone.** `sensors.py` no longer configures GP19/GP20 —
it must not, since driving them as pull-up inputs would fight this module's PWM
(`sensors.init()` runs *after* `motor_control.init()`). The remaining leak sensor
is the pod's (`pod_uart.leak_detected`), which still alerts and still drives the
CRIT LED state. `sensors.hull_status()` now reports `--` (no sensor) rather than
claiming `DRY`.

PWM slices: GP19 is slice 1B (free once GP2/GP3 are released) and GP20 is slice
2A, sharing slice 2 with the winch on GP21 (2B). Same-slice channels share a
frequency but keep independent duty, and both want 50 Hz — so that is fine.

Test-bench ESCs — **two different ESCs on two different motors**:

  LEFT   GP19/J16  NeutronRC 70A-G071  (STM32G071, **AM32**, 2-8S)
                   → Badass 2814-1560kv
  RIGHT  GP20/J15  FlashHobby FH-70A   (**BLHeli-32**)
                   → Badass 2320-1630kv

Both take the same 1.0/1.5/2.0 ms 50 Hz servo signal, so this module drives them
identically — but their *configuration* differs, and both must be set up before
first spin-up (docs/esc_setup.md):
  - AM32 calls reverse **"Bi-directional"**; BLHeli-32 calls it **"3D mode"**.
    Both must be ON or a <1.5 ms pulse just idles and the boat cannot pivot in
    place or reverse to bear away.
  - BLHeli-32 additionally wants its throttle range calibrated to 1000-2000 µs,
    and "Motor Direction" set so positive duty drives the hull *forward* — the
    two ESC families do not agree on default spin direction.

Kv mismatch (1630 vs 1560 kv, ~4.5 %) is trimmed in `motor_control.COMP_R`, not
here: this module stays a pure duty→pulse mapper.

⚠ Safety: the ESC holds the last pulse if commands stop (AM32's own signal-loss
  behaviour aside). The primary safety net is the Pico's heartbeat watchdog
  (watchdog.py, 3 s) → motor_control.estop() → this module drives both ESCs back
  to neutral.

Servo-PWM pulse range (shared with the winch ESC), with AM32 bidirectional mode:
  1.0 ms = full reverse, 1.5 ms = neutral/stop, 2.0 ms = full forward, at 50 Hz.
⚠ That mapping is **only valid in bi-directional / 3D mode**. In stock normal mode
  the same 1.5 ms is ~50 % throttle, so "neutral" — and therefore ESTOP, the
  watchdog and every other stop this firmware can express — *accelerates* the
  motor. This is not theoretical: it happened on the bench on 2026-07-31.
  `BIDIR_CONFIRMED` below is the gate that now blocks arming until both ESCs are
  confirmed; see it, and docs/esc_setup.md, before first spin-up.

Note: GP0/GP1 are dead — do not use.
"""
from machine import Pin, PWM

import esc_telem

# Motor IDs — kept identical to vesc.py so motor_control.py stays a drop-in.
LEFT = 0
RIGHT = 1

# ESC signal pins — the ex-hull-leak connectors. See the module docstring: these
# are real board connectors (J16/J15, pin 1 = GND, pin 2 = signal), unlike the
# GP2/GP3 they replaced, which the MCP2515 owns on Boat_PCB V2.
LEFT_PIN = 19    # J16 — AM32 NeutronRC 70A  → 2814-1560kv
RIGHT_PIN = 20   # J15 — BLHeli-32 FH-70A    → 2320-1630kv

# 50 Hz servo PWM in the duty_u16 domain (same mapping as the winch ESC in
# motor_control.py). 65535 counts per 20 ms period → ~3.277 counts / µs.
STOP_PWM = 4915                 # ~1.5 ms neutral
MIN_PWM = 3277                  # ~1.0 ms full reverse
MAX_PWM = 6553                  # ~2.0 ms full forward
FWD_RANGE = MAX_PWM - STOP_PWM  # 1638
REV_RANGE = STOP_PWM - MIN_PWM  # 1638

# ---- Bi-directional (3D) mode gate -----------------------------------------
# ⚠ SAFETY GATE, NOT A PREFERENCE. Leave these False until you have opened the
# ESC's config tool and *seen* the setting.
#
# This module maps duty 0.0 to a 1.5 ms pulse and calls it "neutral". That is
# only true for an ESC in bi-directional / 3D mode. An ESC in stock **normal**
# mode reads the very same 1.5 ms as **~50 % throttle**, so for it:
#
#   * 1.5 ms at power-up  -> "throttle high" -> it refuses to arm (looks dead), and
#   * every "stop" this firmware can express -- neutral, stop(), and the whole
#     ESTOP / watchdog / heartbeat-loss kill path -- commands **half throttle**.
#
# There is no pulse width that means "stop" to both kinds at once: 1.5 ms stops a
# 3D ESC but is 50 % to a normal one, while 1.0 ms stops a normal one but is
# **full reverse** to a 3D one. So a mixed pair has no safe state at all, and the
# gate is all-or-nothing by design (see bidir_ok()).
#
# MEASURED 2026-07-31, which is why this exists. During a bench sweep the RIGHT
# ESC (BLHeli-32) sat inert while the pulse stayed above 1.0 ms, **armed** the
# moment a -100 command produced 1.000 ms (its throttle zero), and then ran on at
# ~50 % when the sweep returned to 1.5 ms "neutral" -- and kept running through
# SET_THR 0,0 *and* through ESTOP, because both of those are that same 1.5 ms.
# Only an explicit -100 (1.000 ms) stopped it. The LEFT ESC (AM32) was correctly
# bi-directional throughout and behaved as this module assumes.
#
# LEFT  is left False despite that good behaviour: it is strong evidence, not the
#       confirmation this gate asks for. Flip it once you have read the setting.
# RIGHT is False because it is known-wrong -- see docs/esc_setup.md to fix it
#       (BLHeli-32 "3D mode" + throttle range calibrated to 1000-2000 us; stock
#       BLHeli_S has no 3D mode at all and needs a Bluejay reflash).
BIDIR_CONFIRMED = {
    LEFT: False,    # AM32 NeutronRC 70A-G071   -- "Bi-Directional"
    RIGHT: False,   # BLHeli-32 FlashHobby FH-70A -- "3D mode"
}

_NAMES = {LEFT: "LEFT/AM32", RIGHT: "RIGHT/BLHeli32"}

# PWM handles per motor
_pwm = {LEFT: None, RIGHT: None}


def bidir_ok():
    """True iff EVERY drive ESC is confirmed bi-directional.

    All-or-nothing on purpose: a mixed pair has no pulse width that stops both,
    so one unconfirmed ESC makes the whole drive train unsafe, not just its own.
    """
    return all(BIDIR_CONFIRMED.values())


def unconfirmed():
    """Names of the ESCs still not confirmed bi-directional (for banners/alerts)."""
    return [_NAMES[m] for m in (LEFT, RIGHT) if not BIDIR_CONFIRMED[m]]


def init():
    """Create both ESC PWM channels at 50 Hz and arm them at neutral.

    Returns True only if BOTH channels initialised. A False return means at
    least one ESC has no PWM handle, so set_duty()/stop() — including the ESTOP
    kill path — cannot drive it. The caller must surface that (and not arm),
    since a dumb ESC has no self-timeout to fall back on.
    """
    global _pwm
    for mid, pin in ((LEFT, LEFT_PIN), (RIGHT, RIGHT_PIN)):
        try:
            p = PWM(Pin(pin))
            p.freq(50)
            _pwm[mid] = p
        except Exception as e:
            print("escs init error (motor %d): %s" % (mid, e))
            _pwm[mid] = None
    # Send neutral so the ESCs arm on a valid stop pulse immediately.
    set_duty(LEFT, 0.0)
    set_duty(RIGHT, 0.0)
    return ready()


def ready():
    """True iff both ESC PWM channels are live (i.e. the kill path can drive them)."""
    return _pwm[LEFT] is not None and _pwm[RIGHT] is not None


def _duty_to_pwm(duty):
    """Map duty -1.0..+1.0 to an ESC pulse in the duty_u16 domain."""
    if duty > 1.0:
        duty = 1.0
    elif duty < -1.0:
        duty = -1.0
    if duty >= 0:
        return STOP_PWM + int(FWD_RANGE * duty)
    return STOP_PWM + int(REV_RANGE * duty)


def set_duty(motor_id, duty):
    """Drive one ESC. `duty` in -1.0..+1.0 (positive = forward).

    Hard-floored by the bi-directional gate: while any ESC is unconfirmed this
    emits **only** the 1.5 ms neutral pulse, whatever it was asked for. Holding
    1.5 ms is what keeps a normal-mode ESC *inert* — that pulse reads as ~50 %
    throttle to it, so it refuses to arm and never spins. The thing we must
    never emit is its arming pulse (1.000 ms, i.e. duty -1.0); reaching that is
    exactly what armed the BLHeli-32 on 2026-07-31 and left it running.

    Deliberately enforced at the lowest level rather than only in
    motor_control.set_throttle(), so no future caller — SBUS, a mission, a REPL
    poke — can route around it.
    """
    p = _pwm.get(motor_id)
    if p is None:
        return
    if not bidir_ok():
        duty = 0.0
    try:
        p.duty_u16(_duty_to_pwm(duty))
    except:
        pass


def stop():
    """Neutral both ESCs immediately."""
    set_duty(LEFT, 0.0)
    set_duty(RIGHT, 0.0)


# ---- Telemetry -------------------------------------------------------------
# AM32 ESCs emit KISS telemetry on their TX pad; esc_telem.py receives it (PIO
# UART RX) and these accessors delegate to it, so main.py's VESC-shaped telemetry
# / watchdog / health-string / LED code lights up unchanged. When no telemetry is
# wired or arriving, the getters return None / 0.0 (the old "dumb ESC" behaviour),
# so nothing false-trips. esc_telem.init() / poll() are driven from main.py.

def get_motor_temp(motor_id):
    """ESC/FET temperature (°C) from KISS telemetry, or None if none fresh."""
    return esc_telem.temperature(motor_id)


def get_fet_temp(motor_id):
    # KISS telemetry reports a single temperature; expose it as both.
    return esc_telem.temperature(motor_id)


def get_current(motor_id):
    """Motor current (A) from KISS telemetry, or None if none fresh."""
    return esc_telem.current(motor_id)


def get_v_in(motor_id):
    """ESC-sensed rail voltage (V) from KISS telemetry, or None if none fresh."""
    return esc_telem.voltage(motor_id)


def get_fault(motor_id):
    # KISS telemetry carries no discrete fault code; 0 = no fault reported.
    return 0


def max_motor_temp():
    """Hottest fresh ESC temperature, or 0.0 when no telemetry (never trips)."""
    return esc_telem.max_temp()


def is_telemetry_fresh(motor_id, max_age_ms=2000):
    return esc_telem.is_fresh(motor_id, max_age_ms)


def poll_rx():
    """Drain the telemetry RX FIFOs (delegates to esc_telem.poll())."""
    esc_telem.poll()


def request_values(motor_id):
    """No-op: KISS telemetry is streamed by the ESC, not requested."""
    pass


def request_values_round_robin():
    """No-op: KISS telemetry is streamed by the ESC, not requested."""
    pass
