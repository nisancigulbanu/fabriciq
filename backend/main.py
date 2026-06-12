from __future__ import annotations

import importlib.util
import importlib
import logging
import os
import sys
import tempfile
import time
from email import policy
from email.parser import BytesParser
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend.url_parser.dynamic import (
    DynamicScraperBlockedError,
    DynamicScraperNoTextError,
    DynamicScraperTimeoutError,
    DynamicScraperUnavailableError,
)


BASE_DIR = Path(__file__).resolve().parent
WEB_DIR = BASE_DIR / "web"
FRAMES_DIR = BASE_DIR / "forweb01"
logger = logging.getLogger("uvicorn.error")

app = FastAPI(title="FabricIQ Backend")
app.mount("/assets", StaticFiles(directory=WEB_DIR), name="assets")
app.mount("/frames", StaticFiles(directory=FRAMES_DIR), name="frames")


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
LOW_OCR_CONFIDENCE_THRESHOLD = 45.0
LABEL_OCR_TIME_BUDGET_SECONDS = 35.0
LABEL_CAPTURE_ADVICE = (
    "Etiketi daha aydinlik, parlama yapmayacak sekilde ve duz aciyla cekin. "
    "Yazi net gorunmeli, etiket kirisik olmamali ve kadraji mumkun oldugunca doldurmali."
)
NO_FABRIC_MESSAGE = (
    "Bu urun icin kumas bilesimi bulunamadi. Daha net etiket fotografi yukleyebilir "
    "veya urun aciklamasinda kumas bilgisinin yer aldigi bir link verebilirsiniz."
)
URL_FABRIC_NOT_FOUND_MESSAGE = (
    "Bu urun sayfasindan kumas bilgisi otomatik alinamadi. Etiket fotografi yukleyebilirsiniz."
)


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
        "confidence_score": 0.0,
        "confidence_label": "low",
        "warnings": [warning] if warning else [],
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
            "source": None,
            "raw_text": "",
            "composition": [],
            "confidence_score": 0.0,
            "confidence_label": "low",
            "warnings": [message],
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


def _build_label_advice(
    ocr_result: dict[str, object],
    fabric_result: dict[str, object],
) -> str | None:
    """Return capture guidance only when label composition cannot be trusted."""
    has_text = bool(str(ocr_result.get("raw_text") or ocr_result.get("confident_text") or "").strip())
    has_composition = bool(fabric_result.get("composition"))
    is_valid = bool(fabric_result.get("is_valid"))

    confidence = float(ocr_result.get("avg_confidence") or 0.0)

    if not has_text or not has_composition or not is_valid or confidence < LOW_OCR_CONFIDENCE_THRESHOLD:
        return LABEL_CAPTURE_ADVICE

    return None


def _confidence_label(score: float) -> str:
    """Return a compact confidence label for public responses."""
    if score >= 0.75:
        return "high"
    if score >= 0.45:
        return "medium"
    return "low"


def _composition_signature(composition: object) -> tuple[tuple[str, float], ...]:
    """Return a stable signature for comparing parsed composition candidates."""
    if not isinstance(composition, list):
        return ()
    entries: list[tuple[str, float]] = []
    for item in composition:
        if not isinstance(item, dict):
            continue
        try:
            entries.append((str(item.get("fabric") or ""), float(item.get("ratio") or 0)))
        except (TypeError, ValueError):
            continue
    return tuple(sorted(entries))


def _score_if_valid(
    fabric_result: dict[str, object],
    calculate_quality_score: object,
) -> dict[str, int | str]:
    """Calculate quality only for trusted fabric compositions."""
    if not fabric_result.get("is_valid") or not fabric_result.get("composition"):
        return _empty_score_result()
    return calculate_quality_score(fabric_result["composition"])  # type: ignore[operator]


def _build_public_analysis_fields(
    *,
    source: str,
    raw_text: str,
    fabric_result: dict[str, object],
    ocr_result: dict[str, object] | None = None,
    agreement_count: int = 1,
) -> dict[str, object]:
    """Build new flat response fields while keeping legacy nested fields."""
    parser_confidence = float(fabric_result.get("confidence_score") or 0.0)
    confidence_score = parser_confidence
    if ocr_result is not None:
        ocr_confidence = max(0.0, min(1.0, float(ocr_result.get("avg_confidence") or 0.0) / 100.0))
        confidence_score = (parser_confidence * 0.65) + (ocr_confidence * 0.25)
        if agreement_count > 1:
            confidence_score += min(0.1, 0.04 * (agreement_count - 1))
    confidence_score = round(max(0.0, min(1.0, confidence_score)), 2)

    warnings = list(fabric_result.get("warnings") or [])
    if not fabric_result.get("composition") and NO_FABRIC_MESSAGE not in warnings:
        warnings.append(NO_FABRIC_MESSAGE)

    return {
        "source": source,
        "raw_text": raw_text,
        "composition": fabric_result.get("composition") or [],
        "confidence_score": confidence_score,
        "confidence_label": _confidence_label(confidence_score),
        "warnings": warnings,
    }


def _label_candidate_rank(
    ocr_result: dict[str, object],
    fabric_result: dict[str, object],
) -> tuple[int, int, float, float, int]:
    """Rank OCR candidates by parse quality first, OCR confidence second."""
    composition = fabric_result.get("composition") or []
    total_ratio = float(fabric_result.get("total_ratio") or 0)
    confidence = float(ocr_result.get("avg_confidence") or 0.0)
    raw_text = str(ocr_result.get("raw_text") or "")
    total_closeness = max(0.0, 100.0 - abs(100.0 - total_ratio))

    return (
        int(bool(fabric_result.get("is_valid"))),
        len(composition) if isinstance(composition, list) else 0,
        total_closeness,
        confidence,
        len(raw_text),
    )


def _is_confident_complete_label_result(
    ocr_result: dict[str, object],
    fabric_result: dict[str, object],
) -> bool:
    """Return true when OCR found a complete enough label result to stop searching."""
    if not fabric_result.get("is_valid"):
        return False

    confidence = float(ocr_result.get("avg_confidence") or 0.0)
    parser_confidence = float(fabric_result.get("confidence_score") or 0.0)
    if confidence < LOW_OCR_CONFIDENCE_THRESHOLD and parser_confidence < 0.8:
        return False

    total_ratio = float(fabric_result.get("raw_total_ratio") or fabric_result.get("total_ratio") or 0.0)
    if abs(100.0 - total_ratio) > 0.5:
        return False

    return True


LABEL_UPLOAD_OPENAPI_EXTRA = {
    "requestBody": {
        "content": {
            "multipart/form-data": {
                "schema": {
                    "type": "object",
                    "properties": {
                        "file": {
                            "type": "string",
                            "format": "binary",
                        }
                    },
                    "required": ["file"],
                }
            }
        },
        "required": True,
    }
}


def _save_uploaded_file(uploaded_file: tuple[str, bytes]) -> tuple[str, str]:
    """Persist uploaded bytes temporarily and return suffix plus path."""
    filename, file_bytes = uploaded_file
    suffix = Path(filename).suffix or ".img"

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
        temp_file.write(file_bytes)
        return suffix, temp_file.name


@app.get("/health")
async def health() -> dict[str, str]:
    """Return the service health status."""
    return {"status": "ok"}


@app.get("/", response_class=FileResponse)
async def web_app() -> FileResponse:
    """Serve the local FabricIQ web interface."""
    return FileResponse(WEB_DIR / "index.html")


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


@app.post("/debug/label-ocr", response_model=None, openapi_extra=LABEL_UPLOAD_OPENAPI_EXTRA)
async def debug_label_ocr(request: Request) -> object:
    """Return OCR diagnostics for each label preprocessing variant."""
    if not _is_debug_enabled():
        return _debug_disabled_response()

    content_type = request.headers.get("content-type", "")
    request_body = await request.body()
    uploaded_file = _extract_uploaded_file(request_body, content_type)

    if uploaded_file is None:
        return _error_response("No file was provided.", status_code=400, code="missing_file")

    temp_path: str | None = None

    try:
        from anyio.to_thread import run_sync
        from backend.ocr.engine import extract_text_from_image as run_easyocr
        from backend.ocr.engine_paddle import run_paddleocr
        from backend.ocr.fabric_parser import parse_fabric_composition
        from backend.ocr.preprocessor import preprocess_image_variants

        _, temp_path = _save_uploaded_file(uploaded_file)

        def inspect_variants() -> list[dict[str, object]]:
            diagnostics: list[dict[str, object]] = []

            ocr_engines = (
                ("easyocr", run_easyocr),
                ("paddleocr", run_paddleocr),
            )

            for variant_name, processed_image in preprocess_image_variants(temp_path, exhaustive=True):
                for engine_name, run_ocr in ocr_engines:
                    started_at = time.perf_counter()
                    ocr_result = run_ocr(processed_image)
                    elapsed_ms = round((time.perf_counter() - started_at) * 1000, 1)
                    parser_input = ocr_result["raw_text"] or ocr_result["confident_text"]
                    fabric_result = parse_fabric_composition(str(parser_input))
                    diagnostics.append(
                        {
                            "engine": engine_name,
                            "variant": variant_name,
                            "elapsed_ms": elapsed_ms,
                            "rank": _label_candidate_rank(ocr_result, fabric_result),
                            "ocr": ocr_result,
                            "fabric": fabric_result,
                        }
                    )

            return diagnostics

        variants = await run_sync(inspect_variants)
        sorted_variants = sorted(variants, key=lambda item: tuple(item["rank"]), reverse=True)

        return {
            "success": True,
            "variant_count": len(variants),
            "best_variant": sorted_variants[0] if sorted_variants else None,
            "variants": variants,
        }
    except Exception as exc:
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": {
                    "code": "label_ocr_debug_failed",
                    "message": "Label OCR debug failed",
                    "type": type(exc).__name__,
                    "module": type(exc).__module__,
                    "detail": repr(exc),
                },
            },
        )
    finally:
        if temp_path:
            temp_file_path = Path(temp_path)
            if temp_file_path.exists():
                temp_file_path.unlink()


@app.post("/analyze/label", response_model=None, openapi_extra=LABEL_UPLOAD_OPENAPI_EXTRA)
async def analyze_label(request: Request) -> object:
    """Analyze an uploaded clothing label image end-to-end."""
    content_type = request.headers.get("content-type", "")
    request_body = await request.body()
    uploaded_file = _extract_uploaded_file(request_body, content_type)

    if uploaded_file is None:
        return _error_response("No file was provided.", status_code=400, code="missing_file")

    temp_path: str | None = None

    try:
        from backend.ocr.engine import extract_text_from_image as run_easyocr
        try:
            from backend.ocr.engine import run_lmstudio_ocr_from_path
        except ImportError:
            run_lmstudio_ocr_from_path = lambda image_path: None
        from backend.ocr.engine_paddle import run_paddleocr
        from backend.ocr.fabric_parser import parse_fabric_composition
        from backend.ocr.preprocessor import preprocess_image_variants
        from backend.scoring.quality_score import calculate_quality_score

        _, temp_path = _save_uploaded_file(uploaded_file)

        best_result: tuple[
            tuple[int, int, float, float, int],
            dict[str, str | float],
            dict[str, object],
            dict[str, int | str],
        ] | None = None
        candidate_results: list[
            tuple[
                tuple[int, int, float, float, int],
                dict[str, str | float],
                dict[str, object],
                dict[str, int | str],
            ]
        ] = []

        analysis_started_at = time.perf_counter()
        timed_out = False
        lmstudio_result = run_lmstudio_ocr_from_path(temp_path)
        if lmstudio_result is not None:
            text_to_parse = lmstudio_result["raw_text"] or lmstudio_result["confident_text"]
            logger.info("Label LM Studio original-image text sent to parser: %s", str(text_to_parse or "")[:500])
            fabric_result = parse_fabric_composition(str(text_to_parse)) if text_to_parse else _empty_fabric_result(
                warning="Fabric composition could not be extracted from the provided text."
            )
            logger.info(
                "Label LM Studio parser result: composition_count=%s is_valid=%s total=%s warning=%s",
                len(fabric_result.get("composition") or []),
                fabric_result.get("is_valid"),
                fabric_result.get("total_ratio"),
                fabric_result.get("warning"),
            )
            score_result = _score_if_valid(fabric_result, calculate_quality_score)
            candidate_results.append(
                (
                    _label_candidate_rank(lmstudio_result, fabric_result),
                    lmstudio_result,
                    fabric_result,
                    score_result,
                )
            )
            best_result = candidate_results[-1]

        for _, processed_image in preprocess_image_variants(temp_path):
            if best_result is not None and time.perf_counter() - analysis_started_at > LABEL_OCR_TIME_BUDGET_SECONDS:
                timed_out = True
                break

            should_stop = False
            easyocr_result = run_easyocr(processed_image)
            ocr_results = [easyocr_result]
            if (
                not str(easyocr_result.get("raw_text") or easyocr_result.get("confident_text") or "").strip()
                or float(easyocr_result.get("avg_confidence") or 0.0) < 20.0
            ):
                ocr_results.append(run_paddleocr(processed_image))

            for ocr_result in ocr_results:
                text_to_parse = ocr_result["raw_text"] or ocr_result["confident_text"]
                logger.info("Label OCR text sent to parser: %s", str(text_to_parse or "")[:500])
                if text_to_parse:
                    fabric_result = parse_fabric_composition(str(text_to_parse))
                else:
                    fabric_result = _empty_fabric_result(
                        warning="Fabric composition could not be extracted from the provided text."
                    )
                logger.info(
                    "Label parser result: composition_count=%s is_valid=%s total=%s warning=%s",
                    len(fabric_result.get("composition") or []),
                    fabric_result.get("is_valid"),
                    fabric_result.get("total_ratio"),
                    fabric_result.get("warning"),
                )
                score_result = _score_if_valid(fabric_result, calculate_quality_score)
                candidate = (
                    _label_candidate_rank(ocr_result, fabric_result),
                    ocr_result,
                    fabric_result,
                    score_result,
                )
                candidate_results.append(candidate)

                if best_result is None or candidate[0] > best_result[0]:
                    best_result = candidate

                if _is_confident_complete_label_result(ocr_result, fabric_result):
                    should_stop = True

            if should_stop:
                break

        if best_result is None:
            raise ValueError("No OCR preprocessing variants were generated.")

        merged_composition_text = " ".join(
            f"{item['ratio']}% {item['fabric']}"
            for _, _, fabric_result, _ in candidate_results
            for item in fabric_result.get("composition", [])
            if isinstance(item, dict) and item.get("fabric") and item.get("ratio") is not None
        )
        if merged_composition_text:
            merged_by_fabric: dict[str, float] = {}
            merged_order: list[str] = []
            for _, _, candidate_fabric_result, _ in candidate_results:
                merge_items = candidate_fabric_result.get("raw_composition") or candidate_fabric_result.get("composition", [])
                for item in merge_items:
                    if not isinstance(item, dict) or not item.get("fabric"):
                        continue
                    fabric_name = str(item["fabric"])
                    try:
                        ratio_value = float(item.get("ratio") or 0)
                    except (TypeError, ValueError):
                        continue
                    if fabric_name not in merged_by_fabric:
                        merged_order.append(fabric_name)
                    merged_by_fabric[fabric_name] = max(merged_by_fabric.get(fabric_name, 0.0), ratio_value)

            merged_total = sum(merged_by_fabric.values())
            if 95 <= merged_total <= 105:
                merged_fabric_result = {
                    "composition": [
                        {
                            "fabric": fabric_name,
                            "ratio": int(ratio) if ratio.is_integer() else round(ratio, 2),
                        }
                        for fabric_name in merged_order
                        for ratio in [merged_by_fabric[fabric_name]]
                    ],
                    "total_ratio": int(merged_total) if merged_total.is_integer() else round(merged_total, 2),
                    "raw_total_ratio": int(merged_total) if merged_total.is_integer() else round(merged_total, 2),
                    "is_valid": True,
                    "warning": None,
                    "confidence_score": 0.9,
                    "confidence_label": "high",
                    "warnings": [],
                }
            else:
                merged_fabric_result = parse_fabric_composition(merged_composition_text)
            if merged_fabric_result.get("composition"):
                merged_ocr_result: dict[str, str | float] = {
                    "raw_text": " ".join(
                        str(ocr_result.get("raw_text") or "")
                        for _, ocr_result, _, _ in candidate_results
                        if ocr_result.get("raw_text")
                    ),
                    "confident_text": " ".join(
                        str(ocr_result.get("confident_text") or "")
                        for _, ocr_result, _, _ in candidate_results
                        if ocr_result.get("confident_text")
                    ),
                    "avg_confidence": round(
                        max(float(ocr_result.get("avg_confidence") or 0.0) for _, ocr_result, _, _ in candidate_results),
                        2,
                    ),
                }
                merged_score_result = _score_if_valid(merged_fabric_result, calculate_quality_score)
                merged_candidate = (
                    _label_candidate_rank(merged_ocr_result, merged_fabric_result),
                    merged_ocr_result,
                    merged_fabric_result,
                    merged_score_result,
                )
                if merged_candidate[0] > best_result[0]:
                    best_result = merged_candidate

        _, ocr_result, fabric_result, score_result = best_result
        advice = _build_label_advice(ocr_result, fabric_result)
        if timed_out and advice is None:
            advice = LABEL_CAPTURE_ADVICE
        if not fabric_result.get("composition"):
            advice = NO_FABRIC_MESSAGE

        best_signature = _composition_signature(fabric_result.get("composition"))
        agreement_count = sum(
            1
            for _, _, candidate_fabric, _ in candidate_results
            if best_signature and _composition_signature(candidate_fabric.get("composition")) == best_signature
        )
        public_fields = _build_public_analysis_fields(
            source="ocr",
            raw_text=str(ocr_result.get("raw_text") or ocr_result.get("confident_text") or ""),
            fabric_result=fabric_result,
            ocr_result=ocr_result,
            agreement_count=agreement_count,
        )

        return {
            "success": bool(fabric_result.get("composition") and fabric_result.get("is_valid")),
            "ocr": ocr_result,
            "fabric": fabric_result,
            "score": score_result,
            "advice": advice,
            **public_fields,
        }
    except FileNotFoundError as exc:
        return _error_response(str(exc), status_code=404, code="file_not_found", detail=str(exc))
    except ValueError as exc:
        return _error_response(str(exc), status_code=400, code="bad_request", detail=str(exc))
    except Exception as exc:
        return _error_response(
            "Etiket net okunamadi. Daha yakin ve isikli bir fotograf yukleyin.",
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
        extractor = importlib.import_module("backend.url_parser.extractor")

        if hasattr(extractor, "extract_fabric_data"):
            extraction = await run_sync(extractor.extract_fabric_data, request.url)
        else:
            scraped_text_fallback = await run_sync(extractor.extract_fabric_text, request.url)
            extraction = {
                "success": True,
                "source": "url",
                "url": request.url,
                "raw_text": scraped_text_fallback,
                "fabric_candidates": [],
                "price": None,
                "warnings": [],
                "error": None,
            }
        scraped_text = str(extraction.get("raw_text") or "")
        fabric_result = parse_fabric_composition(scraped_text)
        score_result = _score_if_valid(fabric_result, calculate_quality_score)
        if not fabric_result.get("composition") or not fabric_result.get("is_valid"):
            return JSONResponse(
                status_code=422,
                content={
                    "success": False,
                    "ocr": _empty_ocr_result(),
                    "fabric": fabric_result,
                    "score": _empty_score_result(),
                    "advice": URL_FABRIC_NOT_FOUND_MESSAGE,
                    "source": extraction.get("source") or "url",
                    "url": request.url,
                    "raw_text": scraped_text,
                    "fabric_candidates": extraction.get("fabric_candidates") or [],
                    "price": extraction.get("price"),
                    "composition": [],
                    "confidence_score": 0.0,
                    "confidence_label": "low",
                    "warnings": [URL_FABRIC_NOT_FOUND_MESSAGE],
                    "error": "fabric_info_not_found",
                },
            )
        public_fields = _build_public_analysis_fields(
            source=str(extraction.get("source") or "url"),
            raw_text=scraped_text,
            fabric_result=fabric_result,
        )

        return {
            "success": True,
            "ocr": _empty_ocr_result(),
            "fabric": fabric_result,
            "score": score_result,
            "advice": None,
            "url": request.url,
            "fabric_candidates": extraction.get("fabric_candidates") or [],
            "price": extraction.get("price"),
            "error": None,
            **public_fields,
        }
    except DynamicScraperBlockedError:
        return JSONResponse(
            status_code=403,
            content={
                "success": False,
                "error": {
                    "code": "site_blocked",
                    "message": "Bu urun sayfasi otomatik okunamadi. Etiket fotografi ile tekrar deneyebilirsiniz.",
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
                    "message": "Bu urun sayfasi otomatik okunamadi. Etiket fotografi ile tekrar deneyebilirsiniz.",
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
                    "message": URL_FABRIC_NOT_FOUND_MESSAGE,
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
                    "message": "Bu urun sayfasi otomatik okunamadi. Etiket fotografi ile tekrar deneyebilirsiniz.",
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
                "fabric": _empty_fabric_result(warning=URL_FABRIC_NOT_FOUND_MESSAGE),
                "score": _empty_score_result(),
                "advice": URL_FABRIC_NOT_FOUND_MESSAGE,
                "source": "url",
                "url": request.url,
                "raw_text": "",
                "fabric_candidates": [],
                "composition": [],
                "confidence_score": 0.0,
                "confidence_label": "low",
                "warnings": [URL_FABRIC_NOT_FOUND_MESSAGE],
                "error": {
                    "code": "url_analysis_failed",
                    "message": "Bu urun sayfasi otomatik okunamadi. Etiket fotografi ile tekrar deneyebilirsiniz.",
                    "type": type(exc).__name__,
                    "module": type(exc).__module__,
                    "detail": repr(exc),
                },
            },
        )
