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


def _resize_for_ocr(grayscale: np.ndarray) -> np.ndarray:
    """Scale label text up before OCR."""
    return cv2.resize(
        grayscale,
        None,
        fx=2.0,
        fy=2.0,
        interpolation=cv2.INTER_CUBIC,
    )


def _deskew(binary_image: np.ndarray) -> np.ndarray:
    """Deskew a binary image using its foreground text angle."""
    angle = _compute_skew_angle(binary_image)
    return _rotate_image(binary_image, angle)


def _sharpen(image: np.ndarray) -> np.ndarray:
    """Apply a light sharpening kernel for faint label text."""
    kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]])
    return cv2.filter2D(image, -1, kernel)


def _load_grayscale(image_path: str) -> np.ndarray:
    """Load an image from disk as grayscale."""
    path = Path(image_path)
    if not path.is_file():
        raise FileNotFoundError(f"Image file not found: {image_path}")

    image = cv2.imread(str(path))
    if image is None:
        raise ValueError(f"Failed to read image file: {image_path}")

    return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)


def _orientation_variants(grayscale: np.ndarray) -> list[tuple[str, np.ndarray]]:
    """Return likely reading orientations for label photos."""
    return [
        ("original", grayscale),
        ("rot90_clockwise", cv2.rotate(grayscale, cv2.ROTATE_90_CLOCKWISE)),
        ("rot90_counterclockwise", cv2.rotate(grayscale, cv2.ROTATE_90_COUNTERCLOCKWISE)),
        ("rot180", cv2.rotate(grayscale, cv2.ROTATE_180)),
    ]


def _preprocess_oriented_image(grayscale: np.ndarray) -> list[tuple[str, np.ndarray]]:
    """Return OCR-ready variants for one image orientation."""
    enlarged = _resize_for_ocr(grayscale)
    denoised = cv2.fastNlMeansDenoising(enlarged, None, h=10, templateWindowSize=7, searchWindowSize=21)

    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(denoised)
    sharpened = _sharpen(enhanced)

    adaptive_gaussian = cv2.adaptiveThreshold(
        enhanced,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        31,
        15,
    )
    adaptive_mean = cv2.adaptiveThreshold(
        enhanced,
        255,
        cv2.ADAPTIVE_THRESH_MEAN_C,
        cv2.THRESH_BINARY,
        35,
        11,
    )
    _, otsu = cv2.threshold(enhanced, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    _, sharpened_otsu = cv2.threshold(sharpened, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    return [
        ("adaptive_gaussian", _deskew(adaptive_gaussian)),
        ("adaptive_mean", _deskew(adaptive_mean)),
        ("otsu", _deskew(otsu)),
        ("sharpened_otsu", _deskew(sharpened_otsu)),
        ("enhanced_grayscale", enhanced),
    ]


def preprocess_image_variants(image_path: str) -> list[tuple[str, np.ndarray]]:
    """Return multiple OCR-ready variants for difficult label photos."""
    grayscale = _load_grayscale(image_path)
    variants: list[tuple[str, np.ndarray]] = []

    for orientation_name, oriented_image in _orientation_variants(grayscale):
        for variant_name, processed_image in _preprocess_oriented_image(oriented_image):
            variants.append((f"{orientation_name}_{variant_name}", processed_image))

    return variants


def preprocess_image(image_path: str) -> np.ndarray:
    """Load an image from disk and prepare it for OCR."""
    return preprocess_image_variants(image_path)[0][1]
