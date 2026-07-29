# D.R.E.A.M.S — Autonomous Survey Boat
## Context File for Claude Code Agents

This is the master context document for the D.R.E.A.M.S autonomous survey catamaran project.
Read this before touching any file in the repo.

> **Naming:** the project is named **D.R.E.A.M.S**, but the working directory on disk is
> `COE 2 Autonomous Boat/`. There is no `D.R.E.A.M.S/` directory — paths below are relative to the
> repo root (the `COE 2 Autonomous Boat/` folder).

---

## Session Journal — read at start, write at end (REQUIRED)

`docs/session_journal.md` is a running log of what each Claude Code session worked on. It exists so a
fresh chat can pick up where the last one left off. **It's capped at the 5 most recent entries** to
keep it cheap to load every session; older entries live in `docs/session_journal_archive.md`.

1. **At the start of every session:** read `docs/session_journal.md` (entries are newest-first) to
   understand recent work, open questions, and next steps before doing anything else. Don't read the
   archive unless you need context on something specific from further back.
2. **At the end of every session** — or once you've finished a meaningful chunk of work — **append a
   new entry to the top** of the journal (under the `New entries below this line` marker) using the
   template in that file. Keep it short and factual: what changed, why, what's left. If this pushes
   the count past 5, move the oldest entry to the top of `docs/session_journal_archive.md`'s entry
   list (newest-first there too).

This is the narrative of in-progress work. Locked decisions and the architecture-of-record still live
in `docs/changelog_and_decisions.md` — don't duplicate them in the journal.

---

## What This Project Is

An autonomous catamaran survey boat that navigates rivers and lakes, avoids obstacles using
computer vision, collects environmental sensor data (salinity, temperature, depth), and streams
everything to the cloud in real time. Missions can be planned, uploaded, and monitored remotely
through a web dashboard. The full software stack runs in a simulator on a laptop before any
hardware is attached.

---

## Architecture at a Glance

```
┌─────────────────────────────────────────────────┐
│             Raspberry Pi 5 (4/8GB)              │
│  Python 3 · FastAPI · asyncio · USB cameras     │
│  Navigation logic, mission FSM, cloud pipeline  │
│  USB CDC to Boat Pico · SIM7600 cellular        │
└────────────────┬────────────────────────────────┘
                 │ USB CDC (115200)
     ┌───────────┴───────────┐
     │     Boat Pico (A1)    │  RP2040 · MicroPython
     │  motors, GPS, IMU,    │
     │  winch, RC, sensors   │
     └───────────────────────┘
            │ 50 Hz PWM GP2/GP3       │ UART1 (GP4/5)
     ┌──────┴──────┐           ┌───────┴────────┐
     │  AM32 ESCs  │           │   Pod Pico     │ underwater, via slip ring
     │   (L + R)   │           └────────────────┘
     └─────────────┘
   Test-bench branch: direct servo PWM, no VESC / CAN chain. ESC telemetry
   (AM32 KISS) returns on GP16/GP11 via PIO UART.
   ⚠ Boat_PCB V2 instead fits an MCP2515 + TJA1051 on GP2/3/4/6/7 → J2 for the
     VESC architecture. The board and this firmware collide — see docs/pin_map.md.

Pi 5 USB peripherals (+ the radar-bar A4988 stepper on the 40-pin header, the one GPIO user):
  USB-A (1) → Boat Pico (CDC ACM → /dev/ttyACM0)
  USB-A (2) → Left USB camera  (cv2.VideoCapture(0))
  USB-A (3) → Right USB camera (cv2.VideoCapture(1), stereo pair, 120mm baseline)
  USB-A (4) → SIM7600G-H 4G HAT, OR a USB-TTL HC-12 dongle (emergency backup)
  USB-C     → 5V power in (from the 3S logic-domain buck)
  Internal  → Pi 5 onboard WiFi (dock/dev link)
```

Navigation logic runs on the Pi 5. The Boat Pico is a low-level executor. All sensors live on the
Boat Pico or the Pod Pico — the Pi 5 only talks USB.

---

## Hardware — What's Actually on the PCBs

The KiCad 10 project lives in the repo (schematic format version `20260306`, generator `eeschema`):

- `Boat_PCB/Boat_PCB.kicad_sch` — the main carrier/breakout board (source of truth for the Boat Pico
  wiring). Detailed component list in `docs/pcb_design_notes.md`.

### Boat_PCB highlights
Verified from the `Boat_PCB V2` netlist (silkscreen reads `Boat_PCB V2`) on 2026-07-28, cross-checked
with `kicad-cli`. Component/footprint detail in `docs/pcb_design_notes.md`; per-pin detail in
`docs/pin_map.md` (authoritative).

| Group | Refs | Notes |
|-------|------|-------|
| Compute | A1 | RaspberryPi_Pico |
| CAN interface | U1 (MCP2515), U2 (TJA1051T-3), Y1 + C1/C2 | SPI on GP2/3/4, ~INT GP6, ~RESET GP7. ⚠ `~CS` (U1.16) is **tied to GND** — SPI can't frame; ⚠ Y1 frequency and C1/C2 values unset |
| Stepper | A2 (Pololu A4988), J18 (motor) | Driven by **Pi 5 GPIO** via J3, not the Pico. Half step (MS1 high, MS2/MS3 → GND) |
| Batteries | BT1 (XT60, "3s" → electronics), BT4 (XT60, "4s" → VMOT) | Only two battery inlets on V2 — no BT2/BT3 |
| Fuses | All **off-board** on V2 | No fuse footprints; per-pack overcurrent handled by M18 REDLINK BMS |
| Battery dividers | **As built:** Drive 220k/13k (×17.92) → GP26, Elec 100k/30k (×4.33) → GP27, Winch 100k/18k (×6.56) → GP28 | ⚠ Firmware expects ×14.0 / ×6.6 / ×6.6 — **GP26 and GP27 read wrong, GP27 is over-range on an M18**. Fit 56k/10k on all three. No ADC filter caps fitted |
| Power out | J6 (XT60, VMOT), J4 (2-pin JST — **sense tap only**, not a power output) | V2 has **no XT90 drive outputs** — motor power is off-board |
| CAN comms | J2 (3-pin JST-XH: GND / CANH / CANL) | ⚠ **no 120 Ω termination fitted**, no ESD on an off-board connector |
| Winch | J8 (signal, GP21), J9 (RC, GP21 — parallel) | Both are signal-only 2-pin connectors |
| Sensors | J7 (GPS+compass), **J5** (IMU, 10-pin), J11/J13 (**SHT41**, not DHT11), J12 (LED, GP10), J15/J16 (hull leak, GP20/GP19) | ⚠ J7/J11/J13 supply **5 V**; SHT41 is 3.6 V max. ⚠ No I²C pull-ups on any of the three buses |
| Pi 5 header | J3 (2×20), J14/J17 (1×20 breakouts) | ⚠ J3's footprint has the **odd/even rows transposed** — schematic pad *N* = Pi pin *N∓1* |

### No HC-12 on the boat PCB
The HC-12 radio is **not** on either PCB and is no longer part of the old Shore-Pico architecture.
It is retained only as an **optional emergency backup link**, plugged into a Pi 5 USB-A port as a
USB-TTL dongle (alternative to the SIM7600). The primary shore link is SIM7600 cellular; WiFi is used
at the dock. See `docs/pin_map.md` and the project `README.md`.

---

## Pin Maps

The authoritative pin maps live in **`docs/pin_map.md`**, generated from the Boat Pico and Pod Pico
`main.py` docstrings. Do not duplicate them here — edit `docs/pin_map.md` and the firmware docstrings
together. Quick orientation only:

- **Boat Pico (test-bench firmware):** GP0/GP1 dead. GP2/3 drive ESC PWM. GP4/5 UART1 (GPS M10Q +
  Pod, shared 9600). GP6 winch PWM. GP7 SBUS (PIO). GP8/9 I²C0 (BNO085 @ 0x4A). GP10 status NeoPixel.
  GP11/16 AM32 ESC telemetry RX (PIO). GP12/13 SHT41 #A, GP14/15 SHT41 #B (both SoftI2C).
  GP19/20 hull leak (J16/J15). GP26 ADC drive (2× M18 parallel), GP27 ADC electronics (M18),
  GP28 ADC winch (M18).
  > ⚠ **Board divergence.** On `Boat_PCB V2` the MCP2515 CAN interface owns GP2/3/4/6/7 and GP5 is
  > tied to GND, so the drive-ESC / winch / SBUS / GPS assignments above collide with the board —
  > and with GP0/GP1 dead there is no free pin left to move them to. The board's winch signal is
  > GP21, not GP6. Hull leak and ESC telemetry *were* realigned to the board (2026-07-28). Full
  > board-vs-firmware table in `docs/pin_map.md`.
- **Pod Pico:** GP0/1 UART to Boat Pico (slip ring). GP17 EC drive, GP20 leak, GP21 bottom contact,
  GP22 pressure, GP26 water-temp NTC, GP27 EC sense, GP28 light.

> **Battery dividers (M18 three-domain).** Test bench: drive **130k/10k** (×14.0) → GP26 — the packs
> are now **2× M18 parallel** (21 V max → ~1.5 V at the pin, reads correctly at ×14, no resistor rework
> for the parallel swap; fit 56k/10k + set `INV_P_RATIO=6.6` only if you want full ADC range),
> electronics **56k/10k** (×6.6, 21 V → 3.18 V) → GP27, winch **56k/10k** (×6.6) → GP28. All three rails
> are monitored (`firmware/boat-pico/sensors.py`, the authoritative thresholds). The KiCad schematic
> still carries older resistor values and needs updating in KiCad Tool — see `docs/battery_architecture.md`.

---

## Serial Protocol: Pi 5 ↔ Boat Pico

The full protocol spec (v1.0) is in **`docs/serial-protocol.md`** — frame format
`$<payload>*<xor_checksum>\n` at 115200 8N1 over USB CDC, with SEQ-numbered commands
(SET_HDG, SET_THR, SET_WINCH, ESTOP/RESUME, HB heartbeat, POLL_POD, GET_STATUS, …) and unsolicited
responses (ACK/NAK, TEL @1s, ENV @5s, POD_DATA, STATUS, ALERT). See that file for the authoritative
field layouts and alert codes. Do not restate it here.

---

## Simulation-First Development

`pi5/config.yaml` carries a `mode:` flag (`simulator` or `hardware`). In simulator mode,
`pi5/navigation/simulator.py` mocks GPS, the Pico serial link, and motion, so the Pi 5 software stack
runs on a Windows laptop with no hardware attached.

```bash
python run_sim.py                      # run the navigation stack in simulator mode
cd cloud && docker compose up -d       # PostGIS for the cloud API
cd dashboard && npm run dev            # React dashboard
```

---

## Software Stack

| Layer | Technology |
|-------|-----------|
| Boat / Pod Pico firmware | MicroPython + uasyncio |
| Pi 5 navigation | Python 3 + asyncio |
| Pi 5 server | FastAPI + WebSocket |
| Dashboard | React + Vite + Leaflet + Recharts |
| Cloud API | FastAPI + SQLAlchemy + PostGIS |
| Cloud hosting | Docker → Railway or Fly.io |
| Database | PostgreSQL + PostGIS |
| Computer vision | OpenCV StereoSGBM + YOLOv8-nano, stereo USB cameras |
| Remote access | Tailscale VPN (SSH to Pi 5 over cellular) |
| Connectivity | SIM7600 4G LTE (primary), Pi 5 WiFi (dock), HC-12 USB (emergency backup) |

---

## Power Architecture

Three **fully isolated Milwaukee M18 domains** — no shared ground except a single star point on the
logic PCB. Full spec (dividers, thresholds, fusing, runtimes) in **`docs/battery_architecture.md`**.

```
2× M18 (parallel) ─► DRIVE rail (18V nom / 21V max) ─[100A ANL]─┬─[80A]─► ESC L (GP2) → 2814 motor
  (test bench)                                                   ├─[80A]─► ESC R (GP3) → 2814 motor
                                                                 └─[80A]─► tow-ESC stub (unpop.)

1× M18 ──► ELECTRONICS rail (18V nom) ─[15A]─► 5V UBEC → Pi 5 (USB-C)
                                             └─► 3.3V → Boat Pico, sensors

1× M18 ──► WINCH rail (18V nom) ─[20A]─► MOSFET kill → Winch ESC (GP6)
```

> **Test-bench drive:** two **NeutronRC 70A-G071 (AM32)** ESCs driven directly by the Pico as 50 Hz
> servo PWM (GP2/GP3, `firmware/boat-pico/escs.py`) — **no VESC / CAN chain** on this branch. Powered by
> 2× M18 in **parallel** (18V nom, ~double current/runtime — *not* more voltage, so below 6S). AM32 must
> have **Bi-directional mode ON** (the navigator commands reverse for pivots/avoidance) and a 5S LVC —
> see `docs/esc_setup.md`. The pack (~90 A pair) is the tighter limit vs the 70 A ESCs; BMS + ANL fuses +
> Pico watchdog are the backstops. Kv-mismatch via `navigation.motor_gain_*` + firmware `COMP_L/COMP_R`.

Per-pack overcurrent/short/over-discharge is handled by each M18's REDLINK BMS, so no individual pack
fuses are needed. There is **no 12S-midpoint tap** — the winch is a dedicated standalone pack, which
resolves the old midpoint-vs-dedicated ambiguity.

---

## Key Decisions (Locked)

| Decision | Reason |
|----------|--------|
| Pi 5 uses only USB — no GPIO | All sensors on the Picos; Pi 5 is just the brain |
| USB cameras, not CSI | Simpler wiring, no HAT; stereo pair on standard USB |
| HC-12 demoted to USB backup | Removed from the PCB; kept only as an emergency USB-TTL link |
| BNO085 (not QMC5883P) | Full 9-DOF IMU at I²C 0x4A with onboard fusion |
| VESC via UART0 (not CAN HAT) | VESC master on GP12/13; slave reached via COMM_FORWARD_CAN |
| Simulation-first dev | Full stack testable without any hardware |
| THT passive components | Owner preference for reworkability |
| 3-domain M18 batteries | Isolated drive/elec/winch packs; hot-swappable, BMS-protected, no balance tracking |

---

## Related Docs

- `docs/pin_map.md` — authoritative pin assignments (both Picos + Pi 5 USB)
- `docs/battery_architecture.md` — authoritative M18 three-domain battery reference
- `docs/serial-protocol.md` — Pi 5 ↔ Boat Pico protocol (v1.0)
- `docs/object_memory.md` — GPS-anchored buoy/landmark memory (confirm → map marker → verify → forget)
- `docs/system_tree.md` — Mermaid system/power diagram
- `docs/pcb_design_notes.md` — Boat_PCB component breakdown
- `docs/hardware_changes_v1_to_v2.md` — V1 → V2 hardware delta
- # ... 2 more

---

## Session start protocol

- Run `/context` on session start to check token usage
- Run `/compact` when context reaches 70% (do not wait for auto-compact at 95%)
- Run `/clear` when switching to an unrelated task
- Use `/effort low` for simple edits and single-file changes
- Use Plan Mode (Shift+Tab) before any multi-file operation

<!-- code-review-graph MCP tools -->
## MCP Tools: code-review-graph

**IMPORTANT: This project has a knowledge graph. ALWAYS use the
code-review-graph MCP tools BEFORE using Grep/Glob/Read to explore
the codebase.** The graph is faster, cheaper (fewer tokens), and gives
you structural context (callers, dependents, test coverage) that file
scanning cannot.

### When to use graph tools FIRST

- **Exploring code**: `semantic_search_nodes` or `query_graph` instead of Grep
- **Understanding impact**: `get_impact_radius` instead of manually tracing imports
- **Code review**: `detect_changes` + `get_review_context` instead of reading entire files
- **Finding relationships**: `query_graph` with callers_of/callees_of/imports_of/tests_for
- **Architecture questions**: `get_architecture_overview` + `list_communities`

Fall back to Grep/Glob/Read **only** when the graph doesn't cover what you need.

### Key Tools

| Tool | Use when |
| ------ | ---------- |
| `detect_changes` | Reviewing code changes — gives risk-scored analysis |
| `get_review_context` | Need source snippets for review — token-efficient |
| `get_impact_radius` | Understanding blast radius of a change |
| `get_affected_flows` | Finding which execution paths are impacted |
| `query_graph` | Tracing callers, callees, imports, tests, dependencies |
| `semantic_search_nodes` | Finding functions/classes by name or keyword |
| `get_architecture_overview` | Understanding high-level codebase structure |
| `refactor_tool` | Planning renames, finding dead code |

### Workflow

1. The graph auto-updates on file changes (via hooks).
2. Use `detect_changes` for code review.
3. Use `get_affected_flows` to understand impact.
4. Use `query_graph` pattern="tests_for" to check coverage.
