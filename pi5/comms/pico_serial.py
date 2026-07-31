"""Async serial connection to the Boat Pico.

Sends commands, receives responses and unsolicited telemetry/alerts
over USB serial using the protocol from docs/serial-protocol.md.
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import serial_asyncio

from .protocol import ParsedFrame, build_command, parse_frame

logger = logging.getLogger(__name__)


@dataclass
class Telemetry:
    """Latest telemetry from the Boat Pico."""
    lat: float = 0.0
    lon: float = 0.0
    heading: float = 0.0
    speed_knots: float = 0.0
    batt_v: float = 0.0
    batt_pct: int = 0
    hull: str = "DRY"
    mt_left: float = 0.0
    mt_right: float = 0.0
    health: str = "000000"
    # Per-motor current (A) from AM32 KISS telemetry — appended TEL fields,
    # 0.0 when the firmware/ESC don't report it.
    curr_left: float = 0.0
    curr_right: float = 0.0
    # GPS quality. Populated only when a Pi-side GPS owns position (see
    # PicoSerial.use_external_gps); the TEL frame itself carries no such fields,
    # so on a Pico-hosted GPS these stay 0 and `gps_source` stays "pico".
    fix_quality: int = 0       # 0=no fix 1=GPS 2=DGPS 4=RTK-fix 5=RTK-float
    sats: int = 0              # satellites *used in the solution*
    hdop: float = 0.0          # horizontal dilution of precision (lower = better)
    # "pico" | "pi" | "pi-stale" | "pi-nofix" | "pi-nolink" | "sim"
    # — see PicoSerial.use_external_gps for what each one means.
    gps_source: str = "pico"
    # Receiver observability from the Pi-side GPS (NMEA GSV). These describe the
    # *sky*, not the solution: `sats` above is how many satellites made it into
    # the fix, while these say how many the receiver can see and how well it hears
    # them. That distinction is what separates "no sky view — take it outside"
    # from "the antenna or the wiring is broken", which are indistinguishable
    # from a bare "no fix".
    gps_sats_visible: int = 0
    gps_sats_tracked: int = 0  # of those, how many have a non-zero SNR
    gps_best_snr: int = 0      # dB-Hz; much above 30 means the RF chain is fine


@dataclass
class Environment:
    """Latest environment data from the Boat Pico.

    The first six fields are ENV v1.0. The rest are appended by ENV v1.1
    (backward compatible — older firmware simply omits them, leaving defaults):
    a second SHT41 inside the electronics enclosure, plus the M18 electronics and
    M18 winch battery rails (the M18 drive rail stays in TEL as batt_v).
    """
    air_temp: int = 0              # SHT41 #A — open air
    air_humidity: int = 0
    water_temp: float = -999.0
    water_ec: float = 0.0
    water_light: int = 0
    bottom_contact: bool = False
    # ENV v1.1 appended fields
    enc_temp: float = -999.0       # SHT41 #B — electronics enclosure (-999 = none)
    enc_humidity: float = -1.0     # %RH (-1 = none)
    elec_batt_v: float = 0.0       # M18 electronics rail
    elec_batt_pct: int = 0
    winch_batt_v: float = 0.0      # M18 winch rail
    winch_batt_pct: int = 0


@dataclass
class PodData:
    """Pod sensor reading."""
    water_temp: float = -999.0
    salinity_ec: float = 0.0
    light_pct: int = 0
    bottom: bool = False
    leak: bool = False
    pressure_depth_m: float = 0.0


@dataclass
class Alert:
    """An alert from the Boat Pico."""
    severity: str = ""
    code: str = ""
    detail: str = ""


class PicoNak(RuntimeError):
    """The Pico refused a command (NAK). Carries the parsed reason.

    Subclasses RuntimeError so existing `except RuntimeError` / `except Exception`
    callers keep working, while code that needs to *act* on the reason — e.g. tell
    the operator their throttle is being refused because the Pico is latched in
    ESTOP — can read `.reason` instead of string-matching a log line.
    """

    def __init__(self, command: str, reason: str) -> None:
        super().__init__("Command %s NAK'd: %s" % (command, reason))
        self.command = command
        self.reason = reason


# Alert codes that mean the Pico has latched its ESTOP and will refuse throttle
# until it gets a RESUME (motor_control.estop() in the firmware is sticky).
_ESTOP_ALERT_CODES = frozenset({"ESTOP_AUTO", "HB_LOST", "SBUS_LOST"})


class PicoSerial:
    """Async serial interface to the Boat Pico."""

    def __init__(
        self,
        port: str = "/dev/ttyACM0",
        baud: int = 115200,
        command_timeout: float = 2.0,
        max_retries: int = 3,
        silence_timeout: float = 5.0,
    ) -> None:
        self._port = port
        self._baud = baud
        self._command_timeout = command_timeout
        self._max_retries = max_retries
        # A healthy Pico sends TEL every second unprompted, so this many seconds
        # of total silence means the link is dead even if the OS never told us.
        self._silence_timeout = silence_timeout

        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._connected = False

        # Sequence counter (0–255, wrapping)
        self._seq = 0

        # Pending command response futures: {seq: Future}
        self._pending: dict[int, asyncio.Future[ParsedFrame]] = {}

        # Latest state
        self.telemetry = Telemetry()
        self.environment = Environment()
        self.last_alert: Alert | None = None
        # Best-effort mirror of the Pico's latched ESTOP. TEL carries no estop
        # field (only GET_STATUS does, and nothing polls it), so this is inferred
        # from the three things that do reach us: an ESTOP we sent, an ESTOP-class
        # ALERT, and a NAK whose reason is ESTOP. Without it a latched Pico
        # silently NAKs every SET_THR forever and the dashboard shows no cause.
        self.estopped = False

        # External (Pi-side) GPS override — see use_external_gps().
        self._ext_gps = False
        self._ext_max_age_s = 5.0
        # (lat, lon, speed_knots, fix_quality, sats, hdop); None before the first fix
        self._ext_pos: tuple[float, float, float, int, int, float] | None = None
        self._ext_ts = 0.0
        self._ext_stale_logged = False
        # Receiver state, published even with no fix — see set_external_gps_status.
        self._ext_sats_visible = 0
        self._ext_sats_tracked = 0
        self._ext_best_snr = 0
        self._ext_linked = False

        # Callbacks
        self._on_telemetry: Callable[[Telemetry], Any] | None = None
        self._on_environment: Callable[[Environment], Any] | None = None
        self._on_alert: Callable[[Alert], Any] | None = None
        self._on_pod_data: Callable[[PodData], Any] | None = None

        # Background tasks
        self._read_task: asyncio.Task[None] | None = None
        self._hb_task: asyncio.Task[None] | None = None

    @property
    def connected(self) -> bool:
        """Return True if serial connection is open."""
        return self._connected

    def on_telemetry(self, callback: Callable[[Telemetry], Any]) -> None:
        """Register a callback for telemetry updates."""
        self._on_telemetry = callback

    def on_environment(self, callback: Callable[[Environment], Any]) -> None:
        """Register a callback for environment updates."""
        self._on_environment = callback

    def on_alert(self, callback: Callable[[Alert], Any]) -> None:
        """Register a callback for alerts."""
        self._on_alert = callback

    def on_pod_data(self, callback: Callable[[PodData], Any]) -> None:
        """Register a callback for pod data."""
        self._on_pod_data = callback

    # --- External (Pi-side) GPS ------------------------------------------------
    #
    # On this branch the GPS is wired to the *Pi's* header UART, not the Pico —
    # the Pico's GP9 (J7.3 / UART1 RX) is hard-shorted to GND on the as-built
    # board. See pi5/comms/gps_nmea.py for the full story. The Pico therefore
    # reports lat/lon 0.0 and an unhealthy GPS bit forever, so position has to be
    # injected here, where the whole nav stack already reads it: Navigator's loop
    # polls `pico.telemetry` every tick.

    def use_external_gps(self, max_age_s: float = 5.0) -> None:
        """Declare that a Pi-side GPS owns position, not the Pico's TEL fields.

        Changes three behaviours:
          * TEL's lat/lon/speed are replaced by the external fix (see
            :meth:`set_external_position`),
          * ``SENSOR_FAULT,gps`` alerts stop being surfaced — the Pico's GPS is
            not wired on this branch, so that fault is expected and permanent,
            and left alone it repeats about once a second forever,
          * health bit 0 (the Pico's GPS flag) is rewritten to reflect the *Pi's*
            receiver, which is the one that actually determines whether the boat
            knows where it is.

        ``max_age_s`` is how long a fix stays trustworthy. Past it, position is
        still served (see the staleness note in :meth:`_apply_external`) but
        ``fix_quality`` drops to 0 and ``gps_source`` becomes ``"pi-stale"``.

        ``gps_source`` is then a four-rung ladder describing the Pi receiver, and
        the rung is what tells an operator what to *do*:

        ==============  ============================================================
        ``pi-nolink``   no NMEA has ever arrived — module unpowered, TX wire off
                        GPIO15, or the ``uart0`` overlay missing. Check wiring.
        ``pi-nofix``    sentences are flowing but no position yet. Sky-view
                        problem; check the satellite count and SNR.
        ``pi-stale``    had a fix, now older than ``max_age_s``. The position on
                        the map is the last known one, not the current one.
        ``pi``          fresh, usable fix.
        ==============  ============================================================

        Note the asymmetry between the middle two: ``pi-nofix`` means *never*
        locked, so there is no position to serve at all, whereas a receiver that
        locks and then loses it goes to ``pi-stale`` and keeps serving the last
        one. That is deliberate — see :meth:`_apply_external`.
        """
        self._ext_gps = True
        self._ext_max_age_s = max_age_s
        logger.info("Position source: Pi-side GPS (external), staleness limit %.1fs",
                    max_age_s)

    def set_external_gps_status(
        self,
        sats_visible: int = 0,
        sats_tracked: int = 0,
        best_snr: int = 0,
        linked: bool = False,
    ) -> None:
        """Publish Pi-GPS receiver state that isn't a position. Safe at 1 Hz.

        Exists because the no-fix case was previously invisible:
        :meth:`set_external_position` only fires on a *usable* position, so a
        receiver that was streaming perfectly but hadn't locked left
        ``gps_source`` reading ``"pico"`` — naming a receiver this board doesn't
        have wired at all — with nothing to say the Pi GPS was alive and merely
        waiting on satellites. That reads as "the GPS is broken" when it isn't.
        """
        self._ext_sats_visible = sats_visible
        self._ext_sats_tracked = sats_tracked
        self._ext_best_snr = best_snr
        self._ext_linked = linked
        self._apply_external(self.telemetry)

    def set_external_position(
        self,
        lat: float,
        lon: float,
        speed_knots: float = 0.0,
        fix_quality: int = 1,
        sats: int = 0,
        hdop: float = 0.0,
    ) -> None:
        """Publish a fix from the Pi-side GPS. Cheap enough to call per sentence.

        Applies to the live telemetry object immediately as well as storing it,
        so consumers polling between 1 Hz TEL frames see the newest position
        rather than waiting for the next frame to carry it across.
        """
        self._ext_pos = (lat, lon, speed_knots, fix_quality, sats, hdop)
        self._ext_ts = time.monotonic()
        self._ext_stale_logged = False
        if not self._ext_gps:
            # Tolerate wiring order (fix arriving before use_external_gps) rather
            # than silently dropping position.
            self.use_external_gps(self._ext_max_age_s)
        self._apply_external(self.telemetry)

    def _apply_external(self, tel: Telemetry) -> None:
        """Overlay the external fix onto a Telemetry object, in place.

        ⚠ A stale fix still overwrites lat/lon. That is deliberate: the Pico's
        own lat/lon are a hard 0.0 with no receiver attached, and there is no
        guard against (0, 0) anywhere in the nav stack — handing the navigator
        the Gulf of Guinea is far worse than handing it a position a few seconds
        old. Staleness is reported through ``fix_quality``/``gps_source`` instead,
        so a caller that wants to gate on freshness can.

        Heading is **never** touched — that stays the Pico's compass. RMC's course
        over ground is not a heading (it's meaningless at rest) and lives on
        GpsFix.track_deg if anything ever wants it.
        """
        if not self._ext_gps:
            return
        # Receiver state goes out whether or not there is a fix — that is the
        # point of it. Published before the no-fix return below, so "2 of 2 sats,
        # best SNR 34" is visible during acquisition.
        tel.gps_sats_visible = self._ext_sats_visible
        tel.gps_sats_tracked = self._ext_sats_tracked
        tel.gps_best_snr = self._ext_best_snr

        if self._ext_pos is None:
            # No fix has *ever* arrived, so there is no position to serve. Name
            # which of the two situations it is, because the operator's next move
            # differs completely: wait for sky vs go check the wiring.
            tel.gps_source = "pi-nofix" if self._ext_linked else "pi-nolink"
            tel.fix_quality = 0
            tel.sats = 0
            if tel.health:
                tel.health = "0" + tel.health[1:]
            return

        lat, lon, speed, quality, sats, hdop = self._ext_pos
        stale = (time.monotonic() - self._ext_ts) > self._ext_max_age_s
        if stale and not self._ext_stale_logged:
            logger.warning("Pi GPS fix is stale (>%.1fs old) — still serving the last "
                           "known position, fix_quality forced to 0",
                           self._ext_max_age_s)
            self._ext_stale_logged = True

        tel.lat, tel.lon = lat, lon
        tel.speed_knots = speed
        tel.sats = sats
        tel.hdop = hdop
        tel.fix_quality = 0 if stale else quality
        tel.gps_source = "pi-stale" if stale else "pi"
        # Health bit 0 is the *Pico's* GPS health, which on this branch describes
        # a receiver that isn't connected to it. Rewrite it to describe the Pi's.
        if tel.health:
            ok = "1" if (not stale and quality > 0) else "0"
            tel.health = ok + tel.health[1:]

    async def connect(self) -> None:
        """Open the serial connection and start the read loop."""
        try:
            await self._open_streams()
            self._read_task = asyncio.create_task(self._read_loop())
            logger.info("Connected to Boat Pico on %s @ %d", self._port, self._baud)
        except Exception as e:
            self._connected = False
            logger.error("Failed to connect to %s: %s", self._port, e)
            raise

    async def _open_streams(self) -> None:
        """Open (or re-open) the underlying serial streams."""
        self._reader, self._writer = await serial_asyncio.open_serial_connection(
            url=self._port, baudrate=self._baud
        )
        self._connected = True

    async def _close_streams(self) -> None:
        """Drop the serial streams so the read loop will re-open them."""
        self._connected = False
        if self._writer is not None:
            try:
                self._writer.close()
            except Exception:  # noqa: BLE001
                pass
        self._reader = None
        self._writer = None

    async def disconnect(self) -> None:
        """Close the serial connection."""
        if self._read_task:
            self._read_task.cancel()
            try:
                await self._read_task
            except asyncio.CancelledError:
                pass
        if self._hb_task:
            self._hb_task.cancel()
            try:
                await self._hb_task
            except asyncio.CancelledError:
                pass
        if self._writer:
            self._writer.close()
        self._connected = False
        logger.info("Disconnected from Boat Pico")

    def _next_seq(self) -> int:
        """Get the next sequence number (1–255, skip 0 which is for unsolicited)."""
        self._seq = (self._seq % 255) + 1
        return self._seq

    async def _send_raw(self, data: bytes) -> None:
        """Write raw bytes to the serial port."""
        if not self._writer:
            raise ConnectionError("Not connected")
        self._writer.write(data)
        await self._writer.drain()

    async def _send_command(
        self, msg_type: str, *args: str | int | float
    ) -> ParsedFrame:
        """Send a command and wait for ACK/NAK with retries.

        Returns the response ParsedFrame on ACK.
        Raises TimeoutError on no reply, PicoNak (a RuntimeError) on refusal.
        """
        for attempt in range(self._max_retries):
            seq = self._next_seq()
            data = build_command(msg_type, seq, *args)

            # Create a future for this seq
            loop = asyncio.get_event_loop()
            fut: asyncio.Future[ParsedFrame] = loop.create_future()
            self._pending[seq] = fut

            try:
                await self._send_raw(data)
                logger.debug("TX [%d/%d] seq=%d: %s",
                             attempt + 1, self._max_retries, seq,
                             data.decode().strip())
                response = await asyncio.wait_for(fut, self._command_timeout)

                if response.msg_type == "NAK":
                    # NAK,<seq>,<command>,<reason> (serial-protocol.md §NAK), so
                    # fields[0] echoes the command and fields[1] is the reason.
                    # Reading fields[0] logged "SET_THR NAK'd: SET_THR" and hid
                    # the only useful part — ESTOP / RC_ACTIVE / RANGE / PARSE.
                    f = response.fields
                    reason = f[1] if len(f) > 1 else (f[0] if f else "UNKNOWN")
                    if reason == "ESTOP":
                        self.estopped = True
                    raise PicoNak(msg_type, reason)
                return response
            except asyncio.TimeoutError:
                logger.warning("Timeout on %s seq=%d (attempt %d/%d)",
                               msg_type, seq, attempt + 1, self._max_retries)
            finally:
                self._pending.pop(seq, None)

        raise TimeoutError(
            "Command %s failed after %d retries" % (msg_type, self._max_retries)
        )

    async def _read_loop(self) -> None:
        """Background task: read lines from serial, dispatch, and self-heal.

        If the link drops — the Pico resets/re-enumerates on a reflash, a power
        glitch, or another process grabs the port — reopen it with a backoff
        instead of tight-looping the same read error.

        Detecting that drop cannot rely on an error arriving. When the Pico resets
        and re-enumerates, the old fd is left open against a device that no longer
        exists: `readline()` then blocks forever, delivering neither data nor EOF,
        so the loop parks and every command times out for the rest of the process's
        life with nothing logged. Observed on 2026-07-30 — the Pico rebooted, came
        back as a fresh /dev/ttyACM0, and SET_THR timed out for four minutes while
        this loop sat waiting on the corpse of the old one. Hence the silence
        timeout: no frame for `silence_timeout` seconds *is* the error.
        """
        backoff = 0.5
        while True:
            try:
                if self._reader is None:
                    await self._open_streams()
                    logger.info("Reconnected to Boat Pico on %s", self._port)
                    backoff = 0.5
                try:
                    raw_line = await asyncio.wait_for(
                        self._reader.readline(), self._silence_timeout)
                except asyncio.TimeoutError:
                    raise ConnectionError(
                        "no frames for %.1fs (device gone or wedged?)"
                        % self._silence_timeout) from None
                if not raw_line:
                    # Empty read = EOF; the device most likely went away.
                    raise ConnectionError("empty read (device disconnected?)")
                line = raw_line.decode("ascii", errors="ignore").strip()
                if line:
                    msg = parse_frame(line)
                    if msg is None:
                        logger.debug("Bad frame: %s", line)
                    else:
                        self._dispatch(msg)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                await self._close_streams()
                logger.warning("Serial link lost (%s) — retrying in %.1fs", e, backoff)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 5.0)

    def _dispatch(self, msg: ParsedFrame) -> None:
        """Route a parsed message to the appropriate handler."""
        # Check if this is a response to a pending command
        if msg.msg_type in ("ACK", "NAK"):
            fut = self._pending.get(msg.seq)
            if fut and not fut.done():
                fut.set_result(msg)
            return

        # Response types with matching seq (REQ_TEL, POLL_POD, GET_STATUS)
        if msg.msg_type in ("TEL", "POD_DATA", "STATUS") and msg.seq != 0:
            fut = self._pending.get(msg.seq)
            if fut and not fut.done():
                fut.set_result(msg)
                # Also update local state for TEL
                if msg.msg_type == "TEL":
                    self._handle_tel(msg)
                return

        # Unsolicited messages (seq=0)
        if msg.msg_type == "TEL":
            self._handle_tel(msg)
        elif msg.msg_type == "ENV":
            self._handle_env(msg)
        elif msg.msg_type == "ALERT":
            self._handle_alert(msg)
        elif msg.msg_type == "POD_DATA":
            self._handle_pod_data(msg)
        else:
            logger.debug("Unhandled message: %s", msg.raw)

    def _handle_tel(self, msg: ParsedFrame) -> None:
        """Update telemetry from a TEL message."""
        f = msg.fields
        if len(f) < 10:
            return
        try:
            tel = Telemetry(
                lat=float(f[0]),
                lon=float(f[1]),
                heading=float(f[2]),
                speed_knots=float(f[3]),
                batt_v=float(f[4]),
                batt_pct=int(f[5]),
                hull=f[6],
                mt_left=float(f[7]),
                mt_right=float(f[8]),
                health=f[9],
            )
            # Appended per-motor current (TEL v1.1) — parsed only when present,
            # like the ENV v1.1 appendix, so older firmware still works.
            if len(f) >= 12:
                tel.curr_left = float(f[10])
                tel.curr_right = float(f[11])
            # A Pi-side GPS outranks TEL's lat/lon. This has to happen on every
            # frame because _handle_tel builds a *new* Telemetry each time, which
            # would otherwise clobber the injected position once a second.
            self._apply_external(tel)
            self.telemetry = tel
            if self._on_telemetry:
                self._on_telemetry(self.telemetry)
        except (ValueError, IndexError) as e:
            logger.debug("TEL parse error: %s", e)

    def _handle_env(self, msg: ParsedFrame) -> None:
        """Update environment from an ENV message.

        Fields 0-5 are ENV v1.0; 6-11 are the v1.1 appendix (enclosure SHT41 +
        M18 elec/winch battery rails). Parsed only when present so v1.0 firmware still works.
        """
        f = msg.fields
        if len(f) < 6:
            return
        try:
            env = Environment(
                air_temp=int(f[0]),
                air_humidity=int(f[1]),
                water_temp=float(f[2]),
                water_ec=float(f[3]),
                water_light=int(f[4]),
                bottom_contact=f[5] == "1",
            )
            if len(f) >= 12:
                env.enc_temp = float(f[6])
                env.enc_humidity = float(f[7])
                env.elec_batt_v = float(f[8])
                env.elec_batt_pct = int(f[9])
                env.winch_batt_v = float(f[10])
                env.winch_batt_pct = int(f[11])
            self.environment = env
            if self._on_environment:
                self._on_environment(self.environment)
        except (ValueError, IndexError) as e:
            logger.debug("ENV parse error: %s", e)

    def _handle_alert(self, msg: ParsedFrame) -> None:
        """Handle an ALERT message.

        `detail` can itself be multiple comma-separated sub-fields per
        serial-protocol.md §4.3 (e.g. BATT_LOW's <voltage>,<pct> or
        MOTOR_OVERHEAT's <side>,<temp_c>) — rejoin everything after
        severity/code so no sub-field is silently dropped.
        """
        f = msg.fields
        if len(f) < 2:
            return
        alert = Alert(
            severity=f[0],
            code=f[1],
            detail=",".join(f[2:]) if len(f) > 2 else "",
        )
        # With the GPS on the Pi, the Pico's own GPS is permanently unhealthy by
        # design (its UART1 RX is the shorted GP9). Firmware re-alerts about it
        # roughly every second, which buries every other alert and pins reported
        # state at WARN. Drop it — but only when we know the Pi owns position.
        if (self._ext_gps and alert.code == "SENSOR_FAULT"
                and alert.detail.split(",")[0] == "gps"):
            logger.debug("Suppressed SENSOR_FAULT,gps — the Pi owns position")
            return
        if alert.code in _ESTOP_ALERT_CODES:
            # The firmware's estop is latched — it stays refusing throttle until a
            # RESUME, long after the alert that caused it has scrolled away.
            self.estopped = True
        self.last_alert = alert
        logger.warning("ALERT [%s] %s: %s", alert.severity, alert.code, alert.detail)
        if self._on_alert:
            self._on_alert(alert)

    def _handle_pod_data(self, msg: ParsedFrame) -> None:
        """Handle a POD_DATA message."""
        f = msg.fields
        if len(f) < 5:
            return
        try:
            pod = PodData(
                water_temp=float(f[0]),
                salinity_ec=float(f[1]),
                light_pct=int(f[2]),
                bottom=f[3] == "1",
                leak=f[4] == "1",
                pressure_depth_m=float(f[5]) if len(f) > 5 else 0.0,
            )
            if self._on_pod_data:
                self._on_pod_data(pod)
        except (ValueError, IndexError) as e:
            logger.debug("POD_DATA parse error: %s", e)

    # ---- Public command methods ----

    async def set_throttle(self, left: int, right: int) -> ParsedFrame:
        """Send SET_THR command."""
        return await self._send_command("SET_THR", left, right)

    async def set_winch(self, speed: int) -> ParsedFrame:
        """Send SET_WINCH command."""
        return await self._send_command("SET_WINCH", speed)

    async def set_heading(self, heading: float) -> ParsedFrame:
        """Send SET_HDG command."""
        return await self._send_command("SET_HDG", heading)

    async def request_telemetry(self) -> ParsedFrame:
        """Send REQ_TEL and wait for the TEL response."""
        return await self._send_command("REQ_TEL")

    async def poll_pod(self) -> ParsedFrame:
        """Send POLL_POD and wait for POD_DATA response."""
        return await self._send_command("POLL_POD")

    async def emergency_stop(self) -> ParsedFrame:
        """Send ESTOP command."""
        # Latch locally first: if the ACK is what gets lost, the boat is still
        # stopped, and claiming otherwise is the dangerous direction to be wrong in.
        self.estopped = True
        return await self._send_command("ESTOP")

    async def resume(self) -> ParsedFrame:
        """Send RESUME command after ESTOP."""
        frame = await self._send_command("RESUME")
        self.estopped = False        # only on ACK — a NAK/timeout raises above
        return frame

    async def send_heartbeat(self) -> ParsedFrame:
        """Send HB command."""
        return await self._send_command("HB")

    async def set_trim(self, value: float) -> ParsedFrame:
        """Send SET_TRIM command."""
        return await self._send_command("SET_TRIM", value)

    async def calibrate_compass(self, true_bearing: float) -> ParsedFrame:
        """Send CAL_COMPASS command."""
        return await self._send_command("CAL_COMPASS", true_bearing)

    async def rc_override(self) -> ParsedFrame:
        """Send RC_OVERRIDE command."""
        return await self._send_command("RC_OVERRIDE")

    async def rc_release(self) -> ParsedFrame:
        """Send RC_RELEASE command."""
        return await self._send_command("RC_RELEASE")

    async def get_status(self) -> ParsedFrame:
        """Send GET_STATUS command."""
        return await self._send_command("GET_STATUS")

    async def esc_passthrough(self, esc_id: int, baud: int) -> ParsedFrame:
        """Send ESC_PASS — put the Boat Pico into AM32 ESC passthrough (the Pico
        then hands its USB-CDC to the ESC one-wire; disconnect right after so the
        port is free for am32.ca / the passthrough tool). See docs/esc_passthrough.md."""
        return await self._send_command("ESC_PASS", int(esc_id), int(baud))

    async def start_heartbeat(self, interval: float = 1.0) -> None:
        """Start sending periodic heartbeat messages.

        Args:
            interval: Seconds between heartbeats (default 1.0).
        """
        async def _hb_loop() -> None:
            while True:
                try:
                    await self.send_heartbeat()
                except Exception as e:
                    logger.warning("Heartbeat failed: %s", e)
                await asyncio.sleep(interval)

        self._hb_task = asyncio.create_task(_hb_loop())

    async def stop_heartbeat(self) -> None:
        """Stop the periodic heartbeat task."""
        if self._hb_task:
            self._hb_task.cancel()
            try:
                await self._hb_task
            except asyncio.CancelledError:
                pass
            self._hb_task = None
