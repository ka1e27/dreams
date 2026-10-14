## Mass budget

| Item | kg | Carried by | x (m) | z (m) |
|---|---|---|---|---|
| Drive pack 12S ~10 Ah (port hull, between the frames) | 2.70 | hulls | 0.46 | 0.06 |
| Electronics pack 5S2P (stbd hull, between the frames) | 0.85 | hulls | 0.46 | 0.04 |
| Winch pack 5S (stbd hull, between the frames) | 0.70 | hulls | 0.46 | 0.04 |
| Pi 5 on the carrier PCB (Teensy 4.1), radios, RC rx, regulators (stbd hull, aft) | 0.70 | hulls | 0.30 | 0.06 |
| VESC x2, one per hull by its outdrive | 0.40 | hulls | 0.17 | 0.05 |
| Fuses, switches, 12 AWG wiring | 0.40 | hulls | 0.32 | 0.10 |
| Aluminium heat plates on the hull bottoms x2 | 0.40 | hulls | 0.46 | 0.03 |
| IP68 bulkhead connectors / glands in the lids | 0.15 | hulls | 0.36 | 0.25 |
| Hub cowl (printed PLA, painted light) | 0.60 | center | 0.42 | 0.44 |
| Garage: winch bracket, sheave, docking cone | 0.35 | center | 0.46 | 0.43 |
| Stereo cameras + bar | 0.60 | center | 0.69 | 0.53 |
| Mast, GNSS puck, LTE + WiFi whips, e-stop | 0.50 | center | 0.42 | 0.68 |
| Winch (2006 + planetary, drum, level-wind, slip ring) | 1.50 | center | 0.24 | 0.42 |
| Tether, ~20 m 4-conductor | 0.60 | center | 0.24 | 0.42 |
| Pod, stowed in the hub garage (V1-style box) | 1.20 | center | 0.46 | 0.36 |
| Pod sensor growth (pH, DO, turbidity) | 0.80 | center | 0.46 | 0.36 |
| Van Dorn sampler, 2 L, 5 in PVC + release | 0.90 | center | 0.46 | 0.36 |
| Water sample, 2 L (sampling runs) | 2.00 | center | 0.46 | 0.36 |
| Arch frames x2 (1/4" 6061-T6, laser cut) | 0.99 | center | 0.46 | 0.35 |
| Arm fairings + foot shoes (printed PLA) | 0.70 | center | 0.46 | 0.35 |
| Foot plates x2 (6 mm 6061, lightened) + 4 angle brackets | 1.00 | center | 0.46 | 0.26 |
| Hull tubs + lids x2 (printed PLA in one piece each, glassed + sealed) | 6.74 | hulls | 0.44 | 0.12 |
| Lid joints x2 (rail flanges, gasket cord, M4 screws + inserts) | 1.59 | hulls | 0.44 | 0.19 |
| Foot bolting x2 (16 M6 x 60 A4 + bonded seals, EPDM pads) | 0.45 | hulls | 0.46 | 0.25 |
| Belt outdrives x2 (outrunner, mount, leg, belt, shaft, prop) | 1.20 | hulls | -0.04 | 0.21 |
| Leak probes (carrier J8 / J9), vents, fasteners, cable clips | 0.30 | hulls | 0.64 | 0.20 |
| Growth margin 10% | 2.83 | both |  |  |
| **Total (design)** | **31.2** | bridge 12.9 / hulls 18.2 | LCG 0.414 | KG 0.229 |

Modules (design, incl. margin): bridge 12.9 kg (CG 0.433 m fwd of transom), each hull 9.1 kg (tub, lid, drive, packs, electronics). 'Hulls' items hang below the foot bolts in the load cases. Packs are the 09-29 Li-ion/LiPo estimates for V3's rails: drive 12S (~10 Ah), electronics and winch 15-21 V. Kyle's robot arm (~10 kg) is not in the budget: whether it goes on the boat is still open.

## Demi-hull particulars

| Parameter | Value |
|---|---|
| LOA | 940 mm at the shell, 975 mm over the rails |
| Beam | 220 mm at the shell, 255 mm over the rail |
| Depth, baseline to deck | 250 mm |
| Bottom | 12 deg deadrise, chine R50, deck edge R50 |
| Construction | open tub + removable lid, each printed in one piece; joint plane z 190 (72 mm above the DWL) |
| Inside | tub ring frames at x 120 / 335 / 595 / 770; lid ribs (printed flat, bonded in) at x 335 / 595 |
| Rail (lid over the gunwale) | 15 mm flanges 5 + 5 thick, 2.5 lip, 3 mm cord, 30 x M4 (100 pitch, 60 by the frames), 2.14 m long |
| Bow taper from | 470 mm fwd of transom |
| Keel rocker from | 658 mm fwd, stem keel +100 mm |
| Keel rise aft | +40 mm at the transom, straight to 376 mm fwd |
| Enclosed volume | 37.3 L per hull (tub + lid) |
| Shell mass (est.) | 3.37 kg per hull + 0.80 kg lid joint |
| Print | one piece each, on the stern: tub 255 x 190 x 970 tall, lid 255 x 68 x 975 tall (limit 975 on a 800 x 800 x 1000 mm build volume) -> fits |
| Foot on the lid deck | 106-121 mm flat top under a 140 mm foot (narrowest at its fwd end, on the bow taper); a flat landing printed into the lid deck fills the deck-edge radius under it, at most 3.4 mm deep -> fits |
| LWL at design draft | 940 mm |
| Slenderness LWL / vol^(1/3) | 3.76 |
| Prismatic coefficient Cp | 0.73 |
| Immersed transom (design) | 78 mm deep, 139 cm^2 |
| Hull spacing (centrelines) | 700 mm  (s/L = 0.74) |
| Clear tunnel between hulls | 480 mm |
| Overall width | 920 mm at the shells, 955 over the rails |

## Hydrostatics (catamaran, fresh water)

| Condition | kg | Draft mm | Freeboard mm | To lid joint mm | Trim mm (+bow dn) | kg per mm sink | GM_T m | GM_L m | N m per deg heel | Reserve buoy. |
|---|---|---|---|---|---|---|---|---|---|---|
| Light (no growth, no sample, no margin) | 25.5 | 101 | 149 | 89 | -16 | 0.34 | 1.52 | 0.59 | 6.7 | 192% |
| Design (budget + margin) | 31.2 | 118 | 132 | 72 | -1 | 0.34 | 1.22 | 0.45 | 6.5 | 140% |
| Max (design + 5 kg on the bridge) | 36.2 | 132 | 118 | 58 | +10 | 0.34 | 1.00 | 0.34 | 6.2 | 106% |

Design condition: LCB 0.414 m vs LCG 0.414 m fwd of transom; KB 0.070 m, KG 0.229 m. Trim: 67 mm per kg-m of moment. One hull lifts clear at ~20 deg heel; righting moment there ~107 N m.

## Buoyancy (design condition, fresh water)

| Quantity | Value |
|---|---|
| Total buoyancy, both hulls just submerged | 75 kg (732 N), 37.3 L per hull |
| Design weight (incl. margin) | 31.2 kg -> floats at 118 mm, using 42% of the buoyancy |
| Reserve buoyancy | 43 kg (140% of the weight) |
| Buoyancy with the hulls half under (125 mm) | 34 kg (+2 kg over the design weight) |
| Buoyancy with the hulls 3/4 under (188 mm) | 55 kg (+24 kg over the design weight) |
| Sinkage | 0.34 kg per mm (2.9 mm per kg added) |
| Payload until the lid joint is awash | +25 kg |
| Payload keeping 60 mm freeboard to the joint | +4 kg |
| Heel to put the leeward rail in the water | 12 deg (windward hull lifts at 20 deg) |

## Arched bridge

| Parameter | Value |
|---|---|
| Frames | 2x 1/4" 6061-T6 plate, 50 mm deep, at x = 335 / 595 mm (over the lid ribs) |
| Frame span / length | 700 mm foot to foot, 772 mm along the arch |
| Frame blank | 750 x 112 mm, 0.50 kg each after 25% lightening |
| Hub (cowl) | 560 x 400 mm, z 310-550 mm (belt line 440), centred 425 fwd |
| Garage opening (hub floor) | 240 x 301 mm (x by y) between the frames, centred 465 fwd |
| Pod + Van Dorn through it | pod 110 x 80, sampler 210 x 141 side by side: margins +30 / +70 mm -> fits |
| Stowed under the sheave | z 285-445 mm, bottom 167 mm above the DWL |
| Winch envelope (placeholder) | x 175-315, z 372-470: fits inside the cowl (margin +70 mm) |
| Hub underside above DWL | 192 mm |
| Mast top (GNSS) | 820 mm above baseline |

## Frame loads (per frame, design condition)

| Load case | Moment N m | Shear N | Stress MPa | SF on yield |
|---|---|---|---|---|
| LC1 afloat, 2.5 g (hub span / arm root) | 18 | 99 | 7 | 41.2 |
| LC2 lifted by one hull x1.5 (lifted foot) | 100 | 202 | 38 | 7.3 |
| LC3 hulls pitching out of phase, a_cg 2 g (feet) | 97 | 276 | 37 | 7.6 |
| LC4 carried by the hub x2 (arm roots) | 20 | 111 | 8 | 36.4 |

## Foot, lid and rail joints (worst of LC2-LC4)

| Joint | Case | Load | Capacity | SF |
|---|---|---|---|---|
| Foot bolts, M6 A4 (8 per foot, in the lid-rib bosses) | LC3 | 488 N | 2400 N | 4.9 |
| Lid rib under each frame (8 mm PLA, 60 deep) | LC3 | 6.8 MPa | 45 MPa | 6.6 |
| Rib-end bond to the skirt (epoxy fillets, 10 mm legs) | LC3 | 0.3 MPa | 4.0 MPa | 11.7 |
| Rail screws beside a frame (M4 inserts, 3 share) | LC3 | 192 N | 1200 N | 6.2 |

The foot pivots on its far edge and the bolts hold the near side down; each lid rib carries that couple out to the rail, where ~3 screws take it into the tub. Target SF 3. The M6 bolts themselves are good for ~9 kN; the printed bosses and inserts govern, so pull-test a boss and an insert from your printer.

Outdrive (fixed): prop axis z 41 mm, motor axis z 300 mm -> belt centres 259 mm, HTD 3M-9 belt 193 teeth (579 mm), 20T pulleys (19.1 PD). Tightest gap: wall flange over rail 2.0 mm. At full forward thrust (55 N) the leg pushes 119 N on its transom pad and the mount takes 64 N; the leg bends 5.5 N m at the pad (the mount alone would take 10.1 N m).
