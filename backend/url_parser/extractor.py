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
)
from .selenium_dynamic import extract_selenium_text
from .static import extract_static_text


def _has_parseable_composition(text: str) -> bool:
    """Return true when the shared fabric parser can extract a composition."""
    from backend.ocr.fabric_parser import parse_fabric_composition

    return bool(parse_fabric_composition(text)["composition"])


def _extract_dynamic_or_raise(url: str) -> str:
    """Extract with Selenium first, then Playwright as a secondary browser fallback."""
    try:
        return extract_selenium_text(url)
    except (
        DynamicScraperBlockedError,
        DynamicScraperNoTextError,
        DynamicScraperTimeoutError,
        DynamicScraperUnavailableError,
    ):
        return extract_dynamic_text(url)


def extract_fabric_text(url: str) -> str:
    """Extract plain text from a product URL for the shared fabric parser."""
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
