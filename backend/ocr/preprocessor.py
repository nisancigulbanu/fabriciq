"""Image preprocessing utilities for OCR input preparation."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np


def _compute_skew_angle(binary_image: np.ndarray) -> float:
    """Estimate the skew angle from foreground pixels in a binary image."""
    foreground_points = np.column_stack(np.where(binary_image < 255))
    if foreground_points.size == 0:
        return 0.0

    angle = cv2.minAreaRect(foreground_points)[-1]
    if angle < -45:
        angle = 90 + angle
    elif angle > 45:
        angle = angle - 90

    return float(angle)


def _rotate_image(image: np.ndarray, angle: float) -> np.ndarray:
    """Rotate an image around its center while preserving the original size."""
    if abs(angle) < 0.1:
        return image

    height, width = image.shape[:2]
    center = (width / 2.0, height / 2.0)
    rotation_matrix = cv2.getRotationMatrix2D(center, angle, 1.0)

    return cv2.warpAffine(
        image,
        rotation_matrix,
        (width, height),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REPLICATE,
    )


def preprocess_image(image_path: str) -> np.ndarray:
    """Load an image from disk and prepare it for OCR."""
    path = Path(image_path)
    if not path.is_file():
        raise FileNotFoundError(f"Image file not found: {image_path}")

    image = cv2.imread(str(path))
    if image is None:
        raise ValueError(f"Failed to read image file: {image_path}")

    grayscale = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    enlarged = cv2.resize(
        grayscale,
        None,
        fx=2.0,
        fy=2.0,
        interpolation=cv2.INTER_CUBIC,
    )
    denoised = cv2.fastNlMeansDenoising(enlarged, None, h=10, templateWindowSize=7, searchWindowSize=21)

    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(denoised)

    thresholded = cv2.adaptiveThreshold(
        enhanced,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        31,
        15,
    )

    angle = _compute_skew_angle(thresholded)
    return _rotate_image(thresholded, angle)
