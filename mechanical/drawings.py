"""Dimensioned drawing set and CAD files for the D.R.E.A.M.S boat (rev E).

Everything is generated from the parameters in hull_sizing.py, so re-run this after any
change there:
    python mechanical/drawings.py
Outputs:
    mechanical/drawings/DREAMS_V2_drawings.html  7 sheets, ANSI B (17 x 11 in), inline SVG
    mechanical/drawings/DREAMS_V2_drawings.pdf   the same, printed by headless Edge/Chrome
    mechanical/cad/*.txt                         XYZ point curves for SolidWorks
                                                 (Insert > Curve > Curve Through XYZ Points)
    mechanical/cad/arch_frame_plate.dxf          cut file for the two arch frames
Sheets: 1 general arrangement, 2 hull lines, 3 bridge + hub garage + rib bond and ring frame,
4 rail joint + hull interior, 5 belt outdrive assembly, 6 belt outdrive parts, 7 hull sections
one at a time.
Third-angle, dimensions in mm. Model origin: transom, baseline, boat centreline (hull sheets:
hull centreline; outdrive sheets: the drive's centreline, which is the hull's).
(The file names keep "V2" so links to them still work.)
"""

from __future__ import annotations

import math
import shutil
import subprocess
from html import escape
from pathlib import Path

from hull_sizing import (
    MARGIN,
    RHO_WATER,
    Boat,
    Hull,
    Loads,
    arch_centreline,
    arm_path,
    arm_section,
    arm_silhouette,
    conditions,
    draft_for,
    frame_outline,
    joint_checks,
    lid_joint_mass,
    lid_screws,
    load_cases,
    mass_budget,
    offset_polyline,
    print_heights,
    rail_length,
    section,
    section_points,
    shell_mass,
)

HERE = Path(__file__).resolve().parent
OUT = HERE / "drawings"
CAD = HERE / "cad"
W, H = 431.8, 279.4  # ANSI B landscape, mm
DATE = "2026-10-05"
REV = "E (940 hulls, one-piece prints)"

# drawing-only geometry, mm (not in the sizing model)
SHOE_H = 55.0  # foot shoe fairing height above the lid deck
LIGHTENING = ((-110.0, 25.0), (0.0, 25.0), (110.0, 25.0))  # frame holes (y, dia) in the hub span
GARAGE_HOLES_Y = (-120.0, 120.0)  # holes in each frame's hub span for the winch and sheave brackets
CLEAR = 0.3  # print clearance at the drip lip and the spigot
RING = (8.0, 2.0)  # tub ring frame: depth off the wall, thickness at its tip (aft face chamfered 45 deg)
LIMBER = (12.0, 6.0)  # notch in each ring frame at the keel, so a leak runs to the probe: width, height
# hull interior, proposed (mm from the hull centreline); the x positions and the masses are in hull_sizing
PACK_12S = (190.0, 70.0, 70.0)  # drive pack envelope x y z, port hull, between the frames
PACK_5S = (140.0, 45.0, 50.0)  # electronics and winch packs side by side, stbd hull, between the frames
VESC_BOX = (70.0, 45.0, 25.0)  # each VESC, by its outdrive
ELEC_BOX = (140.0, 110.0, 45.0)  # carrier board (131 x 102) with the Pi 5 stacked on it, stbd hull
HEAT_PLATE = (230.0, 100.0, 4.0)  # 6061 plate bedded on the hull bottom under the packs, each hull
# lid joint hardware
BOSS_D = 20.0  # foot-bolt boss in a lid rib, full depth: deck to joint plane
CBORE = (13.0, 8.0)  # counterbore up into the boss for the bolt head: dia, depth
HEAD = (10.0, 6.0)  # M6 socket cap: dia, height
WASHER = (11.5, 1.5)  # M6 bonded seal washer (steel ring + rubber lip)
BOLT_L = 60.0  # M6 x 60
INSERT = (5.6, 8.1)  # M4 brass heat-set insert: OD, length
INSERT_BOSS = (10.0, 10.0)  # boss under the tub flange: dia, depth below the joint plane
M4_HEAD = (8.0, 3.1)  # pan head: dia, height
M4_WASHER = (9.0, 0.8)
M4_HOLE = 4.5
# outdrive detail (the layout numbers are in hull_sizing.Outdrive)
PROP_HUB_D = 20.0  # toroidal_prop.py --hub shaft
PULLEY = (25.0, 13.0)  # 20T HTD 3M pulley over its flanges: dia, width
PULLEY_CAV = (28.0, 16.0)  # pocket for the lower pulley in the pod: dia, length
BEARING = (16.0, 5.0)  # 625-2RS: OD, width
COLLAR = (10.0, 5.0)  # 5 mm shaft collar in front of the fwd bearing: OD, width
NYLOCK = (8.0, 5.0)  # M5 nylock: across flats, height
BELT_T = 2.4  # HTD 3M belt, tooth tip to back
BELT_CAV = 12.0  # belt channel in the leg, along x
SOCKET_WALL = 3.0  # head socket wall round the leg
SECTION_Z = 160.0  # section A-A through the leg
MOTOR_SLOT = 4.0  # motor slides +/- this far up the plate to tension the belt
MOTOR_HOLES = ((12.5, 0.0), (-12.5, 0.0), (0.0, 9.5), (0.0, -9.5))  # 4x M3, 25 x 19 cross (check yours)
COVER_SCREWS = ((-58.0, -30.0), (-58.0, 30.0), (0.0, -30.0), (0.0, 30.0))  # M3 tabs into the mount top (x, y)
PLATE_SCREWS = ((8.0, -15.0), (8.0, 15.0))  # 2x M4: the motor plate's foot into the mount top (x, y)
SOCKET_BOLTS_X = (-83.0, -32.0)  # 2x M4 across the socket and the leg top, at z = mid-socket
LEG_SCREWS = ((-88.0, 0.2), (-88.0, 0.6), (-33.0, 0.4), (-33.0, 0.8))  # M3 joining the halves: x, height
#                                                                    as a fraction of the leg below the head block
POD_SCREWS = ((-78.0, -9.0), (-35.0, -9.0))  # M3 joining the pod halves: x, z from the prop axis

# body-plan station colours, stern (blue) to bow (purple); the stations are every LOA / 10, plus one
# near the stem (station_colours)
COLOURS = ("#1f4e9c", "#2a7fbf", "#138f96", "#2f9e5a", "#5c8f16", "#9a7b00", "#d06a0c", "#c8412a",
           "#b0243f", "#9c2a8a", "#6b3fa0", "#3b3b6b")

GAP, OVER = 1.0, 1.5  # extension-line gap and overshoot, paper mm

STYLE = """<style>
.vis{stroke:#000;stroke-width:0.35;fill:none}
.thin{stroke:#000;stroke-width:0.18;fill:none}
.hid{stroke:#000;stroke-width:0.18;fill:none;stroke-dasharray:1.6 0.9}
.ctr{stroke:#000;stroke-width:0.13;fill:none;stroke-dasharray:6 1.2 1 1.2}
.ph{stroke:#666;stroke-width:0.18;fill:none;stroke-dasharray:5 1 1 1 1 1}
.wl{stroke:#1a5fb4;stroke-width:0.25;fill:none;stroke-dasharray:4 1.5}
.wlt{stroke:#1a5fb4;stroke-width:0.15;fill:none;stroke-dasharray:1.5 1.5}
.lidj{stroke:#8a3ab9;stroke-width:0.3;fill:none;stroke-dasharray:6 1.5}
.dim{stroke:#000;stroke-width:0.15;fill:none}
.dimx{stroke:#000;stroke-width:0.12;fill:none}
.cut{stroke:#000;stroke-width:0.25;fill:#d9d9d9}
.cut2{stroke:#000;stroke-width:0.25;fill:#eeeeee}
.void{stroke:#000;stroke-width:0.2;fill:#ffffff}
.rubber{stroke:#000;stroke-width:0.2;fill:#4a4a4a}
.metal{stroke:#000;stroke-width:0.25;fill:#bfc9d4}
.plate{stroke:#000;stroke-width:0.35;fill:#e4e8ee}
.print{stroke:#000;stroke-width:0.35;fill:#f4efe4}
.see{stroke:#000;stroke-width:0.35;fill:#cdd6e0;fill-opacity:0.55}
.pack{stroke:#000;stroke-width:0.3;fill:#d8e8d0}
.elec{stroke:#000;stroke-width:0.3;fill:#f2dcc0}
.orange{stroke:#000;stroke-width:0.35;fill:#fbe0c8}
.glass{stroke:#1a5fb4;stroke-width:0.2;fill:#cfe2f3}
.frame{stroke:#000;stroke-width:0.5;fill:none}
.grid{stroke:#000;stroke-width:0.18;fill:none}
text{font-family:Arial,Helvetica,sans-serif;fill:#000}
.blue{fill:#1a5fb4}
.purple{fill:#8a3ab9}
</style>"""

DEFS = """<defs><marker id="a" viewBox="0 0 6 2" refX="6" refY="1" markerWidth="2.6" markerHeight="0.9"
 orient="auto-start-reverse" markerUnits="userSpaceOnUse"><path d="M0,0 L6,1 L0,2 z" fill="#000"/></marker></defs>"""


class Sheet:
    def __init__(self, number: int, title: str, scale: str):
        self.number, self.title, self.scale = number, title, scale
        self.parts: list[str] = []
        self.src, self.rev = "mechanical/drawings.py", REV

    def add(self, s: str) -> None:
        self.parts.append(s)

    def line(self, x1, y1, x2, y2, cls="vis"):
        self.add(f'<line class="{cls}" x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}"/>')

    def poly(self, pts, cls="vis", closed=False, style=""):
        tag = "polygon" if closed else "polyline"
        d = " ".join(f"{x:.2f},{y:.2f}" for x, y in pts)
        st = f' style="{style}"' if style else ""
        self.add(f'<{tag} class="{cls}"{st} points="{d}"/>')

    def rect(self, x1, y1, x2, y2, cls="vis"):
        x, y = min(x1, x2), min(y1, y2)
        self.add(f'<rect class="{cls}" x="{x:.2f}" y="{y:.2f}" width="{abs(x2 - x1):.2f}" '
                 f'height="{abs(y2 - y1):.2f}"/>')

    def circle(self, cx, cy, r, cls="vis"):
        self.add(f'<circle class="{cls}" cx="{cx:.2f}" cy="{cy:.2f}" r="{r:.2f}"/>')

    def text(self, x, y, s, size=2.5, anchor="middle", rot=0.0, bold=False, cls="", color=""):
        w = ' font-weight="bold"' if bold else ""
        c = f' class="{cls}"' if cls else ""
        st = f' style="fill:{color}"' if color else ""
        tr = f' transform="rotate({rot:.1f} {x:.2f} {y:.2f})"' if rot else ""
        self.add(f'<text x="{x:.2f}" y="{y:.2f}" font-size="{size}" text-anchor="{anchor}"'
                 f'{w}{c}{st}{tr}>{escape(s)}</text>')

    def lines_of_text(self, x, y, rows, size=2.4, lead=3.6, anchor="start", bold_first=False):
        for i, r in enumerate(rows):
            self.text(x, y + i * lead, r, size, anchor, bold=bold_first and i == 0)

    def dim_h(self, xa, ya, xb, yb, y, value, label=None):
        for x0, y0 in ((xa, ya), (xb, yb)):
            if abs(y - y0) > GAP:
                s = 1 if y > y0 else -1
                self.line(x0, y0 + s * GAP, x0, y + s * OVER, "dimx")
        lab = label if label is not None else f"{value:.0f}"
        if abs(xb - xa) >= 1.4 * len(lab) + 5:
            self.add(f'<line class="dim" x1="{xa:.2f}" y1="{y:.2f}" x2="{xb:.2f}" y2="{y:.2f}" '
                     'marker-start="url(#a)" marker-end="url(#a)"/>')
            self.text((xa + xb) / 2, y - 0.8, lab)
        else:
            lo, hi = min(xa, xb), max(xa, xb)
            self.line(lo - 4, y, hi + 4, y, "dim")
            self.add(f'<line class="dim" x1="{lo - 4:.2f}" y1="{y:.2f}" x2="{lo:.2f}" y2="{y:.2f}" marker-end="url(#a)"/>')
            self.add(f'<line class="dim" x1="{hi + 4:.2f}" y1="{y:.2f}" x2="{hi:.2f}" y2="{y:.2f}" marker-end="url(#a)"/>')
            self.text(hi + 5, y + 0.9, lab, anchor="start")

    def dim_v(self, xa, ya, xb, yb, x, value, label=None):
        for x0, y0 in ((xa, ya), (xb, yb)):
            if abs(x - x0) > GAP:
                s = 1 if x > x0 else -1
                self.line(x0 + s * GAP, y0, x + s * OVER, y0, "dimx")
        lab = label if label is not None else f"{value:.0f}"
        if abs(yb - ya) >= 1.4 * len(lab) + 5:
            self.add(f'<line class="dim" x1="{x:.2f}" y1="{ya:.2f}" x2="{x:.2f}" y2="{yb:.2f}" '
                     'marker-start="url(#a)" marker-end="url(#a)"/>')
            self.text(x - 0.8, (ya + yb) / 2, lab, rot=-90)
        else:
            lo, hi = min(ya, yb), max(ya, yb)
            self.line(x, lo - 4, x, hi + 4, "dim")
            self.add(f'<line class="dim" x1="{x:.2f}" y1="{lo - 4:.2f}" x2="{x:.2f}" y2="{lo:.2f}" marker-end="url(#a)"/>')
            self.add(f'<line class="dim" x1="{x:.2f}" y1="{hi + 4:.2f}" x2="{x:.2f}" y2="{hi:.2f}" marker-end="url(#a)"/>')
            self.text(x + 1.2, hi + 6.5, lab, anchor="start")

    def leader(self, x1, y1, x2, y2, label, anchor="start", size=2.3):
        self.add(f'<line class="dim" x1="{x2:.2f}" y1="{y2:.2f}" x2="{x1:.2f}" y2="{y1:.2f}" marker-end="url(#a)"/>')
        dx = 1.0 if anchor == "start" else -1.0
        self.text(x2 + dx, y2 + 0.8, label, size, anchor)

    def balloon(self, x1, y1, x2, y2, n, r=2.3):
        """Item callout: a numbered circle at (x2, y2) with a leader to the part at (x1, y1)."""
        dx, dy = x1 - x2, y1 - y2
        ln = math.hypot(dx, dy) or 1.0
        self.add(f'<line class="dim" x1="{x2 + dx / ln * r:.2f}" y1="{y2 + dy / ln * r:.2f}" x2="{x1:.2f}" '
                 f'y2="{y1:.2f}" marker-end="url(#a)"/>')
        self.circle(x2, y2, r, "thin")
        self.text(x2, y2 + 0.85, str(n), 2.3, bold=True)

    def view_title(self, x, y, name, scale):
        self.text(x, y, name, 3.1, bold=True)
        self.text(x, y + 3.7, f"SCALE {scale}", 2.2)

    def table(self, x, y, headers, rows, widths, size=2.2, row_h=4.0):
        total = sum(widths)
        n = len(rows) + 1
        self.rect(x, y, x + total, y + n * row_h, "grid")
        for i in range(1, n):
            self.line(x, y + i * row_h, x + total, y + i * row_h, "dimx")
        cx = x
        for w in widths[:-1]:
            cx += w
            self.line(cx, y, cx, y + n * row_h, "dimx")
        for r, cells in enumerate([headers] + rows):
            cx = x
            for w, c in zip(widths, cells):
                self.text(cx + 1.2, y + r * row_h + row_h * 0.72, c, size, "start", bold=r == 0)
                cx += w

    def svg(self, total: int) -> str:
        m = 10.0
        f = [f'<rect class="frame" x="{m}" y="{m}" width="{W - 2 * m}" height="{H - 2 * m}"/>']
        tx, ty, tw, th = W - m - 180, H - m - 36, 180, 36
        f.append(f'<rect class="frame" x="{tx}" y="{ty}" width="{tw}" height="{th}"/>')
        for yy in (ty + 12, ty + 20, ty + 28):
            f.append(f'<line class="grid" x1="{tx}" y1="{yy}" x2="{tx + tw}" y2="{yy}"/>')
        for xx in (tx + 60, tx + 120):
            f.append(f'<line class="grid" x1="{xx}" y1="{ty + 20}" x2="{xx}" y2="{ty + th}"/>')
        tb = Sheet(0, "", "")
        tb.text(tx + 2, ty + 5, "D.R.E.A.M.S — autonomous survey catamaran", 3.2, "start", bold=True)
        tb.text(tx + 2, ty + 10, self.title, 3.0, "start")
        tb.text(tx + 2, ty + 17, "All dimensions mm unless noted. Third-angle projection. Do not scale the print; "
                "build from the numbers.", 2.2, "start")
        tb.text(tx + 2, ty + 25.2, f"SCALE  {self.scale}", 2.4, "start")
        tb.text(tx + 62, ty + 25.2, f"SHEET  {self.number} OF {total}", 2.4, "start")
        tb.text(tx + 122, ty + 25.2, f"REV  {self.rev}", 2.4, "start")
        tb.text(tx + 2, ty + 33.2, f"DATE  {DATE}", 2.4, "start")
        tb.text(tx + 62, ty + 33.2, "DRAWN  Claude Code for M. Hong", 2.4, "start")
        tb.text(tx + 122, ty + 33.2, f"SRC  {self.src}", 2.4, "start")
        return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}mm" height="{H}mm" '
                f'viewBox="0 0 {W} {H}">{STYLE}{DEFS}{"".join(f)}{"".join(self.parts)}{"".join(tb.parts)}</svg>')


# ---- geometry (mm) -------------------------------------------------------------------------


def mm(v: float) -> float:
    return v * 1000.0


def stations(hull: Hull, step: float = 10.0) -> list[float]:
    xs = {round(i * step, 3) for i in range(int(mm(hull.loa) / step) + 1)}
    xs |= {mm(hull.stern_rise_end * hull.loa), mm(hull.taper_start * hull.loa),
           mm(hull.rocker_start * hull.loa), mm(hull.loa)}
    return sorted(xs)


def station_colours(hull: Hull) -> dict[float, str]:
    """Body-plan stations (mm fwd of the transom) and their colours: every LOA / 10, which lands on
    the keel-rise end, the taper start and the rocker start, plus one 40 mm short of the stem."""
    loa = mm(hull.loa)
    xs = [float(round(loa * i / 10)) for i in range(10)] + [10.0 * round((loa - 40) / 10), loa]
    return dict(zip(xs, COLOURS))



def keel(hull: Hull, x: float) -> float:
    return mm(hull.keel_z(x / 1000))


def hb(hull: Hull, x: float) -> float:
    return mm(hull.half_beam(x / 1000))


def chine(hull: Hull, x: float) -> float:
    """Sharp (unfilleted) chine height, as tabulated in the offsets."""
    return keel(hull, x) + mm(hull.chine_rise(x / 1000))


def side_tangent(hull: Hull, x: float) -> float:
    """Where the chine fillet meets the vertical side (the visible tangent edge)."""
    return mm(hull.fillet(x / 1000)[2])


def superellipse(a, b, e, n=72):
    pts = []
    for i in range(n):
        t = 2 * math.pi * i / n
        c, s = math.cos(t), math.sin(t)
        pts.append((a * math.copysign(abs(c) ** (2 / e), c), b * math.copysign(abs(s) ** (2 / e), s)))
    return pts


def ellipse(cx, cy, rx, ry, n=28):
    return [(cx + rx * math.cos(2 * math.pi * i / n), cy + ry * math.sin(2 * math.pi * i / n)) for i in range(n)]


def offset_closed(pts: list[tuple[float, float]], d: float) -> list[tuple[float, float]]:
    """Offset a closed polygon outward by d, with mitred corners."""
    n = len(pts)
    area = sum(pts[i][0] * pts[(i + 1) % n][1] - pts[(i + 1) % n][0] * pts[i][1] for i in range(n))
    sgn = 1.0 if area > 0 else -1.0
    out = []
    for i in range(n):
        p0, p1, p2 = pts[i - 1], pts[i], pts[(i + 1) % n]
        ns = []
        for a, b in ((p0, p1), (p1, p2)):
            ex, ey = b[0] - a[0], b[1] - a[1]
            ln = math.hypot(ex, ey) or 1.0
            ns.append((sgn * ey / ln, -sgn * ex / ln))
        nx, ny = ns[0][0] + ns[1][0], ns[0][1] + ns[1][1]
        ln = math.hypot(nx, ny) or 1.0
        nx, ny = nx / ln, ny / ln
        c = max(nx * ns[0][0] + ny * ns[0][1], 0.3)
        out.append((p1[0] + d * nx / c, p1[1] + d * ny / c))
    return out


def naca_half(t: float, c: float, n: int = 40) -> list[tuple[float, float]]:
    """Symmetric NACA 4-digit half-thickness (x from the LE, y), closed trailing edge."""
    pts = []
    for i in range(n + 1):
        u = (1 - math.cos(math.pi * i / n)) / 2
        yt = 5 * t * (0.2969 * math.sqrt(u) - 0.1260 * u - 0.3516 * u * u + 0.2843 * u**3 - 0.1036 * u**4)
        pts.append((u * c, yt * c))
    return pts


def tub_mass(hull: Hull) -> float:
    """The bare tub's share of the hull, design margin included: shell below the joint plane,
    its transom and ring frames, and the tub flange with its inserts."""
    lid, n = hull.lid, 400
    dx = hull.loa / n
    girth = sum(section(hull, (i + 0.5) * dx, lid.z)[3] for i in range(n)) * dx
    transom = section(hull, 0.0, lid.z)[0]
    shell = (girth * (hull.wall_t * hull.wall_rho + hull.skin_areal) + transom * hull.skin_areal
             + transom * hull.transom_t * hull.wall_rho) * (1 + hull.stiffener_frac)
    flange = (lid.flange_w * lid.flange_t - lid.groove[0] * lid.groove[1]) * rail_length(hull) * hull.wall_rho
    return (shell + flange + lid_screws(hull) * 0.0012) * (1 + MARGIN)


class Geo:
    """Numbers shared by all sheets, in mm."""

    def __init__(self) -> None:
        self.hull, self.boat = Hull(), Boat()
        h, b = self.hull, self.boat
        self.conds = conditions(h, b)
        self.drafts = [mm(draft_for(h, c.total / RHO_WATER / 2).draft) for c in self.conds]
        self.dwl = self.drafts[1]
        design = self.conds[1]
        hydro = draft_for(h, design.total / RHO_WATER / 2)
        self.lcs = load_cases(b, h, design, hydro, Loads())
        self.checks = joint_checks(b, h, self.lcs)
        self.items = mass_budget(h, b)
        self.loa, self.beam, self.depth = mm(h.loa), mm(h.beam), mm(h.depth)
        self.spacing = mm(b.spacing(h))
        self.yc = self.spacing / 2
        self.fx = [mm(v) for v in b.frame_x]
        self.xc = sum(self.fx) / 2
        self.stations = station_colours(h)
        self.aft_stations = [x for x in self.stations if x <= mm(h.stern_rise_end * h.loa) + 0.5]
        self.fwd_stations = [x for x in self.stations if x not in self.aft_stations]
        self.rib_x = [mm(v) for v in h.rib_x()]
        self.ribs = " / ".join(f"x {v:.0f}" for v in self.rib_x)
        self.rings = [mm(v) for v in h.ring_x]
        self.print_h = tuple(mm(v) for v in print_heights(h))  # tub, lid, printed on the stern
        # inside the hulls (hull_sizing.Boat): packs between the frames, VESC by the drive, and so on
        self.pack_x, self.vesc_x, self.elec_x = mm(b.pack_x), mm(b.vesc_x), mm(b.elec_x)
        self.leak_x, self.vent_x = mm(b.leak_x), mm(b.vent_x)
        self.conn_x = (mm(b.motor_conn_x), mm(b.bridge_conn_x))  # lid connectors: motor, bridge (in the shoe)
        self.frame = [(mm(y), mm(z)) for y, z in frame_outline(b, h)]
        self.frame_h, self.frame_t = mm(b.frame_h), mm(b.frame_t)
        self.frame_top = mm(b.arm_hub[1] + b.frame_h / 2)  # top of the frames across the hub
        up, lo = arm_silhouette(b, h)
        self.arm_up = [(mm(y), mm(z)) for y, z in up]
        self.arm_lo = [(mm(y), mm(z)) for y, z in lo]
        path = arm_path(b, h)
        self.arm_plan = [(mm(y), mm(arm_section(i / (len(path) - 1))[0])) for i, (y, _) in enumerate(path)]
        self.hub_x = mm(b.hub_x)
        self.hub_ax, self.hub_ay = (mm(v) for v in b.hub_half)
        self.hub_z = [mm(v) for v in b.hub_z]
        self.mast_top = mm(b.mast_top)
        self.cam_base = mm(b.camera_baseline)
        self.foot_z = mm(b.foot_z)
        self.foot_len, self.foot_w, self.foot_t = mm(b.foot_len), mm(b.foot_w), mm(b.foot_t)
        self.pad_t = mm(b.pad_t)
        self.foot_holes_z = (self.foot_z + 15.0, self.foot_z + 35.0)  # angle-bracket holes in the frame
        self.shoe_len, self.shoe_w = self.foot_len + 44, self.foot_w + 12
        self.bolt_dx = mm(b.foot_bolt_dx)
        self.bolt_y = [mm(v) for v in b.foot_bolt_y]
        self.whip_y = 120.0
        # hub garage: the opening in the hub floor, the sheave, the winch, the stowed pod + Van Dorn
        ox, oln, ow = b.garage_opening()
        self.open_x, self.open_len, self.open_w = mm(ox), mm(oln), mm(ow)
        self.sheave_z, self.sheave_d = (mm(v) for v in b.sheave)
        self.stow_z = tuple(mm(v) for v in b.stowed())
        self.winch = tuple(mm(v) for v in b.winch_env)  # x0, x1, half-width, z0, z1
        self.pod_env = [mm(v) for v in b.pod_env]
        self.sampler_d, self.sampler_len = (mm(v) for v in b.sampler)
        span = self.pod_env[1] + 10.0 + self.sampler_d  # side by side across the opening, 10 apart
        self.pod_y = (-span / 2, -span / 2 + self.pod_env[1])  # pod to port
        self.sampler_y = (span / 2 - self.sampler_d, span / 2)  # sampler to starboard
        self.pod_z = (self.stow_z[1] - self.pod_env[2], self.stow_z[1])
        zc = (self.pod_z[0] + self.pod_z[1]) / 2
        self.sampler_z = (zc - self.sampler_d / 2, zc + self.sampler_d / 2)
        self.stow_fit = [mm(v) for v in b.stow_fit()]
        # lid and rail
        lid = h.lid
        self.lid = lid
        self.zj = mm(lid.z)
        self.fw, self.ft = mm(lid.flange_w), mm(lid.flange_t)
        self.lip_t, self.lip_drop = mm(lid.lip_t), mm(lid.lip_drop)
        self.rail = self.fw + self.lip_t
        self.loa_rails = self.loa + 2 * self.rail  # the rail laps past the transom and the stem
        self.rail_z = (self.zj - self.lip_drop, self.zj + self.ft)
        self.wall = mm(h.wall_t)
        self.n_screws = lid_screws(h, b.frame_x)
        self.rail_len = rail_length(h)
        self.rib_depth = self.depth - self.zj
        self.boss_z = (self.zj, self.depth - self.wall)  # full depth, so the rib is never notched
        self.tub_kg = tub_mass(h)
        self.landing = mm(b.foot_landing(h))  # flat landing in the lid deck under each foot, deepest fill
        # belt outdrive: the layout is hull_sizing.Outdrive (rev D, fixed)
        d = b.drive
        self.drive = d
        dwl_m = self.dwl / 1000
        self.prop_d = mm(d.prop_d)
        self.prop_z = mm(d.prop_z(dwl_m))
        self.prop_bottom = self.prop_z - self.prop_d / 2
        self.total_draft = self.dwl - self.prop_bottom
        self.prop_xf, self.prop_xa = (mm(v) for v in d.prop_x())
        self.nut_x = (self.prop_xa - NYLOCK[1], self.prop_xa)
        self.pod_d = mm(d.pod_d)
        self.pod_x = (mm(d.pod_x[1]), mm(d.pod_x[0]))  # tail, nose
        self.bearings = ((self.pod_x[1] - 15, self.pod_x[1] - 10), (self.pod_x[0], self.pod_x[0] + BEARING[1]))
        self.collar = (self.bearings[0][1], self.bearings[0][1] + COLLAR[1])
        self.shaft_x = (self.nut_x[0] - 4.0, self.collar[1] + 1.0)  # aft end, fwd end
        self.aft_end = self.shaft_x[0]
        self.loa_all = self.loa - self.aft_end
        self.belt_x, self.belt_w = mm(d.belt_x), mm(d.belt_w)
        self.motor_z, self.motor_d = mm(d.motor_z), mm(d.motor_d)
        self.motor_x = tuple(mm(v) for v in d.motor_x)
        self.plate_x = tuple(mm(v) for v in d.plate_x)
        self.plate_top, self.plate_w = mm(d.plate_top), mm(d.plate_w)
        self.top_z = mm(d.top_z)
        self.cover_x = (mm(d.cover[0]), mm(d.cover[1]))
        self.cover_top = mm(d.cover[2])
        self.head_w, self.body_w = mm(d.head_w), mm(d.body_w)
        self.head_x, self.head_z = mm(d.head_x), mm(d.head_z)
        self.platform_x, self.platform_t = mm(d.platform_x), mm(d.platform_t)
        self.wall_t, self.wall_z = (mm(v) for v in d.wall_flange)
        self.wall_bolt_z, self.wall_bolt_y = (mm(v) for v in d.wall_bolts)
        self.socket_z = tuple(mm(v) for v in d.socket_z)
        self.mount_poly = [(mm(x), mm(z)) for x, z in d.mount_outline(h.depth)]
        self.pad = tuple(mm(v) for v in d.pad)  # z0, z1, width, EPDM face
        self.bracket_x, self.bracket_w = (mm(v) for v in d.bracket)
        self.bracket_t = mm(d.bracket_t)
        (bx1, bx2), byy = d.bracket_bolts
        self.bracket_bolts = ((mm(bx1), mm(bx2)), mm(byy))
        self.leg_x = (mm(d.leg_le) - mm(d.leg_chord), mm(d.leg_le))
        self.leg_t = mm(d.leg_t)
        self.leg_z = (self.prop_z + self.pod_d / 2, self.socket_z[1])
        self.centres = mm(d.centre_distance(dwl_m))
        self.teeth = d.belt_teeth(dwl_m)
        self.pd = mm(d.pulley_pd)
        self.shaft_d = mm(d.shaft_d)
        self.gaps = {k: mm(v) for k, v in d.clearances(h).items()}
        self.thrust = d.thrust_loads(dwl_m)  # pad N, mount N, leg moment at the pad N m, moment with no pad N m

    def hub_scale(self, z: float) -> float:
        return self.boat.hub_scale(z / 1000)

    def hub_side(self, n: int = 40) -> list[tuple[float, float]]:
        """(half-extent scale, z) samples up the cowl, bottom to top."""
        z0, z1 = self.hub_z[0], self.hub_z[2]
        return [(self.hub_scale(z0 + (z1 - z0) * i / n), z0 + (z1 - z0) * i / n) for i in range(n + 1)]

    def dome_z(self, x: float, y: float) -> float:
        b = self.boat
        e, p = b.hub_e, b.hub_dome
        s = ((abs(x - self.hub_x) / self.hub_ax) ** e + (abs(y) / self.hub_ay) ** e) ** (1 / e)
        zm, zt = self.hub_z[1], self.hub_z[2]
        return zm if s >= 1 else zm + (zt - zm) * (1 - s**p) ** (1 / p)

    def cowl_half_width(self, x: float, z: float) -> float:
        return mm(self.boat.cowl_half_width(x / 1000, z / 1000))

    def plan_outline(self, step: float = 20.0) -> list[tuple[float, float]]:
        """Closed plan outline of one hull at the side (x, y from its centreline)."""
        xs = stations(self.hull, step)
        return [(x, -hb(self.hull, x)) for x in xs] + [(x, hb(self.hull, x)) for x in reversed(xs)]

    def rail_outline(self, step: float = 20.0) -> list[tuple[float, float]]:
        return offset_closed(self.plan_outline(step), self.rail)

    def pod_outline(self) -> list[tuple[float, float]]:
        """Lower pod seen from the side, drive (x, z): round nose, parallel body, tapered tail."""
        r, z = self.pod_d / 2, self.prop_z
        tail, nose = self.pod_x
        cx = nose - r
        pts = [(cx + r * math.cos(math.radians(a)), z + r * math.sin(math.radians(a))) for a in range(90, -91, -15)]
        return pts + [(tail + 20, z - r), (tail, z - PROP_HUB_D / 2 - 1), (tail, z + PROP_HUB_D / 2 + 1),
                      (tail + 20, z + r)]



# ---- outdrive views (the GA, sheet 4 and the outdrive sheets) ------------------------------


def rounded_top(x0: float, x1: float, z0: float, z1: float, r: float, n: int = 6) -> list[tuple[float, float]]:
    """Rectangle (x, z) with its two top corners rounded."""
    pts = [(x0, z0), (x1, z0)]
    pts += [(x1 - r + r * math.cos(math.radians(90 * i / n)), z1 - r + r * math.sin(math.radians(90 * i / n)))
            for i in range(n + 1)]
    pts += [(x0 + r - r * math.cos(math.radians(90 * (n - i) / n)), z1 - r + r * math.sin(math.radians(90 * (n - i) / n)))
            for i in range(n + 1)]
    return pts


def motor_plate_outline(g: Geo) -> list[tuple[float, float]]:
    """The L-shaped motor plate from the side: upright in front of the motor, foot forward on the mount."""
    a, f = g.plate_x
    z0 = g.top_z
    return [(a, z0), (a, g.plate_top), (f, g.plate_top), (f, z0 + 4), (f + 16, z0 + 4), (f + 16, z0)]


def pad_outline(g: Geo) -> list[tuple[float, float]]:
    """The thrust pad from the side: bonded to the transom, its EPDM face on the leg's nose."""
    z0, z1, _, t = g.pad
    return [(0.0, z0), (g.leg_x[1] + t, z0), (g.leg_x[1] + t, z1), (0.0, z1)]


def drive_side(s: Sheet, g: Geo, Q, k: float, detail: bool = False) -> None:
    """Belt outdrive seen from starboard. Q maps drive (x, z) mm to paper, k is the scale.
    detail=False draws outlines only (the GA); True adds what's inside, hidden-lined."""
    cls = "print" if detail else "vis"

    def box(x0, x1, z0, z1, c=cls):
        s.rect(*Q(x0, z0), *Q(x1, z1), c)

    s.poly([Q(x, z) for x, z in g.mount_poly], cls, closed=True)
    s.poly([Q(x, z) for x, z in pad_outline(g)], cls, closed=True)
    box(g.leg_x[0], g.leg_x[1], g.leg_z[0], g.head_z)
    s.poly([Q(x, z) for x, z in g.pod_outline()], cls, closed=True)
    s.poly([Q(x, z) for x, z in rounded_top(g.cover_x[0], g.cover_x[1], g.top_z, g.cover_top, 8.0)], cls,
           closed=True)
    box(g.prop_xa, g.prop_xf, g.prop_z - PROP_HUB_D / 2, g.prop_z + PROP_HUB_D / 2, "vis")
    box(g.prop_xa, g.prop_xf, g.prop_bottom, g.prop_bottom + g.prop_d, "thin")
    box(g.nut_x[0], g.nut_x[1], g.prop_z - NYLOCK[0] / 2, g.prop_z + NYLOCK[0] / 2, "vis")
    box(g.shaft_x[0], g.nut_x[0], g.prop_z - g.shaft_d / 2, g.prop_z + g.shaft_d / 2, "vis")
    if not detail:
        return
    z0, z1, _, t = g.pad
    box(g.leg_x[1], g.leg_x[1] + t, z0, z1, "rubber")  # EPDM face of the pad
    s.line(*Q(g.platform_x, g.top_z - g.platform_t), *Q(-g.wall_t, g.top_z - g.platform_t), "hid")
    s.poly([Q(x, z) for x, z in motor_plate_outline(g)], "hid", closed=True)
    box(g.motor_x[0], g.motor_x[1], g.motor_z - g.motor_d / 2, g.motor_z + g.motor_d / 2, "hid")
    for z in (g.motor_z, g.prop_z):  # pulleys
        box(g.belt_x - PULLEY[1] / 2, g.belt_x + PULLEY[1] / 2, z - PULLEY[0] / 2, z + PULLEY[0] / 2, "hid")
    for dx in (-g.belt_w / 2, g.belt_w / 2):  # belt
        s.line(*Q(g.belt_x + dx, g.prop_z + PULLEY[0] / 2), *Q(g.belt_x + dx, g.motor_z - PULLEY[0] / 2), "hid")
    for dx in (-BELT_CAV / 2, BELT_CAV / 2):  # belt channel up the leg and through the head block
        s.line(*Q(g.belt_x + dx, g.prop_z + PULLEY_CAV[0] / 2), *Q(g.belt_x + dx, g.top_z), "ph")
    box(g.belt_x - PULLEY_CAV[1] / 2, g.belt_x + PULLEY_CAV[1] / 2, g.prop_z - PULLEY_CAV[0] / 2,
        g.prop_z + PULLEY_CAV[0] / 2, "ph")
    box(g.leg_x[0], g.leg_x[1], g.socket_z[0], g.socket_z[1], "hid")  # leg top in its socket
    for a, b in g.bearings:
        box(a, b, g.prop_z - BEARING[0] / 2, g.prop_z + BEARING[0] / 2, "hid")
    box(*g.collar, g.prop_z - COLLAR[0] / 2, g.prop_z + COLLAR[0] / 2, "hid")
    box(g.prop_xf, g.shaft_x[1], g.prop_z - g.shaft_d / 2, g.prop_z + g.shaft_d / 2, "hid")
    # fasteners: deck bolts up from inside the lid, bolts through the lid's aft wall, socket bolts, screws
    (bx1, bx2), _ = g.bracket_bolts
    for bx in (bx1, bx2):
        s.line(*Q(bx, g.depth - g.wall - 6), *Q(bx, g.depth + g.bracket_t - 2), "hid")
        s.rect(*Q(bx - 4, g.depth - g.wall - 6), *Q(bx + 4, g.depth - g.wall), "hid")
    s.line(*Q(g.wall + 8, g.wall_bolt_z), *Q(-g.wall_t + 1, g.wall_bolt_z), "hid")
    s.rect(*Q(g.wall, g.wall_bolt_z - 4), *Q(g.wall + 6, g.wall_bolt_z + 4), "hid")
    zs = (g.socket_z[0] + g.socket_z[1]) / 2
    for x in SOCKET_BOLTS_X:
        s.circle(*Q(x, zs), 2.0 * k, "vis")
    hl = g.head_z - g.leg_z[0]
    for x, f in LEG_SCREWS:
        s.circle(*Q(x, g.leg_z[0] + f * hl), 1.6 * k, "vis")
    for x, dz in POD_SCREWS:
        s.circle(*Q(x, g.prop_z + dz), 1.6 * k, "vis")


def drive_top(s: Sheet, g: Geo, P, yc: float, detail: bool = False) -> None:
    """Belt outdrive from above; P maps (x, y) mm to paper, yc is the drive's centreline."""
    cls = "print" if detail else "vis"

    def box(x0, x1, y0, y1, c=cls):
        s.rect(*P(x0, yc + y0), *P(x1, yc + y1), c)

    bw = g.bracket_w / 2
    box(g.prop_xa, g.prop_xf, -g.prop_d / 2, g.prop_d / 2, "thin")
    box(g.prop_xa, g.prop_xf, -PROP_HUB_D / 2, PROP_HUB_D / 2, "vis")
    box(g.shaft_x[0], g.prop_xa, -NYLOCK[0] / 2, NYLOCK[0] / 2, "vis")
    box(g.pod_x[0], g.pod_x[1], -g.pod_d / 2, g.pod_d / 2, "hid")
    box(g.head_x, -g.wall_t, -g.body_w / 2, g.body_w / 2)
    box(g.platform_x, -g.wall_t, -g.head_w / 2, g.head_w / 2)
    box(-g.wall_t, g.bracket_x, -bw, bw)
    box(g.cover_x[0], g.cover_x[1], -g.head_w / 2, g.head_w / 2)
    if detail:
        box(g.leg_x[0], g.leg_x[1], -g.leg_t / 2, g.leg_t / 2, "hid")
        box(g.leg_x[1], 0, -g.pad[2] / 2, g.pad[2] / 2, "hid")
        kk = abs(P(1, 0)[0] - P(0, 0)[0])
        (bx1, bx2), byy = g.bracket_bolts
        for bx in (bx1, bx2):
            for sgn in (-1, 1):
                s.circle(*P(bx, yc + sgn * byy), 2.75 * kk, "hid")
        for sgn in (-1, 1):
            s.line(*P(g.wall + 8, yc + sgn * g.wall_bolt_y), *P(-g.wall_t + 1, yc + sgn * g.wall_bolt_y), "hid")


def drive_aft(s: Sheet, g: Geo, R, k: float, yc: float, detail: bool = False) -> None:
    """Belt outdrive from astern, looking forward; R maps (y, z) mm to paper (stbd to the right)."""
    cls = "print" if detail else "vis"

    def box(y0, y1, z0, z1, c=cls):
        s.rect(*R(yc + y0, z0), *R(yc + y1, z1), c)

    bw = g.bracket_w / 2
    box(-bw, bw, g.wall_z, g.top_z)  # the flange down the lid's aft wall, behind everything else
    box(-g.body_w / 2, g.body_w / 2, g.head_z, g.top_z)
    box(-g.head_w / 2, g.head_w / 2, g.top_z - g.platform_t, g.top_z)
    s.poly([R(yc + y, z) for y, z in rounded_top(-g.head_w / 2, g.head_w / 2, g.top_z, g.cover_top, 8.0)],
           cls, closed=True)
    box(-g.leg_t / 2, g.leg_t / 2, g.leg_z[0], g.head_z)
    s.circle(*R(yc, g.prop_z), g.pod_d / 2 * k, cls)
    s.circle(*R(yc, g.prop_z), g.prop_d / 2 * k, "thin")
    s.circle(*R(yc, g.prop_z), PROP_HUB_D / 2 * k, "vis")
    s.circle(*R(yc, g.prop_z), NYLOCK[0] / 2 * k, "vis")
    if detail:
        box(-g.pad[2] / 2, g.pad[2] / 2, g.pad[0], g.pad[1], "hid")
        for sgn in (-1, 1):
            s.line(*R(yc + sgn * g.pd / 2, g.prop_z + PULLEY[0] / 2), *R(yc + sgn * g.pd / 2, g.motor_z - PULLEY[0] / 2),
                   "hid")
            s.circle(*R(yc + sgn * g.wall_bolt_y, g.wall_bolt_z), 2.75 * k, "hid")
        s.circle(*R(yc, g.motor_z), g.motor_d / 2 * k, "hid")


# ---- hub garage and hull interior (the GA and sheets 3 and 4) -------------------------------


def module_masses(g: Geo) -> tuple[float, float]:
    """Design mass (with margin) of the port and starboard tubs with what's fitted in them."""
    f = 1 + MARGIN
    port = stbd = g.tub_kg
    for i in g.items:
        if i.name.startswith("Drive pack"):
            port += i.kg * f
        elif i.name.startswith(("Electronics pack", "Winch pack", "Pi 5")):
            stbd += i.kg * f
        elif i.name.startswith(("VESC", "Aluminium heat plates", "Fuses", "Leak probes")):
            port += i.kg * f / 2
            stbd += i.kg * f / 2
    return port, stbd


def garage_plan(s: Sheet, g: Geo, P) -> None:
    """The hub garage from above, all hidden under the cowl: opening, winch, sheave, pod, sampler."""
    s.rect(*P(g.open_x - g.open_len / 2, -g.open_w / 2), *P(g.open_x + g.open_len / 2, g.open_w / 2), "hid")
    s.rect(*P(g.open_x - g.pod_env[0] / 2, g.pod_y[0]), *P(g.open_x + g.pod_env[0] / 2, g.pod_y[1]), "hid")
    s.rect(*P(g.open_x - g.sampler_len / 2, g.sampler_y[0]), *P(g.open_x + g.sampler_len / 2, g.sampler_y[1]), "hid")
    s.rect(*P(g.winch[0], -g.winch[2]), *P(g.winch[1], g.winch[2]), "hid")
    s.rect(*P(g.open_x - g.sheave_d / 2, -4), *P(g.open_x + g.sheave_d / 2, 4), "hid")
    s.line(*P(g.winch[1], 0), *P(g.open_x - g.sheave_d / 2, 0), "hid")


def garage_side(s: Sheet, g: Geo, Q) -> None:
    """The hub garage from starboard, hidden inside the cowl."""
    s.rect(*Q(g.open_x - g.pod_env[0] / 2, g.pod_z[0]), *Q(g.open_x + g.pod_env[0] / 2, g.pod_z[1]), "hid")
    s.rect(*Q(g.open_x - g.sampler_len / 2, g.sampler_z[0]), *Q(g.open_x + g.sampler_len / 2, g.sampler_z[1]), "hid")
    s.rect(*Q(g.winch[0], g.winch[3]), *Q(g.winch[1], g.winch[4]), "hid")
    k = abs(Q(1, 0)[0] - Q(0, 0)[0])
    s.circle(*Q(g.open_x, g.sheave_z), g.sheave_d / 2 * k, "hid")
    s.line(*Q((g.winch[0] + g.winch[1]) / 2, g.winch[4]), *Q(g.open_x, g.sheave_z + g.sheave_d / 2), "hid")
    s.line(*Q(g.open_x, g.sheave_z - g.sheave_d / 2), *Q(g.open_x, g.pod_z[1]), "hid")
    for x in (g.open_x - g.open_len / 2, g.open_x + g.open_len / 2):  # edges of the floor opening
        s.line(*Q(x, g.hub_z[0] - 8), *Q(x, g.hub_z[0] + 8), "vis")


def garage_aft(s: Sheet, g: Geo, R) -> None:
    """The hub garage from astern, hidden inside the cowl."""
    k = abs(R(1, 0)[0] - R(0, 0)[0])
    s.rect(*R(g.pod_y[0], g.pod_z[0]), *R(g.pod_y[1], g.pod_z[1]), "hid")
    s.circle(*R(sum(g.sampler_y) / 2, sum(g.sampler_z) / 2), g.sampler_d / 2 * k, "hid")
    s.rect(*R(-g.winch[2], g.winch[3]), *R(g.winch[2], g.winch[4]), "hid")
    s.rect(*R(-4, g.sheave_z - g.sheave_d / 2), *R(4, g.sheave_z + g.sheave_d / 2), "hid")
    for y in (-g.open_w / 2, g.open_w / 2):
        s.line(*R(y, g.hub_z[0] - 8), *R(y, g.hub_z[0] + 8), "vis")


def interior_boxes(g: Geo, sgn: int) -> list[tuple[str, str, float, float, float, float, float, float]]:
    """What sits in one tub (sgn -1 port, +1 stbd): (name, style, x0, x1, y0, y1, z0, z1), y from the hull CL."""
    z0 = HEAT_PLATE[2] + 12.0  # on the plate, which is bedded on the V bottom
    px, vx, ex = g.pack_x, g.vesc_x, g.elec_x
    boxes = [("heat plate", "metal", px - HEAT_PLATE[0] / 2, px + HEAT_PLATE[0] / 2,
              -HEAT_PLATE[1] / 2, HEAT_PLATE[1] / 2, 12.0, z0),
             ("VESC", "elec", vx - VESC_BOX[0] / 2, vx + VESC_BOX[0] / 2, -VESC_BOX[1] / 2, VESC_BOX[1] / 2,
              keel(g.hull, vx) + 15.0, keel(g.hull, vx) + 15.0 + VESC_BOX[2])]
    if sgn < 0:
        boxes.append(("12S drive pack", "pack", px - PACK_12S[0] / 2, px + PACK_12S[0] / 2,
                      -PACK_12S[1] / 2, PACK_12S[1] / 2, z0, z0 + PACK_12S[2]))
    else:
        for yy, name in ((-26.0, "electronics pack"), (26.0, "winch pack")):
            boxes.append((name, "pack", px - PACK_5S[0] / 2, px + PACK_5S[0] / 2,
                          yy - PACK_5S[1] / 2, yy + PACK_5S[1] / 2, z0, z0 + PACK_5S[2]))
        ze = keel(g.hull, ex) + 20.0
        boxes.append(("carrier + Pi 5", "elec", ex - ELEC_BOX[0] / 2, ex + ELEC_BOX[0] / 2,
                      -ELEC_BOX[1] / 2, ELEC_BOX[1] / 2, ze, ze + ELEC_BOX[2]))
    return boxes


def hull_interior_plan(s: Sheet, g: Geo, P, yc: float, sgn: int, style: str = "hid") -> None:
    for _, cls, x0, x1, y0, y1, _, _ in interior_boxes(g, sgn):
        s.rect(*P(x0, yc + y0), *P(x1, yc + y1), style if style != "fill" else cls)
    k = abs(P(1, 0)[0] - P(0, 0)[0])
    s.circle(*P(g.leak_x, yc), 4 * k, "hid" if style != "fill" else "vis")
    for cx in g.conn_x:
        s.circle(*P(cx, yc), 8 * k, "vis")


def ring_lines(s: Sheet, g: Geo, P, yc: float, cls: str = "hid") -> None:
    """The tub's ring frames in plan, a line across the inside of the shell at each (y from the hull
    CL at yc): hidden under the lid, visible looking into an open tub."""
    for xr in g.rings:
        w = hb(g.hull, xr) - g.wall
        s.line(*P(xr, yc - w), *P(xr, yc + w), cls)


def hull_interior_side(s: Sheet, g: Geo, Q, sgn: int = 1, style: str = "hid") -> None:
    for _, cls, x0, x1, _, _, z0, z1 in interior_boxes(g, sgn):
        s.rect(*Q(x0, z0), *Q(x1, z1), style if style != "fill" else cls)



# ---- sheet 1: general arrangement ----------------------------------------------------------


def sheet_ga(g: Geo) -> Sheet:
    s = Sheet(1, "General arrangement: plan, profile, view from astern", "1:10")
    k = 0.1
    h = g.hull
    X0, Y0 = 62.0, 74.0

    def P(x, y):
        return X0 + x * k, Y0 + y * k

    outline, rail = g.plan_outline(), g.rail_outline()
    for sgn in (-1, 1):
        yc = sgn * g.yc
        s.poly([P(x, yc + y) for x, y in rail], "vis", closed=True)
        s.poly([P(x, yc + y) for x, y in outline], "thin", closed=True)
        s.line(*P(-175, yc), *P(g.loa + 40, yc), "ctr")
        ring_lines(s, g, P, yc)
        drive_top(s, g, P, yc)
        hull_interior_plan(s, g, P, yc, sgn)
        s.rect(*P(g.xc - g.shoe_len / 2, yc - g.shoe_w / 2), *P(g.xc + g.shoe_len / 2, yc + g.shoe_w / 2), "vis")
        # arm fairing between the hub and the shoe
        outside = [(y, w) for y, w in g.arm_plan if g.hub_ay * 0.97 <= y <= g.yc - g.shoe_w / 2]
        pts = [P(g.xc - w, sgn * y) for y, w in outside] + [P(g.xc + w, sgn * y) for y, w in reversed(outside)]
        s.poly(pts, "vis", closed=True)
        s.circle(*P(g.vent_x, yc), 1.0, "thin")
        s.text(*P((g.xc + g.shoe_len / 2 + g.loa) / 2, yc + 2.5), "STBD HULL" if sgn > 0 else "PORT HULL", 2.4)
    for fxx in g.fx:
        s.line(*P(fxx, -g.yc), *P(fxx, g.yc), "hid")
    s.poly([P(g.hub_x + px, py) for px, py in superellipse(g.hub_ax, g.hub_ay, g.boat.hub_e)], "vis", closed=True)
    garage_plan(s, g, P)
    s.circle(*P(g.hub_x, 0), 7.5, "ph")
    s.circle(*P(g.hub_x, 0), 1.1, "vis")
    for wy in (-g.whip_y, g.whip_y):
        s.circle(*P(g.hub_x, wy), 0.8, "vis")
    bar_x = g.hub_x + g.hub_ax - 60
    s.rect(*P(bar_x - 16, -180), *P(bar_x + 16, 180), "vis")
    s.line(*P(-190, 0), *P(g.loa + 60, 0), "ctr")
    tx = P(g.hub_x + g.hub_ax + 12, 0)[0]  # labels in the tunnel, fwd of the hub
    s.leader(*P(g.hub_x, 0), tx, P(0, -150)[1], "GNSS mast", size=2.0)
    s.leader(*P(g.hub_x, g.whip_y), tx, P(0, 105)[1], "LTE / WiFi whips", size=2.0)
    s.leader(*P(bar_x + 16, -60), tx, P(0, -70)[1], f"stereo bar ({g.cam_base:.0f})", size=2.0)
    s.leader(*P(g.open_x + 30, g.sampler_y[1] - 20), tx, P(0, 35)[1], "garage (sheet 3)", size=2.0)
    s.leader(*P((g.winch[0] + g.winch[1]) / 2, -g.winch[2] + 10), P(g.winch[0] - 40, 0)[0], P(0, -150)[1],
             "winch (placeholder)", anchor="end", size=2.0)
    s.leader(*P(g.xc - 60, -g.yc + 20), P(g.xc - 330, 0)[0], P(0, -g.yc + 70)[1],
             "drive pack (port hull)", anchor="end", size=2.0)
    s.leader(*P(g.xc + 40, g.yc - 25), P(g.xc - 330, 0)[0], P(0, g.yc - 70)[1],
             "electronics + winch packs (stbd hull)", anchor="end", size=2.0)
    s.leader(*P(g.prop_xa, g.yc + g.prop_d / 2), P(-120, 0)[0], P(0, g.yc + 165)[1],
             "belt outdrive + 110 prop (sheets 5, 6)", anchor="end")
    xr_ = 0.72 * g.loa  # rail callout, on the bow taper
    s.leader(*P(xr_, g.yc + hb(h, xr_) + g.rail), P(xr_ + 40, 0)[0], P(0, g.yc + 165)[1],
             f"rail (lid over the gunwale), {g.rail:.1f} out", anchor="start", size=2.0)
    s.text(*P(g.loa + 25, -g.yc - 6), "FWD", 2.6, "start", bold=True)
    s.add(f'<line class="dim" x1="{P(g.loa + 25, 0)[0]:.2f}" y1="{P(0, -g.yc)[1]:.2f}" '
          f'x2="{P(g.loa + 95, 0)[0]:.2f}" y2="{P(0, -g.yc)[1]:.2f}" marker-end="url(#a)"/>')
    top = P(0, -g.yc - g.beam / 2 - g.rail)[1]
    bot = P(0, g.yc + g.beam / 2 + g.rail)[1]
    s.dim_h(*P(0, -g.yc - hb(h, 0) - g.rail), *P(g.loa, -g.yc - hb(h, g.loa)), top - 6, g.loa,
            f"{g.loa:.0f} shell ({g.loa_rails:.0f} over the rails)")
    s.dim_h(*P(g.aft_end, -g.yc - g.prop_d / 2), *P(g.loa, -g.yc - hb(h, g.loa)), top - 12,
            g.loa_all, f"{g.loa_all:.0f} incl. drives")
    s.dim_h(*P(0, g.yc + hb(h, 0) + g.rail), *P(g.fx[0], g.yc), bot + 6, g.fx[0], f"{g.fx[0]:.0f} frame")
    s.dim_h(*P(g.fx[0], g.yc), *P(g.fx[1], g.yc), bot + 6, g.fx[1] - g.fx[0])
    s.dim_h(*P(0, g.yc + hb(h, 0) + g.rail), *P(g.hub_x, 0), bot + 12, g.hub_x, f"{g.hub_x:.0f} hub / mast")
    s.dim_h(*P(g.hub_x - g.hub_ax, 0), *P(g.hub_x + g.hub_ax, 0), P(0, -g.hub_ay + 45)[1], 2 * g.hub_ax)
    xr = P(g.loa, 0)[0] + 10
    width_rails = mm(g.boat.overall_width) + 2 * g.rail
    xw = mm(h.taper_start * h.loa)  # the widest station
    s.dim_v(*P(xw, -g.yc - hb(h, xw) - g.rail), *P(xw, g.yc + hb(h, xw) + g.rail),
            xr + 8, width_rails, f"{width_rails:.0f} over rails ({mm(g.boat.overall_width):.0f} shells)")
    s.dim_v(*P(g.loa - 180, -g.yc), *P(g.loa - 180, g.yc), xr, g.spacing, f"{g.spacing:.0f} hull CL")
    s.dim_v(*P(g.aft_end, g.yc - g.beam / 2), *P(g.aft_end, g.yc + g.beam / 2), P(-175, 0)[0], g.beam)
    s.dim_v(*P(g.hub_x - g.hub_ax, -g.hub_ay), *P(g.hub_x - g.hub_ax, g.hub_ay), P(g.hub_x - g.hub_ax, 0)[0] - 4,
            2 * g.hub_ay)
    s.view_title(P(g.loa / 2, 0)[0], bot + 21, "PLAN VIEW", "1:10")

    # profile from starboard
    Yp = 231.0

    def Q(x, z):
        return X0 + x * k, Yp - z * k

    xs = stations(h, 20)
    s.poly([Q(0, g.depth), Q(0, keel(h, 0))] + [Q(x, keel(h, x)) for x in xs] +
           [Q(g.loa, keel(h, g.loa)), Q(g.loa, g.depth)], "vis", closed=True)
    s.poly([Q(x, side_tangent(h, x)) for x in xs], "thin")
    s.rect(*Q(-g.rail, g.rail_z[0]), *Q(g.loa + g.rail, g.rail_z[1]), "vis")
    for z, cls in ((g.dwl, "wl"), (g.drafts[0], "wlt"), (g.drafts[2], "wlt")):
        s.line(*Q(-180, z), *Q(g.loa + 40, z), cls)
    s.text(*Q(g.loa - 250, g.dwl + 14), f"DWL {g.dwl:.0f} ({g.conds[1].total:.1f} kg)", 2.0, "start", cls="blue")
    s.rect(*Q(g.xc - g.shoe_len / 2, g.depth), *Q(g.xc + g.shoe_len / 2, g.depth + SHOE_H), "vis")
    zc = [(sc, z) for sc, z in g.hub_side()]
    s.poly([Q(g.hub_x - g.hub_ax * sc, z) for sc, z in zc] + [Q(g.hub_x + g.hub_ax * sc, z) for sc, z in reversed(zc)],
           "vis", closed=True)
    for fxx in g.fx:
        s.rect(*Q(fxx - g.frame_t / 2, g.foot_z), *Q(fxx + g.frame_t / 2, g.frame_top), "hid")
    garage_side(s, g, Q)
    hull_interior_side(s, g, Q)
    s.line(*Q(g.hub_x, g.dome_z(g.hub_x, 0)), *Q(g.hub_x, g.mast_top - 45), "vis")
    s.rect(*Q(g.hub_x - 75, g.mast_top - 45), *Q(g.hub_x + 75, g.mast_top), "vis")
    s.line(*Q(g.hub_x + 8, g.dome_z(g.hub_x, g.whip_y)), *Q(g.hub_x + 8, g.mast_top), "thin")
    bar_x = g.hub_x + g.hub_ax - 60
    bz = g.dome_z(bar_x, 0) + 10
    s.rect(*Q(bar_x - 16, bz - 16), *Q(bar_x + 16, bz + 16), "vis")
    drive_side(s, g, Q, k)
    s.line(*Q(-190, g.prop_z), *Q(20, g.prop_z), "ctr")
    s.line(*Q(-200, 0), *Q(g.loa + 30, 0), "ctr")
    s.text(*Q(g.loa + 32, -4), "BL", 2.0, "start")
    s.leader(*Q(g.loa - 290, g.rail_z[1]), Q(g.loa - 230, 0)[0], Q(0, 330)[1], f"rail / lid joint z {g.zj:.0f} (sheet 4)",
             size=2.0)
    xl = Q(-200, 0)[0] - 3
    s.dim_v(*Q(g.aft_end, 0), *Q(g.aft_end, g.dwl), xl, g.dwl)
    s.dim_v(*Q(g.prop_xa, g.prop_bottom), *Q(g.aft_end, g.dwl), xl - 7, g.total_draft,
            f"{g.total_draft:.0f} total draft")
    s.dim_v(*Q(0, 0), *Q(0, g.depth), xl - 14, g.depth)
    s.dim_v(*Q(0, 0), *Q(-g.rail, g.zj), xl - 21, g.zj, f"{g.zj:.0f} joint")
    xr2 = Q(g.loa, 0)[0] + 40
    s.dim_v(*Q(g.loa, 0), *Q(g.hub_x, g.hub_z[0]), xr2, g.hub_z[0], f"{g.hub_z[0]:.0f} hub bottom")
    s.dim_v(*Q(g.loa, 0), *Q(g.hub_x, g.hub_z[2]), xr2 + 7, g.hub_z[2], f"{g.hub_z[2]:.0f} hub top")
    s.dim_v(*Q(g.loa, 0), *Q(g.hub_x, g.mast_top), xr2 + 14, g.mast_top, f"{g.mast_top:.0f} GNSS top")
    s.dim_v(*Q(0, 0), *Q(0, keel(h, 0)), Q(0, 0)[0] + 5, keel(h, 0))
    xa0, xr0 = mm(h.stern_rise_end * h.loa), mm(h.rocker_start * h.loa)
    s.dim_h(*Q(0, 0), *Q(xa0, 0), Q(0, 0)[1] + 7, xa0, f"{xa0:.0f} keel rise")
    s.dim_h(*Q(xr0, 0), *Q(g.loa, keel(h, g.loa)), Q(0, 0)[1] + 7, g.loa - xr0, f"{g.loa - xr0:.0f} rocker")
    s.view_title(Q(g.loa / 2, 0)[0], Q(0, 0)[1] + 16, "PROFILE (FROM STARBOARD)", "1:10")

    # view from astern
    Xa, Ya = 336.0, 196.0

    def R(y, z):
        return Xa + y * k, Ya - z * k

    for sgn in (-1, 1):
        yc = sgn * g.yc
        half = section_points(h, 0.9 * h.taper_start * h.loa)  # the full section, in the parallel body
        ring = [(mm(y), mm(z)) for y, z in half] + [(-mm(y), mm(z)) for y, z in reversed(half[1:-1])]
        s.poly([R(yc + y, z) for y, z in ring], "vis", closed=True)
        t_half = section_points(h, 0.0)
        s.poly([R(yc + mm(y), mm(z)) for y, z in t_half[:17]], "thin")
        s.poly([R(yc - mm(y), mm(z)) for y, z in t_half[:17]], "thin")
        s.rect(*R(yc - g.beam / 2 - g.rail, g.rail_z[0]), *R(yc + g.beam / 2 + g.rail, g.rail_z[1]), "vis")
        drive_aft(s, g, R, k, yc)
        s.rect(*R(yc - g.shoe_w / 2, g.depth), *R(yc + g.shoe_w / 2, g.depth + SHOE_H), "vis")
        s.line(*R(yc, -60), *R(yc, g.depth + 80), "ctr")
        up = [(sgn * y, z) for y, z in g.arm_up if abs(y) >= g.hub_ay * 0.95]
        lo = [(sgn * y, z) for y, z in g.arm_lo if abs(y) >= g.hub_ay * 0.95]
        s.poly([R(y, z) for y, z in up], "vis")
        s.poly([R(y, z) for y, z in lo], "vis")
    zc = g.hub_side()
    s.poly([R(-g.hub_ay * sc, z) for sc, z in zc] + [R(g.hub_ay * sc, z) for sc, z in reversed(zc)], "vis", closed=True)
    s.poly([R(y, z) for y, z in g.frame], "hid", closed=True)
    garage_aft(s, g, R)
    s.line(*R(0, g.hub_z[2]), *R(0, g.mast_top - 45), "vis")
    s.rect(*R(-75, g.mast_top - 45), *R(75, g.mast_top), "vis")
    for wy in (-g.whip_y, g.whip_y):
        s.line(*R(wy, g.dome_z(g.hub_x, wy)), *R(wy, g.mast_top), "vis")
    s.line(*R(-500, g.dwl), *R(500, g.dwl), "wl")
    s.line(*R(0, -60), *R(0, g.mast_top + 30), "ctr")
    ytop = R(0, g.mast_top)[1] - 6
    s.dim_h(*R(-g.hub_ay, g.hub_z[1]), *R(g.hub_ay, g.hub_z[1]), ytop, 2 * g.hub_ay, f"{2 * g.hub_ay:.0f} hub")
    s.dim_h(*R(-g.yc, g.depth + 80), *R(g.yc, g.depth + 80), ytop - 6, g.spacing, f"{g.spacing:.0f} hull CL")
    s.dim_h(*R(-g.yc - g.beam / 2 - g.rail, g.rail_z[1]), *R(g.yc + g.beam / 2 + g.rail, g.rail_z[1]), ytop - 12,
            width_rails, f"{width_rails:.0f} over rails")
    yb = R(0, g.prop_bottom)[1] + 7
    s.dim_h(*R(g.yc - g.beam / 2, 0), *R(g.yc + g.beam / 2, 0), yb, g.beam)
    s.dim_h(*R(-g.yc + g.beam / 2, g.depth), *R(g.yc - g.beam / 2, g.depth), yb, g.spacing - g.beam,
            f"{g.spacing - g.beam:.0f} tunnel")
    s.dim_v(*R(g.hub_ay, g.dwl), *R(g.hub_ay, g.hub_z[0]), R(g.yc + g.beam / 2 + g.rail, 0)[0] + 7,
            g.hub_z[0] - g.dwl, f"{g.hub_z[0] - g.dwl:.0f} hub over DWL")
    s.text(*R(-g.yc - g.beam / 2 - 10, 8), f"{h.deadrise_deg:.0f}° deadrise, R{mm(h.chine_r):.0f} chine", 1.9, "end")
    s.text(*R(0, g.hub_z[0] + 25), "frame (hidden)", 1.8)
    s.view_title(Xa, yb + 9, "VIEW FROM ASTERN", "1:10")

    design = g.conds[1]
    port, stbd = module_masses(g)
    upper = design.total - port - stbd
    s.text(216, 20, "MODULES", 3.0, "start", bold=True)
    s.table(216, 23, ["Module", "Design kg", "Contents"], [
        ["Port tub", f"{port:.1f}", f"one-piece PLA print + ring frames, flange with {g.n_screws} M4 inserts; "
                                    "drive pack, VESC, heat plate, leak probe, thrust pad"],
        ["Stbd tub", f"{stbd:.1f}", "the same shell; electronics + winch packs, Pi 5 + carrier, VESC, heat plate"],
        ["Upper module", f"{upper:.1f}", "bridge (arch frames, arms, hub garage: winch, pod, Van Dorn; mast, "
                                         "cameras) + 2 lids + 2 belt outdrives"],
        ["Boat", f"{design.total:.1f}", f"incl. {MARGIN:.0%} growth margin and a 2 L water sample; no robot arm"],
    ], [26, 20, 148])
    s.lines_of_text(216, 52, [
        "ASSEMBLY",
        "1. Fit each tub's heat plate, packs and electronics, the leak probe (sheet 4) and the drive's thrust pad (sheet 6).",
        f"2. Bond the ribs into each lid with the foot bolted up as the jig (sheet 3). Then {4 * len(g.bolt_y)}x M6 x "
        f"{BOLT_L:.0f} up through the rib bosses hold each foot, EPDM pad between.",
        "3. Bolt each outdrive mount to its lid from inside: 4x M5 up through the aft deck, 2x through the aft wall.",
        f"4. Press the {mm(g.lid.gasket_d):.0f} mm cord into each tub's flange groove.",
        "5. Hold the bridge + lids just above the tubs, plug the lid connectors inside, lower it; the drip lips locate.",
        f"6. Screw down the rails: {g.n_screws} M4 per hull, {mm(g.lid.screw_pitch_near):.0f} mm pitch "
        f"within 150 mm of a frame, {mm(g.lid.screw_pitch):.0f} elsewhere.",
        "",
        f"Waterlines: DWL {g.dwl:.0f} at {design.total:.1f} kg; thin blue = light "
        f"{g.drafts[0]:.0f} / max {g.drafts[2]:.0f}. Lid joint {g.zj - g.dwl:.0f} above the DWL.",
        "Wiring enters each hull only through IP68 bulkhead connectors in its lid. The packs sit low,",
        "on aluminium plates on the hull bottoms, so the water carries their heat away.",
        "Geometry comes from mechanical/hull_sizing.py; regenerate after changes.",
    ], size=2.3, lead=3.5, bold_first=True)
    return s


# ---- sheet 2: demi-hull lines and construction --------------------------------------------


def sheet_lines(g: Geo) -> Sheet:
    s = Sheet(2, "Demi-hull lines, lid joint plane, one-piece prints, offsets and fillets", "1:5 / 1:2.5")
    h = g.hull
    k = 0.2
    X0, Y0 = 38.0, 84.0

    def Q(x, z):
        return X0 + x * k, Y0 - z * k

    xs = stations(h, 10)
    s.poly([Q(0, g.depth), Q(0, keel(h, 0))] + [Q(x, keel(h, x)) for x in xs] +
           [Q(g.loa, keel(h, g.loa)), Q(g.loa, g.depth)], "vis", closed=True)
    s.poly([Q(x, chine(h, x)) for x in xs], "ph")
    s.poly([Q(x, side_tangent(h, x)) for x in xs], "thin")
    s.rect(*Q(-g.rail, g.rail_z[0]), *Q(g.loa + g.rail, g.rail_z[1]), "thin")
    s.line(*Q(-40, g.zj), *Q(g.loa + 30, g.zj), "lidj")
    s.text(*Q(g.loa + 32, g.zj - 3), f"LID JOINT z {g.zj:.0f}", 1.9, "start", cls="purple")
    for x in range(100, int(g.loa), 100):
        s.line(*Q(x, keel(h, x)), *Q(x, g.depth), "thin")
        s.text(*Q(x, -11), f"{x}", 1.8)
    for xr in g.rings:  # inside the tub: ring frames up to the joint plane; lid ribs above it
        s.line(*Q(xr, keel(h, xr) + RING[0]), *Q(xr, g.zj - 4), "hid")
    for xr in g.rib_x:
        s.line(*Q(xr, g.zj), *Q(xr, g.depth - g.wall), "hid")
    s.text(*Q(g.rings[0], g.zj - 18), "ring frames (hidden)", 1.7, "start")
    s.text(*Q(g.rib_x[0] + 6, g.zj + 22), "lid ribs", 1.7, "start")
    for z, cls in ((g.dwl, "wl"), (g.drafts[0], "wlt"), (g.drafts[2], "wlt")):
        s.line(*Q(-40, z), *Q(g.loa + 30, z), cls)
    s.text(*Q(g.loa + 32, g.dwl - 4), f"DWL {g.dwl:.0f}", 2.0, "start", cls="blue")
    s.text(*Q(g.loa + 32, g.drafts[2] + 8), f"max {g.drafts[2]:.0f}", 1.8, "start", cls="blue")
    s.text(*Q(g.loa + 32, g.drafts[0] - 16), f"light {g.drafts[0]:.0f}", 1.8, "start", cls="blue")
    s.rect(*Q(g.xc - g.foot_len / 2, g.depth), *Q(g.xc + g.foot_len / 2, g.foot_z), "ph")
    s.line(*Q(-45, 0), *Q(g.loa + 30, 0), "ctr")
    ytop = Q(0, g.depth)[1] - 10
    s.dim_h(*Q(0, g.depth), *Q(g.loa, g.depth), ytop, g.loa, f"{g.loa:.0f} shell")
    s.dim_h(*Q(-g.rail, g.rail_z[1]), *Q(g.loa + g.rail, g.rail_z[1]), ytop - 7, g.loa_rails,
            f"{g.loa_rails:.0f} over the rails = the lid's print height (tub {g.print_h[0]:.0f})")
    s.dim_v(*Q(0, 0), *Q(0, g.depth), Q(0, 0)[0] - 12, g.depth)
    s.dim_v(*Q(0, 0), *Q(0, g.dwl), Q(0, 0)[0] - 6, g.dwl)
    s.dim_v(*Q(0, 0), *Q(-g.rail, g.zj), Q(0, 0)[0] - 18, g.zj)
    s.dim_v(*Q(0, 0), *Q(0, keel(h, 0)), Q(0, 0)[0] + 5, keel(h, 0))
    s.dim_v(*Q(g.loa, 0), *Q(g.loa, keel(h, g.loa)), Q(g.loa, 0)[0] + 6, keel(h, g.loa))
    yb = Q(0, 0)[1] + 16
    xa0, xr0 = mm(h.stern_rise_end * h.loa), mm(h.rocker_start * h.loa)
    s.dim_h(*Q(0, keel(h, 0)), *Q(xa0, 0), yb, xa0, f"{xa0:.0f} straight keel rise")
    s.dim_h(*Q(0, 0), *Q(xr0, 0), yb + 7, xr0, f"{xr0:.0f} rocker starts: keel z = {keel(h, g.loa):.0f} xi^2")
    s.leader(*Q(300, chine(h, 300)), Q(300, 0)[0] + 6, Q(0, 0)[1] + 9, "sharp chine (phantom) = offsets")
    s.view_title(Q(g.loa / 2, 0)[0], Q(0, 0)[1] + 30, "PROFILE (ONE HULL)", "1:5")

    Yp = 160.0

    def P(x, y):
        return X0 + x * k, Yp + y * k

    s.poly([P(x, y) for x, y in g.rail_outline(10)], "vis", closed=True)
    s.poly([P(x, y) for x, y in g.plan_outline(10)], "thin", closed=True)
    s.line(*P(-40, 0), *P(g.loa + 30, 0), "ctr")
    ring_lines(s, g, P, 0.0)
    s.rect(*P(g.xc - g.foot_len / 2, -g.foot_w / 2), *P(g.xc + g.foot_len / 2, g.foot_w / 2), "ph")
    s.leader(*P(g.xc + g.foot_len / 2, -g.foot_w / 2 + 12), P(g.loa + 30, 0)[0], P(0, -95)[1],
             "foot: a flat landing in the lid deck", size=1.8)
    s.text(P(g.loa + 30, 0)[0] + 1, P(0, -95)[1] + 3.3, f"under it (fills <= {g.landing:.1f})", 1.8, "start")
    for fxx in g.fx:
        for yy in g.bolt_y:
            for sgn in (-1, 1):
                s.circle(*P(fxx + g.bolt_dx, sgn * yy), 3.3 * k, "vis")
    s.circle(*P(g.vent_x, 0), 10 * k, "thin")
    s.leader(*P(g.vent_x + 6, 6), P(g.vent_x + 50, 0)[0], P(0, 118)[1], "M12 IP68 membrane vent (in the lid)", size=2.0)
    bolts = ", +/-".join(f"{v:.0f}" for v in g.bolt_y)
    s.leader(*P(g.fx[1] + g.bolt_dx, -g.bolt_y[-1]), P(g.fx[1] + 40, 0)[0], P(0, -132)[1],
             f"{4 * len(g.bolt_y)}x M6 per foot: frame + {g.bolt_dx:.0f}, y = +/-{bolts}", size=1.8)
    xt = mm(h.taper_start * h.loa)
    s.dim_h(*P(0, hb(h, 0)), *P(xt, hb(h, xt)), P(0, hb(h, 0) + g.rail)[1] + 6, xt, f"{xt:.0f} parallel")
    s.dim_h(*P(xt, hb(h, xt)), *P(g.loa, hb(h, g.loa)), P(0, hb(h, 0) + g.rail)[1] + 6, g.loa - xt,
            f"{g.loa - xt:.0f} taper: half-breadth = {hb(h, 0):.0f} (1 - xi^{h.taper_power:g})")
    s.dim_v(*P(0, -hb(h, 0)), *P(0, hb(h, 0)), P(0, 0)[0] - 7, g.beam)
    s.dim_v(*P(-g.rail, -hb(h, 0) - g.rail), *P(-g.rail, hb(h, 0) + g.rail), P(0, 0)[0] - 14,
            g.beam + 2 * g.rail, f"{g.beam + 2 * g.rail:.0f} rail")
    s.dim_v(*P(g.loa, -hb(h, g.loa)), *P(g.loa, hb(h, g.loa)), P(g.loa, 0)[0] + 7, mm(h.stem_flat),
            f"{mm(h.stem_flat):.0f} stem")
    s.dim_h(*P(0, -hb(h, 0) - g.rail), *P(g.xc - g.foot_len / 2, -g.foot_w / 2), P(0, -hb(h, 0) - g.rail)[1] - 5,
            g.xc - g.foot_len / 2, f"{g.xc - g.foot_len / 2:.0f} foot")
    s.view_title(P(g.loa / 2, 0)[0], P(0, hb(h, 0) + g.rail)[1] + 16, "PLAN (ONE HULL)", "1:5")

    kb = 0.4
    Xb, Yb = 366.0, 160.0

    def B(y, z):
        return Xb + y * kb, Yb - z * kb

    for xs_, side in ((g.aft_stations, -1), (g.fwd_stations, 1)):
        for i, x in enumerate(xs_):
            pts = section_points(h, x / 1000)
            c = g.stations[x]
            s.poly([B(side * mm(y), mm(z)) for y, z in pts], "vis", style=f"stroke:{c}")
            if side < 0:  # aft sections share the side; label them on their V bottoms
                s.text(*B(-58, keel(h, x) + 58 * h.tb + 3), f"{x:.0f}", 1.8, "middle", color=c)
            else:  # stagger: the fuller fwd sections nearly coincide at the side
                s.text(*B(hb(h, x) + 3, side_tangent(h, x) - 2 - 12 * (i % 2)), f"{x:.0f}", 1.8, "start",
                       color=c)
        yr = side * g.beam / 2
        s.rect(*B(yr, g.zj - g.ft), *B(yr + side * (g.fw - CLEAR), g.zj), "cut2")
        s.rect(*B(yr, g.zj), *B(yr + side * g.fw, g.zj + g.ft), "cut")
        s.rect(*B(yr + side * g.fw, g.rail_z[0]), *B(yr + side * g.rail, g.rail_z[1]), "cut")
    s.line(*B(0, -15), *B(0, g.depth + 15), "ctr")
    s.line(*B(-120, 0), *B(120, 0), "ctr")
    s.line(*B(-120, g.dwl), *B(120, g.dwl), "wl")
    s.line(*B(-g.beam / 2 - g.rail - 4, g.zj), *B(g.beam / 2 + g.rail + 4, g.zj), "lidj")
    s.text(*B(-118, g.dwl + 3), f"DWL {g.dwl:.0f}", 1.8, "start", cls="blue")
    s.text(*B(-55, g.zj + 3), f"lid joint {g.zj:.0f}", 1.8, cls="purple")
    s.text(*B(-60, g.depth + 5), "AFT (looking fwd)", 1.9)
    s.text(*B(60, g.depth + 5), "FWD (looking aft)", 1.9)
    s.dim_h(*B(0, g.depth + 15), *B(g.beam / 2, g.depth), B(0, g.depth)[1] - 10, g.beam / 2)
    s.dim_v(*B(g.beam / 2, 0), *B(g.beam / 2, g.depth), B(g.beam / 2 + g.rail, 0)[0] + 4, g.depth)
    s.text(*B(-22, 5), f"{h.deadrise_deg:.0f}°", 1.9, "end")
    s.text(*B(-118, -22), "labels = mm fwd of transom; sheet 7 draws each slice on its own, same colours", 1.8,
           "start")
    s.view_title(Xb, B(0, 0)[1] + 16, "BODY PLAN (with fillets)", "1:2.5")

    s.text(20, 209, "OFFSETS (sharp chine; mm from transom / baseline / hull centreline)", 2.7, "start", bold=True)
    rows = []
    for x in sorted(set(g.stations) | {10.0 * round(0.85 * g.loa / 10)}):  # the stations + one more on the bow
        rows.append([f"{x:.0f}", f"{keel(h, x):.1f}", f"{chine(h, x):.1f}", f"{hb(h, x):.1f}",
                     f"{mm(h.fillet(x / 1000)[0]):.0f} / {mm(h.deck_fillet(x / 1000)):.0f}"])
    half = (len(rows) + 1) // 2
    heads = ["x", "keel z", "chine z", "half-breadth", "R chine / deck"]
    s.table(20, 212, heads, rows[:half], [12, 14, 14, 20, 22], 2.0, 4.0)
    s.table(108, 212, heads, rows[half:], [12, 14, 14, 20, 22], 2.0, 4.0)

    lid = g.lid
    gw, gd = (mm(v) for v in lid.groove)
    s.lines_of_text(200, 198, [
        "CONSTRUCTION (open tub + removable lid, each printed in one piece)",
        f"- Loft the sharp-chine hull from the offsets, fillet chine R{mm(h.chine_r):.0f} and deck edge R{mm(h.deck_r):.0f} "
        f"(0.45 x half-breadth near the stem), split at the lid joint plane z {g.zj:.0f}.",
        f"- PLA on the Elegoo OrangeStorm Giga: 0.6-0.8 nozzle, 4 walls ({g.wall:.1f}), +3-5 % flow. Glass outside "
        "(200 g/m2; 2nd layer on keel, chines, stem), 2 coats epoxy inside.",
        f"- Print the tub and the lid standing on the stern: {g.print_h[0]:.0f} and {g.print_h[1]:.0f} tall incl. the rail "
        f"(Giga: 1000). The rail laps {g.fw:.0f} / {g.rail:.1f} past",
        f"  the transom, so support the {mm(h.transom_t):.0f} mm transom (lid: aft wall) off the bed up to the flange. "
        "10 mm brim; slow the walls near the top.",
        f"- Tub: ring frames at x {' / '.join(f'{v:.0f}' for v in g.rings)}, {RING[0]:.0f} deep, aft face 45 deg so "
        "they print unsupported, a limber notch at the keel (sheet 3).",
        f"- Lid: {mm(lid.rib_t):.0f} mm ribs at {g.ribs} with the foot-bolt bosses, printed flat and bonded in with "
        "thickened-epoxy fillets (sheet 3).",
        f"- Rail: {g.fw:.0f} mm flanges, {mm(lid.gasket_d):.0f} mm cord in a {gw:.0f} x {gd:.1f} groove, {g.n_screws}x M4 "
        f"into heat-set inserts (sheet 4); epoxy and sand the flange: layer lines cross the gasket.",
        "- One sealed space per hull: leak probe at the keel low point (carrier J8 port / J9 stbd), M12 vent in the lid. "
        "Epoxy only, slow hardener: PLA softens ~55 C.",
        f"- Shell {shell_mass(h):.1f} kg per hull incl. ribs, ring frames, glass, epoxy, + {lid_joint_mass(h):.1f} "
        "kg rail. Pressure-test (<= 0.03 bar) before fitting out.",
    ], size=2.0, lead=3.2, bold_first=True)
    return s


# ---- sheet 3: bridge and joint details -------------------------------------------------------


def lid_rib_section(s: Sheet, g: Geo, X: float, Y: float, k: float) -> None:
    """Lid cut through the foot-bolt axes at the fwd rib, where the bow taper makes the deck narrowest,
    looking forward (hull CL at X, z 250 at Y)."""
    h = g.hull

    def L(y, z):
        return X + y * k, Y - (z - g.depth) * k

    x = (g.fx[1] + g.bolt_dx) / 1000
    half = [(mm(y), mm(z)) for y, z in section_points(h, x, part="lid")]
    outer = half + [(-y, z) for y, z in reversed(half[:-1])]
    inner = offset_polyline(outer, g.wall)
    hbx = half[0][0]
    s.poly([L(y, z) for y, z in outer + list(reversed(inner))], "cut", closed=True)
    s.poly([L(y, z) for y, z in inner], "cut", closed=True)  # the rib fills the lid here
    rd, ftop = mm(h.deck_fillet(x)), mm(h.flat_deck(x)) / 2
    for sgn in (-1, 1):  # the flat landing: the deck built up to the foot's underside past the flat top
        ys = [ftop + (g.foot_w / 2 - ftop) * i / 8 for i in range(9)]
        arc = [(sgn * y, g.depth - rd + math.sqrt(max(rd * rd - (y - ftop) ** 2, 0.0))) for y in ys]
        s.poly([L(y, z) for y, z in arc + [(sgn * g.foot_w / 2, g.depth), (sgn * ftop, g.depth)]], "cut", closed=True)
    s.rect(*L(-g.foot_w / 2, g.depth), *L(g.foot_w / 2, g.depth + g.pad_t), "rubber")
    s.rect(*L(-g.foot_w / 2, g.depth + g.pad_t), *L(g.foot_w / 2, g.foot_z), "plate")
    for sgn in (-1, 1):
        yr = sgn * hbx
        s.rect(*L(yr, g.zj), *L(yr + sgn * g.fw, g.zj + g.ft), "cut")
        s.rect(*L(yr + sgn * g.fw, g.rail_z[0]), *L(yr + sgn * g.rail, g.rail_z[1]), "cut")
        s.rect(*L(yr, g.zj - g.ft), *L(yr + sgn * (g.fw - CLEAR), g.zj), "cut2")
        s.rect(*L(yr - sgn * g.wall, g.zj - 22), *L(yr, g.zj), "cut2")
        s.line(*L(yr - sgn * 4, g.zj - 22), *L(yr + sgn * 2, g.zj - 22), "thin")
        for yy in g.bolt_y:
            yb = sgn * yy
            seat = g.zj + CBORE[1]  # counterbore floor: the washer bears up against it
            s.rect(*L(yb - CBORE[0] / 2, g.zj), *L(yb + CBORE[0] / 2, seat), "void")
            s.rect(*L(yb - 3.3, seat), *L(yb + 3.3, g.depth + g.pad_t), "void")
            s.rect(*L(yb - WASHER[0] / 2, seat - WASHER[1]), *L(yb + WASHER[0] / 2, seat), "metal")
            s.rect(*L(yb - HEAD[0] / 2, seat - WASHER[1] - HEAD[1]), *L(yb + HEAD[0] / 2, seat - WASHER[1]), "metal")
            s.rect(*L(yb - 3, seat - WASHER[1]), *L(yb + 3, seat - WASHER[1] + BOLT_L), "metal")
    s.rect(*L(-g.frame_h / 2, g.foot_z), *L(g.frame_h / 2, g.foot_z + 28), "ph")
    s.line(*L(-hbx - g.rail - 6, g.zj), *L(hbx + g.rail + 6, g.zj), "lidj")
    s.line(*L(0, g.zj - 26), *L(0, g.foot_z + 32), "ctr")
    # dimensions
    y_top = L(0, g.foot_z + 28)[1] - 5
    ya, yo = g.bolt_y[0], g.bolt_y[-1]
    s.dim_h(*L(-ya, g.foot_z), *L(ya, g.foot_z), y_top, 2 * ya)
    s.dim_h(*L(-yo, g.foot_z), *L(yo, g.foot_z), y_top - 6, 2 * yo, f"{2 * yo:.0f} bolts")
    s.dim_h(*L(-g.foot_w / 2, g.foot_z), *L(g.foot_w / 2, g.foot_z), y_top - 12, g.foot_w, f"{g.foot_w:.0f} foot")
    sy = mm(g.lid.screw_y)
    y_bot = L(0, g.zj - 22)[1] + 6
    s.dim_h(*L(-hbx - sy, g.zj + g.ft), *L(hbx + sy, g.zj + g.ft), y_bot, 2 * (hbx + sy),
            f"{2 * (hbx + sy):.0f} rail screw lines (rib span)")
    xr = L(hbx + g.rail, 0)[0] + 5
    s.dim_v(*L(hbx, g.zj), *L(hbx, g.depth), xr, g.rib_depth, f"{g.rib_depth:.0f}")
    xl = L(-hbx - g.rail, 0)[0] - 3
    s.leader(*L(-yo, g.zj + 2), xl, L(0, g.zj - 12)[1], f"M6 x {BOLT_L:.0f} A4 + bonded seal, from below", "end", 1.9)
    s.leader(*L(-ya, g.zj + 30), xl, L(0, g.zj + 34)[1], f"4x boss {BOSS_D:.0f} dia, full depth", "end", 1.9)
    s.leader(*L(-20, g.zj + 30), xl, L(0, g.depth - 6)[1], f"RIB {mm(g.lid.rib_t):.0f} thick, printed flat, bonded in",
             "end", 1.9)
    s.leader(*L(-ya + CBORE[0] / 2, g.zj + 4), xl, L(0, g.zj + 2)[1],
             f"counterbore {CBORE[0]:.0f} dia x {CBORE[1]:.0f} for the head", "end", 1.9)
    s.leader(*L(-50, g.depth - 1), xl, L(0, g.depth + 8)[1], f"lid {g.wall:.0f} wall", "end", 1.9)
    s.leader(*L(g.foot_w / 2 - 6, g.foot_z - 2), xr + 16, L(0, g.foot_z + 10)[1], f"foot {g.foot_t:.0f} mm 6061",
             size=1.9)
    s.leader(*L(g.foot_w / 2 - 14, g.depth + 0.7), xr + 16, L(0, g.depth + 3)[1], f"EPDM pad {g.pad_t:.1f}", size=1.9)
    s.leader(*L(hbx + 6, g.zj + 2), xr + 16, L(0, g.zj + 12)[1], "rail (sheet 4)", size=1.9)
    s.leader(*L(hbx - 1, g.zj - 16), xr + 16, L(0, g.zj - 14)[1], "tub (ring frame under the rib)", size=1.9)
    s.leader(*L(g.foot_w / 2 - 2, g.depth - 0.5), xr + 16, L(0, g.depth - 7)[1], "flat landing under the foot",
             size=1.9)
    s.text(xr + 17, L(0, g.depth - 7)[1] + 3.6, f"({g.landing:.1f} deep at its fwd corners)", 1.9, "start")
    s.text(X, L(0, g.foot_z + 28)[1] + 3.5, "arch frame (phantom)", 1.8)


def sheet_details(g: Geo) -> Sheet:
    s = Sheet(3, "Arch frame, foot plate, lid rib, hub garage, rib bond, ring frame", "as noted")
    # arch frame plate, 1:5, seen from ahead (y horizontal, z up)
    k = 0.2
    X0, Z0 = 112.0, 62.0

    def F(y, z):
        return X0 + y * k, Z0 - (z - 250.0) * k

    s.poly([F(y, z) for y, z in g.frame], "plate", closed=True)
    hub_c = g.frame_top - g.frame_h / 2
    for y, d in LIGHTENING:
        s.circle(*F(y, hub_c), d / 2 * k, "vis")
    for y in GARAGE_HOLES_Y:
        s.circle(*F(y, g.frame_top - 12), 2.75 * k * 1.3, "vis")
    for sgn in (-1, 1):
        for z in g.foot_holes_z:
            s.circle(*F(sgn * g.yc, z), 2.75 * k * 1.3, "vis")
    ys = [p[0] for p in g.frame]
    zs = [p[1] for p in g.frame]
    s.line(*F(-g.yc, g.foot_z - 8), *F(-g.yc, max(zs) + 8), "ctr")
    s.line(*F(g.yc, g.foot_z - 8), *F(g.yc, max(zs) + 8), "ctr")
    s.dim_h(*F(min(ys), g.foot_z), *F(max(ys), g.foot_z), F(0, g.foot_z)[1] + 7, max(ys) - min(ys),
            f"{max(ys) - min(ys):.0f} overall")
    s.dim_h(*F(-g.yc, g.foot_z), *F(g.yc, g.foot_z), F(0, g.foot_z)[1] + 13, g.spacing, f"{g.spacing:.0f} foot CL")
    s.dim_v(*F(max(ys), g.foot_z), *F(0, max(zs)), F(max(ys), 0)[0] + 6, max(zs) - g.foot_z,
            f"{max(zs) - g.foot_z:.0f}")
    s.leader(*F(0, hub_c), F(60, 0)[0], F(0, max(zs) + 22)[1], f"3x {LIGHTENING[0][1]:.0f} lightening")
    s.leader(*F(-g.yc, g.foot_holes_z[1]), F(-g.yc + 60, 0)[0], F(0, max(zs) + 22)[1],
             "2x 5.5 per foot (angle brackets)")
    s.text(X0, F(0, g.foot_z)[1] + 20, f"1/4 in (6.35) 6061-T6, 2 req. Section {g.frame_h:.0f} deep, +/-25 from the "
           f"arch centreline; feet stand on the foot plate, {g.foot_z - g.depth:.1f} above the lid deck. "
           "Cut file: cad/arch_frame_plate.dxf", 1.9)
    s.view_title(X0, F(0, g.foot_z)[1] + 26, "ARCH FRAME PLATE (FROM AHEAD)", "1:5")

    # lid rib at the fwd frame, 1:2.5, top right
    kr = 0.4
    Xr, Yr = 318.0, 56.0
    lid_rib_section(s, g, Xr, Yr, kr)
    s.view_title(Xr + 8, Yr + (g.depth - g.zj + 22) * kr + 13,
                 f"LID RIB (SECTION AT x {g.fx[1] + g.bolt_dx:.0f}, LOOKING FWD; THE AFT RIB IS THE SAME)", "1:2.5")

    # foot plate, 1:4, plan (x along the hull, y across)
    k4 = 0.25
    Xf, Yf = 68.0, 124.0

    def T(x, y):
        return Xf + x * k4, Yf + y * k4

    L, Wd = g.foot_len, g.foot_w
    s.rect(*T(-L / 2, -Wd / 2), *T(L / 2, Wd / 2), "plate")
    for fxx in g.fx:
        lx = fxx - g.xc
        s.rect(*T(lx - g.frame_t / 2, -25), *T(lx + g.frame_t / 2, 25), "hid")
        for yy in (-12, 12):
            s.circle(*T(lx + (14 if lx < 0 else -14), yy), 2.75 * k4 * 1.4, "vis")
        for yy in g.bolt_y:
            for sgn in (-1, 1):
                s.circle(*T(lx + g.bolt_dx, sgn * yy), 3.0 * k4 * 1.4, "vis")
                s.circle(*T(lx + g.bolt_dx, sgn * yy), 2.5 * k4 * 1.4, "thin")
    s.dim_h(*T(-L / 2, -Wd / 2), *T(L / 2, -Wd / 2), T(0, -Wd / 2)[1] - 5, L)
    s.dim_v(*T(L / 2, -Wd / 2), *T(L / 2, Wd / 2), T(L / 2, 0)[0] + 5, Wd)
    lx0 = g.fx[0] - g.xc + g.bolt_dx
    s.dim_v(*T(lx0, -g.bolt_y[-1]), *T(lx0, g.bolt_y[-1]), T(-L / 2, 0)[0] - 5, 2 * g.bolt_y[-1])
    s.dim_v(*T(lx0, -g.bolt_y[0]), *T(lx0, g.bolt_y[0]), T(-L / 2, 0)[0] - 11, 2 * g.bolt_y[0])
    s.dim_h(*T(lx0, g.bolt_y[-1]), *T(g.fx[1] - g.xc + g.bolt_dx, g.bolt_y[-1]), T(0, Wd / 2)[1] + 5,
            g.fx[1] - g.fx[0], f"{g.fx[1] - g.fx[0]:.0f} bolt rows")
    s.text(T(0, 0)[0], T(0, Wd / 2)[1] + 11, f"{g.foot_t:.0f} mm 6061. Frames (hidden) at "
           f"{g.fx[0] - g.xc:+.0f} / {g.fx[1] - g.xc:+.0f}. {4 * len(g.bolt_y)}x M6 tapped through at "
           f"frame + {g.bolt_dx:.0f}", 1.9)
    s.text(T(0, 0)[0], T(0, Wd / 2)[1] + 14.3, "(bolts come up from inside the lid); 2x 5.5 per angle bracket. It sits "
           "on a flat landing in the lid deck", 1.9)
    s.view_title(T(0, 0)[0], T(0, Wd / 2)[1] + 20, "FOOT PLATE (PLAN, 2 req)", "1:4")

    ctrl = [(mm(a), mm(b)) for a, b in g.boat.arm_ctrl(g.hull)]
    s.table(118, 102, ["Arch centreline (stbd arm)", "y", "z"], [
        ["hub span, straight", f"0 to {ctrl[0][0]:.0f}", f"{ctrl[0][1]:.0f}"],
        ["Bezier P0 (arm root)", f"{ctrl[0][0]:.0f}", f"{ctrl[0][1]:.0f}"],
        ["Bezier P1", f"{ctrl[1][0]:.0f}", f"{ctrl[1][1]:.0f}"],
        ["Bezier P2", f"{ctrl[2][0]:.0f}", f"{ctrl[2][1]:.0f}"],
        ["Bezier P3 (foot)", f"{ctrl[3][0]:.0f}", f"{ctrl[3][1]:.1f}"],
    ], [46, 20, 16], 2.0, 4.0)
    s.lines_of_text(118, 129, ["Port arm is the mirror image.", "Tangent horizontal at P0, vertical at P3."],
                    size=1.9, lead=3.0)

    # hub garage, 1:10: plan, side and section from astern
    k10 = 0.1
    Xh, Yh = 246.0, 124.0

    def HP(x, y):
        return Xh + (x - g.hub_x) * k10, Yh + y * k10

    s.poly([HP(g.hub_x + px, py) for px, py in superellipse(g.hub_ax, g.hub_ay, g.boat.hub_e)], "orange", closed=True)
    for fxx in g.fx:
        s.line(*HP(fxx, -g.hub_ay), *HP(fxx, g.hub_ay), "hid")
    garage_plan(s, g, HP)
    s.circle(*HP(g.hub_x, 0), 1.1, "vis")
    for wy in (-g.whip_y, g.whip_y):
        s.circle(*HP(g.hub_x, wy), 0.8, "vis")
    s.circle(*HP(g.hub_x - 100, -70), 1.4, "vis")
    bar_x = g.hub_x + g.hub_ax - 60
    s.rect(*HP(bar_x - 16, -180), *HP(bar_x + 16, 180), "vis")
    ox0, ox1 = g.open_x - g.open_len / 2, g.open_x + g.open_len / 2
    s.dim_h(*HP(ox0, g.open_w / 2), *HP(ox1, g.open_w / 2), HP(0, g.hub_ay)[1] + 5, g.open_len,
            f"{g.open_len:.0f} opening")
    s.dim_v(*HP(ox1, -g.open_w / 2), *HP(ox1, g.open_w / 2), HP(g.hub_x + g.hub_ax, 0)[0] + 4, g.open_w,
            f"{g.open_w:.0f}")
    s.dim_h(*HP(g.hub_x, -g.hub_ay), *HP(g.open_x, -g.hub_ay), HP(0, -g.hub_ay)[1] - 4, g.open_x - g.hub_x,
            f"+{g.open_x - g.hub_x:.0f}")
    s.text(HP(g.hub_x, 0)[0], HP(0, -g.hub_ay)[1] - 9, "hub CL to opening CL; all dashed = inside", 1.7)

    Xs, Zs = 322.0, 132.0

    def HS(x, z):
        return Xs + (x - g.hub_x) * k10, Zs - (z - g.hub_z[0]) * k10

    zc = g.hub_side()
    s.poly([HS(g.hub_x - g.hub_ax * sc, z) for sc, z in zc] + [HS(g.hub_x + g.hub_ax * sc, z) for sc, z in reversed(zc)],
           "orange", closed=True)
    for fxx in g.fx:
        s.rect(*HS(fxx - g.frame_t / 2, g.frame_top - g.frame_h), *HS(fxx + g.frame_t / 2, g.frame_top), "hid")
    garage_side(s, g, HS)
    s.line(*HS(g.hub_x, g.hub_z[2]), *HS(g.hub_x, g.hub_z[2] + 30), "vis")
    s.line(*HS(g.hub_x - g.hub_ax - 15, g.dwl), *HS(g.hub_x + g.hub_ax + 15, g.dwl), "wl")
    s.text(*HS(g.hub_x - g.hub_ax - 17, g.dwl + 4), f"DWL {g.dwl:.0f}", 1.6, "end", cls="blue")
    xr = HS(g.hub_x + g.hub_ax, 0)[0] + 3
    marks = [(g.hub_z[2], f"{g.hub_z[2]:.0f} top"), (g.sheave_z, f"{g.sheave_z:.0f} sheave"),
             (g.stow_z[1], f"{g.stow_z[1]:.0f}"), (g.frame_top, f"{g.frame_top:.0f} frames"),
             (g.hub_z[0], f"{g.hub_z[0]:.0f} floor"), (g.stow_z[0], f"{g.stow_z[0]:.0f} stowed bottom")]
    ys = []
    for z, lab in marks:
        yy = HS(0, z)[1]
        y_lab = max([yy] + [v + 2.6 for v in ys])
        ys.append(y_lab)
        s.line(*HS(g.hub_x + g.hub_ax * 0.9, z), xr + 4, yy, "dimx")
        s.line(xr + 4, yy, xr + 7, y_lab, "dimx")
        s.text(xr + 7.5, y_lab + 0.7, lab, 1.7, "start")
    s.dim_v(*HS(g.hub_x - g.hub_ax, g.dwl), *HS(g.hub_x - g.hub_ax, g.stow_z[0]), HS(g.hub_x - g.hub_ax, 0)[0] - 4,
            g.stow_z[0] - g.dwl, f"{g.stow_z[0] - g.dwl:.0f}")

    Xa, Za = 398.0, 132.0

    def HA(y, z):
        return Xa + y * k10, Za - (z - g.hub_z[0]) * k10

    s.poly([HA(-g.hub_ay * sc, z) for sc, z in zc] + [HA(g.hub_ay * sc, z) for sc, z in reversed(zc)], "orange",
           closed=True)
    garage_aft(s, g, HA)
    hub = [(y, z) for y, z in g.frame if abs(y) <= g.hub_ay * 0.95]
    s.poly([HA(y, z) for y, z in hub], "hid")
    s.dim_h(*HA(-g.open_w / 2, g.hub_z[0]), *HA(g.open_w / 2, g.hub_z[0]), HA(0, g.stow_z[0])[1] + 4, g.open_w,
            f"{g.open_w:.0f}")
    s.text(Xa, HA(0, g.hub_z[2])[1] - 3, "from astern", 1.7)

    s.view_title(300.0, 158.0, "HUB GARAGE: WINCH, POD, VAN DORN (PLAN, SIDE, FROM ASTERN)", "1:10")
    s.lines_of_text(226.0, 166.0, [
        f"Pod {g.pod_env[0]:.0f} x {g.pod_env[1]:.0f} x {g.pod_env[2]:.0f} (port) and a {g.boat.sampler_l:g} L horizontal "
        f"Van Dorn, 5 in PVC, {g.sampler_d:.0f} x {g.sampler_len:.0f} (stbd), side by side under the sheave:",
        f"margins {g.stow_fit[0]:+.0f} / {g.stow_fit[1]:+.0f} mm through the opening. Winch, pod and sampler are "
        "placeholders until they're sized; the winch",
        "sits on a bracket off the aft frame, the sheave over the opening on the garage holes in the frames.",
    ], size=1.75, lead=2.6)

    # rib bond, 2:1: the lid skirt cut at mid-depth, seen from above (fwd to the right, inboard up)
    k3 = 2.0
    Xj, Yj = 55.0, 207.0

    def J(u, v):
        return Xj + u * k3, Yj - v * k3

    rt, leg = mm(g.lid.rib_t), mm(g.lid.rib_fillet)
    s.rect(*J(-16, -g.wall), *J(16, 0), "cut")
    s.rect(*J(-16, -g.wall - 0.35), *J(16, -g.wall), "glass")
    s.rect(*J(-rt / 2, 0), *J(rt / 2, 16), "cut2")
    s.poly([J(-rt / 2 - 1.2, 16), J(-1, 16.6), J(1, 15.4), J(rt / 2 + 1.2, 16)], "thin")  # break line
    for sgn in (-1, 1):
        f0 = sgn * (rt / 2 + leg)
        arc = [(f0 - sgn * leg * math.sin(math.radians(t)), leg - leg * math.cos(math.radians(t))) for t in range(0, 91, 10)]
        s.poly([J(sgn * rt / 2, 0)] + [J(u, v) for u, v in arc], "glass", closed=True)
    s.text(*J(-12, -7.5), "OUTSIDE", 1.8)
    s.text(*J(-11, 13), "INSIDE", 1.8)
    s.leader(*J(0, 12), J(19, 0)[0], J(0, 15)[1], f"RIB {rt:.0f}, PLA printed flat", size=1.8)
    s.leader(*J(rt / 2 + 2.5, 2.5), J(19, 0)[0], J(0, 8)[1], f"thickened epoxy, {leg:.0f} legs, both faces,", size=1.8)
    s.text(J(19, 0)[0] + 1, J(0, 8)[1] + 3.3, "along the deck and both skirts", 1.8, "start")
    s.leader(*J(13, -1.2), J(19, 0)[0], J(0, -3)[1], f"lid skirt {g.wall:.1f} + glass outside", size=1.8)
    s.dim_h(*J(-rt / 2, 16), *J(rt / 2, 16), J(0, 16)[1] - 3, rt)
    s.dim_h(*J(rt / 2, 0), *J(rt / 2 + leg, 0), J(0, -g.wall)[1] + 9, leg)
    s.view_title(Xj + 10, 232.0, "RIB BOND (LID SKIRT CUT AT MID-DEPTH, FROM ABOVE)", "2:1")
    s.lines_of_text(17.0, 240.5, [
        "Fit each rib with the foot bolted up through the deck and the rib bosses: the foot is the jig, so the",
        "holes line up. Sand the PLA, fillet both faces along the deck and both skirts, then coat the inside.",
    ], size=1.75, lead=2.6)

    # tub ring frame, 2:1: the tub wall cut along the hull, inside up, fwd to the right
    Xr2, Yr2 = 166.0, 205.0

    def RF(u, v):
        return Xr2 + u * k3, Yr2 - v * k3

    dr, tr = RING
    s.rect(*RF(-18, -g.wall), *RF(8, 0), "cut")
    s.rect(*RF(-18, -g.wall - 0.35), *RF(8, -g.wall), "glass")
    s.poly([RF(0, 0), RF(0, dr), RF(-tr, dr), RF(-tr - dr, 0)], "cut", closed=True)
    s.add(f'<line class="dim" x1="{RF(-16, 12)[0]:.2f}" y1="{RF(0, 12)[1]:.2f}" x2="{RF(-4, 12)[0]:.2f}" '
          f'y2="{RF(0, 12)[1]:.2f}" marker-end="url(#a)"/>')
    s.text(RF(-10, 12)[0], RF(0, 12)[1] - 1.2, "print grows fwd", 1.7)
    s.leader(*RF(-tr - dr / 2 + 0.6, dr / 2 - 0.6), RF(8, 0)[0] + 9, RF(0, 10)[1], "aft face 45°:", size=1.8)
    s.text(RF(8, 0)[0] + 10, RF(0, 10)[1] + 3.3, "prints without", 1.8, "start")
    s.text(RF(8, 0)[0] + 10, RF(0, 10)[1] + 5.8, "supports", 1.8, "start")
    s.dim_v(*RF(0, 0), *RF(0, dr), RF(0, 0)[0] + 4, dr, f"{dr:.0f}")
    s.dim_h(*RF(-tr, dr), *RF(0, dr), RF(0, dr)[1] - 3, tr, f"{tr:.0f}")
    s.text(*RF(-6, -6.5), f"tub wall {g.wall:.1f}", 1.8)
    s.view_title(Xr2 - 4, 232.0, "TUB RING FRAME (SECTION ALONG THE HULL)", "2:1")
    s.lines_of_text(140.0, 240.5, [
        f"At x {' / '.join(f'{v:.0f}' for v in g.rings)}, all the way round inside the tub,",
        f"up to the joint plane. {LIMBER[0]:.0f} x {LIMBER[1]:.0f} limber notch at the keel.",
    ], size=1.75, lead=2.6)

    s.text(222, 179, "HARDWARE (whole boat)", 2.8, "start", bold=True)
    s.table(222, 182, ["Qty", "Item"], [
        ["2", "Arch frame plate, 1/4 in 6061-T6, laser / waterjet cut (DXF)"],
        ["2", f"Foot plate, {g.foot_t:.0f} mm 6061, {g.foot_len:.0f} x {g.foot_w:.0f}, {4 * len(g.bolt_y)}x M6 tapped"],
        ["4", "Angle bracket 25 x 25 x 3 Al, 40 long (frame to foot)"],
        [f"{8 * len(g.bolt_y)}", f"M6 x {BOLT_L:.0f} A4 socket cap + M6 bonded seal washer (feet, from inside)"],
        ["2", f"EPDM pad {g.pad_t:.1f} mm, {g.foot_len:.0f} x {g.foot_w:.0f} (under each foot)"],
        [f"{2 * g.n_screws}", f"M4 x 12 A4 pan head + washer, and M4 x {INSERT[1]:.1f} brass heat-set insert (rails)"],
        ["2", f"{mm(g.lid.gasket_d):.0f} mm EPDM / silicone cord, {g.rail_len:.2f} m (one loop per tub)"],
        ["1", "Hub cowl, 2 arm fairings, 2 foot shoes (printed PLA, painted light)"],
        ["4", f"Lid rib, {mm(g.lid.rib_t):.0f} mm PLA printed flat, 100 % round the bosses; 2 bonded into each lid"],
        ["1", "Garage: winch bracket off the aft frame, sheave bracket, printed docking cone"],
        ["2", "Belt outdrive, complete (sheets 5, 6)"],
        ["2", "M12 IP68 membrane vent (one per lid)"],
        ["4", f"IP68 bulkhead connector in the lids: motor (x {g.conn_x[0]:.0f}) and bridge (x {g.conn_x[1]:.0f}), per hull"],
        ["2", "Leak probe at each tub's keel low point (carrier J8 port / J9 stbd)"],
    ], [12, 108], 1.95, 3.3)

    lc_worst = max(g.lcs, key=lambda lc: lc.moment)
    zsec = g.boat.frame_t * g.boat.frame_h**2 / 6
    bolt_sf, rib_sf, bond_sf, rail_sf = (cap / load for _, _, load, cap, _ in g.checks)
    s.lines_of_text(347, 182, [
        "LOAD PATH",
        "Each frame is a portal fixed at its feet.",
        f"Worst case: {lc_worst.name.split(' (')[0].split(' ', 1)[1]}",
        f"{lc_worst.moment:.0f} N m per frame -> {lc_worst.moment / zsec / 1e6:.0f} MPa,",
        f"SF {276e6 / (lc_worst.moment / zsec):.1f} on 6061-T6 yield.",
        f"Foot: pivots on its far edge; the {4 * len(g.bolt_y)}",
        f"M6 in the rib bosses hold it: SF {bolt_sf:.1f}.",
        f"Lid rib carries it to the rail: SF {rib_sf:.1f};",
        f"its bonded ends: SF {bond_sf:.1f}.",
        f"Rail: 3 M4 inserts per frame: SF {rail_sf:.1f}.",
        "Nothing goes through a tub: all",
        "hardware bolts to the lids.",
        "Details: docs/hull_and_crossbeam_sizing.md",
    ], size=1.9, lead=3.1, bold_first=True)
    return s


# ---- sheet 4: rail joint and the hull interior -------------------------------------------------


def rail_joint(s: Sheet, g: Geo, X0: float, Y0: float, k: float) -> None:
    """Gunwale (rail) joint through a screw, 4:1. y from the hull side (outboard +), z from the
    joint plane (up +); paper origin (X0, Y0)."""
    lid = g.lid
    fw, ft, lt, ld, wall = g.fw, g.ft, g.lip_t, g.lip_drop, g.wall
    gw, gd = (mm(v) for v in lid.groove)
    gy, sy = mm(lid.groove_y), mm(lid.screw_y)
    sp_drop, sp_t = (mm(v) for v in lid.spigot)
    rd = mm(g.hull.deck_fillet(g.xc / 1000))
    zd = g.depth - rd - g.zj  # deck-edge radius starts here
    top, bot = 14.0, -13.0

    def A(y, z):
        return X0 + y * k, Y0 - z * k

    bw = INSERT_BOSS[0] / 2
    tub = [(-wall, bot), (-wall, 0), (gy - gw / 2, 0), (gy - gw / 2, -gd), (gy + gw / 2, -gd), (gy + gw / 2, 0),
           (fw - CLEAR, 0), (fw - CLEAR, -INSERT_BOSS[1]), (sy - bw, -INSERT_BOSS[1]), (sy - bw, -ft), (0, -ft), (0, bot)]
    s.poly([A(y, z) for y, z in tub], "cut2", closed=True)
    sp_out = -wall - CLEAR
    arc_o = [(-rd + math.sqrt(rd * rd - (z - zd) ** 2), z) for z in [zd + (top - zd) * i / 6 for i in range(7)]]
    arc_i = [(-rd + math.sqrt((rd - wall) ** 2 - (z - zd) ** 2), z) for z in [top - (top - zd) * i / 6 for i in range(7)]]
    lidp = ([(sp_out - sp_t, -sp_drop), (sp_out, -sp_drop), (sp_out, 0), (fw, 0), (fw, -ld), (fw + lt, -ld),
             (fw + lt, ft), (0, ft), (0, zd)] + arc_o + arc_i + [(-wall, 3.0), (sp_out - sp_t, 3.0)])
    s.poly([A(y, z) for y, z in lidp], "cut", closed=True)
    s.rect(*A(sy - M4_HOLE / 2, 0), *A(sy + M4_HOLE / 2, ft), "void")
    s.rect(*A(sy - INSERT[0] / 2, -INSERT[1]), *A(sy + INSERT[0] / 2, 0), "metal")
    s.rect(*A(sy - 2, ft + M4_WASHER[1] - 12), *A(sy + 2, ft + M4_WASHER[1]), "metal")
    s.rect(*A(sy - M4_WASHER[0] / 2, ft), *A(sy + M4_WASHER[0] / 2, ft + M4_WASHER[1]), "metal")
    s.rect(*A(sy - M4_HEAD[0] / 2, ft + M4_WASHER[1]), *A(sy + M4_HEAD[0] / 2, ft + M4_WASHER[1] + M4_HEAD[1]), "metal")
    s.poly([A(y, z) for y, z in ellipse(gy, -gd / 2, gw / 2 * 0.78, gd / 2)], "rubber", closed=True)
    for z in (top, bot):  # break lines
        s.poly([A(-wall - 3.2, z), A(-wall - 1.6, z + 0.6), A(-1.0, z - 0.6), A(1.5, z)], "thin")
    s.line(*A(0, bot - 2), *A(0, top + 2), "ctr")
    s.line(*A(-9, 0), *A(fw + lt + 4, 0), "lidj")
    s.text(*A(-9.3, 0.5), f"joint plane z {g.zj:.0f}", 1.9, "end", cls="purple")
    s.text(*A(0.4, top + 2.4), "hull side", 1.8, "start")
    s.text(*A(-7, 8), "LID", 2.6, bold=True)
    s.text(*A(-7, -9), "TUB", 2.6, bold=True)
    s.text(*A(-8.5, -3.5), "INSIDE", 1.8)
    s.text(*A(fw + lt + 2.5, -11), "OUTSIDE", 1.8)
    # dimensions
    yd = A(0, bot)[1]
    s.dim_h(*A(0, -ft), *A(sy, -INSERT_BOSS[1]), yd + 5, sy, f"{sy:.1f} screws")
    s.dim_h(*A(0, -ft), *A(fw, -ld), yd + 11, fw)
    s.dim_h(*A(fw, -ld), *A(fw + lt, -ld), yd + 11, lt, f"{lt:.1f}")
    s.dim_h(*A(0, -ft), *A(fw + lt, -ld), yd + 17, g.rail, f"{g.rail:.1f} rail")
    xr = A(fw + lt, 0)[0] + 5
    s.dim_v(*A(fw + lt, 0), *A(fw + lt, ft), xr, ft, f"{ft:.0f}")
    s.dim_v(*A(fw - CLEAR, -ft), *A(fw - CLEAR, 0), xr + 7, ft, f"{ft:.0f}")
    s.dim_v(*A(fw + lt, -ld), *A(fw + lt, 0), xr + 14, ld, f"{ld:.0f}")
    s.dim_v(*A(fw - CLEAR, -INSERT_BOSS[1]), *A(fw - CLEAR, 0), xr + 21, INSERT_BOSS[1], f"{INSERT_BOSS[1]:.0f}")
    xl = A(sp_out - sp_t, 0)[0] - 4
    s.dim_v(*A(sp_out - sp_t, -sp_drop), *A(sp_out - sp_t, 0), xl, sp_drop, f"{sp_drop:.0f}")
    s.dim_v(*A(gy, -gd), *A(gy, 0), A(gy, 0)[0], gd, f"{gd:.1f}")
    lx = xr + 27
    s.leader(*A(sy + M4_HEAD[0] / 2, ft + 3), lx, A(0, ft + 9)[1], "M4 x 12 A4 pan head + washer", size=1.9)
    s.leader(*A(sy + 2.8, -4), lx, A(0, -3)[1], f"M4 x {INSERT[1]:.1f} brass heat-set insert", size=1.9)
    s.leader(*A(fw - CLEAR - 1, -INSERT_BOSS[1] + 1), lx, A(0, -9.5)[1],
             f"{INSERT_BOSS[0]:.0f} dia boss under each screw, flat outboard", size=1.9)
    s.leader(*A(fw + lt - 1, -ld + 1), lx, A(0, -14)[1], f"drip lip {lt:.1f}, {CLEAR:.1f} clear of the tub flange",
             size=1.9)
    s.leader(*A(gy + 1, -gd / 2), lx, A(0, 2.5)[1],
             f"{mm(lid.gasket_d):.0f} mm cord, {gw:.0f} x {gd:.1f} groove centred {gy:.0f} out", size=1.9)
    s.leader(*A(fw - 1.5, 0.2), lx, A(0, ft + 3.5)[1], "flanges touch: the groove sets 27 % squeeze", size=1.9)
    s.leader(*A(sp_out - sp_t / 2, -sp_drop + 1), A(-12, 0)[0], A(0, -7)[1],
             f"spigot {sp_t:.0f} x {sp_drop:.0f}, {CLEAR:.1f} clear", "end", 1.9)
    s.leader(*A(-wall / 2, top - 2), A(-12, 0)[0], A(0, top - 1)[1], f"lid skirt {wall:.0f}", "end", 1.9)
    s.leader(*A(-wall / 2, bot + 2), A(-12, 0)[0], A(0, bot + 3)[1], f"tub wall {wall:.0f}", "end", 1.9)


def leg_section(s: Sheet, g: Geo, X: float, Y: float, k: float) -> None:
    """Section A-A through the leg, looking down; LE to the right (fwd), stbd down."""
    xm = (g.leg_x[0] + g.leg_x[1]) / 2
    chord = g.leg_x[1] - g.leg_x[0]

    def S(x, y):
        return X + (x - xm) * k, Y + y * k

    half = naca_half(g.leg_t / chord, chord)
    upper = [(g.leg_x[1] - u, -t) for u, t in half]
    lower = [(g.leg_x[1] - u, t) for u, t in reversed(half)]
    s.poly([S(x, y) for x, y in upper + lower], "cut", closed=True)
    cav = (g.pd / 2 + 1.2 + 1.5)
    s.rect(*S(g.belt_x - 6, -cav), *S(g.belt_x + 6, cav), "void")
    for sgn in (-1, 1):
        s.rect(*S(g.belt_x - g.belt_w / 2, sgn * g.pd / 2 - 1.2), *S(g.belt_x + g.belt_w / 2, sgn * g.pd / 2 + 1.2),
               "rubber")
    s.line(*S(g.leg_x[0] - 4, 0), *S(g.leg_x[1] + 4, 0), "ctr")
    y_lo = S(0, g.leg_t / 2)[1]
    s.dim_h(*S(g.leg_x[0], 0), *S(g.leg_x[1], 0), y_lo + 8, chord, f"{chord:.0f} chord")
    s.dim_h(*S(g.belt_x, cav), *S(g.leg_x[1], 0), y_lo + 3.5, g.leg_x[1] - g.belt_x,
            f"{g.leg_x[1] - g.belt_x:.0f} to the belt")
    x_t = g.leg_x[1] - 0.30 * chord
    s.dim_v(*S(x_t, -g.leg_t / 2), *S(x_t, g.leg_t / 2), S(g.leg_x[1], 0)[0] + 6, g.leg_t, f"{g.leg_t:.0f}")
    s.dim_v(*S(g.belt_x + 4, -g.pd / 2), *S(g.belt_x + 4, g.pd / 2), S(g.belt_x, 0)[0] + 18, g.pd,
            f"{g.pd:.1f} PD")
    s.dim_h(*S(g.belt_x - 6, -cav), *S(g.belt_x + 6, -cav), S(0, -g.leg_t / 2)[1] - 4, 12, "12")
    s.leader(*S(g.belt_x - 3, g.pd / 2 + 0.8), S(g.leg_x[0], 0)[0] + 6, y_lo + 14,
             f"belt runs, HTD 3M-{g.belt_w:.0f} (back to back)", size=1.9)
    s.leader(*S(g.leg_x[0] + 20, 0), S(g.leg_x[0], 0)[0] - 2, S(0, -g.leg_t / 2)[1] - 6,
             "halves split on the chord plane, M3 screws", "start", 1.9)
    s.text(*S(g.leg_x[1] + 3, -g.leg_t / 2 - 2), "LE / FWD", 1.9, "start")
    s.text(*S(g.leg_x[0] - 1.5, 1.2), "TE", 1.9, "end")
    s.text(*S(g.belt_x, -3), "free-", 1.8)
    s.text(*S(g.belt_x, 3.5), "flooding", 1.8)


def sheet_lid_hull(g: Geo) -> Sheet:
    s = Sheet(4, "Hull lid joint (rail) and what goes inside each hull", "as noted")
    rail_joint(s, g, 90.0, 80.0, 4.0)
    s.view_title(90.0, 160.0, "RAIL: LID OVER THE GUNWALE (SECTION THROUGH A SCREW)", "4:1")
    h = g.hull

    # plan of each tub, 1:6, packs and electronics filled
    k = 1 / 6
    X0 = 226.0
    for row, (sgn, name) in enumerate(((-1, "PORT TUB"), (1, "STBD TUB"))):
        Yc = 40.0 + 58.0 * row

        def P(x, y, Yc=Yc):
            return X0 + x * k, Yc + y * k

        s.poly([P(x, y) for x, y in g.rail_outline(10)], "thin", closed=True)
        s.poly([P(x, y) for x, y in g.plan_outline(10)], "vis", closed=True)
        s.line(*P(-30, 0), *P(g.loa + 20, 0), "ctr")
        ring_lines(s, g, P, 0.0, "thin")
        hull_interior_plan(s, g, P, 0.0, sgn, style="fill")
        s.circle(*P(g.vent_x, 0), 6 * k, "thin")
        s.text(*P(-40, 4), name, 2.3, "end", bold=True)
        for nm, _, x0, x1, y0, y1, _, _ in interior_boxes(g, sgn):
            if nm == "heat plate":
                continue
            s.leader(*P((x0 + x1) / 2, y1 if sgn > 0 or nm != "VESC" else y0),
                     P((x0 + x1) / 2 + 40, 0)[0], P(0, (hb(h, x0) + 30) * (1 if nm != "electronics pack" else -1.33))[1],
                     nm, size=1.8)
        s.leader(*P(g.leak_x, 4 * sgn), P(g.leak_x + 60, 0)[0],
                 P(0, (hb(h, g.leak_x) + 30) * (1 if sgn < 0 else -1.4))[1], f"leak probe ({'J8' if sgn < 0 else 'J9'})",
                 size=1.8)
        if row == 0:
            s.leader(*P(g.rings[-1], hb(h, g.rings[-1]) - 8), P(g.rings[-1] + 45, 0)[0], P(0, hb(h, g.rings[-1]) + 30)[1],
                     "ring frames", size=1.8)
            for cx, lab in zip(g.conn_x, ("motor", "bridge")):
                s.leader(*P(cx, -6), P(cx + 30, 0)[0], P(0, -hb(h, cx) - 42)[1], f"lid connector: {lab}", size=1.8)
    yb = 40.0 + 58.0 + (g.beam / 2 + g.rail) * k + 5

    def PB(x, y):
        return X0 + x * k, 98.0 + y * k

    s.dim_h(*PB(0, g.beam / 2), *PB(g.vesc_x, g.beam / 2), yb, g.vesc_x)
    s.dim_h(*PB(0, g.beam / 2), *PB(g.elec_x, g.beam / 2), yb + 5, g.elec_x)
    s.dim_h(*PB(0, g.beam / 2), *PB(g.pack_x, g.beam / 2), yb + 10, g.pack_x, f"{g.pack_x:.0f} packs")
    s.dim_h(*PB(0, g.beam / 2), *PB(g.leak_x, g.beam / 2), yb + 15, g.leak_x, f"{g.leak_x:.0f} probe")
    s.view_title(X0 + g.loa * k / 2, yb + 23, "INSIDE THE TUBS (PLAN, PROPOSED)", "1:6")

    # section through each tub at the packs, 1:4, looking forward
    kb = 0.25
    for col, (sgn, name) in enumerate(((-1, "port"), (1, "stbd"))):
        Xc, Yb = 262.0 + 82.0 * col, 228.0

        def B(y, z, Xc=Xc, Yb=Yb):
            return Xc + y * kb, Yb - z * kb

        half = [(mm(y), mm(z)) for y, z in section_points(h, g.pack_x / 1000)]
        ring = half + [(-y, z) for y, z in reversed(half[1:-1])]
        s.poly([B(y, z) for y, z in ring], "vis", closed=True)
        inner = offset_polyline(ring + ring[:1], g.wall)
        s.poly([B(y, z) for y, z in inner], "thin")
        s.line(*B(-g.beam / 2 - g.rail, g.zj), *B(g.beam / 2 + g.rail, g.zj), "lidj")
        s.line(*B(-g.beam / 2 - 15, g.dwl), *B(g.beam / 2 + 15, g.dwl), "wl")
        s.line(*B(0, -8), *B(0, g.depth + 8), "ctr")
        for nm, cls, x0, x1, y0, y1, z0, z1 in interior_boxes(g, sgn):
            if x0 <= g.pack_x <= x1:
                s.rect(*B(y0, z0), *B(y1, z1), cls)
        kx = keel(h, g.pack_x)
        bed = [(-HEAT_PLATE[1] / 2, 12.0), (-HEAT_PLATE[1] / 2, kx + HEAT_PLATE[1] / 2 * h.tb + 1),
               (0, kx + 2), (HEAT_PLATE[1] / 2, kx + HEAT_PLATE[1] / 2 * h.tb + 1), (HEAT_PLATE[1] / 2, 12.0)]
        s.poly([B(y, z) for y, z in bed], "glass", closed=True)
        s.text(Xc, B(0, g.depth)[1] - 3, f"{name} tub at x {g.pack_x:.0f}", 1.9)
    s.lines_of_text(226.0, 155.0, [
        f"SECTIONS AT x {g.pack_x:.0f}, looking fwd, 1:4: the heat plate is bedded on thickened epoxy (blue) on the",
        "V bottom, the packs sit on the plate. DWL dashed blue, lid joint purple.",
    ], size=1.8, lead=2.7)

    s.lines_of_text(20.0, 174.0, [
        "WIRING (everything enters a hull through its lid connectors)",
        "- 12S: drive pack (port) -> port VESC; to the stbd VESC across the bridge (port arm, hub, stbd arm).",
        "- CAN: carrier (stbd) -> stbd VESC -> across the bridge -> port VESC (node IDs 1, 2).",
        "- Electronics pack (stbd) -> carrier -> Pi 5 on the carrier's 5 V. Never also power the Pi from USB-C.",
        "- Winch pack (stbd) -> carrier's fail-safe winch kill -> up the stbd arm -> winch in the hub garage.",
        "- Pod tether (RS-485 + pack voltage) from carrier J2 -> up the stbd arm -> the winch's slip ring.",
        "- Mast (GNSS, LTE, WiFi), stereo cameras, e-stop -> down the stbd arm. Leak probes: J8 port, J9 stbd.",
        f"- Motor wires: outdrive -> lid connector at x {g.conn_x[0]:.0f} -> that hull's VESC.",
        "",
        "HEAT AND WATER",
        "- VESCs and packs sit on 6061 plates bedded on the hull bottom, so the water takes the heat; PLA",
        "  softens ~55 C. Log the hull air temperature (the carrier's SHT45s).",
        f"- Limber notches in the ring frames let a leak run along the keel to the probe at x {g.leak_x:.0f}, fwd of the packs.",
        "- Lifting a lid: unscrew the rail, raise it ~100 mm on the connector slack, unplug inside, lift away.",
    ], size=1.95, lead=3.15, bold_first=True)
    return s


# ---- sheets 5 and 6: the belt outdrive, drawn for CAD ----------------------------------------


def ordinates_x(s: Sheet, Q, items, yb: float, size: float = 1.8) -> None:
    """Ordinate dimensions along x: items (x, z_from, label); extension lines down to paper yb."""
    pts = sorted((Q(x, z)[0], Q(x, z)[1], lab) for x, z, lab in items)
    s.line(pts[0][0] - 2, yb, pts[-1][0] + 2, yb, "dimx")
    last = -1e9
    for px_, py_, lab in pts:
        s.line(px_, py_ + 1.0, px_, yb, "dimx")
        xl = max(px_, last + 2.9)
        last = xl
        s.line(px_, yb, xl, yb + 2.2, "dimx")
        s.text(xl + 0.65, yb + 2.8, lab, size, "end", rot=-90)


def ordinates_z(s: Sheet, Q, items, xb: float, size: float = 1.8) -> None:
    """Ordinate dimensions up z: items (z, x_from, label); extension lines right to paper xb."""
    pts = sorted(((Q(x, z)[1], Q(x, z)[0], lab) for z, x, lab in items), reverse=True)
    last = 1e9
    for py_, px_, lab in pts:
        s.line(px_ + 1.0, py_, xb, py_, "dimx")
        yl = min(py_, last - 2.7)
        last = yl
        s.line(xb, py_, xb + 2.2, yl, "dimx")
        s.text(xb + 2.8, yl + 0.65, lab, size, "start")


DRIVE_PARTS = [  # (no., name) - the balloons on sheet 5 and the parts on sheet 6
    (1, "Mount"), (2, "Motor plate"), (3, "Motor cover"), (4, "Leg + pod halves"), (5, "Prop shaft"),
    (6, "Thrust pad"), (7, "Motor"), (8, "Pulleys x2"), (9, "Belt"), (10, "Bearings x2"), (11, "Shaft collar"),
    (12, "Prop, washer, nylock"), (13, "Lid connector"),
]


def sheet_drive_assembly(g: Geo) -> Sheet:
    s = Sheet(5, "Belt outdrive (fixed), assembled: side, from astern, from above, key points (for CAD)", "1:2")
    k = 0.5
    h = g.hull
    X0, Y0 = 22.0, 196.0
    xmin = -176.0

    def Q(x, z):
        return X0 + (x - xmin) * k, Y0 - z * k

    # the aft end of the hull for context: transom, lid deck, rail, keel
    xe = 104.0
    s.poly([Q(xe, g.depth), Q(0, g.depth), Q(0, keel(h, 0)), Q(xe, keel(h, xe))], "vis")
    s.poly([Q(xe, g.depth + 5), Q(xe - 3, g.depth - 40), Q(xe + 3, g.depth - 120), Q(xe, keel(h, xe) - 5)], "thin")
    s.rect(*Q(-g.rail, g.rail_z[0]), *Q(xe, g.rail_z[1]), "vis")
    s.line(*Q(-176, g.dwl), *Q(xe + 2, g.dwl), "wl")
    s.text(*Q(xe + 4, g.dwl - 2), f"DWL {g.dwl:.0f}", 1.9, "start", cls="blue")
    s.line(*Q(-176, 0), *Q(xe + 2, 0), "ctr")
    s.text(*Q(xe + 4, -2), "BL", 1.9, "start")
    s.rect(*Q(g.conn_x[0] - 8, g.depth), *Q(g.conn_x[0] + 8, g.depth + 14), "metal")  # motor-wire connector
    drive_side(s, g, Q, k, detail=True)
    # centre lines and the section mark
    s.line(*Q(-176, g.prop_z), *Q(-8, g.prop_z), "ctr")
    s.line(*Q(g.belt_x - 18, g.motor_z), *Q(g.plate_x[1] + 10, g.motor_z), "ctr")
    s.line(*Q(g.belt_x, g.prop_z - 18), *Q(g.belt_x, g.motor_z + 18), "ctr")
    for xa in (g.leg_x[0] - 14, g.leg_x[1] + 6):  # cutting plane A-A (sheet 6)
        s.line(*Q(xa, SECTION_Z), *Q(xa + 4, SECTION_Z), "vis")
    s.text(*Q(g.leg_x[0] - 18, SECTION_Z - 2), "A", 2.4, bold=True)
    s.text(*Q(g.leg_x[1] + 12, SECTION_Z - 2), "A", 2.4, bold=True)
    s.text(*Q(g.belt_x + 3, 110), f"{g.teeth} T belt", 1.8, "start")
    # balloons
    bx = -190.0
    for no, (x, z), (lx, lz) in [
            (1, (50, g.depth + 6), (60, 300)), (2, (g.plate_x[0] + 2, 325), (10, 362)),
            (3, (g.cover_x[0] + 10, g.cover_top - 2), (-110, 362)), (4, (g.leg_x[0] + 8, 120), (bx, 140)),
            (5, (g.shaft_x[0] + 2, g.prop_z), (bx, -30)), (6, (-10, (g.pad[0] + g.pad[1]) / 2), (40, 150)),
            (7, (g.motor_x[0] + 8, g.motor_z + 14), (-60, 362)), (8, (g.belt_x - 5, g.motor_z + 8), (-150, 340)),
            (9, (g.belt_x + 4, 80), (-10, 80)), (10, (g.bearings[1][0] + 2, g.prop_z + 6), (bx, 55)),
            (11, (g.collar[0] + 2, g.prop_z + 4), (30, 50)), (12, (g.prop_xa + 8, g.prop_z + 40), (bx, 95)),
            (13, (g.conn_x[0], g.depth + 12), (95, 300))]:
        s.balloon(*Q(x, z), *Q(lx, lz), no)
    # ordinates: x from the transom, z from the baseline
    ordinates_x(s, Q, [(g.bracket_x, g.depth, f"{g.bracket_x:.0f}"), (g.cover_x[1], g.top_z, f"{g.cover_x[1]:.0f}"),
                       (0, keel(h, 0), "0 transom"), (-g.wall_t, g.wall_z, f"{-g.wall_t:.0f}"),
                       (g.leg_x[1], g.leg_z[0], f"{g.leg_x[1]:.0f} LE"), (g.motor_x[0], g.motor_z - 23, f"{g.motor_x[0]:.0f}"),
                       (g.belt_x, g.prop_z - PULLEY[0] / 2, f"{g.belt_x:.0f} belt"),
                       (g.cover_x[0], g.top_z, f"{g.cover_x[0]:.0f}"), (g.leg_x[0], g.leg_z[0], f"{g.leg_x[0]:.0f} TE"),
                       (g.head_x, g.head_z, f"{g.head_x:.0f}"), (g.pod_x[0], g.prop_z - 16, f"{g.pod_x[0]:.0f}"),
                       (g.prop_xa, g.prop_bottom, f"{g.prop_xa:.0f}"), (g.shaft_x[0], g.prop_z, f"{g.shaft_x[0]:.0f}")],
                Q(0, g.prop_bottom)[1] + 6)
    ordinates_z(s, Q, [(g.cover_top, g.cover_x[1], f"{g.cover_top:.0f} cover"),
                       (g.motor_z, g.plate_x[1] + 10, f"{g.motor_z:.0f} motor axis"),
                       (g.top_z, g.bracket_x, f"{g.top_z:.0f} mount top"),
                       (g.top_z - g.platform_t, -g.wall_t, f"{g.top_z - g.platform_t:.0f} platform"),
                       (g.depth, xe, f"{g.depth:.0f} deck"), (g.socket_z[1], g.leg_x[1], f"{g.socket_z[1]:.0f} leg top"),
                       (g.wall_bolt_z, 0, f"{g.wall_bolt_z:.0f} wall bolts"), (g.socket_z[0], g.leg_x[1], f"{g.socket_z[0]:.0f}"),
                       (g.head_z, g.leg_x[1], f"{g.head_z:.0f} head"), (g.wall_z, 0, f"{g.wall_z:.0f} flange"),
                       (g.rail_z[1], xe, f"{g.rail_z[1]:.0f} rail"), (g.pad[1], 0, f"{g.pad[1]:.0f} pad"),
                       (g.pad[0], 0, f"{g.pad[0]:.0f}"), (g.leg_z[0], g.leg_x[1], f"{g.leg_z[0]:.0f}"),
                       (g.prop_z, -8, f"{g.prop_z:.0f} prop axis"), (0, xe, "0"),
                       (g.prop_bottom, g.prop_xf, f"{g.prop_bottom:.0f}")],
                Q(xe, 0)[0] + 16)
    s.view_title(Q(-36, 0)[0], Q(0, g.prop_bottom)[1] + 22, "SIDE VIEW, STARBOARD DRIVE (FIXED)", "1:2")

    # from astern (looking fwd), same scale and heights
    Xa = 252.0

    def R(y, z):
        return Xa + y * k, Y0 - z * k

    ye = 62.0  # the transom behind the drive, broken off at +/- ye
    for z in (g.depth, g.rail_z[1], g.rail_z[0]):
        s.line(*R(-ye, z), *R(ye, z), "thin")
    for sgn in (-1, 1):
        s.poly([R(sgn * ye, g.depth + 6), R(sgn * (ye - 2), g.depth - 20), R(sgn * (ye + 2), g.rail_z[1] + 20),
                R(sgn * ye, g.rail_z[0] - 6)], "thin")
    drive_aft(s, g, R, k, 0.0, detail=True)
    s.line(*R(0, g.prop_bottom - 8), *R(0, g.cover_top + 8), "ctr")
    s.line(*R(-g.prop_d / 2 - 6, g.prop_z), *R(g.prop_d / 2 + 6, g.prop_z), "ctr")
    s.line(*R(-ye, g.dwl), *R(ye, g.dwl), "wl")
    ytop = R(0, g.cover_top)[1] - 4
    s.dim_h(*R(-g.head_w / 2, g.cover_top - 10), *R(g.head_w / 2, g.cover_top - 10), ytop, g.head_w)
    s.dim_h(*R(-g.bracket_w / 2, g.top_z), *R(g.bracket_w / 2, g.top_z), ytop - 6, g.bracket_w,
            f"{g.bracket_w:.0f} mount")
    s.dim_h(*R(-g.body_w / 2, g.head_z), *R(g.body_w / 2, g.head_z), R(0, g.head_z)[1] + 5, g.body_w)
    s.dim_h(*R(-g.leg_t / 2, 120), *R(g.leg_t / 2, 120), R(0, 120)[1] + 12, g.leg_t)
    s.dim_h(*R(-g.prop_d / 2, g.prop_z), *R(g.prop_d / 2, g.prop_z), R(0, g.prop_bottom)[1] + 5, g.prop_d,
            f"{g.prop_d:.0f} prop")
    s.leader(*R(-g.pd / 2, 160), R(-40, 0)[0], R(0, 175)[1], f"belt runs at +/-{g.pd / 2:.1f}", "end", 1.8)
    s.leader(*R(-g.pod_d / 2 + 2, g.prop_z + 8), R(-48, 0)[0], R(0, g.prop_z + 40)[1],
             f"pod {g.pod_d:.0f}", "end", 1.8)
    s.leader(*R(g.wall_bolt_y, g.wall_bolt_z), R(48, 0)[0], R(0, 205)[1], "2x M5 through the lid's aft wall", size=1.8)
    s.view_title(Xa, R(0, g.prop_bottom)[1] + 16, "FROM ASTERN", "1:2")

    # from above, 1:2 (stbd = down the page)
    Xt, Yt = 283.0, 52.0

    def T(x, y):
        return Xt + (x + 165.0) * k, Yt + y * k

    deck_half = hb(h, 0) - mm(h.deck_fillet(0.0))
    for sgn in (-1, 1):
        s.line(*T(0, sgn * deck_half), *T(xe, sgn * deck_half), "thin")
    s.line(*T(0, -deck_half - 8), *T(0, deck_half + 8), "vis")
    drive_top(s, g, T, 0.0, detail=True)
    s.line(*T(-165, 0), *T(xe, 0), "ctr")
    (bx1, bx2), byy = g.bracket_bolts
    s.dim_h(*T(bx1, byy), *T(bx2, byy), T(0, g.bracket_w / 2)[1] + 5, bx2 - bx1)
    s.dim_h(*T(0, byy), *T(bx1, byy), T(0, g.bracket_w / 2)[1] + 5, bx1)
    s.dim_v(*T(bx2, -byy), *T(bx2, byy), T(g.bracket_x, 0)[0] + 4, 2 * byy, f"{2 * byy:.0f}")
    s.dim_v(*T(g.bracket_x, -g.bracket_w / 2), *T(g.bracket_x, g.bracket_w / 2), T(g.bracket_x, 0)[0] + 10,
            g.bracket_w)
    s.leader(*T(bx1, -byy), T(bx1 - 4, 0)[0], T(0, -g.bracket_w / 2 - 9)[1], "4x M5 from inside the lid", "end", 1.8)
    s.view_title(T(-40, 0)[0], T(0, g.prop_d / 2)[1] + 10, "FROM ABOVE", "1:2")

    # key points
    (bx1, bx2), byy = g.bracket_bolts
    rows = [
        ["Mount: deck flange", f"0 to {g.bracket_x:.0f}", f"{g.depth:.0f} to {g.top_z:.0f}", f"+/-{g.bracket_w / 2:.0f}"],
        ["Mount: flange down the lid's aft wall", f"-{g.wall_t:.0f} to 0", f"{g.wall_z:.0f} to {g.top_z:.0f}",
         f"+/-{g.bracket_w / 2:.0f}"],
        ["Mount: head block", f"{g.head_x:.0f} to -{g.wall_t:.0f}", f"{g.head_z:.0f} to {g.top_z:.0f}",
         f"+/-{g.body_w / 2:.0f}"],
        ["Mount: platform (under the cover)", f"{g.platform_x:.0f} to -{g.wall_t:.0f}",
         f"{g.top_z - g.platform_t:.0f} to {g.top_z:.0f}", f"+/-{g.head_w / 2:.0f}"],
        ["Mount: leg socket", f"{g.leg_x[0]:.0f} to {g.leg_x[1]:.0f}", f"{g.socket_z[0]:.0f} to {g.socket_z[1]:.0f}",
         f"+/-{g.leg_t / 2:.0f}"],
        ["Deck bolts, 4x M5 up from inside", f"{bx1:.0f}, {bx2:.0f}", f"{g.depth:.0f}", f"+/-{byy:.0f}"],
        ["Wall bolts, 2x M5 fwd from inside", f"{g.wall + 8:.0f} to -{g.wall_t:.0f}", f"{g.wall_bolt_z:.0f}",
         f"+/-{g.wall_bolt_y:.0f}"],
        ["Thrust pad (+ 2 EPDM face)", f"{g.leg_x[1]:.0f} to 0", f"{g.pad[0]:.0f} to {g.pad[1]:.0f}",
         f"+/-{g.pad[2] / 2:.0f}"],
        ["Motor plate, 4 mm 6061", f"{g.plate_x[0]:.0f} to {g.plate_x[1]:.0f}", f"{g.top_z:.0f} to {g.plate_top:.0f}",
         f"+/-{g.plate_w / 2:.0f}"],
        ["Motor can (41xx)", f"{g.motor_x[0]:.0f} to {g.motor_x[1]:.0f}", f"axis {g.motor_z:.0f}, dia {g.motor_d:.0f}", "0"],
        ["Motor cover", f"{g.cover_x[0]:.0f} to {g.cover_x[1]:.0f}", f"{g.top_z:.0f} to {g.cover_top:.0f}",
         f"+/-{g.head_w / 2:.0f}"],
        ["Belt plane (both pulleys)", f"{g.belt_x:.0f}", f"{g.motor_z:.0f} / {g.prop_z:.0f}", f"runs +/-{g.pd / 2:.1f}"],
        ["Leg, NACA 0035, 80 x 28", f"TE {g.leg_x[0]:.0f}, LE {g.leg_x[1]:.0f}", f"{g.leg_z[0]:.0f} to {g.leg_z[1]:.0f}",
         f"+/-{g.leg_t / 2:.0f}"],
        ["Lower pod, dia 32", f"tail {g.pod_x[0]:.0f}, nose {g.pod_x[1]:.0f}", f"axis {g.prop_z:.0f}", "0"],
        ["Bearings 625-2RS", f"{g.bearings[0][0]:.0f} to {g.bearings[0][1]:.0f}; {g.bearings[1][0]:.0f} to "
         f"{g.bearings[1][1]:.0f}", f"axis {g.prop_z:.0f}", ""],
        ["Shaft collar / shaft, dia 5", f"{g.collar[0]:.0f} to {g.collar[1]:.0f} / {g.shaft_x[0]:.0f} to {g.shaft_x[1]:.0f}",
         f"axis {g.prop_z:.0f}", ""],
        ["Prop hub 20 / disc 110 / nylock", f"{g.prop_xa:.0f} to {g.prop_xf:.0f} / {g.nut_x[0]:.0f}",
         f"{g.prop_z:.0f} +/- {g.prop_d / 2:.0f}", ""],
        ["Motor-wire connector (lid deck)", f"{g.conn_x[0]:.0f}", f"{g.depth:.0f}", "0"],
    ]
    s.text(288.0, 100.0, "KEY POINTS (mm; x fwd of the transom, z above the baseline, y off the hull CL)", 2.3,
           "start", bold=True)
    s.table(288.0, 102.0, ["Feature", "x", "z", "y"], rows, [46, 38, 28, 20], 1.85, 3.25)
    half = (len(DRIVE_PARTS) + 1) // 2
    ly = 102.0 + (len(rows) + 1) * 3.25 + 6
    s.text(288.0, ly, "PARTS (the balloons; 1-6 are drawn on sheet 6, 7-13 are bought)", 2.3, "start", bold=True)
    for i, (no, name) in enumerate(DRIVE_PARTS):
        cx, cy = 291.0 + 66.0 * (i // half), ly + 6.0 + 4.6 * (i % half)
        s.circle(cx, cy, 2.0, "thin")
        s.text(cx, cy + 0.75, str(no), 2.0, bold=True)
        s.text(cx + 3.5, cy + 0.75, name, 2.0, "start")

    r_pad, r_mount, m_pad, m_nopad = g.thrust
    gap = min(g.gaps, key=g.gaps.get)
    s.lines_of_text(22.0, 244.0, [
        "HOW TO USE THIS SHEET",
        "- Datums: x from the transom (the lid's aft face), z from the baseline, y from the hull centreline. "
        "Model the drive in place in the boat assembly.",
        f"- Fixed: no pivot. The leg runs {g.gaps['leg to rail']:.1f} mm clear of the rail (as close as the rail "
        f"allows); its nose rests on the thrust pad on the transom. Tightest gap: {gap} {g.gaps[gap]:.1f} mm.",
        f"- At full thrust ({g.drive.bollard_n:.0f} N) the pad takes {r_pad:.0f} N and the mount {r_mount:.0f} N; "
        f"the leg bends {m_pad:.1f} N m at the pad instead of {m_nopad:.1f} N m at the mount. Reverse hangs on the bolts.",
        f"- Belt tension: slide the motor up its slotted plate (+/-{MOTOR_SLOT:.0f}). The port drive is the mirror "
        "image with an LH prop. Parts, sizes and the motor note: sheet 6.",
    ], size=1.95, lead=3.0, bold_first=True)
    return s


def sheet_drive_parts(g: Geo) -> Sheet:
    s = Sheet(6, "Belt outdrive (fixed), part by part (for CAD), purchased parts and modeling order", "as noted")
    k2 = 0.5
    (bx1, bx2), byy = g.bracket_bolts

    # 1 mount: side (from starboard) and from above, 1:2
    def M1(x, z):
        return 24.0 + (x + 110.0) * k2, 24.0 + (g.top_z - z) * k2

    s.poly([M1(x, z) for x, z in g.mount_poly], "print", closed=True)
    s.line(*M1(g.platform_x, g.top_z - g.platform_t), *M1(-g.wall_t, g.top_z - g.platform_t), "hid")
    s.rect(*M1(g.leg_x[0], g.socket_z[0]), *M1(g.leg_x[1], g.socket_z[1]), "hid")
    for dx in (-BELT_CAV / 2, BELT_CAV / 2):
        s.line(*M1(g.belt_x + dx, g.socket_z[1]), *M1(g.belt_x + dx, g.top_z), "hid")
    zs = (g.socket_z[0] + g.socket_z[1]) / 2
    for x in SOCKET_BOLTS_X:
        s.circle(*M1(x, zs), 2.1 * k2, "vis")
    s.circle(*M1(-g.wall_t / 2, g.wall_bolt_z), 2.8 * k2, "hid")
    yb = M1(0, g.head_z)[1] + 5
    s.dim_h(*M1(g.head_x, g.head_z), *M1(-g.wall_t, g.head_z), yb, -g.wall_t - g.head_x)
    s.dim_h(*M1(-g.wall_t, g.wall_z), *M1(0, g.wall_z), yb, g.wall_t, f"{g.wall_t:.0f}")
    s.dim_h(*M1(0, g.depth), *M1(g.bracket_x, g.depth), yb, g.bracket_x)
    s.dim_v(*M1(g.bracket_x, g.depth), *M1(g.bracket_x, g.top_z), M1(g.bracket_x, 0)[0] + 4, g.bracket_t)
    s.dim_v(*M1(g.head_x, g.head_z), *M1(g.head_x, g.top_z), M1(g.head_x, 0)[0] - 4, g.top_z - g.head_z)
    s.dim_v(*M1(0, g.wall_z), *M1(0, g.top_z), M1(0, 0)[0] + 9, g.top_z - g.wall_z, f"{g.top_z - g.wall_z:.0f}")
    s.dim_h(*M1(g.leg_x[0], g.top_z), *M1(g.leg_x[1], g.top_z), M1(0, g.top_z)[1] - 4, g.leg_x[1] - g.leg_x[0],
            f"socket {g.leg_x[0]:.0f} to {g.leg_x[1]:.0f}")
    s.text(M1(-10, 0)[0], M1(0, g.head_z)[1] + 10.5, f"socket = leg section + 0.2, {g.socket_z[1] - g.socket_z[0]:.0f} "
           "deep, 2x M4 across; wall flange: 2x M5 inserts", 1.7)

    def M2(x, y):
        return 24.0 + (x + 110.0) * k2, 95.0 + y * k2

    s.rect(*M2(g.head_x, -g.body_w / 2), *M2(-g.wall_t, g.body_w / 2), "print")
    s.rect(*M2(g.platform_x, -g.head_w / 2), *M2(-g.wall_t, g.head_w / 2), "print")
    s.rect(*M2(-g.wall_t, -g.bracket_w / 2), *M2(g.bracket_x, g.bracket_w / 2), "print")
    s.rect(*M2(g.belt_x - BELT_CAV / 2, -g.pd / 2 - 3.5), *M2(g.belt_x + BELT_CAV / 2, g.pd / 2 + 3.5), "void")
    for bx in (bx1, bx2):
        for sgn in (-1, 1):
            s.circle(*M2(bx, sgn * byy), 2.8 * k2, "hid")
    for x, y in COVER_SCREWS + PLATE_SCREWS:
        s.circle(*M2(x, y), 2.0 * k2, "vis")
    s.dim_v(*M2(g.bracket_x, -g.bracket_w / 2), *M2(g.bracket_x, g.bracket_w / 2), M2(g.bracket_x, 0)[0] + 4,
            g.bracket_w)
    s.dim_v(*M2(g.platform_x, -g.head_w / 2), *M2(g.platform_x, g.head_w / 2), M2(g.platform_x, 0)[0] - 4, g.head_w)
    s.dim_v(*M2(g.head_x, -g.body_w / 2), *M2(g.head_x, g.body_w / 2), M2(g.head_x, 0)[0] - 4, g.body_w)
    s.dim_h(*M2(g.platform_x, g.head_w / 2), *M2(-g.wall_t, g.head_w / 2), M2(0, g.head_w / 2)[1] + 4,
            -g.wall_t - g.platform_x)
    s.dim_h(*M2(bx1, byy), *M2(bx2, byy), M2(0, g.bracket_w / 2)[1] + 4, bx2 - bx1)
    s.text(M2(42, 0)[0], M2(0, 0)[1] + 0.8, f"4x M5 inserts from below, +/-{byy:.0f}", 1.7)
    s.view_title(M1(40, 0)[0], 127.0, "1  MOUNT (side, above)", "1:2")

    # 2 motor plate, 1:1, looking forward (y across, z up)
    def P2(y, z):
        return 172.0 + y, 52.0 - (z - g.motor_z)

    zt = g.plate_top
    s.rect(*P2(-g.plate_w / 2, g.top_z), *P2(g.plate_w / 2, zt), "metal")
    s.rect(*P2(-6, g.motor_z - 6), *P2(6, g.motor_z + 6 + MOTOR_SLOT), "void")
    for hy, hz in MOTOR_HOLES:
        s.rect(*P2(hy - 1.6, g.motor_z + hz - 1.6), *P2(hy + 1.6, g.motor_z + hz + 1.6 + MOTOR_SLOT), "void")
    s.line(*P2(-g.plate_w / 2 - 4, g.motor_z), *P2(g.plate_w / 2 + 4, g.motor_z), "ctr")
    s.dim_h(*P2(-g.plate_w / 2, zt), *P2(g.plate_w / 2, zt), P2(0, zt)[1] - 4, g.plate_w)
    s.dim_v(*P2(g.plate_w / 2, g.top_z), *P2(g.plate_w / 2, zt), P2(g.plate_w / 2, 0)[0] + 4, zt - g.top_z)
    s.dim_v(*P2(g.plate_w / 2, g.top_z), *P2(g.plate_w / 2, g.motor_z), P2(g.plate_w / 2, 0)[0] + 11,
            g.motor_z - g.top_z, f"{g.motor_z - g.top_z:.0f} to the axis")
    s.text(172.0, P2(0, g.top_z)[1] + 4, "4x M3 slots, 3.2 wide, +4 up (25 x 19: check yours);", 1.7)
    s.text(172.0, P2(0, g.top_z)[1] + 6.6, "12 relief slot; foot 16 forward, 2x 4.3 into the mount", 1.7)
    s.view_title(172.0, 106.0, "2  MOTOR PLATE (4 mm 6061, L)", "1:1")

    # 3 cover, 1:2: side and from astern
    def C1(x, z):
        return 222.0 + (x + 62.0) * k2, 50.0 - (z - g.motor_z) * k2

    s.poly([C1(x, z) for x, z in rounded_top(g.cover_x[0], g.cover_x[1], g.top_z, g.cover_top, 8.0)], "print",
           closed=True)
    s.dim_h(*C1(g.cover_x[0], g.top_z), *C1(g.cover_x[1], g.top_z), C1(0, g.top_z)[1] + 5, g.cover_x[1] - g.cover_x[0])
    s.dim_v(*C1(g.cover_x[0], g.top_z), *C1(g.cover_x[0], g.cover_top), C1(g.cover_x[0], 0)[0] - 4,
            g.cover_top - g.top_z)
    s.circle(*C1(g.cover_x[1] - 1, 290), 4 * k2, "vis")

    def C2(y, z):
        return 290.0 + y * k2, 50.0 - (z - g.motor_z) * k2

    s.poly([C2(y, z) for y, z in rounded_top(-g.head_w / 2, g.head_w / 2, g.top_z, g.cover_top, 8.0)], "print",
           closed=True)
    s.dim_h(*C2(-g.head_w / 2, g.top_z), *C2(g.head_w / 2, g.top_z), C2(0, g.top_z)[1] + 5, g.head_w)
    s.lines_of_text(222.0, 80.0, [
        "2 wall, R8 edges, open at the bottom; 4x M3 tabs into the mount",
        "top; 8 grommet in the front wall for the motor wires; 10 x 3",
        "drain slot at the front.",
    ], size=1.7, lead=2.5)
    s.view_title(262.0, 94.0, "3  MOTOR COVER (side, astern)", "1:2")

    # 4 leg + pod half (starboard half shown; the port half is its mirror), 1:2
    def L(x, z):
        return 20.0 + (x + 118.0) * k2, 254.0 - z * k2

    s.rect(*L(g.leg_x[0], g.leg_z[0]), *L(g.leg_x[1], g.leg_z[1]), "print")
    s.poly([L(x, z) for x, z in g.pod_outline()], "print", closed=True)
    for dx in (-BELT_CAV / 2, BELT_CAV / 2):
        s.line(*L(g.belt_x + dx, g.prop_z + PULLEY_CAV[0] / 2), *L(g.belt_x + dx, g.leg_z[1]), "hid")
    s.rect(*L(g.belt_x - PULLEY_CAV[1] / 2, g.prop_z - PULLEY_CAV[0] / 2),
           *L(g.belt_x + PULLEY_CAV[1] / 2, g.prop_z + PULLEY_CAV[0] / 2), "hid")
    for a, b in g.bearings:
        s.rect(*L(a, g.prop_z - BEARING[0] / 2), *L(b, g.prop_z + BEARING[0] / 2), "hid")
    s.rect(*L(g.collar[0], g.prop_z - 5.5), *L(g.collar[1] + 0.5, g.prop_z + 5.5), "hid")
    s.line(*L(g.pod_x[0] - 4, g.prop_z), *L(g.pod_x[1] + 4, g.prop_z), "ctr")
    hl = g.head_z - g.leg_z[0]
    for x, f in LEG_SCREWS:
        s.circle(*L(x, g.leg_z[0] + f * hl), 1.6 * k2, "vis")
    for x, dz in POD_SCREWS:
        s.circle(*L(x, g.prop_z + dz), 1.6 * k2, "vis")
    for x in SOCKET_BOLTS_X:
        s.circle(*L(x, zs), 2.1 * k2, "vis")
    for xa in (g.leg_x[0] - 8, g.leg_x[1] + 4):
        s.line(*L(xa, SECTION_Z), *L(xa + 4, SECTION_Z), "vis")
    s.text(*L(g.leg_x[0] - 12, SECTION_Z - 2), "A", 2.2, bold=True)
    xr = L(g.pod_x[1], 0)[0] + 4
    s.dim_v(*L(g.leg_x[1], g.leg_z[0]), *L(g.leg_x[1], g.leg_z[1]), xr, g.leg_z[1] - g.leg_z[0],
            f"{g.leg_z[1] - g.leg_z[0]:.0f}")
    s.dim_v(*L(g.leg_x[1], g.socket_z[0]), *L(g.leg_x[1], g.leg_z[1]), xr + 7, g.leg_z[1] - g.socket_z[0],
            f"{g.leg_z[1] - g.socket_z[0]:.0f} in the socket")
    yb = L(0, g.prop_z - g.pod_d / 2)[1] + 5
    s.dim_h(*L(g.pod_x[0], g.prop_z), *L(g.pod_x[1], g.prop_z), yb, g.pod_x[1] - g.pod_x[0],
            f"{g.pod_x[1] - g.pod_x[0]:.0f} pod")
    s.leader(*L(g.belt_x + 6, 150), L(2, 0)[0], L(0, 150)[1], f"belt channel {BELT_CAV:.0f} wide", size=1.7)
    s.leader(*L(g.bearings[0][0] + 2, g.prop_z + 7), L(2, 0)[0], L(0, 120)[1],
             f"{BEARING[0]:.0f} x {BEARING[1]:.0f} seats at {g.bearings[1][0]:.0f} and {g.bearings[0][0]:.0f}", size=1.7)
    s.leader(*L(g.belt_x + 6, g.prop_z + 12), L(2, 0)[0], L(0, 105)[1],
             f"pulley pocket {PULLEY_CAV[0]:.0f} x {PULLEY_CAV[1]:.0f}", size=1.7)
    s.leader(*L(g.collar[0] + 2, g.prop_z + 4), L(2, 0)[0], L(0, 90)[1], "collar pocket 11", size=1.7)
    s.view_title(L(-62, 0)[0], 262.0, "4  LEG + POD HALF (stbd half; split on y = 0)", "1:2")

    # section A-A, 1:1
    leg_section(s, g, 182.0, 202.0, 1.0)
    s.view_title(182.0, 240.0, "SECTION A-A THROUGH THE LEG", "1:1")

    # 5 shaft, 1:1 (fwd to the right)
    def S5(x, y):
        return 95.0 + (x - g.shaft_x[0]), 150.0 + y

    r = g.shaft_d / 2
    s.rect(*S5(g.shaft_x[0], -r), *S5(g.shaft_x[1], r), "metal")
    s.line(*S5(g.prop_xa, -r + 0.5), *S5(g.prop_xf, -r + 0.5), "vis")  # D-flat
    s.line(*S5(g.belt_x - 5, -r + 0.5), *S5(g.belt_x + 5, -r + 0.5), "vis")  # set-screw flat
    for x in range(int(g.shaft_x[0]) + 1, int(g.nut_x[1]) + 4, 1):  # M5 thread
        s.line(*S5(x, -r), *S5(x + 0.6, r), "thin")
    ya = S5(0, r)[1] + 4
    s.dim_h(*S5(g.shaft_x[0], r), *S5(g.shaft_x[1], r), ya + 8, g.shaft_x[1] - g.shaft_x[0],
            f"{g.shaft_x[1] - g.shaft_x[0]:.0f} long, dia {g.shaft_d:.0f}")
    s.dim_h(*S5(g.prop_xa, r), *S5(g.prop_xf, r), ya, g.prop_xf - g.prop_xa, f"{g.prop_xf - g.prop_xa:.0f} D-flat 0.5")
    s.dim_h(*S5(g.shaft_x[0], r), *S5(g.nut_x[1] + 3, r), ya, g.nut_x[1] + 3 - g.shaft_x[0], "M5")
    s.text(*S5(g.belt_x, -r - 1.5), "pulley flat", 1.6)
    s.text(*S5(g.collar[0] + 2, -r - 1.5), "collar", 1.6)
    s.view_title(S5((g.shaft_x[0] + g.shaft_x[1]) / 2, 0)[0], 173.0, "5  PROP SHAFT (316, ends at x "
                 f"{g.shaft_x[0]:.0f} and {g.shaft_x[1]:.0f})", "1:1")

    # 6 thrust pad, 1:1: from the side and from above
    def D1(x, z):
        return 330.0 + (x - g.leg_x[1]), 62.0 - (z - g.pad[0])

    z0, z1, pw, pt = g.pad
    s.rect(*D1(g.leg_x[1] + pt, z0), *D1(0, z1), "print")
    s.rect(*D1(g.leg_x[1], z0), *D1(g.leg_x[1] + pt, z1), "rubber")
    s.line(*D1(0, z0 - 4), *D1(0, z1 + 4), "thin")
    s.text(*D1(1, z1 + 2), "transom", 1.6, "start")
    s.dim_v(*D1(0, z0), *D1(0, z1), D1(0, 0)[0] + 9, z1 - z0)
    s.dim_h(*D1(g.leg_x[1], z1), *D1(0, z1), D1(0, z1)[1] - 4, -g.leg_x[1], f"{-g.leg_x[1]:.0f} incl. 2 EPDM")
    s.text(D1(g.leg_x[1] / 2, 0)[0], D1(0, z0)[1] + 4, f"{pw:.0f} wide, centred on the hull CL;", 1.6)
    s.text(D1(g.leg_x[1] / 2, 0)[0], D1(0, z0)[1] + 6.4, "aft face R11 to fit the leg's nose", 1.6)
    s.view_title(D1(g.leg_x[1] / 2, 0)[0], 80.0, "6  THRUST PAD", "1:1")

    # purchased parts and notes
    s.text(248.0, 104.0, "PURCHASED PARTS (per drive; 2 drives)", 2.5, "start", bold=True)
    s.table(248.0, 106.5, ["No.", "Qty", "Item"], [
        ["7", "1", f"Outrunner, 41xx ({g.motor_d:.0f} x {g.motor_x[1] - g.motor_x[0]:.0f} can), 25 A+. KV: see the note"],
        ["8", "2", f"HTD 3M pulley, {g.drive.pulley_teeth}T ({g.pd:.1f} PD), 9 mm belt; bores to the motor / 5 mm shaft"],
        ["9", "1", f"HTD 3M belt, {g.belt_w:.0f} mm, {g.teeth} T ({g.teeth * mm(g.drive.belt_pitch):.0f} mm), "
                   "PU with aramid or stainless cords"],
        ["10", "2", "625-2RS bearing, stainless (5 x 16 x 5): they run wet"],
        ["11", "1", "Shaft collar, 5 mm bore, 10 OD x 5, set screw"],
        ["12", "1", f"Prop {g.prop_d:.0f} (props/toroidal_..._RH_shaft stbd, _LH_ port) + washer + M5 nylock A4"],
        ["13", "1", f"IP68 bulkhead connector, 3-pin, in the lid's aft deck at x {g.conn_x[0]:.0f}"],
        ["-", "", "6x M5 x 20 A4 + washers (4 up through the deck, 2 through the aft wall), 3 mm Al backing plates"],
        ["-", "", "6x M5 heat-set inserts in the mount; 2x M4 x 40 A4 + nylocks across the socket"],
        ["-", "", "~12x M3 A4 + inserts (leg/pod halves, cover); 2x M4 x 8 (motor plate foot)"],
    ], [9, 9, 154], 1.85, 3.25)

    r_pad, r_mount, m_pad, m_nopad = g.thrust
    s.lines_of_text(248.0, 150.0, [
        "NOTES",
        "- Print 1, 3 and 4 in ABS or ASA (the EXP S5 lists ABS), not PLA: the motor and the sun heat them.",
        "  6 walls or 100 % infill round the socket and the inserts. The mount can be milled from 6061 later.",
        "- Bond 6 to the transom with thickened epoxy; it carries the forward thrust. The leg lifts off with the",
        "  lid; nothing on the drive bolts to the tub.",
        f"- Loads at {g.drive.bollard_n:.0f} N forward: pad {r_pad:.0f} N, mount {r_mount:.0f} N, leg {m_pad:.1f} N m "
        f"at the pad ({m_nopad:.1f} N m with no pad).",
        f"- MOTOR KV. V3's drive rail is 12S (~44 V). Rev C picked {g.drive.kv:.0f} KV for an 18 V pack; on 12S it",
        "  would run at ~10-25 % duty from cruise to top speed. ~150-200 KV suits 12S. Most motors with enough",
        "  power at that KV are a size up (50xx, ~55 dia): that fits the 70 cover with the motor axis ~5 mm up.",
        "  The drawings keep the 41xx envelope until you pick one.",
        "",
        "MODELING ORDER (SolidWorks)",
        "1. Drive assembly layout sketch on the Front plane: transom (x 0), deck (z 250), belt plane, motor and",
        "   prop axes. Origin = transom / baseline / hull CL, like the hull.",
        f"2. Mount: extrude the side profile +/-{g.body_w / 2:.0f} (head block); add the deck and wall flanges "
        f"+/-{g.bracket_w / 2:.0f} and the",
        f"   platform +/-{g.head_w / 2:.0f}; cut the socket (leg section + 0.2), the belt slot and the holes.",
        f"3. Leg + pod: section A-A at z {g.leg_z[0]:.0f} extruded to {g.leg_z[1]:.0f}; pod revolved on the prop axis; "
        "combine, cut the",
        "   pockets, split on y = 0. Mirror the half for the other side.",
        "4. Pad, plate, cover; then mate everything fixed and run Interference Detection.",
    ], size=1.85, lead=2.75, bold_first=True)
    return s


# ---- CAD files -------------------------------------------------------------------------------


def write_curves(g: Geo) -> list[Path]:
    """XYZ curves in mm, SolidWorks axes: X fwd, Y up, Z to starboard."""
    CAD.mkdir(exist_ok=True)
    h, b = g.hull, g.boat
    xs = stations(h, 10)
    curves = {
        "keel_centreline.txt": [(x, keel(h, x), 0.0) for x in xs],
        "chine_stbd.txt": [(x, chine(h, x), hb(h, x)) for x in xs],
        "deck_edge_stbd.txt": [(x, g.depth, hb(h, x)) for x in xs],
        "deck_centreline.txt": [(0.0, g.depth, 0.0), (g.loa, g.depth, 0.0)],
        "lid_joint_line_stbd.txt": [(x, g.zj, hb(h, x)) for x in xs],
        # bridge: arch centreline in the plane of the aft frame, boat coordinates
        "arch_centreline.txt": [(g.fx[0], mm(z), mm(y)) for y, z in arch_centreline(b, h)],
        "arm_fairing_path_stbd.txt": [(g.xc, mm(z), mm(y)) for y, z in arm_path(b, h)],
    }
    for z in (g.hub_z[0], g.frame_top, g.hub_z[1], (g.hub_z[1] + g.hub_z[2]) / 2, g.hub_z[2] - 10):
        sc = g.hub_scale(z)
        pts = superellipse(g.hub_ax * sc, g.hub_ay * sc, b.hub_e, 48)
        curves[f"hub_section_z{z:03.0f}.txt"] = [(g.hub_x + px, z, py) for px, py in pts + pts[:1]]
    paths = []
    for name, pts in curves.items():
        p = CAD / name
        p.write_text("".join(f"{x:.3f} {y:.3f} {z:.3f}\n" for x, y, z in pts), encoding="ascii")
        paths.append(p)
    # cut file for the frame plate (mm; X = y across the boat, Y = z above the baseline)
    ents = ["0\nPOLYLINE\n8\nOUTLINE\n66\n1\n70\n1\n"]
    for y, z in g.frame:
        ents.append(f"0\nVERTEX\n8\nOUTLINE\n10\n{y:.3f}\n20\n{z:.3f}\n")
    ents.append("0\nSEQEND\n")
    hub_c = g.frame_top - g.frame_h / 2
    holes = [(y, hub_c, d / 2) for y, d in LIGHTENING]
    holes += [(y, g.frame_top - 12, 2.75) for y in GARAGE_HOLES_Y]
    holes += [(sgn * g.yc, z, 2.75) for sgn in (-1, 1) for z in g.foot_holes_z]
    for cx, cy, r in holes:
        ents.append(f"0\nCIRCLE\n8\nHOLES\n10\n{cx:.3f}\n20\n{cy:.3f}\n40\n{r:.3f}\n")
    dxf = ("0\nSECTION\n2\nHEADER\n9\n$ACADVER\n1\nAC1009\n9\n$INSUNITS\n70\n4\n0\nENDSEC\n"
           "0\nSECTION\n2\nENTITIES\n" + "".join(ents) + "0\nENDSEC\n0\nEOF\n")
    p = CAD / "arch_frame_plate.dxf"
    p.write_text(dxf, encoding="ascii")
    paths.append(p)
    return paths


def browser() -> str | None:
    for cand in (r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                 r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
                 r"C:\Program Files\Google\Chrome\Application\chrome.exe"):
        if Path(cand).exists():
            return cand
    return shutil.which("msedge") or shutil.which("chrome") or shutil.which("chromium")


# ---- sheet 7: the body plan, one slice at a time ---------------------------------------------


def sheet_sections(g: Geo) -> Sheet:
    s = Sheet(7, "Hull sections one at a time: a reading aid for the body plan", "1:6 / sketch")
    h = g.hull

    def ring(x: float) -> list[tuple[float, float]]:
        """Full section, both halves, at station x (mm)."""
        half = [(mm(y), mm(z)) for y, z in section_points(h, x / 1000)]
        return half + [(-y, z) for y, z in reversed(half[1:-1])]

    # 3D sketch: cabinet oblique, the far (stbd) side drawn up and to the right at 30 deg, half scale
    k3, X3, Y3 = 0.18, 34.0, 72.0
    ca, sa = 0.5 * math.cos(math.radians(30)), 0.5 * math.sin(math.radians(30))

    def obl(x, y, z):
        return X3 + k3 * (x + ca * y), Y3 - k3 * (z + sa * y)

    xs = stations(h, 20)
    wire = "stroke:#8c8c8c"  # light hull lines, so the coloured slices stand out
    for sgn in (1, -1):  # top of each straight side
        s.poly([obl(x, sgn * hb(h, x), g.depth - mm(h.deck_fillet(x / 1000))) for x in xs], "thin", style=wire)
    s.poly([obl(x, 0, keel(h, x)) for x in xs], "thin", style=wire)
    s.poly([obl(x, 0, g.depth) for x in xs], "thin", style=wire)
    for i, x in enumerate(g.stations):  # stern first: the nearer slices draw over the farther
        c = g.stations[x]
        s.poly([obl(x, y, z) for y, z in ring(x)], "vis", closed=True, style=f"stroke:{c};fill:{c};fill-opacity:0.16")
        s.text(*obl(x, 0, g.depth + 24 + 30 * (i % 2)), f"{x:.0f}", 1.9, bold=True, color=c)
    s.text(*obl(0, -hb(h, 0), -38), "TRANSOM", 1.9)
    s.text(*obl(g.loa + 25, 0, keel(h, g.loa) + 40), "BOW", 1.9, "start")
    ya = obl(0, 0, -45)[1]
    s.add(f'<line class="dim" x1="{obl(0.69 * g.loa, 0, 0)[0]:.2f}" y1="{ya:.2f}" x2="{obl(0.88 * g.loa, 0, 0)[0]:.2f}" '
          f'y2="{ya:.2f}" marker-end="url(#a)"/>')
    s.text(obl(0.79 * g.loa, 0, 0)[0], ya - 1.2, "FWD", 1.9, bold=True)
    s.view_title(obl(g.loa / 2, 0, 0)[0], Y3 + 16, "WHERE EACH SLICE IS (ONE HULL)", "sketch, not to scale")

    xa0, xt0, xr0 = (mm(v * h.loa) for v in (h.stern_rise_end, h.taper_start, h.rocker_start))
    s.lines_of_text(250, 20, [
        "HOW TO READ THE BODY PLAN (SHEET 2)",
        "Each coloured shape is one slice straight across ONE hull, like a slice of",
        "bread. Its number is where the slice is: mm forward of the transom.",
        "",
        "Sheet 2 stacks all the slices on one drawing. The hull is the same on both",
        "sides, so it draws only half of each slice: the stern half of the boat on",
        "the left of the centreline, the bow half on the right, in these colours.",
        "",
        "Reading from stern to bow:",
        f"- 0 to {xa0:.0f}: the same shape, but the keel lifts toward the transom",
        f"  (+{keel(h, 0):.0f} mm at 0), so the stern draws less water.",
        f"- {xa0:.0f} to {xt0:.0f}: the widest part ({g.beam:.0f} mm), keel on the baseline.",
        f"- {xt0:.0f} to {g.loa:.0f}: it narrows toward the bow; from {xr0:.0f} the keel",
        f"  also rises, to +{keel(h, g.loa):.0f} at the bow, which ends in a {mm(h.stem_flat):.0f} mm flat face.",
        "",
        f"In each box: blue dashes = waterline ({g.dwl:.0f}), purple = lid joint ({g.zj:.0f}).",
        "In SolidWorks, each box is one sketch on a plane at that x (guide, A2).",
    ], size=2.1, lead=3.35, bold_first=True)

    k5 = 1 / 6
    for n, x in enumerate(g.stations):
        c = g.stations[x]
        cx, y0 = 50.0 + 67.0 * (n % 6), 103.0 + 62.0 * (n // 6)
        base = y0 + 10.5 + g.depth * k5

        def S(y, z):
            return cx + y * k5, base - z * k5

        w = 2 * hb(h, x)
        zs = g.depth - mm(h.deck_fillet(x / 1000))  # top of the straight side
        s.text(cx, y0, f"STATION {x:.0f}", 2.3, bold=True, color=c)
        where = ("the transom itself" if x == 0 else "the bow (stem)" if x >= g.loa
                 else f"{x:.0f} mm fwd of the transom")
        s.text(cx, y0 + 3.3, where, 1.7)
        s.line(*S(-125, 0), *S(125, 0), "thin")
        s.line(*S(-125, g.dwl), *S(125, g.dwl), "wl")
        s.line(*S(-125, g.zj), *S(125, g.zj), "lidj")
        s.line(*S(0, -8), *S(0, g.depth + 4), "ctr")
        s.poly([S(y, z) for y, z in ring(x)], "vis", closed=True, style=f"stroke:{c};fill:{c};fill-opacity:0.12")
        s.dim_h(*S(-w / 2, zs), *S(w / 2, zs), y0 + 7.4, w, f"{w:.0f} wide")
        kz = keel(h, x)
        rc, rd = mm(h.fillet(x / 1000)[0]), mm(h.deck_fillet(x / 1000))
        s.text(cx, base + 3.6, f"keel +{kz:.0f}, R{rc:.0f} chine, R{rd:.0f} deck edge" if kz >= 0.5
               else f"keel on baseline, R{rc:.0f} chine, R{rd:.0f} deck edge", 1.7)
    for row in (0, 1):
        base = 103.0 + 62.0 * row + 10.5 + g.depth * k5
        s.text(16, base - g.dwl * k5 - 0.8, "DWL", 1.6, "start", cls="blue")
        s.text(16, base - g.zj * k5 - 0.8, "joint", 1.6, "start", cls="purple")
    s.text(245, 230, "Scale 1:6. Full slices, both halves, looking forward from the stern.", 1.9, "start")
    return s


def main() -> None:
    g = Geo()
    sheets = [sheet_ga(g), sheet_lines(g), sheet_details(g), sheet_lid_hull(g), sheet_drive_assembly(g),
              sheet_drive_parts(g), sheet_sections(g)]
    OUT.mkdir(exist_ok=True)
    pages = "".join(f'<div class="page">{s.svg(len(sheets))}</div>' for s in sheets)
    html = ("<!DOCTYPE html><html><head><meta charset='utf-8'><title>DREAMS drawings, rev E</title>"
            "<style>@page{size:17in 11in;margin:0}body{margin:0}"
            ".page{width:17in;height:11in;page-break-after:always;overflow:hidden}"
            ".page svg{display:block}</style></head><body>" + pages + "</body></html>")
    out_html = OUT / "DREAMS_V2_drawings.html"
    out_html.write_text(html, encoding="utf-8")
    print(f"wrote {out_html}")
    for p in write_curves(g):
        print(f"wrote {p}")
    exe = browser()
    if exe:
        pdf = OUT / "DREAMS_V2_drawings.pdf"
        subprocess.run([exe, "--headless", "--disable-gpu", "--no-pdf-header-footer",
                        "--print-to-pdf-no-header", f"--print-to-pdf={pdf}", out_html.as_uri()],
                       check=False, capture_output=True, timeout=120)
        print(f"wrote {pdf}" if pdf.exists() else "PDF step failed; open the HTML and print to PDF")
    else:
        print("no Edge/Chrome found; open the HTML and print to PDF (17 x 11 in, no margins)")


if __name__ == "__main__":
    main()
