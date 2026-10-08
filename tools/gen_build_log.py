"""Generate build-log.html from the ENTRIES list below.

Run:  python -I tools/gen_build_log.py
To add an entry: append a tuple to ENTRIES (image slug from img/, or None for a text card)
and re-run. Status is one of: designed, built, tested, failed, shown, incad, planned, dev.
The page around the grid is the TEMPLATE string at the bottom of this file.
"""
import sys
from pathlib import Path

SITE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SITE / "tools"))
from typo import tidy  # noqa: E402

# Available widths per image slug (from tools/build_images.py output)
WIDTHS = {
    "log-cad-pod": (480, 543), "log-pod-print": (363,), "log-assembly": (340,), "log-winch": (380,),
    "log-jet": (480, 544), "log-showcase": (480, 682), "log-pcb-r1": (480, 559),
}
LABEL = {"designed": "Designed", "built": "Built", "tested": "Tested", "failed": "Failed", "shown": "Shown",
         "incad": "In CAD", "planned": "Planned", "dev": "In development"}
GROUP = {"incad": "next", "planned": "next", "dev": "next"}

# (version, when, status, title, description, image slug or None, alt text)
ENTRIES = [
    ("v1", "V1 · Spring 2026", "designed", "The first concept sketch", "Requirements and the twin-hull layout, on paper.", "log-sketch", "Hand-drawn concept sketch of the catamaran with a requirements list"),
    ("v1", "V1 · SolidWorks", "designed", "Bridge and winch in CAD", "The deck that ties the hulls together and carries the winch.", "log-cad-bridge", "SolidWorks model of the catamaran bridge with the winch"),
    ("v1", "V1 · SolidWorks", "designed", "Sensor pod in CAD", "A sealed pod for the sensors, lowered on a tether.", "log-cad-pod", "CAD model of the V1 sensor pod"),
    ("v1", "V1 · Sensor pod", "built", "Printing the sensor pod", "3D-printed and wired.", "log-pod-print", "The 3D-printed V1 sensor pod with electronics inside"),
    ("v1", "V1 · Assembly", "built", "Wiring and assembly", "Putting the boat together outside.", "log-assembly", "Assembling and wiring V1 outdoors"),
    ("v1", "V1 · Hull", "built", "Epoxy-sealing the printed hull", "PLA hulls sealed with marine epoxy.", "log-epoxy", "Brushing marine epoxy onto a printed hull"),
    ("v1", "V1 · Winch", "built", "The sensor-deployment winch", "Lowers the pod to the bottom to sample.", "log-winch", "The V1 winch that lowers the sensor pod"),
    ("v1", "V1 · Propulsion", "failed", "Jet drive", "An early jet-propulsion experiment. A dead end, but a useful one.", "log-jet", "Line drawing of an early jet-propulsion unit"),
    ("v1", "V1 · London", "tested", "Water test at St Katharine Docks", "Navigated to GPS waypoints on its own, with a radio link of about 1 km.", "log-field", "V1 at the edge of St Katharine Docks"),
    ("v1", "V1 · NU London", "shown", "Creators' Showcase", "Shown at the inaugural Creators' Showcase, Northeastern University London.", "log-showcase", "Visitors gathered around V1 at the Creators' Showcase"),
    ("v2", "V2 · Summer 2026", "designed", "Hull CAD", "Hull geometry refined for stability and flow.", "log-v2-cad", "CAD model of the V2 twin hulls"),
    ("v2", "V2 · Hull", "built", "First printed hull section", "The V2 hull, printed in sections.", "log-hull-print", "A printed section of the V2 hull"),
    ("v2", "V2 · Hull", "built", "Fiberglass over the print", "Wetted out with epoxy for stiffness and water resistance.", "log-fiberglass", "Fiberglass cloth wetted out with epoxy over a printed hull"),
    ("v2", "V2 · Electronics", "designed", "Custom PCB, REV 01", "Our first custom board, laid out in KiCad.", "log-pcb-r1", "KiCad layout of the first custom PCB"),
    ("v2", "V2 · Electronics", "designed", "PCB REV 02", "Consolidated power, radio and sensor headers.", "log-pcb-r2", "KiCad layout of the second PCB revision"),
    ("v2", "V2 · Electronics", "built", "Board bring-up", "Powering up and testing the board on the bench.", "log-bringup", "Bringing up the custom PCB on the bench"),
    ("v2", "V2 · Vision", "tested", "Stereo tracking on the bench", "Per-object depth from a stereo pair, with YOLOv8 detection.", "log-stereo", "Stereo camera rig on the test bench"),
    ("v2", "V2 · Software", "built", "Command-center dashboard", "Ran on the Pi 5. Now a live demo you can try.", "log-dashboard", "The V2 command-center dashboard"),
    ("v2", "V2 · Bench", "failed", "Bench testing", "Exposed flaws in motor control, power and safety. We redesigned the whole system.", None, "V2 → V3"),
    ("v3", "V3 · Fall 2026", "designed", "Carrier board, rev D", "130.6 × 101.5 mm, 4 layers, 126 parts, fully routed.", "log-v3-carrier", "3D render of the V3 carrier board"),
    ("v3", "V3 · Fall 2026", "designed", "Sensor-pod board, rev B", "48 × 63 mm. Talks to the boat over an RS-485 tether.", "log-v3-pod", "3D render of the V3 sensor-pod board"),
    ("v3", "V3 · Hull", "incad", "Modular hull", "The new V3 hull, in CAD now.", None, "In CAD"),
    ("v3", "V3 · Software", "planned", "Firmware", "Autonomous waypoint navigation, surface sampling and depth logging.", None, "Next"),
    ("v3", "V3 · Field", "planned", "Field trials", "Autonomous surveys of small bodies of water.", None, "Next"),
    ("later", "Later", "dev", "Sample-collection arm", "A deck arm that works with the winch. Its cycloidal joints are in CAD.", "log-arm", "CAD model of a cycloidal gearbox joint for the arm"),
    ("later", "Later", "planned", "Sediment sampling", "Bring sediment back from the bottom without sending a diver down.", None, "Later"),
]


def picture(slug, alt):
    ws = WIDTHS.get(slug, (480, 720))
    h = lambda w: round(w * 5 / 4)
    srcset_webp = ", ".join(f"img/{slug}-{w}.webp {w}w" for w in ws)
    return (f'<picture><source type="image/webp" srcset="{srcset_webp}" sizes="(max-width: 680px) 50vw, 300px">'
            f'<img src="img/{slug}-{ws[0]}.jpg" alt="{alt}" width="{ws[0]}" height="{h(ws[0])}" loading="lazy"></picture>')


def card(e):
    v, when, s, title, desc, slug, alt = e
    ph = (f'<div class="ph">{picture(slug, alt)}</div>' if slug
          else f'<div class="ph blank" aria-hidden="true"><span>{alt}</span></div>')
    cls = "log-card failed" if s == "failed" else "log-card"
    return (f'        <article class="{cls}" data-v="{v}" data-s="{GROUP.get(s, s)}">{ph}<div class="meta">'
            f'<div class="row"><span>{when}</span><span class="chip {s}">{LABEL[s]}</span></div>'
            f'<h3>{title}</h3><p>{desc}</p></div></article>')


cards = "\n".join(card(e) for e in ENTRIES)
template = (SITE / "tools" / "build-log.template.html").read_text(encoding="utf-8")
out = tidy(template.replace("<!--CARDS-->", cards).replace("<!--COUNT-->", str(len(ENTRIES))))
(SITE / "build-log.html").write_text(out, encoding="utf-8", newline="\n")
print(f"build-log.html written with {len(ENTRIES)} entries")
