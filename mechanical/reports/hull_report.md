## Mass budget

| Item | kg | Carried by | x (m) | z (m) |
|---|---|---|---|---|
| Drive pack 12S ~10 Ah (port hull, middle segment) | 2.70 | hulls | 0.65 | 0.06 |
| Electronics pack 5S2P (stbd hull, middle segment) | 0.85 | hulls | 0.65 | 0.04 |
| Winch pack 5S (stbd hull, middle segment) | 0.70 | hulls | 0.65 | 0.04 |
| Pi 5 on the carrier PCB (Teensy 4.1), radios, RC rx, regulators (stbd hull, aft) | 0.70 | hulls | 0.33 | 0.06 |
| VESC x2, one per hull by its outdrive | 0.40 | hulls | 0.20 | 0.05 |
| Fuses, switches, 12 AWG wiring | 0.40 | hulls | 0.45 | 0.10 |
| Aluminium heat plates on the hull bottoms x2 | 0.40 | hulls | 0.45 | 0.03 |
| IP68 bulkhead connectors / glands in the lids | 0.15 | hulls | 0.40 | 0.25 |
| Hub cowl (printed PLA, painted light) | 0.60 | center | 0.61 | 0.44 |
| Garage: winch bracket, sheave, docking cone | 0.35 | center | 0.65 | 0.43 |
| Stereo cameras + bar | 0.60 | center | 0.87 | 0.53 |
| Mast, GNSS puck, LTE + WiFi whips, e-stop | 0.50 | center | 0.61 | 0.68 |
| Winch (2006 + planetary, drum, level-wind, slip ring) | 1.50 | center | 0.43 | 0.42 |
| Tether, ~20 m 4-conductor | 0.60 | center | 0.43 | 0.42 |
| Pod, stowed in the hub garage (V1-style box) | 1.20 | center | 0.65 | 0.36 |
| Pod sensor growth (pH, DO, turbidity) | 0.80 | center | 0.65 | 0.36 |
| Van Dorn sampler, 2 L, 5 in PVC + release | 0.90 | center | 0.65 | 0.36 |
| Water sample, 2 L (sampling runs) | 2.00 | center | 0.65 | 0.36 |
| Arch frames x2 (1/4" 6061-T6, laser cut) | 0.99 | center | 0.65 | 0.35 |
| Arm fairings + foot shoes (printed PLA) | 0.70 | center | 0.65 | 0.35 |
| Foot plates x2 (6 mm 6061, lightened) + 4 angle brackets | 1.00 | center | 0.65 | 0.26 |
| Hull tubs + lids x2 (printed PLA, glassed + sealed) | 9.23 | hulls | 0.62 | 0.12 |
| Lid joints x2 (rail flanges, gasket cord, M4 screws + inserts) | 1.98 | hulls | 0.62 | 0.19 |
| Foot bolting x2 (16 M6 x 60 A4 + bonded seals, EPDM pads) | 0.45 | hulls | 0.65 | 0.25 |
| Belt outdrives x2 (outrunner, tilt head, bracket, leg, belt, shaft, prop) | 1.20 | hulls | -0.04 | 0.21 |
| Leak probes (carrier J8 / J9), vents, fasteners, cable clips | 0.30 | hulls | 0.60 | 0.20 |
| Growth margin 10% | 3.12 | both |  |  |
| **Total (design)** | **34.3** | bridge 12.9 / hulls 21.4 | LCG 0.581 | KG 0.220 |

Modules (design, incl. margin): bridge 12.9 kg (CG 0.618 m fwd of transom), each hull 10.7 kg (tub, lid, drive, packs, electronics). 'Hulls' items hang below the foot bolts in the load cases. Packs are the 09-29 Li-ion/LiPo estimates for V3's rails: drive 12S (~10 Ah), electronics and winch 15-21 V. Kyle's robot arm (~10 kg) is not in the budget: whether it goes on the boat is still open.

## Demi-hull particulars

| Parameter | Value |
|---|---|
| LOA (hull) | 1300 mm |
| Beam | 220 mm at the shell, 255 mm over the rail |
| Depth, baseline to deck | 250 mm |
| Bottom | 12 deg deadrise, chine R50, deck edge R50 |
| Construction | open tub + removable lid, joint plane z 190 (91 mm above the DWL) |
| Rail (lid over the gunwale) | 15 mm flanges 5 + 5 thick, 2.5 lip, 3 mm cord, 37 x M4 (100 pitch, 60 by the frames), 2.85 m long |
| Bow taper from | 650 mm fwd of transom |
| Keel rocker from | 910 mm fwd, stem keel +100 mm |
| Keel rise aft | +40 mm at the transom, straight to 520 mm fwd |
| Enclosed volume | 51.6 L per hull (tub + lid) |
| Shell mass (est.) | 4.61 kg per hull + 0.99 kg lid joint |
| Print | 3 segments each (520 / 260 / 520 mm, printed on end); tub 255 x 190, lid 255 x 68 mm sections on a 800 x 800 x 1000 mm build volume -> fits |
| Foot on the lid deck | 121 mm flat top under a 140 mm foot, deck falls 0.9 mm at its edges -> fits (EPDM pad takes it up) |
| LWL at design draft | 1298 mm |
| Slenderness LWL / vol^(1/3) | 5.03 |
| Prismatic coefficient Cp | 0.71 |
| Immersed transom (design) | 59 mm deep, 98 cm^2 |
| Hull spacing (centrelines) | 700 mm  (s/L = 0.54) |
| Clear tunnel between hulls | 480 mm |
| Overall width | 920 mm at the shells, 955 over the rails |

## Hydrostatics (catamaran, fresh water)

| Condition | kg | Draft mm | Freeboard mm | To lid joint mm | Trim mm (+bow dn) | kg per mm sink | GM_T m | GM_L m | N m per deg heel | Reserve buoy. |
|---|---|---|---|---|---|---|---|---|---|---|
| Light (no growth, no sample, no margin) | 28.4 | 86 | 164 | 104 | -10 | 0.47 | 1.93 | 1.60 | 9.4 | 263% |
| Design (budget + margin) | 34.3 | 99 | 151 | 91 | +1 | 0.47 | 1.57 | 1.31 | 9.2 | 201% |
| Max (design + 5 kg on the bridge) | 39.3 | 110 | 140 | 80 | +11 | 0.47 | 1.32 | 1.10 | 8.9 | 163% |

Design condition: LCB 0.580 m vs LCG 0.581 m fwd of transom; KB 0.060 m, KG 0.220 m. Trim: 29 mm per kg-m of moment. One hull lifts clear at ~16 deg heel; righting moment there ~118 N m.

## Buoyancy (design condition, fresh water)

| Quantity | Value |
|---|---|
| Total buoyancy, both hulls just submerged | 103 kg (1012 N), 51.6 L per hull |
| Design weight (incl. margin) | 34.3 kg -> floats at 99 mm, using 33% of the buoyancy |
| Reserve buoyancy | 69 kg (201% of the weight) |
| Buoyancy with the hulls half under (125 mm) | 47 kg (+12 kg over the design weight) |
| Buoyancy with the hulls 3/4 under (188 mm) | 76 kg (+42 kg over the design weight) |
| Sinkage | 0.47 kg per mm (2.1 mm per kg added) |
| Payload until the lid joint is awash | +43 kg |
| Payload keeping 60 mm freeboard to the joint | +15 kg |
| Heel to put the leeward rail in the water | 15 deg (windward hull lifts at 16 deg) |

## Arched bridge

| Parameter | Value |
|---|---|
| Frames | 2x 1/4" 6061-T6 plate, 50 mm deep, at x = 520 / 780 mm (over the lid ribs at J1 / J2) |
| Frame span / length | 700 mm foot to foot, 772 mm along the arch |
| Frame blank | 750 x 112 mm, 0.50 kg each after 25% lightening |
| Hub (cowl) | 560 x 400 mm, z 310-550 mm (belt line 440), centred 610 fwd |
| Garage opening (hub floor) | 240 x 301 mm (x by y) between the frames, centred 650 fwd |
| Pod + Van Dorn through it | pod 110 x 80, sampler 210 x 141 side by side: margins +30 / +70 mm -> fits |
| Stowed under the sheave | z 285-445 mm, bottom 186 mm above the DWL |
| Winch envelope (placeholder) | x 360-500, z 372-470: fits inside the cowl (margin +70 mm) |
| Hub underside above DWL | 211 mm |
| Mast top (GNSS) | 820 mm above baseline |

## Frame loads (per frame, design condition)

| Load case | Moment N m | Shear N | Stress MPa | SF on yield |
|---|---|---|---|---|
| LC1 afloat, 2.5 g (hub span / arm root) | 18 | 99 | 7 | 41.2 |
| LC2 lifted by one hull x1.5 (lifted foot) | 110 | 216 | 42 | 6.6 |
| LC3 hulls pitching out of phase, a_cg 2 g (feet) | 147 | 420 | 56 | 5.0 |
| LC4 carried by the hub x2 (arm roots) | 24 | 131 | 9 | 31.0 |

## Foot, lid and rail joints (worst of LC2-LC4)

| Joint | Case | Load | Capacity | SF |
|---|---|---|---|---|
| Foot bolts, M6 A4 (8 per foot, in the lid-rib bosses) | LC3 | 742 N | 2400 N | 3.2 |
| Lid rib under each frame (8 mm PLA, 60 deep) | LC3 | 10 MPa | 45 MPa | 4.3 |
| Rail screws beside a frame (M4 inserts, 3 share) | LC3 | 273 N | 1200 N | 4.4 |

The foot pivots on its far edge and the bolts hold the near side down; each lid rib carries that couple out to the rail, where ~3 screws take it into the tub. Target SF 3. The M6 bolts themselves are good for ~9 kN; the printed bosses and inserts govern, so pull-test a boss and an insert from your printer.

Outdrive (fixed): prop axis z 22 mm, motor axis z 300 mm -> belt centres 278 mm, HTD 3M-9 belt 205 teeth (615 mm), 20T pulleys (19.1 PD). Tightest gap: wall flange over rail 2.0 mm. At full forward thrust (55 N) the leg pushes 131 N on its transom pad and the mount takes 76 N; the leg bends 6.5 N m at the pad (the mount alone would take 11.2 N m).
