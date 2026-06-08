"""Download + stage maritime training data into ml/data/raw/.

Runs on a laptop/Colab (NOT the Pi 5). Pulls Roboflow maritime datasets via the
SDK and prints manual-download instructions for the Singapore Maritime Dataset
(SMD) and SeaShips. Each source labels classes differently, so a per-source
remap to the 6 standard D.R.E.A.M.S classes is documented below and applied by
prepare_dataset.py (this script only stages the raw downloads + writes the remap
tables it will consume).

    export ROBOFLOW_API_KEY=...      # Windows: $env:ROBOFLOW_API_KEY="..."
    python ml/data/download_datasets.py

Output:
    ml/data/raw/roboflow/<project>/{train,valid,test}/{images,labels}
    ml/data/raw/smd/{images,labels}        (manual)
    ml/data/raw/seaships/{images,labels}   (manual)
    ml/data/raw/remap.json                 (per-source class remap → standard ids)
"""
from __future__ import annotations

import json
import os
from pathlib import Path

# Standard 6-class space (id = index). Keep in sync with ml/README.md and
# pi5/cv/onnx_detector.MARITIME_CLASSES.
CLASSES = ["vessel", "kayak", "buoy", "person", "dock", "debris"]

RAW = Path("ml/data/raw")

# Roboflow projects to pull. workspace/project/version vary by dataset; confirm
# the current slugs on roboflow.com (Universe → the dataset → "Download" → SDK
# snippet) and update here. format="yolov8" gives YOLO txt labels + data.yaml.
#
# TODO(confirm): these are representative public maritime projects — verify the
# workspace/project/version are still valid for your Roboflow account before a run.
ROBOFLOW_PROJECTS = [
    # (workspace, project, version)
    ("roboflow-universe-projects", "maritime-object-detection", 1),
    ("maritime", "boat-detection-maritime", 1),
    ("vessel-detection", "vessel-detection", 1),
]

# Per-source remap: source class NAME (lowercased) → standard id, or None to drop.
# Confirm source names against each dataset's data.yaml after download; unknown
# names default to "vessel" with a warning (see prepare_dataset.py).
REMAP_ROBOFLOW = {
    "boat": 0, "ship": 0, "vessel": 0, "ferry": 0, "sailboat": 0, "speedboat": 0,
    "kayak": 1, "canoe": 1, "small_boat": 1, "jet_ski": 1,
    "buoy": 2, "marker": 2, "navigation_buoy": 2,
    "person": 3, "human": 3, "swimmer": 3,
    "dock": 4, "pier": 4, "jetty": 4, "harbor": 4,
    "debris": 5, "log": 5, "flotsam": 5,
}
REMAP_SMD = {
    # SMD object categories → standard ids (Ferry/Boat/Vessel/… → vessel etc.)
    "ferry": 0, "boat": 0, "vessel": 0, "ship": 0, "sailboat": 0,
    "kayak": 1, "speed boat": 1,
    "buoy": 2,
    "person": 3,
    "other": None,
}
REMAP_SEASHIPS = {
    # SeaShips classes are all ship types → vessel.
    "ore carrier": 0, "bulk cargo carrier": 0, "general cargo ship": 0,
    "container ship": 0, "fishing boat": 0, "passenger ship": 0,
}


def _write_remap() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    (RAW / "remap.json").write_text(json.dumps({
        "classes": CLASSES,
        "roboflow": REMAP_ROBOFLOW,
        "smd": REMAP_SMD,
        "seaships": REMAP_SEASHIPS,
    }, indent=2), encoding="utf-8")
    print("  wrote", RAW / "remap.json")


def download_roboflow() -> None:
    api_key = os.environ.get("ROBOFLOW_API_KEY")
    if not api_key:
        print("\n[roboflow] ROBOFLOW_API_KEY not set — skipping Roboflow downloads.")
        print("           Get a free key at https://roboflow.com → Settings → API,")
        print("           then: export ROBOFLOW_API_KEY=...  (PowerShell: $env:ROBOFLOW_API_KEY=...)")
        return
    try:
        from roboflow import Roboflow
    except ImportError:
        print("[roboflow] 'roboflow' not installed — pip install roboflow")
        return

    rf = Roboflow(api_key=api_key)
    dest = RAW / "roboflow"
    dest.mkdir(parents=True, exist_ok=True)
    for workspace, project, version in ROBOFLOW_PROJECTS:
        try:
            print(f"[roboflow] downloading {workspace}/{project} v{version} …")
            proj = rf.workspace(workspace).project(project)
            proj.version(version).download("yolov8", location=str(dest / project))
            print(f"           → {dest / project}")
        except Exception as e:  # noqa: BLE001 — one bad slug shouldn't abort the rest
            print(f"[roboflow] FAILED {workspace}/{project} v{version}: {e}")
            print("           Confirm the workspace/project/version on roboflow.com and edit "
                  "ROBOFLOW_PROJECTS.")


def staging_notes() -> None:
    for name, url in (
        ("smd", "https://sites.google.com/site/dilipprasad/home/singapore-maritime-dataset"),
        ("seaships", "https://github.com/jiaming-wang/SeaShips  (or the official SeaShips site)"),
    ):
        d = RAW / name
        (d / "images").mkdir(parents=True, exist_ok=True)
        (d / "labels").mkdir(parents=True, exist_ok=True)
        print(f"\n[{name}] manual download required.")
        print(f"        Source: {url}")
        print(f"        Put images in {d / 'images'} and YOLO-format .txt labels in {d / 'labels'}.")
        print("        (SMD ships as videos + .mat annotations — extract frames and convert to")
        print("         YOLO txt; SeaShips ships as VOC XML — convert XML→YOLO. prepare_dataset.py")
        print("         then remaps the class ids using ml/data/raw/remap.json.)")


def main() -> None:
    print("=== D.R.E.A.M.S maritime dataset download ===")
    RAW.mkdir(parents=True, exist_ok=True)
    _write_remap()
    download_roboflow()
    staging_notes()
    print("\nDone staging. Next: python ml/data/prepare_dataset.py")


if __name__ == "__main__":
    main()
