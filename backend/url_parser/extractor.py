"""Route URL extraction through static or dynamic product page parsers."""

from __future__ import annotations

from typing import Any

from .detector import detect_page_type
from .static import extract_static_text


def extract_fabric_text(url: str) -> str:
    """Extract plain text from a product URL for the shared fabric parser."""
    detection: dict[str, Any] = detect_page_type(url)

    if detection["is_dynamic"]:
        raise NotImplementedError("Dynamic URL parsing is not implemented yet.")

    return extract_static_text(url)


def extract_text_from_url(url: str) -> str:
    """Backward-compatible alias for URL text extraction."""
    return extract_fabric_text(url)
