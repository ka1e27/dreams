"""Tests for the Pi health probes and the inference CPU budget.

Both exist to keep the always-on loops cheap on a Pi 5 without losing the
under-voltage diagnostics this project depends on.
"""
from __future__ import annotations

import inspect

import pi5.server.app as app
from pi5.cv.cpu_budget import inference_threads

# -- throttle decoding ------------------------------------------------------ #

def test_throttled_now_ignores_the_sticky_occurred_bits():
    """0x50000 = 'under-voltage occurred' + 'throttling occurred'. Those latch
    until reboot, so treating them as live would make the conditional clock probe
    fork forever after the first dip."""
    assert app._throttled_now("0x50000") is False


def test_throttled_now_detects_live_conditions():
    assert app._throttled_now("0x1") is True       # under-voltage NOW
    assert app._throttled_now("0x4") is True       # throttled NOW
    assert app._throttled_now("0x50001") is True   # live + sticky together


def test_throttled_now_on_clean_and_garbage_input():
    assert app._throttled_now("0x0") is False
    assert app._throttled_now(None) is False
    assert app._throttled_now("") is False
    assert app._throttled_now("not-hex") is False


def test_decode_throttled_still_reports_sticky_bits_to_the_operator():
    """_throttled_now ignoring sticky bits must NOT hide them from the UI — the
    dashboard is how the user learned about the brown-outs in the first place."""
    raw, human = app._decode_throttled("throttled=0x50000")
    assert raw == "0x50000"
    assert "under-voltage occurred" in human
    assert "throttling occurred" in human


# -- sysfs reads ------------------------------------------------------------ #

def test_read_sysfs_float_scales(tmp_path):
    p = tmp_path / "temp"
    p.write_text("52900\n")
    assert app._read_sysfs_float(str(p), 1e-3) == 52.9      # milli°C → °C


def test_read_sysfs_float_missing_or_bad_returns_none(tmp_path):
    assert app._read_sysfs_float(str(tmp_path / "nope"), 1.0) is None
    bad = tmp_path / "bad"
    bad.write_text("not a number")
    assert app._read_sysfs_float(str(bad), 1.0) is None


# -- volts cache ------------------------------------------------------------ #

def test_volts_cache_state_starts_unsampled():
    """The cache is keyed off a separate _volts_sampled flag, not on the value
    being non-None: off a Pi the reading legitimately IS None, and a
    `is not None` guard would re-fork four probes every single tick."""
    assert hasattr(app, "_volts_sampled")
    # the guard in _sampled_volts must consult the flag, not the value
    src = inspect.getsource(app._sampled_volts)
    assert "_volts_sampled" in src
    assert "_volts_cache is not None" not in src


# -- inference thread budget ------------------------------------------------ #

def test_auto_leaves_headroom_on_a_quad_core(monkeypatch):
    monkeypatch.setattr("pi5.cv.cpu_budget.os.cpu_count", lambda: 4)
    assert inference_threads() == 2          # measured: ~96% of 4-thread speed
    assert inference_threads(0) == 2
    assert inference_threads(None) == 2


def test_explicit_request_wins_but_is_clamped(monkeypatch):
    monkeypatch.setattr("pi5.cv.cpu_budget.os.cpu_count", lambda: 4)
    assert inference_threads(1) == 1
    assert inference_threads(3) == 3
    assert inference_threads(99) == 4        # never exceed the core count


def test_never_returns_less_than_one(monkeypatch):
    for cores in (1, 2):
        monkeypatch.setattr("pi5.cv.cpu_budget.os.cpu_count", lambda c=cores: c)
        assert inference_threads() >= 1


def test_unknown_core_count_is_survivable(monkeypatch):
    monkeypatch.setattr("pi5.cv.cpu_budget.os.cpu_count", lambda: None)
    assert inference_threads() == 2          # falls back to assuming 4 cores


def test_garbage_request_falls_back_to_auto(monkeypatch):
    monkeypatch.setattr("pi5.cv.cpu_budget.os.cpu_count", lambda: 4)
    assert inference_threads("nonsense") == 2
    assert inference_threads(-4) == 2
