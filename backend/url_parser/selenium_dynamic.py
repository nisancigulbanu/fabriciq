"""Selenium fallback scraper for dynamic product pages."""

from __future__ import annotations

import time
from typing import Any

from .adapters.inditex import fetch_inditex_composition_text
from .detector import USER_AGENT
from .dynamic import DynamicScraperBlockedError, DynamicScraperNoTextError, DynamicScraperUnavailableError
from .static import _extract_fabric_fragments, _extract_price_from_text


SELENIUM_WAIT_SECONDS = 5


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
    options.page_load_strategy = "eager"
    options.add_argument(f"--user-agent={USER_AGENT}")
    options.add_argument("--window-size=1366,900")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--no-sandbox")
    options.add_argument("--lang=tr-TR")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    return options


def _load_page(driver: Any, url: str) -> None:
    """Load a page and continue with the available DOM if rendering times out."""
    try:
        driver.get(url)
    except Exception as exc:
        error_text = f"{type(exc).__name__}: {exc}".lower()
        if "timeout" not in error_text and "timed out" not in error_text:
            raise
        try:
            driver.execute_script("window.stop();")
        except Exception:
            pass


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
        _load_page(driver, url)
        time.sleep(SELENIUM_WAIT_SECONDS)

        body_text = driver.execute_script("return document.body ? document.body.innerText : ''") or ""
        page_title = driver.title
        current_url = driver.current_url
        lower_body_text = body_text.lower()
        is_blocked = "access denied" in lower_body_text or "permission to access" in lower_body_text
        inditex_composition_text = fetch_inditex_composition_text(driver)

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
    return str(extract_selenium_data(url)["raw_text"])


def extract_selenium_data(url: str) -> dict[str, object]:
    """Render a product page with Selenium Chrome and return fabric text plus price."""
    driver = None
    webdriver_error: type[Exception] = Exception

    try:
        driver, webdriver_error = _open_driver()
        driver.set_page_load_timeout(25)
        _load_page(driver, url)
        time.sleep(SELENIUM_WAIT_SECONDS)

        body_text = driver.execute_script("return document.body ? document.body.innerText : ''") or ""
        price = _extract_price_from_text(body_text, source="selenium")
        lower_body_text = body_text.lower()
        if "access denied" in lower_body_text or "permission to access" in lower_body_text:
            raise DynamicScraperBlockedError("The page blocked Selenium browser scraping.")

        inditex_composition_text = fetch_inditex_composition_text(driver)
        if inditex_composition_text:
            return {
                "raw_text": inditex_composition_text,
                "price": price,
            }

        filtered_text = "\n".join(dict.fromkeys(_extract_fabric_fragments(body_text)))
        if not filtered_text:
            raise DynamicScraperNoTextError("Selenium rendered page did not contain fabric-oriented text.")

        return {
            "raw_text": filtered_text,
            "price": price,
        }
    except (DynamicScraperBlockedError, DynamicScraperNoTextError, DynamicScraperUnavailableError):
        raise
    except webdriver_error as exc:
        raise DynamicScraperUnavailableError(str(exc)) from exc
    finally:
        if driver is not None:
            driver.quit()
