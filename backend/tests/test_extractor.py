"""
backend/tests/test_extractor.py — Pytest Suite for Extractor Module
"""
import pytest
from backend.vision.extractor import MockExtractor, get_extractor
from backend.schemas import AttendanceStatus, TokenEnum


def test_mock_extractor_loads_all_30_students():
    extractor = MockExtractor()
    res = extractor.extract("backend/tests/fixtures/sample_sheet_vit.jpg")

    assert res.subject_id == "tybtech_b_ss_theory"
    assert len(res.date_columns) == 4
    assert len(res.rows) == 30

    # First student: Vedant Patole
    r1 = res.rows[0]
    assert r1.sr_no == 1
    assert r1.roll_no == "24108B0001"
    assert r1.name == "VEDANT PATOLE"
    assert len(r1.cells) == 4
    assert r1.cells[0].token == TokenEnum.SIGN
    assert r1.cells[0].status == AttendanceStatus.P

    # Row 3: Ayush Sawant (Absent on 9/9, Present on other dates)
    r3 = res.rows[2]
    assert r3.sr_no == 3
    assert r3.roll_no == "24108B0005"
    assert r3.cells[0].status == AttendanceStatus.A
    assert r3.cells[1].status == AttendanceStatus.P


def test_mock_extractor_arrow_resolution():
    extractor = MockExtractor()
    res = extractor.extract("backend/tests/fixtures/sample_sheet_vit.jpg")

    # On 9/9 (col 0): Sr 9-12 are all absent via arrow chain anchored to Sr 10 AB
    row_9 = res.rows[8]   # Pushkaraj Kadam (↑)
    row_10 = res.rows[9]  # Amey Nadhavale (AB)
    row_11 = res.rows[10] # Mohammad Zaman (↓)
    row_12 = res.rows[11] # Paras Shah (↓)

    assert row_9.cells[0].status == AttendanceStatus.A
    assert row_10.cells[0].status == AttendanceStatus.A
    assert row_11.cells[0].status == AttendanceStatus.A
    assert row_12.cells[0].status == AttendanceStatus.A


def test_get_extractor_factory_offline():
    extractor = get_extractor(use_mock=True)
    assert isinstance(extractor, MockExtractor)


def test_date_column_schema_resilience_to_null():
    from backend.schemas import DateColumn
    # When Gemini returns null for raw_date and iso_date
    col = DateColumn(col_idx=4, raw_date=None, iso_date=None)
    assert col.col_idx == 4
    assert col.raw_date == "Date"
    assert col.iso_date == "2026-09-09"

    # When Gemini returns empty string
    col_empty = DateColumn(col_idx=1, raw_date="", iso_date="")
    assert col_empty.raw_date == "Date"
    assert col_empty.iso_date == "2026-09-09"


def test_gemini_extractor_date_normalization_and_filtering():
    from backend.vision.extractor import GeminiTokenExtractor

    # Test date parsing
    assert GeminiTokenExtractor._normalize_iso_date("9/9/26") == "2026-09-09"
    assert GeminiTokenExtractor._normalize_iso_date("23/9/2026") == "2026-09-23"
    assert GeminiTokenExtractor._normalize_iso_date("invalid", fallback_iso="2026-10-07") == "2026-10-07"
    assert GeminiTokenExtractor._iso_to_raw("2026-09-09") == "9/9/26"


def test_vision_engine_manager_health():
    from backend.vision.engines import EngineManager
    manager = EngineManager()
    chip, tooltip, details = manager.check_health()
    assert chip in ("AttendAI Vision: Online", "Manual mode")
    assert "gemini" in details


def test_manual_mode_fallback():
    from backend.vision.engines import EngineManager, PageImage, ReadContext
    from pathlib import Path
    manager = EngineManager(engine_order="nonexistent_engine")
    chip, tooltip, _ = manager.check_health()
    assert chip == "Manual mode"
    assert "AttendAI Vision is offline" in tooltip

    # Fresh uncached image bytes to test fallback execution
    dummy_page = PageImage(path=Path("backend/tests/fixtures/uncached_dummy.jpg"), bytes=b"dummy_uncached_test_image_123")
    res = manager.read_page_with_fallback(dummy_page, ReadContext())
    assert res.engine_used == "manual_mode"
    assert "AttendAI Vision is offline right now. You can still mark attendance manually." in res.error
    assert len(res.rows) == 30




