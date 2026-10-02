# D.R.E.A.M.S — SolidWorks Modeling Guide (rev D)

A step-by-step path from the drawings to a printable SolidWorks model of the hulls (tub + lid),
arched bridge with its hub garage, joints and belt outdrives (rev D). Work with these open:

- `mechanical/drawings/DREAMS_V2_drawings.pdf`:
  - sheet 1: general arrangement
  - sheet 2: hull lines, offsets and fillets
  - sheet 3: bridge, foot, lid-rib details and the hub garage
  - sheet 4: lid (rail) joint and what goes inside each hull
  - sheets 5 and 6: the belt outdrive, assembled and part by part
  - sheet 7: each hull section drawn on its own
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
"LOA" = 1300   "B" = 220   "D" = 250   "DEADRISE" = 12   "J1" = 520   "J2" = 780
"T_WALL" = 2.4 "T_BH" = 2.4 "LAP" = 8  "R_CHINE" = 50    "R_DECK" = 50
"Y_JOINT" = 190  "RAIL" = 15  "T_FLANGE" = 5  "T_LIP" = 2.5  "LIP_DROP" = 8  "T_RIB" = 8
"FRAME_X1" = 520  "FRAME_X2" = 780  "HUB_X" = 610  "SPAN" = 700
```

**Material.** Make custom materials for PLA (1.24 g/cm³: hulls, cowl, fairings) and ABS (1.04 g/cm³:
the outdrive parts), so Mass Properties can be checked against the budget.

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
   1300**. The segment joints (520, 780) are among them.
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
4. **Check the volume:** Mass Properties should show about **51.6 L**. Split at **Y = 99** (the DWL)
   and the lower body should be about **17.2 L**, with its centre of mass near **X = 580**. Suppress
   the split afterwards.
5. **Save this solid as a body you keep** (right-click the body > Insert into New Part, or just
   leave a copy suppressed). The bridge's lid-rib cut-outs and the foot pad fit are made against it.

### A4. Split into tub and lid

1. Make a plane parallel to the Top plane at **Y = 190** (`"Y_JOINT"`): the joint plane.
2. **Insert > Features > Split** with that plane. Name the bodies **TUB** (below) and **LID** (above).
3. **Shell** each at 2.4 mm, removing the face on the joint plane (the tub is open at the top, the lid
   at the bottom). Use multi-thickness to make the transom 4.0 mm. If the shell fails near the stem,
   keep the nose solid: the slicer prints it at whatever infill you set (~20 % keeps it light).
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

- **Tub bulkheads** at X = 520 / 780 (the segment joints): 2.4 mm walls following the tub's inside,
  stopping **5 mm under the joint plane** (one gasket loop, one sealed space per hull), with a ~10 mm
  limber hole at the foot of each so a leak runs to the probe.
- **Lid ribs** at X = 520 and 780: 8 mm walls filling the lid's section (these are the base walls of
  lid segments 2 and 3, so put them on the forward side of each plane).
- **Rib bosses:** 4 per rib, **Ø20, full depth** (deck to joint plane), at Z = ±40 and ±62 from the
  hull centreline, 10 mm forward of each frame plane (X = 530 and 790). Through-hole Ø6.6, with a
  **Ø13 × 8 mm counterbore** at the bottom for the head of each M6 × 60 bolt and its bonded-seal
  washer. The counterbores mean the rib itself is never notched.
- **Outdrive bracket holes:** 4× Ø5.5 through the lid's aft deck at X = 15 / 70, Z = ±30, with a 3 mm
  aluminium backing plate inside.
- **Outdrive wall bolts:** 2× Ø5.5 through the lid's aft wall at Y 225, Z ±28, with a backing plate
  inside: they hold the mount's flange that runs down the wall.
- **Thrust pad seat:** a flat 30 × 40 on the tub's transom at Y 120–160, Z 0, where the outdrive's thrust
  pad is bonded (no hole).
- **Lid connectors:** holes for IP68 bulkhead connectors at X = 100 (motor wires) and X = 810 (bridge
  cables, inside the foot shoe), Z = 0.
- **Vent:** M12 membrane vent through the lid deck at X = 900.
- **Leak probe:** a small pad at the keel's low point, X = 850, forward of the packs.
- **Inside (sheet 4):** a 6061 heat plate bedded on the bottom of the middle segment of each tub; the
  packs sit on it. The VESC sits by the outdrive at X = 200, and the carrier + Pi in the stbd tub at X = 330.

### A6. Six print segments

1. **Split** TUB and LID at X = 520 / 780. Name them TUB1–3 and LID1–3 (1 = transom end; 520, 260 and
   520 long).
2. **Spigot joints:** on the aft face of segments 2 and 3, Offset Entities 2.2 mm inward and extrude
   8 mm aft, scoped to that body only (same detail on tubs and lids, sheet 3).
3. **Printable internal features.** Each segment prints standing on its aft end, so the hull's X axis
   is vertical in print:

| Feature | How | Why it prints |
|---|---|---|
| Stringers, 3 × 12 mm | Extrude fore-aft, stopping 1 mm short of the joints | Vertical in print |
| Ring frame at mid-segment | Offset ring 8 × 2 mm, then chamfer its underside 45° | Horizontal features need a 45° underside |
| Lid ribs and bosses | Base walls of LID2 and LID3 | They're the bed face; the bosses grow up from it |
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
- **Printing:** it fits the Giga whole; print in PLA and paint it light. Clip it to the frames with
  printed brackets.

### B3. Hub cowl (printed)

- **Sections:** Curve Through XYZ Points with each `hub_section_z*.txt` (z 310, 370, 440, 495, 540).
  Each is a closed superellipse.
- **Lofted Boss** bottom → top through them, with a flat cap at z 310 and a small dome cap (z 550).
- **Shell** at 2.5 mm, removing the bottom face.
- **Service lid:** split off the top above z 470 along a flange (Split + Thicken 6 mm), so you can
  reach the winch.
- **Openings:** cut the bottom for the frames, and the **garage opening** between them: 240 × 301,
  centred at X 650, Z 0 (sheet 3).
- **Printing:** it fits the Giga in one piece (560 × 400 × 240). PLA, painted light. It only has to be
  splash-proof: the electronics are in the hulls now.

### B4. Foot plates (×2) and hardware

- 300 × 140 × 6 mm 6061 (sheet 3), centred at X = 650.
- **8 tapped M6 holes** at X = 530 and 790 (10 mm forward of each frame), Z = ±40 and ±62 from the hull
  centreline. The bolts come up from inside the lid; they must not stand proud of the foot's top face.
- Angle brackets (25 × 25 × 3) join the frames to the foot plate, on the inboard side of each frame.
- A 1.5 mm EPDM pad the size of the foot, with the 8 holes, goes under it.
- Download fastener models from the supplier (McMaster); don't model bolts yourself.

### B5. Hub garage (sheet 3)

Model these as envelopes until they're designed:

- **Winch:** X 360–500, Z ±80, Y 372–470, on a bracket off the aft frame.
- **Sheave:** Ø50 at X 650, Y 500, on the garage holes in the frames.
- **Pod:** 110 × 80 × 160, port of centre.
- **Van Dorn:** Ø141 × 210, lying fore-aft to starboard of the pod.
- The pod and the Van Dorn hang side by side under the sheave, stowed at Y 285–445.

Check with Interference Detection that both pass the 240 × 301 opening.

---

## Part E — Belt outdrive (`DREAMS_outdrive.SLDASM`, one per hull)

The drive is **fixed**: no pivot, nothing moves. Use **sheet 5** for the assembly and **sheet 6** for the
parts:
- sheet 5: side, astern and top views, every key point as x / z / y, the balloon list
- sheet 6: each part on its own, the purchased parts and a modeling order

Coordinates are the boat's: X forward from the transom, Y up from the baseline, Z from the hull
centreline. The belt runs in the transverse plane X −48, down inside the leg.

| Part | How to model it |
|---|---|
| 1 Mount (ABS, or 6061 later) | Deck flange X 0 → 85, 88 wide, Y 250 → 262. A 6 mm flange down the lid's aft wall, X −6 → 0, Y 197 → 262, 88 wide. A head block X −104 → −6, Y 200 → 262, 34 wide, with a 70 wide platform X −66 → −6, Y 252 → 262 under the cover. Cut the leg socket (leg section + 0.2, Y 205 → 245), the belt slot, 4 M5 inserts from below (X 15 / 70, Z ±30), 2 M5 inserts in the wall flange (Y 225, Z ±28), 2 M4 holes across the socket |
| 2 Motor plate (6061) | L bracket at X −6 → −2, 50 wide, up to Y 334, foot forward on the mount; the motor's slots run ±4 up for belt tension |
| 3 Motor cover (ABS) | 2 mm shell X −62 → 4, Z ±35, Y 262 → 335, R8 edges, open at the bottom |
| 4 Leg + pod halves (ABS) | Leg: NACA 0035, 80 chord (LE X −21), 28 thick, from Y 38 to 245. Pod: revolve Ø32 on the prop axis (Y 22), nose X −15, tail X −107. Combine, cut the pockets (sheet 6), **split on Z = 0** |
| 5 Shaft | Ø5 × 142, X −161 → −19: D-flat under the prop, a flat for the pulley set screw, M5 thread |
| 6 Thrust pad (ABS + 2 mm EPDM) | Block X −19 → 0, Y 120 → 160, 30 wide, aft face R11 to fit the leg's nose; bonded to the transom |
| Bought parts | Download STEP models: the outrunner, HTD 3M 20T pulleys, the 205 T belt, 625-2RS bearings, the shaft collar |
| Prop | Import `mechanical/props/toroidal_3loop_p75_RH_shaft/*.stl` (starboard) and `_LH_shaft` (port) as a reference body, or rebuild it from that folder's `curves/` |

Mate everything fixed and run Interference Detection. The leg passes 3.5 mm outside the rail (the rail's
17.5 mm overhang is what stops it going closer), and the wall flange sits 2 mm above the rail.

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
| Outdrives (fixed) | mount X −104 → 85 (wall flange at X −6 → 0), motor X −38 → −6 on axis Y 300, leg LE X −21, prop axis Y 22, prop hub X −109 → −152, Z ±350 |
| Pod + Van Dorn (stowed) | under the sheave at X 650, Y 285 → 445, in the hub garage |

**Checks:**

- Interference Detection.
- Mass Properties: with the batteries as envelopes, the CG should land near X 580 / Y 220.
- A section view on the Right plane at X 530, to see the bolts, bosses, rib and rail line up.

---

## Part D — Export and print (Elegoo Giga for the hull parts; EXP S5 for the outdrive)

- **STL export:** Save Bodies (or each part) → STL, Custom resolution, 0.01 mm deviation, 5°.
- **Tub segments:** aft bulkhead down; 255 × 190 section, 520 / 260 / 520 tall. **Lid segments:** aft
  end down; 255 × 68 section, the same heights. PLA on the Giga: 0.6–0.8 nozzle, 4 walls, +3–5 % flow,
  5 mm brim, no supports. The outdrive parts go in ABS on the S5 (motor heat).
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
