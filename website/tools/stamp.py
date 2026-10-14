"""Version the shared stylesheet and script URLs (styles.css?v=..., site.js?v=...).

GitHub Pages lets browsers cache files for 10 minutes, so right after a deploy a page can load
with the previous stylesheet. A content hash in the URL makes every change fetch fresh files.
Run after editing styles.css or site.js:  python -I tools/stamp.py
"""
import hashlib
import re
from pathlib import Path

SITE = Path(__file__).resolve().parents[1]
VER = {name: hashlib.sha1((SITE / name).read_bytes()).hexdigest()[:8] for name in ("styles.css", "site.js")}
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
print("versions:", VER)
