"""
backend/vision/image_pipeline.py — OpenCV Image Quality Gate & Perspective Pipeline
Provides blur detection, skew checking, table detection, perspective rectification, and cell cropping.
"""
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple, List, Union
import cv2
import numpy as np

logger = logging.getLogger("attendai.vision.image_pipeline")

BLUR_THRESHOLD = 50.0       # Laplacian variance below this is flagged as blurry
SKEW_THRESHOLD_DEG = 15.0    # Degrees tilt to warn about severe skew
MIN_TABLE_AREA_RATIO = 0.15  # Table contour must be at least 15% of photo area


@dataclass
class QualityCheckResult:
    passed: bool
    blur_score: float
    skew_angle: float
    table_detected: bool
    message: str
    guidance: Optional[str] = None


class ImagePipeline:
    """
    OpenCV computer-vision pipeline for photo validation,
    deskewing, perspective correction, and cell cropping.
    """

    @staticmethod
    def check_quality(image: np.ndarray) -> QualityCheckResult:
        """
        Assess image quality before sending to Vision engines:
        - Blur (Laplacian variance)
        - Skew (tilt angle)
        - Table bounds detection
        """
        if image is None or image.size == 0:
            return QualityCheckResult(
                passed=False,
                blur_score=0.0,
                skew_angle=0.0,
                table_detected=False,
                message="Image is empty or unreadable.",
                guidance="Please upload a valid JPG or PNG photo.",
            )

        h, w = image.shape[:2]
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image

        # 1. Blur Score (Laplacian variance)
        laplacian_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        is_blurry = laplacian_var < BLUR_THRESHOLD

        # 2. Skew angle estimation using minAreaRect on binary threshold
        skew_angle = 0.0
        try:
            thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
            coords = np.column_stack(np.where(thresh > 0))
            if len(coords) > 50:
                rect = cv2.minAreaRect(coords)
                angle = rect[-1]
                if angle < -45:
                    angle = 90 + angle
                skew_angle = float(round(angle, 2))
        except Exception as e:
            logger.debug("Skew computation error: %s", e)

        # 3. Table bounds detection
        table_detected = False
        try:
            blur = cv2.GaussianBlur(gray, (5, 5), 0)
            edges = cv2.Canny(blur, 40, 150)
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
            edges = cv2.dilate(edges, kernel, iterations=1)
            contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            image_area = h * w
            for cnt in contours:
                area = cv2.contourArea(cnt)
                if area >= image_area * MIN_TABLE_AREA_RATIO:
                    peri = cv2.arcLength(cnt, True)
                    approx = cv2.approxPolyDP(cnt, 0.03 * peri, True)
                    if len(approx) in (4, 5, 6):
                        table_detected = True
                        break
        except Exception as e:
            logger.debug("Table detection error: %s", e)

        # Formulate guidance and decision
        passed = True
        warnings = []
        guidance = None

        if is_blurry:
            passed = False
            warnings.append(f"Image is blurry (blur score {laplacian_var:.1f} < {BLUR_THRESHOLD})")
            guidance = "This page is blurry, please retake in good lighting with a steady camera."
        elif abs(skew_angle) > SKEW_THRESHOLD_DEG:
            warnings.append(f"High skew angle ({skew_angle}°)")
            if not guidance:
                guidance = "The photo is heavily tilted. Straighten the camera over the paper."
        elif not table_detected:
            # We don't fail outright if table isn't 100% matched, but warn
            warnings.append("Attendance register table borders not clearly outlined")
            if not guidance:
                guidance = "Ensure the entire attendance register grid is visible in frame."

        msg = "Quality check passed." if passed else "Quality check failed: " + "; ".join(warnings)

        return QualityCheckResult(
            passed=passed,
            blur_score=round(laplacian_var, 1),
            skew_angle=skew_angle,
            table_detected=table_detected,
            message=msg,
            guidance=guidance,
        )

    @staticmethod
    def rectify_perspective(image: np.ndarray) -> np.ndarray:
        """
        Straighten the attendance sheet using 4-point quadrilateral warp.
        Falls back to original if no suitable rectangle found.
        """
        if image is None or image.size == 0:
            return image

        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image
        blur = cv2.GaussianBlur(gray, (5, 5), 0)
        edges = cv2.Canny(blur, 40, 150)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        edges = cv2.dilate(edges, kernel, iterations=1)

        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        h, w = image.shape[:2]
        image_area = h * w

        best_quad = None
        best_area = 0

        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < image_area * 0.20:
                continue
            peri = cv2.arcLength(cnt, True)
            approx = cv2.approxPolyDP(cnt, 0.02 * peri, True)
            if len(approx) == 4 and area > best_area:
                best_quad = approx.reshape(4, 2).astype(np.float32)
                best_area = area

        if best_quad is None:
            return image

        try:
            # Order 4 points: TL, TR, BR, BL
            s = best_quad.sum(axis=1)
            diff = np.diff(best_quad, axis=1)
            rect = np.zeros((4, 2), dtype=np.float32)
            rect[0] = best_quad[np.argmin(s)]
            rect[2] = best_quad[np.argmax(s)]
            rect[1] = best_quad[np.argmin(diff)]
            rect[3] = best_quad[np.argmax(diff)]

            tl, tr, br, bl = rect
            w_top = np.linalg.norm(tr - tl)
            w_bot = np.linalg.norm(br - bl)
            h_left = np.linalg.norm(bl - tl)
            h_right = np.linalg.norm(br - tr)

            max_w = int(max(w_top, w_bot))
            max_h = int(max(h_left, h_right))

            if max_w < 200 or max_h < 200:
                return image

            dst = np.array([
                [0, 0],
                [max_w - 1, 0],
                [max_w - 1, max_h - 1],
                [0, max_h - 1],
            ], dtype=np.float32)

            M = cv2.getPerspectiveTransform(rect, dst)
            warped = cv2.warpPerspective(image, M, (max_w, max_h))
            return warped
        except Exception as exc:
            logger.warning("Perspective transform failed: %s", exc)
            return image

    @staticmethod
    def crop_cell(image: np.ndarray, bbox: Tuple[int, int, int, int]) -> np.ndarray:
        """
        Crop cell bounding box (x, y, w, h) from an image.
        """
        h, w = image.shape[:2]
        x, y, cw, ch = bbox
        x1 = max(0, min(w - 1, x))
        y1 = max(0, min(h - 1, y))
        x2 = max(0, min(w, x + cw))
        y2 = max(0, min(h, y + ch))
        return image[y1:y2, x1:x2]
