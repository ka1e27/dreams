# Hardware Changes: V1 → V2

## Summary Table

| Component | V1 | V2 |
|-----------|----|----|
| Brain | 3× Raspberry Pi Pico (MicroPython) | Pi 5 (brain) + Boat Pico (executor) + Pod Pico (underwater) |
| Drive motors | Bilge pump thrusters | 2× brushless outrunners, IP-rated, one per hull |
| ESCs | None | 2× VESC-based ESCs |
| ESC comms | PWM from Pico GPIO | UART0 (GP12/13) → VESC master; slave via CAN-forward |
| Battery (drive) | 3S/4S LiPo | 2× 6S LiPo in series = 12S (BT2 + BT3) |
| Battery (electronics) | Same pack | Separate 3S Li-ion (BT1) |
| Battery (winch) | 5V servo rail | Dedicated 4S LiPo (BT4) — see winch-supply note below |
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

## Battery System: Isolated Packs

| Pack | Ref | Connector | Rail |
|------|-----|-----------|------|
| 6S LiPo A | BT2 | XT60 | 12S drive (in series with BT3) |
| 6S LiPo B | BT3 | XT60 | 12S drive (in series with BT2) |
| 3S Li-ion | BT1 | XT60 | Electronics (Pi 5, Picos, sensors) |
| 4S LiPo | BT4 | XT30 | Winch — see note below |

### Battery monitoring — PCB vs firmware (known discrepancy)
- **PCB (`Boat_PCB`):** divider taps 12S via R2/R4 (220k/13k → GP26), 3S via R5/R6 (100k/30k → GP27),
  and **4S winch via R8/R10 (100k/18k → GP28 ADC2)**.
- **Firmware (`firmware/boat-pico/sensors.py`):** monitors only the 12S (divider 3.3k/47k, GP26) and
  3S (divider 15k/100k, GP27) rails. **GP28 is left as spare** — the 4S winch sense circuit on the
  PCB is not read in code, and the divider values differ from the PCB. Unreconciled; flagged here.

### Winch supply (known discrepancy)
The reference notes claimed "the 12S midpoint (25.2V) is never used; BT4 is a fully separate pack."
However, the PCB also carries a **J6 "6s output"** connector and `docs/system_tree.md` depicts a
**6S midpoint tap → winch ESC**. Whether the winch runs from BT4 or a 6S midpoint tap is unresolved.

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
