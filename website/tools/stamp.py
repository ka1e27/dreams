"""Version the shared stylesheet and script URLs (styles.css?v=..., site.js?v=..., boat-explorer.js?v=...),
and the Boat page's 3D model and its poster (media/boat-v3.glb?v=..., media/boat-v3-poster.*?v=...).

GitHub Pages lets browsers cache files for 10 minutes, so right after a deploy a page can load
with the previous stylesheet or model. A content hash in the URL makes every change fetch fresh files.
Run after editing styles.css, site.js or boat-explorer.js, or after replacing the 3D model or its
poster:  python -I tools/stamp.py
"""
import hashlib
import re
from pathlib import Path

SITE = Path(__file__).resolve().parents[1]
MEDIA = ("media/boat-v3.glb", "media/boat-v3-poster.webp", "media/boat-v3-poster.png")

# the model and poster first: the model's URL lives in boat-explorer.js, whose own hash comes next
MEDIA_VER = {name: hashlib.sha1((SITE / name).read_bytes()).hexdigest()[:8] for name in MEDIA}
for path in sorted(SITE.glob("*.html")) + [SITE / "boat-explorer.js"]:
    text = path.read_text(encoding="utf-8")
    new = text
    for name, v in MEDIA_VER.items():
        new = re.sub(rf"({re.escape(name)})(?:\?v=[0-9a-f]+)?(?=[\"'])", rf"\g<1>?v={v}", new)
    if new != text:
        path.write_text(new, encoding="utf-8", newline="\n")
        print("stamped", path.relative_to(SITE).as_posix(), "(3D model)")

VER = {name: hashlib.sha1((SITE / name).read_bytes()).hexdigest()[:8] for name in ("styles.css", "site.js", "boat-explorer.js")}
PAGES = sorted(SITE.glob("*.html")) + [SITE / "tools" / "build-log.template.html"]

for page in PAGES:
    text = page.read_text(encoding="utf-8")
    new = text
    for name, v in VER.items():
        new = re.sub(rf'((?:href|src)="(?:https://ka1e27\.github\.io/dreams/)?{re.escape(name)})(?:\?v=[0-9a-f]+)?"',
                     rf'\g<1>?v={v}"', new)
    if new != text:
        page.write_text(new, encoding="utf-8", newline="\n")
        print("stamped", page.relative_to(SITE).as_posix())
print("versions:", VER | MEDIA_VER)
