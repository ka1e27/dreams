# ADR-003: Pi 5 Navigation Architecture

**Date**: 2026-04-08  
**Status**: proposed  
**Deciders**: Kyle (project owner), Claude (architect)

## Context

The Pi 5 replaces the Boat Pico as the navigation brain. We need to port the navigation logic from MicroPython to Python, add mission management, and create a testable architecture that works with both real hardware and a simulator.

## Decisions

### 1. Layered architecture: protocol → comms → navigation

```
protocol.py      Pure framing (checksum, parse, build) — no I/O
    ↓
pico_serial.py   Async serial connection, command/response matching
    ↓
navigator.py     Waypoint steering (compute throttle from position)
mission_manager.py   Waypoint sequencing, pod deployment, sampling
    ↓
simulator.py     Virtual boat that implements the same PicoSerial interface
```

**Why:** protocol.py is pure and fully testable without hardware or async. pico_serial.py handles I/O but exposes clean async methods. navigator.py has a `compute_throttle()` pure function that can be tested independently. The simulator implements the same interface as PicoSerial so all navigation/mission code works without a real boat.

### 2. Navigator uses compute_throttle() as a pure function

The core steering math (bearing calculation, proportional turn blending) is extracted into `compute_throttle(lat, lon, heading, tgt_lat, tgt_lon) → (left, right, dist, bearing, error, arrived)`. This is the same algorithm from Boat_pico.py `task_navigate()`.

**Why:** Pure functions are trivially testable. We can validate the steering behaviour against known scenarios without any I/O, mocking, or async.

### 3. PicoSerial uses sequence-numbered futures for command matching

When the Pi 5 sends a command, it creates an `asyncio.Future` keyed by sequence number. The read loop resolves the future when a matching ACK/NAK arrives. This gives clean `await pico.set_throttle(40, 40)` syntax with automatic timeout and retry.

### 4. Simulator as a drop-in PicoSerial replacement

`MockPicoSerial` implements the same method signatures as `PicoSerial` (set_throttle, set_winch, telemetry property, etc.) but routes everything through a physics simulation. This means:
- Navigator and MissionManager don't know if they're running on real hardware or a sim
- Tests can use the simulator without mocking
- Development and testing can happen without the boat

### 5. Mission manager owns the full data collection workflow

The mission phases (TRANSIT → WINCH_DOWN → SAMPLING → WINCH_UP) are ported from Boat_pico.py task_mission() but run on the Pi 5. The MissionManager:
- Loads missions from the same waypoints.json format
- Handles pause/resume/abort
- Manages pod polling during sampling
- Tracks bottom contact confirmations (same 3-confirmation logic)
- Enforces safety timeouts

### 6. Pi 5 navigates autonomously; shore only overrides

The Pi 5 continues its mission independently. Shore commands (via the web API, Step 4) can pause, resume, abort, or redirect, but the Pi 5 doesn't need the shore to navigate. This is different from the old architecture where the Shore Pico uploaded missions but the Boat Pico executed them.

## Consequences

### Positive
- Navigation math is fully testable (27 tests across geo, protocol, navigator, mission)
- Simulator enables development without hardware
- Clean separation of concerns: protocol → I/O → logic
- Same mission format as existing waypoints.json

### Negative
- `pyserial-asyncio` dependency needed on Pi 5
- Two "languages" for serial comms (MicroPython on Pico, Python on Pi 5) — mitigated by shared protocol spec
