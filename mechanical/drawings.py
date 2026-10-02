"""Dimensioned drawing set and CAD files for the D.R.E.A.M.S V2 boat.

Everything is generated from the parameters in hull_sizing.py, so re-run this after any
change there:
    python mechanical/drawings.py
Outputs:
    mechanical/drawings/DREAMS_V2_drawings.html  5 sheets, ANSI B (17 x 11 in), inline SVG
    mechanical/drawings/DREAMS_V2_drawings.pdf   the same, printed by headless Edge/Chrome
    mechanical/cad/*.txt                         XYZ point curves for SolidWorks
                                                 (Insert > Curve > Curve Through XYZ Points)
    mechanical/cad/arch_frame_plate.dxf          cut file for the two arch frames
Sheets are third-angle, dimensions in mm. Model origin: transom, baseline, boat centreline
(hull sheets: hull centreline).
"""

from __future__ import annotations

import math
import shutil
import subprocess
from html import escape
from pathlib import Path

from hull_sizing import (MARGIN, RHO_WATER, Boat, Hull, Loads, arch_centreline, arm_path, arm_section,
                         arm_silhouette, conditions, draft_for, frame_outline, joint_checks, lid_joint_mass,
                         lid_screws, load_cases, offset_polyline, rail_length, section, section_points,
                         shell_mass)

HERE = Path(__file__).resolve().parent
OUT = HERE / "drawings"
CAD = HERE / "cad"
W, H = 431.8, 279.4  # ANSI B landscape, mm
DATE = "2026-09-27"
REV = "C (hull lids + belt outdrive)"

# drawing-only geometry, mm (not in the sizing model)
POD = (110.0, 80.0, 160.0)  # V1-style pod envelope, x y z
POD_GAP = 20.0  # hub underside to pod top when stowed
VENT_X = 900.0  # membrane vent in the lid, segment 4 (clear of the foot)
SHOE_H = 55.0  # foot shoe fairing height above the lid deck
LIGHTENING = ((-110.0, 25.0), (0.0, 25.0), (110.0, 25.0))  # frame holes (y, dia) in the hub span
BOX_HOLES_Y = (-120.0, 120.0)  # box bracket holes along the hub span
TETHER_HOLE = 30.0
CLEAR = 0.3  # print clearance at the drip lip and the spigot
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
BEARING = (16.0, 5.0)  # 625-2RS: OD, width
NYLOCK = (8.0, 5.0)  # M5 nylock: across flats, height
BRACKET_H = 12.0  # tilt-bracket base plate on the lid deck
COVER_GAP = 8.0  # cover bottom above the tilt pin
CHEEK = (12.0, 22.0, 7.0)  # cheeks: aft of the pin, below it, above it
TILT_DEG = 70.0
SECTION_Z = 160.0  # section A-A through the leg

# body-plan stations (mm fwd of the transom) and their colours, stern (blue) to bow (purple)
STATION_COLOURS = {0.0: "#1f4e9c", 130.0: "#2a7fbf", 260.0: "#138f96", 390.0: "#2f9e5a", 520.0: "#5c8f16",
                   650.0: "#9a7b00", 780.0: "#d06a0c", 910.0: "#c8412a", 1040.0: "#b0243f", 1170.0: "#9c2a8a",
                   1250.0: "#6b3fa0", 1300.0: "#3b3b6b"}
AFT_STATIONS = [x for x in STATION_COLOURS if x <= 520.0]
FWD_STATIONS = [x for x in STATION_COLOURS if x > 520.0]

GAP, OVER = 1.0, 1.5  # extension-line gap and overshoot, paper mm

STYLE = """<style>
.vis{stroke:#000;stroke-width:0.35;fill:none}
.thin{stroke:#000;stroke-width:0.18;fill:none}
.hid{stroke:#000;stroke-width:0.18;fill:none;stroke-dasharray:1.6 0.9}
.ctr{stroke:#000;stroke-width:0.13;fill:none;stroke-dasharray:6 1.2 1 1.2}
.ph{stroke:#666;stroke-width:0.18;fill:none;stroke-dasharray:5 1 1 1 1 1}
.wl{stroke:#1a5fb4;stroke-width:0.25;fill:none;stroke-dasharray:4 1.5}
.wlt{stroke:#1a5fb4;stroke-width:0.15;fill:none;stroke-dasharray:1.5 1.5}
.joint{stroke:#c01c28;stroke-width:0.3;fill:none;stroke-dasharray:3 1}
.lidj{stroke:#8a3ab9;stroke-width:0.3;fill:none;stroke-dasharray:6 1.5}
.dim{stroke:#000;stroke-width:0.15;fill:none}
.dimx{stroke:#000;stroke-width:0.12;fill:none}
.cut{stroke:#000;stroke-width:0.25;fill:#d9d9d9}
.cut2{stroke:#000;stroke-width:0.25;fill:#eeeeee}
.void{stroke:#000;stroke-width:0.2;fill:#ffffff}
.rubber{stroke:#000;stroke-width:0.2;fill:#4a4a4a}
.metal{stroke:#000;stroke-width:0.25;fill:#bfc9d4}
.plate{stroke:#000;stroke-width:0.35;fill:#e4e8ee}
.orange{stroke:#000;stroke-width:0.35;fill:#fbe0c8}
.glass{stroke:#1a5fb4;stroke-width:0.2;fill:#cfe2f3}
.frame{stroke:#000;stroke-width:0.5;fill:none}
.grid{stroke:#000;stroke-width:0.18;fill:none}
text{font-family:Arial,Helvetica,sans-serif;fill:#000}
.blue{fill:#1a5fb4}
.red{fill:#c01c28}
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
        tb.text(tx + 2, ty + 5, "D.R.E.A.M.S V2 — autonomous survey catamaran", 3.2, "start", bold=True)
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
    its bulkheads and the tub flange with its inserts."""
    lid, n = hull.lid, 400
    dx = hull.loa / n
    girth = sum(section(hull, (i + 0.5) * dx, lid.z)[3] for i in range(n)) * dx
    transom = section(hull, 0.0, lid.z)[0]
    bulk = sum(section(hull, xj, lid.z - lid.bulkhead_gap)[0] for xj in hull.joints()[1:])
    shell = (girth * (hull.wall_t * hull.wall_rho + hull.skin_areal) + transom * hull.skin_areal
             + (transom + bulk) * hull.bulkhead_t * hull.wall_rho) * (1 + hull.stiffener_frac)
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
        self.loa, self.beam, self.depth = mm(h.loa), mm(h.beam), mm(h.depth)
        self.spacing = mm(b.spacing(h))
        self.yc = self.spacing / 2
        self.fx = [mm(v) for v in b.frame_x]
        self.xc = sum(self.fx) / 2
        self.joints = [mm(v) for v in h.joints()][1:]
        self.seg = mm(h.segment_length)
        self.frame = [(mm(y), mm(z)) for y, z in frame_outline(b, h)]
        self.frame_h, self.frame_t = mm(b.frame_h), mm(b.frame_t)
        up, lo = arm_silhouette(b, h)
        self.arm_up = [(mm(y), mm(z)) for y, z in up]
        self.arm_lo = [(mm(y), mm(z)) for y, z in lo]
        path = arm_path(b, h)
        self.arm_plan = [(mm(y), mm(arm_section(i / (len(path) - 1))[0])) for i, (y, _) in enumerate(path)]
        self.hub_x = mm(b.hub_x)
        self.hub_ax, self.hub_ay = (mm(v) for v in b.hub_half)
        self.hub_z = [mm(v) for v in b.hub_z]
        self.box = [mm(v) for v in b.box]
        self.box_z0 = mm(b.arm_hub[1] + b.frame_h / 2)
        self.mast_top = mm(b.mast_top)
        self.cam_base = mm(b.camera_baseline)
        self.foot_z = mm(b.foot_z)
        self.foot_len, self.foot_w, self.foot_t = mm(b.foot_len), mm(b.foot_w), mm(b.foot_t)
        self.pad_t = mm(b.pad_t)
        self.foot_holes_z = (self.foot_z + 15.0, self.foot_z + 35.0)  # angle-bracket holes in the frame
        self.shoe_len, self.shoe_w = self.foot_len + 44, self.foot_w + 12
        self.bolt_dx = mm(b.foot_bolt_dx)
        self.bolt_y = [mm(v) for v in b.foot_bolt_y]
        self.pod_z1 = self.hub_z[0] - POD_GAP
        self.pod_z0 = self.pod_z1 - POD[2]
        self.whip_y = 120.0
        # lid and rail
        lid = h.lid
        self.lid = lid
        self.zj = mm(lid.z)
        self.fw, self.ft = mm(lid.flange_w), mm(lid.flange_t)
        self.lip_t, self.lip_drop = mm(lid.lip_t), mm(lid.lip_drop)
        self.rail = self.fw + self.lip_t
        self.rail_z = (self.zj - self.lip_drop, self.zj + self.ft)
        self.wall = mm(h.wall_t)
        self.n_screws = lid_screws(h, b.frame_x)
        self.rail_len = rail_length(h)
        self.rib_depth = self.depth - self.zj
        self.boss_z = (self.zj, self.depth - self.wall)  # full depth, so the rib is never notched
        self.tub_kg = tub_mass(h)
        # belt outdrive
        d = b.drive
        self.drive = d
        dwl_m = self.dwl / 1000
        self.prop_d = mm(d.prop_d)
        self.prop_z = mm(d.prop_z(dwl_m))
        self.prop_bottom = self.prop_z - self.prop_d / 2
        self.total_draft = self.dwl - self.prop_bottom
        self.prop_xf, self.prop_xa = (mm(v) for v in d.prop_x())
        self.aft_end = self.prop_xa - NYLOCK[1]
        self.loa_all = self.loa - self.aft_end
        self.belt_x = mm(d.belt_x)
        self.belt_w = mm(d.belt_w)
        self.motor_z = mm(d.motor_z)
        self.motor_d = mm(d.motor_d)
        self.motor_x = (self.belt_x + 10, self.belt_x + 10 + mm(d.motor_l))
        self.pivot = (mm(d.pivot[0]), mm(d.pivot[1]))
        cx, cy, cz = (mm(v) for v in d.cover)
        self.cover_x = (self.belt_x - 20, self.belt_x - 20 + cx)
        self.cover_z = (self.pivot[1] + COVER_GAP, self.pivot[1] + COVER_GAP + cz)
        self.cover_w = cy
        self.bracket_x, self.bracket_w = (mm(v) for v in d.bracket)
        self.leg_x = (mm(d.leg_le) - mm(d.leg_chord), mm(d.leg_le))
        self.leg_t = mm(d.leg_t)
        self.pod_d = mm(d.pod_d)
        self.pod_x = (mm(d.pod_x[1]), mm(d.pod_x[0]))  # tail, nose
        self.leg_z = (self.prop_z + self.pod_d / 2, self.cover_z[0])
        self.centres = mm(d.centre_distance(dwl_m))
        self.teeth = d.belt_teeth(dwl_m)
        self.pd = mm(d.pulley_pd)
        self.shaft_d = mm(d.shaft_d)
        self.bearings = ((self.pod_x[1] - 15, self.pod_x[1] - 10), (self.pod_x[0] + 6, self.pod_x[0] + 11))

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

    def plan_outline(self, step: float = 20.0) -> list[tuple[float, float]]:
        """Closed plan outline of one hull at the side (x, y from its centreline)."""
        xs = stations(self.hull, step)
        return [(x, -hb(self.hull, x)) for x in xs] + [(x, hb(self.hull, x)) for x in reversed(xs)]

    def rail_outline(self, step: float = 20.0) -> list[tuple[float, float]]:
        return offset_closed(self.plan_outline(step), self.rail)

    def pod_outline(self) -> list[tuple[float, float]]:
        """Lower pod seen from the side, boat (x, z): round nose, parallel body, tapered tail."""
        r, z = self.pod_d / 2, self.prop_z
        tail, nose = self.pod_x
        cx = nose - r
        pts = [(cx + r * math.cos(math.radians(a)), z + r * math.sin(math.radians(a))) for a in range(90, -91, -15)]
        return pts + [(tail + 20, z - r), (tail, z - PROP_HUB_D / 2 - 1), (tail, z + PROP_HUB_D / 2 + 1),
                      (tail + 20, z + r)]

    def kick_arc(self) -> list[tuple[float, float]]:
        """Path of the prop's lowest aft corner as the drive tilts up about its pin."""
        px, pz = self.pivot
        vx, vz = self.prop_xa - px, self.prop_bottom - pz
        r, a0 = math.hypot(vx, vz), math.atan2(vz, vx)
        return [(px + r * math.cos(a0 - math.radians(t)), pz + r * math.sin(a0 - math.radians(t)))
                for t in range(0, int(TILT_DEG) + 1, 5)]


# ---- outdrive views (shared by the GA and sheet 4) -----------------------------------------


def drive_profile(s: Sheet, g: Geo, Q, k: float, detail: bool = False) -> None:
    """Belt outdrive from starboard; Q maps boat (x, z) mm to paper, k is the scale."""
    px, pz = g.pivot
    s.rect(*Q(0, g.depth), *Q(g.bracket_x, g.depth + BRACKET_H), "vis")
    s.rect(*Q(px - CHEEK[0], pz - CHEEK[1]), *Q(0, pz + CHEEK[2]), "vis")
    s.circle(*Q(px, pz), 3 * k, "vis")
    s.rect(*Q(g.cover_x[0], g.cover_z[0]), *Q(g.cover_x[1], g.cover_z[1]), "vis")
    s.rect(*Q(g.leg_x[0], g.leg_z[0]), *Q(g.leg_x[1], g.leg_z[1]), "vis")
    s.poly([Q(x, z) for x, z in g.pod_outline()], "vis", closed=True)
    s.rect(*Q(g.prop_xa, g.prop_z - PROP_HUB_D / 2), *Q(g.prop_xf, g.prop_z + PROP_HUB_D / 2), "vis")
    s.rect(*Q(g.prop_xa, g.prop_bottom), *Q(g.prop_xf, g.prop_bottom + g.prop_d), "thin")
    s.rect(*Q(g.aft_end, g.prop_z - NYLOCK[0] / 2), *Q(g.prop_xa, g.prop_z + NYLOCK[0] / 2), "vis")
    for dx in (-g.belt_w / 2, g.belt_w / 2):
        s.line(*Q(g.belt_x + dx, g.prop_z + PULLEY[0] / 2), *Q(g.belt_x + dx, g.motor_z - PULLEY[0] / 2), "hid")
    s.rect(*Q(g.motor_x[0], g.motor_z - g.motor_d / 2), *Q(g.motor_x[1], g.motor_z + g.motor_d / 2), "hid")
    if not detail:
        return
    for z in (g.motor_z, g.prop_z):  # pulleys
        s.rect(*Q(g.belt_x - PULLEY[1] / 2, z - PULLEY[0] / 2), *Q(g.belt_x + PULLEY[1] / 2, z + PULLEY[0] / 2), "hid")
    for a, b in g.bearings:
        s.rect(*Q(a, g.prop_z - BEARING[0] / 2), *Q(b, g.prop_z + BEARING[0] / 2), "hid")
    r = g.shaft_d / 2
    s.rect(*Q(g.pod_x[0], g.prop_z - r), *Q(g.bearings[1][1], g.prop_z + r), "hid")
    s.rect(*Q(g.aft_end - 2, g.prop_z - r), *Q(g.aft_end, g.prop_z + r), "vis")
    s.rect(*Q(g.prop_xf, g.prop_z - r), *Q(g.pod_x[0], g.prop_z + r), "vis")
    s.rect(*Q(g.motor_x[1], g.cover_z[0] + 4), *Q(g.motor_x[1] + 4, g.cover_z[1] - 9), "hid")  # motor plate
    for bx in (15.0, g.bracket_x - 15):  # M5 from inside the lid
        s.line(*Q(bx, g.depth - g.wall - 6), *Q(bx, g.depth + BRACKET_H), "hid")
        s.rect(*Q(bx - 4, g.depth - g.wall - 6), *Q(bx + 4, g.depth - g.wall), "hid")


def drive_plan(s: Sheet, g: Geo, P, yc: float) -> None:
    s.rect(*P(0, yc - g.bracket_w / 2), *P(g.bracket_x, yc + g.bracket_w / 2), "vis")
    s.rect(*P(g.cover_x[0], yc - g.cover_w / 2), *P(g.cover_x[1], yc + g.cover_w / 2), "vis")
    s.rect(*P(g.leg_x[0], yc - g.leg_t / 2), *P(g.cover_x[0], yc + g.leg_t / 2), "vis")
    s.rect(*P(g.pod_x[0], yc - g.pod_d / 2), *P(g.leg_x[0], yc + g.pod_d / 2), "hid")
    s.rect(*P(g.prop_xa, yc - g.prop_d / 2), *P(g.prop_xf, yc + g.prop_d / 2), "thin")


def drive_astern(s: Sheet, g: Geo, R, k: float, yc: float) -> None:
    s.rect(*R(yc - g.bracket_w / 2, g.depth), *R(yc + g.bracket_w / 2, g.depth + BRACKET_H), "vis")
    s.rect(*R(yc - g.cover_w / 2, g.cover_z[0]), *R(yc + g.cover_w / 2, g.cover_z[1]), "vis")
    s.rect(*R(yc - g.leg_t / 2, g.leg_z[0]), *R(yc + g.leg_t / 2, g.leg_z[1]), "vis")
    s.circle(*R(yc, g.prop_z), g.pod_d / 2 * k, "vis")
    s.circle(*R(yc, g.prop_z), g.prop_d / 2 * k, "thin")


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
        for xj in g.joints:
            s.line(*P(xj, yc - hb(h, xj)), *P(xj, yc + hb(h, xj)), "hid")
        drive_plan(s, g, P, yc)
        s.rect(*P(g.xc - g.shoe_len / 2, yc - g.shoe_w / 2), *P(g.xc + g.shoe_len / 2, yc + g.shoe_w / 2), "vis")
        # arm fairing between the hub and the shoe
        outside = [(y, w) for y, w in g.arm_plan if g.hub_ay * 0.97 <= y <= g.yc - g.shoe_w / 2]
        pts = [P(g.xc - w, sgn * y) for y, w in outside] + [P(g.xc + w, sgn * y) for y, w in reversed(outside)]
        s.poly(pts, "vis", closed=True)
        s.circle(*P(VENT_X, yc), 1.0, "thin")
        s.text(*P(300, yc + 2.5), "STBD HULL" if sgn > 0 else "PORT HULL", 2.4)
    for fxx in g.fx:
        s.line(*P(fxx, -g.yc), *P(fxx, g.yc), "hid")
    s.poly([P(g.hub_x + px, py) for px, py in superellipse(g.hub_ax, g.hub_ay, g.boat.hub_e)], "vis", closed=True)
    bx, by, _ = g.box
    s.rect(*P(g.hub_x - bx / 2, -by / 2), *P(g.hub_x + bx / 2, by / 2), "hid")
    s.circle(*P(g.hub_x, 0), 7.5, "ph")
    s.circle(*P(g.hub_x, 0), 1.1, "vis")
    for wy in (-g.whip_y, g.whip_y):
        s.circle(*P(g.hub_x, wy), 0.8, "vis")
    bar_x = g.hub_x + g.hub_ax - 60
    s.rect(*P(bar_x - 16, -180), *P(bar_x + 16, 180), "vis")
    s.rect(*P(g.hub_x - POD[0] / 2, -POD[1] / 2), *P(g.hub_x + POD[0] / 2, POD[1] / 2), "hid")
    s.line(*P(-190, 0), *P(g.loa + 60, 0), "ctr")
    tx = P(960, 0)[0]
    s.leader(*P(g.hub_x, 0), tx, P(0, -150)[1], "GNSS mast (puck dashed)")
    s.leader(*P(g.hub_x, g.whip_y), tx, P(0, 105)[1], "LTE / WiFi whips")
    s.leader(*P(bar_x + 16, -60), tx, P(0, -70)[1], f"stereo bar ({g.cam_base:.0f} baseline)")
    s.leader(*P(g.hub_x + 20, 30), tx, P(0, 35)[1], "pod under hub (hidden)")
    s.text(*P(g.hub_x - g.hub_ax + 30, g.hub_ay - 35), "HUB: IP67 box inside (dashed)", 2.0, "start")
    s.leader(*P(g.prop_xa, g.yc + g.prop_d / 2), P(-120, 0)[0], P(0, g.yc + 165)[1],
             "belt outdrive + 110 prop", anchor="end")
    s.leader(*P(1000, g.yc + hb(h, 1000) + g.rail), P(1060, 0)[0], P(0, g.yc + 165)[1],
             f"rail (lid over the gunwale), {g.rail:.1f} out", anchor="start", size=2.0)
    s.text(*P(g.loa + 25, -g.yc - 6), "FWD", 2.6, "start", bold=True)
    s.add(f'<line class="dim" x1="{P(g.loa + 25, 0)[0]:.2f}" y1="{P(0, -g.yc)[1]:.2f}" '
          f'x2="{P(g.loa + 95, 0)[0]:.2f}" y2="{P(0, -g.yc)[1]:.2f}" marker-end="url(#a)"/>')
    top = P(0, -g.yc - g.beam / 2 - g.rail)[1]
    bot = P(0, g.yc + g.beam / 2 + g.rail)[1]
    s.dim_h(*P(0, -g.yc - hb(h, 0) - g.rail), *P(g.loa, -g.yc - hb(h, g.loa)), top - 6, g.loa)
    s.dim_h(*P(g.aft_end, -g.yc - g.prop_d / 2), *P(g.loa, -g.yc - hb(h, g.loa)), top - 12,
            g.loa_all, f"{g.loa_all:.0f} incl. drives")
    s.dim_h(*P(0, g.yc + hb(h, 0) + g.rail), *P(g.fx[0], g.yc), bot + 6, g.fx[0], f"{g.fx[0]:.0f} frame")
    s.dim_h(*P(g.fx[0], g.yc), *P(g.fx[1], g.yc), bot + 6, g.fx[1] - g.fx[0])
    s.dim_h(*P(0, g.yc + hb(h, 0) + g.rail), *P(g.hub_x, 0), bot + 12, g.hub_x, f"{g.hub_x:.0f} hub / mast / winch")
    s.dim_h(*P(g.hub_x - g.hub_ax, 0), *P(g.hub_x + g.hub_ax, 0), P(0, -g.hub_ay + 45)[1], 2 * g.hub_ax)
    xr = P(g.loa, 0)[0] + 10
    width_rails = mm(g.boat.overall_width) + 2 * g.rail
    s.dim_v(*P(g.loa - 240, -g.yc - hb(h, g.loa - 240) - g.rail), *P(g.loa - 240, g.yc + hb(h, g.loa - 240) + g.rail),
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
    for i, xj in enumerate(g.joints, start=1):
        s.line(*Q(xj, keel(h, xj)), *Q(xj, g.depth), "joint")
        s.text(*Q(xj + 8, g.depth - 28), f"J{i}", 1.9, "start", cls="red")
    for z, cls in ((g.dwl, "wl"), (g.drafts[0], "wlt"), (g.drafts[2], "wlt")):
        s.line(*Q(-180, z), *Q(g.loa + 40, z), cls)
    s.text(*Q(1060, g.dwl + 14), f"DWL {g.dwl:.0f} ({g.conds[1].total:.1f} kg)", 2.0, "start", cls="blue")
    s.rect(*Q(g.xc - g.shoe_len / 2, g.depth), *Q(g.xc + g.shoe_len / 2, g.depth + SHOE_H), "vis")
    zc = [(sc, z) for sc, z in g.hub_side()]
    s.poly([Q(g.hub_x - g.hub_ax * sc, z) for sc, z in zc] + [Q(g.hub_x + g.hub_ax * sc, z) for sc, z in reversed(zc)],
           "vis", closed=True)
    s.rect(*Q(g.hub_x - g.box[0] / 2, g.box_z0), *Q(g.hub_x + g.box[0] / 2, g.box_z0 + g.box[2]), "hid")
    for fxx in g.fx:
        s.rect(*Q(fxx - g.frame_t / 2, g.foot_z), *Q(fxx + g.frame_t / 2, g.box_z0), "hid")
    s.line(*Q(g.hub_x, g.dome_z(g.hub_x, 0)), *Q(g.hub_x, g.mast_top - 45), "vis")
    s.rect(*Q(g.hub_x - 75, g.mast_top - 45), *Q(g.hub_x + 75, g.mast_top), "vis")
    s.line(*Q(g.hub_x + 8, g.dome_z(g.hub_x, g.whip_y)), *Q(g.hub_x + 8, g.mast_top), "thin")
    bar_x = g.hub_x + g.hub_ax - 60
    bz = g.dome_z(bar_x, 0) + 10
    s.rect(*Q(bar_x - 16, bz - 16), *Q(bar_x + 16, bz + 16), "vis")
    s.rect(*Q(g.hub_x - POD[0] / 2, g.pod_z0), *Q(g.hub_x + POD[0] / 2, g.pod_z1), "hid")
    s.line(*Q(g.hub_x, g.pod_z1), *Q(g.hub_x, g.hub_z[0]), "hid")
    drive_profile(s, g, Q, k)
    s.line(*Q(-190, g.prop_z), *Q(20, g.prop_z), "ctr")
    s.line(*Q(-200, 0), *Q(g.loa + 30, 0), "ctr")
    s.text(*Q(g.loa + 32, -4), "BL", 2.0, "start")
    s.text(*Q(10, 330), "J1-J4: tub + lid joints (sheet 2)", 2.0, "start", cls="red")
    s.leader(*Q(900, g.rail_z[1]), Q(960, 0)[0], Q(0, 330)[1], f"rail / lid joint z {g.zj:.0f} (sheet 4)",
             size=2.0)
    xl = Q(-200, 0)[0] - 3
    s.dim_v(*Q(g.aft_end, 0), *Q(g.aft_end, g.dwl), xl, g.dwl)
    s.dim_v(*Q(g.prop_xa, g.prop_bottom), *Q(g.aft_end, g.dwl), xl - 7, g.total_draft,
            f"{g.total_draft:.0f} total draft")
    s.dim_v(*Q(0, 0), *Q(0, g.depth), xl - 14, g.depth)
    s.dim_v(*Q(0, 0), *Q(-g.rail, g.zj), xl - 21, g.zj, f"{g.zj:.0f} joint")
    xr2 = Q(g.loa, 0)[0] + 6
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
        half = section_points(h, 0.6)
        ring = [(mm(y), mm(z)) for y, z in half] + [(-mm(y), mm(z)) for y, z in reversed(half[1:-1])]
        s.poly([R(yc + y, z) for y, z in ring], "vis", closed=True)
        t_half = section_points(h, 0.0)
        s.poly([R(yc + mm(y), mm(z)) for y, z in t_half[:17]], "thin")
        s.poly([R(yc - mm(y), mm(z)) for y, z in t_half[:17]], "thin")
        s.rect(*R(yc - g.beam / 2 - g.rail, g.rail_z[0]), *R(yc + g.beam / 2 + g.rail, g.rail_z[1]), "vis")
        drive_astern(s, g, R, k, yc)
        s.rect(*R(yc - g.shoe_w / 2, g.depth), *R(yc + g.shoe_w / 2, g.depth + SHOE_H), "vis")
        s.line(*R(yc, -60), *R(yc, g.depth + 80), "ctr")
        up = [(sgn * y, z) for y, z in g.arm_up if abs(y) >= g.hub_ay * 0.95]
        lo = [(sgn * y, z) for y, z in g.arm_lo if abs(y) >= g.hub_ay * 0.95]
        s.poly([R(y, z) for y, z in up], "vis")
        s.poly([R(y, z) for y, z in lo], "vis")
    zc = g.hub_side()
    s.poly([R(-g.hub_ay * sc, z) for sc, z in zc] + [R(g.hub_ay * sc, z) for sc, z in reversed(zc)], "vis", closed=True)
    s.rect(*R(-g.box[1] / 2, g.box_z0), *R(g.box[1] / 2, g.box_z0 + g.box[2]), "hid")
    s.poly([R(y, z) for y, z in g.frame], "hid", closed=True)
    s.line(*R(0, g.hub_z[2]), *R(0, g.mast_top - 45), "vis")
    s.rect(*R(-75, g.mast_top - 45), *R(75, g.mast_top), "vis")
    for wy in (-g.whip_y, g.whip_y):
        s.line(*R(wy, g.dome_z(g.hub_x, wy)), *R(wy, g.mast_top), "vis")
    s.rect(*R(-POD[1] / 2, g.pod_z0), *R(POD[1] / 2, g.pod_z1), "vis")
    s.line(*R(0, g.pod_z1), *R(0, g.hub_z[0]), "thin")
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
    upper = design.total - 2 * g.tub_kg
    s.text(216, 20, "MODULES", 3.0, "start", bold=True)
    s.table(216, 23, ["Module", "Design kg", "Contents"], [
        ["Port tub", f"{g.tub_kg:.1f}", f"5 printed segments + bulkheads, flange with {g.n_screws} M4 inserts, "
                                         "leak sensor. Bare float: no hardware"],
        ["Stbd tub", f"{g.tub_kg:.1f}", "mirror of the port tub"],
        ["Upper module", f"{upper:.1f}", "bridge (arch frames, arms, hub: 4x M18, VESCs, Pi 5, radios, winch, pod) "
                                         "+ 2 lids + 2 belt outdrives"],
        ["Boat", f"{design.total:.1f}", f"incl. {MARGIN:.0%} growth margin"],
    ], [26, 20, 148])
    s.lines_of_text(216, 52, [
        "ASSEMBLY",
        f"1. Bolt each foot to its lid from inside: {4 * len(g.bolt_y)}x M6 x {BOLT_L:.0f} up through the rib bosses, EPDM pad between.",
        "2. Bolt each outdrive to its lid's aft deck: 4x M5 from inside.",
        f"3. Press the {mm(g.lid.gasket_d):.0f} mm cord into each tub's flange groove.",
        "4. Lower the bridge + lids onto the tubs; the drip lips locate on the tub flanges.",
        f"5. Screw down the rails: {g.n_screws} M4 per hull, {mm(g.lid.screw_pitch_near):.0f} mm pitch "
        f"within 150 mm of a frame, {mm(g.lid.screw_pitch):.0f} elsewhere.",
        "6. Plug each motor cable into its arm's IP68 connector. Nothing passes through a lid or tub.",
        "",
        f"Waterlines: DWL {g.dwl:.0f} at {design.total:.1f} kg; thin blue = light "
        f"{g.drafts[0]:.0f} / max {g.drafts[2]:.0f}. Lid joint {g.zj - g.dwl:.0f} above the DWL.",
        "Lids, drives and bridge lift off as one unit; the hub keeps the electronics clear of spray.",
        "Geometry comes from mechanical/hull_sizing.py; regenerate after changes.",
    ], size=2.3, lead=3.5, bold_first=True)
    return s


# ---- sheet 2: demi-hull lines and construction --------------------------------------------


def sheet_lines(g: Geo) -> Sheet:
    s = Sheet(2, "Demi-hull lines, lid joint plane, print segments, offsets and fillets", "1:5 / 1:2.5")
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
    for i, xj in enumerate(g.joints, start=1):
        s.line(*Q(xj, keel(h, xj) - 5), *Q(xj, g.depth + 5), "joint")
        s.text(*Q(xj, -24), f"J{i}", 2.0, cls="red")
    for z, cls in ((g.dwl, "wl"), (g.drafts[0], "wlt"), (g.drafts[2], "wlt")):
        s.line(*Q(-40, z), *Q(g.loa + 30, z), cls)
    s.text(*Q(g.loa + 32, g.dwl - 4), f"DWL {g.dwl:.0f}", 2.0, "start", cls="blue")
    s.text(*Q(g.loa + 32, g.drafts[2] + 8), f"max {g.drafts[2]:.0f}", 1.8, "start", cls="blue")
    s.text(*Q(g.loa + 32, g.drafts[0] - 16), f"light {g.drafts[0]:.0f}", 1.8, "start", cls="blue")
    s.rect(*Q(g.xc - g.foot_len / 2, g.depth), *Q(g.xc + g.foot_len / 2, g.foot_z), "ph")
    s.line(*Q(-45, 0), *Q(g.loa + 30, 0), "ctr")
    ytop = Q(0, g.depth)[1] - 10
    marks = [0.0] + g.joints + [g.loa]
    for a, b in zip(marks, marks[1:]):
        s.dim_h(*Q(a, g.depth), *Q(b, g.depth), ytop, b - a)
    s.dim_h(*Q(0, g.depth), *Q(g.loa, g.depth), ytop - 7, g.loa)
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
    for xj in g.joints:
        s.line(*P(xj, -hb(h, xj)), *P(xj, hb(h, xj)), "joint")
    s.rect(*P(g.xc - g.foot_len / 2, -g.foot_w / 2), *P(g.xc + g.foot_len / 2, g.foot_w / 2), "ph")
    for fxx in g.fx:
        for yy in g.bolt_y:
            for sgn in (-1, 1):
                s.circle(*P(fxx + g.bolt_dx, sgn * yy), 3.3 * k, "vis")
    s.circle(*P(VENT_X, 0), 10 * k, "thin")
    s.leader(*P(VENT_X + 6, 6), P(VENT_X + 50, 0)[0], P(0, 118)[1], "M12 IP68 membrane vent (in the lid)", size=2.0)
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

    for xs_, side in ((AFT_STATIONS, -1), (FWD_STATIONS, 1)):
        for i, x in enumerate(xs_):
            pts = section_points(h, x / 1000)
            c = STATION_COLOURS[x]
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
    s.text(*B(-118, -22), "labels = mm fwd of transom; sheet 5 draws each slice on its own, same colours", 1.8,
           "start")
    s.view_title(Xb, B(0, 0)[1] + 16, "BODY PLAN (with fillets)", "1:2.5")

    s.text(20, 209, "OFFSETS (sharp chine; mm from transom / baseline / hull centreline)", 2.7, "start", bold=True)
    rows = []
    for x in [0, 130, 260, 390, 520, 650, 780, 910, 1000, 1100, 1170, 1250, 1300]:
        rows.append([f"{x}", f"{keel(h, x):.1f}", f"{chine(h, x):.1f}", f"{hb(h, x):.1f}",
                     f"{mm(h.fillet(x / 1000)[0]):.0f} / {mm(h.deck_fillet(x / 1000)):.0f}"])
    half = (len(rows) + 1) // 2
    heads = ["x", "keel z", "chine z", "half-breadth", "R chine / deck"]
    s.table(20, 212, heads, rows[:half], [12, 14, 14, 20, 22], 2.0, 4.0)
    s.table(108, 212, heads, rows[half:], [12, 14, 14, 20, 22], 2.0, 4.0)

    lid = g.lid
    gw, gd = (mm(v) for v in lid.groove)
    s.lines_of_text(200, 198, [
        "CONSTRUCTION (open tub + removable lid)",
        f"- Loft the sharp-chine hull from the offsets, fillet chine R{mm(h.chine_r):.0f} and deck edge R{mm(h.deck_r):.0f} "
        "(0.45 x half-breadth near the stem),",
        f"  then split the body at the lid joint plane z {g.zj:.0f}: tub below, lid above.",
        f"- PETG or ASA, {g.wall:.1f} wall. Glass (200 g/m2 + epoxy) the tub and the lid separately, up to the flanges.",
        f"- Tub: {h.segments} x {g.seg:.0f} segments, each printed on its aft {mm(h.bulkhead_t):.1f} bulkhead; "
        f"bulkheads stop {mm(lid.bulkhead_gap):.0f} under the joint plane.",
        f"- Lid: {h.segments} x {g.seg:.0f} segments printed on end; lid segments 3 and 4 stand on their "
        f"{mm(lid.rib_t):.0f} mm ribs (J2 / J3) with the foot-bolt bosses.",
        "- Joints J1-J4: 8 mm half-lap spigots on the tub and on the lid (sheet 3).",
        f"- Rail: {g.fw:.0f} mm flanges, {mm(lid.gasket_d):.0f} mm cord in a {gw:.0f} x {gd:.1f} groove, {g.n_screws}x M4 "
        f"into M4 x {INSERT[1]:.1f} heat-set inserts in {INSERT_BOSS[0]:.0f} mm bosses under the tub flange (sheet 4).",
        "- One sealed space per hull: leak sensor at its lowest point (Boat PCB J15 / J16), M12 vent in the lid.",
        f"- Shell {shell_mass(h):.1f} kg per hull incl. bulkheads, ribs and stiffeners, + {lid_joint_mass(h):.1f} kg rail.",
    ], size=2.0, lead=3.2, bold_first=True)
    return s


# ---- sheet 3: bridge and joint details -------------------------------------------------------


def lid_rib_section(s: Sheet, g: Geo, X: float, Y: float, k: float) -> None:
    """Lid cut through the foot-bolt axes at J2 / J3, looking forward (hull CL at X, z 250 at Y)."""
    h = g.hull

    def L(y, z):
        return X + y * k, Y - (z - g.depth) * k

    x = (g.fx[0] + g.bolt_dx) / 1000
    half = [(mm(y), mm(z)) for y, z in section_points(h, x, part="lid")]
    outer = half + [(-y, z) for y, z in reversed(half[:-1])]
    inner = offset_polyline(outer, g.wall)
    hbx = half[0][0]
    s.poly([L(y, z) for y, z in outer + list(reversed(inner))], "cut", closed=True)
    s.poly([L(y, z) for y, z in inner], "cut", closed=True)  # the rib fills the lid here
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
    s.leader(*L(-20, g.zj + 30), xl, L(0, g.depth - 6)[1], f"RIB {mm(g.lid.rib_t):.0f} thick (lid seg 3 / 4 base)",
             "end", 1.9)
    s.leader(*L(-ya + CBORE[0] / 2, g.zj + 4), xl, L(0, g.zj + 2)[1],
             f"counterbore {CBORE[0]:.0f} dia x {CBORE[1]:.0f} for the head", "end", 1.9)
    s.leader(*L(-50, g.depth - 1), xl, L(0, g.depth + 8)[1], f"lid {g.wall:.0f} wall", "end", 1.9)
    s.leader(*L(g.foot_w / 2 - 6, g.foot_z - 2), xr + 16, L(0, g.foot_z + 10)[1], f"foot {g.foot_t:.0f} mm 6061",
             size=1.9)
    s.leader(*L(g.foot_w / 2 - 14, g.depth + 0.7), xr + 16, L(0, g.depth + 3)[1], f"EPDM pad {g.pad_t:.1f}", size=1.9)
    s.leader(*L(hbx + 6, g.zj + 2), xr + 16, L(0, g.zj + 12)[1], "rail (sheet 4)", size=1.9)
    s.leader(*L(hbx - 1, g.zj - 16), xr + 16, L(0, g.zj - 14)[1], f"tub (bulkhead {mm(g.lid.bulkhead_gap):.0f} below)",
             size=1.9)
    s.text(X, L(0, g.foot_z + 28)[1] + 3.5, "arch frame (phantom)", 1.8)


def sheet_details(g: Geo) -> Sheet:
    s = Sheet(3, "Arch frame, foot plate, lid rib, hub layout, segment joint", "as noted")
    # arch frame plate, 1:5, seen from ahead (y horizontal, z up)
    k = 0.2
    X0, Z0 = 112.0, 62.0

    def F(y, z):
        return X0 + y * k, Z0 - (z - 250.0) * k

    s.poly([F(y, z) for y, z in g.frame], "plate", closed=True)
    hub_c = g.box_z0 - g.frame_h / 2
    for y, d in LIGHTENING:
        s.circle(*F(y, hub_c), d / 2 * k, "vis")
    for y in BOX_HOLES_Y:
        s.circle(*F(y, g.box_z0 - 12), 2.75 * k * 1.3, "vis")
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

    # lid rib at J2 / J3, 1:2.5, top right
    kr = 0.4
    Xr, Yr = 318.0, 56.0
    lid_rib_section(s, g, Xr, Yr, kr)
    s.view_title(Xr + 8, Yr + (g.depth - g.zj + 22) * kr + 13, "LID RIB AT J2 / J3 (SECTION, LOOKING FWD)", "1:2.5")

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
    s.text(T(0, 0)[0], T(0, Wd / 2)[1] + 14.3, "(bolts come up from inside the lid); 2x 5.5 per angle bracket", 1.9)
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

    # hub layout, 1:10: plan + side
    k10 = 0.1
    Xh, Yh = 250.0, 124.0

    def HP(x, y):
        return Xh + (x - g.hub_x) * k10, Yh + y * k10

    s.poly([HP(g.hub_x + px, py) for px, py in superellipse(g.hub_ax, g.hub_ay, g.boat.hub_e)], "orange", closed=True)
    bx, by, bz = g.box
    s.rect(*HP(g.hub_x - bx / 2, -by / 2), *HP(g.hub_x + bx / 2, by / 2), "hid")
    for fxx in g.fx:
        s.line(*HP(fxx, -g.hub_ay), *HP(fxx, g.hub_ay), "hid")
    s.circle(*HP(g.hub_x, 0), 1.1, "vis")
    for wy in (-g.whip_y, g.whip_y):
        s.circle(*HP(g.hub_x, wy), 0.8, "vis")
    s.circle(*HP(g.hub_x - 100, -70), 1.4, "vis")
    bar_x = g.hub_x + g.hub_ax - 60
    s.rect(*HP(bar_x - 16, -180), *HP(bar_x + 16, 180), "vis")
    s.dim_h(*HP(g.hub_x - g.hub_ax, g.hub_ay), *HP(g.hub_x + g.hub_ax, g.hub_ay), HP(0, g.hub_ay)[1] + 5, 2 * g.hub_ax)
    s.dim_v(*HP(g.hub_x + g.hub_ax, -g.hub_ay), *HP(g.hub_x + g.hub_ax, g.hub_ay), HP(g.hub_x + g.hub_ax, 0)[0] + 5,
            2 * g.hub_ay)
    s.text(HP(g.hub_x, 0)[0], HP(0, -g.hub_ay)[1] - 2, "box dashed, frames hidden", 1.8)
    Xs, Zs = 322.0, 144.0

    def HS(x, z):
        return Xs + (x - g.hub_x) * k10, Zs - (z - g.hub_z[0]) * k10

    zc = g.hub_side()
    s.poly([HS(g.hub_x - g.hub_ax * sc, z) for sc, z in zc] + [HS(g.hub_x + g.hub_ax * sc, z) for sc, z in reversed(zc)],
           "orange", closed=True)
    s.rect(*HS(g.hub_x - bx / 2, g.box_z0), *HS(g.hub_x + bx / 2, g.box_z0 + bz), "hid")
    s.rect(*HS(g.hub_x - POD[0] / 2, g.pod_z1 - 40), *HS(g.hub_x + POD[0] / 2, g.pod_z1), "ph")
    s.line(*HS(g.hub_x, g.hub_z[2]), *HS(g.hub_x, g.hub_z[2] + 40), "vis")
    for z, lab in ((g.hub_z[0], f"{g.hub_z[0]:.0f} bottom"), (g.hub_z[1], f"{g.hub_z[1]:.0f} belt"),
                   (g.hub_z[2], f"{g.hub_z[2]:.0f} top")):
        s.line(*HS(g.hub_x + g.hub_ax + 3, z), *HS(g.hub_x + g.hub_ax + 60, z), "dimx")
        s.text(*HS(g.hub_x + g.hub_ax + 62, z - 3), lab, 1.8, "start")
    s.text((Xh + Xs) / 2, HS(0, g.hub_z[0])[1] + 8, f"IP67 box {bx:.0f} x {by:.0f} x {bz:.0f} on the frame tops "
           f"(z {g.box_z0:.0f})", 1.8)
    s.view_title((Xh + Xs) / 2, HS(0, g.hub_z[0])[1] + 14, "HUB COWL LAYOUT (PLAN + SIDE)", "1:10")

    # segment joint 2:1
    k3 = 2.0
    Xj, Yj = 66.0, 222.0

    def J(x, n):
        return Xj + x * k3, Yj - n * k3

    s.poly([J(-24, 0), J(-23, 0), J(-21, -2), J(-8, -2), J(-8, 0), J(0, 0), J(0, 2), J(-24, 2)], "cut", closed=True)
    s.poly([J(22, 2), J(0, 2), J(0, 0), J(-8, 0), J(-8, -2), J(15, -2), J(17, 0), J(22, 0)], "cut", closed=True)
    s.rect(*J(-8, -2), *J(-5.6, -11), "cut")
    s.poly([J(-24, 2), J(22, 2), J(22, 2.35), J(-24, 2.35)], "glass", closed=True)
    s.text(*J(0, 8), "OUTSIDE (glass skin over the joint)", 1.8)
    s.text(*J(-19, 4.2), "aft segment", 1.8)
    s.text(*J(12, 4.2), "fwd segment", 1.8)
    s.text(*J(-17, -8.5), "INSIDE", 1.8)
    s.text(*J(-4.5, -9.5), "bulkhead / rib of the fwd segment (printed on the bed)", 1.8, "start")
    s.leader(*J(-4, 1.8), J(-10, 0)[0], J(0, 6)[1], "8 lap, epoxy", anchor="end", size=1.9)
    s.dim_v(*J(22, 0), *J(22, 2), J(22, 0)[0] + 3, 2.0, "2.0")
    s.dim_v(*J(-16, -2), *J(-16, 2), J(-24, 0)[0] - 3, 4.0, "4.0")
    s.dim_h(*J(-8, -2), *J(0, -2), J(0, -2)[1] + 4, 8)
    s.dim_h(*J(0, -2), *J(15, -2), J(0, -2)[1] + 4, 15)
    s.view_title(Xj, Yj + 30, "SEGMENT JOINT, TUB + LID (45° chamfers print unsupported)", "2:1")

    s.text(222, 170, "HARDWARE (whole boat)", 2.8, "start", bold=True)
    s.table(222, 173, ["Qty", "Item"], [
        ["2", "Arch frame plate, 1/4 in 6061-T6, laser / waterjet cut (DXF)"],
        ["2", f"Foot plate, {g.foot_t:.0f} mm 6061, {g.foot_len:.0f} x {g.foot_w:.0f}, {4 * len(g.bolt_y)}x M6 tapped"],
        ["4", "Angle bracket 25 x 25 x 3 Al, 40 long (frame to foot)"],
        [f"{8 * len(g.bolt_y)}", f"M6 x {BOLT_L:.0f} A4 socket cap + M6 bonded seal washer (feet, from inside)"],
        ["2", f"EPDM pad {g.pad_t:.1f} mm, {g.foot_len:.0f} x {g.foot_w:.0f} (under each foot)"],
        [f"{2 * g.n_screws}", f"M4 x 12 A4 pan head + washer, and M4 x {INSERT[1]:.1f} brass heat-set insert (rails)"],
        ["2", f"{mm(g.lid.gasket_d):.0f} mm EPDM / silicone cord, {g.rail_len:.2f} m (one loop per tub)"],
        ["1", "Hub cowl, 2 arm fairings, 2 foot shoes (printed PETG / ASA)"],
        ["1", f"IP67 box ~{g.box[0]:.0f} x {g.box[1]:.0f} x {g.box[2]:.0f}, glands, 2 IP68 motor connectors"],
        ["2", "Belt outdrive, complete (sheet 4)"],
        ["2", "M12 IP68 membrane vent (one per lid)"],
        ["2", "Leak sensor at each tub's lowest point (Boat PCB J15 / J16)"],
    ], [12, 108], 1.95, 3.6)

    lc_worst = max(g.lcs, key=lambda lc: lc.moment)
    zsec = g.boat.frame_t * g.boat.frame_h**2 / 6
    bolt_sf, rib_sf, rail_sf = (cap / load for _, _, load, cap, _ in g.checks)
    s.lines_of_text(347, 173, [
        "LOAD PATH",
        "Each frame is a portal fixed at its feet.",
        f"Worst case: {lc_worst.name.split(' (')[0].split(' ', 1)[1]}",
        f"{lc_worst.moment:.0f} N m per frame -> {lc_worst.moment / zsec / 1e6:.0f} MPa,",
        f"SF {276e6 / (lc_worst.moment / zsec):.1f} on 6061-T6 yield.",
        f"Foot: pivots on its far edge; the {4 * len(g.bolt_y)}",
        f"M6 in the rib bosses hold it: SF {bolt_sf:.1f}.",
        f"Lid rib carries it to the rail: SF {rib_sf:.1f}.",
        f"Rail: 3 M4 inserts per frame: SF {rail_sf:.1f}.",
        "Nothing goes through a tub: all",
        "hardware bolts to the lids.",
        "Details: docs/hull_and_crossbeam_sizing.md",
    ], size=1.9, lead=3.1, bold_first=True)
    return s


# ---- sheet 4: rail joint and belt outdrive -------------------------------------------------


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


def sheet_lid_drive(g: Geo) -> Sheet:
    s = Sheet(4, "Hull lid joint (rail) and belt outdrive", "as noted")
    rail_joint(s, g, 90.0, 80.0, 4.0)
    s.view_title(90.0, 160.0, "RAIL: LID OVER THE GUNWALE (SECTION THROUGH A SCREW)", "4:1")

    # belt outdrive, 1:4, from starboard
    k = 0.25
    X0, Y0 = 345.0, 146.0

    def Q(x, z):
        return X0 + x * k, Y0 - z * k

    h = g.hull
    xs = [0.0, 20.0, 40.0, 60.0, 80.0, 100.0]
    s.poly([Q(100, g.depth), Q(0, g.depth), Q(0, keel(h, 0))] + [Q(x, keel(h, x)) for x in xs], "vis")
    s.poly([Q(100, g.depth + 4), Q(97, g.depth - 3), Q(103, g.depth - 12), Q(100, keel(h, 100) - 4)], "thin")
    s.rect(*Q(-g.rail, g.rail_z[0]), *Q(100, g.rail_z[1]), "vis")
    drive_profile(s, g, Q, k, detail=True)
    arc = g.kick_arc()
    s.poly([Q(x, z) for x, z in arc], "ph")
    ax, az = arc[-1]
    s.text(*Q(ax + 8, az + 12), f"kicks up ~{TILT_DEG:.0f}° about the pin", 1.9, "start")
    s.line(*Q(-185, g.dwl), *Q(100, g.dwl), "wl")
    s.text(*Q(102, g.dwl - 3), f"DWL {g.dwl:.0f}", 1.8, "start", cls="blue")
    s.line(*Q(-185, 0), *Q(100, 0), "ctr")
    s.text(*Q(102, -4), "BL", 1.8, "start")
    s.line(*Q(-170, g.prop_z), *Q(-10, g.prop_z), "ctr")
    s.line(*Q(-90, g.motor_z), *Q(15, g.motor_z), "ctr")
    s.line(*Q(g.belt_x, g.prop_z - 20), *Q(g.belt_x, g.motor_z + 20), "ctr")
    for xa in (g.leg_x[0] - 12, g.leg_x[1] + 8):  # cutting plane A-A
        s.line(*Q(xa, SECTION_Z), *Q(xa + 4, SECTION_Z), "vis")
    s.line(*Q(g.leg_x[0] - 8, SECTION_Z), *Q(g.leg_x[1] + 8, SECTION_Z), "ctr")
    s.text(*Q(g.leg_x[0] - 16, SECTION_Z - 3), "A", 2.4, bold=True)
    s.text(*Q(g.leg_x[1] + 14, SECTION_Z - 3), "A", 2.4, bold=True)
    xr = Q(100, 0)[0] + 8
    s.dim_v(*Q(0, 0), *Q(-10, g.prop_z), xr, g.prop_z, f"{g.prop_z:.0f} prop axis")
    s.dim_v(*Q(g.belt_x, g.prop_z), *Q(g.belt_x, g.motor_z), xr + 8, g.centres, f"{g.centres:.0f} belt centres")
    s.dim_v(*Q(0, 0), *Q(15, g.motor_z), xr + 16, g.motor_z, f"{g.motor_z:.0f} motor axis")
    s.dim_v(*Q(g.prop_xa, g.prop_bottom), *Q(g.prop_xa, g.prop_bottom + g.prop_d), Q(g.aft_end, 0)[0] - 4,
            g.prop_d, f"{g.prop_d:.0f} prop")
    s.dim_v(*Q(g.pod_x[1] + 20, g.prop_z - g.pod_d / 2), *Q(g.pod_x[1] + 20, g.prop_z + g.pod_d / 2),
            Q(g.pod_x[1], 0)[0] + 3, g.pod_d, f"{g.pod_d:.0f}")
    yb = Q(0, g.prop_bottom)[1] + 5
    s.dim_h(*Q(g.leg_x[0], g.leg_z[0]), *Q(g.leg_x[1], g.leg_z[0]), yb, g.leg_x[1] - g.leg_x[0],
            f"{g.leg_x[1] - g.leg_x[0]:.0f} leg")
    s.dim_h(*Q(g.leg_x[1], 215), *Q(-g.rail, g.rail_z[1]), Q(0, 215)[1], g.leg_x[1] + g.rail,
            f"{-g.rail - g.leg_x[1]:.1f}")
    s.text(*Q(g.belt_x - 8, 205), f"{g.teeth} T", 1.8, "end")
    s.leader(*Q(40, g.rail_z[1]), Q(55, 0)[0], Q(0, 225)[1], "rail", size=1.9)
    bx = -230.0  # balloon column, inside the kick-up arc
    s.balloon(*Q(g.motor_x[0] + 4, g.motor_z + 12), *Q(bx, 330), 1)
    s.balloon(*Q(g.belt_x - PULLEY[1] / 2, g.motor_z - 4), *Q(bx, 305), 2)
    s.balloon(*Q(g.belt_x - PULLEY[1] / 2, g.prop_z + 4), *Q(bx, 45), 2)
    s.balloon(*Q(g.belt_x - g.belt_w / 2, 200), *Q(bx, 205), 3)
    s.balloon(*Q(g.prop_xf + 1, g.prop_z + 1), *Q(bx, 20), 4)
    s.balloon(*Q(g.bearings[1][0] + 2, g.prop_z + 5), *Q(bx, 70), 5)
    s.balloon(*Q(g.aft_end + 2, g.prop_z - 3), *Q(-205, -15), 6)
    s.balloon(*Q(g.pivot[0] - 2, g.pivot[1] - 2), *Q(bx, 272), 7)
    s.balloon(*Q(g.bracket_x - 15, g.depth + BRACKET_H - 2), *Q(62, 290), 8)
    s.balloon(*Q(g.cover_x[0] + 20, g.cover_z[1]), *Q(-120, 362), 9)
    s.balloon(*Q(g.leg_x[0] + 2, 120), *Q(bx, 150), 9)
    s.balloon(*Q(g.prop_xa + 6, g.prop_z + 40), *Q(bx, 100), 10)
    s.view_title(Q(-40, 0)[0], Q(0, g.prop_bottom)[1] + 16, "BELT OUTDRIVE (FROM STARBOARD)", "1:4")

    leg_section(s, g, 104.0, 206.0, 2.0)
    s.view_title(104.0, 255.0, "SECTION A-A (THROUGH THE LEG)", "2:1")

    s.text(200, 180, "OUTDRIVE PARTS (per drive; 2 req)", 2.8, "start", bold=True)
    s.table(200, 183, ["No.", "Qty", "Item"], [
        ["1", "1", f"Outrunner ~{g.drive.kv:.0f} KV, 4108 size, >= 25 A (e.g. SunnySky X4108S-380KV), "
                   "on the slotted motor plate"],
        ["2", "2", f"HTD 3M pulley, {g.drive.pulley_teeth}T ({g.pd:.1f} PD), for a {g.belt_w:.0f} mm belt, "
                   "5 mm bore + set screw"],
        ["3", "1", f"HTD 3M belt, {g.belt_w:.0f} mm, {g.teeth} T ({g.teeth * mm(g.drive.belt_pitch):.0f} mm); "
                   "15 mm belt + pulleys for long runs at 3 m/s"],
        ["4", "1", f"316 stainless shaft {g.shaft_d:.0f} mm, D-flat under the prop, M5 thread for the nylock"],
        ["5", "2", "625-2RS bearing, stainless (5 x 16 x 5)"],
        ["6", "1", "M5 nylock A4 + washer"],
        ["7", "1", "Tilt pin M6 A4 + 2 flanged bushings; spring-plunger detent that holds reverse thrust"],
        ["8", "4", "M5 x 20 A4 + washers: bracket to the lid deck, from inside the lid"],
        ["9", "1", "Printed in ASA: bracket, tilt head, cover, leg halves (M3 screws), pod"],
        ["10", "1", f"Prop {g.prop_d:.0f}: props/toroidal_3loop_p75_RH_shaft (stbd) / _LH_shaft (port), "
                    "or a 110 mm RC prop"],
    ], [9, 9, 202], 1.95, 3.6)

    s.lines_of_text(236, 18, [
        "OUTDRIVE NOTES",
        "- The leg and pod free-flood, so the belt and both bearings run wet: stainless bearings, a PU belt with aramid "
        "or stainless cords, and a fresh-water rinse after use.",
        "- Tension the belt by sliding the motor up its slotted plate. The whole drive tilts about the pin, so a kick-up "
        "doesn't change the tension.",
        "- Forward thrust holds the leg on its rubber stop; the detent holds it against reverse thrust (differential "
        "steering) and lets go when the leg hits something.",
        "- The leg is split on its chord plane so the belt goes in whole. Motor wires run up the arm fairing to the hub; "
        "nothing passes through the lid.",
        f"- Stbd prop RH, port prop LH (tops turn outboard). A {g.belt_w:.0f} mm belt is near its rating at full speed; "
        "cruise is well inside it.",
    ], size=1.9, lead=3.1, bold_first=True)
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
    for z in (g.hub_z[0], g.box_z0, g.hub_z[1], (g.hub_z[1] + g.hub_z[2]) / 2, g.hub_z[2] - 10):
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
    hub_c = g.box_z0 - g.frame_h / 2
    holes = [(y, hub_c, d / 2) for y, d in LIGHTENING]
    holes += [(y, g.box_z0 - 12, 2.75) for y in BOX_HOLES_Y]
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


# ---- sheet 5: the body plan, one slice at a time ---------------------------------------------


def sheet_sections(g: Geo) -> Sheet:
    s = Sheet(5, "Hull sections one at a time: a reading aid for the body plan", "1:6 / sketch")
    h = g.hull

    def ring(x: float) -> list[tuple[float, float]]:
        """Full section, both halves, at station x (mm)."""
        half = [(mm(y), mm(z)) for y, z in section_points(h, x / 1000)]
        return half + [(-y, z) for y, z in reversed(half[1:-1])]

    # 3D sketch: cabinet oblique, the far (stbd) side drawn up and to the right at 30 deg, half scale
    k3, X3, Y3 = 0.15, 34.0, 72.0
    ca, sa = 0.5 * math.cos(math.radians(30)), 0.5 * math.sin(math.radians(30))

    def O(x, y, z):
        return X3 + k3 * (x + ca * y), Y3 - k3 * (z + sa * y)

    xs = stations(h, 20)
    wire = "stroke:#8c8c8c"  # light hull lines, so the coloured slices stand out
    for sgn in (1, -1):  # top of each straight side
        s.poly([O(x, sgn * hb(h, x), g.depth - mm(h.deck_fillet(x / 1000))) for x in xs], "thin", style=wire)
    s.poly([O(x, 0, keel(h, x)) for x in xs], "thin", style=wire)
    s.poly([O(x, 0, g.depth) for x in xs], "thin", style=wire)
    for i, x in enumerate(STATION_COLOURS):  # stern first: the nearer slices draw over the farther
        c = STATION_COLOURS[x]
        s.poly([O(x, y, z) for y, z in ring(x)], "vis", closed=True, style=f"stroke:{c};fill:{c};fill-opacity:0.16")
        s.text(*O(x, 0, g.depth + 24 + 30 * (i % 2)), f"{x:.0f}", 1.9, bold=True, color=c)
    s.text(*O(0, -hb(h, 0), -38), "TRANSOM", 1.9)
    s.text(*O(g.loa + 25, 0, keel(h, g.loa) + 40), "BOW", 1.9, "start")
    ya = O(0, 0, -45)[1]
    s.add(f'<line class="dim" x1="{O(900, 0, 0)[0]:.2f}" y1="{ya:.2f}" x2="{O(1150, 0, 0)[0]:.2f}" '
          f'y2="{ya:.2f}" marker-end="url(#a)"/>')
    s.text(O(1025, 0, 0)[0], ya - 1.2, "FWD", 1.9, bold=True)
    s.view_title(O(g.loa / 2, 0, 0)[0], Y3 + 16, "WHERE EACH SLICE IS (ONE HULL)", "sketch, not to scale")

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
    for n, x in enumerate(STATION_COLOURS):
        c = STATION_COLOURS[x]
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
    sheets = [sheet_ga(g), sheet_lines(g), sheet_details(g), sheet_lid_drive(g), sheet_sections(g)]
    OUT.mkdir(exist_ok=True)
    pages = "".join(f'<div class="page">{s.svg(len(sheets))}</div>' for s in sheets)
    html = ("<!DOCTYPE html><html><head><meta charset='utf-8'><title>DREAMS V2 drawings</title>"
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
