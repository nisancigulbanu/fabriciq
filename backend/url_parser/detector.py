"""Detect whether a product URL can be parsed with the static scraper."""

from __future__ import annotations

from typing import Any

import requests
from bs4 import BeautifulSoup


REQUEST_TIMEOUT_SECONDS = 12
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
FABRIC_KEYWORDS = (
    "fabric",
    "material",
    "composition",
    "cotton",
    "polyester",
    "viscose",
    "elastane",
    "kumaş",
    "kumas",
    "materyal",
    "içerik",
    "icerik",
    "pamuk",
    "polyester",
    "viskon",
    "elastan",
    "acrylic",
    "akrilik",
    "polyamide",
    "polyamid",
    "nylon",
    "naylon",
    "wool",
    "yün",
    "yun",
    "linen",
    "keten",
    "silk",
    "ipek",
)
PRODUCT_DETAIL_SELECTORS = (
    "[class*='product'][class*='detail']",
    "[id*='product'][id*='detail']",
    "[class*='description']",
    "[id*='description']",
    "[class*='material']",
    "[class*='fabric']",
    "[class*='composition']",
    "[class*='kumas']",
    "[class*='materyal']",
    "[class*='icerik']",
)


def _request_page(url: str) -> requests.Response:
    """Fetch a URL with headers suitable for static product pages."""
    response = requests.get(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return response


def _contains_fabric_keyword(text: str) -> bool:
    """Return true when a text block appears to include fabric-related content."""
    lower_text = text.lower()
    return any(keyword in lower_text for keyword in FABRIC_KEYWORDS)


def _has_product_detail_fabric_text(soup: BeautifulSoup) -> bool:
    """Check product detail blocks for fabric-related terms."""
    for selector in PRODUCT_DETAIL_SELECTORS:
        for element in soup.select(selector):
            if _contains_fabric_keyword(element.get_text(" ", strip=True)):
                return True
    return False


def detect_page_type(url: str) -> dict[str, Any]:
    """Detect whether a URL has enough static HTML data to parse without a browser."""
    response = _request_page(url)
    soup = BeautifulSoup(response.text, "html.parser")

    has_json_ld = bool(soup.select("script[type='application/ld+json']"))
    has_product_detail_fabric = _has_product_detail_fabric_text(soup)

    return {
        "url": url,
        "is_dynamic": not (has_json_ld or has_product_detail_fabric),
        "has_json_ld": has_json_ld,
        "has_product_detail_fabric": has_product_detail_fabric,
    }
