"""Route URL extraction through static or dynamic product page parsers."""

from __future__ import annotations

from typing import Any

import requests

from .detector import detect_page_type
from .dynamic import (
    DynamicScraperBlockedError,
    DynamicScraperNoTextError,
    DynamicScraperTimeoutError,
    DynamicScraperUnavailableError,
    extract_dynamic_text,
    extract_dynamic_data,
)
from .selenium_dynamic import extract_selenium_data, extract_selenium_text
from .static import extract_static_candidates, extract_static_data, extract_static_text


def _has_parseable_composition(text: str) -> bool:
    """Return true when the shared fabric parser can extract a composition."""
    from backend.ocr.fabric_parser import parse_fabric_composition

    return bool(parse_fabric_composition(text)["composition"])


def _extract_dynamic_or_raise(url: str) -> str:
    """Extract text with Selenium first, then Playwright as a secondary browser fallback."""
    return str(_extract_dynamic_data_or_raise(url)["raw_text"])


def _extract_dynamic_data_or_raise(url: str) -> dict[str, Any]:
    """Extract data with Selenium first, then Playwright as a secondary browser fallback."""
    try:
        return extract_selenium_data(url)
    except (
        DynamicScraperBlockedError,
        DynamicScraperNoTextError,
        DynamicScraperTimeoutError,
        DynamicScraperUnavailableError,
    ):
        return extract_dynamic_data(url)


def _success_result(
    *,
    source: str,
    url: str,
    raw_text: str,
    fabric_candidates: list[str],
    price: dict[str, object] | None = None,
) -> dict[str, Any]:
    """Build a structured URL extraction success payload."""
    return {
        "success": True,
        "source": source,
        "url": url,
        "raw_text": raw_text,
        "fabric_candidates": fabric_candidates,
        "price": price,
        "composition": [],
        "confidence_score": 0.0,
        "warnings": [],
        "error": None,
    }


def _failure_result(url: str, error: str) -> dict[str, Any]:
    """Build a structured URL extraction failure payload."""
    return {
        "success": False,
        "source": "url",
        "url": url,
        "raw_text": "",
        "fabric_candidates": [],
        "price": None,
        "composition": [],
        "confidence_score": 0.0,
        "warnings": [
            "Bu urun sayfasindan kumas bilgisi otomatik alinamadi. Etiket fotografi yukleyebilirsiniz."
        ],
        "error": error,
    }


def extract_fabric_data(url: str) -> dict[str, Any]:
    """Extract fabric-oriented text from a URL with static-first, browser fallback flow."""
    try:
        detection: dict[str, Any] = detect_page_type(url)
    except requests.RequestException:
        detection = {"is_dynamic": True}

    if not detection.get("is_dynamic"):
        try:
            static_data = extract_static_data(url)
            static_candidates = list(static_data.get("fabric_candidates") or [])
            static_text = str(static_data.get("raw_text") or "\n".join(static_candidates))
            if _has_parseable_composition(static_text):
                return _success_result(
                    source="static_html",
                    url=url,
                    raw_text=static_text,
                    fabric_candidates=static_candidates,
                    price=static_data.get("price"),  # type: ignore[arg-type]
                )
        except requests.RequestException:
            pass

    try:
        dynamic_data = _extract_dynamic_data_or_raise(url)
        dynamic_text = str(dynamic_data.get("raw_text") or "")
        return _success_result(
            source="playwright",
            url=url,
            raw_text=dynamic_text,
            fabric_candidates=[dynamic_text] if dynamic_text else [],
            price=dynamic_data.get("price"),  # type: ignore[arg-type]
        )
    except DynamicScraperNoTextError:
        return _failure_result(url, "fabric_info_not_found")


def extract_fabric_text(url: str) -> str:
    """Extract plain text from a product URL for the shared fabric parser."""
    extracted = extract_fabric_data(url)
    if extracted["success"]:
        return str(extracted["raw_text"])
    if extracted["error"] == "fabric_info_not_found":
        raise DynamicScraperNoTextError("No fabric text found.")

    raise DynamicScraperNoTextError(str(extracted["error"]))


def _legacy_extract_fabric_text(url: str) -> str:
    """Previous plain text extraction implementation kept for reference."""
    try:
        detection: dict[str, Any] = detect_page_type(url)
    except requests.RequestException:
        return _extract_dynamic_or_raise(url)

    if detection["is_dynamic"]:
        return _extract_dynamic_or_raise(url)

    try:
        static_text = extract_static_text(url)
    except requests.RequestException:
        return _extract_dynamic_or_raise(url)

    if _has_parseable_composition(static_text):
        return static_text

    return _extract_dynamic_or_raise(url)


def extract_text_from_url(url: str) -> str:
    """Backward-compatible alias for URL text extraction."""
    return extract_fabric_text(url)
