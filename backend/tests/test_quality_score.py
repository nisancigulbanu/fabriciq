from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.scoring.quality_score import calculate_quality_score


def test_polyester_elastane_scores_low_without_product_context() -> None:
    """Keep general-purpose synthetic scoring conservative without product context."""
    result = calculate_quality_score(
        [{"fabric": "polyester", "ratio": 88}, {"fabric": "elastan", "ratio": 12}]
    )

    assert result["quality_score"] == 22
    assert result["grade"] == "F"
    assert result["scoring_notes"] == []


def test_polyester_elastane_scores_better_for_sports_leggings() -> None:
    """Treat polyester + elastane as functional when the product is activewear."""
    result = calculate_quality_score(
        [{"fabric": "polyester", "ratio": 88}, {"fabric": "elastan", "ratio": 12}],
        product_context="Spor tayt yoga leggings",
    )

    assert result["quality_score"] == 72
    assert result["grade"] == "C"
    assert result["scoring_notes"]
