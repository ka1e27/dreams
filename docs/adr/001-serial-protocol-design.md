# ADR-001: Serial Protocol Design for Pi 5 ↔ Boat Pico

**Date**: 2026-04-08  
**Status**: proposed  
**Deciders**: Kyle (project owner), Claude (architect)

## Context

The autonomous survey boat is being upgraded from a Pico-only architecture (where the Boat Pico runs all navigation, mission management, and motor control) to a split architecture where a Raspberry Pi 5 becomes the main brain and the Boat Pico becomes a real-time controller.

The Pi 5 connects to the Boat Pico over USB serial (`/dev/ttyACM0`). We need a protocol for this link that handles:
- Motor commands (heading, throttle, winch)
- Sensor telemetry (GPS, compass, battery, temperatures)
- Pod sensor data (forwarded through Boat Pico to Pod Pico over UART)
- Safety (heartbeat watchdog, emergency stop, alerts)
- Calibration (compass offset, motor trim)

The existing system uses a proven `$payload*xor_checksum\n` ASCII framing over HC-12 radio at 9600 baud. The radio protocol is half-duplex with burst/listen cycles and handles high-level commands like `GOTO,lat,lon` and `MISSION,count,...`.

## Decision

### 1. Keep the `$payload*xor_checksum\n` frame format

**Alternatives considered:**
- **Binary protocol (protobuf, msgpack):** More bandwidth-efficient, but harder to debug (can't read with a terminal), harder to parse in MicroPython, and USB serial at 115200 has plenty of bandwidth for our data rates.
- **JSON lines:** Easy to parse in Python, but bloated for MicroPython, and the existing codebase has no JSON serialization for messages.
- **New framing (length-prefixed, COBS):** More robust, but the existing XOR checksum framing is proven across ~4 versions of the firmware and is trivially parseable in both Python and MicroPython.

**Why keep it:** The existing frame parser (`rx_frames()` in Boat_pico.py) is battle-tested on noisy HC-12 radio links. If it works over lossy radio, it'll work fine over USB serial. Both the Boat Pico and Pod Pico already have this parser. Reuse means fewer bugs.

### 2. Add sequence numbers (SEQ) to the payload

The existing radio protocol has no sequence numbers — it relies on timing (send command, wait for ACK within 5s, retry). This worked because the HC-12 half-duplex link naturally serialized exchanges.

USB serial is full-duplex. The Pi 5 may send a SET_HDG command while a TEL message is in-flight from the Pico. Without SEQ, we can't match responses to commands.

**Format:** `MSG_TYPE,SEQ,fields...` where SEQ is 0–255. Unsolicited messages (TEL, ENV, ALERT) use SEQ=0.

**Why 0–255:** One byte, wraps cleanly, and the Pi 5 will never have more than a few commands in flight. The existing code uses `int()` parsing, so a small decimal number adds minimal overhead.

### 3. Low-level command set (SET_HDG, SET_THR) instead of high-level (GOTO, MISSION)

**Alternatives considered:**
- **Keep GOTO and MISSION on Pico:** Simpler Pi 5 code, but duplicates navigation logic across two languages (Python and MicroPython) and limits the Pi 5's ability to do obstacle avoidance, path smoothing, or other intelligent navigation.
- **Hybrid (both high and low-level):** More flexible but doubles the command surface and creates ambiguity about who's in control.

**Why low-level:** The whole point of adding the Pi 5 is to move intelligence off the Pico. Navigation logic (bearing calculation, waypoint sequencing, mission management) belongs on the Pi 5 where we have:
- Full Python with numpy, scipy, opencv
- Persistent storage for mission logs
- Network connectivity for remote control
- Enough compute for computer vision

The Pico becomes a "dumb" actuator + sensor platform. It doesn't need to know about waypoints or missions — it just follows heading and throttle commands and reports sensor data.

### 4. Heartbeat watchdog on the Pico

If the Pi 5 crashes, hangs, or loses USB connection, the boat must not continue driving. The Pico monitors HB messages from the Pi 5 and triggers an automatic ESTOP if none arrive within 3000 ms.

**Why 3 seconds:** Fast enough to stop before the boat hits anything at survey speeds (~1-2 knots), but tolerant of brief Pi 5 GC pauses or USB enumeration delays. The existing firmware uses 30s timeouts for radio silence detection — but that was for a lossy radio link. USB is reliable, so a missed heartbeat genuinely means the Pi 5 is down.

### 5. Separate TEL and ENV messages instead of one big packet

The existing firmware sends D1 (navigation data) and D2 (environment data) as separate radio packets because the HC-12 has limited burst bandwidth.

We keep this split but rename to TEL (1s interval, fast-changing data: position, heading, battery) and ENV (5s interval, slow-changing data: air temp, water sensors). This reduces unnecessary USB traffic and makes it easy for the Pi 5 to process at different rates.

### 6. ALERT messages for events instead of inline STATUS

The existing firmware embeds events in `STATUS,EVENT_NAME,...` messages mixed with telemetry. This makes parsing complex (the Shore station has a 100-line `_handle_status()` function).

The new protocol uses dedicated `ALERT,0,severity,code,detail` messages with defined severity levels (CRIT/WARN/INFO) and enumerated codes. This lets the Pi 5 handle alerts with a simple lookup table and route critical alerts immediately (e.g., hull leak → abort mission → surface pod → return home).

### 7. 115200 baud

**Alternatives considered:**
- **9600 (same as radio):** Too slow. At 1s telemetry interval with ~80 byte packets, we'd be spending 80ms per packet. Fine for radio, but wasteful on USB.
- **921600 or higher:** Faster but some MicroPython USB-CDC implementations have issues at very high baud rates.

**Why 115200:** Standard, well-supported, fast enough for our data rates (< 1% bus utilization at our message rates), and the Pico's USB-CDC implementation handles it reliably.

## Consequences

### Positive
- Proven framing reduces risk of protocol bugs
- SEQ numbers enable concurrent command/response matching
- Low-level commands give Pi 5 full control for intelligent navigation
- Heartbeat watchdog ensures safe failure mode
- Structured alerts simplify event handling

### Negative
- Navigation logic must be re-implemented in Python on the Pi 5 (but this was the goal)
- The HC-12 radio link to shore needs a separate protocol (or the Pi 5 bridges to shore via cellular, replacing the radio entirely)
- The Pico firmware becomes simpler but can't operate autonomously without the Pi 5

### Risks
- USB disconnect during operation — mitigated by heartbeat watchdog (Pico kills motors)
- Pi 5 sending commands faster than Pico can process — mitigated by ACK/NAK flow control; Pi 5 waits for response before sending next command of the same type
