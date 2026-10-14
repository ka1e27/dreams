# mechanical/ — D.R.E.A.M.S design tools (rev E)

Small Python scripts that do the boat's engineering maths and produce the drawings, 3D renders and
printable parts. They need only **Python 3.10+** (no packages to install). Microsoft Edge or Chrome
is used, if present, to make the PDFs and PNG renders.

## Quick start

Open a terminal in the repo folder and run:

```
python mechanical/build_all.py
```

That regenerates everything, in about a minute. Then open:

| File | What it is |
|---|---|
| `reports/hull_report.md` | Mass budget, hull particulars, draft/trim/stability, buoyancy, arch-frame and lid-joint checks |
| `reports/propulsion_report.md` | Drag vs speed, prop-diameter trade, belt outdrive vs M200 vs T200 power, cost and endurance |
| `drawings/DREAMS_V2_drawings.pdf` | 7-sheet dimensioned drawing set: sheet 3 has the rib bond and the tub ring frame, sheets 5 and 6 draw the belt outdrive for CAD, sheet 7 explains the hull sections |
| `render/DREAMS_V2_viewer.html` | Spinnable 3D model (double-click; any browser) |
| `render/DREAMS_V2_*.png` | Presentation renders |
| `props/<name>/<name>_viewer.html` | Spinnable toroidal prop, e.g. `toroidal_3loop_p75_RH_shaft` |
| `props/<name>/<name>.stl` | Printable toroidal prop |
| `props/thrust_stand.pdf` | Bench rig for comparing props |

Use `python mechanical/build_all.py --quick` to skip the renders while you're iterating.

## The scripts

| Script | Does | Run alone |
|---|---|---|
| `hull_sizing.py` | The design model: hull shape, hydrostatics, buoyancy, mass budget, bridge and joint loads. **Every other script reads its numbers from here.** `--beam` and `--compare` try other hull widths | `python mechanical/hull_sizing.py` |
| `propulsion.py` | Resistance, prop and drive selection (~25 s). `--beam` for another width, `--selftest` checks the wave-drag maths | `python mechanical/propulsion.py` |
| `drawings.py` | Drawing PDF + SolidWorks curve files (`cad/`) + arch-frame DXF | `python mechanical/drawings.py` |
| `concept_model.py` | 3D viewer, renders and OBJ mesh | `python mechanical/concept_model.py` |
| `toroidal_prop.py` | Parametric toroidal prop (STL, viewer, curves, report) + thrust stand | `python mechanical/toroidal_prop.py --help` |
| `build_all.py` | Runs all of the above in order | |

## Changing the boat

All the design numbers live near the top of **`hull_sizing.py`**, as defaults in these places:

| Where | What's in it | Examples |
|---|---|---|
| `FRAME_X` | The two arch frame stations; the lid ribs sit under them | `(0.335, 0.595)`: move both together to trim the boat |
| `class Hull` | Hull shape and printing | `loa`, `beam`, `depth`, `chine_r`, `taper_start`, `stern_rise`, `ring_x`, `wall_t`, `printer`, `print_margin` |
| `class Lid` (`Hull.lid`) | The removable lid, its rail joint and the bonded ribs | `z` (joint height), `flange_w`, `screw_pitch`, `rib_t`, `rib_bond`, `screw_pullout` |
| `class Boat` | Layout, arch bridge, hub garage, feet and their bolts, what sits inside the hulls | `overall_width`, `frame_x`, `hub_x`, `hub_half`, `winch_env`, `pod_env`, `sampler`, `foot_w`, `foot_bolt_y`, `vesc_x`, `elec_x`, `leak_x` |
| `class Outdrive` (`Boat.drive`) | The fixed belt drive on each lid | `leg_le`, `motor_x`, `cover`, `pad`, `prop_d`, `leg_chord`, `pulley_teeth` |
| `mass_budget()` | Every part's mass and position | the packs and electronics in the hulls, the winch, pod and Van Dorn in the hub |
| `class Loads` | Load factors and safety-factor target | `afloat_g`, `lift_one_hull_g`, `sf_target` |

**Units are metres and kilograms** in `hull_sizing.py` (0.22 = 220 mm). The drawings and CAD files
come out in millimetres.

### Worked example: narrower hulls

1. Compare first, without changing anything:
   `python mechanical/hull_sizing.py --compare 0.22 0.19 0.1524` (0.1524 m = 6 in). It prints
   buoyancy, draft, freeboard to the lid joint, stability, shell mass and whether the bridge feet
   still fit, one column per width. The bridge and hull spacing stay the same. Add the drag with
   `python mechanical/propulsion.py --beam 0.1524`.
2. To make a width the design, change `beam` in `class Hull` and `overall_width` in `class Boat`
   together, keeping the hull spacing: `overall_width = 0.70 + beam`.
3. Run `python mechanical/build_all.py` and read `reports/hull_report.md`:
   - The *Print* line tells you whether the tub and the lid still fit the Giga, printed on end.
   - *Foot on the lid deck* tells you how deep the flat landing under each foot has to be.
   - *Draft*, *Trim* and *To lid joint* show how the boat sits.
   - Every SF in the frame and joint tables must stay ≥ 3.
4. Check the regenerated PDF and viewer.

### What to watch after any change

- **Trim** (hydrostatics table): aim for within ±10 mm. Fix it by moving `FRAME_X` and `hub_x`
  (and the winch envelope) together, or the packs (they sit between the frames).
- **Freeboard to the lid joint:** keep it above ~60 mm at the design load (buoyancy table).
- **Garage fit** (arched-bridge table): the pod + sampler margins and the winch margin must be positive.
- **Outdrive gaps** (the report's last line): the leg and the mount must clear the rail (no CLASH).
- **Frame SF ≥ 3 and joint SFs ≥ 3** (foot bolts, lid rib, rail screws).
- **Print fit** (hull particulars): the tub and the lid each print in one piece, standing on the stern.
  Their height is the shell's length plus the rail flanges that lap past the transom and the stem
  (15 mm each end on the tub, 17.5 on the lid), and it must stay 25 mm under the Giga's 1000 mm
  (`Hull.print_margin`). That's why the shell is 940: the boat is 975 over the rails.
- When you add a real part, put its measured mass and position in `mass_budget()`.

## Toroidal props

```
python mechanical/toroidal_prop.py --list                     # every parameter and its default
python mechanical/toroidal_prop.py                            # default: 3 loops, 110 mm, pitch 75, RH, shaft hub
python mechanical/toroidal_prop.py --hand LH                  # the other hull's prop
python mechanical/toroidal_prop.py --hub m200                 # to fit a Blue Robotics M200 instead
python mechanical/toroidal_prop.py --loops 2 --pitch 70 --chord-root 24 --chord-tip 17 --loop-dtheta 70
```

- Each run makes a folder in `props/` (named like `toroidal_3loop_p75_RH_shaft`) with the STL, a
  viewer, two renders, `report.md` (mass, leg/loop gaps, design rpm) and `curves/` (loop centreline +
  sections, for rebuilding it in SolidWorks). M200-hub props also get a spinner-cap STL.
- **Shaft hub (default):** 20 mm OD with a D-bore for the outdrive's 5 mm stainless shaft (4.5 mm
  across the flat), held on by an M5 nylock.
- **M200 hub:** copies Blue Robotics' weedless-prop interface, measured from their CAD: a cup that
  slides over the rotor and 2× M3 on a 19 mm circle through a 4 mm floor.
- **Printing:** on the EXP Formlabs Form 3L, use a tough resin (Tough 2000, or Durable for impacts).
  Stand it on the hub's front face with supports only on the hub, keeping them off the blade faces.
  Then wash, cure, check the bore on a shaft offcut and balance it.
- **Testing:** build the rig in `props/thrust_stand.pdf`. Log thrust and power against a plain
  110 mm RC prop on the same drive, then compare at ~5, 10 and 25 N per drive.
- **Tuning knobs:**
  - `pitch` sets rpm per speed.
  - `loop_dtheta` sets the petal width.
  - `loop_dz` sets the tip-bridge length.
  - `skew` sweeps the loops back, which helps shed weed.
  - `chord_root` / `chord_tip` set blade area.
  - Keep both gaps in `report.md` above ~2 mm.

## Where the reasoning lives

- `docs/hull_and_crossbeam_sizing.md` — the design record: why each number is what it is
- `docs/solidworks_modeling_guide.md` — how to model the boat in SolidWorks from these files
- `docs/hull_printing_and_sealing.md` — read before printing a hull: watertight slicer settings, the
  sealing options and the leak tests
