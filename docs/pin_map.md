# Pin Map

Authoritative GPIO / UART / I²C / ADC pin assignments for the **Boat Pico**
and the **Pod Pico**, plus the Pi 5's USB topology.

Source-of-truth for each row:

- Boat Pico — pin-map docstring at the top of `firmware/boat-pico/main.py`,
  with constants drawn from the per-module files (`vesc.py`, `sbus.py`,
  `motor_control.py`, `compass.py`, `gps.py`, `sensors.py`).
- Pod Pico — pin-map docstring in `firmware/pod-pico/main.py`, constants
  from `firmware/pod-pico/sensors.py`, `leak_detect.py`, and
  `uart_responder.py`.
- Pi 5 — physical USB connections only; this project uses **no Pi 5 GPIO**.

> The "Connector" column lists the connector convention used on the build,
> not a value enforced by code. The "Constant" column quotes the *Python
> identifier* you'll find in the firmware (since there is no central
> `firmware/config.py` — pin numbers are colocated with the modules that
> use them).

---

## Boat Pico — RP2040, MicroPython

> ⚠ `GP0` and `GP1` are dead on this Pico module — do not reuse.
> The Pod Pico uses GP0/GP1 fine; this restriction is hardware-specific to
> the Boat Pico module.

> ### ⚠ As-built board divergence (GP12–GP16)
>
> The fabricated `Boat_PCB` wires the two **SHT41** temp/humidity connectors to
> **GP12/GP13 (J11)** and **GP14/GP15 (J13)** — verified from the schematic
> netlist. The firmware's `sensors.py` now matches that. **But three other
> modules still claim those same pins and have NOT been relocated:**
>
> | Pin | As-built board (sensors.py) | Still claimed by | Action needed |
> |---|---|---|---|
> | GP12/GP13 | SHT41 #A (SoftI2C, J11) | `vesc.py` UART0 (VESC) | move VESC off GP12/13 |
> | GP14 | SHT41 #B SDA (J13) | `motor_control.py` winch PWM | move winch |
> | GP15 | SHT41 #B SCL (J13) | `sbus.py` SBUS RC input | move SBUS |
> | GP16 | unused | was DHT11 (not on board) | none — DHT11 removed |
>
> The two SHT41 buses are **bit-banged `SoftI2C`** because hardware I²C0 is
> already held by the BNO085 on GP8/GP9. VESC/winch/SBUS cannot coexist on
> GP12–15 with the temp sensors; relocating them is open work (the board's
> winch connector J8/J9 and an SBUS input pin are themselves unresolved — see
> `docs/session_journal.md`). The rows below show the **board** assignment.

| Pin | Direction | Function | Device | Protocol | Connector | Library | Constant |
|---|---|---|---|---|---|---|---|
| GP0 | — | **DEAD — do not use** | — | — | — | — | — |
| GP1 | — | **DEAD — do not use** | — | — | — | — | — |
| GP4 | TX | UART1 TX (shared GPS+pod bus) | u-blox M10Q GPS / Pod Pico | UART · 9600 8N1 | JST-GH 4-pin (mast trunk) | `machine.UART` | `gps.init` → `UART(1, …, tx=Pin(4))` |
| GP5 | RX | UART1 RX (shared GPS+pod bus) | u-blox M10Q GPS / Pod Pico | UART · 9600 8N1 | JST-GH 4-pin | `machine.UART` | `gps.init` → `UART(1, …, rx=Pin(5))` |
| GP8 | SDA | I²C0 data | BNO085 IMU @ 0x4A | I²C · 400 kHz | JST-SH 4-pin | `machine.I2C` | `compass.init` → `I2C(0, sda=Pin(8))` |
| GP9 | SCL | I²C0 clock | BNO085 IMU @ 0x4A | I²C · 400 kHz | JST-SH 4-pin | `machine.I2C` | `compass.init` → `I2C(0, scl=Pin(9))` |
| GP10 | OUT | Status NeoPixel (WS2812, 1 px) | WS2812 indicator | Single-wire (800 kHz) | 3-pin JST-PH (5 V / GND / DIN) | `neopixel.NeoPixel` | `status_led.PIN` |
| GP12 | SDA | SHT41 #A temp/humidity ⚠ | Sensirion SHT41 @ 0x44 (J11) | SoftI2C bit-bang · 100 kHz | 4-pin (VDD/GND/SDA/SCL) | `machine.SoftI2C` | `sensors.SHT_A_SDA` |
| GP13 | SCL | SHT41 #A temp/humidity ⚠ | Sensirion SHT41 @ 0x44 (J11) | SoftI2C bit-bang · 100 kHz | 4-pin | `machine.SoftI2C` | `sensors.SHT_A_SCL` |
| GP14 | SDA | SHT41 #B temp/humidity ⚠ | Sensirion SHT41 @ 0x44 (J13) | SoftI2C bit-bang · 100 kHz | 4-pin | `machine.SoftI2C` | `sensors.SHT_B_SDA` |
| GP15 | SCL | SHT41 #B temp/humidity ⚠ | Sensirion SHT41 @ 0x44 (J13) | SoftI2C bit-bang · 100 kHz | 4-pin | `machine.SoftI2C` | `sensors.SHT_B_SCL` |
| GP16 | — | **Unused** (was DHT11; not on board) | — | — | — | — | — |
| GP17 | IN (pull-up) | Hull leak switch (port) | Conductive contact | DI · active-low | JST-PH 2-pin | `machine.Pin` | `sensors.init` → `Pin(17, IN, PULL_UP)` |
| GP18 | IN (pull-up) | Hull leak switch (starboard) | Conductive contact | DI · active-low | JST-PH 2-pin | `machine.Pin` | `sensors.init` → `Pin(18, IN, PULL_UP)` |
| GP26 | ADC0 | Propulsion battery sense | 12S LiPo via 3.3 / 47 kΩ divider | Analog · 0–3.3 V | Solder to balance lead | `machine.ADC` | `sensors.init` → `ADC(26)` (`P_RATIO`) |
| GP27 | ADC1 | Electronics battery sense | 3S Li-ion via 15 / 100 kΩ divider | Analog · 0–3.3 V | Solder to balance lead | `machine.ADC` | `sensors.init` → `ADC(27)` (`E_RATIO`) |
| GP28 | ADC2 | **Spare** | — | — | — | — | — |

### Boat Pico — buses summary

| Bus | Owner | Pins | Speed | Notes |
|---|---|---|---|---|
| **UART0** | `vesc.py` | GP12 / GP13 | 115200 8N1 | Master VESC; slave via `COMM_FORWARD_CAN`. ⚠ GP12/13 also wired to SHT41 #A (J11) on the board — must relocate |
| **UART1** | `gps.py` *(shared)* | GP4 / GP5 | 9600 8N1 | GPS + Pod Pico share this bus; main.py's `task_uart1_reader` routes lines by `$GP*` / `$POD` prefix |
| **I²C0** | `compass.py` | GP8 / GP9 | 400 kHz | BNO085 only at 0x4A; bus is otherwise empty |
| **SoftI2C #A** | `sensors.py` | GP12 / GP13 | 100 kHz | SHT41 #A @ 0x44 (J11). Bit-banged (HW I²C0 taken). ⚠ shares pins with UART0/VESC |
| **SoftI2C #B** | `sensors.py` | GP14 / GP15 | 100 kHz | SHT41 #B @ 0x44 (J13). ⚠ shares pins with winch PWM (GP14) / SBUS (GP15) |
| **PIO** | `sbus.py` | GP15 | 100 kbd inv 8E2 | One state machine, 1 / 8 used. ⚠ GP15 also wired to SHT41 #B SCL (J13) |
| **USB CDC** | `serial_handler.py` | (USB) | 115200 | Pi 5 ↔ Boat Pico command + telemetry |

---

## Pod Pico — RP2040, MicroPython

Underwater housing on the winched tether. Talks to the Boat Pico over a
single 9600 baud UART through the slip ring.

| Pin | Direction | Function | Device | Protocol | Connector | Library | Constant |
|---|---|---|---|---|---|---|---|
| GP0 | TX | UART0 TX → Boat Pico | Boat Pico (over slip ring) | UART · 9600 8N1 | Slip-ring conductor | `machine.UART` | `uart_responder.init` → `UART(0, tx=Pin(0))` |
| GP1 | RX | UART0 RX ← Boat Pico | Boat Pico | UART · 9600 8N1 | Slip-ring conductor | `machine.UART` | `uart_responder.init` → `UART(0, rx=Pin(1))` |
| GP17 | OUT | EC drive — pulsed high during read | EC salinity probe (anode) | DO · pulsed 15 ms | JST-PH 2-pin (probe) | `machine.Pin` | `sensors.init` → `Pin(17, OUT)` |
| GP20 | IN (pull-up) | Pod-housing leak sensor | Conductive contact (planned) | DI · active-low | JST-PH 2-pin | `machine.Pin` | `leak_detect.init` |
| GP21 | IN (pull-up) | Bottom-contact microswitch | Bottom contact switch | DI · active-low | JST-PH 2-pin | `machine.Pin` | `sensors.init` → `Pin(21, IN, PULL_UP)` |
| GP22 | ADC | Submersible pressure transducer | Pressure transducer (0.5–4.5 V → 0–15 psi via divider) | Analog · 0–3.3 V | M8 4-pin (sensor) | `machine.ADC` | `sensors.init` → `ADC(22)` |
| GP25 | OUT | Onboard LED (heartbeat) | Pico LED | DO | (onboard) | `machine.Pin` | `main.led = Pin(25, OUT)` |
| GP26 | ADC0 | Water temperature NTC | 10 kΩ NTC, B = 3950 | Analog · 0–3.3 V | JST-PH 2-pin | `machine.ADC` | `sensors.init` → `ADC(26)` |
| GP27 | ADC1 | EC probe sense | EC probe (cathode) via 4.7 kΩ series | Analog · 0–3.3 V | JST-PH 2-pin | `machine.ADC` | `sensors.init` → `ADC(27)` |
| GP28 | ADC2 | Light sensor | Photoresistor + divider | Analog · 0–3.3 V | JST-PH 2-pin | `machine.ADC` | `sensors.init` → `ADC(28)` |

### Pod Pico — buses summary

| Bus | Owner | Pins | Speed | Notes |
|---|---|---|---|---|
| **UART0** | `uart_responder.py` | GP0 / GP1 | 9600 8N1 | Sole link to Boat Pico over the slip ring; `$POLL` → `$POD,…` response |

---

## Raspberry Pi 5 — USB topology (+ one GPIO consumer)

The Pi 5 hangs **every sensor off USB**; the 40-pin header is otherwise a
5 V / 3.3 V / GND tap. The **one exception** is the radar-bar pan stepper (see
below), which is the first and only thing in the project to drive Pi 5 GPIO
directly — a deliberate divergence from the "Pi 5 uses only USB — no GPIO"
locked decision in `CLAUDE.md`, made because the Boat Pico is out of free pins
and the bar is tightly coupled to the camera/vision stack on the Pi 5.

### ⚠ Radar-bar stepper — Pi 5 GPIO (A4988)

Driven from the 40-pin header via **gpiozero/lgpio** (`pi5/cv/stepper.py`,
config in `pi5/config.yaml` → `stepper:`). 1/16 microstepping is fixed in
hardware (A4988 MS1/MS2/MS3 → 3V3). The driver runs in a no-op *mock* mode when
gpiozero/lgpio is absent (laptop / simulator), so this never affects the sim.

| Pi 5 pin (BCM) | Header | A4988 | Polarity / notes |
|---|---|---|---|
| GPIO23 | 16 | STEP | rising-edge pulse, ≥1 µs |
| GPIO24 | 18 | DIR  | set ≥200 ns before STEP |
| GPIO25 | 22 | ENABLE | active-LOW (0 = energised/hold, 1 = freewheel) |
| GPIO8  | 24 | SLEEP  | active-LOW (0 = zero-current sleep, 1 = awake) |
| 3V3 (pin 1/17) | — | VIO | A4988 logic supply |
| GND | — | GND | common with the 3S electronics-pack ground (A4988 VM = 12.6 V) |

> ⚠ Boot-state caveat: GPIO25 (ENABLE) defaults LOW at boot, which would briefly
> *energise* the coils before software runs; GPIO8 (SLEEP, an SPI0 CE pin) has a
> boot pull-up = awake. Harmless for an unloaded radar bar, but consider an
> external pull-up on ENABLE if quiescent current at boot matters.

**Travel ranges (two, kept separate).** `config.yaml → stepper:` distinguishes the
*manual* pan range from the *auto-scan* sweep:

- `manual_min_degrees`/`manual_max_degrees` (default **0–360**) — the range the
  operator can lock the bar to from the command center (◄ LEFT / RIGHT ► jog +
  LOCK-TO angle, `POST /stepper/command` `JOG`/`GOTO`).
- `sweep_min_degrees`/`sweep_max_degrees` (default **0–180**) — the back-and-forth
  range SCAN mode hunts over.

`has_slip_ring` only governs **wrapping** (taking the short way across the 0°/360°
seam), which is the one thing a cable can't survive. With no slip ring (default)
the bar is a **linear axis with hard stops** at `manual_min`/`manual_max` and never
winds more than one turn. ⚠ Even so, the default 0–360 manual range will wind the
radar cable up to a full turn at the far end — drop `manual_max_degrees` to 180 (or
fit a slip ring and set `has_slip_ring: true`) if that's a problem for your cable run.

## Raspberry Pi 5 — USB topology

The Pi 5 in this project uses **no GPIO, UART, I²C, or SPI for sensors** at the
physical-pin level — every device hangs off USB (the radar-bar stepper above is
the sole GPIO consumer). The 40-pin header is otherwise unused except as a
5 V / 3.3 V / GND tap if needed.

| Pi 5 port | Device | Driver / module | Notes |
|---|---|---|---|
| USB-A (1) | Boat Pico | `pi5/comms/pico_serial.py` (CDC ACM, 115200) | Shows up as `/dev/ttyACM0` |
| USB-A (2) | Left USB camera | `pi5/cv/camera.py` (`cv2.VideoCapture(0)`) | 640×480 @ 10 fps |
| USB-A (3) | Right USB camera | `pi5/cv/camera.py` (`cv2.VideoCapture(1)`) | Stereo pair, 120 mm baseline |
| USB-A (4) | SIM7600G-H 4G HAT (or USB-TTL HC-12) | OS-level (`/dev/ttyUSB*`) | Cellular bring-up handled outside this codebase |
| USB-C | Power input — 5 V from logic-domain buck | n/a | Sourced from the 3S Li-ion via the buck array |
| Internal | WiFi (Pi 5 onboard) | OS-level via NetworkManager / `nmcli` | Configured by `pi5/comms/network.py` when `network.mode` is `wifi` or `auto` |

> The boat's actual GPIO/peripheral wiring lives entirely on the Picos.
> If you're looking for "where is GPS connected to the Pi 5?" — it isn't.
> GPS hangs off the Boat Pico's UART1 and is reported up to the Pi 5 over
> the USB CDC link as a serial telemetry frame.
