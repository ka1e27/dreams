# Current-aware station-keeping & incoming-wave detection

Two autonomy features added for open-water robustness. Both are simulation-
testable and degrade safely.

## 1. Water-current estimation + station-keeping

`pi5/navigation/current_estimator.py` + additions to `pi5/navigation/navigator.py`.

**Estimate.** With no water-speed sensor, the current vector is
`current = GPS ground velocity − modelled through-water velocity`, where the
model is `v = thrust_a·|thr| + thrust_b·thr²` projected along the compass heading
(`thr` = mean forward motor command, −1..1). Ground velocity is a low-pass-
filtered finite difference of GPS fixes (refreshed each new fix); the current is
smoothed again (it changes slowly). Reported as **set** (compass direction the
current flows toward) and **drift** (m/s) — exposed on `NavState`/`/api/status`
(`navigation.current_set_deg`, `current_drift_ms`) and in the UI.

Because the model is 0 at 0 throttle, a coasting boat reads `current = ground
track`; a boat actively holding station (stationary over ground while thrusting)
reads `current = −water`, both correct. Compass heading is valid at any speed, so
there is no low-speed special case.

**Station-keeping (stay mode).** `Navigator.station_keep()` replaces the old
"drift to `hold_drift_m` then re-acquire" ping-pong. It builds the required
through-water velocity = *(desired ground velocity toward the hold point)* −
*(current estimate)*, points the bow into it and scales forward throttle to it —
so the boat noses into the current and holds. Verified in sim (0.35 m/s current →
holds within ~0.4 m; current estimate recovers 090°/0.35 m/s). `NavState.
station_keeping` lights the UI badge.

**Transit.** ILOS (integral line-of-sight, already in `geo.los_course`) cancels a
steady cross-track bias from current during waypoint legs; leave
`navigation.los_integral_gain` at a small value after field tuning.

**Calibration.** Defaults `thrust_a=0.35, thrust_b=0.15` are a gentle small-boat
curve. To calibrate: in still water drive known throttles, record GPS speed, fit
`v = a·thr + b·thr²`, set `navigation.current_thrust_a/b`. The station-keeper's
P-term holds position even with a rough model — calibration mainly improves the
*displayed* current accuracy.

**Config** (`navigation:`): `current_enabled`, `current_thrust_a/b`,
`sk_pos_gain`, `sk_max_speed`, `sk_deadband_m`, `sk_min_water_speed`,
`sk_speed_gain`. **Sim testing:** `POST /api/sim/current {east_mps, north_mps}`
then `HOLD`.

## 2. Incoming-wave detection (capsize avoidance)

`pi5/cv/wave_detector.py`, wired into `pi5/cv/pipeline.py`.

A small catamaran capsizes when a big wave hits it beam-on; the response is to
bow into steep waves. A cheap (~3 ms/frame) horizon + optical-flow watch on the
Tier-1 loop raises an early warning:

1. **Horizon** — per-column water/sky boundary from the strongest horizontal
   gradient band (or a supplied water mask); its median row rising toward the
   camera + tilting is the swell cue.
2. **Looming flow** — sparse Lucas-Kanade in a band below the horizon; net upward
   motion = a face growing toward us.
3. **Fusion** — rise-rate + looming + rough time-to-impact → a 0-1 **severity**,
   gated by a persistence state machine so wakes/chop/glare don't false-latch.

Outputs `incoming`, `bearing_deg` (relative to bow, + = starboard), `severity`,
`ttc_s` — on `vision_state()`/`/api/status` (`vision.wave`) and drawn on the
`/video` HUD (horizon line + chevron toward the wave). When a severe wave is
imminent and no obstacle is being dodged, the pipeline pushes a **bow-into-wave**
override (pivot toward the wave bearing, throttle eased but nonzero for steerage)
through the navigator's override channel; obstacle avoidance takes priority.

**Config** (`vision.wave_detection:`): `enabled`, `max_fps`, `trigger_severity`,
`response_enabled`, `turn_severity`, `turn_gain`, `turn_min`.

**Limitations / tuning.** No IMU pitch input yet, so a hard pitch of the boat can
nudge the horizon — the persistence window + smoothing absorb short transients;
wire pitch into `analyze(pitch_deg=…)` to de-tilt fully. Tune `trigger_severity`
on real water. Detection is monocular-robust; stereo/TTC refine imminence.
