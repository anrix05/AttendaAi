"""
backend/tests/test_image_pipeline_and_dates.py — Tests for OpenCV Quality Gate and Date Parsing
"""
import numpy as np
import cv2
import pytest
from pathlib import Path

from backend.vision.dates import AcademicDateParser
from backend.vision.image_pipeline import ImagePipeline, QualityCheckResult


def test_date_parser_standard():
    parser = AcademicDateParser(academic_year="2026-27 (Odd)")

    # 9/9/26
    res1 = parser.parse("9/9/26")
    assert res1.is_valid is True
    assert res1.iso == "2026-09-09"
    assert res1.warning is None

    # 23/9/26
    res2 = parser.parse("23/9/26")
    assert res2.is_valid is True
    assert res2.iso == "2026-09-23"

    # 7/10/2026
    res3 = parser.parse("7/10/2026")
    assert res3.is_valid is True
    assert res3.iso == "2026-10-07"

    # Hyphen format: 30-09-26
    res4 = parser.parse("30-09-26")
    assert res4.is_valid is True
    assert res4.iso == "2026-09-30"


def test_date_parser_missing_year():
    parser = AcademicDateParser(academic_year="2026-27 (Odd)")

    # Missing year: 15/9
    res = parser.parse("15/9")
    assert res.is_valid is True
    assert res.iso == "2026-09-15"

    # Missing year: 15/1 (Jan in Odd sem would be spillover/end year 2027)
    res_jan = parser.parse("15/1")
    assert res_jan.is_valid is True
    assert res_jan.iso == "2027-01-15"


def test_date_parser_wrong_year_warning():
    parser = AcademicDateParser(academic_year="2026-27 (Odd)")

    # 2025 is outside 2026-2027
    res = parser.parse("9/9/2025")
    assert res.is_valid is True
    assert res.iso == "2025-09-09"
    assert res.warning is not None
    assert "outside expected academic year" in res.warning


def test_image_quality_sharp_image():
    # Synthetic sharp image with lines and high variance
    img = np.zeros((400, 600, 3), dtype=np.uint8)
    for y in range(0, 400, 20):
        cv2.line(img, (0, y), (600, y), (255, 255, 255), 2)
    for x in range(0, 600, 40):
        cv2.line(img, (x, 0), (x, 400), (255, 255, 255), 2)

    res = ImagePipeline.check_quality(img)
    assert res.passed is True
    assert res.blur_score > 50.0


def test_image_quality_blurry_image():
    # Highly blurred image
    blank = np.zeros((300, 300, 3), dtype=np.uint8)
    res = ImagePipeline.check_quality(blank)
    assert res.passed is False
    assert res.guidance is not None
    assert "blurry" in res.guidance.lower()


def test_perspective_rectify():
    # Verify rectify returns valid numpy array without crash
    img = np.zeros((400, 400, 3), dtype=np.uint8)
    cv2.rectangle(img, (50, 50), (350, 350), (255, 255, 255), -1)
    rectified = ImagePipeline.rectify_perspective(img)
    assert rectified is not None
    assert rectified.shape[0] > 0
