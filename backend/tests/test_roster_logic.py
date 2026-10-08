"""
backend/tests/test_roster_logic.py — Tests for Roll Normalization & Union Roster Logic
"""
import pytest
from backend.roster import (
    normalize_roll_number,
    is_valid_vit_roll,
    RosterStudentItem,
    PageStudentBatch,
    RosterManager,
)


def test_normalize_roll_number_regular():
    # Lowercase b normalization
    assert normalize_roll_number("24108b0001") == "24108B0001"
    assert normalize_roll_number("  24108B0025  ") == "24108B0025"


def test_normalize_roll_number_dse():
    # Direct Second Year (DSE) format
    assert normalize_roll_number("25108b2001") == "25108B2001"
    assert normalize_roll_number("25108B2015") == "25108B2015"


def test_normalize_roll_number_ocr_repairs():
    # 'O' -> '0' at digit positions, '8' -> 'B' at 6th position
    assert normalize_roll_number("241O88OOO5") == "24108B0005"
    # 'I' and 'L' -> '1' at digit positions
    assert normalize_roll_number("24108B000I") == "24108B0001"
    assert normalize_roll_number("24108B000L") == "24108B0001"


def test_is_valid_vit_roll():
    assert is_valid_vit_roll("24108B0001") is True
    assert is_valid_vit_roll("25108B2001") is True
    assert is_valid_vit_roll("24108b0001") is True  # normalizes to B
    assert is_valid_vit_roll("INVALID_ROLL") is False
    assert is_valid_vit_roll("12345") is False


def test_build_union_roster():
    # Page 1 students (Sr 1-3)
    existing = [
        RosterStudentItem(roll_no="24108B0001", name="VEDANT PATOLE", batch=1, sr_no=1),
        RosterStudentItem(roll_no="24108B0002", name="ARYA SURYAVANSHI", batch=1, sr_no=2),
    ]

    # Page 2 adds a new student
    page2_students = [
        RosterStudentItem(roll_no="24108B0002", name="ARYA SURYAVANSHI", batch=1),  # already in roster
        RosterStudentItem(roll_no="24108B0005", name="AYUSH SAWANT", batch=1),        # new student!
        RosterStudentItem(roll_no="25108B2001", name="NIRJA HATI", batch=2),          # batch 2 DSE student!
    ]

    updated_roster, newly_added = RosterManager.build_union_roster(existing, page2_students)

    assert len(updated_roster) == 4
    assert len(newly_added) == 2
    assert [s.roll_no for s in newly_added] == ["24108B0005", "25108B2001"]

    # Verify sequential Sr. No regeneration
    assert [s.sr_no for s in updated_roster] == [1, 2, 3, 4]
    # Verify Batch 1 comes before Batch 2
    assert updated_roster[-1].batch == 2
    assert updated_roster[-1].roll_no == "25108B2001"


def test_page_order_warnings():
    page1 = PageStudentBatch(
        page_index=1,
        students=[
            RosterStudentItem(roll_no="24108B0001", name="STUDENT 1"),
            RosterStudentItem(roll_no="24108B0015", name="STUDENT 15"),
        ],
        first_roll="24108B0001",
        last_roll="24108B0015",
    )

    page2_reversed = PageStudentBatch(
        page_index=2,
        students=[
            RosterStudentItem(roll_no="24108B0005", name="STUDENT 5"),  # Starts earlier than page 1 ended
        ],
        first_roll="24108B0005",
        last_roll="24108B0010",
    )

    warnings = RosterManager.check_page_order_and_duplicates([page1, page2_reversed])
    assert len(warnings) >= 1
    assert any(w.type == "overlap" for w in warnings)
