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


@dataclass
class CameraConfig:
    left_device: int = 0
    right_device: int = 1
    width: int = 640
    height: int = 480
    fps: int = 30
    use_mjpg: bool = True


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

    def start(self) -> None:
        if self._task is not None:
            return
        self._cap_l = self._open(self._cfg.left_device)
        # Right is optional — if it fails, stereo features stay off but the
        # left-camera dashboard stream still works.
        try:
            self._cap_r = self._open(self._cfg.right_device)
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
        # Request MJPG before resolution/fps — far faster over USB than raw YUYV
        # and usually required to reach 30 fps. OpenCV falls back automatically
        # if the camera refuses it.
        if self._cfg.use_mjpg:
            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
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
        logger.info("Camera %d opened: %dx%d @ %.0f fps (mjpg=%s)", device,
                    actual_w, actual_h, actual_fps, self._cfg.use_mjpg)
        # If the camera negotiated a much lower fps (or a different resolution)
        # than asked, it most likely ignored the format set and is running a
        # heavy native mode — the classic IMX219 "stuck at full 8MP ≈ 5 fps".
        if actual_fps and actual_fps + 1 < self._cfg.fps:
            logger.warning(
                "Camera %d gave %.0f fps (< requested %d). If this is an "
                "IMX219/USB camera it's likely stuck in a high-res mode — run "
                "`v4l2-ctl -d /dev/video%d --list-formats-ext` and set "
                "camera.width/height/fps to a listed MJPG mode.",
                device, actual_fps, self._cfg.fps, device)
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

    async def _loop(self) -> None:
        loop = asyncio.get_running_loop()
        interval = 1.0 / max(1, self._cfg.fps)
        while not self._stop.is_set():
            t0 = time.monotonic()
            left = right = None
            # cap.read() blocks (grab + MJPEG→BGR decode). Run it in a worker
            # thread so a 1080p decode doesn't freeze the whole event loop —
            # that blocking is what stops capture and the /video JPEG encode from
            # overlapping, sagging the published stream below the capture rate at
            # high resolution. OpenCV releases the GIL inside read(), so the
            # offload genuinely parallelizes the two.
            if self._cap_l is not None:
                ok, frame = await loop.run_in_executor(None, self._cap_l.read)
                if ok:
                    left = frame
            if self._cap_r is not None:
                ok, frame = await loop.run_in_executor(None, self._cap_r.read)
                if ok:
                    right = frame
            if left is None:
                # Nothing to publish; pause briefly and retry
                await asyncio.sleep(interval)
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
