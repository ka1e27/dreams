"""AM32 ESC passthrough — configure the drive ESCs through the Boat Pico.

⚠ UNTESTED / EXPERIMENTAL. This has not run on hardware yet — it is the first
implementation to iterate on with a Pico + a spare NeutronRC 70A-G071 ESC in the
loop. The PIO one-wire UART timing, the half-duplex turnaround, and the AM32 baud
are the parts most likely to need tuning. See docs/esc_passthrough.md for the
bring-up/validation plan. Do NOT rely on it until the loopback + real-ESC checks
in that doc pass.

⚠ **AM32 only — this will not configure the right ESC.** Since 2026-07-30 the
right-hand ESC is a **BLHeli-32** (FlashHobby FH-70A), which uses a different
one-wire protocol than AM32 and a different (closed-source) configurator. Passing
`esc=1` here bridges the wire, but BLHeliSuite32 is not driven by this path.
Configure the BLHeli side with its own linker/tool — see docs/esc_setup.md.

What it does
------------
The AM32 configurator (am32.ca) talks to an ESC over a **one-wire half-duplex
serial** line on the ESC's signal pin — the USB "linker" is just a USB-serial
adapter on that wire. Those signal wires are already on this Pico — **GP19 = left
ESC, GP20 = right ESC** since 2026-07-30 (they were GP2/GP3; the pins are taken
from `escs.LEFT_PIN`/`escs.RIGHT_PIN`, so this module follows the move
automatically). This module lets the Pi drive that link *through* the Pico, the
same way a flight controller does BLHeli/AM32 passthrough: the Pico repurposes its
USB-CDC as a transparent byte bridge onto the selected ESC's signal wire, so the
configurator (or a CLI probe) running on the Pi can read/write the ESC in place —
no unplugging, no separate linker.

How it's driven
---------------
`serial_handler` handles an ``ESC_PASS,<esc>,<baud>`` command: it ACKs, then flags
``main`` to stop the motors + cancel the async tasks (exactly like REFLASH) and
call :func:`bridge`. From there the USB-CDC is a raw pipe: whatever the Pi sends is
relayed to the ESC one-wire at ``baud``; whatever the ESC replies is relayed back.
The Pi side (``pi5/scripts/esc_passthrough.py``) either pipes am32.ca to it or runs
a scripted probe/baud-scan. The bridge exits (and the Pico resets to normal
firmware) on an escape sequence or an inactivity timeout.

Safety
------
- Only entered from a disarmed/stopped state: the caller drives both ESCs to
  neutral and cancels the motor task before the pin is repurposed.
- An ESC in config/bootloader does not spin the motor, but **props off, out of the
  water** is the rule regardless.
- Exit resets the Pico (`machine.reset()`) so it always comes back up in the known
  normal-firmware state rather than a half-configured one.
"""
import machine
import time

import rp2
from rp2 import PIO, asm_pio

import escs

# Escape sequence the Pi sends to end the bridge (4x 0x00 — never valid mid-frame
# in the AM32 protocol as a run, so it's a safe out-of-band marker).
_ESCAPE = b"\x00\x00\x00\x00"
# If no byte crosses the bridge in either direction for this long, bail out (so a
# crashed/closed host can't strand the Pico in passthrough with motors dead).
_IDLE_TIMEOUT_MS = 20000


# --------------------------------------------------------------------------- #
# PIO one-wire (half-duplex) UART, 8N1. TX and RX are separate state machines on
# the SAME pin; only one runs at a time (so the Pico never captures the echo of
# its own transmission). Programs are the canonical RP2040 pico-examples UART.
# --------------------------------------------------------------------------- #
@asm_pio(sideset_init=PIO.OUT_HIGH, out_init=PIO.OUT_HIGH, out_shiftdir=PIO.SHIFT_RIGHT)
def _uart_tx():
    pull()                      # wait for a byte (line held high = idle/stop)
    set(x, 7).side(0)[7]        # start bit (low), then 8 data bits
    label("bit")
    out(pins, 1)
    jmp(x_dec, "bit")[6]
    nop().side(1)[7]            # stop bit (high)


@asm_pio(in_shiftdir=PIO.SHIFT_RIGHT, fifo_join=PIO.JOIN_RX)
def _uart_rx():
    label("start")
    wait(0, pin, 0)             # wait for the falling edge of a start bit
    set(x, 7)[10]               # delay to the middle of the first data bit
    label("bit")
    in_(pins, 1)
    jmp(x_dec, "bit")[6]
    push(block)                 # push the received byte to the RX FIFO


class HalfDuplexUART:
    """One-wire 8N1 UART on a single GPIO via two PIO state machines.

    ``write()`` drives the pin; ``read()`` releases it to a pull-up input and
    samples the ESC. Direction is switched explicitly around each transfer, so
    the transmitter never records its own echo.
    """

    def __init__(self, gpio, baud, sm_tx=6, sm_rx=7):   # PIO1 SM2/3 — SM0=SBUS, SM4/5=esc_telem
        self._gpio = gpio
        self._baud = int(baud)
        self._pin = machine.Pin(gpio, machine.Pin.IN, machine.Pin.PULL_UP)
        self._tx = rp2.StateMachine(sm_tx, _uart_tx, freq=8 * baud,
                                    out_base=self._pin, sideset_base=self._pin)
        self._rx = rp2.StateMachine(sm_rx, _uart_rx, freq=8 * baud,
                                    in_base=self._pin, jmp_pin=self._pin)
        self._rx.active(1)       # idle listening

    def write(self, data):
        # Take the line: stop RX, drive the pin, clock the bytes out LSB-first
        # (SHIFT_RIGHT UART order — put the raw byte, the program shifts bit 0 first).
        self._rx.active(0)
        self._tx.active(1)
        for b in data:
            self._tx.put(b)
        # Let the last byte (+ start/stop framing, 10 bits) finish before releasing.
        time.sleep_us(len(data) * 10 * 1_000_000 // self._baud + 300)
        self._tx.active(0)
        self._pin.init(machine.Pin.IN, machine.Pin.PULL_UP)
        # Drain any residue the RX FIFO caught during the switch.
        self._rx.active(1)
        self._drain()

    def _drain(self):
        while self._rx.rx_fifo():
            self._rx.get()

    def read(self, timeout_ms):
        """Collect bytes until ``timeout_ms`` passes with the RX FIFO empty."""
        out = bytearray()
        deadline = time.ticks_add(time.ticks_ms(), timeout_ms)
        while time.ticks_diff(deadline, time.ticks_ms()) > 0:
            if self._rx.rx_fifo():
                out.append(self._rx.get() >> 24)   # byte is in the top 8 bits
                deadline = time.ticks_add(time.ticks_ms(), timeout_ms)
        return bytes(out)

    def deinit(self):
        try:
            self._tx.active(0)
            self._rx.active(0)
        except Exception:
            pass


# --------------------------------------------------------------------------- #
# Transparent bridge — repurpose the USB-CDC as a raw pipe to the ESC one-wire.
# --------------------------------------------------------------------------- #
def _esc_gpio(esc_id):
    return escs.LEFT_PIN if int(esc_id) == escs.LEFT else escs.RIGHT_PIN


def bridge(esc_id, baud):
    """Run the passthrough bridge until an escape/idle-timeout, then reset.

    Called by main() after it has stopped the motors and cancelled the async
    tasks. Repurposes stdin/stdout (USB-CDC) to raw and relays bytes to/from the
    selected ESC's one-wire signal line at ``baud``.
    """
    import micropython
    import os
    import select
    import sys

    gpio = _esc_gpio(esc_id)
    uart = HalfDuplexUART(gpio, int(baud))

    # Hardware-watchdog safety net. If ANY part of this bridge hangs — a blocking
    # stdin read (select.poll on the USB-CDC is unreliable on rp2), a PIO stall —
    # the WDT stops being fed and the RP2040 hard-resets back to normal firmware in
    # ~8 s. So the bridge can NEVER permanently strand the Pico (no power-cycle).
    # Fed at the top of the loop, so a hang inside the loop body trips it.
    wdt = machine.WDT(timeout=8000)

    # Make the USB-CDC a raw byte pipe: no REPL, no Ctrl-C interception.
    micropython.kbd_intr(-1)
    try:
        os.dupterm(None)
    except Exception:
        pass

    poll = select.poll()
    poll.register(sys.stdin, select.POLLIN)
    stdin = sys.stdin.buffer
    stdout = sys.stdout.buffer

    esc_tail = bytearray()          # rolling window to spot the escape sequence
    last_activity = time.ticks_ms()

    while True:
        wdt.feed()               # hang anywhere below → WDT not fed → auto-reset
        # Idle-timeout guard so a dead host can't strand us here.
        if time.ticks_diff(time.ticks_ms(), last_activity) > _IDLE_TIMEOUT_MS:
            break

        # PC → ESC: drain everything the host currently has queued and transmit it
        # as one burst (half-duplex: send, then listen). Drain byte-at-a-time under
        # poll() — a fixed stdin.read(64) BLOCKS until 64 bytes arrive, which strands
        # the bridge on any shorter command (and defeats the escape/idle-timeout).
        if poll.poll(5):
            chunk = bytearray()
            while poll.poll(0):
                b = stdin.read(1)
                if not b:
                    break
                chunk += b
            if chunk:
                last_activity = time.ticks_ms()
                esc_tail += chunk
                esc_tail[:] = esc_tail[-len(_ESCAPE):]
                if bytes(esc_tail) == _ESCAPE:
                    break
                uart.write(chunk)
                # ESC → PC: relay the reply (request/response protocol).
                reply = uart.read(timeout_ms=30)
                if reply:
                    stdout.write(reply)

    uart.deinit()
    # Always come back up clean in the normal firmware.
    time.sleep_ms(50)
    machine.reset()
