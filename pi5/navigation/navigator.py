"""Waypoint-following navigator.

Ported from reference/Boat_pico.py task_navigate(). Calculates
bearing and distance to the target waypoint and generates throttle
commands for the Boat Pico.

The Pi 5 runs this at ~5Hz and sends SET_THR commands over serial.
"""
from __future__ import annotations

import asyncio
import logging
import math
import time
from dataclasses import dataclass

from ..comms.pico_serial import PicoSerial
from .current_estimator import CurrentConfig, CurrentEstimator
from .geo import (
    _local_offset,
    distance_and_bearing,
    haversine_distance,
    heading_diff,
    los_course,
)

logger = logging.getLogger(__name__)


@dataclass
class NavConfig:
    """Navigation tuning parameters."""
    arrive_radius_m: float = 5.0
    hold_drift_m: float = 8.0
    cruise_throttle: int = 40
    heading_tolerance_deg: float = 10.0
    max_heading_error_deg: float = 90.0
    turn_min_throttle: int = 15
    update_rate_hz: float = 5.0
    # Distance-based speed ramp: full throttle above this distance
    full_speed_dist_m: float = 50.0
    # Minimum throttle fraction when very close (approach_radius → arrive_radius)
    min_approach_throttle: int = 15
    # ---- Align-first steering ----
    # The boat aims at the waypoint before making forward progress: forward speed
    # is gated by heading alignment, collapsing to zero once the heading error
    # exceeds align_speed_cut_deg so the boat pivots in place instead of arcing.
    # This makes it point directly at the next waypoint within the first fraction
    # of the leg (it rotates almost on the spot, covering negligible distance),
    # rather than orbiting the target.
    align_speed_cut_deg: float = 40.0
    # Throttle used for the differential pivot. Applied around the (gated) forward
    # speed and allowed to drive the inner motor into reverse down to
    # -turn_authority_throttle, so the boat can turn hard in place at any range.
    turn_authority_throttle: int = 55
    # ---- Line-of-sight (LOS) path following ----
    # When a leg start is known, steer to a lookahead point on the *track line*
    # between the previous waypoint and the target instead of pointing straight
    # at the target. This nulls cross-track error (the perpendicular drift a
    # naive "aim at the waypoint" law lets wind/current build up) so the boat
    # follows the intended line rather than curving in from wherever it drifted.
    los_enabled: bool = True
    # Lookahead distance Δ (metres): smaller = more aggressive return to the
    # track; larger = gentler. ~3–8 boat lengths is typical. The desired course
    # is chi_path - atan2(xte, Δ), so at xte = Δ the boat aims 45° back to track.
    los_lookahead_m: float = 12.0
    # Integral LOS (ILOS) gain — set > 0 to cancel the *steady* cross-track bias
    # from a constant current/wind (Lekkas & Fossen). 0 = pure lookahead LOS
    # (robust, no windup risk); enable with a small value after field tuning.
    los_integral_gain: float = 0.0
    # Anti-windup clamp for the ILOS integrator (metre·seconds).
    los_integral_clamp: float = 60.0
    # ---- Per-motor thrust trim (mismatched motors) ----
    # Two different-Kv motors (e.g. the twin 2814s on the test bench) produce
    # unequal thrust at equal command, so the boat crabs. These gains scale each
    # motor's command just before it's sent, so equal *command* → equal *thrust*.
    # 1.0 = no trim. Bench-calibrate until the boat runs straight at equal command
    # (bias the faster motor's gain down); the heading loop mops up the remainder.
    motor_gain_left: float = 1.0
    motor_gain_right: float = 1.0
    # ---- Manual (WASD) override ----
    # Startup speed cap for the dashboard's manual drive, in percent. The
    # operator moves it live with the speed bar; this is only the initial value.
    # Deliberately well below 100 so an armed override does not launch at full
    # throttle on the first keypress.
    manual_speed: int = 40
    # ---- Water-current estimation + station-keeping (stay mode) ----
    # Through-water speed model  v = thrust_a*|thr| + thrust_b*thr^2  (thr = mean
    # forward command, -1..1). Used to estimate the current as
    # (GPS ground velocity - modelled through-water velocity). Calibrate per boat.
    current_enabled: bool = True
    current_thrust_a: float = 0.35
    current_thrust_b: float = 0.15
    # Active station-keeping: hold the target position AGAINST the estimated
    # current (feedforward) instead of the old "drift until hold_drift_m then
    # re-acquire" ping-pong. The controller drives the boat's required
    # through-water velocity = desired-ground-velocity - current_estimate.
    sk_pos_gain: float = 0.25        # desired ground speed per metre of error (1/s)
    sk_max_speed: float = 0.8        # cap on station-keeping ground speed (m/s)
    sk_deadband_m: float = 1.2       # inside this radius + negligible current -> idle
    sk_min_water_speed: float = 0.04  # required through-water speed below which idle
    sk_speed_gain: float = 90.0      # throttle (0-100) per m/s of required water speed


@dataclass
class NavState:
    """Current navigation state — exposed for telemetry and the dashboard."""
    target_lat: float | None = None
    target_lon: float | None = None
    distance_m: float = 0.0
    bearing_deg: float = 0.0
    heading_error: float = 0.0
    throttle_left: int = 0
    throttle_right: int = 0
    arrived: bool = False
    active: bool = False
    # LOS path-following telemetry: signed cross-track error (m, +starboard) and
    # the steering course actually commanded (may differ from bearing_deg when
    # LOS is nulling drift). avoiding = a CV obstacle override is in effect.
    cross_track_m: float = 0.0
    course_deg: float = 0.0
    avoiding: bool = False
    # Water-current estimate: set = compass direction it flows TOWARD (0-360),
    # drift = speed (m/s). station_keeping = actively holding against the current.
    current_set_deg: float = 0.0
    current_drift_ms: float = 0.0
    station_keeping: bool = False
    # Manual (WASD) override. manual_stale = the dead-man timer tripped, so the
    # motors are being held at zero until a fresh input arrives.
    manual: bool = False
    manual_speed: int = 40
    manual_stale: bool = False


class Navigator:
    """Calculates throttle commands to steer toward a target waypoint.

    Usage:
        nav = Navigator(pico, config)
        nav.goto(lat, lon)
        await nav.start()    # runs in background
        ...
        nav.stop_nav()
    """

    def __init__(self, pico: PicoSerial, config: NavConfig | None = None) -> None:
        self._pico = pico
        self._config = config or NavConfig()
        self.state = NavState()

        # Hold position (station-keeping)
        self._hold_lat: float | None = None
        self._hold_lon: float | None = None
        self._holding = False

        # Obstacle avoidance override (set by CV module later)
        self._avoid_left: int = 0
        self._avoid_right: int = 0

        # LOS path-following: start of the current leg (previous waypoint, or the
        # position where goto() was issued) + the ILOS cross-track integrator.
        self._leg_lat: float | None = None
        self._leg_lon: float | None = None
        self._xte_integral: float = 0.0
        self._last_xte: float = 0.0

        # Water-current estimation + active station-keeping.
        self._current = CurrentEstimator(CurrentConfig(
            thrust_a=self._config.current_thrust_a,
            thrust_b=self._config.current_thrust_b))
        self._last_thr_frac: float = 0.0            # last mean forward cmd (-1..1)
        self._last_cur_gps: tuple[float, float] | None = None

        # Manual (WASD) override — highest priority in the nav loop.
        self._manual = False
        self._manual_surge = 0.0        # -1..+1, + = ahead
        self._manual_yaw = 0.0          # -1..+1, + = starboard
        self._manual_speed = int(getattr(self._config, "manual_speed", 40))
        self._manual_stamp = 0.0        # monotonic() of the last operator input

        # Throttle-failure log de-duplication. The loop runs at update_rate_hz, so
        # a persistent refusal (a latched Pico ESTOP NAKs every SET_THR) writes
        # 5 identical lines a second and buries the alert that explains it.
        self._thr_err_sig: str | None = None
        self._thr_err_stamp = 0.0

        self._task: asyncio.Task[None] | None = None
        self._on_arrived: asyncio.Event = asyncio.Event()

    def goto(self, lat: float, lon: float,
             from_lat: float | None = None, from_lon: float | None = None) -> None:
        """Set a target waypoint and begin navigating.

        ``from_lat``/``from_lon`` fix the start of the track line for LOS path
        following (typically the previous waypoint). If omitted, the leg starts
        from wherever the boat is on the first navigation tick, so a bare
        ``goto()`` still follows a sensible straight line from the current spot.
        """
        # An explicit autonomous command means the operator is handing control
        # back. Without this the manual branch would keep outranking the new
        # target and the boat would sit still while the UI claimed it was under
        # way. Done here rather than at the API so every caller is covered.
        if self._manual:
            self.enable_manual(False)
        self.state.target_lat = lat
        self.state.target_lon = lon
        self.state.arrived = False
        self.state.active = True
        self._holding = False
        self._leg_lat = from_lat
        self._leg_lon = from_lon
        self._xte_integral = 0.0
        self._on_arrived.clear()
        logger.info("NAV goto %.6f, %.6f", lat, lon)

    def hold(self, lat: float, lon: float) -> None:
        """Enter station-keeping mode at a position."""
        if self._manual:            # same hand-back rule as goto()
            self.enable_manual(False)
        self._hold_lat = lat
        self._hold_lon = lon
        self._holding = True
        self.state.active = False
        logger.info("NAV hold at %.6f, %.6f", lat, lon)

    def stop_nav(self) -> None:
        """Stop all navigation. Motors will be set to zero."""
        self.state.active = False
        self.state.target_lat = None
        self.state.target_lon = None
        self._holding = False
        self.state.throttle_left = 0
        self.state.throttle_right = 0
        # Drop the LOS leg + integrator so the next goto() starts a fresh track.
        self._leg_lat = None
        self._leg_lon = None
        self._xte_integral = 0.0

    # ---- Manual (WASD) override ------------------------------------------
    # Dead-man interval. The browser repeats the current key state at ~10 Hz; if
    # nothing arrives within this window the loop zeroes the motors on its own.
    # That is the whole safety story for a control surface driven over a network
    # by a tab that can be closed, backgrounded, or lose WiFi mid-turn — the ESCs
    # hold their last pulse forever otherwise.
    MANUAL_TIMEOUT_S = 0.75

    def enable_manual(self, on: bool) -> None:
        """Enter or leave manual override.

        Entering cancels any autonomous navigation (goto/stay) so the two cannot
        fight over the throttle, and starts from a stopped, stale state — the
        boat does not move until the operator actually presses a key.
        """
        on = bool(on)
        if on:
            self.stop_nav()
            self._manual_surge = 0.0
            self._manual_yaw = 0.0
            self._manual_stamp = 0.0        # stale until the first real input
        else:
            self._manual_surge = 0.0
            self._manual_yaw = 0.0
        self._manual = on
        self.state.manual = on
        self.state.manual_stale = False
        logger.info("MANUAL override %s", "ENABLED" if on else "disabled")

    def manual_input(self, surge: float, yaw: float) -> None:
        """Feed one operator input sample. Ignored unless manual mode is on."""
        if not self._manual:
            return
        self._manual_surge = max(-1.0, min(1.0, float(surge)))
        self._manual_yaw = max(-1.0, min(1.0, float(yaw)))
        self._manual_stamp = time.monotonic()

    def set_manual_speed(self, pct: int) -> int:
        """Set the manual speed cap (0-100 %). Returns the clamped value."""
        self._manual_speed = int(max(0, min(100, int(pct))))
        self.state.manual_speed = self._manual_speed
        return self._manual_speed

    @property
    def manual_speed(self) -> int:
        return self._manual_speed

    def manual_mix(self) -> tuple[int, int]:
        """Mix surge/yaw into (left, right) percent, scaled by the speed cap.

        Turning is differential: yaw adds to one side and subtracts from the
        other, so full yaw with no surge pivots in place (which needs the ESCs in
        bidirectional/3D mode — see docs/esc_setup.md). If the combination would
        clip past 100 the pair is scaled down together, preserving the *ratio*
        rather than letting one side saturate and quietly turn the boat.
        """
        scale = self._manual_speed / 100.0
        fwd = self._manual_surge * scale * 100.0
        turn = self._manual_yaw * scale * 100.0
        left = fwd + turn
        right = fwd - turn
        peak = max(abs(left), abs(right))
        if peak > 100.0:
            left = left * 100.0 / peak
            right = right * 100.0 / peak
        return int(round(left)), int(round(right))

    def set_avoidance_override(self, left: int, right: int) -> None:
        """Set obstacle avoidance throttle override (from CV module).

        When non-zero, these values replace the navigator's throttle output.
        Set both to 0 to cancel the override.
        """
        self._avoid_left = left
        self._avoid_right = right

    async def wait_arrived(self, timeout: float | None = None) -> bool:
        """Block until the current waypoint is reached.

        Returns True if arrived, False if timed out.
        """
        try:
            await asyncio.wait_for(self._on_arrived.wait(), timeout)
            return True
        except asyncio.TimeoutError:
            return False

    def compute_throttle(
        self, lat: float, lon: float, hdg: float,
        tgt_lat: float, tgt_lon: float,
        from_lat: float | None = None, from_lon: float | None = None,
    ) -> tuple[int, int, float, float, float, bool]:
        """Pure function: compute throttle given current and target position.

        Returns (left, right, distance, brg, error, arrived), where ``brg`` is
        the bearing to the target and ``error`` is the heading error against the
        *steering course*. When a leg start (``from_lat``/``from_lon``) is given
        and LOS is enabled, the steering course is the lookahead line-of-sight
        course along the track line (which nulls cross-track drift); otherwise it
        is the direct bearing to the target — preserving the legacy behaviour.
        """
        cfg = self._config
        dist, brg = distance_and_bearing(lat, lon, tgt_lat, tgt_lon)

        # Steering course: LOS along the leg when a leg start is known, else
        # straight at the target (the original point-and-go behaviour).
        if from_lat is not None and from_lon is not None and cfg.los_enabled:
            course, self._last_xte = los_course(
                from_lat, from_lon, tgt_lat, tgt_lon, lat, lon,
                lookahead_m=cfg.los_lookahead_m,
                xte_integral=self._xte_integral,
                integral_gain=cfg.los_integral_gain)
        else:
            course, self._last_xte = brg, 0.0
        err = heading_diff(hdg, course)

        if dist < cfg.arrive_radius_m:
            return 0, 0, dist, brg, err, True

        # ---- Speed scaling based on distance ----
        # Ramp from min_approach_throttle at arrive_radius to cruise_throttle
        # at full_speed_dist_m
        if dist >= cfg.full_speed_dist_m:
            dist_factor = 1.0
        else:
            # Linear ramp between arrive_radius and full_speed_dist_m
            ramp_range = cfg.full_speed_dist_m - cfg.arrive_radius_m
            dist_factor = (dist - cfg.arrive_radius_m) / ramp_range if ramp_range > 0 else 1.0
            dist_factor = max(0.0, min(1.0, dist_factor))

        # ---- Alignment gate ----
        # 1.0 when pointed at the waypoint, ramping to 0.0 as the heading error
        # grows past align_speed_cut_deg. This gates forward speed so a misaligned
        # boat rotates almost in place (covering negligible distance) until it is
        # aimed, then drives — instead of arcing forward and orbiting the target.
        abs_err = abs(err)
        if abs_err <= cfg.heading_tolerance_deg:
            align = 1.0
        else:
            span = max(1.0, cfg.align_speed_cut_deg - cfg.heading_tolerance_deg)
            align = max(0.0, 1.0 - (abs_err - cfg.heading_tolerance_deg) / span)

        # ---- Forward speed ----
        # Distance-scaled cruise, gated by alignment. The min_approach floor only
        # applies to the extent the boat is aligned, so a badly-misaligned boat
        # can drop to ~zero forward throttle and pivot on the spot.
        fwd = cfg.cruise_throttle * dist_factor
        fwd_floor = cfg.min_approach_throttle * align
        fwd = int(max(fwd_floor, min(float(cfg.cruise_throttle), fwd * align)))

        # ---- Differential steering (pivot) ----
        # Turn authority is strong at any range so the boat snaps onto the bearing
        # early in the leg. It ramps in from the heading tolerance up to a full
        # pivot at max_heading_error_deg.
        if abs_err < cfg.heading_tolerance_deg:
            turn = 0
        else:
            blend = min(
                (abs_err - cfg.heading_tolerance_deg)
                / max(1.0, cfg.max_heading_error_deg - cfg.heading_tolerance_deg),
                1.0,
            )
            # Floor the differential at turn_min_throttle so a small residual
            # error still produces a brisk correction and the heading converges
            # fully into the tolerance band instead of stalling just outside it.
            turn = max(cfg.turn_min_throttle, int(cfg.turn_authority_throttle * blend))

        if err >= 0:
            # Turn right: left motor faster → boat pivots right
            left = fwd + turn
            right = fwd - turn
        else:
            # Turn left: right motor faster → boat pivots left
            left = fwd - turn
            right = fwd + turn

        # Clamp. The inner motor may reverse down to -turn_authority_throttle so
        # the boat can turn hard in place; motors saturate at ±100.
        rev_floor = -cfg.turn_authority_throttle
        left = max(rev_floor, min(100, left))
        right = max(rev_floor, min(100, right))

        return left, right, dist, brg, err, False

    def _log_thr_error(self, exc: Exception, where: str) -> None:
        """Log a SET_THR failure once, then at most every 5 s while it persists.

        Adds the recovery step for the one cause the operator can actually clear:
        a latched Pico ESTOP refuses every throttle command until a RESUME, and
        nothing else in the stack says so.
        """
        reason = getattr(exc, "reason", None)
        sig = "%s:%s" % (where, reason or str(exc))
        now = time.monotonic()
        if sig == self._thr_err_sig and now - self._thr_err_stamp < 5.0:
            return
        self._thr_err_sig = sig
        self._thr_err_stamp = now
        if reason == "ESTOP":
            logger.error(
                "SET_THR refused (%s): Boat Pico is latched in ESTOP — clear it "
                "(dashboard CLEAR E-STOP / POST /api/resume) before it will drive",
                where)
        elif reason == "RC_ACTIVE":
            logger.error(
                "SET_THR refused (%s): Boat Pico is in RC override — release RC "
                "to hand control back to the Pi", where)
        elif reason == "ESC_UNSAFE":
            logger.error(
                "SET_THR refused (%s): a drive ESC is not confirmed bi-directional, "
                "so 1.5 ms 'neutral' would be ~50%% throttle to it and ESTOP could "
                "not stop it. Throttle stays blocked until the ESC is set to "
                "3D/bi-directional mode and escs.BIDIR_CONFIRMED is updated "
                "(docs/esc_setup.md)", where)
        else:
            logger.error("SET_THR failed (%s): %s", where, exc)

    def _trim(self, left: int, right: int) -> tuple[int, int]:
        """Scale each motor command by its trim gain and re-clamp to [-100, 100].

        Corrects the crab from two mismatched-Kv motors so equal command yields
        equal thrust. A no-op when both gains are 1.0.
        """
        cfg = self._config
        left = int(max(-100, min(100, round(left * cfg.motor_gain_left))))
        right = int(max(-100, min(100, round(right * cfg.motor_gain_right))))
        return left, right

    def _steer_to(self, fwd: int, err: float) -> tuple[int, int]:
        """Align-first differential-thrust steering toward a course error.

        Same shape as compute_throttle's steering (forward speed gated by heading
        alignment so a misaligned boat pivots in place, plus a differential turn
        term). Shared by station-keeping.
        """
        cfg = self._config
        abs_err = abs(err)
        if abs_err <= cfg.heading_tolerance_deg:
            align = 1.0
        else:
            span = max(1.0, cfg.align_speed_cut_deg - cfg.heading_tolerance_deg)
            align = max(0.0, 1.0 - (abs_err - cfg.heading_tolerance_deg) / span)
        fwd = int(fwd * align)
        if abs_err < cfg.heading_tolerance_deg:
            turn = 0
        else:
            blend = min(
                (abs_err - cfg.heading_tolerance_deg)
                / max(1.0, cfg.max_heading_error_deg - cfg.heading_tolerance_deg),
                1.0,
            )
            turn = max(cfg.turn_min_throttle, int(cfg.turn_authority_throttle * blend))
        left, right = (fwd + turn, fwd - turn) if err >= 0 else (fwd - turn, fwd + turn)
        rev = -cfg.turn_authority_throttle
        return max(rev, min(100, left)), max(rev, min(100, right))

    def station_keep(self, lat: float, lon: float, hdg: float) -> tuple[int, int]:
        """Current-aware station-keeping throttle to hold the hold-point.

        Required *through-water* velocity = (desired ground velocity toward the
        hold point) - (estimated current). The boat is pointed into that vector
        and its forward throttle scaled to it, so it actively noses into the
        current and holds station rather than drifting to a dead-band edge and
        lunging back. Returns (left, right) motor commands (pre-trim).
        """
        cfg = self._config
        if self._hold_lat is None or self._hold_lon is None:
            return 0, 0
        dE, dN = _local_offset(lat, lon, self._hold_lat, self._hold_lon)  # boat->hold (E,N)
        err_m = math.hypot(dE, dN)
        v_des = min(cfg.sk_max_speed, cfg.sk_pos_gain * err_m)
        if err_m > 1e-3:
            gE, gN = v_des * dE / err_m, v_des * dN / err_m
        else:
            gE = gN = 0.0
        cE, cN = self._current.vector if cfg.current_enabled else (0.0, 0.0)
        wE, wN = gE - cE, gN - cN               # required through-water velocity
        w_mag = math.hypot(wE, wN)
        if err_m < cfg.sk_deadband_m and w_mag < cfg.sk_min_water_speed:
            return 0, 0
        if w_mag < cfg.sk_min_water_speed:
            return 0, 0
        course = math.degrees(math.atan2(wE, wN)) % 360.0
        err = heading_diff(hdg, course)
        fwd = int(min(cfg.cruise_throttle, cfg.sk_speed_gain * w_mag))
        return self._steer_to(fwd, err)

    async def _nav_loop(self) -> None:
        """Background navigation loop — runs at update_rate_hz."""
        interval = 1.0 / self._config.update_rate_hz
        while True:
            try:
                tel = self._pico.telemetry

                # --- Water-current estimate — refreshed each new GPS fix ---
                if (self._config.current_enabled
                        and (tel.lat, tel.lon) != self._last_cur_gps):
                    self._last_cur_gps = (tel.lat, tel.lon)
                    s_deg, drift_ms = self._current.update(
                        time.monotonic(), tel.lat, tel.lon, tel.heading,
                        self._last_thr_frac)
                    self.state.current_set_deg = s_deg
                    self.state.current_drift_ms = drift_ms

                # --- Manual override: outranks everything, including stay mode ---
                if self._manual:
                    stale = (time.monotonic() - self._manual_stamp
                             > self.MANUAL_TIMEOUT_S)
                    if stale:
                        left, right = 0, 0
                    else:
                        left, right = self._trim(*self.manual_mix())
                    self.state.manual_stale = stale
                    self.state.station_keeping = False
                    self.state.avoiding = False
                    self.state.throttle_left = left
                    self.state.throttle_right = right
                    self._last_thr_frac = (left + right) / 200.0
                    try:
                        await self._pico.set_throttle(left, right)
                    except Exception as e:
                        self._log_thr_error(e, "manual")

                # --- Stay mode: active current-aware station-keeping (priority) ---
                elif self._holding and self._hold_lat is not None:
                    left, right = self.station_keep(tel.lat, tel.lon, tel.heading)
                    self.state.distance_m = haversine_distance(
                        tel.lat, tel.lon, self._hold_lat, self._hold_lon)
                    avoiding = self._avoid_left != 0 or self._avoid_right != 0
                    if avoiding:
                        left, right = self._avoid_left, self._avoid_right
                    left, right = self._trim(left, right)
                    self.state.throttle_left, self.state.throttle_right = left, right
                    self.state.station_keeping = True
                    self.state.avoiding = avoiding
                    self._last_thr_frac = (left + right) / 200.0
                    try:
                        await self._pico.set_throttle(left, right)
                    except Exception as e:
                        self._log_thr_error(e, "stay")
                elif self.state.active and self.state.target_lat is not None:
                    self.state.station_keeping = False
                    # Anchor the LOS track line: use the caller-supplied leg
                    # start, else latch the boat's current position the first
                    # tick so the leg runs from here to the target.
                    if self._leg_lat is None or self._leg_lon is None:
                        self._leg_lat, self._leg_lon = tel.lat, tel.lon

                    left, right, dist, brg, err, arrived = self.compute_throttle(
                        tel.lat, tel.lon, tel.heading,
                        self.state.target_lat, self.state.target_lon,
                        self._leg_lat, self._leg_lon,
                    )

                    self.state.distance_m = dist
                    self.state.bearing_deg = brg
                    self.state.heading_error = err
                    self.state.cross_track_m = self._last_xte
                    self.state.course_deg = (tel.heading + err) % 360.0

                    # ILOS: integrate cross-track error to cancel steady drift,
                    # but freeze the integrator while pivoting hard or avoiding an
                    # obstacle (both are transients that would otherwise wind it
                    # up). Clamped for anti-windup.
                    avoiding = self._avoid_left != 0 or self._avoid_right != 0
                    if (self._config.los_integral_gain > 0.0
                            and abs(err) < self._config.align_speed_cut_deg
                            and not avoiding):
                        self._xte_integral += self._last_xte * interval
                        clamp = self._config.los_integral_clamp
                        self._xte_integral = max(-clamp, min(clamp, self._xte_integral))
                    self.state.avoiding = avoiding

                    if arrived:
                        self.state.arrived = True
                        self.state.active = False
                        self.state.throttle_left = 0
                        self.state.throttle_right = 0
                        self._last_thr_frac = 0.0
                        self._on_arrived.set()
                        logger.info("NAV arrived at %.6f, %.6f",
                                    self.state.target_lat, self.state.target_lon)
                        try:
                            await self._pico.set_throttle(0, 0)
                        except Exception:
                            pass
                    else:
                        # Apply obstacle avoidance override if active
                        if self._avoid_left != 0 or self._avoid_right != 0:
                            left = self._avoid_left
                            right = self._avoid_right

                        # Per-motor trim for mismatched motors (applied last, to
                        # whatever the final command is — nav or avoidance).
                        left, right = self._trim(left, right)
                        self.state.throttle_left = left
                        self.state.throttle_right = right
                        self._last_thr_frac = (left + right) / 200.0
                        try:
                            await self._pico.set_throttle(left, right)
                        except Exception as e:
                            self._log_thr_error(e, "nav")
                else:
                    # Not navigating — ensure motors are stopped
                    self.state.station_keeping = False
                    if self.state.throttle_left != 0 or self.state.throttle_right != 0:
                        self.state.throttle_left = 0
                        self.state.throttle_right = 0
                        self._last_thr_frac = 0.0
                        try:
                            await self._pico.set_throttle(0, 0)
                        except Exception:
                            pass

            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error("Nav loop error: %s", e)

            await asyncio.sleep(interval)

    async def start(self) -> None:
        """Start the background navigation loop."""
        self._task = asyncio.create_task(self._nav_loop())

    async def stop(self) -> None:
        """Stop the navigation loop and zero motors."""
        self.stop_nav()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        try:
            await self._pico.set_throttle(0, 0)
        except Exception:
            pass
