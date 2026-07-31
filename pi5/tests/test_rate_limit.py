"""Tests for the dashboard rate limiter.

These exist because of a live failure: manual override repeats
POST /api/manual/drive at 10 Hz, the limiter counted every path against one
60 rpm per-IP bucket, and six seconds in the operator was 429'd off their own
boat — the drive commands *and* the map, obstacle and recording polls with them.
The invariants worth locking down are that a control-rate stream survives a full
minute and that it cannot starve the other endpoints.

Driven through `dispatch()` with a fake request rather than an HTTP client: the
repo has no httpx, and the middleware's whole logic is in that one method.
"""
from __future__ import annotations

import asyncio

from starlette.responses import Response

from pi5.server.rate_limit import RateLimitMiddleware


class _FakeURL:
    def __init__(self, path: str) -> None:
        self.path = path


class _FakeClient:
    def __init__(self, host: str) -> None:
        self.host = host


class _FakeRequest:
    """The three attributes RateLimitMiddleware.dispatch actually reads."""

    def __init__(self, path: str, ip: str = "10.0.0.5", upgrade: str = "") -> None:
        self.url = _FakeURL(path)
        self.client = _FakeClient(ip)
        self.headers = {"upgrade": upgrade} if upgrade else {}


async def _call_next(_request):
    return Response(status_code=200)


def _mw(**kwargs) -> RateLimitMiddleware:
    return RateLimitMiddleware(app=None, **kwargs)


def _hit(mw: RateLimitMiddleware, path: str, ip: str = "10.0.0.5") -> int:
    """Send one request through the middleware, return the status code."""
    resp = asyncio.run(mw.dispatch(_FakeRequest(path, ip), _call_next))
    return resp.status_code


def _hit_n(mw: RateLimitMiddleware, path: str, n: int, ip: str = "10.0.0.5") -> list[int]:
    return [_hit(mw, path, ip) for _ in range(n)]


class TestManualDrive:
    """The 10 Hz operator-input path must survive being used as intended."""

    def test_a_full_minute_of_10hz_drive_is_not_limited(self):
        mw = _mw()
        codes = _hit_n(mw, "/api/manual/drive", 600)
        assert set(codes) == {200}

    def test_drive_does_not_starve_other_endpoints(self):
        """The original bug: drive traffic burned the shared budget, and the
        dashboard's own polling started 429'ing."""
        mw = _mw()
        _hit_n(mw, "/api/manual/drive", 600)
        assert _hit(mw, "/api/map/objects") == 200
        assert _hit(mw, "/api/telemetry") == 200

    def test_two_armed_tabs_are_not_limited(self):
        """One armed tab was measured at ~15/s (timer + keydown/keyup sends), so
        the cap has to clear a full minute of that with a tab to spare."""
        mw = _mw()
        codes = _hit_n(mw, "/api/manual/drive", 900 * 2)
        assert set(codes) == {200}

    def test_drive_is_still_bounded(self):
        """Not unlimited — a runaway client loop still gets cut off."""
        mw = _mw()
        codes = _hit_n(mw, "/api/manual/drive", 1900)
        assert 429 in codes


class TestOtherPaths:
    """Everything else keeps a limit; the sensitive paths keep a tight one."""

    def test_default_limit_enforced(self):
        mw = _mw(default_rpm=10)
        codes = _hit_n(mw, "/api/map/objects", 12)
        assert codes[:10] == [200] * 10
        assert codes[10:] == [429, 429]

    def test_default_limit_covers_the_dashboard_idle_poll_rate(self):
        """Idle polling is ~70 rpm (objects 2 s + obstacles 3 s + recordings 3 s).
        The shipped default has to clear that with room to spare."""
        mw = _mw()
        assert mw._get_limit("/api/map/objects") >= 150

    def test_estop_keeps_its_strict_limit(self):
        mw = _mw()
        codes = _hit_n(mw, "/api/estop", 12)
        assert codes[:10] == [200] * 10
        assert codes[10:] == [429, 429]

    def test_estop_budget_is_not_consumed_by_other_traffic(self):
        """A limiter that lets ordinary polling eat the E-STOP budget is worse
        than no limiter."""
        mw = _mw()
        _hit_n(mw, "/api/manual/drive", 600)
        _hit_n(mw, "/api/map/objects", 200)
        assert _hit(mw, "/api/estop") == 200

    def test_per_ip_isolation(self):
        mw = _mw(default_rpm=5)
        assert _hit_n(mw, "/api/map/objects", 6, ip="10.0.0.5")[-1] == 429
        assert _hit(mw, "/api/map/objects", ip="10.0.0.9") == 200

    def test_non_api_and_websocket_paths_are_skipped(self):
        mw = _mw(default_rpm=1)
        assert _hit_n(mw, "/static/app.js", 5) == [200] * 5
        resp = asyncio.run(mw.dispatch(
            _FakeRequest("/api/ws/telemetry", upgrade="websocket"), _call_next))
        assert resp.status_code == 200
