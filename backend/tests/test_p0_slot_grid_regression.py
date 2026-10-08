import hashlib
import json
from pathlib import Path
import pytest

from backend.schemas import AttendanceStatus, TokenEnum
from backend.vision.extractor import MultiEngineExtractor


def test_p0_slot_grid_regression_sr31_66():
    """
    P0 Regression Test for sheet Sr 31-66 (09_sr31_66_multi_dates.png):
    1. 4 active slots detected, slot 5 ignored (empty).
    2. 36 student rows.
    3. Slot 1 absent ('A') for roll numbers:
       24108B0037, 24108B0040, 24108B0048, 24108B0057, 24108B0062,
       24108B0065, 24108B0070, 24108B0073, 24108B0074.
    4. Signatures ('P') for the rest (or '?' if ambiguous).
    5. Zero cells may be NM in Slot 1.
    """
    fixture_path = Path("backend/tests/fixtures/sr31_66_vision_fixture.json")
    img_path = Path("backend/tests/fixtures/images/09_sr31_66_multi_dates.png")
    assert fixture_path.exists(), f"Fixture file not found: {fixture_path}"
    assert img_path.exists(), f"Image file not found: {img_path}"

    # Ensure fixture is in vision cache for this image hash
    img_bytes = img_path.read_bytes()
    img_hash = hashlib.sha256(img_bytes).hexdigest()
    cache_dir = Path("data/cache/vision")
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / f"{img_hash}.json"
    cache_file.write_text(fixture_path.read_text(encoding="utf-8"), encoding="utf-8")

    extractor = MultiEngineExtractor(use_mock=False)
    preview = extractor.extract(image_path=img_path)

    # 1. 4 active slots detected, slot 5 ignored
    assert len(preview.date_columns) == 4, f"Expected 4 active slots, got {len(preview.date_columns)}"

    # 2. 36 student rows
    assert len(preview.rows) == 36, f"Expected 36 rows, got {len(preview.rows)}"

    # 3. Check Slot 1 (col_idx == 0)
    expected_absent_rolls = {
        "24108B0037",
        "24108B0040",
        "24108B0048",
        "24108B0057",
        "24108B0062",
        "24108B0065",
        "24108B0070",
        "24108B0073",
        "24108B0074",
    }

    slot1_nm_count = 0
    slot1_a_count = 0
    slot1_p_count = 0
    detected_absent_rolls = set()

    for r in preview.rows:
        slot1_cells = [c for c in r.cells if c.col_idx == 0]
        assert len(slot1_cells) == 1, f"Student {r.roll_no} should have exactly one cell in Slot 1"
        c1 = slot1_cells[0]

        if c1.status == AttendanceStatus.NM:
            slot1_nm_count += 1
        elif c1.status == AttendanceStatus.A:
            slot1_a_count += 1
            detected_absent_rolls.add(r.roll_no)
        elif c1.status == AttendanceStatus.P:
            slot1_p_count += 1

    # Zero cells may be NM in Slot 1
    assert slot1_nm_count == 0, f"Zero cells may be NM in Slot 1, found {slot1_nm_count}"

    # Verify all expected absents match
    assert expected_absent_rolls.issubset(detected_absent_rolls), (
        f"Missing expected absent rolls: {expected_absent_rolls - detected_absent_rolls}"
    )

    # Verify total absents is exactly 9 and presents is 27
    assert slot1_a_count == 9, f"Expected 9 absents in Slot 1, got {slot1_a_count}"
    assert slot1_p_count == 27, f"Expected 27 presents in Slot 1, got {slot1_p_count}"
