# V3 mechanical design: Matthew's rev D

Matthew's hull, bridge and drive design, from 2026-09-26 to 2026-10-02. The design tools are in
`mechanical/`, with their drawings, renders and props, beside two design docs
(`docs/hull_and_crossbeam_sizing.md` and `docs/solidworks_modeling_guide.md`). The tools have moved on
to rev E (2026-10-05: 940 mm hulls, each tub and lid printed in one piece); this file keeps rev D's
decisions, numbers and open questions.

**Status: proposal.** Matthew's own status line was "nothing here is locked". Every number below is
an estimate from his design model (`mechanical/hull_sizing.py` and `propulsion.py`), not a test.
Where a newer decision disagrees, §1 says so, and the newer decision wins.

## 1. Newer decisions that override rev D

Settle these before anyone models the boat in CAD from the rev D drawings.

| Topic | Rev D says | Now | What it means |
|---|---|---|---|
| **Hull length and printing** | 1300 mm hulls, each tub and lid in 3 segments (520 / 260 / 520 mm), split at the frames, printed on end on the Giga (800 × 800 × 1000 mm) | Each hull printed in one piece on the Giga, **985 mm long** (Kyle, 2026-10-14, to confirm) | 985 mm fits the Giga on end with 15 mm to spare. But rev D's layout is drawn for 1300 mm, and Matthew's model says a 985 mm hull sits deeper, leaves less payload and needs ~45 % more power at cruise (§5.5). Move the frames, hub and packs to suit, and re-run trim and the SF checks, before CAD |
| **Sealing** | Glassed outside (200 g/m² E-glass, a second layer on keel, chines and stem), 2 coats of epoxy inside | Epoxy only, no fibreglass, on the first boat (Kyle, 2026-10-14) | Use the printing and epoxy steps in §5.1 without the glass. Rev D used the glass to cover the segment seams, so the soak test matters more |
| **Outdrive mount** | Printed ABS for now; mill a 6061 one later | Motor mounts machined from metal (Kyle, 2026-10-14) | Go straight to the metal version of the mount in §4.3 |
| **Pod** | A 1.2 kg "V1-style box" placeholder | Probably not 3D printed, since it must be very watertight (Kyle, 2026-10-14) | Re-weigh it and check its size against the 240 × 301 mm garage opening once it's designed |
| **Electronics** | Pi 5 on the carrier with a Teensy 4.1 | The carrier (rev F) uses two Pico 2s; the V3.1 starter uses one | The boat starts on V3.1 (next row) |
| **Battery** | Three packs, as the carrier is wired: a 12S ~10 Ah drive pack in the port hull, and 15–21 V electronics and winch packs in the starboard hull | **V3.1: one 10S 10 Ah Li-ion pack** (30–42 V, ~360 Wh) runs everything. **Full V3: two 10S 10 Ah packs in parallel,** plus an optional 4S Li-ion backup for the electronics (Kyle, 2026-10-14). Carrier rev F is built for this (§1.1) | Redo the mass budget and trim for the packs, and pick their hulls. Rough run time on the 985 mm hull (§5.5), from ~325 Wh usable per pack and counting ~35 W of electronics (about 2 A at 15–21 V, brief §2): V3.1 ~5 h at 1.0 m/s and ~1.9 h at 1.5 m/s; full V3 about double |
| **Drive power** | ~94 W for both drives at 1.5 m/s, ~381 W at 3 m/s, ~110 N bollard | Kyle sized V3's drive at 200–300 W per side, belt-driven motors on deck (week of Oct 5) | Same layout. Kyle's figure leaves more headroom than rev D's estimate |
| **Drive motor and controller** | Rev C's 380 KV outrunner, picked for 18 V; the KV for 12S left open (§7) | **Picked** (Kyle, 2026-10-14), two of each: a Flipsky Battle Hardened 5048 200KV 1300 W sensored outrunner, on a Flipsky Mini FSESC4.20 50A (VESC 4.12 based, aluminium heat sink) | On the 10S pack, 200 KV gives ~7,200 rpm unloaded at 36 V nominal and ~6,000 near empty (30 V). Rev D needs ~3,900 rpm at the prop for 3 m/s through its 1:1 belt, so there's headroom. Rev D's 150–200 KV range was for 12S, which is ~185–245 KV at 10S, so 200 KV sits inside it. The controller's 8–60 V (3–13S) covers 10S, and it talks CAN. Raise the motor axis ~5 mm so the 50 mm can fits the cover, and match the motor pulley's bore to the shaft (not confirmed yet) |
| **Test site** | Muddy River as the design target (Matthew, 2026-09-30) | Confirmed with CRWA: water temperature and depth on the Muddy River where people can't walk; water testing from the thaw, about March 2027; CRWA only uses data from sensors that meet NIST standards (Kyle, 2026-10-14) | Agrees. Any sensor upgrade in §6 has to meet the NIST rule |

### 1.1 Two 10S packs on the carrier (rev F)

Rev E was designed for a 12S drive pack plus two separate 15–21 V packs, and its electronics and
winch inputs couldn't take 10S (24 V TVSs, a -40 V winch P-FET, a pod built for 12–21 V on the
tether). Rev F (2026-10-14, Kyle's picks) fixes that:

- **One 10S bus.** The two packs join in parallel and feed the drives, J13 (electronics) and J14
  (winch). Join them only at matching voltage.
- **Rated for 42 V:** SMBJ43A TVSs (D3, D4), a SUP90P06-09L winch P-FET (Q1, -60 V), 100 µF 63 V bulk
  caps.
- **+15V from U15** (Pololu D36V6F15) for the A4988 stepper (which tops out at 35 V) and, through F1,
  the pod tether. 600 mA in all, so the stepper gets about 0.45 A.
- **Optional 4S backup on J18** (underside, plug from below), diode-ORed with the 10S rail into the
  5 V buck. It only keeps the Pi, Picos, sensors and radios up while the 10S bus is off.

The details are in `Boat_PCB/CLAUDE.md` and `docs/v3/V3_DESIGN_BRIEF.md`.

## 2. Decided by Matthew

- **Look:** the EvoLogics Sonobot 5. Two pontoon hulls and a gull-wing bridge arching hull to hull,
  radios at the top (09-26). **The arch stays;** the flat deck suggested on 09-29 and 09-30 was
  dropped (10-01).
- **Hull width: 220 mm.** Don't go smaller (09-29, backed by the numbers in §5.4).
- **Hulls are curved and hollow:** an open tub with a lid screwed down on a gasket. The electronics,
  packs, and later the samples, go inside the hulls (09-30). Solid foam hulls were dropped.
- **First build: printed PLA, sealed** (09-30). A foam and fibreglass hull is parked for later, and
  would have to stay hollow too (a sandwich or a layup over a printed plug).
- **Drive: V1-style belt outdrive**, a brushless motor above the water with a belt down to the prop
  shaft. It replaced Blue Robotics M200 thrusters, which cost too much (09-27).
- **Fixed outdrives, no kick-up** (10-02). It isn't needed, reverse thrust works against it, and it
  adds parts. Mount the drive close to the hull for strength.
- **Water samples come up on the winch** in a Van Dorn style bottle, not on a robot arm (10-01). No
  E. coli testing for now, so no sterile-bottle mechanism.
- **Sampling has a person in the loop.** Someone with a cooler waits near the sampling area. The
  boat brings each sample back in time, and the person decants and ices it. It isn't autonomous yet.
- **The Muddy River area is the design target** (09-30). Onboard samples are mostly nutrients.
- **No winter testing this season.** The December road-salt study and the winter notes in §6.4 wait
  for the 2027–28 winter. Checking our sensors against CRWA's loggers can probably be done by hand.

## 3. Rev D at a glance

| | Value |
|---|---|
| Hulls | 1300 × 220 × 250 mm each (255 over the rail), 700 mm apart on centre, 480 mm clear tunnel, 920 mm overall (955 over the rails) |
| Hull shape | 12° deadrise, R50 chine and deck edge; bow taper from 650 mm forward of the transom; keel rocker from 910 mm (stem keel +100 mm); keel rises to +40 mm at the transom from 520 mm |
| Volume | 51.6 L enclosed per hull; 103 kg of buoyancy with both hulls just under |
| Mass | 34.3 kg design (bridge 12.9, hulls 21.4, with 10 % growth margin); 28.4 kg light; 39.3 kg with 5 kg more on the bridge |
| How it floats (design) | Draft 99 mm, freeboard 151 mm, 91 mm to the lid joint, trim +1 mm (bow down), 0.47 kg per mm of sinkage |
| Payload | +15 kg before the lid joint gets within 60 mm of the water; +43 kg before it's awash |
| Stability | GM_T 1.57 m, 9.2 N·m per degree of heel; the leeward rail goes in at 15°, the windward hull lifts at 16° |
| Strength (target SF 3) | Arch frames 5.0 (hulls pitching out of phase, 2 g), foot bolts 3.2, lid rib 4.3, rail screws 4.4 |
| Draft with props | ~132 mm (the props hang below the keel line) |
| Resistance, both hulls | 6.6 N at 1.0 m/s, 21.5 N at 1.5 m/s, 49.4 N at 3.0 m/s (15 % service margin) |
| Drive power, both | ~23 W at 1.0 m/s, ~94 W at 1.5 m/s, ~381 W at 3.0 m/s |
| Endurance | ~17 h at 1.0 m/s, ~4 h at 1.5 m/s, from ~400 Wh (one 12S ~10 Ah pack for both drives, 90 % usable). The plan is now one 10S pack for everything (§1) |

The current numbers are in `mechanical/reports/hull_report.md` and `propulsion_report.md` on the
branch. Robot arm mass is **not** in the budget (§7).

## 4. How rev D is built

### 4.1 Hulls and the lid joint

- **Tub plus lid.** The joint plane is 190 mm above the baseline, 91 mm above the design waterline.
  The lid laps over the tub on a flange, like a shoebox lid: a friction skirt can't seal 2.85 m of
  printed edge, but a flange clamped on a gasket can.
- **Joint:** 15 mm flanges, 5 mm thick each. A 3 mm EPDM or silicone cord sits in a 5 × 2.2 mm
  groove, so it's squeezed 27 % when the flanges touch: the groove sets the squeeze, the joint can't
  be over-tightened, and hard flange contact keeps it stiff. 37 × M4 × 12 A4 pan heads per hull go
  into brass heat-set inserts outboard of the gasket (100 mm pitch, 60 mm near the frames), so the
  holes are on the wet side and need no sealing. A 2.5 mm drip lip covers the joint and locates the
  lid; a 6 × 2 mm spigot under the lid is a second barrier.
- **Inside:** the 12S drive pack in the port hull's middle segment; the electronics and winch packs
  and the Pi 5 with its carrier in the starboard hull; a VESC by each outdrive. Packs and VESCs sit
  on aluminium heat plates on the hull bottoms, so the water sinks the heat; keep them off the
  walls. Wiring enters only through IP68 bulkhead connectors in the lids. A leak probe at each
  hull's lowest point and a membrane vent in each lid.
- **Shell mass:** ~4.6 kg per hull plus ~1.0 kg for the lid joint.

### 4.2 Arched bridge and the hub garage

- **Two 1/4 in 6061-T6 arch frames**, 50 mm deep, laser or waterjet cut from
  `mechanical/cad/arch_frame_plate.dxf`, at 520 and 780 mm forward of the transom,
  right over 8 mm ribs in the lids. 700 mm foot to foot.
- **Feet:** a 300 × 140 × 6 mm 6061 plate each side, on a 1.5 mm EPDM pad on the lid deck. 8 × M6
  × 60 A4 per foot come up from inside the lid through full-depth Ø20 bosses in the rib, so the rib
  is never notched. No latches. The M6s are good for ~9 kN; the printed bosses and inserts govern,
  so pull-test a boss and an insert from the printer that makes them.
- **Hub:** a printed cowl, 560 × 400 mm, 310–550 mm above the baseline, centred 610 mm forward. Its
  underside is 211 mm above the waterline. GNSS on a mast to 820 mm, LTE and Wi-Fi whips, the
  e-stop, and the stereo camera bar on the front.
- **The hub is the garage.** It holds the winch, a sheave over a 240 × 301 mm opening in the hub
  floor, and a cone that stops the pod swinging. The pod and a 2 L horizontal Van Dorn pull up
  through the opening (30 / 70 mm to spare) and stow with their bottoms 186 mm above the waterline,
  so nothing hangs in the tunnel. The IP67 electronics box of rev C is gone. The winch envelope
  (x 360–500, z 372–470) is a placeholder.

### 4.3 Fixed belt outdrive

- **One mount per drive** bolts to the lid's aft deck (4 × M5 up from inside) and down the lid's aft
  wall (a 6 mm flange, 2 × M5 through the wall). Its head block clamps the leg's top (40 mm socket,
  2 × M4 across) and carries the motor plate and the cover. 13 parts per drive.
- **A thrust pad takes the forward thrust.** It's bonded to the transom (2 mm EPDM face), and the
  leg's nose rests on it. At 55 N of thrust the pad takes 131 N and the mount 76 N, and the leg
  bends 6.5 N·m at the pad instead of 11.2 N·m at the mount. Reverse thrust hangs on the mount's
  bolts. Nothing bolts to the tub, so the drive lifts away with the lid.
- **Geometry:** the leg's leading edge runs 3.5 mm outside the rail, which is what stops it going
  closer; the tightest gap is the wall flange, 2 mm over the rail. The motor sits just behind the
  transom. Motor axis 300 mm and prop axis 22 mm above the baseline: a 205-tooth HTD 3M-9 belt (615
  mm) on 20T pulleys. The drive overhangs the transom by 161 mm.
- **Belt:** at 3 m/s it runs ~3880 rpm and ~0.40 N·m per drive, near a 9 mm belt's rating on a 20T
  pulley. Use a 15 mm belt for long fast runs; cruise at 1.5 m/s is well inside it.
- **Why not kick-up:** rev C's tilt head hit its own bracket at ~13°, and the 3D model's cover
  overlapped the bracket at rest.

### 4.4 Props

- `mechanical/toroidal_prop.py` makes a parametric toroidal (looped-blade) prop. Default: 3 loops,
  110 mm, pitch 75, with a 20 mm hub bored for a 5 mm stainless D-shaft and an M5 nylock. A
  right-hand and a left-hand prop are built, one per hull. `--hub m200` fits a Blue Robotics M200.
- Rev D planned to print it in resin on a Formlabs Form 3L, in a tough resin (Tough 2000, or
  Durable for impacts), standing on the hub's front face with supports only on the hub. Check the
  bore on a shaft offcut and balance it.
- Test it on the thrust stand (`mechanical/props/thrust_stand.pdf`) against a plain 110 mm RC prop
  on the same drive, at about 5, 10 and 25 N per drive.

## 5. Building notes from rev D

### 5.1 Printed PLA hulls: printing and sealing

- 0.6–0.8 mm nozzle, at least 4 walls (~2.4 mm), +3–5 % flow and a hot nozzle for layer fusion.
- Bond segment joints with thickened epoxy. Two coats of epoxy inside. Epoxy only, never polyester.
- **Mix small batches with slow hardener.** Epoxy's exotherm can pass PLA's 55–60 °C softening point.
- The tub prints on end, so layer lines cross the rail gasket: epoxy-coat and sand the flange and
  groove, or use closed-cell EPDM foam tape.
- XPS blocks in the bow and stern bays keep a holed hull afloat.
- Before fitting anything, float each hull for 24 h, or pressurize it gently (≤ 0.03 bar on a water
  manometer) with soapy water on the seams. Before the full build, print, seal and soak a test
  segment for a week.
- PLA softens at 55–60 °C: paint it a light colour and never leave it in a hot car. It also gets
  brittle in the cold.
- ~4.4 kg of PLA per hull (tub, lid, rail), roughly 33–80 h of printing per hull.
- Is PLA the only option on the Giga? Its 300 °C hotend prints PETG (softens ~80 °C). ASA and ABS
  warp badly at this size without an enclosure.

### 5.2 Weight in the bow

A CAD-solid nose prints at the slicer's infill. At 100 % against a 2.4 mm shell, both bows together
add 0.6 kg for the first 75 mm from the stem (the stems sink 7 mm), 1.1 kg for 100 mm, 2.7 kg for
150 mm and 5.0 kg for 200 mm (57 mm). At 20 % infill, 200 mm adds ~1 kg and works as a crash block.
Print 100 % only around bolts, with a slicer modifier.

### 5.3 Robot arm placement

Kyle's arm (~9–10 kg) only works between the arch frames. At 1000 or 1200 mm forward it trims the
bow down 160 or 230 mm, and at 1200 the foot-bolt SF falls to 2.1. Reaching out, it heels the boat
3° (arm CG 0.3 m outboard) to 8.5° (0.6 m out with 2 kg at 0.9 m). Its base bolts to the frames, not
the printed cowl. It would need its own pack and fuse and a cable to the Pi (USB or Ethernet), since
the carrier has no arm power domain.

### 5.4 Hull width study (09-27 and 09-29)

With the arm aboard, 152 mm (6 in) hulls fail (45 mm to the lid joint), 190 mm is marginal (65 mm),
220 mm keeps +7 kg of payload and 250 mm +13 kg. 6 in hulls have 16 % less drag but their 84 mm flat
deck doesn't take the 140 mm feet. Hence 220 mm.

### 5.5 Hull length check: 985 mm (2026-10-14)

Matthew's model, run at 985 mm with the same gear aboard and the hull shape scaled to the new
length, at rev D's 220 mm beam and two wider ones for comparison. Only the shell's mass changes. The
trim, the layout and the strength checks were **not** re-run: the frames, hub and packs are still
placed for a 1300 mm hull.

| | 1300 × 220 (rev D) | 985 × 220 | 985 × 250 | 985 × 300 |
|---|---|---|---|---|
| Enclosed volume per hull | 51.6 L | 39.1 L | 44.2 L | 52.7 L |
| Design mass | 34.3 kg | 31.9 kg | 32.4 kg | 33.4 kg |
| Draft | 99 mm | 116 mm | 108 mm | 98 mm |
| To the lid joint (limit 60 mm) | 91 mm | 74 mm | 82 mm | 92 mm |
| Payload before the joint is within 60 mm | +15 kg | +5 kg | +9 kg | +15 kg |
| With Kyle's arm (+9.9 kg), to the lid joint | 70 mm | **47 mm, fails** | **58 mm, fails** | 71 mm |
| Both drives at 1.0 / 1.5 / 3.0 m/s | 23 / 94 / 381 W | 27 / 138 / 429 W | 28 / 156 / 449 W | 31 / 192 / 498 W |
| Endurance at 1.5 m/s (400 Wh) | 4.2 h | 2.9 h | 2.6 h | 2.1 h |

- At 220 mm wide, a 985 mm hull still floats with 74 mm to the lid joint, but only +5 kg of payload
  is left, so the arm no longer fits.
- Cruise at 1.5 m/s takes ~45 % more power (138 vs 94 W). The shorter hull runs at Froude number
  0.48 instead of 0.42, close to the hump, and endurance drops from ~4.2 h to ~2.9 h.
- Wider hulls buy the freeboard back but cost more power: at 300 mm the freeboard matches rev D's,
  at about twice its cruise power.
- At 3 m/s both drives need ~430 W, inside Kyle's 200–300 W per side.
- The 190 mm joint height and the 60 mm limit are rev D's. A higher lid joint changes the freeboard
  rows, not the power.

## 6. Water sampling and sensors

### 6.1 How a sample gets taken (proposal)

- **Mount the bottle on the pod,** like a small CTD rosette, rather than swapping it for the pod.
  The pod's depth sensor logs where the bottle closed, the descent profile picks the depth, and the
  boat keeps one winch and one tether.
- **Close it about 0.5 m off the bottom,** as CRWA does from a canoe. Touching the mud spikes TSS
  and phosphorus.
- **Arrive heading upstream, then cut the drives,** so the prop wash drifts away downstream.
- **The operator closes the bottle:** RC switch, then the carrier, then RS-485 down the tether, then
  a short pulse on the pod's aux pad (D10) to a micro servo or a small solenoid that pulls the pin.
  Pulse it, never hold it: the pod's 5 V and the tether's fuse are small. The pod logs depth, water
  temperature and time at closing. Fallback with no pod power: a messenger weight dropped from the
  boat, as a hand-run Van Dorn uses.
- **Test by hand first:** a Van Dorn off a dock with a pull-cord trigger (seals, soak time,
  decanting), then move it onto the pod.

### 6.2 The sampler

- **Van Dorn style, horizontal, sized to the garage:** an opaque grey PVC tube (phosphorus and TSS
  are stored dark), open at both ends on the way down so it flushes, with end seals that snap shut on
  elastic when a pin is pulled. 2 L in 5 in PVC (ID ~128 mm) is 155 mm inside, ~210 mm with the
  seals. ~2 L covers a 500 mL phosphorus and a 1 L TSS bottle. Lying horizontally it barely flushes,
  so hold it open at depth for about a minute before closing.
- **Wetted parts must survive a 10 % HCl wash,** which lab bottles get: PVC, acrylic, HDPE, PP,
  silicone. No stainless (HCl pits it) and no printed parts in the sample path.
- **Don't open the lab's bottle underwater.** The tube is the open/close mechanism; decant into the
  lab's bottles on shore. A Van Dorn is an intermediate container: fine for nutrients, TSS and
  chloride, not for E. coli, which must go straight into a sterile bottle.
- **Weight:** pod ~2.0 kg (1.2 plus 0.8 of sensor growth), sampler ~0.9 kg and 2 kg of water: ~5 kg
  on the line once it leaves the water.

### 6.3 Keeping samples valid

- **Cold and fast.** Federal rules (40 CFR 136.3, Table II) say to preserve a grab sample within
  15 minutes of collection and keep it at 6 °C or below. With no ice aboard, the bottle has to reach
  the cooler within ~15 minutes of closing: at 1.5 m/s that's under ~1 km after docking and
  decanting, one bottle per trip.
- **Holding times** (same table): phosphorus, TKN, ammonia and nitrate-nitrite 28 days cooled and
  acidified; nitrate 48 h cooled; orthophosphate filtered within 15 minutes, 48 h; TSS 7 days cooled;
  chloride needs no preservation and keeps 28 days, which makes it the easiest first pilot.
- **The river doesn't keep it cold.** Submerged, the sample stays at river temperature, which is far
  above 6 °C in summer. In winter the job flips to not freezing. Either way, haul it out once it's
  closed, shade it, and log the water temperature at closing.
- **CRWA's own programs** ice every sample to 4 °C right away and keep nutrients dark, and some
  analytes have to reach the lab within 6 h. Robot-collected samples need an amendment to CRWA's
  quality plan, reviewed by the state, before the data counts. A pilot could take field duplicates
  side by side with CRWA staff. (CRWA's plan itself stays out of the repo, per CLAUDE.md §4.1.)

### 6.4 Winter, salt and ice (for the 2027–28 winter)

- **Road salt study:** CRWA already logs conductivity and temperature every 15 minutes above and
  below Route 9 on the Muddy River, and preliminary chloride is above EPA criteria
  (muddyrivermmoc.org). The boat adds what two fixed loggers can't: maps between them and near
  outfalls, bottom profiles (salty meltwater sinks and pools in ponds and slow reaches), and runs
  right after a salting or a melt.
- **The pod's TDS sensor is too small for it.** The DFRobot SEN0244 reads 0–1000 ppm TDS (~0–2000
  µS/cm) at ±10 % of full scale. CRWA's action limit is 994 µS/cm, and salt pulses run to thousands
  or tens of thousands of µS/cm. Rev D suggested an Atlas EZO-EC with a K 1.0 probe (5–200,000 µS/cm,
  ±2 %, rated from 1 °C), validated by parking the pod beside CRWA's Route 9 loggers. It has to meet
  CRWA's NIST rule (§1).
- **Cold:** Li-ion loses capacity in the cold and must never be charged below 0 °C; keep the packs
  in the hulls.
- **No icebreaking.** Rough estimate, with both drives giving ~110 N bollard: ~1 cm of ice works
  slowly, 1.5–2 cm only at full throttle with no margin, 3 cm or more no. Thrust isn't the main
  problem: broken ice slides under the hulls into the props, cold PLA is brittle, a thin ice edge
  saws at the waterline, and a stalled boat sits on ice too thin to walk out on. On ice days, sample
  from bridges or the bank. Fit a UHMW or aluminium stem guard now (debris, launching), with bolts
  that could carry a plow later. Since nothing between the hulls is in the water when stowed, any
  plow goes on the hulls only, and guard rings on the props also shed weed.

### 6.5 Winch materials (suggested)

Loads are small (~5 kg on the line), so metal is for wear, heat and torque joints, not strength.
Metal: a stainless shaft, bearings, 6061 side plates and motor mount, the sheave axle, a bought
reversing (diamond) screw for the level-wind, and a clamping hub that carries the drum torque.
Printed: the drum core and flanges bolted to that hub, the level-wind follower, the fairlead body
(with a smooth insert), covers. Not PLA: the deck is sunny and wound cord loads the drum constantly,
so use ABS, ASA or PETG. Isolate aluminium from stainless (nylon washers, Tef-Gel); road salt makes
it worse. The tether needs a strength member, so the conductors never carry the pod and a full
bottle.

### 6.6 Lessons for V3 software (from the V2 review, 09-25)

V2's code is archived, but these will bite V3 too:

- **Persist every pod reading, descent included.** V2 only kept readings taken while sampling and
  never saved them.
- **Guard against soft bottoms.** In mud the bottom switch may never trip and pressure plateaus
  only past ~0.5 m, so the winch could keep paying out until a timeout. Set a tether-out limit per
  site.
- **Keep the EC probe from interfering with pH and DO.** Pulsed DC on an EC probe upsets the other
  probes unless it's isolated (the pod board isolates TDS) or time-multiplexed.
- **Store units, QC flags and the sensor ID with each reading,** so the data can be exported in a
  WQX-style format for CRWA.

### 6.7 Muddy River context

USGS gauge 01104683 (Muddy River at Brookline) records only gauge height and precipitation, not
discharge. There was a low-oxygen fish kill from Leverett Pond to the Fens in May 2026 and a
cyanobacteria advisory in the Fenway in August 2025. CRWA's priorities there: pH, temperature,
dissolved oxygen, turbidity, conductivity, and nutrient loading (so flow too).

## 7. Open questions

- **Hull length:** confirm 985 mm, then lay the frames, hub and packs out for it and re-run trim and
  the SF checks (§1, §5.5).
- **Fitting the picked motor** (§1). The 5048 200KV replaces rev C's 380 KV pick. Raise the
  motor axis ~5 mm in the outdrive drawings so the can clears the cover, confirm the motor's shaft
  diameter for the pulley bore, and set both controllers to 10S and the same limits in VESC
  Tool, since they share the CAN bus.
- **Does Kyle's arm go on the boat?** With water samples on the winch and sediment on the pod, the
  arm is left with surface grabs. Without it the boat is ~10 kg lighter. With it, rev D still has
  +15 kg of payload, but the foot bolting may need backing plates or M8 to keep SF ≥ 3.
- **The winch's line pull** isn't known; the garage opening has to pass the pod and the bottle.
- **The pod's real size,** against the 240 × 301 mm opening.
- **CRWA:** which analytes and volumes (they size the bottle), how often they want samples, whether
  a ~15 minute close-to-ice window works for them and the lab, and whether bottles filled from a Van
  Dorn still get the triple rinse (~0.5 L more, so a ~2.5 L tube).
- **Muddy River site data:** depths, bridge and culvert clearances, launch points, where it ices.
- **Tests before relying on the numbers:** bond a thrust pad on a sealed PLA coupon and load it
  (the 131 N); pull-test a printed rib boss and a heat-set insert; soak a sealed test segment for a
  week; confirm the outdrive's thrust on the stand.

## 8. The design tools (`mechanical/`)

Stdlib Python 3.10+, no packages. Edge or Chrome, if present, makes the PDFs and PNG renders.
`python mechanical/build_all.py` regenerates everything in about a minute (`--quick` skips the
renders).

| Script | Does |
|---|---|
| `hull_sizing.py` | The design model: hull shape, hydrostatics, buoyancy, mass budget, bridge and joint loads. **Every other script reads its numbers from here.** `--beam` and `--compare` try other hull widths |
| `propulsion.py` | Resistance (ITTC friction, Michell twin-hull wave drag, transom drag), prop diameter trade, belt outdrive vs M200 vs T200 |
| `drawings.py` | A 7-sheet drawing PDF (sheets 5 and 6 draw the outdrive for CAD), SolidWorks guide curves in `cad/`, the arch-frame DXF |
| `concept_model.py` | A spinnable three.js viewer, renders and an OBJ mesh |
| `toroidal_prop.py` | The prop STL, viewer, curves and report, and the thrust stand |

Beside them are `docs/hull_and_crossbeam_sizing.md` (the design record; its body is still rev C,
with rev D and rev E notes at the top) and `docs/solidworks_modeling_guide.md` (rev E, step by step
from the drawings). Generated files are still named `DREAMS_V2_*` from before the V3 sync.

What to watch after any change: trim within ±10 mm (move the hub to fix it), freeboard to the lid
joint above ~60 mm at design load, positive garage margins, no outdrive clash with the rail, every
frame and joint SF ≥ 3, and every printed part fitting the printer.
