"""
train_yolo.py
──────────────
Train/retrain the YOLOv8 model for attendance mark detection.

Uses the augmented dataset if available, otherwise falls back to the
original small dataset.

Usage:
    python backend/ml_pipeline/train_yolo.py

After training, copy weights to the canonical location:
    weights/tsr_yolo_retrained.pt

Training strategy:
  - YOLOv8n (smallest, fastest, CPU-viable)
  - Augmented dataset preferred (200+ images vs 12 originals)
  - 100 epochs with early stopping (patience=25)
  - Aggressive augmentation since dataset is small
"""

import shutil
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]  # attendance_platform/

from ultralytics import YOLO


# ─────────────────────────────────────────────────────────────
# DATASET YAML
# ─────────────────────────────────────────────────────────────

def find_dataset_yaml() -> Path:
    """
    Prefer augmented dataset, fall back to original.
    Also fix absolute paths in data.yaml if they point to a different machine.
    """
    augmented = BASE_DIR / "VIT-Attendance-TSR-1" / "augmented_data.yaml"
    original  = BASE_DIR / "VIT-Attendance-TSR-1" / "data.yaml"

    # Use augmented if it exists and the augmented image folder has images
    aug_images = BASE_DIR / "VIT-Attendance-TSR-1" / "augmented" / "images"
    if augmented.exists() and aug_images.exists():
        image_count = len(list(aug_images.glob("*.jpg")))
        if image_count > 20:
            print(f"✅ Using augmented dataset ({image_count} images)")
            return _ensure_local_paths(augmented)

    print("⚠️  Augmented dataset not found — using original 12-image dataset.")
    print("    Run:  python datasets/data_augment.py   first for better accuracy.")
    return _ensure_local_paths(original)


def _ensure_local_paths(yaml_path: Path) -> Path:
    """
    Read the YAML and replace any hardcoded absolute paths
    (from a different machine) with paths relative to THIS machine.
    Returns path to the (possibly updated) YAML.
    """
    import yaml as _yaml

    with open(yaml_path) as f:
        data = _yaml.safe_load(f)

    changed = False
    dataset_root = yaml_path.parent

    for key in ("train", "val", "test"):
        val = data.get(key)
        if val is None:
            continue
        val_path = Path(val)
        # If path doesn't exist, try resolving relative to dataset root
        if not val_path.exists():
            # Try to reconstruct from the last 3 path components
            parts = val_path.parts
            for i in range(len(parts) - 1, 0, -1):
                candidate = dataset_root / Path(*parts[i:])
                if candidate.exists():
                    data[key] = str(candidate)
                    changed = True
                    break

    if changed:
        fixed_path = yaml_path.parent / f"_fixed_{yaml_path.name}"
        with open(fixed_path, "w") as f:
            _yaml.dump(data, f, default_flow_style=False)
        print(f"   Fixed dataset paths → {fixed_path.name}")
        return fixed_path

    return yaml_path


# ─────────────────────────────────────────────────────────────
# TRAIN
# ─────────────────────────────────────────────────────────────

def train():
    print()
    print("=" * 60)
    print("YOLO ATTENDANCE MARK DETECTOR — TRAINING")
    print("=" * 60)

    dataset_yaml = find_dataset_yaml()

    # Load base model
    base_model_path = BASE_DIR / "yolov8n.pt"
    if not base_model_path.exists():
        base_model_path = BASE_DIR / "backend" / "yolov8n.pt"
    if not base_model_path.exists():
        print("Downloading YOLOv8n base model...")
        model = YOLO("yolov8n.pt")   # auto-downloads
    else:
        model = YOLO(str(base_model_path))

    print(f"\nDataset YAML : {dataset_yaml}")
    print(f"Base model   : {base_model_path}")
    print()

    results = model.train(
        data    = str(dataset_yaml),
        epochs  = 100,
        batch   = 4,              # increase if you have more RAM
        imgsz   = 1280,           # larger = better for small marks
        workers = 0,              # Windows safe
        device  = "cpu",

        # Augmentation — aggressive because dataset is small
        hsv_h    = 0.015,
        hsv_s    = 0.7,
        hsv_v    = 0.4,
        degrees  = 5.0,
        translate = 0.1,
        scale    = 0.5,
        flipud   = 0.0,
        fliplr   = 0.0,           # attendance marks are not horizontally symmetric
        mosaic   = 0.5,
        mixup    = 0.1,
        copy_paste = 0.1,

        patience = 25,            # early stopping
        save     = True,
        project  = str(BASE_DIR / "runs" / "detect"),
        name     = "tsr_retrained",
        exist_ok = True,

        verbose  = True,
    )

    # Copy best weights to canonical location
    best_weights = BASE_DIR / "runs" / "detect" / "tsr_retrained" / "weights" / "best.pt"
    weights_dir  = BASE_DIR / "weights"
    weights_dir.mkdir(exist_ok=True)

    dest = weights_dir / "tsr_yolo_retrained.pt"
    if best_weights.exists():
        shutil.copy2(best_weights, dest)
        print(f"\n✅ Best weights saved to: {dest}")
    else:
        print(f"\n⚠️  Could not find best weights at {best_weights}")

    print()
    print("=" * 60)
    print("TRAINING COMPLETE")
    print(f"Model saved: {dest}")
    print("=" * 60)


if __name__ == "__main__":
    try:
        import yaml
    except ImportError:
        print("Installing PyYAML...")
        import subprocess
        subprocess.run([sys.executable, "-m", "pip", "install", "PyYAML"], check=True)
        import yaml

    train()