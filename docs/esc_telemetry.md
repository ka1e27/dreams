# ESC telemetry — per-motor temperature + current (AM32 KISS)

Wires each drive ESC's **telemetry (TX) pad** into the Boat Pico so the dashboard
shows per-motor **temperature** and **current**, and the firmware regains a
**motor-overheat WARN** the VESC used to provide. Built in the same
compiles-now / bench-validate-later spirit as `docs/esc_passthrough.md`.

> ⚠ **UNTESTED — no hardware yet.** The Pi-side pipeline and the KISS parser are
> unit-tested and run end-to-end in the simulator, but the PIO UART RX and the
> AM32 side must be validated on the bench (see *Bring-up* below).

## What it does

- **Temperature** already had an end-to-end path (`TEL` `mt_l/mt_r` → dashboard);
  it now carries real ESC/FET temperature instead of `0`.
- **Current** is new: appended to `TEL` as `curr_l,curr_r` (a backward-compatible
  v1.1 appendix, like the ENV appendix — see `docs/serial-protocol.md §4.1`) and
  shown on both the command center and the React dashboard.
- **Overheat**: `task_watchdog` sends an edge-triggered `ALERT WARN MOTOR_HOT` at
  ≥ 80 °C (`_MOTOR_WARN_C` in `main.py`). WARN only — an auto-ESTOP on overheat
  could strand the boat mid-water; to also cut the motors, add
  `motor_control.estop()` beside that alert. The `MOT` health flag (`< 85 °C`)
  also becomes meaningful automatically.

## Wiring

| ESC pad | Boat Pico | Notes |
|---|---|---|
| **TX** (telemetry) | left → **GP16**, right → **GP19** | hand-tapped header pins, like GP2/3/6/7; change `TELEM_L_PIN`/`TELEM_R_PIN` in `esc_telem.py` |
| **GND** | shared Pico GND | already common for the PWM signal |
| RC (signal) | GP2 / GP3 | unchanged — drives the motor + carries AM32 config |

3.3 V logic (STM32G071), Pico-safe direct, no level shifter. Each ESC has its own
TX — the two lines can't be joined.

## KISS frame (what `esc_telem.py` parses)

10 bytes, 16-bit values big-endian: `temp(°C)`, `voltage(cV)`, `current(cA)`,
`consumption(mAh)`, `eRPM(÷100)`, `CRC-8` (poly 0x07 over bytes 0–8). Standard
(non-inverted) 3.3 V UART, **115200 8N1**.

## Code path

```
ESC TX ─PIO UART RX─> esc_telem.py ─delegates─> escs.get_motor_temp()/get_current()
        (GP16/GP19)   (CRC + parse)             │
                                                ├─ TEL mt_l/mt_r,curr_l,curr_r (main.py)
                                                └─ MOTOR_HOT WARN (task_watchdog)
   → pico_serial (parse "if present") → server TelemetryOut / status dict → both UIs
```

`esc_telem.init()` and a 100 Hz `task_esc_telem()` (drains the RX FIFOs) run from
`main.py`. When no telemetry arrives, the getters return `None`/`0.0` — the old
"dumb ESC" behaviour — so nothing false-trips.

## Design note — why a 32-byte PIO FIFO

Both hardware UARTs are taken (UART1 = GPS+Pod; UART0's free pins collide), so the
RX is bit-banged in PIO like `sbus.py`. But `sbus.py` uses `push_thresh=8` — an
**8-byte** RX FIFO, *smaller than a 10-byte telem frame* — so a frame arriving
between polls overflows and stalls the state machine. `esc_telem.py` packs **4
bytes per FIFO word (`push_thresh=32`) → a 32-byte buffer**, which holds a whole
frame with margin. **The same fix would harden `sbus.py`/RC-override** — worth a
bench check (this is separate from the S3 bit-timing question, which was cleared).

## Bring-up / validation (on the Pi + bench, props off)

Three things this code can't verify without hardware:

1. **Does the AM32 actually emit telemetry in servo-PWM mode?** Enable the
   telemetry / auto-telemetry option in am32.ca (the README lists "KISS telemetry"
   but doesn't document PWM-mode behaviour). If a build only sends telem under
   DShot, this PWM path stays empty. **Check:** watch raw TX bytes — the
   `esc_passthrough` probe or a scope on the TX pad — with a motor spinning.
2. **PIO byte order** out of the 32-bit shift. If the first frames never pass CRC,
   flip `_BYTE_ORDER_LE` in `esc_telem.py`.
3. **Drain cadence.** `esc_telem.stats()` returns `{frames_ok, crc_fail}`; a
   healthy link climbs `frames_ok` with few `crc_fail`. Persistent `crc_fail`
   with `frames_ok == 0` → wrong baud / byte order / no telem (unknown #1).

Steps: flash AM32 ≥ v1.99, enable telemetry, wire TX→GP16/GP19 + common GND →
spin a motor (props off, bench PSU) → confirm `frames_ok` climbs and the dashboard
shows sane temp/current → cross-check current against a clamp meter.

## Status

- Firmware `py_compile`s; Pi tests **164 pass**; ruff clean; KISS parser
  (CRC/scaling/resync/reject) unit-verified; **runs end-to-end in the simulator**
  (synthetic per-motor load → live temp/current on `/api/status`).
- Not yet validated on hardware (the three unknowns above).
