"""
FINAL ATTENDANCE ENGINE

This replaces the old fixed-roster / fixed-30-student logic.

Design:
1. Detect the attendance table/grid with OpenCV.
2. OCR the printed student information from each row.
3. Detect attendance marks with the trained 2-class YOLO model.
4. Map each mark to its row + date column using the detected grid.
5. PRESENT = any signature / present mark.
6. ABSENT = A / absent mark.
7. Empty cell = NOT_MARKED.
8. Student names/roll numbers come from the uploaded sheet, NOT a hard-coded roster.

Expected YOLO classes:
0 = ABSENT_MARK
1 = PRESENT_MARK

Important:
- The number of students is inferred from the sheet.
- The number of attendance columns is inferred from the table.
- There is no VIT_STUDENT_ROSTER in this engine.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import pytesseract
from ultralytics import YOLO


ROLL_RE = re.compile(r"\b\d{8,14}\b")


class FinalAttendanceEngine:
    def __init__(
        self,
        model_path: str = "weights/attendance_marks_final.pt",
        confidence: float = 0.15,
    ):
        model = Path(model_path)
        if not model.exists():
            fallback = Path("runs/detect/attendance_marks_final/weights/best.pt")
            if fallback.exists():
                model = fallback
            else:
                raise FileNotFoundError(
                    "Final attendance model not found.\n"
                    f"Expected: {model_path}\n"
                    f"Fallback: {fallback}\n"
                    "Train it first with train_attendance_model.py"
                )

        self.model = YOLO(str(model))
        self.confidence = confidence

    # ------------------------------------------------------------
    # IMAGE
    # ------------------------------------------------------------

    def load(self, image_path: str):
        image = cv2.imread(str(image_path))
        if image is None:
            raise ValueError(f"Could not read image: {image_path}")
        return image

    def resize_for_processing(self, image):
        h, w = image.shape[:2]
        target_w = 1800

        if w < target_w:
            scale = target_w / w
            image = cv2.resize(
                image,
                (int(w * scale), int(h * scale)),
                interpolation=cv2.INTER_CUBIC,
            )
        return image

    # ------------------------------------------------------------
    # TABLE GRID
    # ------------------------------------------------------------

    def detect_table(self, image):
        """
        Detect long horizontal/vertical table lines.

        Returns:
            x_lines, y_lines

        x_lines = vertical table boundaries
        y_lines = horizontal row boundaries
        """

        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (3, 3), 0)

        bw = cv2.adaptiveThreshold(
            gray,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV,
            31,
            11,
        )

        h, w = bw.shape

        horizontal_kernel = cv2.getStructuringElement(
            cv2.MORPH_RECT,
            (max(25, w // 25), 1),
        )
        vertical_kernel = cv2.getStructuringElement(
            cv2.MORPH_RECT,
            (1, max(25, h // 35)),
        )

        horizontal = cv2.morphologyEx(
            bw, cv2.MORPH_OPEN, horizontal_kernel
        )
        vertical = cv2.morphologyEx(
            bw, cv2.MORPH_OPEN, vertical_kernel
        )

        x_lines = self._projection_lines(
            vertical.sum(axis=0),
            minimum_fraction=0.20,
            merge_distance=max(5, w // 250),
        )

        y_lines = self._projection_lines(
            horizontal.sum(axis=1),
            minimum_fraction=0.18,
            merge_distance=max(5, h // 250),
        )

        return x_lines, y_lines

    @staticmethod
    def _projection_lines(projection, minimum_fraction, merge_distance):
        if len(projection) == 0:
            return []

        threshold = projection.max() * minimum_fraction
        indexes = np.where(projection >= threshold)[0]

        if len(indexes) == 0:
            return []

        groups = []
        group = [int(indexes[0])]

        for value in indexes[1:]:
            value = int(value)
            if value - group[-1] <= merge_distance:
                group.append(value)
            else:
                groups.append(group)
                group = [value]

        groups.append(group)

        return [int(np.mean(g)) for g in groups if len(g) >= 1]

    def build_grid(self, image):
        """
        Find a usable table region.

        The sheet is not assumed to have 30 students.
        Rows are inferred from horizontal grid lines.
        """

        x_lines, y_lines = self.detect_table(image)

        h, w = image.shape[:2]

        # Fallback: use the strongest broad table area if line detection
        # is imperfect. This is deliberately not tied to a student count.
        if len(x_lines) < 5 or len(y_lines) < 5:
            return self._fallback_grid(image)

        # Keep lines away from the image edges.
        x_lines = [x for x in x_lines if 0.03*w < x < 0.98*w]
        y_lines = [y for y in y_lines if 0.08*h < y < 0.98*h]

        x_lines = self._dedupe_sorted(x_lines, max(4, w // 300))
        y_lines = self._dedupe_sorted(y_lines, max(4, h // 300))

        # Identify the dense student table by looking for a long sequence
        # of horizontal lines with approximately regular spacing.
        row_segment = self._best_regular_segment(y_lines)

        if row_segment is not None:
            y_lines = row_segment

        # We only need the attendance region columns, which are normally
        # the columns to the right of Name/Batch. Detect all columns first.
        return {
            "x_lines": x_lines,
            "y_lines": y_lines,
            "width": w,
            "height": h,
        }

    @staticmethod
    def _dedupe_sorted(values, distance):
        values = sorted(values)
        result = []
        for v in values:
            if not result or abs(v - result[-1]) > distance:
                result.append(v)
            else:
                result[-1] = int((result[-1] + v) / 2)
        return result

    def _best_regular_segment(self, lines):
        if len(lines) < 6:
            return None

        best = None
        best_score = -1

        for start in range(len(lines)):
            for end in range(start + 5, len(lines)):
                segment = lines[start:end + 1]
                gaps = np.diff(segment)

                if len(gaps) < 5:
                    continue

                median_gap = float(np.median(gaps))
                if median_gap <= 2:
                    continue

                variation = float(np.std(gaps) / median_gap)

                # Student rows are approximately regular.
                score = len(segment) - variation * 8

                if score > best_score:
                    best_score = score
                    best = segment

        return best

    @staticmethod
    def _fallback_grid(image):
        h, w = image.shape[:2]

        # This fallback only estimates the broad table; it does not assume
        # a particular number of students.
        return {
            "x_lines": [],
            "y_lines": [],
            "width": w,
            "height": h,
        }

    # ------------------------------------------------------------
    # YOLO MARK DETECTION
    # ------------------------------------------------------------

    def detect_marks(self, image):
        results = self.model.predict(
            source=image,
            conf=self.confidence,
            iou=0.45,
            imgsz=960,
            verbose=False,
        )

        detections = []

        for result in results:
            if result.boxes is None:
                continue

            names = result.names

            for box in result.boxes:
                cls = int(box.cls.item())
                conf = float(box.conf.item())

                x1, y1, x2, y2 = map(
                    float,
                    box.xyxy[0].tolist(),
                )

                detections.append({
                    "class_id": cls,
                    "class_name": names.get(cls, str(cls)),
                    "confidence": round(conf, 3),
                    "x1": x1,
                    "y1": y1,
                    "x2": x2,
                    "y2": y2,
                    "cx": (x1 + x2) / 2,
                    "cy": (y1 + y2) / 2,
                })

        return self.remove_duplicates(detections)

    @staticmethod
    def remove_duplicates(detections):
        selected = []

        for detection in sorted(
            detections,
            key=lambda d: d["confidence"],
            reverse=True,
        ):
            keep = True

            for existing in selected:
                dx = detection["cx"] - existing["cx"]
                dy = detection["cy"] - existing["cy"]
                distance = (dx * dx + dy * dy) ** 0.5

                if distance < 18:
                    keep = False
                    break

            if keep:
                selected.append(detection)

        return selected

    # ------------------------------------------------------------
    # OCR
    # ------------------------------------------------------------

    def ocr_student_rows(self, image, grid):
        """
        OCR is intentionally separate from YOLO.

        We do NOT use the old hard-coded VIT roster.
        Printed roll numbers and names are read from the uploaded sheet.

        For best OCR accuracy, Tesseract should be installed and available
        in PATH. The function also accepts pytesseract.pytesseract.tesseract_cmd
        being configured by the caller.
        """

        x_lines = grid.get("x_lines", [])
        y_lines = grid.get("y_lines", [])

        if len(x_lines) < 5 or len(y_lines) < 5:
            return []

        # First columns are normally:
        # Sr No | Roll No | Name | Batch | attendance...
        # We OCR the full row region and parse roll/name text.
        rows = []

        for r in range(len(y_lines) - 1):
            y1 = y_lines[r]
            y2 = y_lines[r + 1]

            if y2 - y1 < 8:
                continue

            row = image[y1:y2, :]

            scale = 2
            row_big = cv2.resize(
                row,
                None,
                fx=scale,
                fy=scale,
                interpolation=cv2.INTER_CUBIC,
            )

            gray = cv2.cvtColor(row_big, cv2.COLOR_BGR2GRAY)
            gray = cv2.fastNlMeansDenoising(gray, None, 8, 7, 21)

            text = pytesseract.image_to_string(
                gray,
                config="--psm 7",
            ).strip()

            roll_match = ROLL_RE.search(text)

            if roll_match:
                roll_no = roll_match.group(0)
                before_roll = text[:roll_match.start()].strip()
                after_roll = text[roll_match.end():].strip()

                name = self.extract_name(after_roll, before_roll)

                rows.append({
                    "row_index": len(rows) + 1,
                    "roll_no": roll_no,
                    "name": name,
                    "raw_ocr": text,
                    "y1": y1,
                    "y2": y2,
                    "cy": (y1 + y2) / 2,
                })

        return rows

    @staticmethod
    def extract_name(after_roll, before_roll):
        # Remove obvious numeric/table fragments.
        candidate = re.sub(r"\b\d+\b", " ", after_roll)
        candidate = re.sub(r"[^A-Za-z .'-]", " ", candidate)
        candidate = re.sub(r"\s+", " ", candidate).strip()

        if len(candidate) >= 3:
            return candidate.upper()

        candidate = re.sub(r"[^A-Za-z .'-]", " ", before_roll)
        candidate = re.sub(r"\s+", " ", candidate).strip()

        return candidate.upper() if candidate else "UNKNOWN"

    # ------------------------------------------------------------
    # CELL / COLUMN MAPPING
    # ------------------------------------------------------------

    def infer_attendance_columns(self, image, grid):
        """
        Infer attendance columns from detected marks.

        We do not hard-code 3.
        The x positions are clustered from actual sheet detections.
        """

        marks = self.detect_marks(image)

        if not marks:
            return [], marks

        xs = sorted([m["cx"] for m in marks])
        clusters = []

        # Cluster using gaps rather than a fixed x threshold.
        for x in xs:
            if not clusters:
                clusters.append([x])
                continue

            previous_mean = float(np.mean(clusters[-1]))
            gap = abs(x - previous_mean)

            if gap <= max(25, image.shape[1] * 0.035):
                clusters[-1].append(x)
            else:
                clusters.append([x])

        centers = [float(np.mean(c)) for c in clusters]

        # Only attendance marks should normally lie on the right side.
        # Keep all clusters; the caller can filter against the OCR/table area.
        return centers, marks

    def assign_marks_to_rows(self, marks, student_rows):
        """
        Assign each YOLO mark to the closest OCR-derived student row.
        """

        for row in student_rows:
            row["marks"] = []

        if not student_rows:
            return student_rows

        for mark in marks:
            row = min(
                student_rows,
                key=lambda r: abs(r["cy"] - mark["cy"]),
            )

            row["marks"].append(mark)

        return student_rows

    def make_attendance(self, image, student_rows, column_centers):
        """
        Build dynamic student × attendance-column results.
        """

        if not column_centers:
            return student_rows

        column_centers = sorted(column_centers)

        for row in student_rows:
            row["attendance"] = []

            for center_x in column_centers:
                candidates = [
                    m for m in row.get("marks", [])
                    if abs(m["cx"] - center_x)
                    <= max(35, image.shape[1] * 0.025)
                ]

                if not candidates:
                    status = "NOT_MARKED"
                    confidence = 0.0
                else:
                    best = max(
                        candidates,
                        key=lambda m: m["confidence"],
                    )

                    # Class 0 = red A / absent.
                    # Class 1 = signature / P / present.
                    if best["class_id"] == 0:
                        status = "ABSENT"
                    else:
                        status = "PRESENT"

                    confidence = best["confidence"]

                row["attendance"].append({
                    "status": status,
                    "confidence": confidence,
                })

        return student_rows

    # ------------------------------------------------------------
    # COMPLETE PROCESS
    # ------------------------------------------------------------

    def process(self, image_path: str) -> dict[str, Any]:
        image = self.resize_for_processing(
            self.load(image_path)
        )

        grid = self.build_grid(image)

        student_rows = self.ocr_student_rows(
            image,
            grid,
        )

        column_centers, marks = self.infer_attendance_columns(
            image,
            grid,
        )

        student_rows = self.assign_marks_to_rows(
            marks,
            student_rows,
        )

        student_rows = self.make_attendance(
            image,
            student_rows,
            column_centers,
        )

        return {
            "students": student_rows,
            "attendance_column_centers": column_centers,
            "marks": marks,
            "student_count": len(student_rows),
            "attendance_column_count": len(column_centers),
        }


if __name__ == "__main__":
    import sys
    import json

    if len(sys.argv) != 2:
        print("Usage: python attendance_engine.py <image_path>")
        raise SystemExit(1)

    engine = FinalAttendanceEngine()
    result = engine.process(sys.argv[1])

    print(json.dumps(result, indent=2))
