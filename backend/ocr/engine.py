"""OCR engine built on top of EasyOCR."""

from __future__ import annotations

import base64
import json
import logging
import os
import time

import cv2
import easyocr
import numpy as np
import requests

from .preprocessor import preprocess_image

CONFIDENCE_THRESHOLD = 60.0
REMOTE_OCR_CONFIDENCE = 90.0
REMOTE_OCR_TIMEOUT_SECONDS = 90
REMOTE_OCR_URL = os.getenv(
    "FABRICIQ_REMOTE_OCR_URL",
    "https://overcoat-treat-obsession.ngrok-free.dev/ocr",
).strip()
LANGUAGES = ["tr", "en"]
OCR_ALLOWLIST = (
    "0123456789"
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "ğüşöçıİĞÜŞÖÇ"
    "%.,-/ "
)
logger = logging.getLogger(__name__)
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


def _extract_remote_text(payload: object) -> str:
    """Extract OCR text from the Colab/ngrok response payload."""
    if isinstance(payload, dict):
        result = payload.get("result")
    else:
        result = payload

    if isinstance(result, list):
        result = result[0] if result else ""

    if isinstance(result, (dict, list)):
        return json.dumps(result, ensure_ascii=False)

    return str(result or "").strip()


def _run_remote_ocr(image: np.ndarray) -> dict[str, str | float] | None:
    """Try the external Colab OCR service before falling back to local OCR."""
    if not REMOTE_OCR_URL:
        logger.info("Remote OCR URL is empty; using local EasyOCR.")
        return None

    encoded_ok, encoded_image = cv2.imencode(".png", image)
    if not encoded_ok:
        logger.warning("Remote OCR skipped because image encoding failed.")
        return None

    try:
        started_at = time.perf_counter()
        logger.info("Sending image to remote OCR: %s", REMOTE_OCR_URL)
        response = requests.post(
            REMOTE_OCR_URL,
            json={"image_base64": base64.b64encode(encoded_image).decode("ascii")},
            headers={"ngrok-skip-browser-warning": "true"},
            timeout=REMOTE_OCR_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        text = _extract_remote_text(response.json())
        elapsed_seconds = time.perf_counter() - started_at
        logger.info(
            "Remote OCR responded in %.2fs with %s characters.",
            elapsed_seconds,
            len(text),
        )
    except requests.RequestException as exc:
        logger.warning("Remote OCR request failed; using local EasyOCR. Error: %s", exc)
        return None
    except ValueError as exc:
        logger.warning("Remote OCR returned invalid JSON; using local EasyOCR. Error: %s", exc)
        return None

    if not text:
        logger.warning("Remote OCR returned empty text; using local EasyOCR.")
        return None

    return {
        "raw_text": text,
        "confident_text": text,
        "avg_confidence": REMOTE_OCR_CONFIDENCE,
    }


def run_easyocr(image: np.ndarray) -> dict[str, str | float]:
    """Extract raw and confidence-filtered text from an image array with EasyOCR."""
    remote_result = _run_remote_ocr(image)
    if remote_result is not None:
        logger.info("Using remote OCR result.")
        return remote_result

    logger.info("Running local EasyOCR fallback.")
    detections = _get_reader().readtext(
        image,
        detail=1,
        contrast_ths=0.05,
        adjust_contrast=0.7,
        text_threshold=0.6,
        low_text=0.3,
        mag_ratio=2.0,
        allowlist=OCR_ALLOWLIST,
    )
    logger.info("Local EasyOCR returned %s detections.", len(detections))
    return _build_ocr_result(detections)


def extract_text_from_image(processed_image: np.ndarray) -> dict[str, str | float]:
    """Extract raw and confidence-filtered text from a processed image array."""
    return run_easyocr(processed_image)


def extract_text(image_path: str) -> dict[str, str | float]:
    """Extract raw and confidence-filtered text from an image path."""
    processed_image = preprocess_image(image_path)
    return extract_text_from_image(processed_image)
