"""A4988 stepper driver for the radar-bar pan mechanism (Pi 5 GPIO).

Drives a Creality BJ42D15-26V12 NEMA-17 (run bipolar) through an A4988
breakout straight off the **Pi 5 40-pin header** — the first thing in this
project to use the Pi 5 GPIO directly (every sensor otherwise hangs off the
Picos; see ``docs/pin_map.md``). 1/16 microstepping is wired in hardware on the
A4988 (MS1/MS2/MS3 → 3V3), giving 3200 steps/rev = 0.1125° resolution.

Pi 5 GPIO → A4988 (BCM numbering):
    GPIO23 → STEP
    GPIO24 → DIR
    GPIO25 → ENABLE  (active-LOW: 0 = energised/holding, 1 = freewheel)
    GPIO8  → SLEEP   (active-LOW: 0 = zero-current sleep, 1 = awake)

GPIO access uses **gpiozero** (which wraps lgpio on the Pi 5 — RPi.GPIO is
unsupported there). If gpiozero/lgpio isn't importable or the pins can't be
claimed (e.g. running on a laptop or in the simulator), the driver falls back
to ``mock`` mode: position tracking and timing still work, but no pins are
toggled. That keeps ``run_sim.py`` and the test suite working off-Pi, mirroring
how the camera / detection overlay degrade when their deps are missing.

Threading note: stepping is *blocking* (a ``time.sleep`` per pulse), so it must
never run on the asyncio event loop. ``scan_async`` runs the sweep on a daemon
thread; the production motion authority is ``radar_tracker.RadarTracker`` which
owns a single thread and serialises every move. A per-instance lock guards the
pulse train so two callers can't drive STEP at once.
"""
from __future__ import annotations

import logging
import threading
import time

logger = logging.getLogger(__name__)

try:
    from gpiozero import OutputDevice
    _GPIO_AVAILABLE = True
except Exception as _e:  # noqa: BLE001 — any import/backend failure → mock mode
    OutputDevice = None  # type: ignore[assignment]
    _GPIO_AVAILABLE = False
    logger.info("gpiozero unavailable (%s) — StepperMotor runs in mock mode", _e)


class StepperMotor:
    """A4988-driven stepper with absolute position tracking and ramping."""

    def __init__(self, step_pin: int = 23, dir_pin: int = 24,
                 enable_pin: int = 25, sleep_pin: int = 8,
                 steps_per_rev: int = 3200, max_speed_rpm: float = 10.0,
                 auto_sleep_s: float = 5.0,
                 min_deg: float = 0.0, max_deg: float = 180.0,
                 has_slip_ring: bool = False) -> None:
        self.steps_per_rev = int(steps_per_rev)
        self.max_speed_rpm = float(max_speed_rpm)
        self.auto_sleep_s = float(auto_sleep_s)
        self.has_slip_ring = bool(has_slip_ring)
        # Without a slip ring the cable can't take full rotation — clamp travel.
        self.min_deg = 0.0 if has_slip_ring else float(min_deg)
        self.max_deg = 360.0 if has_slip_ring else float(max_deg)

        self._deg_per_step = 360.0 / self.steps_per_rev
        self._position_steps = 0          # absolute, wrapped to one rev
        self._enabled = False
        self._asleep = True               # assume off until first wake
        self._last_move = time.monotonic()
        self._lock = threading.RLock()     # serialises the pulse train

        # Async sweep state
        self._scan_thread: threading.Thread | None = None
        self._stop_event = threading.Event()

        self.mock = not _GPIO_AVAILABLE
        self._step = self._dir = self._enable = self._sleep = None
        if not self.mock:
            try:
                # Raw OutputDevice + explicit values so the A4988 active-low
                # polarity stays obvious at each call site.
                self._step = OutputDevice(step_pin, initial_value=False)
                self._dir = OutputDevice(dir_pin, initial_value=False)
                self._enable = OutputDevice(enable_pin, initial_value=True)   # 1 = disabled
                self._sleep = OutputDevice(sleep_pin, initial_value=True)     # 1 = awake
                self._asleep = False
            except Exception as e:  # noqa: BLE001 — no Pi / pins busy → mock
                logger.warning("Stepper GPIO claim failed (%s) — mock mode", e)
                self.mock = True
        logger.info("StepperMotor init: pins step=%d dir=%d en=%d slp=%d "
                    "steps/rev=%d limits=[%.0f,%.0f] slip_ring=%s mock=%s",
                    step_pin, dir_pin, enable_pin, sleep_pin, self.steps_per_rev,
                    self.min_deg, self.max_deg, self.has_slip_ring, self.mock)

    # -- low-level pin helpers --------------------------------------------- #
    def _w(self, dev, value: int) -> None:
        if dev is not None:
            dev.value = 1 if value else 0

    # -- power management -------------------------------------------------- #
    def enable(self) -> None:
        """Energise and hold position (ENABLE low, SLEEP high)."""
        with self._lock:
            self._w(self._sleep, 1)
            self._w(self._enable, 0)
            self._enabled = True
            self._asleep = False
            self._last_move = time.monotonic()

    def disable(self) -> None:
        """De-energise — coils released, motor freewheels (ENABLE high)."""
        with self._lock:
            self._w(self._enable, 1)
            self._enabled = False

    def sleep(self) -> None:
        """Enter zero-current sleep (SLEEP low). Position is retained in code."""
        with self._lock:
            if not self._asleep:
                self._w(self._sleep, 0)
                self._asleep = True
                logger.debug("stepper sleep")

    def wake(self) -> None:
        """Leave sleep (SLEEP high) and let the charge pump settle (1 ms)."""
        with self._lock:
            if self._asleep:
                self._w(self._sleep, 1)
                time.sleep(0.001)
                self._asleep = False
                logger.debug("stepper wake")

    def maybe_auto_sleep(self) -> bool:
        """Sleep the motor if it has been idle longer than ``auto_sleep_s``.

        Caller (the tracker loop) invokes this while holding; returns True if it
        just put the motor to sleep. No-op while a scan thread is running.
        """
        if (not self._asleep and self._scan_thread is None
                and (time.monotonic() - self._last_move) > self.auto_sleep_s):
            self.sleep()
            return True
        return False

    # -- stepping ---------------------------------------------------------- #
    def step(self, steps: int, direction: int = 1, delay_us: int = 500) -> None:
        """Emit ``steps`` pulses. direction: 1 = CW, -1 = CCW.

        Trapezoidal ramp (ease in/out over up to 200 steps) keeps the radar bar
        from missing steps or vibrating the camera. Blocking — never call on the
        event loop.
        """
        steps = int(steps)
        if steps <= 0:
            return
        self.wake()
        if not self._enabled:
            self.enable()
        with self._lock:
            self._w(self._dir, 1 if direction >= 0 else 0)
            time.sleep(1e-6)  # DIR setup time (>200 ns)
            cruise = max(delay_us, 1) / 1_000_000.0
            ramp = min(200, steps // 2)
            for i in range(steps):
                # ease delay: up to 2.5x cruise at the very ends, →1x at cruise.
                if ramp and i < ramp:
                    factor = 2.5 - 1.5 * (i / ramp)
                elif ramp and i >= steps - ramp:
                    factor = 2.5 - 1.5 * ((steps - 1 - i) / ramp)
                else:
                    factor = 1.0
                self._w(self._step, 1)
                time.sleep(2e-6)
                self._w(self._step, 0)
                time.sleep(cruise * factor)
                self._position_steps = (self._position_steps + direction) % self.steps_per_rev
            self._last_move = time.monotonic()

    def _rpm_to_delay_us(self, rpm: float) -> int:
        rpm = max(0.1, min(self.max_speed_rpm, rpm))
        return int(60_000_000.0 / (rpm * self.steps_per_rev))

    def rotate_degrees(self, degrees: float, direction: int = 1,
                       speed_rpm: float | None = None) -> None:
        """Rotate a relative number of degrees."""
        steps = int(round(abs(degrees) / self._deg_per_step))
        delay = self._rpm_to_delay_us(speed_rpm if speed_rpm else self.max_speed_rpm)
        self.step(steps, 1 if direction >= 0 else -1, delay)

    def rotate_to(self, target_degrees: float, speed_rpm: float | None = None) -> None:
        """Move to an absolute angle (clamped to the configured travel limits)."""
        target = self._clamp(target_degrees)
        current = self.get_position_degrees()
        delta = target - current
        if self.has_slip_ring:
            # take the short way round a full circle
            delta = (delta + 180.0) % 360.0 - 180.0
        if abs(delta) < self._deg_per_step:
            return
        self.rotate_degrees(abs(delta), 1 if delta >= 0 else -1, speed_rpm)

    def _clamp(self, deg: float) -> float:
        if self.has_slip_ring:
            return deg % 360.0
        return max(self.min_deg, min(self.max_deg, deg))

    # -- position ---------------------------------------------------------- #
    def get_position_degrees(self) -> float:
        return round((self._position_steps * self._deg_per_step) % 360.0, 3)

    def reset_position(self) -> None:
        with self._lock:
            self._position_steps = 0

    def center(self, speed_rpm: float | None = None) -> None:
        """Return to 0° (home)."""
        self.rotate_to(0.0, speed_rpm)

    # -- sweeping ---------------------------------------------------------- #
    def scan(self, start_deg: float, end_deg: float, speed_rpm: float = 5.0) -> None:
        """Blocking single sweep from ``start_deg`` to ``end_deg``."""
        self.rotate_to(start_deg, speed_rpm)
        self.rotate_to(end_deg, speed_rpm)

    def scan_async(self, start_deg: float, end_deg: float, speed_rpm: float = 5.0) -> None:
        """Continuously sweep start↔end on a daemon thread until ``stop_scan``."""
        self.stop_scan()
        self._stop_event.clear()
        a, b = self._clamp(start_deg), self._clamp(end_deg)

        def _run() -> None:
            target = b
            self.rotate_to(a, speed_rpm)
            while not self._stop_event.is_set():
                self._sweep_to(target, speed_rpm)
                target = a if target == b else b

        self._scan_thread = threading.Thread(target=_run, name="stepper-scan", daemon=True)
        self._scan_thread.start()

    def _sweep_to(self, target: float, speed_rpm: float) -> None:
        """Step toward ``target`` in small chunks, bailing out on stop_event."""
        delay = self._rpm_to_delay_us(speed_rpm)
        while not self._stop_event.is_set():
            current = self.get_position_degrees()
            delta = self._clamp(target) - current
            if self.has_slip_ring:
                delta = (delta + 180.0) % 360.0 - 180.0
            if abs(delta) < self._deg_per_step:
                return
            chunk = min(abs(delta), 5.0)  # ≤5° per chunk → responsive to stop
            self.rotate_degrees(chunk, 1 if delta >= 0 else -1, speed_rpm)
            _ = delay

    def stop_scan(self) -> None:
        """Stop an async sweep and wait for the thread to finish."""
        self._stop_event.set()
        t = self._scan_thread
        if t is not None and t.is_alive() and t is not threading.current_thread():
            t.join(timeout=2.0)
        self._scan_thread = None

    @property
    def scanning(self) -> bool:
        return self._scan_thread is not None and self._scan_thread.is_alive()

    # -- status / teardown ------------------------------------------------- #
    def state(self) -> str:
        if self._asleep:
            return "SLEEP"
        if self.scanning:
            return "SCANNING"
        if self._enabled:
            return "HOLD"
        return "IDLE"

    def status(self) -> dict:
        return {
            "available": True,
            "mock": self.mock,
            "angle": self.get_position_degrees(),
            "state": self.state(),
            "enabled": self._enabled,
            "asleep": self._asleep,
            "limits": [self.min_deg, self.max_deg],
            "has_slip_ring": self.has_slip_ring,
        }

    def cleanup(self) -> None:
        """Stop motion, de-energise, sleep, and release the GPIO lines."""
        self.stop_scan()
        try:
            self.disable()
            self.sleep()
        except Exception:  # noqa: BLE001
            pass
        for dev in (self._step, self._dir, self._enable, self._sleep):
            try:
                if dev is not None:
                    dev.close()
            except Exception:  # noqa: BLE001
                pass
        logger.info("StepperMotor cleaned up")
