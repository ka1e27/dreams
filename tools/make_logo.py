"""Build the D.R.E.A.M.S logo files in img/ from Kyle's hand-drawn logo.

Run:  python -I tools/make_logo.py
The drawing is redrawn as strokes: coordinates are stroke centrelines measured from the original
1091x809 px sketch. The D and R bowls are Catmull-Rom curves through measured points; everything
else is straight strokes with round caps.

Outputs (all SVG):
  img/logo.svg        the wordmark for light backgrounds, strokes thickened for small sizes (nav)
  img/logo-light.svg  the same for dark backgrounds (footer)
  img/logo-full.svg   the wordmark at the drawing's own stroke weight, for large uses
  img/favicon.svg     the bow and D on a white tile, for browser tabs
"""
from pathlib import Path

SITE = Path(__file__).resolve().parents[1]
OUT = SITE / "img"
INK, RED, RED_ON_DARK = "#0D2E44", "#D7263D", "#FF5468"


def cr(points):
    """Catmull-Rom through points -> SVG cubic path."""
    p = [points[0]] + points + [points[-1]]
    d = f"M{p[1][0]:g} {p[1][1]:g}"
    for i in range(1, len(p) - 2):
        p0, p1, p2, p3 = p[i - 1], p[i], p[i + 1], p[i + 2]
        c1 = (p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6)
        d += f"C{c1[0]:.1f} {c1[1]:.1f} {c2[0]:.1f} {c2[1]:.1f} {p2[0]:g} {p2[1]:g}"
    return d


def line(*pts):
    return "M" + "L".join(f"{x:g} {y:g}" for x, y in pts)


D_STEM = line((146, 313), (229, 492))
D_BOWL = cr([(147, 314), (201.5, 327), (250, 340), (301.5, 360), (330.5, 380), (341, 405), (333, 430), (310.5, 450), (278, 470), (229, 492)])
R_STEM = line((343, 316), (345, 563))
R_BOWL = cr([(344, 317), (370, 324), (390, 330), (413, 340), (428, 355), (431, 368), (426.5, 380), (408.5, 400), (381.5, 420), (347, 440)])

HULL = [line((148, 313.5), (879, 326), (879, 450)), line((345, 565), (879, 573.5)), line((231, 494), (344, 564))]
LETTERS = [
    D_STEM, D_BOWL,                                                               # D
    R_STEM, R_BOWL, line((345, 441), (427, 567)),                                 # R
    line((518, 321), (445, 321), (450, 567.5), (514, 567.5)), line((447, 440), (519, 440)),  # E
    line((527, 570), (574, 318), (638, 571)), line((548, 450), (609, 450)),       # A
    line((654, 571), (642, 317), (695, 450), (741, 321), (750, 573)),             # M
    line((880, 324), (761, 324), (761, 450), (879, 450), (879, 572), (768, 572)),  # S
]


def wordmark(hull, red, hull_w, red_w):
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="136 303 756 282" role="img" aria-label="D.R.E.A.M.S">'
            '<g fill="none" stroke-linecap="round" stroke-linejoin="round">'
            f'<path stroke="{hull}" stroke-width="{hull_w}" d="{"".join(HULL)}"/>'
            f'<path stroke="{red}" stroke-width="{red_w}" d="{"".join(LETTERS)}"/></g></svg>\n')


def favicon():
    # the bow section of the hull: deck and keel up to the R's stem, which closes it like a stern
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="95 289 300 300">'
            '<rect x="95" y="289" width="300" height="300" rx="62" fill="#FFFFFF"/>'
            '<g fill="none" stroke-linecap="round" stroke-linejoin="round">'
            f'<path stroke="{INK}" stroke-width="17" d="{line((148, 313.5), (344, 317))}{line((231, 494), (344, 564))}"/>'
            f'<path stroke="{RED}" stroke-width="21" d="{D_STEM}{D_BOWL}{R_STEM}"/></g></svg>\n')


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    files = {
        "logo.svg": wordmark(INK, RED, 11, 14),
        "logo-light.svg": wordmark("#FFFFFF", RED_ON_DARK, 11, 14),
        "logo-full.svg": wordmark(INK, RED, 8, 10),
        "favicon.svg": favicon(),
    }
    for name, svg in files.items():
        (OUT / name).write_text(svg, encoding="utf-8", newline="\n")
        print("img/" + name, len(svg), "bytes")
