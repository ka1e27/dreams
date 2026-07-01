# D.R.E.A.M.S
# GitHub Short Description (paste into the "About" section)

Autonomous catamaran survey boat with edge computing (Pi 5), computer vision obstacle avoidance, cellular IoT connectivity, multi-microcontroller architecture, custom PCB, and cloud-based environmental data mapping.

---

# README.md

# Survey Boat — Autonomous Environmental Survey Platform

An autonomous catamaran that navigates rivers and lakes, avoids obstacles using real-time computer vision, collects environmental sensor data, and streams everything to the cloud over 4G cellular. Missions are planned, uploaded, and monitored remotely from anywhere through a live web dashboard.

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                    CLOUD                             │
│   PostGIS Database ← FastAPI ← Sensor Readings      │
│   Map Viewer (heatmaps, mission playback)            │
└──────────────────────┬──────────────────────────────┘
                       │ HTTPS
┌──────────────────────┴──────────────────────────────┐
│               RASPBERRY PI 5                         │
│                                                      │
│  Navigation Engine ── Mission Manager                │
│        │                                             │
│  CV Pipeline ──── Stereo Depth ── Boat Avoidance    │
│  (Dual USB cameras / OpenCV SGBM / YOLOv8-nano)      │
│        │                                             │
│  FastAPI Server ── WebSocket Telemetry + Camera      │
│        │                                             │
│  Data Uploader ── Local Buffer ── Cloud POST         │
│        │                                             │
│  SIM7600 4G Modem    HC-12 Radio (backup)            │
└──────────┬──────────────────────────────────────────┘
           │ USB Serial
┌──────────┴──────────────────────────────────────────┐
│              BOAT PICO (MicroPython)                 │
│                                                      │
│  VESC UART (master + CAN-forwarded slave)            │
│        │     SBUS RC override (PIO)                  │
│  Winch ESC PWM ── M10Q GPS ── BNO085 IMU             │
│  Triple battery monitor (M18 drive/elec/winch)       │
│  Watchdog ── Pod UART Bridge                         │
└──────────┬──────────────────────────────────────────┘
           │ UART (through slip ring)
┌──────────┴──────────────────────────────────────────┐
│              POD PICO (MicroPython)                   │
│                                                      │
│  EC Salinity Probe ── NTC Thermistor                 │
│  Light Sensor ── Bottom Contact ── Pressure/Depth    │
│  Leak Detection                                      │
└─────────────────────────────────────────────────────┘
```

## Features

- **Autonomous navigation** — u-blox M10Q GPS waypoint following with BNO085 9-axis fused heading
- **Stereo computer vision** — Two USB cameras + StereoSGBM disparity for distance-aware obstacle avoidance; YOLOv8-nano detects nearby boats and steers away when they get within configurable distance
- **VESC propulsion** — Twin VESC drives (master on UART, slave over CAN) replace hobby ESCs, with current-controlled torque, regen, and motor-temperature telemetry
- **Triple-domain M18 batteries** — three fully isolated Milwaukee M18 domains (3× M18 in series for drive, 1× M18 for electronics, 1× M18 for the winch), all monitored on-Pico. See `docs/battery_architecture.md`
- **Real RC override** — SBUS receiver decoded by Pico PIO drives motors directly when the override switch is flipped; SBUS link loss triggers ESTOP
- **Repurposable winch** — Standard PWM ESC on a swappable spool; survey mode for the underwater pod, fishing mode by swapping the spool mechanically
- **Remote operation** — Upload missions, monitor telemetry, and watch the live camera feed from anywhere; choose 4G cellular for autonomous missions or WiFi when the boat is at the dock / on the bench (configurable, with auto-fallback)
- **Environmental mapping** — Georeferenced salinity, temperature, and depth data uploaded to a PostGIS database with heatmap visualization
- **Multi-MCU architecture** — Pi 5 handles compute, Picos handle real-time motor control and sensor acquisition
- **Failsafe systems** — Motor watchdog, HC-12 backup radio, leak detection with auto pod retraction, local data buffering on cellular dropout

## Project Structure

```
survey-boat/
├── pi5/                  # Raspberry Pi 5 software (Python)
│   ├── navigation/       # Waypoint following, obstacle avoidance, mission management
│   ├── cv/               # Dual-camera capture, stereo depth, YOLO detection, avoidance
│   ├── comms/            # Pico serial interface, cellular, HC-12 fallback
│   ├── server/           # FastAPI telemetry server + WebSocket endpoints
│   ├── scripts/          # Utility scripts (stereo calibration, pico deploy)
│   ├── data/             # Cloud data uploader with offline buffering
│   ├── services/         # systemd unit files for auto-start
│   └── tests/            # pytest unit tests
├── firmware/             # Pico firmware (MicroPython)
│   ├── boat-pico/        # VESC drive, GPS, BNO085 IMU, SBUS, serial command handler
│   └── pod-pico/         # Pod sensors, leak detection, UART responder
├── dashboard/            # React web dashboard (Vite + Leaflet + Recharts)
├── cloud/                # Cloud backend
│   ├── api/              # FastAPI + PostGIS sensor data API
│   └── map-viewer/       # Public heatmap visualization app
└── docs/                 # Architecture docs, serial protocol spec, ADRs
```

## Tech Stack

| Layer | Technology |
|---|---|
| Edge compute | Raspberry Pi 5 (Linux) |
| Real-time control | Raspberry Pi Pico (MicroPython) |
| Propulsion | VESC (UART + CAN daisy-chain) |
| Computer vision | OpenCV StereoSGBM, YOLOv8-nano (ultralytics) |
| Inertial | BNO085 (sensor-fused quaternion over I2C) |
| Positioning | u-blox M10Q (NMEA over UART) |
| RC override | SBUS receiver decoded by Pico PIO |
| Connectivity | SIM7600 4G LTE, Pi 5 built-in WiFi (selectable / auto-fallback), HC-12 433MHz (emergency backup) |
| Remote access | Tailscale VPN |
| Boat server | FastAPI, WebSocket, asyncio |
| Dashboard | React, Vite, Leaflet, Recharts |
| Cloud API | FastAPI, SQLAlchemy, PostGIS |
| Cloud hosting | Docker, Railway / Fly.io |
| Database | PostgreSQL + PostGIS |
| CI/CD | GitHub Actions |

## Getting Started

### Simulation (no hardware needed)

```bash
# Clone the repo
git clone git@github.com:yourusername/survey-boat.git
cd survey-boat

# Start the Pi 5 server in simulator mode
cd pi5
pip install -r requirements.txt
python -m server.app

# In another terminal — start the dashboard
cd dashboard
npm install
npm run dev

# In another terminal — start the cloud database
cd cloud
docker compose up -d
cd api
python -m app
```

Open `http://localhost:5173` to access the dashboard. Click the map to place waypoints, upload a mission, and watch the simulated boat navigate in real time.

### Hardware Deployment

1. Flash Raspberry Pi OS to the Pi 5
2. Clone the repo and install dependencies
3. Set `mode: hardware` in `pi5/config.yaml`
4. Flash Pico firmware via `pi5/scripts/deploy_pico.sh`
5. Pick a network transport in `pi5/config.yaml`:
   - `network.mode: wifi` for shore / development work
   - `network.mode: cellular` for autonomous missions (configure SIM7600 + APN)
   - `network.mode: auto` to prefer WiFi when associated and fall back to cellular
   - For WiFi, set `network.wifi.ssid` and `network.wifi.password` to have the
     boot helper configure NetworkManager via `nmcli`, or leave them empty if
     the OS already has WiFi configured
6. Set up Tailscale for remote SSH access
7. Enable systemd services for auto-start on boot

See `docs/` for detailed setup guides.

## Hardware

- Raspberry Pi 5 (4GB or 8GB)
- 2x Raspberry Pi Pico
- 2x VESC (one per propulsion motor; daisy-chained over CAN)
- Standard hobby ESC for the winch (swappable spool — survey pod or fishing reel)
- Waveshare SIM7600G-H 4G HAT + IoT data SIM
- 2x USB wide-angle cameras (stereo pair) for distance-aware obstacle avoidance
- BNO085 9-axis IMU (I2C) — sensor-fused heading + tilt
- u-blox M10Q GPS module (NMEA on UART)
- SBUS-compatible RC receiver (e.g. FrSky / Radiomaster) for manual override
- HC-12 433MHz radio (backup link)
- EC salinity probe, DHT11, NTC thermistor (water), submersible pressure transducer
- 3D-printed PLA catamaran hull (sealed with marine epoxy)
- 3× Milwaukee M18 (drive, series) + 1× M18 (electronics) + 1× M18 (winch), three isolated domains, monitored independently
- 4-conductor slip ring for underwater pod tether

## License

MIT
