# D.R.E.A.M.S — Maritime YOLOv8 Fine-Tuning Pipeline

Trains a maritime-specific object detector for the Survey Boat V2 vision stack.
The pipeline downloads maritime training data, fine-tunes YOLOv8n from COCO
weights, validates/benchmarks it, and exports an ONNX model the Pi 5 runs with
**onnxruntime** (no PyTorch on the boat).

> **Runs on a laptop/desktop with a GPU, or Google Colab — NOT on the Pi 5.**
> The Pi 5 only receives the final `maritime_yolov8n.onnx`.

```
Maritime datasets (Roboflow, SMD, SeaShips)
        │  ml/data/download_datasets.py
        ▼
Merge + remap + clean + split (70/20/10)
        │  ml/data/prepare_dataset.py   →  ml/data/unified/dataset.yaml
        ▼
Maritime augmentation (water glare/haze/reflection…)
        │  ml/data/augment.py
        ▼
Fine-tune YOLOv8n (freeze backbone first, COCO pretrained)
        │  ml/train.py                   →  ml/runs/maritime_v1/weights/best.pt
        ▼
Validate + CPU benchmark (pass/fail thresholds)
        │  ml/validate.py
        ▼
Export ONNX (imgsz 320, simplified, opset 12)
        │  ml/export_onnx.py             →  pi5/cv/models/maritime_yolov8n.onnx (+ _info.json)
        ▼
Copy .onnx to the Pi → vision_overlay auto-detects it
```

## Target classes (6)

| id | name | covers |
|----|------|--------|
| 0 | `vessel` | boats, ships, ferries |
| 1 | `kayak` | kayaks, canoes, small craft |
| 2 | `buoy` | navigation / marker buoys |
| 3 | `person` | person in water or on a vessel |
| 4 | `dock` | piers, jetties, docks |
| 5 | `debris` | floating debris, logs |

Fewer classes = faster inference and less labelling drift.

## Quick start

```bash
pip install ultralytics onnx onnxruntime roboflow albumentations opencv-python matplotlib

# 1. Data
export ROBOFLOW_API_KEY=your_key          # Windows: $env:ROBOFLOW_API_KEY="your_key"
python ml/data/download_datasets.py
python ml/data/prepare_dataset.py
python ml/data/augment.py                 # optional — doubles the train set

# 2. Train (GPU strongly recommended)
python ml/train.py --epochs 100 --batch 16

# 3. Validate + benchmark on CPU (simulates the Pi 5)
python ml/validate.py

# 4. Export to ONNX for the Pi
python ml/export_onnx.py
```

No local GPU? Use `ml/colab_train.ipynb` (free Colab T4).

## Deploy to the Pi 5

The `.onnx` is **gitignored** (binary). Copy it to the Pi:

```bash
scp pi5/cv/models/maritime_yolov8n.onnx ka1e27@dreams-pi:~/D.R.E.A.M.S/pi5/cv/models/
```

`pi5/cv/vision_overlay.py` **auto-detects** `pi5/cv/models/maritime_yolov8n.onnx`:
if it's present (and `camera.detection.model` is still the COCO default) the
overlay loads it through `pi5/cv/onnx_detector.py` (onnxruntime, CPU). If it's
missing, the overlay falls back to `yolov8n.pt` (COCO). Install onnxruntime on
the Pi: `pip install onnxruntime` (already in `pi5/requirements.txt`).

The model-card `pi5/cv/models/maritime_yolov8n_info.json` (class list + metrics)
**is** tracked in git; the `.onnx`/`.pt` weights are not.

## Datasets & class remapping

Each source labels classes differently; `download_datasets.py` documents and
applies a remap to the 6 standard ids above. Roboflow project slugs/versions and
the exact source class names must be confirmed when you run it (they vary by
dataset version) — see the `REMAP` tables and `TODO` notes in that script.

- **Roboflow maritime datasets** (primary) — via the `roboflow` SDK + `ROBOFLOW_API_KEY`.
- **Singapore Maritime Dataset (SMD)** — manual download (videos + annotations);
  see structure notes in `download_datasets.py`.
- **SeaShips** — manual download; structure notes in `download_datasets.py`.

## Acceptance thresholds (checked by `validate.py`)

| metric | threshold |
|--------|-----------|
| vessel mAP50 | > 0.70 |
| kayak mAP50 | > 0.50 |
| buoy mAP50 | > 0.60 |
| person mAP50 | > 0.65 |
| CPU inference @ imgsz 320 | > 8 FPS |

CPU FPS here is a desktop-CPU proxy; the real Pi 5 number is whatever
`export_onnx.py`'s onnxruntime benchmark reports on the Pi (or in the model card
after you run it there).

## Files

```
ml/
├── README.md                 ← this file
├── train.py                  ← fine-tune YOLOv8n
├── validate.py               ← test-set metrics + CPU benchmark + thresholds
├── export_onnx.py            ← best.pt → maritime_yolov8n.onnx (+ info.json)
├── colab_train.ipynb         ← train on Colab (no local GPU)
└── data/
    ├── download_datasets.py  ← fetch Roboflow + SMD/SeaShips notes
    ├── prepare_dataset.py    ← merge/remap/clean/split → unified/
    ├── augment.py            ← maritime augmentation
    └── unified/              ← gitignored (large)
```
