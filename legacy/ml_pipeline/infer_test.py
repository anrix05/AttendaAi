# import os
# import glob
# from ultralytics import YOLO

# # 1. Load your trained weights
# model_path = "weights/tsr_yolo.pt"
# if not os.path.exists(model_path):
#     # Fallback to runs folder if not yet copied
#     model_path = "runs/detect/tsr_production/weights/best.pt"

# print(f"📦 Loading model from: {model_path}")
# model = YOLO(model_path)

# # 2. Pick the first image found in the Roboflow dataset folder
# train_images = glob.glob("VIT-Attendance-TSR-1/train/images/*.*")
# if not train_images:
#     raise FileNotFoundError("No images found in VIT-Attendance-TSR-1/train/images/")

# test_image_path = train_images[0]
# print(f"🔍 Running inference on: {test_image_path}")

# # 3. Run prediction
# results = model.predict(
#     source=test_image_path,
#     conf=0.25,        # 25% confidence threshold
#     save=True,        # Automatically saves the image with drawn bounding boxes
#     project="runs/detect",
#     name="test_inference",
#     exist_ok=True
# )

# for r in results:
#     boxes = r.boxes
#     print(f"\n✅ Total detections: {len(boxes)}")
#     for box in boxes:
#         cls_id = int(box.cls[0].item())
#         cls_name = model.names[cls_id]
#         conf = float(box.conf[0].item())
#         coords = [round(x, 1) for x in box.xyxy[0].tolist()]
#         print(f"Detected: {cls_name:<12} | Conf: {conf:.2f} | BBox: {coords}")

# print(f"\n🖼️ Annotated result image saved in: runs/detect/test_inference/")














import os
import glob
from collections import Counter
from pathlib import Path

from ultralytics import YOLO


# ============================================================
# PROJECT ROOT
# ============================================================

# infer_test.py is inside:
# attendance_platform/backend/ml_pipeline/
#
# parents[0] = ml_pipeline
# parents[1] = backend
# parents[2] = attendance_platform

BASE_DIR = Path(__file__).resolve().parents[2]


# ============================================================
# MODEL PATHS
# ============================================================

OLD_MODEL = BASE_DIR / "weights" / "tsr_yolo.pt"

RETRAINED_MODEL = BASE_DIR / "weights" / "tsr_yolo_retrained.pt"

OLD_FALLBACK = (
    BASE_DIR
    / "runs"
    / "detect"
    / "tsr_production"
    / "weights"
    / "best.pt"
)

RETRAINED_FALLBACK = (
    BASE_DIR
    / "runs"
    / "detect"
    / "tsr_retrained"
    / "weights"
    / "best.pt"
)


# ============================================================
# FIND MODEL
# ============================================================

def find_model(primary, fallback):

    if primary.exists():
        return primary

    if fallback.exists():
        return fallback

    raise FileNotFoundError(
        "Model not found.\n\n"
        f"Checked:\n"
        f"  - {primary}\n"
        f"  - {fallback}"
    )


old_model_path = find_model(
    OLD_MODEL,
    OLD_FALLBACK
)

retrained_model_path = find_model(
    RETRAINED_MODEL,
    RETRAINED_FALLBACK
)


# ============================================================
# FIND TEST IMAGE
# ============================================================

search_locations = [

    BASE_DIR / "VIT-Attendance-TSR-1" / "train" / "images",

    BASE_DIR / "VIT-Attendance-TSR-1" / "valid" / "images",

    BASE_DIR / "VIT-Attendance-TSR-1" / "val" / "images"
]


test_images = []

for folder in search_locations:

    if folder.exists():

        test_images.extend(
            glob.glob(str(folder / "*.*"))
        )


if not test_images:

    raise FileNotFoundError(
        "No test images found in dataset."
    )


# Same image will be used for BOTH models
test_image_path = test_images[0]


# ============================================================
# DISPLAY CONFIGURATION
# ============================================================

print("\n" + "=" * 70)
print("YOLO MODEL COMPARISON")
print("=" * 70)

print(
    f"\n📁 Project root:\n"
    f"   {BASE_DIR}"
)

print(
    f"\n🔍 Test image:\n"
    f"   {test_image_path}"
)

print(
    f"\n📦 Old model:\n"
    f"   {old_model_path}"
)

print(
    f"\n📦 Retrained model:\n"
    f"   {retrained_model_path}"
)


# ============================================================
# LOAD BOTH MODELS
# ============================================================

print("\nLoading models...")

old_model = YOLO(str(old_model_path))

retrained_model = YOLO(str(retrained_model_path))

print("✅ Both models loaded successfully.")


# ============================================================
# RUN MODEL
# ============================================================

def run_model(model, model_name, output_folder):

    print("\n" + "-" * 70)
    print(f"RUNNING: {model_name}")
    print("-" * 70)

    results = model.predict(

        source=str(test_image_path),

        conf=0.25,

        iou=0.50,

        imgsz=640,

        save=True,

        project=str(BASE_DIR / "runs" / "detect"),

        name=output_folder,

        exist_ok=True,

        verbose=False
    )

    total_detections = 0

    class_counts = Counter()

    for result in results:

        boxes = result.boxes

        total_detections += len(boxes)

        print(
            f"\n✅ Total detections: "
            f"{len(boxes)}"
        )

        if len(boxes) == 0:

            print(
                "⚠️ No objects detected."
            )

            continue

        for index, box in enumerate(boxes):

            cls_id = int(
                box.cls[0].item()
            )

            cls_name = model.names[cls_id]

            confidence = float(
                box.conf[0].item()
            )

            coordinates = [
                round(value, 1)
                for value in box.xyxy[0].tolist()
            ]

            class_counts[cls_name] += 1

            print(
                f"{index + 1:02d}. "
                f"Class={cls_name:<20} "
                f"Confidence={confidence:.3f} "
                f"BBox={coordinates}"
            )

    # --------------------------------------------------------
    # CLASS SUMMARY
    # --------------------------------------------------------

    print("\n📊 Class summary:")

    if class_counts:

        for class_name, count in class_counts.items():

            print(
                f"   {class_name:<25}: {count}"
            )

    else:

        print("   No detections")

    output_path = (
        BASE_DIR
        / "runs"
        / "detect"
        / output_folder
    )

    print(
        f"\n🖼️ Annotated image:\n"
        f"   {output_path}"
    )

    return total_detections, class_counts


# ============================================================
# TEST OLD MODEL
# ============================================================

old_total, old_counts = run_model(

    old_model,

    "OLD MODEL",

    "test_old_model"
)


# ============================================================
# TEST RETRAINED MODEL
# ============================================================

retrained_total, retrained_counts = run_model(

    retrained_model,

    "RETRAINED MODEL",

    "test_retrained_model"
)


# ============================================================
# FINAL COMPARISON
# ============================================================

print("\n" + "=" * 70)
print("FINAL COMPARISON")
print("=" * 70)

print(
    f"\nOld model detections      : "
    f"{old_total}"
)

print(
    f"Retrained model detections: "
    f"{retrained_total}"
)


# ============================================================
# CLASS-BY-CLASS COMPARISON
# ============================================================

all_classes = sorted(
    set(old_counts.keys()) |
    set(retrained_counts.keys())
)

print("\nClass-by-class comparison:")

if all_classes:

    print(
        f"\n{'Class':<25}"
        f"{'Old':<10}"
        f"{'Retrained':<12}"
    )

    print("-" * 47)

    for class_name in all_classes:

        old_count = old_counts.get(
            class_name,
            0
        )

        retrained_count = retrained_counts.get(
            class_name,
            0
        )

        print(
            f"{class_name:<25}"
            f"{old_count:<10}"
            f"{retrained_count:<12}"
        )

else:

    print("No detections from either model.")


# ============================================================
# OUTPUT
# ============================================================

print("\n" + "=" * 70)
print("RESULT FILES")
print("=" * 70)

print(
    "\nOLD MODEL:"
)

print(
    f"   {BASE_DIR / 'runs' / 'detect' / 'test_old_model'}"
)

print(
    "\nRETRAINED MODEL:"
)

print(
    f"   {BASE_DIR / 'runs' / 'detect' / 'test_retrained_model'}"
)

print(
    "\n✅ Model comparison completed."
)