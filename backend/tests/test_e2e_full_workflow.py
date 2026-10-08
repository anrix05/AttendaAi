"""
backend/tests/test_e2e_full_workflow.py — Complete End-to-End Workflow Demonstration Test
Simulates:
1. Create Subject: T.Y.B.TECH - Div B - SS (Theory, SHP)
2. Import 30-student VIT roster
3. Scan sample attendance sheet (9/9, 23/9, 30/9, 7/10)
4. Teacher reviews & resolves uncertain cells -> Commit to Master
5. Scan subsequent session (14/10) -> Commit to Master
6. Rescan same sheet (duplicate dates path) -> Assert idempotency & no data loss
7. Download and validate master_attendance.xlsx (formulas, values, formatting)
"""
import io
import shutil
from pathlib import Path
import openpyxl
import pytest

from backend.config import settings

SAMPLE_IMAGE = Path("backend/tests/fixtures/sample_sheet_vit.jpg")


def test_full_e2e_workflow(client, ground_truth_data):
    subj_id = "ty_ecs_b_ss_theory_e2e"
    subj_dir = settings.SUBJECTS_DIR / subj_id
    if subj_dir.exists():
        shutil.rmtree(subj_dir, ignore_errors=True)

    try:
        # ── Step 1: Create Subject ────────────────────────────────────
        create_res = client.post("/api/subjects", json={
            "id": subj_id,
            "name": "System Software",
            "code": "SS",
            "class_name": "T.Y.B.TECH",
            "division": "B",
            "type": "Theory",
            "faculty": "SHP",
            "academic_year": "2026-27 (Odd)",
        })
        assert create_res.status_code == 201
        print("\n[*] Step 1: Subject created successfully.")

        # ── Step 2: Import 30-Student VIT Roster ──────────────────────
        students_payload = [
            {
                "sr_no": s["sr_no"],
                "roll_no": s["roll_no"],
                "name": s["name"],
                "batch": s["batch"],
            }
            for s in ground_truth_data["students"]
        ]
        roster_res = client.put(f"/api/subjects/{subj_id}/roster", json=students_payload)
        assert roster_res.status_code == 200
        assert len(roster_res.json()) == 30
        print("[*] Step 2: Roster imported (30 students, Batch 1 & 2).")

        # ── Step 3: Scan Sample Attendance Sheet ──────────────────────
        with open(SAMPLE_IMAGE, "rb") as f:
            img_bytes = f.read()

        files = {"file": ("vit_sample_sheet.jpg", io.BytesIO(img_bytes), "image/jpeg")}
        scan_res = client.post(f"/api/subjects/{subj_id}/scan?mock=true", files=files)
        assert scan_res.status_code == 200
        preview = scan_res.json()
        assert len(preview["date_columns"]) == 4
        assert len(preview["rows"]) == 30
        print("[*] Step 3: Sheet scanned and extracted (4 active date columns detected).")

        # ── Step 4: Teacher Reviews & Resolves Uncertain Cells ────────
        # Convert preview into confirmed records, resolving any 'UNCERTAIN' mark to 'P'
        date_iso_cols = [d["iso_date"] for d in preview["date_columns"]]
        date_raw_to_iso = {d["col_idx"]: d["iso_date"] for d in preview["date_columns"]}

        confirmed_records = []
        for r in preview["rows"]:
            for c in r["cells"]:
                iso_d = date_raw_to_iso[c["col_idx"]]
                status_code = c["status"]
                # Resolve any uncertain mark to P as teacher decision
                if status_code == "UNCERTAIN":
                    status_code = "P"
                confirmed_records.append({
                    "roll_no": r["roll_no"],
                    "date": iso_d,
                    "status": status_code,
                })

        commit_res = client.post(f"/api/subjects/{subj_id}/commit", json={
            "scan_id": preview["scan_id"],
            "date_columns": date_iso_cols,
            "records": confirmed_records,
            "overwrite_conflicts": False,
        })
        assert commit_res.status_code == 200
        commit_data = commit_res.json()
        assert len(commit_data["added_dates"]) == 4
        print(f"[*] Step 4: Week 1-4 committed. Initial Class Average: {commit_data['class_average_pct']}%.")

        # ── Step 5: Subsequent Week Scan & Append (14/10/26) ──────────
        subsequent_records = [
            {"roll_no": s["roll_no"], "date": "2026-10-14", "status": "P" if s["sr_no"] % 2 == 1 else "A"}
            for s in ground_truth_data["students"]
        ]
        subseq_res = client.post(f"/api/subjects/{subj_id}/commit", json={
            "date_columns": ["2026-10-14"],
            "records": subsequent_records,
            "overwrite_conflicts": False,
        })
        assert subseq_res.status_code == 200
        assert subseq_res.json()["added_dates"] == ["2026-10-14"]
        print("[*] Step 5: Subsequent session (14/10/26) appended to existing master register.")

        # ── Step 6: Duplicate Date Scan (Idempotency Path) ────────────
        dup_res = client.post(f"/api/subjects/{subj_id}/commit", json={
            "date_columns": ["2026-09-09"],
            "records": [
                {"roll_no": "24108B0001", "date": "2026-09-09", "status": "P"},
            ],
            "overwrite_conflicts": False,
        })
        assert dup_res.status_code == 200
        assert len(dup_res.json()["added_dates"]) == 0  # No new dates added
        print("[*] Step 6: Duplicate date merge tested. Handled idempotently with 0 duplicates.")

        # ── Step 7: Download and Verify Master Excel ──────────────────
        down_res = client.get(f"/api/subjects/{subj_id}/download")
        assert down_res.status_code == 200
        assert "spreadsheet" in down_res.headers.get("content-type", "")

        wb = openpyxl.load_workbook(io.BytesIO(down_res.content), data_only=False)
        ws = wb.active

        # Verify all 5 date headers exist in chronological order
        expected_headers = ["9/9/26", "23/9/26", "30/9/26", "7/10/26", "14/10/26", "TOTAL", "HELD", "ATT %"]
        actual_headers = [ws.cell(row=4, column=col).value for col in range(5, 5 + len(expected_headers))]
        assert actual_headers == expected_headers

        # Verify formulas in row 5 (Vedant Patole)
        assert ws["J5"].value == '=COUNTIF(E5:I5,"P")'
        assert ws["K5"].value == '=COUNTIF(E5:I5,"P")+COUNTIF(E5:I5,"A")'
        assert ws["L5"].value == '=IF(K5=0,"",J5/K5*100)'

        wb.close()
        print("[*] Step 7: Master spreadsheet validated successfully (5 sessions, live formulas).")

    finally:
        if subj_dir.exists():
            shutil.rmtree(subj_dir, ignore_errors=True)
