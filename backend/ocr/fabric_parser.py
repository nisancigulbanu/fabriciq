"""Fabric composition parser for OCR and scraped text."""

from __future__ import annotations

import re
from typing import Any


def _normalize_turkish(text: str) -> str:
    """Türkçe büyük harfleri ASCII'ye yakın forma indir."""
    replacements = {
        "İ": "i", "I": "i",
        "Ğ": "ğ", "Ş": "ş",
        "Ü": "ü", "Ö": "ö", "Ç": "ç",
    }
    for src, dst in replacements.items():
        text = text.replace(src, dst)
    return text.lower()

FABRIC_ALIASES: dict[str, tuple[str, ...]] = {
    "pamuk": ("pamuk", "cotton", "co", "coton"),
    "polyester": (
        "polyester",
        "poliester",
        "pollester",
        "polester",
        "poliaster",
        "polyest",
        "poly",
        "pes",
    ),
    "viskon": ["viskon", "viscose", "vis", "rayon", "viskoz"],
    "naylon": ["naylon", "nylon", "pa", "poliamid", "polyamide"],
    "yun": ("yun", "yün", "wool", "wol"),
    "ipek": ("ipek", "silk"),
    "keten": ("keten", "linen", "lin"),
    "akrilik": ("akrilik", "acrylic", "polyacrylic", "poly acrylic", "poliakrilik", "ac"),
    "elastan": ("elastan", "elastane", "lycra", "spandex", "ea"),
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
COMPOSITION_PATTERN = re.compile(
    rf"(?:(?:%\s*(?P<prefix_ratio>\d{{1,3}}))|(?:(?P<suffix_ratio>\d{{1,3}})\s*%))\s*(?P<fabric>{FABRIC_PATTERN})\b",
    re.IGNORECASE,
)
OCR_SUFFIX_RATIO_PATTERN = re.compile(
    rf"\b(?P<ratio>\d{{1,3}})\s*[90o](?![%\d])\s+(?P<context>.{{0,80}}?(?P<fabric>{CONTEXT_FABRIC_PATTERN})\w*)",
    re.IGNORECASE,
)
CONTEXT_COMPOSITION_PATTERN = re.compile(
    rf"(?:(?:%\s*(?P<prefix_ratio>\d{{1,3}}))|(?:(?P<suffix_ratio>\d{{1,3}})\s*%))(?P<context>.{{0,120}}?(?P<fabric>{CONTEXT_FABRIC_PATTERN})\w*)",
    re.IGNORECASE,
)


def _normalize_ocr_noise(text: str) -> str:
    """Clean common OCR mistakes around fabric percentages and names."""
    text = re.sub(r"\b(100|[1-9]\d?)\s*[9o]\b", r"\1% ", text)
    text = re.sub(r"\b(poli|poly|pol)[a-z0-9]{0,4}ster[a-z0-9]*\b", "polyester", text)
    return text

def _build_warning(total_ratio: int, found_match: bool) -> str:
    """Return a warning message for invalid or missing compositions."""
    if not found_match:
        return "Fabric composition could not be extracted from the provided text."

    return f"Fabric composition total ratio is invalid: {total_ratio}. Expected a total between 95 and 105."


def _match_group(match: re.Match[str], name: str) -> str | None:
    """Return a named regex group only when the active pattern defines it."""
    try:
        return match.group(name)
    except IndexError:
        return None


def parse_fabric_composition(text: str) -> dict[str, Any]:
    """Extract normalized fabric composition entries from plain text."""
    text = _normalize_ocr_noise(_normalize_turkish(text))
    composition: list[dict[str, int | str]] = []
    seen_entries: set[tuple[str, int]] = set()

    matches = (
        list(COMPOSITION_PATTERN.finditer(text))
        + list(CONTEXT_COMPOSITION_PATTERN.finditer(text))
        + list(OCR_SUFFIX_RATIO_PATTERN.finditer(text))
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

        ratio = int(ratio_text)
        entry_key = (normalized_fabric, ratio)
        if entry_key in seen_entries:
            continue

        seen_entries.add(entry_key)
        composition.append(
            {
                "fabric": normalized_fabric,
                "ratio": ratio,
            }
        )

    total_ratio = sum(int(item["ratio"]) for item in composition)
    is_valid = 95 <= total_ratio <= 105
    warning = None if is_valid else _build_warning(total_ratio=total_ratio, found_match=bool(composition))

    return {
        "composition": composition,
        "total_ratio": total_ratio,
        "is_valid": is_valid,
        "warning": warning,
    }
