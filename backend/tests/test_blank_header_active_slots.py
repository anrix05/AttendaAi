"""
backend/tests/test_blank_header_active_slots.py — Test Active Slot Detection on Blank Date Header Sheets
"""
import pytest
from pathlib import Path

from backend.vision.extractor import get_extractor
from backend.schemas import AttendanceStatus


def test_blank_header_detects_four_active_slots():
    """
    On a sheet where date headers are BLANK but columns 1..4 contain marks
    and column 5 is truly blank:
    - Expect 4 active slots
    - Expect slot 5 to be ignored
    - Expect slots to be labelled 'Date missing (column N)' with pre-filled suggestions
    """
    img_path = Path("backend/tests/fixtures/images/09_sr31_66_multi_dates.png")
    assert img_path.exists(), f"Fixture {img_path} not found"

    extractor = get_extractor(use_mock=False)
    preview = extractor.extract(image_path=img_path, subject_id="tybtech_b_ss_theory")

    # 1. Exactly 4 active slots detected
    assert len(preview.date_columns) == 4, f"Expected 4 active slots, got {len(preview.date_columns)}"

    # 2. Check labels and slot numbering
    expected_labels = [
        "Date missing (column 1)",
        "Date missing (column 2)",
        "Date missing (column 3)",
        "Date missing (column 4)",
    ]
    actual_labels = [d.raw_date for d in preview.date_columns]
    assert actual_labels == expected_labels

    # 3. Suggestions pre-filled (separated by 7 days)
    assert preview.date_columns[0].iso_date == "2026-09-09"
    assert preview.date_columns[1].iso_date == "2026-09-16"
    assert preview.date_columns[2].iso_date == "2026-09-23"
    assert preview.date_columns[3].iso_date == "2026-09-30"
    assert all(d.needs_confirmation for d in preview.date_columns)

    # 4. Each row has exactly 4 cells
    assert len(preview.rows) > 0
    for r in preview.rows:
        assert len(r.cells) == 4


def test_commit_blocks_missing_dates(client):
    """Verify that committing a sheet with missing dates is blocked until dates are confirmed."""
    # 1. Create subject
    subj_payload = {
        "name": "Blank Header Subject",
        "code": "BLANK_SUB",
        "class_name": "T.Y.B.TECH",
        "division": "B",
        "type": "Theory",
        "faculty": "SHP",
    }
    create_res = client.post("/api/subjects", json=subj_payload)
    assert create_res.status_code == 201
    subj_id = create_res.json()["id"]

    # 2. Attempt commit with missing dates
    bad_commit = {
        "date_columns": ["Date missing (column 1)", "Date missing (column 2)"],
        "records": [
            {"roll_no": "24108B0001", "date": "Date missing (column 1)", "status": "P"},
            {"roll_no": "24108B0001", "date": "Date missing (column 2)", "status": "P"},
        ],
    }
    commit_res = client.post(f"/api/subjects/{subj_id}/commit", json=bad_commit)
    assert commit_res.status_code == 400
    assert "missing" in commit_res.json()["detail"].lower()
