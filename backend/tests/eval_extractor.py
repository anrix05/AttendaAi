"""
backend/tests/eval_extractor.py — Accuracy and Metric Evaluation for Sheet Extractor
"""
import json
import sys
import time
from pathlib import Path
from typing import Dict, Any

# Ensure project root is in sys.path
BASE_DIR = Path(__file__).resolve().parents[2]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from backend.config import settings
from backend.vision.extractor import get_extractor, MockExtractor
from backend.schemas import AttendanceStatus

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
GROUND_TRUTH_FILE = FIXTURES_DIR / "ground_truth_ss_divb.json"
SAMPLE_IMAGE = FIXTURES_DIR / "sample_sheet_vit.jpg"


def run_evaluation(use_mock: bool = False) -> Dict[str, Any]:
    print("=" * 70)
    print("ATTENDAI EXTRACTOR ACCURACY & METRICS EVALUATION")
    print("=" * 70)
    print(f"Sample Image   : {SAMPLE_IMAGE}")
    print(f"Ground Truth   : {GROUND_TRUTH_FILE}")
    print(f"Extractor Mode : {'MockExtractor (Offline)' if use_mock else f'Live Gemini Vision ({settings.GEMINI_MODEL})'}")
    print()

    with open(GROUND_TRUTH_FILE, "r", encoding="utf-8") as f:
        gt_data = json.load(f)

    extractor = MockExtractor() if use_mock else get_extractor(use_mock=False)

    t0 = time.time()
    try:
        preview = extractor.extract(SAMPLE_IMAGE)
    except Exception as exc:
        print(f"⚠️ Extraction failed with live API ({exc}). Falling back to MockExtractor for metrics baseline.")
        extractor = MockExtractor()
        preview = extractor.extract(SAMPLE_IMAGE)
    elapsed = time.time() - t0

    # Build GT mapping: (roll_no, col_idx) -> status
    gt_map = {}
    dates = gt_data["dates"]
    for s in gt_data["students"]:
        for d in dates:
            rec = s["records"].get(d["iso"])
            if rec:
                gt_map[(s["roll_no"], d["col_idx"])] = rec["status"]

    total_cells = 0
    correct_cells = 0
    uncertain_cells = 0
    false_positives_p_vs_a = 0  # Confidently wrong A vs P
    confusion = {}

    for row in preview.rows:
        for c in row.cells:
            key = (row.roll_no, c.col_idx)
            if key not in gt_map:
                continue

            expected = gt_map[key]
            predicted = c.status.value
            total_cells += 1

            pair = (expected, predicted)
            confusion[pair] = confusion.get(pair, 0) + 1

            if predicted == "UNCERTAIN":
                uncertain_cells += 1
            elif predicted == expected:
                correct_cells += 1
            else:
                if (expected == "P" and predicted == "A") or (expected == "A" and predicted == "P"):
                    false_positives_p_vs_a += 1

    accuracy = (correct_cells / (total_cells - uncertain_cells) * 100) if (total_cells - uncertain_cells) > 0 else 0.0
    overall_exact_match = (correct_cells / total_cells * 100) if total_cells > 0 else 0.0
    uncertain_pct = (uncertain_cells / total_cells * 100) if total_cells > 0 else 0.0

    print("EVALUATION RESULTS:")
    print(f"   Total Evaluated Cells  : {total_cells}")
    print(f"   Correct Matches        : {correct_cells}")
    print(f"   Uncertain Cells        : {uncertain_cells} ({uncertain_pct:.1f}%)")
    print(f"   Confidently Wrong (P/A): {false_positives_p_vs_a}")
    print(f"   Cell Accuracy (excl ?) : {accuracy:.1f}%")
    print(f"   Total Exact Match      : {overall_exact_match:.1f}%")
    print(f"   Processing Time        : {elapsed:.2f}s")
    print()
    print("CONFUSION PAIRS (Expected -> Predicted):")
    for (exp, pred), count in sorted(confusion.items()):
        print(f"   {exp:>9} -> {pred:<9} : {count} cells")
    print("=" * 70)

    return {
        "total_cells": total_cells,
        "correct_cells": correct_cells,
        "uncertain_cells": uncertain_cells,
        "uncertain_pct": uncertain_pct,
        "accuracy": accuracy,
        "false_p_vs_a": false_positives_p_vs_a,
        "elapsed_sec": elapsed,
    }


if __name__ == "__main__":
    import sys
    use_mock_flag = "--mock" in sys.argv
    run_evaluation(use_mock=use_mock_flag)
