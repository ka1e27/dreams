# D.R.E.A.M.S — Session Journal

A running log of what each Claude Code session worked on. **Read this top-to-bottom at the start
of every session** to understand recent work, then **append a new entry at the end of the session**
describing what you did.

- Newest entries go at the **top** (just under this header), so the most recent context is read first.
- Keep entries short and factual — what changed and why, not a transcript.
- This is a *narrative* of work-in-progress. For locked decisions and the architecture-of-record,
  see `docs/changelog_and_decisions.md`; for hardware deltas, `docs/hardware_changes_v1_to_v2.md`.
  Don't duplicate those here — link to them.
- **This file holds only the 5 most recent entries.** When appending pushes the count past 5, move
  the oldest entry (or entries) to the top of `docs/session_journal_archive.md`'s entry list, keeping
  it newest-first there too. The archive isn't read automatically at session start — only pull from
  it if you need context on something specific from further back.

### Entry template (copy this)

```
## YYYY-MM-DD — <short title>

**Worked on:** one or two sentences on the goal.
**Changed:**
- `path/to/file` — what and why
**Decisions / open questions:** anything left unresolved or flagged for next time.
**Next steps:** what a future session should pick up.
```

---

<!-- New entries below this line, newest first. Keep at most 5 — move older ones to
     docs/session_journal_archive.md. -->

## 2026-08-04 — V3 planning docs brought into the repo, fenced off from the V2 bench

**Worked on:** user supplied two externally-written V3 PCB planning files and asked that they be added
"in a way that doesn't affect the current testing of the current pcb." Docs only — no code, firmware,
config or test touched.

**Changed:**
- `docs/v3/DREAMS_V3_parts_footprints.md`, `docs/v3/V3_PCB_SESSION_CONTEXT.md` — both stored
  **verbatim**; only a scope banner was prepended to each.
- `docs/v3/README.md` — new. The fence: states the V2/V3 boundary, tables the five places the two
  boards contradict each other, and sends bench work back to `CLAUDE.md` / `docs/pin_map.md` /
  `docs/serial-protocol.md`. Also records that `DREAMS_MASTER_CONTEXT.md`, which both files
  reference, is this repo's `docs/PROJECT_CONTEXT.md`.
- `CLAUDE.md` — one row added to "Where truth lives", marking `docs/v3/` authoritative for *nothing*
  on the bench.

**The confusion this guards against:** V3 assumes **VESC-over-CAN** propulsion. The bench has
mismatched hobby ESCs on direct servo PWM (GP19/GP20) with throttle held at zero by
`escs.BIDIR_CONFIRMED`. A session reading V3 as current could walk straight through the gate added on
2026-07-31 after the runaway. Same trap for the IMU: the bench BNO085's fault is four floating strap
pins on the module, not anything the V3 TCA9548A design addresses.

**Decisions / open questions:**
- **Subdirectory, not a branch.** V3 KiCad layout is already live work on this branch
  (`Boat_PCB/Boat_PCB_V3/` exists on disk with `.kicad_pcb` + `.kicad_sch`), so a `v3` branch would
  hide the BOM from the sessions that need it. Isolation is by scope banner + fence instead. Nothing
  mechanical was ever at risk: CI builds only `pi5/`, `cloud/api/`, `dashboard/`, `cloud/map-viewer/`,
  and no test or workflow reads `docs/`.
- `Boat_PCB/Boat_PCB_V3/` and `Boat_PCB/Boat_PCB_V2.kicad_*` are **still untracked**. Committing the
  layout is a separate decision and was left alone.
- Nothing here is committed — the two files, the fence, and this entry are all working-tree only.

**Separately, this session — one test fails on Windows and it is not a regression:**
`pi5/tests/test_wave_detector.py::test_rising_horizon_latches_incoming` (499 pass, 1 fail here; the
suite is genuinely green on the Pi). The test passes `max_fps=1000` to disable the rate cap in
`pi5/cv/wave_detector.py:119`, which gates on `time.monotonic()`. On Windows + Python 3.12 that is
`GetTickCount64()` at **15.625 ms** resolution (verified: 200k reads → 2 distinct values), so the 1 ms
interval reads as zero elapsed and `analyze()` returns its cached result. Only ~3 of 24 frames
actually process, `_hy` never reaches 5 samples, `rise_rate` stays `0.00`, severity plateaus at 0.07,
and `incoming` can never latch. Fix is `time.perf_counter()` in the rate gate, or inject a clock in
the test. **Not changed** — it is bench-adjacent CV code and was not this session's ask.

**Next steps:** (1) The IMU pickup block — **🚩 "PARKED 2026-07-30, PICK UP HERE"**, the four floating
strap pins and the bring-up sequence — rotated into `docs/session_journal_archive.md` with its entry
when this entry pushed the journal past 5. It is no longer read at session start; pull it from the
archive before touching the IMU. (2) Everything else still open is unchanged: the watchdog re-arm hole
(highest priority, firmware), `docs/esc_am32_conversion.md` Stage 1, the CDC write wedge, the 22 bad
doc checksums. (3) If V3 firmware work starts, the open Teensy concurrency-model call in
`docs/v3/V3_PCB_SESSION_CONTEXT.md` gates every rewritten module.

## 2026-07-31 — Motor runaway: a non-3D ESC turns "neutral" into 50 % throttle, and ESTOP into acceleration

**Worked on:** user reported the drive motors not spinning, with both ESCs powered and connected.
Diagnosed on the bench, hit a **runaway**, then added a firmware safety gate. Props were off
throughout; drive pack is now unplugged.

### What happened

Bench sweep with props off, one motor at a time, then a staged reverse ramp. The **AM32 (left/GP19)
behaved correctly the whole time**. The **BLHeli-32 (right/GP20)** sat inert, then **armed partway
through and kept running after the test ended — through `SET_THR 0,0` and through `ESTOP`.**

Cause: `escs.py` maps duty 0.0 to a 1.5 ms pulse and calls it neutral, which is **only true in
bi-directional / 3D mode**. The BLHeli-32 was never configured (the flagged "Next steps (1)", never
done), so in stock normal mode it reads that same 1.5 ms as **~50 % throttle**:

| stage | pulse | what the BLHeli did |
|---|---|---|
| power-up / neutral | 1.500 ms | ~50 % throttle → **refused to arm** — which is why it looked dead |
| `-100` | **1.000 ms** | its *throttle zero* → **armed** |
| back to "neutral" | 1.500 ms | **~50 % throttle → ran on** |

### 🔴 The generalisation, which is the actually serious part

**Every stop this firmware can express is 1.5 ms** — neutral, `escs.stop()`,
`motor_control.estop()`, and the heartbeat watchdog. So against a normal-mode ESC *the entire safety
system commands half throttle*. With props on and in the water, hitting E-STOP would drive the boat
forward. Only an explicit `-100` stopped it.

And a mixed pair has **no safe state at all** — 1.5 ms stops a 3D ESC but is 50 % to a normal one;
1.0 ms stops a normal one but is **full reverse** to a 3D one. No single pulse width stops both.

### The guard (deployed and verified on hardware)

`escs.BIDIR_CONFIRMED` — per-ESC, **defaults to False on both**, all-or-nothing (one unconfirmed ESC
blocks the whole drive train, because of the no-shared-stop-pulse argument above).

- **Hard floor in `escs.set_duty()`**: while unconfirmed it emits *only* 1.5 ms, whatever it is
  asked for. Enforced at the lowest level so SBUS, a mission, or a REPL poke cannot route around it.
  Holding 1.5 ms is what keeps a normal-mode ESC **inert** — it refuses to arm; the pulse that must
  never be emitted is its arming pulse (1.000 ms), and now cannot be.
- `set_throttle()` → `(False, "ESC_UNSAFE")`; **every** value refused including 0, since 0 is not a
  stop for a normal-mode ESC. `set_throttle_rc()` (SBUS) gated too. ESTOP still outranks it and
  keeps its own distinct reason.
- One-shot `CRIT ESC_UNSAFE` alert on the **first refused SET_THR**, not at boot — the Pi usually
  connects after the Pico has booted, so a boot alert would reach nobody. Keeps it out of the
  per-cycle SENSOR_FAULT stream.
- Loud boot banner; `navigator._log_thr_error()` prints the recovery step.

**Verified on the real Pico** (drive pack out): banner shows the block; `$NAK,…,SET_THR,ESC_UNSAFE`
for both 30 % and 0; `$ALERT,0,CRIT,ESC_UNSAFE,LEFT/AM32,RIGHT/BLHeli32` fires exactly once (0
repeats in the following 6 s); and a direct `set_duty(-1.0)` — the exact call that armed the ESC —
now writes 4915 (1.500 ms), not 3277. **500 tests pass** (+18 new), ruff clean.

**Changed:** `firmware/boat-pico/escs.py` (gate + hard floor + docstring), `motor_control.py` (both
throttle paths), `main.py` (banner + one-shot alert), `pi5/navigation/navigator.py` (ESC_UNSAFE
recovery line), `docs/serial-protocol.md` (NAK reason + alert code), `docs/esc_setup.md` (new
"bi-directional gate" section + reworked first-spin checklist), new
`pi5/tests/test_esc_bidir_gate.py` (18 tests; first harness here that runs **firmware** modules on
CPython with `machine` stubbed — reusable pattern).

**Decisions / open questions:** `LEFT` is left `False` even though the AM32 demonstrably behaved
bi-directionally — that is strong evidence, not the read-it-back-in-the-config-tool confirmation the
gate asks for. Deliberately fail-safe; flip it when verified. The gate is **not clearable from the
Pi** by design: it needs an ESC config change plus a firmware edit.

### Then: asked to set 3D mode for them — can't, and the reason redirects the whole plan

Investigated properly before answering. **BLHeli_32 is closed source and was discontinued in 2024**;
`esc-configurator` supports only BLHeli_S / Bluejay / AM32, so there is **no open implementation of
the _32 settings protocol** to build a Pi-side tool from. This repo's `am32_config.py` and
`esc_passthrough.py` are AM32-only and say so. Declined to write one: it would mean reverse-engineering
a closed protocol and then writing EEPROM to the ESC that just ran away, with nothing to validate
against.

**Better path found, and it fixes the root cause rather than the instance:** the ESC is a
**FlashHobby FHD 70A on an STM32F051**, and AM32 has a first-class **`FLASHHOBBY_F051`** target
(`USE_SERIAL_TELEMETRY`, current + voltage sense defined). Converting puts **both ESCs on AM32** —
one firmware, one settings vocabulary, mixed-mode hazard class gone — makes `am32_config.py` work on
it, and makes ESC telemetry reachable.

**And it needs no ST-Link: the Pi 5 is the programmer.** OpenOCD 0.12 is already installed with
`raspberrypi5-gpiod.cfg`, the `linuxgpiod` + `cmsis-dap` drivers, `target/stm32f0x.cfg`, and
`stm32f1x unlock` for clearing BLHeli_32's SWD readout protection. Only collision is OpenOCD's
default SWDIO (**GPIO8** = the A4988's sleep pin) — remap to GPIO9; SWCLK GPIO11 and GND are already
free and adjacent (header pins 21 / 23 / 25).

**Full procedure written up in `docs/esc_am32_conversion.md`** — user is doing it in a later session.
Artefacts identified: `AM32_F051_BOOTLOADER_PA2_V17.hex` + `AM32_FLASHHOBBY_F051_2.20.hex`. Three
things flagged in that doc as unverified: the **PA2** bootloader choice is *inferred* (from
`FD6288_F051` sharing `HARDWARE_GROUP_F0_A` and being named "FD6288_PA2"), the chip must be checked
as a genuine STM32F051 and **not a CKS32F051 clone**, and **Stage 1 has never been run** — the
sandbox permission classifier blocked OpenOCD from driving GPIO, so the user must run it. Stage 2
(RDP clear) is **irreversible** — no going back to BLHeli_32.

**Next steps:** (1) **Work through `docs/esc_am32_conversion.md`** — non-destructive Stage 1
pre-flight first. (2) Afterwards, read the setting back, set `BIDIR_CONFIRMED` → True on **both**,
redeploy, re-run the first-spin checklist, and confirm the watchdog kills to an actual **stop**.
(3) While in there: solder the GP11 telemetry wire (never connected — `frames_ok = 0`) and re-tune
`COMP_R` off real erpm. (4) Still open from the previous entry: the watchdog re-arm hole, the 22 bad
doc checksums, the CDC write wedge. (5) Minor: the repo calls this ESC "FH-70A"; it is the
**FHD 70A**.

## 2026-07-30 — Bench check: the latched ESTOP was real, the GPS got a fix, and the watchdog does not re-arm

**Worked on:** "check the pico", then "check everything and clear the e stop". Diagnosis + one
one-line lint fix. No firmware changed — but a **new firmware safety bug** was found and is not fixed.

### 🔴 The watchdog never re-arms after a RESUME that isn't followed by a heartbeat

`watchdog._triggered` is a one-shot latch cleared **only** by `feed()`. So after a heartbeat-loss
ESTOP, a `RESUME` re-enables the motors while the watchdog stays in its already-triggered state:
`check()` keeps returning True but never calls `_on_timeout()` again. Measured directly —

```
RESUME with no HB ever fed  ->  IDLE
  ... 6.5 s later           ->  IDLE      (watchdog should have re-fired)
  SET_THR,0,0               ->  $ACK      *** motors enabled, heartbeat dead 6.5 s ***
```

Protection only returns once a real heartbeat arrives. This is worst combined with the **CDC write
wedge** already flagged twice: the wedge lets telemetry keep streaming (link looks healthy) while
commands stop → HB_LOST → ESTOP → operator clicks CLEAR E-STOP → motors armed with **no watchdog at
all**. Suggested fix: have `motor_control.resume()` call `watchdog.feed()`, which restarts the timer
*and* clears `_triggered`, giving a clean 3 s grace window that re-fires if no real HB follows.

Normal watchdog operation is fine and was re-verified: HB → `ACTIVE`, stop → ~3 s → `HB_LOST` + ESTOP.

### The latched ESTOP was real — and is now cleared

`$STATUS,1,ESTOP,001110,NONE` read straight off the wire, confirming the previous entry's
by-elimination diagnosis (`safety_overrides=NONE`, so not RC_ACTIVE). `RESUME` ACK'd, state → `IDLE`,
`SET_THR,0,0` → `$ACK`. **Bench left un-estopped**, i.e. in the no-watchdog state described above.
`$NAK,71,SET_THR,ESTOP` en route also validates this morning's NAK-reason fix reading `fields[1]`.

### ✅ The GPS has a 3D fix — the top open item from two entries ago is closed

`/dev/ttyAMA0` @38400: **151/151 NMEA checksums valid, 0 bad.** GGA quality **1**, **6 sats**,
HDOP 2.80, alt 158.7 m; RMC status **A** (valid). Taking the antenna outside worked.

### Link, and a measurement trap worth remembering

75/75 frames checksum-valid over 20 s; write path `TIOCOUTQ` 1280 → 0 in <200 ms. **No CDC wedge
today** — still intermittent, still unexplained. ⚠ Checksums are **decimal** (`"$%s*%d"`, both sides);
scoring them as hex reports ~75 % of a healthy link as corrupt. Separately, **all 22 concrete
examples in `docs/serial-protocol.md` have fabricated checksums** matching neither base (e.g.
`$SET_THR,13,40,40*71` should be `*125`); same in `pi5/comms/protocol.py:71`'s docstring. The spec's
*definition* ("decimal ASCII") is correct — only the worked examples are wrong. Not yet fixed.

### Everything else

- **Power — still the known unfixed PSU problem.** All 4 recent boots ended with **zero**
  clean-shutdown markers (hard power-offs); 5 boots today. 34 `Undervoltage detected!` events, all
  clustered 14:19–14:49, none in the last 4 boots. Currently `throttled=0x0`, 47.7 °C.
- **Cameras fine.** video0 + video2 both capture (640x480); video1/3 are metadata nodes.
  `config.yaml` already documents this trap and is correct (`left_device: 0`, `right_device: 2`).
- **Sensors unchanged:** elec rail 19.06 V / 67 % healthy; drive 0.21 V + winch 0.18 V (packs
  unplugged — correctly *not* flagged critical by the `> 5.0` guard); SHT41 #B alive (25.2 °C /
  48.7 %, pull-ups still holding); SHT41 #A dead; IMU dead; pod absent. Health `001110`.
- **Stepper** on real GPIO, not mock. **482 tests pass.**

**Changed:** `pi5/tests/test_pico_nak.py` — dropped an unused `Alert` import (the only `ruff` error in
`pi5`; `run_hardware.py` clean, firmware's 130 are MicroPython builtins + the documented intentional
bare-excepts and are not in the lint gate). Journal. Nothing else.

**Decisions / open questions:** the watchdog re-arm bug is firmware and needs a reflash, so it was
left for sign-off rather than changed unasked. Also spotted: `CLAUDE.md` says `pi5/config.yaml`
carries a `mode: simulator|hardware` flag — it does not; the entry points are `run_sim.py` /
`run_hardware.py`.

**Next steps:** (1) **Fix the watchdog re-arm** — highest priority, it is a live safety hole.
(2) Regenerate the 22 doc checksums + the docstring. (3) The bench is left **un-estopped with no
watchdog**; keep props off until the stack is running and heartbeating. (4) Still open: the CDC write
wedge, the parked IMU float-pin wiring, the stepper `find`/`burst` runs, the buoy screen's
false-positive gates.

## 2026-07-30 — Manual override: 429'd off the boat, and a NAK message that hid its own reason

**Worked on:** user report — "i get these when i try to run the manual override", with a log full of
`429 Too Many Requests` on `/api/manual/drive` and `SET_THR failed (manual): Command SET_THR NAK'd:
SET_THR`. Three separate faults, one per layer.

### 1. The rate limiter was starving the dashboard (the actual blocker)

`RateLimitMiddleware` counted **every** path against one 60 rpm per-IP bucket. Manual override
repeats `/api/manual/drive` at `MAN_HZ = 10` (600 rpm), so six seconds after arming, that bucket was
full and *everything* from that IP 429'd — the drive frames, `/api/map/objects`, telemetry, E-STOP.
The limiter was already below the dashboard's **idle** draw: objects 2 s + obstacles 3 s +
recordings 3 s ≈ **70 rpm** against a 60 rpm cap, which is the `/api/map/objects` 429 in the log.

Now counted **per (IP, path class)** with three classes: `/api/manual/drive` 900 rpm (10 Hz + the
extra keydown/keyup sends), sensitive paths unchanged at 10–20, default raised 60 → **300**. Buckets
also mean ordinary polling can no longer eat the E-STOP budget. Trade-off accepted and documented:
an abuser spreading traffic gets the sum of the limits — this bounds runaway client loops, the API
key and Tailscale-only exposure do the security.

### 2. The NAK reason was never being read

`NAK,<seq>,<command>,<reason>` — `_send_command` logged `fields[0]`, which is the *echoed command*.
Hence the tautology `SET_THR NAK'd: SET_THR`, with the one diagnostic in the frame (ESTOP /
RC_ACTIVE / RANGE / PARSE) thrown away. Reads `fields[1]` now and raises **`PicoNak`** (subclasses
RuntimeError, so existing `except` clauses are unaffected) carrying `.command` / `.reason`.
`docs/serial-protocol.md`'s sequence diagram said `NAK,seq,reason` — wrong, and the likely origin of
the bug; fixed to match the canonical §5 form.

### 3. Root cause of the NAKs: the Pico's ESTOP is latched, and nothing on the Pi knew

By elimination the reason can only be ESTOP or RC_ACTIVE (RANGE/PARSE are impossible — `manual_mix`
→ `_trim` returns clamped ints; RC_ACTIVE needs an explicit `RC_OVERRIDE`). The firmware's
`motor_control.estop()` is **sticky until RESUME**, `TEL` carries no estop field, and nothing polls
`GET_STATUS` — so a Pico latched by an `HB_LOST` (3 s watchdog, e.g. the *previous* server shutdown)
refuses every `SET_THR` from the next run, forever, silently. The dashboard meanwhile shows ARMED
with live throttle numbers on dead motors.

`PicoSerial.estopped` now mirrors it best-effort — set by an ESTOP-class ALERT
(`ESTOP_AUTO`/`HB_LOST`/`SBUS_LOST`), an `ESTOP` NAK, or an ESTOP we sent (latched *before* the ACK:
if the ACK is what gets lost, the boat is still stopped); cleared only by an ACK'd RESUME. Surfaced
as `pico_estopped` on nav telemetry + both manual endpoints, and shown in the panel as a note
pointing at **CLEAR E-STOP**. Deliberately **not** auto-cleared on arming manual or on reconnect —
silently clearing an estop someone set on purpose is the wrong direction to be wrong in, and the
first refused `SET_THR` re-latches the flag anyway, so it self-heals.

**Changed:**
- `pi5/server/rate_limit.py` — per-(IP, path-class) buckets; high-rate class for the drive tick
- `pi5/server/app.py` — `default_rpm=300`; `pico_estopped` in `_nav_out`, `_manual_state`, drive reply
- `pi5/comms/pico_serial.py` — `PicoNak`; reason = `fields[1]`; `estopped` latch mirror
- `pi5/navigation/navigator.py` — `_log_thr_error()`: de-duplicates the 5 Hz flood to once per 5 s
  and prints the recovery step for ESTOP / RC_ACTIVE
- `pi5/server/models.py`, `templates/command_center.html` — `pico_estopped` field + panel note
- `pi5/tests/test_rate_limit.py` (9), `pi5/tests/test_pico_nak.py` (15) — new; **480 pass**
- `docs/serial-protocol.md` — fixed the NAK diagram; documented the field offset + the latch

**Decisions / open questions:** the latched-ESTOP diagnosis is by elimination, not observed — the
server was down by the time I looked, so I could not read the live reason. The fixed log line now
prints it: **if the next run says `RC_ACTIVE` instead, the cause is different** (a stray
`RC_OVERRIDE`, not an estop). Unresolved: nothing ever polls `GET_STATUS`, so the Pico's authoritative
state string is still unused — a periodic poll would make `estopped` exact instead of inferred.

**Next steps:** (1) Restart the stack and arm manual — the 429s should be gone; if the boat still
does not move, read the new `SET_THR refused` line and click CLEAR E-STOP. (2) Consider adding estop
to `TEL` (or polling `GET_STATUS`) so the mirror cannot drift. (3) Still open from before: the
stepper `find`/`burst` runs, and the buoy screen's false-positive gates.

## 2026-07-30 — Drive ESCs moved onto the hull-leak connectors; WASD manual override in the dashboard

**Worked on:** two user requests. (1) Repurpose the hull-leak pins as the two drive-ESC signals, now
that the ESCs are mismatched hardware. (2) Add a game-style manual override to the command center.

### 1. Drive ESCs GP2/GP3 → GP19/GP20 (hull leak removed)

`escs.py` drove **GP2/GP3**, which belong to the MCP2515 on `Boat_PCB V2` and reach **no connector**
— the bench was tapping the Pico header directly. The two hull-leak connectors are JST-XH 2-pin
wired **1 = GND, 2 = signal**, i.e. exactly an ESC servo lead, so propulsion moved onto them.

| | pin | connector | ESC | motor | telemetry |
|---|---|---|---|---|---|
| **Left** | GP19 | J16 (ex-"Hull Leak Left") | NeutronRC 70A-G071 · **AM32** | Badass 2814-**1560 kv** | GP16 |
| **Right** | GP20 | J15 (ex-"Hull Leak Right") | FlashHobby FH-70A · **BLHeli-32** | Badass 2320-**1630 kv** | GP11 |

This relieves **three of the five MCP2515 clashes** (GP6 winch → GP21 earlier, now GP2/GP3).
**SBUS on GP7 still clashes** and has nowhere to go (GP0/GP1 dead).

PWM slices verified: GP19 = slice 1B (free once GP2/GP3 are released), GP20 = slice 2A, sharing
slice 2 with the winch on GP21 (2B). Same-slice channels share a *frequency* but keep independent
duty; both want 50 Hz. Noted at `MW_PIN` because it is a trap for a future edit.

**⚠ Hull leak sensing is gone.** `sensors.py` must never configure GP19/GP20 again — `sensors.init()`
runs *after* `motor_control.init()`, so a pull-up input there would fight live ESC PWM. That
ordering was the one genuine bug risk in this change.

`hull_status()` now returns **`--`**, not `DRY`: returning `DRY` would assert a dry hull on a boat
with no hull sensor. That required Pi-side changes, because `--` would otherwise read as a *leak* —
the sentry pre-roll trigger in `app.py`, plus two places in `command_center.html` that would have
raised a **false CRITICAL leak alarm**. `--` now renders muted. The pod leak sensor
(`pod_uart.leak_detected`) is the only remaining leak alarm.

Kv mismatch is trimmed in firmware only: **`motor_control.COMP_R = 0.957`** (1560/1630).
`navigation.motor_gain_*` deliberately left at 1.0 — setting both compensates twice.

**Changed:** `escs.py` (pins + docstring), `sensors.py` (leak removed), `main.py` (alerts, LED
condition, pin map, banner), `motor_control.py` (COMP_R, slice note), `esc_telem.py` +
`esc_passthrough.py` (docstrings; passthrough already derives pins from `escs.*` so it followed),
`docs/pin_map.md`, `docs/esc_setup.md` (now covers **both** ESCs), `docs/serial-protocol.md`,
`pi5/server/app.py`, `command_center.html`.

### 2. Manual (WASD) override

New: arm/disarm panel in CONTROLS with W/A/S/D (arrows too), a live speed-limit bar, L/R readout,
ALL STOP (Space), and lit key indicators.

Architecture: the endpoints are **thin and never touch the Pico** — they only feed the Navigator,
which owns the throttle. Manual is the **highest-priority branch in `_nav_loop`**, above stay mode.
Mixing lives in `navigator.manual_mix()` so it is testable in Python and uses the same `_trim()`
clamp as the autonomous path.

Safety, which is most of the work here:
- **Dead-man timeout** (`MANUAL_TIMEOUT_S = 0.75`). The browser repeats key state at 10 Hz; if
  nothing arrives the loop zeroes the motors itself. A closed tab, frozen renderer or dropped WiFi
  stops the boat with no operator action. The ESCs hold their last pulse forever otherwise.
- Must be **armed explicitly**; arming cancels goto/stay and starts *stale*, so the boat does not
  move until a key is actually pressed.
- **ESTOP disarms manual**, or the next keypress would drive straight through the ESTOP.
- `goto()`/`hold()` disarm manual **in the navigator**, so every caller (API + mission manager) is
  covered — otherwise manual would outrank a new target and the boat would sit still while the UI
  claimed it was under way.
- Refuses to arm while a mission is running (409) rather than silently aborting someone's survey.
- Browser releases all keys on blur / tab-hide / Escape — `keyup` never fires for a key held when
  the window loses focus.
- Combined W+D scales the *pair* instead of clamping one side, so full-speed turns keep their ratio
  rather than quietly straightening out.

**Changed:** `navigator.py` (manual state/mix/loop branch, NavConfig.manual_speed), `models.py`,
`app.py` (`/api/manual`, `/api/manual/drive`, `/api/manual/speed`, ESTOP interlock),
`command_center.html` (panel + CSS + input loop), `config.yaml`, new
`pi5/tests/test_manual_override.py`.

**Verification:** 456 tests pass (437 → +19 new). A 24-check smoke test of the handlers passed
(validation, mission interlock, ESTOP disarm, goto hand-back, NaN rejection, clamping). Dashboard JS
parses clean under `node --check`; all referenced element IDs exist. `httpx` is absent so
`TestClient` is unavailable — handlers were called directly instead; routes verified registered.

**Decisions / open questions:**
- Manual is Pi-side, **not** the Pico's SBUS `RC_OVERRIDE` path. It therefore depends on the USB
  link — which is exactly the link that wedged twice earlier today (see the entry below). The
  dead-man timeout is what covers that, but **the CDC wedge is now on the critical path for a
  control surface** and deserves the investigation it is already flagged for.
- ⚠ **None of the ESC re-pin work has run on hardware** — the changed pins are the ones being
  rewired. Boot banner should read `Drive ESCs: GP19(L,AM32,...)/GP20(R,BLHeli32,...) PWM 50Hz OK`.

**Next steps:**
1. Configure both ESCs before first spin-up — they are no longer identical: AM32 "Bi-Directional"
   vs BLHeli-32 **"3D mode"**, and BLHeli-32 also needs its **throttle range calibrated to
   1000–2000 µs** (AM32 auto-detects, BLHeli generally does not) and telemetry set to
   **continuous**, not DShot-request-only, or `esc_telem.py` gets nothing. Full table in
   `docs/esc_setup.md`. If it turns out to be BLHeli**_S** rather than _32, stock firmware has no 3D
   mode — reflash with Bluejay or the right motor will never reverse.
2. Tune `COMP_R` from 0.957 on the bench via ESC telemetry erpm — Kv only equalises *no-load* rpm and
   these are different frames (2814 vs 2320).
3. Bench-test manual override with props **off** first; confirm the dead-man actually cuts by
   closing the tab mid-throttle.
