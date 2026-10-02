## Mass budget

| Item | kg | Carried by | x (m) | z (m) |
|---|---|---|---|---|
| Drive packs 2x M18 HD12.0 (one per VESC, 18 V) | 3.10 | center | 0.51 | 0.42 |
| Electronics pack M18 XC5.0 | 0.82 | center | 0.51 | 0.42 |
| Winch pack M18 XC6.0 | 1.15 | center | 0.51 | 0.42 |
| M18 adapter plates x4 | 0.32 | center | 0.51 | 0.42 |
| VESC x2 + heatsinks | 0.40 | center | 0.75 | 0.40 |
| Fuses, switches, 12 AWG wiring | 0.40 | center | 0.61 | 0.40 |
| Pi 5, Boat PCB, Picos, SIM7600, GPS, IMU, RC rx, UBEC | 0.70 | center | 0.75 | 0.45 |
| Hub IP67 box + glands + connectors | 1.60 | center | 0.61 | 0.43 |
| Hub cowl (printed PETG/ASA) | 0.60 | center | 0.61 | 0.44 |
| Stereo cameras + bar | 0.60 | center | 0.87 | 0.53 |
| Mast, GNSS puck, LTE + WiFi whips, e-stop | 0.50 | center | 0.61 | 0.68 |
| Winch (2006 + planetary, drum, level-wind, slip ring) | 1.50 | center | 0.61 | 0.34 |
| Tether, ~20 m 4-conductor | 0.60 | center | 0.61 | 0.34 |
| Pod, stowed under the hub (V1-style box) | 1.20 | center | 0.61 | 0.21 |
| Pod sensor growth (pH, DO, turbidity) | 0.80 | center | 0.61 | 0.21 |
| Arch frames x2 (1/4" 6061-T6, laser cut) | 0.99 | center | 0.65 | 0.35 |
| Arm fairings + foot shoes (printed PETG/ASA) | 0.70 | center | 0.65 | 0.35 |
| Foot plates x2 (6 mm 6061, lightened) + 4 angle brackets | 1.00 | center | 0.65 | 0.26 |
| Hull tubs + lids x2 (printed PETG, glassed) | 8.23 | hulls | 0.62 | 0.12 |
| Lid joints x2 (rail flanges, gasket cord, M4 screws + inserts) | 2.02 | hulls | 0.62 | 0.19 |
| Foot bolting x2 (16 M6 x 60 A4 + bonded seals, EPDM pads) | 0.45 | hulls | 0.65 | 0.25 |
| Belt outdrives x2 (outrunner, cover, tilt bracket, leg, belt, shaft, prop) | 1.16 | hulls | -0.05 | 0.20 |
| Leak sensors, vents, fasteners, cable clips | 0.30 | hulls | 0.60 | 0.20 |
| Growth margin 10% | 2.91 | both |  |  |
| **Total (design)** | **32.0** | bridge 18.7 / hulls 13.4 | LCG 0.584 | KG 0.284 |

Modules (design, incl. margin): bridge 18.7 kg (CG 0.603 m fwd of transom), each hull 6.7 kg (tub, lid, drive). 'Hulls' items hang below the foot bolts in the load cases.

## Demi-hull particulars

| Parameter | Value |
|---|---|
| LOA (hull) | 1300 mm |
| Beam | 220 mm at the shell, 255 mm over the rail |
| Depth, baseline to deck | 250 mm |
| Bottom | 12 deg deadrise, chine R50, deck edge R50 |
| Construction | open tub + removable lid, joint plane z 190 (96 mm above the DWL) |
| Rail (lid over the gunwale) | 15 mm flanges 5 + 5 thick, 2.5 lip, 3 mm cord, 37 x M4 (100 pitch, 60 by the frames), 2.85 m long |
| Bow taper from | 650 mm fwd of transom |
| Keel rocker from | 910 mm fwd, stem keel +100 mm |
| Keel rise aft | +40 mm at the transom, straight to 520 mm fwd |
| Enclosed volume | 51.6 L per hull (tub + lid) |
| Shell mass (est.) | 4.11 kg per hull + 1.01 kg lid joint |
| Print | 5 x 260 mm segments each; tub 255 x 190, lid 255 x 68 mm sections on a 330 x 240 x 300 mm build volume -> fits |
| Foot on the lid deck | 121 mm flat top under a 140 mm foot, deck falls 0.9 mm at its edges -> fits (EPDM pad takes it up) |
| LWL at design draft | 1289 mm |
| Slenderness LWL / vol^(1/3) | 5.11 |
| Prismatic coefficient Cp | 0.71 |
| Immersed transom (design) | 54 mm deep, 87 cm^2 |
| Hull spacing (centrelines) | 700 mm  (s/L = 0.54) |
| Clear tunnel between hulls | 480 mm |
| Overall width | 920 mm at the shells, 955 over the rails |

## Hydrostatics (catamaran, fresh water)

| Condition | kg | Draft mm | Freeboard mm | To lid joint mm | Trim mm (+bow dn) | kg per mm sink | GM_T m | GM_L m | N m per deg heel | Reserve buoy. |
|---|---|---|---|---|---|---|---|---|---|---|
| Light (no growth, no margin) | 28.3 | 86 | 164 | 104 | -3 | 0.47 | 1.85 | 1.52 | 9.0 | 264% |
| Design (budget + margin) | 32.0 | 94 | 156 | 96 | +2 | 0.47 | 1.62 | 1.34 | 8.9 | 222% |
| Max (design + 5 kg on the bridge) | 37.0 | 105 | 145 | 85 | +12 | 0.47 | 1.36 | 1.12 | 8.6 | 179% |

Design condition: LCB 0.582 m vs LCG 0.584 m fwd of transom; KB 0.058 m, KG 0.284 m. Trim: 30 mm per kg-m of moment. One hull lifts clear at ~16 deg heel; righting moment there ~110 N m.

## Buoyancy (design condition, fresh water)

| Quantity | Value |
|---|---|
| Total buoyancy, both hulls just submerged | 103 kg (1012 N), 51.6 L per hull |
| Design weight (incl. margin) | 32.0 kg -> floats at 94 mm, using 31% of the buoyancy |
| Reserve buoyancy | 71 kg (222% of the weight) |
| Buoyancy with the hulls half under (125 mm) | 47 kg (+14 kg over the design weight) |
| Buoyancy with the hulls 3/4 under (188 mm) | 76 kg (+44 kg over the design weight) |
| Sinkage | 0.47 kg per mm (2.1 mm per kg added) |
| Payload until the lid joint is awash | +45 kg |
| Payload keeping 60 mm freeboard to the joint | +17 kg |
| Heel to put the leeward rail in the water | 16 deg (windward hull lifts at 16 deg) |

## Arched bridge

| Parameter | Value |
|---|---|
| Frames | 2x 1/4" 6061-T6 plate, 50 mm deep, at x = 520 / 780 mm (over the lid ribs at J2 / J3) |
| Frame span / length | 700 mm foot to foot, 772 mm along the arch |
| Frame blank | 750 x 112 mm, 0.50 kg each after 25% lightening |
| Hub (cowl) | 560 x 400 mm, z 310-550 mm (belt line 440), centred 610 fwd |
| IP67 box in the hub | 480 x 300 x 120 mm on the frame tops (fits inside the cowl, margin +0.023) |
| Hub underside above DWL | 216 mm |
| Mast top (GNSS) | 820 mm above baseline |

## Frame loads (per frame, design condition)

| Load case | Moment N m | Shear N | Stress MPa | SF on yield |
|---|---|---|---|---|
| LC1 afloat, 2.5 g (hub span / arm root) | 28 | 156 | 11 | 26.0 |
| LC2 lifted by one hull x1.5 (lifted foot) | 112 | 254 | 43 | 6.5 |
| LC3 hulls pitching out of phase, a_cg 2 g (feet) | 136 | 390 | 52 | 5.4 |
| LC4 carried by the hub x2 (arm roots) | 16 | 89 | 6 | 45.4 |

## Foot, lid and rail joints (worst of LC2-LC4)

| Joint | Case | Load | Capacity | SF |
|---|---|---|---|---|
| Foot bolts, M6 A4 (8 per foot, in the lid-rib bosses) | LC3 | 688 N | 2400 N | 3.5 |
| Lid rib under each frame (8 mm PETG, 60 deep) | LC3 | 10 MPa | 45 MPa | 4.7 |
| Rail screws beside a frame (M4 inserts, 3 share) | LC3 | 254 N | 1200 N | 4.7 |

The foot pivots on its far edge and the bolts hold the near side down; each lid rib carries that couple out to the rail, where ~3 screws take it into the tub. Target SF 3. The M6 bolts themselves are good for ~9 kN; the printed bosses and inserts govern, so pull-test a boss and an insert from your printer.

Outdrive: prop axis z 17 mm, motor axis z 300 mm -> belt centres 283 mm, HTD 3M-9 belt 209 teeth (627 mm), 20T pulleys (19.1 PD).
