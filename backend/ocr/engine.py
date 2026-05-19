"""OCR engine built on top of EasyOCR."""

from __future__ import annotations

import easyocr
import numpy as np

from .preprocessor import preprocess_image

CONFIDENCE_THRESHOLD = 60.0
LANGUAGES = ["tr", "en"]
_reader: easyocr.Reader | None = None


def _get_reader() -> easyocr.Reader:
    """Create and cache the EasyOCR reader."""
    global _reader

    if _reader is None:
        _reader = easyocr.Reader(LANGUAGES)

    return _reader


def _normalize_confidence(score: float) -> float:
    """Convert an EasyOCR confidence score from 0-1 to 0-100."""
    return round(score * 100, 2)


def _build_ocr_result(detections: list[list[object]]) -> dict[str, str | float]:
    """Convert EasyOCR detections into the public OCR result format."""
    if not detections:
        return {
            "raw_text": "",
            "confident_text": "",
            "avg_confidence": 0.0,
        }

    raw_tokens: list[str] = []
    confident_tokens: list[str] = []
    confidence_scores: list[float] = []

    for detection in detections:
        _, text, confidence = detection
        cleaned_text = str(text).strip()
        normalized_confidence = _normalize_confidence(float(confidence))

        confidence_scores.append(normalized_confidence)

        if cleaned_text:
            raw_tokens.append(cleaned_text)
            if normalized_confidence >= CONFIDENCE_THRESHOLD:
                confident_tokens.append(cleaned_text)

    average_confidence = round(sum(confidence_scores) / len(confidence_scores), 2) if confidence_scores else 0.0

    return {
        "raw_text": " ".join(raw_tokens),
        "confident_text": " ".join(confident_tokens),
        "avg_confidence": average_confidence,
    }


def extract_text_from_image(processed_image: np.ndarray) -> dict[str, str | float]:
    """Extract raw and confidence-filtered text from a processed image array."""
    detections = _get_reader().readtext(processed_image, detail=1)
    return _build_ocr_result(detections)


def extract_text(image_path: str) -> dict[str, str | float]:
    """Extract raw and confidence-filtered text from an image path."""
    processed_image = preprocess_image(image_path)
    return extract_text_from_image(processed_image)
