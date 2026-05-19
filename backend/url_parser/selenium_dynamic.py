"""Selenium fallback scraper for dynamic product pages."""

from __future__ import annotations

import json
import re
import time
from typing import Any
from urllib.parse import urlparse

from .detector import USER_AGENT
from .dynamic import DynamicScraperBlockedError, DynamicScraperNoTextError, DynamicScraperUnavailableError
from .static import _extract_fabric_fragments


SELENIUM_WAIT_SECONDS = 5
INDITEX_API_TIMEOUT_SECONDS = 12


def _import_selenium() -> object:
    """Import Selenium lazily so static URL parsing does not require it."""
    try:
        from selenium import webdriver
        from selenium.common.exceptions import WebDriverException
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.chrome.service import Service
    except ImportError as exc:
        raise DynamicScraperUnavailableError(
            "Selenium fallback is not installed. Run `python -m pip install selenium webdriver-manager`."
        ) from exc

    return webdriver, WebDriverException, Options, Service


def _build_chrome_options(options_class: object) -> object:
    """Build Chrome options for a browser that resembles a normal user session."""
    options = options_class()
    options.add_argument(f"--user-agent={USER_AGENT}")
    options.add_argument("--window-size=1366,900")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--no-sandbox")
    options.add_argument("--lang=tr-TR")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    return options


def _find_first_pattern(pattern: str, text: str) -> str | None:
    """Return the first regex capture group from a text."""
    match = re.search(pattern, text, flags=re.IGNORECASE)
    return match.group(1) if match else None


def _extract_inditex_context(page_source: str, current_url: str) -> dict[str, str] | None:
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


def _composition_from_inditex_payload(payload: dict[str, Any]) -> str:
    """Convert Inditex product detail JSON composition into parser-friendly text."""
    detail = payload.get("detail")
    if not isinstance(detail, dict):
        return ""

    chunks: list[str] = []

    def append_item(item: Any) -> None:
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

    composition_entries = detail.get("composition")
    if isinstance(composition_entries, list):
        for entry in composition_entries:
            if not isinstance(entry, dict):
                continue
            for item in entry.get("composition", []):
                append_item(item)

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
                        append_item(item)
                    target_chunks.extend(chunks[before_count:])
                    del chunks[before_count:]

            chunks.extend(preferred_zone_chunks or fallback_zone_chunks)

    return "\n".join(dict.fromkeys(chunks))


def _composition_from_inditex_response_text(response_text: str) -> str:
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
        name = match.group("name").strip()
        percentage = match.group("percentage").strip().rstrip("%")
        if not name or not percentage:
            continue
        try:
            if int(float(percentage)) <= 0:
                continue
        except ValueError:
            pass
        chunks.append(f"{percentage}% {name}")

    return "\n".join(dict.fromkeys(chunks))


def _fetch_inditex_composition_text(driver: Any) -> str:
    """Fetch Inditex product detail JSON through the active browser session."""
    context = _extract_inditex_context(driver.page_source, driver.current_url)
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
    composition_text = _composition_from_inditex_response_text(response_text)
    if composition_text:
        return composition_text

    try:
        payload = json.loads(response_text)
    except json.JSONDecodeError:
        return ""

    return _composition_from_inditex_payload(payload)


def _open_driver() -> tuple[Any, Any]:
    """Open Chrome with Selenium Manager first and webdriver-manager as fallback."""
    webdriver, webdriver_error, options_class, service_class = _import_selenium()
    options = _build_chrome_options(options_class)

    try:
        return webdriver.Chrome(options=options), webdriver_error
    except Exception:
        try:
            from webdriver_manager.chrome import ChromeDriverManager
        except ImportError as exc:
            raise DynamicScraperUnavailableError(
                "Chrome driver could not be resolved and webdriver-manager is not installed."
            ) from exc

        service = service_class(ChromeDriverManager().install())
        return webdriver.Chrome(service=service, options=options), webdriver_error


def inspect_selenium_page(url: str) -> dict[str, object]:
    """Return raw Selenium page diagnostics without filtering fabric text."""
    driver = None

    try:
        driver, _ = _open_driver()
        driver.set_page_load_timeout(25)
        driver.get(url)
        time.sleep(SELENIUM_WAIT_SECONDS)

        body_text = driver.execute_script("return document.body ? document.body.innerText : ''") or ""
        page_title = driver.title
        current_url = driver.current_url
        lower_body_text = body_text.lower()
        is_blocked = "access denied" in lower_body_text or "permission to access" in lower_body_text
        inditex_composition_text = _fetch_inditex_composition_text(driver)

        return {
            "current_url": current_url,
            "title": page_title,
            "is_blocked": is_blocked,
            "body_length": len(body_text),
            "inditex_composition_text": inditex_composition_text,
            "body_text": body_text,
        }
    except Exception as exc:
        return {
            "error_type": type(exc).__name__,
            "error_module": type(exc).__module__,
            "error_detail": repr(exc),
        }
    finally:
        if driver is not None:
            driver.quit()


def extract_selenium_text(url: str) -> str:
    """Render a product page with Selenium Chrome and return fabric-oriented plain text."""
    driver = None
    webdriver_error: type[Exception] = Exception

    try:
        driver, webdriver_error = _open_driver()
        driver.set_page_load_timeout(25)
        driver.get(url)
        time.sleep(SELENIUM_WAIT_SECONDS)

        body_text = driver.execute_script("return document.body ? document.body.innerText : ''") or ""
        lower_body_text = body_text.lower()
        if "access denied" in lower_body_text or "permission to access" in lower_body_text:
            raise DynamicScraperBlockedError("The page blocked Selenium browser scraping.")

        inditex_composition_text = _fetch_inditex_composition_text(driver)
        if inditex_composition_text:
            return inditex_composition_text

        filtered_text = "\n".join(dict.fromkeys(_extract_fabric_fragments(body_text)))
        if not filtered_text:
            raise DynamicScraperNoTextError("Selenium rendered page did not contain fabric-oriented text.")

        return filtered_text
    except (DynamicScraperBlockedError, DynamicScraperNoTextError, DynamicScraperUnavailableError):
        raise
    except webdriver_error as exc:
        raise DynamicScraperUnavailableError(str(exc)) from exc
    finally:
        if driver is not None:
            driver.quit()
