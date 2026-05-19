from __future__ import annotations

import sys
import types
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from main import app


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
    composition: list[dict[str, int | str]] | None = None,
) -> dict[str, str]:
    """Install fake OCR and scoring modules for endpoint tests."""
    captured: dict[str, str] = {}

    fake_preprocessor = types.ModuleType("ocr.preprocessor")
    fake_preprocessor.preprocess_image = lambda image_path: "processed-image"

    fake_engine = types.ModuleType("ocr.engine")
    fake_engine.extract_text_from_image = lambda processed_image: {
        "raw_text": raw_text,
        "confident_text": confident_text,
        "avg_confidence": 88.5,
    }

    fake_parser = types.ModuleType("ocr.fabric_parser")

    def parse_fabric_composition(text: str) -> dict[str, object]:
        captured["text_to_parse"] = text
        parsed_composition = composition or [{"fabric": "pamuk", "ratio": 60}, {"fabric": "polyester", "ratio": 40}]
        return {
            "composition": parsed_composition,
            "total_ratio": sum(int(item["ratio"]) for item in parsed_composition),
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

    monkeypatch.setitem(sys.modules, "backend.ocr.preprocessor", fake_preprocessor)
    monkeypatch.setitem(sys.modules, "backend.ocr.engine", fake_engine)
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
    assert captured["text_to_parse"] == "60% Cotton 40% PES"


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


def test_analyze_url_returns_dynamic_not_supported(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Return a clear error while dynamic URL parsing is not implemented."""
    _install_fake_url_pipeline(monkeypatch, dynamic=True)

    response = client.post("/analyze/url", json={"url": "https://example.com/dynamic-product"})

    assert response.status_code == 501
    assert response.json() == {
        "success": False,
        "error": "Dynamic pages not supported yet",
    }
