# Configuring AM32 ESCs from the Pi — `am32_config.py`

`pi5/scripts/am32_config.py` reads and changes AM32 ESC settings (bi-directional,
telemetry, LVC, direction) **directly from the Raspberry Pi**, over the Pi's GPIO
UART — no `am32.ca` browser, no USB-TTL linker, no flight controller.

It speaks the AM32 one-wire bootloader protocol (transcribed from
`am32-firmware/AM32-bootloader`, `bootloader/main.c`: 19200 8N1, CRC-16 poly
`0xA001`, `SET_ADDRESS`/`READ_FLASH`/`SET_BUFFER`/`PROG_FLASH`). It configures
**settings only** — it does not flash firmware (that still needs am32.ca + an
adapter, or an ST-Link).

> **Why not am32.ca?** On this Pi, Chromium's Web Serial only lists **USB** serial
> devices, so it never offers the Pi's GPIO UART (`/dev/ttyAMA0`). A USB-TTL
> adapter would work in am32.ca (it's USB), but this tool avoids needing one.

## Wiring (one-wire half-duplex → the Pi's 2-wire UART)

```
ESC signal ─────────────┬──────────── Pi pin 10  (GPIO15 / RXD0)   direct
                        └──[ ~1 kΩ ]── Pi pin 8   (GPIO14 / TXD0)   via resistor
ESC GND  ────────────────────────────  Pi pin 6   (GND)
```
- 3.3 V both sides — **no level shifter.**
- Use the ESC's **signal** pad (normally on Pico **GP2**). Move it to the Pi for
  config, then back to GP2 after. **Props off.** 470 Ω–2.2 kΩ all work for the resistor.

## One-time Pi 5 setup (pins 8/10 aren't a UART by default)

```bash
sudo dtoverlay uart0                                   # enable uart0 on GPIO14/15 -> /dev/ttyAMA0
sudo systemctl stop serial-getty@ttyAMA10.service      # free the port from the login console
sudo chown root:dialout /dev/ttyAMA0 && sudo chmod 660 /dev/ttyAMA0
```
Runtime-only (reverts on reboot). To persist: add `dtoverlay=uart0` to
`/boot/firmware/config.txt` and disable the serial console via `raspi-config`.

## Usage

```bash
python -m pi5.scripts.am32_config read
python -m pi5.scripts.am32_config set --bidir on --telemetry on
python -m pi5.scripts.am32_config set --lvc 3.0          # 3.0 V/cell cutoff (for the boat's M18 rail)
python -m pi5.scripts.am32_config set --lvc off          # bench on 4S
```
`set` is read-modify-write: only the flags you pass change; everything else
(name, motor timing, KV, boot flag) is preserved and the result is read back and
verified. It refuses to write if the boot byte isn't `0x01` (safety).

## Status (2026-07-26)

- **Read + write proven on hardware** — read a NeutronRC 70A-G071 (64K, flash code
  `0x35`), wrote `bidirectional` + `telemetry 30ms` ON, verified by read-back.
- **Telemetry not yet confirmed flowing** on the boat side. The AM32 G071 emits
  serial telemetry on the **MCU's PB6** (USART1, 115200 8N1, open-drain + pull-up),
  and the transmit lives in the commutation path — so it likely only streams while
  a **motor is spinning**. Bench test to finish: motor connected (props off), a
  little throttle, then watch `esc_telem` `frames_ok` on the Pico climb and TEL
  `mt_l`/`curr_l` go live. Also verify the wire on Pico **GP16** is on the ESC's
  actual **telemetry** pad (the one routed to PB6), not the signal/RX pad.

See also `docs/esc_setup.md` (settings reference) and `docs/esc_telemetry.md`
(the Pico-side receiver on GP16/GP19).
