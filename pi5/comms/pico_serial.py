"""Async serial connection to the Boat Pico.

Sends commands, receives responses and unsolicited telemetry/alerts
over USB serial using the protocol from docs/serial-protocol.md.
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import serial_asyncio

from .protocol import ParsedFrame, build_command, checksum, parse_frame

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


@dataclass
class Environment:
    """Latest environment data from the Boat Pico."""
    air_temp: int = 0
    air_humidity: int = 0
    water_temp: float = -999.0
    water_ec: float = 0.0
    water_light: int = 0
    bottom_contact: bool = False


@dataclass
class PodData:
    """Pod sensor reading."""
    water_temp: float = -999.0
    salinity_ec: float = 0.0
    light_pct: int = 0
    bottom: bool = False
    leak: bool = False


@dataclass
class Alert:
    """An alert from the Boat Pico."""
    severity: str = ""
    code: str = ""
    detail: str = ""


class PicoSerial:
    """Async serial interface to the Boat Pico."""

    def __init__(
        self,
        port: str = "/dev/ttyACM0",
        baud: int = 115200,
        command_timeout: float = 2.0,
        max_retries: int = 3,
    ) -> None:
        self._port = port
        self._baud = baud
        self._command_timeout = command_timeout
        self._max_retries = max_retries

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

    async def connect(self) -> None:
        """Open the serial connection and start the read loop."""
        try:
            self._reader, self._writer = await serial_asyncio.open_serial_connection(
                url=self._port, baudrate=self._baud
            )
            self._connected = True
            self._read_task = asyncio.create_task(self._read_loop())
            logger.info("Connected to Boat Pico on %s @ %d", self._port, self._baud)
        except Exception as e:
            self._connected = False
            logger.error("Failed to connect to %s: %s", self._port, e)
            raise

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
        Raises TimeoutError or RuntimeError on failure.
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
                    reason = response.fields[0] if response.fields else "UNKNOWN"
                    raise RuntimeError(
                        "Command %s NAK'd: %s" % (msg_type, reason)
                    )
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
        """Background task: read lines from serial and dispatch."""
        assert self._reader is not None
        while True:
            try:
                raw_line = await self._reader.readline()
                if not raw_line:
                    continue
                line = raw_line.decode("ascii", errors="ignore").strip()
                if not line:
                    continue
                msg = parse_frame(line)
                if msg is None:
                    logger.debug("Bad frame: %s", line)
                    continue
                self._dispatch(msg)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error("Read loop error: %s", e)
                await asyncio.sleep(0.1)

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
            self.telemetry = Telemetry(
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
            if self._on_telemetry:
                self._on_telemetry(self.telemetry)
        except (ValueError, IndexError) as e:
            logger.debug("TEL parse error: %s", e)

    def _handle_env(self, msg: ParsedFrame) -> None:
        """Update environment from an ENV message."""
        f = msg.fields
        if len(f) < 6:
            return
        try:
            self.environment = Environment(
                air_temp=int(f[0]),
                air_humidity=int(f[1]),
                water_temp=float(f[2]),
                water_ec=float(f[3]),
                water_light=int(f[4]),
                bottom_contact=f[5] == "1",
            )
            if self._on_environment:
                self._on_environment(self.environment)
        except (ValueError, IndexError) as e:
            logger.debug("ENV parse error: %s", e)

    def _handle_alert(self, msg: ParsedFrame) -> None:
        """Handle an ALERT message."""
        f = msg.fields
        if len(f) < 2:
            return
        alert = Alert(
            severity=f[0],
            code=f[1],
            detail=f[2] if len(f) > 2 else "",
        )
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
        return await self._send_command("ESTOP")

    async def resume(self) -> ParsedFrame:
        """Send RESUME command after ESTOP."""
        return await self._send_command("RESUME")

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
