"""Alternative OCR engine built on top of PaddleOCR."""

from __future__ import annotations

from typing import Any

import numpy as np

CONFIDENCE_THRESHOLD = 40.0
_reader: Any | None = None


def _empty_ocr_result() -> dict[str, str | float]:
    """Return an empty OCR payload."""
    return {
        "raw_text": "",
        "confident_text": "",
        "avg_confidence": 0.0,
    }


def _get_reader() -> Any:
    """Create and cache the PaddleOCR reader."""
    global _reader

    if _reader is None:
        try:
            from paddleocr import PaddleOCR
        except ImportError:
            return None

        _reader = PaddleOCR(lang="en", use_angle_cls=True)

    return _reader


def _normalize_confidence(score: float) -> float:
    """Convert a PaddleOCR confidence score from 0-1 to 0-100."""
    return round(score * 100, 2)


def _iter_paddle_lines(results: Any) -> list[tuple[str, float]]:
    """Extract text and confidence pairs from PaddleOCR result variants."""
    if not results:
        return []

    page_results = results[0] if isinstance(results, list) and len(results) == 1 else results
    lines: list[tuple[str, float]] = []

    if isinstance(page_results, dict):
        texts = page_results.get("rec_texts") or []
        scores = page_results.get("rec_scores") or []
        for text, score in zip(texts, scores):
            lines.append((str(text), float(score)))
        return lines

    for item in page_results:
        if not isinstance(item, (list, tuple)) or len(item) < 2:
            continue

        text_info = item[1]
        if not isinstance(text_info, (list, tuple)) or len(text_info) < 2:
            continue

        text, confidence = text_info[0], text_info[1]
        lines.append((str(text), float(confidence)))

    return lines


def _build_ocr_result(results: Any) -> dict[str, str | float]:
    """Convert PaddleOCR detections into the public OCR result format."""
    lines = _iter_paddle_lines(results)
    if not lines:
        return _empty_ocr_result()

    raw_tokens: list[str] = []
    confident_tokens: list[str] = []
    confidence_scores: list[float] = []

    for text, confidence in lines:
        cleaned_text = text.strip()
        normalized_confidence = _normalize_confidence(confidence)
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


def run_paddleocr(image: np.ndarray) -> dict[str, str | float]:
    """Extract raw and confidence-filtered text from an image array with PaddleOCR."""
    reader = _get_reader()
    if reader is None:
        return _empty_ocr_result()

    try:
        return _build_ocr_result(reader.ocr(image, cls=True))
    except Exception:
        return _empty_ocr_result()
