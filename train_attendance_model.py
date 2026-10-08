"""
TRAIN THE FINAL ATTENDANCE-MARK YOLO MODEL

Purpose:
- Class 0: ABSENT_MARK (red A / absent mark)
- Class 1: PRESENT_MARK (signature OR existing P annotation)

The original dataset has:
0 = A
1 = P
2 = VIT-Attendance-TSR
3 = signature

This script converts those labels into a 2-class training dataset:
A -> ABSENT_MARK
P + signature -> PRESENT_MARK
TSR -> ignored

It also creates augmented training examples through Ultralytics training.
"""

from pathlib import Path
import shutil
import random
import yaml

from ultralytics import YOLO

SOURCE = Path("VIT-Attendance-TSR-1")
OUT = Path("attendance_mark_dataset")

# Change only if your dataset uses "valid" instead of "val".
SPLITS = {
    "train": SOURCE / "train",
    "val": SOURCE / "valid" if (SOURCE / "valid").exists() else SOURCE / "val",
}

CLASS_MAP = {
    0: 0,  # A -> ABSENT_MARK
    1: 1,  # P -> PRESENT_MARK
    3: 1,  # signature -> PRESENT_MARK
    # 2 = TSR -> ignored
}

def convert_labels():
    if OUT.exists():
        shutil.rmtree(OUT)

    for split, src in SPLITS.items():
        image_src = src / "images"
        label_src = src / "labels"

        image_dst = OUT / split / "images"
        label_dst = OUT / split / "labels"
        image_dst.mkdir(parents=True, exist_ok=True)
        label_dst.mkdir(parents=True, exist_ok=True)

        if not image_src.exists() or not label_src.exists():
            raise FileNotFoundError(f"Missing {image_src} or {label_src}")

        for image in image_src.iterdir():
            if image.is_file():
                shutil.copy2(image, image_dst / image.name)

        for label in label_src.glob("*.txt"):
            output_lines = []

            for raw in label.read_text(encoding="utf-8").splitlines():
                parts = raw.strip().split()
                if len(parts) != 5:
                    continue

                old_class = int(float(parts[0]))
                if old_class not in CLASS_MAP:
                    continue

                new_class = CLASS_MAP[old_class]
                output_lines.append(
                    f"{new_class} " + " ".join(parts[1:])
                )

            (label_dst / label.name).write_text(
                "\n".join(output_lines),
                encoding="utf-8"
            )

    data = {
        "path": str(OUT.resolve()),
        "train": "train/images",
        "val": "val/images",
        "nc": 2,
        "names": ["ABSENT_MARK", "PRESENT_MARK"],
    }

    (OUT / "data.yaml").write_text(
        yaml.safe_dump(data, sort_keys=False),
        encoding="utf-8"
    )

def main():
    random.seed(42)
    convert_labels()

    print("\n2-class dataset created:")
    print("  0 = ABSENT_MARK")
    print("  1 = PRESENT_MARK")
    print("  P and signature are both PRESENT_MARK.")
    print("  TSR annotations are ignored.\n")

    model = YOLO("yolov8n.pt")

    results = model.train(
        data=str((OUT / "data.yaml").resolve()),
        epochs=100,
        imgsz=960,
        batch=4,
        workers=2,
        device="cpu",
        patience=25,
        project="runs/detect",
        name="attendance_marks_final",
        pretrained=True,

        # Conservative augmentation for handwriting/signatures.
        degrees=3,
        translate=0.08,
        scale=0.15,
        shear=2,
        perspective=0.0005,
        fliplr=0.0,
        flipud=0.0,
        mosaic=0.5,
        mixup=0.0,
        copy_paste=0.0,
        hsv_h=0.01,
        hsv_s=0.25,
        hsv_v=0.20,
    )

    best = Path("runs/detect/attendance_marks_final/weights/best.pt")
    weights = Path("weights")
    weights.mkdir(exist_ok=True)

    if best.exists():
        shutil.copy2(best, weights / "attendance_marks_final.pt")
        print("\nTRAINING COMPLETE")
        print(f"Best model: {best}")
        print(f"Copied to: {weights / 'attendance_marks_final.pt'}")
    else:
        print("\nTraining finished, but best.pt was not found at:")
        print(best)

if __name__ == "__main__":
    main()
