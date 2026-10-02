"""D.R.E.A.M.S V2 hull, bridge and joint sizing calculator.

Modelled on the EvoLogics Sonobot 5 (05.2024 guide: 1300 mm long, 920 mm wide, 120 mm
draft, < 27 kg): two pontoon hulls and a gull-wing bridge that arches from hull to hull.
The computer, radios, batteries and winch live in a sealed hub at the crown of the arch,
with the antennas on top, out of the spray. Each hull is an open printed tub with a
removable lid: the lid's rail flange laps over the tub's gunwale flange on a gasket cord and
screws down. The bridge feet bolt to the lids from underneath, and a V1-style belt outdrive
sits on each lid's aft deck, so the tubs carry no hardware at all. Tub and lid segments are
sized for the Ultimaker S5 at the EXP makerspace (330 x 240 x 300 mm build volume).

Stdlib only:
    python mechanical/hull_sizing.py                        # report for the design in this file
    python mechanical/hull_sizing.py --beam 0.1524          # same boat, 6 in hulls (same bridge)
    python mechanical/hull_sizing.py --compare 0.22 0.1524  # side-by-side buoyancy summary

propulsion.py, drawings.py and concept_model.py import this module, so the drawings, the
3D model and the numbers always agree. Change a parameter here and re-run them all.

Coordinates: x forward from the transom, y to starboard (from a hull's centreline for hull
geometry, from the boat centreline for the bridge), z up from the baseline (lowest point
of the keel). SI units throughout. Demi-hull form: constant-deadrise V bottom with a
rounded chine, vertical sides, rounded deck edge, flat deck, parallel midbody, bow tapered
in plan, keel rocker at the bow (cut-away forefoot) and a straight keel rise aft.
"""

from __future__ import annotations

import argparse
import math
from dataclasses import dataclass, field

G = 9.81
RHO_WATER = 1000.0  # fresh water (Muddy River). Sea water (1025) floats ~2.5 % higher.
NU_WATER = 1.14e-6  # kinematic viscosity at 15 C, m^2/s


# ---- Hull geometry ---------------------------------------------------------------------------


@dataclass
class Lid:
    """Removable hull lid. The hull is an open tub; the lid (deck, deck-edge radius and a short
    skirt) sits on it at a horizontal joint plane. Both halves carry an outward flange there
    and the lid's drip lip laps down over the tub's flange: a shoebox joint on a gasket cord,
    screwed down through the rail. Sections are measured from the hull side (y outboard) and
    from the joint plane (z up)."""

    z: float = 0.190  # joint plane = top of the tub flange, m above baseline
    flange_w: float = 0.015  # both flanges stick out this far from the hull side
    flange_t: float = 0.005  # each flange: tub below the plane, lid above
    lip_t: float = 0.0025  # drip lip on the lid flange's outer edge
    lip_drop: float = 0.008  # lip reaches this far below the joint plane
    groove: tuple[float, float] = (0.005, 0.0022)  # gasket groove in the tub flange, width x depth
    groove_y: float = 0.004  # groove centre from the hull side (inboard of the screws)
    gasket_d: float = 0.003  # EPDM or silicone cord: 27 % squeeze when the flanges touch
    screw_y: float = 0.0105  # screw line from the hull side, outboard of the gasket
    screw_pitch: float = 0.100  # along the rail; `screw_pitch_near` within 150 mm of a frame
    screw_pitch_near: float = 0.060
    screw_pullout: float = 1200.0  # N, M4 brass heat-set insert in PETG (pull-test your prints)
    spigot: tuple[float, float] = (0.006, 0.002)  # locating lip inside the tub wall: drop x thickness
    rib_t: float = 0.008  # lid ribs under the frames (printed base walls of lid segments 3 and 4)
    rib_joints: tuple[int, ...] = (2, 3)  # the ribs sit on joints J2 / J3, under the arch frames
    bulkhead_gap: float = 0.005  # tub bulkheads stop this far under the joint plane (one gasket loop)
    petg_strength: float = 45e6  # Pa, printed PETG stressed along its layers


@dataclass
class Hull:
    """One demi-hull."""

    loa: float = 1.30  # m. Sonobot 5: 1300 mm
    beam: float = 0.22  # m, outside the shell (the rail adds 17.5 mm a side above the waterline)
    depth: float = 0.25  # m, baseline to deck
    deadrise_deg: float = 12.0
    chine_r: float = 0.050  # m, rounded chine (the Sonobot pontoon look; glass lays over it)
    deck_r: float = 0.050  # m, rounded deck edge
    taper_start: float = 0.50  # fraction of LOA (from transom) where the bow taper begins
    taper_power: float = 1.8  # plan-view taper exponent; higher = fuller bow
    rocker_start: float = 0.70  # fraction of LOA where the keel starts rising to the stem
    bow_rise: float = 0.10  # m, keel height at the stem (cut-away forefoot sheds weed)
    stern_rise: float = 0.04  # m, keel height at the transom (shrinks the immersed transom)
    stern_rise_end: float = 0.40  # fraction of LOA where the straight aft keel rise ends
    stem_flat: float = 0.010  # m, width of the flat stem face (don't loft to a knife edge)
    # construction: an open tub of 5 printed segments, each standing on its aft bulkhead,
    # bonded transom-first and glassed outside; the lid is 5 more segments printed on end
    # the same way (lid segments 3 and 4 stand on the ribs under the frames)
    segments: int = 5
    wall_t: float = 0.0020  # m, printed shell (5 perimeters x 0.4 mm)
    wall_rho: float = 1270.0  # kg/m^3, PETG (ASA 1070; not PLA, which softens ~55 C)
    skin_areal: float = 0.45  # kg/m^2, 200 g/m^2 glass + epoxy on the outside
    bulkhead_t: float = 0.0024  # m, tub bulkhead at the aft end of every segment
    stiffener_frac: float = 0.15  # stringers + chamfered ring frames, fraction of shell mass
    printer: tuple[float, float, float] = (0.330, 0.240, 0.300)  # Ultimaker S5, x y z
    lid: Lid = field(default_factory=Lid)

    @property
    def tb(self) -> float:
        return math.tan(math.radians(self.deadrise_deg))

    @property
    def segment_length(self) -> float:
        return self.loa / self.segments

    def joints(self) -> list[float]:
        """x of each segment's aft face (transom first); each carries a tub bulkhead."""
        return [i * self.segment_length for i in range(self.segments)]

    def rib_x(self) -> list[float]:
        """x of the lid ribs that take the bridge feet."""
        return [self.joints()[j] for j in self.lid.rib_joints]

    def flat_deck(self, x: float) -> float:
        """Width of the flat top between the deck-edge radii at station x."""
        return 2 * (self.half_beam(x) - self.deck_fillet(x))

    def half_beam(self, x: float) -> float:
        xs = self.taper_start * self.loa
        if x <= xs:
            return self.beam / 2
        xi = min((x - xs) / (self.loa - xs), 1.0)
        return max(self.beam / 2 * (1 - xi**self.taper_power), self.stem_flat / 2)

    def keel_z(self, x: float) -> float:
        xa, xr = self.stern_rise_end * self.loa, self.rocker_start * self.loa
        if x < xa:
            return self.stern_rise * (1 - x / xa)
        if x <= xr:
            return 0.0
        xi = min((x - xr) / (self.loa - xr), 1.0)
        return self.bow_rise * xi**2

    def chine_rise(self, x: float) -> float:
        """Height of the sharp (unfilleted) chine above the keel."""
        return self.half_beam(x) * self.tb

    def fillet(self, x: float) -> tuple[float, float, float, float, float]:
        """Chine fillet at station x: radius, centre (y0, z0), bottom tangent height zT, and
        the tangent angle (= deadrise) from the vertical. Radius shrinks near the stem."""
        hb, zk = self.half_beam(x), self.keel_z(x)
        beta = math.radians(self.deadrise_deg)
        r = min(self.chine_r, 0.45 * hb)
        y0 = hb - r
        z0 = zk + y0 * self.tb + r / math.cos(beta)
        return r, y0, z0, z0 - r * math.cos(beta), beta

    def deck_fillet(self, x: float) -> float:
        return min(self.deck_r, 0.45 * self.half_beam(x))

    def half_width(self, x: float, z: float) -> float:
        """Half-breadth of the hull surface at station x, height z."""
        if not 0 <= x <= self.loa:
            return 0.0
        zk = self.keel_z(x)
        if z <= zk or z > self.depth:
            return 0.0
        hb = self.half_beam(x)
        r, y0, z0, zt, _ = self.fillet(x)
        if z < zt:
            return (z - zk) / self.tb
        if z < z0:
            return y0 + math.sqrt(max(r * r - (z - z0) ** 2, 0.0))
        rd = self.deck_fillet(x)
        zd = self.depth - rd
        if z <= zd:
            return hb
        return hb - rd + math.sqrt(max(rd * rd - (z - zd) ** 2, 0.0))


def section_points(hull: Hull, x: float, nv=6, nf=10, ns=8, nd=6, nt=5,
                   part: str = "all") -> list[tuple[float, float]]:
    """Half-section outline (y >= 0, z) at station x, from the keel round the rounded chine,
    up the side, round the deck edge to the deck centreline. part="tub" stops at the lid
    joint plane and part="lid" starts there. Point counts don't depend on x, for lofting."""
    zk, hb, D = hull.keel_z(x), hull.half_beam(x), hull.depth
    r, y0, z0, zt, beta = hull.fillet(x)
    rd = hull.deck_fillet(x)
    zd = D - rd
    zj = min(max(hull.lid.z, z0), zd)
    yt = y0 + r * math.sin(beta)
    bottom = [(yt * i / nv, zk + (zt - zk) * i / nv) for i in range(nv)]
    bottom += [(y0 + r * math.sin(beta + (math.pi / 2 - beta) * i / nf),
                z0 - r * math.cos(beta + (math.pi / 2 - beta) * i / nf)) for i in range(nf)]
    top = [(hb - rd + rd * math.cos(math.pi / 2 * i / nd), zd + rd * math.sin(math.pi / 2 * i / nd))
           for i in range(nd)]
    top += [((hb - rd) * (1 - i / nt), D) for i in range(nt + 1)]
    if part == "tub":
        return bottom + [(hb, z0 + (zj - z0) * i / ns) for i in range(ns + 1)]
    if part == "lid":
        return [(hb, zj + (zd - zj) * i / ns) for i in range(ns)] + top
    return bottom + [(hb, z0 + (zd - z0) * i / ns) for i in range(ns)] + top


def _circ(u: float, r: float) -> float:
    """int sqrt(r^2 - u^2) du."""
    u = max(-r, min(r, u))
    return 0.5 * (u * math.sqrt(max(r * r - u * u, 0.0)) + r * r * math.asin(u / r))


def _circ_z(u: float, r: float) -> float:
    """int u sqrt(r^2 - u^2) du."""
    u = max(-r, min(r, u))
    return -((r * r - u * u) ** 1.5) / 3


def section(hull: Hull, x: float, t: float) -> tuple[float, float, float, float]:
    """Immersed area, waterline half-breadth, first moment of area about the baseline and
    wetted girth of station x at draft t (both sides), with the rounded chine and deck edge."""
    zk, hb = hull.keel_z(x), hull.half_beam(x)
    top = min(t, hull.depth)
    if top <= zk or hb <= 0:
        return 0.0, 0.0, 0.0, 0.0
    tb = hull.tb
    r, y0, z0, zt, beta = hull.fillet(x)
    rd = hull.deck_fillet(x)
    zd = hull.depth - rd
    area = mz = girth = 0.0
    # V bottom
    h1 = min(top, zt) - zk
    area += h1 * h1 / (2 * tb)
    mz += (zk * h1 * h1 / 2 + h1**3 / 3) / tb
    girth += h1 / math.sin(beta)
    # chine fillet
    if top > zt:
        ua, ub = zt - z0, min(top, z0) - z0
        area += y0 * (ub - ua) + _circ(ub, r) - _circ(ua, r)
        mz += (z0 * y0 * (ub - ua) + y0 * (ub * ub - ua * ua) / 2
               + z0 * (_circ(ub, r) - _circ(ua, r)) + _circ_z(ub, r) - _circ_z(ua, r))
        girth += r * (math.acos(max(-1.0, min(1.0, -ub / r))) - beta)
    # vertical side
    if top > z0:
        za, zb = z0, min(top, zd)
        area += hb * (zb - za)
        mz += hb * (zb * zb - za * za) / 2
        girth += zb - za
    # deck edge fillet
    if top > zd:
        vb = top - zd
        area += (hb - rd) * vb + _circ(vb, rd) - _circ(0.0, rd)
        mz += (zd * (hb - rd) * vb + (hb - rd) * vb * vb / 2
               + zd * (_circ(vb, rd) - _circ(0.0, rd)) + _circ_z(vb, rd) - _circ_z(0.0, rd))
        girth += rd * math.asin(min(vb / rd, 1.0))
    return 2 * area, hull.half_width(x, min(top, hull.depth - 1e-9)), 2 * mz, 2 * girth


@dataclass
class Hydro:
    draft: float
    volume: float  # one hull, m^3
    lcb: float
    kb: float
    awp: float  # one hull
    lcf: float
    it_own: float  # one hull about its own centreline
    il: float  # one hull about the LCF
    wsa: float  # one hull, transom excluded (it separates / runs dry)
    lwl: float
    transom_area: float  # immersed transom area, one hull
    max_section: float  # largest immersed section area, one hull

    @property
    def cp(self) -> float:
        """Prismatic coefficient."""
        return self.volume / (self.max_section * self.lwl)


def hydrostatics(hull: Hull, t: float, n: int = 800) -> Hydro:
    dx = hull.loa / n
    xs = [(i + 0.5) * dx for i in range(n)]
    secs = [section(hull, x, t) for x in xs]
    vol = sum(s[0] for s in secs) * dx
    awp = sum(2 * s[1] for s in secs) * dx
    if vol <= 0 or awp <= 0:
        raise ValueError(f"no immersed volume at draft {t:.3f} m")
    lcb = sum(x * s[0] for x, s in zip(xs, secs)) * dx / vol
    kb = sum(s[2] for s in secs) * dx / vol
    lcf = sum(x * 2 * s[1] for x, s in zip(xs, secs)) * dx / awp
    it_own = sum((2 * s[1]) ** 3 / 12 for s in secs) * dx
    il = sum(2 * s[1] * (x - lcf) ** 2 for x, s in zip(xs, secs)) * dx
    wsa = sum(s[3] for s in secs) * dx
    wetted = [x for x, s in zip(xs, secs) if s[1] > 0]
    return Hydro(t, vol, lcb, kb, awp, lcf, it_own, il, wsa,
                 max(wetted) - min(wetted) + dx, section(hull, 0.0, t)[0],
                 max(s[0] for s in secs))


def draft_for(hull: Hull, volume_per_hull: float) -> Hydro:
    lo, hi = 1e-4, hull.depth
    if hydrostatics(hull, hi).volume < volume_per_hull:
        raise ValueError("hull sinks: displacement exceeds enclosed volume")
    for _ in range(40):
        mid = (lo + hi) / 2
        if hydrostatics(hull, mid).volume < volume_per_hull:
            lo = mid
        else:
            hi = mid
    return hydrostatics(hull, (lo + hi) / 2)


def shell_mass(hull: Hull, n: int = 400) -> float:
    """Printed tub + lid shells, outside glass, tub bulkheads, lid ribs and stiffeners, one hull."""
    dx = hull.loa / n
    skin = deck = 0.0
    for i in range(n):
        x = (i + 0.5) * dx
        skin += section(hull, x, hull.depth)[3] * dx  # bottom + chines + sides + deck edges
        deck += hull.flat_deck(x) * dx
    lid = hull.lid
    transom = section(hull, 0.0, hull.depth)[0]  # tub transom + the lid's aft end wall
    bulkheads = sum(section(hull, xj, lid.z - lid.bulkhead_gap)[0] for xj in hull.joints()[1:])
    ribs = sum(section(hull, x, hull.depth)[0] - section(hull, x, lid.z)[0] for x in hull.rib_x())
    mass = (
        skin * (hull.wall_t * hull.wall_rho + hull.skin_areal)
        + transom * hull.skin_areal
        + deck * hull.wall_t * hull.wall_rho
        + (transom + bulkheads) * hull.bulkhead_t * hull.wall_rho
        + ribs * lid.rib_t * hull.wall_rho
    )
    return mass * (1 + hull.stiffener_frac)


def rail_length(hull: Hull, n: int = 400) -> float:
    """Plan perimeter of the hull at the lid joint plane: both sides, transom and stem face."""
    xs = [hull.loa * i / n for i in range(n + 1)]
    side = sum(math.hypot(b - a, hull.half_beam(b) - hull.half_beam(a)) for a, b in zip(xs, xs[1:]))
    return 2 * side + 2 * hull.half_beam(0.0) + hull.stem_flat


def lid_screws(hull: Hull, frame_x: tuple[float, ...] = (0.52, 0.78)) -> int:
    """M4 screws round one rail: normal pitch, closer within 150 mm of each frame (both sides)."""
    lid = hull.lid
    near = 2 * len(frame_x) * 0.30  # rail length within +/-150 mm of a frame, both sides
    return math.ceil(near / lid.screw_pitch_near + (rail_length(hull) - near) / lid.screw_pitch)


def lid_joint_mass(hull: Hull) -> float:
    """Rail flanges, drip lip, locating spigot, rib bolt bosses, gasket cord and screws, one hull."""
    lid = hull.lid
    area = (2 * lid.flange_w * lid.flange_t - lid.groove[0] * lid.groove[1]
            + lid.lip_t * (lid.flange_t + lid.lip_drop) + lid.spigot[0] * lid.spigot[1])
    rail = rail_length(hull)
    bosses = 4 * len(lid.rib_joints) * math.pi / 4 * 0.020**2 * (hull.depth - lid.z)  # full depth
    screws = lid_screws(hull) * (0.0019 + 0.0012 + 0.0004)  # M4 x 12 A4 pan head, brass insert, washer
    return (area * rail + bosses) * hull.wall_rho + screws + rail * 0.008  # cord ~8 g/m


def print_fit(hull: Hull) -> tuple[bool, str]:
    """Tub and lid segments print standing on end: section in x-y of the bed, length in z."""
    px, py, pz = hull.printer
    lid = hull.lid
    width = hull.beam + 2 * (lid.flange_w + lid.lip_t)  # over the rail
    tub_h, lid_h = lid.z, hull.depth - lid.z + lid.lip_drop

    def fits(a: float, b: float) -> bool:
        return max(a, b) <= px - 0.010 and min(a, b) <= py - 0.010

    ok = fits(width, tub_h) and fits(width, lid_h) and hull.segment_length <= pz - 0.010
    return ok, (f"{hull.segments} x {hull.segment_length * 1000:.0f} mm segments each; tub "
                f"{width * 1000:.0f} x {tub_h * 1000:.0f}, lid {width * 1000:.0f} x {lid_h * 1000:.0f} mm "
                f"sections on a {px * 1000:.0f} x {py * 1000:.0f} x {pz * 1000:.0f} mm build volume")


# ---- Boat layout and the arched bridge -------------------------------------------------------


@dataclass
class Outdrive:
    """V1-style belt outdrive, one per hull, bolted to the lid's aft deck. An outrunner above
    the deck drives the prop shaft 1:1 through an HTD 3M timing belt that runs down inside a
    streamlined leg. The whole drive tilts up about a transverse pin when the leg hits
    something, like an outboard. x is from the transom (negative = aft of it)."""

    prop_d: float = 0.110  # toroidal_prop.py default, or a 110 mm RC boat prop
    tip_immersion: float = 0.20  # prop tip below the DWL, x prop_d
    belt_x: float = -0.055  # plane of both pulleys
    motor_z: float = 0.300  # motor axis, m above baseline (motor axis runs fore-aft)
    motor_d: float = 0.046  # 4108-size outrunner can
    motor_l: float = 0.032
    pivot: tuple[float, float] = (-0.030, 0.262)  # tilt pin (x, z), transverse
    cover: tuple[float, float, float] = (0.080, 0.070, 0.073)  # printed motor cover x y z
    bracket: tuple[float, float] = (0.085, 0.070)  # footprint on the lid's aft deck, x y
    leg_le: float = -0.028  # leg leading edge x (clears the transom rail)
    leg_chord: float = 0.080
    leg_t: float = 0.028  # the two belt runs, 19 mm apart, run inside it
    pod_d: float = 0.032  # lower pod: pulley and two 625-2RS bearings
    pod_x: tuple[float, float] = (-0.022, -0.114)  # pod nose and tail (tail 6 mm past the leg)
    hub_len: float = 0.043  # toroidal prop hub, toroidal_prop.py --hub shaft
    pulley_teeth: int = 20  # both pulleys (1:1)
    belt_pitch: float = 0.003  # HTD 3M
    belt_w: float = 0.009
    shaft_d: float = 0.005  # 316 stainless, D-flat at the prop end
    kv: float = 380.0
    mass: float = 0.58  # kg per drive: motor 0.17, cover + bracket 0.18, leg + pod 0.14, rest 0.09
    cg: tuple[float, float] = (-0.050, 0.200)  # x, z of one drive

    @property
    def pulley_pd(self) -> float:
        return self.pulley_teeth * self.belt_pitch / math.pi

    def prop_z(self, dwl: float) -> float:
        """Prop axis height that keeps the tip `tip_immersion` x D under the waterline."""
        return dwl - self.tip_immersion * self.prop_d - self.prop_d / 2

    def centre_distance(self, dwl: float) -> float:
        return self.motor_z - self.prop_z(dwl)

    def belt_teeth(self, dwl: float) -> int:
        """1:1 drive: belt length = 2 C + pi PD = 2 C + teeth x pitch."""
        return round((2 * self.centre_distance(dwl)) / self.belt_pitch) + self.pulley_teeth

    def prop_x(self) -> tuple[float, float]:
        """Fore and aft faces of the prop hub (2 mm washer behind the pod)."""
        a = self.pod_x[1] - 0.002
        return a, a - self.hub_len


@dataclass
class Boat:
    overall_width: float = 0.92  # m, hull side to hull side (the rails add 35 mm). Sonobot 5: 920
    # arch frames: two 1/4" 6061-T6 plates, laser or waterjet cut, standing in the
    # transverse plane over the lid ribs (and tub bulkheads) at 520 and 780 mm
    frame_x: tuple[float, float] = (0.52, 0.78)
    frame_t: float = 0.00635  # 1/4" plate
    frame_h: float = 0.050  # depth of the plate section
    frame_lightening: float = 0.25  # fraction of plate area removed by holes
    # stbd arm centreline, a cubic Bezier from the hub (y, z) out and down to the foot
    arm_hub: tuple[float, float] = (0.17, 0.345)  # where the arm leaves the hub span
    arm_c1: tuple[float, float] = (0.26, 0.345)  # tangent horizontal at the hub
    arm_c2_dz: float = 0.050  # second control point this far above the foot (tangent vertical)
    foot_z: float = 0.2575  # frame end = top of the foot plate (deck 250 + pad + plate)
    # feet: 6 mm 6061 plates bolted to the lids from underneath. M6 x 60 bolts come up from
    # inside the lid through full-depth bosses in the lid ribs under each frame (heads in
    # counterbores, so the rib is never notched), through the deck, into the foot plate.
    foot_len: float = 0.30  # foot plate along x, centred between the frames
    foot_w: float = 0.14  # foot plate across the hull; may overhang the flat deck ~1 mm deep
    foot_t: float = 0.006
    pad_t: float = 0.0015  # EPDM pad between foot and lid deck: seals the bolt holes
    foot_bolt_y: tuple[float, ...] = (0.040, 0.062)  # bolts each side of the hull CL, at each frame
    foot_bolt_dx: float = 0.010  # bolts sit this far fwd of each frame; the 20 mm bosses clear the joint face
    foot_bolt_rating: float = 2400.0  # N per M6: bonded-seal washer ring bearing on the counterbore floor
    #                                    (PETG yield). Boss shear-out ~16 kN, A4 bolt ~9 kN. Pull-test one.
    drive: Outdrive = field(default_factory=Outdrive)
    # hub (sealed electronics bay) and its lens-shaped cowl
    hub_x: float = 0.61  # cowl centre, m fwd of transom (puts the bridge CG over the LCB)
    hub_half: tuple[float, float] = (0.28, 0.20)  # cowl half-length (x), half-width (y)
    hub_z: tuple[float, float, float] = (0.31, 0.44, 0.55)  # cowl bottom, belt line, top
    hub_e: float = 4.5  # plan-view superellipse exponent of the cowl
    hub_dome: float = 3.0  # dome profile exponent (2 = elliptical, higher = flatter top)
    box: tuple[float, float, float] = (0.48, 0.30, 0.12)  # IP67 box, packs lying flat, on the frames
    mast_top: float = 0.82  # top of the GNSS puck. Sonobot 5: 805 mm construction height
    camera_z: float = 0.53  # stereo bar on the front of the dome
    camera_baseline: float = 0.32  # m, as calibrated (pi5/cv/calibration.npz)

    def spacing(self, hull: Hull) -> float:
        """Hull centreline-to-centreline spacing."""
        return self.overall_width - hull.beam

    def foot_drop(self, hull: Hull) -> float:
        """How far the deck falls away under the foot's edges, where the foot overhangs the
        flat top onto the deck-edge radius. The EPDM pad takes up about 1 mm."""
        x = sum(self.frame_x) / 2
        over = (self.foot_w - hull.flat_deck(x)) / 2
        rd = hull.deck_fillet(x)
        if over <= 0:
            return 0.0
        return rd - math.sqrt(rd * rd - over * over) if over < rd else hull.depth

    def hub_scale(self, z: float) -> float:
        """Plan scale of the cowl at height z: flat bottom with a rounded edge, widest at the
        belt line, flat-topped dome above."""
        zb, zm, zt = self.hub_z
        if z <= zm:
            u = (zm - z) / (zm - zb)
            return 0.8 + 0.2 * math.sqrt(max(1 - u * u, 0.0))
        u = min((z - zm) / (zt - zm), 1.0)
        return max(1 - u**self.hub_dome, 0.0) ** (1 / self.hub_dome)

    def box_clearance(self) -> float:
        """Smallest margin (>0 = fits) between the IP67 box corners and the cowl, as a
        fraction of the cowl's plan size, checked at the box floor and roof."""
        ax, ay = self.hub_half
        bx, by, bz = self.box
        need = ((bx / 2 / ax) ** self.hub_e + (by / 2 / ay) ** self.hub_e) ** (1 / self.hub_e)
        floor = self.arm_hub[1] + self.frame_h / 2
        return min(self.hub_scale(floor), self.hub_scale(floor + bz)) - need

    def arm_ctrl(self, hull: Hull) -> tuple[tuple[float, float], ...]:
        yc = self.spacing(hull) / 2
        return (self.arm_hub, self.arm_c1, (yc, self.foot_z + self.arm_c2_dz), (yc, self.foot_z))

    @property
    def frame_spacing(self) -> float:
        return self.frame_x[1] - self.frame_x[0]


def bezier(ctrl, t: float) -> tuple[float, float]:
    (a, b), (c, d), (e, f), (g, h) = ctrl
    u = 1 - t
    return (u**3 * a + 3 * u * u * t * c + 3 * u * t * t * e + t**3 * g,
            u**3 * b + 3 * u * u * t * d + 3 * u * t * t * f + t**3 * h)


def arch_centreline(boat: Boat, hull: Hull, n_arm: int = 40) -> list[tuple[float, float]]:
    """Frame centreline (y, z) from the port foot, over the hub, to the starboard foot."""
    ctrl = boat.arm_ctrl(hull)
    stbd = [bezier(ctrl, i / n_arm) for i in range(n_arm + 1)]  # hub -> foot
    port = [(-y, z) for y, z in reversed(stbd)]  # foot -> hub
    return port + stbd


ARM_START_Y = 0.10  # the arm fairing starts here, hidden inside the hub


def arm_path(boat: Boat, hull: Hull, n: int = 40) -> list[tuple[float, float]]:
    """Arm fairing centreline (y, z), starboard: a straight run inside the hub, then the arch."""
    ctrl = boat.arm_ctrl(hull)
    y0, z0 = boat.arm_hub
    path = [(ARM_START_Y + (y0 - ARM_START_Y) * i / 6, z0) for i in range(6)]
    return path + [bezier(ctrl, i / n) for i in range(n + 1)]


def arm_section(s: float) -> tuple[float, float, float]:
    """Arm fairing section at path fraction s (0 inside the hub, 1 at the foot): half-width
    along x, half-thickness, and how far the section centre rides up above the frame."""
    root = max(0.0, 1 - s / 0.42) ** 2  # flare where the arm grows out of the hub
    return 0.15 + 0.03 * root + 0.02 * s**4, 0.032 + 0.045 * root, 0.045 * root


def arm_silhouette(boat: Boat, hull: Hull) -> tuple[list[tuple[float, float]], list[tuple[float, float]]]:
    """Upper and lower edges (y, z) of the starboard arm fairing seen from ahead."""
    path = arm_path(boat, hull)
    upper, lower = [], []
    for i, (y, z) in enumerate(path):
        a, b = path[max(i - 1, 0)], path[min(i + 1, len(path) - 1)]
        ty, tz = b[0] - a[0], b[1] - a[1]
        ln = math.hypot(ty, tz)
        ny, nz = -tz / ln, ty / ln
        _, t, lift = arm_section(i / (len(path) - 1))
        upper.append((y + (lift + t) * ny, z + (lift + t) * nz))
        lower.append((y + (lift - t) * ny, z + (lift - t) * nz))
    return upper, lower


def offset_polyline(pts: list[tuple[float, float]], d: float) -> list[tuple[float, float]]:
    """Offset a polyline by d along its left normal."""
    out = []
    for i, (y, z) in enumerate(pts):
        a = pts[max(i - 1, 0)]
        b = pts[min(i + 1, len(pts) - 1)]
        ty, tz = b[0] - a[0], b[1] - a[1]
        ln = math.hypot(ty, tz) or 1.0
        out.append((y - tz / ln * d, z + ty / ln * d))
    return out


def frame_outline(boat: Boat, hull: Hull) -> list[tuple[float, float]]:
    """Closed outline (y, z) of one arch frame plate."""
    c = arch_centreline(boat, hull)
    upper = offset_polyline(c, boat.frame_h / 2)
    lower = offset_polyline(c, -boat.frame_h / 2)
    return [(y, max(z, boat.foot_z)) for y, z in upper + list(reversed(lower))]  # flat on the feet


def polygon_area(pts: list[tuple[float, float]]) -> float:
    return abs(sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(pts, pts[1:] + pts[:1]))) / 2


def frame_mass(boat: Boat, hull: Hull) -> float:
    return (polygon_area(frame_outline(boat, hull)) * (1 - boat.frame_lightening)
            * boat.frame_t * 2700.0)


# ---- Mass budget -----------------------------------------------------------------------------


@dataclass
class Item:
    name: str
    kg: float
    where: str  # "center" (the bridge module) or "hulls" (split evenly between the hulls)
    x: float  # m fwd of transom
    z: float  # m above baseline


def mass_budget(hull: Hull, boat: Boat | None = None) -> list[Item]:
    boat = boat or Boat()
    hx = boat.hub_x
    fx = sum(boat.frame_x) / 2
    box_z = boat.arm_hub[1] + boat.frame_h / 2  # box floor sits on the frame tops
    pack_z = box_z + 0.05
    # M18 weights (Milwaukee spec): HD12.0 3.42 lb, XC6.0 2.53 lb, XC5.0 1.8 lb.
    return [
        Item("Drive packs 2x M18 HD12.0 (one per VESC, 18 V)", 2 * 1.55, "center", hx - 0.10, pack_z),
        Item("Electronics pack M18 XC5.0", 0.82, "center", hx - 0.10, pack_z),
        Item("Winch pack M18 XC6.0", 1.15, "center", hx - 0.10, pack_z),
        Item("M18 adapter plates x4", 0.32, "center", hx - 0.10, pack_z),
        Item("VESC x2 + heatsinks", 0.40, "center", hx + 0.14, box_z + 0.03),
        Item("Fuses, switches, 12 AWG wiring", 0.40, "center", hx, box_z + 0.03),
        Item("Pi 5, Boat PCB, Picos, SIM7600, GPS, IMU, RC rx, UBEC", 0.70, "center", hx + 0.14, box_z + 0.08),
        Item("Hub IP67 box + glands + connectors", 1.60, "center", hx, box_z + boat.box[2] / 2),
        Item("Hub cowl (printed PETG/ASA)", 0.60, "center", hx, boat.hub_z[1]),
        Item("Stereo cameras + bar", 0.60, "center", hx + boat.hub_half[0] - 0.02, boat.camera_z),
        Item("Mast, GNSS puck, LTE + WiFi whips, e-stop", 0.50, "center", hx, 0.68),
        Item("Winch (2006 + planetary, drum, level-wind, slip ring)", 1.50, "center", hx, box_z - 0.03),
        Item("Tether, ~20 m 4-conductor", 0.60, "center", hx, box_z - 0.03),
        Item("Pod, stowed under the hub (V1-style box)", 1.20, "center", hx, boat.hub_z[0] - 0.10),
        Item("Pod sensor growth (pH, DO, turbidity)", 0.80, "center", hx, boat.hub_z[0] - 0.10),
        Item("Arch frames x2 (1/4\" 6061-T6, laser cut)", 2 * frame_mass(boat, hull), "center", fx, 0.35),
        Item("Arm fairings + foot shoes (printed PETG/ASA)", 0.70, "center", fx, 0.35),
        Item("Foot plates x2 (6 mm 6061, lightened) + 4 angle brackets", 1.00, "center", fx, boat.foot_z),
        Item("Hull tubs + lids x2 (printed PETG, glassed)", 2 * shell_mass(hull), "hulls", 0.62, 0.12),
        Item("Lid joints x2 (rail flanges, gasket cord, M4 screws + inserts)", 2 * lid_joint_mass(hull),
             "hulls", 0.62, hull.lid.z),
        Item("Foot bolting x2 (16 M6 x 60 A4 + bonded seals, EPDM pads)", 0.45, "hulls", fx, hull.depth),
        Item("Belt outdrives x2 (outrunner, cover, tilt bracket, leg, belt, shaft, prop)",
             2 * boat.drive.mass, "hulls", *boat.drive.cg),
        Item("Leak sensors, vents, fasteners, cable clips", 0.30, "hulls", 0.60, 0.20),
    ]


MARGIN = 0.10  # growth margin on the whole budget


@dataclass
class Condition:
    name: str
    center_kg: float
    hulls_kg: float
    lcg: float
    kg_z: float
    center_lcg: float

    @property
    def total(self) -> float:
        return self.center_kg + self.hulls_kg


def condition(name: str, items: list[Item], margin: float, extra_center_kg: float = 0.0,
              extra_x: float | None = None, extra_z: float = 0.45) -> Condition:
    extra_x = Boat().hub_x if extra_x is None else extra_x
    m = sum(i.kg for i in items)
    mx = sum(i.kg * i.x for i in items)
    mz = sum(i.kg * i.z for i in items)
    center = sum(i.kg for i in items if i.where == "center")
    cmx = sum(i.kg * i.x for i in items if i.where == "center")
    hulls = m - center
    f = 1 + margin
    center, hulls, m, mx, mz, cmx = (v * f for v in (center, hulls, m, mx, mz, cmx))
    center += extra_center_kg
    m += extra_center_kg
    mx += extra_center_kg * extra_x
    mz += extra_center_kg * extra_z
    cmx += extra_center_kg * extra_x
    return Condition(name, center, hulls, mx / m, mz / m, cmx / center)


def conditions(hull: Hull, boat: Boat | None = None) -> list[Condition]:
    items = mass_budget(hull, boat)
    light = [i for i in items if not i.name.startswith("Pod sensor growth")]
    return [
        condition("Light (no growth, no margin)", light, 0.0),
        condition("Design (budget + margin)", items, MARGIN),
        condition("Max (design + 5 kg on the bridge)", items, MARGIN, extra_center_kg=5.0),
    ]


# ---- Loads -----------------------------------------------------------------------------------


@dataclass
class Loads:
    afloat_g: float = 2.5  # LC1 vertical load factor (slam at speed, rough launch)
    lift_one_hull_g: float = 1.5  # LC2 dynamic factor when hauled out by one hull
    pitch_acg_g: float = 2.0  # LC3 a_cg for the pitch-connecting moment
    carry_g: float = 2.0  # LC4 whole boat carried by the hub / mast base (people will)
    sf_target: float = 3.0  # on yield


@dataclass
class LoadCase:
    name: str
    moment: float  # N m, per frame
    shear: float  # N, per frame


def load_cases(boat: Boat, hull: Hull, cond: Condition, hydro: Hydro, loads: Loads) -> list[LoadCase]:
    """Bending in one arch frame. Feet fixed to the hulls; the two frames share the bridge
    load by the lever rule about the bridge's own CG."""
    yc = boat.spacing(hull) / 2
    x1, x2 = boat.frame_x
    share = max((x2 - cond.center_lcg) / (x2 - x1), (cond.center_lcg - x1) / (x2 - x1), 0.5)
    w_c = cond.center_kg * G
    w_h = cond.hulls_kg / 2 * G
    arm = yc - boat.arm_hub[0]  # foot to arm root
    span = 2 * boat.arm_hub[0]  # hub span between the arm roots
    p1 = share * w_c * loads.afloat_g
    lc1 = LoadCase(f"LC1 afloat, {loads.afloat_g:g} g (hub span / arm root)",
                   max(p1 * span / 4, p1 / 2 * arm), p1 / 2)
    n2 = loads.lift_one_hull_g
    lc2 = LoadCase(f"LC2 lifted by one hull x{n2:g} (lifted foot)",
                   share * (w_c * yc + w_h * 2 * yc) * n2, share * (w_c + w_h) * n2)
    mp = cond.total * loads.pitch_acg_g * G * hydro.lwl / 8
    f3 = mp / boat.frame_spacing
    lc3 = LoadCase(f"LC3 hulls pitching out of phase, a_cg {loads.pitch_acg_g:g} g (feet)", f3 * yc, f3)
    # LC4: carried by the hub, the two hulls hang from the arms
    f4 = share * w_h * loads.carry_g
    lc4 = LoadCase(f"LC4 carried by the hub x{loads.carry_g:g} (arm roots)", f4 * arm, f4)
    return [lc1, lc2, lc3, lc4]


def foot_station(boat: Boat, hull: Hull, moment: float, lift: float) -> tuple[float, float, float]:
    """One frame station of one foot carrying `moment` (N m, about the hull axis) and `lift`
    (N, pulling the foot off the lid). The foot pivots on its far edge; the M6 bolts in the
    lid-rib bosses hold it down. The rib spans between the rail screw lines. Returns the worst
    bolt tension (N), the rib bending moment (N m) and the larger rail reaction (N)."""
    c = boat.foot_w / 2
    ys = list(boat.foot_bolt_y) + [-y for y in boat.foot_bolt_y]
    levers = [c + y for y in ys]
    s2 = sum(v * v for v in levers)
    bolts = [moment * v / s2 + lift / len(ys) for v in levers]
    heel = sum(bolts) - lift  # the foot's far edge presses down on the lid
    loads = list(zip(ys, bolts)) + [(-c, -heel)]  # on the rib, upward +
    a = hull.half_beam(hull.rib_x()[0]) + hull.lid.screw_y
    r_plus = -sum(f * (y + a) for y, f in loads) / (2 * a)
    r_minus = -sum(f for _, f in loads) - r_plus
    m_rib = max(abs(r_minus * (y + a) + sum(f * (y - yi) for yi, f in loads if yi < y))
                for y, _ in loads)
    return max(bolts), m_rib, max(abs(r_plus), abs(r_minus))


RAIL_SHARE = 3  # rail screws that share a frame's reaction (60 mm pitch, +/-90 mm of the rib)


def joint_checks(boat: Boat, hull: Hull, lcs: list[LoadCase]) -> list[tuple[str, str, float, float, str]]:
    """Worst case over LC2-LC4 for each link between a foot and its tub:
    (joint, governing case, load, capacity, units)."""
    _, lc2, lc3, lc4 = lcs
    cases = [(lc2, lc2.moment, 0.0), (lc3, lc3.moment, lc3.shear), (lc4, 0.0, lc4.shear)]
    lid = hull.lid
    d = hull.depth - lid.z
    z_rib = lid.rib_t * d * d / 6
    worst = {"bolt": (0.0, ""), "rib": (0.0, ""), "rail": (0.0, "")}
    for lc, m, lift in cases:
        b, mr, r = foot_station(boat, hull, m, lift)
        for key, val in (("bolt", b), ("rib", mr / z_rib), ("rail", r / RAIL_SHARE)):
            if val > worst[key][0]:
                worst[key] = (val, lc.name.split(" ")[0])
    n_bolts = 2 * 2 * len(boat.foot_bolt_y)
    return [
        (f"Foot bolts, M6 A4 ({n_bolts} per foot, in the lid-rib bosses)", worst["bolt"][1],
         worst["bolt"][0], boat.foot_bolt_rating, "N"),
        (f"Lid rib under each frame ({lid.rib_t * 1000:.0f} mm PETG, {d * 1000:.0f} deep)", worst["rib"][1],
         worst["rib"][0], lid.petg_strength, "Pa"),
        (f"Rail screws beside a frame (M4 inserts, {RAIL_SHARE} share)", worst["rail"][1],
         worst["rail"][0], lid.screw_pullout, "N"),
    ]


# ---- Report ----------------------------------------------------------------------------------


def table(headers: list[str], rows: list[list[str]]) -> str:
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    out += ["| " + " | ".join(r) + " |" for r in rows]
    return "\n".join(out)


def variant(beam: float) -> tuple[Hull, Boat]:
    """This boat with another hull beam. The hull centreline spacing is held, so the same
    bridge fits; the fillets shrink with the hull (0.45 x half-breadth at most)."""
    return Hull(beam=beam), Boat(overall_width=Boat().spacing(Hull()) + beam)


def buoyancy(hull: Hull, boat: Boat) -> dict[str, float]:
    """Headline buoyancy numbers for the design condition, fresh water."""
    design = conditions(hull, boat)[1]
    h = draft_for(hull, design.total / RHO_WATER / 2)
    s = boat.spacing(hull)
    enclosed = hydrostatics(hull, hull.depth).volume
    gm_t = h.kb + 2 * (h.it_own + h.awp * (s / 2) ** 2) / (2 * h.volume) - design.kg_z
    at_joint = 2 * hydrostatics(hull, hull.lid.z).volume * RHO_WATER
    keep = min(hull.lid.z - 0.060, hull.depth)
    at_keep = 2 * hydrostatics(hull, keep).volume * RHO_WATER
    return {
        "beam": hull.beam, "enclosed_l": enclosed * 1000, "total_kg": 2 * enclosed * RHO_WATER,
        "design_kg": design.total, "draft": h.draft, "freeboard": hull.depth - h.draft,
        "joint_fb": hull.lid.z - h.draft, "reserve": 2 * enclosed * RHO_WATER / design.total - 1,
        "per_mm": 2 * h.awp * RHO_WATER / 1000, "payload_joint": at_joint - design.total,
        "payload_keep": at_keep - design.total, "gm_t": gm_t, "shell": shell_mass(hull),
        "heel_rail": math.degrees(math.asin(min((hull.lid.z - h.draft) / (s / 2), 1))),
        "heel_lift": math.degrees(math.asin(min(h.draft / (s / 2), 1))),
        "hub_clear": boat.hub_z[0] - h.draft, "flat_deck": hull.flat_deck(sum(boat.frame_x) / 2),
        "foot_drop": boat.foot_drop(hull), "prop_z": boat.drive.prop_z(h.draft), "lwl": h.lwl,
        "bolt_sf": foot_bolt_sf(hull, boat, design, h),
        "half_kg": 2 * hydrostatics(hull, hull.depth / 2).volume * RHO_WATER,
        "q3_kg": 2 * hydrostatics(hull, 0.75 * hull.depth).volume * RHO_WATER,
    }


def foot_bolt_sf(hull: Hull, boat: Boat, design: Condition, h: Hydro) -> float:
    """Foot-bolt SF with the foot trimmed to what the deck can take (flat top + ~1 mm fall)."""
    x = sum(boat.frame_x) / 2
    rd = hull.deck_fillet(x)
    over = math.sqrt(max(rd * rd - (rd - 0.001) ** 2, 0.0))
    w = min(boat.foot_w, hull.flat_deck(x) + 2 * over)
    edge = w / 2 - 0.008
    trimmed = Boat(overall_width=boat.overall_width, foot_w=w,
                   foot_bolt_y=tuple(sorted({max(edge - 0.022, 0.012), edge})))
    lcs = load_cases(trimmed, hull, design, h, Loads())
    bolt = joint_checks(trimmed, hull, lcs)[0]
    return bolt[3] / bolt[2]


def report(hull: Hull | None = None, boat: Boat | None = None) -> None:
    hull, boat, loads = hull or Hull(), boat or Boat(), Loads()
    s = boat.spacing(hull)
    items = mass_budget(hull, boat)
    lid = hull.lid

    print("## Mass budget\n")
    rows = [[i.name, f"{i.kg:.2f}", i.where, f"{i.x:.2f}", f"{i.z:.2f}"] for i in items]
    base = condition("budget", items, 0.0)
    rows.append([f"Growth margin {MARGIN:.0%}", f"{base.total * MARGIN:.2f}", "both", "", ""])
    conds = conditions(hull, boat)
    design = conds[1]
    rows.append(["**Total (design)**", f"**{design.total:.1f}**",
                 f"bridge {design.center_kg:.1f} / hulls {design.hulls_kg:.1f}",
                 f"LCG {design.lcg:.3f}", f"KG {design.kg_z:.3f}"])
    print(table(["Item", "kg", "Carried by", "x (m)", "z (m)"], rows))
    print(f"\nModules (design, incl. margin): bridge {design.center_kg:.1f} kg "
          f"(CG {design.center_lcg:.3f} m fwd of transom), each hull {design.hulls_kg / 2:.1f} kg "
          f"(tub, lid, drive). 'Hulls' items hang below the foot bolts in the load cases.")

    enclosed = hydrostatics(hull, hull.depth).volume
    hd = draft_for(hull, design.total / RHO_WATER / 2)
    fits, fit_note = print_fit(hull)
    rail = hull.beam + 2 * (lid.flange_w + lid.lip_t)
    print("\n## Demi-hull particulars\n")
    print(table(["Parameter", "Value"], [
        ["LOA (hull)", f"{hull.loa * 1000:.0f} mm"],
        ["Beam", f"{hull.beam * 1000:.0f} mm at the shell, {rail * 1000:.0f} mm over the rail"],
        ["Depth, baseline to deck", f"{hull.depth * 1000:.0f} mm"],
        ["Bottom", f"{hull.deadrise_deg:.0f} deg deadrise, chine R{min(hull.chine_r, 0.45 * hull.beam / 2) * 1000:.0f}, "
                   f"deck edge R{min(hull.deck_r, 0.45 * hull.beam / 2) * 1000:.0f}"],
        ["Construction", f"open tub + removable lid, joint plane z {lid.z * 1000:.0f} "
                         f"({(lid.z - hd.draft) * 1000:.0f} mm above the DWL)"],
        ["Rail (lid over the gunwale)", f"{lid.flange_w * 1000:.0f} mm flanges {lid.flange_t * 1000:.0f} + "
                                        f"{lid.flange_t * 1000:.0f} thick, {lid.lip_t * 1000:.1f} lip, "
                                        f"{lid.gasket_d * 1000:.0f} mm cord, {lid_screws(hull, boat.frame_x)} x M4 "
                                        f"({lid.screw_pitch * 1000:.0f} pitch, {lid.screw_pitch_near * 1000:.0f} by the frames), "
                                        f"{rail_length(hull):.2f} m long"],
        ["Bow taper from", f"{hull.taper_start * hull.loa * 1000:.0f} mm fwd of transom"],
        ["Keel rocker from", f"{hull.rocker_start * hull.loa * 1000:.0f} mm fwd, stem keel +{hull.bow_rise * 1000:.0f} mm"],
        ["Keel rise aft", f"+{hull.stern_rise * 1000:.0f} mm at the transom, straight to {hull.stern_rise_end * hull.loa * 1000:.0f} mm fwd"],
        ["Enclosed volume", f"{enclosed * 1000:.1f} L per hull (tub + lid)"],
        ["Shell mass (est.)", f"{shell_mass(hull):.2f} kg per hull + {lid_joint_mass(hull):.2f} kg lid joint"],
        ["Print", f"{fit_note} -> {'fits' if fits else 'DOES NOT FIT'}"],
        ["Foot on the lid deck", f"{hull.flat_deck(sum(boat.frame_x) / 2) * 1000:.0f} mm flat top under a "
                                 f"{boat.foot_w * 1000:.0f} mm foot, deck falls {boat.foot_drop(hull) * 1000:.1f} mm "
                                 f"at its edges -> {'fits (EPDM pad takes it up)' if boat.foot_drop(hull) <= 0.001 else 'DOES NOT FIT: narrow the foot or flatten the deck'}"],
        ["LWL at design draft", f"{hd.lwl * 1000:.0f} mm"],
        ["Slenderness LWL / vol^(1/3)", f"{hd.lwl / hd.volume ** (1 / 3):.2f}"],
        ["Prismatic coefficient Cp", f"{hd.cp:.2f}"],
        ["Immersed transom (design)", f"{(hd.draft - hull.stern_rise) * 1000:.0f} mm deep, {hd.transom_area * 1e4:.0f} cm^2"],
        ["Hull spacing (centrelines)", f"{s * 1000:.0f} mm  (s/L = {s / hd.lwl:.2f})"],
        ["Clear tunnel between hulls", f"{(s - hull.beam) * 1000:.0f} mm"],
        ["Overall width", f"{boat.overall_width * 1000:.0f} mm at the shells, "
                          f"{(boat.overall_width + 2 * (lid.flange_w + lid.lip_t)) * 1000:.0f} over the rails"],
    ]))

    print("\n## Hydrostatics (catamaran, fresh water)\n")
    rows = []
    for c in conds:
        h = draft_for(hull, c.total / RHO_WATER / 2)
        vol = 2 * h.volume
        bm_t = 2 * (h.it_own + h.awp * (s / 2) ** 2) / vol
        bm_l = h.il / h.volume
        gm_t = h.kb + bm_t - c.kg_z
        gm_l = h.kb + bm_l - c.kg_z
        k_roll = c.total * G * gm_t * math.pi / 180
        trim = (c.lcg - h.lcb) / gm_l * h.lwl  # + = bow down, over the waterline length
        reserve = 2 * enclosed * RHO_WATER / c.total - 1
        rows.append([c.name, f"{c.total:.1f}", f"{h.draft * 1000:.0f}",
                     f"{(hull.depth - h.draft) * 1000:.0f}", f"{(lid.z - h.draft) * 1000:.0f}",
                     f"{trim * 1000:+.0f}", f"{2 * h.awp * RHO_WATER / 1000:.2f}", f"{gm_t:.2f}",
                     f"{gm_l:.2f}", f"{k_roll:.1f}", f"{reserve:.0%}"])
    print(table(["Condition", "kg", "Draft mm", "Freeboard mm", "To lid joint mm", "Trim mm (+bow dn)",
                 "kg per mm sink", "GM_T m", "GM_L m", "N m per deg heel", "Reserve buoy."], rows))
    h = hd
    gm_l = h.kb + h.il / h.volume - design.kg_z
    print(f"\nDesign condition: LCB {h.lcb:.3f} m vs LCG {design.lcg:.3f} m fwd of transom; "
          f"KB {h.kb:.3f} m, KG {design.kg_z:.3f} m. Trim: {h.lwl / (design.total * gm_l) * 1000:.0f} mm "
          f"per kg-m of moment. One hull lifts clear at "
          f"~{math.degrees(math.asin(min(h.draft / (s / 2), 1))):.0f} deg heel; righting moment "
          f"there ~{design.total * G * s / 2:.0f} N m.")

    bu = buoyancy(hull, boat)
    print("\n## Buoyancy (design condition, fresh water)\n")
    print(table(["Quantity", "Value"], [
        ["Total buoyancy, both hulls just submerged", f"{bu['total_kg']:.0f} kg ({bu['total_kg'] * G:.0f} N), "
                                                      f"{bu['enclosed_l']:.1f} L per hull"],
        ["Design weight (incl. margin)", f"{bu['design_kg']:.1f} kg -> floats at {bu['draft'] * 1000:.0f} mm, "
                                         f"using {bu['design_kg'] / bu['total_kg']:.0%} of the buoyancy"],
        ["Reserve buoyancy", f"{bu['total_kg'] - bu['design_kg']:.0f} kg ({bu['reserve']:.0%} of the weight)"],
        [f"Buoyancy with the hulls half under ({hull.depth / 2 * 1000:.0f} mm)",
         f"{bu['half_kg']:.0f} kg ({bu['half_kg'] - bu['design_kg']:+.0f} kg over the design weight)"],
        [f"Buoyancy with the hulls 3/4 under ({0.75 * hull.depth * 1000:.0f} mm)",
         f"{bu['q3_kg']:.0f} kg ({bu['q3_kg'] - bu['design_kg']:+.0f} kg over the design weight)"],
        ["Sinkage", f"{bu['per_mm']:.2f} kg per mm ({1 / bu['per_mm']:.1f} mm per kg added)"],
        ["Payload until the lid joint is awash", f"+{bu['payload_joint']:.0f} kg"],
        ["Payload keeping 60 mm freeboard to the joint", f"+{max(bu['payload_keep'], 0):.0f} kg"],
        ["Heel to put the leeward rail in the water", f"{bu['heel_rail']:.0f} deg (windward hull lifts at "
                                                      f"{bu['heel_lift']:.0f} deg)"],
    ]))

    print("\n## Arched bridge\n")
    outline = frame_outline(boat, hull)
    arch = arch_centreline(boat, hull)
    arch_len = sum(math.dist(a, b) for a, b in zip(arch, arch[1:]))
    hub_bottom = boat.hub_z[0]
    print(table(["Parameter", "Value"], [
        ["Frames", f"2x 1/4\" 6061-T6 plate, {boat.frame_h * 1000:.0f} mm deep, at x = "
                   f"{boat.frame_x[0] * 1000:.0f} / {boat.frame_x[1] * 1000:.0f} mm (over the lid ribs at J2 / J3)"],
        ["Frame span / length", f"{s * 1000:.0f} mm foot to foot, {arch_len * 1000:.0f} mm along the arch"],
        ["Frame blank", f"{(max(p[0] for p in outline) - min(p[0] for p in outline)) * 1000:.0f} x "
                        f"{(max(p[1] for p in outline) - min(p[1] for p in outline)) * 1000:.0f} mm, "
                        f"{frame_mass(boat, hull):.2f} kg each after {boat.frame_lightening:.0%} lightening"],
        ["Hub (cowl)", f"{2 * boat.hub_half[0] * 1000:.0f} x {2 * boat.hub_half[1] * 1000:.0f} mm, "
                       f"z {boat.hub_z[0] * 1000:.0f}-{boat.hub_z[2] * 1000:.0f} mm (belt line {boat.hub_z[1] * 1000:.0f}), centred {boat.hub_x * 1000:.0f} fwd"],
        ["IP67 box in the hub", f"{boat.box[0] * 1000:.0f} x {boat.box[1] * 1000:.0f} x {boat.box[2] * 1000:.0f} mm on the frame tops "
                                f"({'fits' if boat.box_clearance() > 0 else 'DOES NOT FIT'} inside the cowl, margin {boat.box_clearance():+.3f})"],
        ["Hub underside above DWL", f"{(hub_bottom - hd.draft) * 1000:.0f} mm"],
        ["Mast top (GNSS)", f"{boat.mast_top * 1000:.0f} mm above baseline"],
    ]))
    if any(abs(a - b) > 0.02 for a, b in zip(boat.frame_x, hull.rib_x())):
        print("\n**WARNING: the arch frames are not over the lid ribs (Lid.rib_joints vs Boat.frame_x).**")

    print("\n## Frame loads (per frame, design condition)\n")
    lcs = load_cases(boat, hull, design, h, loads)
    z_sec = boat.frame_t * boat.frame_h**2 / 6
    rows = []
    for lc in lcs:
        sig = lc.moment / z_sec
        rows.append([lc.name, f"{lc.moment:.0f}", f"{lc.shear:.0f}", f"{sig / 1e6:.0f}",
                     f"{276e6 / sig:.1f}"])
    print(table(["Load case", "Moment N m", "Shear N", "Stress MPa", "SF on yield"], rows))

    print("\n## Foot, lid and rail joints (worst of LC2-LC4)\n")
    rows = []
    for name, case, load, cap, unit in joint_checks(boat, hull, lcs):
        scale, u = (1e6, "MPa") if unit == "Pa" else (1.0, "N")
        rows.append([name, case, f"{load / scale:.0f} {u}", f"{cap / scale:.0f} {u}", f"{cap / load:.1f}"])
    print(table(["Joint", "Case", "Load", "Capacity", "SF"], rows))
    drive = boat.drive
    print(f"\nThe foot pivots on its far edge and the bolts hold the near side down; each lid rib "
          f"carries that couple out to the rail, where ~{RAIL_SHARE} screws take it into the tub. "
          f"Target SF {loads.sf_target:g}. The M6 bolts themselves are good for ~9 kN; the printed "
          f"bosses and inserts govern, so pull-test a boss and an insert from your printer.")
    print(f"\nOutdrive: prop axis z {drive.prop_z(hd.draft) * 1000:.0f} mm, motor axis z "
          f"{drive.motor_z * 1000:.0f} mm -> belt centres {drive.centre_distance(hd.draft) * 1000:.0f} mm, "
          f"HTD 3M-{drive.belt_w * 1000:.0f} belt {drive.belt_teeth(hd.draft)} teeth "
          f"({drive.belt_teeth(hd.draft) * drive.belt_pitch * 1000:.0f} mm), "
          f"{drive.pulley_teeth}T pulleys ({drive.pulley_pd * 1000:.1f} PD).")


def compare(beams: list[float]) -> None:
    """Side-by-side buoyancy and fit summary for several hull beams (same bridge)."""
    cols = [buoyancy(*variant(b)) for b in beams]
    base_boat = Boat()

    def row(label: str, fmt) -> list[str]:
        return [label] + [fmt(c) for c in cols]

    heads = ["Hull beam"] + [f"{c['beam'] * 1000:.0f} mm ({c['beam'] / 0.0254:.1f} in)" for c in cols]
    print(table(heads, [
        row("Enclosed volume per hull", lambda c: f"{c['enclosed_l']:.1f} L"),
        row("Total buoyancy (both hulls)", lambda c: f"{c['total_kg']:.0f} kg"),
        row("Design weight", lambda c: f"{c['design_kg']:.1f} kg"),
        row("Reserve buoyancy", lambda c: f"{c['total_kg'] - c['design_kg']:.0f} kg ({c['reserve']:.0%})"),
        row("Buoyancy, hulls half under", lambda c: f"{c['half_kg']:.0f} kg ({c['half_kg'] - c['design_kg']:+.0f})"),
        row("Buoyancy, hulls 3/4 under", lambda c: f"{c['q3_kg']:.0f} kg ({c['q3_kg'] - c['design_kg']:+.0f})"),
        row("Design draft", lambda c: f"{c['draft'] * 1000:.0f} mm"),
        row("Freeboard to deck / to lid joint", lambda c: f"{c['freeboard'] * 1000:.0f} / {c['joint_fb'] * 1000:.0f} mm"),
        row("Sinkage", lambda c: f"{c['per_mm']:.2f} kg/mm"),
        row("Payload until the joint is awash", lambda c: f"+{c['payload_joint']:.0f} kg"),
        row("Payload keeping 60 mm to the joint", lambda c: f"+{max(c['payload_keep'], 0):.0f} kg"),
        row("GM_T", lambda c: f"{c['gm_t']:.2f} m"),
        row("Heel to wet the leeward rail", lambda c: f"{c['heel_rail']:.0f} deg"),
        row("Hub underside above water", lambda c: f"{c['hub_clear'] * 1000:.0f} mm"),
        row("Prop axis above baseline", lambda c: f"{c['prop_z'] * 1000:.0f} mm"),
        row("Shell mass per hull", lambda c: f"{c['shell']:.2f} kg"),
        row(f"Flat deck under the {base_boat.foot_w * 1000:.0f} mm feet",
            lambda c: f"{c['flat_deck'] * 1000:.0f} mm, edge falls {c['foot_drop'] * 1000:.1f} mm "
                      f"({'fits' if c['foot_drop'] <= 0.001 else 'too narrow'})"),
        row("Foot-bolt SF, foot trimmed to the deck", lambda c: f"{c['bolt_sf']:.1f}"),
    ]))
    print("\nSame bridge and hull spacing in every column; deck and chine radii shrink with the hull "
          "(to 0.45 x half-breadth). Bolt SF target 3.")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--beam", type=float, help="report for another hull beam, m (6 in = 0.1524)")
    ap.add_argument("--compare", type=float, nargs="+", metavar="BEAM",
                    help="side-by-side buoyancy summary for these beams, m")
    args = ap.parse_args()
    if args.compare:
        compare(args.compare)
    elif args.beam:
        report(*variant(args.beam))
    else:
        report()


if __name__ == "__main__":
    main()
