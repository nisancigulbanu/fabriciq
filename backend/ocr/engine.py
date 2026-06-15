"""OCR engine built on top of EasyOCR."""

from __future__ import annotations

import base64
import json
import logging
import os
import time

import cv2
import numpy as np
import requests

from .preprocessor import preprocess_image

try:
    import easyocr
except ModuleNotFoundError:
    easyocr = None


logger = logging.getLogger("uvicorn.error")


def _int_env(name: str, default: int) -> int:
    """Read an integer environment variable without breaking OCR startup."""
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        logger.warning("Invalid integer environment value for %s; using %s.", name, default)
        return default


CONFIDENCE_THRESHOLD = 60.0
REMOTE_OCR_CONFIDENCE = 90.0
REMOTE_OCR_TIMEOUT_SECONDS = 90
LMSTUDIO_OCR_TIMEOUT_SECONDS = _int_env("FABRICIQ_LMSTUDIO_TIMEOUT_SECONDS", 180)
REMOTE_OCR_URL = os.getenv(
    "FABRICIQ_REMOTE_OCR_URL",
    "",
).strip()
LMSTUDIO_OCR_BASE_URL = os.getenv("FABRICIQ_LMSTUDIO_BASE_URL", "http://127.0.0.1:1234").rstrip("/")
LMSTUDIO_OCR_MODEL = os.getenv("FABRICIQ_LMSTUDIO_MODEL", "qwen2-vl-2b-instruct").strip()
LANGUAGES = ["tr", "en"]
OCR_ALLOWLIST = (
    "0123456789"
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "ğüşöçıİĞÜŞÖÇ"
    "%.,-/ "
)
_reader: object | None = None

LMSTUDIO_PROMPT_ECHO_MARKERS = (
    "bu bir kiyafet etiketi ocr gorevidir",
    "bu bir kıyafet etiketi ocr gorevidir",
    "gorseldeki etikette yazan",
    "görseldeki etikette yazan",
    "sadece ham metin olarak dondur",
    "sadece ham metin olarak döndür",
)
LMSTUDIO_FABRIC_HINTS = (
    "%",
    "pamuk",
    "cotton",
    "polyester",
    "elastan",
    "elastane",
    "viskoz",
    "viscose",
    "modal",
    "lyocell",
    "keten",
    "linen",
    "yün",
    "wool",
    "akrilik",
    "acrylic",
    "poliamid",
    "polyamide",
    "naylon",
    "nylon",
)


def _encode_lmstudio_image(image: np.ndarray) -> tuple[str, bytes] | None:
    """Encode an image for LM Studio without expanding photos into large PNG payloads."""
    max_side = 1280
    height, width = image.shape[:2]
    scale = min(1.0, max_side / max(height, width))
    if scale < 1.0:
        image = cv2.resize(
            image,
            (int(width * scale), int(height * scale)),
            interpolation=cv2.INTER_AREA,
        )

    encoded_ok, encoded_image = cv2.imencode(
        ".jpg",
        image,
        [int(cv2.IMWRITE_JPEG_QUALITY), 88],
    )
    if not encoded_ok:
        return None

    return "image/jpeg", encoded_image.tobytes()


def _get_reader() -> object:
    """Create and cache the EasyOCR reader."""
    global _reader

    if easyocr is None:
        raise RuntimeError("EasyOCR is not installed in the active Python environment.")

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


def _looks_like_lmstudio_prompt_echo(text: str) -> bool:
    """Return true when the model echoed the OCR instruction instead of reading the image."""
    normalized = " ".join(text.lower().split())
    return any(marker in normalized for marker in LMSTUDIO_PROMPT_ECHO_MARKERS)


def _has_fabric_hint(text: str) -> bool:
    """Return true when OCR text contains any likely fabric/composition hint."""
    normalized = text.lower()
    return any(hint in normalized for hint in LMSTUDIO_FABRIC_HINTS)


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


def _run_lmstudio_ocr(image: np.ndarray) -> dict[str, str | float] | None:
    """Try LM Studio's OpenAI-compatible vision endpoint."""
    if not LMSTUDIO_OCR_BASE_URL or not LMSTUDIO_OCR_MODEL:
        logger.info("LM Studio OCR settings are empty; skipping LM Studio.")
        return None

    encoded_result = _encode_lmstudio_image(image)
    if encoded_result is None:
        logger.warning("LM Studio OCR skipped because image encoding failed.")
        return None

    mime_type, encoded_image = encoded_result
    image_base64 = base64.b64encode(encoded_image).decode("ascii")
    endpoint = f"{LMSTUDIO_OCR_BASE_URL}/v1/chat/completions"
    prompt = (
        "Read the clothing label in the image and transcribe only the visible label text. "
        "Focus on material composition, percentages, and fabric names. "
        "Do not describe the image. Do not repeat these instructions. Do not guess missing values. "
        "If no readable label text is visible, return NO_TEXT_FOUND."
    )

    try:
        started_at = time.perf_counter()
        logger.info(
            "Sending image to LM Studio OCR: %s model=%s payload_bytes=%s",
            endpoint,
            LMSTUDIO_OCR_MODEL,
            len(encoded_image),
        )
        response = requests.post(
            endpoint,
            json={
                "model": LMSTUDIO_OCR_MODEL,
                "messages": [
                    {
                        "role": "system",
                        "content": "You are an OCR engine. Return only text visible in the provided image.",
                    },
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:{mime_type};base64,{image_base64}"},
                            },
                        ],
                    }
                ],
                "temperature": 0,
                "max_tokens": 1024,
            },
            timeout=LMSTUDIO_OCR_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        payload = response.json()
        text = str(payload["choices"][0]["message"]["content"] or "").strip()
        elapsed_seconds = time.perf_counter() - started_at
        logger.info(
            "LM Studio OCR responded in %.2fs with %s characters.",
            elapsed_seconds,
            len(text),
        )
        logger.info("LM Studio OCR text preview: %s", text[:500])
    except (KeyError, IndexError, TypeError) as exc:
        logger.warning("LM Studio OCR response shape was unexpected; trying next OCR path. Error: %s", exc)
        return None
    except requests.RequestException as exc:
        logger.warning("LM Studio OCR request failed; trying next OCR path. Error: %s", exc)
        return None
    except ValueError as exc:
        logger.warning("LM Studio OCR returned invalid JSON; trying next OCR path. Error: %s", exc)
        return None

    if not text:
        logger.warning("LM Studio OCR returned empty text; trying next OCR path.")
        return None
    if _looks_like_lmstudio_prompt_echo(text):
        logger.warning("LM Studio OCR echoed the prompt instead of reading the label; trying next OCR path.")
        return None
    if not _has_fabric_hint(text):
        logger.warning("LM Studio OCR returned text without fabric hints; trying next OCR path.")
        return None
    if text.upper().strip().startswith(("NO_COMPOSITION_FOUND", "NO_TEXT_FOUND")):
        logger.warning("LM Studio OCR found no readable label text; trying next OCR path.")
        return None

    return {
        "raw_text": text,
        "confident_text": text,
        "avg_confidence": REMOTE_OCR_CONFIDENCE,
    }


def run_lmstudio_ocr_from_path(image_path: str) -> dict[str, str | float] | None:
    """Extract composition text from the original uploaded image with LM Studio."""
    image = cv2.imread(image_path)
    if image is None:
        logger.warning("LM Studio OCR skipped because the original image could not be read: %s", image_path)
        return None

    return _run_lmstudio_ocr(image)


def run_easyocr(image: np.ndarray) -> dict[str, str | float]:
    """Extract raw and confidence-filtered text from an image array with EasyOCR."""
    remote_result = _run_remote_ocr(image)
    if remote_result is not None:
        logger.info("Using remote OCR result.")
        return remote_result

    if easyocr is None:
        logger.warning("Local EasyOCR is not installed; returning empty OCR result.")
        return {
            "raw_text": "",
            "confident_text": "",
            "avg_confidence": 0.0,
        }

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
