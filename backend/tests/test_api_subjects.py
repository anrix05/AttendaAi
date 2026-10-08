"""
backend/tests/test_api_subjects.py — Integration Tests for Subject & Roster Endpoints
"""
import io
import pandas as pd
import pytest


def test_health_check(client):
    res = client.get("/api/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert data["app"] == "AttendAI"
    assert "engine_chip" in data

    # Diagnostics endpoint
    diag = client.get("/api/diagnostics")
    assert diag.status_code == 200
    diag_data = diag.json()
    assert "engines" in diag_data



def test_create_and_list_subject(client):
    payload = {
        "name": "System Software",
        "code": "SS",
        "class_name": "T.Y.B.TECH",
        "division": "B",
        "type": "Theory",
        "faculty": "SHP",
        "academic_year": "2026-27 (Odd)",
    }
    res = client.post("/api/subjects", json=payload)
    assert res.status_code == 201
    created = res.json()
    assert created["id"] == "tybtech_b_ss_theory"
    assert created["name"] == "System Software"
    assert len(created["students"]) == 0

    # List subjects
    list_res = client.get("/api/subjects")
    assert list_res.status_code == 200
    subjects = list_res.json()
    assert len(subjects) == 1
    assert subjects[0]["id"] == "tybtech_b_ss_theory"


def test_create_subject_with_roster(client, ground_truth_data):
    students_in = [
        {
            "sr_no": s["sr_no"],
            "roll_no": s["roll_no"],
            "name": s["name"],
            "batch": s["batch"],
        }
        for s in ground_truth_data["students"]
    ]

    payload = {
        "id": "ss_div_b_test",
        "name": "System Software",
        "code": "SS",
        "class_name": "T.Y.B.TECH",
        "division": "B",
        "type": "Theory",
        "faculty": "SHP",
        "academic_year": "2026-27 (Odd)",
        "roster": students_in,
    }
    res = client.post("/api/subjects", json=payload)
    assert res.status_code == 201
    created = res.json()
    assert len(created["students"]) == 30
    assert created["students"][0]["roll_no"] == "24108B0001"
    assert created["students"][21]["roll_no"] == "25108B2001"  # DSE student

    # Get details
    detail_res = client.get("/api/subjects/ss_div_b_test")
    assert detail_res.status_code == 200
    detail = detail_res.json()
    assert len(detail["students"]) == 30
    assert detail["stats"]["enrolled_students"] == 30


def test_reject_invalid_roll_number(client):
    payload = {
        "name": "Database Systems",
        "code": "DBMS",
        "class_name": "T.Y.B.TECH",
        "division": "A",
        "faculty": "XYZ",
        "roster": [
            {"sr_no": 1, "roll_no": "INVALID_ROLL_123", "name": "JOHN DOE", "batch": 1}
        ],
    }
    res = client.post("/api/subjects", json=payload)
    assert res.status_code == 422  # Pydantic validation error


def test_reject_duplicate_roll_number(client):
    payload = {
        "name": "Operating Systems",
        "code": "OS",
        "class_name": "T.Y.B.TECH",
        "division": "A",
        "faculty": "ABC",
        "roster": [
            {"sr_no": 1, "roll_no": "24108B0001", "name": "ALICE", "batch": 1},
            {"sr_no": 2, "roll_no": "24108B0001", "name": "BOB", "batch": 1},
        ],
    }
    res = client.post("/api/subjects", json=payload)
    assert res.status_code == 400
    assert "Duplicate roll number" in res.json()["detail"]


def test_upload_roster_csv(client):
    # 1. Create empty subject
    client.post("/api/subjects", json={
        "id": "csv_subject",
        "name": "Machine Learning",
        "code": "ML",
        "class_name": "B.TECH",
        "division": "A",
        "faculty": "ML_PROF",
    })

    # 2. Upload CSV
    csv_data = "Sr No,Roll No,Name,Batch\n1,24108B0001,STUDENT ONE,1\n2,24108B0002,STUDENT TWO,1\n"
    files = {"file": ("roster.csv", io.BytesIO(csv_data.encode("utf-8")), "text/csv")}
    res = client.post("/api/subjects/csv_subject/roster/upload", files=files)
    assert res.status_code == 200
    roster = res.json()
    assert len(roster) == 2
    assert roster[0]["roll_no"] == "24108B0001"
    assert roster[1]["name"] == "STUDENT TWO"


def test_soft_and_permanent_delete(client):
    client.post("/api/subjects", json={
        "id": "del_test",
        "name": "To Delete",
        "code": "DEL",
        "class_name": "T.Y",
        "division": "C",
        "faculty": "FAC",
    })

    # Soft delete
    del_res = client.delete("/api/subjects/del_test")
    assert del_res.status_code == 200

    # Should not appear in active list
    list_res = client.get("/api/subjects")
    assert not any(s["id"] == "del_test" for s in list_res.json())

    # Permanent delete
    perm_res = client.delete("/api/subjects/del_test?permanent=true")
    assert perm_res.status_code == 200


def test_create_subject_with_branch_and_semester(client):
    payload = {
        "name": "Data Structures and Algorithms",
        "code": "DSA",
        "branch": "Computer Engineering",
        "class_name": "Semester 3",
        "division": "A",
        "type": "Theory",
        "faculty": "RKD",
        "academic_year": "2026-27 (Odd)",
    }
    res = client.post("/api/subjects", json=payload)
    assert res.status_code == 201
    created = res.json()
    assert created["branch"] == "Computer Engineering"
    assert created["class_name"] == "Semester 3"
    assert created["id"] == "semester3_a_dsa_theory"

    # Detail check
    detail_res = client.get(f"/api/subjects/{created['id']}")
    assert detail_res.status_code == 200
    detail = detail_res.json()
    assert detail["branch"] == "Computer Engineering"
    assert detail["class_name"] == "Semester 3"

    # List check
    list_res = client.get("/api/subjects")
    assert list_res.status_code == 200
    found = next((s for s in list_res.json() if s["id"] == created["id"]), None)
    assert found is not None
    assert found["branch"] == "Computer Engineering"
    assert found["class_name"] == "Semester 3"

