"""Static product page scraper for fabric-related plain text."""

from __future__ import annotations

import json
import re
from typing import Any, Iterable

import requests
from bs4 import BeautifulSoup

from .detector import FABRIC_KEYWORDS, REQUEST_TIMEOUT_SECONDS, USER_AGENT


PRODUCT_TEXT_SELECTORS = (
    "script[type='application/ld+json']",
    "[itemtype*='schema.org/Product']",
    "[class*='product'][class*='detail']",
    "[id*='product'][id*='detail']",
    "[class*='product'][class*='description']",
    "[id*='product'][id*='description']",
    "[class*='description']",
    "[id*='description']",
    "[class*='detail']",
    "[id*='detail']",
    "[class*='material']",
    "[class*='fabric']",
    "[class*='composition']",
    "[class*='kumas']",
    "[class*='materyal']",
    "[class*='icerik']",
)
JSON_LD_TEXT_KEYS = {
    "name",
    "description",
    "material",
    "materials",
    "text",
    "value",
}
JSON_LD_METADATA_KEYS = {
    "@context",
    "@id",
    "@type",
    "url",
    "image",
    "sku",
    "gtin",
    "brand",
    "offers",
    "aggregateRating",
    "review",
}
HTML_BREAK_PATTERN = re.compile(r"<br\s*/?>", re.IGNORECASE)
HTML_TAG_PATTERN = re.compile(r"<[^>]+>")
FRAGMENT_SPLIT_PATTERN = re.compile(r"[\n\r\t|•]+")


def _request_page(url: str) -> requests.Response:
    """Fetch a product page as static HTML."""
    response = requests.get(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return response


def _iter_json_ld_nodes(value: Any) -> Iterable[Any]:
    """Yield all nested JSON-LD nodes from dicts and lists."""
    if isinstance(value, dict):
        yield value
        for nested in value.values():
            yield from _iter_json_ld_nodes(nested)
    elif isinstance(value, list):
        for item in value:
            yield from _iter_json_ld_nodes(item)


def _stringify_json_ld_value(value: Any) -> str | None:
    """Convert useful JSON-LD primitive values to plain text."""
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    if isinstance(value, (int, float)):
        return str(value)
    return None


def _extract_json_ld_text(soup: BeautifulSoup) -> str:
    """Extract product-oriented plain text from schema.org JSON-LD blocks."""
    chunks: list[str] = []

    for script in soup.select("script[type='application/ld+json']"):
        raw_json = script.string or script.get_text(strip=True)
        if not raw_json:
            continue

        try:
            parsed_json = json.loads(raw_json)
        except json.JSONDecodeError:
            continue

        for node in _iter_json_ld_nodes(parsed_json):
            if not isinstance(node, dict):
                continue

            node_type = node.get("@type")
            is_product_node = node_type == "Product" or (
                isinstance(node_type, list) and "Product" in node_type
            )

            for key, value in node.items():
                lower_key = str(key).lower()
                if key in JSON_LD_METADATA_KEYS and not is_product_node:
                    continue

                if key in JSON_LD_TEXT_KEYS or "material" in lower_key or "fabric" in lower_key:
                    text_value = _stringify_json_ld_value(value)
                    if text_value:
                        chunks.append(text_value)
                elif isinstance(value, str) and is_product_node and key not in JSON_LD_METADATA_KEYS:
                    stripped = value.strip()
                    if stripped:
                        chunks.append(stripped)

    return "\n".join(dict.fromkeys(chunks))


def _extract_selector_text(soup: BeautifulSoup) -> str:
    """Extract plain text from likely product detail and description areas."""
    chunks: list[str] = []

    for selector in PRODUCT_TEXT_SELECTORS:
        if selector.startswith("script"):
            continue

        for element in soup.select(selector):
            text = element.get_text(" ", strip=True)
            chunks.extend(_extract_fabric_fragments(text))

    return "\n".join(dict.fromkeys(chunks))


def _extract_fabric_fragments(text: str) -> list[str]:
    """Return deduplicated text fragments that contain fabric-related terms."""
    normalized_text = HTML_BREAK_PATTERN.sub("\n", text)
    normalized_text = HTML_TAG_PATTERN.sub(" ", normalized_text)
    fragments = FRAGMENT_SPLIT_PATTERN.split(normalized_text)
    relevant_fragments: list[str] = []

    for fragment in fragments:
        cleaned_fragment = " ".join(fragment.split())
        if not cleaned_fragment:
            continue

        lower_fragment = cleaned_fragment.lower()
        if any(keyword in lower_fragment for keyword in FABRIC_KEYWORDS):
            relevant_fragments.append(cleaned_fragment)

    return list(dict.fromkeys(relevant_fragments))


def extract_static_text(url: str) -> str:
    """Extract raw plain text from a static product page."""
    response = _request_page(url)
    soup = BeautifulSoup(response.text, "html.parser")

    json_ld_text = _extract_json_ld_text(soup)
    selector_text = _extract_selector_text(soup)

    return "\n".join(chunk for chunk in (json_ld_text, selector_text) if chunk)
