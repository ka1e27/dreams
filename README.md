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
│  CV Pipeline ──── Obstacle Avoidance                 │
│  (OpenCV / YOLOv8-nano)                              │
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
│  Motor Control (ESC PWM) ── GPS ── Compass           │
│  Watchdog ── Pod UART Bridge                         │
└──────────┬──────────────────────────────────────────┘
           │ UART (through slip ring)
┌──────────┴──────────────────────────────────────────┐
│              POD PICO (MicroPython)                   │
│                                                      │
│  EC Salinity Probe ── DHT11 ── NTC Thermistors       │
│  Leak Detection                                      │
└─────────────────────────────────────────────────────┘
```

## Features

- **Autonomous navigation** — GPS waypoint following with compass heading correction
- **Computer vision** — Real-time obstacle detection and avoidance using OpenCV and YOLOv8-nano
- **Remote operation** — Upload missions, monitor telemetry, and watch the live camera feed from anywhere over 4G cellular
- **Environmental mapping** — Georeferenced salinity, temperature, and depth data uploaded to a PostGIS database with heatmap visualization
- **Multi-MCU architecture** — Pi 5 handles compute, Picos handle real-time motor control and sensor acquisition
- **Custom PCB** — KiCad-designed carrier board with power regulation, sensor connectors, and status LEDs
- **Failsafe systems** — Motor watchdog, HC-12 backup radio, leak detection with auto pod retraction, local data buffering on cellular dropout

## Project Structure

```
survey-boat/
├── pi5/                  # Raspberry Pi 5 software (Python)
│   ├── navigation/       # Waypoint following, obstacle avoidance, mission management
│   ├── cv/               # Camera capture, water segmentation, YOLO detection
│   ├── comms/            # Pico serial interface, cellular, HC-12 fallback
│   ├── server/           # FastAPI telemetry server + WebSocket endpoints
│   ├── data/             # Cloud data uploader with offline buffering
│   ├── services/         # systemd unit files for auto-start
│   └── tests/            # pytest unit tests
├── firmware/             # Pico firmware (MicroPython)
│   ├── boat-pico/        # Motor control, GPS, compass, serial command handler
│   └── pod-pico/         # Sensor reading, leak detection, UART responder
├── dashboard/            # React web dashboard (Vite + Leaflet + Recharts)
├── cloud/                # Cloud backend
│   ├── api/              # FastAPI + PostGIS sensor data API
│   └── map-viewer/       # Public heatmap visualization app
├── pcb/                  # KiCad schematic and PCB layout
└── docs/                 # Architecture docs, serial protocol spec, ADRs
```

## Tech Stack

| Layer | Technology |
|---|---|
| Edge compute | Raspberry Pi 5 (Linux) |
| Real-time control | Raspberry Pi Pico (MicroPython) |
| Computer vision | OpenCV, YOLOv8-nano |
| Connectivity | SIM7600 4G LTE, HC-12 433MHz (backup) |
| Remote access | Tailscale VPN |
| Boat server | FastAPI, WebSocket, asyncio |
| Dashboard | React, Vite, Leaflet, Recharts |
| Cloud API | FastAPI, SQLAlchemy, PostGIS |
| Cloud hosting | Docker, Railway / Fly.io |
| Database | PostgreSQL + PostGIS |
| PCB design | KiCad → JLCPCB |
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
5. Configure the SIM7600 cellular modem
6. Set up Tailscale for remote SSH access
7. Enable systemd services for auto-start on boot

See `docs/` for detailed setup guides.

## Hardware

- Raspberry Pi 5 (4GB or 8GB)
- 2x Raspberry Pi Pico
- Waveshare SIM7600G-H 4G HAT + IoT data SIM
- USB wide-angle camera
- QMC5883P compass (I2C)
- GPS module (NMEA)
- HC-12 433MHz radio
- EC salinity probe, DHT11, NTC thermistors
- Custom PCB (KiCad, fabricated via JLCPCB)
- 3D-printed PLA catamaran hull (sealed with marine epoxy)
- 3S LiPo batteries (separate for propulsion and electronics)
- 4-conductor slip ring for underwater pod tether

## License

MIT
