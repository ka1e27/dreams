# GPS-anchored object memory

The boat remembers **where things are on the water**. When the vision pipeline
confirms a buoy (or dock, rock, person, …), it works out that object's real
GPS coordinate and drops a marker on the map. From then on it doesn't need to
keep staring at it — it can scan for the unknown and just re-verify the known
object's position whenever it happens to see it again.

This is separate from, and complementary to, the two existing perception layers:

| Layer | Question it answers | Lives in |
|-------|---------------------|----------|
| `ThreatAssessor` | "what's in frame right now, is it approaching, do I steer away?" | `pi5/cv/threat_assessor.py` |
| **`ObjectMemory`** | **"what stationary things are out here and exactly where?"** | `pi5/cv/object_memory.py` |
| `reactive_avoidance` | "how do I not hit the nearest one?" | `pi5/cv/avoidance.py` |

Threat tracking is *pixel*-based (a bbox centroid, frame to frame). Object memory
is *world*-based (a lat/lon), so an object keeps its identity when the camera
looks away and comes back.

## How a detection becomes a marker

```
detection (class, bbox, stereo range)
        │
        ▼   bearing off the bow  = (bbox_cx − frame_cx)/frame_cx · (FOV/2)     [+starboard]
            true bearing         = boat_heading + bearing_off_bow
            object position      = geo.destination_point(boat_fix, true_bearing, range)
        │
        ▼
   ObjectMemory.observe(...)
        │
        ├─ matches an existing object of the same class within a range-scaled
        │  spatial gate?  → fold the fix in (inverse-distance²-weighted mean, so
        │                    closer/steadier looks pull the estimate in) + ++sightings
        └─ matches nothing? → start a new *candidate* (not on the map yet)
        │
        ▼
   sightings ≥ confirm_sightings  →  CONFIRMED  →  marker drops on the map
```

Because identity is the world coordinate, the boat can look away, scan elsewhere,
and re-acquire the same object later — the new fix lands near the stored mean and
folds straight back in, refining it rather than planting a duplicate. That's the
"drop the marker once you've confirmed it, then just verify the coordinate each
time you see it again" behaviour.

> ### ⚠ Corrected 2026-07-30 — the cameras ride ON the radar bar
>
> This section used to read: *"The cameras are **fixed forward**; the A4988 stepper
> drives a separate radar bar, so the object's bearing off the bow is purely
> `heading + pixel offset` — the radar-pan angle is **not** part of it."*
>
> **That is wrong, and it was wrong in a way that mattered.** The builder confirmed the
> cameras pan with the bar. A bbox offset is therefore relative to the **bar**, not the
> bow, and the true bearing is:
>
> ```
> true bearing = heading + bar angle + pixel offset
> ```
>
> The stereo pair still moves rigidly *together* (the calibration is unaffected — both
> eyes ride the same bar), so distance is unchanged. But the missing `bar angle` term
> put every marker out by however far the bar was panned: a buoy seen with the bar at
> 90° was charted 90° off the boat, and the same bearing feeds **avoidance steering**,
> so the boat would have dodged the wrong way. Fixed in
> `pipeline._avoidance_bearing`, gated on `stepper.cameras_on_bar` (set it false for a
> hull-mounted camera, where the boresight *is* the bow).

## Permanent vs transient — what's kept, what's forgotten

Class → category is defined in `object_memory.py`:

* **PERMANENT** — `buoy`, `dock`, `bridge`, `rock`, `wreck`, `pier`, `piling`,
  `marker`, `beacon`. Stationary navigation marks; kept for the whole session
  (unless `permanent_ttl_s` is set).
* **TRANSIENT** — `person`, `surfer`/`swimmer`, `kayak`, `boat`/`vessel`,
  `sailboat`, `debris`, `jetski`, `raft`, `canoe`, `paddleboard`. Movers/drifters;
  **forgotten `transient_ttl_s` after they were last seen** (a swimmer who has
  left shouldn't haunt the chart).
* Anything else (e.g. `water_anomaly`) is **not remembered** — it isn't a
  placeable object.

Unconfirmed *candidates* age out fast (`candidate_ttl_s`) so a single false box
never leaves anything behind.

## "Keep scanning even with things nearby"

Once a landmark is confirmed on the map, the pipeline stops locking the radar bar
onto it (`release_radar_on_known`), so the bar keeps sweeping for the unknown.
Safety carve-out: a **CRITICAL** threat (a vessel or a person) is *always*
tracked, and **reactive avoidance runs off the primary threat regardless of the
radar** — releasing the bar never disables collision avoidance. A transient
object that has drifted away from its charted spot no longer matches it, so it's
treated as unknown and tracked again.

## Where it shows up

* **Command center** (`/`, `pi5/server/templates/command_center.html`): a marker
  layer polling `GET /api/map/objects` every 2 s — cyan = permanent, amber =
  transient, with a hover label and a click-through detail popup.
* **React dashboard** (`dashboard/`): same layer via `useMapObjects`.
* **API**:
  * `GET  /api/map/objects` → `{available, objects:[…]}` (confirmed markers only).
  * `POST /api/map/objects/clear` → forget everything (operator reset).
* **Vision state**: `vision_state()["object_memory"]` carries
  `{total, confirmed, permanent, transient}` counts.

## Simulator

There's no camera in the sim, so `SimObjectMapper`
(`pi5/navigation/sim_obstacles.py`) plays the sensor's part from ground truth —
exactly as `SimAvoider` does for avoidance. It "sees" obstacles in a forward
cone, adds a little range/bearing noise, and feeds the **same** `ObjectMemory`.
Drop a `buoy` or a `person` from the command center's **SIM MAP** buttons (or
`POST /api/sim/obstacles {label, ahead_m}`) and watch it confirm onto the map.
A generic `obstacle` (the DROP OBSTACLE button, for avoidance) isn't a mapped
class, so it stays off the object layer.

## Configuration (`pi5/config.yaml` → `vision.object_memory`)

| Key | Default | Meaning |
|-----|---------|---------|
| `enabled` | `true` | master switch |
| `confirm_sightings` | `3` | agreeing looks before a marker drops |
| `match_radius_m` | `6.0` | base "same object" spatial gate (m) |
| `match_radius_frac` | `0.08` | + this × range (far fixes are noisier) |
| `match_radius_max_m` | `25.0` | cap on the gate |
| `transient_ttl_s` | `45.0` | forget a confirmed mover this long after last seen |
| `candidate_ttl_s` | `12.0` | drop an unconfirmed candidate this fast |
| `permanent_ttl_s` | `0.0` | 0 = keep permanent marks all session |
| `max_range_m` | `60.0` | ignore detections ranged beyond this |
| `min_confidence` | `0.30` | ignore detections below this confidence |
| `max_objects` | `200` | memory cap (drops least-valuable first) |
| `release_radar_on_known` | `true` | don't re-lock the bar on charted landmarks |

Object memory needs a **stereo range** to place a detection, so it's a no-op on a
mono rig (detections with no distance are ignored).

## Tests

* `pi5/tests/test_geo.py::TestDestinationPoint` — the forward geodesic.
* `pi5/tests/test_object_memory.py` — geolocation, confirmation, refine-not-
  duplicate, convergence to truth, permanent/transient/candidate expiry, gating,
  queries.
* `pi5/tests/test_vision_pipeline.py` — confirm→map, no-marker-before-confirm,
  transient expiry, dock-mapped-not-anomaly, radar-release-on-known through the
  real pipeline.
* `pi5/tests/test_sim_object_mapper.py` — the sim ground-truth feeder.
