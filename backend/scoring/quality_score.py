"""Rule-based quality scoring for fabric compositions."""

from __future__ import annotations

import re

FABRIC_WEIGHTS: dict[str, int] = {
    "ipek": 100,
    "kasmir": 95,
    "yun": 85,
    "yün": 85,
    "keten": 80,
    "pamuk": 75,
    "viskon": 55,
    "viskoz": 55,
    "elastan": 40,
    "akrilik": 35,
    "naylon": 30,
    "poliamid": 30,
    "polyester": 20,
}

NATURAL_FABRICS = {"ipek", "kasmir", "yun", "yün", "keten", "pamuk"}
SYNTHETIC_FABRICS = {"viskon", "viskoz", "elastan", "akrilik", "naylon", "poliamid", "polyester"}
ACTIVEWEAR_KEYWORDS = {
    "activewear",
    "athletic",
    "fitness",
    "gym",
    "legging",
    "leggings",
    "performance",
    "pilates",
    "running",
    "sport",
    "sports",
    "tayt",
    "antrenman",
    "egzersiz",
    "kosu",
    "spor",
    "yoga",
}


def _grade_for_score(score: int) -> str:
    """Map a numeric quality score to a letter grade."""
    if score >= 90:
        return "A"
    if score >= 80:
        return "B"
    if score >= 70:
        return "C"
    if score >= 60:
        return "D"
    return "F"


def _composition_ratio(composition: list[dict[str, int | float | str]], fabric_names: set[str]) -> float:
    """Return total ratio for a group of normalized fabric names."""
    total = 0.0
    for item in composition:
        fabric = str(item.get("fabric", "")).lower()
        if fabric not in fabric_names:
            continue
        try:
            total += float(item.get("ratio", 0))
        except (TypeError, ValueError):
            continue
    return total


def _is_activewear_context(product_context: str | None) -> bool:
    """Return true when product text implies a sport/performance use case."""
    context = (product_context or "").lower()
    if not context:
        return False
    tokens = set(re.findall(r"[a-zA-ZğüşöçıİĞÜŞÖÇ]+", context))
    return bool(tokens & ACTIVEWEAR_KEYWORDS)


def _activewear_adjustment(
    composition: list[dict[str, int | float | str]],
    base_score: int,
    product_context: str | None,
) -> tuple[int, str | None]:
    """Adjust score when synthetic fibers are functional for sportswear."""
    if not _is_activewear_context(product_context):
        return base_score, None

    polyester_ratio = _composition_ratio(composition, {"polyester"})
    polyamide_ratio = _composition_ratio(composition, {"poliamid", "naylon"})
    elastane_ratio = _composition_ratio(composition, {"elastan"})
    performance_synthetic_ratio = polyester_ratio + polyamide_ratio

    if performance_synthetic_ratio >= 60 and 5 <= elastane_ratio <= 25:
        adjusted_score = max(base_score, 68)
        if 70 <= performance_synthetic_ratio <= 92 and 8 <= elastane_ratio <= 18:
            adjusted_score = max(adjusted_score, 72)
        return (
            min(100, adjusted_score),
            "Spor/performans ürünü bağlamında polyester veya poliamid + elastan karışımı esneklik, form koruma ve hareket rahatlığı için olumlu değerlendirildi.",
        )

    return base_score, None


def calculate_quality_score(
    composition: list[dict[str, int | float | str]],
    product_context: str | None = None,
) -> dict[str, int | str | list[str]]:
    """Calculate a normalized quality score from parsed fabric composition."""
    weighted_sum = 0.0
    recognized_ratio_total = 0.0
    natural_ratio = 0.0
    synthetic_ratio = 0.0

    for item in composition:
        fabric = str(item.get("fabric", "")).lower()
        ratio = float(item.get("ratio", 0))
        weight = FABRIC_WEIGHTS.get(fabric)

        if weight is None:
            continue

        weighted_sum += weight * ratio
        recognized_ratio_total += ratio

        if fabric in NATURAL_FABRICS:
            natural_ratio += ratio
        elif fabric in SYNTHETIC_FABRICS:
            synthetic_ratio += ratio

    if recognized_ratio_total == 0:
        return {
            "quality_score": 0,
            "grade": "F",
            "natural_ratio": 0,
            "synthetic_ratio": 0,
            "scoring_notes": [],
        }

    normalized_score = weighted_sum / recognized_ratio_total
    quality_score = max(0, min(100, round(normalized_score)))
    scoring_notes: list[str] = []
    quality_score, activewear_note = _activewear_adjustment(composition, quality_score, product_context)
    if activewear_note:
        scoring_notes.append(activewear_note)

    return {
        "quality_score": quality_score,
        "grade": _grade_for_score(quality_score),
        "natural_ratio": round(natural_ratio),
        "synthetic_ratio": round(synthetic_ratio),
        "scoring_notes": scoring_notes,
    }
