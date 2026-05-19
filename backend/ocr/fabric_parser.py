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
    "polyester": ("polyester", "pes", "poly"),
    "viskon": ["viskon", "viscose", "vis", "rayon", "viskoz"],
    "naylon": ["naylon", "nylon", "pa", "poliamid", "polyamide"],
    "yun": ("yun", "yün", "wool", "wol"),
    "ipek": ("ipek", "silk"),
    "keten": ("keten", "linen", "lin"),
    "akrilik": ("akrilik", "acrylic", "ac"),
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
COMPOSITION_PATTERN = re.compile(
    rf"(?:(?:%\s*(?P<prefix_ratio>\d{{1,3}}))|(?:(?P<suffix_ratio>\d{{1,3}})\s*%))\s*(?P<fabric>{FABRIC_PATTERN})\b",
    re.IGNORECASE,
)

def _build_warning(total_ratio: int, found_match: bool) -> str:
    """Return a warning message for invalid or missing compositions."""
    if not found_match:
        return "Fabric composition could not be extracted from the provided text."

    return f"Fabric composition total ratio is invalid: {total_ratio}. Expected a total between 95 and 105."


def parse_fabric_composition(text: str) -> dict[str, Any]:
    """Extract normalized fabric composition entries from plain text."""
    text = _normalize_turkish(text)
    composition: list[dict[str, int | str]] = []
    seen_entries: set[tuple[str, int]] = set()

    for match in COMPOSITION_PATTERN.finditer(text):
        ratio_text = match.group("prefix_ratio") or match.group("suffix_ratio")
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
