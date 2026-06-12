"""Image preprocessing utilities for OCR input preparation."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

MAX_INPUT_LONG_EDGE = 1800
MAX_OCR_VARIANT_LONG_EDGE = 1000
OCR_SCALE_FACTOR = 1.6
FAST_VARIANT_NAMES = {
    "band_upper_grayscale",
    "band_lower_grayscale",
    "band_middle_grayscale",
    "band_upper_denoise_clahe",
    "band_lower_denoise_clahe",
    "grayscale_resize",
    "denoise_clahe",
    "sharpened_otsu",
    "adaptive_gaussian",
}


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
    enlarged = cv2.resize(
        grayscale,
        None,
        fx=OCR_SCALE_FACTOR,
        fy=OCR_SCALE_FACTOR,
        interpolation=cv2.INTER_CUBIC,
    )
    return _limit_variant_size(enlarged)


def _limit_variant_size(image: np.ndarray) -> np.ndarray:
    """Keep OCR variants large enough to read but bounded for CPU latency."""
    height, width = image.shape[:2]
    long_edge = max(height, width)
    if long_edge <= MAX_OCR_VARIANT_LONG_EDGE:
        return image

    scale = MAX_OCR_VARIANT_LONG_EDGE / long_edge
    return cv2.resize(
        image,
        (max(1, round(width * scale)), max(1, round(height * scale))),
        interpolation=cv2.INTER_AREA,
    )


def _deskew(binary_image: np.ndarray) -> np.ndarray:
    """Deskew a binary image using its foreground text angle."""
    angle = _compute_skew_angle(binary_image)
    return _rotate_image(binary_image, angle)


def _reduce_fabric_texture(binary_image: np.ndarray) -> np.ndarray:
    """Remove small thread-like texture artifacts from a binary OCR image."""
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
    return cv2.morphologyEx(binary_image, cv2.MORPH_OPEN, kernel)


def _sharpen(image: np.ndarray) -> np.ndarray:
    """Apply a light sharpening kernel for faint label text."""
    kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]])
    return cv2.filter2D(image, -1, kernel)


def apply_clahe_enhancement(image: np.ndarray) -> np.ndarray:
    """Enhance local contrast by applying CLAHE to the LAB lightness channel."""
    if len(image.shape) == 2:
        bgr_image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    else:
        bgr_image = image

    lab_image = cv2.cvtColor(bgr_image, cv2.COLOR_BGR2LAB)
    lightness, channel_a, channel_b = cv2.split(lab_image)
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    enhanced_lightness = clahe.apply(lightness)
    enhanced_lab = cv2.merge((enhanced_lightness, channel_a, channel_b))
    return cv2.cvtColor(enhanced_lab, cv2.COLOR_LAB2BGR)


def apply_adaptive_threshold(image: np.ndarray) -> np.ndarray:
    """Apply Gaussian adaptive thresholding to a grayscale version of an image."""
    if len(image.shape) == 2:
        grayscale = image
    else:
        grayscale = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    return cv2.adaptiveThreshold(
        grayscale,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        11,
        2,
    )


def _load_grayscale(image_path: str) -> np.ndarray:
    """Load an image from disk as grayscale."""
    path = Path(image_path)
    if not path.is_file():
        raise FileNotFoundError(f"Image file not found: {image_path}")

    image = cv2.imread(str(path))
    if image is None:
        raise ValueError(f"Failed to read image file: {image_path}")

    grayscale = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    return _limit_image_size(grayscale)


def _limit_image_size(grayscale: np.ndarray) -> np.ndarray:
    """Downscale very large photos before OCR preprocessing."""
    height, width = grayscale.shape[:2]
    long_edge = max(height, width)
    if long_edge <= MAX_INPUT_LONG_EDGE:
        return grayscale

    scale = MAX_INPUT_LONG_EDGE / long_edge
    return cv2.resize(
        grayscale,
        (max(1, round(width * scale)), max(1, round(height * scale))),
        interpolation=cv2.INTER_AREA,
    )


def _orientation_variants(grayscale: np.ndarray) -> list[tuple[str, np.ndarray]]:
    """Return likely reading orientations for label photos."""
    variants = [
        ("original", grayscale),
        ("rot90_clockwise", cv2.rotate(grayscale, cv2.ROTATE_90_CLOCKWISE)),
        ("rot90_counterclockwise", cv2.rotate(grayscale, cv2.ROTATE_90_COUNTERCLOCKWISE)),
        ("rot180", cv2.rotate(grayscale, cv2.ROTATE_180)),
    ]
    height, width = grayscale.shape[:2]
    if height > width * 1.25:
        return [variants[2], variants[1], variants[0], variants[3]]
    return [variants[2], variants[1], variants[0], variants[3]]


def _long_label_band_variants(image: np.ndarray, prefix: str) -> list[tuple[str, np.ndarray]]:
    """Return OCR crops for long label photos where full-line OCR is noisy."""
    height, width = image.shape[:2]
    if width < height * 2.4:
        return []

    bands = (
        ("upper", 0.18, 0.46),
        ("lower", 0.52, 0.84),
        ("middle", 0.34, 0.68),
    )
    variants: list[tuple[str, np.ndarray]] = []
    for band_name, start_fraction, end_fraction in bands:
        y1 = max(0, int(height * start_fraction))
        y2 = min(height, int(height * end_fraction))
        if y2 - y1 < 24:
            continue
        crop = image[y1:y2, :]
        crop = cv2.resize(crop, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
        variants.append((f"band_{band_name}_{prefix}", crop))
    return variants


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
    adaptive_gaussian = _reduce_fabric_texture(adaptive_gaussian)
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

    band_variants = (
        _long_label_band_variants(enlarged, "grayscale")
        + _long_label_band_variants(enhanced, "denoise_clahe")
    )

    return band_variants + [
        ("original", _limit_variant_size(grayscale)),
        ("grayscale_resize", enlarged),
        ("grayscale_clahe", clahe.apply(enlarged)),
        ("denoise_clahe", enhanced),
        ("adaptive_gaussian", _deskew(adaptive_gaussian)),
        ("adaptive_mean", _deskew(adaptive_mean)),
        ("otsu", _deskew(otsu)),
        ("sharpened_otsu", _deskew(sharpened_otsu)),
        ("enhanced_grayscale", enhanced),
        ("clahe_lab", apply_clahe_enhancement(grayscale)),
        ("adaptive_threshold_gaussian_11", apply_adaptive_threshold(grayscale)),
    ]


def preprocess_image_variants(image_path: str, *, exhaustive: bool = False) -> list[tuple[str, np.ndarray]]:
    """Return OCR-ready variants for label photos.

    The default path is intentionally small for interactive use. Exhaustive mode
    is kept for debug diagnostics where accuracy investigation matters more than
    response time.
    """
    grayscale = _load_grayscale(image_path)
    variants: list[tuple[str, np.ndarray]] = []

    for orientation_name, oriented_image in _orientation_variants(grayscale):
        for variant_name, processed_image in _preprocess_oriented_image(oriented_image):
            if not exhaustive and variant_name not in FAST_VARIANT_NAMES:
                continue
            if not exhaustive and orientation_name == "rot180":
                continue
            variants.append((f"{orientation_name}_{variant_name}", processed_image))

    return variants if exhaustive else variants[:10]


def preprocess_image(image_path: str) -> np.ndarray:
    """Load an image from disk and prepare it for OCR."""
    return preprocess_image_variants(image_path)[0][1]
