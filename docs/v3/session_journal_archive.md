# D.R.E.A.M.S V3 — Session Journal Archive

Entries moved out of [`session_journal.md`](session_journal.md) once it passes 5, newest first.

---

## 2026-09-26 — V2 hull + arched bridge (Sonobot 5 look), drives, drawings, 3D renders

**Worked on:** sized the V2 catamaran to the Sonobot 5. Rev A used straight crossbeams. Rev B
(current) follows Matthew's steer: an orange gull-wing bridge arching hull to hull, the computer,
radios and batteries in a sealed hub at the crown, and antennas on top. Also picked the props and
motors, and made drawings, a SolidWorks guide and 3D renders.
**Changed (all new, untracked):**
- `mechanical/hull_sizing.py` — hull (R50 chine/deck fillets), hydrostatics, mass budget, arch frames
  (Bezier arch, plate outline), hub cowl + IP67 box fit check, frame/latch load cases.
- `mechanical/propulsion.py` — resistance (ITTC + Michell twin-hull + Holtrop transom), prop trade,
  M200 vs T200.
- `mechanical/drawings.py` -> `mechanical/drawings/DREAMS_V2_drawings.{html,pdf}` (3 sheets) and
  `mechanical/cad/` (guide curves, sweep paths, hub sections, `arch_frame_plate.dxf`).
- `mechanical/concept_model.py` -> `mechanical/render/` (single-file three.js viewer, 6 PNG renders,
  OBJ). three.js r147 vendored in `render/vendor/` (MIT).
- `docs/hull_and_crossbeam_sizing.md`, `docs/solidworks_modeling_guide.md`.
**Result (proposal):**
- Hulls 1300 x 220 x 250 in 5 printed segments; 920 wide, 700 spacing.
- 29.6 kg design, 89 mm draft, ~134 mm with props.
- Two 1/4" 6061-T6 laser-cut arch frames at x 520/780.
- Hub 560 x 400 (z 310-550) centred at x 610, holding a 480 x 300 x 120 IP67 box with 4 M18 packs lying flat.
- Feet latch to printed hull receivers: 6 draw latches, dowels, no tools.
- Drives: 2x M200 + 112 weedless prop, one HD12.0 per VESC at 18 V.
**Decisions / open questions:**
- The drive bus changes from 54 V series to one M18 per VESC. Battery docs and firmware NOT
  updated yet; pending Matthew's approval.
- Batteries in the hub (as asked) vs in the hulls (Sonobot-like, needs hatches).
- Makerspace policy on long PETG/ASA prints; real pod size; a real IP67 box near 480 x 300 x 120.
**Later the same day:** added `mechanical/toroidal_prop.py`.
- Parametric looped-blade prop that bolts onto the M200. The hub is measured from Blue Robotics'
  weedless-prop CAD: cup ID 36.8 over the rotor, 2x M3 on a 19 PCD.
- Outputs: watertight STL, viewer, curves, report. Defaults 3 loops / 110 mm / pitch 75; RH and LH built.
- Also made `mechanical/props/thrust_stand.pdf` (pivot-arm load-cell rig + procedure), plus
  `mechanical/build_all.py` and `mechanical/README.md` (how to use and change the tools).
- Drive train decision (proposal): direct drive, prop on the M200 rotor, no gearbox.
**Next steps:** approve the drive bus; source latches + box; test-print a receiver and a segment
joint; print a toroidal prop on the Form 3L and bench it against the weedless prop; model in
SolidWorks and check 51.6 L / 14.8 L at DWL 89.

## 2026-09-25 — CRWA feedback: focus on the Muddy River

**Worked on:** logged her meeting feedback and researched it; no code changed.
**Feedback:** survey the Muddy River, where flow and water level are poor. Parameters she named: pH,
temperature, dissolved oxygen, turbidity, conductivity, plus nutrient loading into the area (so flow too).
**Findings that affect the design (verified in code):**
- Pod readings are never persisted. `_profile_data` is filled only in SAMPLING
  (`pi5/navigation/mission_manager.py`), `get_profile_data()` has no callers, `logging.data_log` is
  unused, and only the vision pipeline calls `CloudUploader.add_reading`. Descent readings aren't kept at all.
- Shallow soft-bottom hazard: bottom detection needs the switch or a pressure plateau (only past
  0.5 m), and pressure is broken (GP22). In soft mud the winch can keep paying out until
  `max_time_s` (300 s × 0.10 m/s ≈ 30 m).
- The EC probe is pulsed DC (15 ms high), not AC as the deck says. It will interfere with pH/DO probes
  unless isolated or time-multiplexed.
- Pod Pico ADC is full (GP26–28). New sensors need I²C (e.g. Atlas EZO behind isolators) plus an
  external ADC. `POD_DATA` in `docs/serial-protocol.md` lacks the pressure field the firmware already sends.
- `cloud/api/models.py` `SensorReading` is wide, with no unit/QC/sensor-ID columns. The plan is a
  WQX-style export for CRWA.
**Context:** USGS 01104683 (Muddy R. at Brookline) records only gage height and precipitation, no
discharge. There was a May 2026 low-DO fish kill (Leverett Pond → Fens) and an Aug 2025 cyanobacteria advisory in the Fenway.
**Next steps:** wire pod data logging; fix pressure; add tether-out limit per site; decide DO sensor
(optical vs galvanic); send follow-up email to our CRWA contact (data request, reach priority, permissions via MMOC).

## 2026-09-23 — Feedback deck for our CRWA contact; two bugs found along the way

**Worked on:** built a 9-slide feedback-meeting deck for our contact at the Charles River Watershed
Association, meeting Fri 2026-09-25 10:00 in person. No code in the repo was changed.
**Changed:**
- `docs/presentations/DREAMS_CRWA_feedback_2026-09-25_v2.pptx` (new, untracked) — current deck: V1
  origin story with portfolio photos, V2 system + upgrades, mission flow with a command-center
  screenshot of a simulated survey on the Charles lower basin, sensor table, status, CRWA questions.
  `..._2026-09-25.pptx` is the earlier 7-slide draft.
**Decisions / open questions:**
- **Bug: pod pressure sensor can't be read.** `firmware/pod-pico/sensors.py` calls `ADC(22)` (and
  `docs/pin_map.md` lists GP22 as ADC), but RP2040 ADC is only GP26–GP29. The `try/except` swallows
  the error, so `pressure_depth_m` stays 0 and the mission falls back to winch-time depth. Needs a
  pin move (no free ADC pin on the pod — GP26/27/28 are NTC/EC/light) or an external I²C ADC.
- **Map tiles watermarked.** CARTO `dark_all` tiles (`command_center.html`, `waypoint_planner.html`,
  `dashboard/src/components/BoatMap.jsx`) now render "API KEY REQUIRED". The deck screenshot used
  a scratch copy with Esri World Imagery; the repo still points at CARTO.
**Next steps:** fix the two issues above; after the meeting, log her feedback (sensor priorities,
test sites, QA/QC expectations) and decide whether the deck belongs in git.
