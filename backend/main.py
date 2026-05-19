from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
from email import policy
from email.parser import BytesParser
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from backend.url_parser.dynamic import (
    DynamicScraperBlockedError,
    DynamicScraperNoTextError,
    DynamicScraperTimeoutError,
    DynamicScraperUnavailableError,
)


app = FastAPI(title="FabricIQ Backend")


class UrlRequest(BaseModel):
    """Request body for URL-based product analysis."""

    url: str


FABRIC_DEBUG_KEYWORDS = (
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
    "viskon",
    "naylon",
    "polyamid",
    "yün",
    "wool",
    "akrilik",
)

DEVELOPMENT_ENVIRONMENTS = {"development", "dev", "local"}


def _empty_ocr_result() -> dict[str, str | float]:
    """Return an empty OCR payload."""
    return {
        "raw_text": "",
        "confident_text": "",
        "avg_confidence": 0.0,
    }


def _empty_fabric_result(warning: str | None = None) -> dict[str, object]:
    """Return an empty fabric analysis payload."""
    return {
        "composition": [],
        "total_ratio": 0,
        "is_valid": False,
        "warning": warning,
    }


def _empty_score_result() -> dict[str, int | str]:
    """Return an empty score payload."""
    return {
        "quality_score": 0,
        "grade": "F",
        "natural_ratio": 0,
        "synthetic_ratio": 0,
    }


def _is_debug_enabled() -> bool:
    """Return true when development-only endpoints should be available."""
    return os.getenv("ENVIRONMENT", "development").strip().lower() in DEVELOPMENT_ENVIRONMENTS


def _error_response(
    message: str,
    status_code: int,
    *,
    code: str,
    detail: str | None = None,
) -> JSONResponse:
    """Build a structured error response."""
    return JSONResponse(
        status_code=status_code,
        content={
            "success": False,
            "ocr": _empty_ocr_result(),
            "fabric": _empty_fabric_result(warning=message),
            "score": _empty_score_result(),
            "advice": None,
            "error": {
                "code": code,
                "message": message,
                "detail": detail,
            },
        },
    )


def _debug_disabled_response() -> JSONResponse:
    """Return a not-found response when debug endpoints are disabled."""
    return JSONResponse(
        status_code=404,
        content={
            "success": False,
            "error": {
                "code": "debug_disabled",
                "message": "Debug endpoints are disabled.",
            },
        },
    )


def _extract_uploaded_file(request_body: bytes, content_type: str) -> tuple[str, bytes] | None:
    """Extract the uploaded file name and bytes from a multipart request body."""
    message = BytesParser(policy=policy.default).parsebytes(
        f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode("utf-8") + request_body
    )

    if not message.is_multipart():
        return None

    for part in message.iter_parts():
        if part.get_param("name", header="content-disposition") != "file":
            continue

        filename = part.get_filename()
        payload = part.get_payload(decode=True) or b""
        if not filename:
            return None
        return filename, payload

    return None


def _debug_relevant_lines(text: str) -> list[str]:
    """Return compact fabric-related lines from scraper debug text."""
    lines: list[str] = []

    for raw_line in text.splitlines():
        line = " ".join(raw_line.split())
        if not line:
            continue

        lower_line = line.lower()
        if "%" in line or any(keyword in lower_line for keyword in FABRIC_DEBUG_KEYWORDS):
            lines.append(line)

    return list(dict.fromkeys(lines))[:40]


@app.get("/health")
async def health() -> dict[str, str]:
    """Return the service health status."""
    return {"status": "ok"}


@app.get("/debug/runtime")
async def debug_runtime() -> object:
    """Return runtime diagnostics for local development."""
    if not _is_debug_enabled():
        return _debug_disabled_response()

    return {
        "python_executable": sys.executable,
        "python_version": sys.version,
        "main_file": __file__,
        "cwd": str(Path.cwd()),
        "playwright_available": importlib.util.find_spec("playwright") is not None,
        "selenium_available": importlib.util.find_spec("selenium") is not None,
        "webdriver_manager_available": importlib.util.find_spec("webdriver_manager") is not None,
    }


@app.post("/debug/url-text", response_model=None)
async def debug_url_text(request: UrlRequest) -> object:
    """Return scraper text diagnostics for a product URL."""
    if not _is_debug_enabled():
        return _debug_disabled_response()

    try:
        from anyio.to_thread import run_sync
        from backend.ocr.fabric_parser import parse_fabric_composition
        from backend.url_parser.selenium_dynamic import inspect_selenium_page

        diagnostics = await run_sync(inspect_selenium_page, request.url)
        if "error_type" in diagnostics:
            return JSONResponse(
                status_code=500,
                content={
                    "success": False,
                    "url": request.url,
                    "error": diagnostics,
                },
            )

        scraped_text = str(diagnostics.get("body_text", ""))
        lower_text = scraped_text.lower()
        matched_keywords = [
            keyword for keyword in FABRIC_DEBUG_KEYWORDS if keyword in lower_text
        ]
        inditex_composition_text = str(diagnostics.get("inditex_composition_text", ""))
        parser_input = inditex_composition_text or scraped_text
        parsed_composition = parse_fabric_composition(parser_input)

        return {
            "success": True,
            "url": request.url,
            "current_url": diagnostics.get("current_url"),
            "title": diagnostics.get("title"),
            "is_blocked": diagnostics.get("is_blocked"),
            "text_length": len(scraped_text),
            "contains_fabric_keyword": bool(matched_keywords),
            "matched_keywords": matched_keywords,
            "inditex_composition_text": inditex_composition_text,
            "parsed_composition": parsed_composition,
            "relevant_lines": _debug_relevant_lines(parser_input),
            "text_preview": scraped_text[:5000],
        }
    except Exception as exc:
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "url": request.url,
                "error": {
                    "code": "debug_failed",
                    "message": "URL text debug failed",
                    "type": type(exc).__name__,
                    "module": type(exc).__module__,
                    "detail": repr(exc),
                },
            },
        )


@app.post("/analyze/label", response_model=None)
async def analyze_label(request: Request) -> object:
    """Analyze an uploaded clothing label image end-to-end."""
    content_type = request.headers.get("content-type", "")
    request_body = await request.body()
    uploaded_file = _extract_uploaded_file(request_body, content_type)

    if uploaded_file is None:
        return _error_response("No file was provided.", status_code=400, code="missing_file")

    filename, file_bytes = uploaded_file
    suffix = Path(filename).suffix or ".img"
    temp_path: str | None = None

    try:
        from backend.ocr.engine import extract_text_from_image
        from backend.ocr.fabric_parser import parse_fabric_composition
        from backend.ocr.preprocessor import preprocess_image
        from backend.scoring.quality_score import calculate_quality_score

        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
            temp_file.write(file_bytes)
            temp_path = temp_file.name

        processed_image = preprocess_image(temp_path)
        ocr_result = extract_text_from_image(processed_image)
        text_to_parse = ocr_result["raw_text"] or ocr_result["confident_text"]
        fabric_result = parse_fabric_composition(str(text_to_parse))
        score_result = calculate_quality_score(fabric_result["composition"])

        return {
            "success": True,
            "ocr": ocr_result,
            "fabric": fabric_result,
            "score": score_result,
            "advice": None,
        }
    except FileNotFoundError as exc:
        return _error_response(str(exc), status_code=404, code="file_not_found", detail=str(exc))
    except ValueError as exc:
        return _error_response(str(exc), status_code=400, code="bad_request", detail=str(exc))
    except Exception as exc:
        return _error_response(
            "Label analysis failed",
            status_code=500,
            code="label_analysis_failed",
            detail=f"{type(exc).__name__}: {exc}",
        )
    finally:
        if temp_path:
            temp_file_path = Path(temp_path)
            if temp_file_path.exists():
                temp_file_path.unlink()


@app.post("/analyze/url", response_model=None)
async def analyze_url(request: UrlRequest) -> object:
    """Analyze an e-commerce product URL end-to-end."""
    try:
        from anyio.to_thread import run_sync
        from backend.ocr.fabric_parser import parse_fabric_composition
        from backend.scoring.quality_score import calculate_quality_score
        from backend.url_parser.extractor import extract_fabric_text

        scraped_text = await run_sync(extract_fabric_text, request.url)
        fabric_result = parse_fabric_composition(scraped_text)
        score_result = calculate_quality_score(fabric_result["composition"])

        return {
            "success": True,
            "ocr": _empty_ocr_result(),
            "fabric": fabric_result,
            "score": score_result,
            "advice": None,
        }
    except DynamicScraperBlockedError:
        return JSONResponse(
            status_code=403,
            content={
                "success": False,
                "error": {
                    "code": "site_blocked",
                    "message": "Page blocked browser-based scraping",
                    "source": "browser",
                },
            },
        )
    except DynamicScraperTimeoutError as exc:
        return JSONResponse(
            status_code=504,
            content={
                "success": False,
                "error": {
                    "code": "dynamic_timeout",
                    "message": "Dynamic page timed out",
                    "detail": str(exc),
                },
            },
        )
    except DynamicScraperNoTextError as exc:
        return JSONResponse(
            status_code=422,
            content={
                "success": False,
                "error": {
                    "code": "no_fabric_text",
                    "message": "No fabric text found on rendered page",
                    "detail": str(exc),
                },
            },
        )
    except DynamicScraperUnavailableError as exc:
        return JSONResponse(
            status_code=503,
            content={
                "success": False,
                "error": {
                    "code": "dynamic_runtime_unavailable",
                    "message": "Dynamic scraper runtime unavailable",
                    "detail": str(exc),
                },
            },
        )
    except ValueError as exc:
        return _error_response(str(exc), status_code=400, code="bad_request", detail=str(exc))
    except Exception as exc:
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "ocr": _empty_ocr_result(),
                "fabric": _empty_fabric_result(warning="URL analysis failed"),
                "score": _empty_score_result(),
                "advice": None,
                "error": {
                    "code": "url_analysis_failed",
                    "message": "URL analysis failed",
                    "type": type(exc).__name__,
                    "module": type(exc).__module__,
                    "detail": repr(exc),
                },
            },
        )
