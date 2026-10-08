"""
preprocessing.py
────────────────
Image preprocessing pipeline for attendance sheets.
Handles perspective correction, contrast enhancement,
deskewing and resizing before AI analysis.
"""

import cv2
import numpy as np
from pathlib import Path


# ─────────────────────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────────────────────

TARGET_WIDTH   = 1600   # minimum width after resize
CLAHE_CLIP     = 2.0
CLAHE_GRID     = (8, 8)


# ─────────────────────────────────────────────────────────────
# IMAGE LOADING
# ─────────────────────────────────────────────────────────────

def load_image(image_path: str) -> np.ndarray:
    """Load image from path. Returns BGR numpy array."""
    path = Path(image_path)
    if not path.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")

    image = cv2.imread(str(path))
    if image is None:
        raise ValueError(f"Could not read image: {image_path}")

    return image


# ─────────────────────────────────────────────────────────────
# ORDER POINTS (for perspective transform)
# ─────────────────────────────────────────────────────────────

def _order_points(pts: np.ndarray) -> np.ndarray:
    """Order 4 points: top-left, top-right, bottom-right, bottom-left."""
    rect  = np.zeros((4, 2), dtype=np.float32)
    s     = pts.sum(axis=1)
    diff  = np.diff(pts, axis=1)

    rect[0] = pts[np.argmin(s)]    # top-left
    rect[2] = pts[np.argmax(s)]    # bottom-right
    rect[1] = pts[np.argmin(diff)] # top-right
    rect[3] = pts[np.argmax(diff)] # bottom-left
    return rect


# ─────────────────────────────────────────────────────────────
# PERSPECTIVE CORRECTION
# ─────────────────────────────────────────────────────────────

def correct_perspective(image: np.ndarray) -> np.ndarray:
    """
    Detect the largest rectangular region (the attendance sheet)
    and apply a perspective warp to straighten it.
    Falls back to the original image if no clear quadrilateral found.
    """
    original = image.copy()
    gray     = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blur     = cv2.GaussianBlur(gray, (5, 5), 0)
    edges    = cv2.Canny(blur, 40, 150)

    # Dilate edges slightly so broken lines connect
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    edges  = cv2.dilate(edges, kernel, iterations=1)

    contours, _ = cv2.findContours(
        edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )

    h, w = image.shape[:2]
    image_area = h * w

    best_quad = None
    best_area = 0

    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < image_area * 0.20:
            continue

        peri  = cv2.arcLength(cnt, True)
        approx = cv2.approxPolyDP(cnt, 0.02 * peri, True)

        if len(approx) == 4 and area > best_area:
            best_quad = approx.reshape(4, 2).astype(np.float32)
            best_area = area

    if best_quad is None:
        return original

    try:
        ordered = _order_points(best_quad)
        tl, tr, br, bl = ordered

        w_top    = np.linalg.norm(tr - tl)
        w_bottom = np.linalg.norm(br - bl)
        h_left   = np.linalg.norm(bl - tl)
        h_right  = np.linalg.norm(br - tr)

        max_w = int(max(w_top, w_bottom))
        max_h = int(max(h_left, h_right))

        if max_w < 100 or max_h < 100:
            return original

        dst = np.array([
            [0,         0        ],
            [max_w - 1, 0        ],
            [max_w - 1, max_h - 1],
            [0,         max_h - 1],
        ], dtype=np.float32)

        M = cv2.getPerspectiveTransform(ordered, dst)
        warped = cv2.warpPerspective(image, M, (max_w, max_h))
        return warped

    except Exception:
        return original


# ─────────────────────────────────────────────────────────────
# DESKEW
# ─────────────────────────────────────────────────────────────

def deskew(image: np.ndarray) -> np.ndarray:
    """
    Correct small rotation using Hough line detection.
    Only corrects angles up to ±10 degrees.
    """
    gray   = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    thresh = cv2.threshold(
        gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
    )[1]

    coords = np.column_stack(np.where(thresh > 0))
    if len(coords) < 10:
        return image

    angle = cv2.minAreaRect(coords)[-1]

    # minAreaRect returns angles in [-90, 0)
    if angle < -45:
        angle = 90 + angle
    else:
        angle = angle

    # Only correct small tilts
    if abs(angle) > 10:
        return image

    h, w = image.shape[:2]
    center = (w // 2, h // 2)
    M = cv2.getRotationMatrix2D(center, angle, 1.0)

    rotated = cv2.warpAffine(
        image, M, (w, h),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REPLICATE,
    )
    return rotated


# ─────────────────────────────────────────────────────────────
# CONTRAST ENHANCEMENT
# ─────────────────────────────────────────────────────────────

def enhance_contrast(image: np.ndarray) -> np.ndarray:
    """
    Apply CLAHE on the L-channel of LAB color space.
    Improves readability without destroying handwriting color.
    """
    lab  = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)

    clahe  = cv2.createCLAHE(clipLimit=CLAHE_CLIP, tileGridSize=CLAHE_GRID)
    l_eq   = clahe.apply(l)

    lab_eq = cv2.merge((l_eq, a, b))
    result = cv2.cvtColor(lab_eq, cv2.COLOR_LAB2BGR)
    return result


# ─────────────────────────────────────────────────────────────
# RESIZE
# ─────────────────────────────────────────────────────────────

def ensure_min_width(image: np.ndarray, min_width: int = TARGET_WIDTH) -> np.ndarray:
    """Scale up image if it is smaller than min_width."""
    h, w = image.shape[:2]
    if w >= min_width:
        return image

    scale  = min_width / w
    new_w  = min_width
    new_h  = int(h * scale)

    return cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_CUBIC)


# ─────────────────────────────────────────────────────────────
# MAIN PIPELINE
# ─────────────────────────────────────────────────────────────

def preprocess(image_path: str) -> np.ndarray:
    """
    Full preprocessing pipeline:
    load → perspective correct → deskew → contrast enhance → resize

    Returns a clean BGR image ready for AI analysis.
    """
    image = load_image(image_path)
    image = correct_perspective(image)
    image = deskew(image)
    image = enhance_contrast(image)
    image = ensure_min_width(image)
    return image
