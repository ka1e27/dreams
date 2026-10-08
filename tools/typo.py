"""Typographic tidy for the site's HTML: keeps names, part numbers and units from breaking across lines.

tidy(html) only touches text between tags (never attributes, <title>, <script> or <style>) and is safe to re-run.
- "a · b"      -> "a&nbsp;· b"   (a line can break after a separator dot, never before it)
- Pi 5, Teensy 4.1, 130.6 × 101.5 mm, 433 MHz, 5 V ...  -> joined with &nbsp;
- RS-485, ESP32-S3, u-blox -> wrapped in <span class="nw"> so they never split at the hyphen
"""
import re

RAW = {"script", "style", "title", "textarea"}
JOIN = [
    (re.compile(r" · "), "&nbsp;· "),
    (re.compile(r"\bPi 5\b"), "Pi&nbsp;5"),
    (re.compile(r"\bTeensy 4\.1\b"), "Teensy&nbsp;4.1"),
    (re.compile(r"(\d) × (\d)"), r"\1&nbsp;×&nbsp;\2"),
    (re.compile(r"(\d) (mm|km|MHz|V|Ω)(?![\w-])"), r"\1&nbsp;\2"),
]
KEEP = re.compile(r"\b(RS-485|ESP32-S3|u-blox)\b")
NW = '<span class="nw">'


def tidy(html):
    parts = re.split(r"(<[^>]*>)", html)
    raw = None
    for i, p in enumerate(parts):
        if p.startswith("<"):
            m = re.match(r"<(/?)([a-zA-Z][a-zA-Z0-9]*)", p)
            if m:
                name = m.group(2).lower()
                if raw is None and not m.group(1) and name in RAW:
                    raw = name
                elif raw == name and m.group(1):
                    raw = None
            continue
        if raw or not p.strip():
            continue
        for rx, rep in JOIN:
            p = rx.sub(rep, p)
        if not (i > 0 and parts[i - 1] == NW and KEEP.fullmatch(p)):
            p = KEEP.sub(NW + r"\1</span>", p)
        parts[i] = p
    return "".join(parts)
