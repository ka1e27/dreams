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
> The old GP12–GP15 collision is **resolved**: the drive ESCs and SBUS moved off the
> temp-sensor pins to GP2/GP3/GP7, the winch to GP21, and `sensors.py` matches the
> board's SHT41 connectors (J11 on GP12/13, J13 on GP14/15).
>
> **But the pins the ESCs and SBUS moved *to* are not free on the V2 board.**
> `Boat_PCB V2` fits an **MCP2515 + TJA1051 CAN interface** (U1/U2, for the VESC
> architecture) which owns GP2, GP3, GP4, GP6 and GP7. This branch's firmware is the
> *test-bench* variant that assumes no CAN. The two cannot coexist:
>
> | Pin | This branch's firmware | V2 board wires it to | Verdict |
> |---|---|---|---|
> | GP2 | Left drive ESC PWM (`escs.LEFT_PIN`) | U1.13 — MCP2515 `SCK` | **conflict** |
> | GP3 | Right drive ESC PWM (`escs.RIGHT_PIN`) | U1.14 — MCP2515 `SI` (MOSI) | **conflict** |
> | GP4 | UART1 TX (GPS + Pod) | U1.15 — MCP2515 `SO` (MISO) | **conflict** — two outputs fight |
> | GP5 | UART1 RX (GPS + Pod) | **GND** in the schematic — but **measurably free on the built board** (2026-07-29) | reaches no connector |
> | GP6 | *unused by firmware* (was the winch) | U1.12 — MCP2515 `~INT` | ✅ resolved — winch moved to GP21 |
> | GP7 | SBUS RC input (`sbus.SBUS_PIN`) | U1.17 — MCP2515 `~RESET` + R11 10 k pull-up | **conflict** |
> | GP11 | Right ESC telemetry RX (`esc_telem.TELEM_R_PIN`) | *unconnected* | ✅ no clash — **not routed to a connector**, solder to the Pico pin |
> | GP16 | Left ESC telemetry RX (`esc_telem.TELEM_L_PIN`) | *unconnected* | ✅ no clash — same, solder direct |
> | GP19 | Left drive ESC PWM (`escs.LEFT_PIN`) | J16.2 — ex-"Hull Leak Left" | ✅ repurposed 2026-07-30 — real connector, no clash |
> | GP20 | Right drive ESC PWM (`escs.RIGHT_PIN`) | J15.2 — ex-"Hull Leak Right" | ✅ repurposed 2026-07-30 — real connector, no clash |
> | GP21 | Winch ESC PWM (`motor_control.MW_PIN`) | J8.1 + J9.1 — "Winch ESC" (parallel) | ✅ matches the board |
>
> ### ⚠ 2026-07-30 — drive ESCs moved onto the hull-leak connectors
>
> `escs.py` drove **GP2/GP3**, which on `Boat_PCB V2` belong to the MCP2515 and reach
> **no connector** — the bench tapped the Pico header directly. Both drive ESCs now use
> the two hull-leak connectors instead:
>
> | | pin | connector | ESC | motor | telemetry |
> |---|---|---|---|---|---|
> | **Left** | GP19 | J16 (ex-"Hull Leak Left") | NeutronRC 70A-G071 · **AM32** | Badass 2814-**1560 kv** | GP16 |
> | **Right** | GP20 | J15 (ex-"Hull Leak Right") | FlashHobby FH-70A · **BLHeli-32** | Badass 2320-**1630 kv** | GP11 |
>
> J15/J16 are JST-XH 2-pin wired **1 = GND, 2 = signal** — exactly an ESC servo lead.
> PWM slices work out: GP19 = slice 1B (free once GP2/GP3 are released), GP20 = slice 2A,
> sharing slice 2 with the winch on GP21 (2B) — same 50 Hz, independent duty, so no clash.
>
> **Hull leak sensing is gone.** `sensors.py` must never configure GP19/GP20 again —
> `sensors.init()` runs *after* `motor_control.init()`, so a pull-up input there would
> fight live ESC PWM. `sensors.hull_status()` now returns **`--`** (no sensor) rather than
> `DRY`, `HULL_LEAK` alerts are no longer emitted, and the **pod leak sensor
> (`pod_uart.leak_detected`) is the only remaining leak alarm**.
>
> The two ESCs run **different firmware** and need different setup (AM32 "Bi-directional"
> vs BLHeli-32 "3D mode") — see `docs/esc_setup.md`. The ~4.5 % Kv mismatch is trimmed in
> `motor_control.COMP_R = 0.957`; leave `navigation.motor_gain_*` at 1.0 so it is not
> compensated twice.

> **CORRECTION (2026-07-29): J7 *is* the GPS UART — the firmware is on the wrong pins.**
> An earlier revision of this file claimed "the GPS has no UART on this board" because it
> listed GP8/GP9 as I²C0 only. They are **dual-function**: the RP2040 muxes UART1 TX to
> GP4/**GP8**/GP20/GP24 and RX to GP5/**GP9**/GP21/GP25. So J7.4/J7.3 = GP8/GP9 are a
> legitimate UART1 TX/RX pair, and J7 was laid out as the GPS serial link. The firmware's
> GP4/GP5 reach **no connector at all**.
>
> ⚠ **But GP9 is hard-shorted to GND on the as-built board** (confirmed by multimeter and
> by a 2 mA pad-drive test: GP9 and GP10 both lose against the short, every other
> GND-adjacent pad is clean). One blob spans Pico pads **12 (GP9) · 13 (GND) · 14 (GP10)**,
> which explains three symptoms at once: GPS dead (GP9 = UART1 RX), status NeoPixel dead
> (GP10, and `status_led.py` has been driving an output into a dead short), and
> `IMU: I2C0 GP8/GP9 FAIL` every boot (GP9 = SCL0, a clock line held low).
>
> **Resolution: the GPS moved to the Pi 5's header UART** — see the Pi 5 section below.
> That routes around the short entirely, so it doesn't matter whether the copper is on the
> Pico or the carrier board.
>
> **Firmware realigned to the board on 2026-07-28** (three moves, all in this branch):
> leak sensing GP17/GP18 → **GP19/GP20** so it reads the board's real J16/J15
> connectors (GP17/GP18 are the BNO085's RST/INT on J5); right-ESC telemetry
> GP19 → **GP11** (GP11 and GP16 are the only two unconnected pins on V2, so both
> telemetry taps are clash-free and all four inputs fit); and winch PWM GP6 → **GP21**,
> the board's actual winch signal net. The winch was the **only** one of the five CAN
> pins with a free board-side pin to move to — GP0/GP1 are dead and every other pin is
> committed, so **there is no free pin left** to relieve the GP2/3/4/5/7 conflicts above.
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
| GP4 | TX | UART1 TX (shared GPS+pod bus) | Pod Pico · 9600 8N1 (**GPS moved to the Pi**) | ⚠ U1.15 — MCP2515 `SO`; reaches no connector | `gps.init` → `UART(1, …, tx=Pin(4))` |
| GP5 | RX | UART1 RX (shared GPS+pod bus) | Pod Pico · 9600 8N1 (**GPS moved to the Pi**) | reaches no connector; schematic ties it to GND but the built board leaves it **free** | `gps.init` → `UART(1, …, rx=Pin(5))` |
| GP6 | — | *unused by firmware* (was the winch until 2026-07-28) | — | ⚠ U1.12 — MCP2515 `~INT` | — |
| GP7 | IN | SBUS RC receiver (PIO) | SBUS · 100 kbd inv 8E2 | ⚠ U1.17 — MCP2515 `~RESET` + R11 10 k pull-up | `sbus.SBUS_PIN` |
| GP8 | SDA **or UART1 TX** | I²C0 data (firmware) / UART1 TX (board intent) | BNO085 IMU @ 0x4A · 400 kHz | **J7.4** — GPS+Compass, 6-pin JST-XH | `compass.init` → `I2C(0, sda=Pin(8))` |
| GP9 | SCL **or UART1 RX** | I²C0 clock (firmware) / UART1 RX (board intent) | BNO085 IMU @ 0x4A · 400 kHz | **J7.3** — ⚠ **SHORTED TO GND** on the built board | `compass.init` → `I2C(0, scl=Pin(9))` |
| GP10 | OUT | Status NeoPixel (WS2812, 1 px) | WS2812 · single-wire 800 kHz | **J12.2** — 3-pin JST-XH (pin 3 = VSYS **5 V**) | `status_led.PIN` |
| GP11 | IN | Right ESC telemetry RX | **BLHeli-32** KISS · PIO UART 115200 | unconnected — **not routed to any connector** | `esc_telem.TELEM_R_PIN` |
| GP12 | SDA | SHT41 #A temp/humidity | SHT41 @ 0x44 · SoftI2C 100 kHz | **J11.1** — 4-pin JST-XH, external | `sensors.SHT_A_SDA` |
| GP13 | SCL | SHT41 #A temp/humidity | SHT41 @ 0x44 · SoftI2C 100 kHz | **J11.2** | `sensors.SHT_A_SCL` |
| GP14 | SDA | SHT41 #B temp/humidity | SHT41 @ 0x44 · SoftI2C 100 kHz | **J13.1** (internal) + J5.4 + J7.1 — 3 devices | `sensors.SHT_B_SDA` |
| GP15 | SCL | SHT41 #B temp/humidity | SHT41 @ 0x44 · SoftI2C 100 kHz | **J13.2** + J5.3 + J7.2 | `sensors.SHT_B_SCL` |
| GP16 | IN | Left ESC telemetry RX | **AM32** KISS · PIO UART 115200 | unconnected — **not routed to any connector** | `esc_telem.TELEM_L_PIN` |
| GP17 | — | *unused by firmware* | — | **J5.7** — BNO085 `RST` | — |
| GP18 | — | *unused by firmware* | — | **J5.8** — BNO085 `INT` | — |
| GP19 | OUT | **Left drive ESC** (AM32 NeutronRC 70A → 2814-1560kv) | 50 Hz servo PWM · slice 1B | **J16.2** — ex-"Hull Leak Left", 2-pin JST-XH (1 = GND, 2 = signal) | `escs.LEFT_PIN` |
| GP20 | OUT | **Right drive ESC** (BLHeli-32 FlashHobby FH-70A → 2320-1630kv) | 50 Hz servo PWM · slice 2A (shares slice 2 with the winch, both 50 Hz) | **J15.2** — ex-"Hull Leak Right", 2-pin JST-XH (1 = GND, 2 = signal) | `escs.RIGHT_PIN` |
| GP21 | OUT | Winch ESC | Winch ESC · 50 Hz servo PWM | **J8.1 + J9.1** — Winch ESC signal (both in parallel) | `motor_control.MW_PIN` |
| GP22 | — | *unused by firmware* | — | **J1.12** — 5 V buck `PG` (open-drain) + R1 10 k → A4988 VDD/MS1 | — |
| GP26 | ADC0 | Drive battery sense | 2× M18 parallel · analog 0–3.3 V | **J4** "12s Tap" → R2/R4 = 56k/10k **×6.6** | `ADC(26)`, `INV_P_RATIO` = 6.6 ✓ |
| GP27 | ADC1 | Electronics battery sense | 1× M18 · analog 0–3.3 V | **BT1** "3s" → R5/R6 = 56k/10k **×6.6** | `ADC(27)`, `INV_E_RATIO` = 6.6 ✓ |
| GP28 | ADC2 | Winch battery sense | 1× M18 · analog 0–3.3 V | **BT4** "4s" → R8/R10 = 56k/10k **×6.6** | `ADC(28)`, `INV_W_RATIO` = 6.6 ✓ |

### ✅ Battery dividers — 56 k / 10 k on all three rails

**The physical board carries 56 k / 10 k in all three divider positions** (confirmed by the
builder, 2026-07-28), so every rail reconstructs at the same ratio and lands just under the
ADC ceiling at full charge:

| Rail | Fitted | Ratio | Firmware | 18 V nom | 21 V max |
|---|---|---|---|---|---|
| Drive → GP26 | R2 56 k / R4 10 k | ×6.6 | `INV_P_RATIO` = 6.6 ✓ | 2.73 V | 3.18 V |
| Electronics → GP27 | R5 56 k / R6 10 k | ×6.6 | `INV_E_RATIO` = 6.6 ✓ | 2.73 V | 3.18 V |
| Winch → GP28 | R8 56 k / R10 10 k | ×6.6 | `INV_W_RATIO` = 6.6 ✓ | 2.73 V | 3.18 V |

`INV_P_RATIO` was **14.0 → 6.6** on 2026-07-28 to match; at ×14.0 a full 21 V drive pack
reported 16.4 V, which is under `P_WARN` (17.0) and a hair over `P_CRIT` (16.0), so the boat
would have tripped return-to-home on a full battery. Divider drain is 318 µA per rail at
21 V (5.7 mW in the 56 k — trivial for a 1/4 W part).

> ⚠ **The KiCad schematic disagrees with the board, and the board is right.**
> `Boat_PCB.kicad_sch` still carries the pre-M18 values — drive 220 k/13 k (×17.92),
> electronics 100 k/30 k (×4.33, which would be *over-range* on an M18: 4.15 V into a 3.3 V
> pin), winch 100 k/18 k (×6.56). A netlist export therefore reports ratios that don't match
> what's populated or what the firmware expects. **Trust `sensors.py` and this table**; the
> schematic needs updating in KiCad. 13 k, 30 k and 18 k aren't even in the on-hand resistor
> kit, which is corroborating evidence they were never fitted.

**The 1 kΩ series resistors (R3/R7/R9) currently filter nothing** — V2 dropped the old
C3/C4 filter caps and never replaced them. Fit 100 nF from each of GP26/27/28 to GND to
form the RC (1.6 kHz corner) and to supply the ADC's sample-and-hold charge locally.

### Boat Pico — buses summary

| Bus | Owner | Pins | Speed | Notes |
|---|---|---|---|---|
| **UART0** | `vesc.py` | GP12 / GP13 | 115200 8N1 | **Not used on this branch** — `escs.py` (direct PWM) replaced the VESC chain. Those pins now carry SHT41 #A |
| **UART1** | `gps.py` *(shared)* | GP4 / GP5 | 9600 8N1 | Pod Pico only now — **the GPS moved to the Pi's UART** (`/dev/ttyAMA0` @ 38400). `task_uart1_reader` still routes lines by `$GP*` / `$POD` prefix, and `pod_uart.init(gps._uart)` means `gps.init()` **cannot simply be deleted**. ⚠ Also note the module is **38400**, not the 9600 in `gps.py` — one UART can't serve both, another reason position lives on the Pi |
| **I²C0** | `compass.py` | GP8 / GP9 | 400 kHz | BNO085 @ 0x4A via J7. ⚠ **DEAD — GP9 (SCL) is shorted to GND**, so this bus can never clock. Also ⚠ no external pull-ups. The board wires J7's *compass* pins to GP14/GP15 (SoftI2C #B) anyway, so `compass.py` needs moving there |
| **SoftI2C #A** | `sensors.py` | GP12 / GP13 | 100 kHz | SHT41 #A @ 0x44 (J11). Bit-banged (HW I²C0 taken). ⚠ no pull-ups — fit 4.7 kΩ |
| **SoftI2C #B** | `sensors.py` | GP14 / GP15 | 100 kHz | SHT41 #B @ 0x44 (J13). **Three connectors on this bus** (J5 + J7 + J13). ⚠ no pull-ups — fit 2.2 kΩ |
| **PIO** | `sbus.py`, `esc_telem.py` | GP7 (SBUS), GP16 / GP11 (ESC telem) | 100 kbd inv 8E2 / 115200 | 3 of 8 state machines (`esc_telem._SM_L = 4`, `_SM_R = 5`). ⚠ GP7 = MCP2515 `~RESET`. GP16/GP11 are unconnected on V2 — no clash, but solder direct |
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
| **J7** | GPS + Compass — ⚠ **unused, GPS now on the Pi** | JST-XH 6-pin | 1 = GP14 (SDA-B) · 2 = GP15 (SCL-B) · 3 = GP9 (**UART1 RX** / SCL0 — ⚠ shorted to GND) · 4 = GP8 (**UART1 TX** / SDA0) · 5 = **VSYS 5 V** ⚠ · 6 = GND |
| **J5** | IMU (14,15 I²C · 17,18 RST/INT) | JST-XH 10-pin | 1 = **3V3** · 2 = GND · 3 = GP15 · 4 = GP14 · 7 = GP17 (RST) · 8 = GP18 (INT) · 5, 6, 9, 10 = n/c |
| **J11** | Temp + Humidity, External | JST-XH 4-pin | 1 = GP12 (SDA-A) · 2 = GP13 (SCL-A) · 3 = GND · 4 = **VSYS 5 V** |
| **J13** | Temp + Humidity, Internal | 1×4 header | 1 = GP14 (SDA-B) · 2 = GP15 (SCL-B) · 3 = GND · 4 = **VSYS 5 V** |
| **J15** | ~~Hull Leak Right~~ → **Right drive ESC signal** | JST-XH 2-pin | 1 = GND · 2 = GP20 |
| **J16** | ~~Hull Leak Left~~ → **Left drive ESC signal** | JST-XH 2-pin | 1 = GND · 2 = GP19 |
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
| GPIO24 | 18 | 17 | DIR | set ≥200 ns before STEP · **polarity is a build fact — see below** |
| GPIO25 | 22 | 21 | ~ENABLE | active-LOW (0 = energised/hold, 1 = freewheel) |
| GPIO8 | 24 | 23 | ~RESET **+** ~SLEEP | both tied on-board (A2.13 + A2.14) — one pin releases both |
| 3V3 | **1** | 2 | VDD **+** MS1 | Pi 3V3 powers the logic *and* holds MS1 high |
| GND | 6, 9, 14, 20 | 5, 10, 13, 19 | GND | VMOT comes from **BT4** (XT60), not the electronics pack |

> ### ✅ Half step, not 1/16 — `steps_per_rev` fixed 2026-07-28
>
> The board does **half step**, not the 1/16 that `stepper.py` used to claim. Only MS1 is
> high (via Pi 3V3 on J3 pad 2); `A2.11` (MS2) and `A2.12` (MS3) are both hard-wired to
> **GND**. MS1 high with MS2/MS3 low is **half step** → **400 steps/rev** on a 200-step
> motor, 0.9°/step.
>
> The old `steps_per_rev = 3200` was an **8× error on every move**: `_deg_per_step`
> computed 0.1125° against a real 0.9°, so a commanded 10° pan travelled 80° and drove
> the soft limits straight through into the end stops — and the pulse train ran 8× too
> fast for the commanded rpm, so the motor was likely skipping steps rather than
> tracking. Now `400` in `pi5/config.yaml`, `stepper.py`'s default, `stepper_test.py`
> and `run_hardware.py`'s fallback. Pulling MS2/MS3 high for real 1/16 stepping would
> need trace cuts — don't raise the value without doing that first.
>

> ### Which way does it turn? Two config knobs, don't guess between them
>
> Whether `DIR` high is clockwise depends on which way the coil pairs landed in **J18**
> and on the gearing between motor and bar — neither is knowable from software, and
> neither is captured in KiCad. So direction is configuration, not code:
>
> | Symptom | Set | Effect |
> |---|---|---|
> | **Every** move mirrored — manual jog included | `stepper.invert_direction: true` | Inverts the DIR pin. Position accounting is untouched, so 90° stays the same physical place; the shaft just gets there turning the other way. |
> | Manual jog correct, but **TRACK** chases the wrong way | `stepper.invert_tracking: true` | Flips only the bbox→bearing sign in `radar_tracker`. Nothing else moves. |
> | Both wrong the same way | `invert_direction` alone | It already covers tracking. |
>
> Swapping one coil pair at J18 does the same thing as `invert_direction` in hardware —
> the flag exists so you don't have to, given how much this board has already been reworked.

> ### Angle convention: **0° = dead ahead**, + starboard, − port
>
> | | Value | Why |
> |---|---|---|
> | Boot position | `0°` | The stepper has **no home switch** — `_position_steps` starts at 0, so it *assumes* the bar is pointing dead ahead at power-on. Point it forward before starting the stack. |
> | `bow_degrees` | `0` | Must equal the boot position, or the first tracking command jumps the difference before it aims at anything. |
> | `sweep_*_degrees` | `-90 … 90` | Forward-looking half-circle, centred on the bow. |
> | `manual_*_degrees` | `-180 … 180` | A **full 360° and no further** — enough to follow a target right around the boat, never more than one turn of cable. Tracking uses the same limits. |
> | CENTER button | → `bow_degrees` | "Look forward", not "go to the axis zero". |
>
> Re-centred on 2026-07-30. The old 0…360 axis had **no way to express "a bit to port"** —
> every port-side bearing clamped at the 0 end stop, so half the field of view was
> untrackable — and with `bow_degrees` at 90 on a 0–180 sweep the first `rotate_to(90 ±
> offset)` from a standing start of 0 was a **~90° lurch to starboard whichever side the
> target was on**. That was the second "it turns away from me" report, and it was a
> *coordinate* fault, not a polarity one — `invert_tracking` would not have fixed it.
>
> ### Tracking is a closed loop — the cameras ride ON the bar (2026-07-30)
>
> Confirmed by the builder; this **supersedes** `docs/object_memory.md`'s "the cameras are
> fixed forward", which was stale and had the pan angle omitted from every bearing.
> Turning the bar turns the cameras, so a target off-centre in frame walks *toward* centre
> as the bar comes round. Each tick (`radar_tracker._step_toward`):
>
> 1. take the target's box centre — the **median of both cameras** when
>    `camera.detection.detect_right` is on, else the single camera that is running;
> 2. convert its offset from frame centre to degrees via `fov_degrees`;
> 3. nudge the bar by `offset × track_gain`, capped at `max_step_degrees`;
> 4. stop inside `center_deadband_degrees`.
>
> **Velocity feedforward.** A position-only loop can only react to an error that has
> already opened, so the faster the target moves the further behind the bar trails —
> until it walks out of frame. The tracker measures the target's angular rate and aims
> ahead of it: `step = (offset + rate × lead_seconds) × gain`.
>
> The rate is fitted (least squares, `velocity_window_seconds`) on the **bow-relative
> bearing**, `bar angle + offset` — *not* on the pixel offset. With the cameras on the
> bar the offset shrinks purely because the bar turned, which is not the target moving.
> Samples are taken only when the **detection actually changes**: the tracker loop runs
> at 10 Hz while the detector is capped lower, so re-sampling a frozen box while the bar
> slews would read the bar's own motion as the target's — a feedforward feeding itself.
>
> Measured against a rate-limited bar with 200 ms of detection latency (steady-state lag,
> constant velocity):
>
> | target rate | `lead_seconds` 0 | 0.15 | 0.25 | 0.35 |
> |---|---|---|---|---|
> | 10°/s | 4.9° | 3.4° | 2.4° | **1.4°** |
> | 20°/s | 7.6° | 4.6° | 2.6° | **0.8°** |
> | 30°/s | 9.3° | 5.0° | 2.7° | **1.9°** |
> | 40°/s | 12.5° | 8.4° | 6.8° | **6.4°** |
> | 50°/s | 16.7° | 15.5° | 15.5° | 15.5° |
>
> Past ~40°/s the bar is speed-limited, not lag-limited — no amount of lead helps and
> `max_rpm` (10 rpm = 60°/s) is the ceiling. ⚠ Lead is a *prediction*, so it overshoots
> on a sharp reversal; that settles within a few ticks and is the trade for the table above.
>
> Speed takes the **larger** of "fast enough for this error" (`track_speed_min_rpm` at
> centre → `track_speed_rpm` at the frame edge) and "fast enough for this rate"
> (`|rate| ÷ 6 × velocity_speed_margin` rpm), capped at `max_rpm`. Scaling on error alone
> gives a target crossing quickly through the middle the *slowest* bar exactly when it
> needs the quickest.
>
> **A wrong DIR polarity makes this diverge**: moving the wrong way *increases* the
> offset, which commands a bigger move the same wrong way, until the bar hits a stop.
> That is what the 2026-07-29 runaway actually was, and `stepper.invert_direction` is
> what fixes it. The backstop is `_STALL_LIMIT`: five corrections that fail to shrink the
> offset (once the rate estimate is mature, so the startup transient doesn't count) and
> the radar panel warns. It picks between the two causes — *"the bar may be turning the
> wrong way"* vs *"target moving at N°/s — faster than the bar can slew"* — on whether
> the measured rate actually exceeds `max_rpm`. It **warns without halting**: halting
> abandoned targets the bar could hold, and it isn't needed to prevent an end-stop
> runaway, because under a direction fault the target leaves the frame within a second or
> two and the lock drops on its own.
>
> ⚠ **Every bbox bearing is now relative to the bar, not the bow.**
> `pipeline._avoidance_bearing` adds the bar angle back in (gated on
> `stepper.cameras_on_bar`) — geolocation would otherwise plant map markers however far
> the bar was panned out of true, and avoidance would steer away from the wrong side.
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

The Pi 5 has **two** GPIO consumers: the radar-bar A4988 stepper (above) and — since
2026-07-29 — the **GPS on the header UART**. Everything else hangs off USB. The 40-pin
header carries the A4988 control lines, the GPS UART, 5 V/GND to the board, and the
J14/J17 breakouts.

### GPS on the header UART (GPIO14/15 → `/dev/ttyAMA0`)

**Measured working on the bench 2026-07-29:** 38400 baud, 3D fix, 1 Hz, 100 %
checksum-clean.

| Pi 5 pin | BCM | Function | Wired to | Notes |
|---|---|---|---|---|
| 10 | GPIO15 | UART0 RXD | GPS module **TX** | The only wire that matters — NMEA is unsolicited |
| 8 | GPIO14 | UART0 TXD | GPS module RX | ⚠ Probably **not connected** — 5× `UBX-MON-VER` polls got no reply |
| 1 / 17 | — | 3V3 | GPS VCC | Use per the module's rating; check its logic level is 3.3 V |
| 6 / 9 / 14 | — | GND | GPS GND | |

- **Requires the `uart0` overlay** — GPIO14/15 are muxed to *no function* out of the
  box, so `/dev/ttyAMA0` does not exist until `dtoverlay=uart0` is in
  `/boot/firmware/config.txt` (added 2026-07-29) or loaded at runtime with
  `sudo dtoverlay uart0`.
- ✅ **No serial-console clash on a Pi 5.** `console=serial0` resolves to `ttyAMA10`,
  the separate 3-pin debug-UART connector. Nothing needs stopping (this differs from
  the Pi 4 advice you'll find elsewhere).
- **38400 baud, not 9600** — the u-blox **M10** factory default. Confirmed by the
  constellation set too: GP+GA+GB+GQ (GPS/Galileo/BeiDou/QZSS, no GLONASS).
- ⚠ **Collides with `pi5/scripts/am32_config.py`**, which flashes AM32 ESCs over
  `/dev/ttyAMA0` on these same two pins. Unplug the GPS to configure an ESC.
- ⚠ The module's **I²C is not wired** to the Pi (`i2cdetect -y 1` is empty — no
  compass, no u-blox DDC at 0x42). Only its UART TX is connected.
- Read by `pi5/comms/gps_nmea.py`; injected into `pico.telemetry` via
  `PicoSerial.set_external_position`, which is where the whole nav stack already
  reads position. **Heading still comes from the Pico's compass.**

#### Reading `gps_source` when there's no position (2026-07-30)

`telemetry.gps_source` names the **Pi receiver's** state, and the rung tells you
what to actually go and do. The command center shows this on the *GPS Fix* row.

| `gps_source` | Dashboard | Means | Do this |
|---|---|---|---|
| `pi-nolink` | `NO SIGNAL` (red) | no NMEA has *ever* arrived | module unpowered, TX off GPIO15, or overlay missing → `sudo dtoverlay uart0` |
| `pi-nofix` | `NO FIX · 2/6 sats · 34dB` (amber if any sat is heard) | streaming cleanly, not locked | **sky-view problem, not wiring.** Needs 4 sats; get the antenna clear of roofs |
| `pi-stale` | `STALE FIX` (amber) | locked once, fix now older than `stale_after_s` | position on the map is the last known one, not current |
| `pi` | `GPS · 6 sats` (green) | fresh usable fix | — |

Note the asymmetry: `pi-nofix` means **never** locked (no position exists to
serve), whereas locking and then losing it goes to `pi-stale` and keeps serving
the last position — deliberate, because the Pico's lat/lon are a hard 0.0 and
nothing in the nav stack guards against (0, 0).

The satellite counts come from **NMEA GSV**, summed across constellations
(the M10 emits GPGSV/GAGSV/GBGSV/GQGSV each second). `gps_sats_visible` is how
many the receiver believes are up there, `gps_sats_tracked` how many it actually
*hears* (SNR > 0), and `gps_best_snr` the strongest signal in dB-Hz. Much above
30 dB-Hz proves the antenna and RF chain work, so a missing fix is then purely
about sky view. ⚠ Blank elevation/azimuth in GSV means **no almanac yet** — a cold
start, which needs ~30 s of *uninterrupted* signal to complete and will therefore
never finish indoors on a marginal signal, however long you leave it.

**Why the GPS is here and not on the Pico:** the Pico's **GP9 is hard-shorted to
GND** on the as-built board (one blob across Pico pads 12/13/14 — which also kills
GP10's status NeoPixel and I²C0). GP9 is both J7.3, where the GPS TX lands, and
UART1 RX. Moving the GPS to the Pi routes around the fault with no rework.

| Pi 5 port | Device | Driver / module | Notes |
|---|---|---|---|
| USB-A (1) | Boat Pico | `pi5/comms/pico_serial.py` (CDC ACM, 115200) | Shows up as `/dev/ttyACM0` |
| USB-A (2) | Left USB camera | `pi5/cv/camera.py` (`cv2.VideoCapture(0)`) | 640×480 @ 10 fps |
| USB-A (3) | Right USB camera | `pi5/cv/camera.py` (`cv2.VideoCapture(1)`) | Stereo pair, 120 mm baseline |
| USB-A (4) | SIM7600G-H 4G HAT (or USB-TTL HC-12) | OS-level (`/dev/ttyUSB*`) | Cellular bring-up handled outside this codebase |
| USB-C | Power input — 5 V from logic-domain UBEC | n/a | Sourced from the 1× M18 electronics pack via the 5 V UBEC |
| Internal | WiFi (Pi 5 onboard) | OS-level via NetworkManager / `nmcli` | Configured by `pi5/comms/network.py` when `network.mode` is `wifi` or `auto` |

> **"Where is the GPS connected?"** As of 2026-07-29: the **Pi 5's header UART**
> (GPIO15 ← module TX, `/dev/ttyAMA0` @ 38400) — see the section above. The Boat
> Pico's UART1 GP4/GP5 assignment below is what the *firmware* still does, and it
> reaches no connector; the board routes the GPS to J7.3/J7.4 = GP9/GP8, and GP9 is
> shorted to GND. Everything *else* on the boat still hangs off the Picos.
