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
    subgraph PowerProp["⚡ Drive Domain — 3× M18 series (54 V nom / 63 V max)"]
        direction LR
        BATT12["3× M18 series<br/>54 V nom"]
        BATT12 -->|"200A ANL → XT90"| VESCM
        BATT12 -->|"100A ANL → XT90"| VESCS
    end

    subgraph Power6S["⚡ Winch Domain — 1× M18 (18 V nom)"]
        direction LR
        TAP6S[("1× M18 winch pack<br/>dedicated, isolated")]
        TAP6S -->|"20A blade → MOSFET kill"| WESC
    end

    subgraph PowerLogic["⚡ Electronics Domain — 1× M18 (18 V nom)"]
        direction LR
        BATT3["1× M18<br/>18 V nom"]
        BATT3 -->|"15A blade → 5 V UBEC"| PI5
        BATT3 -->|"3.3 V"| BPI
        BATT3 -->|"5 V"| HC12
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
        BMON_P["Drive divider<br/>200k / 10k (×21)"]
        BMON_E["Elec divider<br/>56k / 10k (×6.6)"]
        BMON_W["Winch divider<br/>56k / 10k (×6.6)"]
    end

    BPI ==>|"UART1 PH-4<br/>GP4/5 @ 9600"| GPS
    BPI -->|"1-wire GP16"| DHT
    BPI -->|"GPIO GP17 PH-2"| HULL_L
    BPI -->|"GPIO GP18 PH-2"| HULL_R
    BPI -->|"ADC0 GP26"| BMON_P
    BPI -->|"ADC1 GP27"| BMON_E
    BPI -->|"ADC2 GP28"| BMON_W
    BMON_P -.->|"sense"| BATT12
    BMON_E -.->|"sense"| BATT3
    BMON_W -.->|"sense"| TAP6S

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
| **Drive** | 3× M18 in series | 54 V nom (63 V max) | VESC master, VESC slave, both brushless motors |
| **Winch** | 1× M18 standalone (dedicated, isolated) | 18 V nom | Winch ESC → 2006 motor, via a MOSFET kill switch |
| **Electronics** | 1× M18 standalone (isolated from drive) | 18 V nom | Pi 5 (5 V UBEC), both Picos (3.3 V), HC-12, SBUS RX, SIM7600 HAT, pod via slip-ring |

Three fully isolated M18 domains (no shared ground except the logic-PCB star point) stop motor
brownouts and switching noise from corrupting the Pi 5's USB host or browning out the BNO085
mid-rotation, and give the winch its own supply instead of tapping the drive midpoint.

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
