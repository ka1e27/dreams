"""Build the site's optimized images into img/ (WebP + JPEG, EXIF-safe).

Run from anywhere:  python -I tools/build_images.py            (everything)
                    python -I tools/build_images.py log-dorm   (only the named slugs)
Sources: the portfolio's high-res originals where they exist, else the copies in images/.
Every output is named <slug>-<width>.<ext>; pages reference them with <picture>/srcset.
"""
import sys
from pathlib import Path
from PIL import Image, ImageEnhance, ImageFilter, ImageOps

SITE = Path(__file__).resolve().parents[1]
PORT = Path(r"C:\Users\kyleg\Projects\Kyle_Tran_Portfolio_Website\images")
OLD = SITE / "images"
OUT = SITE / "img"
OUT.mkdir(exist_ok=True)
DARK = (10, 26, 39)  # --deep-2, behind drawings that need padding
ONLY = set(sys.argv[1:])  # optional slugs to rebuild


def load(p):
    im = ImageOps.exif_transpose(Image.open(p))
    if im.mode in ("RGBA", "LA", "P"):
        im = im.convert("RGBA")
    else:
        im = im.convert("RGB")
    return im


def flatten(im, bg=(255, 255, 255)):
    if im.mode != "RGBA":
        return im
    base = Image.new("RGB", im.size, bg)
    base.paste(im, mask=im.split()[3])
    return base


def emit(slug, im, widths, alpha=False, q=80):
    if ONLY and slug not in ONLY:
        return
    sizes = []
    for w in widths:
        w = min(w, im.width)
        h = round(im.height * w / im.width)
        r = im.resize((w, h), Image.LANCZOS) if w != im.width else im
        if alpha:
            r.save(OUT / f"{slug}-{w}.webp", "WEBP", quality=88, method=6)
            r.save(OUT / f"{slug}-{w}.png", "PNG", optimize=True)
        else:
            r = flatten(r)
            r.save(OUT / f"{slug}-{w}.webp", "WEBP", quality=q - 4, method=6)
            r.save(OUT / f"{slug}-{w}.jpg", "JPEG", quality=q, optimize=True, progressive=True)
        sizes.append(f"{w}x{h}")
    kb = sum(f.stat().st_size for f in OUT.glob(f"{slug}-*")) // 1024
    print(f"{slug:22} {' '.join(sizes):28} {kb} KB total")


def cover(im, ratio, center=(0.5, 0.5)):
    w, h = im.size
    if w / h > ratio:
        nw = round(h * ratio)
        x = round((w - nw) * center[0])
        return im.crop((x, 0, x + nw, h))
    nh = round(w / ratio)
    y = round((h - nh) * center[1])
    return im.crop((0, y, w, y + nh))


def trim(im, thresh=230, margin=24):
    """Crop a drawing on white paper to its ink."""
    box = im.convert("L").point(lambda v: 255 if v < thresh else 0).getbbox()
    x0, y0, x1, y1 = box
    return im.crop((max(0, x0 - margin), max(0, y0 - margin), min(im.width, x1 + margin), min(im.height, y1 + margin)))


def fit_blur(im, ratio):
    """Whole frame, centered on a blurred, darkened copy of itself (for tall video frames in 4:5 cards)."""
    w, h = im.size
    cw = round(h * ratio)
    bg = cover(im, ratio).resize((cw, h), Image.LANCZOS).filter(ImageFilter.GaussianBlur(22))
    bg = ImageEnhance.Brightness(bg).enhance(0.5)
    bg.paste(im, ((cw - w) // 2, 0))
    return bg


def contain(im, ratio, bg, pad=0.06):
    im = flatten(im, bg if bg != "white" else (255, 255, 255)) if im.mode == "RGBA" else im
    w, h = im.size
    cw = max(w, round(h * ratio)) if w / h < ratio else w
    ch = round(cw / ratio)
    if ch < h:
        ch = h; cw = round(ch * ratio)
    cw = round(cw * (1 + pad)); ch = round(ch * (1 + pad))
    fill = (255, 255, 255) if bg == "white" else bg
    canvas = Image.new("RGB", (cw, ch), fill)
    canvas.paste(im, ((cw - w) // 2, (ch - h) // 2))
    return canvas


# --- Hero (St Katharine Docks original, 4284x5712) ---
docks = load(PORT / "D.R.E.A.M.S v1 with lake background.jpg")
emit("hero-docks", docks.crop((0, 950, 4284, 3627)), [2400, 1600, 1000], q=78)
emit("docks-portrait", docks.crop((575, 1000, 2975, 4000)), [1200, 800, 600], q=80)

# --- Build log, 4:5 cards (photos cover-cropped; drawings contained) ---
LOG = {
    # slug: (source, mode)
    "log-sketch": (PORT / "D.R.E.A.M.S v1 sketch.jpeg", "cover"),
    "log-cad-bridge": (PORT / "picture of cad of catamaran bridge and winch on dreams v1.png", "white"),
    "log-cad-pod": (PORT / "picture of cad of sensor pod for dreams v1.png", "white"),
    "log-pod-print": (PORT / "dreams v1 sensor pod.png", "cover"),
    "log-assembly": (PORT / "working on dreams v1 outside.png", "cover"),
    "log-epoxy": (PORT / "Epoxying D.R.E.A.M.S v1.jpg", "cover"),
    "log-winch": (PORT / "dreams v1 winch.png", "cover"),
    "log-jet": (PORT / "attempts at jet propulsion on dreams v1.png", "white"),
    "log-showcase": (PORT / "D.R.E.A.M.S v1 at a showcase.jpg", "cover"),
    "log-v2-cad": (PORT / "picture of cad design for hull of dreams v2.png", "white"),
    "log-hull-print": (PORT / "part of the hull of dreams v2.JPG", "cover"),
    "log-fiberglass": (OLD / "dreams-hull-fiberglass.jpg", "cover"),
    "log-pcb-r1": (PORT / "dreams v2 pcb v1.png", "cover"),
    "log-pcb-r2": (PORT / "PCB for dreams v2 v2 of pcb.png", "dark"),
    "log-bringup": (OLD / "dreams-v2-pcb-bringup.jpg", "cover"),
    "log-stereo": (PORT / "stereo + tracking for D.R.E.A.M.S v2.JPG", "cover"),
    "log-dashboard": (OLD / "v2-dashboard.jpg", "dark"),
    "log-v3-carrier": (OLD / "v3-carrier.png", "dark"),
    "log-v3-pod": (OLD / "v3-pod.png", "dark"),
    "log-arm": (PORT / "web" / "arm-gearbox-assembly.png", "white"),
    # Added 2026-10-08 from Kyle's photos and the winch test video (cover crops take an offset, 0-1)
    "log-deck-figure": (OLD / "dreams-v1-deck-figure.jpg", "cover", (0.5, 0.5), (330, 195, 1330, 1445)),
    "log-hull-coat": (OLD / "dreams-v1-hull-coat.jpg", "cover", (0.5, 0.3)),
    "log-dorm": (OLD / "dreams-v1-room-workshop.jpg", "cover", (0.3, 0.5)),
    "log-winch-test": (OLD / "dreams-v1-winch-test-frame.png", "fitblur"),
    "log-stand-sketch": (OLD / "dreams-v1-stand-sketch.jpg", "sketch"),
    "log-demo": (OLD / "dreams-v1-demo.jpg", "cover", (0.55, 0.5)),
}
for slug, (src, mode, *opt) in LOG.items():
    if ONLY and slug not in ONLY:
        continue
    im = load(src)
    if len(opt) > 1:
        im = im.crop(opt[1])  # pre-crop box (x0, y0, x1, y1)
    if mode == "cover":
        im = cover(flatten(im), 4 / 5, opt[0] if opt else (0.5, 0.5))
    elif mode == "fitblur":
        im = fit_blur(flatten(im), 4 / 5)
    elif mode == "sketch":
        im = contain(trim(flatten(im)), 4 / 5, "white")
    else:
        im = contain(im, 4 / 5, "white" if mode == "white" else DARK)
    emit(slug, im, [720, 480])
emit("log-field", cover(docks.crop((0, 950, 4284, 4800)), 4 / 5, (0.42, 0.5)), [720, 480])

# --- Feature images ---
emit("showcase", flatten(load(PORT / "D.R.E.A.M.S v1 at a showcase.jpg")), [1280, 800])
emit("v2-dashboard", flatten(load(OLD / "v2-dashboard.jpg")), [1600, 1000])
emit("v3-carrier-iso", load(OLD / "v3-carrier.png"), [900, 600], alpha=True)
emit("v3-pod-iso", load(OLD / "v3-pod.png"), [900, 600], alpha=True)
emit("arm-gearbox", flatten(load(PORT / "web" / "arm-gearbox-assembly.png")), [1200, 700])
emit("arm-disc", flatten(load(PORT / "web" / "arm-cycloidal-disc.png")), [900, 600])
emit("omar", flatten(load(OLD / "dreams-omar.jpg")), [1200, 800])
emit("kyle-tran", cover(flatten(load(OLD / "team" / "kyle-tran.jpg")), 4 / 5, (0.5, 0.2)), [900, 600])
emit("matthew-hong", cover(flatten(load(OLD / "team" / "matthew-hong-headshot.jpg")), 4 / 5, (0.5, 0.15)), [900, 600])

# Wide versions of the 2026-10-08 photos (team page workshop, contact page header)
emit("room-workshop", flatten(load(OLD / "dreams-v1-room-workshop.jpg")), [1600, 1000], q=78)
emit("showcase-demo", flatten(load(OLD / "dreams-v1-demo.jpg")), [1200, 800], q=80)
# Build-log page header: V1 with the plush husky riding in a hull
husky = flatten(load(PORT / "D.R.E.A.M.S with husky.jpg"))
emit("husky-boat", husky.crop((0, round(husky.height * 0.17), husky.width, husky.height)), [1400, 900], q=78)  # drop the wall and socket
