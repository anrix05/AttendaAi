"""
process_sheet.py
─────────────────
Main orchestrator for the Attendance Sheet Analysis Pipeline.

Pipeline stages:
  1. Image preprocessing (perspective, deskew, CLAHE)
  2. Gemini Vision extraction (student data + attendance marks)
  3. YOLO mark detection (verification layer)
  4. OpenCV cell analysis (empty/ink/red-ink per cell)
  5. Decision fusion (Gemini + YOLO + OpenCV → P/A/NM/?)
  6. Result packaging

Usage
-----
    from backend.ml_pipeline.process_sheet import AttendanceProcessor
    processor = AttendanceProcessor(api_key="YOUR_GEMINI_KEY")
    result    = processor.process("path/to/image.jpg")
"""

import sys
import time
from pathlib import Path

# Allow running directly: python backend/ml_pipeline/process_sheet.py
BASE_DIR = Path(__file__).resolve().parents[2]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import cv2
import numpy as np

from backend.vision.preprocessing   import preprocess
from backend.vision.gemini_extractor import GeminiExtractor
from backend.vision.cell_analyzer   import analyze_cell
from backend.vision.mark_detector   import MarkDetector
from backend.intelligence.decision_engine import decide, decide_all


# ─────────────────────────────────────────────────────────────
# ATTENDANCE PROCESSOR
# ─────────────────────────────────────────────────────────────

class AttendanceProcessor:
    """
    End-to-end attendance sheet processor.

    Parameters
    ----------
    api_key       : Gemini API key (falls back to GEMINI_API_KEY env var)
    yolo_model    : Path to YOLO .pt file (auto-detected if None)
    use_yolo      : Whether to run YOLO verification (default True)
    use_opencv    : Whether to run per-cell OpenCV analysis (default True)
    """

    def __init__(
        self,
        api_key:   str | None  = None,
        yolo_model: str | None = None,
        use_yolo:  bool        = True,
        use_opencv: bool       = True,
    ):
        self.use_yolo   = use_yolo
        self.use_opencv = use_opencv

        # Gemini extractor (required)
        self.gemini = GeminiExtractor(api_key=api_key)

        # YOLO mark detector (optional — skip if model missing)
        self.mark_detector = None
        if use_yolo:
            try:
                self.mark_detector = MarkDetector(model_path=yolo_model)
            except FileNotFoundError as exc:
                print(f"⚠️  YOLO model not found — running Vision-only mode.")
                print(f"   {exc}")
                self.use_yolo = False

    # ─────────────────────────────────────────────────────────
    # MAIN PROCESS METHOD
    # ─────────────────────────────────────────────────────────

    def process(self, image_path: str) -> dict:
        """
        Process a single attendance sheet image.

        Returns
        -------
        dict with:
            sheet_info : {subject, class, academic_year, dates}
            students   : list of student dicts with attendance
            decisions  : list of per-cell decisions
            summary    : {present_count, absent_count, uncertain_count, not_marked_count}
            image_path : str
        """
        t_start = time.time()
        image_path = str(image_path)

        print()
        print("=" * 70)
        print("ATTENDANCE SHEET ANALYSIS PIPELINE")
        print("=" * 70)
        print(f"Image: {image_path}")

        # ── Stage 1: Preprocessing ────────────────────────────
        print()
        print("Stage 1 ── Image preprocessing...")
        try:
            image = preprocess(image_path)
            print(f"   Output size: {image.shape[1]}×{image.shape[0]} px")
        except Exception as exc:
            print(f"⚠️  Preprocessing failed ({exc}), using raw image.")
            image = cv2.imread(image_path)
            if image is None:
                raise ValueError(f"Cannot read image: {image_path}")

        # ── Stage 2: OCR Vision extraction ────────────────────────
        print()
        print("Stage 2 ── OCR Vision Engine extraction...")
        gemini_result = self.gemini.extract(image_path)

        sheet_info = gemini_result.get("sheet_info") or {}
        students   = gemini_result.get("students")   or []
        dates      = sheet_info.get("dates")          or []

        print(f"   Students extracted : {len(students)}")
        print(f"   Date columns       : {len(dates)}")

        # ── Stage 3: YOLO detection ───────────────────────────
        yolo_detections = []
        if self.use_yolo and self.mark_detector:
            print()
            print("Stage 3 ── YOLO verification...")
            try:
                yolo_detections = self.mark_detector.detect(image)
            except Exception as exc:
                print(f"⚠️  YOLO failed ({exc}), skipping.")

        # ── Stage 4: Build cell grid + OpenCV analysis ────────
        print()
        print("Stage 4 ── Building attendance cell grid...")

        # Estimate cell regions based on image dimensions
        # We don't rely on grid line detection here because the OCR Engine
        # already gave us the data — this is for OpenCV verification only.
        cell_grid, cell_analyses = self._build_cell_grid(
            image, students, dates
        )

        print(f"   Attendance cells analyzed: {len(cell_analyses)}")

        # ── Stage 5: Decision fusion ──────────────────────────
        print()
        print("Stage 5 ── Decision fusion (OCR + YOLO + OpenCV)...")

        decisions = decide_all(
            gemini_result  = gemini_result,
            yolo_detections= yolo_detections,
            cell_grid      = cell_grid,
            cell_analyses  = cell_analyses,
        )

        # ── Stage 6: Summary ──────────────────────────────────
        summary = self._summarize(decisions)

        elapsed = time.time() - t_start

        print()
        print("-" * 70)
        print("SUMMARY")
        print(f"   Present    : {summary['present_count']}")
        print(f"   Absent     : {summary['absent_count']}")
        print(f"   Not Marked : {summary['not_marked_count']}")
        print(f"   Uncertain  : {summary['uncertain_count']}")
        print(f"   Review needed: {summary['review_count']}")
        print(f"   Total time : {elapsed:.1f}s")
        print("=" * 70)

        return {
            "sheet_info": sheet_info,
            "students":   students,
            "decisions":  decisions,
            "summary":    summary,
            "image_path": image_path,
        }

    # ─────────────────────────────────────────────────────────
    # CELL GRID BUILDER
    # ─────────────────────────────────────────────────────────

    def _build_cell_grid(
        self,
        image:    np.ndarray,
        students: list,
        dates:    list,
    ) -> tuple[list, dict]:
        """
        Estimate pixel regions for each attendance cell and run OpenCV analysis.

        We estimate positions by dividing the image into a grid matching
        the number of students and dates. This is approximate but sufficient
        for ink/red-ink detection.

        Returns
        -------
        cell_grid      : list of {student_idx, date_idx, x1, y1, x2, y2}
        cell_analyses  : {(student_idx, date_idx): analysis_dict}
        """
        if not self.use_opencv or not students or not dates:
            return [], {}

        h, w = image.shape[:2]

        # Rough estimate: top 15% is header, bottom 5% is footer
        # The attendance body occupies the middle 80%
        header_h = int(h * 0.15)
        footer_h = int(h * 0.05)
        body_h   = h - header_h - footer_h

        # Left ~20% is student info (Sr/Roll/Name/Batch)
        # Right ~80% is attendance columns
        info_w = int(w * 0.22)
        att_w  = w - info_w

        num_students = len(students)
        num_dates    = len(dates)

        if num_students == 0 or num_dates == 0:
            return [], {}

        cell_h = body_h  // num_students
        cell_w = att_w   // num_dates

        cell_grid     = []
        cell_analyses = {}

        for s_idx in range(num_students):
            y1 = header_h + s_idx * cell_h
            y2 = y1 + cell_h

            for d_idx in range(num_dates):
                x1 = info_w + d_idx * cell_w
                x2 = x1 + cell_w

                cell_def = {
                    "student_idx": s_idx,
                    "date_idx":    d_idx,
                    "x1": x1, "y1": y1,
                    "x2": x2, "y2": y2,
                }
                cell_grid.append(cell_def)

                if self.use_opencv:
                    analysis = analyze_cell(image, cell_def)
                    cell_analyses[(s_idx, d_idx)] = analysis

        return cell_grid, cell_analyses

    # ─────────────────────────────────────────────────────────
    # SUMMARIZE
    # ─────────────────────────────────────────────────────────

    @staticmethod
    def _summarize(decisions: list) -> dict:
        present    = sum(1 for d in decisions if d["status"] == "PRESENT")
        absent     = sum(1 for d in decisions if d["status"] == "ABSENT")
        not_marked = sum(1 for d in decisions if d["status"] == "NOT_MARKED")
        uncertain  = sum(1 for d in decisions if d["status"] == "UNCERTAIN")
        review     = sum(1 for d in decisions if d.get("review"))

        return {
            "present_count":    present,
            "absent_count":     absent,
            "not_marked_count": not_marked,
            "uncertain_count":  uncertain,
            "review_count":     review,
            "total_cells":      len(decisions),
        }


# ─────────────────────────────────────────────────────────────
# DIRECT RUN / QUICK TEST
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import os

    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        print("❌ Set GEMINI_API_KEY environment variable first.")
        print("   set GEMINI_API_KEY=your_key_here")
        sys.exit(1)

    # Find first image in dataset
    dataset_dir = BASE_DIR / "VIT-Attendance-TSR-1" / "train" / "images"
    images = sorted(
        list(dataset_dir.glob("*.jpg")) +
        list(dataset_dir.glob("*.jpeg")) +
        list(dataset_dir.glob("*.png"))
    )

    if not images:
        print(f"No images found in {dataset_dir}")
        sys.exit(1)

    test_image = images[0]
    print(f"Testing on: {test_image.name}")

    processor = AttendanceProcessor(api_key=api_key)
    result    = processor.process(str(test_image))

    print()
    print("First 5 students:")
    for student in result["students"][:5]:
        print(f"  {student['sr_no']:>3}. {student['roll_no']:<14} {student['name']:<30}")
        print(f"       Attendance: {student['attendance']}")