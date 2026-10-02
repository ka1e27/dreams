# D.R.E.A.M.S V2 — SolidWorks Modeling Guide

A step-by-step path from the drawings to a printable SolidWorks model of the V2 hulls (tub + lid),
arched bridge, joints and belt outdrives (rev C). Work with these open:

- `mechanical/drawings/DREAMS_V2_drawings.pdf`: sheet 1 is the general arrangement, sheet 2 the hull
  lines, offsets and fillets, sheet 3 the bridge, foot and lid-rib details, sheet 4 the lid (rail)
  joint and the belt outdrive, sheet 5 each hull section drawn on its own.
- `mechanical/render/DREAMS_V2_viewer.html`: the 3D concept, to spin around while you model.
- `mechanical/cad/`: guide curves, sweep paths, hub sections, and the arch-frame DXF.
- `docs/hull_and_crossbeam_sizing.md`: the reasoning behind every number.

If a number changes, change it in `mechanical/hull_sizing.py`, then re-run `python mechanical/build_all.py`.
Drawings, curve files and renders regenerate to match.

---

## 0. Set up once

**Units.** Tools > Options > Document Properties > Units > **MMGS**. Every file in `cad/` is in mm.

**Axes.** Use the drawings' origin and axes, so the curve files land in the right place:

| SolidWorks | Boat | Plane that holds the view |
|---|---|---|
| **X** | forward from the transom | Right plane (YZ) = a station/section |
| **Y** | up from the baseline (lowest point of the keel) | Front plane (XY) = the profile |
| **Z** | to starboard | Top plane (XZ) = the plan |

In the hull part, the origin is on the hull centreline. In the assembly (and the bridge files), it's on
the boat centreline, with the hulls at Z = ±350.

**Global variables.** Tools > Equations, then add the following. Type `=` in a dimension box to link to one.

```
"LOA" = 1300   "B" = 220   "D" = 250   "DEADRISE" = 12   "SEG" = "LOA"/5
"T_WALL" = 2.0 "T_BH" = 2.4 "LAP" = 8  "R_CHINE" = 50    "R_DECK" = 50
"Y_JOINT" = 190  "RAIL" = 15  "T_FLANGE" = 5  "T_LIP" = 2.5  "LIP_DROP" = 8  "T_RIB" = 8
"FRAME_X1" = 520  "FRAME_X2" = 780  "HUB_X" = 610  "SPAN" = 700
```

**Material.** Make custom materials for PETG (1.27 g/cm³) and ASA (1.07 g/cm³), so Mass Properties
can be checked against the budget.

---

## Part A — Hull (`DREAMS_hull.SLDPRT`; both hulls are this part, multi-body)

### A1. Guide curves

**Insert > Curve > Curve Through XYZ Points > Browse**. Set the file type to `*.txt` and load each file:

- `keel_centreline.txt`: (0, 40, 0) → (1300, 100, 0)
- `chine_stbd.txt`: (0, 63.4, 110) → (1300, 101.1, 5). This is the **sharp** chine; the fillets
  come later.
- `deck_edge_stbd.txt`: (0, 250, 110) → (1300, 250, 5)
- `deck_centreline.txt`: a straight line at Y = 250

Check the end points with the Measure tool. If a curve comes in 25.4× off, the part was in inches when
you imported it. Turn on curvature combs: they should be smooth. There's one intended small kink in the
keel at x = 520, where the straight keel rise meets the flat keel.

### A2. Stations and half-sections

1. Make planes parallel to the Right plane at X = **0, 260, 520, 650, 780, 910, 1040, 1170, 1250,
   1300**. The segment joints (260, 520, 780, 1040) are among them.
2. On each plane, sketch the starboard half-section as a **closed 4-line polygon**:
   keel → chine → deck edge → deck centre → back down the centreline.
3. Don't dimension it. Give each vertex a **Pierce** relation to its guide curve. The sketch goes
   black when it's fully defined.
4. Every section has the same 4 segments, in the same order. That's what stops the loft twisting.
5. **Sheet 5** draws what each finished (filleted) section should look like, one box per station, with
   its width, keel height and radii. Use it to check each sketch before you loft.

### A3. Loft, mirror, fillet, verify

1. **Lofted Boss/Base** through STA 0000 … STA 1300 with all four curves as guide curves. Turn
   **Merge tangent faces off**. If the preview twists, drag the connectors onto matching corners. If it
   still won't go, use **Boundary Boss/Base** (Direction 1 = sections, Direction 2 = curves).
2. **Mirror** about the Front plane, with Merge solids on.
3. **Variable-radius fillets** on the two chine edges and the two deck edges. Use R50 over most of the
   length, shrinking to 0.45 × half-breadth near the stem. The control points are in the fillet table on
   sheet 2: R50 (49.5) through the midbody to x = 650, then 47 at 780, 40 at 910, 33 at 1000, 24 at
   1100, 16 at 1170, 7 at 1250, 2 at 1300.
   Put the fillets in before splitting and shelling.
4. **Check the volume:** Mass Properties should show about **51.6 L**. Split at **Y = 94** (the DWL)
   and the lower body should be about **16.0 L**, with its centre of mass near **X = 582**. Suppress
   the split afterwards.
5. **Save this solid as a body you keep** (right-click the body > Insert into New Part, or just
   leave a copy suppressed). The bridge's lid-rib cut-outs and the foot pad fit are made against it.

### A4. Split into tub and lid

1. Make a plane parallel to the Top plane at **Y = 190** (`"Y_JOINT"`): the joint plane.
2. **Insert > Features > Split** with that plane. Name the bodies **TUB** (below) and **LID** (above).
3. **Shell** each at 2.0 mm, removing the face on the joint plane (the tub is open at the top, the lid
   at the bottom). Use multi-thickness to make the transom 4.0 mm.
4. **Rail flanges.** Sketch on the joint plane: Convert Entities on the outer edge of the tub's rim,
   then Offset it **15 mm outward**.
   - Tub flange: Extrude 5 mm **down** (Y 185–190), scoped to TUB.
   - Lid flange: Extrude 5 mm **up** (Y 190–195), scoped to LID.
   - Drip lip: on the lid flange's outer edge, a 2.5 mm wall extruded down to **Y 182**.
5. **Gasket groove:** in the tub flange's top face, 5 mm wide × 2.2 mm deep, from 1.5 to 6.5 mm off
   the hull side (Offset Entities twice, Extruded Cut 2.2 mm).
6. **Locating spigot:** under the lid, a 2 mm wall 6 mm deep, 0.3 mm inside the tub's inner face.
   **Insert > Fastening Feature > Lip/Groove** does steps 4–6's spigot and groove in one go if you
   prefer: pick TUB as the groove body and LID as the lip body.
7. **Screw holes:** a sketch on the joint plane with points on a curve offset **10.5 mm** outside the
   hull side. Space them 100 mm apart, and 60 mm within 150 mm of x = 520 and x = 780: 37 holes.
   Use **Hole Wizard** twice:
   - through the lid flange, M4 clearance (Ø4.5)
   - into the tub flange, M4 heat-set insert hole (check the insert maker's size, ~Ø5.6 × 8.5 deep).
   Add a **Mounting Boss** (Insert > Fastening Feature) Ø10 under the tub flange at every hole, so the
   8.1 mm insert has material.

### A5. Tub bulkheads, lid ribs and bosses

- **Tub bulkheads** at X = 260 / 520 / 780 / 1040: 2.4 mm walls following the tub's inside, stopping
  **5 mm under the joint plane** (one gasket loop, one sealed space per hull).
- **Lid ribs** at X = 520 and 780: 8 mm walls filling the lid's section (these are the base walls of
  lid segments 3 and 4, so put them on the forward side of each plane).
- **Rib bosses:** 4 per rib, **Ø20, full depth** (deck to joint plane), at Z = ±40 and ±62 from the
  hull centreline, 10 mm forward of each frame plane (X = 530 and 790). Through-hole Ø6.6, with a
  **Ø13 × 8 mm counterbore** at the bottom for the head of each M6 × 60 bolt and its bonded-seal
  washer. The counterbores mean the rib itself is never notched.
- **Outdrive bracket holes:** 4× Ø5.5 through the lid's aft deck at X = 15 / 70, Z = ±25, with a 3 mm
  aluminium backing plate inside.
- **Vent:** M12 membrane vent through the lid deck at X = 900.
- **Leak sensor:** a small pad at the lowest point of each tub, on the flat keel between X = 520 and 780.

### A6. Ten print segments

1. **Split** TUB and LID at X = 260 / 520 / 780 / 1040. Name them TUB1–5 and LID1–5 (1 = transom end).
2. **Spigot joints:** on the aft face of segments 2–5, Offset Entities 2.2 mm inward and extrude 8 mm
   aft, scoped to that body only (same detail on tubs and lids, sheet 3).
3. **Printable internal features.** Each segment prints standing on its aft end, so the hull's X axis
   is vertical in print:

| Feature | How | Why it prints |
|---|---|---|
| Stringers, 3 × 12 mm | Extrude fore-aft, stopping 1 mm short of the joints | Vertical in print |
| Ring frame at mid-segment | Offset ring 8 × 2 mm, then chamfer its underside 45° | Horizontal features need a 45° underside |
| Lid ribs and bosses | Base walls of LID3 and LID4 | They're the bed face; the bosses grow up from it |
| Flanges, lip, spigot | Part of every section | Vertical in print, no supports |

**No hole goes through the tub below the rail.** Everything that bolts on goes through the lid, from
inside.

---

## Part B — Bridge (an assembly of its own: `DREAMS_bridge.SLDASM`)

### B1. Arch frame plates (×2)

- **File > Open** `mechanical/cad/arch_frame_plate.dxf`, import it as a sketch in mm, and extrude it
  **6.35 mm**. The DXF is also the file to send to a laser or waterjet service.
- Coordinates in the DXF: X = across the boat, Y = height above the baseline. So the sketch goes on
  a plane parallel to the Right plane.
- **In the bridge assembly:** place one frame at X = 520 and one at X = 780.
- **To draw it yourself instead:** sketch the arch centreline from the Bezier table on sheet 3
  (a straight span at y ±170 / z 345, then a spline P0 → P3), offset it ±25 mm, close the ends
  horizontally at z 257.5, and add the holes.

### B2. Arm fairings (×2, printed)

- **Path:** Curve Through XYZ Points with `arm_fairing_path_stbd.txt`. It runs at X = 650, from inside
  the hub to the foot.
- **Profile:** a rounded rectangle 300 mm (X) × 64 mm, on a plane normal to the path at its start.
- **Features > Swept Boss/Base.** Then flare the root: add a second, 360 × 154 mm profile inside the
  hub, and **Loft** the root with the path as a guide. Or use **Boundary Boss** between the swept end
  and a sketch on the hub's side. Shell it at 2 mm; it's a hollow cable duct.
- **Split for printing:** cut it into ≤ 330 × 240 × 300 pieces (Split with planes), and add 10 mm lap
  tabs at the cuts. Clip it to the frames with printed brackets.

### B3. Hub cowl (printed)

- **Sections:** Curve Through XYZ Points with each `hub_section_z*.txt` (z 310, 370, 440, 495, 540).
  Each is a closed superellipse.
- **Lofted Boss** bottom → top through them, with a flat cap at z 310 and a small dome cap (z 550).
- **Shell** at 2.5 mm, removing the bottom face.
- **Service lid:** split off the top above z 470 along a flange (Split + Thicken 6 mm), so you can
  reach the IP67 box.
- **Openings:** cut the bottom for the frames and the tether (30 mm hole at X 610, Z 0).
- **Printing:** it's larger than the S5 bed, so split it into quadrants with 10 mm lap tabs and bond
  them. The cowl only has to be splash-proof; the IP67 box does the sealing.

### B4. Foot plates (×2) and hardware

- 300 × 140 × 6 mm 6061 (sheet 3), centred at X = 650.
- **8 tapped M6 holes** at X = 530 and 790 (10 mm forward of each frame), Z = ±40 and ±62 from the hull
  centreline. The bolts come up from inside the lid; they must not stand proud of the foot's top face.
- Angle brackets (25 × 25 × 3) join the frames to the foot plate, on the inboard side of each frame.
- A 1.5 mm EPDM pad the size of the foot, with the 8 holes, goes under it.
- Download fastener models from the supplier (McMaster); don't model bolts yourself.

### B5. IP67 box and contents

Model the box as an envelope, 480 × 300 × 120 on the frame tops (z 370). Place these inside it:

- the four M18 packs lying flat, 2 × 2 at the aft end
- the VESCs and electronics at the forward end
- the winch below the box floor, between the frames

Check with Interference Detection.

---

## Part E — Belt outdrive (`DREAMS_outdrive.SLDASM`, one per hull)

All numbers are on sheet 4. The motor axis and prop shaft both run fore-aft, so the belt runs in a
transverse plane (X = −55) down the inside of the leg.

| Part | How to model it |
|---|---|
| Bracket (printed ASA) | A block on the lid's aft deck, X −40 → 85, 70 wide, with 4 M5 inserts in its base. The tilt pin hole (Ø6.2) runs across it at X −30, Y 262 |
| Tilt head + motor plate | Rotates on the pin. Carries the motor on **slotted** holes (that's the belt tensioner) and the spring-plunger dimple |
| Motor | Download the outrunner's STEP. Axis along X at Y 300, the shaft pointing aft to the upper pulley at X −55 |
| Motor cover (printed) | 80 × 70 × 73 shell over the motor and upper pulley; leave a drain slot at the bottom |
| Leg (printed, two halves) | Sketch an 80 mm chord, 28 mm thick symmetric foil (NACA 0035 is close) starting at X −28, and Extrude it from the pod up to the tilt head. **Split** it on the centre plane (Z = 0 of the drive) into two halves with a channel for the two belt runs (PD 19.1 apart, 9 mm belt, 2 mm clearance) |
| Lower pod (printed) | Revolve: Ø32, nose at X −22, tail at X −114 (6 mm past the leg), on the prop axis (Y 17). Bearing seats for 2× 625-2RS (Ø16 × 5) either side of the lower pulley |
| Shaft | Ø5 316 stainless, D-flat 0.5 mm deep at the prop end, M5 thread for the nylock |
| Pulleys, belt | Download HTD 3M 20T 9 mm pulley models; belt 209 teeth (627 mm) |
| Prop | Import `mechanical/props/toroidal_3loop_p75_RH_shaft/*.stl` (starboard) and `_LH_shaft` (port) as a reference body, or rebuild it from that folder's `curves/` |

Check the tilt: rotate the head 70° about the pin with a Hinge mate and make sure nothing hits the lid
or the rail.

---

## Part C — Top-level assembly

Start with a **layout sketch** on the assembly Top plane:

- hull centrelines at Z = ±350
- frame stations at X = 520 / 780
- the hub centre at X = 610

Mate everything to this sketch.

| Item | Position (mm) |
|---|---|
| Tubs + lids | origin at X 0, Y 0, Z ±350; joint plane Y 190 |
| Foot pads + foot plates | on the lid deck (Y 250), pad 250 → 251.5, plate 251.5 → 257.5, centred X 650, Z ±350 |
| Arch frames | planes X 520 and X 780; feet at Z ±350, Y 257.5 |
| Hub cowl | centred X 610, Z 0, bottom Y 310, top Y 550 |
| Mast / GNSS | X 610, Z 0, top Y 820; whips at Z ±120 |
| Stereo bar | front of the dome, X ≈ 830, Y ≈ 530, lenses at Z ±160 |
| Outdrives | bracket on the lid aft deck (X −40 → 85), pin X −30 / Y 262, motor axis Y 300, prop axis Y 17, prop hub X −116 → −159, Z ±350 |
| Pod (stowed) | X 610, Z 0, Y 130 → 290 |

**Checks:**

- Interference Detection.
- Mass Properties: with the batteries as envelopes, the CG should land near X 583 / Y 284.
- A section view on the Right plane at X 530, to see the bolts, bosses, rib and rail line up.

---

## Part D — Export and print (Ultimaker S5, EXP)

- **STL export:** Save Bodies (or each part) → STL, Custom resolution, 0.01 mm deviation, 5°.
- **Tub segments:** aft bulkhead down; 255 × 190 section, 260 tall. **Lid segments:** aft end down;
  255 × 68 section, 260 tall. PETG, 5 walls, 0.2–0.3 mm layers, 5 mm brim, no supports. Check the
  makerspace's policy on long prints and on PETG/ASA first.
- **After printing:**
  1. Bond the spigots with thickened epoxy and glass the tub and the lid separately (200 g/m²), up to
     the flanges.
  2. Press the heat-set inserts into the tub flange and fit the cord.
  3. **Leak test:** screw a lid down and pressurise the hull to a few kPa through the vent port. Brush
     soapy water along the rail and the bolt holes and look for bubbles.

---

## Common problems

| Symptom | Likely cause | Fix |
|---|---|---|
| Loft twists | Sections with different segment counts, or bad connectors | 4 lines in every section; realign the connectors |
| Variable fillet fails near the bow | Radius bigger than the local half-breadth | Use the sheet-2 radius table; stop the fillet at x ≈ 1290 |
| Shell fails | A face radius smaller than the wall thickness | Shell each body separately; Offset Surface + Thicken for the bow segments |
| Rail offset fails at the stem | The 15 mm offset folds back on the 10 mm stem flat | Offset the plan outline as a sketch, fillet the offset R15 at the stem, then extrude |
| Lip/Groove won't build | Faces picked on the wrong body | Pick the tub rim for the groove and the lid rim for the lip; scope each to its body |
| Hub loft wavy | Section curves with different point starts | All `hub_section` files start at +X; keep "Merge tangent faces" on for the cowl |
| DXF comes in the wrong size | Import units | Set units = millimetres in the DXF import dialog |
| Volume far off 51.6 L | Loft bulging between stations | Add stations (390, 1100, 1200) |
