"""API key authentication for REST endpoints and WebSocket connections.

Validates X-API-Key header against the configured key.
The key should be set via BOAT_API_KEY environment variable.
"""
from __future__ import annotations

import hmac
import logging
import os

from fastapi import HTTPException, Security, WebSocket
from fastapi.security import APIKeyHeader

logger = logging.getLogger(__name__)

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
_api_key: str | None = None


def configure(key: str | None = None) -> None:
    """Set the API key. Falls back to BOAT_API_KEY env var."""
    global _api_key
    _api_key = key or os.environ.get("BOAT_API_KEY")
    if not _api_key:
        logger.warning(
            "No API key configured — all endpoints are unprotected. "
            "Set BOAT_API_KEY environment variable for production."
        )


def _verify_key(key: str | None) -> bool:
    """Constant-time comparison of the provided key against the configured key."""
    if not _api_key:
        return True  # Dev mode — no key required
    if not key:
        return False
    return hmac.compare_digest(key.encode(), _api_key.encode())


def key_valid(key: str | None) -> bool:
    """Public key check for query-param-authenticated routes (e.g. MJPEG <img>).

    Returns True in dev mode (no key configured), matching require_api_key.
    """
    return _verify_key(key)


async def require_api_key(
    key: str | None = Security(_api_key_header),
) -> str:
    """Dependency that validates the API key on REST endpoints.

    Returns the key on success, raises 401/403 on failure.
    Skips validation if no key is configured (dev mode).
    """
    if not _api_key:
        return "dev-mode"
    if not key:
        raise HTTPException(status_code=401, detail="Missing X-API-Key header")
    if not _verify_key(key):
        raise HTTPException(status_code=403, detail="Invalid API key")
    return key


async def validate_ws(ws: WebSocket) -> bool:
    """Validate API key on WebSocket connection.

    Checks the key query parameter: ws://host/ws/telemetry?key=<api_key>
    Also accepts X-API-Key header (some WS clients support headers).
    Returns True if valid, closes the WebSocket and returns False otherwise.
    """
    if not _api_key:
        return True  # Dev mode

    # Check query parameter first (most WS clients can't set headers)
    key = ws.query_params.get("key")
    # Fall back to header
    if not key:
        key = ws.headers.get("x-api-key")

    if _verify_key(key):
        return True

    await ws.close(code=4003, reason="Invalid or missing API key")
    logger.warning("WebSocket auth failed from %s", ws.client.host if ws.client else "unknown")
    return False
