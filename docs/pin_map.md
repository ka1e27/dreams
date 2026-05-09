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

| Pin | Direction | Function | Device | Protocol | Connector | Library | Constant |
|---|---|---|---|---|---|---|---|
| GP0 | — | **DEAD — do not use** | — | — | — | — | — |
| GP1 | — | **DEAD — do not use** | — | — | — | — | — |
| GP4 | TX | UART1 TX (shared GPS+pod bus) | u-blox M10Q GPS / Pod Pico | UART · 9600 8N1 | JST-GH 4-pin (mast trunk) | `machine.UART` | `gps.init` → `UART(1, …, tx=Pin(4))` |
| GP5 | RX | UART1 RX (shared GPS+pod bus) | u-blox M10Q GPS / Pod Pico | UART · 9600 8N1 | JST-GH 4-pin | `machine.UART` | `gps.init` → `UART(1, …, rx=Pin(5))` |
| GP8 | SDA | I²C0 data | BNO085 IMU @ 0x4A | I²C · 400 kHz | JST-SH 4-pin | `machine.I2C` | `compass.init` → `I2C(0, sda=Pin(8))` |
| GP9 | SCL | I²C0 clock | BNO085 IMU @ 0x4A | I²C · 400 kHz | JST-SH 4-pin | `machine.I2C` | `compass.init` → `I2C(0, scl=Pin(9))` |
| GP12 | TX | UART0 TX → VESC master | VESC master (CAN-forwards to slave) | UART · 115200 8N1 | JST-PH 4-pin (VESC standard) | `machine.UART` | `vesc._TX_PIN` |
| GP13 | RX | UART0 RX ← VESC master | VESC master | UART · 115200 8N1 | JST-PH 4-pin | `machine.UART` | `vesc._RX_PIN` |
| GP14 | OUT | Winch ESC PWM | Winch ESC (hobby) | PWM · 50 Hz · 1–2 ms pulse | 3-pin servo header | `machine.PWM` | `motor_control.MW_PIN` |
| GP15 | IN  | SBUS receiver | SBUS RC RX (FrSky / Radiomaster) | Inverted UART · 100 kbd 8E2 (PIO) | 3-pin servo header | `rp2.PIO` / `rp2.StateMachine` | `sbus.SBUS_PIN` |
| GP16 | I/O | DHT11 1-wire | DHT11 air temp / humidity | 1-wire | Dupont 4-pin | `dht.DHT11` | `sensors.init` → `dht.DHT11(Pin(16))` |
| GP17 | IN (pull-up) | Hull leak switch (port) | Conductive contact | DI · active-low | JST-PH 2-pin | `machine.Pin` | `sensors.init` → `Pin(17, IN, PULL_UP)` |
| GP18 | IN (pull-up) | Hull leak switch (starboard) | Conductive contact | DI · active-low | JST-PH 2-pin | `machine.Pin` | `sensors.init` → `Pin(18, IN, PULL_UP)` |
| GP26 | ADC0 | Propulsion battery sense | 12S LiPo via 3.3 / 47 kΩ divider | Analog · 0–3.3 V | Solder to balance lead | `machine.ADC` | `sensors.init` → `ADC(26)` (`P_RATIO`) |
| GP27 | ADC1 | Electronics battery sense | 3S Li-ion via 15 / 100 kΩ divider | Analog · 0–3.3 V | Solder to balance lead | `machine.ADC` | `sensors.init` → `ADC(27)` (`E_RATIO`) |
| GP28 | ADC2 | **Spare** | — | — | — | — | — |

### Boat Pico — buses summary

| Bus | Owner | Pins | Speed | Notes |
|---|---|---|---|---|
| **UART0** | `vesc.py` | GP12 / GP13 | 115200 8N1 | Master VESC; slave reached via `COMM_FORWARD_CAN` |
| **UART1** | `gps.py` *(shared)* | GP4 / GP5 | 9600 8N1 | GPS + Pod Pico share this bus; main.py's `task_uart1_reader` routes lines by `$GP*` / `$POD` prefix |
| **I²C0** | `compass.py` | GP8 / GP9 | 400 kHz | BNO085 only at 0x4A; bus is otherwise empty |
| **PIO** | `sbus.py` | GP15 | 100 kbd inv 8E2 | One state machine, 1 / 8 used |
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

## Raspberry Pi 5 — USB topology only

The Pi 5 in this project uses **no GPIO, UART, I²C, or SPI** at the
physical-pin level — every device hangs off USB. The 40-pin header is
unused except as a 5 V / 3.3 V / GND tap if needed.

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
