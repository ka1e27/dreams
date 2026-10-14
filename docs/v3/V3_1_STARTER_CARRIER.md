# V3.1 starter carrier

An interim board to get the boat moving before the full V3 carrier. It keeps the Pi 5 and the Pololu
5 V buck, swaps the Teensy for one Raspberry Pi Pico 2, and leaves out what the first trials don't
need: current sensing, the I²C mux and its sensors, the radar stepper and the winch kill. The full V3
carrier now uses two Picos as well (rev E, 2026-10-13, with its own pin map), and this board keeps a
header for a second one.

- **Files:** `Boat_PCB/Boat_PCB_V3_1/`, KiCad 10. It uses the shared library in `Boat_PCB/lib/`.
- **Board:** 98 × 67 mm, 2 layers, 1.6 mm FR-4, GND poured on both sides. The tall parts (the Pico,
  both Pololu modules, the 2nd-Pico header and every capacitor), the SMD parts and the SHT41 module are
  on the underside, so nothing under the Pi is taller than about 9 mm. 75 footprints (21 underneath),
  rev A, 2026-10-12.
- **Checks:** ERC 0, DRC 0, 0 unconnected, schematic parity 0 (commands in `CLAUDE.md`).

## Power

One 10S Li-ion pack (30–42 V) runs the whole boat: the drive VESCs take it directly, the winch goes
through its own off-board buck, and this board takes it on J1.

- **Input:** J1 (XT60, notch = negative) → F1 (2 A time-lag TR5 fuse; fit a TR5 socket so it can be
  swapped) → Q1 (IRF9540N reverse-polarity P-FET, D1 15 V gate zener, R1) → D2 (SMBJ43A TVS) and C1
  (100 µF 63 V).
- **Why Q1:** the D36V50F5's own reverse protection only covers 40 V, and a full 10S pack is 42 V.
- **Pack voltage:** R2/R3 (100k / 7.5k) into ADC0, with C2 at the pin. V_pack = V_adc × 14.33, so
  42 V reads 2.93 V and full scale (3.3 V) is 47.3 V.
- **5 V:** U1 (Pololu D36V50F5, 5.5 A) feeds the Pi 5 through header pins 2 and 4, the Pico's VSYS
  through D3 (B5819W), the GPS, the RC receiver (through F3, 0.75 A), the CAN transceiver and the
  2nd-Pico header. C3 (470 µF) is the bulk.
- **Why the 5 V feed takes a detour:** the Pi's 5 V pins are on the socket's outer row, and the inner
  row (3V3, GPIO2/3) can't be crossed. So the feed runs round the socket's left end and comes into
  pins 2/4 from the board edge: 1.3 mm of copper on both layers, about 5.8 A at a 10 °C rise.
- **3.3 V:** the Pico's own 3V3 pin (about 300 mA available) feeds the SHT41, the Qwiic sensors, the
  I²C pull-ups, the RS-485 transceiver and the CAN transceiver's logic side.
- **Pod:** U2 (Pololu D36V6F15, 600 mA, on the underside) makes 15 V for the tether. It has no fuse of its own, since
  the regulator's over-current, short-circuit and thermal protection already cover a tether fault.
  The pod takes 12–21 V and has a 24 V TVS at its input, so it must never see the pack.

## What else is on it

- **Pi 5:** face down on the 40-pin socket and its four standoff holes (30 mm standoffs), with the
  USB and Ethernet end at the board's right edge. The header carries power only. The Pi talks to the
  Pico over a USB cable, which also flashes it.
- **Pi cooling:** face down, the Pi's SoC faces the board. Only short parts are left under it (about
  9 mm at most), so on 30 mm standoffs there's about 20 mm for a heatsink or cooler.
- **Pico 2:** socketed on the underside, hanging under the board, so a Pico, Pico 2 or a W variant
  fits; the W's antenna keep-out is kept clear. Its USB end faces the right edge, under the Pi's USB
  ports, so a short cable reaches the Pi. Its BOOTSEL button faces down and stays in reach.
  Ten flat resistors sit between its socket rows on top. Underneath, nothing but the 1 mm VSYS diode
  D3 and those resistors' trimmed leads sit between the board and the Pico, so it also fits soldered
  straight on its own headers instead of the 8.5 mm sockets.
- **CAN:** U4 (TJA1051T/3) on GP10/GP11, driven by can2040 on the PIO. J3 and J4 are the same bus,
  for daisy-chaining the VESCs. Fit JP1 to switch in the 120 Ω terminator R5. D5 is a NUP2105L TVS.
- **Pod tether (J5):** RS-485 through U5 (THVD2410) with DE and ~RE together on GP2, R6 holding it in
  receive and R7 terminating this end, plus the 15 V feed. Same pin order as the pod's J1. GP19 high
  switches the pod off: Q2 pulls U2's SHDN low, and R8 keeps the pod on while the Pico boots.
- **GPS (J6):** UART on a PIO UART (GP6 TX, GP7 RX, 1 kΩ series) and its built-in compass on I²C0.
  Fed 5 V.
- **SHT41 (J8):** a Teyleten Robot GY-SHT41-D module for the hull air. It's soldered straight onto
  the carrier's underside on its 4-pin 0.1 in header under the top-left corner, sensor side down,
  away from the Pi's heat. It has no regulator, so VIN goes to 3V3: the SHT41 is 3.6 V max, and the
  module's 10k pull-ups then sit at the Pico's 3.3 V.
- **Qwiic (J9, J10):** I²C0 at 3.3 V for the TMP119 breakout (water, potted on its cable) and a
  spare. Addresses: SHT41 0x44, TMP119 0x48, compass 0x0D, 0x0E or 0x1E, so one bus is enough.
- **RC (J7):** SBUS, inverted by the Pico's UART with no extra chip, or CRSF/ELRS, on UART1.
- **Hull leak (J11, J12):** excited probes. LEAK_EXC (GP18) feeds each probe through 100 kΩ, and ADC1
  and ADC2 read them through 1 kΩ.
- **ESC headers:** J13 (winch) and J15/J16 (drive L/R, a fallback if the drive isn't on CAN).
  Servo-style, signal through 330 Ω, middle pin open so an ESC's BEC can't back-feed the 5 V rail.
- **Winch home switch (J14):** 10 kΩ pull-up, then 1 kΩ and 100 nF into GP17.
- **2nd-Pico header (J17, 2×7, underside):** 5 V, 3V3, GND, I²C0, a UART pair on GP20/21 and GP3,
  GP12, GP13, GP22. It sits 3 mm below the Pico's socket, so a 2×7 IDC ribbon plug fits. Its pin
  legend is on the top side, round its solder joints.
- **SW1:** resets the Pico. It's under the Pi's USB end, at the board's top edge. Hold BOOTSEL (under
  the board) and tap SW1 for the UF2 bootloader; Arduino-Pico can also reboot the Pico into it over
  USB.

## Layout

The XT60, every JST-XH and the ESC headers are top-entry and sit outside the Pi, so their cables
plug in with the Pi fitted. The Qwiic ports are under the Pi's USB end on the right edge and take their
cables from the side. The 2nd-Pico header (J17) and the Pico's USB port are on the underside.

- **Left edge:** RC (J7) and GPS (J6), then the XT60 (J1) in the corner.
- **Bottom edge:** F1, then leak L/R, the winch home switch, CAN A/B, the pod tether and the three ESC
  headers.
- **Beside the left edge, just outside the Pi:** Q1, the RC fuse F3 and the pack test point TP4, in
  the column between the connectors and U1.
- **Under the Pi, on top:** only short parts. These are the Pico's resistor bank, the pack divider,
  the CAN terminator jumper, reset, the 5 V LED, TP1–TP3 and TP5, the RS-485 and ESC resistors,
  and the Qwiic ports on the right edge. Use a 6 × 6 mm tact switch no taller than about 9 mm for SW1.
- **Underside:** the Pico, with its USB end toward the right edge, and U1 at the left, just above the
  Pi socket's left end, with its VOUT pins nearest the Pi's 5 V pins. U2 (the 15 V pod regulator),
  the 2nd-Pico header J17, all nine capacitors, the SHT41 module under the top-left corner and the SMD
  parts are here too. Apart from the 1 mm diode D3, none of them sit under the Pico. C1 is
  the tallest (up to 20 mm); the Pico with its USB plug in reaches about 17 mm. Mount the carrier at
  least 22 mm off whatever it sits on.

## Pico pin map

| Pin | GPIO | Use | Pin | GPIO | Use |
|---|---|---|---|---|---|
| 1 | GP0 | RS-485 TX (UART0) | 21 | GP16 | Winch ESC PWM |
| 2 | GP1 | RS-485 RX (UART0) | 22 | GP17 | Winch home switch |
| 4 | GP2 | RS-485 DE + ~RE | 24 | GP18 | Leak excite |
| 5 | GP3 | 2nd-Pico header | 25 | GP19 | Pod power off (high = off) |
| 6 | GP4 | I²C0 SDA | 26 | GP20 | 2nd-Pico UART TX (PIO) |
| 7 | GP5 | I²C0 SCL | 27 | GP21 | 2nd-Pico UART RX (PIO) |
| 9 | GP6 | GPS TX (PIO UART) | 29 | GP22 | 2nd-Pico header |
| 10 | GP7 | GPS RX (PIO UART) | 30 | RUN | SW1 reset |
| 11 | GP8 | RC TX (UART1) | 31 | GP26 / ADC0 | Pack voltage |
| 12 | GP9 | RC RX (UART1) | 32 | GP27 / ADC1 | Leak L |
| 14 | GP10 | CAN RX (can2040) | 34 | GP28 / ADC2 | Leak R |
| 15 | GP11 | CAN TX (can2040) | 36 | 3V3 | Sensor and transceiver 3.3 V |
| 16 | GP12 | 2nd-Pico header | 39 | VSYS | 5 V through D3 |
| 17 | GP13 | 2nd-Pico header | 40 | VBUS | Not connected |
| 19 | GP14 | Drive L ESC PWM | 35, 37 | ADC_VREF, 3V3_EN | Not connected |
| 20 | GP15 | Drive R ESC PWM | | | |

## Connectors

| Ref | Name | Pins |
|---|---|---|
| J1 | 10S pack in (XT60) | 1 −, 2 + |
| J3, J4 | CAN A, CAN B (JST-XH 3) | 1 CANH, 2 CANL, 3 GND |
| J5 | Pod tether (JST-XH 4) | 1 GND, 2 +15 V, 3 RS-485 A, 4 RS-485 B |
| J6 | GPS (JST-XH 6) | 1 TX (from the GPS), 2 RX (to the GPS), 3 GND, 4 5 V, 5 SCL, 6 SDA |
| J7 | RC receiver (JST-XH 4) | 1 GND, 2 5 V, 3 RX (receiver SBUS or CRSF TX), 4 TX (receiver CRSF RX) |
| J8 | SHT41 module, GY-SHT41-D (0.1 in, underside) | 1 VIN (3V3), 2 GND, 3 SCL, 4 SDA |
| J9, J10 | Qwiic (JST-SH 4) | 1 GND, 2 3V3, 3 SDA, 4 SCL |
| J11, J12 | Hull leak L, R (JST-XH 2) | 1 GND, 2 probe |
| J13, J15, J16 | Winch, drive L, drive R ESC (0.1 in) | 1 signal, 2 open, 3 GND |
| J14 | Winch home switch (JST-XH 2) | 1 GND, 2 switch |
| J17 | 2nd Pico (2×7, 0.1 in, underside) | 1/2 5 V, 3/4/6 GND, 5 3V3, 7 SDA, 8 SCL, 9 TX, 10 RX, 11 GP3, 12 GP12, 13 GP13, 14 GP22 |

The back silkscreen carries the same pin legend beside every connector.

## Before the first power-up

1. **Continuity-check the Pi socket:** pads 2 and 4 must land on the Pi's 5 V pins. The socket
   footprint's column order was set from a real board and was transposed once on V2. Backwards, it
   puts 5 V on the Pi's 3V3 rail.
2. Fit F1 in a TR5 socket, and check J1's polarity (XT60 notch = negative).
3. Check that the GPS module pulls its I²C lines up to 3.3 V, not 5 V. The Pico isn't 5 V tolerant.
4. First power-up without the Pi: 5 V at TP2, 3.3 V at TP3 with the Pico fitted, 15 V on J5 pin 2.
5. Solder the SHT41 module on last, sensor side down, with the column marked SDA, SCL, GND, VIN on the
   back silkscreen. Never feed it 5 V: it has no regulator.
6. Never power the Pi from this board and from its own USB-C at the same time.

## Firmware notes

- C++ with Arduino-Pico or the Pico SDK. On the RP2350, can2040 needs Pico SDK 2.0 or later.
- **SBUS:** 100 kbaud, 8E2, inverted. Invert RX on GP9 in the GPIO block (`gpio_set_inover`).
- **Leak:** drive GP18 high, wait about 10 ms, read ADC1 and ADC2, then drive it low again. A probe
  held at DC corrodes.
- **Pod power:** GP19 low (the default, held by R8) keeps the pod on; high switches it off.
- **RS-485:** drive GP2 high to transmit; R6 holds the transceiver in receive otherwise.
