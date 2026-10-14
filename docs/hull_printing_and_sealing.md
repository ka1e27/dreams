# D.R.E.A.M.S — Printing and Sealing the PLA Hulls (rev E)

How to get the printed PLA tubs and lids watertight, with less mess than V2's method (epoxy brushed on
the outside). **Read this before the first hull print**, alongside Part D of
[`solidworks_modeling_guide.md`](solidworks_modeling_guide.md).

**Status:** advice from 2026-10-08. **Not decided yet.** The model, the drawings and the guide still
describe the current plan: 200 g/m² glass + epoxy outside, 2 coats of epoxy inside. Once a sealing
option (§3) and a glass option (§5) are picked, update:

- `Hull.skin_areal` / `seal_areal` in `mechanical/hull_sizing.py`;
- the CONSTRUCTION note on sheet 2 (`sheet_lines()` in `mechanical/drawings.py`);
- step 2 of "After printing" in the guide's Part D.

Then re-run `python mechanical/build_all.py`.

---

## 1. Why the coating doesn't have to work hard

- At the 118 mm design draft the water pushes on the hull at only **1.2 kPa (0.17 psi)**. Printed
  walls leak by wicking through seams and gaps between lines, not because pressure forces water
  through. A well-printed wall does most of the sealing; the coating backs it up.
- The lid is 72 mm above the water at rest and only sees spray. The lower part of the tub is what
  lives in the water.
- A smooth outside isn't needed for speed. At 1.5 m/s, skin friction is 3.8 N of the 27.5 N of drag;
  wave drag is 17.4 N (`mechanical/reports/propulsion_report.md`). Layer lines barely matter.

Areas, one hull (from `hull_sizing.py`):

| Surface | Area |
|---|---|
| Outside of the tub (bottom, chines, sides, transom) | 0.47 m² |
| Outside of the lid (skirt, deck edges, flat deck, aft wall) | 0.26 m² |
| Wet at the design draft | 0.31 m² |
| Inside | about the same as the outside |
| Rail (gasket) length | 2.14 m |

## 2. Print it watertight (whatever the sealing option)

The Giga's stock nozzle is 0.6 mm, which suits the 2.4 mm wall (`Hull.wall_t`, 4 lines × 0.6 mm).

- **Wall:**
  - Set the wall line width to 0.60 mm.
  - In the preview, the 2.4 mm wall must slice as exactly 4 lines side by side, with no gap fill or
    infill between them.
  - Slicers lay wall loops on both faces of a thin wall, so 2 loops already give 4 lines. Setting
    more doesn't hurt.
- **Flow:** run the slicer's flow calibration, then add 3–5 %.
- **Heat:** print at the hot end of the filament's range (~220–230 °C for most PLA). Turn the part
  cooling down on the walls; the layers are long enough to cool on their own.
- **Layers:** 0.3 mm or less, i.e. no more than half the line width.
- **Seam:**
  - Paint it onto the outer edge of the flange, on the tub and on the lid. That spot is above the
    water, outboard of the gasket and under the lid's drip lip.
  - The seam is a column of start/stop points running the full length of the hull. In the preview,
    check that none of it lands below the waterline, e.g. along the keel.
  - Don't use random seams: they scatter blobs over the bottom.
- **Solid where it's thick:** 100 % infill in the flanges and in the 4 mm transom / aft wall.
- **Drafts:** keep them off the printer for the whole print. A cold draft weakens the bond between
  layers.
- **Already in the guide (Part D):**
  - Print stern down: the tub is 970 tall, the lid 975 (the Giga takes 1000).
  - Support the transom up to the flange: it prints 15 / 17.5 mm off the bed.
  - 10 mm brim.
  - Slow the outer walls over the top 200 mm.

## 3. Seal it: pick one

### A. Epoxy poured inside ("slosh"): recommended

The drips land inside, where nobody sees them. The coat is out of the sun and away from scuffs, and
the outside just gets paint (§4).

1. **Bond the lid ribs first** (guide Part D, step 1). The rib-bond check (`Lid.rib_bond`) assumes
   epoxy on bare, sanded PLA.
2. Sand off the transom supports. Wipe the inside with isopropyl alcohol, not acetone.
3. Wear nitrile gloves, ventilate, and work at room temperature, out of the sun.
4. **First coat:**
   - Mix ~100–150 g of laminating epoxy with a **slow** hardener (e.g. WEST 105 + 207, which leaves
     little blush).
   - Pour it into the tub.
   - Tilt and roll the tub until every inside face is wet, including the ring frames and the limber
     notches.
   - Pour the excess out.
5. **Keep it moving, and don't let it sit in the keel.** A pool of curing epoxy can heat past
   55–60 °C, where PLA softens. A thin film can't.
6. **Second coat:** put it on once the first is tacky, and no sanding is needed. If the first coat
   has cured hard, wash off any blush with water, scuff it, then recoat.
7. **The lid:** the same way, upside down (deck down), one compartment at a time between the ribs.
8. **How much:** a quart-size kit does both hulls. That's ~1.5 m² of inside per coat, at about
   0.1 kg/m² kept per coat, plus whatever gets poured off.

### B. dichtol AM Hydro (DIAMANT Polymer): cleanest, if you can get it

A water-based, one-part sealer made for 3D prints, with PLA on its list. It soaks into the pores and
sets there instead of leaving a film. There's no mixing and no pot life, and it cleans up with water.

- The maker says it seals gaps up to ~0.2 mm, so it still needs a good print (§2).
- A drone maker's tests on underwater housings found it beat epoxy impregnation (3Printr, below).
- **Application, as the retailers describe it.** Get the technical data sheet before using it.
  - Clean the part first: residue in the pores blocks it.
  - Then use one of three methods:
    - dip the part for ~10 min, then drain it;
    - brush on 4 coats, a minute apart, keeping the surface wet for at least 5 min;
    - pour it in, leave it ~5 min, then pour the surplus off (this suits the tub).
  - Keep the part at or below 40 °C. Allow about a day to dry at 20 °C.
- **Before committing to it:**
  - Do all the epoxy bonding (ribs, heat plates, thrust pad) first.
  - On a coupon, test that paint sticks over it and that epoxy still bonds next to it.
- **Buying:**
  - Sold in 250 mL and 1 L bottles by 3DJake in the EU.
  - No US seller confirmed. The maker's US subsidiary is DIAMANT Polymers Inc. in Cincinnati.
  - Sources disagree on shelf life (1 or 5 years), so check the batch date.
  - Coverage per m² isn't published.

### C. Epoxy outside, rolled and tipped (not brushed)

If the epoxy goes outside anyway, this is how boatbuilders coat vertical surfaces. It's thinner and
neater than brushing.

1. Stand the tub upside down on a block smaller than its opening, so drips fall off the rail edge.
   Mask the flange.
2. Scuff with 120–180 grit and wipe with isopropyl alcohol.
3. Mix small batches with dispensing pumps, and pour each into a roller tray straight away. Spread
   thin, the epoxy stays cooler and workable for longer.
4. Roll on a thin coat with a thin (~1/8 in) foam roller (WEST 800 covers). Then "tip" it: drag a
   foam brush, or a strip cut from a roller cover, lightly over it to pop bubbles and level it.
5. Put on 2–3 thin coats, each one while the last is still tacky. Pull the tape at the gel stage.
6. Epoxy breaks down in sunlight, so it still needs paint (§4).

## 4. Outside finish and the rail (all options)

- **Paint:** scuff, prime, and paint a light colour. Paint gives the UV protection epoxy lacks, and a
  light colour keeps the PLA under its ~55–60 °C softening point in the sun.
- **Rail flange and groove:** the tub prints on end, so layer lines cross the gasket.
  - Brush a thin epoxy coat on the flange top and in the groove, then sand it smooth. Or use
    closed-cell EPDM foam tape instead of the cord.
  - If the heat-set inserts are already in, thread waxed M4 screws into them to keep the epoxy out.
- **Holes:**
  - The foot bolts get bonded seal washers and EPDM pads (already in the plan).
  - Bed the outdrive's wall bolts and the lid glands in sealant.

## 5. Glass: probably not a full skin

- The current plan has glass outside *and* epoxy inside, which is more epoxy work than V2 had.
- The full glass skin mainly earned its place over rev D's segment seams, and rev E has none.
- No check in `hull_sizing.py` counts on it: `skin_areal` is mass only.
- For knocks (docks, rocks, launching), protect only what hits:
  - glass tape along the keel and up the stem, or
  - a UHMW strip there. The 10-01 journal entry suggested a UHMW or aluminium stem guard anyway,
    with bolts that could carry an ice plow later.
- Printed PLA is brittle. If the first hull cracks on a knock, that's the case for more glass.

## 6. Test, in this order

1. **Profile cup, before the hull:**
   - Take the midbody section, close it with a straight wall at the joint plane, extrude it 150 mm
     and shell it to 2.4 mm with a 4 mm floor. Put the seam on the straight wall.
   - Print it on the Giga with the hull's exact settings.
   - Fill it with dyed water and leave it overnight on paper towels.
   - A weep means changing the settings before spending about a day printing a tub.
2. **Seal** (§3), including the flange (§4).
3. **Tub fill:**
   - Fill the sealed tub to the design waterline (118 mm above the keel, ~15 L), in a cradle on
     paper towels, and leave it overnight.
   - Don't lift it while it's full.
   - Mark any weep, then drain, dry and fix it (thin CA wicks into a weeping layer line; or use
     epoxy), and retest.
4. **Lid-on pressure test** (guide Part D, step 4): screw the lid down and pressurise the hull to
   ≤ 0.03 bar through the vent port. Brush soapy water along the rail and the bolt holes and look for
   bubbles.
5. **First float:** short and near the dock, with empty hulls and a paper towel at each keel low
   point. Check them after 30 min.

## 7. Weight

What each option does to the design condition (`hull_sizing.py`, rev E, nothing else changed):

| Sealing | Assumed (kg/m²) | Shell, one hull | Design | Draft | To lid joint | Payload to the 60 mm limit |
|---|---|---|---|---|---|---|
| Current plan: glass + epoxy outside, 2 coats inside | 0.45 out, 0.20 in | 3.37 kg | 31.2 kg | 118 mm | 72 mm | +4.2 kg |
| A: epoxy inside (slosh), paint outside | 0.08 out, 0.25 in | 3.14 kg | 30.6 kg | 116 mm | 74 mm | +4.7 kg |
| B: dichtol (no film), paint outside | 0.08 out | 2.93 kg | 30.2 kg | 115 mm | 75 mm | +5.1 kg |
| C: rolled epoxy + paint outside, nothing inside | 0.28 out | 3.08 kg | 30.5 kg | 116 mm | 74 mm | +4.8 kg |

The slosh figure allows a little extra for pooling. The current plan has no paint in the model. All
rows use the model's own shell maths (× 1.15 for stiffeners) and the 10 % margin.

## 8. Skip these

- **Flex Seal, Plasti Dip:** soft rubber coats. They scuff and peel at launch and leave a rough skin.
- **Spar urethane or varnish:** fine above the water, but not made to stay underwater.
- **Acetone smoothing:** an ABS trick that doesn't work on PLA. Don't thin epoxy with solvent either.
- **XTC-3D:** made for prints, but it's still a brushed two-part epoxy.
- **Polyester resin:** epoxy only, as the drawings already say.

## 9. Also before the first full hull print

- From the 10-05 journal entry: print a ~300 mm bow-end test on end (taper + rocker). It checks the
  overhangs, and how much a tall print wobbles.
- From the 10-05 journal entry: pull-test a rib-bond coupon (thickened epoxy on sanded PLA) against
  `Lid.rib_bond` (4 MPa).
- Pull-test a heat-set insert in a printed flange against `Lid.screw_pullout` (1200 N).
- Test a flat-printed coupon against `Lid.print_strength` (45 MPa); the ribs rely on it.

## Sources

- Giga, stock 0.6 mm nozzle: [3DJake listing](https://www.3djake.com/elegoo/orangestorm-giga) ·
  [Elegoo nozzle kit](https://www.elegoo.com/products/nozzle-kit-for-orangestorm-giga)
- Seam settings: [OrcaSlicer wiki](https://www.orcaslicer.com/wiki/print_settings/quality/quality_settings_seam)
- dichtol AM Hydro:
  - [Fabbaloo](https://www.fabbaloo.com/news/make-3d-prints-truly-watertight-with-diamants-dichtol-am-hydro-sealant)
  - [3DJake, 250 mL](https://www.3djake.com/diamant-polymer/dichtol-am-hydro?sai=17880)
  - [3Printr: making prints waterproof with dichtol](https://3printr.com/how-to-make-3d-printed-parts-waterproof-with-dichtol-5969153)
  - [3Printr: pore-deep impregnation](https://www.3printr.com/pore-deep-impregnation-a-new-solution-for-3d-printed-components-4862425/)
  - [DIAMANT Polymer in the USA](https://www.polyformnext.de/news-en/expansion-diamant-polymer-strengthens-its-market-presence-in-the-usa.htm)
- Roll and tip:
  - [WEST 800 roller covers](https://powerboatsupply.com/boat-supplies-accessories/paint-maintenance/west-system-products/west-system-roller-covers-2-pk-8002)
  - [Off Center Harbor: rolling and tipping](https://www.offcenterharbor.com/?p=41438)
