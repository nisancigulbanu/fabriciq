from __future__ import annotations

import tempfile
from email import policy
from email.parser import BytesParser
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel


app = FastAPI(title="FabricIQ Backend")


class UrlRequest(BaseModel):
    """Request body for URL-based product analysis."""

    url: str


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


def _error_response(message: str, status_code: int) -> JSONResponse:
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
                "message": message,
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


@app.get("/health")
async def health() -> dict[str, str]:
    """Return the service health status."""
    return {"status": "ok"}


@app.post("/analyze/label", response_model=None)
async def analyze_label(request: Request) -> object:
    """Analyze an uploaded clothing label image end-to-end."""
    content_type = request.headers.get("content-type", "")
    request_body = await request.body()
    uploaded_file = _extract_uploaded_file(request_body, content_type)

    if uploaded_file is None:
        return _error_response("No file was provided.", status_code=400)

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
        return _error_response(str(exc), status_code=404)
    except ValueError as exc:
        return _error_response(str(exc), status_code=400)
    except Exception as exc:
        return _error_response(f"Label analysis failed: {exc}", status_code=500)
    finally:
        if temp_path:
            temp_file_path = Path(temp_path)
            if temp_file_path.exists():
                temp_file_path.unlink()


@app.post("/analyze/url", response_model=None)
async def analyze_url(request: UrlRequest) -> object:
    """Analyze an e-commerce product URL end-to-end."""
    try:
        from backend.ocr.fabric_parser import parse_fabric_composition
        from backend.scoring.quality_score import calculate_quality_score
        from backend.url_parser.extractor import extract_fabric_text

        scraped_text = extract_fabric_text(request.url)
        fabric_result = parse_fabric_composition(scraped_text)
        score_result = calculate_quality_score(fabric_result["composition"])

        return {
            "success": True,
            "ocr": _empty_ocr_result(),
            "fabric": fabric_result,
            "score": score_result,
            "advice": None,
        }
    except NotImplementedError:
        return JSONResponse(
            status_code=501,
            content={
                "success": False,
                "error": "Dynamic pages not supported yet",
            },
        )
    except ValueError as exc:
        return _error_response(str(exc), status_code=400)
    except Exception as exc:
        return _error_response(f"URL analysis failed: {exc}", status_code=500)
