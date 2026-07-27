"""Camera clip recorder — manual capture + Tesla-Sentry-style event recording.

The recorder keeps a rolling **pre-roll** buffer of recent frames so an
event-triggered clip includes the seconds *before* the trigger (like Sentry
mode saving the run-up to an incident). Clips are written to disk as
browser-playable video (VP8/WebM, falling back to MPEG-4) with a JSON metadata
sidecar, and old clips are pruned to a cap.

Design notes:
- All OpenCV work (JPEG encode for the pre-roll ring, ``VideoWriter`` for the
  clip) is synchronous and lives here; the server calls ``add_frame`` /
  ``tick`` / ``stop`` from a thread (``asyncio.to_thread``) so the event loop
  never blocks. A single lock guards the shared state.
- Frames are down-scaled to ``width`` on the way in, so both memory (pre-roll
  is JPEG-encoded) and CPU (a Pi 5 encoding continuously) stay bounded.
- The module imports ``cv2`` lazily so it can be imported (and most of it
  unit-tested) even where OpenCV isn't installed.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

# Preferred (fourcc, extension, mime) in order. VP8/WebM plays natively in every
# modern browser <video>; MPEG-4 is the fallback when the VP8 encoder is absent.
_CODECS = [
    ("VP80", ".webm", "video/webm"),
    ("mp4v", ".mp4", "video/mp4"),
]

# Trigger reasons the sentry monitor may raise, mapped to a coarse severity the
# UI colours by. Anything unknown is treated as "event".
TRIGGER_SEVERITY = {
    "manual": "manual",
    "critical-threat": "critical",
    "hull-leak": "critical",
    "pod-leak": "critical",
    "estop": "warning",
    "event": "warning",
}


@dataclass
class _Clip:
    """Bookkeeping for the clip currently being written."""
    name: str
    path: Path
    reason: str
    trigger: str            # "manual" | "sentry"
    started_wall: float
    started_mono: float
    size: tuple[int, int]   # (w, h)
    fps: float
    mime: str
    writer: object = None
    frames: int = 0
    end_mono: float | None = None   # sentry auto-stop deadline; None = manual


@dataclass
class RecorderConfig:
    fps: float = 10.0
    preroll_s: float = 6.0
    clip_s: float = 12.0          # minimum sentry clip length after a trigger
    max_clip_s: float = 300.0     # max length of ONE segment file; a still-active
    #                               threat rolls over into a new segment (a clip is
    #                               never cut off while the threat is still seen)
    retrigger_extend_s: float = 8.0  # keep recording this long after the threat clears
    cooldown_s: float = 6.0       # ignore identical re-triggers within this window
    width: int = 640              # frames are scaled to this width (keep aspect)
    max_clips: int = 60           # oldest clips pruned beyond this count
    max_age_days: float = 14.0    # clips older than this are deleted (0 = keep forever)
    jpeg_quality: int = 70
    sentry_default: bool = False


class Recorder:
    """Rolling pre-roll buffer + manual/sentry clip writer."""

    def __init__(self, out_dir: str | Path, config: RecorderConfig | None = None) -> None:
        self.cfg = config or RecorderConfig()
        self.dir = Path(out_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._preroll: deque[tuple[float, bytes]] = deque(
            maxlen=max(1, int(self.cfg.preroll_s * self.cfg.fps)))
        self._preroll_size: tuple[int, int] | None = None   # (w, h) of buffered jpegs
        self._clip: _Clip | None = None
        self.sentry_enabled = bool(self.cfg.sentry_default)
        self._cooldowns: dict[str, float] = {}   # reason -> mono time it may re-fire
        self._last_frame_mono = 0.0
        self._last_event_mono: float | None = None   # last sentry sighting
        self._seq = 0                            # guarantees unique clip names
        try:
            self._prune_by_age()                 # drop stale clips left from prior runs
        except Exception:  # noqa: BLE001 — startup cleanup must never block construction
            logger.debug("startup age-prune skipped", exc_info=True)

    # -- ingest ------------------------------------------------------------- #
    def add_frame(self, bgr: "np.ndarray", now: float | None = None) -> None:
        """Feed one BGR frame. Buffers it for pre-roll and, if a clip is
        recording, writes it. Cheap no-op if neither sentry nor a clip wants
        frames (so the feed can idle when the feature is off)."""
        import cv2
        mono = time.monotonic() if now is None else float(now)
        with self._lock:
            want = self.sentry_enabled or self._clip is not None
            if not want:
                return
            small = self._scale(bgr, cv2)
            h, w = small.shape[:2]
            self._last_frame_mono = mono
            if self._clip is not None:
                self._write(self._match_size(small, self._clip.size, cv2))
            # Keep filling the pre-roll ring (skip while a clip runs — those
            # frames are already in the file, and we want fresh run-up next time).
            if self._clip is None and self.sentry_enabled:
                ok, buf = cv2.imencode(
                    ".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, self.cfg.jpeg_quality])
                if ok:
                    self._preroll_size = (w, h)
                    self._preroll.append((mono, buf.tobytes()))

    # -- triggers ----------------------------------------------------------- #
    def start_manual(self, now: float | None = None) -> dict | None:
        """Begin a manual clip (runs until stop())."""
        with self._lock:
            if self._clip is not None:
                return self._clip_public(self._clip)
            return self._open_clip("manual", "manual", end_in=None, now=now)

    def note_event(self, reason: str, now: float | None = None) -> bool:
        """Sentry hook: a critical moment is happening *right now*. Starts a clip
        (seeded with the pre-roll) or keeps the running one alive.

        The clip records until the threat *clears* — i.e. until
        ``retrigger_extend_s`` passes with no further event — not a fixed length,
        so a threat that lingers keeps recording. There's no hard length cap
        here; the per-segment cap is handled by rollover in :meth:`tick`. The
        per-reason cooldown only gates *starting* a new clip, not extending one.
        Returns True if it started/extended a clip."""
        mono = time.monotonic() if now is None else float(now)
        with self._lock:
            if not self.sentry_enabled:
                return False
            self._last_event_mono = mono
            until = self._cooldowns.get(reason, 0.0)
            self._cooldowns[reason] = mono + self.cfg.cooldown_s
            if self._clip is not None:
                if self._clip.end_mono is not None:
                    # Push the trailing window past this sighting so the clip
                    # runs on while the threat is still visible.
                    self._clip.end_mono = max(self._clip.end_mono,
                                              mono + self.cfg.retrigger_extend_s)
                    if reason not in self._clip.reason.split("+"):
                        self._clip.reason += "+" + reason
                return True
            if mono < until:
                return False   # still cooling down and no clip to extend
            self._open_clip(reason, "sentry",
                            end_in=self.cfg.clip_s, now=mono, seed_preroll=True)
            return True

    def tick(self, now: float | None = None) -> None:
        """Stop a sentry clip once the threat has cleared (``retrigger_extend_s``
        elapsed with no new event). If the threat is *still* active when a
        segment reaches ``max_clip_s``, roll over into a fresh segment instead of
        stopping — so a persistent threat is never cut off mid-event."""
        mono = time.monotonic() if now is None else float(now)
        with self._lock:
            c = self._clip
            if c is None or c.end_mono is None:
                return
            threat_active = (self._last_event_mono is not None
                             and (mono - self._last_event_mono) < self.cfg.retrigger_extend_s)
            if (mono - c.started_mono) >= self.cfg.max_clip_s and threat_active:
                reason, size = c.reason, c.size    # continue seamlessly in a new file
                self.stop(now=mono)
                self._open_clip(reason, "sentry", end_in=self.cfg.clip_s,
                                now=mono, size=size)
                return
            if mono >= c.end_mono:
                self.stop(now=mono)

    def stop(self, now: float | None = None) -> dict | None:
        """Finalise the current clip: close the writer, write metadata, prune."""
        with self._lock:
            c = self._clip
            if c is None:
                return None
            self._clip = None
            try:
                if c.writer is not None:
                    c.writer.release()
            except Exception as e:  # noqa: BLE001
                logger.debug("writer release failed: %s", e)
            duration = max(0.0, (time.monotonic() if now is None else now) - c.started_mono)
            meta = {
                "name": c.name,
                "file": c.path.name,
                "reason": c.reason,
                "trigger": c.trigger,
                "severity": self._severity(c.reason),
                "started": c.started_wall,
                "duration_s": round(c.frames / c.fps, 1) if c.fps else round(duration, 1),
                "frames": c.frames,
                "fps": c.fps,
                "width": c.size[0],
                "height": c.size[1],
                "mime": c.mime,
                "favorite": False,   # user pin — favorites are never auto-deleted
                "size_bytes": c.path.stat().st_size if c.path.exists() else 0,
            }
            c.path.with_suffix(".json").write_text(json.dumps(meta), encoding="utf-8")
            logger.info("Recording saved: %s (%s, %.1fs, %d frames)",
                        c.path.name, c.reason, meta["duration_s"], c.frames)
            self._prune()
            return meta

    # -- sentry mode -------------------------------------------------------- #
    def set_sentry(self, enabled: bool) -> None:
        with self._lock:
            self.sentry_enabled = bool(enabled)
            if not enabled:
                self._preroll.clear()

    # -- queries ------------------------------------------------------------ #
    @property
    def recording(self) -> bool:
        return self._clip is not None

    def status(self) -> dict:
        with self._lock:
            c = self._clip
            return {
                "sentry_enabled": self.sentry_enabled,
                "recording": c is not None,
                "active_reason": c.reason if c else None,
                "active_trigger": c.trigger if c else None,
                "active_frames": c.frames if c else 0,
                "preroll_frames": len(self._preroll),
                "clip_count": self._count_clips(),
            }

    def list_clips(self) -> list[dict]:
        """All saved clips (metadata), newest first."""
        out = []
        for j in self.dir.glob("*.json"):
            try:
                m = json.loads(j.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            vid = self.dir / m.get("file", "")
            if not vid.exists():
                continue
            m["size_bytes"] = vid.stat().st_size
            m.setdefault("favorite", False)
            out.append(m)
        out.sort(key=lambda m: m.get("started", 0), reverse=True)
        return out

    def clip_path(self, file_name: str) -> Path | None:
        """Resolve a clip's video path, rejecting anything outside the dir."""
        if not file_name or "/" in file_name or "\\" in file_name or ".." in file_name:
            return None
        p = (self.dir / file_name).resolve()
        try:
            p.relative_to(self.dir.resolve())
        except ValueError:
            return None
        return p if p.exists() and p.is_file() else None

    def delete_clip(self, file_name: str) -> bool:
        p = self.clip_path(file_name)
        if p is None:
            return False
        with self._lock:
            p.unlink(missing_ok=True)
            p.with_suffix(".json").unlink(missing_ok=True)
        return True

    def set_favorite(self, file_name: str, favorite: bool) -> dict | None:
        """Pin/unpin a clip. Favorites are exempt from age + count pruning (but
        can still be deleted explicitly). Returns the updated metadata or None."""
        with self._lock:
            vid = self.clip_path(file_name)
            if vid is None:
                return None
            jp = vid.with_suffix(".json")
            try:
                m = json.loads(jp.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                return None
            m["favorite"] = bool(favorite)
            jp.write_text(json.dumps(m), encoding="utf-8")
            return m

    # -- internals ---------------------------------------------------------- #
    def _scale(self, bgr: "np.ndarray", cv2) -> "np.ndarray":
        h, w = bgr.shape[:2]
        if w <= self.cfg.width:
            return bgr
        nh = max(2, int(round(h * self.cfg.width / w)))
        nh -= nh % 2  # even dims keep encoders happy
        return cv2.resize(bgr, (self.cfg.width, nh), interpolation=cv2.INTER_AREA)

    @staticmethod
    def _match_size(bgr: "np.ndarray", size: tuple[int, int], cv2) -> "np.ndarray":
        if (bgr.shape[1], bgr.shape[0]) == size:
            return bgr
        return cv2.resize(bgr, size, interpolation=cv2.INTER_AREA)

    def _open_clip(self, reason: str, trigger: str, *, end_in: float | None,
                   now: float | None = None, seed_preroll: bool = False,
                   size: tuple[int, int] | None = None) -> dict | None:
        import cv2
        mono = time.monotonic() if now is None else float(now)
        # Frame size: an explicit size (segment rollover) wins; else the pre-roll
        # size (if seeding) or the config default.
        if size is None:
            size = self._preroll_size if (seed_preroll and self._preroll_size) else \
                (self.cfg.width, int(self.cfg.width * 9 / 16) & ~1)
        self._seq += 1
        base = f"clip-{time.strftime('%Y%m%d-%H%M%S', time.localtime())}-{self._seq:04d}-{trigger}"
        writer = mime = ext = None
        for fourcc, ext_try, mime_try in _CODECS:
            path = self.dir / (base + ext_try)
            w = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*fourcc),
                                self.cfg.fps, size)
            if w.isOpened():
                writer, ext, mime = w, ext_try, mime_try
                break
            w.release()
            path.unlink(missing_ok=True)
        if writer is None:
            logger.error("No usable video codec — recording unavailable")
            return None
        clip = _Clip(
            name=base, path=self.dir / (base + ext),
            reason=reason, trigger=trigger, started_wall=time.time(), started_mono=mono,
            size=size, fps=self.cfg.fps, mime=mime, writer=writer,
            end_mono=(mono + end_in) if end_in is not None else None)
        self._clip = clip
        if seed_preroll:
            for _ts, buf in list(self._preroll):
                arr = cv2.imdecode(np.frombuffer(buf, np.uint8), cv2.IMREAD_COLOR)
                if arr is not None:
                    self._write(self._match_size(arr, size, cv2))
            self._preroll.clear()
        logger.info("Recording started: %s (%s)", clip.path.name, reason)
        return self._clip_public(clip)

    def _write(self, bgr: "np.ndarray") -> None:
        c = self._clip
        if c is None or c.writer is None:
            return
        try:
            c.writer.write(bgr)
            c.frames += 1
        except Exception as e:  # noqa: BLE001
            logger.debug("frame write failed: %s", e)

    def _clip_public(self, c: _Clip) -> dict:
        return {"name": c.name, "file": c.path.name, "reason": c.reason,
                "trigger": c.trigger, "severity": self._severity(c.reason)}

    @staticmethod
    def _severity(reason: str) -> str:
        for part in reason.split("+"):
            base = part.split(":")[0]
            if TRIGGER_SEVERITY.get(base) == "critical":
                return "critical"
        first = reason.split("+")[0].split(":")[0]
        return TRIGGER_SEVERITY.get(first, "warning")

    def _count_clips(self) -> int:
        return sum(1 for _ in self.dir.glob("clip-*.json"))

    def _delete_meta(self, json_path: Path) -> None:
        """Delete a clip's video + its metadata sidecar."""
        try:
            m = json.loads(json_path.read_text(encoding="utf-8"))
            (self.dir / m.get("file", "")).unlink(missing_ok=True)
        except (OSError, ValueError):
            pass
        json_path.unlink(missing_ok=True)

    def _clip_started(self, json_path: Path) -> float:
        """A clip's wall-clock start time — from metadata, else the file mtime."""
        try:
            started = float(json.loads(json_path.read_text(encoding="utf-8")).get("started", 0.0))
            if started > 0.0:
                return started
        except (OSError, ValueError):
            pass
        try:
            return json_path.stat().st_mtime
        except OSError:
            return 0.0

    def _is_favorite(self, json_path: Path) -> bool:
        try:
            return bool(json.loads(json_path.read_text(encoding="utf-8")).get("favorite", False))
        except (OSError, ValueError):
            return False

    def _prune_by_age(self) -> int:
        """Delete non-favorite clips older than ``max_age_days`` (0 disables)."""
        if self.cfg.max_age_days <= 0:
            return 0
        cutoff = time.time() - self.cfg.max_age_days * 86400.0
        removed = 0
        for j in list(self.dir.glob("clip-*.json")):
            if self._is_favorite(j):
                continue                           # favorites are never auto-deleted
            if self._clip_started(j) < cutoff:
                self._delete_meta(j)
                removed += 1
        if removed:
            logger.info("Pruned %d recording(s) older than %.0f days",
                        removed, self.cfg.max_age_days)
        return removed

    def prune_old(self) -> int:
        """Age-retention sweep the server can call periodically, even when
        nothing is recording. Thread-safe."""
        with self._lock:
            return self._prune_by_age()

    def _prune(self) -> None:
        self._prune_by_age()                       # age first...
        # ...then the count cap, over non-favorites only (favorites always kept).
        others = [p for p in self.dir.glob("clip-*.json") if not self._is_favorite(p)]
        others.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        for old in others[self.cfg.max_clips:]:
            self._delete_meta(old)
