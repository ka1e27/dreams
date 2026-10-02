# D.R.E.A.M.S V3 — Session Journal

A running log of what each Claude Code session worked on, so a fresh chat can pick up where the
last one left off. **Read it top to bottom at the start of every session**, then **add an entry at
the top** when you finish a meaningful chunk of work.

- Newest entries go at the **top**, just under the marker below.
- Keep entries short and factual: what changed and why, not a transcript.
- This is the narrative of work in progress. Locked hardware decisions live in
  [`V3_DESIGN_BRIEF.md`](V3_DESIGN_BRIEF.md) and the KiCad files. Don't duplicate them here; link
  to them.
- **Keep at most 5 entries.** When a new entry pushes the count past 5, move the oldest to the top
  of `docs/v3/session_journal_archive.md` (create it the first time), newest first there too.
- V2's journal is archived with the rest of V2: `git show v2-final:docs/session_journal.md`.

### Entry template (copy this)

```
## YYYY-MM-DD — <short title>

**Worked on:** one or two sentences on the goal.
**Changed:**
- `path/to/file` — what and why
**Decisions / open questions:** anything left unresolved or flagged for next time.
**Next steps:** what a future session should pick up.
```

---

<!-- New entries below this line, newest first. Keep at most 5 — move older ones to
     docs/v3/session_journal_archive.md. -->

## 2026-10-02 — Outdrives fixed (no kick-up) and tight to the transom

**Worked on:** Matthew's call on the outdrive drawn for CAD on 10-01.
**From Matthew:** drop the kick-up: it isn't needed, reverse thrust works against it, and it adds parts. Make
the drive static and move it closer to the hull for strength.
**Changed:**
- `mechanical/hull_sizing.py`: `Outdrive` rewritten. The pin, cheeks, knuckle and shear screw are gone, and
  `mount_outline()`, `clearances()` and `thrust_loads()` replace `tilt_check()`.
- `drawings.py`: sheets 1, 5 and 6 redrawn.
- `concept_model.py` updated.
- `docs/solidworks_modeling_guide.md`: A5, Part E and Part C.
- `mechanical/README.md`, and the rev D note in `docs/hull_and_crossbeam_sizing.md`.
**The fixed drive (proposal):**
- **One mount**, printed ABS for now; a 6061 version can be milled later. It has:
  - a deck flange on the lid's aft deck (4× M5 up from inside, as before);
  - a 6 mm flange down the lid's aft wall, held by 2 new M5 through the wall at z 225;
  - a head block behind them that clamps the leg's top (40 mm socket, 2× M4 across) and carries the motor
    plate and the cover.
- **The leg moved 7 mm forward:** its leading edge is at x −21, 3.5 mm outside the rail's 17.5 mm
  overhang. The rail is what stops it going closer.
- **A thrust pad takes the forward thrust.** It's bonded to the tub's transom (x −19 to 0, z 120–160,
  2 mm EPDM face).
  - At 55 N bollard, the pad takes 131 N and the mount 76 N.
  - The leg bends 6.5 N m at the pad, against 11.2 N m at the mount without it.
  - Reverse thrust hangs on the mount's bolts.
  - Nothing bolts to the tub, and the leg still lifts away with the lid.
- **The motor moved forward**, now that there's no pivot to clear:
  - the can sits just behind the transom (x −38 to −6), with the plate at −6;
  - the belt plane is at x −48 and the cover runs from x −62 to +4;
  - the drive overhangs the transom by 161 mm (was 168).
- **Unchanged:** motor axis z 300, prop axis z 22, belt 205 T, leg section, pod, prop. The tightest gap is
  the wall flange, 2 mm over the rail.
**Results:**
- Design 34.3 kg, trim +1 mm, all hull and bridge SFs unchanged (≥ 3.2).
- Parts per drive went from 16 to 13.
**Committed** on `feature/mechanical-rev-d`, with a PR to `main`:
- the rev C snapshot, as it stood on 09-27;
- rev D;
- a CI workflow, `.github/workflows/mechanical.yml`, with its commands in `CONTRIBUTING.md`. It runs
  ruff, the quick build and the hull report's checks;
- this journal.
**Open:**
- Motor KV for the 12S rail (unchanged).
- Bond a test pad on a glassed coupon and load it.
- `stash@{0}` (09-29's V2 journal edits) can be dropped now that this journal is committed.
- `docs/presentations/` (the 09-25 CRWA decks, 2 MB of .pptx) is still untracked.

## 2026-10-01 — Winter moves to 2027-28; water samples come up on the winch

**Worked on:** Matthew's steer on winter work and on how water samples get collected. No design
files changed.
**From Matthew:**
- No winter testing this season; the boat may not be finished by then. The December road-salt study
  and the 09-30 winter notes (skim ice, cold Li-ion, brittle PLA, samples freezing) wait for the
  **2027-28 winter**. Checking our sensors against CRWA's (e.g. the Rt. 9 loggers) can probably be
  done by hand.
- **Water samples come up on the winch.** A closing bottle goes down on the tether, in place of the
  pod or mounted with it. It closes and seals at depth, is hauled up and rides back to shore, where
  it goes into the cooler. This takes the place of 09-30's deck cooler; no ice goes aboard.
**Findings:**
- It's CRWA's own method. The Chandler Pond QAPP (§B1) takes a probe depth profile from a canoe at
  the deepest point, plus Van Dorn bottle samples there for internal nutrient loading; profiles go
  to 0.5 m off the bottom. Its equipment table lists "Sampling device e.g., Van Dorn". A robot doing
  it still needs the QAPP amendment.
- **The limit is ~15 min to ice.** The QAPP says "immediately on ice". 40 CFR 136.3 Table II,
  footnote 2: "preserve each grab sample within 15 minutes of collection"; footnote 18 sets ≤ 6 °C.
  Its holding times: TP, TKN, ammonia and nitrate-nitrite cool + H₂SO₄, 28 d; nitrate cool, 48 h;
  orthophosphate filtered within 15 min, 48 h; TSS cool, 7 d; chloride nothing, 28 d. (The QAPP lets
  the lab acidify TP within 6 h.) With no ice aboard, the bottle must reach the cooler within
  ~15 min of closing: at 1.5 m/s that's under ~1 km after docking and decanting, and one bottle per
  trip. Put the window in the amendment.
- A Van Dorn is an intermediate container: fine for nutrients, TSS and chloride, not for E. coli
  (SOP 7.3.1.3: straight into the sterile bottle).
**Proposal:**
- **Mount the bottle on the pod** (a small CTD rosette) rather than swapping it for the pod. The
  pod's depth sensor logs where the bottle closed, the descent profile picks the depth, and the
  boat keeps one winch and one tether. Close it short of the bottom (CRWA uses 0.5 m off), since
  touching the mud spikes TSS and TP.
- **Sampler:** Van Dorn style. An opaque tube (grey PVC: TP and TSS are stored dark), open at both
  ends on the way down so it flushes, with end seals that snap shut on elastic when a pin is
  pulled. ~2 L covers TP (500 mL) + TSS (1 L). Decant into the lab's bottles on shore. Material
  rules are in the block below.
- **Trigger:** the pod's AUX pads (J10: GND, +3V3, AUX_IO = D10) can drive a micro servo's signal,
  or a MOSFET for a small solenoid, to pull the pin. The pod's 5 V is a 600 mA D36V6F5 shared with
  the XIAO and sensors, and the tether is behind F1 (0.40 A PTC), so the release is a short pulse,
  never held. Fallback with no pod power: a messenger weight dropped from the boat, as a hand-run
  Van Dorn uses.
- **At the station:** arrive heading upstream, then cut the drives, so the prop wash drifts away
  downstream.
- **Weight:** the pod is ~2.0 kg in the mass budget (1.2 + 0.8 growth). With ~1 kg of sampler and
  ~2 kg of water that's ~5 kg on the line once it leaves the water. On board it's ~3 kg vs the deck
  cooler's ~7 kg, so ~8 mm more to the lid joint (0.47 kg/mm).
**Open:**
- Does Kyle's arm still go on the boat? With the winch taking the water samples (sediment already
  had to come up on the pod), the arm is left with E. coli and surface grabs. Without it the boat
  is ~10 kg lighter, roughly back to rev C's draft, freeboard and foot-bolt SF.
- The winch's line pull isn't in the repo or the V2 docs. The moon pool has to pass pod + bottle.
- CRWA: analytes and volumes (they size the bottle), and whether a ~15 min close-to-ice window
  works for them and the lab.
- `origin/pcb/pod-rev-b` (9e7780a, 09-29) holds pod rev B, a re-placement with the same netlist.
  No PR yet. KiCad isn't installed on this laptop (checked 2026-10-01), though CLAUDE.md expects it.
**Next steps:** sketch the pod + sampler frame and the release; measure the winch's line pull; carry
the sampler into rev D of `hull_sizing.py` (no deck cooler, ~3 kg of sample aboard).

**Later the same session: CRWA's bottles, winch materials, an ice plow, and "doesn't the river keep
it cold?"**
- **CRWA's bottles (QAPP Table B3.1):** all HDPE. TP 500 mL and TSS 1 L are "pre-cleaned" (acid-washed
  in 10 % HCl), 4 °C and dark; chlorophyll a 1 L amber; E. coli 120–250 mL sterile and sealed, with
  thiosulfate; cyanobacteria 75 mL. Nutrient bottles are rinsed 3× with ambient water before filling
  (Table B4.3). E. coli bottles stay sealed until sampling (Table B4.6). Necks are standard GPI/SPI
  finishes (e.g. 53-400: 53 mm thread OD, 400 = one turn, 410 = 1.5, 415 = 2; ASTM D2911). Pace
  supplies them: get one of each, or the catalogue numbers, before designing to a neck.
- **Suggested: don't open the lab's bottle underwater.** The Van Dorn tube is the open/close
  mechanism. It flushes on the way down (the 3× rinse), and one cast covers TP + TSS. Wetted parts
  must survive a 10 % HCl wash: PVC, acrylic, HDPE, PP, silicone. No stainless (HCl pits it) and no
  printed parts in the sample path. If the boat ever fills a lab bottle directly (E. coli), use a
  valved cap on the bottle's neck finish; a vent tube reaching ~13 mm into the bottle leaves the ½ in
  of headspace.
- **Winch (suggested): a metal skeleton with printed parts.** Loads are small (~5 kg on the line with
  the sampler), so metal is for wear, heat and torque joints, not strength:
  - Metal: stainless shaft, bearings, 6061 side plates and motor mount, sheave axle, a bought
    reversing (diamond) screw for the level-wind, and a clamping hub that carries the drum torque.
  - Printed: drum core and flanges bolted to that hub, level-wind follower, fairlead body (smooth
    insert), covers.
  - Not PLA: the deck is sunny and wound cord loads the drum constantly. Use ABS, ASA or PETG.
  - Isolate aluminium from stainless (nylon washers, Tef-Gel); road salt makes it worse. The tether
    needs a strength member; the conductors should never carry the pod and a full bottle.
- **Ice plow (estimate, scratch script):** edge-loaded floating ice (σf 0.5–0.8 MPa, E 2 GPa), broken
  by a full-width 20° ramp (H/V 0.48 at μ 0.1), with clearing taken as equal to the breaking push.
  Push needed: 5 mm 18–29 N, 10 mm 44–70 N, 15 mm 72–116 N, 20 mm 104–166 N, 30 mm 172–275 N. Both belt
  drives together give ~110 N bollard (`propulsion.py` estimate, untested). So ~1 cm yes, slowly;
  1.5–2 cm only at full throttle with no margin; ≥ 3 cm no. Thrust isn't the main problem:
  - On a cat the plow must span the full 920 mm, or the strip between the hulls hits the pod and
    moon pool.
  - Broken ice slides under the hulls into the props, which hang below the keel line.
  - Cold PLA is brittle, and a thin ice edge saws at the waterline.
  - A stalled boat sits on ice too thin for anyone to walk out on.

  **Suggested:** no icebreaking. On ice days, sample from bridges or the bank. Fit a UHMW or
  aluminium stem guard now (debris, launching), with bolts that could carry a plow later.
- **Solid bow (scratch script on `hull_sizing.py`, 41.4 kg design, LCF x 0.55 m, BM_L 1.2 m):** a
  CAD-solid nose prints at the slicer's infill. At 100 %, vs a 2.4 mm shell, both bows add 0.6 kg for
  75 mm from the stem (stems sink 7 mm), 1.1 kg for 100 mm (13 mm), 2.7 kg for 150 mm (32 mm) and
  5.0 kg for 200 mm (57 mm). With ~76 mm to the lid joint against a 60 mm minimum, ~16 mm of bow-down
  trim is all there is. At 20 % infill, 200 mm adds ~1 kg (11 mm) and works as a crash block. A 1.5 kg
  full-width plow at the stem sinks it ~21 mm.
- **"If it stays in the water, doesn't it stay cold?"** Only below 6 °C. Submerged, the sample stays at
  river temperature, and in summer that's far above 6 °C, so the ~15 min to ice stands. In winter
  (0–4 °C) the river is the cooler, and the job flips to not freezing. Either way, haul it out once
  it's closed (a weeping seal would mix in water from along the route), shade it, and log the pod's
  water temperature at closing.
**Open (added):** do bottles filled from a Van Dorn still get the 3× rinse? That's ~0.5 L more, so the
tube would be ~2.5 L. Neck finishes of Pace's bottles.

**Later the same session: the tunnel stays above the water; plows on the hulls; a person with the
cooler.**
**From Matthew:**
- **The bridge stays the arch** (rev B/C gull-wing, Sonobot look). The flat deck suggested on 09-29 and
  09-30 is dropped; don't plan around it.
- Everything between the hulls (pod, sampler) sits above the water when stowed, so plows go on the two
  hulls only.
- Van Dorn sampler confirmed. No E. coli testing for now, so no sterile-bottle mechanism.
- A person with the cooler waits near the sampling area. The boat brings each sample back in time, and
  the person decants and ices it. Sampling isn't autonomous yet.
**What that means (suggested; numbers from `hull_sizing.py`'s rev C arch, draft 94–114 mm):**
- **The hub is the garage.** It has been empty since 09-30 moved the electronics and packs into the
  hulls, so the IP67 box (1.6 kg) goes. Put the winch up in the dome, a sheave over an opening in the
  hub floor between the arch frames, and a cone that stops the pod swinging. The pod and sampler pull
  up into the hub. The hub floor is 196–216 mm above the water, the arch's underside at the hub
  206–226 mm, and the hub is 240 mm tall inside (z 310–550). Pulled up, their bottoms sit ≥ ~100 mm
  above the water and nothing hangs in the tunnel.
- **The window into the hub is 254 × 311 mm:** 254 mm fore-aft between the 1/4 in frames at x 520 / 780,
  311 mm across where the cowl narrows at its floor (377 mm above the frame tops at z 370).
- **Horizontal Van Dorn sized to that window**, lying athwartships. 2 L in 5 in PVC (ID ~128 mm) is
  155 mm inside, about 210 mm with the end seals. 1.5 L in 4 in (ID ~102 mm) is 182 mm inside.
  2 L in 4 in (243 mm inside, ~290 mm with seals) only fits if the cowl's floor is widened. It suits
  shallow water and samples near the bottom. It barely flushes on the way down, so hold it open at
  depth for about a minute before closing.
- The arch structure is 3.3 kg in the model (frames 1.0, feet 1.0, fairings 0.7, cowl 0.6). Dropping the
  IP67 box pays back half of it. If Kyle's arm stays on the hub top, its base bolts to the frames, not
  the printed cowl.
- **Hull plows:** the stems are near-vertical at the waterline, so each plow adds a ~20–25° ramp there
  (from ~40 mm below the waterline to ~50 mm above). Ice resists a narrow push about as hard as a
  wide one, so the limits stay: ~1 cm comfortable, 1.5–2 cm at full throttle. Bolt the plows into the
  solid nose, using a slicer modifier to print 100 % around the bolts and ~20 % elsewhere. Each prop
  sits right behind its hull and still takes that hull's broken ice: add guard rings, which also
  shed weed.
- **Operator in the loop:** the operator closes the bottle (RC switch → Teensy → RS-485 → a pulse on
  the pod's AUX). The pod logs depth, water temperature and time at closing. First test the Van Dorn
  by hand off a dock with a pull-cord trigger (seals, soak time, decanting), then move it onto the
  pod.
**Open (added):** the pod's real size; it and the sampler have to pass the 254 × 311 mm window.

**Later the same session: rev D of the design model and the drawings (the arch, the hub garage, the
outdrive drawn for CAD).**
**From Matthew:** update the CAD drawing PDF to match the arch, and make the propeller-motor drive easier
to read for CAD.
**Changed** (`mechanical/` and `docs/` are untracked; rev C survives only in this session's scratchpad):
- `mechanical/hull_sizing.py` → rev D:
  - Hull: PLA (2.4 mm walls, epoxy inside), printed on the Giga in 3 segments split at x 520 / 780
    (`split_x`), with the ribs at J1 / J2.
  - Packs and electronics move into the hulls, using the 09-29 Li-ion estimates: 12S drive pack in the
    port hull; 5S electronics + winch packs and the Pi + carrier in the stbd hull; one VESC per hull by
    its outdrive.
  - The hub becomes the garage: floor opening, sheave, winch envelope, pod, a 2 L Van Dorn and a 2 L
    sample. The IP67 box is gone.
  - The outdrive is redrawn (below) and gets a `tilt_check()`.
- `mechanical/drawings.py`: 7 sheets.
  - 1: GA
  - 2: lines (3 PLA segments)
  - 3: frame, foot and rib details, plus the hub garage in plan, side and from astern
  - 4: rail joint, plus inside the tubs (plan, sections, wiring, heat)
  - 5: outdrive assembled, 1:2: side view with ordinates and the 70° ghost, from astern, from above,
    key-points table, balloon list
  - 6: outdrive part by part: bracket, tilt head, motor plate, cover, leg + pod half, section A-A, shaft,
    purchased parts, notes, modeling order
  - 7: the body plan aid
- Also: `concept_model.py` (new outdrive, pod + Van Dorn in the hub), `propulsion.py` (12S pack energy),
  `mechanical/README.md`, `docs/solidworks_modeling_guide.md` (rev D), and a rev D note at the top of
  `docs/hull_and_crossbeam_sizing.md` (its body is still rev C). `build_all.py` runs clean.
**Result (proposal, no arm):**
- Design 34.3 kg (bridge 12.9, hulls 21.4), draft 99 mm, 91 mm to the lid joint, trim +1 mm.
- +15 kg of payload before the lid joint gets within 60 mm of the water, so Kyle's ~10 kg arm still
  fits if it stays.
- SFs: frames 5.0, foot bolts 3.2, lid rib 4.3, rail 4.4.
- Garage: the 240 × 301 opening passes the pod + Van Dorn with 30 / 70 mm to spare; stowed bottom
  186 mm above the DWL; the winch fits with 70 mm. Belt 205 T (615 mm), prop axis z 22.
**Found: the rev C outdrive couldn't kick up.**
- As drawn on sheet 4, its cover sat 35 mm forward of the pin, just above the bracket. It hit the
  cheeks at 2°, and the deck plate at 13° even with the cheeks outboard. The 3D model's cover
  overlapped the bracket at rest.
- Rev D puts the motor behind the pin: can at x −97 to −65, plate at −101, shaft forward to the upper
  pulley at −55.
- Everything that tilts stays within ±35, with the cheeks outboard at ±36 to 44.
- A nose rests on an EPDM pad on the lid's aft wall; forward thrust and the drive's weight hold it there.
- A nylon M5 shear screw holds against reverse thrust (~7 N m) and breaks near ~20 N m.
- `tilt_check()` sweeps it: clear to 75°.
- Unchanged: pin (−30, 262), belt plane −55, motor axis 300, leg, pod, prop.
- Changed: the bracket is 88 wide (bolts at y ±30), and the aft bearing moved to the pod's tail so the
  prop thrusts on it.
**Open (added):**
- Motor KV: V3's drive rail is 12S, and rev C's 380 KV (picked for 18 V) would run at ~10–25 % duty.
  ~150–200 KV suits 12S; most such motors are 50xx (~55 dia), which fits the cover if the motor axis
  goes up ~5 mm. Matthew's pick.
- Placeholders until sized: the winch envelope, the pod, the Van Dorn.
- Commit `mechanical/` + `docs/` (rev C first from the backup, then rev D) on a `docs/` branch.

## 2026-09-30 — Hull decision: back to rev C's curved, hollow hulls, printed in PLA and sealed

**Worked on:** Matthew's call on the 09-29 proposals. No design files changed.
**Decided (Matthew):**
- Hulls stay **curved and hollow** (rev C shape: open tub + screwed lid on a gasket). The 09-29 solid
  XPS suggestion is dropped. The reason is new: the **electronics, and later the water/sediment
  samples, go inside the hulls.** Rev C put everything in the hub and kept the tubs empty.
- **First build is printed PLA, sealed** (the "printed PLA route" under 09-29's waterproofing).
- Foam + fibreglass is parked for a later hull. If it comes back it has to stay hollow too, so it
  would be a glass/foam sandwich or a layup over a printed plug, not a solid foam block.
**What this changes (to work through next):**
- Access: a lid held by ~30 M4 screws is fine for electronics but not for pulling samples every
  run. Plan a screw-in deck hatch (4–6 in inspection port) in each lid over the sample bay.
- Heat: VESCs and packs in a sealed PLA hull (PLA softens 55–60 °C). Mount them to an aluminium
  plate on the hull bottom so the water sinks the heat, keep them off the walls, and log hull temp.
- Samples need ≤ 6 °C: river water in summer won't do it, so there's still an insulated box with ice packs.
- Weight moves down into the hulls: lower CG, and the bridge feet carry less. That should help
  the foot-bolt SF (2.7 with the arm on 09-29; target 3). Re-run to confirm.
- Hull-to-hull and hull-to-deck wiring goes through cable glands in the lids. The hull-leak
  inputs are useful again: they are **J8 / J9** on the rev D schematic (J10 is the winch ESC; the
  09-29 entry had them off by one).
- Still open: arch bridge or flat deck. With nothing left in the hub, the flat deck is simpler.
**Next steps:** update `hull_sizing.py` to a rev D: PLA density, Giga print fit (3 tub + 3 lid
segments split at x 520 / 780), Li-ion packs, electronics and sample bay in the hulls, arm on the deck,
and a lid hatch. Then re-run the freeboard, trim and joint SFs, and update the hull doc. Before the
full build, print, seal and soak a test segment for a week.

**Later the same session: the sample bay.** Matthew's idea: a servo door (or an open port) that the
arm drops samples through, into a bay kept apart from the electronics. It replaces the lid hatch
above. Numbers are from a scratch script on `hull_sizing.py` (unchanged); the layout assumes the
flat deck, with crossbeams at x 520 / 780.
- **Where (suggested):** the middle segment (x 520–780) of one hull, between the crossbeams and
  right beside the arm. The lid top there is clear for 222 mm and flat for 121 mm.
- **Separation (suggested):** an insulated box (20 mm XPS, epoxy-coated inside) bonded under a door
  collar in the lid. The box is the only wet space, so the rest of the hull stays one dry space and
  no printed joint has to seal. The foam also stops a cold wall sweating onto the electronics.
- **Door:** ~120 × 210 mm, clear opening ~100 × 190 mm inside a 10 mm coaming. Hinged on the
  outboard edge so it opens away from the arm. A waterproof servo inside the box drives an
  over-centre toggle that locks the door down on a foam gasket, with no holding current; a Hall
  sensor confirms "closed". The door only needs to be splash-proof and hold the cold, because the box
  walls keep the electronics dry. The fallback is a spring flap the bottle pushes open.
- **Capacity:** inside the foam ≈ 214 × 140 × 200 mm (~6 L). The opening is ~100 wide, so bottles
  stand in one fore-aft row: ~3 × 250 mL or ~4 × 125 mL. The row is a rack that lifts out through
  the door and goes straight into CRWA's cooler. For more bottles, add a second bay in the other
  hull, or a sliding rack under a fixed port.
- **Cold:** about 20 mm XPS leaks ~8–10 W at ΔT 25 K. Chilling a 250 mL sample from 22 °C takes
  ~19 kJ. So ~1–1.5 kg of ice packs under the rack covers a 4–6 h run. Log the bay temperature for
  the lab.
- **Balance:** a loaded bay (~2.5–3.5 kg with ice) heels the boat ~1° (≈ 9.7 N·m per degree). The
  12S drive pack (2.7 kg) in the other hull's middle segment cancels most of it.
- **Control:** carrier rev D has no servo header. Teensy pins 2, 3 and 29 (PWM-capable) and 14 / 15
  (analog) carry no-connect flags, so a 3-pin header is an easy rev E add. Suggested for now: the
  arm's controller runs the door, powered from the arm's pack. The carrier's 5 V rail carries the Pi.
- **Leak probes (J8 / J9)** go in the dry bays. The sample bay will always be damp.
**Open:**
- CRWA's bottle sizes and how many samples a run needs.
- How the bottles get capped: gripper, snap caps, or a fixed capping post.
- Kyle's reach. From a flat deck it's ~350 mm out and ~100 mm down to the door, and ~350 mm down to
  hold a bottle 15 cm under the surface. The arch hub would put the arm ~250 mm higher.

**Later the same session: CRWA's sample-handling rules.** Our CRWA contact sent CRWA's QAPP for its Chandler
Pond project (AquaQAPP, effective May 2026 – June 2027; `Downloads\Water Quality Assessment of
Chandler Pond_FINAL.docx`, not in the repo). The notes below come from it and its attached
collection SOP, plus CRWA's volunteer manual (18th ed., 2022, linked from crwa.org/vmm).
- **Cold is required.** Every sample goes "immediately on ice to 4 °C", and nutrients and chlorophyll
  are also kept dark. The lab checks the cooler on arrival with a temperature blank. A warm nutrient
  sample is flagged suspect; a warm E. coli sample is discarded and recollected.
- **The clock is tighter than the temperature.** E. coli and cyanobacteria must be processed within
  6 h of collection, and total phosphorus acidified at the lab within 6 h. TSS allows 7 days and
  unfiltered chlorophyll a 24 h. The QAPP's QC table says to take the bacteria sample at the last
  stop to shorten the hold. These replace the rough 40 CFR 136 figures in the 09-29 entry.
- **The chain today:**
  - Volunteers carry a small cooler with their own ice pack, then cap and ice each bottle right away.
  - They drive straight to a drop-off point.
  - CRWA staff check the bottles and chain-of-custody forms, relabel them, re-ice them at 4 °C and
    drive the coolers to a contracted lab. Chandler Pond uses Pace Analytical (Westborough); the 2022
    manual sends the monthly program's samples to the MWRA lab on Deer Island.
  - CRWA itself only does cyanobacteria counts and turbidity.
- **Bottles (QAPP Table B3.1):** E. coli 120–250 mL sterile HDPE with thiosulfate; cyanobacteria
  75 mL; TP 500 mL; TSS 1 L; chlorophyll a 1 L amber. A full set is ~2.8 L per site. The bay above
  only takes the small bottles.
- **Boat grab procedure (SOP 7.3.1.3)**, which the arm would have to copy:
  - Drives off and drifting.
  - Sample on the upstream side, away from water that has touched the hull.
  - Keep the bottle capped until filling, and never touch the inside of the cap or neck.
  - Plunge it neck-down, then turn it ~45° into the current (push it forward in still water), with
    the mouth ~15 cm under the surface.
  - Leave ~1/2 in of headspace. Don't rinse the bottle.
  - Cap it at once, ice it at once, and log the exact time.
  - Bacteria go straight into the sterile bottle, with no intermediate container.
- **Approval:** DEP pre-approves an AquaQAPP only while its methods are unchanged, so robot
  collection needs a QAPP amendment and DEP review before the data counts. The QAPP's own check is
  field duplicates (≤ 20 % RPD for most analytes), so a pilot could have the boat take duplicates
  side by side with CRWA staff.
- **Pod fit:** the once-a-year mid-pond station is the pod-and-winch job: a depth profile from a canoe
  to 0.5 m off the bottom, plus a Van Dorn bottle at the bottom for internal phosphorus loading.
  Sensor targets: DO ±0.2 mg/L, pH ±0.2, temperature ±0.1 °C, conductivity ±0.5 % + 1 µS/cm, with a
  logged calibration before and after each trip.
**Open:**
- Can the lab take smaller TP, TSS and chlorophyll volumes?
- Would CRWA pilot on Chandler Pond? It's a calm 10.8-acre pond with a monthly program running now.

**Later the same session: the Muddy River is the design target; nutrients and road salt.**
**Decided (Matthew):**
- The Muddy River area is the primary target the design is sized around for now.
- Onboard samples will be mostly nutrients, with little or no E. coli. Ice goes aboard only on
  sampling days. How often CRWA wants samples is still unknown.
- New study: how December road salting affects the river. CRWA already logs conductivity and
  temperature every 15 min above and below Rt. 9 on the Muddy River (2026), and preliminary chloride
  is above EPA criteria (muddyrivermmoc.org). The boat adds what two fixed loggers can't:
  - maps between them and near outfalls;
  - bottom profiles, since salty meltwater sinks and pools in ponds and slow reaches;
  - runs right after a salting or melt.
**What this changes (proposal):**
- **Sample storage:** nutrient bottles are 500 mL–1 L (a 1 L bottle is ~9–10 cm across and > 20 cm
  tall). That's too big for the hull door (121 mm flat top, ~19 cm clear inside the insulation).
  Suggested: a removable insulated cooler on the flat deck beside the arm. It takes ice only on sample
  days and is lifted off and handed to CRWA at the end. The hull bay stays an option for small
  bottles. This needs the flat deck.
- **Hold times still bite:** TP must reach the lab within 6 h (Chandler Pond QAPP) unless it's
  acidified or frozen. TSS allows 7 days. Chloride needs no preservation and keeps 28 days
  (40 CFR 136), so it's the easiest first robot-sample pilot.
- **Weight:** ~4 L of samples + ~2 kg of ice + the cooler ≈ 7 kg, which is ~15 mm more draft
  (0.47 kg/mm). The 09-29 budget allowed 5 kg; with printed hulls this lands at the 60 mm
  lid-joint limit. Re-check it in rev D.
- **Conductivity sensor:** the pod's DFRobot SEN0244 reads 0–1000 ppm TDS (~0–2000 µS/cm) at ±10 %
  of full scale. CRWA's action limit is 994 µS/cm, and salt pulses in urban streams and pond bottoms
  run to thousands, even tens of thousands, of µS/cm. So for the salt study the EC upgrade comes
  first: an Atlas EZO-EC with a K 1.0 probe (5–200,000 µS/cm, ±2 %, rated from 1 °C). Validate it
  by parking the pod beside CRWA's Rt. 9 loggers.
- **Winter operation:**
  - Water near 0 °C and possible skim ice; the boat can't run in ice.
  - Li-ion loses capacity in the cold and must never be charged below 0 °C; keep the packs in the
    insulated hulls.
  - PLA gets more brittle in the cold.
  - In December the sample box's job flips to keeping the samples from freezing, with no ice.
**Open:**
- How often CRWA wants samples, and which nutrient analytes and volumes.
- Muddy River site data: depths, bridge and culvert clearances, launch points, where it ices over.
- The flat deck is still unconfirmed.

## 2026-09-29 — V3 sync + this journal; PLA-only hull waterproofing; 20 lb arm and Li-ion mass check

**Worked on:** synced this clone to V3 and started this journal. Matthew's inputs for the hull:
- The hulls must be printed in **PLA** on an **Elegoo OrangeStorm Giga** (800 × 800 × 1000 mm).
  How do we waterproof them, and how would a foam + fibreglass hull work instead?
- Keep the **220 mm** hulls for now, or go smaller?
- The packs will probably be **Li-ion instead of M18**, and a **robot arm of about 20 lb (9.1 kg)**
  goes on the boat.

**Changed:**
- Local `main` fast-forwarded 7a4124b → 5b3b610 (V3 clean slate; V2 at `v2-final`). The four
  uncommitted V2-journal entries (09-23 to 09-27) are carried below verbatim. The original edits are
  also in `stash@{0}`; drop it once this file is committed.
- `docs/v3/session_journal.md` (new, this file). `CLAUDE.md` and `docs/v3/README.md` now point to it.
- No design files changed. The numbers below come from a scratch script that imports
  `mechanical/hull_sizing.py` and `propulsion.py` unchanged. It swaps the M18s for Li-ion packs
  (12S ~10 Ah LiPo 2.7 kg, 5S2P electronics 0.85 kg, 5S winch 0.70 kg), adds the arm (9.07 kg plus
  0.8 kg of base plate and driver, on the hub at x 610, CG z 450) and uses PLA density for the shells.

**Result (proposal; 220 mm hulls, 10 % margin, fresh water):**

| | Rev C (M18, no arm) | Li-ion + arm, printed PLA + lid | Li-ion + arm, sealed XPS + glass |
|---|---|---|---|
| Design mass | 32.0 kg | 41.4 kg | 35.6 kg |
| Draft | 94 mm | 114 mm | 102 mm |
| Freeboard to lid joint / deck | 96 / 156 mm | 76 / 136 mm | no joint / 148 mm |
| Reserve buoyancy | 222 % | 149 % | 190 % |
| Both drives @ 1.5 m/s | 89 W | 110 W | 97 W |
| Foot-bolt SF, rev C model (target 3) | 3.5 | **2.7** | 3.1 |

- **Width:** with the arm, 152 mm fails (45 mm to the joint; 5 kg over the 60 mm-to-joint limit),
  190 mm is marginal (65 mm, +2 kg), 220 mm keeps +7 kg and 250 mm +13 kg. **Stay at 220; don't
  go smaller.**
- **A one-piece hull doesn't fit the Giga.** Standing on end needs LOA ≤ ~980 mm. At 220 wide that
  floats with 53 mm to the joint (fails); even 300 wide needs ~2× the power at 1.5 m/s (229 vs
  110 W), because a shorter hull runs at a higher Froude number. Keep 1300 and print each tub (and
  lid) in **3 pieces split at the frame stations (x 520 / 780)**, each standing on its bulkhead.
  Glass over the seams so they stop being leak paths.
- **Arm placement:** keep it between the arch frames. At x 1000 / 1200 it trims the bow down
  160 / 230 mm, and at 1200 the foot-bolt SF falls to 2.1. Reaching out, it heels the boat 3° (arm
  CG 0.3 m outboard) to 8.5° (CG 0.6 m out + 2 kg at 0.9 m). Rev C's rail joint goes under at
  12.5°; a sealed hull's deck edge at 23–25°.
- **PLA:** ~4.4 kg per hull (tub, lid, rail), roughly 33–80 h of printing per hull depending on flow
  rate. It still softens at 55–60 °C (why the rev C doc said "PLA is out"): paint it a light colour
  and never leave it in a hot car.
- **Drive endurance @ 1.5 m/s:** ~3.6 h printed / ~4.1 h XPS from ~400 Wh usable, vs 4.4 h in rev C.

**Waterproofing (proposal):**
- **Printed PLA route:** 0.6–0.8 mm nozzle, ≥ 4 walls (~2.4 mm), +3–5 % flow and a hot nozzle for
  layer fusion. Bond the segment spigots with thickened epoxy. Glass the outside (1 × 200 g/m²
  E-glass overall, a second layer on the keel, chines and stem) and give the inside 2 coats of epoxy.
  XPS blocks in the bow and stern bays keep a holed hull afloat. Epoxy only, no polyester. Mix small
  batches with slow hardener: the exotherm can pass PLA's 55–60 °C. Because the tub prints on end,
  layer lines cross the rail gasket, so epoxy-coat and sand the flange and groove, or use closed-cell
  EPDM foam tape. Float each hull for 24 h, or pressurize it gently (≤ 0.03 bar, a water manometer)
  with soapy water on the seams, before fitting anything.
- **XPS foam + glass route:** insulation-board XPS (~28 kg/m³) glued with epoxy, never solvent
  adhesive. Hot-wire cut it to section templates from `mechanical/cad/` (printed on the Giga), then
  sand to the R50 radii. Bond in hardpoints (G10, marine ply or solid PLA with inserts) where the
  feet and outdrives bolt. Then 2 × 200 g/m² glass + epoxy, peel ply, fill, fair, light paint. The
  solid core can't sink, has no gasket and weighs ~2.4 kg per hull vs ~5.0 kg printed with a lid. It
  gives up the inside space (nothing lives in the hulls; it's all in the hub) and rev C's openable
  lid, and the bridge feet bolt down into the hardpoints from above.
- **Suggested:** XPS + glass hulls, with the Giga making the templates, hardpoints, hub cowl,
  fairings and outdrive parts. The printed hull is the fallback. This reverses rev C's openable
  hulls, so it's Matthew's call.

**Decisions / open questions:**
- Decided (Matthew): 220 mm hulls for now. The numbers back it.
- Construction route: XPS + glass, or printed PLA + glass?
- The arm: model, reach, payload, mount point, power and control. Carrier rev D has no arm
  connector or power domain, so the arm needs its own pack and fuse, and probably talks to the Pi
  over USB or Ethernet (or joins the CAN bus).
- Packs: Li-ion or LiPo, and what capacities? The board expects a 12S drive pack and 15–21 V
  electronics and winch packs. J14 is still labelled "XT60 M18 WINCH", but any 5S pack fits it.
- With solid hulls, the hull-leak inputs (J9 / J10) have nothing to watch; they could move to the
  hub box.
- Material: is PLA really the only option on the Giga? Its 300 °C hotend prints PETG (softens
  ~80 °C). ASA and ABS warp badly at this size without an enclosure.
- If the hulls stay printed, the foot bolting needs rework (backing plates or M8) to get back to
  SF ≥ 3 with the arm.
- `mechanical/`, `docs/hull_and_crossbeam_sizing.md` and `docs/solidworks_modeling_guide.md` are
  still untracked and still say V2, Ultimaker S5, PETG/ASA and M18.

**Next steps:** Matthew picks the construction route, gets the arm's specs and confirms the material
rule. Then update `hull_sizing.py` (arm item, Li-ion packs, Giga print fit, a sealed-hull option)
and the hull doc, commit `mechanical/` and the docs on a `docs/` branch, and drop `stash@{0}`. Before
building, glass a printed PLA panel and an XPS coupon and soak both for a week.

**Later the same session: the frame pick.** Matthew asked for the easiest and cheapest frame. New
input: the arm is Kyle's personal project, and it should grab water or sediment samples from the
boat or the pod and store them on board for CRWA to test later.
- **Suggested:** sealed XPS + glass hulls, and a **flat deck on two straight 1.5 × 1/8 in 6061
  square-tube crossbeams** in place of the arch. On the rev C portal loads with the arm and 5 kg of
  samples (worst 177 N·m per beam), the yield SF is 2.9 for 1 in tube, 4.9 for 1.25 in and 7.5 for
  1.5 in. The 1.5 in tube is also the stiffest base for the arm.
- **Rough cost, both hulls + bridge:**
  - Foam hulls ~$400–500 (XPS $54/sheet × 2, 6 oz cloth, epoxy, consumables, hot wire, paint).
  - Flat deck ~$150–200 (tube, ply deck, clamps, an off-the-shelf waterproof case).
  - Printed hulls cost about the same in cash, but add ~100 h of printing and a ~3 m gasket per hull.
  - The arch adds waterjet plates, a multi-piece printed cowl and a custom-size IP67 box.
- **Numbers with the arm + 5 kg of samples and cooler:** XPS + flat deck 41.2 kg, draft 114 mm,
  136 mm of freeboard to the deck, 110 W at 1.5 m/s. Printed + lid + arch would be 46.4 kg with 65 mm
  to the lid joint (limit 60).
- **Layout:**
  - A deck plate between the crossbeams near x 600–700, with a moon-pool hole for the winch tether.
  - The arm beside the hole, and a cooler (ice packs, printed bottle rack) within its reach.
  - The electronics box and packs placed to trim the boat.
  - The arm is a bolt-on module (4-bolt plate, its own fused pack, one USB/Ethernet cable to the Pi),
    so the boat surveys fine without it.
- **Samples for CRWA:**
  - Keep them ≤ 6 °C and dark. Holding times are ~8 h for E. coli and ~48 h for nitrate and
    orthophosphate (40 CFR 136).
  - Use the lab's bottles, and log each sample's ID, time, GPS and depth.
  - Sediment has to come up on the pod, because the arm can't reach the bottom.
- **Open:**
  - Matthew's go-ahead on dropping the arch (the Sonobot look) and the openable hulls.
  - Ask our CRWA contact which analytes and bottles CRWA wants, and whether they accept robot-collected
    samples.
  - Kyle's arm specs.
  - A sampler on the pod.

> **Carried over from the V2 journal on 2026-09-29.** The entries below were written before this
> clone was synced to V3 (09-23, 09-25 and 09-26 are now in the archive). Paths into `pi5/`, `firmware/`,
> `dashboard/`, `cloud/` and the old `docs/*.md` now live at `v2-final`. The `mechanical/` files and
> hull docs they mention are untracked in this tree.

## 2026-09-27 — V2 rev C: hull lids, bolted feet, V1-style belt outdrive, 6 in hull check

**Worked on:** Matthew's three changes. (1) The M200s cost too much: go back to V1's drive, a deck motor
with a belt down to the prop shaft. (2) Openable hulls: a lid that goes over the gunwale to seal, with
the bridge screwed into the lids from underneath. (3) Buoyancy now vs 6 in wide hulls.
**Changed (all untracked):**
- `mechanical/hull_sizing.py` — new `Lid` (`Hull.lid`: joint plane z 190, 15 mm rail flanges,
  3 mm cord in a 5 × 2.2 groove, M4 screws outboard of the gasket, 8 mm lid ribs at J2/J3) and
  `Outdrive` (`Boat.drive`). Feet now bolt from inside the lid: 8× M6 per foot through rib bosses. The
  latch/receiver fields are gone. `section_points(part="tub"|"lid")`, new foot/rib/rail joint checks,
  a buoyancy table, and `--beam` / `--compare` for other hull widths.
- `mechanical/propulsion.py` — belt outdrive is the baseline row (κ 0.46, bollard estimated), cost
  column, appendage drag from the leg + pod, `--beam`.
- `mechanical/toroidal_prop.py` — `--hub shaft` (default: 20 mm hub, D-bore for a 5 mm shaft, M5
  nylock) or `--hub m200`. Folder names end in `_shaft` / `_m200`, and the old folders were
  deleted. The thrust stand now holds an outdrive.
- `mechanical/drawings.py` (rev C, new sheet 4: rail joint + outdrive; sheet 5: each hull section on its
  own, body plan colour-coded to match), `mechanical/concept_model.py`
  (tub/lid/rail, outdrives, toroidal props), `mechanical/build_all.py`, `mechanical/README.md`.
- `docs/hull_and_crossbeam_sizing.md` (rev C), `docs/solidworks_modeling_guide.md` (tub/lid split,
  Lip/Groove, rib bosses, Part E outdrive).
**Result (proposal):**
- 32.0 kg design (+2.4 kg, mostly the rail), draft 94 mm, 96 mm freeboard to the lid joint.
- Total buoyancy 103 kg, reserve 223 %.
- Joint SFs: foot bolts 3.5, lid rib 4.7, rail screws 4.7. The bosses run full depth with
  counterbored heads, so the rib isn't notched. The pod and prop were moved 10 mm aft to clear the leg.
- Belt drives ~$140–200 for both vs ~$390–410 for M200s, at ~8 % more power (89 vs 82 W at 1.5 m/s).
- 6 in hulls: 73 kg buoyancy, 116 mm draft, only 74 mm to the joint (+5 kg payload to keep 60 mm),
  16 % less drag. But the 140 mm feet don't fit the 84 mm flat deck.
**Decisions / open questions:** 6 in vs 220 (suggested ~190 as a middle ground); the drive packs
could now ride in the hulls; pull-test a printed rib boss and a flange insert; confirm the outdrive's
κ / bollard on the stand. The drive-bus approval from rev B is still pending.
**Next steps:** Matthew picks the hull width; source the motor, belts and pulleys (or reuse V1's); test-print
a rail joint section and a lid-rib boss; model in SolidWorks per the guide.

<!-- Older entries: V2-era sessions live at `git show v2-final:docs/session_journal.md` and
     `v2-final:docs/session_journal_archive.md`. -->
