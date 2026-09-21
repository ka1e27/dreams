# Contributing

## Branching Strategy

We use **GitHub Flow** — simple feature branches off `main`.

```
main (protected, always deployable)
  ├── feature/pi5-cv-obstacle       → PR → merge to main
  ├── fix/gps-stale-timeout         → PR → merge to main
  └── firmware/pod-leak-threshold   → PR → merge to main
```

### Rules

- `main` is protected — direct pushes are blocked
- All changes go through Pull Requests
- CI must pass before merging
- At least one review is recommended for non-trivial changes

### Branch naming

| Prefix | Use |
|--------|-----|
| `feature/` | New functionality |
| `fix/` | Bug fixes |
| `firmware/` | Pico firmware changes |
| `docs/` | Documentation only |
| `cloud/` | Cloud API or map viewer changes |

## Pull Request Process

1. Create a branch from `main`
2. Make your changes
3. Run tests locally:
   ```bash
   # Pi 5 code
   kicad-cli pcb drc --severity-all Boat_PCB/Boat_PCB_V3/Boat_PCB_V3.kicad_pcb
   
   # Dashboard
   cd dashboard && npm run build
   
   # Cloud API (requires PostGIS)
   cd cloud && docker compose up -d
   # then test against localhost:8000
   ```
4. Open a PR with:
   - A clear title (under 70 characters)
   - Description of what changed and why
   - Test plan
5. Wait for CI to pass
6. Merge when approved

## Project Structure

```
firmware/
  boat-pico/        MicroPython — Boat Pico real-time controller
  pod-pico/         MicroPython — Underwater sensor pod
pi5/
  comms/            Serial protocol and Pico communication
  navigation/       Navigator, mission manager, simulator
  server/           FastAPI dashboard API
  data/             Cloud data uploader
  tests/            pytest test suite
dashboard/          React + Vite — real-time boat dashboard
cloud/
  api/              FastAPI + PostGIS — cloud data storage
  map-viewer/       React — historical data heatmap viewer
deploy/             Caddy config, deployment guides
docs/
  adr/              Architecture Decision Records
  serial-protocol.md  Pi 5 ↔ Pico serial protocol spec
reference/          Original single-file MicroPython firmware
```

## Testing

- **Pi 5 code**: `pytest pi5/tests/ -v`
- **Firmware**: Flash to Pico and test manually (no desktop Python tests for MicroPython)
- **Dashboard**: `cd dashboard && npm run build` (build-time checks)
- **Cloud API**: Run against PostGIS via `docker compose up -d`

## Code Style

- **Python (Pi 5)**: Type hints, docstrings, `ruff` for linting
- **MicroPython**: No type hints (not supported), keep it compact, docstrings on modules and public functions
- **JavaScript/React**: Functional components, hooks, no class components
