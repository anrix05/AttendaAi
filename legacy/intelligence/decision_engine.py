"""
decision_engine.py
──────────────────
Merges Gemini extraction + YOLO + OpenCV evidence into a
final attendance decision for each cell/student-date pair.

Decision hierarchy:
  1. Gemini (primary — most reliable for structured documents)
  2. OpenCV empty-cell detection (catches missing marks Gemini may miss)
  3. YOLO (verification / fallback)
  4. Conflict → UNCERTAIN

Confidence levels:
  HIGH   ≥ 0.85   → accept automatically
  MEDIUM 0.60–0.85 → accept but flag for review
  LOW    < 0.60   → flag as UNCERTAIN / needs human review
"""

# ─────────────────────────────────────────────────────────────
# CONFIDENCE THRESHOLDS
# ─────────────────────────────────────────────────────────────

CONF_HIGH   = 0.85
CONF_MEDIUM = 0.60
YOLO_CONF   = 0.45   # minimum YOLO confidence to trust


# ─────────────────────────────────────────────────────────────
# DECISION ENGINE
# ─────────────────────────────────────────────────────────────

def decide(
    gemini_status: str | None,       # "P" | "A" | "NM" | "?" | None
    cell_analysis: dict | None,      # from cell_analyzer.analyze_cell()
    yolo_detections: list[dict],     # detections whose center falls in this cell
) -> dict:
    """
    Make the final attendance decision for one student-date cell.

    Returns:
        status     : "PRESENT" | "ABSENT" | "NOT_MARKED" | "UNCERTAIN"
        confidence : float  (0.0–1.0)
        source     : str    (which source drove the decision)
        review     : bool   (should user review this cell?)
        evidence   : list[str] (human-readable evidence notes)
    """
    evidence = []

    # ─── Map Gemini codes → canonical statuses ─────────────────
    gemini_map = {
        "P":  "PRESENT",
        "A":  "ABSENT",
        "NM": "NOT_MARKED",
        "?":  "UNCERTAIN",
    }
    gemini_canonical = gemini_map.get(str(gemini_status or "").upper(), None)

    # ─── OpenCV evidence ──────────────────────────────────────
    has_ink  = False
    is_red   = False
    density  = 0.0

    if cell_analysis:
        has_ink = cell_analysis.get("has_ink", False)
        is_red  = cell_analysis.get("is_red",  False)
        density = cell_analysis.get("density", 0.0)
        is_empty = cell_analysis.get("is_empty", True)
    else:
        is_empty = True

    if has_ink:
        evidence.append(f"ink_density={density:.2f}")
    else:
        evidence.append("cell_empty")

    if is_red:
        evidence.append("red_ink_detected")

    # ─── YOLO evidence ────────────────────────────────────────
    yolo_present = [d for d in yolo_detections if d["status"] == "PRESENT"]
    yolo_absent  = [d for d in yolo_detections if d["status"] == "ABSENT"]

    best_yolo_present = max(
        (d["confidence"] for d in yolo_present), default=0.0
    )
    best_yolo_absent  = max(
        (d["confidence"] for d in yolo_absent), default=0.0
    )

    if yolo_present:
        evidence.append(f"yolo_present={best_yolo_present:.2f}")
    if yolo_absent:
        evidence.append(f"yolo_absent={best_yolo_absent:.2f}")

    # ─── CASE 1: Gemini gave a clear answer ───────────────────
    if gemini_canonical and gemini_canonical != "UNCERTAIN":
        base_conf = 0.90   # Gemini starts with high base confidence

        # If Gemini says PRESENT but cell is empty → downgrade
        if gemini_canonical == "PRESENT" and is_empty:
            base_conf = 0.55
            evidence.append("gemini_present_but_empty_cell")
            return _result("UNCERTAIN", base_conf, "gemini+opencv_conflict", evidence)

        # If Gemini says ABSENT but no red ink and no YOLO absent → mild downgrade
        if gemini_canonical == "ABSENT" and not is_red and best_yolo_absent < YOLO_CONF:
            base_conf = 0.72
            evidence.append("gemini_absent_no_red_ink")

        # If Gemini says NOT_MARKED but ink exists → flag
        if gemini_canonical == "NOT_MARKED" and has_ink:
            base_conf = 0.60
            evidence.append("gemini_not_marked_but_ink_present")
            return _result("UNCERTAIN", base_conf, "gemini+opencv_conflict", evidence)

        # YOLO strongly disagrees → downgrade confidence
        if (
            gemini_canonical == "PRESENT"
            and best_yolo_absent > 0.70
            and best_yolo_present < 0.30
        ):
            base_conf = 0.60
            evidence.append("yolo_disagrees")
            return _result("UNCERTAIN", base_conf, "gemini+yolo_conflict", evidence)

        if (
            gemini_canonical == "ABSENT"
            and best_yolo_present > 0.70
            and best_yolo_absent < 0.30
        ):
            base_conf = 0.60
            evidence.append("yolo_disagrees")
            return _result("UNCERTAIN", base_conf, "gemini+yolo_conflict", evidence)

        # Red ink strongly supports ABSENT regardless of Gemini
        if is_red and gemini_canonical == "PRESENT":
            evidence.append("red_ink_overrides_gemini_present")
            return _result("ABSENT", 0.88, "opencv_red_ink", evidence)

        return _result(gemini_canonical, base_conf, "gemini", evidence)

    # ─── CASE 2: Gemini uncertain / missing → fallback ───────
    evidence.append("gemini_uncertain_fallback")

    # Empty cell → NOT_MARKED
    if is_empty:
        return _result("NOT_MARKED", 0.95, "opencv_empty", evidence)

    # Red ink → ABSENT
    if is_red:
        return _result("ABSENT", 0.88, "opencv_red_ink", evidence)

    # YOLO says ABSENT with good confidence
    if best_yolo_absent >= YOLO_CONF:
        return _result("ABSENT", best_yolo_absent, "yolo", evidence)

    # YOLO says PRESENT with good confidence
    if best_yolo_present >= YOLO_CONF:
        return _result("PRESENT", best_yolo_present, "yolo", evidence)

    # Has ink but nothing else is clear
    if has_ink:
        return _result("UNCERTAIN", 0.50 + density * 0.3, "opencv_ink", evidence)

    return _result("NOT_MARKED", 0.80, "opencv_empty", evidence)


# ─────────────────────────────────────────────────────────────
# HELPER
# ─────────────────────────────────────────────────────────────

def _result(status: str, confidence: float, source: str, evidence: list) -> dict:
    confidence = round(max(0.0, min(1.0, confidence)), 4)
    review     = confidence < CONF_HIGH or status == "UNCERTAIN"

    return {
        "status":     status,
        "confidence": confidence,
        "source":     source,
        "review":     review,
        "evidence":   evidence,
    }


# ─────────────────────────────────────────────────────────────
# BATCH DECIDE
# ─────────────────────────────────────────────────────────────

def decide_all(
    gemini_result: dict,
    yolo_detections: list[dict],
    cell_grid: list[dict],         # list of {student_idx, date_idx, x1,y1,x2,y2}
    cell_analyses: dict,           # {(student_idx, date_idx): analysis_dict}
) -> list[dict]:
    """
    Run decide() for every attendance cell in the grid.

    Returns a list of decision dicts, one per cell, each containing:
        student_idx, date_idx, status, confidence, source, review, evidence
    """
    students = gemini_result.get("students", [])
    dates    = gemini_result.get("sheet_info", {}).get("dates", [])

    decisions = []

    for cell in cell_grid:
        s_idx = cell["student_idx"]
        d_idx = cell["date_idx"]

        # Get Gemini status for this student-date
        gemini_status = None
        if s_idx < len(students):
            att = students[s_idx].get("attendance", {})
            # date_idx is 1-based in Gemini output
            gemini_status = att.get(str(d_idx + 1))

        # Get OpenCV analysis
        cv_analysis = cell_analyses.get((s_idx, d_idx))

        # Get YOLO detections that fall inside this cell
        cx1, cy1, cx2, cy2 = cell["x1"], cell["y1"], cell["x2"], cell["y2"]
        cell_yolo = [
            d for d in yolo_detections
            if cx1 <= d["center_x"] <= cx2
            and cy1 <= d["center_y"] <= cy2
        ]

        dec = decide(gemini_status, cv_analysis, cell_yolo)
        dec.update({
            "student_idx": s_idx,
            "date_idx":    d_idx,
        })
        decisions.append(dec)

    return decisions
