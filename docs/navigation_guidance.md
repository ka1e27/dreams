# Navigation guidance — LOS path following + reactive avoidance

How the boat steers between waypoints and around obstacles, and how to tune it.
Code: `pi5/navigation/navigator.py`, `pi5/navigation/geo.py`, `pi5/cv/avoidance.py`.

---

## Why line‑of‑sight (LOS), not "point at the waypoint"

The naive law — face the next waypoint and drive — ignores **cross‑track error**: the
perpendicular distance from the boat to the straight line between waypoints. On a river or in
wind, current pushes the boat sideways; a point‑at‑the‑waypoint controller happily follows a
long curved path in from wherever it drifted, and on a survey grid that means the transects
bow and the coverage has gaps.

**Lookahead LOS guidance** (Lekkas & Fossen, 2012) fixes this. Instead of aiming at the
waypoint, the boat aims at a point a fixed *lookahead distance* Δ ahead of its own
projection onto the track line:

```
chi_d = chi_path − atan2(e + k_i·e_int, Δ)
```

- `chi_path` — compass bearing of the leg (previous waypoint → target).
- `e` — signed cross‑track error (**+ starboard / − port** of the track).
- `Δ` — lookahead distance. Small Δ = snap back to the line hard; large Δ = gentle. At
  `e = Δ` the boat aims 45° back toward the line.
- `k_i·e_int` — the optional **integral (ILOS)** term that cancels the *steady* cross‑track
  bias from a constant current/wind.

This drives the boat onto the **track line** and holds it there. It's the guidance law used
across the USV/marine literature (ArduPilot boat frame, MOOS‑IvP, Fossen's textbook) and has
proven stability guarantees (USGES, Fossen & Pettersen 2014).

### In this codebase

- `geo.cross_track_error(from, to, pos)` → `(xte_m, along_m, path_course)`.
- `geo.los_course(from, to, pos, lookahead_m, xte_integral, integral_gain)` → `(course, xte)`.
- `Navigator.compute_throttle(..., from_lat, from_lon)` steers to the LOS course when a leg
  start is supplied; with no leg it falls back to bearing‑to‑target (legacy behaviour, kept
  for single `goto()` and the unit tests).
- `MissionManager` passes the **previous waypoint** as the leg start, so each mission leg
  follows its planned line; the first leg latches the boat's current position.
- The **align‑first** pivot is preserved: forward speed is still gated by heading alignment
  (`align_speed_cut_deg`) so a badly‑misaligned boat rotates in place before driving — LOS
  only changes *what heading it aligns to* (the lookahead course, not the raw target).

### Tuning (`navigation:` in `pi5/config.yaml`)

| Key | Default | Effect |
|---|---|---|
| `los_enabled` | `true` | Master switch. `false` = legacy point‑at‑waypoint. |
| `los_lookahead_m` | `12.0` | Δ. ~3–8 boat lengths. Smaller = tighter tracking but more zig‑zag; larger = smoother but wider corner‑cutting. |
| `los_integral_gain` | `0.0` | ILOS. `0` = pure lookahead (robust, no windup). Set a small value (≈0.02) to cancel a steady river current — **field‑tune it**, too much oscillates. |
| `los_integral_clamp` | `60.0` | Anti‑windup clamp (metre·seconds) on the ILOS integrator. |

The integrator is frozen while the boat is pivoting hard (`|err| ≥ align_speed_cut_deg`) or
avoiding an obstacle, so transients don't wind it up. It resets on every new `goto()`.

> Note: `run_hardware.py` now actually reads the `navigation:` block into `NavConfig`
> (`_nav_config`). Previously the whole block was ignored and the Navigator ran on hard‑coded
> defaults.

---

## Reactive obstacle avoidance

Detection alone doesn't keep a boat off obstacles — something has to *steer*. The vision
pipeline (`pi5/cv/pipeline.py`) now closes that loop: when the primary tracked threat enters
the avoidance envelope it pushes a **steer‑away override** into the navigator, which replaces
waypoint steering until the threat clears.

`pi5/cv/avoidance.py:reactive_avoidance(bearing, distance, cfg)` is a pure, tested rule:

- Beyond `trigger_distance_m` → no override (hold course).
- Inside it → **slow down** (more the closer it is) and **bear away** from the threat's
  bearing. Threat to starboard → bear to port, and vice‑versa.
- A near **head‑on** threat is passed **to starboard** — the COLREGS Rule 14 convention for
  two power‑driven vessels meeting head‑on.
- Near `critical_distance_m` the turn is hard enough to reverse the inner motor, so the
  catamaran can pivot clear from a standstill.

Range prefers **stereo depth**; on a single‑camera rig it falls back to a coarse monocular
bbox‑size proxy so avoidance still functions (less precisely). Bearing comes from the
threat's horizontal position in the forward camera frame (bore = bow assumed).

### Tuning (`vision.reactive_avoidance:` in `pi5/config.yaml`)

| Key | Default | Effect |
|---|---|---|
| `enabled` | `true` | Master switch (also toggleable live: command center **AVOID** button, `POST /vision/avoidance/toggle`). |
| `trigger_distance_m` | `8.0` | Start bearing away at this range. |
| `critical_distance_m` | `3.0` | Full‑authority hard turn at this range. |
| `max_steer` | `65` | Peak differential steer at full severity. |
| `head_on_deg` | `8.0` | `|bearing|` under this counts as head‑on → pass to starboard. |
| `min_forward_frac` | `0.2` | Forward‑throttle floor at full severity — a small floor makes the boat **arc** around a hazard instead of stopping (stopping lets path‑following pull it straight back at the obstacle). `0` = may fully stop. |
| `pass_bearing_deg` | `110.0` | Bug escape: `|bearing|` behind the beam at which a *tracked* hazard counts as passed → release. |
| `pass_hold_s` | `6.0` | Bug escape: when sight of the hazard is lost, keep the committed maneuver this long to carry the boat past before releasing. |
| `cruise_throttle` | = `navigation.cruise_throttle` | Forward throttle at the trigger edge. |

The override is released **once** when the threat clears (set `0,0`), so it never fights the
navigator frame‑by‑frame. The tracker's 3 s lost‑TTL means avoidance persists briefly through
a detection flicker rather than dropping the instant a box disappears — intentional.

### What this is and isn't

This is a light, deterministic layer — the right first line of defence for a slow survey boat.
With the bug‑style commit‑and‑pass controller it reliably **prevents collisions** *and* **routes
past** a blocking obstacle to the waypoint (the memoryless orbit failure is fixed; verified in the
sim for centered and offset hazards). Try it: `run_sim.py` → **DROP OBSTACLE** drops one ~15 m
ahead and you can watch the boat commit to a side, pass it, and re‑join the track.

It is still not a full COLREGS planner or a velocity‑obstacle/DWA optimiser. The bug escape handles
one blocking obstacle at a time along the route; for dense multi‑obstacle fields, give‑way/stand‑on
logic, or optimal detours, the next step is a polar obstacle map (VFH) or a dynamic‑window layer
between the threats and the navigator — the override interface (`Navigator.set_avoidance_override`)
is the seam to plug it into.

Sources: [Lekkas & Fossen, LOS guidance for path following](https://www.semanticscholar.org/paper/a67bf2689fe5e711881bcf8f698a62a2e9690ad1),
[Integral LOS with speed‑dependent lookahead](https://www.sciencedirect.com/science/article/pii/S1474667016312629),
[Unified LOS with integral wind‑up mitigation for USVs](https://www.sciencedirect.com/science/article/abs/pii/S0029801824029536).
