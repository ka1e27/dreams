"""Radar-bar tracker — coordinates the stepper with YOLO detections.

Owns the radar bar's motion on a **single daemon thread** so the blocking
stepper pulse train never touches the asyncio event loop. The FastAPI
endpoints only set the mode / a goto target (cheap, thread-safe); this loop is
the sole caller that actually drives the motor — which keeps the stepper's lock
uncontended and avoids two writers fighting over STEP.

Modes:
    SCAN   — continuous sweep between the configured limits, hunting for targets
    TRACK  — locked onto a detected priority target, keeping it centred in frame
    HOLD   — energised, stationary (auto-sleeps after the stepper's idle window)
    SLEEP  — motor in zero-current sleep

Tracking is best-effort: if no detection overlay is wired (or it exposes no
boxes), the tracker simply SCANs. Bearing is derived from a target's horizontal
position in the frame and the camera's horizontal FOV.

**The cameras ride ON the bar** (confirmed by the builder 2026-07-30 — this
supersedes ``docs/object_memory.md``'s "the cameras are fixed forward"). That
closes the loop: turning the bar turns the cameras, so a target off-centre in
frame moves *toward* centre as the bar comes round. Tracking is therefore a
**relative** controller — nudge the bar by the target's current offset, repeat,
stop inside a deadband — not an absolute aim at a fixed bow angle.

**Velocity feedforward.** A pure position controller always trails a moving
target: it only ever reacts to the error the target has *already* opened up, so
the faster you move the further behind the bar sits, until you leave the frame
and the lock drops. So the tracker also estimates the target's **angular rate**
and aims where it is going:

    step = (offset + rate × lead_seconds) × gain

The rate is measured on the **bow-relative bearing** (``bar angle + offset``),
not on the pixel offset. Those differ: with the cameras on the bar, the offset
shrinks purely because the bar turned, which is not the target moving. Bearing
is the frame-independent quantity, so it stays honest whether the bar is
tracking well, badly, or not at all. The slew speed then takes the *larger* of
"fast enough for this error" and "fast enough for this rate", so a target
crossing quickly gets a quick bar even while it is momentarily near centre.

Two consequences worth knowing:

* **The bar needs real travel.** A target can be anywhere around the boat, not
  just within one camera FOV of the bow, so the axis is a full **360°** with hard
  stops (``manual_*_degrees`` = ±180) — enough to follow a target right around,
  and never more than one turn of cable.
* **A wrong DIR polarity makes this diverge.** Moving the wrong way *increases*
  the offset, which commands a bigger move the same wrong way. That is what the
  2026-07-29 runaway actually was; ``stepper.invert_direction`` is what fixes it.
  ``_stall_ticks`` below is the backstop: if the offset stops shrinking while the
  bar is still moving, tracking halts and says so instead of winding to the stop.
"""
from __future__ import annotations

import logging
import threading
import time
from collections import deque

logger = logging.getLogger(__name__)

SCAN, TRACK, HOLD, SLEEP = "SCAN", "TRACK", "HOLD", "SLEEP"

# Consecutive corrections that fail to reduce the offset before tracking gives
# up and reports a probable direction fault. ~0.5 s at the loop's 10 Hz.
_STALL_LIMIT = 5


class RadarTracker:
    def __init__(self, stepper, overlay=None, *,
                 sweep_min_deg: float = 0.0, sweep_max_deg: float = 180.0,
                 scan_speed_rpm: float = 3.0, track_speed_rpm: float = 8.0,
                 fov_deg: float = 75.0, frame_width: int = 640,
                 priority_classes: list[str] | None = None,
                 lost_timeout_s: float = 3.0, initial_mode: str = SLEEP,
                 bow_deg: float | None = None, invert_tracking: bool = False,
                 min_track_conf: float = 0.0,
                 center_deadband_deg: float = 3.0, track_gain: float = 0.9,
                 track_speed_min_rpm: float = 1.5,
                 max_step_deg: float = 30.0,
                 lead_seconds: float = 0.35, velocity_window_s: float = 0.8,
                 velocity_speed_margin: float = 1.4) -> None:
        self.stepper = stepper
        self.overlay = overlay
        self.sweep_min = float(sweep_min_deg)
        self.sweep_max = float(sweep_max_deg)
        self.scan_speed = float(scan_speed_rpm)
        self.track_speed = float(track_speed_rpm)
        self.fov_deg = float(fov_deg)
        self.frame_width = int(frame_width)
        self.priority = set(priority_classes or ["boat", "person"])
        self.lost_timeout_s = float(lost_timeout_s)
        # Bar angle that points dead ahead — the origin tracking measures bearings
        # about. Defaults to the middle of the sweep range, which is what the
        # shipped 0-180° sweep means: 90° = bow, 0° = port beam, 180° = starboard.
        self.bow_deg = (float(bow_deg) if bow_deg is not None
                        else (self.sweep_min + self.sweep_max) / 2.0)
        # Mirror the bbox→bearing sign. Needed when the bar's + direction runs
        # opposite to "target moves right in frame" — e.g. the bar is geared or
        # mounted reversed, or its 0° is on the starboard side. Flip this when
        # only TRACK is mirrored; if manual jog is mirrored too the fault is the
        # DIR pin, so use stepper.invert_direction instead.
        self.invert_tracking = bool(invert_tracking)
        # "Centred enough" — inside this the bar stops rather than hunting. Must
        # be at least a step or two (0.9° each) or the bar buzzes forever chasing
        # sub-step corrections it can't make.
        self.center_deadband = max(0.5, float(center_deadband_deg))
        # Fraction of the measured offset to move per tick. 1.0 aims straight at
        # the target and would be exact if the FOV figure were; a little under
        # damps the overshoot that FOV error would otherwise turn into hunting.
        self.track_gain = max(0.05, min(2.0, float(track_gain)))
        # Speed floor, used when the target is already near centre. The bar
        # creeps for fine corrections and slews for big ones, so small
        # corrections don't get flung past centre by a fast ramp.
        self.track_speed_min = max(0.1, float(track_speed_min_rpm))
        # Cap on a single correction, so one bad frame can't fling the bar.
        self.max_step = max(1.0, float(max_step_deg))
        # How far ahead to aim, in seconds of the target's measured angular rate.
        # Covers the loop period plus detection latency plus the bar's own ramp;
        # 0 disables the feedforward and leaves a pure position controller.
        self.lead_seconds = max(0.0, float(lead_seconds))
        # Estimation window. Long enough to average out box jitter, short enough
        # to react to a change of pace.
        self.velocity_window_s = max(0.1, float(velocity_window_s))
        # Headroom on the slew speed above the bare rate needed to keep pace —
        # matching it exactly means never closing the error that already exists.
        self.velocity_speed_margin = max(1.0, float(velocity_speed_margin))

        self._track_class = ""   # operator-chosen single class; "" = use self.priority
        self._track_class_auto = False   # True when the pipeline set it, not the operator
        # Operator pin: False = "stop sweeping, just track". TRACK then holds
        # through a dropout instead of reverting to SCAN, and automatic SCAN
        # requests from the pipeline are ignored.
        self._auto_rescan = True
        # Why the bar isn't locked right now, in the operator's terms. Set on
        # every acquisition attempt — the alternative is guessing at "it knew I
        # was there but didn't track me" from outside the process, which cost
        # two bench round-trips on 2026-07-29/30.
        self._no_lock_reason: str = ""
        self._centered = False        # target inside the deadband → bar at rest
        self._last_offset: float | None = None
        self._stall_ticks = 0         # consecutive moves that didn't reduce the offset
        # Set while LOCKED but not converging — a different situation from
        # _no_lock_reason (which is about acquisition), and the one that matters
        # most, so it gets its own field rather than being hidden behind the
        # "◎ tracking" readout.
        self._track_warning: str = ""
        # (monotonic time, bow-relative bearing) samples for the rate estimate.
        # Only appended when the DETECTION changes — see _note_bearing.
        self._bearing_hist: deque = deque(maxlen=32)
        self._last_box_key: tuple | None = None
        self._target_rate = 0.0       # deg/s, + = target drifting to starboard
        # Minimum confidence a box needs before the bar will lock onto it. This is
        # the tracker's OWN gate, deliberately separate from the overlay's CONF
        # threshold: the overlay decides what is worth drawing and remembering,
        # this decides what is worth swinging a motor at. 0.0 = lock onto anything
        # the overlay kept (the pre-2026-07-29 behaviour).
        self._min_track_conf = max(0.0, min(1.0, float(min_track_conf)))
        self._mode = initial_mode
        self._goto: float | None = None
        self._target_locked = False
        self._target_info: dict | None = None   # {label, conf} of the locked target
        self._last_seen = 0.0
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # -- public, thread-safe command surface ------------------------------- #
    def set_mode(self, mode: str, *, automatic: bool = False) -> None:
        """Switch mode. ``automatic=True`` marks a request from the vision
        pipeline rather than the operator.

        The distinction matters because the pipeline resumes SCAN whenever its
        threat assessment goes quiet, which would silently undo an operator who
        has pinned TRACK-only. Operator intent wins: an automatic SCAN is
        ignored while the pin is on, and an operator SCAN lifts the pin (asking
        to scan plainly means you want scanning).
        """
        mode = mode.upper()
        if mode not in (SCAN, TRACK, HOLD, SLEEP):
            raise ValueError("unknown mode %r" % mode)
        with self._lock:
            if mode == SCAN:
                if automatic and not self._auto_rescan:
                    return
                if not automatic:
                    self._auto_rescan = True
            self._mode = mode
            if mode != TRACK:
                self._target_locked = False
                self._target_info = None

    def set_auto_rescan(self, enabled: bool) -> bool:
        """Allow / forbid falling back to SCAN when the target is lost.

        Disabling it is the "stop sweeping, just track" pin: the bar stays in
        TRACK and holds position through a dropout instead of wandering off on a
        sweep the moment a detection flickers. Also drops any class pin the
        pipeline had applied, so a stale automatic lock (e.g. onto a buoy that
        has since vanished) can't leave the tracker blind to everything else.
        """
        v = bool(enabled)
        with self._lock:
            self._auto_rescan = v
            if not v:
                self._mode = TRACK
                if self._track_class_auto:
                    self._track_class = ""
                    self._track_class_auto = False
        return v

    def set_track_class(self, label: str | None, *, automatic: bool = False) -> None:
        """Restrict tracking to one class label (keeps the bar following the same
        target the operator picked for the vision overlay). "" / None / "AUTO"
        restores the default priority_classes set.

        ``automatic=True`` marks a pin applied by the vision pipeline (it pins
        the bar to whatever it graded the primary threat). Those are recorded
        separately so ``set_auto_rescan`` can drop them: a pipeline pin that
        outlives the object it was made for narrows the tracker to one class
        that is no longer in view, and everything else — a person, say — is
        then invisible to it until the pipeline's clear-timeout expires.
        """
        tc = str(label or "").strip()
        if tc.upper() == "AUTO":
            tc = ""
        with self._lock:
            # An operator pin outranks an automatic one; don't let the pipeline
            # silently retarget a bar the operator has aimed by hand.
            if automatic and self._track_class and not self._track_class_auto:
                return
            self._track_class = tc
            self._track_class_auto = bool(automatic) and bool(tc)
            # Dropping the lock lets the next loop re-acquire against the new class.
            if tc:
                self._target_locked = False
                self._target_info = None

    def set_min_track_conf(self, conf: float) -> float:
        """Set the minimum confidence needed to lock the bar onto a target.

        Raising it above the currently locked target's score drops the lock on
        the spot rather than waiting for lost_timeout_s, so the operator sees the
        change take effect immediately instead of up to 3 s later.
        """
        v = max(0.0, min(1.0, float(conf)))
        with self._lock:
            self._min_track_conf = v
            info = self._target_info
            if info is not None and float(info.get("conf", 0.0)) < v:
                self._target_locked = False
                self._target_info = None
        return v

    def goto(self, degrees: float) -> None:
        """Queue an absolute move; switches to HOLD so the loop executes it."""
        with self._lock:
            self._goto = float(degrees)
            self._mode = HOLD
            self._target_locked = False

    def jog(self, delta_degrees: float) -> None:
        """Pan a relative amount (manual control). +ve = right/CW, -ve = left/CCW.

        Resolves the relative move against the bar's current angle here (a cheap,
        thread-safe read) and queues it as an absolute goto; the stepper clamps
        it to the travel limits, so jogging into an end stop simply parks there.
        """
        cur = self.stepper.get_position_degrees() if self.stepper is not None else 0.0
        self.goto(cur + float(delta_degrees))

    def center(self) -> None:
        """Point the bar dead ahead — the bow, not the raw zero of the axis.
        They coincide on the shipped config, but CENTER means "look forward"."""
        self.goto(self.bow_deg)

    def wake(self) -> None:
        with self._lock:
            self._mode = HOLD

    def status(self) -> dict:
        s = self.stepper.status() if self.stepper is not None else {"available": False}
        with self._lock:
            mode = self._mode
            locked = self._target_locked
            info = dict(self._target_info) if self._target_info else None
            track_class = self._track_class
            min_conf = self._min_track_conf
            auto_rescan = self._auto_rescan
            no_lock = self._no_lock_reason
            centered = self._centered
            offset = self._last_offset
            warning = self._track_warning
            rate = self._target_rate
        # While scanning the stepper reports SCANNING; otherwise mirror our mode.
        state = "SCANNING" if mode == SCAN else mode
        return {
            "available": s.get("available", False),
            "mock": s.get("mock"),
            "angle": s.get("angle"),
            "state": state,
            "mode": mode,
            "target_locked": locked,
            "target": info,                       # {label, conf} when locked
            "track_class": track_class,           # "" = auto (priority_classes)
            "track_conf": round(min_conf, 2),     # min confidence to lock the bar
            "auto_rescan": auto_rescan,           # False = operator pinned TRACK-only
            # Only meaningful while actually hunting — it goes stale in HOLD/SLEEP.
            "no_lock_reason": (no_lock if not locked and mode in (SCAN, TRACK) else ""),
            "track_warning": warning if locked else "",   # locked but not converging
            "centered": centered and locked,          # target inside the deadband
            "offset_deg": (round(offset, 1) if offset is not None and locked else None),
            # Target's angular rate (deg/s, + = drifting starboard) and the lead
            # the bar is applying for it.
            "target_rate_dps": (round(rate, 1) if locked else None),
            "lead_deg": (round(rate * self.lead_seconds, 1) if locked else None),
            "priority_classes": sorted(self.priority),
            "limits": s.get("limits"),            # manual travel range
            "sweep": [self.sweep_min, self.sweep_max],   # auto-scan range
            "has_slip_ring": s.get("has_slip_ring"),
            "bow_deg": self.bow_deg,              # bar angle that points dead ahead
            "invert_tracking": self.invert_tracking,
            "invert_direction": s.get("invert_direction"),
        }

    # -- lifecycle --------------------------------------------------------- #
    def start(self) -> None:
        if self.stepper is None:
            logger.warning("RadarTracker has no stepper — not starting")
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="radar-tracker", daemon=True)
        self._thread.start()
        logger.info("RadarTracker started (mode=%s, sweep=[%.0f,%.0f], bow=%.0f°, "
                    "invert_tracking=%s, min_track_conf=%.2f)",
                    self._mode, self.sweep_min, self.sweep_max, self.bow_deg,
                    self.invert_tracking, self._min_track_conf)

    def stop(self) -> None:
        self._stop.set()
        t = self._thread
        if t is not None and t.is_alive():
            t.join(timeout=3.0)
        if self.stepper is not None:
            self.stepper.cleanup()

    # -- control loop (daemon thread) -------------------------------------- #
    def _run(self) -> None:
        while not self._stop.is_set():
            with self._lock:
                mode, goto = self._mode, self._goto
                self._goto = None
            try:
                if mode == SLEEP:
                    self._ensure_not_scanning()
                    self.stepper.sleep()
                    time.sleep(0.1)
                elif mode == HOLD:
                    self._ensure_not_scanning()
                    if goto is not None:
                        self.stepper.rotate_to(goto, self.track_speed)
                    else:
                        self.stepper.maybe_auto_sleep()
                    time.sleep(0.05)
                elif mode == SCAN:
                    self._do_scan()
                elif mode == TRACK:
                    self._do_track()
            except Exception as e:  # noqa: BLE001 — a motion glitch must not kill the loop
                logger.error("radar tracker loop error: %s", e)
                time.sleep(0.2)

    def _ensure_not_scanning(self) -> None:
        if self.stepper.scanning:
            self.stepper.stop_scan()

    def _do_scan(self) -> None:
        if not self.stepper.scanning:
            self.stepper.scan_async(self.sweep_min, self.sweep_max, self.scan_speed)
        target = self._best_target()
        if target is not None:
            self.stepper.stop_scan()
            with self._lock:
                self._mode = TRACK
                self._target_locked = True
                self._target_info = self._target_dict(target)
                self._last_seen = time.monotonic()
                # Fresh acquisition — forget the previous target's convergence
                # history so its offsets can't trip the stall backstop.
                self._last_offset = None
                self._stall_ticks = 0
            # …and its motion history, or the jump from the old target's bearing
            # to the new one reads as an enormous rate and the bar leads wildly.
            self._reset_rate()
        time.sleep(0.1)

    def _do_track(self) -> None:
        self._ensure_not_scanning()
        target = self._best_target()
        if target is not None:
            with self._lock:
                self._target_locked = True
                self._target_info = self._target_dict(target)
                self._last_seen = time.monotonic()
            self._step_toward(target)
        elif (time.monotonic() - self._last_seen) > self.lost_timeout_s:
            with self._lock:
                self._target_locked = False
                self._target_info = None
                # With the operator's TRACK-only pin on, a dropout means HOLD
                # here and keep looking — not wander off on a sweep. A flickering
                # detection would otherwise bounce the bar between modes and it
                # never settles long enough to actually follow anything.
                if self._auto_rescan:
                    self._mode = SCAN
            # Target gone: stop leading on a rate we can no longer confirm.
            self._reset_rate()
            if not self._auto_rescan:
                self.stepper.maybe_auto_sleep()
        time.sleep(0.1)

    # -- detection helpers ------------------------------------------------- #
    def _boxes(self) -> list[tuple]:
        """Latest detection boxes from the overlay, or [] if unavailable."""
        if self.overlay is None:
            return []
        getter = getattr(self.overlay, "boxes", None)
        if getter is None:
            return []
        try:
            return getter() or []
        except Exception:  # noqa: BLE001
            return []

    def _best_target(self):
        """Highest-confidence box matching the wanted classes, else None.

        Wanted = the operator-chosen single class if set, else priority_classes.
        Box layout matches DetectionOverlay: (x1, y1, x2, y2, label, conf, hl).
        Boxes scoring below ``min_track_conf`` are ignored entirely, so a weak
        detection can still be drawn and mapped without the bar chasing it.

        Also records *why* nothing was chosen (``_no_lock_reason``), which the
        status surface publishes — "it saw me and didn't track" has three quite
        different causes and they are indistinguishable from the outside.
        """
        with self._lock:
            tc = self._track_class
            floor = self._min_track_conf
        wanted = {tc.lower()} if tc else {c.lower() for c in self.priority}
        best = None
        best_conf = -1.0
        seen: list[str] = []
        rejected: tuple[str, float] | None = None   # best wanted box under the floor
        for box in self._boxes():
            try:
                label, conf = str(box[4]), float(box[5])
            except (IndexError, TypeError, ValueError):
                continue
            seen.append(label)
            if label.lower() not in wanted:
                continue
            if conf < floor:
                if rejected is None or conf > rejected[1]:
                    rejected = (label, conf)
                continue
            if conf > best_conf:
                best, best_conf = box, conf
        self._set_no_lock_reason(best, seen, rejected, wanted, floor)
        return best

    def _set_reason(self, reason: str) -> None:
        with self._lock:
            self._no_lock_reason = reason

    def _set_no_lock_reason(self, best, seen, rejected, wanted, floor) -> None:
        """Phrase the acquisition outcome for the operator (empty = locked on)."""
        if best is not None:
            self._set_reason("")      # acquired — _step_toward owns any message
            return
        if rejected is not None:
            reason = ("%s %.2f is below TRK CONF %.2f"
                      % (rejected[0], rejected[1], floor))
        elif not seen:
            reason = "nothing detected"
        else:
            uniq = sorted(set(seen))[:4]
            reason = ("no %s in view (seeing: %s)"
                      % ("/".join(sorted(wanted)), ", ".join(uniq)))
        self._set_reason(reason)

    @staticmethod
    def _target_dict(box) -> dict:
        """Compact {label, conf} for the status surface (UI tracking readout)."""
        try:
            return {"label": box[4], "conf": round(float(box[5]), 3)}
        except (IndexError, TypeError, ValueError):
            return {"label": "?", "conf": 0.0}

    # -- aiming ------------------------------------------------------------ #
    def _boxes_right(self) -> list[tuple]:
        """Right-camera boxes, or [] when only one camera runs the detector."""
        if self.overlay is None:
            return []
        getter = getattr(self.overlay, "boxes_right", None)
        if getter is None:
            return []
        try:
            return getter() or []
        except Exception:  # noqa: BLE001
            return []

    def _match_right(self, box) -> tuple | None:
        """The right camera's box for the same object, or None.

        Both eyes ride the same bar with a 120 mm baseline, so the same object
        lands at nearly the same height and size in both frames and is displaced
        only horizontally. Matching on label + vertical centre is therefore
        enough, and is what keeps the median honest — pairing a person in one eye
        with a different person in the other would bias the bearing rather than
        de-noise it.
        """
        label = str(box[4]).lower()
        cy = (box[1] + box[3]) / 2.0
        h = max(1.0, box[3] - box[1])
        best, best_dy = None, None
        for r in self._boxes_right():
            try:
                if str(r[4]).lower() != label:
                    continue
                dy = abs(((r[1] + r[3]) / 2.0) - cy)
            except (IndexError, TypeError, ValueError):
                continue
            if dy > h:            # more than one box-height apart → not the same thing
                continue
            if best_dy is None or dy < best_dy:
                best, best_dy = r, dy
        return best

    def _target_offset_deg(self, box) -> float:
        """Target's horizontal offset from frame centre, in degrees.

        Positive = right of centre. Uses the **median of both cameras'** box
        centres when the right eye is also running the detector, else the single
        centre from the one that is.
        """
        centers = [(box[0] + box[2]) / 2.0]
        mate = self._match_right(box)
        if mate is not None:
            centers.append((mate[0] + mate[2]) / 2.0)
        target_x = sorted(centers)[len(centers) // 2] if len(centers) % 2 else \
            sum(centers) / len(centers)
        half = self.frame_width / 2.0
        if half <= 0:
            return 0.0
        offset = (target_x - half) / half * (self.fov_deg / 2.0)
        return -offset if self.invert_tracking else offset

    def _note_bearing(self, box, offset_deg: float) -> None:
        """Record a bearing sample, but only for a genuinely NEW detection.

        The tracker loop runs at 10 Hz while the detector is capped lower
        (``detect_max_fps``), so most ticks re-read the *same* box. Sampling
        those would be actively harmful: the offset is frozen while the bar keeps
        moving, so ``bar + offset`` drifts at exactly the bar's slew rate and the
        estimator would report the bar's own motion as target motion — a
        feedforward loop feeding on itself.
        """
        try:
            key = (round(box[0], 2), round(box[1], 2), round(box[2], 2),
                   round(box[3], 2), str(box[4]))
        except (IndexError, TypeError, ValueError):
            return
        if key == self._last_box_key:
            return
        self._last_box_key = key
        now = time.monotonic()
        # Bow-relative bearing: frame-independent, so it doesn't move just
        # because the bar did.
        bearing = self.stepper.get_position_degrees() - self.bow_deg + offset_deg
        with self._lock:
            self._bearing_hist.append((now, bearing))
            cutoff = now - self.velocity_window_s
            while len(self._bearing_hist) > 2 and self._bearing_hist[0][0] < cutoff:
                self._bearing_hist.popleft()
            self._target_rate = self._fit_rate()

    def _fit_rate(self) -> float:
        """Least-squares slope of bearing vs time (deg/s). Caller holds the lock.

        A regression over the window rather than a first/last difference: box
        edges jitter by a few pixels between frames, and a two-point difference
        turns that jitter straight into a phantom rate that the feedforward would
        then act on.
        """
        hist = self._bearing_hist
        n = len(hist)
        if n < 3:
            return 0.0
        t0 = hist[0][0]
        ts = [t - t0 for t, _ in hist]
        bs = [b for _, b in hist]
        span = ts[-1] - ts[0]
        if span < 0.05:                  # too short to divide by
            return 0.0
        mt, mb = sum(ts) / n, sum(bs) / n
        den = sum((t - mt) ** 2 for t in ts)
        if den <= 1e-9:
            return 0.0
        return sum((t - mt) * (b - mb) for t, b in zip(ts, bs)) / den

    def _reset_rate(self) -> None:
        """Forget the rate history — on a new lock, or when the target is lost."""
        with self._lock:
            self._bearing_hist.clear()
            self._last_box_key = None
            self._target_rate = 0.0

    def _rpm_for_rate(self, rate_dps: float) -> float:
        """Slew speed needed to merely keep pace with ``rate_dps`` (deg/s).

        One revolution is 360°, so deg/s ÷ 6 = rpm. The margin is what lets the
        bar actually *close* an error rather than just matching the target's pace
        and trailing it forever.
        """
        return abs(rate_dps) / 6.0 * self.velocity_speed_margin

    def _speed_cap(self) -> float:
        """Never ask for more than the motor is configured to give."""
        cap = getattr(self.stepper, "max_speed_rpm", None)
        return float(cap) if cap else self.track_speed

    def _speed_for(self, offset_deg: float, rate_dps: float = 0.0) -> float:
        """Slew fast when the target is out at the edge or moving quickly, creep
        when it is near centre and settled.

        Takes the LARGER of the two demands. Scaling on error alone means a
        target crossing fast through the middle of the frame gets the slowest
        possible bar exactly when it most needs the quickest — which is how a
        target outruns the frame despite the loop "working".
        """
        span = max(1e-6, self.fov_deg / 2.0)
        frac = min(1.0, abs(offset_deg) / span)
        by_error = self.track_speed_min + (self.track_speed - self.track_speed_min) * frac
        speed = max(by_error, self._rpm_for_rate(rate_dps))
        return max(self.track_speed_min, min(self._speed_cap(), speed))

    def _step_toward(self, box) -> None:
        """One correction: lead the target, and stop once it is centred and still."""
        offset = self._target_offset_deg(box)
        self._note_bearing(box, offset)
        rate = self._target_rate
        # Where the target will be by the time the bar gets there. This is the
        # whole point of the feedforward: a position-only loop reacts to an error
        # that has already opened, so the faster the target moves the further
        # behind it sits, until it walks out of frame.
        lead = rate * self.lead_seconds
        predicted = offset + lead

        # "Settled" needs both: centred AND not about to leave. A fast target
        # crossing the middle is momentarily at offset 0 and must NOT be treated
        # as done, or the bar stops dead and the target sails past.
        if abs(predicted) <= self.center_deadband and abs(offset) <= self.center_deadband:
            with self._lock:                     # centred — hold, don't hunt
                self._centered = True
                self._stall_ticks = 0
                self._last_offset = offset
                self._track_warning = ""
            return

        # Divergence warning. With the cameras on the bar the offset should
        # shrink as we turn; a run of corrections that only makes it worse means
        # either the bar is turning the wrong way (DIR polarity /
        # invert_tracking) or the target is genuinely outrunning it. Those need
        # opposite fixes, so the message picks between them on whether the rate
        # actually exceeds what the motor can slew.
        #
        # This only WARNS — it used to halt tracking, which turned out to be
        # worse than the problem: a target crossing at 30°/s opens a big offset
        # during the initial catch-up (before the rate estimate has filled its
        # window) and the halt then abandoned a target the bar could easily have
        # held. Nor is halting needed to prevent an end-stop runaway: under a
        # direction fault the target leaves the frame in a second or two and the
        # lock drops on its own, long before the bar winds anywhere.
        with self._lock:
            prev = self._last_offset
            # Don't judge convergence until the rate estimate is usable, or the
            # startup transient reads as divergence every single time.
            mature = len(self._bearing_hist) >= 3
            if mature and prev is not None and abs(offset) > abs(prev) - 0.5:
                self._stall_ticks += 1
            else:
                self._stall_ticks = 0
            self._last_offset = offset
            self._centered = False
            edge = abs(offset) > self.fov_deg / 4.0
            if self._stall_ticks >= _STALL_LIMIT and edge:
                self._track_warning = (
                    "target moving at %.0f°/s — faster than the bar can slew "
                    "(raise stepper.max_rpm / track_speed_rpm)" % abs(rate)
                    if self._rpm_for_rate(rate) > self._speed_cap() else
                    "not centring after %d corrections — the bar may be turning "
                    "the wrong way (check stepper.invert_direction / "
                    "invert_tracking)" % self._stall_ticks)
            else:
                self._track_warning = ""

        step = max(-self.max_step, min(self.max_step, predicted * self.track_gain))
        self.stepper.rotate_to(self.stepper.get_position_degrees() + step,
                               self._speed_for(offset, rate))
