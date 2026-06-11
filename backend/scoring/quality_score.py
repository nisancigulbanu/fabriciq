"""Rule-based quality scoring for fabric compositions."""

from __future__ import annotations

FABRIC_WEIGHTS: dict[str, int] = {
    "ipek": 100,
    "kasmir": 95,
    "yun": 85,
    "keten": 80,
    "pamuk": 75,
    "viskon": 55,
    "elastan": 40,
    "akrilik": 35,
    "naylon": 30,
    "poliamid": 30,
    "polyester": 20,
}

NATURAL_FABRICS = {"ipek", "kasmir", "yun", "keten", "pamuk"}
SYNTHETIC_FABRICS = {"viskon", "elastan", "akrilik", "naylon", "poliamid", "polyester"}


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


def calculate_quality_score(composition: list[dict[str, int | str]]) -> dict[str, int | str]:
    """Calculate a normalized quality score from parsed fabric composition."""
    weighted_sum = 0.0
    recognized_ratio_total = 0
    natural_ratio = 0
    synthetic_ratio = 0

    for item in composition:
        fabric = str(item.get("fabric", "")).lower()
        ratio = int(item.get("ratio", 0))
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
        }

    normalized_score = weighted_sum / recognized_ratio_total
    quality_score = max(0, min(100, round(normalized_score)))

    return {
        "quality_score": quality_score,
        "grade": _grade_for_score(quality_score),
        "natural_ratio": natural_ratio,
        "synthetic_ratio": synthetic_ratio,
    }
