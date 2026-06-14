from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.scoring.quality_score import calculate_quality_score


def test_polyester_elastane_scores_as_good_for_activewear() -> None:
    """Score a common activewear blend near the documented good range."""
    result = calculate_quality_score(
        [{"fabric": "polyester", "ratio": 80}, {"fabric": "elastan", "ratio": 20}],
        product_context="activewear",
    )

    assert 74 <= result["quality_score"] <= 76
    assert result["grade"] == "B"
    assert result["score_details"]["performance_score"] > result["score_details"]["sustainability_score"]
    assert result["score_details"]["product_type"] == "activewear"
    assert result["score_details"]["formula_version"] == "kp_sp_v1"
    assert result["scoring_notes"]


def test_nylon_elastane_scores_high_for_activewear() -> None:
    """Treat nylon plus elastane as a strong activewear composition."""
    result = calculate_quality_score(
        [{"fabric": "naylon", "ratio": 78}, {"fabric": "elastan", "ratio": 22}],
        product_context="tayt leggings",
    )

    assert result["quality_score"] >= 84
    assert result["grade"] == "B"
    assert result["score_details"]["category"] == "İyi"


def test_cotton_scores_poorly_for_activewear() -> None:
    """Penalize cotton-heavy activewear because it holds moisture and loses shape."""
    result = calculate_quality_score(
        [{"fabric": "pamuk", "ratio": 100}],
        product_context="activewear",
    )

    assert result["quality_score"] < 40
    assert result["grade"] == "F"
    assert result["score_details"]["product_type"] == "activewear"


def test_cotton_scores_well_for_tshirt_underwear() -> None:
    """Reward cotton in skin-contact everyday garments."""
    result = calculate_quality_score(
        [{"fabric": "pamuk", "ratio": 100}],
        product_context="tshirt_underwear",
    )

    assert result["quality_score"] >= 70
    assert result["grade"] == "B"
    assert result["score_details"]["product_type"] == "tshirt_underwear"


def test_polo_tshirt_url_slug_scores_as_tshirt_not_activewear() -> None:
    """Classify Trendyol-style polo/tisort slugs as everyday t-shirt context."""
    result = calculate_quality_score(
        [{"fabric": "pamuk", "ratio": 100}],
        product_context="https://www.trendyol.com/kigili/polo-yaka-slim-fit-nakisli-100-pamuk-tisort-p-702124365?boutiqueId=61 spor",
    )

    assert result["score_details"]["product_type"] == "tshirt_underwear"
    assert result["quality_score"] >= 70
    assert result["grade"] == "B"


def test_baby_zibin_url_slug_scores_as_baby_kids_before_tshirt() -> None:
    """Prioritize explicit baby/kids signals over generic t-shirt or underwear page text."""
    result = calculate_quality_score(
        [{"fabric": "pamuk", "ratio": 100}],
        product_context=(
            "https://www.trendyol.com/mai-perla/"
            "unisex-bebek-sari-arili-3-lu-zibin-takimi-p-110574796?boutiqueId=61 "
            "tshirt underwear"
        ),
    )

    assert result["score_details"]["product_type"] == "baby_kids"


def test_polyester_scores_low_for_knitwear_and_better_for_outerwear() -> None:
    """Score the same fiber differently by product context."""
    knitwear = calculate_quality_score(
        [{"fabric": "polyester", "ratio": 100}],
        product_context="knitwear",
    )
    outerwear = calculate_quality_score(
        [{"fabric": "polyester", "ratio": 100}],
        product_context="outerwear",
    )

    assert knitwear["quality_score"] < 40
    assert outerwear["quality_score"] >= 55
    assert outerwear["quality_score"] > knitwear["quality_score"]


def test_unknown_product_context_falls_back_to_general() -> None:
    """Use neutral coefficients when product context cannot be recognized."""
    result = calculate_quality_score(
        [{"fabric": "polyester", "ratio": 88}, {"fabric": "elastan", "ratio": 12}],
        product_context="unknown-context",
    )

    assert result["score_details"]["product_type"] == "general"
    assert result["quality_score"] < 60


def test_unknown_fabric_adds_note_without_breaking_score() -> None:
    """Ignore unknown fibers and explain that they were excluded."""
    result = calculate_quality_score(
        [{"fabric": "pamuk", "ratio": 80}, {"fabric": "mystery", "ratio": 20}],
        product_context="tshirt_underwear",
    )

    assert result["quality_score"] > 0
    assert any("Tanınmayan lifler" in note for note in result["scoring_notes"])
