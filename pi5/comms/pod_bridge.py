"""Pod sensor bridge — request pod data through the Boat Pico.

The Pi 5 doesn't talk to the pod directly. It sends POLL_POD to the
Boat Pico, which forwards the poll to the Pod Pico over UART and
relays the response back.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field

from .pico_serial import PicoSerial, PodData

logger = logging.getLogger(__name__)


@dataclass
class PodReading:
    """A timestamped pod sensor reading."""
    timestamp: float
    water_temp: float
    salinity_ec: float
    light_pct: int
    bottom_contact: bool
    leak_detected: bool

    @classmethod
    def from_pod_data(cls, pod: PodData) -> PodReading:
        """Create from a PodData message."""
        return cls(
            timestamp=time.time(),
            water_temp=pod.water_temp,
            salinity_ec=pod.salinity_ec,
            light_pct=pod.light_pct,
            bottom_contact=pod.bottom,
            leak_detected=pod.leak,
        )


class PodBridge:
    """Manages periodic pod polling and maintains a reading history."""

    def __init__(self, pico: PicoSerial, poll_interval: float = 5.0) -> None:
        self._pico = pico
        self._poll_interval = poll_interval
        self._latest: PodReading | None = None
        self._history: list[PodReading] = []
        self._max_history = 1000
        self._task: asyncio.Task[None] | None = None
        self._pod_ok = False

    @property
    def latest(self) -> PodReading | None:
        """Most recent pod reading."""
        return self._latest

    @property
    def pod_ok(self) -> bool:
        """True if the pod is responding."""
        return self._pod_ok

    @property
    def history(self) -> list[PodReading]:
        """History of pod readings."""
        return self._history

    async def poll_once(self) -> PodReading | None:
        """Poll the pod once and return the reading, or None on failure."""
        try:
            response = await self._pico.poll_pod()
            if response.msg_type == "POD_DATA":
                pod = PodData(
                    water_temp=float(response.fields[0]),
                    salinity_ec=float(response.fields[1]),
                    light_pct=int(response.fields[2]),
                    bottom=response.fields[3] == "1",
                    leak=response.fields[4] == "1",
                )
                reading = PodReading.from_pod_data(pod)
                self._latest = reading
                self._history.append(reading)
                if len(self._history) > self._max_history:
                    self._history = self._history[-self._max_history:]
                self._pod_ok = True
                return reading
        except TimeoutError:
            logger.warning("Pod poll timed out")
            self._pod_ok = False
        except RuntimeError as e:
            logger.warning("Pod poll failed: %s", e)
            self._pod_ok = False
        except (ValueError, IndexError) as e:
            logger.warning("Pod data parse error: %s", e)
        return None

    async def start(self, interval: float | None = None) -> None:
        """Start periodic pod polling in the background."""
        if interval is not None:
            self._poll_interval = interval

        async def _poll_loop() -> None:
            while True:
                await self.poll_once()
                await asyncio.sleep(self._poll_interval)

        self._task = asyncio.create_task(_poll_loop())

    async def stop(self) -> None:
        """Stop periodic polling."""
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    def clear_history(self) -> None:
        """Clear the reading history."""
        self._history.clear()
