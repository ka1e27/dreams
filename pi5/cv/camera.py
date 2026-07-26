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

# Upper bound for a live left/right reassignment (set_devices) to finish. It has
# to cover opening BOTH cameras back-to-back, and a single 1080p open over
# Windows DirectShow can take 6-8s — two of them blow a 10s budget, which made
# the right camera (always opened second) report "not responding" even though it
# came up a second later. Give the whole swap generous headroom instead.
_APPLY_TIMEOUT_S = 45.0


def _capture_backend() -> int:
    """OpenCV capture backend for this OS — shared by _open and _probe_device.

    The producer and the device scanner MUST agree on the backend, or the scan
    lists devices the producer can't actually open. On the Pi that's V4L2; on
    Windows it's DirectShow. OpenCV's Windows default (MSMF) both enumerates
    phantom indices that then fail to open under DShow AND is far slower to
    probe, so pin DShow explicitly.
    """
    if sys.platform.startswith("linux"):
        return cv2.CAP_V4L2
    if sys.platform == "win32":
        return cv2.CAP_DSHOW
    return cv2.CAP_ANY


def _device_name(index: int) -> str:
    """Human-readable name for a capture device (best effort)."""
    if sys.platform.startswith("linux"):
        try:
            with open(f"/sys/class/video4linux/video{index}/name", encoding="utf-8") as f:
                return f.read().strip()
        except OSError:
            pass
    return f"Camera {index}"


def _probe_device(index: int) -> bool:
    """True if `index` opens AND delivers frames (filters UVC metadata nodes)."""
    try:
        cap = cv2.VideoCapture(index, _capture_backend())
        if not cap.isOpened():
            return False
        # Metadata-only /dev/video* nodes open fine but never grab a frame.
        ok = bool(cap.grab())
        cap.release()
        return ok
    except Exception:  # noqa: BLE001 — a broken device just isn't listed
        return False


def scan_devices(skip: "set[int] | frozenset[int]" = frozenset(),
                 max_probe: int = 8) -> "list[dict]":
    """Enumerate attached capture devices. BLOCKING — call via an executor.

    Indices in `skip` are devices the producer currently holds open; they are
    reported as in_use without probing (opening them a second time would fight
    the live capture). On Linux the /dev/video* nodes are scanned (metadata-only
    nodes are filtered out by a grab test); elsewhere indices 0..max_probe-1
    are probed, stopping after two consecutive misses past the last hit.
    """
    skip = set(skip)
    if sys.platform.startswith("linux"):
        import glob
        candidates = sorted(
            int(p[len("/dev/video"):]) for p in glob.glob("/dev/video[0-9]*"))
        stop_on_miss = False
    else:
        candidates = list(range(max_probe))
        stop_on_miss = True

    devices: list[dict] = []
    misses = 0
    for idx in candidates:
        if idx in skip:
            devices.append({"index": idx, "name": _device_name(idx), "in_use": True})
            misses = 0
            continue
        if _probe_device(idx):
            devices.append({"index": idx, "name": _device_name(idx), "in_use": False})
            misses = 0
        elif stop_on_miss:
            misses += 1
            if misses >= 2:
                break
    return devices


def _fourcc_to_str(val: float) -> str:
    """Decode an OpenCV CAP_PROP_FOURCC value into its 4-char code (e.g. 'YUYV')."""
    v = int(val)
    if v <= 0:
        return ""
    return "".join(chr((v >> (8 * i)) & 0xFF) for i in range(4)).strip("\x00 ")


@dataclass
class CameraConfig:
    left_device: int = 0
    # None = no right camera configured (single-camera rig; stereo stays off).
    right_device: "int | None" = 2
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
        # Runtime left/right reassignment (set_devices). The capture loop owns
        # the VideoCapture handles, so swaps are queued here and applied at the
        # top of a loop iteration — never from another task mid-read.
        self._pending_devices: "tuple[int, int | None] | None" = None
        self._devices_applied = asyncio.Event()

    def start(self) -> None:
        if self._task is not None:
            return
        self._cap_l = self._open(self._cfg.left_device)
        # Right is optional — if it fails, stereo features stay off but the
        # left-camera dashboard stream still works.
        if self._cfg.right_device is not None:
            try:
                self._cap_r = self._open(self._cfg.right_device)
                self._right_ever_open = True
            except Exception as e:
                logger.warning("Right camera unavailable: %s", e)
                self._cap_r = None
        else:
            self._cap_r = None
        self._task = asyncio.create_task(self._loop())

    def _open(self, device: int) -> cv2.VideoCapture:
        # On Linux (the Pi) force the V4L2 backend. With OpenCV's default backend
        # the FOURCC + resolution sets below often DON'T take, which leaves a raw
        # sensor like the IMX219 stuck in its native 8MP mode — and 3280x2464
        # over USB is only ~5 fps. Forcing V4L2 makes the format switch apply, so
        # the camera actually drops to the requested (binned, fast) mode.
        # On Windows, DirectShow is similarly unreliable — use CAP_DSHOW explicitly.
        cap = cv2.VideoCapture(device, _capture_backend())
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
        # Read defaults before setting (for debugging)
        default_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        default_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        default_fps = cap.get(cv2.CAP_PROP_FPS)

        if sys.platform.startswith("linux"):
            # V4L2 wants the pixel format pinned before resolution/fps.
            if fourcc:
                cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*fourcc[:4]))
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, self._cfg.width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self._cfg.height)
            cap.set(cv2.CAP_PROP_FPS, self._cfg.fps)
            # Force auto-exposure (V4L2 "aperture priority" = 3). UVC exposure
            # controls PERSIST on the device across processes, so a prior manual
            # setting (e.g. from a calibration/probe run) otherwise leaves the
            # feed near-black. Requesting auto on every open guarantees a
            # correctly-exposed frame and lets the camera track changing outdoor
            # light. Best-effort — a no-op if the camera lacks the control.
            try:
                cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 3)
            except Exception:  # noqa: BLE001
                pass
        else:
            # DirectShow negotiates the capture pin as one WxHxFourCC mode. If
            # FOURCC is set first and the camera has no discrete mode for that
            # exact combination, DSHOW silently keeps the native resolution
            # instead of erroring — so set width/height FIRST here, then let
            # the format follow (and re-apply size after, in case setting
            # FOURCC reset the pin back to native).
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, self._cfg.width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self._cfg.height)
            cap.set(cv2.CAP_PROP_FPS, self._cfg.fps)
            if fourcc:
                cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*fourcc[:4]))
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, self._cfg.width)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self._cfg.height)
        try:
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # keep only the freshest frame
        except Exception:  # noqa: BLE001 — not all backends support it
            pass

        # On Windows, DirectShow needs a few frames to stabilize resolution settings
        if not sys.platform.startswith("linux"):
            for _ in range(5):
                try:
                    cap.grab()
                except Exception:  # noqa: BLE001
                    pass

        actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        actual_fps = cap.get(cv2.CAP_PROP_FPS)
        actual_fourcc = _fourcc_to_str(cap.get(cv2.CAP_PROP_FOURCC))
        logger.info(
            "Camera %d opened: %dx%d @ %.0f fps (fourcc=%s, requested %s) "
            "[defaults were %dx%d @ %.0f fps]",
            device, actual_w, actual_h, actual_fps,
            actual_fourcc or "?", fourcc or "default",
            default_w, default_h, default_fps
        )
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

    @property
    def device_map(self) -> dict:
        """Current left/right device assignment and whether each is delivering."""
        return {
            "left": self._cfg.left_device,
            "left_open": self._cap_l is not None,
            "right": self._cfg.right_device,
            "right_open": self._cap_r is not None,
        }

    def active_devices(self) -> "set[int]":
        """Device indices this producer currently holds open (skip when scanning)."""
        out: set[int] = set()
        if self._cap_l is not None:
            out.add(self._cfg.left_device)
        if self._cap_r is not None and self._cfg.right_device is not None:
            out.add(self._cfg.right_device)
        return out

    async def set_devices(self, left: int, right: "int | None") -> dict:
        """Reassign which capture device is left / right, live.

        The swap is applied by the capture loop itself (it owns the handles):
        both current captures are released first, then the new indices are
        opened. right=None runs single-camera (stereo off). A device that
        fails to open is left to the normal auto-reconnect retry, so plugging
        it in later recovers without another call. Returns device_map.
        """
        if self._task is None or self._task.done():
            # Loop not running (never started / failed) — apply directly.
            self._apply_devices(left, right)
            return self.device_map
        self._devices_applied.clear()
        self._pending_devices = (left, right)
        try:
            await asyncio.wait_for(
                self._devices_applied.wait(), timeout=_APPLY_TIMEOUT_S)
        except asyncio.TimeoutError:
            logger.warning("set_devices(%s, %s): apply timed out", left, right)
        return self.device_map

    def _apply_devices(self, left: int, right: "int | None") -> None:
        """Release current captures and open the new indices. BLOCKING —
        called from the capture loop via an executor (or directly when the
        loop isn't running)."""
        for cap in (self._cap_l, self._cap_r):
            if cap is not None:
                try:
                    cap.release()
                except Exception:  # noqa: BLE001
                    pass
        self._cap_l = self._cap_r = None
        self._cfg.left_device = left
        self._cfg.right_device = right
        self._fail.clear()
        self._last_reopen.clear()
        # Treat a configured right as "seen" so auto-reconnect keeps trying it
        # even if the first open below fails.
        self._right_ever_open = right is not None
        try:
            self._cap_l = self._open(left)
        except Exception as e:  # noqa: BLE001 — reconnect loop keeps retrying
            logger.warning("Left camera %s failed to open: %s", left, e)
        if right is not None:
            try:
                self._cap_r = self._open(right)
            except Exception as e:  # noqa: BLE001
                logger.warning("Right camera %s failed to open: %s", right, e)

    @staticmethod
    def _grab_retrieve(
        cap_l: "cv2.VideoCapture | None", cap_r: "cv2.VideoCapture | None"
    ) -> "tuple[bool, cv2.Mat | None, bool, cv2.Mat | None]":
        """Blocking: latch BOTH cameras near-simultaneously, then decode both.

        For a stereo pair the two images must be captured as close in time as
        possible — any skew shows up as extra horizontal disparity on moving
        targets (the vessels we most want to range), corrupting depth. cap.read()
        is grab()+retrieve() fused, so reading left fully (grab + JPEG decode)
        *before* grabbing right leaves a skew of one decode time (~10-20 ms at
        1080p). Splitting the phases — grab() both back-to-back (each just latches
        the driver's freshest buffered frame, sub-millisecond) then retrieve()
        (decode) both — cuts the software skew to ~one grab call.

        (The sensors are still free-running/un-genlocked, so up to ~1 frame-period
        of inherent asynchrony remains; eliminating it needs hardware sync.)

        Returns (l_ok, left, r_ok, right); either cap may be None.
        """
        gl = gr = False
        try:
            if cap_l is not None:
                gl = cap_l.grab()
            if cap_r is not None:
                gr = cap_r.grab()
        except Exception:  # noqa: BLE001 — a grab error is just a miss
            pass
        l_ok, left, r_ok, right = False, None, False, None
        try:
            if gl:
                l_ok, left = cap_l.retrieve()
        except Exception:  # noqa: BLE001
            l_ok, left = False, None
        try:
            if gr:
                r_ok, right = cap_r.retrieve()
        except Exception:  # noqa: BLE001
            r_ok, right = False, None
        return bool(l_ok), left, bool(r_ok), right

    def _account(
        self, ok: bool, frame: "cv2.Mat | None",
        cap: "cv2.VideoCapture", device: int
    ) -> "tuple[cv2.Mat | None, cv2.VideoCapture | None]":
        """Fold one camera's grab/retrieve result into the fail/reconnect state.

        Returns (frame|None, cap|None). A single failed read is a transient miss
        and the handle is kept; only after _READ_FAIL_LIMIT failures in a row is
        it treated as a real disconnect — released, returning cap=None so the
        loop reopens the device.
        """
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
            # Apply a queued left/right reassignment (set_devices) before
            # touching the handles — this loop is their only owner.
            if self._pending_devices is not None:
                new_l, new_r = self._pending_devices
                self._pending_devices = None
                await loop.run_in_executor(None, self._apply_devices, new_l, new_r)
                self._devices_applied.set()
            # Auto-reconnect any dropped camera (throttled inside _reconnect).
            # Left is required; right only if it was present at least once.
            if self._cap_l is None:
                self._cap_l = await self._reconnect(loop, self._cfg.left_device)
            if (self._cap_r is None and self._right_ever_open
                    and self._cfg.right_device is not None):
                self._cap_r = await self._reconnect(loop, self._cfg.right_device)

            left = right = None
            if self._cap_l is not None or self._cap_r is not None:
                # Grab both handles back-to-back, then decode both, in one
                # executor call — minimises the stereo capture skew and still
                # overlaps the blocking decode with the /video JPEG encode.
                try:
                    l_ok, l_img, r_ok, r_img = await loop.run_in_executor(
                        None, self._grab_retrieve, self._cap_l, self._cap_r)
                except Exception as e:  # noqa: BLE001 — treat as a double miss
                    logger.debug("Camera grab/retrieve raised: %s", e)
                    l_ok = r_ok = False
                    l_img = r_img = None
                if self._cap_l is not None:
                    left, self._cap_l = self._account(
                        l_ok, l_img, self._cap_l, self._cfg.left_device)
                if self._cap_r is not None:
                    right, self._cap_r = self._account(
                        r_ok, r_img, self._cap_r, self._cfg.right_device)
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
