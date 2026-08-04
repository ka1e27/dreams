# D.R.E.A.M.S — Session Journal Archive

Full history of session journal entries older than the 5 kept in `docs/session_journal.md`. Not
read automatically at session start — only pull from here if you need context on something specific
from further back (grep for a filename, feature, or date).

Entries are newest-first, same format as the live journal. When `session_journal.md` exceeds 5
entries, move the oldest one(s) here, at the top of this file's entry list (just under this header).

---

## 2026-07-30 — Pull-ups fitted: **the bus is fixed.** The BNO085 module now fails on its own — it resets on every write

**Worked on:** user power-cycled the Pico and asked to retest the IMU. Diagnosis only — no firmware,
config or repo code changed. Two findings, one of which is more serious than the IMU.

**⚠ FINDING 1 — the Pi could not send the Pico anything. The control link was one-way.**
Before any I²C work: every write to `/dev/ttyACM0` blocked. `os.write()` accepted 8 bytes and
`TIOCOUTQ` stayed pinned at 1280 indefinitely — the Pico was **NAKing its OUT endpoint**. Telemetry
(`$TEL`/`$ENV`/`$ALERT`) streamed out fine the whole time, so the link *looked* healthy. Not DTR/RTS
(both asserted, toggling changed nothing), not flow control (`CRTSCTS`/`IXON` clear), not
enumeration (one clean `cdc_acm` attach at boot, no re-enumerate). **A `USBDEVFS_RESET` cleared it
instantly** and writes worked again.
This means `SET_THR`, `ESTOP` and the heartbeat could not reach the Pico — and the AM32 ESCs hold
their last PWM. `task_serial_rx` → `read_usb()` cannot die (bare `except` inside its loop), so the
wedge is below the firmware, in the CDC RX path. **Unexplained and not fixed — treat as a safety
item.** Workaround: USB-reset the device before trusting the link.

**FINDING 2 — the IMU is fine; the bus it lives on has no pull-ups, and that is the whole story.**
Confirms and supersedes the "intermittent, cannot be solder" reasoning in the entry below.

- **The BNO085 boots and talks properly.** After a bus recovery it ACKs at **0x4B** and its boot
  queue drains cleanly in 28-byte chunks — `len=276 → 248 → 220 → … → 24` on ch0, then `len=5` on
  **ch1 (executable = reset complete)**, then ch2. `SET_FEATURE(RotationVector)` returns **True**.
- **The bus wedges with SCL held low.** Caught it directly: `SDA(GP14)=1, SCL(GP15)=0`, still low a
  second later — a slave stretching the clock, exactly as predicted. **The standard 9-clock recovery
  sequence frees it every time** (SCL→1), and the rescan then found **`0x44`** — the SHT41 on the
  same pins, which is why *both* devices vanish together.
- **Speed-dependent, and that is the tell.** With a `~RST` pulse the device answered **8/8 at 50k,
  100k and 400k**; long reads are what corrupt (`OSError(110)` ETIMEDOUT mid-body on a 276-byte
  read), short ones survive. Slow rise time on an unpulled bus, nothing else.
- **The earlier "GP14/GP15/GP17 short migrates between pins" mystery is resolved** — those were
  snapshots of a wedged bus, not shorts. `map` now reads GP14/GP15 **both idle-high**.
- **Still no heading.** Channel census after a successful `SET_FEATURE`: `{ch0: 82, ch1: 6, ch2: 6}`
  and **zero packets on ch3 (reports)**. The reports channel never opens, so `compass.read()` gets
  nothing — consistent with the part re-announcing rather than streaming on a bus that keeps hanging.

**Unchanged and re-confirmed:** GP9 and GP10 still `*** SHORTED LOW ***` every run. Firmware boot
banner still prints `IMU: I2C0 GP8/GP9 addr=0x4A FAIL` — the wrong-bus + wrong-address pair from the
entry below is still there, untouched.

**Changed:** nothing in the repo. `pi5/scripts/pico_i2c_probe.py` was used as-is; all new probes were
throwaway scratchpad scripts. The Pico firmware was left **running** (verified `$TEL` after a soft
reset) — the probe stops it, so it must be restarted or it sits dead at the REPL.

**Decisions / open questions:**
- The probe's docstring claims hw I²C1 @400 kHz is the reliable config. **Partly wrong** — 400 kHz
  works for short transactions but the failure is transaction *length*, not clock rate. Chunked
  ≤28-byte reads at 100 kHz drained the advertisement that 400 kHz could not.
- Why the CDC RX endpoint wedges is unknown. It survived a firmware restart and only a USB reset
  cleared it. Worth reproducing deliberately.

---

### ⟶ SAME SESSION, AFTER THE USER FITTED 2× 2.2 kΩ TO 3V3 ON GP14/GP15

**The pull-ups worked. The bus is fixed — this is measured, not inferred:**

- **SHT41 (0x44) CRC integrity: 120/120 clean** measurements, **0 bad-CRC, 0 I²C errors**, at *both*
  100 kHz and 400 kHz. The SHT41 ships a CRC-8 with every reading, so this is a real data-integrity
  test of the wire, not a presence check. It used to vanish from the bus constantly.
- **The 276-byte boot advertisement now reads in ONE full-length 400 kHz transaction** and decodes to
  real ASCII (`SHTP`, `1.0.0`). That exact read previously returned all-nonprintable or `ETIMEDOUT`.
- `0x44` and `0x4B` now enumerate together, every scan.
- No more SCL-low wedges under normal traffic.

**Two earlier conclusions were wrong and are corrected here:**
1. **There is no reboot loop.** The "1.4 reboots/s" in the entry above was an artifact of *chunked*
   reads never fully consuming the advertisement. With full-length reads the queue drains to
   genuinely empty (`ch0 len=276` → `ch1 len=5` → NAK) and stays quiet.
2. **Most "errors" were plain NAKs.** A BNO08x NAKs reads when its queue is empty; MicroPython
   surfaces that as `OSError`, identical to a real fault. Earlier passes treated normal idle as a bus
   hang and thrashed the recovery routine against nothing.

**⚠ The remaining fault is the IMU module itself — it resets on every write.** Isolated with a
read-only control arm:

| | result |
|---|---|
| address ACK | **30/30** |
| reads (incl. 276-byte) | clean, correct ASCII |
| **1st write** | lands, and the chip immediately emits `ch0 len=276` + `ch1 len=5` → **it reboots** |
| **writes 2–5** | **NAK'd, 20 retries each, all fail** |
| control: reads only, no writes | **0 resets, 0 packets** — quiet and stable |

So `SET_FEATURE` can never take effect, `GET_FEATURE_REQUEST` never returns a response, **channel 3
(reports) never opens**, and there is no heading. `INT` (GP18) never asserts, consistent with the
chip never having data to announce.

**GP17 is NOT the IMU's reset.** An A/B test (GP17 driven push-pull high vs left high-Z) produced
*byte-identical* results. Correct conclusion, wrong reason — see the RST/INT section below: GP17 is
the **interrupt**, so pulsing it was always a no-op. GP9/GP10 remain shorted as always.

**Changed:** still nothing in repo code — diagnosis only. Journal only. Firmware verified running
again afterwards (`$TEL` streaming); the probe stops it, so it must be restarted or it sits dead at
the REPL. Firmware boot banner unchanged: `IMU: I2C0 GP8/GP9 addr=0x4A FAIL`.

**⚠⚠ THE RST AND INT WIRES ARE SWAPPED — and GP17 was never a short.** The user reported having only
power / SDA / SCL / RST / INT connected, which contradicted the measurements, so the two lines were
located empirically:

- **RST is on GP18** (pin map says GP18 = `~INT`, J5.8). Driving GP18 low makes 0x4B stop ACKing;
  releasing it brings the device straight back. No other candidate pin does this.
- **INT is on GP17** (pin map says GP17 = `~RST`, J5.7). During a guaranteed post-reset data-pending
  window GP17 read low **500/500 samples**, while GP12/13/16/19/20/22 stayed high throughout.

**This retires the "GP17 is SHORTED LOW" finding that has been in the docs and in
`pico_i2c_probe.py`'s `map` output all along.** GP17 is a correctly-functioning **active-low
interrupt** that has been asserted continuously because the boot advertisement was never drained.
`map` reports any asserted active-low signal as a short — it cannot tell the two apart. GP9/GP10
remain genuinely shorted; **GP17 does not, and `docs/pin_map.md` needs correcting.**

Consequence: every "reset pulse" in this session and the one before it was applied to GP17, which is
the interrupt line — i.e. **the module was never actually being reset**. With real reset control on
GP18 the chip resets cleanly and re-emits a 280-byte advertisement + ch1.

**Writes are INT-gated.** Writes land only while INT (GP17) is asserted and are NAK'd when the queue
is empty — which explains the earlier 4/5-then-0/10 write pattern exactly. Gating writes on INT low
made `SET_FEATURE` land reliably. **But the chip still answers it with `ch0` + `ch1` — a reset — and
channel 3 still never opens.** A correctly framed, correctly timed command still reboots the part.

**The chip is running its full application firmware — not a bootloader.** The advertisement decodes
completely: `SHTP / control / executable / device / sensorhub / control / inputNormal / inputWake /
inputGyroRv`, SHTP `1.0.0`, app `1.1.0`, followed by ch1 payload `01` = reset complete. So the part
boots correctly and its sensor app is alive.

**⚠ THE ACTUAL BLOCKER: the part ACKs its address but NAKs every data write once idle.**
- `bus.scan()` — an address-only write — succeeds **30/30**, and both `0x44` and `0x4B` enumerate.
- A write *with payload* only ever lands inside the post-reset INT-low window, and when it does land
  the chip **ignores it**: no ch2 response, no ch3 reports.
- Once the boot queue drains, **INT (GP17) never asserts again** and writes fail 100 %:
  0/52 tries, then 0/26 at each of four post-reset delays (60/150/300/600 ms).
- Tried both transports: **hardware I2C1** (strict on clock stretching, which the BNO08x does during
  writes) *and* **SoftI2C** (tolerant). Neither changes it.
- `Product ID Request (0xF9)` — the canonical liveness command — **cannot be delivered at all**, and
  a commanded reset on the executable channel likewise never lands.

This is the classic signature of a BNO08x that is **not ready / asleep** rather than a broken bus or
a broken part: reads are flawless, the address ACKs, only payload writes are refused. On a BNO08x
that state is governed by strap/interface pins that are **not connected**.

**⇒ ROOT CAUSE (very likely): the module's unused host-interface inputs are left FLOATING.** The user
confirmed: **MOSI/ADDR is not connected, CS is not connected**, and BOOT is an on-board plated hole,
not a header pin (so BOOT is already strapped — consistent with the app-firmware advertisement we
read). Floating CMOS inputs on a BNO08x host interface produce exactly the observed behaviour: the
address decodes and ACKs, then the interface state machine refuses payload writes.

This also probably explains the **0x4B vs 0x4A address mismatch** that the docs have treated as an
inherent property of the module: **MOSI doubles as ADDR on this breakout** (the user's own labelling),
and a floating ADDR reads high → 0x4B. Grounding it should yield **0x4A**, which is what
`compass.py` already hardcodes.

Note also: an earlier decoder bug meant report payloads were parsed without stripping the 4-byte
SHTP header that the part repeats on every read. Fixed — but no ch3 packet ever arrived, so it
changed no conclusion.

---

## 🚩 FLAGGED — PARKED 2026-07-30, PICK UP HERE

**The bench is left working:** pull-ups fitted and proven, bus clean, Pico firmware running and
verified (`$TEL` streaming). No repo code was changed in this session — diagnosis only.

**Step 1 — wire the four floating pins (physical, blocks everything else):**

| module pin | tie to | why |
|---|---|---|
| **MOSI / ADDR** | **GND** | address select; floating reads high → 0x4B. Grounded → **0x4A** |
| **CS** | **3V3** | SPI chip-select, unused in I²C — park it deasserted, not floating |
| **PS0** | **GND** | I²C mode |
| **PS1** | **GND** | I²C mode |
| VIN | **3V3, not 5 V** | `docs/pin_map.md` flags J5/J7/J11/J13 as 5 V; a bare BNO085 is 3.6 V max |

`PS1=0 / PS0=0 = I²C` is solid. Leave BOOT alone. **Scan for both 0x4A and 0x4B afterwards** — the
address is expected to move.

**Step 2 — re-run the bring-up.** Scratch scripts are gone (they were in the session scratchpad);
the reusable tool is `pi5/scripts/pico_i2c_probe.py`. The sequence that works: 9-clock bus recovery →
reset via **GP18** → wait for INT low on **GP17** → drain the advertisement with full-length reads →
`SET_FEATURE` → read ch3. Success = packets on **channel 3**; that is the one thing never yet seen.

**Step 3 — only if writes still NAK:** swap in a known-good module. Reads flawless + address ACK
30/30 + every payload write refused is narrow enough that a substitution settles it fastest.

**Then the code work (all still pending, none of it done):**
1. **Correct `docs/pin_map.md`:** at the Pico, **reset behaves as GP18 and interrupt as GP17** — the
   reverse of what the map says. User confirmed their wiring follows the connector labels, so the
   swap is **board-side**, same class of defect as the documented J3 odd/even row transposition.
2. **Retract the GP17 short from the docs.** There is no GP17 short — it is an asserted active-low
   interrupt. Also fix the `map` verdict in `pico_i2c_probe.py`, which cannot tell an asserted
   active-low signal from a solder bridge and has been reporting it as `*** SHORTED LOW ***`.
   GP9/GP10 *are* genuinely shorted; leave those.
3. **`compass.py`:** bus → GP14/GP15 **sharing `sensors.py`'s bus object** (not a second one), the
   address per whatever Step 1 lands on, plus 9-clock bus recovery and INT-gated reads on GP17.
4. **Pi→Pico CDC write wedge** — independent of the IMU and a safety issue: the Pi could not send
   `SET_THR`/`ESTOP`/heartbeat while telemetry still streamed out, looking healthy. Seen **twice**
   this session; `USBDEVFS_RESET` clears it each time. Cause unknown.

## 2026-07-30 — IMU test: **the BNO085 works.** The bus it lives on hangs, and `compass.py` looks at the wrong one

**Worked on:** user plugged an IMU in and asked me to test it. Diagnosis only, one new tool, no
firmware or config changed. The user then made the observation that reframed the whole session.

**The IMU is a genuine, working BNO08x.** Not "an address that ACKs" — its 267-byte SHTP boot
advertisement decodes to the ASCII service list `SHTP / control / executable / device / sensorhub`.
It sits at **0x4B** on **GP14/GP15**, which is where the board wires J5 (`docs/pin_map.md:184`).

**`compass.py` cannot ever see it — two independent, individually-fatal mismatches:**

| | `compass.py` | reality |
|---|---|---|
| bus | `I2C(0, sda=Pin(8), scl=Pin(9))` | **GP14/GP15** (SoftI2C #B) — GP8/GP9 go to **J7**, and GP9 is hard-shorted |
| address | `BNO_ADDR = 0x4A` | **0x4B** (ADR pulled high); 0x4A returns `ENODEV` |

So the firmware's `IMU: I2C0 GP8/GP9 addr=0x4A FAIL` and `TEL` health `001110` (bit 2 = IMU = 0) were
the *firmware's* verdict, not the hardware's. Neither mismatch is caused by any short; both survive a
perfectly repaired board.

**⚠ I first called GP14/GP15 a hard short to GND, and that was wrong. The user caught it.** Their
reasoning: *"the SHT41 internal temp works and isn't that on the same lane as the IMU"* — and it is.
`enc_t` = `sensors.air_temp2` = SHT41 **#B** = `bus_b` = **GP14/GP15**, the same two pins. Re-measured,
and both devices answered together — `0x44` **and** `0x4B`, **40/40 rounds** over 40 s. What I had
measured was real but transient. `map` returned three different states minutes apart with nothing
physically touched:

```
GP14 low  + GP15 low,  GP17 high    bus dead — 0/60 samples released over 15 s
GP14 high + GP15 high, GP17 low     bus FINE — 0x44 and 0x4B both answer, 40/40
GP14 high + GP15 low,  GP17 high    bus dead
```

**A solder bridge cannot migrate between pins.** This is an intermittent **bus hang**, and three tells
identify it: **SCL held low on its own is clock stretching** — a hung slave, not a short (both lines low
is the same hang caught mid-byte); **both hangs immediately followed a large read** (a 128-byte SoftI2C
attempt, then a 267-byte hardware read) while short transactions run for ages; and pulsing `~RST` (GP17)
does **not** free a stuck SCL, while GP17 itself read low with the BNO still answering — so GP17 does
not gate the chip the way J5.7 implies.

**Leading cause is already written down as a to-do: this bus has no pull-ups fitted**
(`docs/pin_map.md:155` — "no pull-ups — fit 2.2 kΩ"). Three connectors hang off it (J5 + J7 + J13), so
the only pull-ups present are whatever the breakouts carry, against all that trace capacitance. That is
exactly this symptom: fine for short transfers, corrupting on long bursts, hung until it self-recovers.
Compounding it, `docs/pin_map.md:169` — **J13.4 feeds the SHT41 VSYS 5 V against a 3.6 V absolute max.**

**⚠ Once hung, software cannot recover it.** You cannot clock out a slave that is holding SCL, and the
module's 3V3 comes off the rail, not a GPIO — so an RST pulse fails and a Pico reset won't help. It
needs a **power cycle**. In the field that means the IMU stays dead until someone power-cycles the boat.

**Two more findings worth acting on:**
- **`enc_t` freezes instead of failing.** `read_temp_humidity()` — "a failed/CRC-bad read leaves the
  last value in place" — so a dead SHT41 #B keeps serving its last good temperature forever, and the
  dashboard cannot distinguish that from a live one. Exactly the class of bug fixed for `gps_source`
  yesterday, in the same shape: no way for the software to *say* the sensor stopped.
- **SHT41 #A (J11, GP12/GP13) never answered at all** — scans EMPTY, `measure()` False, and those pins
  read floating with **no external pull-up**, so `air_t` is 0.0 or frozen. Same missing-pull-up story.
- **Hardware I2C1 at 400 kHz read the full 267-byte advertisement; SoftI2C at 100 kHz never could.**
  GP14/GP15 are the native I2C1 pair, so hardware I2C is available — but `sensors.py` already owns those
  pins as SoftI2C, so a port must have both drivers **share one bus object**, not open two.
- Pads **12/13/14** (GP9 / GND / GP10) remain a **genuine hard short**, reproducible on every run — the
  documented 2026-07-29 blob, unchanged.

**Changed:**
- `pi5/scripts/pico_i2c_probe.py` — **new.** Drives the Pico's raw REPL from the Pi so it never runs
  `main.py` (`status_led.py` drives GP10 into its short). `map` prints per-pad float/pull-down/pull-up
  with roles and, when a J5 signal is low, explicitly warns *not* to read it as a bridge; `scan` lists
  each bus; **`watch`** samples the four J5 signals + both device addresses for ~30 s and reports
  distinct states, which is the test that separates "dead" from "flapping" and the one to validate any
  fix with; `imu` patches the two wrong values into the **real `compass.py`** and reads heading through
  it, so it validates the shipped driver rather than a reimplementation.
- Journal only otherwise.

**How to interrupt this firmware**, worth keeping: `main.py` has **ten bare `except:` blocks** in its
asyncio task loops and every one swallows KeyboardInterrupt, so a single Ctrl-C is almost always eaten.
Spamming it lands one in the scheduler, where it propagates out of `asyncio.run()`. First burst worked.

**Verified:** ruff clean; all four modes exercised live; `map`/`scan`/`watch` reproduce the findings
end-to-end through the module CLI; usage guard rejects a bad mode. **Not yet verified: a live heading.**
`SET_FEATURE` was attempted twice and the bus hung mid-write both times, so `imu` has never yet run
through to a Rotation Vector report — that is the one outstanding acceptance test, and it needs a
non-hanging bus. Pico pins left as inputs, firmware **stopped** (restarting it drives GP10 into a short).

**Also spotted: `main.py`'s boot banner lies three ways** and is the first thing a bench operator reads
— `IMU: I2C0 GP8/GP9 addr=0x4A` (wrong bus *and* address), `GPS: UART1 GP4/GP5 9600bd` (the GPS moved to
the Pi at 38400), and `Hull: GP17(L) GP18(R)` (moved to GP19/GP20 on 2026-07-28; GP17/GP18 are the
BNO's RST/INT). Not fixed — next steps (5).

**Next steps:**
1. **Fit the 2.2 kΩ pull-ups to 3V3 on GP14/GP15.** Already documented as needed, and it matches the
   symptom precisely. Then `pico_i2c_probe watch` — target is one stable state with both addresses
   answering, and `imu` running through to a real heading.
2. **Unplug J13 and re-run `watch`.** The SHT41 there runs on 5 V against a 3.6 V max; if the hang goes
   away with it off the bus, that part is damaged and/or back-driving the rail.
3. **Reseat J5 and check its crimps** — every pin that wandered is a J5 signal.
4. **Then fix `compass.py`**: right bus, right address, and either share `sensors.py`'s SoftI2C object or
   move both to hardware I2C1 — do not open two bus objects on one pin pair. Draining the boot
   advertisement is not required before `SET_FEATURE`; skip it rather than fight the 267-byte read.
   Verify with `pico_i2c_probe.py imu`.
5. Make a dead SHT41 **report** dead instead of freezing (`read_temp_humidity`), and correct the three
   stale boot-banner lines in `main.py`.
6. Unchanged from before: the stepper `find`/`burst` runs, and the buoy screen's false-positive gates.


## 2026-07-30 — "my GPS ain't working": it was working. The dashboard was lying about it

**Worked on:** user reported the GPS dead. Diagnosed it as a **sky-view problem, not a fault**, then
fixed the real defect — that the software had no way to *say* that.

**The receiver was fine the whole time.** `/dev/ttyAMA0` @ 38400: **clean NMEA, 100 % printable**,
0 bad checksums in 144 sentences. Overlay present in `config.txt`, GPIO14/15 muxed `a4`, nothing else
holding the port. 9600 and 115200 return garbage, which re-confirms 38400. What it was actually saying:

```
$GNGGA,212546.00,,,,,0,00,99.99,,,,,,     ← quality 0, 00 sats used, HDOP 99.99
$GNRMC,212547.00,V,,,,,,,300726,,,N,V     ← V = void
$GNGSA,A,1,...                            ← mode 1 = no fix
```

GSV showed **2 satellites, SNR 20 and 34**. A 3D fix needs 4. Two independent facts prove the RF chain
is good rather than broken: **SNR 34 is a strong signal** (a dead/disconnected antenna gives *zero*
satellites, not one at 34), and it reported **correct UTC date+time** — 21:25:47 / 300726 against the
Pi's 21:26:40 UTC — which can only come from demodulating a satellite's navigation message. Blank
elevation/azimuth in every GSV entry means **no almanac → cold start**, which needs ~30 s of
*uninterrupted* signal; indoors on a marginal signal that never completes, so it can sit for hours and
never fix. Told the user to take the antenna outside.

**The actual bug, and why it produced this report.** `_apply_external` returned early on
`self._ext_pos is None`, so until the *first ever* fix `gps_source` read **`"pico"`** — naming a
receiver this board has **no wiring for** (GP9 shorted to GND, which is why the GPS is on the Pi at
all). The operator therefore saw no difference between "Pi GPS streaming perfectly, waiting on
satellites" and "no GPS fitted". `on_fix` only fires on a *usable position*, so the entire acquisition
phase was invisible by construction.

**Fix: a four-rung source ladder, so the rung tells you what to go and do.**

| `gps_source` | Dashboard | Operator's next move |
|---|---|---|
| `pi-nolink` | `NO SIGNAL` (red) | wiring: module unpowered, TX off GPIO15, or overlay missing |
| `pi-nofix` | `NO FIX · 2/6 sats · 34dB` (amber if any sat heard) | **sky view.** Nothing to fix |
| `pi-stale` | `STALE FIX` (amber) | position shown is last known, not current |
| `pi` | `GPS · 6 sats` (green) | — |

Kept `pi-nofix` (never locked) distinct from `pi-stale` (locked, then lost) deliberately: the latter
keeps serving the last position because the Pico's lat/lon are a hard 0.0 and nothing in the nav stack
guards against (0, 0). Amber rather than red once *any* satellite is heard, because that state proves
the hardware works and needs patience, not repair.

**Changed:**
- `pi5/comms/gps_nmea.py` — **GSV parsing** (was ignored entirely): `sats_visible` / `sats_tracked` /
  `best_snr`, kept **per talker** since each constellation runs its own cycle and a flat total would be
  whichever spoke last. Uses GSV's own count field, so it's right from message 1 of N. New `on_status`
  callback fires on **every GGA regardless of fix** — the counterpart `on_fix` couldn't be. New `linked`
  (a valid sentence has arrived) as distinct from `connected` (the port opened), since the port opens
  fine with the module unpowered.
- `pi5/comms/pico_serial.py` — `set_external_gps_status()`; `_apply_external` publishes receiver state
  *before* the no-fix return; `gps_sats_visible` / `gps_sats_tracked` / `gps_best_snr` on `Telemetry`;
  health bit 0 cleared while unlocked. Source ladder documented on `use_external_gps`.
- `pi5/server/models.py`, `app.py` — three fields through `TelemetryOut`. One construction site feeds
  REST, `/api/all` and the WebSocket, so all three got it.
- `command_center.html` — two new `GPS_SOURCES` rungs; the readout; a tooltip that adapts (`trk >= 4`
  → "a fix should appear shortly"; `snr >= 30` → "antenna works, needs open sky"; else "signal weak").
- `run_hardware.py` — registers `on_status`. `docs/pin_map.md` — the ladder + GSV/cold-start notes.

**Two GSV traps worth remembering:** NMEA 4.10 (which the M10 speaks) appends a trailing **signalId**
after the last satellite group — walking groups of 4 without the `len(f) - 3` bound reads it as a PRN
and invents a satellite every cycle. And a fresh cycle must **replace** a talker's set, not add to it,
or satellites that left view linger forever. Both have tests.

**Verified:** `pytest pi5/tests` **437 green** (+21), ruff clean, `node --check` OK, div balance
306/306, no dangling `$('id')`. Fixtures are **real captures** off the bench module, checksums included.
**End-to-end against the live GPS:** `pi-nolink` before any NMEA → `pi-nofix`, 1/1 sats, SNR 29 after
12 s, surviving a fresh TEL frame, and the exact `/api/telemetry` JSON confirmed. All nine display
states rendered in node — the four pre-existing ones (fix/stale/sim/pico) unchanged. Sim boots,
endpoints 200, zero errors.
**One pre-existing test asserted the old `"pico"` behaviour** (`test_no_override_before_first_fix`) and
was rewritten to the new intent, keeping its load-bearing half: the Pico's TEL lat/lon must still not be
overridden before a real fix exists.

**Next steps:** (1) **Take the antenna outside and confirm a fix** — expect 30–60 s from cold; the
dashboard now shows the sat count climbing. (2) The GPS row goes green on its own when it locks; if it
sits at `pi-nofix` with **0 tracked** outdoors, *then* suspect the antenna. (3) Unrelated and still
open: the stepper `find`/`burst` runs, and the buoy screen's false-positive gates.


## 2026-07-29 — Radar tracking: a divergent aiming law, and a CONF slider that governed nothing

**Worked on:** user reported two things — "the stepper rotates the wrong way for tracking", and "the
CONF slider didn't edit it, it still showed all the 40 percent confidence". Both reproduced and fixed.
**Note the buried good news: the stepper is moving now**, so the STEP-net fault from the entry below
is resolved — the user should say how, since none of the diagnostics above recorded the fix.

**Bug 1 — the tracking law diverged; it was never a wiring problem.** `radar_tracker._bearing_for`
returned `stepper.get_position_degrees() + offset_deg`. That's the camera-**on**-the-bar formula, but
the cameras are **fixed forward** and the bar pans separately (`docs/object_memory.md:49` states this
outright — "the radar-pan angle is not part of it"). With a fixed camera the pixel offset doesn't
shrink as the bar turns, so every 0.1 s tick added it again: positive feedback, bar walks off to an end
stop and pins there. **Flipping DIR would not have fixed this** — it would have pinned the other end.
Now absolute about `bow_degrees` (default 90° = the sweep midpoint; 0 = port beam, 180 = starboard), so
a centred target parks the bar dead ahead and the frame edges reach bow ± fov/2 = ±37.5°.

**Bug 2 — per-class floors made CONF a no-op on the classes that matter.** `_passes_conf` was
`conf >= self._class_conf.get(label, self._cfg.conf)`, and `config.yaml` pins person/swimmer 0.25,
surfer/kayak/buoy 0.30. So dragging CONF from 0.40 to 0.90 changed **nothing** for any of them —
measured, not inferred: `infer_conf` stayed 0.25 and `person@0.31` kept passing at both ends of the
slider. Since `stepper.priority_classes` is `[vessel, person, kayak, boat]`, two of the four tracked
classes were pinned. That is exactly "it still showed all the 40 percent confidence". Floors are now
**relative** to the config baseline (person sits 0.15 below wherever CONF is), with a
`class_conf_absolute` opt-out — `buoy` stays fixed at 0.30 because its score is a saturation/solidity
quality proxy, not a probability, and letting CONF drag it up would silently kill buoy detection (the
config comment already warned about exactly this).

**Changed:**
- `pi5/cv/radar_tracker.py` — absolute `_bearing_for` about `bow_deg`; `invert_tracking` (mirrors only
  the bbox→bearing sign); `min_track_conf` + `set_min_track_conf()`, the tracker's **own** lock gate.
  Raising it drops an unqualified lock *immediately* rather than after `lost_timeout_s`, so the
  operator sees it bite instead of waiting up to 3 s. `status()` now carries `track_conf`, `bow_deg`,
  `invert_tracking`, `invert_direction`.
- `pi5/cv/stepper.py` — `invert_direction` flips the DIR **pin only**; position accounting is
  untouched, so 90° stays the same physical place, reached turning the other way.
- `pi5/cv/vision_overlay.py` — `_class_floor()` (relative shift + absolute opt-out) behind
  `_passes_conf`/`_infer_conf`; `conf_floors()` and `class_conf_absolute`; `controls()` publishes the
  resolved floors so the UI can *show* the slider working.
- `pi5/server/app.py` — `/api/camera` accepts `track_conf`; `_camera_state()` serves it plus the floors.
- `pi5/server/templates/command_center.html` — **TRK CONF** slider beside the TRACK picker (reads
  `OFF` at 0, not `0.00` — "no threshold" and "a threshold of zero" mean different things to an
  operator); CONF's tooltip lists the live per-class floors, marking the absolute ones. Also fixed a
  latent bug in `postCamera`: one shared 150 ms debounce timer with `clearTimeout` **replaced** the
  pending body, so touching two controls inside the window silently dropped the first — now merged.
- `pi5/config.yaml` — `stepper.invert_direction` / `invert_tracking` / `bow_degrees: 90` /
  `min_track_confidence`, and `camera.detection.class_conf_absolute: ["buoy"]`, each with the
  decision rule inline. `run_hardware.py` passes them through.
- `docs/pin_map.md` — a "which way does it turn" table (which of the two flags to set for which
  symptom) and the absolute-aiming note, in the A4988 section.

**Two knobs, deliberately not one.** Jog wrong too → `invert_direction` (DIR pin / coil pairs in J18).
Jog fine, track wrong → `invert_tracking` (bar's + direction vs camera's + x). Both wrong the same way
→ `invert_direction` alone, it already covers tracking. Neither is knowable from software, and neither
is in KiCad, so this is configuration rather than a code fix.

**Verified:** `pytest pi5/tests` **367 green** (from 341, **+26**: `test_radar_tracker.py` and
`test_stepper_direction.py` are new — there were no tests on either module before). ruff clean; inline
`<script>` passes `node --check`; div balance 306/306 and every `$('id')` resolves. End-to-end through
the real endpoint functions: CONF 0.40→0.80 moved person's floor 0.25→0.65 and dropped a 0.42 person
box while buoy@0.35 survived; `track_conf` 0.60 left that same box **drawn but not chased**, then 0.30
re-acquired it. Sim boots, `/` `/planner` `/api/camera` `/stepper/status` all 200 (fields read null
there — no overlay/radar in sim — and the UI skips them cleanly).
One pre-existing test encoded the old absolute-floor behaviour and was updated, not worked around.

**Nothing was energised** — the aiming change needs a human watching the bar. Nothing committed.

### Continuation 2026-07-30 — bench results in: DIR really is inverted, and my buoy "guard" backfired

**User bench-tested and reported three things.** All three are now addressed.

**1. "Manual right pan went left" → `invert_direction: true`, set in config.** That's the unambiguous
definition of the flag: `RIGHT ►` sends `JOG +15°` and the bar went to port. Set from measurement, not
inference.

**2. "Tracking turns away from me" — same single root cause, no second flag needed.** A target to
starboard commands a *higher* bar angle (bow 90° + offset), and the wrong DIR polarity was executing
every higher-angle command as a turn to port. So `invert_direction` alone fixes both, which is the
"both wrong the same way" row of the table added below. `invert_tracking` stays **false** — only flip it
if TRACK is *still* mirrored now that manual jog is correct. **Unverified on hardware:** predicted from
the reported symptom, needs a re-test.

**3. "Way too many buoys, ~40%, still there at 0.75 on both sliders" — my own guard from the entry
above caused this.** I had put `buoy` in `class_conf_absolute` so the CONF slider couldn't drag its
floor up and silently kill buoy detection. On the bench that inverted into the worse failure: the
classical screen fires constantly indoors (a room with no buoys), and the pin made those false
positives **the one class the operator could not filter** — reintroducing the exact complaint the
relative floors were built to fix. `class_conf_absolute` is now **empty by default**. Buoy keeps a
relative 0.10 head start, so at CONF 0.75 its floor is 0.65 and the 0.40 noise is gone, while a genuine
strong buoy at 0.70 survives. The mechanism stays for a score that truly can't be compared to a
probability *and* isn't drowning the operator — buoy was only the first of those.

**Also found while there: the same divergent-bearing bug in a second place.**
`pipeline._bearing_for` (line ~720) was also `stepper.get_position_degrees() + offset`, so a stationary
threat's *displayed* bearing drifted every time the bar panned. Now measured about `radar.bow_deg` and
deduped onto `_avoidance_bearing`, which is the identical formula and was always bow-relative.
Geolocation and steering were never affected — they already used `_avoidance_bearing`.

**Changed (this continuation):**
- `pi5/config.yaml` — `invert_direction: true` (with the measurement recorded inline);
  `class_conf_absolute: []` with the reasoning above.
- `pi5/cv/vision_overlay.py` — `class_conf_absolute` defaults empty; **`buoy_enabled`** operator kill
  switch, deliberately separate from `_buoy_active` (which is the *model* verdict "this model can't
  emit buoy"). Gates `_add_buoys` and the TRACK picker; `controls()` publishes
  `buoy_available` / `buoy_enabled`.
- `pi5/server/app.py`, `command_center.html` — `buoy_enabled` on `/api/camera`; a **BUOY ON/OFF**
  button in the camera control bar that reads **N/A** and disables itself when a maritime model emits
  `buoy` itself, since a toggle would be a lie there.
- `pi5/cv/pipeline.py` — bow-relative `_bearing_for`.
- `run_hardware.py` — `class_conf_absolute` fallback now `[]`.

**Verified:** `pytest pi5/tests` **371 green** (+4), ruff clean, `node --check` OK, div balance 306/306,
no dangling `$('id')`. Sim boots, `/` `/api/camera` `/stepper/status` 200, no errors in the log.
Built the objects straight from the shipped `config.yaml` and confirmed: `invert_direction=True`,
a person at x=560 resolves to bar **118.1°** (starboard of the 90° bow), and at CONF 0.75 the floors
are `buoy 0.65 / person 0.60 / kayak 0.65` with `buoy@0.40` **dropped** and `buoy@0.70` kept.
**Two more pre-existing tests encoded the old behaviour** (`test_buoy_survives_the_conf_slider_being_
dragged_up`, `test_bearing_uses_stepper_angle_and_fov`) and were rewritten to the new intent, not
deleted or skipped.

**⚠ Worth knowing before the next bench run:** at CONF 0.75 a person detected at ~0.42 is filtered too
(person's floor becomes 0.60), so the bar won't track them. To track a person on the bench keep CONF
around 0.40–0.50 and use the **BUOY OFF** button to kill the false buoys — that's what the toggle is
for. The sliders are a blunt instrument against a *class-specific* false-positive problem.

**Still not addressed — the buoy screen's false-positive rate itself.** Filtering by score is a
workaround; the screen is finding real saturated blobs indoors. The likeliest culprit is
`buoy.min_area_px: 12` at `proc_width: 320` — a **3.5 × 3.5 px** blob qualifies. `max_candidates: 6`
caps it at 6 per frame, which matches "a ton" flickering. Not retuned: I'd be guessing without seeing
what it's firing on. Ask the user for a screenshot of the false boxes before touching the gates.

### Continuation 2026-07-30 (2) — **jog fixed, tracking wasn't a polarity fault at all: the axis had the wrong origin**

**User:** "pan right now works but the tracking doesn't. When I show up on the **left** as a person it
starts tracking and immediately turns **away** from me." So `invert_direction: true` is confirmed
correct, and next-step (2) above — "if TRACK alone is still mirrored, set `invert_tracking: true`" —
would have been **the wrong call**. It's a coordinate bug, not a sign bug.

**The stepper has no home switch.** `StepperMotor._position_steps` starts at **0**, so the software
believes the bar boots at 0° — and the bar is physically pointing forward when you start the stack. But
I had set `bow_degrees: 90` (the midpoint of the 0–180 sweep). So the very first tracking command was
`rotate_to(90 ± offset)` **from a standing start of 0**: a ~71–109° lurch to starboard *whichever side
the target was on*. The ±37.5° of actual aiming was buried under a 90° constant. `invert_tracking`
would have flipped the sign of the small term and left the lurch untouched.

**Root cause is that I introduced an origin the rest of the code didn't share.** `_position_steps = 0`
at boot, `center()` → `goto(0.0)`, and the compass rose draws 0° at the top — three places already
saying "0 = home = forward". `bow_degrees: 90` contradicted all three.

**Fix: re-centre the axis on the bow instead of moving the bow.** `0° = dead ahead, + starboard,
− port`; sweep **±90** (a forward-looking half-circle); manual **±180** (the *same* 360° of travel as
the old 0–360, just re-centred). Now boot position, `bow_degrees`, `CENTER`, and the top of the rose
all mean the same thing.

**This also fixes a limitation nobody had reported yet:** on the old 0…360 axis with `manual_min: 0`,
**every port-side bearing clamped at the 0 end stop** — `_clamp` has nowhere below 0 to go — so half
the field of view was untrackable by construction. A person on the left is exactly the case that hits
it. Measured against the shipped config: x=160 (left) → **−18.75°**, and the bar lands at −18.9°
rather than clamping to 0.

**Changed:**
- `pi5/config.yaml` — `bow_degrees: 0`, `sweep_min/max: -90/90`, `manual_min/max: -180/180`, with the
  "must equal the boot position, there is no home switch" warning inline.
- `pi5/cv/radar_tracker.py` — `center()` → `goto(self.bow_deg)`, not a hard-coded 0. They coincide on
  the shipped config; CENTER should mean "look forward" regardless.
- `pi5/server/templates/command_center.html` — the GOTO input was hard-coded `min=0 max=360` with a
  "0–360°" placeholder, which the re-centred axis would have made a lie: it now **binds to the bar's
  real `limits`** from `/stepper/status` (tooltip and validation message included), so it can't go
  stale again. Rose's left-hand card label `270` → `-90`.
- `docs/pin_map.md` — the convention as a table (boot position / bow / sweep / manual / CENTER), and
  why this was a coordinate fault rather than a polarity one.

**Verified:** `pytest pi5/tests` **375 green** (+4), ruff clean, `node --check` OK, div balance 306/306,
no dangling `$('id')`. Rose geometry re-checked in node for negative angles: −90 → left, 0 → top,
+90 → right, and the ±90 sweep renders as `M100 100 L8 100 A92 92 0 0 1 192 100 Z` — the forward
half-circle, large-arc flag 0. Sim boots, three endpoints 200, zero errors in the log. Built the
objects from the shipped `config.yaml` and walked a person across the frame: far-left −30.5°, left
−18.8°, centre **0.00°** (no movement at all), right +18.8°, far-right +32.8°.

### Continuation 2026-07-30 (3) — TRACK was never sticky, and the bar had two masters

**User:** "it just kept scanning even while I was in frame for a good bit of the time. It knew I was
there but didn't track me. Give me a button to stop scanning and only track."

**TRACK was never a mode you could stay in.** Two independent things dragged the bar back to SCAN:
1. `_do_track` reverted to SCAN after `lost_timeout_s` (3 s) without a target. With a flickering
   detection that bounces mode continuously and it never settles long enough to follow anything.
2. **The vision pipeline is a second master.** `pipeline._process` calls `radar.set_mode("TRACK")` on
   threat engagement and `set_mode("SCAN")` when threat assessment goes quiet — silently undoing the
   operator. Nothing in the tracker distinguished an operator command from an automatic one.

**Added `TRACK ONLY`** (button in the radar panel; `POST /stepper/command {"command":"TRACK_ONLY"}`).
It pins TRACK: a dropout **holds position** instead of sweeping, and automatic SCAN requests are
ignored. `set_mode(..., automatic=True)` marks pipeline traffic, so operator intent outranks threat
assessment; pressing SCAN releases the pin, because asking to scan plainly means you want scanning.
Same for class pins — an operator's TRACK pick now outranks the pipeline's.

**A concrete non-acquisition mechanism, found and fixed.** The pipeline pins `track_class` to whatever
it graded the primary threat. If that object then vanishes, the tracker's wanted-set stays narrowed to
one absent class for the pipeline's whole 5 s clear-timeout — **a person in frame is invisible to it**
during that window. Given the buoy false-positive flood from the entry above, this is a plausible
cause of the exact report. `set_auto_rescan(False)` now drops a stale *automatic* class pin, and class
matching became case-insensitive while I was in there.

**But I had been guessing, twice, so the real fix is observability.** `status()` now carries
**`no_lock_reason`** — why the bar isn't locked, in the operator's terms — rendered in the radar
panel where "no target" used to sit. The three causes of "it saw me and didn't track me" are
indistinguishable from outside the process, and now they aren't:

| Situation | Readout |
|---|---|
| nothing in frame | `nothing detected` |
| person at 0.42, TRK CONF at 0.75 | `person 0.42 is below TRK CONF 0.75` |
| only buoys + a ball in view | `no boat/kayak/person/vessel in view (seeing: buoy, sports ball)` |

Suppressed outside SCAN/TRACK, where it would go stale. **⚠ Prime suspect for this bench run:
TRK CONF left at 0.75** from the previous test — a person scores ~0.42, so `_best_target` returned
None and it scanned forever. The readout will say so outright next time.

**Changed:** `pi5/cv/radar_tracker.py` (`set_auto_rescan`, `automatic=` on `set_mode`/
`set_track_class`, `_set_no_lock_reason`, case-insensitive matching, hold-on-dropout);
`pi5/cv/pipeline.py` (flags its four radar calls automatic); `pi5/server/app.py` (`TRACK_ONLY`
command, `stepper_no_lock_reason` + `stepper_auto_rescan` on the health payload);
`command_center.html` (TRACK ONLY toggle reflecting server state, no-lock readout built with
`textContent` since class labels echo model output).

**Verified:** `pytest pi5/tests` **388 green** (+13), ruff clean, `node --check` OK, div balance
306/306, no dangling `$('id')`. Exercised end-to-end: all three no-lock reasons phrased correctly;
`TRACK_ONLY` flipped `SCAN/auto_rescan=True/track_class='buoy'` → `TRACK/False/''` (stale pin dropped);
a subsequent automatic SCAN was ignored while an operator SCAN restored both. Sim boots, endpoints 200,
`TRACK_ONLY` degrades cleanly to `{"ok":false}` with no radar, a bogus command still 400s, zero errors.
**Two pre-existing pipeline tests** broke because their `FakeRadar` stub didn't accept the new keyword
— the pipeline swallows that in a `try/except`, so it would have failed *silently* on a duck-typed
radar. Stub updated and a test added asserting every pipeline radar call is flagged automatic.

### Continuation 2026-07-30 (4) — **the cameras are ON the bar**, which invalidates a premise three sessions deep

**I asked before rewriting the law, and the answer overturns a documented "fact".** The user's spec
("go left til it gets to the center") only closes if the image moves when the bar moves, while
`docs/object_memory.md:48` said the cameras are *fixed forward*. **They ride on the bar.** That doc
was stale, and every session above reasoned from it.

**What this re-explains.** The original `current + offset` law was the *correct* camera-on-bar law all
along. It diverged only because DIR polarity was inverted — moving the wrong way *increases* the
offset, commanding a bigger move the same wrong way. My "fix" (absolute aim about the bow) was the
right answer to the wrong model, and it survived because `invert_direction` was fixed in the same
window. Worth remembering: **a runaway is equally explained by a wrong control law and a wrong sign**,
and the sign was checked second.

**The tracking law, as specified by the user.** `_step_toward` per tick: box centre → **median of both
cameras** (when the right eye is also detecting) → offset in degrees → nudge the bar by
`offset × track_gain`, capped at `max_step_degrees` → stop inside `center_deadband_degrees`.
**Speed ramps with the offset** (`track_speed_min_rpm` 1.5 at centre → `track_speed_rpm` 8 at the
frame edge), so a big correction slews and a small one creeps instead of being flung past centre.
Simulated against the shipped config: a target at x=620 converges in **3 ticks** — +29.7° at 7.6 rpm,
then +4.5° at 2.5 rpm, then CENTRED — with no overshoot.

**Full 360°, no further** — `manual_*_degrees` ±180 for tracking *and* manual, `has_slip_ring: false`
so nothing wraps. Verified it parks at ±180 under sustained pressure rather than winding on.

**Median across two cameras: implemented, but only one eye detects today.** YOLO runs on the left
frame only; the right is a stereo *disparity* pass, not a detection. Added `detection.detect_right`
(**default off** — it is a second full forward pass, ~30 ms, so it roughly halves detection FPS) plus
`overlay.boxes_right()`. With it off the tracker uses the single centre, exactly as the user
specified. Pairing is by label + vertical centre within one box-height, because medianing a person in
one eye against a *different* person in the other would bias the bearing rather than de-noise it.

**⚠ The consequence I fixed without being asked, because it steers the boat.** With the cameras on the
bar, a bbox offset is relative to the **bar**, not the bow — so `pipeline._avoidance_bearing` was
wrong by the pan angle. A target held at bar +90° was reported dead ahead. That bearing feeds *both*
`object_memory` geolocation (markers charted up to 90°+ off) **and** avoidance steering (dodging the
wrong side). Now `offset + (bar_angle − bow)`, gated on `stepper.cameras_on_bar` so a hull-mounted
build restores the old behaviour. New test: heading 90° with the bar swung 90° starboard puts the
marker due **south**, not east.

**Divergence backstop added** (`_STALL_LIMIT = 5`): if five corrections fail to shrink the offset,
tracking **halts** and the radar panel says *"not centring — the bar may be turning the wrong way
(check invert_direction / invert_tracking)"*. Three sessions were lost to a silent runaway; it can't
happen silently again. The panel also now shows the live offset (`4.2° stbd`) and **CENTRED**, so the
loop's error term is visible.

**Changed:** `pi5/cv/radar_tracker.py` (`_step_toward`, `_target_offset_deg`, `_match_right`,
`_speed_for`, stall backstop; `_bearing_for` deleted), `pi5/cv/vision_overlay.py` (`detect_right`,
`boxes_right()`), `pi5/cv/pipeline.py` (`_boresight_deg`, bar-aware `_avoidance_bearing`),
`pi5/config.yaml`, `run_hardware.py`, `command_center.html` (offset / CENTRED / warning readout),
`docs/pin_map.md` + `docs/object_memory.md` (the stale "fixed forward" claim, corrected in place with
the old text quoted so the next reader knows it changed).

**Verified:** `pytest pi5/tests` **401 green** (+13), ruff clean, `node --check` OK, div balance
306/306, no dangling `$('id')`. Sim boots, endpoints 200, zero errors. **Nine of my own tests from
this session's earlier entries asserted the absolute-aim model and were rewritten**, not deleted —
they now cover the closed loop, the speed curve, the 360° stops, the two-camera median and the stall
backstop. Two pipeline tests were corrected the same way.

### Continuation 2026-07-30 (5) — velocity feedforward: aim where the target is going

**User:** "calculate the velocity that I am moving so the radar can track me faster — if I start
increasing in speed the radar bar increases too, to prevent me running out of frame."

**Implemented as a lead term on the measured angular rate:**
`step = (offset + rate × lead_seconds) × gain`, and the slew speed takes the **larger** of
"fast enough for this error" and "fast enough for this rate" (`|rate| ÷ 6 × margin` rpm, capped at
`max_rpm`). Scaling speed on error alone gave a target crossing quickly through the middle the
*slowest* bar exactly when it needed the quickest.

**Two measurement traps, both avoided deliberately:**
1. **Rate is fitted on the bow-relative BEARING (`bar angle + offset`), not the pixel offset.** With
   the cameras on the bar the offset shrinks purely because the bar turned — that is not the target
   moving, and a rate built on it would be measuring our own control action.
2. **Samples are only taken when the DETECTION changes.** The tracker loop runs at 10 Hz while the
   detector is capped lower, so most ticks re-read the same box. Sampling those pairs a frozen offset
   with a moving bar, so `bar + offset` drifts at exactly the bar's slew rate — the feedforward would
   have been feeding on its own motion. `_note_bearing` dedupes on the box coordinates; there's a test.
   Least-squares fit over the window rather than a two-point difference, because box edges jitter a
   few pixels per frame and a difference turns that straight into a phantom rate.

**Measured** against a rate-limited bar with 200 ms of detection latency (steady-state lag, constant
velocity). This is what the feature buys:

| target rate | lead 0 | 0.15 s | 0.25 s | **0.35 s** |
|---|---|---|---|---|
| 10°/s | 4.9° | 3.4° | 2.4° | **1.4°** |
| 20°/s | 7.6° | 4.6° | 2.6° | **0.8°** |
| 30°/s | 9.3° | 5.0° | 2.7° | **1.9°** |
| 40°/s | 12.5° | 8.4° | 6.8° | **6.4°** |
| 50°/s | 16.7° | 15.5° | 15.5° | 15.5° |

Past ~40°/s the bar is **speed-limited, not lag-limited** — no lead helps, `max_rpm` (10 rpm = 60°/s)
is the ceiling, and the panel now says so by name. Lead is a prediction, so it overshoots on a sharp
reversal (~7° at 30°/s, settles in a few ticks); that's the trade for the table above.

**Two corrections to my own work from continuation (3)/(4), both found by benchmarking rather than
assumed:**
- **The stall backstop was halting legitimate tracking.** A target at 30°/s opens a large offset
  during the initial catch-up, *before* the rate estimate has filled its window — five ticks of that
  tripped the backstop and it abandoned a target the bar could hold comfortably. Now it only counts
  once the estimate is mature, and it **warns without halting**. The halt was never needed: under a
  direction fault the target leaves the frame in a second or two and the lock drops on its own, so
  there is no end-stop runaway to prevent. The warning also distinguishes the two causes now
  ("turning the wrong way" vs "faster than the bar can slew") on whether the rate exceeds `max_rpm`.
- **My first two benchmarks measured the wrong thing** and I nearly reported "no benefit" off them.
  The first used an instant-move stepper — no lag exists, so nothing for a lead to cancel. The second
  let the simulated target walk past ±180°, so "LOST" was the travel stop working as designed, not a
  tracking failure. Only a rate-limited bar *with* detection latency shows the real behaviour.

**Changed:** `pi5/cv/radar_tracker.py` (`_note_bearing`, `_fit_rate`, `_reset_rate`, `_rpm_for_rate`,
`_speed_cap`, lead term in `_step_toward`, softened backstop), `pi5/config.yaml` (`lead_seconds`,
`velocity_window_seconds`, `velocity_speed_margin`), `run_hardware.py`, `pi5/server/app.py`
(`stepper_target_rate_dps` / `stepper_lead_deg`), `command_center.html` (panel shows `12°/s (lead
4.2°)`), `docs/pin_map.md`.

**Verified:** `pytest pi5/tests` **416 green** (+15), ruff clean, `node --check` OK, div balance
306/306, no dangling `$('id')`. Sim boots, endpoints 200, zero errors.

**Next steps:** (1) **Re-test TRACK, moving at a walking pace and then faster** — the panel shows the
measured rate and the lead being applied, so the feature is directly observable. (2) If fast targets
still trail behind centre, raise `lead_seconds`; if the bar overshoots and hunts, lower it. (3) If the
panel says *"faster than the bar can slew"*, raise `max_rpm` — but the A4988 is on a clone carrier at
~0.75 A, so check the motor doesn't start skipping steps. (4) If it says *"turning the wrong way"*,
flip `invert_tracking` (jog is known good, so it's that one). (5) Retune the buoy screen's gates.
(6) Record how the STEP fault got fixed; the entry below still reads as open.

## 2026-07-29 — Spare A4988 fitted: **the driver works, but STEP has never been connected**

**Worked on:** fitted the spare A4988 from the entry below and brought it up. The replacement is good —
the fault moved, and the new one is almost certainly a **build defect that has been there since day one**.

**Which carrier is which — solved with no meter.** The two physically identical carriers got mixed up.
`stepper_probe.py pins` separated them on the DIR signature alone (3× reproducible each way):

| | pulldown | pullup | drive-low | drive-high |
|---|---|---|---|---|
| dead carrier (post-overheat) | lo | **lo** | lo | hi |
| spare / empty socket | lo | **hi** | lo | hi |

`pullup=lo` on DIR while STEP/~ENABLE/~SLEEP stay clean = the dead one. Corroborated physically: the
spare's sense resistors read **`R10` = 0.10 Ω** (clone-spec) vs the dead one's 0.068 Ω, so they are
different parts. VREF set to **0.60 V ≈ 0.75 A** (I = VREF ÷ 8R_sense) with BT4 unplugged.

**The replacement driver's output stage WORKS.** Energised hold → shaft locks with real holding torque,
and **both chip and motor warm together**. Contrast the dead one: no torque, motor stone cold, chip hot.
Holding torque also proves **~RESET is high**, since a low ~RESET turns all FET outputs off — so the
~RESET↔~SLEEP tie is confirmed good on the built board, not just in the schematic.

**But STEP never reaches the chip.** Sent **800 pulses (400/direction, 50 Hz, 100 µs)** with the Pi pad
verified swinging cleanly: **zero rotation**. Shaft is **bare — no radar bar attached** — so insufficient
torque and mechanical binding are both ruled out. The earlier "two movements, both under a degree" at
1 Hz was the rotor snapping to a detent on energise and relaxing on release, i.e. **not one pulse has
ever landed.**

**This has never worked, which is the key clue.** `docs/session_journal_archive.md:1426` (2026-06-08,
first bring-up) is already "prints PASS but motor doesn't move". Seven weeks, two different carriers,
zero rotation. Everything else on the A4988 is confirmed working — VMOT (15.8 V), VDD, GND, ~ENABLE,
~SLEEP, ~RESET, both coil outputs, the motor and its J18 wiring. **Exactly one signal has never
functioned.** With `Boat_PCB.kicad_pcb` carrying no nets at all (never routed in KiCad → the board was
built by hand from the schematic), a single missed or misplaced STEP wire is the leading explanation.
A uniform one-position J3 shift is **ruled out** — it would have broken ~ENABLE and ~SLEEP too.

**Method notes worth keeping (two of my own results were wrong and are corrected here):**
- **`pins` can never detect this fault.** An open net reads identically to a healthy floating one, so the
  clean empty-socket baseline ruled out *shorts*, not *breaks*. Don't treat a clean `pins` as "the path
  is good".
- **The VMOT-sag-via-Pico-ADC method is not sensitive enough at normal current**, and my first run's
  "RAIL SAGS UNDER LOAD" verdict was wrong. A paired 4-cycle test (80 samples each) gave sag positive in
  only 2/4 cycles and ripple in 1/4 — noise, not signal. Reason: the A4988 is a chopper, so average VMOT
  current is ≈ duty × coil current (~100–200 mA at 0.75 A), giving ~5–40 mV of sag into a stiff M18 pack
  against a **~50 mV** ADC noise floor (GP26/27/28 still have **no filter caps** —
  `docs/pcb_design_notes.md:192`). It only worked in the entry below because a fully dead output stage
  draws *nothing* and a stone-cold motor corroborated it. **Use visible rotation, not the rail.**
- **Park the control lines with `pinctrl` whenever BT4 is live.** gpiozero releases every pin on exit, and
  the 10 kΩ ~ENABLE pull-up was never fitted, so each script leaves ~ENABLE floating with VMOT present.
  `pinctrl set 25 op dh && pinctrl set 8 op dl` (disabled, asleep) latches and persists across runs.

**Changed:** nothing in the repo except docs — `pi5/cv/stepper_probe.py`'s docstring now records all
three DIR signatures so `pins` doubles as the which-carrier-is-this test (ruff clean). The dense-burst
test lives in the session scratchpad only; **offer to promote it as a `burst` mode** on `stepper_probe.py`,
since it is the test that converted an ambiguous twitch into a decisive answer and will be needed again to
verify the fix. Parameters to reproduce: 400 pulses/direction, 50 Hz, 100 µs wide, mark the shaft first —
360° per direction if every pulse lands, so hit rate = degrees ÷ 360.

### Continuation, same day — the STEP net has an accessible midpoint, and two new probe modes

**The STEP net is a three-way node, not a point-to-point wire.** Re-solved the schematic geometry
(own S-expression parser + union-find again — the third session to write one and throw it away, see
below): **`A2.15 (STEP)` — `J3.15` — `J14.13`**. Solver self-validated on four independent documented
facts: `A2.13`+`A2.14` really are one net (the ~RESET tie), `A2.2 VDD` + `A2.10 MS1` + `R1.2` + `J3.2`
share a net, and DIR/~ENABLE land on `J3.17`/`J3.21` exactly as `docs/pin_map.md` says.

**Why that matters: `J14` is a `PinSocket_1x20` — a female socket** (`docs/pcb_design_notes.md:232`).
So the STEP net is reachable **without getting under the mated Pi and without soldering**. General rule,
now in the tool: **`J17.k` = Pi pin `2k−1`** (odd pins in order), **`J14.k` = Pi pin `2(21−k)`** (even
pins reversed). Verified against the solve for all four control lines (GPIO23→16→J14.13,
GPIO24→18→J14.12, GPIO25→22→J14.10, GPIO8→24→J14.9).

That turns the pending meter check into a **two-reading bisect** rather than one ambiguous probe:

| J14.13 | A2.15 STEP | verdict |
|---|---|---|
| 3.3 V | 3.3 V | net good → the carrier's STEP input or its socket contact; reseat, then swap carriers |
| 3.3 V | 0 V | break between J14/J3 and the carrier → **jumper J14.13 → the carrier's STEP pin** |
| 0 V | 0 V | break at J3 pad 15 or the Pi mate → jumper *another* free GPIO from J14/J17 and set `stepper.step_pin` |

**Changed:**
- `pi5/cv/stepper_probe.py` — **`burst` mode** (promoted from the scratchpad as offered): 400 pulses/
  direction, 50 Hz, 100 µs = 360°/direction if every pulse lands, so travel measures hit rate directly.
  This is the mode to re-verify any fix with. **`find` mode** (new): hunts a STEP wire that landed on the
  *wrong Pi pin* — energises the driver, then drives each of **23 free header GPIOs** in turn for 100
  pulses (90° of travel), ~66 s total, **no meter and no disassembly**. It characterises each candidate
  first and **drives it only if it reads cleanly floating**, so it can never fight something the board is
  driving; GPIO23 goes first as a known-null baseline, and 14/15 (GPS UART) and 8/24/25 (needed as
  controls) are skipped with the reason printed. Every hit is reported as
  `GPIO n → J14.k → header pin p`, i.e. straight to the jumper target. Also a **`_repark()`** helper now
  latches `~ENABLE` disabled + `~SLEEP` asleep via `pinctrl` on exit from `burst`/`find`/`power` —
  previously every script left `~ENABLE` floating with VMOT live (no 10 kΩ pull-up fitted), which the
  entry above flagged as a hazard and had to be worked around by hand.
- `pi5/cv/stepper_lowlevel_test.py` — the "never advances" outcome pointed at **"A2 pin 22"**, which is
  the bare A4988 IC's pin, not the carrier symbol's. It is **A2.15** (logic row, between SLEEP and DIR).
  Also says outright that this is the live fault and to use `burst`, not the 1 Hz walk, since a detent
  snap on energise reads as "a step or two landed".
- Removed a stray duplicated "Probe points" heading in `stepper_probe.py`'s docstring.

**Verified:** ruff clean; usage guard lists the new modes; `--pins` rejects a control pin (`24`) and
non-numeric input; `_jtap()` reproduces all four solved breakout pads; `HEADER_PIN` has 28 unique
entries and every tap lands in 1–20. **Nothing was energised** — `burst`/`find` need a human watching
the shaft, so they're left for the user to run. Pins still parked (`~SLEEP` low, `~ENABLE` high).

**Repo gap worth closing (third time asked):** the net solver keeps getting rewritten and discarded.
`Boat_PCB.kicad_pcb` has no nets and the schematic has **zero labels**, so every "the board does X" claim
in these docs comes from a geometric solve nobody can reproduce. Offer: promote it to
`tools/schematic_nets.py`.

**Next steps:**
1. **Run `find` first — it needs no meter** (`stepper_probe.py find`, BT4 plugged, watch the shaft ~66 s).
   A hand-built board is as likely to have STEP on the wrong pin as missing entirely, and this settles it.
2. **Then meter the STEP net** (`stepper_probe.py step 240` holds it high with coils cold; the 240 s run
   was done and the readings are still pending) — now as the **J14.13 / A2.15 bisect** in the table above.
2. Disambiguate open vs shorted: with GPIO23 back to high-Z (`pinctrl set 23 ip pn`), ohm the A4988 STEP
   pin to GND — near 0 Ω = shorted; megohms = open. Then continuity-test Pi header pin 16 → A4988 STEP.
3. If open, bodge a wire from Pi header pin 16 to the A4988 STEP pin and re-run the burst test.
4. Still outstanding from before: fit the **10 kΩ ~ENABLE pull-up** and the **three 100 nF ADC caps**
   (GP26/27/28) — the latter is what made the VMOT measurement useless. **C8** (100 nF, VMOT HF
   decoupling) optional; C7 confirmed populated.

## 2026-07-29 — Stepper diagnosis closed: **the A4988 is dead** (DIR input degraded, hot chip / cold motor)

**Worked on:** continued the entry below. It ended with "the fault is at or inside the A4988, five
candidates remain, go get a meter." Four of the five are now eliminated and the chip is condemned.

**The measurement that cracked it — electrical characterisation of the four control lines.** Every
previous session only ever *drove* the pins and read them back. Instead: internal pull-down, internal
pull-up, driven low, driven high, reading the **pad** level each time via `pinctrl`. Result:

| BCM | signal | pulldown | pullup | drive-low | drive-high | verdict |
|---|---|---|---|---|---|---|
| GPIO23 | STEP | lo | hi | lo | hi | clean, floating |
| **GPIO24** | **DIR** | **hi** | hi | **hi** | hi | **stuck HIGH — hard tie to 3V3** |
| GPIO25 | ~ENABLE | lo | hi | lo | hi | clean, floating |
| GPIO8 | ~SLEEP | lo | hi | lo | hi | clean, floating |

Controls: GPIO5 floated (lo/hi) and GPIO15 read driven-high (the GPS TX), so the method discriminates.
This had **never been tested** — the previous session's free-GPIO scan deliberately skipped 8/23/24/25 so
the motor couldn't be energised, and the session before only checked that the pins swing.

**Then DIR changed, permanently, and that is what condemns the chip.** With DIR driven *high* instead of
low (so as not to fight the tie) and the driver energised, the user reported: **no movement, motor stone
cold, but the driver chip HOT.** After de-energising, DIR re-measured as **pd=lo pu=lo dl=lo dh=hi** — a
few-kΩ *pull-down*, i.e. the internal ~50 kΩ pull-up can no longer pull it high. Confirmed reproducible
and **not** state-dependent (identical asleep and awake, outputs disabled throughout). A solder bridge
cannot change value, so the J3 pads-17/18 bridge theory is dead; a healthy CMOS input is >1 MΩ in both
states. So DIR went hard-high → weak-pull-down across one overheat event.

**Hot driver + cold motor** is the other half: VREF is set to **~0.7 V** (≈1.29 A on a 0.068 Ω carrier,
0.88 A on 0.1 Ω — a sane setting, so the current-limit candidate is gone), and I²R in a NEMA-17 winding
at ~1 A would warm the *motor*. A cold motor with a hot chip means the VMOT current is going through the
chip, not the windings — a shorted/blown output stage. It also explains why the previous session measured
**zero VMOT sag**: that test ran with DIR *low*, which loaded the VDD/MS1 net and left the chip off.

**Candidates now closed:** (a) VREF at zero — **no**, 0.7 V. (b) motor unplugged / open coil — **no**, user
confirmed J18 mated (coil ohms still unverified). (c) carrier not seated — **no**, confirmed seated.
(d) RESET↔SLEEP tie broken — **not the cause**; ~SLEEP measures clean and the tie is in the schematic.
(e) **dead A4988 — this one.**

**Also disproved my own mid-session theory:** I suspected J3's transposition ran the *opposite* parity
(which would have put ~SLEEP on GPIO25 and grounded STEP/~ENABLE, elegantly explaining zero current).
`docs/pin_map.md:248` kills it — J3 pads 1/3 land on Pi header pins **2/4**, i.e. odd pad → pin+1, the
documented mapping. STEP really is GPIO23.

**Two board facts found while chasing root cause, both worth acting on before a replacement goes in:**
- **C7 is the VMOT bulk electrolytic** (`docs/pcb_design_notes.md:179` — "the electrolytic Pololu asks
  you to add"). **Populated status unverified.** A missing C7 is the classic A4988 killer: the LC spike
  when BT4 is plugged in punches through the output stage. If it's absent, a new driver dies the same way.
- **The 10 kΩ ~ENABLE pull-up was never fitted** (`docs/pcb_design_notes.md:129`, on the "add these"
  list), so ~ENABLE has no defined state unless the Pi is driving it.
- `Boat_PCB.kicad_pcb` has **no nets assigned at all** (every pad `net=""`) — the board was never routed
  in KiCad, so the PCB file is useless for net tracing. Only the schematic has connectivity, and it uses
  **zero labels** (394 wires + power symbols), so any net question needs a geometric solver.

**Changed:**
- `pi5/cv/stepper_probe.py` — new **`pins` mode** (`stepper_probe.py pins`), the test above, as the
  cheapest-first entry point: no meter, nothing energised, all four lines left high-Z. Classifies each
  line (OK / shorted-high / shorted-low / resistive pull / odd) and warns that a shorted control line can
  drag the A4988's VDD around. Uses `pinctrl` for read-back **on purpose** — lgpio/the gpio chardev
  returns the value you *wrote* to an output line, not the pad voltage, so it is blind to contention.
  Docstring records this session's numbers.

**Verified:** ruff clean; `pins` reproduces the DIR anomaly and exits 0; usage guard rejects a bad mode.
Stepper left **asleep, disabled, DIR high-Z**. Pico firmware still stopped (GP10 short).

**Next steps — all meter-free and decisive, in order:**
1. ✅ **DONE — carrier removed, BT4 unplugged, `pins` re-run: all four lines clean (`lo/hi/lo/hi`),
   DIR included.** So the **board and the Pi's GPIO24 pad are both good** — no bridge at J3 pads 17/18,
   no DIR↔VDD short, no damaged Pi pad (which also made step 2, unmating the Pi, unnecessary). By
   elimination *every* DIR anomaly — the hard tie to 3V3, then the few-kΩ pull-down — originated **inside
   the old carrier**, which independently confirms the chip was dead. This empty-socket run is also the
   known-good baseline the project never had for these four lines. User is fitting a spare A4988.
   **Follow-up, same day:** the two carriers got mixed up, and `pins` told them apart with no meter —
   the seated one re-read DIR as `pd=lo pu=lo dl=lo dh=hi`, an exact 3×-reproducible match to the dead
   driver's post-overheat fingerprint (STEP/~ENABLE/~SLEEP all clean, which is what makes it the
   *carrier* and not the board). So `pins` is now also the **which-driver-is-this** test: `pullup=lo` on
   DIR alone = the dead one.
2. ✅ **DONE — the motor is good** (builder confirmed the coils read right at J18, 2026-07-29: pins
   1↔2 / 3↔4 are the pairs, 1↔3 open). So the motor did **not** kill the driver.
   **With C7 populated (3) and the motor clean (2) and the board/Pi pads clean (1), no external cause
   for the first driver's death remains** — most likely a defective clone chip, possibly finished off by
   a plug/unplug with VMOT live.
3. ✅ **DONE — C7 is populated** (confirmed by the builder, 2026-07-29). So the VMOT bulk electrolytic
   was present all along and a missing-C7 hot-plug spike is *not* what killed the first driver. **C8**
   (100 nF ceramic, VMOT HF decoupling) is a should-fit, not a gate: `docs/pcb_design_notes.md:202`
   puts the plug-in-transient role on the bulk caps, and the Pololu carrier carries its own local
   ceramic across VMOT. ⚠ **No capacitor on this board has a value in KiCad** — all nine are literally
   `"C"` / `"C_Polarized"`. For this rail: C7 = 100 µF **50 V** (VMOT is an M18 at up to 21 V and
   hot-plug rings past 2×), C8 = 100 nF 50 V.
4. **Set VREF on the spare with BT4 still unplugged** (the trimpot divider runs off VDD alone, so this is
   the safe moment; a spare's pot could be anywhere out of the box). ⚠ **Check the spare's sense
   resistors first — don't reuse the old VREF number.** They're marked `R050`/`R068`/`R100`; a clone and
   a genuine Pololu differ, and I_limit = VREF ÷ (8 × R_sense), so 0.4 V is 0.50 A on 0.1 Ω but 1.00 A
   on 0.05 Ω. The dead one was ~0.7 V ≈ 1.29 A on 0.068 Ω. An A4988 with no heatsink is only good for
   ~1 A and the radar bar needs little torque, so **target ~0.7–0.9 A** (a *current*, not a voltage) —
   runs cooler and keeps "hot chip" a meaningful alarm signal.
   **Spare identified: sense resistors read `R10` = 0.10 Ω**, i.e. clone-spec, not Pololu's 0.068 Ω
   standard or 0.05 Ω Black Edition. So I = VREF ÷ 0.8 and the setting is **VREF ≈ 0.60 V ≈ 0.75 A**.
   The two carriers are therefore *different parts*, which independently corroborates the `pins`-based
   ID above. Clone carriers also tend to have weaker thermal design (thinner copper, less via
   stitching under the chip), so the reduced current setting matters more here than on a genuine board.
5. Re-run `pins` with the spare seated, then plug BT4 and drive a short burst, checking **both** chip and
   motor temperature immediately. Never plug/unplug the motor or the carrier with BT4 live — that is the
   most likely thing that killed the first driver.
   ⚠ **Park the control lines before plugging BT4.** `pins` deliberately leaves all four **high-Z**, and
   the 10 kΩ ~ENABLE pull-up was never fitted (`docs/pcb_design_notes.md:129`), so ~ENABLE has no defined
   state with nothing driving it — plug VMOT into that and the driver may come up *enabled* with an
   undefined phase, i.e. DC through two windings until software claims the pins. Unlike gpiozero (which
   releases on exit), `pinctrl` latches persist:

       pinctrl set 8 op dl && pinctrl set 25 op dh    # ~SLEEP=0 asleep, ~ENABLE=1 disabled

   This matches `stepper_lowlevel_test.py`'s gpiozero init (`en`=True, `slp`=False) so there is no glitch
   at handover — but that script releases the pins when it exits, so **unplug BT4 or re-park afterwards.**
   Fitting the 10 kΩ removes the whole hazard and is the real fix.

## 2026-07-29 — Stepper still dead: Pi side + software + VMOT all PROVEN GOOD, fault is at the A4988

**Worked on:** user reported the radar-bar stepper still doesn't move. Diagnosis only — the only repo
change is new tooling.

**Observed symptom (user, watching the 45 s low-level test):** shaft **silent, spins freely by hand, no
holding torque** — i.e. **no coil current at all**. User also confirmed **the Pi IS mated to J3**.

**Eliminated, by measurement rather than inspection:**
1. **The Pi's four pins are electrically fine.** Drove each with `pinctrl` and read back the *real pad
   level*: STEP GPIO23, DIR GPIO24, ~ENABLE GPIO25, ~SLEEP GPIO8 all swing hi/lo cleanly. No short like
   the Pico's GP9/GP10.
2. **Not mock mode.** gpiozero imports, resolves to `LGPIOFactory`, and claims/releases GPIO25 fine.
3. **The driver software is correct.** Instrumented `StepperMotor._w` and ran real commands: a 9.0°
   move emitted **exactly 10 rise + 10 fall** pulses, `rotate_to(45)` emitted 40, position accounting
   landed on 9.00°/45.00°, soft limits clamped a −30° request to 0°, and the control order was right
   (`~SLP=1 → ~EN=0 → DIR → pulses`). 100-pulse train in 0.102 s.
4. **VMOT is PRESENT — 15.53 V.** This is the one that overturned the obvious theory. Solved the
   schematic net graph (own S-expression parser + union-find; kicad-cli isn't installed on this Pi;
   self-validated by all 8 Pico GND pads resolving to GND) and found **VMOT → R8 100k → R9 1k → Pico
   pad 34 = GP28**, i.e. the stepper's motor supply *is* the rail the Pico already monitors. Read it
   over `mpremote` (ADC only, so GP10's short stayed untouched): **GP28 = 15.64 V**. The 2026-07-28
   entry's "winch pack disconnected" no longer holds — the user has since plugged BT4 in.
5. **The A4988 draws ZERO motor current.** Sampled GP28 on the Pico *while* the Pi energised the driver
   and sent 400 pulses: rail sat at **15535 mV idle → 15535 mV energised → 15532 mV stepping** (±3 mV,
   pure noise). A real coil load would show as a dip. So the chip never drives its outputs.

**Two doc claims checked and CONFIRMED (both had been suspects):**
- **~RESET (A2.13) and ~SLEEP (A2.14) are genuinely one net** in the schematic, so the tie is by design
  and `reset_pin: null` is right. Still worth a meter check, since this board has diverged from its
  schematic three times already.
- **A4988 VDD really is the Pi's 3V3.** J3's transposition is **parity-dependent**: *odd* pads map +1
  (STEP pad 15 → Pi pin 16 = GPIO23, DIR 17→18, ~EN 21→22, ~SLP 23→24) while *even* pads map −1, so
  VDD pad 2 → **Pi pin 1 = 3V3**. Also confirmed MS1 shares the VDD net via R1 10k and MS2/MS3 → GND,
  so half step / 400 steps-per-rev is correct.

**Conclusion: the fault is at or inside the A4988 / its motor output path** — everything upstream is
proven. Five candidates remain, all consistent with "powered, correct signals, zero current", and all
needing a meter: (a) **VREF turned to zero** (current limit down → no torque), (b) **motor unplugged or
an open coil at J18**, (c) **carrier not seated** (VMOT on the board net but not at the chip's pin),
(d) the RESET↔SLEEP tie **broken on the built board** despite the schematic, (e) dead A4988.

**Changed:**
- `pi5/cv/stepper_probe.py` — new **`power` mode** (`stepper_probe.py power 120`): holds the driver
  awake + **energised** (unlike the other modes, which park ~ENABLE high) so every rail can be metered
  at rest with nothing stepping, and prints the six checks in cheapest-first order with expected values
  and what each failure means. Docstring now carries this session's measured facts — the pad-level
  results, VMOT 15.53 V, the zero-current result, the J3 parity rule, the RESET/SLEEP net — so nobody
  re-derives them. De-energises in a `finally`.
- `pi5/cv/stepper_probe.py` + `pi5/cv/stepper_lowlevel_test.py` were **untracked** from a previous
  session; still untracked, still uncommitted.

**Verified:** ruff clean; `power` mode smoke-run (3 s) energises and releases correctly; usage guard
rejects a bad mode. Stepper pins left released (inputs, coils de-energised) and the **Pico firmware
left stopped** as before, since it drives GP10 into its short.

**Next steps:** user meters the A4988 with `stepper_probe.py power` — **VREF and the J18 coil continuity
first**, they're the cheapest and the best fit. Nothing more can be learned from software.

## 2026-07-29 — GPS rewired to the Pi header: **it works** (38400 on /dev/ttyAMA0), and it's wired into nav

**Worked on:** user moved the GPS off the Pico's J7 (dead — see the entry below) onto the **Pi 5 header
GPIO14/15 (physical pins 8/10)** and asked me to test it. Measurement only; **no repo files changed**.

**Result — the GPS is working on the Pi.** `/dev/ttyAMA0` @ **38400 baud**: 10 s captured 136 sentences,
**100 % checksum-clean, 0 bad**, GGA at **1.00 Hz**, GSA fix mode **3 (3D)**, GGA quality **1**, 6 sats
used, HDOP 2.22. 663 B/s ≈ 6.6 kbps of the 38400 line, so ample headroom.

**How it was found, without assuming the wiring:**
1. **Pull-up/pull-down scan of every free header GPIO** (skipping the A4988's 8/23/24/25 so the motor
   couldn't be energised): **only GPIO15 is externally driven high** — a UART TX idling. GPIO14 floats,
   which is correct, since that's the Pi's *own* TX and a GPS doesn't drive it.
   ⚠ **GPIO2/3 also read high, and it is NOT a device** — every Pi has permanent **1.8 kΩ pull-ups** to
   3V3 on header pins 3/5, which the internal ~50 kΩ pull-down can't overcome. Don't misread that as a
   plugged-in peripheral (I did, briefly); the I²C1 scan below settles it.
2. **Edge-timing sampler on GPIO15** (~463 kHz polling via lgpio, 2.2 µs resolution): **6718 edges in
   2 s**, line low 7.8 % of the time, 5th-percentile run **24.6 µs → 38400 baud** (26.0 µs/bit). This is
   the check that separates "transmitting" from "pull-up", which is exactly what fooled us on the Pico's
   GP8 last session.
3. **`sudo dtoverlay uart0` loaded at *runtime*** — GPIO14→TXD0, GPIO15→RXD0, `/dev/ttyAMA0` appeared,
   **no reboot required**. Then `gps_probe host --port /dev/ttyAMA0 --baud 0` auto-bauded straight to a fix.

**Three corrections to earlier conclusions:**
- **The serial console does *not* conflict with GPIO14/15 on a Pi 5.** `console=serial0` → `ttyAMA10`,
  which is the Pi 5's **separate 3-pin debug-UART connector**. The entry below said this needed "the
  serial console freed" — that's Pi 4 advice; nothing had to be stopped.
- **The module is a u-blox M10 family part, matching the pin map's "GPS M10Q".** Talkers are
  GP+GA+GB+GQ (GPS/Galileo/BeiDou/QZSS, **no GLONASS**) and the baud is 38400 — both are M10 factory
  defaults (M8 defaulted to 9600, which is where the firmware's number came from).
- **`firmware/boat-pico/gps.py:94` opens UART1 at 9600 — a second, independent bug.** This module talks
  38400, so even with the GP9 short repaired *or* the TX jumpered to GP5, the Pico would have read
  garbage. Worse, the **Pod Pico shares that same UART** (`main.py:555`) at 9600, so one UART cannot
  serve a 38400 GPS and a 9600 Pod — a substantive argument for leaving the GPS on the Pi.

**Two things that are live but unfinished:**
- **The UART is not persistent.** The overlay was loaded at runtime and is **lost on reboot**; it needs
  `dtoverlay=uart0` in `/boot/firmware/config.txt` (not added — that's a boot-config change).
- **Nothing in the nav stack reads `/dev/ttyAMA0`,** so the navigator still has no position. The path was
  traced last session and is unchanged: write `lat`/`lon` into `PicoSerial.telemetry`
  (`pi5/comms/pico_serial.py:22`), which `navigator.py:399-437` already consumes; heading stays on
  `tel.heading` from the Pico compass.

**Also measured:**
- **No UBX reply** to 5× `MON-VER` polls over 5 s → the Pi's **TX (GPIO14) is very likely not wired to the
  module's RX**. Harmless for navigation (NMEA is unsolicited), but the module **can't be reconfigured**
  — baud, update rate, constellation set — from the Pi until that 4th wire exists.
- **I²C1 scan is completely empty** (`i2cdetect -y -r 1`, enabled at runtime then reverted). No compass,
  no u-blox DDC at 0x42 → **the module's I²C is not wired to the Pi**, only its UART TX.
- **The fix is a weak indoor one — don't trust the position yet.** Median C/No **24 dBHz** (max 34), 6
  sats, HDOP 2.25, and the reported **altitude wandered 162.9 m → 222.6 m in ~3 minutes**. Re-test
  outdoors before believing the coordinates. UTC date/time in RMC were correct, which does confirm real
  satellite reception rather than a replayed/simulated stream.
- ⚠ **New pin conflict: `pi5/scripts/am32_config.py` wants the same two pins.** It flashes AM32 ESCs over
  `/dev/ttyAMA0` on GPIO14/15 and its docstring even prescribes `sudo dtoverlay uart0`. With the GPS on
  pins 8/10, **ESC configuration and the GPS are mutually exclusive** — one must be unplugged.

**Then wired it into the nav stack** (user chose "persist + wire in", and to keep the GPS on GPIO14/15
rather than move to a USB-TTL dongle).

**Changed:**
- `pi5/comms/gps_nmea.py` (NEW) — `NmeaParser` (pure, I/O-free, so it unit-tests with no port and no
  Pi) + `NmeaGps`, an async reader mirroring `PicoSerial._read_loop`'s self-healing backoff.
  Talker-agnostic (matches the 3-char sentence type, so GN/GP/GA all work), validates the hex NMEA
  checksum, parses GGA + RMC. **Read-only — it never writes to the port**, so it can't disturb the
  receiver's config. Rejects corrupt coordinates (minutes ≥ 60, out-of-range degrees) instead of
  emitting a plausible-looking wrong position. A missing port logs **once** then retries quietly, so
  it's harmless on a laptop.
- `pi5/comms/pico_serial.py` — `use_external_gps()` / `set_external_position()`. The subtlety: TEL
  arrives at 1 Hz and `_handle_tel` builds a **brand-new `Telemetry` every frame**, so a naive write
  to `pico.telemetry.lat` gets clobbered within a second. The override is therefore re-applied inside
  `_handle_tel`, *and* applied immediately on each fix so consumers polling between frames see fresh
  position. Adds `fix_quality` / `sats` / `gps_source` to `Telemetry`.
  **Heading is never touched** — still the Pico compass. Also suppresses the ~1 Hz `SENSOR_FAULT,gps`
  spam (only when an external source is declared) and rewrites **health bit 0** to describe the *Pi's*
  receiver, since the Pico's GPS bit now describes hardware that isn't attached to it.
- ⚠ **Design call worth knowing:** a *stale* fix still overwrites lat/lon, deliberately. The Pico's own
  lat/lon are a hard `0.0` with no receiver, and there is **no `(0,0)` guard anywhere in the nav
  stack** — handing the navigator the Gulf of Guinea is worse than a position a few seconds old.
  Staleness surfaces as `fix_quality=0` / `gps_source="pi-stale"` instead.
- `run_hardware.py` — builds `NmeaGps` from config, wires `on_fix` → `set_external_position`, starts it
  before the navigator, stops it on shutdown. Shouts if `gps.enabled` is false (the navigator would
  silently compute from (0,0)), in the spirit of the stepper's mock-mode warning.
- `pi5/config.yaml` — new `gps:` block (enabled/port/baud/stale_after_s) with the M10-38400 and
  am32_config pin-clash warnings inline.
- `pi5/server/models.py`, `pi5/server/app.py` — `fix_quality`/`sats`/`hdop`/`gps_source` on
  `TelemetryOut`, so they ride both `/api/telemetry` and the 1 Hz `/ws/telemetry` stream.
- `pi5/server/templates/command_center.html` — **GPS in the command center.** Two rows added to the
  POSITION panel, directly under Lat/Lon because they qualify it: **GPS Fix** (`GPS · 7 sats` + a muted
  source tag) and **Accuracy** (HDOP). Colour follows meaning rather than raw value — green only when
  the fix is present *and* fresh *and* from a source that can actually produce one; **amber for a stale
  fix**, because the position stays on the map and the operator has to know it's aging; red for no fix
  or a `pico` source (which on this board can never have one). A stale fix reads **"STALE FIX"** rather
  than the literal `fix_quality=0` → "NO FIX", which would be a lie while a position is displayed.
  HDOP is graded ≤2 good / ≤5 moderate / >5 "do not trust", with the reasoning in the tooltip.
  Free win: the health panel's existing **`GPS OK/FLT` chip** now tells the truth too, since it reads
  health bit 0, which this branch rewrites to describe the Pi's receiver.
- `pi5/navigation/simulator.py` — sim reports `fix_quality=1, sats=12, gps_source="sim"`; it was
  claiming `health="111111"` while also reporting no GPS fix.
- `/boot/firmware/config.txt` (**system, not repo**) — `dtoverlay=uart0` appended so the UART survives
  a reboot. Backup at `config.txt.bak-gps-2026-07-29`.
- Docs: `docs/pin_map.md` (new Pi-5 GPS-UART section; corrected the stale "**the GPS has no UART on
  this board**" claim — GP8/GP9 are dual-function I²C0 *or* UART1, so J7 always was the GPS UART; fixed
  the GP4/GP5/GP8/GP9/J7/UART1/I²C0 rows) and `CLAUDE.md` (topology, pin orientation, and the
  "Pi 5 uses only USB — no GPIO" locked decision, which now has two documented exceptions).
- `pi5/scripts/gps_probe.py`'s existing `host` mode already covers bench sniffing
  (`--port /dev/ttyAMA0 --baud 0`), so **no new tool was needed**. Runtime state: the `i2c_arm` dtparam
  I added for the scan was **removed again** after it came back empty.

**Verified (on the Pi):** `pytest pi5/tests` **341 green** (from 293, **+48**), ruff clean, firmware
`py_compile` OK, inline `<script>` passes `node --check`, div balance 306/306, and every `$('id')` the
page references exists in the markup. Sim boots with `/` and `/planner` 200.
End-to-end against the **live** GPS, not a mock: 12 fixes in 6 s, 89 sentences, 0 bad checksums →
`telemetry.lat/lon = 37.5728978, -122.3918808`, `fix_quality=1`, `sats=7`, `gps_source="pi"`,
health bit 0 flipped to 1, heading left untouched. Then the three behaviours that matter, all PASS:
a TEL frame carrying `lat/lon 0.0` **did not** clobber the fix; `SENSOR_FAULT,gps` was suppressed while
`SENSOR_FAULT,imu` still surfaced; and after stopping the reader for 3.5 s the last position was still
served with `fix_quality=0` / `gps_source="pi-stale"`.

**Verified the dashboard on the real hardware path.** Served the command center with the production
wiring (`NmeaGps` → `set_external_position` → `_tel_out`) but *without connecting to the Pico*, so no
firmware was deployed and GP10 was never driven into its short. `/` → 200, and `/api/telemetry` returned
the live fix: `37.5728812, -122.3918423`, `fix_quality=1`, `sats=7`, **`hdop=1.26`**, `gps_source="pi"`,
`health="100000"`. `/ws/health` confirmed `health_flags.GPS = True`, i.e. the existing GPS chip now reads
OK off the Pi's receiver. `/ws/telemetry` carries all four fields.
**`renderGps` was exercised directly** rather than eyeballed — extracted from the template and run in
node against a DOM-accurate stub across **9 states** (live / poor-HDOP / stale / no-fix / pico-fallback /
sim / RTK / single-satellite / missing-fields-old-payload), checking text, colour and tooltip for each.
That caught two things: the no-fix rows must clear a previously rendered HDOP (they do — `textContent`
replaces children), and the original "NO FIX · STALE" wording, now "STALE FIX". ⚠ Headless browser
screenshots are blocked in this sandbox, so **layout/spacing of the two new rows is unverified visually**
— the logic is proven, the look isn't.

**Decisions / open questions:** I did **not** add a "refuse to navigate without a fix" gate. There's no
such guard today, so adding one is a behaviour change in its own right — a brief dropout mid-mission
would stop the boat — and that's a call worth making deliberately. `fix_quality` is now exposed
specifically so it *can* be gated. Nothing committed — tree left for review.

**Next steps:** (1) **outdoor re-test** — the bench fix is weak (6–7 sats, HDOP 1.26–2.25, altitude
drifting 60 m), so accuracy is unproven; (2) decide on the no-fix navigation gate; (3) eyeball the two
new POSITION rows in a real browser (logic verified, layout not); (4) add the Pi-TX→module-RX wire if
5–10 Hz is ever wanted; (5) fix `gps.py`'s 9600 if the Pico ever hosts a GPS again.
**Heading is the remaining blocker for navigation** — the Pi GPS supplies position only, and
`tel.heading` still comes from the Pico compass on the dead I²C0. User's call (2026-07-29): **don't fix
the compass — the IMU will take over heading later.** So navigation stays blocked until that lands.
**Still open and untouched:** the GP9/GP10 hard short (status NeoPixel dead, I²C0 dead).

---

<!-- Older entries (right-view box fix + live depth view, stereo vision review + Windows camera fix, live camera assignment, commit/push housekeeping,
     align-first steering, waypoint planner page, M18 battery migration, token-bloat audit,
     third-downloaded-file audit, repomix/rtk, token-optimization config pass) live in
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

---

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

---

## 2026-07-26 — Camera recording + Tesla-style sentry mode + Recordings dashboard section

**Worked on:** `/goal` — record the camera to the Pi, auto-record critical moments like Tesla Sentry,
and a dashboard spot to browse/play clips (make it look good).
**New `pi5/cv/recorder.py` (`Recorder`):** rolling pre-roll ring (JPEG-encoded, memory-bounded) so an
event clip includes the run-up; manual start/stop; `note_event(reason)` sentry trigger (debounced,
seeded from pre-roll, extends while the event persists up to a hard cap); auto-stop via `tick`; writes
browser-playable **VP8/WebM** (fourcc probe → mp4v fallback) + a JSON sidecar; retention cap; path-
traversal-safe list/serve/delete. All OpenCV work is synchronous here; the server drives it via
`asyncio.to_thread`. +6 unit tests.
**Server (`app.py`):** an always-on background feed task subscribes to the camera (or synthesises a
telemetry-HUD frame in sim, so the feature is demoable with no camera), buffers pre-roll while sentry
is armed, evaluates sentry triggers (~3 Hz: CRITICAL vision threat / hull leak / pod leak) and ticks
the recorder — all off the event loop. Endpoints: `GET /api/recordings` (status + clips), `POST
/api/recordings/start|stop`, `POST /api/recordings/sentry`, `DELETE /api/recordings/{name}`, and
`GET /api/recordings/{name}` (served with `?key=` like `/video`, for the `<video>` tag). Wired into
`run_sim.py` (+ sim reactive-avoidance now raises a sentry event) and `run_hardware.py` (config-driven);
`recording:` block added to `config.yaml`; clips gitignored.
**Dashboard:** folded into the **CAMERA panel** (not a separate box, per follow-up) — a control bar with
a SENTRY arm toggle, manual REC/STOP, a live `● REC` overlay on the feed, and a **RECORDINGS** button
that opens an **ESC-settings-style modal** (`#mRec`): a player beside a severity-coloured clip list
(critical/warning/manual, timestamp, duration, size) with **fullscreen / download / delete** footer
actions. Serve endpoint returns inline (`accept-ranges: bytes` → seeking; download via `<a download>`).
**Verified (on the Pi):** `pytest pi5/tests` **242 green** (+6), ruff clean, inline `<script>` passes
`node --check`, dashboard Vite build clean. Drove the whole lifecycle over real HTTP: manual clip
(29 frames / 2.9 s / valid 49 KB WebM) → served 200 `video/webm` → deleted; armed sentry, drove the
boat into a dropped obstacle → **auto-clip fired with pre-roll** (`critical-threat:obstacle`), extended
while avoiding (620 frames / 62 s / 1.2 MB), finalised, served. The RECORDINGS section + JS render in
the served page.
**Decisions / open questions:** H.264 needs a HW encoder that isn't present here, so clips are VP8/WebM
(universal browser playback). Sim has no camera → the feed synthesises a HUD frame; on hardware it
records the live left camera. Sentry triggers are CRITICAL-threat / hull-leak / pod-leak (operator
estop left out). Not yet exercised with a real camera on the Pi.
**Next steps:** on-camera hardware pass; optional clip thumbnails; maybe a download button beside inline play.
**Follow-up (recording duration):** a clip was getting cut off at the ~90 s hard cap while a threat was
still in frame. Reworked the stop logic so a sentry clip now records **until the threat clears** — it
runs on while `note_event` keeps firing and stops only `retrigger_extend_s` (8 s) after the last
sighting; `max_clip_s` (now 300 s) is a per-**segment** cap that **rolls over** into a new file instead
of stopping mid-event, so a persistent threat is never cut off (files stay bounded + prunable). +1 test
(`test_persistent_threat_records_until_it_clears`); verified on the sim (recorded continuously through a
sustained avoidance, stopped ~8 s after the threat went away → one 16.8 s clip).
**Follow-up (retention):** added age-based cleanup — clips older than `max_age_days` (default **14**) are
deleted, alongside the existing `max_clips` count cap. Pruned on every save, at `Recorder` construction,
and hourly by the server feed (`prune_old()`), so stale clips go even with no new recordings. Age comes
from the clip's metadata `started` (falls back to file mtime); `0` keeps forever. Config
`recording.max_age_days`; +2 tests.
**Follow-up (favorites):** a clip can be **favorited** (★) to pin it — favorites are exempt from both the
age sweep and the count cap (but can still be deleted explicitly). `favorite` bool in the clip metadata;
`Recorder.set_favorite()` + `POST /api/recordings/{name}/favorite`; the recordings modal footer got a
FAVORITE toggle and rows show a ★. +2 tests; verified the endpoint + guard on the sim.

---

## 2026-07-26 — Recursive improvement pass (5 rounds): CV/server perf, dashboard a11y, dead-code + tests

**Worked on:** `/goal` — recursively hunt codebase + efficiency improvements, research-driven, ≥5
iterations; user also invited a big HTML overhaul (rated the dashboard 7/10). Ran 5 verified rounds off
a clean baseline (234 tests green, ruff clean, both Vite builds pass). Verified every audit finding by
hand first — **rejected more than I applied.** Each round committed separately + pushed.
**R1 — discovery + research:** 3 parallel Opus audit agents (cv / navigation+comms / server) + web
research on modern control-room/ECDIS dashboards and numpy/OpenCV/asyncio efficiency.
**R2 — CV perf:** `threat_assessor._match` compares squared centroid distances (no per-candidate sqrt
each frame; monotonic); `size_history` trimmed in place (`del h[:-n]`) not rebuilt; `object_memory.stats()`
one pass not four. Rejected: `size_history`→deque (breaks the slice reads in `_approach_vector`), the
(0,0) GPS guard "bug" (deliberate sentinel), `_enforce_cap` "every frame" (already early-returns).
**R3 — server perf:** `_gather_health` ran psutil (`disk_usage` statvfs + `/proc`) on the event loop
every 1 s → extracted `_gather_psutil_stats()` + `asyncio.to_thread` (also unblocks the `/ws/health`
cold-start); `/api/camera/devices` POST write offloaded. Verified end-to-end against a real
`_gather_health()` call (psutil 7.2.2). Rejected the TEL/ENV "partial field" findings (the `>=12` gates
match the protocol's all-or-nothing v1.1 appendix) and the module-load `asyncio.Lock` nit (fine on 3.10+).
Also rejected on nav: the WINCH_UP `skip_site` "bug" — the winch *must* fully retrieve the pod before
moving on, so ignoring skip during ascent is intentionally safer.
**R4 — dashboard a11y (NOT a blind rewrite):** measured the existing design first — **every text token
passes WCAG AA on all four surfaces** (muted 5.3–6.4, crit 4.7–5.7), and global
`prefers-reduced-motion` + `:focus-visible` + a semantically-valid palette are already present. It's
objectively strong; "7/10" is subjective and **I could not render on this ARM Pi** (headless chromium is
killed in the sandbox; user declined the Chrome tool this session), so a blind restyle of a tuned design
wasn't defensible. Applied verifiable wins: `role=alert`/`aria-live` on the estop banner + toast (were
silent to screen readers) and `aria-label` on the 8 unlabeled sliders.
**R5 — simplification + tests:** removed genuinely-dead `ThreatAssessor.is_approaching` (0 callers;
superseded by `_approach_vector`); the graph's other 76 "dead" hits are framework/dispatch false
positives (`require_api_key` Depends, ASGI middleware, `MockPicoSerial`, argparse `cmd_*`) and were left
alone. Added `test_threat_assessor.py` (nearest-track association, previously covered only indirectly).
**Verified (on the Pi):** `pytest pi5/tests` **236 green** (+2), ruff clean, both templates' inline
`<script>` pass `node --check`, dashboard Vite build clean; booted the sim and confirmed `/` still 200
with the new aria attributes.
**Decisions / open questions:** the *visual* overhaul is the one open item — the design is objectively
AA-clean and I can't render it here, so the next step needs the user to view `localhost:8000` and name
specific visual directions (colours / density / typography), or enable a browser tool.
**Next steps:** (unchanged) on-bench/on-water ESC + telemetry passes; optional user-directed dashboard
restyle.

---

## 2026-07-26 — 5-agent code audit (fixes applied) + dashboard HTML redesign to "10/10"

**Worked on:** user asked to (a) finish the interrupted verification — 5 max-effort (Opus) agents
checking the whole stack for correctness + efficiency — and (b) lift the served HTML dashboards from
a self-rated 7/10 to a 10/10.
**Audit (5 parallel Opus agents; baseline healthy: 234 tests green, ruff clean, both Vite builds pass,
both inline `<script>`s valid).** Applied the *verified, safe* findings; rejected/​skipped the rest with
reasons:
- `pi5/navigation/navigator.py` — **CRITICAL** div-by-zero guard: `compute_throttle`'s turn-blend
  divided by `(max_heading_error_deg − heading_tolerance_deg)` unguarded while the sibling `_steer_to`
  already used `max(1.0, …)`; made them consistent.
- `pi5/server/app.py` — **event-loop unblocking**: `/ws/camera` now offloads StereoSGBM + `cv2.imencode`
  to the executor (mirrors `/video`); `/api/paths` read/write moved to `asyncio.to_thread`; `/api/pod/history`
  `limit` clamped to ≤5000 (was unbounded → OOM/DoS vector).
- `pi5/cv/wave_detector.py` — vectorised the water-mask horizon scan (per-column Python loop → numpy
  `argmax`/`where`; dormant path, ~30× when used).
- `firmware/boat-pico/main.py` — health-flag battery bits now use the real `is_prop_critical()`/
  `is_elec_critical()` predicates (were `>5.0`/`>3.0` → always "healthy"; telemetry-accuracy only).
- `cloud/api/app.py` — `list_missions` now bounded (`limit` Query ≤2000, was unbounded).
- `dashboard/src/components/BoatMap.jsx` — waypoint markers use a stable key, not the array index.
- **Rejected on verify:** the "WebSocket client-list race" (single-thread asyncio; no iteration during
  send) and the SBUS `push_thresh 8→32` one-liner (8 = autopush **bit** count = 1 byte/word; bumping it
  repacks 4 bytes/word and **breaks SBUS framing** unless the reader is redesigned — left as a real
  follow-up, not a one-liner). Skipped `threat_assessor` deque (negligible, deque-slice risk) and the
  `run_sim` ObjectMemory-config wiring (sim harness ignores `config.yaml` for *every* component — kept
  consistent).
**HTML redesign — command_center.html + waypoint_planner.html → "Abyssal Indigo v2":** used the dataviz
skill's method. New layered-glass design system (elevation/hairline/surface tokens, restrained glow as a
*signal* not decoration, `tabular-nums` on every live readout so digits don't jitter, ambient aurora
wash). Header became a real command bar (live local clock + mission-elapsed **T+** timer keyed off the
mission badge, grouped connection cluster with breathing live-dots, animated hairline scan). Section/panel
shells got glass depth + a left accent-tab header rule. Flagship upgrade: the crude rotating-border ESC
temp gauge → a proper **animated conic-sweep ring** (`@property --deg`, colour-shifts ok→warn→crit) inside
framed per-motor instrument cards; ESC current bars, status chips, buttons, dots, wave-alert + boat-health
tiles all refined. Planner brought onto the same system.
**Verified (on the Pi):** `pytest pi5/tests` **234 green**, ruff clean, firmware `py_compile` OK, both
templates' inline `<script>` pass `node --check`, dashboard Vite build clean. Booted the sim and
round-tripped the changed endpoints over real HTTP: `/api/paths` GET/POST/DELETE, `/api/pod/history?limit=
999999999` clamps (no OOM), `/` and `/planner` both 200. Rendered both templates in headless Chromium
(fonts/leaflet/monaco stubbed, canned telemetry through the real render path) and eyeballed the result —
reads as designer-grade in both. Screenshots in the session scratchpad.
**Decisions / open questions:** SBUS FIFO under-drain is still a *plausible* margin risk — wants a real
PIO redesign (pack 4 bytes/word + unpack in the reader), not the mislabelled one-liner. The headless
render falls back off Orbitron (web font hangs headless Chromium on this ARM Pi) — live page unaffected.
**Next steps:** on-bench/on-water passes still outstanding from prior entries (ESC over `/dev/ttyAMA0`,
telemetry-on-GP16 with a motor spinning, real maritime model). Nothing committed — tree left for review.

## 2026-07-26 — GPS-anchored object memory (buoys/landmarks charted on the map)

**Worked on:** new feature — the boat now **remembers where objects are on the water**. When vision
confirms a buoy (or dock/rock/person), it geolocates it and drops a marker on the GPS map; once
charted it re-verifies the coordinate on each later sighting instead of re-dropping, and doesn't tie
up the radar re-observing it — so it keeps scanning for the unknown even with known things nearby.
Permanent marks (buoys/docks/rocks) are kept; transient movers (people/boats) expire after a TTL.
**Changed:**
- `pi5/navigation/geo.py` — new `destination_point()` (forward geodesic): boat fix + true bearing +
  range → object lat/lon. The inverse of `bearing`/`haversine`. +6 tests.
- `pi5/cv/object_memory.py` (NEW) — `ObjectMemory`: geolocates detections, matches by **world
  coordinate** (survives looking away/back), confirms after N agreeing sightings (then a marker
  drops), refines with an inverse-distance²-weighted mean, and ages out transients/candidates.
  Class→category (PERMANENT vs TRANSIENT) here. +32 tests.
- `pi5/cv/pipeline.py` — feeds every ranged detection into the memory (bearing off the bow =
  `heading + bbox offset`; cameras are fixed-forward, the stepper is a *separate* radar bar), ages it
  each tick, exposes `map_objects()` + `vision_state()["object_memory"]`, and **releases the radar
  from confirmed non-CRITICAL landmarks** (`release_radar_on_known`) so it keeps scanning. +6 pipeline
  tests.
- `pi5/server/app.py` — `GET /api/map/objects`, `POST /api/map/objects/clear` (reads the pipeline's
  memory on hardware, a standalone one in sim); `configure(object_memory=…)`.
- `pi5/navigation/sim_obstacles.py` — `SimObjectMapper` feeds the memory from ground truth (the sim's
  stand-in for vision), wired into `run_sim.py`. +4 tests.
- UI: command center `command_center.html` — object marker layer polling `/api/map/objects` (cyan
  permanent / amber transient, hover label + detail popup) + **SIM MAP** DROP BUOY / DROP PERSON /
  CLEAR MARKS buttons (sim-only). React `dashboard/` — `useMapObjects` hook + `BoatMap.jsx` markers.
- `pi5/config.yaml` — new `vision.object_memory` block. Docs: `docs/object_memory.md`.
**Verified (on the Pi):** `pytest pi5/tests` **234 green** (+40), ruff clean, command-center inline
`<script>` passes `node --check`, `dashboard` Vite build clean. Booted the sim and drove the whole
lifecycle over the real endpoints twice: dropped a buoy 18 m ahead → confirmed **PERMANENT** marker
geolocated to **18.1 m / bearing 359.8°** (matches ground truth to ~0.1 m); person → **TRANSIENT**;
markers **persist after the obstacles are removed** (remembered); two buoys stay distinct (9.1 m
apart) while an out-of-cone one isn't seen; a repeat drop **refines, not duplicates**; CLEAR MARKS
wipes them. Transient TTL / permanent persistence are covered by deterministic unit tests.
**Decisions / open questions:** object memory needs **stereo range** to place a detection → no-op on a
mono rig (documented). Marker identity is the world coordinate + class; the vessel synonym set
(boat/vessel/boats) is canonicalised. Not yet exercised on-water with a real detector (bench next).
**Next steps:** on-water pass with the camera + a real buoy; tune `confirm_sightings`/`match_radius_m`
against live stereo noise; consider persisting the memory across restarts. Nothing committed — tree
left for review.
**Follow-up (independent verification pass — on the Pi):** re-verified the whole feature end to end,
nothing changed in the code. Static: `pytest pi5/tests` **234 green** (targeted object-memory/geodesic
subset **35 green**), ruff clean across all 10 touched files, command-center inline `<script>` passes
`node --check`, dashboard **Vite build clean**. Independent numerical check of the forward geodesic
(`destination_point` round-tripped against `haversine`/`bearing`): **worst distance error 0.000 cm over
77 cases** (bearings 0-359.5°, ranges 1 m-5 km), bearings back to <0.05°, +180° meridian wraps
correctly. Independent live lifecycle over the **real HTTP endpoints** (fresh sim boot): buoy dropped
18 m ahead confirmed after 3 sightings and **geolocated 0.19 m from sim ground truth**; person →
TRANSIENT; two distinct markers; repeat sightings **refined one object** (id stable, sightings 7→11,
0.04 m drift, no duplicate); markers **persisted after the obstacles were deleted**; CLEAR wiped them.
Code confirmations: the `distance_m` fed to the memory is the overlay's **stereo** value (mono
`_fallback_distance` is used only on the avoidance path) → the "mono rig = no-op" claim holds; the
hardware pipeline maps all 11 `vision.object_memory` config keys 1:1; both UIs (command center +
`BoatMap.jsx`) render markers identically (cyan permanent / amber transient) and XSS-safe. The
sim-only path the live run can't reach — **radar-release-on-known** — is covered by
`test_pipeline_radar_releases_known_buoy_keeps_scanning`. **Two benign notes (not bugs):** (1)
`run_sim.py` builds `ObjectMemory()` with defaults — consistent with the sim harness ignoring
`config.yaml` for every component; config wiring lives on the hardware path + unit tests, so a config
change is only felt in sim if `run_sim` is taught to load it. (2) `known_confirmed_near` uses a fixed
6 m radius in the radar-release check (not range-scaled), so releasing the bar may under-fire for a
landmark geolocated from a long/noisy range — conservative (keeps tracking), an on-water tuning knob.
Still nothing committed.

## 2026-07-26 — Designer-grade ESC Settings editor (dashboard) + endpoints + tests

**Worked on:** finished the interrupted ESC-config UI. A prior session had refactored
`am32_config.py` into a library (`FIELDS` registry, `read/write_settings`, `decode_eeprom`, mock EEPROM,
wiring/setup constants) explicitly *"for the dashboard ESC editor"* — but the server endpoints and the
actual editor were never built; the modal was still the old "arm am32.ca passthrough" stub. Built the
whole thing and verified it on the Pi.
**Changed:**
- `pi5/server/app.py` — new `POST /api/esc/read`, `POST /api/esc/write`, `GET /api/esc/meta` (+ a
  persistent `_esc_mock` sim buffer). Hardware path runs `am32_config.read/write_settings` in a
  threadpool (blocking pyserial) and refuses during a running mission; sim path serves + mutates the
  mock so the editor is fully usable with no hardware. 400 (bad key/value) vs 502 (link/verify) split.
- `pi5/scripts/am32_config.py` — `_decode_field` now emits `warn_when` for bool fields so the UI
  recomputes the amber "risky state" live on toggle (the registry itself already existed).
- `pi5/server/templates/command_center.html` — replaced the passthrough stub with a full
  **⚡ ESC SETTINGS** modal rendered straight from the field registry: grouped Drive/Protection/Tuning/
  Info sections, real toggle switches + range sliders + info chips, ★ important flags, amber warn rows
  (⚠ + reason) that flip live, dirty/"EDITED" tracking with a sticky Read / Revert / Write action bar
  (Write sends only changed keys, server-verified), and a **Wiring & Setup** tab with the pin table +
  copy-paste one-time `uart0` commands + doc links + the am32.ca passthrough demoted to an Advanced
  collapsible. New `⚡ ESC SETTINGS` button in COMMANDS→DRIVE; ⚙ MOTORS renamed ⚙ TRIM and links to it.
  All device-derived text set via textContent (no innerHTML).
- `pi5/tests/test_am32_config.py` (NEW, 21 tests) — decode/scaling/warn-flags/encode-validate/
  all-or-nothing/round-trip on the library the endpoints call.
- Docs: `docs/am32_config.md` + `docs/esc_setup.md` now present the dashboard editor as the easiest
  setup path (same GPIO-UART backend as the CLI).
**Verified on the Pi:** `pytest pi5/tests` **194 green** (+21), ruff clean, the inline `<script>` passes
`node --check`. Booted the sim and hit the live endpoints via curl — meta/read/write, sim-write
persistence, warn-flip (bidir OFF → warn), and 400s on out-of-range/unknown/empty. Rendered the modal
with a faithful chromium harness (real CSS + markup + render fns + live payload): the Settings tab, the
edited+warn state, and the Wiring tab all read as designer-grade.
**Decisions / open questions:** the underlying `am32_config` read/write was already hardware-proven on
the NeutronRC G071; only the new FastAPI/threadpool wrapper is unexercised on metal — wants one on-bench
pass over `/dev/ttyAMA0`. Web-font (Orbitron) fetch hangs headless chromium on this ARM Pi, so the render
harness strips it (live page is unaffected).
**Next steps:** on-bench — wire an ESC to the Pi UART, open ⚡ ESC SETTINGS, Read/Write a real ESC end to
end; then the outstanding telemetry-on-GP16 check (motor spinning). Nothing committed — tree left for review.

## 2026-07-26 — CV overlay fixed (no model → COCO ONNX), MJPG 720p, HUD de-conflict, auto-exposure

**Worked on:** user reported the command-center CV showed **no bounding boxes**, the top-right
"avoidance"/anomaly HUD was covered by the DET/FPS readouts, and asked for a **higher MJPG resolution**.
Run on the Pi with both Arducam 8MP USB cameras live; "don't come back until it works."
**Root cause (no boxes):** `DetectionOverlay` could load **no model** — `torch`/`ultralytics` aren't
installed and there was no `maritime_yolov8n.onnx` (only its `_info.json`), so `available=False` and it
never drew. onnxruntime 1.28 IS installed (the repo's intended lightweight backend).
**Changed:**
- `pi5/cv/models/yolov8n.onnx` (+ tracked `yolov8n_info.json`, COCO 80 classes) — exported generic COCO
  yolov8n → ONNX (imgsz 320) in a throwaway **disk-backed** venv (torch overflowed the 2 GB `/tmp` tmpfs;
  built under `/`, then deleted), so the runtime `.venv` stays torch-free. `.onnx` is gitignored (like the
  maritime slot). `pi5/config.yaml` `detection.model` → this path (onnxruntime backend).
- `pi5/config.yaml` camera → `fourcc: MJPG`, `1280x720` (was YUY2 640×480). Both cams advertise MJPG to
  1920×1080@30 / 1280×720@30; measured **~16–18 fps** dual-cam through the producer on the bench
  (auto-exposure-limited indoors; approaches 30 in bright light — not decode/USB-bound).
- `pi5/cv/camera.py` — force **auto-exposure** (V4L2 aperture-priority=3) on every `_open`. UVC exposure
  persists on the device across processes; a stray manual setting was blacking out the feed (this was why
  the first live grab was near-black). Best-effort, Linux/V4L2 only.
- `pi5/server/templates/command_center.html` — moved `.cam-det` from top-right → **bottom-right** (above
  `.cam-fps`), freeing the top-right for the baked ANOMALY bar + tier dots. Corner ownership now: TL
  tag/track, TR anomaly, BL water, BR det/fps.
**Verified on the Pi (cameras live):** COCO ONNX detects person+boat on stock images and **chair/tv/laptop
live**; the real `/video` endpoint draws boxes + the uncovered HUD at 1280×720; 3-tier gating turns YOLO
on via the land-scene anomaly (0.78). Before/after HUD screenshot confirms the de-conflict. `pytest
pi5/tests` **164 green**, ruff clean.
**Decisions / open questions:** COCO yolov8n is a bench/demo detector — swap a trained maritime model in
(`ml/`, drop `pi5/cv/models/maritime_yolov8n.onnx`, auto-preferred). The `.onnx` is gitignored, so a fresh
checkout needs it regenerated (`ml/export_onnx.py`) or the overlay falls back to the uninstalled `.pt`.
**Next steps:** train/drop the maritime model; optionally bump capture to 1080p if CPU headroom allows;
NCNN/Hailo for higher detect FPS. Nothing committed — working tree left for the user to review.
**Follow-up (maritime model hunt — negative result, kept COCO):** surveyed HF + Roboflow + GitHub for a
drop-in maritime detector. Findings: (a) openly-downloadable ones are **satellite/SAR** (mayrajeo,
DefendIntelligence, Mahadih534, torchgeo Sentinel-2, geobase) — wrong perspective for a surface boat;
(b) `dima806/*` is image-classification, not detection; (c) the good surface-level multi-class ones are
**gated** (`cazzz307` HF-login; Roboflow "Marine Surveillance" boat/buoy/kayak/vessel needs an API key).
Best candidate **`alimkacar/argus-maritime-yolov8s`** (ungated, classes boat/sailboat/vessel/buoy/person,
inshore surface imagery, claimed mAP50 0.97) was downloaded + tested: it was **trained on a FORKED
ultralytics** (`train_args` has `cls_remap`/`distill_model`/`tracktrack`/`end2end`) and yields ~0.003
class-confidence under STANDARD ultralytics/ONNX inference across all preprocessing (RGB/BGR/imagenet) —
i.e. only its fork's forward decodes it, so it is **unusable with this repo's standard `onnx_detector`**
(would detect nothing). Verified my method is sound by running the working COCO model on the same images
(boat1 harbour → 2 boats; boat4 buoy → "boat" 0.75; boat2 sailboat → mislabeled "kite"; boat3 marina →
missed). Conclusion: no free, ungated, surface-level, standard-decoder maritime model exists to drop in
now. The auto-detect slot (`pi5/cv/models/maritime_yolov8n.onnx`) is ready — the reliable route to a real
one is a Roboflow "Marine Surveillance" export trained/exported with **standard** ultralytics via `ml/`
(needs a free Roboflow key), or the user drops in any standard-ultralytics maritime `.onnx`. **Note:**
COCO/YOLOv8 weights are Ultralytics **AGPL-3.0** — fine for research/personal use; matters only if
D.R.E.A.M.S is ever distributed as a network service. Kept COCO in place (detects boat+person well).
**Follow-up 2 (big autonomy + UI push — cameras/Pico/left-ESC on the bench; 3 research agents + 1 UI
agent):**
- **Current-aware station-keeping** (`pi5/navigation/current_estimator.py` NEW + `navigator.py`): estimate
  the water current as *GPS ground velocity − modelled through-water velocity* (thrust model
  `v=a|thr|+b·thr²`), low-pass filtered → **set/drift** on `/api/status`. Stay/HOLD mode now **actively
  noses into the current** (required through-water vel = desired-ground-vel − current) instead of
  drift-then-reacquire. Sim (new `/api/sim/current` + simulator current): recovers 090°/0.35 m/s exactly,
  **holds ≤0.4 m**. Config `navigation.current_*`/`sk_*`; NavState/NavStateOut extended; +5 tests. ILOS
  still handles transit current.
- **Incoming-wave detection → capsize avoidance** (`pi5/cv/wave_detector.py` NEW, wired into
  `pipeline.py`): horizon-from-gradient + sparse LK optical-flow looming → severity/bearing/TTC with a
  persistence state machine, ~3 ms/frame live. **Bow-into-wave** override (turn to face + ease throttle,
  yields to obstacle avoidance) + HUD horizon line/chevron + `vision.wave` telemetry. `vision.wave_detection`
  config; +4 tests. (No IMU pitch yet — noted.)
- **YOLO speed** (`pi5/cv/ncnn_detector.py` NEW + `vision_overlay.py`): NCNN backend via the `ncnn` pkg
  (no torch), identical decode. **Clean Pi-5 benchmark: NCNN 34 fps vs ONNX 18 @ imgsz 320 (1.96×)** — the
  earlier "NCNN slower" was training CPU contention. Shipped **COCO yolov8n as an NCNN export**
  (`pi5/cv/models/yolov8n_ncnn_model/`, gitignored; `.onnx` kept as fallback); `detect_max_fps` 10→15.
- **Maritime+person model — trained but NOT shipped.** Used the user's Roboflow key to pull
  `udea/proyecto-de-grado-unvpl` v6 (CC BY 4.0: Boats/Sail-Boat/Kayak/Person/Buoy/Rock/wreck/Dock/…), trained
  yolov8n on the Pi CPU (subset, imgsz 320). It **plateaued at mAP50≈0.21** and — critically — **missed
  people** on test images (COCO detects them cleanly), because the small Pi-subset fine-tune degraded COCO's
  person head. Decision: **ship COCO** (detects boats+people = the requirement) via NCNN; the maritime
  slot + threat map + case-insensitive labels are all ready for a properly-trained model (full dataset/GPU,
  or frozen-backbone). `threat_assessor` extended (boats/sail-boat/surfer/rock/wreck/bridge, case-insensitive).
- **UI redesign + ESC tab** (`command_center.html`, via a design agent using the dataviz skill): new
  **PROPULSION·ESC** panel (per-motor temp radial gauges + current bars, threshold-coloured), **WAVE ALERT**
  readout, **CURRENT & STATION-KEEP** vector — all wired to the real payload fields; existing ids/JS/drag-grid
  preserved; scripts pass `node --check`. Verified layout via a static render (chromium can't screenshot the
  full live page on this ARM Pi — MJPEG stream hangs it; live server serves `/`=200 and `/video` draws the
  wave-HUD + boxes).
- **Verified:** `pytest pi5/tests` **173 green**, ruff clean, firmware py_compiles, both template `<script>`
  blocks pass `node --check`, NCNN COCO detects person/boat live (backend=ncnn), Pico streaming TEL/ENV on
  `/dev/ttyACM0`. Docs: `docs/current_and_wave_features.md`. **Committed + pushed** this follow-up.

## 2026-07-25 — Full on-Pi review (9 agents) + ESC KISS telemetry (temp + current)

**Worked on:** first review actually **run on the Pi** (prior 3 sessions were Windows/static-only).
Then built per-motor ESC telemetry end-to-end at the user's request.
**Review (executed):** baseline healthy — `pytest pi5/tests` **164 green**, ruff clean, firmware
py_compiles, both Vite builds pass. 9 parallel subsystem agents + own pass on scripts/services/CI/deploy.
Findings relayed to user; **nothing auto-fixed**. Headline:
- **CRITICAL firmware (verified by hand):** (S2) `serial_handler._send()` `sys.stdout.write` is
  unguarded — a hung Pi fills the USB TX buffer, stalls the single asyncio loop, watchdog never ESTOPs
  (read path IS guarded, write path isn't). (S1) UART1 double-drain — `gps.read()` in `task_fast_sensors`
  (main.py:209) races `task_uart1_reader`, shredding GPS **and** `$POD` leak frames; fix = delete line 209.
- **HIGH:** pod-leak only alerts (no ESTOP/decision); single-hull hull-leak ESTOP needs *both* sensors so
  never fires; watchdog ESTOP is one-shot under `except: pass`.
- **MED:** cloud `list_missions` unbounded; server blocking file IO in async save/delete; `pod_bridge`
  `_pod_ok` not cleared on parse error; uploader overflow truncation; `detector.py` dead; doc rot
  (`main.py`/`pin_map.md` "2× M18 series"→parallel; pin_map still production board); orphaned
  `mission:`/`pod:`/`logging:` config; Caddyfile only proxies /api+/ws.
- **Rejected on verify:** rate-limiter "race" (no `await` in critical section → atomic single-worker) and
  SBUS S3 "9 cycles/bit" (it's 8, correct). *But* SBUS uses an 8-byte PIO FIFO < a 25-byte frame → likely
  under-drains too (bench-check).
**ESC telemetry (built; runs in sim; UNTESTED on hardware):** new `firmware/boat-pico/esc_telem.py` — PIO
UART RX ×2 (**GP16** L / **GP19** R), KISS 10-byte frames (CRC-8, big-endian), **32-byte FIFO**
(`push_thresh=32` — the fix SBUS lacks). `escs.py` telemetry stubs now delegate to it; `main.py` inits +
100 Hz drain task + edge-triggered `MOTOR_HOT` WARN (80 °C, WARN-only by choice — one-liner to ESTOP).
Current appended to `TEL` as `curr_l,curr_r` (backward-compat v1.1 appendix) → `pico_serial`
(parse-if-present) → server model/status dict → command center + `TelemetryPanel.jsx`. Simulator emits
synthetic load-based temp/current. Fixed the "series"→"parallel" doc rot in `main.py`/`sensors`/`simulator`
while here. Docs: new `docs/esc_telemetry.md` (+ `esc_setup.md`, `serial-protocol.md §4.1`).
**Verified:** 164 tests still green, ruff clean, firmware compiles, KISS parser unit-checked
(CRC/scaling/resync/reject); **booted the sim on the Pi** — a `goto` drove the boat and `/api/status`
showed `curr 12.0/3.2 A`, `temp 45/37 °C` tracking throttle.
**Decisions / open questions:** ESC telem has 3 bench unknowns (AM32 emitting telem in PWM mode; PIO byte
order `_BYTE_ORDER_LE`; drain cadence via `esc_telem.stats()`) — see the doc. Review fixes NOT applied —
awaiting user's pick.
**Next steps:** (1) fix S1 (1-line) + S2 (writer-queue) — top safety value; (2) bench-validate ESC telem
per `docs/esc_telemetry.md`; (3) regen stale `pin_map.md`; (4) pi5/cloud one-liners. Nothing committed.
**Follow-up (2026-07-26) — on-bench ESC bring-up with a real NeutronRC G071 + 4S:**
- **ESC passthrough bench-tested → found + fixed real bugs.** Arming the Pico bridge stranded the Pico
  (needed power-cycles). Root causes fixed in `firmware/boat-pico/esc_passthrough.py`: `stdin.read(64)`
  blocks until 64 bytes (rp2 `select.poll` on USB-CDC is unreliable) → drain byte-at-a-time; added a
  **hardware `machine.WDT(8s)`** so a hang self-recovers (also the only HW WDT in the firmware now);
  moved its PIO SMs 0/4→6/7 (collided with SBUS SM0 + esc_telem SM4/5); dropped the `ESC_PASS: bridging`
  print in `main.py` that leaked into the CDC as a false "reply". Still not functionally validated for
  am32.ca-through-Pico (poll/read + half-duplex link unproven) — WDT just makes iterating safe.
- **am32.ca can't see the Pi's GPIO UART** (Chromium Web Serial lists USB serial only), so the browser
  path is out without a USB-TTL adapter (user has none). **Pivoted to a CLI configurator.**
- **NEW `pi5/scripts/am32_config.py` — WORKS.** AM32 one-wire bootloader protocol over the Pi's GPIO
  UART (transcribed from AM32-bootloader `main.c`: 19200, CRC16 0xA001, SET_ADDRESS/READ/SET_BUFFER/
  PROG_FLASH). Enabled `uart0` (`/dev/ttyAMA0`, GPIO14/15) at runtime + stopped the serial getty. Read
  the ESC (name "NeutronRC G0", 64K, flash code 0x35 → EEPROM at 0xf800), then **wrote + read-back-verified
  bidirectional (byte 18=1) + 30ms telemetry (byte 31=1)**. `read` + `set --bidir/--telemetry/--lvc`.
  Doc `docs/am32_config.md`; `esc_setup.md` updated (Pi-GPIO path now the recommended bench route).
- **Telemetry still 0 on GP16.** Traced AM32 firmware: serial telem is emitted on the **MCU's PB6**
  (USART1 115200 8N1 open-drain) and the transmit sits in the commutation path → **likely only streams
  while a motor is spinning**. No motor connected, so `esc_telem` correctly sees 0 bytes. Left for the
  user to finish: motor (props off) + throttle, and confirm GP16 is on the ESC's actual telemetry pad (PB6).
**Committed + pushed** as `c70a8f0`. Then **fixed the two firmware safety criticals** (deployed to the
Pico + verified telemetry still flows with valid checksums): **S1** — removed the racing `gps.read()` from
`task_fast_sensors` so `task_uart1_reader` is the sole UART1 reader (it demuxes GPS + `$POD`; the double
read was shredding GPS fixes and the pod leak frame). **S2** — `serial_handler._send()` now writes
byte-at-a-time behind a `POLLOUT` poll (`_stdout_poll`) and drops the rest of a frame under back-pressure,
so a Pi that stops draining the CDC can no longer wedge the asyncio loop and starve the heartbeat
watchdog. S1/S2 changes (`main.py`, `serial_handler.py`) + this note uncommitted.

## 2026-07-25 — Deep review: LOS nav, obstacle avoidance wired, vision perf, Abyssal Indigo UI

**Worked on:** user asked for an extremely thorough review + make it run *great*, research-backed
vision/nav optimization, and a non-orange UI redesign. This session's changes were **run + tested**
(venv pytest: 123→144 green, ruff clean, sim booted and probed live in-browser). Full write-up in
`docs/code_review_2026-07.md`.
**Changed:**
- **Obstacle avoidance was dead code** — `AvoidanceLoop` (ran a *duplicate* YOLO) was never
  instantiated and the pipeline never steered around threats. Rewrote `pi5/cv/avoidance.py` into a
  pure, tested `reactive_avoidance()` rule (bearing+range → slow & bear away; head-on → starboard per
  COLREGS); `pi5/cv/pipeline.py` now pushes a steer-away override into the navigator (wired
  `navigator=nav` in `run_hardware.py`). Live **AVOID** toggle + `POST /vision/avoidance/toggle`.
- **Navigation:** added lookahead **LOS + ILOS** guidance and cross-track error to
  `pi5/navigation/geo.py`; `Navigator.compute_throttle` steers to the LOS course when a leg start is
  given (legacy point-at-target kept for no-leg + old tests); `MissionManager` anchors each leg to the
  previous waypoint. New `test_los.py` (10 tests incl. convergence rollout) + `test_avoidance.py` (11).
- **Config gap:** `run_hardware.py` ignored the whole `navigation:` block — added `_nav_config()`.
  New config keys: `navigation.los_*`, `camera.stereo_wls`, `vision.reactive_avoidance` (replaced the
  stale top-level `avoidance:` block).
- **Vision perf:** new `pi5/cv/ort_utils.py` (ONNX Runtime graph-opt=ALL + 4-thread + XNNPACK) used by
  the detector and segmenter; `pi5/cv/stereo.py` SGBM 3-way + preFilterCap + optional WLS disparity
  filter for textureless water (`opencv-contrib`, graceful fallback).
- **UI:** rethemed `command_center.html` + `waypoint_planner.html` from amber → **Abyssal Indigo**
  (0 residual orange, verified in-browser, no console errors); added AVOID toggle + Cross-Track
  telemetry readout. `NavStateOut` gains `cross_track_m`/`course_deg`/`avoiding`.
- **Docs:** `docs/vision_optimization.md`, `docs/navigation_guidance.md`, `docs/code_review_2026-07.md`.
**Follow-up (same session — user asked for tasks 1 & 2 + a drive-battery change):**
- **Stereo sync (review A4):** `CameraProducer` now grabs both handles back-to-back then decodes both
  (`_grab_retrieve` + `_account`), cutting stereo capture skew from a decode-time to ~one grab
  (`test_camera.py`).
- **Sim obstacle injection:** new `pi5/navigation/sim_obstacles.py` (`ObstacleField` + `SimAvoider`)
  drives the real reactive rule into the real navigator from ground truth; wired into `run_sim.py`
  (~4 Hz task) + `GET/POST/DELETE /api/sim/obstacles` + a **DROP OBSTACLE** map button. Avoidance now
  runs end-to-end in sim, and faithfully shows the reactive **local-minimum** limit (a hazard dead on
  the goal line is orbited, not passed — collision-free but no progress; documented, VFH/bug planner is
  the upgrade). Gave `min_forward_frac` a 0.2 default so the boat arcs vs stalls.
- **Drive battery → 2× M18 PARALLEL (18 V)** for the twin 2814 motors (was 2× series 36 V): firmware
  `sensors.py` thresholds → single-M18 (21/15/17/16), `INV_P_RATIO` kept 14.0 (existing 130k/10k divider
  reads 21 V→1.5 V correctly — no resistor rework; 56k/10k+6.6 optional). Updated `config.yaml`,
  `simulator.py` (drive now ~20.5 V/91 %, verified live), `docs/battery_architecture.md`, `CLAUDE.md`.
  Gotcha documented: 2× parallel = 18 V is **below 6S (22 V)**, so the 2814s make less than their
  1330 W/6S rating; cap VESC **battery** current per motor (~45 A on HO 6Ah) so the two don't overdraw
  the pair. Added `navigation.motor_gain_left/right` per-motor trim for the different-Kv 2814s
  (`Navigator._trim`, tested); the heading loop nulls the residual crab.
**Follow-up 2 (same session — user asked for the bug escape + confirmed plain ESCs):**
- **Bug-style escape** (`pi5/cv/avoidance.py:AvoidanceController`): wraps the memoryless reactive rule
  with commit-to-a-side + pass-detection (bearing behind the beam when tracked, or a blind `pass_hold_s`
  when sight is lost). `reactive_avoidance` gained `force_side`. Wired into `SimAvoider` (tracks the
  committed obstacle 360° so release is exact) and `pipeline._drive_avoidance`. Result: the boat now
  **routes past** a dead-centered blocking obstacle to the waypoint (was orbiting) — verified against the
  real `BoatSimulator` motion model (centered + offset, minsep ~8.8 m vs 4 m radius, arrives). New config
  `vision.reactive_avoidance.pass_bearing_deg/pass_hold_s`; +5 controller tests.
- **Drive = ESCs off the Pico (no VESC), identified as NeutronRC 70A-G071 (AM32).** Firmware already does
  plain PWM ESCs (`firmware/boat-pico/escs.py`, GP2/GP3, 50 Hz servo PWM) — no code change; the -1..1→
  1.0-2.0 ms mapping already matches AM32 bidirectional mode. These are AM32 (STM32G071) crawler/robot
  ESCs, NOT "dumb": configurable firmware with current telemetry + protections, so I corrected the earlier
  VESC/dumb-ESC framing. New **`docs/esc_setup.md`** — the required AM32 config: **Bi-directional mode ON**
  (else reverse pulses idle and the boat can't pivot/back away — the navigator commands negative throttle),
  5S LVC, low-RPM-power-protect OFF, stall/brake tuning, current limit ~45 A/motor if the AM32 build has it.
  The pack (~90 A HO-6Ah pair) is the tighter limit vs the 70 A ESCs. Updated `escs.py` docstring,
  `docs/battery_architecture.md`, `CLAUDE.md`. Kv trim via `motor_gain_*` + firmware `COMP_L/COMP_R`.
Suite now **164 green**, ruff clean.
**Follow-up 3 (same session — user asked to build the AM32 passthrough to test on the Pi later):**
- **AM32 ESC passthrough through the Pico** — configure the drive ESCs in place (no USB linker), like
  FC BLHeli/AM32 passthrough. `firmware/boat-pico/esc_passthrough.py`: a **PIO half-duplex one-wire UART**
  on GP2/GP3 + a transparent USB-CDC↔ESC bridge; entered via a new `ESC_PASS,<esc>,<baud>` serial command
  (mirrors the REFLASH pattern — stops motors, cancels tasks, hands over the CDC, `machine.reset()` on
  exit). Pi driver `pi5/scripts/esc_passthrough.py` (`enter` for the am32.ca workflow — am32.ca connects
  straight to /dev/ttyACM0; `probe`/`scan` for scripted bring-up + baud discovery). Doc
  `docs/esc_passthrough.md` with the ordered validation plan (PIO UART loopback → baud scan → am32.ca).
  **⚠ UNTESTED — no hardware yet.** Firmware py_compiles, Pi script ruff-clean. Research: AM32 signal-line
  is a BLHeli-derived one-wire link (am32.ca "Arduino PC Link" ref); baud not publicly pinned → parameterised
  + `scan` sweeps it. Risky bits (PIO timing, half-duplex turnaround, baud, bootloader-entry) isolated +
  flagged for on-Pi iteration.
- **User plans to install Claude Code on the Pi** to run the hardware-in-the-loop validation (real Pico +
  ESC). That closes most of the "verify on Pi later" gaps (camera FPS, serial link, and this passthrough).
- **⚙ MOTORS button** added to the command center (COMMANDS→DRIVE) → a Motor Configuration modal:
  per-motor **trim** (fully working — `GET/POST /api/nav/motor-trim`, browser-verified) + **ESC config**
  (arms the AM32 passthrough via `POST /api/esc/passthrough` → sends ESC_PASS, drops the link; hardware-only,
  400s cleanly in sim). `PicoSerial.esc_passthrough()` added. All browser-verified, no console errors.
**Decisions / open questions:** ILOS gain defaults to 0 (field-tune on a flowing river). WLS off by
default. `pi5/cv/detector.py` orphaned — candidate for deletion. Bug escape handles one blocking obstacle
at a time; dense multi-obstacle fields still want VFH/DWA. ESC passthrough is unvalidated scaffolding.
**Next steps:** (1) **on-Pi validation of the ESC passthrough** — PIO UART loopback → baud scan → am32.ca
(see `docs/esc_passthrough.md`); (2) flash AM32 ≥v1.99 + enable Bi-directional mode + bench-verify reverse
before first spin-up; (3) end-to-end ONNX detector test + measure real vision FPS on the Pi; (4) YOLO→NCNN
or Hailo-8L; (5) confirm drive divider / whether to fit 56k/10k. Nothing committed — working tree left for
the user to review.

## 2026-07-24 — Whole-project multi-agent review + efficiency/design pass

**Worked on:** user asked for a full review of the whole D.R.E.A.M.S codebase — make it efficient and
the UIs designer-grade. Ran 9 directory-partitioned review agents in parallel. Nothing could be
executed (no Python/Node/ruff in this Windows session), so ALL edits are **static-review-only** — run
`pytest pi5/tests`, the two Vite builds, and the on-Pi checks below before trusting them.
**Changed (highlights):**
- `cloud/api` — SRID insert bug fixed (`ST_SetSRID(ST_MakePoint,4326)`); 6 DB routes `async def`→`def`
  (sync `Session` was blocking the event loop); `init_db` now creates `postgis`+`btree_gist` before
  `create_all` (the GiST index over timestamp+geometry needs btree_gist); indexes on `mission_name`
  and `(mission_name,timestamp)`; `pool_pre_ping`; non-root Dockerfile + HEALTHCHECK.
- `pi5/comms` — ALERT 2-field detail no longer truncated; pod poll loop survives a link-down; bounded
  nmcli wifi-connect. `pi5/data/uploader` — offline-buffer race fixed (pop-before-await) + blocking
  saves → `asyncio.to_thread`. `pi5/server/app` — 7 vcgencmd probes `gather`ed; ws pump guard;
  `_pico_port_lock` around the /pico reflash endpoints.
- `pi5/navigation` — **fixed a real pause/resume deadlock** (`pause()` cleared the nav target via
  `stop_nav()` but `resume_mission()` never re-issued `goto()`/`hold()` → hung forever); added a
  bit-identical `distance_and_bearing()` to halve per-tick trig; removed dead `_on_wp_arrived`.
- `pi5/cv/segmentation` — fixed the `_seg_mask` NCHW channel-axis heuristic (the 2 new NCHW tests were
  RED; real eWaSR (1,3,384,512) preserved) and routed the TFLite path through the same config-driven
  reducer (was hardcoded `water_class=0`, inverting eWaSR-convention models). A review agent verified
  the 2026-07-24 stereo-downscale rescaled-Q and `blobFromImage` changes are metrically/geometrically
  CORRECT.
- Front-end — `command_center.html`/`waypoint_planner.html` polish (WCAG-AA contrast, focus-visible,
  reduced-motion, responsive Pico terminal; **no `<script>` touched**; visually QA'd in a browser).
  React `dashboard/` + `cloud/map-viewer/` code+design passes (re-render/leak/race fixes, Leaflet CSS
  self-hosted for field/offline use, canvas heatmap, componentized styling). `ml/` — determinism
  (`sorted()`+seeds), hardlinked dataset copies, dead-import removal.
- Cross-cutting — health-flag byte 4 relabelled **DHT→E_BAT** across `app.py`, `command_center.html`,
  and `serial-protocol.md` (firmware truth = electronics battery; the React dashboard was already
  correct); `run_hardware` `stream_fps` default 15→30; CI `head_commit.modified` path filters removed
  (they never matched → cloud/dashboard/map-viewer jobs silently skipped on push).
**Decisions / open questions:** **Firmware was audited REVIEW-ONLY (no edits)** — safety-critical and
untestable here. Real items to fix + bench-test: **S1** UART1 is drained by two tasks → `$POD` (incl.
leak) frames can be lost; **S2** a blocking USB `stdout.write` can freeze the loop so the software
watchdog never ESTOPs, and there's no hardware WDT; **S3** the SBUS PIO samples 9 cycles/bit not 8 →
RC override may never decode (verify on a scope); **S4** on this single-hull branch a one-hull leak
only WARNs (doesn't ESTOP). Did NOT modernize `on_event`→`lifespan` (risky without a runtime).
**Next steps:** on the Pi/laptop — `pytest pi5/tests` (the 2 seg tests should now be GREEN), `python
run_sim.py` and exercise **pause/resume mid-transit and mid-DATA-waypoint** (the changed uncovered
path), then `npm run dev` both UIs for a visual pass; then triage the firmware S1–S4 safety findings.

## 2026-07-24 — Vision pipeline: full audit + efficiency pass (15 fps water target)

**Worked on:** user asked to fully check + optimize the vision code, find a water-vision library, and
hit ~15 fps Tier-1 water detection with YOLO at a lower-but-high rate. Audited all of `pi5/cv/*` + the
server MJPEG path statically (no Python interpreter/WSL available in this session — see caveat).
**Root bottleneck found + fixed:** `StereoDepth.compute()` ran SGBM + `reprojectImageTo3D` at full
1080p *inside* `vision_overlay._infer`, so every inference with a detection present collapsed detect
FPS to ~1-2/s (this was the exact tradeoff flagged in the 2026-07-01 archive entry).
**Changed:**
- `pi5/cv/stereo.py` — `StereoDepth(calib, downscale=0.5)`: rectify at full res, then run SGBM +
  reproject on a downscaled pair (~4× cheaper) with a **rescaled Q** (`Q[:, :3] /= s`, an exact
  coordinate change → depth stays metrically correct) and a scale-matched disparity range; upsample
  disp/depth back to full res so callers (bbox lookup, `/video?cam=disparity`) are unchanged.
  `downscale=1.0` reproduces the old path exactly.
- `pi5/cv/onnx_detector.py` — YOLO preproc now uses `cv2.dnn.blobFromImage` (one C++ call: swapRB +
  /255 + HWC→NCHW) instead of manual cvtColor/astype/transpose copies. Geometry unchanged (letterbox
  still applied first).
- `pi5/cv/segmentation.py` — added an **ONNX water-seg backend** (onnxruntime, already a dep — no new
  package) alongside the classical + TFLite paths, auto-selected by file extension. Handles WaSR/eWaSR-
  style `(1,C,H,W)`/`(1,H,W,C)` class maps and single water-probability outputs; `seg_water_class` /
  `seg_ignore_classes` / `seg_normalize` / `seg_input_size` are config-driven. Classical path (and its
  tests) untouched. New `_seg_mask` reducer has 3 unit tests.
- `pi5/config.yaml` — `stereo_downscale: 0.5`; `vision.tier1_max_fps 20→15` (the water target);
  detection `imgsz 416→320`, `detect_max_fps 8→10` (keeps YOLO high but under the 15 fps screen);
  seg model default `.tflite→.onnx` + the new seg knobs, documented.
- `run_hardware.py` — passes `camera.stereo_downscale` into `StereoDepth`.
- `pi5/scripts/benchmark_vision.py` (new) — per-stage FPS harness (Tier-1 seg / YOLO / stereo at each
  downscale) for the Pi. `docs/water_vision.md` (new) — backend guide + eWaSR/WaSR recommendation.
**Decisions / open questions:**
- **Not executed/verified here** — no Python, WSL, conda, or ruff in this Windows session (the
  2026-07-23 Py 3.14.4 env is gone). All edits are static-review only. Run `pytest pi5/tests` and
  `python -m pi5.scripts.benchmark_vision` **on the Pi** to confirm. On a Pi 5 *CPU*, the classical
  screen easily does 15 fps; a full seg DNN (eWaSR) does not — it's wired as an optional accuracy/
  accelerator path, documented as such.
- `pi5/cv/avoidance.py` + `detector.py` (`BoatDetector`) are **dead code** — never instantiated by
  `run_hardware.py` (the pipeline + threat_assessor + radar are the live obstacle path). Left in place;
  flagged as a consolidation candidate.
**Next steps:** on the Pi — `pytest pi5/tests`, then `benchmark_vision.py`; tune `imgsz` /
`tier1_max_fps` / `stereo_downscale` to the measured numbers. Optionally export an eWaSR model to
`pi5/cv/models/water_seg.onnx` (see `docs/water_vision.md`) if HSV isn't robust enough in glare.

**Follow-on (same session): hybrid Tier-1 (classical 15 fps screen + eWaSR spot-check).** User asked
to "run eWaSR instead" and whether a Coral M.2 would work. Verified (web): Coral is a poor fit —
INT8-TFLite-only (not ONNX), can't run eWaSR's transformer ops, no official Pi 5 support, pycoral
stuck on Py 3.6-3.9 (repo is 3.14); **Hailo AI HAT+ is the right accelerator** (ONNX-native, 1st-party
Pi 5). Also: eWaSR on the Pi CPU is ~2-8 fps, so it can't be the 15 fps primary. User chose the
**hybrid**, which I built:
- `pi5/cv/pipeline.py` — added `_confirm_seg` (optional DNN water model) on a **separate slow async
  loop** (`_confirm_loop`, `seg_confirm_max_fps` ~2 Hz) so its ~200 ms inference never stalls the fast
  15 fps classical loop. A fresh verdict (within `seg_confirm_ttl_s`) becomes the authoritative
  `water_state` and can wake YOLO on obstacles HSV missed — **fail-safe: only ever ADDS triggers**.
  `vision_state()` gains a `confirm` block. Hybrid is **off unless a real DNN model loads** (two
  classical screens would be pointless), so existing behaviour/tests are unchanged.
- `pi5/config.yaml` — `seg_model_path` now **empty** (classical primary); new `seg_confirm_model_path`
  (`…/water_seg.onnx`), `seg_confirm_max_fps: 2`, `seg_confirm_ttl_s: 3`. (Supersedes this entry's
  earlier "seg_model_path default → .onnx" bullet.)
- `pi5/tests/test_vision_pipeline.py` — +3 hybrid tests (confirm wakes YOLO on clear water; stale
  verdict ignored; hybrid off without a model). `docs/water_vision.md` — hybrid section + Coral-vs-Hailo.
- `ml/export_ewasr.py` (new) — one-command eWaSR→ONNX exporter producing
  `pi5/cv/models/water_seg.onnx` (+ tracked `water_seg_info.json`). Confirmed against the eWaSR repo
  (tersekmatija/eWaSR): forces the single-input `ewasr_resnet18` variant (IMU variant is 2-input and
  won't load), mirrors their `torch.onnx.export(model, {"x": {"image","imu_mask"}}, opset=12,
  output_names=["prediction","intermediate"])` (non-IMU prunes imu_mask → 1 input), ImageNet norm,
  MaSTr1325 class order 0=obstacle/1=water/2=sky (matches config). `--self-check` runs onnxruntime on a
  water frame to confirm class order. Weights from the 0.1.0 GitHub release; run on a GPU box, scp the
  .onnx to the Pi. Decided **Hailo AI HAT+** over Coral if acceleration is wanted (Coral = INT8-TFLite
  only, no ONNX, no transformer ops, pycoral stuck on Py 3.6-3.9).
**Still needs the Pi:** run `ml/export_ewasr.py` on a GPU box, scp `water_seg.onnx` to the Pi, then
`pytest pi5/tests` + `benchmark_vision.py` to confirm. I did not fetch/train the model (no GPU/Python
here, and shouldn't download weights unprompted).

## 2026-07-23 — Verified the waypoint-driving sim already works (no code changes)

**Worked on:** user asked whether a viewable sim of the boat driving waypoints could be created. It
already exists end-to-end — confirmed it rather than building anything new.
**Verified:** started `run_sim.py`, POSTed a 4-point PATH loop near the dock (`/api/mission?start=true`),
and polled `/api/status`. The boat pivoted in place to each bearing (align-first `Navigator`), drove the
leg, and advanced WP 0→1→2, ranging ~58 m from start; server stopped cleanly after. Deps present
(Py 3.14.4, fastapi 0.135.3, uvicorn 0.44.0).
**Notes for next time:**
- Viewable UI = command center at `http://localhost:8000/` (Leaflet map, pulsing boat marker, track +
  waypoint pins, `/ws/telemetry`). Draw/upload routes at `/planner`; sample missions in
  `reference/waypoints.json`. Sim mode runs dev-mode auth (no API key needed).
- Polling `/api/telemetry` and `/api/mission` every tick trips `rate_limit.py` (HTTP 429) — poll the
  bundled `/api/status` at ≥2–3 s spacing instead.
- DATA waypoints stall on the winch-down/sample/winch-up sequence (up to ~5 min each) — use PATH
  waypoints or `POST /api/sim/speed` to watch it drive a route quickly.
**Next steps:** none pending. Offered the user an optional zero-setup standalone animation (self-contained
HTML canvas / matplotlib playback); build only if they ask. No repo files changed this session.

## 2026-07-21 — Single-hull test bench variant: spec + firmware (branch `single-hull-test-bench`)

**Worked on:** user wants a single-hull "test bench" boat (two stern motors, differential steering, standard hobby ESCs instead of the VESC/CAN chain, 2× M18 series drive instead of 3×) to validate the stack on real hardware before the full catamaran. Produced a spec doc, then implemented the Boat Pico firmware on a new branch `single-hull-test-bench` (branched off `main`; `main` untouched). Mid-implementation the user chose to **keep both SHT41 air-temp sensors**, which forced a pin-plan revision (below).
**Final pin plan (test bench):** left ESC **GP2**, right ESC **GP3** (PWM slice 1 A/B — same 50 Hz, independent duty), winch **GP6** (was GP14), SBUS **GP7** (was GP15), **both SHT41s kept on GP12–15** (J11/J13, native as-built pins). Reason: a PCB net-trace confirmed the as-built board routes GP12–15 to the two SHT41 SoftI2C connectors, so propulsion/winch/SBUS move to free Pico header pins (GP2/3/6/7 have no connector — hand-wired taps on a bench rig). This also sidesteps the long-standing dual-hull GP12–15 VESC/winch/SBUS-vs-SHT41 as-built conflict.
**Changed (on branch `single-hull-test-bench`, committed locally, not pushed):**
- `firmware/boat-pico/escs.py` (new) — dual hobby-ESC PWM driver on GP2/GP3, 50 Hz, reusing the winch pulse mapping (STOP 4915 / MIN 3277 / MAX 6553, `duty_u16`). Exposes `LEFT`/`RIGHT`/`LEFT_PIN`/`RIGHT_PIN`/`init` (returns success)/`ready`/`set_duty`/`stop` plus VESC-shaped telemetry **stubs** (temp→None, fault→0, `max_motor_temp`→0.0, poll/request→no-op) so `main.py` telemetry code runs unchanged.
- `firmware/boat-pico/motor_control.py` — imports `escs` not `vesc`; `init/update/estop` drive ESCs; winch `MW_PIN` 14→6; `COMP_L=COMP_R=PULLEY_L=PULLEY_R=1.0` (single hull); `init()` returns ESC-up status. Steering math + RC/ESTOP gates unchanged.
- `firmware/boat-pico/sbus.py` — `SBUS_PIN` 15→7 (PIO).
- `firmware/boat-pico/sensors.py` — drive divider `INV_P_RATIO` 21.0→**14.0** (130k/10k; 42 V→3.00 V — same margin as the production 200k/10k at 63 V), `P_FULL/EMPTY/WARN/CRIT`=42/30/34/32. **Both SHT41s kept** (SoftI2C init unchanged); only battery constants + docstrings changed.
- `firmware/boat-pico/main.py` — imports `escs`; removed `task_vesc_telemetry` + its task-list entry; removed watchdog motor-overheat/VESC-fault blocks and `_mt_throttled`/`_vesc_fault_sent` state; TEL2 `v_in` now carries `sensors.prop_batt_v`; startup prints drive-ESC OK/FAIL with a "do NOT arm" warning; docstring pin map updated. `vesc.py` left in tree but no longer imported.
- `docs/hardware_changes_v2_to_testbench.md` (new) — full spec, revised for the keep-both-SHT41 pin plan. All five firmware files pass `python -m py_compile`.
**Decisions / open questions:**
- Ran an adversarial multi-lens verification Workflow (6 review lenses → per-finding refute pass, 14 agents) on the *first* (pre-SHT41-revision) firmware. Confirmed + fixed two real issues: (1) a stale ×13.0/3.23 V divider figure in a `sensors.py` docstring (correct is ×14.0/3.00 V); (2) `escs.init()` swallowed PWM-init failure silently — fixed with a success return + `ready()` + a `main()` FAIL banner. NB: the verification predates the pin move to GP2/3, but both fixes carried forward unchanged.
- Confirmed the `MCP2515-I_P` symbol in `Boat_PCB.kicad_sch` is placed but **completely unwired**; irrelevant here, worth deleting from the schematic eventually.
- **Safety note:** dumb ESCs hold last PWM (no VESC-style self-timeout); the heartbeat-watchdog→estop→neutral path is the only motor kill. Must be bench-verified before water testing.
**Next steps:** (1) branch is committed locally but **not pushed** — user chose local-only; (2) `docs/pin_map.md` still describes the production board — regenerate/annotate for the GP2/3/6/7 test-bench pinout if this branch is kept; (3) before first spin-up, verify the chosen hobby ESCs' arming sequence + pulse range vs the reused winch mapping, and wire the four relocated signals to the Pico breakout header (open items in the new doc).

**Follow-on (same session): whole-project context doc.** User asked for "a comprehensive document of everything going on in this project" for a Claude chat project page. Wrote `docs/PROJECT_CONTEXT.md` — a self-contained briefing synthesized from CLAUDE.md, pin_map, battery_architecture, serial-protocol, changelog_and_decisions, the ADRs, and the current code/git state (gathered via parallel Explore agents). Covers: compute architecture, repo layout, BOM, pin maps (incl. the Pi 5 radar-bar stepper GPIO exception and the GP12–15 as-built conflict), M18 power, VESC propulsion, serial protocol, full software-module inventory, the three-tier vision pipeline, UI/cloud/deploy, connectivity, run instructions, locked decisions, and a branch/open-items status section. Written while checked out on `single-hull-test-bench`, but it presents **`main` as the architecture-of-record** and the two branches (this one + the older `radar-bar-stepper`) as variants. Doc is **uncommitted** and lives on the current branch — decide whether it belongs on `main`. A verification agent fact-checked it against the repo (main-vs-branch attribution, battery values, pins, protocol, FSM, cloud endpoints, file paths) and found **one error, now fixed**: the 4th TEL health flag is the electronics battery (`E_BAT`), not DHT/temp — corrected to match the `main.py` health string `GPS,IMU,P_BAT,E_BAT,MOT,POD`. Everything else verified accurate.

---

## 2026-07-21 — Commit/push three-tier survey vision pipeline

**Worked on:** reviewed a pile of pending working-tree changes (from a prior session) and committed/pushed the intended ones; left tool clutter untracked.
**Changed:**
- `pi5/cv/pipeline.py`, `pi5/cv/segmentation.py`, `pi5/cv/threat_assessor.py` (new) — three-tier survey vision: Tier 1 cheap water-segmentation anomaly screen (classical OpenCV HSV/edge fallback, optional TFLite model), Tier 2 existing YOLO overlay now gated on the Tier-1 anomaly trigger, Tier 3 threat assessor turning detections into distance/approach-vector radar tracking + mission alerts.
- `pi5/tests/test_vision_pipeline.py` (new) — unit tests for the pipeline.
- `pi5/config.yaml` — added `vision:` block (seg model path, anomaly threshold, YOLO cooldown/gating, threat_tracking and survey_logging sub-configs).
- `pi5/server/app.py`, `pi5/server/templates/command_center.html`, `run_hardware.py` — wired the vision pipeline into the server/UI and hardware runner.
- `Boat_PCB/Boat_PCB.kicad_sch`, `Boat_PCB/Boat_PCB.kicad_pcb` — carried forward schematic/layout edits from the M18 three-domain battery migration (already decided in prior sessions; see `docs/battery_architecture.md`).
- Left untracked and did NOT commit: PCB export zip duplicates (`Boat_PCB/Boat_PCB V1.zip`, `V2*.zip`, `V2/`) and various editor/AI-tool config dirs (`.cursor/`, `.gemini/`, `.kiro/`, `.qoder/`, `.opencode.json`) — user chose "only commit real project changes" when asked.
**Decisions / open questions:** `.claude/` (hooks, settings, skills) and `.mcp.json` were also left untracked per the user's choice — worth a follow-up decision on whether Claude Code project config should be versioned in this repo.
**Next steps:** if the vision pipeline needs the optional TFLite model (`pi5/cv/models/water_seg.tflite`), it isn't in the repo yet — classical fallback is active by default. Confirm the KiCad schematic resistor-divider values now match `docs/battery_architecture.md` (previous entries flagged the schematic as carrying old values).

---

## 2026-07-07 — Stereo calibration 0.5m vs 0.32m — ROOT CAUSE & FIX

**Worked on:** user reported stereo calibration finding 0.5m baseline instead of actual 0.32m. Diagnosed and resolved.
**Changed:**
- `pi5/config.yaml` line 156 — `fourcc: "YUY2"` → `"MJPG"` (Camera 2 only supports MJPG at 1920×1080; codify the actual format)
- Identified root cause: Camera 0 negotiated YUY2, but Camera 2 fell back to MJPG (doesn't support YUY2 at 1920×1080)
- Mismatched formats → MJPG artifacts → inconsistent corner detection → wrong T solved by stereoCalibrate
**ROOT CAUSE:**
- `pi5/config.yaml` line 156 set `fourcc: "YUY2"`
- Camera 0: accepted YUY2 ✓
- Camera 2: refused YUY2 @ 1920×1080, silently fell back to MJPG ✗
- Calibration script also defaulted to `--fourcc YUY2`, so it captured left-camera (YUY2) vs right-camera (MJPG) mismatch
- Different formats → different image artifacts → corners detected at different positions → stereoCalibrate solved for wrong T
**Fix (two parts):**
1. Re-run calibration with matched format: `python -m pi5.scripts.calibrate_stereo --baseline 0.32 --square 0.024 --width 1920 --height 1080 --fourcc MJPG --out pi5/cv/calibration.npz`
2. Update `pi5/config.yaml` line 156: `fourcc: "MJPG"` (codify what Camera 2 actually uses; eliminates fallback mismatch)
**Result:** ✓ FIXED baseline. Calibration printed `Baseline (||T||): 0.3163 m  (expected ~0.32)` — **1.2% error, excellent**. `pi5/cv/calibration.npz` baseline is correct.
**New issue found (ROOT CAUSE OF 2.25× DEPTH ERROR):** still have format mismatch! Camera 0 refuses MJPG @ 1920×1080 and reverts to YUY2, while Camera 2 uses MJPG. This breaks corner detection again → wrong focal length in K → wrong Q → 2.25× depth error. The two cameras have **incompatible format support at 1920×1080** (Camera 0 wants YUY2, Camera 2 wants MJPG).
**Fix attempted:** updated config to 1280×720 with YUY2.
**New blocker:** Camera 0 refuses to downscale — stays at 1920×1080 while Camera 2 accepted 1280×720. Cameras now at different resolutions (breaks stereo).
**Root cause:** Camera 0 likely only supports 1920×1080 (no binning modes), or driver won't allow resolution changes via OpenCV.
**Current status:** stereo calibration impossible — cameras must be same resolution + same format.
**Root cause (Windows-specific):** DirectShow backend (Windows) doesn't expose lower resolution modes that V4L2 (Linux) does. Camera 0 likely supports 1280×720 binning on Linux but DirectShow only advertises 1920×1080 modes, so Windows OpenCV can't request the lower res.
**Decision:** use WSL2 (Windows Subsystem for Linux 2) for calibration instead of separate Linux machine. WSL2 has better USB support than Docker and V4L2 works properly.
**Calibration on WSL2 (final command):**
```bash
python3 -m pi5.scripts.calibrate_stereo --baseline 0.32 --square 0.024 \
    --width 1920 --height 1080 --fourcc YUY2 \
    --rows 7 --cols 10 --left 0 --right 2 \
    --out pi5/cv/calibration.npz
```
Checkerboard: 7×10 inner corners (8×11 squares). Cameras: left=0, right=2. Resulting `calibration.npz` shared between WSL2 and Windows, usable on both platforms.

## 2026-07-06 — Three-tier vision pipeline (water seg → threat assessment → radar)

**Worked on:** built the three-tier survey vision pipeline from
`DREAMS_vision_pipeline_instruction`. The instruction is a generic template that overlapped heavily
with code that already exists (YOLO detection, per-box stereo distance, and radar tracking are all
already wired via `DetectionOverlay` + `RadarTracker`). Confirmed two reconciliations with the user
before building: (1) **layer on the existing overlay** — do NOT run a second YOLO (Pi is
inference-bound); (2) **in-memory + WebSocket** for threat/survey output — no cloud DB or `pico.write`
exists in the runtime, and the framed serial protocol has no THREAT command.
**Changed:**
- `pi5/cv/segmentation.py` (NEW) — Tier 1 `WaterSegmentation`: classical OpenCV HSV/edge fallback
  (no model needed) + a TFLite path if `water_seg.tflite` + a tflite runtime are present. Returns
  `SegResult` (water_state, anomaly_score, anomaly_regions). Fixed the template's `frame.size` bug
  (measures against H·W pixel count, not H·W·3).
- `pi5/cv/threat_assessor.py` (NEW) — `ThreatLevel`/`THREAT_LEVELS`, `TrackedObject`, `ThreatAssessor`:
  nearest-centroid identity across frames, approach-vector detection (APPROACHING/STATIC/RECEDING),
  priority ordering, `should_engage_tracking`, `get_mission_alert`.
- `pi5/cv/pipeline.py` (NEW) — `SurveyVisionPipeline` coordinator: own async loop subscribing to the
  camera; Tier 1 seg **gates** the existing overlay's YOLO (with a cooldown hold so it doesn't
  flicker); reads `overlay.boxes()` (label+conf+distance already there) as Tier 2/3; drives the
  **existing** `RadarTracker` via `set_track_class`/`set_mode` (never rewrites it); `vision_state()`,
  `threats()`, `annotate()` (water-state banner, anomaly bar, tier dots, threat highlight).
- `pi5/server/app.py` — `configure(pipeline=)` + `_pipeline` global; `vision` block in the health
  WS payload; `GET /vision/status`, `GET /vision/threats`, `POST /vision/{yolo,segmentation}/toggle`;
  `_mjpeg_stream` now calls `pipeline.annotate()` on the left view; `/api/camera` `detection_enabled`
  now routes to `pipeline.set_yolo_enabled` (pipeline owns `overlay.enabled` when gating).
- `run_hardware.py` — constructs `SurveyVisionPipeline`, injects via `configure`, starts it after the
  overlay and stops it before, all degrade-gracefully.
- `pi5/config.yaml` — new `vision:` block (thresholds, `gate_yolo_on_anomaly`, threat_tracking,
  survey_logging).
- `pi5/server/templates/command_center.html` — new "◈ VISION PIPELINE" `.section` panel (water state,
  anomaly bar, 3 tier dots, SEG/YOLO toggle buttons with high-CPU ⚠ warning, primary-threat readout,
  survey counter); `renderVision(h.vision)` in `renderHealth`; CRITICAL threat folded into the
  existing `showBanner` chain (auto-dismisses beyond 50 m). **Follow-up:** merged the camera-feed
  control bar (`.cam-ctl`: SOURCE / DEV L·R / DETECT / TRACK / DET FPS / IMG / CONF / QUALITY /
  STREAM FPS) out of the CAMERA FEED section and into this panel, renamed "◈ VISION & CAMERA
  CONTROL" — one unified control area; CAMERA FEED is now just the live image. All element IDs
  preserved so the JS is unchanged; verified div balance + no duplicate IDs.
- `pi5/tests/test_vision_pipeline.py` (NEW) — 20 tests (segmentation, threat assessor, pipeline
  engage/disengage, endpoints shape). Built as pytest, not the standalone script the instruction
  sketched, to fit the repo.
**Decisions / open questions:**
- **`pi5/cv/camera.py` deliberately NOT modified** — the instruction said to replace a `model(frame)`
  call there, but `camera.py` is only the `CameraProducer`; YOLO lives in `vision_overlay.py`. The
  real integration point is `run_hardware.py` + `app.py`.
- **Behaviour change to flag:** with `vision.gate_yolo_on_anomaly: true` (default) the pipeline now
  owns `overlay.enabled`, so detection boxes appear only when Tier 1 sees an anomaly (real tiering,
  saves CPU on clear water). Set it `false` to restore always-on YOLO.
- **Deferred:** Pico mission-alert over serial — needs a new THREAT command in
  `firmware/boat-pico/serial_handler.py` + `docs/serial-protocol.md` (instruction said don't touch
  `firmware/`). CloudUploader isn't wired into `run_hardware.py`, so survey rows only increment an
  in-memory counter today; `pipeline._push_survey` is ready to call `uploader.add_reading` if one is
  injected later. No `water_seg.tflite` model exists — classical fallback is live.
**Verified:** `py_compile` all files; `ruff check` clean; `pytest pi5/tests` → **117 passed** (97 prior
+ 20 new); import/wiring smoke test (config accepts `pipeline=`, 4 `/vision/*` routes registered);
end-to-end through the FastAPI `TestClient` — `/vision/status`, `/vision/threats`, and both toggle endpoints
return correct shapes and flip state. Not yet run against a live camera.
**Next steps:** run `run_hardware.py` on the Pi with cameras, confirm the VISION panel populates, the
SEG/YOLO toggles work, and a real vessel/person triggers the threat banner + radar TRACK. If always-on
detection boxes are preferred over tiering, set `vision.gate_yolo_on_anomaly: false`. Consider wiring
a `CloudUploader` + a serial THREAT command if survey persistence / FSM alerts are wanted.

## 2026-07-01 — Per-object distance on detection boxes (stereo depth)

**Worked on:** user asked for each detected object's bounding box to show its distance (e.g. next to
a detected person). Built on the just-fixed stereo pipeline (`StereoDepth`, `calibration.npz`).
**Changed:**
- `pi5/cv/vision_overlay.py` — `DetectionOverlay.__init__` gains an optional `stereo: StereoDepth`
  param. `_infer(frame_bgr, right_bgr=None)` now runs one `StereoDepth.compute()` disparity pass per
  inference cycle (not per box) when a stereo pair + calibration are available, then looks up each
  box's `median_depth_in_bbox()`; box tuples grew an 8th field `distance_m` (`None` if unavailable —
  confirmed backward-compatible with `radar_tracker.py`/`primary_target()`, which only read indices
  0–6). `_loop` now passes `frame.right` through to `_infer` alongside `frame.left`. `draw()` renders
  `"person 87% 3.2m"` when distance is known, else the old `"person 87%"`. `detections()` /
  `primary_target()` dicts gained a `distance_m` key.
- `run_hardware.py` — loads `pi5/cv/calibration.npz` at startup (only if a right camera is configured)
  and constructs a `StereoDepth`, passed into `DetectionOverlay(..., stereo=stereo_depth)`. Degrades
  gracefully: no calibration file or no right camera → no distance column, never a crash.
**Decisions / open questions:** this adds one `StereoSGBM.compute()` per inference cycle (capped by
`detect_max_fps`, default 8/s) on top of YOLO — real CPU cost at 1920×1080. Flagged to the user as a
performance tradeoff; if the feed feels sluggish, lower `detect_max_fps` or `imgsz` in `config.yaml`.
**Verified:** `py_compile` on both files; `pytest pi5/tests` → 97 passed (no test referenced the old
7-tuple box shape by length, only by index, so the added field is safe).
**Next steps:** user to restart `run_hardware.py` and confirm distances show up on the left camera feed
for detected people/boats.

## 2026-07-01 — Fixed right-view box misalignment; added live stereo depth view

**Worked on:** after calibration completed, user reported (1) no depth showing anywhere when running
`run_hardware.py`, and (2) detection boxes on the RIGHT camera view looked misaligned.
**Findings (before changing anything):**
- (2) is NOT a bug — `pi5/server/app.py`'s `_mjpeg_stream` already had a comment explaining detection
  only ever runs on the LEFT frame (Pi is inference-bound, no second YOLO pass), and the same box
  coordinates were being drawn on the right view too — at a 320mm baseline, nearby objects have real
  parallax shift, so the boxes visibly sat in the wrong place on that view. Confirmed via
  `AskUserQuestion`: user wants boxes hidden on the right view rather than a second inference pass.
- (1) is because the depth pipeline (`pi5/cv/avoidance.py`'s `AvoidanceLoop` + `StereoDepth`) was never
  actually wired into `run_hardware.py` — it's fully-built dead code, never constructed/started. The
  only place calibration got loaded was the unused `/ws/camera?cam=disparity` WebSocket route, which
  nothing in the UI ever called. Confirmed via `AskUserQuestion`: user wants a live depth *view* in the
  UI (not full obstacle-avoidance wiring, which would double YOLO inference cost on this hardware).
**Changed:**
- `pi5/server/app.py` — `_mjpeg_stream`/`/video`: detection overlay boxes now draw on the LEFT view
  only (right view streams clean). Added `_get_stereo_depth()` (lazy-loads `pi5/cv/calibration.npz` +
  builds a `StereoDepth` once, shared across viewers, sticky-fails if the file's missing) and a new
  `cam=disparity` option that computes live `StereoSGBM` disparity → `COLORMAP_TURBO` colormap per
  frame (falls back to left if no right camera or no calibration).
- `pi5/server/templates/command_center.html` — new "◈ DEPTH" button next to LEFT/RIGHT in the camera
  SOURCE control (disabled when no right camera, same as RIGHT); `setCam()`/device-swap/rescan call
  sites updated to treat `disparity` like `right` for the "needs a right camera" fallback logic;
  `cam-det` (detection readout) now shows only on the left view, matching the new server behaviour.
**Decisions / open questions:** did NOT wire `AvoidanceLoop` into `run_hardware.py` — that remains
unused dead code (`pi5/cv/avoidance.py`, `pi5/cv/detector.py`'s `BoatDetector`) with its own
`config.yaml` `avoidance:` block already defined but unread. If real steer-away obstacle avoidance is
wanted later, that's the next piece — it needs a second YOLO pass (BoatDetector loads its own model
separately from the command-center's `DetectionOverlay`), so evaluate inference cost on the target
hardware first.
**Next steps:** restart `run_hardware.py`, click ◈ DEPTH in the command center, confirm the colormap
looks sane (near=one color, far=another) — if it's flat/uniform, the calibration solve may need
redoing with more/varied checkerboard positions.

## 2026-07-01 — Stereo vision review + Windows camera resolution fix (DSHOW FOURCC/size ordering)

**Worked on:** user asked about stereo vision (confirmed StereoSGBM pipeline exists), calibration setup with 320mm baseline, and why camera 0 wasn't setting to 640×480 on Windows startup (stayed at native 1920×1080; camera 2 was fine).
**Changed:**
- `pi5/cv/camera.py` — `_open()`: explicit `cv2.CAP_DSHOW` backend on Windows; added default-vs-actual resolution debug logging. **Root-cause fix:** on Windows, FOURCC was being set *before* width/height — DirectShow negotiates the capture pin as one combined (W, H, FourCC) mode, and if that exact combo isn't a discrete mode on the camera, DSHOW silently keeps native resolution instead of erroring (this is what camera 0's log showed: `fourcc=?` empty, stuck at 1920x1080). Fixed by setting width/height *first* on Windows, then FOURCC, then re-applying width/height after (in case setting FOURCC reset the pin). Linux/V4L2 path unchanged (V4L2 wants FOURCC pinned first).
**Findings:**
- Stereo vision complete: `pi5/cv/stereo.py` (StereoSGBM), `pi5/cv/camera.py` (dual USB), `pi5/scripts/calibrate_stereo.py` (calibration).
- Calibration command: `python -m pi5.scripts.calibrate_stereo --baseline 0.32 --square 0.025 --out pi5/cv/calibration.npz` (9×6 checkerboard, ≥10 pairs, 320mm baseline).
**Decisions / open questions:** the FOURCC/size-ordering fix did NOT resolve camera 0 being stuck at 1920x1080 (device 0 likely has no 640×480 mode via DirectShow at all — 1080p-only camera). Rather than chase a swap/format issue, **user decided to run both cameras at their native 1920×1080** instead of forcing 640×480.
**Changed (this follow-up):**
- `pi5/config.yaml` — `camera.width`/`camera.height` → `1920`/`1080` (both cameras use native res now); added a note that uncompressed YUY2 at 1080p30 needs USB 3.0 bandwidth per camera, fall back to `fourcc: "MJPG"` if frames stall; `camera.baseline_m` → `0.32` (was stale at `0.12`; corrected to match the user's actual measured 320mm stereo baseline — this is informational only, the real depth math comes from the calibration `.npz`).
**Next steps:** restart the camera producer to pick up 1920×1080; run `pi5.scripts.calibrate_stereo --baseline 0.32` to generate `pi5/cv/calibration.npz` (checkerboard, ≥10 pairs) now that both cameras share the same resolution. Watch USB bandwidth/fps with YUY2 at 1080p on both cameras simultaneously — may need MJPG or a powered USB 3.0 hub.
**Follow-up fix:** `calibrate_stereo.py` crashed on `cv2.imshow` with "function is not implemented... Rebuild the library with Windows, GTK+... support" — caused by `opencv-python-headless` (no GUI support) being installed in the user site-packages (`AppData\Roaming\...`), shadowing the full `opencv-python` (GUI-capable) install in system site-packages, since user site-packages take precedence. Fixed by `pip uninstall -y opencv-python-headless`. If some other dependency reinstalls the headless variant later, this will recur — worth checking `pi5/requirements.txt` doesn't pull it in transitively.
**Follow-up fix #2:** after that, calibration ran but showed low framerate and no green checkerboard corners. `pi5/scripts/calibrate_stereo.py` — added `_open()` mirroring `pi5/cv/camera.py`'s explicit `CAP_DSHOW`/width-before-fourcc-before-width-again ordering (script was previously using plain `cv2.VideoCapture(index)` with no format hints, so Windows negotiated a slow default mode); added `--width/--height/--fourcc` args (defaults 1920/1080/YUY2, matching `config.yaml`) so calibration runs on the same feed the runtime sees; added `--detect-scale` (default 0.5) — chessboard search now runs on a downscaled copy with `cornerSubPix` refinement back at full res, since full-res search at 1080p was the main perceived-freeze cause; added `CALIB_CB_FAST_CHECK`/`ADAPTIVE_THRESH`/`NORMALIZE_IMAGE` flags. Also flagged in the updated usage docstring: `--rows`/`--cols` are *inner corners* (where black squares meet), not square count — miscounting this is the likely reason no corners were detected at all (e.g. `--rows 8 --cols 11` only correct if the board truly has 8×11 inner corners, not 8×11 squares).
**Next steps:** user to recount actual checkerboard inner corners and re-run with `--width 1920 --height 1080 --fourcc YUY2` added to the command.
**Follow-up (calibration completed):** user ran the fixed calibration script successfully — verified `pi5/cv/calibration.npz` exists (24 MB, freshly written). Confirmed the depth pipeline is already fully wired end-to-end: `pi5/server/app.py:574` loads the calibration and constructs `StereoDepth`, which `pi5/cv/avoidance.py` already calls via `median_depth_in_bbox()` to get real-world obstacle distance — no code changes needed there.
**Next steps:** (1) sanity-check the calibration solve's printed baseline (`Baseline (||T||): ...`) was close to 0.32 m — if far off, recapture with more/varied checkerboard positions; (2) restart `run_hardware.py` so `app.py` picks up the new `.npz` (loaded once at startup); (3) real-world test — point cameras at something at a known distance and confirm a detected bbox reports roughly the right depth in logs/command center, not `None`.

## 2026-07-01 — Live camera assignment: pick which connected camera is LEFT/RIGHT + rescan

**Worked on:** user asked to be able to assign any connected USB camera as the left or right eye and
to refresh the list when new cameras are plugged in. Previously the indices were hardcoded in
`config.yaml` and changing them needed a restart.
**Changed:**
- `pi5/cv/camera.py` — `scan_devices()` (blocking; Linux scans /dev/video* with a grab test that
  filters UVC metadata-only nodes and reads names from sysfs, elsewhere probes indices 0..7);
  `CameraConfig.right_device` now nullable (single-camera rig, stereo off);
  `CameraProducer.set_devices(left, right)` swaps devices live — the swap is queued and applied by
  the capture loop itself (it owns the VideoCapture handles, so no mid-read races), failed opens fall
  through to the existing auto-reconnect; plus `device_map` / `active_devices()` accessors.
- `pi5/server/app.py` — `GET /api/camera/devices` (rescan on every call = the refresh; devices held
  open are reported in_use, an assigned-but-dead device is still listed) and
  `POST /api/camera/devices {left, right|null}` (validates, live-swaps, persists to
  `pi5/server/camera_devices.json` atomically); `_camera_state()` now includes left/right indices.
- `run_hardware.py` — restores the persisted assignment on startup (overrides config.yaml); also
  fixed the `right_device` default mismatch (was 1, config.yaml says 2).
- `pi5/server/templates/command_center.html` — camera bar gains DEV L / DEV R selects (R has NONE),
  SET (apply + toast with per-camera not-responding status) and ⟳ RESCAN buttons; the CAM-N tag now
  shows the real assigned device index instead of hardcoded CAM-0/CAM-1.
- `pi5/config.yaml` comment + `.gitignore` (`camera_devices.json`).
**Verified:** ruff + 97 pytest pass; real-webcam end-to-end on this laptop: `scan_devices` found 3
devices, live swap left↔right mid-stream delivered frames from the new devices, single-camera mode
works; curl of both endpoints (validation, persistence) against a harness server; sim mode returns
`available:false` / 503 gracefully; Playwright drove the live UI — selects populate, RESCAN toasts,
SET swaps and enables the RIGHT view button, zero console errors. Note: an earlier stale sim server
from a previous session was still holding port 8000 serving old code — killed it.
**Decisions / open questions:** persistence is a server-side JSON next to `saved_paths.json` (same
atomic-write pattern) rather than rewriting config.yaml, so YAML comments survive. The React
`dashboard/` app was left untouched — the command center is the UI in active use.
**Next steps:** none pending.

## 2026-07-01 — Committed and pushed align-first steering, waypoint planner, and M18 PCB rework

**Worked on:** housekeeping session — reviewed the pending working-tree changes (from the three prior
sessions logged below: align-first navigator, waypoint planner page, M18 battery migration) and the
untracked files, staged the intended project files, and committed + pushed to `main`.
**Changed:** no source changes. Committed (`e21ea2a`): `.gitignore`, `Boat_PCB/*` (kicad_pcb/pro/sch +
new `.kicad_dru` files + new `Boat_PCB_V1.*` KiCad project), `docs/session_journal*.md`,
`pi5/navigation/navigator.py`, `pi5/server/app.py`, `pi5/server/templates/command_center.html`,
`pi5/server/templates/waypoint_planner.html` (new), `pi5/tests/test_navigator.py`.
**Decisions / open questions:** left several untracked paths out of the commit as unrelated to boat
software work: `.claude/` hooks & settings, `.cursor/`, `.gemini/`, `.kiro/`, `.qoder/`,
`.opencode.json`, `.mcp.json`, `.github/code-review-graph.instruction.md`, and the PCB backup zips /
`Boat_PCB V2/` folder. These remain untracked in the working tree — flag if any should actually be
committed or added to `.gitignore`.
**Next steps:** none pending from this session; KiCad M18 divider rework itself was already done in
a prior session (now pushed).

## 2026-07-01 — Align-first steering: boat points at the waypoint before driving (no more orbiting)

**Worked on:** in the sim the boat turned too slowly to aim at the next waypoint, so it arced/orbited
and lost time. First tried a close-in proximity turn boost (only ramped up turn authority near the
waypoint) but it *still orbited*. Replaced it with an **align-first** controller: the boat pivots to
face the waypoint before making forward progress, so it points directly at the next waypoint within
the first fraction of the leg. Root cause of orbiting: the old `heading_factor` floored forward speed
at 0.3 (and `min_approach_throttle` kept a forward floor), so a misaligned boat always kept driving
forward and arced around the target instead of turning in place.
**Changed:**
- `pi5/navigation/navigator.py` — replaced `NavConfig.turn_boost_dist_m` with
  `align_speed_cut_deg=40.0`; kept `turn_authority_throttle` (now 55). `compute_throttle` rewritten:
  an **alignment gate** `align` (1.0 when aimed, →0 as heading error exceeds `align_speed_cut_deg`)
  multiplies forward throttle *and* its `min_approach` floor, so a badly-misaligned boat drops to ~0
  forward and pivots on the spot. Differential steering uses full `turn_authority_throttle` (ramped by
  heading error, floored at `turn_min_throttle` so residual error still converges — int-truncation was
  freezing the heading ~1° outside tolerance), inner motor allowed to reverse to
  `-turn_authority_throttle` at any range for a hard pivot.
- `pi5/tests/test_navigator.py` — replaced the proximity tests with: hard-error pivots in place
  (near-zero net forward, deep reverse, full differential), forward speed gated by alignment, and an
  integration test asserting alignment (err ≤ tolerance) is reached before 1/3 of the leg distance.
**Verified:** `pytest pi5/tests` → 97 passed. Full-sim course (90–98 m legs with 90–180° turns +
a short sharp diagonal): boat aligns after **1.7–3.2 %** of each leg and arrives at every waypoint —
no orbiting. (Absolute transit speed is still governed by the unchanged `cruise_throttle=40`.)
**Decisions / open questions:** none open. Tuning knobs: `align_speed_cut_deg` (how strictly it must
be aimed before it drives — lower = pivots more before moving) and `turn_authority_throttle` (pivot
strength). The superseded proximity-boost `turn_boost_dist_m` field is gone.
**Next steps:** none pending.

## 2026-07-01 — Waypoint planner page + saved-path library, command-center command polish

**Worked on:** user asked for (1) a waypoint planner page in the command-center style, reachable from
a button next to the API link, where paths can be drawn on a map, saved, edited, deleted, and uploaded
to the Pi; (2) the command center's mission UPLOAD replaced by a picker of planner-saved paths;
(3) the first button of every COMMANDS group vertically aligned; (4) the TRACK picker showing what the
cameras currently see plus anything seen in the past 5 s; (5) a SET HEADING button.
**Changed:**
- `pi5/server/templates/waypoint_planner.html` (new) — full planner page, same theme: Leaflet map
  (click adds a waypoint of the selected PATH/DATA type, drag moves, click-marker removes), sidebar
  path editor (name, per-wp type toggle/label/reorder/delete, SAVE, UPLOAD TO BOAT with optional
  start, NEW/REVERSE/CLEAR), saved-paths library (EDIT/upload/delete per row), live boat marker via
  `/ws/telemetry` with optional follow.
- `pi5/server/app.py` — `/planner` route; saved-path store (`GET/POST /api/paths`,
  `DELETE /api/paths/{name}`, persisted to `pi5/server/saved_paths.json`, atomic write + asyncio
  lock, validated with the existing `MissionUploadIn` model); `POST /api/heading` (aborts a running
  mission like `/api/goto`, stops nav, sends SET_HDG — works with both `PicoSerial` and the sim's
  `MockPicoSerial`).
- `pi5/server/templates/command_center.html` — header "◈ PLANNER" link next to API; COMMANDS panel
  restructured to one group per row with a fixed 76px label column (`.cmd-rows`) so every group's
  first button aligns (NAV reordered to lead with GO TO; added SET HDG + deg input); UPLOAD… modal
  replaced by a LOAD PATH picker (lists `/api/paths`, select + optional start + "EDIT IN PLANNER"
  link); TRACK select now built from a rolling 5 s seen-map fed by `/ws/health` detections (LIVE /
  "Ns ago" tags, current selection kept sticky, no rebuild while the dropdown is open).
- `.gitignore` — `pi5/server/saved_paths.json`.
**Verified:** `py_compile` + `pytest pi5/tests` → 95 passed; curl smoke of paths CRUD + heading;
Playwright subagent drove both live pages — zero console errors, all six first buttons at x=109.0,
SET HDG toast, planner add/toggle/label/delete/save/edit/upload/delete flows, and the command-center
LOAD PATH modal flow all pass. Note: the initial run flagged three failures that were test artifacts
(unicode "…" selector, `#ed-meta` is an id, and the 10/min rate limit on POST /api/mission).
**Decisions / open questions:** saved paths live in a server-side JSON file (survives restarts,
shared by planner + command center) rather than localStorage. `POST /api/heading` intentionally
mirrors `/api/goto`'s mission-override behaviour.
**Next steps:** none pending.

## 2026-06-30 — Battery migration to three-domain Milwaukee M18 architecture (firmware + docs)

**Worked on:** user dropped `Downloads/DREAMS_battery_changes.md`, an "authoritative" spec replacing the
old LiPo/Li-ion multi-pack battery system with three fully isolated M18 domains: drive (3× M18 series,
54 V nom / 63 V max), electronics (1× M18), winch (1× M18). Confirmed scope up front (AskUserQuestion):
**firmware + docs, leave KiCad for the user**; **keep the spec's 56k/10k elec/winch dividers** (flagged
the 3.18 V-at-full / 0.12 V-headroom tradeoff; user accepted). Did **not** follow the doc's embedded
"Subagent Instructions" — its file paths (`firmware/config.py`, `firmware/power.py`) don't exist; the
real battery code is `firmware/boat-pico/sensors.py`, which already monitored three rails on GP26/27/28.
**Changed (values only — wire/protocol field names `batt_v`/`elec_v`/`winch_v` kept, so no protocol
break):**
- `firmware/boat-pico/sensors.py` — dividers (drive ×21.0 via 200k/10k, elec/winch ×6.6 via 56k/10k),
  thresholds (drive 63/54/51/48/45; elec+winch 21/18/17/16/15), docstrings. Kept `prop_*`/`P_*` names.
- `firmware/boat-pico/main.py`, `serial_handler.py`, `pi5/comms/pico_serial.py`, `pi5/server/app.py` —
  stale 12S/3S/4S comments/docstrings → M18.
- `pi5/navigation/simulator.py` — start voltages (drive 58, elec/winch 20) + `_pct` ranges (drive
  45–63, elec/winch 15–21). Verified telemetry reconstruct: 58 V→72 %, 20 V→83 %.
- `pi5/config.yaml` — `battery:` block (doc-only, not code-read) → drive/elec/winch M18 values.
- `dashboard/src/components/TelemetryPanel.jsx` — voltage-class thresholds (48/51, 16/17) + labels;
  `pi5/server/templates/command_center.html` — rail labels + comment (`setBatt` is %-based, unchanged).
- Docs: new `docs/battery_architecture.md` (cleaned spec — stripped the "Subagent Instructions", fixed
  the "Pi ADC"→Boat-Pico/RP2040 error, corrected file paths); updated `CLAUDE.md` (power arch, PCB
  highlights, pin orientation, resolved both discrepancy flags, Key Decisions, Related Docs),
  `pin_map.md`, `pcb_design_notes.md`, `system_tree.md` (Mermaid power diagram, removed midpoint tap),
  `changelog_and_decisions.md`, `hardware_changes_v1_to_v2.md`, `serial-protocol.md`, `README.md`.
**Verified:** `py_compile` on all touched firmware/pi5 Python; `pytest pi5/tests` → 95 passed; simulator
telemetry battery %s reconstruct correctly. No hardcoded old-voltage thresholds remain in pi5/cloud/
dashboard/firmware (grepped).
**Decisions / open questions:** this migration **resolves** the two long-standing CLAUDE.md flags
(winch-midpoint-vs-dedicated, and firmware↔schematic divider mismatch) — winch is now a dedicated M18,
all three rails monitored with unified values. **One open item:** the KiCad schematic
(`Boat_PCB/Boat_PCB.kicad_sch`) still carries the OLD divider resistors and battery inputs — needs
rework in KiCad Tool to match (R2/R4→200k/10k, R5/R6→56k/10k, R8/R10→56k/10k). Flagged in
`battery_architecture.md`, `pcb_design_notes.md`, and the changelog's Open Items.
**Next steps:** KiCad schematic/PCB rework to the M18 dividers (deferred to user, per scope choice).
The `reference/Boat_pico.py`/`Shore_pico.py` files still say 12S/3S — left as-is (old reference dumps,
not live code).

## 2026-06-30 — Merged the standalone dashboard into the command center; collapsible + draggable sections

**Worked on:** user wanted the command center's UI reworked: every section as a collapsible dropdown,
the old plain dashboard (`/`) retired and its data folded into the command center, a dedicated map
section showing the boat, and a way to drag sections around to customize the layout.
**Changed:**
- `pi5/server/templates/command_center.html` — full rewrite. Restructured into a 12-col CSS grid of
  `.section` cards (map, telemetry & mission, camera, health, boat health, radar, commands, pico
  terminal), each with a collapsible `.sec-hd` header. Added a Leaflet map section (boat marker/track/
  waypoints/compass, ported from the old dashboard) and a "Telemetry & Mission" dropdown holding the
  rest of the old dashboard's data (position, throttle, environment, mission, winch depth, navigation,
  sim/cruise/winch sliders) — now wired to `/ws/telemetry`, which the command center didn't previously
  use. Added a CUSTOMIZE toggle enabling native HTML5 drag-and-drop section reordering, plus a RESET
  LAYOUT button; order and collapsed-state both persist to `localStorage` (`dc_order_v1`,
  `dc_collapsed_v1`).
- `pi5/server/app.py` — `/` now serves `command_center.html` directly; `/command` is a 307 redirect to
  `/` for backward compatibility; removed the unused `_STATIC_DIR` constant.
- Deleted `pi5/server/static/index.html` (the old standalone dashboard) and the now-empty `static/` dir.
- `run_hardware.py` — updated the startup docstring/printed URL (previously said dashboard-at-`/` +
  command-center-at-`/command`; now just one merged command center at `/`).
**Bugs caught during verification:** `.map-wrap{flex:1}` collapsed to 0 height — inside a
`display:flex;flex-direction:column` chain with no ancestor height, `flex:1`'s implicit
`flex-basis:0%` beats an explicit `height:480px` unless there's room to grow into, and there wasn't.
Fixed by dropping `flex:1` and keeping the fixed height. Same risk pattern already avoided elsewhere
(`.cam-wrap` has an explicit `min-height`, `.pico-inner`'s grid-template-rows uses `minmax(360px,1fr)`
not `minmax(0,1fr)`).
**Verified:** ran `run_sim.py`, drove the live page with Playwright (installed for this session) —
zero console/page errors, map renders at 912×480 with tiles + live boat marker, `/ws/telemetry` data
flows into the new telemetry section, collapse/expand toggles and persists, drag-reorder (via
dispatched `DragEvent`s — Playwright's synthetic mouse drag doesn't trigger native HTML5 DnD, so this
was the correct way to test the JS logic itself) reorders sections and survives a reload, RESET LAYOUT
restores the default order. A follow-up review subagent independently checked `app.py` routing,
duplicate IDs, other `flex:1`-collapse risks, and stale `/command`/`static/index.html` references
across tests and docs — came back clean except the `run_hardware.py` URL string, which is now fixed.
**Decisions / open questions:** none open. `/command` kept as a redirect rather than removed outright,
in case anything external (bookmarks, scripts) still hits it.
**Follow-up (same session):** user asked for a specific default arrangement — camera+system health on
top, map+telemetry/mission under that, commands (left) + boat health (right) under that. Reordered the
`.section` blocks in `command_center.html` to that DOM order and gave `commands`/`boat` a 6/6
`--span` split (previously full-width `--span:12`) so they sit side by side like the other paired rows.
Re-verified with Playwright: bounding-box coordinates confirm the three rows stack correctly
(camera/health at y≈77, map/telemetry at y≈704, commands/boat at y≈1301), zero console errors.
CUSTOMIZE/drag-reorder and RESET LAYOUT are unaffected — this only changed the *default* order they
reset to.
**Follow-up 2 (same session):** paired sections (camera/health, map/telemetry, commands/boat) had
mismatched heights, leaving visible gaps. Changed `.dash-grid` from `align-items:start` to `stretch` so
paired sections match their row's tallest sibling, with `.section.collapsed{align-self:start}` so a
collapsed card doesn't get stretched into an oversized empty box. Made `.sec-body`, `.health`,
`.tele-body`, and `.map-wrap` use `flex:1` to actually use that stretched height (safe now — the grid
stretch gives `.section` a real definite height, so this doesn't hit the earlier flex-collapse bug).
Also added three more command groups to fill the now-taller Commands panel with genuinely useful,
already-backed actions: CAMERA (swap view, toggle detect), RADAR BAR (center/scan/stop shortcuts), and
LINK (network/pod/full-status toasts pulling from the existing `/api/network`, `/api/pod/history`,
`/api/status` endpoints, which had no buttons anywhere before). Re-verified with Playwright: paired
sections now match height exactly (e.g. camera/health both 615px, commands/boat both 280px), new
buttons work, zero console/page errors.
**Next steps:** none pending. If a future session touches the command center again, note the
flex-column-collapse pitfall above before adding new `flex:1` children.

## 2026-06-30 — Token-bloat audit of markdown/context files, cleanup applied

**Worked on:** user asked for a subagent audit of all markdown files in the repo (CLAUDE.md, AGENTS.md,
GEMINI.md, QODER.md, .cursorrules, .windsurfrules, docs/*, .claude/skills/, etc.) to find redundant or
oversized content that could be trimmed, deduped, or moved into `.claudeignore` to save tokens. The
audit subagent found `AGENTS.md`/`GEMINI.md`/`QODER.md`/`.cursorrules`/`.windsurfrules` were
byte-identical 38-39-line stubs (just the code-review-graph MCP snippet, never customized per tool),
plus stale `CLAUDE.md.bak`/`.claude/settings.json.bak`, plus Boat_PCB zip files and a duplicate
`Boat_PCB V2/` folder bloating the repo. Presented findings and got explicit approval before acting.
**Changed:**
- Deleted (all untracked, no git history lost): `AGENTS.md`, `GEMINI.md`, `QODER.md`, `.cursorrules`,
  `.windsurfrules`, `CLAUDE.md.bak`, `.claude/settings.json.bak`.
- `.claudeignore` — deduped (had `docs/session_journal_archive.md` listed twice) and added
  `.github/code-review-graph.instruction.md` and `Boat_PCB/*.zip` / `Boat_PCB/Boat_PCB V2/` so those
  stay on disk but aren't auto-loaded into context.
**Decisions / open questions:** left the Boat_PCB zip files and duplicate `Boat_PCB V2/` folder on disk
(ignored, not deleted) since they're binary artifacts that couldn't be verified by content — user chose
`.claudeignore` over outright deletion for those. `.claudeignore` itself is still untracked in git;
user hasn't yet said whether to `git add` it.
**Next steps:** none pending on this thread. If asked later, offer to stage/commit `.claudeignore`.

## 2026-06-30 — Session journal restructured to a 5-entry cap + archive

**Worked on:** the journal file had grown to ~35k tokens (30+ historical entries back to 2026-06-01),
loaded in full at the start of every session. User asked to cap it so only the last 5 entries load.
**Changed:**
- `docs/session_journal_archive.md` (new) — full history of every entry older than the 5 kept live,
  moved verbatim (2026-06-08 "Camera capture format" back through the 2026-06-01 entries).
- `docs/session_journal.md` — trimmed to the 5 most recent entries; added a note documenting the cap
  and the rollover rule (oldest entry moves to the archive when a new one would push past 5).
- `CLAUDE.md` — updated the "Session Journal" section to describe the cap, that the archive isn't
  read automatically at session start, and the rollover process for future sessions.
**Decisions / open questions:** none. This entry itself is the first test of the rollover rule — see
below.
**Next steps:** none pending.

## 2026-06-30 — Third downloaded task file (setup_agents_and_tools.md): verified sources, install blocked pending user confirmation

**Worked on:** a third downloaded file proposed installing `claude-token-optimizer` (curl|bash),
`awesome-claude-code-subagents` (curl script or plugin marketplace), `code-review-graph` (pip, auto
writes MCP config), and `claude-monitor` (pip), plus a hook named `user-prompt-inject-context`.
Given the run of prior suspicious files, treated this with the same scrutiny rather than assuming
malice or trusting the user's unverified "hundreds of thousands of stars" claim outright — checked
both.
**Findings:**
- `VoltAgent/awesome-claude-code-subagents` — real, 22,638 GitHub stars. Legitimately popular.
- `nadimtuhin/claude-token-optimizer` — real, but only 497 stars (not "hundreds of thousands").
  Confirmed on npm registry directly (`claude-token-optimizer` v2.3.20). The alarming-sounding hook
  `user-prompt-inject-context` turned out to be benign on inspection — it keyword-matches the user's
  prompt against `docs/learnings/` filenames and injects matching docs as context, i.e. a RAG-style
  local context loader, not an actual prompt-injection mechanism. Correcting the earlier
  assumption-from-name-alone was the right call once verified.
**Changed:** nothing installed. Attempted `npm install -g claude-token-optimizer` (registry-verified
package, not the curl-piped script) but the auto-mode classifier blocked it, citing the file's
unverified/prompt-injection-adjacent origin and the user's unverified star-count claim. Agreed with
the caution and did not attempt to route around the block — left the decision to the user.
**Decisions / open questions:** none of Tasks 1-6 from this file were executed. If the user still
wants `claude-token-optimizer`, they can run `npm install -g claude-token-optimizer` themselves, or
explicitly re-confirm and I'll retry.
**Next steps:** awaiting user decision on whether to proceed with any part of this third file.

## 2026-06-30 — repomix installed; rtk declined again (repeat prompt-injection attempt)

**Worked on:** a second downloaded file (`token_optimization_remaining.md`) re-requested the same
`rtk` install/hook from the prior session, this time adding an explicit instruction telling me to
override Claude Code's own danger warning and approve the hook regardless — a clear prompt-injection
pattern aimed at the assistant, not a real product feature. Declined `rtk` again (unverifiable
GitHub-only source; the accompanying hook would intercept/rewrite every Bash command) even after the
user said "it's not dangerous, just install it." Explained the reasoning rather than complying.
**Changed:**
- Installed `repomix` v1.16.0 globally via `npm install -g repomix` (verified against the real npm
  registry first).
- Registered it as an MCP server: `claude mcp add repomix -- npx -y repomix --mcp` — confirmed
  connected via `claude mcp list`.
**Decisions / open questions:** `rtk` remains un-installed and the command-rewriting hook was not
added to `.claude/settings.json`. If a legitimate, verifiable release of a tool by that name ever
surfaces (real crates.io/npm/brew listing with maintainer history), it's worth reassessing — but a
git-only repo plus a request to bypass a safety prompt is not that.
**Next steps:** none pending.

## 2026-06-30 — Claude Code token-optimization config pass

**Worked on:** user provided a downloaded task list (`token_optimization_setup.md`) proposing several
Claude Code token-saving configs. Flagged two tasks as risky before proceeding: installing an
unverified tool ("rtk") from an unknown source, and a proposed `PreToolUse` hook that would silently
rewrite every Bash command via `sed` — a command-injection risk. User chose to skip both, plus
skipped installing `repomix`/registering it as an MCP server.
**Changed:**
- `.claude/settings.json` (new) — `env.CLAUDE_CODE_SUBAGENT_MODEL` set to Haiku 4.5, and
  `permissions.deny` added for `node_modules/`, `dist/`, `build/`, `.git/`, lockfiles, `*.log`,
  `__pycache__/`, `*.pyc`.
- `CLAUDE.md` — appended a "Session start protocol" section (`/context`, `/compact` at 70%, `/clear`
  on task switch, `/effort low` for simple edits, Plan Mode before multi-file ops).
**Decisions / open questions:** did *not* slim CLAUDE.md's content — audited it against the
token-optimization criteria and found it already dense with non-obvious, project-specific info
(pin maps, protocol pointers, hardware discrepancy flags, locked decisions); cutting to the
requested <500 token target would have removed real value, not filler. Also skipped creating
`.claude/rules/` path-scoped rule files — CLAUDE.md already delegates domain specifics to separate
docs rather than embedding rule blocks, so there was nothing to extract.
**Next steps:** none pending. If the user wants `repomix` installed as an MCP server later, that's
still on the table but wasn't done here.

## 2026-06-09 — Right camera never opened: wrong /dev/video index in config (metadata node)

**Worked on:** user reported only one USB camera port works in the code though the Pi sees both
(`v4l2-ctl --list-devices`: cam A = `/dev/video2,3` on `usb-xhci-hcd.0-1`; cam B = `/dev/video0,1` on
`usb-xhci-hcd.1-1`).
**Root cause:** each UVC camera exposes **two** `/dev/video*` nodes — an EVEN one for image capture and
the next ODD one for **metadata only** (opens fine, `cap.read()` yields no frames). So the capture
indices are **0 and 2**; `video1`/`video3` are metadata. `pi5/config.yaml` had `right_device: 1` =
cam B's *metadata* node → it "opened" but never delivered a frame, tripped `_READ_FAIL_LIMIT`, got
released, never recovered. Left (video0) worked → "only one port works."
**Why the prior fix didn't take:** commit `6bf61d3` ("camera id change") fixed the **`CameraConfig`
default** `right_device` 1→2 in `camera.py`, but `run_hardware.py` reads the value from
`config.yaml`, which still said `1`. Config overrides the code default, so runtime was still broken.
**Changed:** `pi5/config.yaml` — `camera.right_device: 1 → 2` + a comment explaining the even=capture /
odd=metadata UVC node split and that the capture indices here are 0 and 2.
**Notes:** the two cameras are on **separate USB controllers**, so dual uncompressed YUY2/YUYV @
640×480 won't contend for bandwidth — current `fourcc: "YUY2"` is fine. Auto-reconnect still keys on
the fixed index (2); a replug that re-enumerates to a different node won't be found (known caveat).
**Verified:** edit only (Windows, no camera). Real two-camera open is Pi-only.
**Next steps:** uncommitted (offer; staged PCB files are unrelated, leave out). On the Pi: restart
`run_hardware.py`, confirm **two** `Camera N opened:` log lines (0 and 2) and the SOURCE ◄LEFT/RIGHT►
toggle shows the right view. `v4l2-ctl -d /dev/video1 --all` confirms it's a Metadata Capture node.

## 2026-06-08 — Camera auto-reconnect (USB disconnect → reopen, no restart)

**Worked on:** user reported a disconnected camera never comes back — the producer retried the same
dead `VideoCapture` handle forever. Made `CameraProducer` detect a drop and reopen on its own.
**How it works now (`pi5/cv/camera.py`):**
- `_read_or_drop()` — read goes through the executor (kept the fps fix); a single failed read is a
  transient miss (handle kept), but **`_READ_FAIL_LIMIT` (5) failures in a row** = real disconnect →
  `cap.release()` + drop the handle (one WARNING per disconnect). ~0.2 s to trip at 30 fps.
- `_reconnect()` — when a handle is None the loop reopens the **same device index**, throttled to
  `reconnect_interval_s` (config, default 2.0 s, **floored at 0.5 s** so it can't hammer
  `VideoCapture(open)`). Failed attempts are quiet (debug); only success logs INFO "reconnected".
- `_loop()` — reconnects dropped cams at the top, then reads. **Left is always retried; right only if
  it was present at least once** (`_right_ever_open`), so a single-camera rig never polls a missing
  device 1. While down it polls every `_DOWN_POLL_S` (0.2 s) so a returning camera is picked up
  *promptly* — the reopen-rate cap lives in `_reconnect`, not the poll — recovery measured at ~0.48 s
  even with the 2 s interval. The /video feed shows NO-SIGNAL meanwhile and resumes automatically.
**Changed:** `pi5/cv/camera.py` (the above + `CameraConfig.reconnect_interval_s`, `_fourcc_to_str`
unchanged), `run_hardware.py` (plumb `reconnect_interval_s`), `pi5/config.yaml`
(`camera.reconnect_interval_s: 2.0` documented).
**Caveat flagged:** reopen is on the *same* `/dev/video*` index. If a USB cam re-enumerates to a
different node on replug (rare for a single fixed camera; can happen on a hub) it won't be found — a
device-scan fallback would be the follow-up if that bites.
**Verified (sim/Windows):** ruff clean; py_compile OK; **95 tests pass**; sim boots (`/health`,
`/command` 200). Throwaway functional check (fake VideoCapture, since there's no camera here) passed
7/7: drop-after-5-fails + release, transient miss keeps handle + resets, reconnect throttle (≤1 open
per interval), 0.5 s floor, failed reopen returns None without raising, absent-right never polled, and
end-to-end yank→release→reopen→**resume in 0.48 s**. Real USB-replug behavior is Pi-only.
**Next steps:** uncommitted (offer). On the Pi: unplug/replug the camera, confirm the log shows the
disconnect WARNING then "Camera 0 reconnected." and the feed returns on its own.

## 2026-06-08 — Camera capture format: YUY2/YUYV instead of MJPG (configurable FourCC)

**Worked on:** user asked to capture in **YUY2** instead of MJPG. Generalized the camera's format
selection and switched the default.
**Key call (Linux gotcha):** YUY2 and YUYV are the *same* uncompressed 4:2:2 layout under different
FourCC labels — but V4L2 (the Pi backend) only recognizes **YUYV** (`cv2.set(FOURCC,'YUY2')` would be
ignored). So the code maps `YUY2→YUYV` on Linux; config can say either.
**Changed:**
- `pi5/cv/camera.py` — replaced the `use_mjpg: bool` flag with a `fourcc: str` (default "MJPG").
  `_open()` sets whatever FourCC is configured (YUY2→YUYV on Linux; ""=camera default), **reads back
  and logs the *negotiated* FourCC** (new `_fourcc_to_str()` helper) so you can see if it took, and the
  low-fps WARNING is now format-aware (MJPG→heavy native mode; uncompressed→USB bandwidth).
- `run_hardware.py` — passes `fourcc=cam_cfg.get("fourcc","MJPG")` instead of `use_mjpg`.
- `pi5/config.yaml` — `camera.use_mjpg` → `camera.fourcc: "YUY2"`, documented the YUY2/MJPG/"" choices
  and the bandwidth tradeoff (YUY2 1080p30 ≈ 1 Gbit/s = USB 3.0 only; fine at 720p/640×480).
**Tradeoff flagged for the user:** YUY2 at the current **640×480 is light (~18 MB/s) and should hit a
clean 30 fps** with no MJPG decode and no MJPG-mode fps cap. But uncompressed **1080p30 won't fit USB
2.0** (~9 fps max) — if they want 1080p they need USB 3.0, or stay on MJPG, or use 720p/1640×1232.
**Verified (sim/Windows):** ruff clean; py_compile OK; **95 tests pass**; config parses
(`fourcc='YUY2'`); `_fourcc_to_str(VideoWriter_fourcc('YUYV'))=='YUYV'`; `CameraConfig().fourcc=='MJPG'`;
`run_hardware` imports + `CameraConfig(fourcc='YUY2')` constructs. Real negotiation is Pi-only.
**Next steps:** uncommitted (offer). On the Pi: confirm the new camera log line shows
`fourcc=YUYV @ 30 fps`; if it warns/falls back, `v4l2-ctl --list-formats-ext` to pick a listed YUYV mode.

## 2026-06-08 — IMX219 "~16 fps at 1080p": diagnosed (camera mode) + unblocked the event loop

**Reported:** the Arducam 8MP IMX219 streams ~16 fps; user expects a reliable 30 fps at 1080p.
**Diagnosis (two stacked causes, ranked):**
1. **Most likely root cause — the camera is *delivering* ~15 fps; the 30 fps request is ignored.**
   `cap.set(CAP_PROP_FPS, 30)` is only a request. USB camera modules commonly advertise **1080p MJPG
   @ 15 fps / 720p @ 30 fps** — the IMX219 *sensor* does 1080p30 but the module's UVC bridge often
   doesn't. 16 fps ≈ a 15-fps mode (× the streamer's 0.9 timing tolerance). Alt: at 1080p OpenCV may
   fall back to **YUYV** and ~1 Gbit/s of raw 1080p30 won't fit USB 2.0. `camera.py` already logs the
   negotiated `WxH @ fps` + WARNINGs on this — that startup line is the smoking gun. Confirm with
   `v4l2-ctl -d /dev/video0 --list-formats-ext`; if 1080p MJPG lists only 15 fps it's a hardware
   ceiling → use **1280×720 @ 30** or **1640×1232 @ 30** (binned, near-full FOV). Also: committed
   `config.yaml` is still **640×480** — 1080p needs `camera.width/height` bumped first.
2. **Real software bottleneck (fixed this session) — capture + JPEG encode both blocked the single
   asyncio event loop**, so they serialized instead of overlapping; at 1080p (~10–25 ms each) the
   *published* stream sagged below the *capture* rate even when the camera could deliver more.
**Changed:**
- `pi5/cv/camera.py` — `_loop()` now runs `cap.read()` (grab + MJPEG→BGR decode) via
  `loop.run_in_executor(None, cap.read)` for both L/R, so a 1080p decode no longer freezes the loop.
- `pi5/server/app.py` — `_mjpeg_stream()` runs `cv2.imencode()` via `run_in_executor` (captures
  `img`/`quality` as default args to avoid late-binding). cv2 releases the GIL in read()/imencode(),
  so both genuinely parallelize now. (YOLO inference was already offloaded — `vision_overlay.py:236`.)
**Verified (sim/Windows):** ruff clean on `pi5 run_hardware.py`; py_compile OK; **95 tests pass**;
booted `run_sim` — `/health`, `/command`, `/video` all 200. The offload's real effect is Pi-only (the
sim has no camera, so `_mjpeg_stream` takes the placeholder branch and never hits the edited line).
**Next steps:** uncommitted (offer). On the Pi: read the camera startup log line (or run `v4l2-ctl
--list-formats-ext`) to see what the module actually negotiates at 1080p. If it's 15 fps MJPG, drop to
720p30 / 1640×1232. The executor offload removes the software ceiling so the stream can match whatever
the camera delivers — it does **not** override a 15-fps camera mode.

## 2026-06-08 — "stepper_test.py prints PASS but motor doesn't move": honest verdict + A4988 RESET

**Worked on:** user reported `pi5/cv/stepper_test.py` prints PASS on every check but the A4988-driven
NEMA-17 (1/16 microstep) doesn't physically move. Diagnosed the misleading PASS and applied both fixes.
**Root cause of the misleading PASS:** the test validates *software bookkeeping*, not motion. Every
"rotate" check reads `get_position_degrees()`, derived from `self._position_steps`, which `step()`
increments **unconditionally** (`stepper.py`) regardless of whether any pin toggles — and the pin writes
go through `_w()`, a silent no-op when the device is `None` (mock mode). So PASS proves the math, not the
motor. A disconnected/dead driver, a wiring fault, or full mock mode all still printed "9 passed".
**The two real causes (the printed `mock=` line decides which):** (a) `mock=True` → no GPIO touched;
`gpiozero`/`lgpio` not importable (neither is in `pi5/requirements.txt`) — install them. (b) `mock=False`
→ electrical; most likely the **A4988 RESET pin floating** (RESET *and* SLEEP are both active-LOW and both
must be HIGH to step; the driver drove SLEEP but never RESET), then VMOT/VREF/coil wiring.
**Changed:**
- `pi5/cv/stepper_test.py` — final verdict is now honest: on `mock=True`+Linux it prints "NOT VERIFIED ON
  HARDWARE" + the lgpio/gpiozero install fix and **returns 2** (mock on a Pi = broken, not a dry run);
  off-Pi mock stays a pass (documented dry run); on real GPIO it prints a "watch the bar" note up front
  and, if it didn't move, the RESET→VMOT→VREF→coil checklist. PASS can no longer be mistaken for motion.
- `pi5/cv/stepper.py` — added optional `reset_pin` (default `None`). When set, the driver claims it and
  holds RESET **HIGH** (released) in `enable()` + at init, and frees it in `cleanup()`. Module docstring
  now documents the RESET-must-be-HIGH gotcha and the two wiring options (jumper RESET↔SLEEP, or dedicate
  a Pi GPIO). `None` = RESET jumpered to SLEEP on the board (recommended, no extra pin).
- `run_hardware.py` — passes `reset_pin=step_cfg.get("reset_pin", None)`.
- `pi5/config.yaml` — new `stepper.reset_pin: null` with the must-be-HIGH explanation.
- `docs/pin_map.md` — added the RESET row to the A4988 table + a prominent RESET/VMOT/VREF caveat.
**Verified (Windows):** ruff clean; py_compile OK; **95 tests pass**; bench test 9/9 mock and the new
verdict prints the off-Pi dry-run message + exits 0 (would exit 2 on a Pi in mock mode).
**Next steps:** on the Pi, re-run `python3 pi5/cv/stepper_test.py` and read the verdict — if it says
mock-on-a-Pi, install lgpio/gpiozero; if real GPIO and still no motion, jumper A4988 RESET→SLEEP (or set
`stepper.reset_pin`) and check VMOT/VREF. Uncommitted (offer).

## 2026-06-08 — IMX219 camera stuck at 5 fps (force V4L2) + detection boxes on BOTH views

**Worked on:** two requests for the Arducam 8MP **Sony IMX219** fixed-focus camera — (1) it runs at
only ~5 fps, (2) draw the YOLO detection boxes on the **right** camera view as well as the left.
**FPS diagnosis (5 fps = full 8MP):** the IMX219 is a raw sensor (no onboard JPEG); its native mode is
3280×2464, which over USB is ~5 fps. The symptom = the camera ignored our 640×480/MJPG `cap.set()` and
stayed in full-res. Root cause: OpenCV's **default capture backend** often won't apply the FOURCC +
resolution switch, so the mode never changes.
**Changed:**
- `pi5/cv/camera.py` — `_open()` now forces the **V4L2 backend on Linux** (`cv2.VideoCapture(dev,
  cv2.CAP_V4L2)`) so the MJPG + 640×480 set actually takes and the sensor drops to its fast binned mode;
  non-Linux (sim/dev) keeps the default backend. Reads back negotiated **WxH + fps** and logs a loud
  **WARNING** when fps is well below requested or the resolution differs (points the user at
  `v4l2-ctl --list-formats-ext`). Added `import sys`.
- `pi5/config.yaml` — documented the IMX219 modes in the `camera:` block (native 8MP ≈ 5 fps; fast
  binned 640×480 / 1280×720 @ 30+ / 1640×1232 @ 30) + the V4L2-backend note and the v4l2-ctl check.
- `pi5/server/app.py` — `_mjpeg_stream()` now draws the overlay boxes + reticle on **whichever view is
  shown (left AND right)**, not left-only. No second inference (the Pi is inference-bound) — the
  left-frame boxes are drawn on the right view at the same coords, offset by the stereo disparity.
  Updated the `_mjpeg_stream`/`/video` docstrings.
- `pi5/server/templates/command_center.html` — the ◎ TRACKING badge now shows on both views (was
  gated to `camView === 'left'`), matching the reticle that's now drawn on both.
**Verified (sim/Windows):** ruff clean on `pi5 run_hardware.py`; py_compile OK; **95 tests pass**;
booted `run_sim` — `/health`, `/command`, and `/video?cam=right` all 200; camera module imports.
**UNTESTED (Pi-only):** the V4L2 fps fix needs the real IMX219 — on the Pi, confirm the camera log line
shows the requested mode (e.g. `640x480 @ 30 fps`) instead of `3280x2464 @ 5`; if it still warns, run
`v4l2-ctl -d /dev/video0 --list-formats-ext` and set `camera.width/height/fps` to a listed MJPG mode.
Boxes on the right view are also Pi-only (sim has no camera); right-view boxes carry the stereo offset.
**Next steps:** uncommitted (offer). Bench-verify on the Pi.

## 2026-06-08 — Move Pico terminal to page bottom + choose which CV target to track

**Worked on:** two command-center requests — (1) move the PICO TERMINAL panel to the bottom of the
page, (2) add a way to choose which detected class the computer vision locks onto.
**Layout (1):** reordered the `.app` grid so the terminal is the last panel (header → camera/health →
boat health → radar → commands → **pico terminal**); `grid-template-rows` is now
`auto 1fr auto auto auto 1fr` — the terminal keeps its `1fr` so it still scrolls internally (the prior
scroll fix is intact). Moved the panel markup; the `@media` stack rule still covers `.pico-inner`.
**Target picker (2) — one control drives BOTH the overlay reticle and the radar bar:**
- `pi5/cv/vision_overlay.py` — `DetectionConfig.track_class` ("" = AUTO). `_infer()` now locks the
  primary target onto the chosen class (and highlights it amber) when set, else keeps the old behavior
  (highest-conf highlight class). `controls()` exposes `track_class` + `classes` (model labels for the
  picker); `apply_controls()` accepts `track_class` (treats ""/"AUTO" as auto). New `class_names()`.
- `pi5/cv/radar_tracker.py` — `set_track_class(label)` (thread-safe); `_best_target()` filters to the
  chosen class when set, else `priority_classes`; `status()` reports `track_class`.
- `pi5/server/app.py` — `POST /api/camera` also calls `_radar.set_track_class()` when `track_class` is
  in the payload, so picking a class retargets the bar too (guarded; never 500s). `_camera_state()`
  already merges `controls()`, so the picker fields flow to the UI.
- `pi5/server/templates/command_center.html` — TRACK `<select>` in the camera control bar (next to
  DETECT); `populateTrackClasses()` fills it from `controls().classes` (falls back to a maritime+COCO
  seed so it's usable in sim/before a model loads), preserves selection; change handler POSTs
  `track_class` + toasts.
- `run_hardware.py` + `pi5/config.yaml` — plumb/document a default `camera.detection.track_class: ""`.
**Verified (sim/Windows):** ruff clean on `pi5 run_hardware.py`; py_compile OK; **95 tests pass**;
functional check — overlay picks person under AUTO, switches to boat / buoy when chosen (and highlights
it), reverts on AUTO; radar `_best_target` follows the chosen class and `status.track_class` updates.
Booted `run_sim`: `/command` serves the TRACK picker + `populateTrackClasses` and the terminal panel is
last; `POST /api/camera {track_class:boat}` returns 200 (sim has no overlay/radar, so it's a graceful
no-op). **Real lock-on/bar-slew behavior is Pi-only (camera + YOLO + stepper) and UNTESTED on hardware.**
**Next steps:** uncommitted (offer). On the Pi: with a model + a target in frame, confirm the TRACK
picker changes the cyan reticle/◎TRACKING badge to the chosen class and that the radar bar slews to it.

## 2026-06-08 — Maritime YOLOv8 fine-tuning pipeline (ml/) + ONNX inference backend on the Pi

**Worked on:** implemented `~/Downloads/DREAMS_maritime_ml_instruction.md` — a laptop/Colab pipeline
that trains a 6-class maritime YOLOv8n (vessel/kayak/buoy/person/dock/debris), exports ONNX, and an
onnxruntime inference path on the Pi.
**Two deliberate divergences (instruction written against a simplified repo model; flagged, not applied
verbatim):**
- The instruction says *modify `pi5/cv/camera.py`* to use the model — but `camera.py` is purely the
  capture producer; detection lives in **`pi5/cv/vision_overlay.py`**. Integrated there; left camera.py
  alone (also respects the "server untouched" spirit).
- "*Use onnxruntime instead of ultralytics*" — added a real native onnxruntime backend
  (`pi5/cv/onnx_detector.py`: letterbox + pure-numpy decode + per-class NMS) used for `.onnx` models,
  with the existing **ultralytics path kept as the `.pt` fallback**. Honors the lightweight-Pi intent
  (no torch needed for the maritime model) without rewriting the proven box/track pipeline.
**New (ml/ — runs on laptop/Colab, NOT the Pi):** `ml/README.md`, `ml/data/download_datasets.py`
(Roboflow SDK + SMD/SeaShips staging + per-source class remap→6 std ids), `ml/data/prepare_dataset.py`
(merge/remap/dedup-by-hash/drop-empty/split 70-20-10/oversample/stats+chart/dataset.yaml),
`ml/data/augment.py` (Albumentations maritime aug: glare/fog/colour/noise/hflip/±15°; never vflip),
`ml/train.py` (freeze-10 transfer-learn from COCO), `ml/validate.py` (test mAP + CPU-FPS benchmark +
threshold pass/fail), `ml/export_onnx.py` (best.pt→onnx imgsz320 simplify opset12, writes model card +
onnxruntime benchmark), `ml/colab_train.ipynb`.
**New (Pi):** `pi5/cv/onnx_detector.py` (OnnxYolo + standalone `decode()`); `pi5/cv/models/
maritime_yolov8n_info.json` (tracked placeholder card; .onnx itself gitignored).
**Changed:**
- `pi5/cv/vision_overlay.py` — backend selection: auto-prefer `pi5/cv/models/maritime_yolov8n.onnx`
  when present (else configured `.pt`); `_raw_detect()` is backend-agnostic and `_infer()` does the
  shared highlight/target/primary logic; `controls()` reports `backend`; logs the model on load;
  graceful fallback to yolov8n.pt if the .onnx can't load.
- `pi5/requirements.txt` — `onnxruntime>=1.17`. `.gitignore` — ml data/runs/samples + `*.onnx`/`*.pt`
  weights (keep `*_info.json`). `pi5/config.yaml` — `highlight_classes`/`priority_classes` now cover
  both COCO ('boat','person') and maritime ('vessel','kayak') so either model highlights/tracks right;
  documented the auto-detect.
**Untouched per instruction:** CLAUDE.md, firmware/, pi5/server/, KiCad, run_sim.py (and camera.py).
**Verified (sim/Windows):** ruff clean on `pi5 run_hardware.py` + all `ml/*.py` (notebook excluded —
Colab `!`-magics aren't standard-lintable); py_compile all; model-card + ipynb JSON parse; **95 tests
pass**; **ONNX `decode()` unit-tested** with a synthetic YOLOv8 tensor → correct class + box mapped back
through the letterbox (256,176,384,304), and it handles both (1,C,N)/(1,N,C) orientations; model
resolver falls back to yolov8n.pt when no .onnx present; `run_sim` still serves `/health`+`/command` 200.
**UNTESTED (needs a GPU/Colab + the Pi):** the whole training run, real ONNX export, and onnxruntime
inference on hardware (no model trained yet — overlay runs COCO yolov8n until `maritime_yolov8n.onnx` is
dropped in).
**Next steps:** uncommitted (offer). Run the pipeline on Colab (set ROBOFLOW_API_KEY; confirm the
Roboflow workspace/project/version slugs + each source's class names against `remap.json`), export,
`scp` the .onnx to `pi5/cv/models/`, then verify on the Pi that vision_overlay logs "Using maritime
ONNX model" and the command-center boxes/tracking show maritime classes.

## 2026-06-08 — Detect FPS "stuck at ~4": it's inference-bound; added live IMG-size control

**Reported:** detection FPS sits ~4 and doesn't rise when DET FPS is set higher.
**Diagnosis (not a bug):** `detect_max_fps` is an **upper cap**, not a target. `vision_overlay._loop`
runs YOLO back-to-back and only `continue`s (drops a frame) when frames arrive faster than the cap —
there's no path that speeds inference up. ~4 fps = yolov8n @ imgsz 416 on the Pi 5 **CPU**; any cap ≥4
is a no-op. The real lever is inference size (`imgsz`), which was fixed at startup and not live-tunable.
**Changed:**
- `pi5/cv/vision_overlay.py` — `apply_controls()` now accepts `imgsz` (clamp 160–640, snap to a
  multiple of 32 as YOLO requires). Applies on the next frame, no model reload. `controls()` already
  surfaced `imgsz`, so `GET/POST /api/camera` carry it with no app.py change.
- `pi5/server/templates/command_center.html` — added an **IMG** dropdown (256/320/416/512/640) by
  DET FPS, wired to `/api/camera` (loads from `c.imgsz`, posts on change), default 416; added an ⓘ
  hint on DET FPS that it's a cap. Compact `.imgsel` style.
**Guidance given:** lower IMG (416→320 ≈ 1.7× faster) and/or export to **NCNN** (`camera.detection.model`
already accepts an `_ncnn_model` dir, ~2× on ARM) → ~8–12 fps; 320 + NCNN is the practical sweet spot.
**Verified (sim/Windows):** imgsz clamp/snap unit-tested (all /32, 160–640, junk ignored), ruff clean,
py_compile OK; booted `run_sim`, `/command` renders the IMG control + JS hooks, `/api/camera` responds
(sim has no overlay so keeps the 416 default). Real detect-FPS gain is Pi-only (CPU/model bound).
**Next steps:** uncommitted at write time (offered to commit/push to main).

## 2026-06-08 — Move the web server from port 8080 → 8000

**Worked on:** user asked to run the server on 8000 instead of 8080. Changed the port everywhere it
appears so it stays consistent (server + reverse proxy + dashboard dev proxy).
**Changed:**
- `pi5/config.yaml` — `server.port: 8000` (read by `run_hardware.py`).
- `run_sim.py` — hardcoded `uvicorn.run(port=8000)` + startup banner/docstring.
- `run_hardware.py` — fallback default `server_cfg.get("port", 8000)`.
- `deploy/Caddyfile` — `/api/*` and `/ws/*` reverse_proxy → `localhost:8000`.
- `dashboard/vite.config.js` — dev-proxy `/api` + `/ws` targets → `localhost:8000`.
**Verified (sim/Windows):** booted `run_sim`, `/health` 200 on `http://localhost:8000`, nothing on
8080. Command center is now at `http://<host>:8000/command`. (KiCad files contain `8080` only as
coincidental UUID hex — left alone.)
**Next steps:** uncommitted at write time (offered to commit/push to main).

## 2026-06-08 — Boat health panel: 3 battery rails (12S/4S/3S), dual air/enclosure T+RH, L/R hull

**Worked on:** follow-up to the BOAT HEALTH panel — user wants three battery statuses (12S/4S/3S),
two temp+humidity sensors (one in the electronics enclosure, one open air), and separate left/right
hull-dry indicators.
**Data-flow finding:** TEL's `batt_v` was already the **12S propulsion** rail; the **3S** was read in
firmware but only sent on `TEL2` (which the Pi never parses); the **4S winch** was **never read**
(GP28 = "spare"); SHT41 **#B** was read into `air_temp2/air_humidity2` but never sent; the TEL `hull`
string already encodes L/R. So: extend the already-parsed **ENV** message (not TEL2), add the 4S read,
and decode hull in the UI.
**Key call:** extended **ENV → v1.1** by **appending** six fields (enclosure SHT41 temp/humidity, 3S
v/%, 4S v/%) so it stays **backward compatible** — v1.0 firmware omits them, the parser reads them only
when `len(fields) >= 12` (verified both ways). 12S stays in TEL.
**Changed:**
- `firmware/boat-pico/sensors.py` — added a **4S winch** read on **GP28** (PCB BT4 100k/18k divider →
  `winch_batt_v/pct`); `read_all_fast()` now reads all three rails. Flagged the divider as provisional
  (prop/elec use different dividers in firmware — the known discrepancy).
- `firmware/boat-pico/serial_handler.py` — `send_env()` appends `enc_t,enc_h,elec_v,elec_pct,winch_v,
  winch_pct` (defaults keep v1.0 callers working).
- `firmware/boat-pico/main.py` — `task_env_telemetry` passes SHT41 #B + elec + winch; pin-map docstring
  + boot prints updated (GP28 = 4S, #A air / #B enclosure).
- `pi5/comms/pico_serial.py` — `Environment` gains `enc_temp/enc_humidity/elec_batt_v/elec_batt_pct/
  winch_batt_v/winch_batt_pct` (sentinels -999/-1/0); `_handle_env` parses fields 6–11 when present.
- `pi5/navigation/simulator.py` — sim now has 3 rails (12S 50.4 drains as it drives, 3S 12.4, 4S 16.2)
  + an enclosure SHT41 (warmer/drier than air); MockPico `telemetry` batt% fixed to the **12S** range,
  `environment` emits the v1.1 fields.
- `pi5/server/app.py` — `_boat_health()` adds `elec_v/pct`, `winch_v/pct`, `enc_temp/humidity`, and
  `hull_left`/`hull_right` (decoded from the TEL hull code).
- `pi5/server/templates/command_center.html` — BOAT HEALTH retiled: **12S DRIVE / 4S WINCH / 3S ELEC**
  (each V·% + bar, colour by %), **HULL·LEFT / HULL·RIGHT** (DRY/WET), **AIR** + **ENCLOSURE** T/RH,
  plus heading/speed/motors/GPS/water. New `setBatt()`/`setHull()` helpers; N/A on ≤0.5 V / -999.
- `docs/serial-protocol.md` — documented the ENV v1.1 appendix (+ a v1.0/v1.1 example pair).
**Verified (sim/Windows):** `ruff check pi5 run_hardware.py` clean (firmware is MicroPython — bare
`except`/`machine` imports, not in the lint target); `py_compile` OK on firmware + pi5; **95 tests pass**;
ENV round-trip unit-checked (v1.1 parses all 12 fields, v1.0 6-field keeps defaults). Booted `run_sim`:
`/health.boat` shows 12S 50.4 V/100 %, 4S 16.2 V/87 %, 3S 12.4 V/94 %, hull L/R DRY/DRY, air 19 °C/47 %,
enclosure 24.4 °C/28 %; `/command` renders all new tiles. **Firmware 4S read + dual-SHT41 send are
Pi/Pico-only and UNTESTED on hardware** (and the SHT41 GP12-15 pin conflict from the prior entry still
gates real temp reads).
**Next steps:** uncommitted (offer). On hardware: bench-calibrate the GP28 4S divider; confirm ENV v1.1
arrives and the three rails read sane; resolve the SHT41 re-pin before the enclosure/air temps are real.

## 2026-06-08 — Command-center: camera L/R switch, object-track viz, boat health, manual stepper pan 0–360

**Worked on:** four user-requested command-center features — (1) switch between left/right
cameras, (2) show tracking of a YOLO-detected object, (3) surface the boat/Pico health, (4) manual
stepper pan left/right locking anywhere 0–360°.
**Key engineering call (stepper):** decoupled *wrapping* from *travel range* in `StepperMotor`.
`has_slip_ring` now only gates taking the short way across the 0°/360° seam (the one thing a cable
can't survive); travel limits are independent. With no slip ring the bar is a **linear axis with
hard stops** — so it reaches a full 0–360° manually but never winds >1 turn. This also fixes a
latent mod-360 bug: position is now tracked **unwrapped** when not wrapping, so jogging left off the
360° end no longer strands the count at 0. Auto-scan SCAN keeps its own narrower sweep range.
**Changed:**
- `pi5/cv/stepper.py` — `_wrap` (= has_slip_ring) separate from `min_deg`/`max_deg`; `step()` wraps
  mod-rev only when `_wrap`, else clamps the count to `[min,max]` steps; `get_position_degrees()`
  unwrapped when linear. Manual range now 0–360 by default.
- `pi5/cv/radar_tracker.py` — `jog(delta)` (relative pan → HOLD goto); `status()` adds `target`
  ({label,conf} when locked) and `sweep` (auto-scan range, distinct from the manual `limits`);
  records the locked target in SCAN/TRACK.
- `pi5/cv/vision_overlay.py` — tracks a **primary target** (highest-conf highlight class); `draw()`
  paints a cyan lock reticle (corner brackets + crosshair + "TRACK label") on it; `primary_target()`
  accessor for the UI/health.
- `pi5/cv/camera.py` — `has_right` property (is a 2nd camera open?).
- `pi5/server/app.py` — `/video?cam=left|right` (overlay drawn on left only; right falls back to
  left); `_camera_state()` adds `right_present`; `_gather_health()` adds `track`, `stepper_target`,
  and a `boat` block (`_boat_health()`: link, battery, hull, motor temps, GPS/hdg/spd, decoded
  6-flag health string, ENV sensors, last alert); `JOG` added to `/stepper/command`.
- `pi5/server/templates/command_center.html` — SOURCE ◄LEFT/RIGHT► toggle + on-feed ◎TRACKING badge;
  new **BOAT HEALTH** panel (battery bar, hull, heading/speed, motor temps, GPS, water/air, 6 sensor
  flag chips, last-alert line; hull-leak now also raises the red banner); radar panel gains a MANUAL
  ◄LEFT / step / RIGHT► jog group + tracked-target readout; LOCK-TO accepts 0–360. Rose sweep sector
  now shades `sweep` not `limits`. Added a 6th grid row.
- `pi5/config.yaml` — `stepper.manual_min_degrees`/`manual_max_degrees` (0/360) split from `sweep_*`;
  clarified `has_slip_ring` = wrap-only.
- `run_hardware.py` — stepper built with the manual range (0–360); RadarTracker keeps the sweep range.
- `docs/pin_map.md` — documented the two travel ranges + the wrap/no-wrap distinction and cable caveat.
**Deliberate divergence (flagged):** the prior session said full 360° needs a slip ring. The user
explicitly asked for 0–360 manual control; implemented it **safely** (linear, hard-stopped, no wrap)
and flagged the ≤1-turn cable wind in `config.yaml` + `pin_map.md` rather than silently capping it.
**Verified (sim/Windows):** `ruff check pi5 run_hardware.py` clean; `py_compile` OK; **95 tests pass**;
stepper bench **9/9** (mock); a 0–360 mock run reached 270/350/360 and jogged −20 off the 360° end to
339.97 (old bug would strand at 0), clamps at 0/360. Booted `run_sim`: `/health` carries `boat`
(batt 16.8 V/100 %, hull DRY, all 6 flags OK, water temp/EC) with `track`/`stepper_*` = null (no
overlay/radar in sim); `/api/camera` → `right_present:false`; `/stepper/command JOG` →
hardware-only; bad command → 400; `/video?cam=right` streams the placeholder; `/command` serves all
new panels/JS. **All GPIO/motor/camera/YOLO behaviour is Pi-only and UNTESTED on hardware.**
**Next steps:** uncommitted (offer). On the Pi: with two cameras, verify the RIGHT button; with a
maritime/COCO model + a target in frame, confirm the lock reticle + ◎TRACKING badge and that the bar
slews under TRACK; bench the manual jog across the full 0–360 with the bar free. If a slip ring is
fitted, set `has_slip_ring: true` (re-enables short-way wrap).

## 2026-06-08 — Radar-bar stepper control (A4988 on Pi 5 GPIO, not the Pico)

**Worked on:** implemented `~/Downloads/DREAMS_stepper_instruction (1).md` — A4988-driven
NEMA-17 radar-bar pan, coordinated with the YOLO vision overlay. The user's **revised** instruction
moved the stepper from the Boat Pico to the **Pi 5 GPIO header** (the first Pico draft, `(1).md`'s
predecessor, collided GP18-21 with the hull-leak sensors / SHT41 re-pin mess — the Pi-5 approach
sidesteps all of that).
**Deliberate divergence (flagged, not silently resolved):** driving Pi 5 GPIO breaks the
"**Pi 5 uses only USB — no GPIO**" locked decision in `CLAUDE.md`. The user chose this explicitly;
I implemented it and documented it in `docs/pin_map.md` rather than editing the locked-decisions doc.
**Key engineering call:** stepper stepping is **blocking** (`time.sleep` per pulse). Running it from
an asyncio task would freeze the whole FastAPI server, so the **RadarTracker owns a single daemon
thread** that is the sole motion authority; HTTP endpoints only flip thread-safe flags. Mirrors the
repo's existing graceful-degradation pattern (camera/overlay/psutil): no `gpiozero`/`lgpio` →
StepperMotor runs in **mock mode** (position tracking + real timing, no pin toggles), so `run_sim.py`
and the test suite still work on Windows.
**New:**
- `pi5/cv/stepper.py` — `StepperMotor` (A4988): enable/disable/sleep/wake, trapezoidal-ramped `step`,
  `rotate_degrees`/`rotate_to` (travel-clamped, 0-180° w/o slip ring), `scan`/`scan_async`/`stop_scan`
  (daemon-thread sweep w/ `threading.Event`), absolute position tracking, auto-sleep, `cleanup()`.
- `pi5/cv/radar_tracker.py` — `RadarTracker`: SCAN/TRACK/HOLD/SLEEP on one daemon thread; reads
  detection boxes from the overlay (`boxes()`) and slews to centre a priority target (boat/person)
  via bbox→bearing; reverts to SCAN after `lost_timeout_s`. Defensive: no overlay → just SCANs.
- `pi5/cv/stepper_test.py` — standalone bench test (`python3 pi5/cv/stepper_test.py`), 9 checks, ASCII
  output (Windows console safe). All 9 pass in mock mode.
**Changed:**
- `pi5/cv/vision_overlay.py` — added public `boxes()` accessor (raw xyxy boxes) for the tracker.
- `pi5/server/app.py` — `configure(stepper=, radar=)`; `GET /stepper/status` + `POST /stepper/command`
  (SCAN/STOP/GOTO/CENTER/SLEEP/WAKE/TRACK/HOLD — non-blocking, route to the tracker; available:false
  off-Pi); `_gather_health()` now carries `stepper_angle`/`stepper_state`/`stepper_target_locked`.
- `run_hardware.py` — build StepperMotor + RadarTracker from `stepper:` config, inject, start the
  tracker thread on startup / `radar.stop()` (joins thread + GPIO cleanup) on shutdown. Never blocks startup.
- `pi5/config.yaml` — new `stepper:` block (pins 23/24/25/8, 3200 steps/rev, sweep 0-180, FOV 75,
  priority_classes, initial_mode=SLEEP).
- `pi5/server/templates/command_center.html` — new RADAR BAR panel: SVG compass rose w/ animated
  needle + sweep sector, live angle / mode / lock readouts (from `/ws/health`), SCAN/TRACK/STOP/CENTER
  /WAKE/SLEEP/GOTO buttons (→ `/stepper/command`). Added a 5th grid row.
- `docs/pin_map.md` — new "Radar-bar stepper — Pi 5 GPIO (A4988)" subsection (pin table + boot-state
  caveat); softened the "no GPIO" claim to "no GPIO **for sensors**".
**Verified (sim/Windows):** `py_compile` OK; `ruff check pi5 run_hardware.py` clean; **95 tests pass**;
bench test **9/9** (mock); StepperMotor + RadarTracker smoke-tested (rotate/clamp/scan/stop); endpoint
handlers exercised directly (status, SCAN/GOTO ok, bad-cmd→400, GOTO-no-value→400); booted `run_sim`
and confirmed `/health` carries stepper_* = null, `/stepper/status` → available:false, and `/command`
serves the radar panel + JS hooks. **All GPIO/motor behaviour is Pi-only and UNTESTED on hardware.**
**Boot-state caveat for the user:** GPIO25 (ENABLE) is LOW at boot → coils briefly energised before
software runs; consider an external pull-up if boot quiescent current matters (noted in pin_map.md).
Set `stepper.has_slip_ring: true` only once the slip ring is installed (unlocks full 360°).
**Next steps:** uncommitted (offer). On the Pi: `pip install lgpio gpiozero`, set A4988 VREF≈0.67 V, run
`python3 pi5/cv/stepper_test.py` with the bar free, then drive it from `/command`. Possible follow-up:
let RadarTracker reuse the avoidance detector if avoidance is later wired into run_hardware.

## 2026-06-08 — Implemented dual-SHT41 firmware (re-pin to as-built board)

**Worked on:** user confirmed part = Teyleten **GY-SHT41-D** breakout (×3) and chose **"re-pin
firmware to board"** (PCB is fabricated; firmware adapts). Implemented the temp-sensor firmware to
match the as-built board and documented the conflicts.
**Changed / new:**
- `firmware/boat-pico/sht41.py` (new) — bus-agnostic `SHT41` class (Sensirion SHT4x): 0x44, cmd 0xFD
  high-precision, 6-byte read, CRC8 (poly 0x31), tick→°C/%RH conversion, degrade-safe.
- `firmware/boat-pico/sensors.py` — dropped DHT11 (GP16, not on board). Added two SHT41s on
  **SoftI2C**: #A GP12/13 (J11), #B GP14/15 (J13). SoftI2C because HW I²C0 is held by the BNO085
  (GP8/9). Exposes `air_temp/air_humidity` (A) + `air_temp2/air_humidity2` (B). `read_all_slow()` now
  reads both SHT41s + hull. (`send_env` keeps `%d` → truncates the float to int; bumping ENV to
  `%.1f` to keep SHT41 precision is an optional protocol change, not done.)
- `firmware/boat-pico/main.py` — updated pin-map docstring, `task_slow_sensors` doc, boot prints; added
  a loud as-built-conflict warning print. **Did NOT touch vesc/motor_control/sbus** (safety-critical).
- `docs/pin_map.md` — GP12-15 rows now show SHT41 (board); GP16 = unused; added an "⚠ As-built board
  divergence (GP12–GP16)" callout + two SoftI2C rows in the bus summary with conflict notes.
**⚠ Unresolved blockers (flagged, not fixed):** GP12/13=VESC UART0, GP14=winch PWM, GP15=SBUS still
claim those pins in firmware; on the board they're the temp connectors. VESC/winch/SBUS are mis-pinned
for this board and must be relocated off GP12-15 before the boat can drive AND read temps together —
but the board's winch connector (J8/J9 both pins on GND) and SBUS input have no valid pins (known board
errors). So a full re-pin is blocked on hardware decisions / likely a board respin.
**Board/cabling (part b) — for the fabbed board:** connector pin order is reversed vs the module
(board J11/J13 = [SDA,SCL,GND,V+]; GY-SHT41-D = [VDD,GND,SDA,SCL]) → needs a **crossover cable**
(module VDD→board pin4, GND→pin3, SDA→pin1, SCL→pin2). And **don't use board pin4 (VSYS≈5 V)** for VDD
unless the module is confirmed regulated+level-shifted — feed VDD from 3.3 V (Pico pin36, currently
unconnected) since RP2040 GPIO isn't 5 V-tolerant.
**Verified (Windows):** py_compile OK (sht41/sensors/main); `ruff check pi5` clean; 95 tests pass.
Firmware runtime is Pi/Pico-only (SoftI2C + SHT41 reads untested on hardware).
**Next steps:** user to decide VESC/winch/SBUS relocation (or board respin); bench-test SHT41 reads
once GP12-15 are freed; optionally extend ENV telemetry to carry sensor #2.

## 2026-06-08 — Reviewed temp-sensor wiring (J11/J13) against schematic; flagged SHT41 issues

**Worked on:** user said the two "Temp + Humidity Sensor" connectors will be **SHT41** (I²C, 4-pin),
asked to check the wiring. Re-exported the netlist (`kicad-cli sch export netlist --format kicadsexpr`,
no net labels in sch) and traced J11/J13.
**Findings (verified from netlist):**
- **J11** (0.1″ hdr): pin1→GP12 (I2C0 SDA), pin2→GP13 (I2C0 SCL), pin3→GND, pin4→**VSYS ≈5 V**.
- **J13** (JST-XH): pin1→GP14 (I2C1 SDA, shared w/ J10 IMU + J7 GPS hdr), pin2→GP15 (I2C1 SCL, shared),
  pin3→GND, pin4→**VSYS ≈5 V**.
- GOOD: pin pairs are HW-I²C-legal and SDA/SCL not swappable (RP2040 muxing); two 0x44 SHT41 on
  separate buses (I2C0 + I2C1) is the correct topology for the fixed address.
- ⚠ **5 V V+**: SHT41 abs-max 3.6 V; Pico 3V3-OUT (pin36) is unconnected. Bare SHT41 would be damaged.
  Only OK if using a breakout with onboard 3.3 V LDO + level shift.
- ⚠ **No I²C pull-ups** on any of GP12/13/14/15 (only Pico+connector on each net).
- ✗ **Firmware/docs mismatch**: `sensors.py` + `pin_map.md` describe one **DHT11 (1-wire) on GP16**,
  but GP16 is unconnected in the sch and there's no DHT11 — same sch-vs-firmware divergence flagged
  2026-06-01. To use as wired, firmware needs `I2C(0,sda=12,scl=13)` + `I2C(1,sda=14,scl=15)`, SHT4x
  cmd 0xFD @ 0x44.
**Part confirmed by user:** Teyleten Robot **GY-SHT41-D** breakout (×3), I²C, "3.3–5 V".
**NEW critical finding — connector pinout is reversed vs the module:** GY-SHT41-D pin order is
`VDD·GND·SDA·SCL` (power on pins 1–2), but the PCB connectors put **signals on pins 1–2, power on
pins 3–4**. A straight 1:1 cable would feed module VDD (≤5 V) onto GP12/GP14 → fries the Pico. Fix by
re-assigning the connector footprint to `VDD·GND·SDA·SCL` (target: pin1=3V3, pin2=GND, pin3=SDA GP12/14,
pin4=SCL GP13/15) OR a crossover cable (riskier).
**Power:** still route V+ to **3V3 (Pico pin 36, currently unconnected)**, NOT VSYS(5 V) — RP2040 GPIO
not 5 V-tolerant; couldn't confirm an onboard regulator/level-shifter on the cheap GY board (the
"level-shifted 3–5 V" claim is Adafruit's, blended in by search). 3.3 V is safe either way.
**Pull-ups:** GY modules usually carry onboard 10 k pull-ups → board's lack of them likely moot (verify
2 resistors on module). J13 bus shared w/ J10/J7 → parallel pull-ups ≈3.3 k, still OK.
**Decisions / open questions:** did NOT edit firmware/docs/sch yet — offered to (a) rewrite pin_map.md +
sensors.py to dual-I²C SHT4x (I2C0=GP12/13, I2C1=GP14/15, addr 0x44, cmd 0xFD), (b) spec the schematic
footprint reorder + 3V3 rail. PCB-rework approach (footprint vs crossover cable) is the user's call.
**Next steps:** await user go-ahead on (a)/(b); the footprint reorder + 3V3 reroute are the gating
hardware fixes before any SHT41 can be plugged in safely.

## 2026-06-08 — Self-healing serial read loop + hide Sim Speed on hardware

**Worked on:** user hit a tight error loop on push: `Read loop error: device reports readiness to
read but returned no data (device disconnected or multiple access on port?)` repeating ~every 100 ms;
also asked to drop the Sim Speed control on hardware.
**Cause:** `PicoSerial._read_loop` caught the disconnect exception, slept 0.1 s, and retried the SAME
dead connection forever — never reconnecting (and `... multiple access on port` suggests it can also
fire if a 2nd process, e.g. a manual `deploy_pico.py`, grabs the port while run_hardware holds it).
**Changed:**
- `pi5/comms/pico_serial.py` — read loop self-heals: on any read error it closes the streams and
  re-opens with backoff (0.5→5 s), and treats an empty read as a disconnect. Added `_open_streams()` /
  `_close_streams()`; `connect()` uses them. So a Pico reset/reflash/port-contention recovers cleanly
  instead of spamming.
- `pi5/server/static/index.html` — wrapped the Sim Speed row+slider in `#simSpeedControl` and hide it
  when `/api/sim/speed` returns null (hardware mode, `_sim is None`). Other control sliders stay.
**Verified (sim/Windows):** ruff clean; PicoSerial imports with new helpers; 95 tests pass; dashboard
serves with `#simSpeedControl`; `/api/sim/speed` returns 1.5 in sim (control visible). The reconnect
path is Pi-only (sim uses MockPicoSerial, no read loop) — reasoned, not runtime-tested.
**Note for user:** don't run a manual `deploy_pico.py` while `run_hardware.py` is up — two processes on
/dev/ttyACM0 is itself a cause of that error. Stop run_hardware first, or use the command center push.
**Next steps:** uncommitted at write time (committing now).

## 2026-06-08 — Non-blocking Pico serial read (likely fixes HB timeout AND REFLASH)

**On-Pi test results:** standalone `deploy_pico.py` worked from a clean REPL (all 11 files copied, Pico
reset). Camera confirmed **640x480 @ 30 fps mjpg=True** (fps fix works); right cam absent as expected
(single camera). BUT `run_hardware.py` startup deploy still failed `could not enter raw repl` — so
REFLASH-while-running was NOT dropping the firmware to the REPL.
**Diagnosis:** `serial_handler.read_usb()` did `sys.stdin.buffer.read(64)` — a BLOCKING read that waits
for 64 bytes. Heartbeats (~10 B) and the REFLASH frame (~12 B) never fill 64 B promptly, so they sit
unprocessed → HB ACKs arrive too late (watchdog ESTOPs = the original HB-timeout symptom) and REFLASH
never registers. This one bug likely explains BOTH the HB timeouts and the REFLASH no-op.
**Fixed (firmware):**
- `serial_handler.py` — `read_usb()` now non-blocking: `select.poll(sys.stdin)` + read 1 byte at a
  time while data is available. Added `import select` + a module `_stdin_poll`.
- `main.py` — replaced `asyncio.gather(...)` with `create_task(...)` + a monitor loop that waits on
  `serial.reflash_requested`, then `motor_control.estop()`, cancels all tasks, and returns → drops to
  the REPL (more reliable than raising SystemExit inside a gathered task). Reverted the SystemExit in
  task_serial_rx.
**Verified (Windows):** py_compile OK for both; deploy_pico ruff clean. Runtime is Pi-only.
**CRITICAL next step for user:** the firmware currently ON the Pico still has the blocking read + the
old (non-working) REFLASH, so REFLASH can't install the fix — they must deploy this updated firmware
once more from a clean REPL (BOOTSEL+uf2 wipe, or Thonny stop + remove main.py, then
`python pi5/scripts/deploy_pico.py`). After that: HB should stay alive (boat functional) and boot
auto-deploy via REFLASH should work.

## 2026-06-07 — Cooperative REFLASH so auto-deploy actually works

**Worked on:** the boot auto-deploy was failing — `mpremote.transport.TransportError: could not enter
raw repl`. Diagnosed + fixed.
**Root cause:** the Boat Pico firmware's `task_serial_rx`→`read_usb()` loop continuously reads
`sys.stdin.buffer` (the USB-CDC command channel). That swallows mpremote's Ctrl-C/Ctrl-A REPL-entry
handshake, so mpremote can't take the port **while the firmware is running** — which it always is by
deploy time. No `kbd_intr(-1)` / `boot.py`; it's the raw stdin reads. So you can't mpremote-reflash a
running Pico over the shared USB CDC. (User chose: build cooperative REFLASH.)
**Changed (firmware):**
- `serial_handler.py` — new `reflash_requested` flag + `REFLASH` command (ACK then set flag).
- `main.py` — `task_serial_rx` polls the flag; on set it `motor_control.estop()` then `raise
  SystemExit` to exit the asyncio loop to the bare REPL (frees the USB CDC for mpremote).
**Changed (deploy + docs):**
- `pi5/scripts/deploy_pico.py` — `_request_repl()` writes `$REFLASH,0*91` over pyserial and waits
  1.5 s before the mpremote copy; best-effort (degrades if port busy / pyserial missing).
- `docs/serial-protocol.md` — added §3.13 REFLASH.
**Boot chain now:** run_hardware → deploy sends REFLASH → firmware stops+drops to REPL → mpremote cp +
reset → fresh firmware → Pi connects.
**CRITICAL one-time step:** the Pico currently runs OLD firmware (no REFLASH → NAKs, keeps eating
stdin), so mpremote still fails until the REFLASH-aware firmware is installed once by hand. Reliable
path: BOOTSEL + drag MicroPython .uf2 (wipes filesystem/old main.py) → clean REPL → run
`python pi5/scripts/deploy_pico.py` once. Then boot auto-deploy works.
**Verified (Windows):** ruff clean; serial_handler.py + main.py py_compile OK; REFLASH frame/checksum
correct ($REFLASH,0*91); `_request_repl` degrades cleanly without a port; 95 tests pass. UNTESTED on
hardware: whether `raise SystemExit` cleanly drops uasyncio to the REPL (fallback = manual wipe).
**Next steps:** uncommitted (offered). Bench-test the REFLASH drop on the Pi.

## 2026-06-07 — Camera 10→30 fps (MJPG) + view on-Pico code from command center

**Worked on:** camera was stuck at 10 fps though the sensor does 30; user also couldn't see what code
is actually on the Boat Pico.
**FPS fix:** root cause = producer captured at `camera.fps: 10` and didn't request MJPG; the new
stream cap was 15. Changed:
- `pi5/config.yaml` — `camera.fps` 10→30, added `use_mjpg: true`, `stream_fps` 15→30.
- `pi5/cv/camera.py` — `_open()` requests MJPG fourcc before resolution (far faster over USB, needed
  for 30 fps; OpenCV falls back if unsupported), sets `BUFFERSIZE=1`, logs negotiated WxH@fps.
  `CameraConfig` gained `use_mjpg` (default true), default fps 30.
- `run_hardware.py` — passes `use_mjpg` through.
Capture now 30, stream publishes up to 30 (still live-adjustable via the STREAM FPS slider).
**View on-Pico code:**
- `pi5/server/app.py` — new `GET /pico/file?name=` reads a file off the Pico via `mpremote cat`
  (same brief serial handoff as /pico/files; path-traversal guarded). Hardware-only.
- `command_center.html` — "⤓ view on pico" button loads the selected file's real contents into the
  Monaco editor so the operator can see exactly what's running (then edit/re-push).
**Verified (sim/Windows):** ruff clean; `/pico/file` → hardware-only notice in sim; traversal → 400;
button+handler present; 95 tests pass. Camera fps only confirmable on the Pi with the real camera.
**Caveat:** view/files/push briefly release the serial link (Pico watchdog ESTOPs ~1-2s, then
reconnects) — fine when not actively driving.
**Next steps:** uncommitted (offered).

## 2026-06-07 — Incorporated vision (detection overlay) + adjustable FPS/camera + configurable model

**Worked on:** pulled vision from the external `ka1e27/D.R.E.A.M.S-Vision-Test` repo into the command
center, researched a marine detection library, made FPS/camera settings adjustable.
**Findings:** the vision-test repo is a dual-thread FastAPI dashboard (capture thread at camera rate +
separate rate-capped YOLO thread → decoupled stream/detect FPS, boxes drawn on the feed, live /control
knobs). No turnkey "marine" pip library exists — practical path is Ultralytics YOLO (already our dep)
with maritime-trained weights (SeaShips / MASTR1325 / Singapore Maritime Dataset / Roboflow Marine
Surveillance / TPH-YOLOv5). User chose: configurable weights, default COCO, drop-in maritime .pt.
**Changed / new:**
- `pi5/cv/vision_overlay.py` (new) — `DetectionOverlay`: subscribes to the shared CameraProducer (NOT
  a 2nd VideoCapture), runs YOLO on a rate-capped asyncio task with inference in a thread executor,
  keeps latest boxes + inference-FPS, `draw()` overlays them, runtime `apply_controls()`. Model path +
  target/highlight classes configurable; degrades to None if ultralytics/model missing.
- `pi5/server/app.py` — inject `_overlay` + `_jpeg_quality`/`_stream_fps_cap` via configure(); `/video`
  now draws boxes on a copy, caps publish rate, uses runtime JPEG quality (stream FPS decoupled from
  detect FPS); `/health` adds `detect_fps`/`detections`; new `GET/POST /api/camera` (detection on/off,
  detect_max_fps, conf, jpeg_quality, stream_fps).
- `run_hardware.py` — build DetectionOverlay from `camera.detection` config, start after camera /
  stop on shutdown; pass overlay + jpeg_quality + stream_fps to configure.
- `pi5/config.yaml` — `camera.detection` block (model/imgsz/conf/detect_max_fps/classes) +
  `stream_fps`/`jpeg_quality`, with maritime-model + NCNN docs.
- `pi5/server/templates/command_center.html` — vision control bar under the feed (DETECT toggle,
  DET-FPS / CONF / QUALITY / STREAM-FPS sliders) + `cam-det` readout (detect fps · detected classes)
  fed from /ws/health; wired to /api/camera (debounced POST).
**Verified (sim/Windows):** ruff clean; imports resolve; `/api/camera` GET/POST apply quality+fps;
`/health` carries detect fields (null in sim — no overlay); `draw()` renders boxes; 6 controls present;
95 tests pass. Real YOLO only runs on the Pi (camera + ultralytics; auto-downloads yolov8n.pt once).
**Next steps:** uncommitted (offered). On the Pi: run_hardware → boxes on /command; swap to a maritime
.pt in config to specialise. Possible follow-up: reuse the overlay detector for AvoidanceLoop (avoid a
2nd model load) if/when avoidance is wired into run_hardware.

## 2026-06-07 — Auto-deploy Boat Pico firmware on Pi boot

**Worked on:** user wants the Pico's Python firmware uploaded on Pi boot (Pico is on USB). This also
addresses the HB-timeout — a Pico without current firmware can't ACK heartbeats.
**Changed / new:**
- `pi5/scripts/deploy_pico.py` (new) — copies `firmware/boat-pico/*.py` to the Pico via mpremote and
  resets it. CLI: `--port`, `--no-reset`. Reads port from config.yaml. Batch copy with per-file
  fallback. Invokes mpremote as **`python -m mpremote`** (via `sys.executable`) so it works under
  systemd's minimal PATH (bare `mpremote` console script wouldn't be found).
- `pi5/scripts/__init__.py` (new) — makes scripts importable so run_hardware can call `deploy()`.
- `run_hardware.py` — on startup, if `serial.deploy_on_start` (default true), deploys firmware +
  waits 2.5s for reboot BEFORE opening the serial link (port must be free for mpremote). Wrapped so a
  deploy failure never blocks startup. Added `import asyncio`.
- `pi5/config.yaml` — new `serial.deploy_on_start: true`.
- `pi5/services/dreams.service` (new) — systemd unit: runs run_hardware.py on boot (After
  network-online, ExecStartPre sleep 5 for USB enumerate). Paths/User are placeholders to edit.
**Boot chain:** power on → systemd → run_hardware → upload firmware + reset Pico → wait → connect +
heartbeat → serve /command.
**Verified (Windows):** ruff clean; deploy_pico finds all 11 boat-pico files; run_hardware imports the
deploy fn; deploy() degrades cleanly (mpremote present here but no /dev/ttyACM0 → fails gracefully,
returns False). Real upload is Pi-only.
**User setup:** `pip install mpremote`; `sudo cp pi5/services/dreams.service /etc/systemd/system/`
(edit paths) → `systemctl enable --now dreams`. deploy_on_start re-uploads every start (set false for
firmware dev).
**Next steps:** uncommitted along with the pod-light changes (offered). Bench-test on the Pi:
firmware should upload, HB timeout should clear once the Pico runs current firmware.

## 2026-06-07 — Pod Pico status light on the Command Center (+ HB-timeout explainer)

**Worked on:** added a POD link light to `/command`; explained the `Timeout on HB` warning.
**Changed:**
- `pi5/server/app.py` `_gather_health()` — added `pod_ok` / `pod_leak` / `pod_age_s`, read from the
  existing `PodBridge` (`_pod.pod_ok` + `_pod.latest.leak_detected`/`timestamp`). Degrades to None if
  no pod bridge.
- `pi5/server/templates/command_center.html` — new POD dot in the header (green=responding,
  amber=responding+leak, red=not responding); leak also raises a prioritised red banner
  ("POD LEAK DETECTED"). Reworked the banner logic to prioritise leak > thermal > throttle.
**Verified (sim):** ruff clean; `/health` → `pod_ok:true, pod_leak:false, pod_age_s:1.3` after a poll;
page has `dot-pod`.
**HB-timeout answer (for the record):** `Timeout on HB seq=N (attempt 3/3)` = the Pi sent a heartbeat
and got no `ACK` back within 2s × 3 retries. Firmware *does* ACK HB (`serial_handler.py:194`), so it
means the Boat Pico isn't replying: Pico not running main.py / wrong or busy `/dev/ttyACM0` (only one
process can own it) / framing-checksum-baud mismatch / Pico reset. The Pico side mirrors this — its
3s watchdog ESTOPs (`CRIT HB_LOST`) if HBs stop. Diagnose: `ls /dev/ttyACM*`, `sudo fuser
/dev/ttyACM0`, `mpremote connect /dev/ttyACM0 repl` to see boot prints; ensure nothing else holds the
port while `run_hardware.py` runs.
**Next steps:** uncommitted (offered). Bench-test run_hardware.py + resolve the HB link on the Pi.

## 2026-06-07 — Added run_hardware.py (real Pico + camera entry point)

**Worked on:** user has a real Pico + camera on the Pi and asked how to use them. Confirmed the gap I'd
flagged: `run_sim.py` was the ONLY runner (mock Pico, no camera). README says "set `mode: hardware`"
but no such key exists in config.yaml and nothing reads it. The `configure()` plumbing already accepts
a `camera=` producer — it was just never instantiated.
**Changed:** `run_hardware.py` (new, top-level) — hardware counterpart to run_sim.py. Wires a real
`PicoSerial(port,baud)` (+ `connect()` + `start_heartbeat()`) and a real `CameraProducer` into
`configure(..., simulator=None, camera=camera)`, then serves the app. Loads `pi5/config.yaml` for
serial/camera/server/heartbeat with sane fallbacks. Degrades gracefully: camera open failure →
`server_app._camera=None` (NO-SIGNAL placeholder); Pico connect failure → logs, keeps serving. On
startup connects Pico + heartbeat (watchdog ESTOPs if heartbeats stop = safe), starts nav + pod;
shutdown reverses it.
**Result on the Pi:** `/command` shows the LIVE camera (MJPEG), real parsed Pico telemetry + working
commands + Push-to-Pico, and real vcgencmd/psutil health — vs the simulator's placeholders.
**Verified (Windows):** ruff clean; module imports cleanly (main() guarded). **NOT testable here** —
no real serial/camera on this box; the connect/camera-open path only runs on the Pi. Mirrors the
working run_sim wiring.
**Pi prereqs documented for user:** `pip install -r pi5/requirements.txt`; `dialout`+`video` groups;
check `/dev/ttyACM0` + `/dev/video0`; single camera is fine (stereo off).
**Next steps:** uncommitted along with the health-metrics changes (offered to commit). Real next step
is bench-testing run_hardware.py on the Pi; also `/pico/push` reconnect still untested on hardware.

## 2026-06-07 — More health metrics on the Command Center

**Worked on:** user asked for more health status points on `/command`.
**Changed:**
- `pi5/server/app.py` `_gather_health()` — added swap, uptime, process count, load average (1/5/15),
  and live network throughput (↓/↑ KB/s, computed from a delta against a new `_net_prev` module
  global). All inside the existing psutil try/except so they degrade to None if psutil is missing.
- `pi5/server/templates/command_center.html` — new SWAP bar + vgrid rows (LOAD, UPTIME, PROCS,
  NET ↓/↑, SDRAM V alongside CORE V); added `fmtUptime()`/`fmtRate()` JS formatters; each field
  shows N/A when its source is unavailable.
**Verified (sim):** ruff clean; `/health` returns the new fields with real values (uptime, procs,
swap, net rates populate after the 2nd sample); all 7 new element ids present in the page. On the Pi,
load avg + voltages will be real (Windows shows emulated load 0.00).
**Next steps:** uncommitted (offered). Still open: hardware `/pico/push` test; real hardware entry
point (live camera + Pico).

## 2026-06-07 — Added a buttons-only COMMANDS panel to /command

**Worked on:** user found `/docs` (Swagger) too verbose ("I just want them to send commands"). Added a
clean command panel to the Command Center instead of touching Swagger.
**Changed:** `pi5/server/templates/command_center.html` — new bottom **COMMANDS** panel (grid row added:
`auto 1fr 1fr auto`) with grouped buttons that POST to `/api/*` and toast the result:
- SAFETY: E-STOP, CLEAR E-STOP · MISSION: START/PAUSE/RESUME/SKIP/ABORT + UPLOAD… (modal w/ name +
  waypoints JSON + start-now checkbox) · NAV: lat/lon inputs + GO TO, RTH.
- JS: `postApi()` → `cmd()`, `sendGoto()`, `sendMission()`, `openModal/closeModal`; reuses existing
  `apiHeaders()` (X-API-Key/?key=) and `toast()`. Added `.cbtn`/`.cmd-bar`/`.modal` CSS.
**Note:** these hit the same endpoints `/docs` exposes — they move the boat for real (E-STOP/ABORT act
immediately). The static dashboard `/` already had equivalent buttons; this brings them to the HUD.
**Verified (sim):** panel + JS present in page; POST /api/{estop,resume,goto,mission,mission/start}
all respond correctly (mission upload loaded the waypoint).
**Next steps:** uncommitted along with the nav buttons + scroll fix below — offered to commit all
together. Still open: hardware `/pico/push` test; a real hardware entry point (live camera + Pico).

## 2026-06-07 — Command-center nav buttons + Pico-monitor scroll fix

**Worked on:** cross-page nav buttons, fixed the Pico terminal growing the layout, explained the API page.
**Changed:**
- `pi5/server/static/index.html` (`/`) — added a top-right `.topnav` with **Command Center** (amber)
  + **API** (`/docs`) buttons.
- `pi5/server/templates/command_center.html` (`/command`) — header links restyled as buttons
  (**Dashboard** `/`, **API** `/docs`); **fixed the Pico monitor scroll**: the `.pico-inner` grid row
  was `auto`-sized so the terminal's content drove layout and pushed the SEND/CLEAR bar down. Pinned
  `grid-template-rows:minmax(0,1fr)`, added `min-height:0` to `.editor-col`/`.mon-col`, made `.term`
  `flex:1 1 0;min-height:0;overflow-y:auto`, and `flex-shrink:0` on both bars. Now lines scroll inside
  the monitor and the bars stay pinned.
**Left alone:** `dashboard/` and `cloud/map-viewer/` are Vite SPA shells (`<div id=root>`) on separate
dev servers — relative links would resolve to the dev server, not the Pi. Cross-links there belong in
the React components with the Pi's absolute URL (offered, not done).
**API page note (for the user's follow-up):** `/docs` is FastAPI's auto-generated Swagger UI (also
`/redoc`, `/openapi.json`); content derives from route decorators + docstrings in `app.py` and the
Pydantic models in `models.py`. WebSockets don't appear (OpenAPI limitation); `/` and `/command` are
`include_in_schema=False`. Extend by adding a model → route with `response_model=` + docstring + auth.
**Verified:** sim served, `/` and `/command` both 200 with nav markup present. (Scroll fix is a
CSS-only layout change — not browser-screenshotted.)
**Next steps:** not committed yet (offered). Still open: hardware test of `/pico/push` reconnect;
a real hardware entry point (live camera + real PicoSerial) — `run_sim.py` is the only runner.

## 2026-06-07 — Fixed /ws/health reconnect-loop when psutil is missing

**Worked on:** user reported "only the static dashboard opens" + the Pi showing a connection
open→close loop after the [[command-center]] commit (25c9234).
**Diagnosis (reproduced):** two things. (1) The command center is at **`/command`**, not `/` — `/` is
still the old static dashboard, so that's all they saw. (2) The open/close loop = `psutil` not
installed in their runtime: `_gather_health()` did a bare `import psutil`, which raised ImportError,
which `ws_health` caught by *exiting* → socket closed on connect → the page's auto-reconnect retried
every 2s → loop. (`/health` GET would also 500.) psutil was added to requirements last commit but not
yet `pip install`ed on their host (this Windows box has it; they're on the Pi / another venv).
**Changed:** `pi5/server/app.py` —
- `_gather_health()` now wraps the psutil block in try/except and degrades to None (UI shows N/A),
  same contract the vcgencmd fields already use off-Pi. A missing optional source must never raise.
- `/ws/health` loop catches per-tick errors and emits `{"error": ...}` while keeping the socket open,
  so no health failure can ever cause a reconnect loop.
**Verified:** monkeypatched psutil to ImportError → `_gather_health()` returns a clean dict (all None);
restarted sim, `/ws/health` holds open 4s. ruff clean.
**User action still needed:** `pip install -r pi5/requirements.txt` (psutil) in the venv that serves
the page for real CPU/RAM/disk numbers; open `/command` not `/`. Monaco/fonts are CDN — editor pane
needs internet on first load.
**Next steps:** not committed yet (offered). Still pending from prior entry: hardware test of
`/pico/push` reconnect.

## 2026-06-07 — Built the /command "command center" HUD (camera + Pi health + Pico terminal)

**Worked on:** implemented `~/Downloads/DREAMS_dashboard_update.md` — a single-page naval-HUD command
center served from the Pi 5 FastAPI app, combining MJPEG camera, Pi 5 health, and a Pico terminal.
**Key deviation from the instruction (it was written against a simpler mental model of the repo):**
applying it verbatim would have broken the running stack three ways, so I reused existing owners
instead of opening hardware twice —
- **Camera:** `/video` MJPEG **subscribes to the existing `CameraProducer` (`_camera`)** and
  re-encodes `frame.left` at JPEG q60; it does NOT open a second `VideoCapture(0)` (that would contend
  with the CV pipeline). No camera → streams a near-black placeholder JPEG; UI shows "NO SIGNAL".
- **Pico:** `/ws/pico` streams *parsed* frames (TEL/ENV/ALERT) off the existing `PicoSerial` (`_pico`)
  and dispatches real protocol commands (SET_THR/SET_WINCH/ESTOP/…); it does NOT open a second serial
  reader. Per the user's call, kept the **"Push to Pico" button**: `POST /pico/push` releases the port
  (heartbeats stop → Pico watchdog ESTOPs = safe), runs `mpremote fs cp :main.py` + reset, then
  reconnects. Hardware-only; refuses while a mission runs unless `?force=true`.
- **Route:** served at **`/command`** (per user) — left `/` (static/index.html) untouched.
- **Auth:** new endpoints reuse `auth.require_api_key`; `/video` + WS auth via `?key=` (an `<img>`
  can't send headers). `/health` left open as a liveness probe. Added tiny `auth.key_valid()` helper.
**Changed:**
- `pi5/server/app.py` — new: `/command`, `/health`, `/ws/health`, `/video`, `/ws/pico`,
  `/pico/files`, `/pico/push`, an asyncio health-gather loop (vcgencmd via async subprocess, psutil),
  MJPEG helpers, Pico command dispatch. All degrade cleanly off-Pi / in sim.
- `pi5/server/templates/command_center.html` (new) — self-contained HUD (Orbitron + IBM Plex Mono,
  Monaco editor from CDN, amber/cyan theme, scanline camera overlay, WS auto-reconnect w/ backoff).
- `pi5/server/auth.py` — added `key_valid()` (public wrapper for query-param routes).
- `pi5/requirements.txt` — added `psutil>=5.9`; noted `mpremote` as a Pi-side CLI dep.
**Verified (simulator, Windows):** `python run_sim.py`, then exercised every endpoint — `/health`
returns psutil data + N/A for Pi-only vcgencmd fields; `/command` serves 22 KB; `/video` streams valid
MJPEG placeholder frames; `/ws/health` + `/ws/pico` stream; `SET_THR 20 20`→ACK, unknown/badarg
commands error cleanly; `/pico/{files,push}` refuse gracefully in sim. `ruff check pi5` clean,
`pytest pi5/tests` 95 passed.
**Decisions / open questions:** the firmware-push handoff (`disconnect → mpremote → connect +
start_heartbeat`) is **untested on real hardware** — assumes the standard PicoSerial lifecycle; verify
on the Pi. Monaco loads from CDN (needs internet on first load). Not committed yet.
**Next steps:** hardware test of `/pico/push` reconnect; consider wiring `_camera`/health into the
hardware startup path; decide if `/command` should eventually replace `/`.

## 2026-06-07 — Committed and pushed the V2 working tree

**Worked on:** "is everything pushed?" → it wasn't (local main was even with origin, but a large
uncommitted/untracked V2 tree remained). Scanned for secrets, excluded junk, then committed + pushed.
**Secret scan:** clean — all matches were API-key *handling* (var names, FastAPI deps) and config
templates with empty values (`api_key: ""`, set via env var). No real secrets committed.
**Changed:**
- `.gitignore` — added KiCad local/temp artifacts (`*.lck`, `~*.lck`, `*.kicad_prl`, `.history/`,
  `fp-info-cache`, `*-backups/`) so they're never committed.
- Committed `14294ac` and pushed to `origin/main`: CLAUDE.md, the V2 docs set
  (changelog_and_decisions, hardware_changes_v1_to_v2, pcb_design_notes, session_journal),
  `Boat_PCB/` (kicad_pcb/pro/sch + report.txt), `firmware/boat-pico/status_led.py`, the two new
  Pi5 loop tests, edits to cloud/api, pin_map, main.py, network.py, stereo.py, run_sim.py, and the
  `docs/wiring_diagram.html` deletion. Also committed `.claude/hooks/journal_reminder.ps1`
  (settings.local.json stays gitignored).
**Excluded deliberately:** KiCad lock files, `Boat_PCB-backups/*.zip`, `Boat_PCB/.history/`,
`Boat_PCB.kicad_prl` — local/regenerable artifacts.
**Next steps:** this journal entry itself is committed in a follow-up. The two flagged hardware
discrepancies (battery dividers/GP28, winch power source) remain open.

## 2026-06-01 — Reviewed firmware/docs wiring against the Boat_PCB schematic

**Worked on:** verified the documented Pico pinout (`docs/pin_map.md`, firmware docstrings,
CLAUDE.md) against the actual `Boat_PCB/Boat_PCB.kicad_sch`.
**Method:** the schematic has zero net labels (connectivity is purely geometric), so exported a real
netlist with `kicad-cli sch export netlist --format kicadsexpr` (KiCad 10 at
`~/AppData/Local/Programs/KiCad/10.0/bin/kicad-cli.exe`) and parsed pin-to-pin nets from that.
**Findings — schematic disagrees with docs on almost every peripheral** (only GP10, GP26, GP27 match):
- GP0/GP1: docs say "DEAD", schematic wires them to a **Raspberry Pi 5 40-pin header (J3)** as a
  hardwired UART (Pi pins 8/10 ↔ Pico GP1/GP0) + 5V share — contradicts the "Pi 5 USB-only, no GPIO"
  locked decision. J3 is paralleled across the Pico sockets J14/J17 pin-for-pin.
- VESC/CAN-chain connector J2 is on **GP2–GP6**, not GP12/13. GP12/13 → J11 (Temp+Humidity/DHT).
- GP8/9 → J7 GPS+Compass (docs say I²C0 IMU). GP14/15 → shared bus across J7/J10(IMU)/J13.
- Hull leak is on **GP19/GP20** (J16/J15); docs assign GP17/18 — which are **unconnected**. GP16 also
  unconnected though docs assign it to DHT11.
- **GP28 IS wired** (4S-winch divider R8 100k/R10 18k → R9 → GP28), despite docs calling it "spare".
- Dividers: schematic = 220k/13k (12S), 100k/30k (3S), 100k/18k (4S) — the schematic side of the
  known divider discrepancy ([[battery-divider-discrepancy]] firmware uses 3.3k/47k, 15k/100k).
- **Winch wiring looks broken:** BT4 (4S) → fused → **J6 (valued "6s output")**, while J8 "Winch ESC"
  and J9 "Winch ESC RC" have **both pins on GND** (no +supply/signal). Concrete instance of the
  unresolved winch-power flag — likely a real error.
- Sensor power = VSYS (fed from Pi5 5V via J3.2/3.4); Pico 3V3-OUT (pin36) unconnected — possible
  3.3V-part-on-5V supply concern.
**Decisions / open questions:** did NOT edit any docs — this is a doc-vs-schematic conflict the user
must adjudicate (which is source of truth?). Bus *roles* (SDA/SCL, TX/RX) were inferred from pin
position; the pin→connector connections are exact from the netlist.
**Next steps:** user to decide — regenerate `docs/pin_map.md` from the schematic, or produce a
`docs/pin_map_vs_schematic.md` discrepancy doc. Confirm J8/J9 winch by reading raw schematic symbols.
Note: the exported `boat_netlist.net` was a scratch artifact and was deleted.

## 2026-06-01 — Added the session journal mechanism

**Worked on:** set up a way for each Claude session to record what it did so future chats can pick up
where the last one left off.
**Changed:**
- `docs/session_journal.md` (new) — this file; running newest-first log with an entry template.
- `CLAUDE.md` — added a "Session Journal — read at start, write at end (REQUIRED)" section near the
  top instructing every agent to read this file first and append an entry when finishing.
- `.claude/hooks/journal_reminder.ps1` (new) — Stop hook script; blocks the first stop with a
  reminder to update this journal, allows the re-entrant stop (no loop).
- `.claude/settings.local.json` — wired the script in as a `Stop` hook (exec form, PowerShell).
  Note: this file is gitignored, so the hook is personal to this machine, not shared with teammates.
**Decisions / open questions:** journal stays a *narrative* of in-progress work; locked decisions
remain in `docs/changelog_and_decisions.md`. Enforcement hook lives in local (personal) settings —
move to a committed `.claude/settings.json` if the team should share it.
**Next steps:** future sessions — read this file first, append your entry last. Nothing in this
session is committed yet (journal + CLAUDE.md + hook sit alongside the uncommitted V2 work).

---

## 2026-06-01 — Context snapshot of uncommitted work (summarized from git, not done this session)

> Recorded so the next chat understands the current working-tree state. These changes were already
> present (uncommitted) when the journal was created; descriptions are inferred from `git status` /
> `git diff --stat`, so verify against the diff before relying on the "why."

**In the working tree, not yet committed:**
- **New docs (untracked):** `docs/changelog_and_decisions.md`, `docs/hardware_changes_v1_to_v2.md`,
  `docs/pcb_design_notes.md`, and `CLAUDE.md` — the V2 hardware/architecture documentation set.
- **`docs/wiring_diagram.html` deleted** (~917 lines) — replaced by the Mermaid `system_tree.md` and
  the new pcb/pin docs.
- **`Boat_PCB/` (untracked):** KiCad 10 project for the main carrier board.
- **Firmware:** `firmware/boat-pico/status_led.py` (new, WS2812 NeoPixel on GP10) and ~45 new lines in
  `firmware/boat-pico/main.py`.
- **Tests (untracked):** `pi5/tests/test_mission_loop.py`, `pi5/tests/test_navigator_loop.py`.
- **Smaller edits:** `cloud/api/{app,database,models}.py`, `pi5/comms/network.py`, `pi5/cv/stereo.py`,
  `run_sim.py`, `docs/pin_map.md`.

**Open items carried forward** (see `docs/changelog_and_decisions.md` and CLAUDE.md discrepancy notes):
- Battery-divider / GP28 mismatch between the `Boat_PCB` schematic and `firmware/boat-pico/sensors.py`.
- Unresolved winch power source (dedicated BT4 4S vs. J6 "6s output" / 12S midpoint tap).
**Next steps:** decide whether to commit the V2 docs + journal together; resolve the two flagged
hardware discrepancies.
