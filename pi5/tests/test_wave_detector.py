"""Tests for the incoming-wave detector (capsize avoidance)."""
import numpy as np

from pi5.cv.wave_detector import WaveConfig, WaveDetector


def _frame(horizon_y: int, w: int = 640, h: int = 360):
    """A crude sky-over-water frame with the horizon at row ``horizon_y``."""
    img = np.zeros((h, w, 3), np.uint8)
    img[:horizon_y] = (200, 180, 150)   # sky (BGR-ish)
    img[horizon_y:] = (120, 90, 40)     # water
    # a little texture so optical flow has features to track
    img[::7, ::7] = (255, 255, 255)
    return img


def test_rising_horizon_latches_incoming():
    """A horizon steadily rising toward the camera should raise severity and,
    after the persistence window, latch incoming=True."""
    wd = WaveDetector(WaveConfig(max_fps=1000, persist_frames=3,
                                 trigger_severity=0.3))
    early_sev = late_sev = 0.0
    latched = False
    y = 220
    for i in range(24):
        r = wd.analyze(_frame(y))
        if i == 4:
            early_sev = r.severity
        late_sev = r.severity
        latched = latched or r.incoming
        y = max(40, y - 5)              # horizon rises 5 px/frame
    assert late_sev > early_sev        # severity grew as the wave approached
    assert latched                     # eventually flagged incoming


def test_flat_scene_not_incoming():
    """A static horizon (calm water) must never flag an incoming wave."""
    wd = WaveDetector(WaveConfig(max_fps=1000, persist_frames=3,
                                 trigger_severity=0.3))
    incoming = False
    for _ in range(24):
        r = wd.analyze(_frame(200))    # horizon never moves
        incoming = incoming or r.incoming
    assert not incoming
    assert wd.result.severity < 0.3


def test_to_dict_shape():
    wd = WaveDetector(WaveConfig(max_fps=1000))
    wd.analyze(_frame(200))
    d = wd.to_dict()
    assert set(d) >= {"enabled", "incoming", "bearing_deg", "severity", "ttc_s"}
    assert isinstance(d["incoming"], bool)


def test_disabled_is_noop():
    wd = WaveDetector(WaveConfig(enabled=False))
    r = wd.analyze(_frame(120))
    assert r.incoming is False and r.severity == 0.0
