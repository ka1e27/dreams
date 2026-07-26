"""Tests for CameraProducer's capture accounting — the synchronized stereo
grab/retrieve and the fail-count/release state machine. No real camera needed."""
from __future__ import annotations

import numpy as np

from pi5.cv.camera import _READ_FAIL_LIMIT, CameraConfig, CameraProducer


class FakeCap:
    """Minimal cv2.VideoCapture stand-in driven by a queue of frames.

    grab() records the order it was called in (so we can assert both cameras are
    grabbed before either is retrieved) and reports whether a frame is available;
    retrieve() hands back the next frame and advances.
    """
    order: list[str] = []

    def __init__(self, name, frames):
        self.name = name
        self.frames = frames
        self.i = 0
        self.retrieved_before = None
        self.released = False

    def grab(self):
        FakeCap.order.append("grab:" + self.name)
        return self.i < len(self.frames)

    def retrieve(self):
        # Snapshot how many grabs happened before this retrieve — used to prove
        # both grabs landed before any retrieve (near-simultaneous latch).
        self.retrieved_before = list(FakeCap.order)
        if self.i < len(self.frames):
            f = self.frames[self.i]
            self.i += 1
            return (f is not None, f)
        return (False, None)

    def release(self):
        self.released = True


def _img(v=0):
    return np.full((4, 4, 3), v, dtype=np.uint8)


def test_grab_both_before_retrieve():
    FakeCap.order = []
    capl = FakeCap("L", [_img(1)])
    capr = FakeCap("R", [_img(2)])
    l_ok, left, r_ok, right = CameraProducer._grab_retrieve(capl, capr)
    assert l_ok and r_ok
    assert left is not None and right is not None
    # Both grabs must precede the first retrieve → minimal stereo skew.
    assert FakeCap.order[:2] == ["grab:L", "grab:R"]
    assert capl.retrieved_before[:2] == ["grab:L", "grab:R"]


def test_grab_single_camera():
    FakeCap.order = []
    capl = FakeCap("L", [_img(1)])
    l_ok, left, r_ok, right = CameraProducer._grab_retrieve(capl, None)
    assert l_ok and left is not None
    assert r_ok is False and right is None


def test_grab_handles_failed_grab():
    FakeCap.order = []
    capl = FakeCap("L", [])            # no frames → grab() False
    l_ok, left, r_ok, right = CameraProducer._grab_retrieve(capl, None)
    assert l_ok is False and left is None


def _producer():
    return CameraProducer(CameraConfig(left_device=0, right_device=None))


def test_account_ok_resets_fail_count():
    cp = _producer()
    cap = FakeCap("L", [])
    cp._fail[0] = 3
    frame, out_cap = cp._account(True, _img(5), cap, 0)
    assert frame is not None and out_cap is cap
    assert cp._fail[0] == 0


def test_account_transient_miss_keeps_handle():
    cp = _producer()
    cap = FakeCap("L", [])
    for _ in range(_READ_FAIL_LIMIT - 1):
        frame, out_cap = cp._account(False, None, cap, 0)
        assert frame is None and out_cap is cap    # kept
    assert not cap.released


def test_account_releases_after_limit():
    cp = _producer()
    cap = FakeCap("L", [])
    out_cap = cap
    for _ in range(_READ_FAIL_LIMIT):
        frame, out_cap = cp._account(False, None, cap, 0)
    assert out_cap is None          # dropped
    assert cap.released
