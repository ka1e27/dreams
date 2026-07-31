"""Pi-side NMEA GPS reader — the u-blox M10 on the Pi 5 header UART.

**Why the GPS is on the Pi and not the Boat Pico.** Every other sensor on this
boat hangs off a Pico (see ``docs/pin_map.md``), but the GPS can't: on the
as-built board the Pico's **GP9 is hard-shorted to GND** (one solder blob across
Pico pads 12/13/14, which also kills GP10's status NeoPixel and I²C0), and GP9 is
both J7.3 — the connector the GPS TX lands on — and UART1 RX. The module's TX
drove straight into that short. Rather than rework the board, the GPS moved to the
**Pi 5 40-pin header**, which routes around the fault entirely.

Wiring, measured on the bench 2026-07-29:
    module TX  → Pi **GPIO15** (header pin 10, RXD0)   ← the only wire that matters
    module VCC → Pi 3V3/5V (per the module's rating)
    module GND → Pi GND
    module RX  ← Pi GPIO14 (header pin 8, TXD0)        ← optional, see below

**The UART is not enabled by default.** GPIO14/15 are muxed to *no function* on a
fresh Pi 5, so ``/dev/ttyAMA0`` does not exist until::

    dtoverlay=uart0        # in /boot/firmware/config.txt  (persists)
    sudo dtoverlay uart0   # or at runtime, no reboot needed

✅ Unlike a Pi 4, the **serial console does not conflict** here: ``console=serial0``
resolves to ``ttyAMA10``, the Pi 5's separate 3-pin debug-UART connector. Nothing
needs stopping.

**Baud is 38400, not 9600.** That is the u-blox **M10** factory default (M8 used
9600, which is where ``firmware/boat-pico/gps.py``'s number came from). Measured
directly off the line: 5th-percentile pulse width 24.6 µs ≈ 26.0 µs/bit. The
constellation mix also identifies the part — GP+GA+GB+GQ (GPS/Galileo/BeiDou/QZSS,
**no GLONASS**) is the M10 default set.

⚠ **GPIO14/15 collide with ``pi5/scripts/am32_config.py``**, which flashes AM32 ESCs
over ``/dev/ttyAMA0`` on these same two pins. The GPS must be unplugged to configure
an ESC, and vice versa.

⚠ **The Pi's TX may not be wired.** Five ``UBX-MON-VER`` polls got no reply on the
bench, so GPIO14 probably isn't landing on the module's RX. Harmless — NMEA is
unsolicited, so reading works regardless — but it means the module **cannot be
reconfigured** (baud, update rate, constellations) from the Pi until that wire
exists. This class is read-only by design and never writes to the port.

Everything here is **parse-only and I/O-free** except :class:`NmeaGps`, so the
sentence handling is unit-testable with no serial port and no Pi.
"""
from __future__ import annotations

import asyncio
import logging
import math
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# u-blox M10 factory default. Overridable via config.yaml's gps.baud.
DEFAULT_BAUD = 38400
DEFAULT_PORT = "/dev/ttyAMA0"


@dataclass
class GpsFix:
    """The receiver's latest state, accumulated across sentence types.

    GGA supplies position/quality/sats/HDOP/altitude; RMC supplies the validity
    flag, speed and course over ground. Fields keep their last known value — a
    ``GGA`` with ``fix_quality=0`` clears the quality but deliberately leaves
    ``lat``/``lon`` alone, so a brief dropout doesn't blank the position.
    """

    lat: float = 0.0
    lon: float = 0.0
    fix_quality: int = 0        # GGA field 6: 0=none 1=GPS 2=DGPS 4=RTK-fix 5=RTK-float
    sats: int = 0               # satellites *used in the solution*, not tracked
    hdop: float = 0.0
    altitude_m: float = 0.0
    speed_knots: float = 0.0
    track_deg: float = 0.0      # course over ground — only meaningful while moving
    valid: bool = False         # RMC status == 'A'
    utc: str = ""               # hhmmss.ss as sent
    date: str = ""              # ddmmyy as sent

    @property
    def has_fix(self) -> bool:
        """True when the receiver reports a usable position."""
        return self.fix_quality > 0


def checksum_ok(line: str) -> bool:
    """Validate an NMEA sentence's ``*HH`` XOR checksum."""
    if not line.startswith("$") or "*" not in line:
        return False
    body, _, ck = line[1:].partition("*")
    if len(ck) < 2:
        return False
    try:
        want = int(ck[:2], 16)
    except ValueError:
        return False
    got = 0
    for ch in body:
        got ^= ord(ch)
    return got == want


def _num(value: str, cast: Callable[[str], Any], default: Any) -> Any:
    """Cast an NMEA field, tolerating the empty strings it uses for 'unknown'."""
    if not value:
        return default
    try:
        return cast(value)
    except ValueError:
        return default


def dm_to_deg(value: str, hemi: str, limit: float) -> float | None:
    """Convert NMEA ``ddmm.mmmm`` / ``dddmm.mmmm`` + hemisphere to signed degrees.

    ``limit`` is the absolute bound for the axis (90 for latitude, 180 for
    longitude); anything outside it, or with minutes ≥ 60, is rejected as
    corrupt rather than silently producing a plausible-looking position.
    """
    if not value or "." not in value:
        return None
    dot = value.index(".")
    if dot < 2:
        return None
    try:
        deg = int(value[: dot - 2] or "0")
        minutes = float(value[dot - 2 :])
    except ValueError:
        return None
    if minutes >= 60.0 or deg < 0:
        return None
    out = deg + minutes / 60.0
    if out > limit:
        return None
    return -out if hemi in ("S", "W") else out


class NmeaParser:
    """Accumulates NMEA sentences into a single :class:`GpsFix`.

    Talker-agnostic: matches on the 3-character sentence type, so ``$GNGGA``,
    ``$GPGGA`` and ``$GAGGA`` are all handled. GSV is parsed for the satellite
    view (see :attr:`sats_visible`); the rest (GSA/VTG/GLL) are counted and
    ignored.
    """

    def __init__(self) -> None:
        self.fix = GpsFix()
        self.sentences = 0        # checksum-valid sentences seen
        self.bad_checksum = 0
        self.position_updates = 0
        # Satellite view, kept **per talker** (GP/GA/GB/GQ...). Each constellation
        # runs its own independent GSV cycle with its own count, so a single flat
        # total would just be whichever talker spoke last — the M10 emits GPGSV,
        # GAGSV, GBGSV and GQGSV every second.
        self._gsv_declared: dict[str, int] = {}
        self._gsv_snr: dict[str, dict[str, int]] = {}

    # --- satellite view (GSV) ---
    #
    # These are about the *sky*, not the solution. `fix.sats` is how many
    # satellites made it into the position; these say how many the receiver can
    # see and how well it hears them, which is what separates "no sky view" from
    # "the antenna or the wiring is broken".

    @property
    def sats_visible(self) -> int:
        """Satellites reported in view, summed across constellations.

        Read from GSV's own count field rather than by counting parsed entries,
        so it is right from the first message of a multi-message cycle instead of
        ramping up as the cycle arrives.
        """
        return sum(self._gsv_declared.values())

    @property
    def sats_tracked(self) -> int:
        """Of those in view, how many are actually being received (SNR > 0).

        The gap between this and :attr:`sats_visible` is the diagnostic one: a
        satellite in view with no SNR is predicted from the almanac but not
        heard.
        """
        return sum(1 for d in self._gsv_snr.values() for s in d.values() if s > 0)

    @property
    def best_snr(self) -> int:
        """Strongest satellite SNR in dB-Hz; 0 when nothing is being received.

        Doubles as an antenna check — anything much above 30 means the RF chain
        works and a missing fix is about sky view, not hardware.
        """
        snrs = [s for d in self._gsv_snr.values() for s in d.values() if s > 0]
        return max(snrs) if snrs else 0

    def feed_line(self, line: str) -> GpsFix | None:
        """Parse one sentence.

        Returns the fix **only when this sentence carried a usable position**,
        so a caller can treat a non-None return as "there is new position to
        publish". State is updated either way.
        """
        line = line.strip()
        if not line.startswith("$") or "*" not in line:
            return None
        if not checksum_ok(line):
            self.bad_checksum += 1
            return None
        self.sentences += 1

        f = line[1:].partition("*")[0].split(",")
        tag = f[0]
        if len(tag) < 5:
            return None
        kind = tag[2:5]
        if kind == "GGA":
            out = self._gga(f)
        elif kind == "RMC":
            out = self._rmc(f)
        elif kind == "GSV":
            self._gsv(tag[:2], f)
            return None
        else:
            return None
        if out is not None:
            self.position_updates += 1
        return out

    def _gsv(self, talker: str, f: list[str]) -> None:
        """Record one GSV message's slice of the satellite view.

        Layout is ``total_msgs, msg_num, sats_in_view`` then N groups of
        ``(prn, elev, azim, snr)``. NMEA 4.10+ — which the M10 speaks — appends a
        trailing *signalId* field after the last group, so the group walk is
        bounded by ``len(f) - 3``: without that, signalId gets read as a PRN and
        invents a satellite every cycle.
        """
        if len(f) < 4:
            return
        self._gsv_declared[talker] = _num(f[3], int, 0)
        # A new cycle replaces this talker's previous one, so satellites that
        # dropped out of view stop being counted instead of lingering forever.
        if _num(f[2], int, 1) <= 1:
            self._gsv_snr[talker] = {}
        seen = self._gsv_snr.setdefault(talker, {})
        for i in range(4, len(f) - 3, 4):
            prn, _elev, _azim, snr = f[i:i + 4]
            if prn:
                seen[prn] = _num(snr, int, 0)

    def _gga(self, f: list[str]) -> GpsFix | None:
        if len(f) < 10:
            return None
        fx = self.fix
        fx.utc = f[1]
        fx.fix_quality = _num(f[6], int, 0)
        fx.sats = _num(f[7], int, 0)
        fx.hdop = _num(f[8], float, 0.0)
        fx.altitude_m = _num(f[9], float, 0.0)
        lat = dm_to_deg(f[2], f[3], 90.0)
        lon = dm_to_deg(f[4], f[5], 180.0)
        if fx.fix_quality > 0 and lat is not None and lon is not None:
            fx.lat, fx.lon = lat, lon
            return fx
        return None

    def _rmc(self, f: list[str]) -> GpsFix | None:
        if len(f) < 10:
            return None
        fx = self.fix
        fx.utc = f[1]
        fx.valid = f[2] == "A"
        fx.speed_knots = _num(f[7], float, 0.0)
        fx.track_deg = _num(f[8], float, 0.0)
        fx.date = f[9]
        lat = dm_to_deg(f[3], f[4], 90.0)
        lon = dm_to_deg(f[5], f[6], 180.0)
        if fx.valid and lat is not None and lon is not None:
            fx.lat, fx.lon = lat, lon
            return fx
        return None


@dataclass
class GpsStats:
    """Diagnostics for the command center / bench, not used by navigation."""

    connected: bool = False
    linked: bool = False        # a valid sentence has arrived (see NmeaGps.linked)
    sentences: int = 0
    bad_checksum: int = 0
    position_updates: int = 0
    reconnects: int = 0
    age_s: float = math.inf
    # Satellite view — the "why is there no fix" fields. See NmeaParser.
    sats_visible: int = 0
    sats_tracked: int = 0
    best_snr: int = 0
    fix: GpsFix = field(default_factory=GpsFix)


class NmeaGps:
    """Async reader that turns ``/dev/ttyAMA0`` into a stream of position fixes.

    Read-only: it never writes to the port, so it cannot disturb a receiver's
    configuration. Self-heals like :class:`~pi5.comms.pico_serial.PicoSerial` —
    if the port vanishes (module unplugged, overlay removed, another process
    grabs it) the loop reopens it with a capped backoff instead of dying.

    Off a Pi — or on a Pi with the overlay not loaded — the port simply won't
    open; the loop logs once and keeps retrying, so importing and starting this
    is harmless in the simulator or on a laptop.
    """

    def __init__(
        self,
        port: str = DEFAULT_PORT,
        baud: int = DEFAULT_BAUD,
        stale_after_s: float = 5.0,
    ) -> None:
        self._port = port
        self._baud = baud
        self._stale_after_s = stale_after_s

        self.parser = NmeaParser()
        self._fix_ts: float = 0.0
        self._connected = False
        self._reconnects = 0
        self._open_failed_logged = False

        self._on_fix: Callable[[GpsFix], Any] | None = None
        self._on_status: Callable[[GpsStats], Any] | None = None
        self._task: asyncio.Task[None] | None = None
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None

    # --- state ---

    @property
    def fix(self) -> GpsFix:
        """The latest accumulated fix (may be stale — check :attr:`age_s`)."""
        return self.parser.fix

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def linked(self) -> bool:
        """True once at least one checksum-valid sentence has arrived.

        Deliberately distinct from :attr:`connected`, which only says the *port*
        opened. The port opens fine with the module unpowered or its TX wire off
        GPIO15, so this is the flag that means "the receiver is actually talking".
        The two of them together separate the three failure modes an operator
        cares about: no port (overlay missing), port but no bytes (wiring/power),
        bytes but no fix (sky view).
        """
        return self.parser.sentences > 0

    @property
    def age_s(self) -> float:
        """Seconds since the last *usable position*; ``inf`` before the first."""
        if self._fix_ts == 0.0:
            return math.inf
        return time.monotonic() - self._fix_ts

    @property
    def has_fix(self) -> bool:
        """True when we hold a position that is both valid and fresh."""
        return self.parser.fix.has_fix and self.age_s <= self._stale_after_s

    def stats(self) -> GpsStats:
        return GpsStats(
            connected=self._connected,
            linked=self.linked,
            sentences=self.parser.sentences,
            bad_checksum=self.parser.bad_checksum,
            position_updates=self.parser.position_updates,
            reconnects=self._reconnects,
            age_s=self.age_s,
            sats_visible=self.parser.sats_visible,
            sats_tracked=self.parser.sats_tracked,
            best_snr=self.parser.best_snr,
            fix=self.parser.fix,
        )

    def on_fix(self, callback: Callable[[GpsFix], Any]) -> None:
        """Register a callback fired on every sentence carrying a usable position."""
        self._on_fix = callback

    def on_status(self, callback: Callable[[GpsStats], Any]) -> None:
        """Register a callback fired on every GGA, **with or without a fix**.

        This is the counterpart to :meth:`on_fix`, which by design only fires on a
        usable position and so goes completely silent in the one state an operator
        most needs reported: receiver alive, streaming cleanly, not locked. GGA is
        the 1 Hz "here is where I think I am" sentence, which makes it the natural
        tick for publishing receiver status.
        """
        self._on_status = callback

    # --- lifecycle ---

    async def start(self) -> None:
        """Spawn the read loop. Never raises on a missing port — it retries."""
        if self._task is None:
            self._task = asyncio.create_task(self._read_loop())
            logger.info("GPS reader started on %s @ %d", self._port, self._baud)

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        await self._close()
        logger.info("GPS reader stopped")

    async def _close(self) -> None:
        self._connected = False
        if self._writer is not None:
            try:
                self._writer.close()
            except Exception:  # noqa: BLE001 — closing a dead port is not news
                pass
        self._reader = None
        self._writer = None

    async def _open(self) -> None:
        import serial_asyncio

        self._reader, self._writer = await serial_asyncio.open_serial_connection(
            url=self._port, baudrate=self._baud
        )
        self._connected = True

    async def _read_loop(self) -> None:
        backoff = 0.5
        while True:
            try:
                if self._reader is None:
                    await self._open()
                    self._reconnects += 1
                    self._open_failed_logged = False
                    logger.info("GPS port open: %s @ %d", self._port, self._baud)
                    backoff = 0.5
                raw = await self._reader.readline()
                if not raw:
                    raise ConnectionError("empty read (device disconnected?)")
                line = raw.decode("ascii", errors="ignore").strip()
                if not line:
                    continue
                fix = self.parser.feed_line(line)
                if fix is not None:
                    self._fix_ts = time.monotonic()
                    if self._on_fix:
                        try:
                            self._on_fix(fix)
                        except Exception as e:  # noqa: BLE001 — a bad consumer
                            logger.error("GPS on_fix callback failed: %s", e)
                # Cheap tag test rather than re-parsing: "$GNGGA,..."[3:6] == "GGA"
                # for every talker. Fires whether or not the sentence carried a
                # position, which is the whole point — see on_status.
                if self._on_status is not None and line[3:6] == "GGA":
                    try:
                        self._on_status(self.stats())
                    except Exception as e:  # noqa: BLE001 — a bad consumer
                        logger.error("GPS on_status callback failed: %s", e)
            except asyncio.CancelledError:
                raise
            except Exception as e:  # noqa: BLE001 — the loop must outlive any error
                await self._close()
                # Log the first failure loudly, then stay quiet until it recovers:
                # a missing port would otherwise spam a line every few seconds
                # forever on a laptop or a Pi without the uart0 overlay.
                if not self._open_failed_logged:
                    logger.warning(
                        "GPS link unavailable on %s (%s) — retrying. If this is a Pi, "
                        "check the uart0 overlay: sudo dtoverlay uart0",
                        self._port, e,
                    )
                    self._open_failed_logged = True
                else:
                    logger.debug("GPS retry on %s: %s", self._port, e)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 5.0)
