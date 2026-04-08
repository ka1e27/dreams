# ADR-002: Firmware Module Restructure

**Date**: 2026-04-08  
**Status**: proposed  
**Deciders**: Kyle (project owner), Claude (architect)

## Context

The original Boat Pico firmware (`reference/Boat_pico.py`) is a single 1100-line file containing all hardware drivers, navigation logic, mission management, radio protocol handling, and safety watchdogs. This made sense when the Pico was the only brain, but the Pi 5 upgrade means:

1. Navigation and mission logic move to the Pi 5
2. The Pico becomes a real-time sensor/actuator controller
3. The code needs to be testable and maintainable across two developers (human + AI)

## Decision

### Split into focused modules

**Boat Pico (`firmware/boat-pico/`):**

| Module | Responsibility | Extracted from |
|--------|---------------|----------------|
| `main.py` | Async event loop, task orchestration | `main()`, all `task_*()` functions |
| `serial_handler.py` | Pi 5 USB serial protocol | New (replaces radio `rx_frames()` + `task_commands()`) |
| `motor_control.py` | ESC PWM, RC override, ESTOP | `set_m()`, `motors_update()`, `rc_on()`, `rc_off()` |
| `gps.py` | NMEA parsing | `_process_line()` GPS section, `read_uart1()` |
| `compass.py` | QMC5883P I2C driver | `init_compass()`, `read_compass()` |
| `pod_uart.py` | Pod poll-response bridge | Pod parsing from `_process_line()`, `poll_pod()` |
| `sensors.py` | Battery, DHT, NTC, hull leak | `read_batt()`, `read_dht()`, `read_mtemp()`, `read_hull()` |
| `watchdog.py` | Pi 5 heartbeat monitor | New (was implicit in radio timeout logic) |

**Pod Pico (`firmware/pod-pico/`):**

| Module | Responsibility | Extracted from |
|--------|---------------|----------------|
| `main.py` | Async event loop | `main()` from Pod_pico.py |
| `sensors.py` | EC, NTC, light, bottom contact | `read_temp()`, `read_ec()`, `read_light()`, `read_bottom()` |
| `leak_detect.py` | Leak sensor with debouncing | New (adds leak detection the original didn't have) |
| `uart_responder.py` | Poll-response protocol | `check_poll()`, `send_data()` |

### Preserve driver code verbatim where possible

The NTC temperature calculation, EC probe reading sequence, compass I2C register writes, GPS NMEA parsing, and ESC PWM duty calculations are copied directly from the reference code. These have been tested on real hardware — no reason to rewrite them.

Changes made:
- Wrapped in functions with docstrings and clear parameters
- Removed global state in favour of module-level variables
- Added return values for error reporting
- Added health tracking (fail counts, timeouts)

### UART1 sharing (GPS + Pod)

The original code runs GPS and Pod on the same UART1 and routes lines by prefix (`$GPR`/`$GNR` for GPS, `$POD` for pod). We keep this pattern with a dedicated `task_uart1_reader()` in main.py that reads bytes and dispatches to the appropriate parser.

### GP0/GP1 avoidance

The original code used GP0/GP1 for HC-12 radio (UART0). These pins are dead on the Boat Pico. In the new firmware:
- UART0 (GP12/GP13) is reserved for HC-12 but unused in the Pi 5 architecture
- USB serial to Pi 5 uses the USB-CDC interface (sys.stdin/stdout), not a UART
- Pod Pico still uses GP0/GP1 for UART0 to Boat Pico (these pins work on the Pod Pico)

### New: Leak detection on Pod

The original Pod firmware had no leak sensor. The new `leak_detect.py` adds:
- GP20 for a simple water-bridge leak sensor
- Debouncing (3 consecutive reads to confirm)
- Latching behaviour (leak flag stays set until reset — safety feature)
- Leak status included in POD response as a 6th field

This is backwards-compatible: if the Boat Pico receives a 5-field POD response (old pod), it works. If it gets 6 fields, it reads the leak flag.

## Consequences

### Positive
- Each module is independently understandable
- Hardware pin assignments documented in one place (module docstrings + main.py)
- Safety watchdog is explicit rather than implicit
- Adding new sensors or commands means editing one module, not searching a 1100-line file

### Negative
- More files to flash to the Pico
- Module imports add small startup overhead (negligible on RP2040)
- Need to ensure modules are ordered correctly in the filesystem

### Migration path
1. Flash pod-pico firmware to Pod Pico — works immediately (same poll-response protocol)
2. Flash boat-pico firmware to Boat Pico — will idle until Pi 5 sends heartbeats
3. Develop Pi 5 software (Step 3) — once it sends HB + commands, the system is live
