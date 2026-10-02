"""Regenerate everything in mechanical/ in one go.

    python mechanical/build_all.py           # reports, drawings, 3D renders, default props
    python mechanical/build_all.py --quick   # skip the slow parts (renders, prop PNGs)

Run it from anywhere; it finds its own folder. Reports land in mechanical/reports/.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPORTS = HERE / "reports"


def run(script: str, *args: str, save: str | None = None) -> None:
    t0 = time.time()
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    r = subprocess.run([sys.executable, str(HERE / script), *args], cwd=HERE, env=env,
                       capture_output=True, text=True, encoding="utf-8")
    if r.returncode:
        print(f"FAILED {script}:\n{r.stderr}")
        sys.exit(r.returncode)
    if save:
        REPORTS.mkdir(exist_ok=True)
        (REPORTS / save).write_text(r.stdout, encoding="utf-8")
        print(f"  {script:18s} -> reports/{save}  ({time.time() - t0:.0f} s)")
    else:
        print(f"  {script:18s} done  ({time.time() - t0:.0f} s)")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--quick", action="store_true", help="skip browser renders (PNG) for speed")
    quick = ap.parse_args().quick
    print("Building D.R.E.A.M.S V2 mechanical outputs:")
    run("hull_sizing.py", save="hull_report.md")
    run("propulsion.py", save="propulsion_report.md")
    run("drawings.py")
    run("concept_model.py", *(["--no-png"] if quick else []))
    for hand in ("RH", "LH"):
        run("toroidal_prop.py", "--hand", hand, *(["--no-png"] if quick else []))
    print("\nOpen:")
    for rel in ("reports/hull_report.md", "reports/propulsion_report.md",
                "drawings/DREAMS_V2_drawings.pdf", "render/DREAMS_V2_viewer.html",
                "props/toroidal_3loop_p75_RH_shaft/toroidal_3loop_p75_RH_shaft_viewer.html", "props/thrust_stand.pdf"):
        print(f"  mechanical/{rel}")


if __name__ == "__main__":
    main()
