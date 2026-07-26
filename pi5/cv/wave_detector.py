"""Vision-based incoming-wave / swell detection for capsize avoidance.

A small catamaran broaches and capsizes when a large wave hits it side-on. This
module watches the water surface from the forward cameras and raises an early
warning — with a bearing and a severity — so the boat can bow into a big set
before it arrives (the classic seamanship response: take steep waves on the bow,
never the beam).

It is deliberately cheap (a few ms/frame on a Pi 5 CPU) so it can ride the
existing Tier-1 vision loop alongside YOLO + water segmentation:

  1. **Horizon** — the water/sky boundary row per column, from the strongest
     horizontal-gradient band (or a supplied water mask). Its vertical position
     rising toward the camera + tilting is the primary swell cue.
  2. **Looming flow** — sparse Lucas-Kanade optical flow in a band just below the
     horizon; net upward (image-y-decreasing) motion = a face growing toward us.
  3. **Fusion** — rise-rate + looming + a rough time-to-impact fold into a 0-1
     severity, gated by a persistence state machine so wakes/chop don't trip it.

Bearing comes from the horizon tilt and the crest's horizontal offset mapped
through the camera FOV. Design + parameters follow the horizon-tracking /
optical-flow-looming approach used for USV obstacle & sea-state sensing.

No pitch/roll input yet (the Boat Pico reports heading only), so a hard pitch of
the boat itself can nudge the horizon — the persistence window and smoothing
absorb short transients; wire IMU pitch into ``analyze(pitch_deg=...)`` later to
de-tilt fully.
"""
from __future__ import annotations

import math
import time
from collections import deque
from dataclasses import dataclass, field


@dataclass
class WaveConfig:
    enabled: bool = True
    proc_width: int = 320          # downscale width for all analysis (cheap)
    fov_deg: float = 75.0          # camera horizontal FOV (bbox->bearing)
    max_fps: float = 10.0          # analysis rate cap (Hz)
    band_px: int = 60              # optical-flow ROI height below the horizon (proc px)
    max_features: int = 80
    hist: int = 30                 # frames of horizon history (~3 s at 10 Hz)
    # Fusion weights (rise-rate, looming, imminence) and normalisers.
    w_rise: float = 0.45
    w_loom: float = 0.30
    w_ttc: float = 0.25
    rise_norm_px: float = 6.0      # proc-px/frame horizon rise = "fast"
    loom_norm: float = 3.0         # mean upward flow px/frame = "fast"
    # State machine.
    trigger_severity: float = 0.55  # severity above which a wave is "incoming"
    persist_frames: int = 6         # consecutive approaching frames before latching
    clear_frames: int = 8           # frames below trigger before clearing
    ema_alpha: float = 0.35         # smoothing on bearing/severity


@dataclass
class WaveResult:
    incoming: bool = False
    bearing_deg: float = 0.0       # relative to bow; + = starboard, - = port
    severity: float = 0.0          # 0-1
    ttc_s: float = float("inf")    # rough time-to-impact
    horizon_y: float = 0.0         # horizon row (fraction of frame height, 0=top)
    rise_rate: float = 0.0         # proc-px/frame (>0 = rising toward camera)
    detail: dict = field(default_factory=dict)


class WaveDetector:
    def __init__(self, cfg: WaveConfig | None = None) -> None:
        self.cfg = cfg or WaveConfig()
        self.enabled = self.cfg.enabled
        self._hy: deque[float] = deque(maxlen=self.cfg.hist)
        self._prev_gray = None
        self._prev_pts = None
        self._roi_y0 = 0
        self._approach = 0
        self._clear = 0
        self._latched = False
        self._sev = 0.0
        self._brg = 0.0
        self._last = 0.0
        self._result = WaveResult()

    # -- horizon ------------------------------------------------------------ #
    @staticmethod
    def _horizon_from_gradient(gray):
        """Row index (per column) of the strongest horizontal edge = horizon.

        Returns (per-column horizon y array, tilt slope px/col, median y)."""
        import cv2
        import numpy as np
        # Vertical Sobel emphasises the horizontal sky/water boundary.
        sob = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
        mag = np.abs(sob)
        # For each column, the row of maximum gradient is the horizon there.
        hy = np.argmax(mag, axis=0).astype(np.float32)
        # Reject columns with no real edge (flat) by blending toward the median.
        col_peak = mag.max(axis=0)
        thr = max(1.0, float(np.median(col_peak)) * 0.5)
        med = float(np.median(hy[col_peak >= thr])) if np.any(col_peak >= thr) else float(np.median(hy))
        hy[col_peak < thr] = med
        # Robust tilt via a least-squares line over confident columns.
        xs = np.arange(len(hy), dtype=np.float32)
        m = col_peak >= thr
        if int(m.sum()) >= 8:
            slope = float(np.polyfit(xs[m], hy[m], 1)[0])
        else:
            slope = 0.0
        return hy, slope, med

    def analyze(self, frame_bgr, water_mask=None, pitch_deg: float = 0.0) -> WaveResult:
        """Analyse one frame; returns the latest :class:`WaveResult`. Rate-capped
        internally, so it's safe to call every frame."""
        if not self.enabled or frame_bgr is None:
            return self._result
        now = time.monotonic()
        if self._last and (now - self._last) < 1.0 / max(1.0, self.cfg.max_fps):
            return self._result
        self._last = now
        import cv2
        import numpy as np

        h0, w0 = frame_bgr.shape[:2]
        scale = self.cfg.proc_width / float(w0)
        pw = self.cfg.proc_width
        ph = max(2, int(round(h0 * scale)))
        small = cv2.resize(frame_bgr, (pw, ph), interpolation=cv2.INTER_AREA)
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)

        # --- horizon ---
        if water_mask is not None:
            mask = cv2.resize(water_mask, (pw, ph), interpolation=cv2.INTER_NEAREST)
            hy = np.array([
                (np.argmax(mask[:, x] > 0) if mask[:, x].any() else ph) for x in range(pw)
            ], dtype=np.float32)
            slope = float(np.polyfit(np.arange(pw), hy, 1)[0]) if pw >= 8 else 0.0
            med = float(np.median(hy))
        else:
            hy, slope, med = self._horizon_from_gradient(gray)
        self._hy.append(med)

        # rise rate: horizon moving UP the image (y decreasing) = wave face
        # rising toward us. Positive rise_rate = approaching.
        rise = 0.0
        if len(self._hy) >= 5:
            rise = (self._hy[-5] - self._hy[-1]) / 4.0

        # --- optical flow looming in a band below the horizon ---
        y0 = int(np.clip(med, 0, ph - 1))
        y1 = int(np.clip(med + self.cfg.band_px, 0, ph))
        loom = 0.0
        crest_dx = 0.0
        roi = gray[y0:y1, :]
        if roi.shape[0] >= 8 and self._prev_gray is not None and self._prev_gray.shape == gray.shape:
            prev_roi = self._prev_gray[y0:y1, :]
            pts = cv2.goodFeaturesToTrack(prev_roi, self.cfg.max_features, 0.01, 6)
            if pts is not None and len(pts) >= 6:
                nxt, st, _ = cv2.calcOpticalFlowPyrLK(prev_roi, roi, pts, None,
                                                      winSize=(15, 15), maxLevel=2)
                st = st.flatten() == 1
                if int(st.sum()) >= 4:
                    d = (nxt - pts).reshape(-1, 2)[st]
                    # upward motion (dy < 0) = looming toward us
                    loom = float(np.mean(np.maximum(0.0, -d[:, 1])))
                    # crest horizontal position: features that moved most (upward)
                    up = pts.reshape(-1, 2)[st][d[:, 1] < -0.5]
                    if len(up):
                        crest_dx = float(np.mean(up[:, 0])) - pw / 2.0
        self._prev_gray = gray

        # --- bearing (relative to bow) ---
        # tilt of the horizon + the crest's horizontal offset, mapped via FOV.
        tilt_deg = math.degrees(math.atan2(slope * pw, pw))  # rise over full width
        crest_brg = (crest_dx / (pw / 2.0)) * (self.cfg.fov_deg / 2.0)
        bearing = crest_brg if abs(crest_brg) > 1.0 else tilt_deg
        bearing = max(-90.0, min(90.0, bearing))

        # --- time to impact (rough) ---
        ttc = float("inf")
        if rise > 0.5:
            # horizon distance ~ proportional to how high it sits; use rows-to-camera
            rows_below = max(1.0, ph - med)
            ttc = float(np.clip(rows_below / (rise * self.cfg.max_fps), 0.5, 20.0))

        # --- severity fusion ---
        c = self.cfg
        sev = (c.w_rise * min(1.0, max(0.0, rise) / c.rise_norm_px)
               + c.w_loom * min(1.0, loom / c.loom_norm)
               + c.w_ttc * (0.0 if ttc == float("inf") else max(0.0, 1.0 - ttc / 10.0)))
        sev = max(0.0, min(1.0, sev))

        # --- smoothing + state machine ---
        a = c.ema_alpha
        self._sev = a * sev + (1 - a) * self._sev
        self._brg = a * bearing + (1 - a) * self._brg
        approaching = self._sev >= c.trigger_severity and rise > 0.3
        if approaching:
            self._approach += 1
            self._clear = 0
        else:
            self._clear += 1
            self._approach = max(0, self._approach - 1)
        if self._approach >= c.persist_frames:
            self._latched = True
        if self._clear >= c.clear_frames:
            self._latched = False

        self._result = WaveResult(
            incoming=self._latched,
            bearing_deg=round(self._brg, 1),
            severity=round(self._sev, 2),
            ttc_s=round(ttc, 1) if ttc != float("inf") else float("inf"),
            horizon_y=round(med / ph, 3),
            rise_rate=round(rise, 2),
            detail={"loom": round(loom, 2), "tilt_deg": round(tilt_deg, 1)},
        )
        return self._result

    @property
    def result(self) -> WaveResult:
        return self._result

    def to_dict(self) -> dict:
        r = self._result
        return {
            "enabled": self.enabled,
            "incoming": r.incoming,
            "bearing_deg": r.bearing_deg,
            "severity": r.severity,
            "ttc_s": None if r.ttc_s == float("inf") else r.ttc_s,
            "horizon_y": r.horizon_y,
        }

    # -- HUD ---------------------------------------------------------------- #
    def draw(self, frame) -> None:
        """Overlay the horizon line + a wave-alert chevron when incoming."""
        r = self._result
        if not self.enabled:
            return
        import cv2
        h, w = frame.shape[:2]
        y = int(r.horizon_y * h)
        col = (60, 180, 255) if not r.incoming else (40, 60, 255)  # BGR amber->red
        cv2.line(frame, (0, y), (w, y), col, 1, cv2.LINE_AA)
        if r.incoming:
            cx = int(w / 2 + (r.bearing_deg / (self.cfg.fov_deg / 2)) * (w / 2))
            cx = max(20, min(w - 20, cx))
            for k in range(3):
                yy = y + 12 + k * 10
                cv2.line(frame, (cx - 12, yy + 8), (cx, yy), (40, 60, 255), 2, cv2.LINE_AA)
                cv2.line(frame, (cx + 12, yy + 8), (cx, yy), (40, 60, 255), 2, cv2.LINE_AA)
            txt = "WAVE %d%% %s" % (int(r.severity * 100),
                                    ("%.0fs" % r.ttc_s) if r.ttc_s != float("inf") else "")
            cv2.putText(frame, txt, (cx - 40, y - 6), cv2.FONT_HERSHEY_SIMPLEX,
                        0.5, (40, 60, 255), 2, cv2.LINE_AA)
