"""Inditex-family product composition extraction helpers."""

from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urlparse


INDITEX_API_TIMEOUT_SECONDS = 12


def _find_first_pattern(pattern: str, text: str) -> str | None:
    """Return the first regex capture group from a text."""
    match = re.search(pattern, text, flags=re.IGNORECASE)
    return match.group(1) if match else None


def extract_inditex_context(page_source: str, current_url: str) -> dict[str, str] | None:
    """Extract Inditex product API context values from a rendered page."""
    product_id = (
        _find_first_pattern(r"inditex\.iProductId\s*=\s*(\d+)", page_source)
        or _find_first_pattern(r"iProductId\s*=\s*(\d+)", page_source)
        or _find_first_pattern(r"ProductId\s*=\s*(\d+)", page_source)
        or _find_first_pattern(r'"productId"\s*:\s*(\d+)', page_source)
        or _find_first_pattern(r'"pelement"\s*:\s*\["?(\d+)"?\]', page_source)
    )
    store_id = (
        _find_first_pattern(r"inditex\.iStoreId\s*=\s*(\d+)", page_source)
        or _find_first_pattern(r'"storeId"\s*:\s*\["?(\d+)"?\]', page_source)
    )
    catalog_id = _find_first_pattern(r"inditex\.iCatalogId\s*=\s*(\d+)", page_source)
    language_id = _find_first_pattern(r"inditex\.iLangId\s*=\s*(-?\d+)", page_source)

    if not all((product_id, store_id, catalog_id, language_id)):
        return None

    return {
        "origin": f"{urlparse(current_url).scheme}://{urlparse(current_url).netloc}",
        "product_id": str(product_id),
        "store_id": str(store_id),
        "catalog_id": str(catalog_id),
        "language_id": str(language_id),
    }


def _append_composition_item(chunks: list[str], item: Any) -> None:
    """Append a parser-friendly composition item if it has name and percentage."""
    if not isinstance(item, dict):
        return

    name = str(item.get("name", "")).strip()
    percentage = str(item.get("percentage") or item.get("description") or "").strip().rstrip("%")
    if not name or not percentage:
        return

    try:
        if int(float(percentage)) <= 0:
            return
    except ValueError:
        pass

    chunks.append(f"{percentage}% {name}")


def composition_from_inditex_payload(payload: dict[str, Any]) -> str:
    """Convert Inditex product detail JSON composition into parser-friendly text."""
    detail = payload.get("detail")
    if not isinstance(detail, dict):
        return ""

    chunks: list[str] = []

    composition_entries = detail.get("composition")
    if isinstance(composition_entries, list):
        for entry in composition_entries:
            if not isinstance(entry, dict):
                continue
            for item in entry.get("composition", []):
                _append_composition_item(chunks, item)

    if not chunks:
        zone_entries = detail.get("compositionByZone")
        if isinstance(zone_entries, list):
            preferred_zone_chunks: list[str] = []
            fallback_zone_chunks: list[str] = []

            for entry in zone_entries:
                if not isinstance(entry, dict):
                    continue
                for zone in entry.get("zones", []):
                    if not isinstance(zone, dict):
                        continue

                    zone_name = str(zone.get("zoneName", "")).lower()
                    target_chunks = preferred_zone_chunks if "ana kuma" in zone_name or "main" in zone_name else fallback_zone_chunks
                    before_count = len(chunks)
                    for item in zone.get("composition", []):
                        _append_composition_item(chunks, item)
                    target_chunks.extend(chunks[before_count:])
                    del chunks[before_count:]

            chunks.extend(preferred_zone_chunks or fallback_zone_chunks)

    return "\n".join(dict.fromkeys(chunks))


def composition_from_inditex_response_text(response_text: str) -> str:
    """Extract product-level composition directly from an Inditex JSON response string."""
    composition_index = response_text.find('"composition":[')
    if composition_index == -1:
        return ""

    composition_by_zone_index = response_text.find('"compositionByZone"', composition_index)
    composition_text = response_text[
        composition_index: composition_by_zone_index if composition_by_zone_index != -1 else composition_index + 4000
    ]
    chunks: list[str] = []

    for match in re.finditer(
        r'"name"\s*:\s*"(?P<name>[^"]+)"[^{}]*?"(?:percentage|description)"\s*:\s*"(?P<percentage>[^"]+)"',
        composition_text,
    ):
        _append_composition_item(chunks, {"name": match.group("name"), "percentage": match.group("percentage")})

    return "\n".join(dict.fromkeys(chunks))


def fetch_inditex_composition_text(driver: Any) -> str:
    """Fetch Inditex product detail JSON through the active browser session."""
    context = extract_inditex_context(driver.page_source, driver.current_url)
    if context is None:
        return ""

    api_path = (
        f"/itxrest/2/catalog/store/{context['store_id']}/{context['catalog_id']}"
        f"/category/0/product/{context['product_id']}/detail"
        f"?languageId={context['language_id']}&appId=1"
    )

    script = """
    const url = arguments[0];
    const timeoutMs = arguments[1] * 1000;
    const callback = arguments[arguments.length - 1];
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), timeoutMs);
    fetch(url, {credentials: 'include', signal: controller.signal})
      .then(response => response.text().then(text => callback({status: response.status, text})))
      .catch(error => callback({error: String(error)}))
      .finally(() => clearTimeout(timeout));
    """
    result = driver.execute_async_script(script, api_path, INDITEX_API_TIMEOUT_SECONDS)
    if not isinstance(result, dict) or result.get("status") != 200:
        return ""

    response_text = str(result.get("text", ""))
    composition_text = composition_from_inditex_response_text(response_text)
    if composition_text:
        return composition_text

    try:
        payload = json.loads(response_text)
    except json.JSONDecodeError:
        return ""

    return composition_from_inditex_payload(payload)
