"""
mark_detector.py
─────────────────
YOLO-based attendance mark detector.
Acts as verification layer: confirms Gemini's P/A decisions
and catches marks that Gemini may have missed.
"""

from pathlib import Path

import cv2
import numpy as np
from ultralytics import YOLO


# ─────────────────────────────────────────────────────────────
# CLASS → STATUS MAPPING
# ─────────────────────────────────────────────────────────────

ABSENT_CLASSES  = {"a", "absent", "ab"}
PRESENT_CLASSES = {"p", "present", "signature", "sign"}
IGNORE_CLASSES  = {"vit-attendance-tsr"}   # table header label — useless


# ─────────────────────────────────────────────────────────────
# MARK DETECTOR
# ─────────────────────────────────────────────────────────────

class MarkDetector:
    """
    Wraps the trained YOLO model for attendance mark detection.
    """

    DEFAULT_CONF = 0.25
    DEFAULT_IOU  = 0.45
    DEFAULT_IMGSZ = 1280   # larger than default for better small-mark detection

    def __init__(
        self,
        model_path:         str | Path | None = None,
        conf:               float = DEFAULT_CONF,
        iou:                float = DEFAULT_IOU,
        imgsz:              int   = DEFAULT_IMGSZ,
        uncertain_threshold: float = 0.45,
    ):
        self.conf                = conf
        self.iou                 = iou
        self.imgsz               = imgsz
        self.uncertain_threshold = uncertain_threshold

        model_path = self._resolve_model_path(model_path)
        print()
        print(f"🔍 Loading YOLO model:")
        print(f"   {model_path}")
        self.model = YOLO(str(model_path))

    # ─────────────────────────────────────────
    # RESOLVE MODEL PATH
    # ─────────────────────────────────────────

    @staticmethod
    def _resolve_model_path(model_path: str | Path | None) -> Path:
        """
        Find the best available trained model.
        Search order:
          1. Caller-specified path
          2. weights/tsr_yolo_retrained.pt
          3. weights/tsr_yolo.pt
          4. runs/detect/tsr_retrained/weights/best.pt
          5. runs/detect/tsr_production/weights/best.pt
        """
        if model_path is not None:
            p = Path(model_path)
            if p.exists():
                return p
            raise FileNotFoundError(f"Model not found: {model_path}")

        # attendance_platform/backend/vision/mark_detector.py
        # parents: [vision, backend, attendance_platform]
        base = Path(__file__).resolve().parents[2]

        candidates = [
            base / "weights" / "tsr_yolo_retrained.pt",
            base / "weights" / "tsr_yolo.pt",
            base / "runs" / "detect" / "tsr_retrained" / "weights" / "best.pt",
            base / "runs" / "detect" / "tsr_production" / "weights" / "best.pt",
        ]

        for candidate in candidates:
            if candidate.exists():
                return candidate

        raise FileNotFoundError(
            "No YOLO model found. Train one first with:\n"
            "  python backend/ml_pipeline/train_yolo.py\n"
            f"Searched:\n" + "\n".join(f"  {c}" for c in candidates)
        )

    # ─────────────────────────────────────────
    # DETECT
    # ─────────────────────────────────────────

    def detect(self, image: np.ndarray) -> list[dict]:
        """
        Run YOLO inference on the full image.

        Returns list of detections:
            class_name  : str
            status      : "PRESENT" | "ABSENT"
            confidence  : float
            certainty   : "CERTAIN" | "UNCERTAIN"
            x1, y1, x2, y2 : float (pixel coordinates)
            center_x, center_y : float
        """
        results = self.model.predict(
            source  = image,
            conf    = self.conf,
            iou     = self.iou,
            imgsz   = self.imgsz,
            verbose = False,
        )

        detections = []
        names = self.model.names

        for result in results:
            if result.boxes is None:
                continue

            for box in result.boxes:
                cls_id      = int(box.cls[0].item())
                confidence  = float(box.conf[0].item())
                x1, y1, x2, y2 = (float(v) for v in box.xyxy[0].tolist())

                if isinstance(names, dict):
                    class_name = str(names.get(cls_id, cls_id))
                else:
                    class_name = str(names[cls_id])

                lower = class_name.lower().strip()

                if lower in IGNORE_CLASSES:
                    continue
                elif lower in ABSENT_CLASSES:
                    status = "ABSENT"
                elif lower in PRESENT_CLASSES:
                    status = "PRESENT"
                else:
                    # Unknown class — treat as PRESENT if it looks like ink
                    status = "PRESENT"

                certainty = (
                    "CERTAIN"
                    if confidence >= self.uncertain_threshold
                    else "UNCERTAIN"
                )

                detections.append({
                    "class_name": class_name,
                    "status":     status,
                    "confidence": round(confidence, 4),
                    "certainty":  certainty,
                    "x1": round(x1, 1),
                    "y1": round(y1, 1),
                    "x2": round(x2, 1),
                    "y2": round(y2, 1),
                    "center_x": round((x1 + x2) / 2, 1),
                    "center_y": round((y1 + y2) / 2, 1),
                })

        print()
        print(f"   YOLO detections: {len(detections)}")
        return detections
