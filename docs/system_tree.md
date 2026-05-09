# System Tree

Complete component tree for **D.R.E.A.M.S** — sensors, actuators, compute,
and power domains. Solid borders mark present components; dashed borders
mark planned / future / mode-swap components.

Sourced from `README.md` and the pin-map docstrings in
`firmware/boat-pico/main.py` and `firmware/pod-pico/main.py`.

```mermaid
flowchart TB
    %% =========================================================
    %% POWER DOMAINS
    %% =========================================================
    subgraph PowerProp["⚡ 12S LiPo — Propulsion Power Domain (50.4 V nom)"]
        direction LR
        BATT12["12S LiPo<br/>50.4 V · 12000 mAh"]
        BATT12 -->|"XT90 + fuse"| VESCM
        BATT12 -->|"XT60"| VESCS
    end

    subgraph Power6S["⚡ 6S Midpoint Tap (25.2 V nom)"]
        direction LR
        TAP6S[("6S Balance-Lead Tap<br/>cell-6 / cell-7 junction")]
        TAP6S -->|"XT30"| WESC
    end

    subgraph PowerLogic["⚡ 3S Li-ion — Logic Power Domain (12.6 V nom)"]
        direction LR
        BATT3["3S Li-ion<br/>12.6 V · 5000 mAh"]
        BATT3 -->|"5 V buck"| PI5
        BATT3 -->|"3.3 V buck"| BPI
        BATT3 -->|"5 V buck"| HC12
        BATT3 -->|"5 V"| RCRX
        BATT3 -.->|"5 V"| SIM
        BATT3 -.->|"slip ring 5 V"| PPI
    end

    %% =========================================================
    %% SEALED ELECTRONICS BAY
    %% =========================================================
    subgraph Bay["🛡 Sealed Electronics Bay"]
        direction TB
        PI5["Raspberry Pi 5<br/>4 / 8 GB"]
        BPI["Boat Pico<br/>RP2040"]
        BNO["BNO085 IMU<br/>I²C 0x4A"]
        HC12["HC-12 433 MHz<br/>backup radio"]
        SIM["SIM7600G-H 4G HAT"]

        PI5 ==>|"USB CDC<br/>115200 bd"| BPI
        PI5 -.->|"USB 2.0"| SIM
        PI5 -.->|"UART or USB-TTL"| HC12
        BPI ==>|"I²C0 SH-4<br/>GP8/9 @ 400 kHz"| BNO
    end

    %% =========================================================
    %% SENSORS — boat-side
    %% =========================================================
    subgraph BoatSensors["Boat-Side Sensors"]
        direction TB
        GPS["u-blox M10Q GPS<br/>NMEA 9600 bd"]
        DHT["DHT11<br/>air temp / RH"]
        HULL_L["Hull leak L<br/>contact, active-low"]
        HULL_R["Hull leak R<br/>contact, active-low"]
        BMON_P["12S divider<br/>3.3 / 47 kΩ"]
        BMON_E["3S divider<br/>15 / 100 kΩ"]
    end

    BPI ==>|"UART1 PH-4<br/>GP4/5 @ 9600"| GPS
    BPI -->|"1-wire GP16"| DHT
    BPI -->|"GPIO GP17 PH-2"| HULL_L
    BPI -->|"GPIO GP18 PH-2"| HULL_R
    BPI -->|"ADC0 GP26"| BMON_P
    BPI -->|"ADC1 GP27"| BMON_E
    BMON_P -.->|"sense"| BATT12
    BMON_E -.->|"sense"| BATT3

    %% =========================================================
    %% RC OVERRIDE
    %% =========================================================
    RCRX["SBUS Receiver<br/>(FrSky / Radiomaster)"]
    BPI <==|"PIO software UART<br/>GP15 inverted"| RCRX

    %% =========================================================
    %% PROPULSION
    %% =========================================================
    subgraph Propulsion["Propulsion"]
        direction LR
        VESCM["VESC Master<br/>(left hull)"]
        VESCS["VESC Slave<br/>(right hull)"]
        MOT_L["Brushless<br/>Left Motor"]
        MOT_R["Brushless<br/>Right Motor"]
        VESCM -->|"3-phase"| MOT_L
        VESCS -->|"3-phase"| MOT_R
        VESCM <==>|"CAN-H/L<br/>120 Ω term"| VESCS
    end

    BPI ==>|"UART0 PH-4<br/>GP12/13 @ 115200"| VESCM
    VESCM -.->|"telemetry over UART<br/>motor temp / RPM / fault"| BPI

    %% =========================================================
    %% WINCH (survey + future fishing)
    %% =========================================================
    WESC["Winch ESC<br/>50 Hz hobby PWM"]
    WMOT["Winch Motor"]
    BPI ==>|"PWM servo-3<br/>GP14 @ 50 Hz"| WESC
    WESC -->|"3-phase"| WMOT
    SPOOL_S["Survey Spool<br/>(pod tether)"]
    SPOOL_F["Fishing Reel Spool"]
    WMOT --> SPOOL_S
    WMOT -.->|"manual swap"| SPOOL_F

    %% =========================================================
    %% UNDERWATER POD
    %% =========================================================
    SLIPRING["4-conductor<br/>Slip Ring"]
    SPOOL_S ==>|"tether<br/>2× pwr + 2× UART"| SLIPRING
    BPI <==>|"UART1 shared bus<br/>$POD lines via PIO mux"| SLIPRING

    subgraph Pod["💧 Underwater Sensor Pod"]
        direction TB
        PPI["Pod Pico<br/>RP2040"]
        WTEMP["Water Temp<br/>NTC 10 kΩ"]
        EC["EC Salinity Probe<br/>2-electrode"]
        LIGHT["Photoresistor"]
        BTM["Bottom Contact<br/>microswitch"]
        PRESS["Pressure Transducer<br/>0.5–4.5 V → 0–15 psi"]
        LEAK["Pod Leak Sensor"]
    end

    SLIPRING ==> PPI
    PPI -->|"ADC0 GP26"| WTEMP
    PPI -->|"GP17 drive + ADC1 GP27"| EC
    PPI -->|"ADC2 GP28"| LIGHT
    PPI -->|"GPIO GP21"| BTM
    PPI -->|"ADC GP22"| PRESS
    PPI -->|"GPIO GP20"| LEAK

    %% =========================================================
    %% PERCEPTION (USB to Pi 5)
    %% =========================================================
    subgraph Cameras["Stereo Camera Mast"]
        direction LR
        CAM_L["USB Camera L"]
        CAM_R["USB Camera R"]
    end
    PI5 ==>|"USB 2.0"| CAM_L
    PI5 ==>|"USB 2.0"| CAM_R

    %% =========================================================
    %% CONNECTIVITY (cloud-side)
    %% =========================================================
    subgraph Cloud["☁ Cloud / Shore"]
        direction LR
        WIFI["WiFi AP<br/>(dock / dev)"]
        CELL["4G Tower<br/>(SIM)"]
        DASH["React Dashboard"]
        API["FastAPI + PostGIS"]
    end
    PI5 -.->|"WiFi (Pi 5 internal)"| WIFI
    SIM ==>|"LTE"| CELL
    WIFI ==>|"HTTPS"| API
    CELL ==>|"HTTPS"| API
    API ==> DASH

    %% =========================================================
    %% STYLING
    %% =========================================================
    classDef future stroke-dasharray:6 4,stroke:#888,color:#666
    classDef compute fill:#1e293b,stroke:#7dd3fc,stroke-width:2px,color:#e0f2fe
    classDef sensor fill:#0f172a,stroke:#14b8a6,color:#ccfbf1
    classDef actuator fill:#1e1b4b,stroke:#f59e0b,color:#fde68a
    classDef power fill:#1c0f0f,stroke:#ef4444,color:#fee2e2
    classDef bay fill:transparent,stroke:#7dd3fc,stroke-dasharray:6 3,stroke-width:2px

    class SPOOL_F,SLIPRING,LEAK future
    class PI5,BPI,PPI compute
    class GPS,BNO,DHT,HULL_L,HULL_R,BMON_P,BMON_E,WTEMP,EC,LIGHT,BTM,PRESS sensor
    class VESCM,VESCS,MOT_L,MOT_R,WESC,WMOT actuator
    class BATT12,BATT3,TAP6S power
```

## Power Distribution

| Domain | Source | Nominal | Loads |
|---|---|---|---|
| **12S Propulsion** | 12S LiPo | 50.4 V | VESC master, VESC slave, both brushless motors |
| **6S Midpoint Tap** | Cell-6/7 balance-lead junction of the 12S | 25.2 V | Winch ESC (chosen so a hobby-grade ESC sees a sane voltage instead of the full 12S) |
| **3S Logic** | 3S Li-ion (isolated from propulsion) | 12.6 V | Pi 5 (5 V buck), both Picos (3.3 V buck), HC-12, SBUS RX, SIM7600 HAT, pod via slip-ring |

Isolating logic onto its own pack stops motor brownouts and switching noise
from corrupting the Pi 5's USB host or browning out the BNO085 mid-rotation.

## Edge legend

- **Thick (`==>`)** — high-rate streaming connection (telemetry, motor command, video frame).
- **Thin (`-->`)** — periodic / event-driven.
- **Dashed (`-.->`)** — optional or future link, or a sense-only path that doesn't carry power.

## Future / mode-swap components

| Component | Status | Notes |
|---|---|---|
| Fishing reel spool | mode swap | Mechanical replacement for the survey-pod tether spool. No firmware change; `winch.mode` in `pi5/config.yaml` flips the dashboard label. |
| Pod leak sensor | future | Wired in firmware (`firmware/pod-pico/leak_detect.py`) but the physical sensor element is a planned add. |
| Slip-ring assembly | future | 4-conductor slip ring on order; until installed, the pod tether is hand-passed and missions skip continuous streaming. |
