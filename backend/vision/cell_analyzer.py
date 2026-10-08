"""
cell_analyzer.py
─────────────────
OpenCV-based per-cell analysis.
Determines whether a cell is empty, contains ink, or contains red ink
WITHOUT needing a neural network.

Used as a verification / fallback layer alongside Gemini.
"""

import cv2
import numpy as np


# ─────────────────────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────────────────────

# Ink density thresholds
INK_DENSITY_THRESHOLD  = 0.04   # > 4% dark pixels → has ink
HEAVY_INK_THRESHOLD    = 0.20   # > 20% → definitely has ink

# Red ink HSV ranges
RED_LOWER_1 = np.array([0,   60,  50])
RED_UPPER_1 = np.array([10, 255, 255])
RED_LOWER_2 = np.array([165, 60,  50])
RED_UPPER_2 = np.array([180, 255, 255])

RED_RATIO_THRESHOLD = 0.015   # > 1.5% red pixels → red ink


# ─────────────────────────────────────────────────────────────
# CELL ANALYSIS
# ─────────────────────────────────────────────────────────────

def ink_density(crop: np.ndarray) -> float:
    """
    Return fraction of pixels that are 'ink' (dark pixels).
    Works on BGR or grayscale image.
    """
    if crop is None or crop.size == 0:
        return 0.0

    if len(crop.shape) == 3:
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    else:
        gray = crop

    _, binary = cv2.threshold(
        gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
    )
    total  = binary.size
    filled = int(cv2.countNonZero(binary))
    return filled / total if total > 0 else 0.0


def red_ratio(crop: np.ndarray) -> float:
    """
    Return fraction of pixels that fall within red ink HSV ranges.
    """
    if crop is None or crop.size == 0 or len(crop.shape) < 3:
        return 0.0

    hsv  = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, RED_LOWER_1, RED_UPPER_1) | \
           cv2.inRange(hsv, RED_LOWER_2, RED_UPPER_2)

    total = crop.shape[0] * crop.shape[1]
    red   = int(cv2.countNonZero(mask))
    return red / total if total > 0 else 0.0


def analyze_cell(image: np.ndarray, cell: dict) -> dict:
    """
    Analyze a single cell region of the attendance sheet.

    Parameters
    ----------
    image : BGR numpy array of the full sheet
    cell  : dict with keys x1, y1, x2, y2

    Returns
    -------
    dict with:
        has_ink   : bool
        is_red    : bool
        density   : float  (0.0–1.0)
        red_ratio : float  (0.0–1.0)
        is_empty  : bool
    """
    x1 = max(0, int(cell["x1"]))
    y1 = max(0, int(cell["y1"]))
    x2 = min(image.shape[1], int(cell["x2"]))
    y2 = min(image.shape[0], int(cell["y2"]))

    if x2 <= x1 or y2 <= y1:
        return _empty_analysis()

    crop = image[y1:y2, x1:x2]

    if crop.size == 0:
        return _empty_analysis()

    density   = ink_density(crop)
    r_ratio   = red_ratio(crop)

    has_ink  = density > INK_DENSITY_THRESHOLD
    is_red   = r_ratio > RED_RATIO_THRESHOLD
    is_empty = not has_ink

    return {
        "has_ink":   has_ink,
        "is_red":    is_red,
        "density":   round(density, 4),
        "red_ratio": round(r_ratio, 4),
        "is_empty":  is_empty,
    }


def _empty_analysis() -> dict:
    return {
        "has_ink":   False,
        "is_red":    False,
        "density":   0.0,
        "red_ratio": 0.0,
        "is_empty":  True,
    }
