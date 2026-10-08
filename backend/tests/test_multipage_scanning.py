"""
backend/tests/test_multipage_scanning.py — Test Multi-Page Scanning & Continuation Sheet Inheritance
"""
import pytest
from pathlib import Path
import numpy as np
import cv2


def test_multipage_scan_flow(client, ground_truth_data):
    # 1. Create a subject
    payload = {
        "name": "System Software Multi",
        "code": "SS_MULTI",
        "class_name": "T.Y.B.TECH",
        "division": "B",
        "type": "Theory",
        "faculty": "SHP",
        "academic_year": "2026-27 (Odd)",
    }
    create_res = client.post("/api/subjects", json=payload)
    assert create_res.status_code == 201
    subj_id = create_res.json()["id"]

    # 2. Upload 2 pages simultaneously (Page 1: Sr 1-30, Page 2: Sr 31-66)
    img_dir = Path("backend/tests/fixtures/images")
    p1_path = img_dir / "01_ss_divb_sr1_30_arrows.jpg"
    p2_path = img_dir / "09_sr31_66_multi_dates.png"

    with open(p1_path, "rb") as f1, open(p2_path, "rb") as f2:
        files = [
            ("files", ("page1.jpg", f1.read(), "image/jpeg")),
            ("files", ("page2.png", f2.read(), "image/png")),
        ]
        res = client.post(f"/api/subjects/{subj_id}/scan", files=files)

    assert res.status_code == 200
    data = res.json()

    # Check date columns populated from Page 1
    assert len(data["date_columns"]) >= 1
    # Check rows combined from both pages
    assert len(data["rows"]) > 30
    # Check dates have ISO format
    for dc in data["date_columns"]:
        assert "-" in dc["iso_date"]


def test_blurry_image_rejection(client):
    # Create subject
    payload = {
        "name": "Blurry Test",
        "code": "BLUR_TEST",
        "class_name": "T.Y.B.TECH",
        "division": "A",
        "type": "Theory",
        "faculty": "ABC",
    }
    create_res = client.post("/api/subjects", json=payload)
    subj_id = create_res.json()["id"]

    # Generate a solid black blurry image (variance = 0)
    solid_img = np.zeros((300, 300, 3), dtype=np.uint8)
    _, encoded = cv2.imencode(".jpg", solid_img)

    files = {"file": ("blurry.jpg", encoded.tobytes(), "image/jpeg")}
    res = client.post(f"/api/subjects/{subj_id}/scan", files=files)

    assert res.status_code == 400
    err_detail = res.json()["detail"]
    assert "blurry" in err_detail.lower()
