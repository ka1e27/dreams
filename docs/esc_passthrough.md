# AM32 ESC passthrough (through the Boat Pico)

Configure the drive ESCs (NeutronRC 70A-G071 / AM32) **in place**, through the Pico, without a
separate USB linker or unplugging anything — the way a flight controller does BLHeli/AM32
passthrough. See `docs/esc_setup.md` for *what* to configure; this is *how* to reach the ESCs
through the boat.

> ## ⚠ Status: EXPERIMENTAL — not yet validated on hardware
> This is a first implementation to bring up with a Pico + a spare ESC on the bench. The
> risky parts (PIO one-wire UART timing, half-duplex turnaround, the AM32 signal-line baud) are
> isolated and **must pass the validation steps below before you trust it**. Do the whole
> bring-up **props off, boat out of the water**.

## How it works

The AM32 configurator (`am32.ca`) talks to an ESC over a **one-wire half-duplex serial** line on
the ESC's signal pin — the USB "linker" is just a USB-serial adapter on that wire. Those signal
wires are already on the Pico (GP2 = left ESC, GP3 = right ESC), so the Pico can *become* that
adapter:

```
 am32.ca (Chromium on the Pi)  ──USB──▶  Pico /dev/ttyACM0
                                          │  (bridge mode: CDC ⇄ raw)
                                          ▼
                              PIO half-duplex UART on GP2/GP3
                                          │  one wire, 8N1, @baud
                                          ▼
                                    ESC signal pin (AM32)
```

Flow: the Pi sends `ESC_PASS,<esc>,<baud>`; the Pico ACKs, **stops the motors, cancels all tasks**
(same path as REFLASH), and calls `esc_passthrough.bridge()`, which repurposes the USB-CDC as a
raw pipe onto the selected ESC's one-wire signal at `baud`. From then on the Pico's own
`/dev/ttyACM0` *is* the transparent link to the ESC — so **am32.ca connects straight to
`/dev/ttyACM0`**, no PTY or WebSerial workaround. The bridge exits (and the Pico **resets** to
normal firmware) on a 4×`0x00` escape or ~20 s of inactivity.

Files:
- `firmware/boat-pico/esc_passthrough.py` — PIO one-wire UART + the transparent bridge.
- `firmware/boat-pico/serial_handler.py` — the `ESC_PASS` command.
- `firmware/boat-pico/main.py` — enters the bridge when flagged.
- `pi5/scripts/esc_passthrough.py` — the Pi-side driver (`enter` / `probe` / `scan`).

## Safety

- The bridge is only entered *after* both ESCs are driven to neutral and the motor task is
  cancelled; the Pi tool also sends `ESTOP` first.
- An ESC in config/bootloader doesn't spin — but **props off, out of the water** regardless.
- Exit always `machine.reset()`s the Pico, so it can never linger half-configured with dead motors.
- Stop the boat stack before using this (it holds `/dev/ttyACM0`): kill `run_hardware.py`.

## Bring-up / validation plan (do these in order)

**1. PIO one-wire UART loopback (no ESC).** Prove the UART before involving an ESC. Jumper GP2 to
a spare hardware-UART RX pin and cross-check both directions from the REPL:

```python
# On the Pico REPL, props disconnected:
from esc_passthrough import HalfDuplexUART
from machine import UART, Pin
hd = HalfDuplexUART(2, 19200)          # passthrough pin
u  = UART(1, baudrate=19200, tx=Pin(8), rx=Pin(9))   # reference UART; jumper GP2<->GP9 for RX, GP2<->GP8 for TX
hd.write(b"AT\r"); print(u.read())     # expect b'AT\r'  -> TX works
u.write(b"OK\r");  print(hd.read(200)) # expect b'OK\r'  -> RX works
```

If bytes are garbled, the fix is almost always the RX mid-bit delay (`[10]` in `_uart_rx`) or the
TX inter-byte timing in `write()` — tune those first. This step needs no ESC and is fully on you +
me to iterate.

**2. Find the baud + confirm the ESC link.** Wire GP2/GP3 to the ESC signal (a series ~1 kΩ on the
signal line avoids bus contention), power the ESC from its battery, boat stack stopped:

```bash
python -m pi5.scripts.esc_passthrough scan --esc left --hex 2f
```

It sweeps candidate bauds and reports which produce a reply. Any consistent reply = the one-wire
link works and tells us the baud. (The AM32 signal-line baud isn't publicly documented — this is
how we pin it down.)

**3. Probe with real AM32 bytes.** Once a baud responds, send an actual AM32 init/EEPROM-read and
inspect the raw reply:

```bash
python -m pi5.scripts.esc_passthrough probe --esc left --baud <found> --hex <am32-init>
```

**4. The real workflow — am32.ca.** Arm the bridge and drive it from the configurator:

```bash
python -m pi5.scripts.esc_passthrough enter --esc left --baud <found>
```

Then open `am32.ca` in Chromium **on the Pi**, Port Select `/dev/ttyACM0`, Connect, Read. If it
reads settings, the passthrough works end-to-end. Configure per `docs/esc_setup.md`, Save.
Disconnect when done (the Pico resets itself). Repeat for the right ESC.

## Known risks / things we'll likely tune on the bench

- **PIO UART timing** — the RX mid-bit sample delay and TX turnaround are the usual suspects.
- **Half-duplex turnaround** — the bridge sends a PC burst then listens for 30 ms; a slow or very
  fast ESC reply may need that window widened/narrowed (`uart.read` timeout in `bridge()`).
- **One-wire contention** — without a series resistor on the signal line, Pico↔ESC drive fights
  can corrupt bytes; add ~1 kΩ.
- **Baud** — parameterised precisely because it's unconfirmed; `scan` resolves it.
- **am32.ca + reset entry** — some configurators pulse the line to enter the bootloader; if am32.ca
  can't get the ESC into config, we may need to add a bootloader-entry sequence to the bridge.

If any step stalls, that's the iterate-on-hardware loop: I adjust the firmware/tool, you reflash
(`mpremote`) and re-run the step.
