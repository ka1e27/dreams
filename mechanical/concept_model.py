"""3D concept model and renders of the D.R.E.A.M.S boat (rev E; files keep the V2 names).

Builds the boat as triangle meshes from the parameters in hull_sizing.py and writes:
    mechanical/render/DREAMS_V2_viewer.html   interactive 3D viewer, one self-contained file
    mechanical/render/DREAMS_V2_<view>.png    still renders (headless Edge/Chrome, WebGL)
    mechanical/render/DREAMS_V2_concept.obj   the concept mesh in mm (X fwd, Y up, Z stbd),
                                              for reference in CAD, not for manufacture
Run:
    python mechanical/concept_model.py            # viewer + OBJ + renders
    python mechanical/concept_model.py --no-png   # skip the browser renders
Each hull is drawn as a dark tub and an orange lid (the lid belongs to the upper module with
the bridge) meeting at the black rail. The belt outdrives carry the toroidal shaft-hub prop
from toroidal_prop.py (RH to starboard, LH to port).
The viewer embeds three.js r147 (MIT licence, mechanical/render/vendor/).
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
import subprocess
from pathlib import Path

import toroidal_prop as tp
from hull_sizing import (
    RHO_WATER,
    Boat,
    Hull,
    Outdrive,
    arm_path,
    arm_section,
    bezier,
    conditions,
    draft_for,
    section_points,
)

HERE = Path(__file__).resolve().parent
OUT = HERE / "render"
VENDOR = OUT / "vendor"


# ---- mesh primitives (boat coordinates, metres: x fwd, y stbd, z up) ------------------------


class Mesh:
    def __init__(self, name: str, mat: str):
        self.name, self.mat = name, mat
        self.v: list[tuple[float, float, float]] = []
        self.f: list[tuple[int, int, int]] = []

    def grid(self, rows: list[list[tuple[float, float, float]]], closed: bool = True) -> None:
        """Triangulate a structured grid of rows with equal point counts."""
        base = len(self.v)
        n = len(rows[0])
        for r in rows:
            self.v.extend(r)
        cols = n if closed else n - 1
        for i in range(len(rows) - 1):
            for j in range(cols):
                a = base + i * n + j
                b = base + i * n + (j + 1) % n
                c = base + (i + 1) * n + (j + 1) % n
                d = base + (i + 1) * n + j
                self.f += [(a, b, c), (a, c, d)]

    def fan(self, ring: list[tuple[float, float, float]]) -> None:
        cx = sum(p[0] for p in ring) / len(ring)
        cy = sum(p[1] for p in ring) / len(ring)
        cz = sum(p[2] for p in ring) / len(ring)
        base = len(self.v)
        self.v.append((cx, cy, cz))
        self.v.extend(ring)
        n = len(ring)
        for j in range(n):
            self.f.append((base, base + 1 + j, base + 1 + (j + 1) % n))


def superellipse(a: float, b: float, e: float, n: int = 40) -> list[tuple[float, float]]:
    pts = []
    for i in range(n):
        t = 2 * math.pi * i / n
        c, s = math.cos(t), math.sin(t)
        pts.append((a * math.copysign(abs(c) ** (2 / e), c), b * math.copysign(abs(s) ** (2 / e), s)))
    return pts


def rounded_block(name, mat, cx, cy, z0, z1, a, b, e=4.0, top_round=0.4, bottom_round=0.0,
                  top_scale=0.8, n=36) -> Mesh:
    """Superellipse plan (half-axes a along x, b along y) extruded z0..z1 with rounded edges."""
    m = Mesh(name, mat)
    plan = superellipse(a, b, e, n)
    h = z1 - z0
    levels = []
    k = 8
    for i in range(k + 1):  # bottom rounding
        t = i / k
        z = z0 + bottom_round * h * t
        s = 1.0 if bottom_round == 0 else top_scale + (1 - top_scale) * math.sin(t * math.pi / 2)
        levels.append((z, s))
    for i in range(1, k + 1):  # top rounding
        t = i / k
        z = z1 - top_round * h * (1 - t)
        s = top_scale + (1 - top_scale) * math.cos(t * math.pi / 2)
        levels.append((z, s))
    rows = [[(cx + px * s, cy + py * s, z) for px, py in plan] for z, s in levels]
    m.grid(rows)
    m.fan(list(reversed(rows[0])))
    m.fan(rows[-1])
    return m


def cylinder(name, mat, p0, p1, r, n=28, caps=True) -> Mesh:
    m = Mesh(name, mat)
    ax = [p1[i] - p0[i] for i in range(3)]
    ln = math.sqrt(sum(a * a for a in ax))
    ax = [a / ln for a in ax]
    ref = (0, 0, 1) if abs(ax[2]) < 0.9 else (1, 0, 0)
    u = [ax[1] * ref[2] - ax[2] * ref[1], ax[2] * ref[0] - ax[0] * ref[2], ax[0] * ref[1] - ax[1] * ref[0]]
    lu = math.sqrt(sum(a * a for a in u))
    u = [a / lu for a in u]
    w = [ax[1] * u[2] - ax[2] * u[1], ax[2] * u[0] - ax[0] * u[2], ax[0] * u[1] - ax[1] * u[0]]
    rows = []
    for p in (p0, p1):
        rows.append([tuple(p[i] + r * (math.cos(2 * math.pi * j / n) * u[i]
                                       + math.sin(2 * math.pi * j / n) * w[i]) for i in range(3))
                     for j in range(n)])
    m.grid(rows)
    if caps:
        m.fan(list(reversed(rows[0])))
        m.fan(rows[1])
    return m


def ellipsoid(name, mat, c, rx, ry, rz, n=32, k=16) -> Mesh:
    m = Mesh(name, mat)
    rows = []
    for i in range(1, k):
        th = math.pi * i / k
        rows.append([(c[0] + rx * math.sin(th) * math.cos(2 * math.pi * j / n),
                      c[1] + ry * math.sin(th) * math.sin(2 * math.pi * j / n),
                      c[2] + rz * math.cos(th)) for j in range(n)])
    m.grid(rows)
    m.fan(rows[0])
    m.fan(list(reversed(rows[-1])))
    return m


# ---- the boat --------------------------------------------------------------------------------


def stations(hull: Hull) -> list[float]:
    loa = hull.loa
    return sorted({round(i * 0.01, 4) for i in range(int(loa / 0.01) + 1)}
                  | {hull.stern_rise_end * loa, hull.taper_start * loa, hull.rocker_start * loa, loa})


def tub_mesh(hull: Hull, yc: float) -> Mesh:
    """Open tub from the lid joint plane round the keel and back; transom and stem capped."""
    m = Mesh("tub", "hull")
    rows = []
    for x in stations(hull):
        half = section_points(hull, x, part="tub")  # keel -> stbd side at the joint plane
        u = [(-y, z) for y, z in reversed(half[1:])] + half
        rows.append([(x, yc + y, z) for y, z in u])
    m.grid(rows, closed=False)
    m.fan(list(reversed(rows[0])))
    m.fan(rows[-1])
    return m


def lid_mesh(hull: Hull, yc: float) -> Mesh:
    """Removable lid from the joint plane up over the deck and down again; ends capped."""
    m = Mesh("lid", "lid")
    rows = []
    for x in stations(hull):
        half = section_points(hull, x, part="lid")  # stbd side at the joint plane -> deck CL
        u = half + [(-y, z) for y, z in reversed(half[:-1])]
        rows.append([(x, yc + y, z) for y, z in u])
    m.grid(rows, closed=False)
    m.fan(list(reversed(rows[0])))
    m.fan(rows[-1])
    return m


def rail_mesh(hull: Hull, yc: float, r: float = 0.003) -> Mesh:
    """The rail where the lid laps over the tub: both flanges and the drip lip, as one
    rounded bar swept round the hull's plan outline at the joint plane, rounded at the
    transom corners and round the stem."""
    lid = hull.lid
    w = lid.flange_w + lid.lip_t
    zb, zt = lid.z - lid.lip_drop, lid.z + lid.flange_t
    xs = stations(hull)
    # plan outline, starting mid-transom so the seam hides there
    pts = [(0.0, 0.0)] + [(x, hull.half_width(x, lid.z)) for x in xs]
    pts += [(x, -hull.half_width(x, lid.z)) for x in reversed(xs)]
    ring = [p for i, p in enumerate(pts) if math.dist(p, pts[i - 1]) > 1e-6]
    cx = sum(p[0] for p in ring) / len(ring)

    def normal(a, b):
        nx, ny = b[1] - a[1], -(b[0] - a[0])
        ln = math.hypot(nx, ny) or 1.0
        nx, ny = nx / ln, ny / ln
        mx, my = (a[0] + b[0]) / 2 - cx, (a[1] + b[1]) / 2
        return (nx, ny) if nx * mx + ny * my >= 0 else (-nx, -ny)

    samples = []  # (inner point, outward unit direction)
    n = len(ring)
    for i, p in enumerate(ring):
        a0 = math.atan2(*reversed(normal(ring[i - 1], p)))
        a1 = math.atan2(*reversed(normal(p, ring[(i + 1) % n])))
        da = (a1 - a0 + math.pi) % (2 * math.pi) - math.pi
        k = max(1, math.ceil(abs(da) / math.radians(15)))
        for j in range(k + 1 if k > 1 else 1):
            t = a0 + da * (j / k if k > 1 else 0.5)
            samples.append((p, (math.cos(t), math.sin(t))))
    prof = [(-0.001, zb), (w - r, zb)]
    prof += [(w - r + r * math.sin(math.pi / 2 * i / 3), zb + r - r * math.cos(math.pi / 2 * i / 3)) for i in range(1, 4)]
    prof += [(w - r + r * math.cos(math.pi / 2 * i / 3), zt - r + r * math.sin(math.pi / 2 * i / 3)) for i in range(3)]
    prof += [(w - r, zt), (-0.001, zt)]
    rows = [[(p[0] + d * c, yc + p[1] + d * s, z) for d, z in prof] for p, (c, s) in samples]
    m = Mesh("rail", "rail")
    m.grid(rows + rows[:1])
    return m


def arm_mesh(boat: Boat, hull: Hull, side: int) -> Mesh:
    """Gull-wing arm: rounded-rectangle section swept along the arch centreline."""
    m = Mesh("arm", "bridge")
    path = arm_path(boat, hull)
    xc = sum(boat.frame_x) / 2
    rows = []
    for i, (y, z) in enumerate(path):
        a = path[max(i - 1, 0)]
        b = path[min(i + 1, len(path) - 1)]
        ty, tz = b[0] - a[0], b[1] - a[1]
        ln = math.hypot(ty, tz)
        ny, nz = -tz / ln, ty / ln
        half_w, half_t, lift = arm_section(i / (len(path) - 1))
        sec = superellipse(half_w, half_t, 2.8, 36)
        rows.append([(xc + px, side * (y + (py + lift) * ny), z + (py + lift) * nz) for px, py in sec])
    m.grid(rows)
    m.fan(rows[0])
    m.fan(list(reversed(rows[-1])))
    return m


def hub_mesh(boat: Boat) -> Mesh:
    m = Mesh("hub", "bridge")
    ax, ay = boat.hub_half
    zb, zm, zt = boat.hub_z
    plan = superellipse(ax, ay, boat.hub_e, 72)
    zs = [zb + (zm - zb) * (1 - math.cos(math.pi / 2 * i / 12)) for i in range(13)]
    zs += [zm + (zt - zm) * math.sin(math.pi / 2 * i / 16) for i in range(1, 17)]
    rows = [[(boat.hub_x + px * max(boat.hub_scale(z), 0.02), py * max(boat.hub_scale(z), 0.02), z)
             for px, py in plan] for z in zs]
    m.grid(rows)
    m.fan(list(reversed(rows[0])))
    m.fan(rows[-1])
    return m


def hub_surface_z(boat: Boat, x: float, y: float) -> float:
    """Height of the cowl's dome at plan position (x, y)."""
    ax, ay = boat.hub_half
    zb, zm, zt = boat.hub_z
    e, p = boat.hub_e, boat.hub_dome
    s = ((abs(x - boat.hub_x) / ax) ** e + (abs(y) / ay) ** e) ** (1 / e)
    if s >= 1:
        return zm
    return zm + (zt - zm) * (1 - s**p) ** (1 / p)


def naca00(t: float, n: int = 20) -> list[tuple[float, float]]:
    """Closed symmetric NACA 4-digit section, chord 1 from the leading edge: round the upper
    surface from the trailing edge to the nose, then back along the lower surface."""
    xs = [(1 - math.cos(math.pi * i / n)) / 2 for i in range(n + 1)]
    yt = [5 * t * (0.2969 * math.sqrt(x) - 0.1260 * x - 0.3516 * x**2 + 0.2843 * x**3 - 0.1036 * x**4)
          for x in xs]
    return list(zip(reversed(xs), reversed(yt))) + [(x, -y) for x, y in zip(xs[1:-1], yt[1:-1])]


def revolve_x(name, mat, x0, yc, zc, profile, n=32) -> Mesh:
    """Body of revolution about a fore-aft axis: profile (u, r) with u measured aft of x0.
    The aft end is capped; start the profile at r = 0 for a closed nose."""
    m = Mesh(name, mat)
    rows = [[(x0 - u, yc + r * math.cos(2 * math.pi * j / n), zc + r * math.sin(2 * math.pi * j / n))
             for j in range(n)] for u, r in profile]
    m.grid(rows)
    m.fan(rows[-1])
    return m


def prop_meshes(d: Outdrive, yc: float, zp: float, hand: str) -> list[Mesh]:
    """The toroidal shaft-hub prop from toroidal_prop.py, on its washer and nylock nut. Its axis
    (+Z, mm, hub front face at Z = 0) points aft; x fwd / y stbd / z up is a left-handed frame,
    so x = -Z, y = X, z = Y keeps the prop's hand."""
    p = tp.Prop(hand=hand)
    x0, x1 = d.prop_x()
    parts = []
    for src in [tp.loop_mesh(p, k)[0] for k in range(p.loops)] + tp.hub_meshes(p):
        m = Mesh(f"prop {src.name}", "resin")
        m.v = [(x0 - vz / 1000, yc + vx / 1000, zp + vy / 1000) for vx, vy, vz in src.outward().v]
        m.f = list(src.f)
        parts.append(m)
    parts.append(cylinder("washer", "steel", (d.pod_x[1] + 0.0005, yc, zp), (x0, yc, zp), 0.006))
    parts.append(cylinder("nylock", "steel", (x1, yc, zp), (x1 - 0.005, yc, zp), 0.0046, n=6))
    return parts


def outdrive_meshes(boat: Boat, hull: Hull, yc: float, dwl: float, hand: str) -> list[Mesh]:
    """V1-style belt outdrive, fixed (rev D): the mount on the lid's aft deck and down its aft wall,
    the head block that clamps the leg, the platform and motor cover, the thrust pad on the transom,
    the streamlined leg (the belt runs inside), the lower pod and the prop."""
    d = boat.drive
    zp = d.prop_z(dwl)
    dk = hull.depth

    def block(name, mat, x0, x1, y0, y1, z0, z1, e=8.0, top_round=0.0, top_scale=1.0):
        return rounded_block(name, mat, (x0 + x1) / 2, yc + (y0 + y1) / 2, z0, z1, (x1 - x0) / 2, (y1 - y0) / 2,
                             e=e, top_round=top_round, top_scale=top_scale)

    bw, hw, bh = d.bracket[1] / 2, d.head_w / 2, d.body_w / 2
    wt, wz = d.wall_flange
    parts = [block("drive mount", "bracket", 0.0, d.bracket[0], -bw, bw, dk - 0.001, d.top_z),
             block("mount wall flange", "bracket", -wt, 0.0, -bw, bw, wz, d.top_z),
             block("mount head block", "bracket", d.head_x, -wt, -bh, bh, d.head_z, d.top_z),
             block("mount platform", "bracket", d.platform_x, -wt, -hw, hw, d.top_z - d.platform_t, d.top_z),
             block("motor cover", "black", d.cover[0], d.cover[1], -hw, hw, d.top_z, d.cover[2], e=4,
                   top_round=0.35, top_scale=0.82),
             block("thrust pad", "bracket", d.leg_le + d.pad[3], 0.0, -d.pad[2] / 2, d.pad[2] / 2, d.pad[0], d.pad[1])]
    leg = Mesh("leg", "bridge")
    sec = [(d.leg_le - u * d.leg_chord, yc + v * d.leg_chord) for u, v in naca00(d.leg_t / d.leg_chord)]
    rows = [[(x, y, z) for x, y in sec] for z in (zp, d.head_z + 0.002)]
    leg.grid(rows)
    leg.fan(list(reversed(rows[0])))
    leg.fan(rows[-1])
    parts.append(leg)
    # lower pod: elliptic nose, parallel body over the pulley and bearings, taper to the hub
    big, tail = d.pod_d / 2, 0.010
    length = d.pod_x[0] - d.pod_x[1]
    prof = [(big * (1 - math.cos(math.pi / 2 * i / 8)), big * math.sin(math.pi / 2 * i / 8)) for i in range(9)]
    prof += [(length - 0.035 + 0.035 * j / 8, tail + (big - tail) * (1 + math.cos(math.pi * j / 8)) / 2)
             for j in range(9)]
    parts.append(revolve_x("pod", "bridge", d.pod_x[0], yc, zp, prof))
    return parts + prop_meshes(d, yc, zp, hand)


def build(hull: Hull, boat: Boat) -> tuple[list[Mesh], dict]:
    dwl = draft_for(hull, conditions(hull, boat)[1].total / RHO_WATER / 2).draft
    yc = boat.spacing(hull) / 2
    fx0, fx1 = boat.frame_x
    xc = (fx0 + fx1) / 2
    parts: list[Mesh] = []
    for side in (-1, 1):
        y = side * yc
        parts += [tub_mesh(hull, y), lid_mesh(hull, y), rail_mesh(hull, y)]
        parts.append(arm_mesh(boat, hull, side))
        # foot shoe (fairing over the bolted foot plate) on its EPDM pad on the lid deck
        shoe_z0 = hull.depth + boat.pad_t
        parts.append(rounded_block("EPDM pad", "rail", xc, y, hull.depth - 0.003, shoe_z0,
                                   0.174, 0.075, e=5, top_round=0.0, top_scale=1.0))
        parts.append(rounded_block("foot shoe", "bridge", xc, y, shoe_z0, shoe_z0 + 0.055,
                                   0.172, 0.074, e=5, top_round=0.5, top_scale=0.75))
        parts += outdrive_meshes(boat, hull, y, dwl, "RH" if side > 0 else "LH")
    parts.append(hub_mesh(boat))
    hx = boat.hub_x
    front = hx + boat.hub_half[0]
    # stereo camera bar with two lenses, status lights, e-stop
    bar_x = front - 0.06
    bar_z = hub_surface_z(boat, bar_x, 0.0) + 0.010
    parts.append(rounded_block("stereo bar", "black", bar_x, 0.0, bar_z - 0.016, bar_z + 0.016,
                               0.016, 0.18, e=6, top_round=0.3))
    for ly in (-boat.camera_baseline / 2, boat.camera_baseline / 2):
        parts.append(cylinder("lens", "glass", (bar_x + 0.014, ly, bar_z), (bar_x + 0.022, ly, bar_z), 0.012))
    ctrl = boat.arm_ctrl(hull)
    ly, lz = min((bezier(ctrl, i / 100) for i in range(101)), key=lambda p: abs(p[0] - (boat.hub_half[1] + 0.06)))
    for side, mat in ((-1, "red"), (1, "green")):
        parts.append(rounded_block(f"light {mat}", mat, xc + 0.152, side * ly, lz - 0.007, lz + 0.007,
                                   0.004, 0.02, e=6))
    ez = hub_surface_z(boat, hx - 0.10, -0.07)
    parts.append(cylinder("e-stop", "red", (hx - 0.10, -0.07, ez - 0.005), (hx - 0.10, -0.07, ez + 0.018), 0.014))
    # GNSS mast and puck, LTE / WiFi whips
    zt = boat.hub_z[2]
    parts.append(cylinder("mast", "black", (hx, 0, zt - 0.01), (hx, 0, boat.mast_top - 0.04), 0.011))
    parts.append(ellipsoid("GNSS puck", "white", (hx, 0, boat.mast_top - 0.022), 0.075, 0.075, 0.024))
    for wy in (-0.12, 0.12):
        wz = hub_surface_z(boat, hx, wy)
        parts.append(cylinder("whip base", "black", (hx, wy, wz - 0.005), (hx, wy, wz + 0.03), 0.012))
        parts.append(cylinder("whip", "black", (hx, wy, wz + 0.03), (hx, wy, boat.mast_top), 0.007))
    # the pod and its Van Dorn sampler, pulled up into the hub garage under the sheave
    ox, _, _ = boat.garage_opening()
    s0, s1 = boat.stowed()
    pdx, pdy, pdz = boat.pod_env
    span = pdy + 0.010 + boat.sampler[0]
    parts.append(rounded_block("pod", "pod", ox, -span / 2 + pdy / 2, s1 - pdz, s1, pdx / 2, pdy / 2, e=4,
                               top_round=0.15, bottom_round=0.15, top_scale=0.8))
    sy, sz = span / 2 - boat.sampler[0] / 2, s1 - pdz / 2
    parts.append(cylinder("Van Dorn sampler", "pod", (ox - boat.sampler[1] / 2, sy, sz),
                          (ox + boat.sampler[1] / 2, sy, sz), boat.sampler[0] / 2))
    parts.append(cylinder("tether", "black", (ox, -0.015, s1), (ox, -0.015, boat.sheave[0]), 0.003, n=8))
    rail = hull.lid.flange_w + hull.lid.lip_t
    params = {
        "dwl": dwl, "loa": hull.loa, "loa_rails": hull.loa + 2 * rail, "yc": yc, "beam": hull.beam, "depth": hull.depth,
        "hub_x": hx, "mass": conditions(hull, boat)[1].total, "width": boat.overall_width + 2 * rail,
        "mast": boat.mast_top, "decal_z": (hull.lid.z - hull.lid.lip_drop + dwl) / 2,
        "floor": min(v[2] for p in parts for v in p.v) - 0.001,
    }
    return parts, params


# ---- output ----------------------------------------------------------------------------------


def write_obj(parts: list[Mesh], path: Path) -> None:
    lines = ["# D.R.E.A.M.S V2 concept mesh, mm, X fwd / Y up / Z stbd (reference only)"]
    off = 1
    for p in parts:
        lines.append(f"o {p.name.replace(' ', '_')}")
        lines += [f"v {x * 1000:.2f} {z * 1000:.2f} {y * 1000:.2f}" for x, y, z in p.v]
        lines += [f"f {a + off} {b + off} {c + off}" for a, b, c in p.f]
        off += len(p.v)
    path.write_text("\n".join(lines) + "\n", encoding="ascii")


def scene_json(parts: list[Mesh], params: dict) -> str:
    meshes = []
    for p in parts:
        pos = []
        for x, y, z in p.v:  # three.js: X fwd, Y up, Z stbd (right-handed)
            pos += [round(x, 4), round(z, 4), round(y, 4)]
        meshes.append({"name": p.name, "mat": p.mat, "pos": pos, "idx": [i for f in p.f for i in f]})
    return json.dumps({"meshes": meshes, "params": params}, separators=(",", ":"))


VIEWER_JS = r"""
const D = window.DREAMS;
const P = D.params;
const q = new URLSearchParams(location.hash.slice(1));
const STILL = q.has('still');
const W = STILL ? +q.get('w') : innerWidth, H = STILL ? +q.get('h') : innerHeight;
let mode = q.get('mode') || 'water';
THREE.ColorManagement.legacyMode = false;
const renderer = new THREE.WebGLRenderer({antialias: true, preserveDrawingBuffer: true});
renderer.setPixelRatio(STILL ? 1 : devicePixelRatio);
renderer.setSize(W, H);
renderer.outputEncoding = THREE.sRGBEncoding;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.0;
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
document.body.appendChild(renderer.domElement);
const scene = new THREE.Scene();

function gradientTex(top, mid, bottom) {
  const c = document.createElement('canvas'); c.width = 4; c.height = 512;
  const g = c.getContext('2d'), gr = g.createLinearGradient(0, 0, 0, 512);
  gr.addColorStop(0, top); gr.addColorStop(0.5, mid); gr.addColorStop(1, bottom);
  g.fillStyle = gr; g.fillRect(0, 0, 4, 512);
  const t = new THREE.CanvasTexture(c); t.encoding = THREE.sRGBEncoding; return t;
}
// environment for reflections: a sky dome with a bright sun patch
const pmrem = new THREE.PMREMGenerator(renderer);
const envScene = new THREE.Scene();
const sky = new THREE.Mesh(new THREE.SphereGeometry(50, 32, 16),
  new THREE.MeshBasicMaterial({map: gradientTex('#6f9fcf', '#dfeaf3', '#5d6f7a'), side: THREE.BackSide}));
envScene.add(sky);
const sunPatch = new THREE.Mesh(new THREE.SphereGeometry(4, 16, 8), new THREE.MeshBasicMaterial({color: 0xffffff}));
sunPatch.position.set(20, 30, 15); envScene.add(sunPatch);
scene.environment = pmrem.fromScene(envScene, 0.02).texture;

const MAT = {
  hull: new THREE.MeshPhysicalMaterial({color: 0x2b2f35, roughness: 0.42, metalness: 0.0, clearcoat: 0.7, clearcoatRoughness: 0.25}),
  bridge: new THREE.MeshPhysicalMaterial({color: 0xf07818, roughness: 0.32, metalness: 0.0, clearcoat: 1.0, clearcoatRoughness: 0.12}),
  lid: new THREE.MeshPhysicalMaterial({color: 0xf07818, roughness: 0.32, metalness: 0.0, clearcoat: 1.0, clearcoatRoughness: 0.12}),
  rail: new THREE.MeshStandardMaterial({color: 0x141517, roughness: 0.85}),
  bracket: new THREE.MeshStandardMaterial({color: 0x2a2d31, roughness: 0.55}),
  resin: new THREE.MeshPhysicalMaterial({color: 0xd8d2c4, roughness: 0.35, clearcoat: 0.5, clearcoatRoughness: 0.2}),
  black: new THREE.MeshStandardMaterial({color: 0x121314, roughness: 0.45}),
  glass: new THREE.MeshPhysicalMaterial({color: 0x05070a, roughness: 0.05, metalness: 0.2, clearcoat: 1.0}),
  steel: new THREE.MeshStandardMaterial({color: 0xd4d7db, roughness: 0.25, metalness: 0.95, flatShading: true}),
  white: new THREE.MeshStandardMaterial({color: 0xf4f4f2, roughness: 0.45}),
  red: new THREE.MeshStandardMaterial({color: 0xd01818, emissive: 0x6a0000, roughness: 0.4}),
  green: new THREE.MeshStandardMaterial({color: 0x19b33a, emissive: 0x004d12, roughness: 0.4}),
  pod: new THREE.MeshStandardMaterial({color: 0x30343a, roughness: 0.5}),
};
for (const k in MAT) { MAT[k].side = THREE.DoubleSide; MAT[k].envMapIntensity = 0.75; }
const WATER_ENV = 0.55;
const boat = new THREE.Group();
for (const m of D.meshes) {
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.Float32BufferAttribute(m.pos, 3));
  g.setIndex(m.idx); g.computeVertexNormals();
  const mesh = new THREE.Mesh(g, MAT[m.mat]);
  mesh.castShadow = true; mesh.receiveShadow = true; mesh.name = m.name;
  boat.add(mesh);
}
// name decals on the outboard hull sides
function decal(side) {
  const c = document.createElement('canvas'); c.width = 1024; c.height = 160;
  const g = c.getContext('2d');
  g.fillStyle = '#ffffff'; g.font = 'bold 118px Arial'; g.textBaseline = 'middle';
  g.fillText('D.R.E.A.M.S', 12, 84);
  const t = new THREE.CanvasTexture(c); t.encoding = THREE.sRGBEncoding; t.anisotropy = 8;
  const mat = new THREE.MeshStandardMaterial({map: t, transparent: true, roughness: 0.4, depthWrite: false,
    polygonOffset: true, polygonOffsetFactor: -2});
  const pl = new THREE.Mesh(new THREE.PlaneGeometry(0.40, 0.0625), mat);
  pl.position.set(0.32, P.decal_z, side * (P.yc + P.beam / 2 + 0.0012));
  pl.rotation.y = side > 0 ? 0 : Math.PI;
  boat.add(pl);
}
decal(1); decal(-1);
scene.add(boat);

// lights
const sun = new THREE.DirectionalLight(0xfff4e5, 2.1);
sun.position.set(2.6, 4.2, 2.2); sun.target.position.set(0.6, 0.2, 0);
sun.castShadow = true; sun.shadow.mapSize.set(2048, 2048);
const sc = sun.shadow.camera; sc.left = -1.6; sc.right = 1.6; sc.top = 1.6; sc.bottom = -1.6; sc.near = 0.5; sc.far = 12;
sun.shadow.bias = -0.0004; sun.shadow.normalBias = 0.01;
scene.add(sun, sun.target);
const hemi = new THREE.HemisphereLight(0xdbe8f5, 0x3c4650, 0.45); scene.add(hemi);
const fill = new THREE.DirectionalLight(0xdfe9ff, 0.45); fill.position.set(-3, 2, -2.5); scene.add(fill);

// water
function waterNormals() {
  const n = 256, c = document.createElement('canvas'); c.width = c.height = n;
  const g = c.getContext('2d'), img = g.createImageData(n, n), h = new Float32Array(n * n);
  const waves = [];
  for (let i = 0; i < 18; i++) waves.push([1 + Math.floor(Math.random() * 7), Math.floor(Math.random() * 7) - 3,
                                           Math.random() * 6.3, 0.6 / (1 + i * 0.35)]);
  for (let y = 0; y < n; y++) for (let x = 0; x < n; x++) {
    let v = 0;
    for (const [kx, ky, ph, a] of waves) v += a * Math.sin(2 * Math.PI * (kx * x + ky * y) / n + ph);
    h[y * n + x] = v;
  }
  for (let y = 0; y < n; y++) for (let x = 0; x < n; x++) {
    const dx = h[y * n + (x + 1) % n] - h[y * n + (x + n - 1) % n];
    const dy = h[((y + 1) % n) * n + x] - h[((y + n - 1) % n) * n + x];
    const l = Math.hypot(dx, dy, 2), i = 4 * (y * n + x);
    img.data[i] = 128 - 127 * dx / l; img.data[i + 1] = 128 - 127 * dy / l; img.data[i + 2] = 128 + 127 * 2 / l; img.data[i + 3] = 255;
  }
  g.putImageData(img, 0, 0);
  const t = new THREE.CanvasTexture(c); t.wrapS = t.wrapT = THREE.RepeatWrapping; t.repeat.set(30, 30); return t;
}
const water = new THREE.Mesh(new THREE.PlaneGeometry(80, 80), new THREE.MeshPhysicalMaterial({
  color: 0x173f52, roughness: 0.12, metalness: 0.0, transparent: true, opacity: 0.9,
  normalMap: waterNormals(), normalScale: new THREE.Vector2(0.28, 0.28), clearcoat: 1.0, clearcoatRoughness: 0.05}));
water.rotation.x = -Math.PI / 2; water.position.y = P.dwl; water.receiveShadow = true;
water.material.envMapIntensity = WATER_ENV;
scene.add(water);
const floor = new THREE.Mesh(new THREE.PlaneGeometry(40, 40), new THREE.ShadowMaterial({opacity: 0.22}));
floor.rotation.x = -Math.PI / 2; floor.position.y = P.floor; floor.receiveShadow = true;
scene.add(floor);

function setMode(m) {
  mode = m;
  const wet = m === 'water';
  water.visible = wet; floor.visible = !wet;
  scene.background = wet ? gradientTex('#5f8fbf', '#c9dbea', '#c9dbea') : new THREE.Color(0xf2eeeb);
  scene.fog = wet ? new THREE.Fog(0xb9cfe2, 10, 45) : null;
}

const DX = P.loa / 2 - 0.65;  // the boat views were framed on a 1300 mm hull; slide them to this one
const VIEWS = {
  hero:   {pos: [2.35 + DX, 0.78, 1.95], tgt: [0.52 + DX, 0.30, 0.0], fov: 30},
  stern:  {pos: [-1.85 + DX, 0.92, -1.55], tgt: [0.55 + DX, 0.30, 0.0], fov: 30},
  front:  {pos: [6.0 + DX, 0.44, 0.0], tgt: [0.55 + DX, 0.40, 0.0], fov: 11},
  side:   {pos: [0.62 + DX, 0.42, 6.6], tgt: [0.62 + DX, 0.40, 0.0], fov: 13},
  top:    {pos: [0.62 + DX, 7.0, 0.0], tgt: [0.62 + DX, 0.0, 0.0], fov: 13, up: [0, 0, -1]},
  studio: {pos: [2.3 + DX, 1.35, 2.05], tgt: [0.55 + DX, 0.32, 0.0], fov: 28},
  drive:  {pos: [-0.80, 0.26, 1.06], tgt: [-0.04, 0.14, 0.33], fov: 30},
};
const camera = new THREE.PerspectiveCamera(30, W / H, 0.05, 100);
let controls = null;
if (!STILL && THREE.OrbitControls) { controls = new THREE.OrbitControls(camera, renderer.domElement); controls.enableDamping = true; }
function setView(name) {
  const v = VIEWS[name]; camera.fov = v.fov; camera.up.set(...(v.up || [0, 1, 0]));
  camera.position.set(...v.pos); camera.updateProjectionMatrix();
  camera.lookAt(...v.tgt); if (controls) { controls.target.set(...v.tgt); controls.update(); }
}
setMode(mode); setView(q.get('view') || 'hero');
if (STILL) {
  renderer.render(scene, camera);
  document.title = 'ready';
} else {
  const ui = document.getElementById('ui');
  for (const v of Object.keys(VIEWS)) {
    const b = document.createElement('button'); b.textContent = v; b.onclick = () => setView(v); ui.appendChild(b);
  }
  const t = document.createElement('button'); t.textContent = 'water / studio';
  t.onclick = () => setMode(mode === 'water' ? 'studio' : 'water'); ui.appendChild(t);
  addEventListener('resize', () => { camera.aspect = innerWidth / innerHeight; camera.updateProjectionMatrix(); renderer.setSize(innerWidth, innerHeight); });
  (function loop() { requestAnimationFrame(loop); if (controls) controls.update(); renderer.render(scene, camera); })();
}
"""


def viewer_html(data: str, params: dict) -> str:
    three = (VENDOR / "three.min.js").read_text(encoding="utf-8")
    orbit = (VENDOR / "OrbitControls.js").read_text(encoding="utf-8")
    info = (f"D.R.E.A.M.S concept, rev E: {params['loa_rails'] * 1000:.0f} x {params['width'] * 1000:.0f} mm over the "
            f"rails, {params['mass']:.1f} kg design, draft {params['dwl'] * 1000:.0f} mm. Drag to orbit, scroll to zoom.")
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><title>D.R.E.A.M.S concept, rev E</title>
<style>body{{margin:0;overflow:hidden;font-family:Arial,sans-serif}}#ui{{position:absolute;top:10px;left:10px}}
#ui button{{margin:0 4px 4px 0;padding:6px 10px;border:0;border-radius:4px;background:#20262ecc;color:#fff;cursor:pointer}}
#info{{position:absolute;bottom:10px;left:10px;color:#20262e;font-size:13px;background:#ffffffb0;padding:4px 8px;border-radius:4px}}</style>
</head><body><div id="ui"></div><div id="info">{info}</div>
<script>/* three.js r147, MIT licence, (c) 2010-2022 three.js authors */
{three}</script>
<script>{orbit}</script>
<script>window.DREAMS = {data};</script>
<script>{VIEWER_JS}</script></body></html>"""


def browser() -> str | None:
    for cand in (r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                 r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
                 r"C:\Program Files\Google\Chrome\Application\chrome.exe"):
        if Path(cand).exists():
            return cand
    return shutil.which("msedge") or shutil.which("chrome") or shutil.which("chromium")


RENDERS = [("hero", "water"), ("stern", "water"), ("studio", "studio"), ("front", "studio"),
           ("side", "studio"), ("top", "studio"), ("drive", "studio")]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--no-png", action="store_true", help="skip the headless-browser renders")
    args = ap.parse_args()
    hull, boat = Hull(), Boat()
    parts, params = build(hull, boat)
    OUT.mkdir(exist_ok=True)
    write_obj(parts, OUT / "DREAMS_V2_concept.obj")
    viewer = OUT / "DREAMS_V2_viewer.html"
    viewer.write_text(viewer_html(scene_json(parts, params), params), encoding="utf-8")
    tris = sum(len(p.f) for p in parts)
    print(f"wrote {viewer} ({tris} triangles) and DREAMS_V2_concept.obj")
    exe = browser()
    if args.no_png or not exe:
        return
    for view, mode in RENDERS:
        png = OUT / f"DREAMS_V2_{view}.png"
        w, h = (1920, 1080)
        url = viewer.as_uri() + f"#still&view={view}&mode={mode}&w={w}&h={h}"
        subprocess.run([exe, "--headless=new", "--use-angle=swiftshader", "--enable-unsafe-swiftshader",
                        "--hide-scrollbars", f"--window-size={w},{h}", "--virtual-time-budget=20000",
                        f"--screenshot={png}", url], capture_output=True, timeout=300)
        print(f"wrote {png}" if png.exists() else f"render failed: {view}")


if __name__ == "__main__":
    main()
