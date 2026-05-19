"""Dynamic product page scraper using Playwright."""

from __future__ import annotations

from .detector import FABRIC_KEYWORDS, USER_AGENT
from .static import _extract_fabric_fragments


DYNAMIC_TIMEOUT_MS = 20000
POST_LOAD_WAIT_MS = 1500
PRODUCT_HINT_SELECTORS = (
    "[class*='product']",
    "[id*='product']",
    "[class*='detail']",
    "[id*='detail']",
    "[class*='description']",
    "[id*='description']",
    "[class*='material']",
    "[class*='fabric']",
    "[class*='composition']",
    "[class*='kumas']",
    "[class*='materyal']",
    "[class*='icerik']",
)


class DynamicScraperUnavailableError(RuntimeError):
    """Raised when Playwright or its browser runtime is unavailable."""


class DynamicScraperBlockedError(RuntimeError):
    """Raised when a site blocks browser-based scraping."""


class DynamicScraperTimeoutError(RuntimeError):
    """Raised when a dynamic page cannot be loaded in time."""


class DynamicScraperNoTextError(RuntimeError):
    """Raised when rendering succeeds but no fabric-oriented text is found."""


def _import_playwright() -> object:
    """Import Playwright lazily so static URL parsing does not require it."""
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise DynamicScraperUnavailableError(
            "Playwright is not installed. Run `python -m pip install playwright` and "
            "`python -m playwright install chromium`."
        ) from exc

    return sync_playwright, PlaywrightError, PlaywrightTimeoutError


def _contains_fabric_keyword(text: str) -> bool:
    """Return true when a string contains a fabric-related keyword."""
    lower_text = text.lower()
    return any(keyword in lower_text for keyword in FABRIC_KEYWORDS)


def _extract_visible_text(page: object) -> str:
    """Extract fabric-oriented visible text from a rendered browser page."""
    chunks: list[str] = []

    for selector in PRODUCT_HINT_SELECTORS:
        for element in page.locator(selector).all():
            try:
                text = element.inner_text(timeout=1000).strip()
            except Exception:
                continue

            if text and _contains_fabric_keyword(text):
                chunks.extend(_extract_fabric_fragments(text))

    if chunks:
        return "\n".join(dict.fromkeys(chunks))

    body_text = page.locator("body").inner_text(timeout=3000)
    if "access denied" in body_text.lower() or "permission to access" in body_text.lower():
        raise DynamicScraperBlockedError("The page blocked browser-based scraping.")

    filtered_text = "\n".join(dict.fromkeys(_extract_fabric_fragments(body_text)))
    if not filtered_text:
        raise DynamicScraperNoTextError("Rendered page did not contain fabric-oriented text.")

    return filtered_text


def extract_dynamic_text(url: str) -> str:
    """Render a JavaScript-heavy product page and return plain text for fabric parsing."""
    sync_playwright, playwright_error, playwright_timeout_error = _import_playwright()

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                context = browser.new_context(
                    user_agent=USER_AGENT,
                    locale="tr-TR",
                    viewport={"width": 1366, "height": 900},
                )
                page = context.new_page()
                response = page.goto(url, wait_until="domcontentloaded", timeout=DYNAMIC_TIMEOUT_MS)
                if response is not None and response.status in {401, 403, 429}:
                    raise DynamicScraperBlockedError(
                        f"The page blocked browser-based scraping with HTTP {response.status}."
                    )
                try:
                    page.wait_for_load_state("networkidle", timeout=8000)
                except playwright_timeout_error:
                    pass
                page.wait_for_timeout(POST_LOAD_WAIT_MS)
                return _extract_visible_text(page)
            finally:
                browser.close()
    except playwright_timeout_error as exc:
        raise DynamicScraperTimeoutError(str(exc)) from exc
    except playwright_error as exc:
        raise DynamicScraperUnavailableError(str(exc)) from exc
