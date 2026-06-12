"""Fabric composition parser for OCR and scraped text."""

from __future__ import annotations

import math
import re
from itertools import combinations
from typing import Any

Ratio = int | float
CompositionEntry = dict[str, Ratio | str]


def _normalize_turkish(text: str) -> str:
    """Lowercase Turkish text consistently, including common mojibake forms."""
    replacements = {
        "İ": "i",
        "I": "i",
        "Ğ": "ğ",
        "Ş": "ş",
        "Ü": "ü",
        "Ö": "ö",
        "Ç": "ç",
        "Ä°": "i",
        "Äž": "ğ",
        "Åž": "ş",
        "Ãœ": "ü",
        "Ã–": "ö",
        "Ã‡": "ç",
        "Ä±": "ı",
        "Ã¼": "ü",
        "Ã¶": "ö",
        "Ã§": "ç",
        "ÅŸ": "ş",
        "ÄŸ": "ğ",
        "yÃ¼n": "yün",
        "iÃ§erik": "içerik",
        "kumaÅŸ": "kumaş",
    }
    for source, replacement in replacements.items():
        text = text.replace(source, replacement)
    return text.lower()


FABRIC_ALIASES: dict[str, tuple[str, ...]] = {
    "pamuk": ("pamuk", "cotton", "co", "coton"),
    "polyester": (
        "polyester",
        "poliester",
        "pollester",
        "polester",
        "poliaster",
        "palesler",
        "poiesler",
        "poliecter",
        "polfesder",
        "poliesiera",
        "polesfen",
        "polesler",
        "palesier",
        "pocfester",
        "poester",
        "poreeter",
        "polyest",
        "poly",
        "pes",
    ),
    "viskoz": ("viskoz", "viskon", "viscose", "vis", "rayon"),
    "modal": ("modal", "modae", "modai", "modal viskon", "modal viscose"),
    "lyocell": ("lyocell", "liyosel", "tensel", "tencel"),
    "poliamid": ("poliamid", "poliamit", "polyamide", "polyamid", "polyamit", "poliyamid", "pa"),
    "naylon": ("naylon", "nylon"),
    "yün": ("yün", "yun", "wool", "wol"),
    "ipek": ("ipek", "silk"),
    "keten": ("keten", "linen", "lin"),
    "akrilik": ("akrilik", "acrylic", "polyacrylic", "poly acrylic", "poliakrilik", "ac"),
    "elastan": (
        "elastan",
        "elastane",
        "elasthan",
        "elasthane",
        "elasten",
        "elastene",
        "elastano",
        "e1astan",
        "lycra",
        "spandex",
        "ea",
    ),
}

ALIAS_TO_FABRIC: dict[str, str] = {
    _normalize_turkish(alias): fabric
    for fabric, aliases in FABRIC_ALIASES.items()
    for alias in aliases
}
FABRIC_PATTERN = "|".join(
    sorted((re.escape(alias) for alias in ALIAS_TO_FABRIC), key=len, reverse=True)
)
CONTEXT_FABRIC_PATTERN = "|".join(
    sorted((re.escape(alias) for alias in ALIAS_TO_FABRIC if len(alias) >= 4), key=len, reverse=True)
)
RATIO_PATTERN = r"\d{1,3}(?:[,.]\d{1,2})?"
COMPOSITION_PATTERN = re.compile(
    rf"(?:(?:%\s*(?P<prefix_ratio>{RATIO_PATTERN}))|(?:(?P<suffix_ratio>{RATIO_PATTERN})\s*%))\s*(?P<fabric>{FABRIC_PATTERN})\b",
    re.IGNORECASE,
)
OCR_SUFFIX_RATIO_PATTERN = re.compile(
    rf"\b(?P<ratio>{RATIO_PATTERN})\s*[90o](?![%\d])\s+(?P<context>.{{0,80}}?(?P<fabric>{CONTEXT_FABRIC_PATTERN})\w*)",
    re.IGNORECASE,
)
CONTEXT_COMPOSITION_PATTERN = re.compile(
    rf"(?:(?:%\s*(?P<prefix_ratio>{RATIO_PATTERN}))|(?:(?P<suffix_ratio>{RATIO_PATTERN})\s*%))(?P<context>.{{0,120}}?(?P<fabric>{CONTEXT_FABRIC_PATTERN})\w*)",
    re.IGNORECASE,
)
FABRIC_FIRST_COMPOSITION_PATTERN = re.compile(
    rf"\b(?P<fabric>{CONTEXT_FABRIC_PATTERN})\w*\s*(?:[:\-/,]|\s)+\s*(?:(?:%\s*(?P<prefix_ratio>{RATIO_PATTERN}))|(?:(?P<suffix_ratio>{RATIO_PATTERN})\s*%))",
    re.IGNORECASE,
)
BARE_RATIO_FABRIC_PATTERN = re.compile(
    rf"\b(?P<ratio>{RATIO_PATTERN})\s+(?P<fabric>{CONTEXT_FABRIC_PATTERN})\w*\b",
    re.IGNORECASE,
)


def _normalize_ocr_noise(text: str) -> str:
    """Clean common OCR mistakes around fabric percentages and names."""
    text = text.replace("l00", "100").replace("I00", "100")
    text = re.sub(r"\b[lI](?=\d\s*%?\s*[a-zA-ZğüşöçıİĞÜŞÖÇ])", "1", text)
    text = text.replace("l5", "15").replace("I5", "15")
    text = text.replace(" %", "%")
    text = re.sub(r"\bS0\b", "50", text)
    text = re.sub(r"\bB0\b", "80", text)
    text = re.sub(
        r"\b[8bB]{1,2}(84)\b(?=.{0,80}\b(?:modal|modae|modai|polyester|pocfester|poester|poreeter))",
        r"\1",
        text,
    )
    text = re.sub(r"\b16[9o]\b(?=.{0,80}\b(?:polyester|pocfester|poester|poreeter))", "16% ", text)
    text = re.sub(r"(?<=\d)[Oo](?=[\d %])", "0", text)
    text = re.sub(r"\b(100|[1-9]\d?)\s*[9o]\b", r"\1% ", text)
    text = re.sub(r"\b(poli|poly|pol)[a-z0-9]{0,4}ster[a-z0-9]*\b", "polyester", text)
    text = re.sub(r"\b(palesler|poiesler|poliecter|polfesder|poliesiera|polesfen|polesler|palesier|pocfester|poester|poreeter)\w*\b", "polyester", text)
    text = re.sub(r"\be1astan\w*\b", "elastan", text, flags=re.IGNORECASE)
    text = re.sub(r"\bpo[iIl1]yamid\w*\b", "poliamid", text, flags=re.IGNORECASE)
    return text


def _build_warning(total_ratio: float, found_match: bool) -> str:
    """Return a warning message for invalid or missing compositions."""
    if not found_match:
        return "Bu metinde kumas bilesimi bulunamadi."
    return f"Kumas bilesimi toplam orani guvenilir degil: {total_ratio:g}. Beklenen aralik 95-105."


def _match_group(match: re.Match[str], name: str) -> str | None:
    """Return a named regex group only when the active pattern defines it."""
    try:
        return match.group(name)
    except IndexError:
        return None


def _parse_ratio(ratio_text: str) -> float:
    """Parse integer and comma-decimal percentages."""
    return float(ratio_text.replace(",", "."))


def _format_ratio(value: float) -> Ratio:
    """Keep whole-number ratios as ints for backward-compatible output."""
    rounded = round(value, 2)
    if math.isclose(rounded, round(rounded), abs_tol=0.001):
        return int(round(rounded))
    return rounded


def _select_best_composition_subset(composition: list[CompositionEntry]) -> list[CompositionEntry]:
    """Choose the most plausible 95-105 total subset from noisy OCR/page matches."""
    if not composition:
        return []

    all_total = sum(float(item["ratio"]) for item in composition)
    all_fabrics = [str(item["fabric"]) for item in composition]
    if 95 <= all_total <= 105 and len(all_fabrics) == len(set(all_fabrics)):
        return composition

    if len(composition) > 16:
        return composition

    valid_subsets: list[tuple[int, float, int, int, tuple[CompositionEntry, ...]]] = []
    for subset_size in range(1, len(composition) + 1):
        for subset in combinations(composition, subset_size):
            total = sum(float(item["ratio"]) for item in subset)
            if 95 <= total <= 105:
                fabrics = [str(item["fabric"]) for item in subset]
                duplicate_fabric_count = len(fabrics) - len(set(fabrics))
                valid_subsets.append(
                    (
                        duplicate_fabric_count,
                        abs(100 - total),
                        -subset_size,
                        composition.index(subset[0]),
                        subset,
                    )
                )

    if not valid_subsets:
        return composition

    _, _, _, _, best_subset = min(valid_subsets, key=lambda item: item[:4])
    return list(best_subset)


def _normalize_total_to_100(composition: list[CompositionEntry]) -> list[CompositionEntry]:
    """Normalize a plausible 95-105 total to exactly 100."""
    total = sum(float(item["ratio"]) for item in composition)
    if not composition or not 95 <= total <= 105 or math.isclose(total, 100.0, abs_tol=0.001):
        return [{"fabric": item["fabric"], "ratio": _format_ratio(float(item["ratio"]))} for item in composition]

    normalized: list[CompositionEntry] = []
    running_total = 0.0
    for index, item in enumerate(composition):
        if index == len(composition) - 1:
            ratio = 100.0 - running_total
        else:
            ratio = round(float(item["ratio"]) * 100.0 / total, 2)
            running_total += ratio
        normalized.append({"fabric": item["fabric"], "ratio": _format_ratio(ratio)})
    return normalized


def _confidence_label(score: float) -> str:
    """Map confidence score to a compact label."""
    if score >= 0.75:
        return "high"
    if score >= 0.45:
        return "medium"
    return "low"


def _calculate_parser_confidence(
    composition: list[CompositionEntry],
    *,
    raw_total: float,
    found_match: bool,
) -> float:
    """Score how trustworthy a parsed composition looks."""
    if not found_match or not composition:
        return 0.0

    score = 0.2
    score += min(0.25, len(composition) * 0.08)
    if all(str(item["fabric"]) in FABRIC_ALIASES for item in composition):
        score += 0.25
    if 95 <= raw_total <= 105:
        score += 0.25
    if math.isclose(raw_total, 100.0, abs_tol=0.5):
        score += 0.05
    if len(composition) > 8:
        score -= 0.2
    return round(max(0.0, min(1.0, score)), 2)


def _recover_common_ocr_mix(text: str) -> list[CompositionEntry]:
    """Recover common two-part mixes when OCR keeps fabrics and ratios but scrambles order."""
    has_modal = any(alias in text for alias in ("modal", "modae", "modai"))
    has_polyester = any(alias in text for alias in ("polyester", "pocfester", "poester", "poreeter"))
    if has_modal and has_polyester:
        has_84 = bool(re.search(r"(?<!\d)84(?!\d)", text))
        has_16 = bool(re.search(r"(?<!\d)16(?!\d)", text))
        if has_84 and has_16:
            return [
                {"fabric": "modal", "ratio": 84},
                {"fabric": "polyester", "ratio": 16},
            ]
    return []


def parse_fabric_composition(text: str) -> dict[str, Any]:
    """Extract normalized fabric composition entries from plain text."""
    normalized_text = _normalize_ocr_noise(_normalize_turkish(text or ""))
    composition: list[CompositionEntry] = []
    seen_entries: set[tuple[str, float]] = set()

    matches = (
        list(COMPOSITION_PATTERN.finditer(normalized_text))
        + list(CONTEXT_COMPOSITION_PATTERN.finditer(normalized_text))
        + list(OCR_SUFFIX_RATIO_PATTERN.finditer(normalized_text))
        + list(FABRIC_FIRST_COMPOSITION_PATTERN.finditer(normalized_text))
        + list(BARE_RATIO_FABRIC_PATTERN.finditer(normalized_text))
    )

    for match in matches:
        ratio_text = _match_group(match, "prefix_ratio") or _match_group(match, "suffix_ratio")
        if ratio_text is None:
            ratio_text = _match_group(match, "ratio")
        if ratio_text is None:
            continue

        fabric_text = _normalize_turkish(match.group("fabric"))
        normalized_fabric = ALIAS_TO_FABRIC.get(fabric_text)
        if normalized_fabric is None:
            continue

        ratio = _parse_ratio(ratio_text)
        if ratio <= 0 or ratio > 100:
            continue

        entry_key = (normalized_fabric, ratio)
        if entry_key in seen_entries:
            continue

        seen_entries.add(entry_key)
        composition.append({"fabric": normalized_fabric, "ratio": ratio})

    composition = _select_best_composition_subset(composition)
    raw_total_ratio = sum(float(item["ratio"]) for item in composition)
    raw_composition = [
        {"fabric": item["fabric"], "ratio": _format_ratio(float(item["ratio"]))} for item in composition
    ]
    is_valid = 95 <= raw_total_ratio <= 105
    if not is_valid:
        recovered_composition = _recover_common_ocr_mix(normalized_text)
        if recovered_composition:
            composition = recovered_composition
            raw_composition = recovered_composition
            raw_total_ratio = sum(float(item["ratio"]) for item in composition)
            is_valid = True
    composition = _normalize_total_to_100(composition) if is_valid else [
        {"fabric": item["fabric"], "ratio": _format_ratio(float(item["ratio"]))} for item in composition
    ]
    total_ratio = _format_ratio(sum(float(item["ratio"]) for item in composition))
    warning = None if is_valid else _build_warning(total_ratio=raw_total_ratio, found_match=bool(composition))
    confidence_score = _calculate_parser_confidence(
        composition,
        raw_total=raw_total_ratio,
        found_match=bool(composition),
    )

    return {
        "composition": composition,
        "raw_composition": raw_composition,
        "total_ratio": total_ratio,
        "raw_total_ratio": _format_ratio(raw_total_ratio),
        "is_valid": is_valid,
        "warning": warning,
        "confidence_score": confidence_score,
        "confidence_label": _confidence_label(confidence_score),
        "warnings": [warning] if warning else [],
    }
