# Converting the right drive ESC from BLHeli_32 to AM32

**Status: PLANNED, NOT STARTED.** Researched 2026-07-31; no step below has been executed.
Written so a fresh session can pick this up cold.

> **Read `docs/esc_setup.md` first** — specifically the "bi-directional gate" section. That gate is
> what currently keeps the boat safe, and it stays on until this conversion (or a BLHeliSuite32 fix)
> is done and verified.

---

## Why we're doing this

On 2026-07-31 the right ESC ran away on the bench: it armed mid-test and kept spinning through
`SET_THR 0,0` *and* through `ESTOP`. Root cause — it is in stock **normal mode**, where the 1.5 ms
pulse `escs.py` calls "neutral" is **~50 % throttle**. Full write-up in the session journal.

The fix is to put it in bi-directional/3D mode. That turned out to be unreachable from here:

- **BLHeli_32 is closed source**, and licensing/development were **terminated in 2024**.
- **esc-configurator does not support BLHeli_32** — only BLHeli_S, Bluejay (SiLabs EFM8) and AM32
  (ARM). There is no open implementation of the _32 settings protocol to build a Pi-side tool from.
- Writing one would mean reverse-engineering a closed protocol and then writing EEPROM to the ESC
  that just ran away. Rejected as irresponsible.

**Converting to AM32 solves more than the immediate bug:**

1. `pi5/scripts/am32_config.py` already exists and works — bi-directional becomes a one-command
   change *from the Pi*, over a protocol transcribed from open source.
2. **Both ESCs end up on AM32.** The mixed-firmware hazard class disappears entirely, rather than
   this one instance being patched.
3. Telemetry becomes reachable — the AM32 target defines `USE_SERIAL_TELEMETRY` plus current and
   voltage sense. `esc_telem.py` has been receiving zero bytes.
4. `escs.BIDIR_CONFIRMED` can then be set `True` on both, legitimately.

---

## The hardware

| | |
|---|---|
| ESC | **FlashHobby FHD 70A**, 3–6S, BLHeli_32 · GP20 / J15 (right) |
| MCU | **STM32F051** (48 MHz) — user-confirmed. AM32 debug config names `STM32F051K6Ux` |
| Motor | Badass 2320-1630 kv |

> ⚠ The repo elsewhere calls this **"FlashHobby FH-70A"**. The actual product is the **FHD 70A**
> (the vendor URL slug says `75a`; the page title reads "Flashhobby FHD 70A 3-6S BL32"). Worth
> correcting in `escs.py`, `motor_control.py` and `docs/esc_setup.md` at some point.

> ⚠ **Check the chip marking says `STM32F051`, not `CKS32F051`.** The CKS part is a clone and AM32's
> README explicitly says it "is not recommended due to too many random issues". Cheap ESCs often
> carry it. Verify before the irreversible step.

**Drive-rail voltage is fine:** the ESC is 3–6S and the drive rail is 2× M18 in parallel,
18 V nom / 21 V max.

---

## Target and artefacts (verified to exist, 2026-07-31)

AM32 has a **first-class target** for this board — `Inc/targets.h`:

```c
#ifdef FLASHHOBBY_F051
#define FILE_NAME "FLASHHOBBY_F051"
#define FIRMWARE_NAME "FLASHHOBBY  "
#define DEAD_TIME 30
#define TARGET_VOLTAGE_DIVIDER 110
#define MILLIVOLT_PER_AMP 10
#define CURRENT_OFFSET 1010 // millivolts
#define HARDWARE_GROUP_F0_A
#define USE_SERIAL_TELEMETRY
#endif
```

| Artefact | Where |
|---|---|
| Firmware | **`AM32_FLASHHOBBY_F051_2.20.hex`** — AM32 release `v2.20` |
| Bootloader | **`AM32_F051_BOOTLOADER_PA2_V17.hex`** — AM32-bootloader release `v17.0.0` |

> ⚠ **PA2 is an INFERENCE, not a verified fact.** The bootloader variants are named by signal-input
> pin (`PA0`, `PA2`, `PA6`, `PA15`, `PB4`). `FLASHHOBBY_F051` declares `HARDWARE_GROUP_F0_A`, and the
> `FD6288_F051` target shares that same group while being named `"FD6288_PA2"` — hence PA2. **If the
> ESC does not respond to the bootloader over the signal wire after flashing, this is the first thing
> to suspect.** It is recoverable: SWD access remains open once RDP is cleared, so just flash a
> different pin variant.

---

## Programmer: the Pi 5 itself — no ST-Link needed

Verified present on this Pi (2026-07-31):

| | |
|---|---|
| OpenOCD | `0.12.0+rpt20250909` at `/usr/bin/openocd` |
| Adapter drivers | `linuxgpiod` ✓ `cmsis-dap` ✓ (also `sysfsgpio`, `bcm2835gpio`, `jlink`) |
| Interface config | `/usr/share/openocd/scripts/interface/raspberrypi5-gpiod.cfg` ✓ |
| Target config | `/usr/share/openocd/scripts/target/stm32f0x.cfg` ✓ |
| RDP clear | `stm32f1x unlock` present in the binary ✓ (F0 uses the F1 flash driver family) |

`bcm2835gpio` does **not** work on Pi 5 (RP1 southbridge) — the `linuxgpiod` driver is the Pi 5 route,
and `raspberrypi5-gpiod.cfg` selects it. `/dev/gpiochip0` is `pinctrl-rp1` (54 lines) = the header.

### Wiring

OpenOCD's default SWDIO is **GPIO8**, which on `Boat_PCB V2` is the A4988's `~RESET`+`~SLEEP`
(`docs/pin_map.md`). **Remap it.** These three header pins are free and adjacent:

| Signal | BCM | Header pin |
|---|---|---|
| SWCLK | GPIO11 | **23** (OpenOCD's default — no override needed) |
| SWDIO | GPIO9 | **21** (overrides the GPIO8 default) |
| GND | — | **25** |

Pi header pins already spoken for, all avoided: **GPIO8** (stepper sleep), **GPIO14/15** (GPS UART0),
**GPIO23/24/25** (stepper STEP/DIR/ENABLE).

### Powering the ESC

The STM32 needs the ESC powered, i.e. the drive pack connected.

1. **Disconnect the motor leads first** so nothing can spin, whatever the firmware state.
2. Then connect the drive pack.
3. Note the SWD GND bridges the **drive** and **electronics** ground domains, which
   `docs/battery_architecture.md` otherwise keeps isolated. Acceptable on the bench; be aware of it.

If PCIe ASPM is not in performance mode OpenOCD warns that the first pulses may clock at ~20 MHz:

```bash
echo performance | sudo tee /sys/module/pcie_aspm/parameters/policy
```

### Fallback probe

If bit-banging is unreliable, flash a spare Pico with **`debugprobe_on_pico.uf2`**
(github.com/raspberrypi/debugprobe) and use it as a CMSIS-DAP probe — `interface/cmsis-dap.cfg` is
already installed. Bit-bang runs ~800 kHz SWD writes / ~360 kHz reads.

---

## Procedure

Common prefix, used by every stage below:

```bash
OOCD="sudo openocd -f interface/raspberrypi5-gpiod.cfg \
  -c 'adapter gpio swdio -chip 0 9' \
  -c 'adapter gpio swclk -chip 0 11' \
  -c 'transport select swd' \
  -f target/stm32f0x.cfg"
```

### Stage 1 — pre-flight (NON-destructive, do this first)

```bash
sudo openocd -f interface/raspberrypi5-gpiod.cfg \
  -c 'adapter gpio swdio -chip 0 9' \
  -c 'adapter gpio swclk -chip 0 11' \
  -c 'transport select swd' \
  -f target/stm32f0x.cfg \
  -c init -c 'dap info' -c shutdown
```

**Pass = a Cortex-M0 is detected and an IDCODE is reported.** Nothing is written. If this fails,
stop and fix wiring/power — do not proceed.

> Expect the target to report as **locked / protected** at this point. That is normal: BLHeli_32
> enables SWD readout protection. Detection may still succeed while memory access is refused.

### Stage 2 — clear readout protection ⚠ IRREVERSIBLE

**This is the point of no return.** Clearing RDP mass-erases the flash, and per AM32's wiki the ESC
*"permanently loses the ability to flash BLHeli_32 firmware back."* Everything after this step is
recoverable; this step is not.

```bash
sudo openocd ... -c init -c 'reset halt' -c 'stm32f1x unlock 0' -c shutdown
```

Then **power-cycle the ESC** — an RDP option-byte change only takes effect after a power-on reset.
Re-run Stage 1 afterwards; memory should now be accessible.

### Stage 3 — flash the AM32 bootloader

```bash
sudo openocd ... -c init -c 'reset halt' \
  -c 'program AM32_F051_BOOTLOADER_PA2_V17.hex verify reset exit'
```

The `.hex` carries absolute addresses, so no offset is needed.

### Stage 4 — flash the AM32 application

Either over SWD with the same `program` command using `AM32_FLASHHOBBY_F051_2.20.hex`, or — the
normal AM32 route — over the signal wire through the bootloader you just installed.

**Sanity check:** the ESC should now identify as AM32 with firmware name `FLASHHOBBY  `.

### Stage 5 — configure it from the Pi (this is the part that was the original goal)

`pi5/scripts/am32_config.py` speaks the AM32 bootloader protocol directly. Per its docstring the ESC
signal line goes to the **Pi's UART0**: signal → pin 10 (GPIO15/RXD0) direct, plus a ~1 kΩ resistor
to pin 8 (GPIO14/TXD0), ESC GND → pin 6.

> ⚠ **This shares GPIO14/15 with the GPS.** The GPS must be unplugged while configuring an ESC.

```bash
python -m pi5.scripts.am32_config read
python -m pi5.scripts.am32_config set --bidir on --telemetry on
python -m pi5.scripts.am32_config set --lvc 3.0
python -m pi5.scripts.am32_config read        # read back and CONFIRM
```

Match the left ESC's settings — see the table in `docs/esc_setup.md`.

### Stage 6 — release the safety gate

Only after reading the setting **back**:

1. `firmware/boat-pico/escs.py` → `BIDIR_CONFIRMED = {LEFT: True, RIGHT: True}`.
   (`LEFT` was deliberately left `False` too — the AM32 behaved correctly on the bench, but that is
   evidence, not confirmation. Read it back in the tool as well before flipping it.)
2. `python pi5/scripts/deploy_pico.py --port /dev/ttyACM0`
3. Boot banner must read `Drive ESC mode: bi-directional CONFIRMED on both — throttle enabled`.
4. Work through the **first-spin checklist** in `docs/esc_setup.md` — props off.
5. Confirm the watchdog kills to an actual **stop**, not a steady hum. That is the exact failure
   this whole exercise exists to prevent.

---

## Also worth doing while in here

- **Solder the telemetry wire.** `esc_telem.py` reads the right ESC on **GP11**, which
  `docs/pin_map.md` records as *"not routed to a connector — solder to the Pico pin"*. It has been
  receiving zero bytes (`frames_ok = 0, crc_fail = 0`) the whole time. AM32's `USE_SERIAL_TELEMETRY`
  makes this actually useful — current, voltage and erpm.
- **Then tune `COMP_R`** (currently `0.957`, from the Kv ratio alone) against real erpm. Kv only
  equalises *no-load* rpm and these are different frames (2814 vs 2320).

---

## Open questions for whoever picks this up

1. **Is PA2 the right bootloader?** Inferred, not verified — see the warning above.
2. **Genuine STM32F051 or a CKS32F051 clone?** Check the chip marking before Stage 2.
3. **Where are the SWD pads on the FHD 70A?** Not established. Usually small pads near the MCU,
   sometimes under heatshrink; SWCLK/SWDIO/GND/3V3.
4. **Stage 1 has never been run.** It was attempted on 2026-07-31 but the sandbox permission
   classifier blocked OpenOCD from driving GPIO, so it must be run by the user (`!` prefix in Claude
   Code, or a plain shell).

## Sources

- AM32 targets — https://github.com/am32-firmware/AM32/blob/main/Inc/targets.h
- AM32 "flash AM32 on BLHeli_32 hardware" — https://wiki.am32.ca/guides/Hacking-Guide.html
- AM32 bootloader releases — https://github.com/am32-firmware/AM32-bootloader/releases
- esc-configurator (supported firmware list) — https://github.com/stylesuxx/esc-configurator
- Betaflight ESC firmware wiki — https://betaflight.com/docs/wiki/getting-started/hardware/esc-firmware
- Oscar Liang, flashing AM32 on BLHeli_32 — https://oscarliang.com/flash-am32-blheli32-esc/
