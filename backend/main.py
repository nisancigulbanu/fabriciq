from __future__ import annotations

import importlib.util
import importlib
import inspect
import json
import logging
import os
import sys
import tempfile
import time
from urllib.parse import unquote, urlparse
from email import policy
from email.parser import BytesParser
from logging.handlers import RotatingFileHandler
from pathlib import Path

import requests
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
LOG_DIR = BASE_DIR.parent / "logs"
logger = logging.getLogger("uvicorn.error")


def _configure_file_logging() -> None:
    """Write backend logs to a local file in addition to uvicorn output."""
    LOG_DIR.mkdir(exist_ok=True)
    log_path = Path(os.getenv("FABRICIQ_LOG_FILE", LOG_DIR / "fabriciq.log"))
    if any(isinstance(handler, RotatingFileHandler) and Path(handler.baseFilename) == log_path for handler in logger.handlers):
        return

    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=1_000_000,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")
    )
    logger.addHandler(file_handler)
    logger.setLevel(logging.INFO)


def _load_env_file() -> None:
    """Load simple KEY=value pairs from .env without overriding existing env vars."""
    for env_path in (BASE_DIR / ".env", BASE_DIR.parent / ".env"):
        if not env_path.exists():
            continue
        for line in env_path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            key = key.strip().lstrip("\ufeff")
            value = value.strip().strip('"').strip("'")
            if not os.environ.get(key):
                os.environ[key] = value


_load_env_file()
_configure_file_logging()

app = FastAPI(title="FabricIQ Backend")
app.mount("/assets", StaticFiles(directory=WEB_DIR), name="assets")
app.mount("/frames", StaticFiles(directory=FRAMES_DIR), name="frames")


class UrlRequest(BaseModel):
    """Request body for URL-based product analysis."""

    url: str


class AssistantRequest(BaseModel):
    """Request body for FabricIQ assistant recommendations."""

    product_name: str | None = None
    price: float | None = None
    fabric_composition: dict[str, float]
    quality_score: int | float | str | None = None
    grade: str | None = None
    natural_ratio: float | None = None
    synthetic_ratio: float | None = None
    scoring_notes: list[str] | None = None
    score_details: dict[str, object] | None = None
    rag_database_notes: str | list[str] | None = None
    question: str | None = None
    model: str | None = None


FABRIC_RAG_KNOWLEDGE = {
    "pamuk": "Pamuk nefes alir, gunluk kullanimda konforludur; ancak bakim ve su tuketimi acisindan dikkatli degerlendirilmelidir.",
    "cotton": "Pamuk nefes alir, gunluk kullanimda konforludur; ancak bakim ve su tuketimi acisindan dikkatli degerlendirilmelidir.",
    "polyester": "Polyester dayanikli ve ucuzdur fakat petrol bazlidir, mikroplastik yayabilir ve sicak havada terletme riski tasir.",
    "viskoz": "Viskoz yumusak ve dokumlu bir liftir; seluloz bazli olsa da uretim sureci kimyasal yogun olabilir.",
    "viscose": "Viskoz yumusak ve dokumlu bir liftir; seluloz bazli olsa da uretim sureci kimyasal yogun olabilir.",
    "elastan": "Elastan esneklik ve rahatlik katar; dusuk oranlarda yararlidir fakat geri donusumu zorlastirabilir.",
    "elastane": "Elastan esneklik ve rahatlik katar; dusuk oranlarda yararlidir fakat geri donusumu zorlastirabilir.",
    "poliamid": "Poliamid dayanikli bir sentetik liftir; uzun omurlu olabilir fakat dogada cozunmesi zordur.",
    "polyamide": "Poliamid dayanikli bir sentetik liftir; uzun omurlu olabilir fakat dogada cozunmesi zordur.",
    "keten": "Keten nefes alan, dayanikli ve daha dusuk su ihtiyaci olan degerli bir dogal liftir.",
    "linen": "Keten nefes alan, dayanikli ve daha dusuk su ihtiyaci olan degerli bir dogal liftir.",
    "yün": "Yun isi dengesi iyi olan dogal bir liftir; kalite ve bakim acisindan avantajlidir.",
    "wool": "Yun isi dengesi iyi olan dogal bir liftir; kalite ve bakim acisindan avantajlidir.",
    "akrilik": "Akrilik yun hissi verebilir ancak sentetiktir, boncuklanma ve mikroplastik riski tasir.",
    "acrylic": "Akrilik yun hissi verebilir ancak sentetiktir, boncuklanma ve mikroplastik riski tasir.",
}

GEMINI_DEFAULT_MODEL = "gemini-3-flash-preview"
PRODUCT_TYPE_CONTEXTS = {
    "general": None,
    "activewear": "activewear spor performans tayt yoga leggings fitness koşu",
    "knitwear": "knitwear kışlık kazak triko hırka sıcak tutma wool knitwear",
    "tshirt_underwear": "tshirt_underwear tişört t-shirt iç giyim underwear atlet cilt konfor",
    "shirt_blouse": "shirt_blouse gömlek bluz shirt blouse döküm nefes alabilirlik",
    "denim": "denim kot jean jeans dayanıklılık",
    "outerwear": "outerwear dış giyim mont ceket kaban su rüzgar dayanıklılık",
    "swimwear": "swimwear mayo bikini yüzme klor tuz suyu esneklik",
    "socks": "socks çorap nem yönetimi sürtünme dayanımı",
    "officewear": "officewear ofis iş kıyafeti takım business",
    "baby_kids": "baby_kids bebek çocuk hassas cilt hipoalerjenik",
    "home_textile": "home_textile ev tekstili çarşaf nevresim",
}
PRODUCT_TYPE_ALIASES = {
    "winter": "knitwear",
    "underwear": "tshirt_underwear",
    "tshirt": "tshirt_underwear",
    "shirt": "shirt_blouse",
    "blouse": "shirt_blouse",
    "swim": "swimwear",
    "sock": "socks",
    "kids": "baby_kids",
    "baby": "baby_kids",
}


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


def _empty_score_result() -> dict[str, object]:
    """Return an empty score payload."""
    return {
        "quality_score": 0,
        "grade": "F",
        "natural_ratio": 0,
        "synthetic_ratio": 0,
        "scoring_notes": [],
        "score_details": {
            "performance_score": 0.0,
            "sustainability_score": 0.0,
            "final_score": 0.0,
            "category": "Yetersiz",
            "product_type": "general",
            "formula_version": "kp_sp_v1",
        },
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


def _extract_multipart_upload(request_body: bytes, content_type: str) -> tuple[tuple[str, bytes] | None, dict[str, str]]:
    """Extract uploaded file and plain form fields from a multipart request body."""
    message = BytesParser(policy=policy.default).parsebytes(
        f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode("utf-8") + request_body
    )

    if not message.is_multipart():
        return None, {}

    uploaded_file: tuple[str, bytes] | None = None
    fields: dict[str, str] = {}
    for part in message.iter_parts():
        field_name = part.get_param("name", header="content-disposition")
        if not field_name:
            continue

        if field_name == "file":
            filename = part.get_filename()
            payload = part.get_payload(decode=True) or b""
            if filename:
                uploaded_file = (filename, payload)
            continue

        payload = part.get_payload(decode=True) or b""
        charset = part.get_content_charset() or "utf-8"
        try:
            fields[str(field_name)] = payload.decode(charset).strip()
        except UnicodeDecodeError:
            fields[str(field_name)] = payload.decode("utf-8", errors="ignore").strip()

    return uploaded_file, fields


def _extract_uploaded_file(request_body: bytes, content_type: str) -> tuple[str, bytes] | None:
    """Extract the uploaded file name and bytes from a multipart request body."""
    uploaded_file, _ = _extract_multipart_upload(request_body, content_type)
    return uploaded_file


def _label_product_context(product_type: str | None) -> str | None:
    """Return scorer context for label OCR based on the selected product type."""
    return PRODUCT_TYPE_CONTEXTS[_normalize_product_type(product_type)]


def _normalize_product_type(product_type: str | None) -> str:
    """Return a supported product type, falling back to general."""
    product_type_value = (product_type or "").strip().lower()
    product_type_value = PRODUCT_TYPE_ALIASES.get(product_type_value, product_type_value)
    if product_type_value in PRODUCT_TYPE_CONTEXTS:
        return product_type_value
    return "general"


def _url_product_context(url: str, scraped_text: str) -> str:
    """Put URL slug first so product-title hints beat page chrome text."""
    parsed = urlparse(url)
    slug_text = " ".join(part for part in parsed.path.split("/") if part)
    slug_text = unquote(slug_text).replace("-", " ").replace("_", " ")
    return f"url_product_hint {slug_text}\n{url}\n{scraped_text}"


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
    product_context: str | None = None,
) -> dict[str, object]:
    """Calculate quality only for trusted fabric compositions."""
    if not fabric_result.get("is_valid") or not fabric_result.get("composition"):
        return _empty_score_result()

    signature = inspect.signature(calculate_quality_score)  # type: ignore[arg-type]
    accepts_context = (
        "product_context" in signature.parameters
        or any(parameter.kind == inspect.Parameter.VAR_KEYWORD for parameter in signature.parameters.values())
    )
    if accepts_context:
        return calculate_quality_score(  # type: ignore[operator]
            fabric_result["composition"],
            product_context=product_context,
        )

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


def _assistant_material_context(fabric_composition: dict[str, float]) -> list[str]:
    """Return RAG snippets for the fabrics found in the product."""
    snippets: list[str] = []
    for fabric_name, ratio in fabric_composition.items():
        normalized_name = str(fabric_name).strip().lower()
        knowledge = FABRIC_RAG_KNOWLEDGE.get(normalized_name)
        if knowledge:
            snippets.append(f"{fabric_name} (%{ratio:g}): {knowledge}")
        else:
            snippets.append(f"{fabric_name} (%{ratio:g}): Bu materyal icin bilgi tabaninda ozel not yok.")
    return snippets


def _assistant_extra_rag_notes(notes: str | list[str] | None) -> list[str]:
    """Normalize optional RAG notes supplied by the caller."""
    if notes is None:
        return []
    if isinstance(notes, str):
        return [notes.strip()] if notes.strip() else []
    return [str(note).strip() for note in notes if str(note).strip()]


def _assistant_rag_context(request: AssistantRequest) -> list[str]:
    """Return all RAG snippets available for the assistant call."""
    return [
        *_assistant_material_context(request.fabric_composition),
        *_assistant_extra_rag_notes(request.rag_database_notes),
    ]


def _local_assistant_recommendation(request: AssistantRequest, rag_context: list[str]) -> str:
    """Build a deterministic recommendation when no LLM API key is configured."""
    synthetic_ratio = float(request.synthetic_ratio or 0)
    natural_ratio = float(request.natural_ratio or 0)
    price_text = f"{request.price:g} TL" if request.price is not None else "fiyat bilgisi yok"
    grade = request.grade or str(request.quality_score or "belirsiz")

    if synthetic_ratio >= 70:
        verdict = "Bu ürün fiyat/içerik açısından temkinli değerlendirilmeli."
        reason = "Sentetik lif oranı yüksek olduğu için sıcak havada terletme, koku tutma ve mikroplastik etkisi açısından dezavantaj oluşturabilir."
        alternative = "Aynı tarzda pamuk, keten, yün, tencel/liyosel veya daha yüksek doğal lif oranı olan alternatiflerle karşılaştır."
    elif natural_ratio >= 70:
        verdict = "Bu ürün içerik açısından güçlü ve konfor odaklı bir aday."
        reason = "Doğal lif oranı yüksek olduğu için nefes alma, günlük konfor ve mevsimsel kullanım beklentisi daha iyi."
        alternative = "Benzer fiyat bandında daha yüksek kalite skoru yoksa bu içerik dengesi mantıklı görünüyor."
    else:
        verdict = "Bu ürün orta seviyede; karar fiyat, kullanım amacı ve alternatiflerle verilmeli."
        reason = "Doğal ve sentetik lifler dengeli olduğu için hem konfor hem dayanıklılık tarafında artı ve eksiler birlikte değerlendirilir."
        alternative = "Fiyat yakınsa doğal lif oranı daha yüksek bir seçenek daha mantıklı olabilir."

    material_notes = "\n".join(f"- {snippet}" for snippet in rag_context)
    scoring_notes = "\n".join(f"- {note}" for note in (request.scoring_notes or []))
    scoring_notes_text = f"\n{scoring_notes}" if scoring_notes else ""
    question_note = f"\n\nKullanici sorusu: {request.question}" if request.question else ""
    return (
        "**Hızlı Özet**\n"
        f"- {verdict} Fiyat: {price_text}. Kalite notu/skoru: {grade}.\n\n"
        "**Kumaşın Artıları ve Eksileri**\n"
        f"- Doğal lif oranı %{natural_ratio:g}, sentetik lif oranı %{synthetic_ratio:g}.\n"
        f"- {reason}\n"
        f"{material_notes}\n\n"
        "**Fiyat Değerlendirmesi**\n"
        "- Fiyat bilgisi yoksa fiyat/performans için kesin çıkarım yapmam; yalnızca kalite skoru ve kumaş içeriğini yorumlarım.\n"
        "- Fiyat mevcutsa kalite skoru ve materyal dengesiyle birlikte değerlendirilmelidir."
        f"{scoring_notes_text}\n\n"
        "**Alternatif Önerisi**\n"
        f"- {alternative}"
        f"{question_note}"
    )


def _assistant_system_prompt() -> str:
    """Return the shared assistant behavior prompt."""
    return (
        "Sen 'FabricIQ' isimli akıllı tekstil analiz asistanısın. Görevin, teknik kumaş verilerini "
        "ve fiyat bilgilerini inceleyerek kullanıcılara anlaşılır, bilinçli ve kişiselleştirilmiş "
        "alışveriş tavsiyeleri sunmaktır. Amacın, sürdürülebilir ve etik tüketim alışkanlıklarını "
        "teşvik ederken kullanıcının parasının tam karşılığını almasına yardımcı olmaktır.\n\n"
        "1. ROL VE TON:\n"
        "- Uzman, güvenilir, tarafsız ve yönlendirici bir tekstil/alışveriş danışmanı gibi davran.\n"
        "- Teknik terimleri günlük kullanıma ve pratik etkilere çevirerek açıkla: terletme, dayanıklılık, "
        "çevreye etki, esneklik, koku tutma gibi.\n"
        "- Kesin yargılarla konuşma. 'Bunu kesin al' veya 'bunu sakın alma' deme; veriye dayalı tavsiye ver.\n\n"
        "2. VERİ YORUMLAMA VE RAG BAĞLAMI:\n"
        "- Sana sağlanan Doğal/Sentetik Oranı, Kalite Skoru ve RAG Bilgi Tabanı Verileri'ne sadık kal.\n"
        "- Sentetik oran yüksekse mikroplastik, doğada çözünmeme, terletme ve koku yapma risklerine dikkat çek.\n"
        "- Ürün spor, tayt, yoga, koşu veya performans giyim bağlamındaysa polyester/poliamid + elastan karışımını "
        "tek başına düşük kalite sayma; esneklik, form koruma ve hareket rahatlığı açısından fonksiyonel olabileceğini belirt.\n"
        "- Pamuk, keten, yün, tencel/liyosel gibi doğal veya sürdürülebilir lifleri kalite ve konfor açısından olumlu değerlendir.\n"
        "- Veri eksikse tahmin yapma. Eksik bilgiyi açıkça belirt ve sadece mevcut veriyle analiz yap.\n\n"
        "3. FİYAT/PERFORMANS ANALİZİ:\n"
        "- Ürünün fiyatını sistemin atadığı Kalite Skoru ile karşılaştır.\n"
        "- Skor Detayları verilirse performans puanı (KP), sürdürülebilirlik puanı (SP) ve nihai puanı birlikte yorumla.\n"
        "- Kumaş içeriği ucuz materyallerden oluştuğu halde fiyat yüksekse kullanıcıyı nazikçe marka primi konusunda uyar.\n"
        "- Fiyatına göre iyi doğal lif dengesi sunuyorsa bunu fırsat veya mantıklı tercih olarak vurgula.\n\n"
        "4. ÇIKTI FORMATI:\n"
        "- Yanıtı Türkçe ver.\n"
        "- Başlıkları kalın Markdown ile yaz ve alt kırılımlar için madde imleri kullan.\n"
        "- Sırasıyla şu başlıkları kullan: **Hızlı Özet**, **Kumaşın Artıları ve Eksileri**, "
        "**Fiyat Değerlendirmesi**, **Alternatif Önerisi**.\n"
        "- Alternatif önerisi gerekmiyorsa yine başlığı yazıp kısa şekilde gerekmediğini veya hangi koşulda aranacağını belirt.\n"
        "- Sadece verilen bağlamdaki bilgileri kullan; uydurma marka, fiyat, sertifika veya ürün bilgisi ekleme."
    )


def _assistant_user_prompt(request: AssistantRequest, rag_context: list[str]) -> str:
    """Build the user prompt from product data and RAG context."""
    user_payload = {
        "Ürün Bilgisi": request.product_name,
        "Kumaş Oranları": request.fabric_composition,
        "Kalite Skoru": request.quality_score,
        "Kalite Notu": request.grade,
        "Skor Notları": request.scoring_notes or [],
        "Skor Detayları": request.score_details or {},
        "Doğal/Sentetik Oranı": {
            "doğal": request.natural_ratio,
            "sentetik": request.synthetic_ratio,
        },
        "Fiyat": request.price,
        "RAG Veritabanı Notları": rag_context,
        "Kullanıcı Sorusu": request.question,
    }
    return (
        "Aşağıdaki RAG bağlamı ve ürün analiz verilerine göre yanıt ver. "
        "Kullanıcı sorusu yoksa 'fiyatına değer mi?' sorusunu yanıtla. "
        "Eksik alanlar için tahmin yapma.\n"
        f"{json.dumps(user_payload, ensure_ascii=False)}"
    )


def _int_env(name: str, default: int) -> int:
    """Return an integer env var with a safe default."""
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        logger.warning("Invalid integer environment value for %s; using %s.", name, default)
        return default


def _gemini_generation_config(*, include_thinking_config: bool = True) -> dict[str, object]:
    """Return Gemini generation config with optional thinking controls."""
    config: dict[str, object] = {
        "temperature": 0.35,
        "maxOutputTokens": _int_env("GEMINI_MAX_OUTPUT_TOKENS", 4096),
    }
    if include_thinking_config:
        config["thinkingConfig"] = {
            "thinkingBudget": _int_env("GEMINI_THINKING_BUDGET", 0),
        }
    return config


def _gemini_body(system_prompt: str, user_prompt: str, *, include_thinking_config: bool = True) -> dict[str, object]:
    """Build the Gemini API request body."""
    return {
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
        "generationConfig": _gemini_generation_config(include_thinking_config=include_thinking_config),
    }


def _should_retry_without_thinking_config(response: requests.Response) -> bool:
    """Return true when Gemini rejects thinkingConfig."""
    if response.status_code != 400:
        return False
    response_text = response.text.lower()
    return "thinkingconfig" in response_text or "thinkingbudget" in response_text


def _call_gemini_recommendation(request: AssistantRequest, rag_context: list[str]) -> tuple[str, str]:
    """Call Gemini and return recommendation text plus provider name."""
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        logger.warning("Gemini assistant fallback: no API key loaded.")
        return _local_assistant_recommendation(request, rag_context), "local_fallback"

    model = request.model or os.getenv("GEMINI_MODEL", GEMINI_DEFAULT_MODEL)
    timeout = float(os.getenv("GEMINI_TIMEOUT_SECONDS", "90"))
    endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    logger.info("Calling Gemini assistant model=%s key_length=%s timeout=%s", model, len(api_key), timeout)
    system_prompt = (
        _assistant_system_prompt()
    )
    user_prompt = _assistant_user_prompt(request, rag_context)
    response = requests.post(
        endpoint,
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": api_key,
        },
        json=_gemini_body(system_prompt, user_prompt),
        timeout=timeout,
    )
    if _should_retry_without_thinking_config(response):
        logger.warning("Gemini rejected thinkingConfig; retrying without thinkingConfig.")
        response = requests.post(
            endpoint,
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": api_key,
            },
            json=_gemini_body(system_prompt, user_prompt, include_thinking_config=False),
            timeout=timeout,
        )
    response.raise_for_status()
    payload = response.json()
    candidates = payload.get("candidates") or []
    finish_reasons = [
        candidate.get("finishReason")
        for candidate in candidates
        if isinstance(candidate, dict)
    ]
    logger.info(
        "Gemini assistant response candidates=%s finish_reasons=%s usage=%s",
        len(candidates),
        finish_reasons,
        payload.get("usageMetadata"),
    )
    parts = candidates[0].get("content", {}).get("parts", []) if candidates else []
    text = "\n".join(str(part.get("text") or "") for part in parts if isinstance(part, dict)).strip()
    if not text:
        logger.warning(
            "Gemini assistant fallback: empty text response. candidates=%s finish_reasons=%s prompt_feedback=%s",
            len(candidates),
            finish_reasons,
            payload.get("promptFeedback"),
        )
        return _local_assistant_recommendation(request, rag_context), "local_fallback"
    return text, f"gemini:{model}"


def _call_assistant_model(request: AssistantRequest, rag_context: list[str]) -> tuple[str, str]:
    """Call Gemini unless the local model is explicitly selected."""
    model = (request.model or "").strip().lower()
    if model == "local":
        return _local_assistant_recommendation(request, rag_context), "local_fallback"
    return _call_gemini_recommendation(request, rag_context)


def _assistant_provider_warning(exc: requests.RequestException) -> str:
    """Return a user-facing warning for assistant provider failures."""
    if isinstance(exc, requests.Timeout):
        return (
            "Secilen AI saglayicisi zamaninda yanit vermedi; FabricIQ yerel tavsiye mantigini kullandi."
        )

    response = getattr(exc, "response", None)
    status_code = getattr(response, "status_code", None)
    if status_code == 404:
        return (
            "Secilen Gemini modeli veya API yolu bulunamadi; FabricIQ yerel tavsiye mantigini kullandi."
        )
    if status_code == 403:
        return (
            "API key yetkisi veya proje erisimi reddedildi; FabricIQ yerel tavsiye mantigini kullandi."
        )
    if status_code == 429:
        return (
            "API kota veya hiz limitine takildi; FabricIQ yerel tavsiye mantigini kullandi."
        )

    return "LLM istegi basarisiz oldu; FabricIQ yerel tavsiye mantigini kullandi."


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
    uploaded_file, form_fields = _extract_multipart_upload(request_body, content_type)
    product_type = _normalize_product_type(form_fields.get("product_type"))
    product_context = _label_product_context(product_type)

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
            "product_type": product_type,
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


@app.post("/assistant/recommend", response_model=None)
async def recommend_product(request: AssistantRequest) -> object:
    """Return an LLM-backed buy/value recommendation for analyzed product data."""
    try:
        rag_context = _assistant_rag_context(request)
        recommendation, provider = _call_assistant_model(request, rag_context)
        return {
            "success": True,
            "recommendation": recommendation,
            "provider": provider,
            "rag_context": rag_context,
        }
    except requests.RequestException as exc:
        logger.warning("Assistant LLM request failed; returning local fallback. Error: %s", exc)
        rag_context = _assistant_rag_context(request)
        return {
            "success": True,
            "recommendation": _local_assistant_recommendation(request, rag_context),
            "provider": "local_fallback",
            "rag_context": rag_context,
            "warning": _assistant_provider_warning(exc),
        }
    except Exception as exc:
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": {
                    "code": "assistant_failed",
                    "message": "Akilli kiyafet asistani su anda tavsiye uretmedi.",
                    "detail": f"{type(exc).__name__}: {exc}",
                },
            },
        )


@app.post("/analyze/label", response_model=None, openapi_extra=LABEL_UPLOAD_OPENAPI_EXTRA)
async def analyze_label(request: Request) -> object:
    """Analyze an uploaded clothing label image end-to-end."""
    content_type = request.headers.get("content-type", "")
    request_body = await request.body()
    uploaded_file, form_fields = _extract_multipart_upload(request_body, content_type)
    product_type = _normalize_product_type(form_fields.get("product_type"))
    product_context = _label_product_context(product_type)

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
            dict[str, object],
        ] | None = None
        candidate_results: list[
            tuple[
                tuple[int, int, float, float, int],
                dict[str, str | float],
                dict[str, object],
                dict[str, object],
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
            score_result = _score_if_valid(fabric_result, calculate_quality_score, product_context=product_context)
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
                score_result = _score_if_valid(fabric_result, calculate_quality_score, product_context=product_context)
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
                merged_score_result = _score_if_valid(
                    merged_fabric_result,
                    calculate_quality_score,
                    product_context=product_context,
                )
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
            "product_type": product_type,
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
        score_context = _url_product_context(request.url, scraped_text)
        score_result = _score_if_valid(
            fabric_result,
            calculate_quality_score,
            product_context=score_context,
        )
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
