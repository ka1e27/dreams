"""Cloud data uploader — buffer locally, flush when online.

Collects sensor readings with GPS coordinates and uploads them to the
cloud API on a configurable interval. Buffers to a local JSON file
when cellular is unavailable and flushes when connectivity returns.
"""
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import asdict, dataclass
from pathlib import Path

import aiohttp

logger = logging.getLogger(__name__)

BUFFER_FILE = Path("/home/pi/boat/data/upload_buffer.json")


@dataclass
class ReadingPayload:
    """A sensor reading ready for upload."""
    timestamp: str
    lat: float
    lon: float
    water_temp: float | None = None
    salinity_ec: float | None = None
    light_pct: int | None = None
    depth_m: float | None = None
    air_temp: float | None = None
    air_humidity: float | None = None
    batt_v: float | None = None
    mission_name: str | None = None
    waypoint_idx: int | None = None


@dataclass
class TrackPayload:
    """A GPS track point ready for upload."""
    timestamp: str
    lat: float
    lon: float
    heading: float | None = None
    speed_knots: float | None = None
    mission_name: str | None = None


class CloudUploader:
    """Buffers sensor data locally and uploads to the cloud API."""

    def __init__(
        self,
        api_url: str,
        api_key: str = "",
        upload_interval_s: float = 30.0,
        buffer_path: Path | str = BUFFER_FILE,
        max_buffer_size: int = 10000,
    ) -> None:
        self._api_url = api_url.rstrip("/")
        self._api_key = api_key
        self._interval = upload_interval_s
        self._buffer_path = Path(buffer_path)
        self._max_buffer = max_buffer_size

        self._readings: list[dict] = []
        self._track: list[dict] = []
        self._task: asyncio.Task[None] | None = None

        # Load any buffered data from previous session
        self._load_buffer()

    def _load_buffer(self) -> None:
        """Load buffered readings from disk."""
        if not self._buffer_path.exists():
            return
        try:
            data = json.loads(self._buffer_path.read_text())
            self._readings = data.get("readings", [])
            self._track = data.get("track", [])
            if self._readings or self._track:
                logger.info("Loaded %d buffered readings, %d track points",
                             len(self._readings), len(self._track))
        except Exception as e:
            logger.warning("Failed to load buffer: %s", e)

    def _save_buffer(self) -> None:
        """Save buffered readings to disk for persistence across restarts."""
        try:
            self._buffer_path.parent.mkdir(parents=True, exist_ok=True)
            data = {"readings": self._readings[-self._max_buffer:],
                    "track": self._track[-self._max_buffer:]}
            self._buffer_path.write_text(json.dumps(data))
        except Exception as e:
            logger.warning("Failed to save buffer: %s", e)

    def add_reading(self, reading: ReadingPayload) -> None:
        """Add a sensor reading to the upload buffer."""
        self._readings.append(asdict(reading))
        if len(self._readings) > self._max_buffer:
            self._readings = self._readings[-self._max_buffer:]

    def add_track_point(self, point: TrackPayload) -> None:
        """Add a GPS track point to the upload buffer."""
        self._track.append(asdict(point))
        if len(self._track) > self._max_buffer:
            self._track = self._track[-self._max_buffer:]

    async def _upload_batch(self, session: aiohttp.ClientSession,
                            endpoint: str, payload: dict) -> bool:
        """Upload a batch of data. Returns True on success."""
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["X-API-Key"] = self._api_key
        try:
            async with session.post(
                f"{self._api_url}{endpoint}",
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status in (200, 201):
                    return True
                body = await resp.text()
                logger.warning("Upload to %s failed: %d %s", endpoint, resp.status, body)
                return False
        except aiohttp.ClientError as e:
            logger.debug("Upload connection error: %s", e)
            return False
        except Exception as e:
            logger.warning("Upload error: %s", e)
            return False

    async def flush(self) -> None:
        """Attempt to upload all buffered data."""
        if not self._readings and not self._track:
            return

        async with aiohttp.ClientSession() as session:
            # Upload readings in batches of 500
            while self._readings:
                batch = self._readings[:500]
                ok = await self._upload_batch(
                    session, "/api/v1/readings", {"readings": batch}
                )
                if ok:
                    self._readings = self._readings[500:]
                    logger.info("Uploaded %d readings (%d remaining)",
                                len(batch), len(self._readings))
                else:
                    logger.info("Upload failed — %d readings buffered", len(self._readings))
                    break

            # Upload track points
            while self._track:
                batch = self._track[:500]
                ok = await self._upload_batch(session, "/api/v1/track", batch)
                if ok:
                    self._track = self._track[500:]
                else:
                    break

        self._save_buffer()

    async def _upload_loop(self) -> None:
        """Background loop — flush buffer periodically."""
        while True:
            try:
                await self.flush()
            except Exception as e:
                logger.warning("Upload loop error: %s", e)
                self._save_buffer()
            await asyncio.sleep(self._interval)

    async def start(self) -> None:
        """Start the background upload loop."""
        self._task = asyncio.create_task(self._upload_loop())

    async def stop(self) -> None:
        """Stop the upload loop and save buffer."""
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._save_buffer()
