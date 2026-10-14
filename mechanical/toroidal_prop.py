"""Parametric toroidal (looped-blade) propeller for the D.R.E.A.M.S drives, plus a thrust stand.

Each "blade" is a closed loop: a leading leg leaves the hub, bends through a tip bridge at the
full radius, and comes back to the hub as a trailing leg further aft. Blade sections are
NACA 4-digit foils laid along the local helix of the chosen pitch. Two hubs:
    --hub shaft  (default) for the belt outdrive: a 20 mm hub with a D-bore for a 5 mm
                 stainless shaft (4.5 mm across the flat), held by an M5 nylock nut
    --hub m200   for a Blue Robotics M200: copies their weedless prop's interface (measured
                 from their CAD) - a cup over the rotor, 2x M3 on a 19 mm circle, open barrel

Stdlib only:
    python mechanical/toroidal_prop.py                    # default design
    python mechanical/toroidal_prop.py --loops 3 --pitch 75 --name t3_p75
    python mechanical/toroidal_prop.py --hand LH          # the opposite-rotation prop
    python mechanical/toroidal_prop.py --hub m200         # to fit a Blue Robotics M200 instead
    python mechanical/toroidal_prop.py --list             # every parameter and its default
Outputs in mechanical/props/<name>/:
    <name>.stl            print this (mm, prop axis = +Z, motor side at Z = 0)
    <name>_spinner.stl    optional press-in tail cone (M200 hub only)
    <name>_viewer.html    spin it in a browser;  <name>.png  still render
    curves/*.txt          loop centreline + section curves for SolidWorks
    report.md             geometry, mass, clearances, design-point rpm
    mechanical/props/thrust_stand.pdf (+ .html)  the bench rig drawing, made once
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
import struct
import subprocess
from dataclasses import asdict, dataclass, fields
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "props"
VENDOR = HERE / "render" / "vendor"

Vec = tuple[float, float, float]


@dataclass
class Prop:
    name: str = "toroidal_3loop_p75"
    hand: str = "RH"  # RH turns clockwise seen from astern; LH is the mirror (the other hull)
    loops: int = 3  # number of looped blades (2 = less wetted area, 3 = smoother)
    diameter: float = 110.0  # mm; the stock weedless prop is 112
    pitch: float = 75.0  # mm per revolution (weedless ~66)
    loop_dz: float = 20.0  # mm, axial length of the tip bridge (leading leg to trailing leg)
    loop_dtheta: float = 60.0  # deg, angle between a loop's two legs at the hub (petal width)
    skew: float = 15.0  # deg, sweeps the petal back against rotation (sheds weed)
    fullness: float = 0.8  # radius profile exponent; < 1 = fuller loop near the tip
    chord_root: float = 20.0  # mm
    chord_tip: float = 14.0  # mm, at the tip bridge
    thick_root: float = 0.11  # thickness / chord
    thick_tip: float = 0.08
    camber: float = 0.02  # NACA max camber / chord
    camber_pos: float = 0.40
    min_te: float = 0.45  # mm, minimum trailing-edge thickness (resin printers hold ~0.4)
    hub: str = "shaft"  # "shaft" (belt outdrive) or "m200"
    # shaft hub (belt outdrive)
    shaft_hub_od: float = 20.0  # mm
    shaft_d: float = 5.0  # 316 stainless prop shaft
    shaft_flat: float = 0.5  # depth of the D-flat (4.5 mm across the flat)
    shaft_clear: float = 0.15  # print clearance on the bore (diameter)
    # M200 hub = Blue Robotics weedless-prop interface to the rotor (measured from their CAD)
    hub_od: float = 40.0  # mm (weedless 39.5)
    cup_id: float = 36.8  # slides over the ~36.5 mm rotor bell; 0.3 mm print clearance
    cup_depth: float = 29.0
    floor_t: float = 4.0
    screw_pcd: float = 19.0  # 2x M3 on this circle, at +/-90 deg
    screw_hole: float = 3.4
    centre_hole: float = 11.5  # clears the rotor's centre boss / shaft
    barrel_bore: float = 34.0  # open aft barrel: hex-key access to the screws
    hub_len: float = 0.0  # 0 = just long enough for the loop roots
    density: float = 1.2  # g/cm^3, resin (Formlabs Tough ~1.2); PETG 1.27, nylon PA12 1.01


# ---- small vector helpers --------------------------------------------------------------------


def add(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def mul(a, k):
    return (a[0] * k, a[1] * k, a[2] * k)


def dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def norm(a):
    n = math.sqrt(dot(a, a)) or 1.0
    return (a[0] / n, a[1] / n, a[2] / n)


class Mesh:
    def __init__(self, name: str):
        self.name = name
        self.v: list[Vec] = []
        self.f: list[tuple[int, int, int]] = []

    def grid(self, rows, closed=True):
        base, n = len(self.v), len(rows[0])
        for r in rows:
            self.v.extend(r)
        cols = n if closed else n - 1
        for i in range(len(rows) - 1):
            for j in range(cols):
                a, b = base + i * n + j, base + i * n + (j + 1) % n
                c, d = base + (i + 1) * n + (j + 1) % n, base + (i + 1) * n + j
                self.f += [(a, b, c), (a, c, d)]

    def fan(self, ring):
        c = mul(tuple(sum(p[k] for p in ring) for k in range(3)), 1 / len(ring))
        base = len(self.v)
        self.v.append(c)
        self.v.extend(ring)
        for j in range(len(ring)):
            self.f.append((base, base + 1 + j, base + 1 + (j + 1) % len(ring)))

    def signed_volume(self) -> float:
        return sum(dot(self.v[a], cross(self.v[b], self.v[c])) for a, b, c in self.f) / 6

    def volume(self) -> float:
        return abs(self.signed_volume())

    def outward(self) -> "Mesh":
        """Flip the winding if the normals point inwards (slicers expect outward normals)."""
        if self.signed_volume() < 0:
            self.f = [(a, c, b) for a, b, c in self.f]
        return self


# ---- blade geometry ------------------------------------------------------------------------


def naca(t: float, m: float, p: float, n: int = 22) -> list[tuple[float, float]]:
    """Closed NACA 4-digit section, chord 0..1, TE -> upper -> LE -> lower -> TE (open loop)."""
    xs = [0.5 * (1 - math.cos(math.pi * i / n)) for i in range(n + 1)]  # 0 at LE, 1 at TE
    upper, lower = [], []
    for x in xs:
        yt = 5 * t * (0.2969 * math.sqrt(x) - 0.1260 * x - 0.3516 * x**2 + 0.2843 * x**3 - 0.1036 * x**4)
        if m > 0 and x < p:
            yc, dy = m / p**2 * (2 * p * x - x * x), 2 * m / p**2 * (p - x)
        elif m > 0:
            yc, dy = m / (1 - p) ** 2 * (1 - 2 * p + 2 * p * x - x * x), 2 * m / (1 - p) ** 2 * (p - x)
        else:
            yc, dy = 0.0, 0.0
        th = math.atan(dy)
        upper.append((x - yt * math.sin(th), yc + yt * math.cos(th)))
        lower.append((x + yt * math.sin(th), yc - yt * math.cos(th)))
    return list(reversed(upper)) + lower[1:-1]


def loop_centreline(p: Prop, k: int, n: int = 72) -> list[tuple[float, Vec]]:
    """(s, point) along loop k, s from -0.02 (inside the hub) to 1.02."""
    w = 1 if p.hand == "RH" else -1
    rot = -w  # RH turns -theta in this frame (clockwise seen from astern, +Z)
    R = p.diameter / 2
    r_in = hub_radius(p) - 1.5  # roots buried in the hub wall
    z_a = root_z(p)
    theta0 = 2 * math.pi * k / p.loops
    pts = []
    for i in range(n + 1):
        s = -0.02 + 1.04 * i / n
        sc = min(max(s, 0.0), 1.0)
        r = r_in + (R - r_in) * math.sin(math.pi * sc) ** p.fullness
        if s < 0 or s > 1:
            r = r_in - 1.5 * abs(s - sc) / 0.02
        # legs sweep in angle near the hub; the tip bridge runs axially, so its span is never
        # parallel to the flow (that is what makes it a ring-wing segment, not a twisted ribbon)
        ang = sc + math.sin(2 * math.pi * sc) / (2 * math.pi)
        ax = sc - math.sin(2 * math.pi * sc) / (2 * math.pi)
        th = theta0 + rot * (math.radians(p.loop_dtheta) * ang - math.radians(p.skew) * math.sin(math.pi * sc))
        z = z_a + p.loop_dz * ax
        pts.append((s, (r * math.cos(th), r * math.sin(th), z)))
    return pts


def hub_radius(p: Prop) -> float:
    return (p.shaft_hub_od if p.hub == "shaft" else p.hub_od) / 2


def root_z(p: Prop) -> float:
    """Axial position of a loop's leading root: clear of the hub's front (or the M200 floor)."""
    r_in = hub_radius(p) - 1.5
    half_axial = 0.5 * p.chord_root * math.sin(math.atan(p.pitch / (2 * math.pi * r_in)))
    start = 0.0 if p.hub == "shaft" else p.cup_depth + p.floor_t
    return start + 2.5 + half_axial


def hub_length(p: Prop) -> float:
    r_in = hub_radius(p) - 1.5
    half_axial = 0.5 * p.chord_root * math.sin(math.atan(p.pitch / (2 * math.pi * r_in)))
    return p.hub_len or root_z(p) + p.loop_dz + half_axial + 4.0


def loop_mesh(p: Prop, k: int) -> tuple[Mesh, list[list[Vec]]]:
    w = 1 if p.hand == "RH" else -1
    rot = -w
    line = loop_centreline(p, k)
    rows, sections = [], []
    for i, (s, c) in enumerate(line):
        a = line[max(i - 1, 0)][1]
        b = line[min(i + 1, len(line) - 1)][1]
        T = norm(sub(b, a))
        r = math.hypot(c[0], c[1])
        e_th = (-c[1] / r, c[0] / r, 0.0)
        # blade element moves along the helix: rotation plus advance towards the motor (-Z)
        h = norm(add(mul(e_th, rot * r), (0.0, 0.0, -p.pitch / (2 * math.pi))))
        cdir = norm(sub(h, mul(T, dot(h, T))))
        ndir = norm(cross(T, cdir))
        if ndir[2] > 0:  # suction side faces forward (-Z)
            ndir = mul(ndir, -1)
        sc = min(max(s, 0.0), 1.0)
        u = math.sin(math.pi * sc) ** 1.5
        chord = p.chord_root + (p.chord_tip - p.chord_root) * u
        tr = p.thick_root + (p.thick_tip - p.thick_root) * u
        tr = max(tr, 1.0 / chord)
        sec = []
        for x, y in naca(tr, p.camber, p.camber_pos):
            y += math.copysign(max(0.0, p.min_te / 2 / chord - abs(y)) * x**4, y if y else 1.0)
            sec.append(add(add(c, mul(cdir, (0.5 - x) * chord)), mul(ndir, y * chord)))
        rows.append(sec)
        if 0.0 <= s <= 1.0 and i % 6 == 0:
            sections.append(sec + sec[:1])
    m = Mesh(f"loop {k + 1}")
    m.grid(rows)
    m.fan(list(reversed(rows[0])))
    m.fan(rows[-1])
    m.rows = [(s_, r_) for (s_, _), r_ in zip(line, rows)]
    return m, sections


# ---- hub -----------------------------------------------------------------------------------


def revolve(name: str, profile: list[tuple[float, float]], n: int = 96) -> Mesh:
    """Revolve a closed (r, z) profile (r > 0 everywhere) about Z."""
    m = Mesh(name)
    rows = [[(r * math.cos(2 * math.pi * j / n), r * math.sin(2 * math.pi * j / n), z) for j in range(n)]
            for r, z in profile]
    m.grid(rows + rows[:1], closed=True)
    return m


def ear_clip(poly: list[tuple[float, float]]) -> list[tuple[int, int, int]]:
    """Triangulate a simple counter-clockwise polygon."""
    idx = list(range(len(poly)))

    def area2(a, b, c):
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])

    def inside(p_, a, b, c):
        return area2(a, b, p_) >= -1e-12 and area2(b, c, p_) >= -1e-12 and area2(c, a, p_) >= -1e-12

    tris = []
    while len(idx) > 3:
        for k in range(len(idx)):
            i0, i1, i2 = idx[k - 1], idx[k], idx[(k + 1) % len(idx)]
            a, b, c = poly[i0], poly[i1], poly[i2]
            if area2(a, b, c) <= 1e-12:
                continue
            if any(inside(poly[j], a, b, c) for j in idx if j not in (i0, i1, i2)):
                continue
            tris.append((i0, i1, i2))
            idx.pop(k)
            break
        else:
            raise RuntimeError("ear clipping failed (polygon not simple?)")
    tris.append(tuple(idx))
    return tris


def floor_mesh(p: Prop, r_out: float, z0: float, z1: float, n: int = 96) -> Mesh:
    """Floor disk with a centre hole and 2 screw holes on the Y axis, as one watertight shell.
    Triangulated as four simple quadrant polygons that share their seam edges."""
    rc, hs, h = p.centre_hole / 2, p.screw_hole / 2, p.screw_pcd / 2

    def arc(r, a0, a1, cx=0.0, cy=0.0, steps=24):
        return [(cx + r * math.cos(a0 + (a1 - a0) * i / steps), cy + r * math.sin(a0 + (a1 - a0) * i / steps))
                for i in range(steps + 1)]

    q = n // 4
    quads = []
    for k in range(4):  # quadrant k spans polar angle k*90 .. (k+1)*90 degrees, traversed CCW
        a0, a1 = k * math.pi / 2, (k + 1) * math.pi / 2

        def seam(alpha, outward):
            """Points along the radial seam at alpha; screw holes sit on the +/-Y seams."""
            u = (math.cos(alpha), math.sin(alpha))
            has_hole = abs(math.cos(alpha)) < 1e-9
            if not has_hole:
                pts = [(rc * u[0], rc * u[1]), (r_out * u[0], r_out * u[1])]
                return pts if outward else pts[::-1]
            cx, cy = h * u[0], h * u[1]
            if outward:  # inner point -> round the +v side of the hole -> outer point
                betas = [alpha + math.pi - math.pi * i / 12 for i in range(13)]
                pts = [(rc * u[0], rc * u[1])] + [(cx + hs * math.cos(b), cy + hs * math.sin(b)) for b in betas]
                return pts + [(r_out * u[0], r_out * u[1])]
            betas = [alpha - math.pi * i / 12 for i in range(13)]  # outer -> round the -v side -> inner
            pts = [(r_out * u[0], r_out * u[1])] + [(cx + hs * math.cos(b), cy + hs * math.sin(b)) for b in betas]
            return pts + [(rc * u[0], rc * u[1])]

        poly = seam(a0, True) + arc(r_out, a0, a1, steps=q)[1:-1] + seam(a1, False) + arc(rc, a1, a0, steps=q // 2)[1:-1]
        clean = [poly[0]]
        for pt in poly[1:]:
            if math.dist(pt, clean[-1]) > 1e-9:
                clean.append(pt)
        if math.dist(clean[0], clean[-1]) < 1e-9:
            clean.pop()
        quads.append(clean)
    m = Mesh("floor")
    for poly in quads:
        # ensure counter-clockwise
        area = sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(poly, poly[1:] + poly[:1]))
        if area < 0:
            poly.reverse()
        base = len(m.v)
        m.v += [(x, y, z0) for x, y in poly] + [(x, y, z1) for x, y in poly]
        np_ = len(poly)
        for a, b, c in ear_clip(poly):
            m.f.append((base + a, base + c, base + b))
            m.f.append((base + np_ + a, base + np_ + b, base + np_ + c))
    walls = [arc(r_out, 0, 2 * math.pi, steps=n)[:-1]]  # outer wall faces out (CCW)
    walls += [arc(rc, 2 * math.pi, 0, steps=n // 2)[:-1],  # hole walls face into the holes (CW)
              arc(hs, 2 * math.pi, 0, 0.0, h, 24)[:-1], arc(hs, 2 * math.pi, 0, 0.0, -h, 24)[:-1]]
    for ring in walls:
        m.grid([[(x, y, z0) for x, y in ring], [(x, y, z1) for x, y in ring]])
    return m


def shaft_hub(p: Prop) -> Mesh:
    """20 mm hub with a D-bore: the D-flat drives it, an M5 nylock on the shaft end holds it."""
    ro, L, n = p.shaft_hub_od / 2, hub_length(p), 64
    rb = p.shaft_d / 2 + p.shaft_clear / 2
    yf = rb - p.shaft_flat - p.shaft_clear / 2  # the flat, measured from the centre
    xf = math.sqrt(max(rb * rb - yf * yf, 0.0))
    outer, inner = [], []
    for j in range(n):
        t = 2 * math.pi * j / n
        outer.append((ro * math.cos(t), ro * math.sin(t)))
        x, y = rb * math.cos(t), rb * math.sin(t)
        if y < -yf:
            x, y = max(-xf, min(xf, x)), -yf
        inner.append((x, y))
    rows = [[(x, y, 0.0) for x, y in outer], [(x, y, L) for x, y in outer],
            [(x, y, L) for x, y in inner], [(x, y, 0.0) for x, y in inner]]
    m = Mesh("hub")
    m.grid(rows + rows[:1])
    return m


def hub_meshes(p: Prop) -> list[Mesh]:
    if p.hub == "shaft":
        return [shaft_hub(p)]
    ro, rc, rb = p.hub_od / 2, p.cup_id / 2, p.barrel_bore / 2
    zf0, zf1, L = p.cup_depth, p.cup_depth + p.floor_t, hub_length(p)
    shell = revolve("hub", [(rc, 0.0), (ro - 0.6, 0.0), (ro, 0.6), (ro, L - 1.0), (ro - 1.0, L),
                            (rb, L), (rb, zf1 - 0.01), (rc, zf0 + 0.01)])
    return [shell, floor_mesh(p, rc + 0.3, zf0, zf1)]


def spinner_mesh(p: Prop) -> Mesh:
    rb = p.barrel_bore / 2
    cone = [(rb - 0.25, -8.0), (rb - 0.25, 0.0), (p.hub_od / 2 - 1.0, 0.0)]
    cone += [((p.hub_od / 2 - 1.0) * math.cos(math.pi / 2 * i / 10), 22.0 * math.sin(math.pi / 2 * i / 10))
             for i in range(1, 10)]
    cone += [(0.8, 22.0), (0.8, 20.5)]
    inner = [((rb - 2.0) * math.cos(math.pi / 2 * i / 8), 20.0 * math.sin(math.pi / 2 * i / 8)) for i in range(8, -1, -1)]
    return revolve("spinner", cone + [(max(r, 0.8), z) for r, z in inner] + [(rb - 2.0, -8.0)])


# ---- checks and report -----------------------------------------------------------------------


def min_gap(a: list[Vec], b: list[Vec]) -> float:
    best = 1e9
    for pa in a[::3]:
        for pb in b[::3]:
            d = (pa[0] - pb[0]) ** 2 + (pa[1] - pb[1]) ** 2 + (pa[2] - pb[2]) ** 2
            if d < best:
                best = d
    return math.sqrt(best)


def design_rpm(p: Prop, v: float, slip: float) -> float:
    return v * (1 - 0.03) / (p.pitch / 1000 * (1 - slip)) * 60


def report(p: Prop, loops: list[Mesh], hub: list[Mesh], folder: Path) -> str:
    vol = sum(m.volume() for m in loops + hub) / 1000  # cm^3 (overlaps counted twice: small)
    # leading vs trailing leg of loop 1 (away from the tip bridge, where they are one surface)
    lead = [v for s_, row in loops[0].rows if 0.04 <= s_ <= 0.36 for v in row]
    trail = [v for s_, row in loops[0].rows if 0.64 <= s_ <= 0.96 for v in row]
    gap_legs = min_gap(lead, trail)
    gap_loops = min_gap(loops[0].v, loops[1].v) if len(loops) > 1 else float("nan")
    kv, volts = (380 if p.hub == "shaft" else 470), 18.0
    lines = [
        f"# {p.name}",
        "",
        f"{p.loops}-loop toroidal prop, {p.diameter:.0f} mm, pitch {p.pitch:.0f} mm, {p.hand}.",
        "",
        "| Check | Value |",
        "|---|---|",
        f"| Printed volume / mass | {vol:.1f} cm^3, ~{vol * p.density:.0f} g at {p.density} g/cm^3 |",
        f"| Gap between the legs of one loop | {gap_legs:.1f} mm |",
        f"| Gap between neighbouring loops | {gap_loops:.1f} mm |",
        (f"| Hub | {p.shaft_hub_od:.0f} OD x {hub_length(p):.0f} long, D-bore for a {p.shaft_d:.0f} mm shaft "
         f"({p.shaft_d - p.shaft_flat:.1f} across the flat), M5 nylock on the shaft end |" if p.hub == "shaft" else
         f"| Hub | {p.hub_od:.0f} OD x {hub_length(p):.0f} long; cup {p.cup_id} ID x {p.cup_depth:.0f} deep over the "
         f"M200 rotor; 2x {p.screw_hole} on {p.screw_pcd:.0f} PCD |"),
        f"| Rpm at 1.5 m/s (30 % slip) | {design_rpm(p, 1.5, 0.30):.0f} |",
        f"| Rpm at 3.0 m/s (40 % slip) | {design_rpm(p, 3.0, 0.40):.0f} |",
        (f"| Drive | 1:1 belt from a ~{kv} KV outrunner: {kv * volts:.0f} rpm no-load at {volts:.0f} V |"
         if p.hub == "shaft" else f"| M200 no-load speed at {volts:.0f} V | {kv * volts:.0f} rpm (direct drive) |"),
        "",
        "Gaps under ~2 mm print poorly and trap weed; open them with loop_dz / loop_dtheta / skew.",
        "Balance every print on a knife-edge or magnetic balancer before running it.",
    ]
    text = "\n".join(lines) + "\n"
    (folder / "report.md").write_text(text, encoding="utf-8")
    (folder / "params.json").write_text(json.dumps(asdict(p), indent=2), encoding="utf-8")
    return text


# ---- output ----------------------------------------------------------------------------------


def write_stl(meshes: list[Mesh], path: Path) -> None:
    tris = [(m.v[a], m.v[b], m.v[c]) for m in meshes for a, b, c in m.f]
    with open(path, "wb") as fh:
        fh.write(b"D.R.E.A.M.S toroidal prop".ljust(80, b" "))
        fh.write(struct.pack("<I", len(tris)))
        for a, b, c in tris:
            nrm = norm(cross(sub(b, a), sub(c, a)))
            fh.write(struct.pack("<12fH", *nrm, *a, *b, *c, 0))


def write_curves(p: Prop, folder: Path, all_sections: list[list[list[Vec]]]) -> None:
    cd = folder / "curves"
    cd.mkdir(exist_ok=True)
    for k in range(p.loops):
        pts = [c for _, c in loop_centreline(p, k) if True]
        (cd / f"loop{k + 1}_centreline.txt").write_text("".join(f"{x:.3f} {y:.3f} {z:.3f}\n" for x, y, z in pts))
        for j, sec in enumerate(all_sections[k]):
            (cd / f"loop{k + 1}_section{j:02d}.txt").write_text("".join(f"{x:.3f} {y:.3f} {z:.3f}\n" for x, y, z in sec))


VIEWER_JS = r"""
THREE.ColorManagement.legacyMode = false;
const q = new URLSearchParams(location.hash.slice(1));
const STILL = q.has('still');
const W = STILL ? +q.get('w') : innerWidth, H = STILL ? +q.get('h') : innerHeight;
const r = new THREE.WebGLRenderer({antialias: true, preserveDrawingBuffer: true});
r.setPixelRatio(STILL ? 1 : devicePixelRatio); r.setSize(W, H);
r.outputEncoding = THREE.sRGBEncoding; r.toneMapping = THREE.ACESFilmicToneMapping;
r.shadowMap.enabled = true; document.body.appendChild(r.domElement);
const scene = new THREE.Scene(); scene.background = new THREE.Color(0xf2eeeb);
const env = new THREE.Scene();
env.add(new THREE.Mesh(new THREE.SphereGeometry(20, 32, 16), new THREE.MeshBasicMaterial({color: 0xd8dde3, side: THREE.BackSide})));
const lamp = new THREE.Mesh(new THREE.SphereGeometry(3, 16, 8), new THREE.MeshBasicMaterial({color: 0xffffff})); lamp.position.set(8, 10, 6); env.add(lamp);
scene.environment = new THREE.PMREMGenerator(r).fromScene(env, 0.03).texture;
const mats = {
  loop: new THREE.MeshPhysicalMaterial({color: 0xf07818, roughness: 0.3, clearcoat: 1, clearcoatRoughness: 0.15, side: THREE.DoubleSide}),
  hub: new THREE.MeshPhysicalMaterial({color: 0x2b2f35, roughness: 0.4, clearcoat: 0.6, side: THREE.DoubleSide}),
};
const prop = new THREE.Group();
for (const m of window.PROP.meshes) {
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.Float32BufferAttribute(m.pos, 3)); g.setIndex(m.idx); g.computeVertexNormals();
  const mesh = new THREE.Mesh(g, m.name.startsWith('loop') ? mats.loop : mats.hub); mesh.castShadow = true; prop.add(mesh);
}
scene.add(prop);  // prop axis along X, aft end (spinner side) towards +X
const sun = new THREE.DirectionalLight(0xffffff, 1.8); sun.position.set(0.25, 0.45, 0.3); sun.castShadow = true; scene.add(sun);
scene.add(new THREE.HemisphereLight(0xffffff, 0x445566, 0.5));
const floor = new THREE.Mesh(new THREE.PlaneGeometry(2, 2), new THREE.ShadowMaterial({opacity: 0.18}));
floor.rotation.x = -Math.PI / 2; floor.position.y = -0.06; floor.receiveShadow = true; scene.add(floor);
const cam = new THREE.PerspectiveCamera(25, W / H, 0.01, 10);
const VIEWS = {three: [0.20, 0.11, 0.22], axial: [0.42, 0.0, 0.0], side: [0.0, 0.0, 0.40], front: [-0.42, 0.0, 0.0]};
function view(n) { cam.position.set(...VIEWS[n]); cam.lookAt(0, 0, 0); if (ctl) { ctl.target.set(0, 0, 0); ctl.update(); } }
let ctl = null;
if (!STILL && THREE.OrbitControls) { ctl = new THREE.OrbitControls(cam, r.domElement); ctl.enableDamping = true; }
view(q.get('view') || 'three');
if (STILL) { r.render(scene, cam); document.title = 'ready'; }
else {
  const ui = document.getElementById('ui');
  for (const n of Object.keys(VIEWS)) { const b = document.createElement('button'); b.textContent = n; b.onclick = () => view(n); ui.appendChild(b); }
  const spin = document.createElement('button'); spin.textContent = 'spin'; let on = false; spin.onclick = () => on = !on; ui.appendChild(spin);
  addEventListener('resize', () => { cam.aspect = innerWidth / innerHeight; cam.updateProjectionMatrix(); r.setSize(innerWidth, innerHeight); });
  (function loop() { requestAnimationFrame(loop); if (on) prop.rotation.x += 0.03; if (ctl) ctl.update(); r.render(scene, cam); })();
}
"""


def write_viewer(meshes: list[Mesh], p: Prop, path: Path) -> None:
    zc = hub_length(p) / 2

    def to_three(v):  # prop axis Z -> three.js X (aft end towards +X), proper rotation
        return (round((v[2] - zc) / 1000, 5), round(v[1] / 1000, 5), round(-v[0] / 1000, 5))

    data = {"meshes": [{"name": m.name, "pos": [c for v in m.v for c in to_three(v)],
                        "idx": [i for f in m.f for i in f]} for m in meshes]}
    three = (VENDOR / "three.min.js").read_text(encoding="utf-8")
    orbit = (VENDOR / "OrbitControls.js").read_text(encoding="utf-8")
    info = f"{p.name}: {p.loops}-loop toroidal prop, {p.diameter:.0f} mm, pitch {p.pitch:.0f}, {p.hand}. Drag to orbit."
    html = (f"<!DOCTYPE html><html><head><meta charset='utf-8'><title>{p.name}</title><style>body{{margin:0;"
            f"overflow:hidden;font-family:Arial}}#ui{{position:absolute;top:10px;left:10px}}#ui button{{margin-right:4px;"
            f"padding:6px 10px;border:0;border-radius:4px;background:#20262ecc;color:#fff}}#info{{position:absolute;"
            f"bottom:10px;left:10px;font-size:13px}}</style></head><body><div id='ui'></div><div id='info'>{info}</div>"
            f"<script>/* three.js r147, MIT licence */\n{three}</script><script>{orbit}</script>"
            f"<script>window.PROP = {json.dumps(data, separators=(',', ':'))};</script><script>{VIEWER_JS}</script></body></html>")
    path.write_text(html, encoding="utf-8")


def browser() -> str | None:
    for cand in (r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                 r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
                 r"C:\Program Files\Google\Chrome\Application\chrome.exe"):
        if Path(cand).exists():
            return cand
    return shutil.which("msedge") or shutil.which("chrome") or shutil.which("chromium")


def screenshot(html: Path, png: Path, view: str, w: int = 1600, h: int = 1000) -> bool:
    exe = browser()
    if not exe:
        return False
    subprocess.run([exe, "--headless=new", "--use-angle=swiftshader", "--enable-unsafe-swiftshader",
                    "--hide-scrollbars", f"--window-size={w},{h}", "--virtual-time-budget=15000",
                    f"--screenshot={png}", html.as_uri() + f"#still&view={view}&w={w}&h={h}"],
                   capture_output=True, timeout=300)
    return png.exists()


# ---- thrust stand drawing ----------------------------------------------------------------------


def thrust_stand(folder: Path) -> Path | None:
    from drawings import Sheet  # same drawing framework as the boat sheets
    from hull_sizing import RHO_WATER, Boat, Hull, conditions, draft_for

    s = Sheet(1, "Prop thrust stand: pivot arm, load cell, test procedure", "1:5")
    k = 0.2
    X0, Y0 = 90.0, 100.0  # pivot

    def P(x, y):  # x right (aft, where the prop pushes the water), y up, mm
        return X0 + x * k, Y0 - y * k

    hull, boat = Hull(), Boat()
    drive = boat.drive
    dwl = draft_for(hull, conditions(hull, boat)[1].total / RHO_WATER / 2).draft
    c = drive.centre_distance(dwl) * 1000  # motor axis to prop axis
    tote_w, tote_h, water = 500.0, 400.0, 340.0
    arm_dn = arm_up = 380.0  # pivot to prop axis = pivot to load cell: F = T
    floor = -arm_dn - 170
    s.rect(*P(-tote_w / 2, floor), *P(tote_w / 2, floor + tote_h), "thin")
    s.line(*P(-tote_w / 2, floor + water), *P(tote_w / 2, floor + water), "wl")
    s.text(*P(tote_w / 2 - 5, floor + water + 6), "water line", 2.0, "end", cls="blue")
    s.rect(*P(-tote_w / 2 - 40, 10), *P(tote_w / 2 + 40, 30), "vis")  # frame rail
    s.text(*P(-tote_w / 2 - 30, 36), "2020 extrusion frame across the tote", 2.0, "start")
    s.circle(*P(0, 0), 8 * k, "vis")
    mz = -arm_dn + c  # motor axis
    s.rect(*P(-10, mz + 30), *P(10, arm_up), "vis")  # arm, down to the drive's bracket
    s.rect(*P(-30, mz + 30), *P(40, mz + 45), "vis")  # outdrive bracket, bolted to the arm
    s.rect(*P(-25, mz - 36), *P(55, mz + 30), "vis")  # motor cover
    s.circle(*P(40, mz), drive.motor_d * 500 * k, "hid")  # motor
    leg_c, leg_t = drive.leg_chord * 1000, drive.leg_t * 1000
    s.rect(*P(0, -arm_dn + 10), *P(leg_c, mz - 36), "vis")  # leg, seen from the side
    pd = drive.pulley_pd * 1000
    for y in (mz, -arm_dn):
        s.circle(*P(22, y), pd / 2 * k, "thin")  # pulleys
    s.line(*P(22 - pd / 2, mz), *P(22 - pd / 2, -arm_dn), "hid")  # belt runs
    s.line(*P(22 + pd / 2, mz), *P(22 + pd / 2, -arm_dn), "hid")
    pod_l = (drive.pod_x[0] - drive.pod_x[1]) * 1000
    s.rect(*P(0, -arm_dn - 16), *P(pod_l, -arm_dn + 16), "vis")  # lower pod
    xp = pod_l + 2 + drive.hub_len * 500
    s.rect(*P(pod_l + 2, -arm_dn - 10), *P(pod_l + 2 + drive.hub_len * 1000, -arm_dn + 10), "vis")  # prop hub
    s.line(*P(xp, -arm_dn - drive.prop_d * 500), *P(xp, -arm_dn + drive.prop_d * 500), "vis")  # prop disc
    s.rect(*P(20, arm_up - 20), *P(120, arm_up), "metal")  # load cell
    s.line(*P(10, arm_up - 10), *P(20, arm_up - 10), "vis")
    s.add(f'<line class="dim" x1="{P(xp + 20, -arm_dn)[0]:.2f}" y1="{P(0, -arm_dn)[1]:.2f}" x2="{P(xp + 70, -arm_dn)[0]:.2f}" '
          f'y2="{P(0, -arm_dn)[1]:.2f}" marker-end="url(#a)"/>')
    s.text(*P(xp + 75, -arm_dn + 2), "water pushed aft", 2.0, "start")
    s.dim_v(*P(-10, 0), *P(-10, -arm_dn), P(-tote_w / 2 - 60, 0)[0], arm_dn, f"{arm_dn:.0f} pivot to prop axis")
    s.dim_v(*P(-10, 0), *P(-10, arm_up - 10), P(-tote_w / 2 - 60, 0)[0], arm_up - 10, f"{arm_up - 10:.0f} pivot to load cell")
    s.dim_v(*P(leg_c, mz), *P(leg_c, -arm_dn), P(leg_c, 0)[0] + 18, c, f"{c:.0f} belt centres")
    s.dim_h(*P(-tote_w / 2, floor), *P(tote_w / 2, floor), P(0, floor)[1] + 7, tote_w,
            f"{tote_w:.0f} tote (>= 4 prop diameters)")
    s.leader(*P(0, 0), P(60, 0)[0], P(0, 60)[1], "pivot: 8 mm shaft in 2 flanged bearings")
    s.leader(*P(70, arm_up - 10), P(150, 0)[0], P(0, arm_up + 20)[1], "10 kg bar load cell + HX711")
    s.leader(*P(40, mz + 45), P(170, 0)[0], P(0, mz + 95)[1], "the boat's outdrive: bracket bolted to the arm")
    s.leader(*P(55, mz), P(170, 0)[0], P(0, mz + 45)[1], "motor dry above the water")
    s.text(*P(-15, (mz - arm_dn) / 2 - 20), f"leg {leg_c:.0f} x {leg_t:.0f}, belt inside", 2.0, "end")
    s.view_title(P(0, 0)[0], P(0, floor)[1] + 16, "SIDE VIEW", "1:5")
    s.lines_of_text(215, 25, [
        "HOW IT WORKS",
        "Thrust T at the prop axis turns the arm about the pivot; the arm's top presses the",
        f"load cell. With equal arms the load-cell force equals T (F = T x {arm_dn:.0f} / {arm_up - 10:.0f} here).",
        "",
        "PROCEDURE",
        "1. Calibrate: hang known weights from a string over a pulley at the prop axis.",
        "2. Power one outdrive from one M18 pack through a VESC; log current, voltage and rpm",
        "   with VESC Tool's real-time data, and thrust from the HX711 (Pico or Arduino).",
        "3. For each prop, step the rpm 1000 -> 4000 in 500 rpm steps, 10 s per step.",
        "4. Plot thrust vs electrical power. Compare props at the same thrust:",
        "   ~5 N (1 m/s cruise), ~10 N (1.5 m/s), ~25 N (3 m/s) per drive.",
        "5. Weed test: hang loose strands upstream at 1500 rpm for 2 min; count wraps.",
        "",
        "Keep the prop >= 1.5 D below the surface and >= 2 D from the walls and floor;",
        "a tote gives fair comparisons between props, not absolute numbers.",
        "A plain 110 mm RC boat prop = baseline. Record water temperature and belt tension.",
        "",
        "PARTS",
        "2020 extrusion (~1.5 m) + corner brackets; 8 mm shaft + 2x KFL08 bearings;",
        "10 kg bar load cell + HX711; 27-gal tote; one of the boat's outdrives, a VESC,",
        "one M18 pack, 20 A blade fuse and a kill switch.",
    ], size=2.3, lead=3.7, bold_first=False)
    s.table(215, 118, ["rpm", "V", "A", "W", "thrust N", "g/W", "notes"],
            [["1000", "", "", "", "", "", ""], ["1500", "", "", "", "", "", ""], ["2000", "", "", "", "", "", ""],
             ["...", "", "", "", "", "", ""], ["4000", "", "", "", "", "", ""]], [18, 14, 14, 14, 20, 16, 60], 2.2, 5.0)
    s.text(215, 115, "DATA SHEET (one per prop)", 2.6, "start", bold=True)
    s.src, s.rev = "mechanical/toroidal_prop.py", "B (belt outdrive)"
    html = ("<!DOCTYPE html><html><head><meta charset='utf-8'><style>@page{size:17in 11in;margin:0}body{margin:0}"
            ".page{width:17in;height:11in;overflow:hidden}.page svg{display:block}</style></head><body>"
            "<div class='page'>" + s.svg(1) + "</div></body></html>")
    out = folder / "thrust_stand.html"
    out.write_text(html, encoding="utf-8")
    exe = browser()
    if exe:
        pdf = folder / "thrust_stand.pdf"
        subprocess.run([exe, "--headless", "--disable-gpu", "--no-pdf-header-footer", f"--print-to-pdf={pdf}",
                        out.as_uri()], capture_output=True, timeout=120)
        return pdf if pdf.exists() else out
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    defaults = Prop()
    for f in fields(Prop):
        ap.add_argument("--" + f.name.replace("_", "-"), type=type(getattr(defaults, f.name)), default=None)
    ap.add_argument("--list", action="store_true", help="print every parameter and its default")
    ap.add_argument("--no-png", action="store_true")
    args = ap.parse_args()
    if args.list:
        for f in fields(Prop):
            print(f"--{f.name.replace('_', '-'):14s} {getattr(defaults, f.name)}")
        return
    over = {f.name: getattr(args, f.name) for f in fields(Prop) if getattr(args, f.name) is not None}
    p = Prop(**over)
    if "name" not in over:
        p.name = f"toroidal_{p.loops}loop_p{p.pitch:.0f}_{p.hand}_{p.hub}"
    folder = OUT / p.name
    folder.mkdir(parents=True, exist_ok=True)
    loops, sections = zip(*(loop_mesh(p, k) for k in range(p.loops)))
    for m in loops:
        m.outward()
    hub = [m.outward() for m in hub_meshes(p)]
    meshes = list(loops) + hub
    write_stl(meshes, folder / f"{p.name}.stl")
    if p.hub == "m200":
        write_stl([spinner_mesh(p).outward()], folder / f"{p.name}_spinner.stl")
    write_curves(p, folder, list(sections))
    write_viewer(meshes, p, folder / f"{p.name}_viewer.html")
    print(report(p, list(loops), hub, folder))
    print(f"wrote {folder}")
    if not args.no_png:
        for view in ("three", "axial"):
            png = folder / f"{p.name}_{view}.png"
            print(f"wrote {png}" if screenshot(folder / f"{p.name}_viewer.html", png, view) else "render skipped")
    print(f"wrote {thrust_stand(OUT)}")


if __name__ == "__main__":
    main()
