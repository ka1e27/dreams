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

## 2026-07-29 — GPS bench test: the module can't reach the Pico, and the board gives it no path

**Worked on:** user plugged in the GPS, it wasn't working, asked me to test it. Diagnosed on the live
bench Pico (no code changes to firmware or the nav stack).

**Result — the GPS is not connected to anything that can read it.** Three independent checks:
1. **Nothing is transmitting.** Scanned 18 Pico GPIOs (all but the ESC/winch/NeoPixel outputs and the
   dead GP0/GP1): **zero edges** over 1.3 s each, and **GP4/GP5 both read floating** (internal pull-up
   → 1, pull-down → 0). No NMEA anywhere on the Pico.
2. **No path exists on the board.** Confirmed by solving the schematic's net graph directly
   (`Boat_PCB.kicad_sch`; the solver self-validates — all eight Pico GND pads and VSYS/VBUS resolve
   correctly). **J7, the "GPS + Compass" connector, carries no UART:** 1=GP14, 2=GP15, 3=GP9, 4=GP8,
   5=**VSYS 5 V**, 6=GND. GP4 goes only to U1.15 (MCP2515 SO) and GP5 to the GND net. This confirms the
   2026-07-28 audit's claim from the board file rather than the netlist export.
3. **Not on the Pi either.** No USB serial device but the Pico (`lsusb`, `/dev/serial/by-id`), and Pi
   GPIO14/15 measure floating with `pinctrl` and are muxed to function *none* — so nothing is wired to
   the Pi's header UART, and `/dev/serial0` (→ ttyAMA10) isn't connected to those pins anyway.

**Two live-board facts that contradict the docs — measurement wins, KiCad is stale (again):**
- **GP5 is NOT tied to GND on the built board** (an internal ~55 kΩ pull-up takes it to 1, so there is
  no low-resistance path). The schematic *does* tie it — `docs/pin_map.md` and `main.py`'s docstring
  state this as as-built fact. A jumper into GP5 therefore works, which is what makes a bench test
  possible at all.
- **GP9 (= J7.3) reads hard low against the internal pull-up** — a real short to GND, and the schematic
  shows no such tie. If a module is sitting in J7, its pin 3 is a ground, i.e. **its pinout doesn't
  match J7's order**. That also explains why I²C0 scans empty. J7.5 is 5 V, so a mismatched plug can put
  5 V on a module data pin or try to power the module through a Pico GPIO — flagged to the user; leave
  J7 unplugged until the module's pinout is checked.
- Also measured: U1 (MCP2515) is **not driving GP4**, so the documented UART-TX-vs-SO contention isn't
  live on this board. Electronics M18 present (GP27 → 17.7 V); drive + winch packs disconnected
  (GP26/GP28 ≈ 0.2 V), which is why a firmware restart was safe here.

**Changed:**
- `pi5/scripts/gps_probe.py` (NEW) — four-mode bench tool, following `am32_config.py`'s
  self-documenting-CLI pattern. `boat` (read-only: decodes the firmware's TEL health bit + GPS
  SENSOR_FAULT alerts, and detects "firmware isn't running"), `pins` (the GPIO scan above),
  `uart` (opens UART1 on GP5 and parses what arrives), `host` (sniffs a USB-TTL adapter, auto-baud).
  Reuses `deploy_pico._request_repl` so the REPL modes drop the firmware via `$REFLASH` — which estops
  the motors first — and restarts it after. Reports the distinction that matters on a bench: **no data
  at all** (wiring/power) vs **data but no fix** (antenna/sky view). The docstring carries the measured
  J7 pinout and the 3-jumper bypass so nobody re-derives this.

**Verified (on the Pi):** all four modes exercised against the live Pico; `pins` reproduced the manual
scan including the GP9 short; `boat` reported `health=001110`, GPS bit 0, 9 `SENSOR_FAULT,gps` alerts in
8 s. `pytest pi5/tests` **293 green**, ruff clean.

**Decisions / open questions:** the Pico was found **halted at the REPL** — the firmware wasn't running,
so nothing was reading the GPS regardless of wiring. I left it **running** (drive/winch rails
disconnected, so ESC PWM at neutral can't move anything). Awaiting the user on which bench path to take
(jumper GPS TX → GP5, or a USB-TTL adapter) and on what module it actually is.
**Separate leftover bug, not fixed:** `firmware/boat-pico/main.py:589` still prints
`Hull: GP17(L) GP18(R)` in the boot banner, but `sensors.py` moved to GP19/GP20 on 2026-07-28 — the
banner is now misleading. Also `IMU: I2C0 GP8/GP9 addr=0x4A FAIL` every boot: the board wires the IMU
connector **J5.3/J5.4 to GP15/GP14** (the SHT41 #B SoftI2C bus), not to I²C0 GP8/GP9 where
`compass.py` looks — a firmware-vs-board mismatch of the same family as the GPS one, worth its own pass.

**Re-test after the user re-seated the module in J7** (they asked specifically about GP8 / GP9 — J7.4
and J7.3). Still no GPS, and now measured properly rather than inferred:
- **GP8 changed from floating to driven high**, but it is *not* transmitting: 10 s of PIO soft-UART RX at
  9600 captured **0 bytes**. It's a pull-up, not a TX. (GP8 needed the soft UART — hardware UART1 RX can
  only be GP5/GP9/GP21/GP25, so GP8 is otherwise unlistenable.)
- **GP9 is still held at ground:** PIO captured **5356 bytes of pure 0x00** — one endless start bit,
  which is the signature of a grounded pin rather than data. Hardware UART1 on GP9 gave 0 bytes at
  9600/38400/115200.
- Still **zero edges on all 18 scanned pins**, which rules out *any* baud (edge counting is
  baud-independent), and both I²C buses re-scanned: nothing on GP8/GP9 (SCL held low, so it can't work)
  and only the SHT41 `0x44` on GP14/GP15. No compass, no u-blox DDC at `0x42` → the module isn't
  answering on I²C either, so it is not alive through J7.
- Read together: one J7 pin held to GND and another pulled high means **the module's connector isn't
  landing where J7 expects**. Since J7.5 is 5 V, a reversed/offset plug puts 5 V on one of the module's
  signal pins — or on its GND pin. User told to unplug it pending the module's pinout.

**Changed (second pass):**
- `pi5/scripts/gps_probe.py` — added a **`soft` mode**: PIO 8N1 soft-UART RX on *any* pin, reusing the
  same PIO program as `esc_telem.py`/`sbus.py` at the GPS baud. Needed for GP8, and it's also the shape a
  permanent fix would take given no connector routes a hardware UART. Recognises the all-zeros case and
  names it (grounded pin, not a transmitter) instead of reporting it as garbage data. Also a `--pins`
  filter on the scan for fast re-checks, refusing pins outside the safe list. ruff clean, 293 still green.

**CORRECTION — J7 *is* the GPS UART; the firmware is on the wrong pins.** The user pointed out that
GP8/GP9 are UART1, and they're right: the RP2040 muxes UART1 TX to GP4/**GP8**/GP20/GP24 and RX to
GP5/**GP9**/GP21/GP25. So J7.4/J7.3 are a legitimate UART1 TX/RX pair and **the connector was laid out as
the GPS serial link** — my earlier "no board connector carries a UART" was wrong, and it came from
`docs/pin_map.md` listing GP8/GP9 as I²C0 only when they are dual-function. The board-side fix is
`gps.init` → `UART(1, tx=Pin(8), rx=Pin(9))`, no rewiring. GP4/GP5, which the firmware uses today, reach
no connector at all.

**Why it still doesn't work, and why the firmware change is NOT yet applied:** the user reports the
module's LED blinking constantly, i.e. it is powered and (on u-blox parts, TIMEPULSE at 1 Hz) very likely
holding a fix and transmitting. But **GP9 — the GPS TX line — is shorted to GND**, so nothing arrives:
hardware UART1 on GP8/GP9 at 9600 captured 0 bytes (the UART drops the endless framing errors), while a
PIO capture on the same pin returned 5356 bytes of pure 0x00, the signature of a held-low line. The
schematic has no such tie, so it is a build fault — Pico pads **12 (GP9) and 13 (GND) are adjacent**, so a
solder bridge is the first thing to check. Separately, GP8 is currently held high by something
unidentified; pointing the firmware's UART **TX** at GP8 before knowing what that is could drive a GPIO
into a supply rail, so the one-line change waits on the module's pinout.

**FAULT LOCALISED — a hard short across three adjacent Pico pads: 12 (GP9) · 13 (GND) · 14 (GP10).**
User confirmed continuity GP9→GND with a multimeter and localised it to the Pico, not the PCB. Probing
every pad that neighbours a GND pad (7, 9, 12, 14, 17, 19, 22, 24, 27, 29) found **GP9 and GP10 both
shorted to GND and every other one clean** — so it's one localised blob spanning pads 12-13-14, not a
systematic soldering problem. Software bound on the short: under ~18 kΩ, since the internal ~55 kΩ
pull-up can't lift either pin above logic 0.

**One blob explains three separate symptoms:**
- **GPS dead** — GP9 is J7.3 and UART1 RX; the module's TX drives into the short.
- **Status NeoPixel dead** — GP10 is `status_led.PIN` (J12). Free visual confirmation: that LED can never
  have lit. Worse, `status_led.py` drives GP10 as an *output*, so every LED update since the board was
  built has been sourcing current into a dead short — the pin may itself be damaged by now.
- **`IMU: I2C0 GP8/GP9 addr=0x4A FAIL` on every boot** — GP9 is also SCL0, and a clock line held low
  kills the bus.

**It is a HARD short, and not the LED harness.** User reports J12 unplugged and no visible solder
bridge anywhere — yet GP10 (whose only board net is J12.2) is still shorted, so the fault is at the Pico
or in its mount, not in a harness. Quantified it by forcing the pad's DRIVE field to 2 mA
(`PADS_BANK0 + 0x04 + 4n`, bits 5:4) and reading the **real pad level** from `SIO.GPIO_IN` (0xd0000004)
rather than the output latch: **GP10 driven high still reads 0** — the driver loses. Control pin GP5 reads
1 under the identical test, so the method is sound. Tested GP10 rather than GP9 because `status_led.py`
has been driving GP10 into this fault continuously anyway. A hard short rules out flux/contamination
(that would be kΩ and the 2 mA driver would win); this is metal or damaged silicon.

**Firmware left STOPPED deliberately.** It drives GP10 into the dead short on every status-LED update, so
running it is active stress on a suspect pin. Restart with
`.venv/bin/python -m mpremote connect /dev/ttyACM0 reset` when needed.

**Hypothesis worth testing: this is the schematic's GP5-to-GND tie, executed on the wrong pads.** The user
asked whether GP5 being grounded could explain it. It can't cause it (independent pins), and **GP5 is
measurably free on this board** — it read 1 in the same drive test GP10 failed, which *voids the
2026-07-28 audit's loudest hardware worry* ("GP5 tied to GND, so the GPS can never work"). But the
inversion is suspicious: the design ties exactly one Pico GPIO to its adjacent GND pad (pad 7 → pad 8),
and the board instead ties two GPIOs to *their* adjacent GND pad (pads 12/14 → pad 13) while the designed
tie is absent. Same motif, wrong location. This board has form for exactly that class of error — the
2026-07-28 audit found J3's footprint has its odd/even rows transposed. If the hypothesis holds, the
copper is on the **carrier board**, not the Pico, and the fix is cutting one connection.

**Repo gap — the board's routing has no source of truth here.** `Boat_PCB.kicad_pcb` contains **zero
copper**: no nets, no tracks, no vias, no zones, only placed footprints. No gerbers in the repo either, and
`report.txt` is a stale KiCad update log (still lists `F1`, and shows GP5/GP8/GP9/GP10 all *unconnected*).
So every "the board does X" claim in the docs — including this session's — actually derives from the
**schematic**, and the physical board demonstrably diverges from it. Flagged as a V3 blocker: nobody can
review this board's wiring from the repo.

**Option analysed, no code written: move the GPS to the Pi 5.** Traced the position path — the whole nav
stack reads `PicoSerial.telemetry` (`pi5/comms/pico_serial.py:22`), written *only* by `_handle_tel`, and
`navigator.py:399-437` consumes `tel.lat`/`tel.lon`. So a Pi-side NMEA reader writing into that one object
needs **no other changes**, and would deliver position at the module's native 1-10 Hz rather than relayed
at 1 Hz through TEL. Heading must stay on `tel.heading` (Pico compass). Three gotchas: `SENSOR_FAULT,gps`
would spam forever (`main.py:452`) and reported state would sit at `WARN` (`main.py:481`) — checked, and
**neither cuts the motors**; the GPS health bit stays 0; and **the Pod Pico shares the GPS UART**
(`main.py:555` `pod_uart.init(gps._uart)`, demuxed by sentence prefix in `task_uart1_reader`), so
`gps.init()` cannot simply be dropped. Wiring: a USB-TTL dongle → `/dev/ttyUSB0` (respects the "Pi 5 =
USB only" locked decision; `gps_probe host` already tests it), or the Pi's GPIO14/15 — measured floating,
function `none` — which needs `dtoverlay=uart0` plus the serial console freed and would then collide with
`am32_config.py`, which uses the same two pins. **Main attraction:** it routes around the dead GP9
entirely, so it doesn't matter whether the short is the Pico or the board. Weighed against the one-wire
GP5 jumper, which works today with zero code changes. Awaiting the user's choice.

**Next steps:** (1) Look at the Pico's **underside / castellations** and its mount — a top-side-invisible
bridge or wicked solder under the module fits a hard short with nothing visible. If it's socketed, pull it
and measure GP9→GND and GP10→GND on the Pico **alone**; that's the only way to separate Pico from carrier
board conclusively. Still shorted standalone with nothing visible → internal damage, replace the Pico.
(2) **Zero-rework workaround, which does not need GP9 at all:** move the module's TX wire from J7.3 to
Pico **GP5 (pin 7)**, leaving VCC/GND in J7.5/J7.6. GP5 measures floating and passed the drive test, and
`gps.init` *already* listens on GP5 — so the GPS works with **no firmware change and no rework**.
(3) Consequences of writing GP9/GP10 off: the status NeoPixel needs a jumper from J12.2 to a free pin
(GP6 measures floating — the MCP2515 isn't driving it) plus a one-line `status_led.PIN` change; and I²C0
is permanently dead, which makes moving `compass.py` to SoftI2C **GP14/GP15** mandatory rather than
merely correct — that is where the board wires J7's compass pins anyway.
(4) Alternatively, if the short is cleared, apply `UART(1, tx=Pin(8), rx=Pin(9))` in
`gps.init`, or move just the GPS TX wire from J7.3 to Pico GP5 (pin 7), which needs **no** firmware
change since GP5 is what `gps.init` already listens on and it measures floating. (4) `compass.py` is on
I²C0 GP8/GP9 but the board puts J7's compass pins on **GP14/GP15** (SoftI2C #B, shared with J5 + both
SHT41s) — the firmware has J7's UART and I²C swapped relative to the board; worth its own pass.
(5) Fix `docs/pin_map.md`: GP8/GP9 are **I²C0 *or* UART1**, and J7 is the GPS UART + compass connector.

---

## 2026-07-28 — Applied the pin-map audit to code: winch → GP21, stepper 8× fix, divider ratio

**Worked on:** pulled `e27ee7f` (the Boat_PCB V2 netlist audit below) and applied the three items it
had flagged but left unfixed in code.

**Changed:**
- `firmware/boat-pico/motor_control.py` — winch PWM **GP6 → GP21** (`MW_PIN`). The board routes the
  winch signal to GP21 (J8.1 + J9.1 in parallel); GP6 is the MCP2515's `~INT`, so the old pin drove
  the CAN chip, not the winch ESC. GP21 was unused by firmware, making this the **only** one of the
  five CAN-contested pins (GP2/3/4/6/7) that a pin move can resolve.
- `pi5/cv/stepper.py`, `pi5/config.yaml`, `pi5/cv/stepper_test.py`, `run_hardware.py` —
  `steps_per_rev` **3200 → 400**. The A4988 is half step (MS1 high off the Pi's 3V3, MS2/MS3
  hard-grounded), not 1/16. Verified: a commanded 10° pan now moves 9.9°, not 80°. It also fixes an
  8× *overspeed* — the pulse train ran at 8× the commanded rpm, so the motor was likely skipping
  steps rather than tracking. Docstring rewritten: RESET is tied to SLEEP on the board (so
  `reset_pin` stays null), plus the auto-sleep-resets-the-translator drift caveat and the
  VDD-comes-from-the-Pi dependency.
- `firmware/boat-pico/sensors.py` — **`INV_P_RATIO` 14.0 → 6.6.** User confirmed the physical board
  has **56k/10k fitted on all three** dividers, so every rail reconstructs at ×6.6. At ×14.0 a full
  21 V drive pack reported 16.4 V — under `P_WARN` (17.0), a hair over `P_CRIT` (16.0) — i.e. return-
  to-home on a full battery. Verified all three rails now report 21.00/18.00/17.00/16.00 V exactly
  and trip WARN/CRIT at the right pack voltages.
- Docs synced: `docs/pin_map.md`, `CLAUDE.md`, `docs/battery_architecture.md`,
  `docs/pcb_design_notes.md`, `docs/PROJECT_CONTEXT.md`, `docs/hardware_changes_v2_to_testbench.md`,
  and the `main.py`/`sensors.py`/`esc_telem.py` docstrings. Also fixed a stale row the pulled pin map
  still carried: the PIO buses table listed ESC telemetry on GP19 (the hull-leak connector) after the
  table above it had already moved it to GP11.

**Verified (on the Pi):** `pytest pi5/tests` **293 green**, ruff clean, firmware `py_compile` OK, sim
boots with `/` and `/planner` 200. A static pin-claim sweep over the Boat Pico firmware shows **zero
collisions** and matches `docs/pin_map.md` exactly (GP2/3, 4/5, 7, 8/9, 10, 11, 12–15, 16, 19/20, 21,
26–28 claimed; GP6/17/18/22 free).

**Decisions / open questions:** the audit's "as-built" divider values (×17.92/×4.33/×6.56) came from
the **KiCad netlist, which is the stale copy** — the populated board is 56k/10k throughout. Docs now
say so in all five places and flag the KiCad edit as the outstanding task; 13k/30k/18k aren't in the
on-hand resistor kit, which corroborates they were never fitted. That also **voids the GP27
over-range warning** (4.15 V into a 3.3 V pin) from the previous entry. Nothing committed — tree left
for review.

**Next steps:** unchanged from the entry below except the three items now closed — still open: route
the MCP2515 `~CS`, free GP5 before expecting CAN or GPS to work, fit the 100 nF ADC caps + I²C
pull-ups, update the six divider values in KiCad, reposition the R9/R11/R2 reference texts, re-export
the gerbers under version control.

---

## 2026-07-28 — Boat_PCB V2 netlist audit; pin maps rebuilt from the board; hull leak + ESC telem realigned

**Worked on:** full wiring double-check of `Boat_PCB V2` against the KiCad netlist, then updating every
pin map to match reality. Verified three ways: an S-expression parse of `Boat_PCB.kicad_pcb`, a raw
regex extraction, and `kicad-cli sch export netlist` from the schematic. DRC + ERC run with
`kicad-cli` 10.0.5. Board files were unchanged by the 18 commits pulled from origin, so the audit
holds against current `single-hull-test-bench`.

**Changed:**
- `firmware/boat-pico/sensors.py` — hull leak **GP17/GP18 → GP19/GP20** to match the board's actual
  J16/J15 connectors. On V2, GP17/GP18 are the BNO085's RST/INT on J5, so the old pins were reading
  the IMU's control lines, not leak contacts. Docstring now flags that the quoted divider values are
  the M18 *target*, not what's fitted.
- `firmware/boat-pico/esc_telem.py` — right ESC telemetry **GP19 → GP11**. GP19 is the J16 hull-leak
  connector; a leak switch shorts to GND and would have held the telemetry line low. GP11/GP16 are
  the only unconnected pins on V2, so both taps are now clash-free — all four inputs fit.
- `docs/pin_map.md` — Boat Pico table was missing **ten pins** (GP2/3/6/7/11/16/19/20/21/22). Added
  them plus a verified `Board (V2)` column, a full connector index, the divider-mismatch table, and
  the missing-pull-up / 5 V-on-sensor-connectors warnings. Corrected the stepper section: it claimed
  1/16 microstepping but MS2/MS3 are grounded → **half step**.
- `docs/pcb_design_notes.md` — described a board that doesn't exist (BT2/BT3, F1–F4, XT90 outputs
  J4/J5, DHT11, IMU on J10, "no Pi 5 on this board"). Rebuilt from the netlist; added the CAN
  interface, A4988, DRC/ERC status. It also mislabelled R9 as a leak pull-up.
- `CLAUDE.md` — quick-orientation pin list, Boat_PCB highlights table, architecture diagram.
- `docs/esc_telemetry.md`, `docs/esc_setup.md`, `docs/am32_config.md`, `pi5/scripts/am32_config.py` —
  GP19 → GP11 for the right telemetry tap.
- `firmware/pod-pico/main.py` — docstring was missing GP22 (pressure ADC), which `sensors.py` uses.

**Decisions / open questions:**
- **`pi5/cv/stepper.py` has an 8× error and is NOT yet fixed.** It assumes 1/16 microstepping
  (`steps_per_rev = 3200`) but the board is half step (400). A commanded 10° pan travels 80° and blows
  through the soft limits. One-line fix, left for a deliberate change.
- **Three hard board faults, all inherited from V1:** MCP2515 `~CS` (U1.16) tied to GND (SPI can't
  frame transactions); Pico **GP5 tied to GND** (kills UART1 RX / GPS, and GP4 sits on the MCP2515's
  `SO` output — two drivers on one net); A4988 VDD has no on-board supply, fed only from the Pi's 3V3
  via J3 pad 2.
- **GP2/3/4/6/7 conflict is unresolved and unresolvable by pin moves** — the V2 board commits them to
  the MCP2515, this branch drives ESCs/winch/SBUS/GPS on them, and no free pins remain.
- **Silkscreen swap:** R9's and R11's reference text sit over each other's footprints (verified
  geometrically — 6.32 mm offsets vs. 5.08 mm elsewhere). Fit 1 kΩ at the pad printed "R11" and 10 kΩ
  at "R9". R2's label has drifted over J4.
- **J3's pad numbering is transposed** (odd/even rows shifted one position), so schematic pad *N* =
  Pi pin *N∓1*. Confirmed by 6/6 power-pin alignment and by matching `stepper.py`'s BCM numbers.
  Reading Pi pins off the schematic pad numbers gives a wrong — and alarming — answer.
- Dividers still pre-M18: drive ×17.92 (firmware expects ×14.0), elec ×4.33 (expects ×6.6, and
  over-range on an M18 at 4.15 V into a 3.3 V pin). Fitting 56k/10k on all three gives ×6.6 exactly;
  then set `INV_P_RATIO = 6.6`. Also no ADC filter caps and no I²C pull-ups anywhere.

**Next steps:** fix `stepper.py`'s `steps_per_rev`; rework the three dividers + add the 100 nF ADC
caps and I²C pull-ups; route `~CS` and free GP5 before expecting CAN or GPS to work; reposition the
three reference texts and annotate the mounting holes MH1–MH4; re-export the gerbers (those in
`Boat_PCB V2/` predate the current `.kicad_pcb`) and get them under version control.

---

## 2026-07-28 — Buoy detection was dead on hardware; inference thread budget; health-loop forks; dashboard safety UI

**Worked on:** `/goal` — three max-effort passes: make the stack cheaper on the Pi, *verify* buoy +
person-in-water detection, and fix the dashboard's buttons/clutter. Pass 1 = 4 parallel Opus audits
(read-only, so they added no CPU load); pass 2 = 3 fresh Opus agents re-reviewing my own diff; pass 3 =
verification on the Pi. Everything ran under a 1 Hz `EXT5V`/throttle watchdog with heavy commands pinned
to 2 cores (`nice -n 15 taskset -c 0,1`).

**Headline: the boat could not detect a buoy at all.** The active detector is
`pi5/cv/models/yolov8n_ncnn_model` — generic **COCO, 80 classes, no `buoy`**. `maritime_yolov8n_info.json`
is a placeholder (`mAP50: 0.0`) and its weights are absent, so *nothing* ever emitted the label that
`threat_assessor` grades WARNING and `object_memory` charts as a PERMANENT marker. The entire
"confirm a buoy → drop a GPS marker" feature (docs/object_memory.md) was only ever exercised by the
sim's ground-truth `SimObjectMapper`. The existing buoy/person tests pass because `FakeOverlay` injects
detections — YOLO never runs in them. `water_seg.onnx` is also absent, so Tier-1b hybrid seg is off.

**Changed:**
- `pi5/cv/buoy_detector.py` (NEW) — classical colour/shape buoy screen: one HSV threshold pass +
  contour filter (saturation / solidity / area / aspect), **measured 0.62–0.96 ms/frame** on this Pi
  (640×480→1280×720, ripple noise) vs ~30 ms for a YOLO pass. Emits the same
  `(x1,y1,x2,y2,label,conf)` tuples, so boxes/distance/radar/threat/map all work unchanged.
  **Suppression uses containment, not IoU** — an orange life jacket is a small blob *inside* a large
  `person` box where IoU is tiny, so an IoU gate would have charted a phantom PERMANENT buoy on a
  swimmer. Green is off by default (sunlit foliage) and the top 35% of frame is skipped (sky/treeline).
- `pi5/cv/vision_overlay.py` — `class_conf` per-class confidence floors (backend runs at the lowest
  floor, each box then filtered by its own class) so a distant swimmer survives at 0.25 without
  flooding other classes; `buoy_fallback` that **auto-disables when the loaded model emits `buoy`
  itself**; `_infer_conf` is a property (the CONF slider mutates `_cfg.conf`, so a cached copy went stale).
- `pi5/cv/threat_assessor.py` — `swimmer` was graded **INFO, i.e. not tracked at all**, while
  `object_memory` canonicalises it to `person`. Added it plus jetski/raft/canoe/paddleboard as CRITICAL.
- `pi5/cv/cpu_budget.py` (NEW) + `ncnn_detector`/`onnx_detector`/`ort_utils`/`segmentation` — inference
  no longer pins **all four** Pi 5 cores. Measured (yolov8n@320, NCNN, median of 15): 1 thread 27.9 ms /
  2 → 18.4 / 3 → 19.2 / 4 → 17.7. Thread 2 gets ~96% of the speed-up; **the 4-thread pass drove this Pi's
  sticky throttle flags `0x0` → `0x50000` (under-voltage occurred + throttling occurred)**. Since
  `detect_max_fps: 15` is a 66.7 ms budget, even one thread clears the cap with 2.4× headroom — the extra
  threads bought latency nobody consumes and cost a brown-out. Default is now cores−2; override via
  `camera.detection.num_threads` / `vision.seg_num_threads`.
- `pi5/server/app.py` — the 1 Hz health loop forked **7 `vcgencmd` subprocesses every second, forever**
  (604,800/day). Temp + ARM clock now come from sysfs (~37 µs for both), the 4 voltage rails are sampled
  every 10 s, and `get_throttled` still forks every tick because it *is* the under-voltage alarm.
  Measured 7 → 1.4 forks/s, child CPU **2.5 → 0.5 ms/s**, tick wall time 19.2 → 2.7 ms. During an
  **active** throttle (`_throttled_now`, live bits 0-3 only — the sticky 16-19 bits latch until reboot)
  it spends the fork on `measure_clock arm` so the operator never sees a masked clock while debugging.
- `pi5/server/templates/command_center.html` — removed two **duplicated live-handler** control groups
  from COMMANDS (VISION SEG/YOLO/AVOID and RADAR BAR CENTER/SCAN/STOP); both existed twice, and only
  the surviving copies are the ones `renderVision()` actually keeps in sync. Replaced **every** native
  `window.confirm()` with an in-page `#mConfirm` dialog (a browser can suppress native dialogs
  permanently — unacceptable for ABORT / CLEAR E-STOP / DELETE clip / CLEAR MARKS / ARM PASSTHROUGH /
  ESC WRITE). Added a real focus trap + focus restore + ESC-to-close to back up the new
  `role=dialog aria-modal=true` (aria-modal without a trap is a promise the page was breaking). Put a
  deliberate gap between E-STOP and CLEAR E-STOP. Moved CLEAR MARKS out of the sim-only group — the
  buoy screen charts real markers on hardware now. Added `min-width:0` + 1200/820 px breakpoints for the
  8-group camera bar and `pointer:coarse` tap targets for dockside tablet use.

**Verified (on the Pi):** `pytest pi5/tests` **293 green** (from 247, **+46**), ruff clean, firmware
`py_compile` OK, inline `<script>` passes `node --check`, div balance 304/304, no undefined onclick
handlers. Proved the detection chain on the **live** backend, not a mock: ncnn loads (80 COCO classes) →
fallback auto-activates → `_raw_detect` returned `('buoy', 0.681)` boxed on the target →
`threat_level_for` = WARNING → `category_for` = PERMANENT. Sim booted, `/` and `/planner` 200, `/ws/health`
frames carry correct `temp_c` / `clock_mhz` (tracked 1500↔2400 MHz) / decoded throttle / volts, and
`sysfs` vs `vcgencmd` cross-checked (clock delta 0.0 MHz over 6 samples).

**Pass-2 reviewers found 4 real bugs in my own changes — all fixed:** (1) the volts cache guard used
`_volts_cache is not None`, but off a Pi the reading legitimately *is* None, so it re-forked 4 probes
every tick — worse than before; now keyed off a separate `_volts_sampled` flag. (2) Buoy suppression ran
against *unfiltered* YOLO boxes, so a sub-threshold box (boat @ 0.32 vs its 0.40 floor) could kill a buoy
and then be dropped itself, leaving the operator with neither. (3) `x1`/`y1` weren't clamped to the frame.
(4) The segmentation model silently inherited the new thread count — now explicit via config.
**Rejected:** the per-client telemetry-recompute "MED" finding (~300 µs/s with 1–2 dashboards; not worth
the staleness risk), a raw-BGR recorder pre-roll (+330 MB on a 4 GB Pi — worse than the JPEG ring), and a
claim that `scaling_cur_freq` systematically masks throttling (6 back-to-back samples showed *exact*
agreement with `measure_clock arm` at both 1500 and 2400 MHz; the RPi cpufreq driver queries the
firmware). The concern was still addressed via the throttle-aware fallback above.

**Decisions / open questions:** the classical screen is a **stopgap, not a substitute for a trained
model** — it finds red/orange/yellow buoys by colour, so it will miss unlit black/green marks and wants
on-water tuning of `min_sat` / `roi_top_frac`. Charting a buoy as a *map marker* still needs **stereo
range**, so a mono rig detects and grades buoys but won't place them. This Pi now carries sticky
`0x50000` flags from the thread benchmark — the 27 W PSU swap from the 2026-07-27 entry is still
outstanding and still recommended. Nothing committed — tree left for review.

**Next steps:** on-water pass with a real buoy + camera to tune the colour gates; train/export the
maritime model so the fallback can switch itself off; still-open UI ideas the reviewer and I both rated
low priority (auto-refreshing DIAGNOSTICS instead of 3 manual poll buttons, folding TRIM/ESC into one
DRIVE settings modal).

## 2026-07-27 — Pi 5 power-off during camera record/replay = computer-USB brown-out

**Worked on:** the on-camera hardware pass flagged last session. User reported the Pi 5 **fully powered
off** twice — once while recording, once while replaying a clip — and asked why.
**Root cause: a 5 V brown-out from underpowering.** The bench Pi 5 was powered from the user's **computer
USB port** (~0.5–0.9 A @ 5 V); a Pi 5 needs 5 A/25 W and pulls 1.5–2.5 A+ under the always-on CV stack +
both USB cameras. `vcgencmd pmic_read_adc` showed `EXT5V` idling at only ~5.0 V *with the software
stopped* (no headroom). Recording adds a **VP8 software encode** (`pi5/cv/recorder.py:337`, `VP80`)
across all cores; replay is a cheap static serve (`pi5/server/app.py:1643`) but the CV pipeline still
runs under it — either tips total draw past the port's limit → PMIC undervoltage cutoff → instant off.
Active Cooler fitted + 49 °C idle → thermal ruled out. No code bug.
**Why the crashes left no logs:** journald was volatile (`/var/log/journal` empty, logs in tmpfs) and
rsyslog absent → wiped on reboot.
**Changed (system state, NOT the repo):**
- Enabled **persistent journald** — drop-in `/etc/systemd/journald.conf.d/99-persistent.conf`
  (`Storage=persistent`; machine-id dir now present) so a future hard-off is captured in
  `journalctl -b -1 -k`.
- Added `~/pi_power_monitor.py` (off-repo) — a black-box logger sampling EXT5V/Vcore/temp/throttle to
  `~/pi_power_monitor.csv` with **fsync per line**, so a brown-out preserves readings to the last second.
**Fix given to user:** power the Pi from a real **5 V/5 A USB-C PSU** (official 27 W); do **not** set
`usb_max_current_enable=1` on a weak supply (removes the USB safety cap → worse brown-outs).
**Decisions / open questions:** on the deployed boat the Pi runs off the **M18 → 5 V UBEC**, which faces
the same CV+record peak — offered to switch the recorder **VP8 → MJPG** (cameras already emit MJPG,
near-zero CPU) or trim record fps/res to widen the power margin. **Awaiting user go-ahead**; no code
touched this session.
**Next steps:** user swaps to the 27 W PSU + re-runs record/replay (optionally under
`~/pi_power_monitor.py` to confirm `EXT5V` stays ~5.1 V flat); then decide on the MJPG recorder change
for the boat's UBEC budget.

<!-- Older entries (right-view box fix + live depth view, stereo vision review + Windows camera fix, live camera assignment, commit/push housekeeping,
     align-first steering, waypoint planner page, M18 battery migration, token-bloat audit,
     third-downloaded-file audit, repomix/rtk, token-optimization config pass) live in
     docs/session_journal_archive.md. -->

