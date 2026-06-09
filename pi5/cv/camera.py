"""Dual-camera capture producer.

Wraps two cv2.VideoCapture handles into a single asyncio-friendly producer
that consumers can subscribe to. Frames come out as synchronized
(left, right, ts) tuples so the dashboard streamer and the stereo / YOLO
pipelines all share the same image source.
"""
from __future__ import annotations

import asyncio
import logging
import sys
import time
from dataclasses import dataclass

import cv2

logger = logging.getLogger(__name__)

# Consecutive failed reads before a camera is treated as disconnected (so one
# bad frame doesn't trigger a needless reopen). At 30 fps this trips in ~0.2s.
_READ_FAIL_LIMIT = 5

# How often the loop wakes to look for a returning camera while one is down.
# This is just the poll cadence — actual reopen attempts are rate-limited to
# reconnect_interval_s inside _reconnect(), so a returning camera is picked up
# promptly without hammering cv2.VideoCapture(open) faster than the interval.
_DOWN_POLL_S = 0.2


def _fourcc_to_str(val: float) -> str:
    """Decode an OpenCV CAP_PROP_FOURCC value into its 4-char code (e.g. 'YUYV')."""
    v = int(val)
    if v <= 0:
        return ""
    return "".join(chr((v >> (8 * i)) & 0xFF) for i in range(4)).strip("\x00 ")


@dataclass
class CameraConfig:
    left_device: int = 0
    right_device: int = 1
    width: int = 640
    height: int = 480
    fps: int = 30
    # Pixel format the camera is asked to deliver (FourCC). "MJPG" = compressed
    # (light over USB, but the module may cap its MJPG modes, e.g. 1080p@15).
    # "YUY2"/"YUYV" = uncompressed 4:2:2 (no decode cost, dodges the MJPG fps
    # caps, but ~16 bpp → needs much more USB bandwidth). "" = camera default.
    fourcc: str = "MJPG"
    # If a camera stops delivering frames (USB unplugged, driver hiccup) the
    # producer releases it and retries the same device index this often
    # (seconds) until it returns. The feed shows the NO-SIGNAL placeholder
    # meanwhile and recovers automatically — no restart needed.
    reconnect_interval_s: float = 2.0


@dataclass
class StereoFrame:
    left: "cv2.Mat"
    right: "cv2.Mat | None"
    ts: float


class CameraProducer:
    """Opens both cameras and broadcasts captured frames to subscribers.

    The producer is started once (in the FastAPI app's lifespan) and runs
    until shutdown. Subscribers attach an asyncio.Queue via subscribe().
    """

    def __init__(self, cfg: CameraConfig) -> None:
        self._cfg = cfg
        self._cap_l: cv2.VideoCapture | None = None
        self._cap_r: cv2.VideoCapture | None = None
        self._task: asyncio.Task[None] | None = None
        self._subscribers: list[asyncio.Queue[StereoFrame]] = []
        self._latest: StereoFrame | None = None
        self._stop = asyncio.Event()
        # Auto-reconnect state. Right is only retried after it has been present
        # at least once (so a single-camera rig never polls a missing device).
        self._right_ever_open = False
        # Keyed by device index: consecutive read failures + last reopen attempt.
        self._fail: dict[int, int] = {}
        self._last_reopen: dict[int, float] = {}
        self._reconnect_interval = max(0.5, float(cfg.reconnect_interval_s))

    def start(self) -> None:
        if self._task is not None:
            return
        self._cap_l = self._open(self._cfg.left_device)
        # Right is optional — if it fails, stereo features stay off but the
        # left-camera dashboard stream still works.
        try:
            self._cap_r = self._open(self._cfg.right_device)
            self._right_ever_open = True
        except Exception as e:
            logger.warning("Right camera unavailable: %s", e)
            self._cap_r = None
        self._task = asyncio.create_task(self._loop())

    def _open(self, device: int) -> cv2.VideoCapture:
        # On Linux (the Pi) force the V4L2 backend. With OpenCV's default backend
        # the FOURCC + resolution sets below often DON'T take, which leaves a raw
        # sensor like the IMX219 stuck in its native 8MP mode — and 3280x2464
        # over USB is only ~5 fps. Forcing V4L2 makes the format switch apply, so
        # the camera actually drops to the requested (binned, fast) mode.
        if sys.platform.startswith("linux"):
            cap = cv2.VideoCapture(device, cv2.CAP_V4L2)
        else:
            cap = cv2.VideoCapture(device)
        if not cap.isOpened():
            raise RuntimeError(f"camera {device} failed to open")
        # Request the pixel format (FourCC) before resolution/fps. MJPG is
        # compressed — light over USB but the module may cap its MJPG modes
        # (e.g. 1080p@15). YUY2/YUYV is uncompressed 4:2:2 — no decode cost and
        # it dodges the MJPG fps caps, but at ~16 bpp it needs far more USB
        # bandwidth (1080p30 ≈ 1 Gbit/s → USB 3.0 only; fine at 720p/VGA).
        # OpenCV falls back automatically if the camera refuses the format.
        fourcc = self._cfg.fourcc.strip()
        if sys.platform.startswith("linux") and fourcc.upper() == "YUY2":
            fourcc = "YUYV"  # V4L2's label for the identical 4:2:2 format
        if fourcc:
            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*fourcc[:4]))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self._cfg.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self._cfg.height)
        cap.set(cv2.CAP_PROP_FPS, self._cfg.fps)
        try:
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # keep only the freshest frame
        except Exception:  # noqa: BLE001 — not all backends support it
            pass
        actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        actual_fps = cap.get(cv2.CAP_PROP_FPS)
        actual_fourcc = _fourcc_to_str(cap.get(cv2.CAP_PROP_FOURCC))
        logger.info("Camera %d opened: %dx%d @ %.0f fps (fourcc=%s, requested %s)",
                    device, actual_w, actual_h, actual_fps,
                    actual_fourcc or "?", fourcc or "default")
        # If the camera negotiated a much lower fps (or a different resolution)
        # than asked it ignored the mode set. For MJPG that's usually a heavy
        # native mode (the classic IMX219 "stuck at full 8MP ≈ 5 fps"); for
        # uncompressed YUY2/YUYV at high res it's usually USB bandwidth.
        if actual_fps and actual_fps + 1 < self._cfg.fps:
            logger.warning(
                "Camera %d gave %.0f fps (< requested %d) in %s. Run "
                "`v4l2-ctl -d /dev/video%d --list-formats-ext` and set "
                "camera.width/height/fps to a mode the camera lists at this "
                "format. Uncompressed YUY2/YUYV at 1080p needs USB 3.0 — drop "
                "to 720p/VGA, or use MJPG, if you're bandwidth-limited.",
                device, actual_fps, self._cfg.fps, actual_fourcc or "?", device)
        if (actual_w, actual_h) != (self._cfg.width, self._cfg.height):
            logger.warning("Camera %d resolution is %dx%d, requested %dx%d",
                           device, actual_w, actual_h, self._cfg.width, self._cfg.height)
        return cap

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            try:
                await self._task
            except Exception:
                pass
        if self._cap_l is not None:
            self._cap_l.release()
        if self._cap_r is not None:
            self._cap_r.release()

    def subscribe(self) -> asyncio.Queue[StereoFrame]:
        """Get a queue that receives every new frame.

        Use a bounded queue so a slow consumer can't pile up backpressure;
        we drop the oldest frame if the queue is full.
        """
        q: asyncio.Queue[StereoFrame] = asyncio.Queue(maxsize=2)
        self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue[StereoFrame]) -> None:
        try:
            self._subscribers.remove(q)
        except ValueError:
            pass

    @property
    def latest(self) -> StereoFrame | None:
        return self._latest

    @property
    def has_right(self) -> bool:
        """True if a second (right) camera opened — gates the stereo / right view."""
        return self._cap_r is not None

    async def _read_or_drop(
        self, loop: asyncio.AbstractEventLoop, cap: "cv2.VideoCapture", device: int
    ) -> "tuple[cv2.Mat | None, cv2.VideoCapture | None]":
        """Read one frame. Returns (frame|None, cap|None).

        cap.read() is blocking (grab + decode), so it runs in a worker thread —
        that lets capture overlap the /video JPEG encode instead of serializing
        on the event loop (cv2 releases the GIL inside read()). A single failed
        read is a transient miss and the handle is kept; only after
        _READ_FAIL_LIMIT failures in a row do we treat it as a real disconnect,
        release the handle, and return cap=None so the loop reopens the device.
        """
        try:
            ok, frame = await loop.run_in_executor(None, cap.read)
        except Exception as e:  # noqa: BLE001 — any read error counts as a miss
            logger.debug("Camera %d read raised: %s", device, e)
            ok, frame = False, None
        if ok and frame is not None:
            self._fail[device] = 0
            return frame, cap
        self._fail[device] = self._fail.get(device, 0) + 1
        if self._fail[device] >= _READ_FAIL_LIMIT:
            logger.warning(
                "Camera %d stopped delivering frames (%d failed reads) — "
                "releasing and retrying every %.1fs until it returns.",
                device, self._fail[device], self._reconnect_interval)
            try:
                cap.release()
            except Exception:  # noqa: BLE001
                pass
            return None, None
        return None, cap  # transient miss — keep the handle

    async def _reconnect(
        self, loop: asyncio.AbstractEventLoop, device: int
    ) -> "cv2.VideoCapture | None":
        """Try to reopen a dropped camera, throttled to reconnect_interval_s.

        Returns the new VideoCapture on success, else None (a quiet retry —
        only the success is logged at INFO). Reopens on the same configured
        device index; if a USB camera re-enumerates to a different /dev/video*
        node it won't be found here (rare for a single fixed-index camera).
        """
        now = time.monotonic()
        if now - self._last_reopen.get(device, 0.0) < self._reconnect_interval:
            return None
        self._last_reopen[device] = now
        try:
            cap = await loop.run_in_executor(None, self._open, device)
        except Exception as e:  # noqa: BLE001 — still absent; retry next interval
            logger.debug("Camera %d reconnect attempt failed: %s", device, e)
            return None
        logger.info("Camera %d reconnected.", device)
        self._fail[device] = 0
        return cap

    async def _loop(self) -> None:
        loop = asyncio.get_running_loop()
        interval = 1.0 / max(1, self._cfg.fps)
        while not self._stop.is_set():
            t0 = time.monotonic()
            # Auto-reconnect any dropped camera (throttled inside _reconnect).
            # Left is required; right only if it was present at least once.
            if self._cap_l is None:
                self._cap_l = await self._reconnect(loop, self._cfg.left_device)
            if self._cap_r is None and self._right_ever_open:
                self._cap_r = await self._reconnect(loop, self._cfg.right_device)

            left = right = None
            if self._cap_l is not None:
                left, self._cap_l = await self._read_or_drop(
                    loop, self._cap_l, self._cfg.left_device)
            if self._cap_r is not None:
                right, self._cap_r = await self._read_or_drop(
                    loop, self._cap_r, self._cfg.right_device)
            if left is None:
                # No left frame: a transient miss (handle kept) or the camera
                # dropped and is awaiting reconnect. While down, poll quickly so
                # a returning camera is picked up fast — _reconnect() still
                # throttles the actual reopen attempts to reconnect_interval_s.
                await asyncio.sleep(
                    _DOWN_POLL_S if self._cap_l is None else interval)
                continue
            sf = StereoFrame(left=left, right=right, ts=time.time())
            self._latest = sf
            for q in list(self._subscribers):
                if q.full():
                    try:
                        q.get_nowait()
                    except asyncio.QueueEmpty:
                        pass
                try:
                    q.put_nowait(sf)
                except asyncio.QueueFull:
                    pass
            elapsed = time.monotonic() - t0
            sleep_for = interval - elapsed
            if sleep_for > 0:
                await asyncio.sleep(sleep_for)
            else:
                # Yield to the loop even if we're already behind
                await asyncio.sleep(0)
