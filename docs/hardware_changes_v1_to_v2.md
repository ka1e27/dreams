# Hardware Changes: V1 → V2

## Summary Table

| Component | V1 | V2 |
|-----------|----|----|
| Brain | 3× Raspberry Pi Pico (MicroPython) | Pi 5 (brain) + Boat Pico (executor) + Pod Pico (underwater) |
| Drive motors | Bilge pump thrusters | 2× brushless outrunners, IP-rated, one per hull |
| ESCs | None | 2× VESC-based ESCs |
| ESC comms | PWM from Pico GPIO | UART0 (GP12/13) → VESC master; slave via CAN-forward |
| Battery (drive) | 3S/4S LiPo | 3× Milwaukee M18 in series (54 V nom) — see battery note below |
| Battery (electronics) | Same pack | Separate 1× M18 pack |
| Battery (winch) | 5V servo rail | Dedicated 1× M18 pack (no drive-midpoint tap) |
| Winch motor | Hobby servo | Brushless + planetary gearbox, PWM from GP14 |
| Radio (primary) | HC-12 433MHz | **SIM7600G-H 4G cellular** (+ Pi 5 WiFi at the dock) |
| Radio (backup) | — | HC-12 retained as an optional USB-TTL dongle on the Pi 5 |
| GPS | NEO-6M UART | u-blox M10Q UART1 (GP4/5) |
| IMU / Compass | QMC5883P I²C 0x2C | **BNO085 I²C0 @ 0x4A (GP8/9)** |
| Camera | None | 2× USB cameras (stereo pair via Pi 5 USB-A) |
| Shore station | Shore Pico + HC-12 | Pi 5 server + WebSocket over cellular/WiFi |

---

## Compass Change: QMC5883P → BNO085

V1 used a QMC5883P magnetometer at I²C address 0x2C on the Boat Pico.

V2 uses a **BNO085** 9-DOF IMU at I²C address **0x4A**, on I²C0 (GP8/GP9) via J7 or J10. The firmware
module is `firmware/boat-pico/compass.py` — it now drives a BNO085, not a QMC5883P. Calibration
offsets from V1 do **not** carry over; the BNO085 uses a different register set and onboard fusion.

---

## Radio: HC-12 Demoted to Optional USB Backup

V1: HC-12 433MHz on the Shore Pico, range ~1km open field, primary link.

V2: HC-12 is **removed from the PCB** and from the old Shore-Pico architecture. The boards have no
HC-12 connector. It survives only as an **optional emergency backup** — a USB-TTL HC-12 dongle on a
Pi 5 USB-A port, as an alternative to the SIM7600 (see `docs/pin_map.md`, which lists USB-A (4) as
"SIM7600G-H 4G HAT (or USB-TTL HC-12)").

Primary shore communication is now:
- SIM7600G-H 4G LTE — Pi 5 FastAPI server reachable over the internet
- Pi 5 onboard WiFi at the dock
- Tailscale VPN for SSH from anywhere
- React dashboard over WebSocket

---

## ESC Communication: PWM → UART (not CAN HAT)

The schematic shows J2 labeled "CAN chain" — a 7-pin 2.54mm header on Boat Pico GP12/13 (UART0). This
is a **UART connection to the VESC master**; the master forwards commands to the VESC slave over its
own CAN bus (`COMM_FORWARD_CAN`).

There is **no MCP2515 CAN HAT**. The Pi 5 does not talk CAN. The Boat Pico sends UART commands to the
VESC master, handled by `firmware/boat-pico/vesc.py`.

---

## Cameras: USB, Not CSI

Two USB cameras connect to Pi 5 USB-A ports:
- Left: `cv2.VideoCapture(0)` → stereo pair
- Right: `cv2.VideoCapture(1)` → stereo pair, ~120mm baseline

No CSI cameras, no Pi Camera, no camera HAT. The Pi 5 40-pin header is unused.

---

## Battery System: Three Isolated M18 Domains

The current design uses three fully isolated Milwaukee M18 domains (no shared ground except the
logic-PCB star point). This supersedes the earlier LiPo/Li-ion multi-pack design. Full spec in
**`docs/battery_architecture.md`**.

| Domain | Packs | Voltage (nom/max) | Rail |
|--------|-------|-------------------|------|
| Drive | 3× M18 in series | 54 V / 63 V | Both VESCs + brushless motors |
| Electronics | 1× M18 | 18 V / 21 V | Pi 5, Picos, GPS, compass, radio, camera |
| Winch | 1× M18 | 18 V / 21 V | Winch ESC + 2006 motor |

### Battery monitoring (firmware + docs migrated)
All three rails are monitored on the Boat Pico ADCs:
- Drive **200k/10k** (×21.0, 63 V → 3.00 V) → GP26
- Electronics **56k/10k** (×6.6, 21 V → 3.18 V) → GP27
- Winch **56k/10k** (×6.6) → GP28

`firmware/boat-pico/sensors.py`, the Pi 5 simulator, and the dashboards use these values. The
**KiCad schematic still carries the old divider resistors** and must be reworked to match — this is
the only remaining open item from the migration.

### Winch supply — resolved
The winch is now a **dedicated standalone M18 pack**. The old ambiguity between a dedicated 4S pack
and a 12S/6S-midpoint tap is gone; there is no midpoint tap in this design.

---

## What Stayed the Same

- Boat Pico as motor/sensor controller (MicroPython + uasyncio)
- HC-12 XOR-checksum framing **style** — reused for the new USB serial protocol
- Haversine GPS navigation math (ported to Python 3 on the Pi 5, `pi5/navigation/geo.py`)
- Hull-leak detection wiring (GPIO pull-up, active-low contacts, GP17/GP18)
- Bottom-contact microswitch concept (Pod Pico GP21)
- Mission concept: TRANSIT → WINCH → SAMPLE loop
- Winch time-based depth estimation (AS5600 still dead, not replaced)
- GP0/GP1 dead on the Boat Pico — do not use
