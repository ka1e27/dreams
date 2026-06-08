# Serial Protocol: Pi 5 ↔ Boat Pico

**Version:** 1.0  
**Transport:** USB Serial (`/dev/ttyACM0`), 115200 baud, 8N1  
**Encoding:** ASCII, newline-terminated

---

## 1. Frame Format

Every message follows the same frame structure used by the existing firmware, extended with a sequence number for reliable command/response matching:

```
$<payload>*<checksum>\n
```

| Field | Description |
|-------|-------------|
| `$` | Start-of-frame (0x24) |
| `<payload>` | Comma-separated ASCII fields |
| `*` | Checksum delimiter |
| `<checksum>` | XOR of all bytes in `<payload>`, decimal ASCII |
| `\n` | End-of-frame (0x0A) |

### Checksum Calculation

XOR every byte in the payload string (between `$` and `*`):

```python
def checksum(payload: str) -> int:
    cs = 0
    for ch in payload:
        cs ^= ord(ch)
    return cs
```

### Payload Structure

```
<MSG_TYPE>,<SEQ>,<field1>,<field2>,...
```

| Field | Description |
|-------|-------------|
| `MSG_TYPE` | Command or response identifier (uppercase) |
| `SEQ` | Sequence number (0–255, wraps). Commands and their responses share the same SEQ. Unsolicited messages (telemetry, alerts) use SEQ=0. |
| Remaining fields | Command-specific, comma-separated |

**Why sequence numbers?** USB serial is reliable but the Pi 5 may send commands faster than the Pico processes them. SEQ lets the Pi 5 match responses to commands without ambiguity. The existing radio protocol didn't need this because the HC-12 half-duplex link naturally serialized exchanges.

---

## 2. Message Flow

```
Pi 5 (commander)                    Boat Pico (controller)
     │                                     │
     │──── CMD,seq,... ──────────────────>│  Command
     │                                     │
     │<──── ACK,seq,... ─────────────────│  Success response
     │<──── NAK,seq,reason ──────────────│  Failure response
     │                                     │
     │<──── TEL,0,... ──────────────────│  Unsolicited telemetry (periodic)
     │<──── ALERT,0,... ────────────────│  Unsolicited alert
     │                                     │
     │──── POLL_POD,seq ────────────────>│  Request pod data
     │<──── POD_DATA,seq,... ────────────│  Pod sensor response
```

### Timing

| Parameter | Value | Notes |
|-----------|-------|-------|
| Command timeout | 2000 ms | Pi 5 retransmits if no ACK/NAK within this window |
| Max retries | 3 | Then report command failure to application layer |
| Telemetry interval | 1000 ms | Boat Pico sends TEL unsolicited |
| Heartbeat interval | 1000 ms | Pi 5 sends HB; Pico expects one every 3000 ms |
| Pod poll interval | 5000 ms | Configurable; Pico forwards to Pod UART |

---

## 3. Commands (Pi 5 → Boat Pico)

### 3.1 SET_HDG — Set Target Heading

Set the desired compass heading. The Pico's motor controller steers toward this heading.

```
$SET_HDG,<seq>,<heading>*<cs>\n
```

| Field | Type | Range | Description |
|-------|------|-------|-------------|
| heading | float | 0.0–359.9 | Target heading in degrees true |

**Response:**
```
$ACK,<seq>,SET_HDG,<heading>*<cs>\n
$NAK,<seq>,SET_HDG,RANGE*<cs>\n
```

**Example:**
```
> $SET_HDG,12,185.5*87\n
< $ACK,12,SET_HDG,185.5*44\n
```

---

### 3.2 SET_THR — Set Throttle

Set motor throttle. Positive = forward, negative = reverse. The Pico applies pulley compensation and trim internally.

```
$SET_THR,<seq>,<left>,<right>*<cs>\n
```

| Field | Type | Range | Description |
|-------|------|-------|-------------|
| left | int | -100 to 100 | Left motor speed percentage |
| right | int | -100 to 100 | Right motor speed percentage |

**Response:**
```
$ACK,<seq>,SET_THR,<left>,<right>*<cs>\n
$NAK,<seq>,SET_THR,RANGE*<cs>\n
$NAK,<seq>,SET_THR,RC_ACTIVE*<cs>\n
```

**Example:**
```
> $SET_THR,13,40,40*71\n
< $ACK,13,SET_THR,40,40*28\n
```

---

### 3.3 SET_WINCH — Set Winch Speed

Control the winch motor for pod deployment.

```
$SET_WINCH,<seq>,<speed>*<cs>\n
```

| Field | Type | Range | Description |
|-------|------|-------|-------------|
| speed | int | -100 to 100 | Positive = down, negative = up, 0 = stop |

**Response:**
```
$ACK,<seq>,SET_WINCH,<speed>*<cs>\n
$NAK,<seq>,SET_WINCH,RC_ACTIVE*<cs>\n
```

**Example:**
```
> $SET_WINCH,14,50*82\n
< $ACK,14,SET_WINCH,50*39\n
```

---

### 3.4 REQ_TEL — Request Telemetry

Request an immediate telemetry packet (in addition to the periodic ones).

```
$REQ_TEL,<seq>*<cs>\n
```

**Response:** A `TEL` message with the matching SEQ (see Section 4.1).

**Example:**
```
> $REQ_TEL,15*60\n
< $TEL,15,51.506726,-0.071438,185.3,1.2,15.4,92,DRY,52.1,49.3,111100*33\n
```

---

### 3.5 POLL_POD — Request Pod Sensor Data

Tell Boat Pico to poll the underwater pod and relay the response.

```
$POLL_POD,<seq>*<cs>\n
```

**Response:**
```
$POD_DATA,<seq>,<water_temp>,<salinity_ec>,<light_pct>,<bottom>,<leak>*<cs>\n
$NAK,<seq>,POLL_POD,TIMEOUT*<cs>\n
$NAK,<seq>,POLL_POD,NO_POD*<cs>\n
```

| Field | Type | Description |
|-------|------|-------------|
| water_temp | float | Water temperature in °C (-999.0 = sensor error) |
| salinity_ec | float | Electrical conductivity in µS/cm |
| light_pct | int | Light level 0–100% |
| bottom | int | 1 = bottom contact, 0 = no contact |
| leak | int | 1 = leak detected, 0 = dry |

**Example:**
```
> $POLL_POD,16*72\n
< $POD_DATA,16,18.3,4520.0,45,0,0*91\n
```

---

### 3.6 ESTOP — Emergency Stop

Kill all motors immediately. Aborts any active navigation on the Pico. The Pico enters idle state and will not accept SET_HDG or SET_THR until a RESUME is received.

```
$ESTOP,<seq>*<cs>\n
```

**Response:**
```
$ACK,<seq>,ESTOP*<cs>\n
```

**Example:**
```
> $ESTOP,17*44\n
< $ACK,17,ESTOP*3\n
```

---

### 3.7 RESUME — Resume After Emergency Stop

Re-enable motor commands after an ESTOP.

```
$RESUME,<seq>*<cs>\n
```

**Response:**
```
$ACK,<seq>,RESUME*<cs>\n
```

---

### 3.8 HB — Heartbeat

Pi 5 sends this periodically so the Pico knows the brain is alive.

```
$HB,<seq>*<cs>\n
```

**Response:**
```
$ACK,<seq>,HB*<cs>\n
```

If the Pico doesn't receive a HB for 3000 ms, it triggers an automatic ESTOP and sends an alert.

**Example:**
```
> $HB,18*11\n
< $ACK,18,HB*72\n
```

---

### 3.9 SET_TRIM — Set Motor Trim

Adjust motor compensation for asymmetric thrust.

```
$SET_TRIM,<seq>,<trim>*<cs>\n
```

| Field | Type | Range | Description |
|-------|------|-------|-------------|
| trim | float | -0.5 to 0.5 | Positive favors left, negative favors right |

**Response:**
```
$ACK,<seq>,SET_TRIM,<trim>,L=<comp_l>,R=<comp_r>*<cs>\n
$NAK,<seq>,SET_TRIM,RANGE*<cs>\n
```

---

### 3.10 CAL_COMPASS — Calibrate Compass North

Set the compass heading offset so it reads true north.

```
$CAL_COMPASS,<seq>,<true_bearing>*<cs>\n
```

| Field | Type | Range | Description |
|-------|------|-------|-------------|
| true_bearing | float | 0.0–359.9 | Known true bearing the boat is currently facing |

**Response:**
```
$ACK,<seq>,CAL_COMPASS,<true_bearing>,HDG_OFF=<offset>*<cs>\n
$NAK,<seq>,CAL_COMPASS,RANGE*<cs>\n
```

---

### 3.11 RC_OVERRIDE / RC_RELEASE — RC Passthrough Mode

Hand motor control to the external RC receiver, bypassing all Pi 5 commands.

```
$RC_OVERRIDE,<seq>*<cs>\n
$RC_RELEASE,<seq>*<cs>\n
```

**Response:**
```
$ACK,<seq>,RC_OVERRIDE*<cs>\n
$ACK,<seq>,RC_RELEASE*<cs>\n
```

---

### 3.12 GET_STATUS — Request Full Status

Returns operational state and all sensor health flags.

```
$GET_STATUS,<seq>*<cs>\n
```

**Response:**
```
$STATUS,<seq>,<state>,<health_flags>,<safety_overrides>*<cs>\n
```

| Field | Type | Description |
|-------|------|-------------|
| state | string | `IDLE`, `ACTIVE`, `ESTOP`, `RC` |
| health_flags | string | 6-char binary: GPS,CMP,BAT,DHT,MOT,POD (1=ok, 0=fault) |
| safety_overrides | string | `NONE` or `+`-joined list: `compass+gps` |

**Example:**
```
> $GET_STATUS,19*55\n
< $STATUS,19,ACTIVE,111100,NONE*82\n
```

---

### 3.13 REFLASH — Drop to REPL for Firmware Upload

Tells the Boat Pico to stop its async loop and return to the bare MicroPython
REPL so the Pi 5 can reflash it over USB with `mpremote`. Without this, the
firmware continuously reads the USB-CDC channel and `mpremote` can't enter the
raw REPL ("could not enter raw repl"). On receipt the Pico ACKs, **stops the
motors**, then exits to the REPL; the Pi must re-establish the link afterwards
(the firmware is no longer running until it is reflashed and reset).

```
$REFLASH,<seq>*<cs>\n
```

**Response:**
```
$ACK,<seq>,REFLASH*<cs>\n
```

Used by `pi5/scripts/deploy_pico.py` (and `run_hardware.py` on startup): it
sends REFLASH over raw serial, waits ~1.5 s for the Pico to drop out, then runs
`mpremote fs cp` + `reset`. Note: firmware that predates this command will NAK
it (`UNKNOWN`) and keep running — so the REFLASH-aware firmware must be
installed once by hand (Pico at a clean REPL) before auto-deploy works.

---

## 4. Unsolicited Messages (Boat Pico → Pi 5)

These are sent periodically or on events. They always use SEQ=0.

### 4.1 TEL — Telemetry

Sent every 1000 ms.

```
$TEL,0,<lat>,<lon>,<heading>,<speed>,<batt_v>,<batt_pct>,<hull>,<mt_l>,<mt_r>,<health>*<cs>\n
```

| Field | Type | Description |
|-------|------|-------------|
| lat | float | GPS latitude (decimal degrees) |
| lon | float | GPS longitude (decimal degrees) |
| heading | float | Compass heading (degrees true, corrected) |
| speed | float | GPS speed (knots) |
| batt_v | float | Battery voltage |
| batt_pct | int | Battery percentage (0–100) |
| hull | string | `DRY`, `L!`, `R!`, or `L!R!` |
| mt_l | float | Left motor temperature (°C) |
| mt_r | float | Right motor temperature (°C) |
| health | string | 6-char binary: GPS,CMP,BAT,DHT,MOT,POD |

**Example:**
```
< $TEL,0,51.506726,-0.071438,185.3,1.2,15.4,92,DRY,52.1,49.3,111100*33\n
```

### 4.2 ENV — Environment Telemetry

Sent every 5000 ms (slow-changing data).

```
$ENV,0,<air_t>,<air_h>,<water_t>,<water_ec>,<water_light>,<bottom>[,<enc_t>,<enc_h>,<elec_v>,<elec_pct>,<winch_v>,<winch_pct>]*<cs>\n
```

| Field | Type | Description |
|-------|------|-------------|
| air_t | int | Open-air temperature (°C, SHT41 #A on J11) |
| air_h | int | Open-air humidity (%, SHT41 #A) |
| water_t | float | Water temperature (°C, -999.0 = no reading) |
| water_ec | float | Water EC (µS/cm) |
| water_light | int | Underwater light level (0–100%) |
| bottom | int | 1 = bottom contact, 0 = no contact |

**ENV v1.1 appendix (optional trailing fields).** Fields 0–5 above are v1.0;
the six below are appended by current firmware and are backward compatible — a
parser that only knows v1.0 stops at `bottom`, and v1.0 firmware simply omits
them. They carry the second SHT41 (electronics enclosure) and the two battery
rails *not* in TEL (the 12S propulsion rail stays in TEL as `batt_v`).

| Field | Type | Description |
|-------|------|-------------|
| enc_t | float | Electronics-enclosure temperature (°C, SHT41 #B on J13; -999.0 = none) |
| enc_h | float | Electronics-enclosure humidity (%, SHT41 #B; -1.0 = none) |
| elec_v | float | 3S electronics battery voltage |
| elec_pct | int | 3S electronics battery percentage (0–100) |
| winch_v | float | 4S winch battery voltage (GP28 ADC; provisional divider — see CLAUDE.md) |
| winch_pct | int | 4S winch battery percentage (0–100) |

**Examples:**
```
< $ENV,0,22,65,18.3,4520.0,45,0*77\n                                  (v1.0)
< $ENV,0,22,65,18.3,4520.0,45,0,29.5,42.0,12.40,94,16.20,87*..\n       (v1.1)
```

### 4.3 ALERT — Alerts and Events

Sent on state changes, faults, and safety events.

```
$ALERT,0,<severity>,<code>,<detail>*<cs>\n
```

| Severity | Meaning |
|----------|---------|
| `CRIT` | Motor kill triggered (hull leak, battery critical, heartbeat lost) |
| `WARN` | Degraded but operational (sensor fault, battery low, motor hot) |
| `INFO` | State change (RC override on/off, ESTOP, resume) |

| Code | Severity | Detail | Description |
|------|----------|--------|-------------|
| `HB_LOST` | CRIT | — | Pi 5 heartbeat lost, motors killed |
| `BATT_CRIT` | CRIT | `<voltage>,<pct>` | Battery critically low |
| `HULL_LEAK` | CRIT | `LEFT`, `RIGHT`, or `BOTH` | Water detected in hull |
| `MOTOR_OVERHEAT` | CRIT | `<side>,<temp_c>` | Motor temp above critical threshold |
| `BATT_LOW` | WARN | `<voltage>,<pct>` | Battery below warning level |
| `MOTOR_HOT` | WARN | `<side>,<temp_c>` | Motor temp above warning level |
| `MOTOR_COOL` | INFO | `<temp_c>` | Motor temp back to normal |
| `SENSOR_FAULT` | WARN | `<sensor_name>` | Sensor stopped responding |
| `SENSOR_OK` | INFO | `<sensor_name>` | Sensor recovered |
| `POD_LOST` | WARN | — | Pod stopped responding to polls |
| `POD_LEAK` | CRIT | — | Pod leak sensor triggered |
| `ESTOP_AUTO` | CRIT | `<reason>` | Automatic emergency stop triggered |
| `RC_ON` | INFO | — | RC override activated |
| `RC_OFF` | INFO | — | RC override released |

**Examples:**
```
< $ALERT,0,CRIT,HB_LOST*88\n
< $ALERT,0,WARN,BATT_LOW,14.1,65*102\n
< $ALERT,0,WARN,SENSOR_FAULT,compass*77\n
< $ALERT,0,CRIT,HULL_LEAK,LEFT*91\n
```

---

## 5. Error Responses

All NAK responses follow this pattern:

```
$NAK,<seq>,<command>,<reason>*<cs>\n
```

| Reason | Meaning |
|--------|---------|
| `RANGE` | Numeric parameter out of valid range |
| `PARSE` | Could not parse the command |
| `RC_ACTIVE` | Command rejected — RC override is active |
| `ESTOP` | Command rejected — emergency stop is active, send RESUME first |
| `TIMEOUT` | Downstream operation timed out (e.g., pod poll) |
| `NO_POD` | Pod is not connected or not responding |
| `UNKNOWN` | Unrecognized command type |

---

## 6. Implementation Notes

### Compared to the existing radio protocol

The existing HC-12 protocol uses the same `$...*cs\n` framing but differs in several ways:

| Aspect | HC-12 (existing) | USB Serial (new) |
|--------|-------------------|-------------------|
| Baud rate | 9600 | 115200 |
| Duplex | Half (burst/listen cycles) | Full |
| Reliability | Lossy — commands sent blind or with retries | Reliable — USB handles framing |
| Sequence numbers | None | Yes (0–255) |
| Navigation logic | Runs on Boat Pico | Runs on Pi 5 |
| Command set | High-level (GOTO, MISSION) | Low-level (SET_HDG, SET_THR) |
| Telemetry | D1/D2 packets over radio | TEL/ENV packets over USB |

### Parser implementation (MicroPython)

The Pico side should reuse the existing `rx_frames()` buffer pattern from `Boat_pico.py` (lines 163–186), which handles byte-at-a-time accumulation and is proven reliable. Add SEQ extraction after frame validation.

### Parser implementation (Python)

The Pi 5 side uses `asyncio` with `serial_asyncio` or `aioserial`. Read lines, validate checksum, extract SEQ, dispatch to handler.

### What stays on the Pico

- Motor PWM output (ESC control)
- GPS NMEA parsing
- Compass I2C reads (QMC5883P at 0x2C)
- Pod UART poll-response forwarding
- DHT11, NTC thermistors, hull leak sensors
- Battery ADC
- Watchdog (heartbeat monitoring)
- RC override GPIO detection

### What moves to the Pi 5

- Waypoint navigation (bearing/distance calculations)
- Mission management (load, execute, pause, abort)
- All decision-making (when to deploy pod, when to move to next waypoint)
- Telemetry logging and forwarding
- Computer vision (future)
- Web dashboard / API server
- Cellular connectivity (4G via SIM7600 — replaces the HC-12 radio link to shore entirely)

### Shore communication

The Pi 5 replaces the HC-12 radio link. Shore communication goes over cellular internet (Pi 5 ↔ Shore via WebSocket/REST). The HC-12 radio and Shore Pico are no longer part of the architecture. The Pi 5 navigates autonomously via waypoints and continues its mission unless overridden by shore commands over the cellular link.

---

## 7. Quick Reference

### Commands (Pi 5 → Pico)

| Command | Payload | Description |
|---------|---------|-------------|
| `SET_HDG` | `<heading>` | Set target heading (0–359.9°) |
| `SET_THR` | `<left>,<right>` | Set motor throttle (-100 to 100) |
| `SET_WINCH` | `<speed>` | Set winch speed (-100 to 100) |
| `REQ_TEL` | — | Request immediate telemetry |
| `POLL_POD` | — | Poll underwater sensor pod |
| `ESTOP` | — | Emergency stop all motors |
| `RESUME` | — | Resume after ESTOP |
| `HB` | — | Heartbeat (send every 1s) |
| `SET_TRIM` | `<trim>` | Motor trim (-0.5 to 0.5) |
| `CAL_COMPASS` | `<true_bearing>` | Calibrate compass north |
| `RC_OVERRIDE` | — | Enable RC passthrough |
| `RC_RELEASE` | — | Disable RC passthrough |
| `GET_STATUS` | — | Request full status |

### Responses (Pico → Pi 5)

| Message | Payload | Trigger |
|---------|---------|---------|
| `ACK` | `<command>,...` | Command succeeded |
| `NAK` | `<command>,<reason>` | Command failed |
| `TEL` | lat,lon,hdg,spd,batt,... | Every 1s (unsolicited) |
| `ENV` | air_t,air_h,water_t,... | Every 5s (unsolicited) |
| `POD_DATA` | temp,ec,light,bottom,leak | Response to POLL_POD |
| `STATUS` | state,health,overrides | Response to GET_STATUS |
| `ALERT` | severity,code,detail | On events (unsolicited) |
