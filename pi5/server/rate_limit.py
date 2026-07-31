"""Rate limiting middleware using a sliding window counter.

Limits requests per (IP, path class). No external dependencies — uses an
in-memory dict with automatic cleanup.

Counting is **per path class, not per IP as a whole**. One global per-IP bucket
meant a chatty endpoint starved every other one: manual override repeats
/api/manual/drive at 10 Hz (600 rpm), which burned a 60 rpm budget in six
seconds and then 429'd the operator out of their own dashboard — map objects,
telemetry, even the E-STOP. Separate buckets keep a control-rate stream from
crowding out the endpoints that matter.

The trade-off: an abuser willing to spread traffic across path classes gets the
sum of the limits rather than one ceiling. That's accepted — this limiter exists
to bound runaway client loops and accidental hammering, not to stop a determined
attacker (the API key in `auth.py` and Tailscale-only exposure do that).
"""
from __future__ import annotations

import time
from collections import defaultdict

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Per-IP, per-path-class rate limiter.

    Three classes, most specific first:
      * high-rate control paths — operator input repeated at a fixed tick
      * strict paths — auth-sensitive / destructive actions
      * everything else — `default_rpm`
    WebSocket upgrades are not limited here; they go through their own auth.
    """

    def __init__(self, app, default_rpm: int = 300, burst_rpm: int = 120):
        super().__init__(app)
        self._default_rpm = default_rpm
        self._burst_rpm = burst_rpm
        # {(ip, bucket): [timestamp, ...]}
        self._requests: dict[tuple[str, str], list[float]] = defaultdict(list)
        self._last_cleanup = time.monotonic()
        self._cleanup_interval = 60.0  # seconds

        # Operator-input paths the dashboard repeats on a timer. /api/manual/drive
        # ticks at MAN_HZ = 10 in command_center.html and every frame matters — the
        # all-zero ones are what stop the boat on key release and what feed the
        # navigator's dead-man timer.
        #
        # Sized from measurement, not from MAN_HZ: one armed tab was observed
        # sustaining ~15/s (900 rpm) — the timer plus the extra immediate sends on
        # keydown/keyup — which sat exactly on a 900 rpm cap and tripped it. 1800
        # leaves room for that plus a second tab or a reload, and still bounds a
        # runaway loop.
        self._high_rate_paths = {
            "/api/manual/drive": 1800,
        }

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
        stale_keys = []
        for key, timestamps in self._requests.items():
            self._requests[key] = [t for t in timestamps if t > cutoff]
            if not self._requests[key]:
                stale_keys.append(key)
        for key in stale_keys:
            del self._requests[key]
        self._last_cleanup = now

    def _classify(self, path: str) -> tuple[str, int]:
        """Return the (bucket, limit) a path counts against."""
        for prefix, limit in self._high_rate_paths.items():
            if path.startswith(prefix):
                return prefix, limit
        for prefix, limit in self._strict_paths.items():
            if path.startswith(prefix):
                return prefix, limit
        return "default", self._default_rpm

    def _get_limit(self, path: str) -> int:
        """Return the rate limit for a given path."""
        return self._classify(path)[1]

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
        bucket, limit = self._classify(request.url.path)
        key = (ip, bucket)

        # Count requests in the last 60 seconds for this bucket
        recent = [t for t in self._requests[key] if t > cutoff]
        self._requests[key] = recent

        if len(recent) >= limit:
            retry_after = int(60 - (now - recent[0])) + 1
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded. Try again in %d seconds." % retry_after},
                headers={"Retry-After": str(retry_after)},
            )

        self._requests[key].append(now)

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(max(0, limit - len(recent) - 1))
        return response
