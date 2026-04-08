"""Rate limiting middleware using a sliding window counter.

Limits requests per IP address. No external dependencies — uses an
in-memory dict with automatic cleanup.
"""
from __future__ import annotations

import time
from collections import defaultdict

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Per-IP rate limiter with configurable limits per path prefix.

    Default: 60 requests/minute for API endpoints, 10/minute for auth-sensitive
    endpoints (estop, mission control). WebSocket upgrade requests are not limited
    here — they go through their own auth.
    """

    def __init__(self, app, default_rpm: int = 60, burst_rpm: int = 120):
        super().__init__(app)
        self._default_rpm = default_rpm
        self._burst_rpm = burst_rpm
        # {ip: [(timestamp, path_prefix), ...]}
        self._requests: dict[str, list[float]] = defaultdict(list)
        self._last_cleanup = time.monotonic()
        self._cleanup_interval = 60.0  # seconds

        # Stricter limits for sensitive endpoints (requests per minute)
        self._strict_paths = {
            "/api/estop": 10,
            "/api/resume": 10,
            "/api/rth": 10,
            "/api/mission": 20,
            "/api/goto": 20,
        }

    def _cleanup(self) -> None:
        """Remove entries older than 60 seconds."""
        now = time.monotonic()
        if now - self._last_cleanup < self._cleanup_interval:
            return
        cutoff = now - 60.0
        stale_ips = []
        for ip, timestamps in self._requests.items():
            self._requests[ip] = [t for t in timestamps if t > cutoff]
            if not self._requests[ip]:
                stale_ips.append(ip)
        for ip in stale_ips:
            del self._requests[ip]
        self._last_cleanup = now

    def _get_limit(self, path: str) -> int:
        """Return the rate limit for a given path."""
        for prefix, limit in self._strict_paths.items():
            if path.startswith(prefix):
                return limit
        return self._default_rpm

    async def dispatch(self, request: Request, call_next) -> Response:
        # Skip rate limiting for WebSocket upgrades
        if request.headers.get("upgrade", "").lower() == "websocket":
            return await call_next(request)

        # Skip non-API paths (e.g. static files)
        if not request.url.path.startswith("/api"):
            return await call_next(request)

        self._cleanup()

        ip = request.client.host if request.client else "unknown"
        now = time.monotonic()
        cutoff = now - 60.0
        limit = self._get_limit(request.url.path)

        # Count requests in the last 60 seconds
        recent = [t for t in self._requests[ip] if t > cutoff]
        self._requests[ip] = recent

        if len(recent) >= limit:
            retry_after = int(60 - (now - recent[0])) + 1
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded. Try again in %d seconds." % retry_after},
                headers={"Retry-After": str(retry_after)},
            )

        self._requests[ip].append(now)

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(max(0, limit - len(recent) - 1))
        return response
