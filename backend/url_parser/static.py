"""Static product page scraper for fabric-related plain text."""

from __future__ import annotations

import json
import re
from typing import Any, Iterable

import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse

from .detector import FABRIC_KEYWORDS, REQUEST_TIMEOUT_SECONDS, USER_AGENT


SITE_PROFILES = {
    "trendyol.com": {
        "keywords": ["materyal", "kumaş", "kumas", "içerik", "icerik", "ürün özellikleri"],
        "selectors": [
            ".detail-attr-container",
            ".product-detail-container",
            "[class*='product-detail']",
        ],
    },
    "zara.com": {
        "keywords": ["composition", "materials", "care", "fabric"],
        "selectors": [
            "[class*='composition']",
            "[class*='product-detail']",
            "[data-qa*='composition']",
        ],
    },
}
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


RAW_PRODUCT_PATTERN = re.compile(r"rawProduct\s*=\s*'(?P<json>.*?)';", re.DOTALL)
PRICE_PATTERNS = (
    re.compile(
        r"(?P<currency>TRY|TL|₺|USD|\$|EUR|€|GBP|£)\s*"
        r"(?P<amount>\d{1,3}(?:[.\s]\d{3})*(?:[,.]\d{2})?|\d+(?:[,.]\d{2})?)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?P<amount>\d{1,3}(?:[.\s]\d{3})*(?:[,.]\d{2})?|\d+(?:[,.]\d{2})?)\s*"
        r"(?P<currency>TRY|TL|₺|USD|\$|EUR|€|GBP|£)",
        re.IGNORECASE,
    ),
)
CURRENCY_ALIASES = {
    "TRY": "TRY",
    "TL": "TRY",
    "₺": "TRY",
    "USD": "USD",
    "$": "USD",
    "EUR": "EUR",
    "€": "EUR",
    "GBP": "GBP",
    "£": "GBP",
}


def _normalize_currency(currency: object) -> str | None:
    """Normalize common currency labels into ISO-like codes."""
    if currency is None:
        return None

    return CURRENCY_ALIASES.get(str(currency).strip().upper())


def _parse_price_amount(amount: object) -> float | None:
    """Parse a localized price amount into a float."""
    raw_amount = str(amount or "").strip()
    if not raw_amount:
        return None

    compact = re.sub(r"\s+", "", raw_amount)
    if "," in compact and "." in compact:
        if compact.rfind(",") > compact.rfind("."):
            compact = compact.replace(".", "").replace(",", ".")
        else:
            compact = compact.replace(",", "")
    elif "," in compact:
        compact = compact.replace(".", "").replace(",", ".")
    else:
        compact = compact.replace(",", "")

    try:
        return float(compact)
    except ValueError:
        return None


def _build_price_result(
    *,
    amount: object,
    currency: object,
    text: object | None = None,
    source: str,
) -> dict[str, object] | None:
    """Build a normalized price result."""
    parsed_amount = _parse_price_amount(amount)
    normalized_currency = _normalize_currency(currency)
    if parsed_amount is None and not text:
        return None

    return {
        "amount": parsed_amount,
        "currency": normalized_currency,
        "text": str(text or "").strip() or None,
        "source": source,
    }


def _extract_price_from_text(text: str, *, source: str = "text") -> dict[str, object] | None:
    """Extract a likely price from visible text."""
    for pattern in PRICE_PATTERNS:
        for match in pattern.finditer(text or ""):
            result = _build_price_result(
                amount=match.group("amount"),
                currency=match.group("currency"),
                text=match.group(0),
                source=source,
            )
            if result is not None:
                return result

    return None


def _request_page(url: str) -> requests.Response:
    """Fetch a product page as static HTML."""
    response = requests.get(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return response


def _profile_for_url(url: str) -> dict[str, object] | None:
    """Return an optional site profile for a URL domain."""
    hostname = urlparse(url).hostname or ""
    for domain, profile in SITE_PROFILES.items():
        if hostname == domain or hostname.endswith(f".{domain}"):
            return profile
    return None


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


def _extract_json_ld_price(soup: BeautifulSoup) -> dict[str, object] | None:
    """Extract product offer price from schema.org JSON-LD blocks."""
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
            is_offer_node = node_type == "Offer" or (
                isinstance(node_type, list) and "Offer" in node_type
            )
            has_offer_price = "price" in node or "lowPrice" in node or "highPrice" in node
            if not is_offer_node and not has_offer_price:
                continue

            amount = node.get("price") or node.get("lowPrice") or node.get("highPrice")
            currency = node.get("priceCurrency")
            result = _build_price_result(
                amount=amount,
                currency=currency,
                source="json_ld",
            )
            if result is not None:
                return result

    return None


def _extract_raw_product_price(soup: BeautifulSoup) -> dict[str, object] | None:
    """Extract price from Akinon-style rawProduct script data."""
    for script in soup.select("script"):
        script_text = script.string or script.get_text(" ", strip=True)
        if not script_text or "rawProduct" not in script_text:
            continue

        match = RAW_PRODUCT_PATTERN.search(script_text)
        if not match:
            continue

        try:
            raw_product = json.loads(match.group("json"))
        except json.JSONDecodeError:
            continue

        result = _build_price_result(
            amount=raw_product.get("price") or raw_product.get("retail_price"),
            currency=raw_product.get("currency_type") or "TRY",
            source="raw_product",
        )
        if result is not None:
            return result

    return None


def _extract_selector_text(soup: BeautifulSoup, url: str) -> str:
    """Extract plain text from likely product detail and description areas."""
    chunks: list[str] = []
    selectors = list(PRODUCT_TEXT_SELECTORS)
    profile = _profile_for_url(url)
    if profile:
        selectors.extend(str(selector) for selector in profile.get("selectors", []))

    for selector in selectors:
        if selector.startswith("script"):
            continue

        for element in soup.select(selector):
            text = element.get_text(" ", strip=True)
            chunks.extend(_extract_fabric_fragments(text, url=url))

    return "\n".join(dict.fromkeys(chunks))


def _extract_meta_text(soup: BeautifulSoup) -> str:
    """Extract useful meta description/product text."""
    chunks: list[str] = []
    for selector in (
        "meta[name='description']",
        "meta[property='og:description']",
        "meta[name='twitter:description']",
    ):
        for element in soup.select(selector):
            content = element.get("content")
            if isinstance(content, str) and content.strip():
                chunks.append(content.strip())
    return "\n".join(dict.fromkeys(chunks))


def _extract_script_text(soup: BeautifulSoup) -> str:
    """Extract fabric-looking snippets from non-JSON script data."""
    chunks: list[str] = []
    for script in soup.select("script:not([type='application/ld+json'])"):
        script_text = script.string or script.get_text(" ", strip=True)
        if not script_text:
            continue
        if any(keyword in script_text.lower() for keyword in FABRIC_KEYWORDS):
            chunks.extend(_extract_fabric_fragments(script_text))
    return "\n".join(dict.fromkeys(chunks))


def _extract_fabric_fragments(text: str, *, url: str | None = None) -> list[str]:
    """Return deduplicated text fragments that contain fabric-related terms."""
    normalized_text = HTML_BREAK_PATTERN.sub("\n", text)
    normalized_text = HTML_TAG_PATTERN.sub(" ", normalized_text)
    fragments = FRAGMENT_SPLIT_PATTERN.split(normalized_text)
    relevant_fragments: list[str] = []
    keywords = list(FABRIC_KEYWORDS)
    if url:
        profile = _profile_for_url(url)
        if profile:
            keywords.extend(str(keyword) for keyword in profile.get("keywords", []))

    for fragment in fragments:
        cleaned_fragment = " ".join(fragment.split())
        if not cleaned_fragment:
            continue

        lower_fragment = cleaned_fragment.lower()
        if "%" in cleaned_fragment or any(keyword in lower_fragment for keyword in keywords):
            relevant_fragments.append(cleaned_fragment)

    return list(dict.fromkeys(relevant_fragments))


def extract_static_candidates(url: str) -> list[str]:
    """Extract fabric candidate text blocks from a static product page."""
    return list(extract_static_data(url)["fabric_candidates"])


def extract_static_data(url: str) -> dict[str, object]:
    """Extract fabric candidate text and product price from a static product page."""
    response = _request_page(url)
    soup = BeautifulSoup(response.text, "html.parser")

    json_ld_text = _extract_json_ld_text(soup)
    selector_text = _extract_selector_text(soup, url)
    meta_text = "\n".join(_extract_fabric_fragments(_extract_meta_text(soup), url=url))
    script_text = _extract_script_text(soup)
    candidates = [chunk for chunk in dict.fromkeys((json_ld_text, selector_text, meta_text, script_text)) if chunk]
    raw_text = "\n".join(candidates)
    price = _extract_raw_product_price(soup) or _extract_json_ld_price(soup) or _extract_price_from_text(
        soup.get_text(" ", strip=True),
        source="static_html",
    )

    return {
        "fabric_candidates": candidates,
        "raw_text": raw_text,
        "price": price,
    }


def extract_static_text(url: str) -> str:
    """Extract raw plain text from a static product page."""
    return "\n".join(extract_static_candidates(url))
