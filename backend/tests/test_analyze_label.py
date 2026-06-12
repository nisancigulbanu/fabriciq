from __future__ import annotations

import sys
import types
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.main import app


@pytest.fixture
def client() -> TestClient:
    """Create a FastAPI test client."""
    original_init = httpx.Client.__init__

    def patched_init(self, *args, app=None, **kwargs):  # type: ignore[no-untyped-def]
        return original_init(self, *args, **kwargs)

    httpx.Client.__init__ = patched_init  # type: ignore[assignment]
    return TestClient(app)


def _install_fake_pipeline(
    monkeypatch: pytest.MonkeyPatch,
    *,
    raw_text: str,
    confident_text: str,
    avg_confidence: float = 88.5,
    composition: list[dict[str, int | str]] | None = None,
    is_valid: bool = True,
    warning: str | None = None,
) -> dict[str, str]:
    """Install fake OCR and scoring modules for endpoint tests."""
    captured: dict[str, str] = {}

    fake_preprocessor = types.ModuleType("ocr.preprocessor")
    fake_preprocessor.preprocess_image = lambda image_path: "processed-image"
    fake_preprocessor.preprocess_image_variants = lambda image_path: [("default", "processed-image")]

    fake_engine = types.ModuleType("ocr.engine")
    fake_engine.extract_text_from_image = lambda processed_image: {
        "raw_text": raw_text,
        "confident_text": confident_text,
        "avg_confidence": avg_confidence,
    }

    fake_parser = types.ModuleType("ocr.fabric_parser")

    def parse_fabric_composition(text: str) -> dict[str, object]:
        captured.setdefault("texts_to_parse", []).append(text)  # type: ignore[union-attr]
        captured["text_to_parse"] = text
        parsed_composition = composition or [{"fabric": "pamuk", "ratio": 60}, {"fabric": "polyester", "ratio": 40}]
        return {
            "composition": parsed_composition,
            "total_ratio": sum(int(item["ratio"]) for item in parsed_composition),
            "is_valid": is_valid,
            "warning": warning,
        }

    fake_parser.parse_fabric_composition = parse_fabric_composition

    fake_scorer = types.ModuleType("scoring.quality_score")
    fake_scorer.calculate_quality_score = lambda parsed_composition: {
        "quality_score": 53,
        "grade": "F",
        "natural_ratio": 60,
        "synthetic_ratio": 40,
    }

    fake_paddle_engine = types.ModuleType("ocr.engine_paddle")
    fake_paddle_engine.run_paddleocr = lambda processed_image: {
        "raw_text": "",
        "confident_text": "",
        "avg_confidence": 0.0,
    }

    monkeypatch.setitem(sys.modules, "backend.ocr.preprocessor", fake_preprocessor)
    monkeypatch.setitem(sys.modules, "backend.ocr.engine", fake_engine)
    monkeypatch.setitem(sys.modules, "backend.ocr.engine_paddle", fake_paddle_engine)
    monkeypatch.setitem(sys.modules, "backend.ocr.fabric_parser", fake_parser)
    monkeypatch.setitem(sys.modules, "backend.scoring.quality_score", fake_scorer)

    return captured


def _install_fake_multi_variant_pipeline(monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    """Install a fake OCR pipeline with one bad variant and one parseable variant."""
    captured: dict[str, object] = {"ocr_calls": []}

    fake_preprocessor = types.ModuleType("ocr.preprocessor")
    fake_preprocessor.preprocess_image_variants = lambda image_path: [
        ("bad", "bad-image"),
        ("good", "good-image"),
    ]

    fake_engine = types.ModuleType("ocr.engine")

    def extract_text_from_image(processed_image: str) -> dict[str, str | float]:
        captured["ocr_calls"].append(processed_image)  # type: ignore[union-attr]
        if processed_image == "bad-image":
            return {
                "raw_text": "blurred text",
                "confident_text": "",
                "avg_confidence": 22.0,
            }

        return {
            "raw_text": "60% Pamuk 40% Polyester",
            "confident_text": "60% Pamuk 40% Polyester",
            "avg_confidence": 91.0,
        }

    fake_engine.extract_text_from_image = extract_text_from_image

    fake_parser = types.ModuleType("ocr.fabric_parser")

    def parse_fabric_composition(text: str) -> dict[str, object]:
        captured["selected_text"] = text
        if "Pamuk" not in text:
            return {
                "composition": [],
                "total_ratio": 0,
                "is_valid": False,
                "warning": "Fabric composition could not be extracted from the provided text.",
            }

        return {
            "composition": [{"fabric": "pamuk", "ratio": 60}, {"fabric": "polyester", "ratio": 40}],
            "total_ratio": 100,
            "is_valid": True,
            "warning": None,
        }

    fake_parser.parse_fabric_composition = parse_fabric_composition

    fake_scorer = types.ModuleType("scoring.quality_score")
    fake_scorer.calculate_quality_score = lambda parsed_composition: {
        "quality_score": 53,
        "grade": "F",
        "natural_ratio": 60,
        "synthetic_ratio": 40,
    }

    fake_paddle_engine = types.ModuleType("ocr.engine_paddle")
    fake_paddle_engine.run_paddleocr = lambda processed_image: {
        "raw_text": "",
        "confident_text": "",
        "avg_confidence": 0.0,
    }

    monkeypatch.setitem(sys.modules, "backend.ocr.preprocessor", fake_preprocessor)
    monkeypatch.setitem(sys.modules, "backend.ocr.engine", fake_engine)
    monkeypatch.setitem(sys.modules, "backend.ocr.engine_paddle", fake_paddle_engine)
    monkeypatch.setitem(sys.modules, "backend.ocr.fabric_parser", fake_parser)
    monkeypatch.setitem(sys.modules, "backend.scoring.quality_score", fake_scorer)

    return captured


def _install_fake_url_pipeline(
    monkeypatch: pytest.MonkeyPatch,
    *,
    scraped_text: str = "60% Cotton 40% Polyester",
    dynamic: bool = False,
) -> dict[str, object]:
    """Install fake URL extraction, parser, and scoring modules for endpoint tests."""
    captured: dict[str, object] = {}

    fake_extractor = types.ModuleType("url_parser.extractor")

    def extract_fabric_text(url: str) -> str:
        captured["url"] = url
        if dynamic:
            raise NotImplementedError("Dynamic URL parsing is not implemented yet.")
        return scraped_text

    fake_extractor.extract_fabric_text = extract_fabric_text

    fake_parser = types.ModuleType("ocr.fabric_parser")

    def parse_fabric_composition(text: str) -> dict[str, object]:
        captured["text_to_parse"] = text
        return {
            "composition": [{"fabric": "pamuk", "ratio": 60}, {"fabric": "polyester", "ratio": 40}],
            "total_ratio": 100,
            "is_valid": True,
            "warning": None,
        }

    fake_parser.parse_fabric_composition = parse_fabric_composition

    fake_scorer = types.ModuleType("scoring.quality_score")

    def calculate_quality_score(composition: list[dict[str, int | str]]) -> dict[str, int | str]:
        captured["composition"] = composition
        return {
            "quality_score": 53,
            "grade": "F",
            "natural_ratio": 60,
            "synthetic_ratio": 40,
        }

    fake_scorer.calculate_quality_score = calculate_quality_score

    monkeypatch.setitem(sys.modules, "backend.url_parser.extractor", fake_extractor)
    monkeypatch.setitem(sys.modules, "backend.ocr.fabric_parser", fake_parser)
    monkeypatch.setitem(sys.modules, "backend.scoring.quality_score", fake_scorer)

    return captured


def test_analyze_label_returns_success_for_valid_image(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Return success=true for a valid uploaded image."""
    _install_fake_pipeline(monkeypatch, raw_text="%60 Pamuk %40 Polyester", confident_text="%60 Pamuk %40 Polyester")

    response = client.post(
        "/analyze/label",
        files={"file": ("label.jpg", b"fake-image-bytes", "image/jpeg")},
    )

    assert response.status_code == 200
    assert response.json()["success"] is True


def test_analyze_label_returns_non_empty_fabric_composition(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Return a non-empty fabric composition in the response."""
    _install_fake_pipeline(monkeypatch, raw_text="%60 Pamuk %40 Polyester", confident_text="%60 Pamuk %40 Polyester")

    response = client.post(
        "/analyze/label",
        files={"file": ("label.jpg", b"fake-image-bytes", "image/jpeg")},
    )

    assert response.status_code == 200
    assert response.json()["fabric"]["composition"]


def test_analyze_label_returns_400_when_file_is_missing(client: TestClient) -> None:
    """Return a structured 400 response when no file is sent."""
    response = client.post("/analyze/label")

    assert response.status_code == 400
    assert response.json()["success"] is False


def test_analyze_label_uses_raw_text_when_confident_text_is_empty(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fallback to raw_text when confident_text is empty."""
    captured = _install_fake_pipeline(
        monkeypatch,
        raw_text="60% Cotton 40% PES",
        confident_text="",
    )

    response = client.post(
        "/analyze/label",
        files={"file": ("label.jpg", b"fake-image-bytes", "image/jpeg")},
    )

    assert response.status_code == 200
    assert captured["texts_to_parse"][0] == "60% Cotton 40% PES"


def test_analyze_label_returns_capture_advice_when_ocr_is_weak(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Return capture guidance when OCR confidence is low or composition is invalid."""
    _install_fake_pipeline(
        monkeypatch,
        raw_text="blurred text",
        confident_text="",
        avg_confidence=31.0,
        composition=[],
        is_valid=False,
        warning="Fabric composition could not be extracted from the provided text.",
    )

    response = client.post(
        "/analyze/label",
        files={"file": ("label.jpg", b"fake-image-bytes", "image/jpeg")},
    )

    response_json = response.json()
    assert response.status_code == 200
    assert response_json["advice"]
    assert "duz aciyla" in response_json["advice"]


def test_analyze_label_uses_best_preprocessing_variant(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Try multiple preprocessing variants and return the parseable OCR result."""
    captured = _install_fake_multi_variant_pipeline(monkeypatch)

    response = client.post(
        "/analyze/label",
        files={"file": ("label.jpg", b"fake-image-bytes", "image/jpeg")},
    )

    response_json = response.json()
    assert response.status_code == 200
    assert response_json["fabric"]["is_valid"] is True
    assert response_json["advice"] is None
    assert captured["ocr_calls"] == ["bad-image", "good-image"]


def test_analyze_label_returns_advice_for_valid_low_confidence_result(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Show capture guidance when a parsed composition came from weak OCR."""
    _install_fake_pipeline(
        monkeypatch,
        raw_text="100% Polyester",
        confident_text="",
        avg_confidence=34.0,
        composition=[{"fabric": "polyester", "ratio": 100}],
        is_valid=True,
        warning=None,
    )

    response = client.post(
        "/analyze/label",
        files={"file": ("label.jpg", b"fake-image-bytes", "image/jpeg")},
    )

    response_json = response.json()
    assert response.status_code == 200
    assert response_json["fabric"]["is_valid"] is True
    assert response_json["advice"]
    assert "duz aciyla" in response_json["advice"]


def test_analyze_label_continues_after_partial_valid_total(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Keep searching when a valid-but-incomplete OCR result totals below 100."""
    captured: dict[str, object] = {"ocr_calls": []}

    fake_preprocessor = types.ModuleType("ocr.preprocessor")
    fake_preprocessor.preprocess_image_variants = lambda image_path: [
        ("partial", "partial-image"),
        ("complete", "complete-image"),
    ]

    fake_engine = types.ModuleType("ocr.engine")

    def extract_text_from_image(processed_image: str) -> dict[str, str | float]:
        captured["ocr_calls"].append(processed_image)  # type: ignore[union-attr]
        if processed_image == "partial-image":
            return {
                "raw_text": "98% Cotton",
                "confident_text": "98% Cotton",
                "avg_confidence": 92.0,
            }

        return {
            "raw_text": "98% Cotton 2% Elastane",
            "confident_text": "98% Cotton 2% Elastane",
            "avg_confidence": 88.0,
        }

    fake_engine.extract_text_from_image = extract_text_from_image

    fake_paddle_engine = types.ModuleType("ocr.engine_paddle")
    fake_paddle_engine.run_paddleocr = lambda processed_image: {
        "raw_text": "",
        "confident_text": "",
        "avg_confidence": 0.0,
    }

    from backend.ocr.fabric_parser import parse_fabric_composition

    fake_parser = types.ModuleType("ocr.fabric_parser")
    fake_parser.parse_fabric_composition = parse_fabric_composition

    fake_scorer = types.ModuleType("scoring.quality_score")
    fake_scorer.calculate_quality_score = lambda parsed_composition: {
        "quality_score": 74,
        "grade": "C",
        "natural_ratio": 98,
        "synthetic_ratio": 2,
    }

    monkeypatch.setitem(sys.modules, "backend.ocr.preprocessor", fake_preprocessor)
    monkeypatch.setitem(sys.modules, "backend.ocr.engine", fake_engine)
    monkeypatch.setitem(sys.modules, "backend.ocr.engine_paddle", fake_paddle_engine)
    monkeypatch.setitem(sys.modules, "backend.ocr.fabric_parser", fake_parser)
    monkeypatch.setitem(sys.modules, "backend.scoring.quality_score", fake_scorer)

    response = client.post(
        "/analyze/label",
        files={"file": ("label.jpg", b"fake-image-bytes", "image/jpeg")},
    )

    response_json = response.json()
    assert response.status_code == 200
    assert captured["ocr_calls"] == ["partial-image", "complete-image"]
    assert response_json["fabric"]["composition"] == [
        {"fabric": "pamuk", "ratio": 98},
        {"fabric": "elastan", "ratio": 2},
    ]


def test_analyze_label_merges_composition_across_ocr_variants(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Merge partial composition entries when different variants read different rows."""
    fake_preprocessor = types.ModuleType("ocr.preprocessor")
    fake_preprocessor.preprocess_image_variants = lambda image_path: [
        ("top_rows", "top-image"),
        ("bottom_rows", "bottom-image"),
    ]

    fake_engine = types.ModuleType("ocr.engine")

    def extract_text_from_image(processed_image: str) -> dict[str, str | float]:
        if processed_image == "top-image":
            return {
                "raw_text": "83% viskoz 15% poliamit",
                "confident_text": "83% viskoz 15% poliamit",
                "avg_confidence": 91.0,
            }

        return {
            "raw_text": "15% poliamit 2% elastan",
            "confident_text": "15% poliamit 2% elastan",
            "avg_confidence": 84.0,
        }

    fake_engine.extract_text_from_image = extract_text_from_image

    fake_paddle_engine = types.ModuleType("ocr.engine_paddle")
    fake_paddle_engine.run_paddleocr = lambda processed_image: {
        "raw_text": "",
        "confident_text": "",
        "avg_confidence": 0.0,
    }

    from backend.ocr.fabric_parser import parse_fabric_composition

    fake_parser = types.ModuleType("ocr.fabric_parser")
    fake_parser.parse_fabric_composition = parse_fabric_composition

    fake_scorer = types.ModuleType("scoring.quality_score")
    fake_scorer.calculate_quality_score = lambda parsed_composition: {
        "quality_score": 51,
        "grade": "F",
        "natural_ratio": 0,
        "synthetic_ratio": 100,
    }

    monkeypatch.setitem(sys.modules, "backend.ocr.preprocessor", fake_preprocessor)
    monkeypatch.setitem(sys.modules, "backend.ocr.engine", fake_engine)
    monkeypatch.setitem(sys.modules, "backend.ocr.engine_paddle", fake_paddle_engine)
    monkeypatch.setitem(sys.modules, "backend.ocr.fabric_parser", fake_parser)
    monkeypatch.setitem(sys.modules, "backend.scoring.quality_score", fake_scorer)

    response = client.post(
        "/analyze/label",
        files={"file": ("label.jpg", b"fake-image-bytes", "image/jpeg")},
    )

    response_json = response.json()
    assert response.status_code == 200
    assert response_json["fabric"]["composition"] == [
        {"fabric": "viskoz", "ratio": 83},
        {"fabric": "poliamid", "ratio": 15},
        {"fabric": "elastan", "ratio": 2},
    ]
    assert response_json["fabric"]["total_ratio"] == 100


def test_analyze_url_returns_success_for_static_page(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Analyze a static URL through extractor, parser, and scorer."""
    captured = _install_fake_url_pipeline(monkeypatch, scraped_text="60% Cotton 40% Polyester")

    response = client.post("/analyze/url", json={"url": "https://example.com/product"})

    assert response.status_code == 200
    response_json = response.json()
    assert response_json["success"] is True
    assert response_json["fabric"]["composition"]
    assert captured["url"] == "https://example.com/product"
    assert captured["text_to_parse"] == "60% Cotton 40% Polyester"


def test_analyze_url_returns_structured_error_for_unexpected_dynamic_failure(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Return a structured error when URL extraction fails unexpectedly."""
    _install_fake_url_pipeline(monkeypatch, dynamic=True)

    response = client.post("/analyze/url", json={"url": "https://example.com/dynamic-product"})

    assert response.status_code == 500
    assert response.json()["success"] is False
    assert response.json()["error"]["message"] == (
        "Bu urun sayfasi otomatik okunamadi. Etiket fotografi ile tekrar deneyebilirsiniz."
    )
