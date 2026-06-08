"""Network transport selector — WiFi, cellular, or auto.

Most of the heavy lifting (PPP / mobile broadband for the SIM7600,
wpa_supplicant for WiFi) lives at the OS level. This module just:

  * configures WiFi via ``nmcli`` when the user has provided credentials,
  * reports which interface is currently providing a route,
  * probes that the route can actually reach the cloud API, and
  * exposes ``is_online()`` so the uploader can skip pointless attempts
    during known dropouts.

In ``auto`` mode WiFi is preferred — when the boat is at the dock or on
the bench it'll use the WiFi network and leave the cellular SIM idle.
Push the boat away from the AP and the OS's route metric will favour
cellular automatically.
"""
from __future__ import annotations

import asyncio
import logging
import shutil
import socket
from dataclasses import dataclass
from typing import Literal

logger = logging.getLogger(__name__)

NetworkMode = Literal["wifi", "cellular", "auto"]


@dataclass
class WifiConfig:
    ssid: str = ""
    password: str = ""


@dataclass
class CellularConfig:
    device: str = "/dev/ttyUSB2"
    baud: int = 115200
    apn: str = "internet"


@dataclass
class NetworkConfig:
    mode: NetworkMode = "auto"
    wifi: WifiConfig | None = None
    cellular: CellularConfig | None = None
    online_probe_url: str = ""


# Linux interface name patterns we treat as each transport.
_WIFI_PATTERNS = ("wlan", "wifi", "wlp")
_CELLULAR_PATTERNS = ("ppp", "wwan", "usb")


class NetworkManager:
    """Tracks which transport is active and whether we can reach the cloud."""

    def __init__(self, cfg: NetworkConfig) -> None:
        self._cfg = cfg
        self._task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()
        self._online = False
        self._active_iface: str | None = None
        self._active_kind: Literal["wifi", "cellular", "other", "offline"] = "offline"

    # ---- Lifecycle ----

    async def start(self) -> None:
        # Best-effort WiFi configuration before the probe loop starts.
        if self._cfg.mode in ("wifi", "auto"):
            await self._ensure_wifi()
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            try:
                await self._task
            except Exception:
                pass

    # ---- Public state ----

    def is_online(self) -> bool:
        """True if the most recent probe reached the cloud."""
        return self._online

    @property
    def active_interface(self) -> str | None:
        return self._active_iface

    @property
    def active_kind(self) -> str:
        """One of: wifi, cellular, other, offline."""
        return self._active_kind

    def status(self) -> dict:
        """Snapshot for telemetry / dashboard."""
        return {
            "mode": self._cfg.mode,
            "active_kind": self._active_kind,
            "active_interface": self._active_iface,
            "online": self._online,
        }

    # ---- WiFi bring-up via nmcli ----

    async def _ensure_wifi(self) -> None:
        wifi = self._cfg.wifi
        if wifi is None or not wifi.ssid or not wifi.password:
            return  # OS-managed, nothing to do
        if shutil.which("nmcli") is None:
            logger.info("nmcli not available — leaving WiFi to OS configuration")
            return
        # Idempotent: nmcli will update the connection if it already exists.
        try:
            proc = await asyncio.create_subprocess_exec(
                "nmcli", "device", "wifi", "connect", wifi.ssid,
                "password", wifi.password,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            if proc.returncode != 0:
                logger.warning("nmcli wifi connect failed: %s",
                               stderr.decode(errors="ignore").strip())
            else:
                logger.info("WiFi associated with %s", wifi.ssid)
        except Exception as e:
            logger.warning("nmcli invocation failed: %s", e)

    # ---- Probe loop ----

    async def _loop(self) -> None:
        # Quick probes when offline (so we recover fast when WiFi pops up at
        # the dock); slower when online to avoid burning power/data.
        while not self._stop.is_set():
            try:
                await self._refresh()
            except Exception as e:
                logger.debug("network probe error: %s", e)
            interval = 30.0 if self._online else 5.0
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=interval)
            except asyncio.TimeoutError:
                pass

    async def _refresh(self) -> None:
        iface = await asyncio.to_thread(self._read_default_route_iface)
        kind = self._classify(iface)
        # In strict modes, only the matching transport counts as online.
        if self._cfg.mode == "wifi" and kind != "wifi":
            self._online = False
            self._active_iface = iface
            self._active_kind = kind if iface else "offline"
            return
        if self._cfg.mode == "cellular" and kind != "cellular":
            self._online = False
            self._active_iface = iface
            self._active_kind = kind if iface else "offline"
            return
        # In auto mode anything routable counts; do an actual reachability probe.
        ok = await self._probe()
        self._active_iface = iface
        self._active_kind = kind if iface else "offline"
        self._online = ok

    @staticmethod
    def _read_default_route_iface() -> str | None:
        """Return the interface name used for the default IPv4 route."""
        try:
            with open("/proc/net/route", "r") as f:
                next(f)  # header
                for line in f:
                    parts = line.split()
                    if len(parts) < 4:
                        continue
                    iface, dest, _gateway, flags = parts[0], parts[1], parts[2], parts[3]
                    # Default route: destination 0x00000000 and RTF_UP (0x1)
                    if dest == "00000000" and (int(flags, 16) & 0x1):
                        return iface
        except FileNotFoundError:
            return None
        except Exception:
            return None
        return None

    @staticmethod
    def _classify(iface: str | None) -> Literal["wifi", "cellular", "other", "offline"]:
        if not iface:
            return "offline"
        lower = iface.lower()
        if any(lower.startswith(p) for p in _WIFI_PATTERNS):
            return "wifi"
        if any(lower.startswith(p) for p in _CELLULAR_PATTERNS):
            return "cellular"
        return "other"

    async def _probe(self) -> bool:
        """Cheap reachability check. Prefers a TCP connect over a full HTTP
        request so we don't accumulate cellular bytes on every probe."""
        host, port = self._probe_target()
        if host is None:
            return False
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(_tcp_connect, host, port), timeout=5.0
            )
        except asyncio.TimeoutError:
            return False
        except Exception:
            return False

    def _probe_target(self) -> tuple[str | None, int]:
        url = self._cfg.online_probe_url
        if not url:
            # Fall back to the cloud root if the user hasn't set one.
            return None, 0
        from urllib.parse import urlparse
        try:
            u = urlparse(url)
            host = u.hostname
            port = u.port or (443 if u.scheme == "https" else 80)
            return host, port
        except Exception:
            return None, 0


def _tcp_connect(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=4.0):
            return True
    except OSError:
        return False
