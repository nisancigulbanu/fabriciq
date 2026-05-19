"""URL parsing utilities for product pages."""

from .dynamic import extract_dynamic_text
from .extractor import extract_fabric_text, extract_text_from_url
from .selenium_dynamic import extract_selenium_text

__all__ = ["extract_dynamic_text", "extract_fabric_text", "extract_selenium_text", "extract_text_from_url"]
