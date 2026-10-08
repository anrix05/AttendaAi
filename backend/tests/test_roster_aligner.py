"""
backend/tests/test_roster_aligner.py — Tests for Fuzzy Roster Aligner
"""
import pytest
from backend.vision.roster_aligner import RosterAligner, ScannedStudentRow, RosterStudent


@pytest.fixture
def aligner():
    return RosterAligner()


@pytest.fixture
def sample_roster():
    return [
        RosterStudent(sr_no=1, roll_no="24108B0001", name="VEDANT PATOLE", batch=1),
        RosterStudent(sr_no=2, roll_no="24108B0002", name="ARYA SURYAVANSHI", batch=1),
        RosterStudent(sr_no=3, roll_no="24108B0005", name="AYUSH SAWANT", batch=1),
        RosterStudent(sr_no=22, roll_no="25108B2001", name="NIRJA HATI", batch=2),
    ]


def test_exact_roll_alignment(aligner, sample_roster):
    scanned = [
        ScannedStudentRow(sr_no=1, raw_roll_no="24108B0001", raw_name="VEDANT PATOLE"),
        ScannedStudentRow(sr_no=2, raw_roll_no="24108B0002", raw_name="ARYA SURYAVANSHI"),
    ]
    aligned = aligner.align(scanned, sample_roster)
    assert len(aligned) == 2
    assert aligned[0].matched_student.roll_no == "24108B0001"
    assert aligned[0].match_strategy == "exact_roll"
    assert aligned[0].confidence == 1.0


def test_ocr_digit_normalization(aligner, sample_roster):
    """
    Test OCR confusion: 'O' instead of '0', '8' instead of 'B'.
    Scanned '241O88OOO5' -> Repairs to '24108B0005'.
    """
    scanned = [
        ScannedStudentRow(sr_no=3, raw_roll_no="241O88OOO5", raw_name="AYUSH SAWANT"),
    ]
    aligned = aligner.align(scanned, sample_roster)
    assert len(aligned) == 1
    assert aligned[0].matched_student.roll_no == "24108B0005"
    assert aligned[0].match_strategy == "exact_roll"


def test_fuzzy_name_repair(aligner, sample_roster):
    """
    Roll number was poorly recognized ('25108BXXXX'), but name 'NIRJA HATI' matches DSE student.
    """
    scanned = [
        ScannedStudentRow(sr_no=22, raw_roll_no="25108BXXXX", raw_name="NIRJA HATI", batch=2),
    ]
    aligned = aligner.align(scanned, sample_roster)
    assert len(aligned) == 1
    assert aligned[0].matched_student.roll_no == "25108B2001"
    assert aligned[0].match_strategy in ("fuzzy_name_and_sr", "fuzzy_name")
    assert aligned[0].confidence >= 0.80
