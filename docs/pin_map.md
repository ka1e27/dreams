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
- Pi 5 — USB topology, plus the **radar-bar stepper on the 40-pin header** (the
  project's one Pi GPIO consumer — see that section below).
- Board wiring — verified against the KiCad netlist of `Boat_PCB/Boat_PCB.kicad_pcb`
  (silkscreen `Boat_PCB V2`), cross-checked with `kicad-cli sch export netlist`.

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

> ### ⚠ As-built board divergence — read before wiring anything
>
> The old GP12–GP15 collision is **resolved**: the drive ESCs, winch and SBUS moved
> off the temp-sensor pins to GP2/GP3/GP6/GP7, and `sensors.py` matches the board's
> SHT41 connectors (J11 on GP12/13, J13 on GP14/15).
>
> **But the pins they moved *to* are not free on the V2 board.** `Boat_PCB V2` fits an
> **MCP2515 + TJA1051 CAN interface** (U1/U2, for the VESC architecture) which owns
> GP2, GP3, GP4, GP6 and GP7. This branch's firmware is the *test-bench* variant that
> assumes no CAN. The two cannot coexist:
>
> | Pin | This branch's firmware | V2 board wires it to | Verdict |
> |---|---|---|---|
> | GP2 | Left drive ESC PWM (`escs.LEFT_PIN`) | U1.13 — MCP2515 `SCK` | **conflict** |
> | GP3 | Right drive ESC PWM (`escs.RIGHT_PIN`) | U1.14 — MCP2515 `SI` (MOSI) | **conflict** |
> | GP4 | UART1 TX (GPS + Pod) | U1.15 — MCP2515 `SO` (MISO) | **conflict** — two outputs fight |
> | GP5 | UART1 RX (GPS + Pod) | **GND** (tied to ground) | **conflict** — GPS RX reads 0 |
> | GP6 | Winch ESC PWM (`motor_control.MW_PIN`) | U1.12 — MCP2515 `~INT` | **conflict** (board winch is GP21) |
> | GP7 | SBUS RC input (`sbus.SBUS_PIN`) | U1.17 — MCP2515 `~RESET` + R11 10 k pull-up | **conflict** |
> | GP11 | Right ESC telemetry RX (`esc_telem.TELEM_R_PIN`) | *unconnected* | ✅ no clash — **not routed to a connector**, solder to the Pico pin |
> | GP16 | Left ESC telemetry RX (`esc_telem.TELEM_L_PIN`) | *unconnected* | ✅ no clash — same, solder direct |
> | GP19 | Hull leak left (`sensors.init`) | J16.2 — "Hull Leak Left" | ✅ matches the board |
> | GP20 | Hull leak right (`sensors.init`) | J15.2 — "Hull Leak Right" | ✅ matches the board |
>
> **The GPS has no UART on this board.** J7 carries only I²C pairs (GP8/9 and GP14/15)
> plus power; `gps.py` is UART/NMEA on GP4/GP5, and GP5 is grounded.
>
> **Hull leak and ESC telemetry were realigned on 2026-07-28.** Leak sensing moved
> GP17/GP18 → **GP19/GP20** so it reads the board's real J16/J15 connectors (GP17/GP18
> are the BNO085's RST/INT on J5), and right-ESC telemetry moved GP19 → **GP11**. GP11
> and GP16 are the only two unconnected pins on V2, so both telemetry taps are now
> clash-free and all four inputs fit. GP0/GP1 are dead and every other pin is committed,
> so **there is no free pin left** to relieve the GP2/3/4/6/7 CAN conflict above.
>
> The two SHT41 buses are **bit-banged `SoftI2C`** because hardware I²C0 is already
> held by the BNO085 on GP8/GP9. The `Board (V2)` column below is the **verified
> netlist**; the `Firmware` column is what this branch's code actually drives.

| Pin | Dir | Function (firmware) | Device · Protocol | Board (V2) — verified netlist | Constant |
|---|---|---|---|---|---|
| GP0 | — | **DEAD — do not use** | — | unconnected | — |
| GP1 | — | **DEAD — do not use** | — | unconnected | — |
| GP2 | OUT | Left drive ESC | AM32 ESC · 50 Hz servo PWM | ⚠ U1.13 — MCP2515 `SCK` | `escs.LEFT_PIN` |
| GP3 | OUT | Right drive ESC | AM32 ESC · 50 Hz servo PWM | ⚠ U1.14 — MCP2515 `SI` | `escs.RIGHT_PIN` |
| GP4 | TX | UART1 TX (shared GPS+pod bus) | u-blox M10Q / Pod Pico · 9600 8N1 | ⚠ U1.15 — MCP2515 `SO` | `gps.init` → `UART(1, …, tx=Pin(4))` |
| GP5 | RX | UART1 RX (shared GPS+pod bus) | u-blox M10Q / Pod Pico · 9600 8N1 | ⚠ **tied to GND** | `gps.init` → `UART(1, …, rx=Pin(5))` |
| GP6 | OUT | Winch ESC | Winch ESC · 50 Hz servo PWM | ⚠ U1.12 — MCP2515 `~INT` | `motor_control.MW_PIN` |
| GP7 | IN | SBUS RC receiver (PIO) | SBUS · 100 kbd inv 8E2 | ⚠ U1.17 — MCP2515 `~RESET` + R11 10 k pull-up | `sbus.SBUS_PIN` |
| GP8 | SDA | I²C0 data | BNO085 IMU @ 0x4A · 400 kHz | **J7.4** — GPS+Compass, 6-pin JST-XH | `compass.init` → `I2C(0, sda=Pin(8))` |
| GP9 | SCL | I²C0 clock | BNO085 IMU @ 0x4A · 400 kHz | **J7.3** | `compass.init` → `I2C(0, scl=Pin(9))` |
| GP10 | OUT | Status NeoPixel (WS2812, 1 px) | WS2812 · single-wire 800 kHz | **J12.2** — 3-pin JST-XH (pin 3 = VSYS **5 V**) | `status_led.PIN` |
| GP11 | IN | Right ESC telemetry RX | AM32 KISS · PIO UART 115200 | unconnected — **not routed to any connector** | `esc_telem.TELEM_R_PIN` |
| GP12 | SDA | SHT41 #A temp/humidity | SHT41 @ 0x44 · SoftI2C 100 kHz | **J11.1** — 4-pin JST-XH, external | `sensors.SHT_A_SDA` |
| GP13 | SCL | SHT41 #A temp/humidity | SHT41 @ 0x44 · SoftI2C 100 kHz | **J11.2** | `sensors.SHT_A_SCL` |
| GP14 | SDA | SHT41 #B temp/humidity | SHT41 @ 0x44 · SoftI2C 100 kHz | **J13.1** (internal) + J5.4 + J7.1 — 3 devices | `sensors.SHT_B_SDA` |
| GP15 | SCL | SHT41 #B temp/humidity | SHT41 @ 0x44 · SoftI2C 100 kHz | **J13.2** + J5.3 + J7.2 | `sensors.SHT_B_SCL` |
| GP16 | IN | Left ESC telemetry RX | AM32 KISS · PIO UART 115200 | unconnected — **not routed to any connector** | `esc_telem.TELEM_L_PIN` |
| GP17 | — | *unused by firmware* | — | **J5.7** — BNO085 `RST` | — |
| GP18 | — | *unused by firmware* | — | **J5.8** — BNO085 `INT` | — |
| GP19 | IN (pull-up) | Hull leak switch (port) | Conductive contact · active-low | **J16.2** — "Hull Leak Left", 2-pin JST-XH | `sensors.init` → `Pin(19, IN, PULL_UP)` |
| GP20 | IN (pull-up) | Hull leak switch (starboard) | Conductive contact · active-low | **J15.2** — "Hull Leak Right", 2-pin JST-XH | `sensors.init` → `Pin(20, IN, PULL_UP)` |
| GP21 | — | *unused by firmware* | — | **J8.1 + J9.1** — Winch ESC signal (both in parallel) | — |
| GP22 | — | *unused by firmware* | — | **J1.12** — 5 V buck `PG` (open-drain) + R1 10 k → A4988 VDD/MS1 | — |
| GP26 | ADC0 | Drive battery sense | 2× M18 parallel · analog 0–3.3 V | **J4** "12s Tap" → R2/R4 = **×17.92** | `ADC(26)`, `INV_P_RATIO` = 14.0 ⚠ |
| GP27 | ADC1 | Electronics battery sense | 1× M18 · analog 0–3.3 V | **BT1** "3s" → R5/R6 = **×4.33** | `ADC(27)`, `INV_E_RATIO` = 6.6 ⚠ |
| GP28 | ADC2 | Winch battery sense | 1× M18 · analog 0–3.3 V | **BT4** "4s" → R8/R10 = **×6.56** | `ADC(28)`, `INV_W_RATIO` = 6.6 ✓ |

### ⚠ Battery dividers — board does not match firmware

The board still carries the pre-M18 divider values. `sensors.py` scales by `INV_*_RATIO`,
so every mismatch is a direct voltage-reading error:

| Rail | Board as-built | Actual ratio | Firmware expects | Reading error |
|---|---|---|---|---|
| Drive → GP26 | R2 220 k / R4 13 k | ×17.92 | ×14.0 | reads **78 % of true** — a 21 V pack shows 16.4 V, below `P_WARN` |
| Electronics → GP27 | R5 100 k / R6 30 k | ×4.33 | ×6.6 | reads **1.52× high** — never warns on a dying pack |
| Winch → GP28 | R8 100 k / R10 18 k | ×6.56 | ×6.6 | 0.7 % — fine |

**GP27 is also over-range.** R5/R6 were sized for a 3S LiPo (12.6 V → 2.91 V). With an
M18 fitted, GP27 sees 18 × 0.2308 = **4.15 V** (4.85 V at 21 V) against a 3.3 V limit. R7's
1 kΩ series resistor holds clamp current to ~1.2 mA so the pin should survive, but the
reading clips across the whole operating range.

Fitting **56 k / 10 k on all three** gives ×6.6 exactly (21 V → 3.18 V) and only requires
setting `INV_P_RATIO = 6.6`. Both values are in the on-hand resistor kit.

**The 1 kΩ series resistors (R3/R7/R9) currently filter nothing** — V2 dropped the old
C3/C4 filter caps and never replaced them. Fit 100 nF from each of GP26/27/28 to GND to
form the RC (1.6 kHz corner) and to supply the ADC's sample-and-hold charge locally.

### Boat Pico — buses summary

| Bus | Owner | Pins | Speed | Notes |
|---|---|---|---|---|
| **UART0** | `vesc.py` | GP12 / GP13 | 115200 8N1 | **Not used on this branch** — `escs.py` (direct PWM) replaced the VESC chain. Those pins now carry SHT41 #A |
| **UART1** | `gps.py` *(shared)* | GP4 / GP5 | 9600 8N1 | GPS + Pod Pico share this bus; `task_uart1_reader` routes lines by `$GP*` / `$POD` prefix. ⚠ GP4 = MCP2515 `SO`, GP5 = **GND** on the board — this bus cannot work as wired |
| **I²C0** | `compass.py` | GP8 / GP9 | 400 kHz | BNO085 @ 0x4A via J7. ⚠ **no external pull-ups on the board** — 400 kHz needs ~1.5 kΩ to 3V3 |
| **SoftI2C #A** | `sensors.py` | GP12 / GP13 | 100 kHz | SHT41 #A @ 0x44 (J11). Bit-banged (HW I²C0 taken). ⚠ no pull-ups — fit 4.7 kΩ |
| **SoftI2C #B** | `sensors.py` | GP14 / GP15 | 100 kHz | SHT41 #B @ 0x44 (J13). **Three connectors on this bus** (J5 + J7 + J13). ⚠ no pull-ups — fit 2.2 kΩ |
| **PIO** | `sbus.py`, `esc_telem.py` | GP7 (SBUS), GP16 / GP19 (ESC telem) | 100 kbd inv 8E2 / 115200 | 3 of 8 state machines (`esc_telem._SM_L = 4`, `_SM_R = 5`). ⚠ GP7 = MCP2515 `~RESET`, GP19 = hull-leak connector J16 |
| **USB CDC** | `serial_handler.py` | (USB) | 115200 | Pi 5 ↔ Boat Pico command + telemetry |

> ### ⚠ No I²C pull-up resistors anywhere on the board
>
> All 11 fitted resistors are accounted for (three dividers, R1 PG pull-up, R11 MCP2515
> reset pull-up). None of the three I²C buses has a pull-up, so they rely on the RP2040's
> internal ~50–80 kΩ — too weak, especially on cable runs to a mast-mounted GPS/compass.
> Fit to 3V3: **1.5 kΩ** on GP8/GP9 (400 kHz needs a 300 ns rise time), **2.2 kΩ** on
> GP14/GP15 (three devices), **4.7 kΩ** on GP12/GP13. Don't go below 1 kΩ on any bus.
>
> ### ⚠ Sensor connectors supply 5 V, not 3.3 V
>
> `J7.5`, `J11.4` and `J13.4` are wired to **VSYS (5 V)**, while `J5.1` is 3V3 — and J5, J7
> and J13 all share the GP14/GP15 bus. SHT41 silicon is **3.6 V absolute max**. Confirm your
> GY-SHT41-D breakouts regulate onboard; even then, a 5 V-referenced module pulling the bus
> high exceeds the RP2040's limits. 3V3 is exposed on exactly one connector pin on the whole
> board: **J5 pin 1**.

---

### Boat_PCB V2 — connector index (what plugs in where)

Every connector on the board, pin by pin, from the verified netlist. `VSYS` = **5 V**.

| Ref | Silkscreen value | Type | Pinout |
|---|---|---|---|
| **J7** | GPS + Compass | JST-XH 6-pin | 1 = GP14 (SDA-B) · 2 = GP15 (SCL-B) · 3 = GP9 (SCL0) · 4 = GP8 (SDA0) · 5 = **VSYS 5 V** · 6 = GND |
| **J5** | IMU (14,15 I²C · 17,18 RST/INT) | JST-XH 10-pin | 1 = **3V3** · 2 = GND · 3 = GP15 · 4 = GP14 · 7 = GP17 (RST) · 8 = GP18 (INT) · 5, 6, 9, 10 = n/c |
| **J11** | Temp + Humidity, External | JST-XH 4-pin | 1 = GP12 (SDA-A) · 2 = GP13 (SCL-A) · 3 = GND · 4 = **VSYS 5 V** |
| **J13** | Temp + Humidity, Internal | 1×4 header | 1 = GP14 (SDA-B) · 2 = GP15 (SCL-B) · 3 = GND · 4 = **VSYS 5 V** |
| **J15** | Hull Leak Right | JST-XH 2-pin | 1 = GND · 2 = GP20 |
| **J16** | Hull Leak Left | JST-XH 2-pin | 1 = GND · 2 = GP19 |
| **J12** | led | JST-XH 3-pin | 1 = GND · 2 = **GP10** (data) · 3 = **VSYS 5 V** — *value says "GPIO 12", wired to GP10* |
| **J8** | Winch ESC | JST-XH 2-pin | 1 = GP21 · 2 = GND |
| **J9** | Winch ESC RC | 1×2 socket | 1 = GP21 · 2 = GND — parallel with J8 |
| **J18** | Stepper Motor | JST-XH 4-pin | 1 = 1B · 2 = 1A · 3 = 2A · 4 = 2B (from A2/A4988) |
| **J2** | *(CAN out)* | JST-XH 3-pin | 1 = GND · 2 = CANH (U2.7) · 3 = CANL (U2.6) — ⚠ **no 120 Ω termination fitted** |
| **J4** | 12s Tap | JST-XH 2-pin | 1 = R2 → GP26 divider · 2 = GND — *sense tap only* |
| **J6** | 4s output | XT60 | 1 = GND · 2 = VMOT |
| **BT1** | 3s (electronics) | XT60 | 1 = GND · 2 = rail → J1 buck V<sub>IN</sub>, C5/C6, R5 → GP27 |
| **BT4** | 4s (motor) | XT60 | 1 = GND · 2 = VMOT → A2, C7/C8, J6, R8 → GP28 |
| **J1** | *(Pololu 36 V→5 V buck)* | 2×6 module | 7, 8 = V<sub>IN</sub> · 1, 2 = 5 V out (VSYS) · 3–6 = GND · 12 = `PG` → GP22 |
| **J3** | Raspberry Pi 5 connector | 2×20 header | Full Pi header — **rows transposed**, see stepper section |
| **J14 / J17** | *(breakout)* | 1×20 sockets | J14 = Pi even pins reversed · J17 = Pi odd pins in order |

> ⚠ **Silkscreen swap on R9 / R11.** The reference text for these two is placed over the
> wrong footprint (each label sits nearer its neighbour's body than its own). When
> populating: fit **1 kΩ** at the pad printed *"R11"* and **10 kΩ** at the pad printed
> *"R9"*. The 1 kΩ belongs in the divider cluster with R5–R8/R10; the 10 kΩ is the isolated
> one beside the MCP2515. R2's label has also drifted over J4.

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

The Pi 5 hangs **every sensor off USB**. The **one exception** is the radar-bar pan
stepper (see below), the only thing in the project to drive Pi 5 GPIO directly — a
deliberate divergence from the "Pi 5 uses only USB — no GPIO" locked decision in
`CLAUDE.md`, made because the Boat Pico is out of free pins and the bar is tightly
coupled to the camera/vision stack on the Pi 5.

The header is **not** just a power tap on `Boat_PCB V2`: **J3** mates the full 40-pin
header, and **J14 / J17** break every Pi pin back out (even pins reversed / odd pins in
order respectively). Four of those pins drive the A4988.

> ⚠ **Powering the Pi.** `J3` pads 1 and 3 (Pi header pins **2** and **4**, both 5 V) are
> wired to `Net-(A1-VSYS)`, the output of the J1 Pololu buck — the same rail that feeds the
> Pico. Those pins are *bidirectional*: whenever the Pi is powered over USB-C they become
> outputs, so populating J1 **and** connecting USB-C parallels two 5 V supplies and can
> backfeed the buck (Pololu step-downs are not reverse-current tolerant). Pick one:
> buck-powers-everything (leave USB-C off) **or** Pi-powers-the-board (don't populate J1).
>
> Sizing matters too — the narrowest VSYS trace is 1.25 mm (~2.6 A at a 10 °C rise), and the
> common 36 V→5 V Pololu parts are 2.5–2.8 A, well under a Pi 5's appetite. Header powering
> also bypasses the Pi's USB-C input protection, and without PD negotiation the Pi 5 caps
> **total USB current at 600 mA** — set `usb_max_current_enable=1` in
> `/boot/firmware/config.txt` if the upstream supply genuinely delivers more.

### ⚠ Radar-bar stepper — Pi 5 GPIO (A4988)

Driven from the 40-pin header via **gpiozero/lgpio** (`pi5/cv/stepper.py`, config in
`pi5/config.yaml` → `stepper:`). The driver runs in a no-op *mock* mode when
gpiozero/lgpio is absent (laptop / simulator), so this never affects the sim.

The A4988 is **A2** on `Boat_PCB V2` (a Pololu carrier), and every control line reaches
the Pi through **J3**, the 40-pin header. Verified against the netlist:

| Pi 5 pin (BCM) | Header | J3 pad | A4988 | Polarity / notes |
|---|---|---|---|---|
| GPIO23 | 16 | 15 | STEP | rising-edge pulse, ≥1 µs |
| GPIO24 | 18 | 17 | DIR | set ≥200 ns before STEP |
| GPIO25 | 22 | 21 | ~ENABLE | active-LOW (0 = energised/hold, 1 = freewheel) |
| GPIO8 | 24 | 23 | ~RESET **+** ~SLEEP | both tied on-board (A2.13 + A2.14) — one pin releases both |
| 3V3 | **1** | 2 | VDD **+** MS1 | Pi 3V3 powers the logic *and* holds MS1 high |
| GND | 6, 9, 14, 20 | 5, 10, 13, 19 | GND | VMOT comes from **BT4** (XT60), not the electronics pack |

> ### ⚠ Half step, not 1/16 — `steps_per_rev` is wrong
>
> `stepper.py` states *"1/16 microstepping is wired in hardware (MS1/MS2/MS3 → 3V3),
> giving 3200 steps/rev"* and defaults `steps_per_rev = 3200`. **The board doesn't do
> that.** Only MS1 is high (via Pi 3V3 on J3 pad 2); `A2.11` (MS2) and `A2.12` (MS3) are
> both hard-wired to **GND**. MS1 high with MS2/MS3 low is **half step** → **400 steps/rev**
> on a 200-step motor.
>
> That's an **8× error on every move**: `_deg_per_step` computes 0.1125° when reality is
> 0.9°, so a commanded 10° pan travels 80° and the soft limits get driven straight through
> into the end stops. Fix by setting `steps_per_rev = 400` (half step is the intended
> configuration). Pulling MS2/MS3 high for real 1/16 stepping would need trace cuts.
>
> ### ⚠ J3's schematic pin numbers are not Pi header pin numbers
>
> J3's footprint has the **odd/even rows transposed** relative to the `Conn_02x20_Odd_Even`
> symbol, so schematic pad *N* lands on Pi header pin *N∓1*. Confirmed two ways: all six
> power/ground pins align only under the swap (0 conflicts vs. 6), and the four A4988
> signals then match `stepper.py`'s BCM numbers exactly. **Read the table above, not the
> schematic pad numbers.** The two breakout sockets split the header by parity —
> **J17** = Pi odd pins in order (J17.1 = Pi pin 1 = 3V3), **J14** = Pi even pins reversed
> (J14.20 = Pi pin 2 = 5 V).
>
> ### ⚠ The stepper depends on a mated Pi
>
> A4988 VDD has no on-board supply — it is fed only from the Pi's 3V3 on header pin 1. With
> no Pi on J3 the driver is dead, and GP22's `PG` pull-up (R1, which rides the same net)
> floats. Bench-testing the Pico alone will not exercise the stepper.

> ✅ **RESET is already handled on the board.** The A4988 has *two* active-low control
> pins, SLEEP **and** RESET, and both must be high before a STEP pulse takes effect — a
> floating/low RESET is the classic "driver powered, no error, motor never moves." V2 ties
> `A2.13` (~RESET) to `A2.14` (~SLEEP) on one net, which is Pololu's documented approach, so
> GPIO8 releases both and `stepper.reset_pin` does **not** need setting.
>
> ⚠ Side effect of that tie: `auto_sleep_s` also asserts RESET, which resets the A4988's
> internal microstep translator to its home phase. Software position tracking won't know,
> so expect up to a step of drift per sleep/wake cycle — smaller at half step than it would
> be at 1/16, but it accumulates.
>
> Still confirm **VMOT** (from BT4; C7 is the bulk electrolytic Pololu asks for) and the
> **VREF** current limit — logic runs off VDD alone, so the chip will ACK STEP with no coil
> power at all.
>
> ⚠ Boot-state caveat: GPIO25 (~ENABLE) defaults LOW at boot, which *energises* the coils
> before software runs, and the net only reaches J14.10/J3.21 so it floats until the Pi
> configures the pin. Fit a **10 kΩ pull-up to the VDD/MS1 net** for a disabled default.
> GPIO8 (SLEEP, an SPI0 CE pin) has a boot pull-up = awake.

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
the sole GPIO consumer). The 40-pin header carries the A4988 control lines, 5 V/GND
to the board, and the J14/J17 breakouts; see the stepper section above for the map.

| Pi 5 port | Device | Driver / module | Notes |
|---|---|---|---|
| USB-A (1) | Boat Pico | `pi5/comms/pico_serial.py` (CDC ACM, 115200) | Shows up as `/dev/ttyACM0` |
| USB-A (2) | Left USB camera | `pi5/cv/camera.py` (`cv2.VideoCapture(0)`) | 640×480 @ 10 fps |
| USB-A (3) | Right USB camera | `pi5/cv/camera.py` (`cv2.VideoCapture(1)`) | Stereo pair, 120 mm baseline |
| USB-A (4) | SIM7600G-H 4G HAT (or USB-TTL HC-12) | OS-level (`/dev/ttyUSB*`) | Cellular bring-up handled outside this codebase |
| USB-C | Power input — 5 V from logic-domain UBEC | n/a | Sourced from the 1× M18 electronics pack via the 5 V UBEC |
| Internal | WiFi (Pi 5 onboard) | OS-level via NetworkManager / `nmcli` | Configured by `pi5/comms/network.py` when `network.mode` is `wifi` or `auto` |

> The boat's actual GPIO/peripheral wiring lives entirely on the Picos.
> If you're looking for "where is GPS connected to the Pi 5?" — it isn't.
> GPS hangs off the Boat Pico's UART1 and is reported up to the Pi 5 over
> the USB CDC link as a serial telemetry frame.
