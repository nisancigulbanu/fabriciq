"""Product-aware quality and sustainability scoring for fabric compositions."""

from __future__ import annotations

import re
from typing import Any

FORMULA_VERSION = "kp_sp_v1"
PERFORMANCE_WEIGHT = 0.6
SUSTAINABILITY_WEIGHT = 0.4

KP_BASE: dict[str, int] = {
    "merino_yun": 95,
    "ipek": 92,
    "kasmir": 90,
    "keten": 82,
    "uzun_elyaf_pamuk": 80,
    "organik_pamuk": 76,
    "pamuk": 72,
    "modal": 74,
    "lyocell": 78,
    "bambu_viskon": 65,
    "viskon": 60,
    "viskoz": 60,
    "asetat": 55,
    "akrilik": 52,
    "poliamid": 70,
    "naylon": 70,
    "polyester": 62,
    "rpet": 68,
    "elastan": 85,
    "yun": 80,
    "yün": 80,
    "kenevir": 75,
    "polipropilen": 48,
}

SP_BASE: dict[str, int] = {
    "organik_kenevir": 90,
    "keten": 87,
    "lyocell": 85,
    "organik_pamuk": 78,
    "merino_yun": 73,
    "rpet": 72,
    "modal": 70,
    "bambu_viskon": 62,
    "yun": 60,
    "yün": 60,
    "kenevir": 68,
    "ipek": 65,
    "pamuk": 48,
    "uzun_elyaf_pamuk": 48,
    "viskon": 42,
    "viskoz": 42,
    "akrilik": 30,
    "polyester": 35,
    "poliamid": 40,
    "naylon": 40,
    "elastan": 28,
    "kasmir": 52,
    "polipropilen": 32,
    "asetat": 45,
}

NATURAL_FABRICS = {
    "ipek",
    "kasmir",
    "merino_yun",
    "yun",
    "yün",
    "keten",
    "pamuk",
    "uzun_elyaf_pamuk",
    "organik_pamuk",
    "kenevir",
    "organik_kenevir",
}
SYNTHETIC_FABRICS = {
    "viskon",
    "viskoz",
    "bambu_viskon",
    "modal",
    "lyocell",
    "elastan",
    "akrilik",
    "naylon",
    "poliamid",
    "polyester",
    "rpet",
    "polipropilen",
    "asetat",
}

PRODUCT_COEFFICIENTS: dict[str, dict[str, float]] = {
    "activewear": {
        "pamuk": 0.70,
        "polyester": 1.10,
        "rpet": 1.10,
        "naylon": 1.20,
        "poliamid": 1.20,
        "elastan": 1.30,
        "yun": 0.60,
        "yün": 0.60,
        "lyocell": 0.80,
        "viskon": 0.60,
        "viskoz": 0.60,
        "akrilik": 0.50,
    },
    "knitwear": {
        "pamuk": 0.90,
        "polyester": 0.60,
        "naylon": 0.75,
        "poliamid": 0.75,
        "elastan": 0.40,
        "yun": 1.30,
        "yün": 1.30,
        "merino_yun": 1.30,
        "kasmir": 1.25,
        "lyocell": 0.85,
        "viskon": 0.80,
        "viskoz": 0.80,
        "akrilik": 0.85,
    },
    "tshirt_underwear": {
        "pamuk": 1.20,
        "organik_pamuk": 1.20,
        "polyester": 0.75,
        "naylon": 0.80,
        "poliamid": 0.80,
        "elastan": 0.70,
        "yun": 0.85,
        "yün": 0.85,
        "lyocell": 1.10,
        "modal": 1.10,
        "viskon": 0.95,
        "viskoz": 0.95,
        "akrilik": 0.60,
    },
    "shirt_blouse": {
        "pamuk": 1.10,
        "polyester": 0.80,
        "naylon": 0.85,
        "poliamid": 0.85,
        "elastan": 0.65,
        "yun": 0.90,
        "yün": 0.90,
        "lyocell": 1.15,
        "viskon": 1.10,
        "viskoz": 1.10,
        "keten": 1.15,
        "akrilik": 0.55,
    },
    "denim": {
        "pamuk": 1.25,
        "polyester": 0.65,
        "naylon": 0.70,
        "poliamid": 0.70,
        "elastan": 0.75,
        "yun": 0.50,
        "yün": 0.50,
        "lyocell": 0.70,
        "viskon": 0.65,
        "viskoz": 0.65,
        "akrilik": 0.40,
    },
    "outerwear": {
        "pamuk": 0.85,
        "polyester": 1.15,
        "rpet": 1.15,
        "naylon": 1.10,
        "poliamid": 1.10,
        "elastan": 0.50,
        "yun": 1.05,
        "yün": 1.05,
        "lyocell": 0.80,
        "viskon": 0.70,
        "viskoz": 0.70,
        "akrilik": 0.90,
    },
    "swimwear": {
        "pamuk": 0.40,
        "polyester": 1.05,
        "rpet": 1.05,
        "naylon": 1.25,
        "poliamid": 1.25,
        "elastan": 1.30,
        "yun": 0.30,
        "yün": 0.30,
        "lyocell": 0.50,
        "viskon": 0.40,
        "viskoz": 0.40,
        "akrilik": 0.55,
    },
    "socks": {
        "pamuk": 1.05,
        "polyester": 0.80,
        "naylon": 1.15,
        "poliamid": 1.15,
        "elastan": 0.90,
        "yun": 1.20,
        "yün": 1.20,
        "merino_yun": 1.25,
        "lyocell": 0.70,
        "viskon": 0.65,
        "viskoz": 0.65,
        "akrilik": 0.85,
    },
    "officewear": {
        "pamuk": 1.15,
        "polyester": 0.70,
        "naylon": 0.80,
        "poliamid": 0.80,
        "elastan": 0.60,
        "yun": 1.10,
        "yün": 1.10,
        "lyocell": 1.10,
        "viskon": 1.00,
        "viskoz": 1.00,
        "akrilik": 0.50,
    },
    "baby_kids": {
        "pamuk": 1.30,
        "organik_pamuk": 1.35,
        "polyester": 0.50,
        "naylon": 0.55,
        "poliamid": 0.55,
        "elastan": 0.65,
        "yun": 1.00,
        "yün": 1.00,
        "lyocell": 1.15,
        "viskon": 0.75,
        "viskoz": 0.75,
        "akrilik": 0.40,
    },
    "home_textile": {
        "pamuk": 1.25,
        "polyester": 0.70,
        "naylon": 0.75,
        "poliamid": 0.75,
        "elastan": 0.40,
        "yun": 0.90,
        "yün": 0.90,
        "lyocell": 1.10,
        "viskon": 0.95,
        "viskoz": 0.95,
        "akrilik": 0.45,
    },
    "general": {},
}

PRODUCT_TYPE_KEYWORDS: dict[str, set[str]] = {
    "activewear": {
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
        "koşu",
        "spor",
        "yoga",
    },
    "knitwear": {"kazak", "triko", "hırka", "hirka", "sweater", "knitwear", "knit", "jumper"},
    "tshirt_underwear": {"tshirt", "t-shirt", "tişört", "tisort", "polo", "iç", "ic", "underwear", "atlet"},
    "shirt_blouse": {"gömlek", "gomlek", "bluz", "shirt", "blouse"},
    "denim": {"kot", "denim", "jean", "jeans"},
    "outerwear": {"mont", "ceket", "kaban", "outerwear", "coat", "jacket", "parka"},
    "swimwear": {"mayo", "bikini", "swimwear", "swimsuit"},
    "socks": {"çorap", "corap", "sock", "socks"},
    "officewear": {"ofis", "office", "takım", "takim", "suit", "business"},
    "baby_kids": {"bebek", "çocuk", "cocuk", "baby", "kids", "child"},
    "home_textile": {"çarşaf", "carsaf", "nevresim", "sheet", "home", "textile"},
}

PRODUCT_TYPE_KEYWORDS["baby_kids"].update({"zibin"})

PRODUCT_TYPE_ALIASES = {
    "winter": "knitwear",
    "underwear": "tshirt_underwear",
    "tshirt": "tshirt_underwear",
    "t-shirt": "tshirt_underwear",
    "shirt": "shirt_blouse",
    "blouse": "shirt_blouse",
    "sweater": "knitwear",
    "knit": "knitwear",
    "legging": "activewear",
    "leggings": "activewear",
    "tayt": "activewear",
    "swim": "swimwear",
    "sock": "socks",
    "kids": "baby_kids",
    "baby": "baby_kids",
}

PRODUCT_TYPE_PRIORITY = (
    "baby_kids",
    "tshirt_underwear",
    "shirt_blouse",
    "denim",
    "knitwear",
    "outerwear",
    "swimwear",
    "socks",
    "officewear",
    "home_textile",
    "activewear",
)


def _grade_for_score(score: float) -> str:
    """Map a numeric score to a letter grade."""
    if score >= 85:
        return "A"
    if score >= 70:
        return "B"
    if score >= 55:
        return "C"
    if score >= 40:
        return "D"
    return "F"


def _category_for_score(score: float) -> str:
    """Return a human-readable score category."""
    if score >= 85:
        return "Mükemmel"
    if score >= 70:
        return "İyi"
    if score >= 55:
        return "Orta"
    if score >= 40:
        return "Düşük"
    return "Yetersiz"


def _normalize_fabric(fabric: str) -> str:
    """Normalize parser output and common aliases to scoring keys."""
    normalized = fabric.strip().lower()
    if normalized in {
        "y" + chr(227) + chr(188) + "n",
        "y" + chr(227) + chr(131) + chr(194) + chr(188) + "n",
        "y" + chr(227) + chr(131) + chr(226) + chr(188) + "n",
    }:
        return "yün"
    alias_map = {
        "nylon": "naylon",
        "polyamide": "poliamid",
        "polyamid": "poliamid",
        "viscose": "viskoz",
        "rayon": "viskoz",
        "liyosel": "lyocell",
        "tencel": "lyocell",
        "spandex": "elastan",
        "lycra": "elastan",
        "poliester": "polyester",
        "geri dönüştürülmüş polyester": "rpet",
        "geri donusturulmus polyester": "rpet",
        "recycled polyester": "rpet",
        "recycled polyamide": "poliamid",
    }
    return alias_map.get(normalized, normalized)


def _tokens(text: str) -> set[str]:
    """Return simple lower-case tokens from product context."""
    normalized = re.sub(r"[_/?=&.]+", " ", text.lower())
    return set(re.findall(r"[a-zA-ZğüşöçıİĞÜŞÖÇ]+", normalized))


def _product_type_from_tokens(context_tokens: set[str]) -> str | None:
    """Return the first product type matching a token set."""
    for product_type in PRODUCT_TYPE_PRIORITY:
        keywords = PRODUCT_TYPE_KEYWORDS[product_type]
        if context_tokens & keywords:
            return product_type
    return None


def _normalize_product_type(product_context: str | None) -> str:
    """Infer or normalize a product type from explicit type or free text."""
    context = (product_context or "").strip().lower()
    if not context:
        return "general"
    if context in PRODUCT_COEFFICIENTS:
        return context
    if context in PRODUCT_TYPE_ALIASES:
        return PRODUCT_TYPE_ALIASES[context]

    if context.startswith("url_product_hint "):
        primary_context = context.splitlines()[0]
        primary_product_type = _product_type_from_tokens(_tokens(primary_context))
        if primary_product_type:
            return primary_product_type

    context_tokens = _tokens(context)
    return _product_type_from_tokens(context_tokens) or "general"


def _composition_ratio(composition: list[dict[str, int | float | str]], fabric_names: set[str]) -> float:
    """Return total ratio for a group of normalized fabric names."""
    total = 0.0
    for item in composition:
        fabric = _normalize_fabric(str(item.get("fabric", "")))
        if fabric not in fabric_names:
            continue
        try:
            total += float(item.get("ratio", 0))
        except (TypeError, ValueError):
            continue
    return total


def _blend_adjustment(
    composition: list[dict[str, int | float | str]],
    product_type: str,
) -> tuple[float, list[str]]:
    """Return product-specific blend adjustment and explanatory notes."""
    notes: list[str] = []
    polyester_ratio = _composition_ratio(composition, {"polyester", "rpet"})
    polyamide_ratio = _composition_ratio(composition, {"poliamid", "naylon"})
    elastane_ratio = _composition_ratio(composition, {"elastan"})
    cotton_ratio = _composition_ratio(composition, {"pamuk", "organik_pamuk", "uzun_elyaf_pamuk"})
    synthetic_performance_ratio = polyester_ratio + polyamide_ratio

    if product_type in {"activewear", "swimwear"}:
        if synthetic_performance_ratio >= 60 and 8 <= elastane_ratio <= 28:
            notes.append(
                "Performans ürünü bağlamında sentetik ana lif + elastan karışımı esneklik, hızlı kuruma ve form koruma açısından avantajlı değerlendirildi."
            )
            return 16.0, notes
        if synthetic_performance_ratio >= 80 and elastane_ratio == 0:
            notes.append("Sentetik ana lif performans için kabul edilebilir; elastan olmadığı için esneklik sınırlı kabul edildi.")
            return 4.0, notes
        if cotton_ratio >= 80:
            notes.append("Pamuk oranı bu ürün tipi için yüksek; nem tutma ve form kaybı nedeniyle performans puanı düşürüldü.")
            return -12.0, notes

    if product_type == "baby_kids" and (polyester_ratio + polyamide_ratio + _composition_ratio(composition, {"akrilik"})) >= 80:
        notes.append("Bebek/çocuk giyiminde yüksek sentetik oranı cilt konforu açısından dezavantajlı değerlendirildi.")
        return -10.0, notes

    return 0.0, notes


def calculate_quality_score(
    composition: list[dict[str, int | float | str]],
    product_context: str | None = None,
) -> dict[str, Any]:
    """Calculate product-aware performance, sustainability, and final score."""
    recognized_ratio_total = 0.0
    performance_score = 0.0
    sustainability_score = 0.0
    natural_ratio = 0.0
    synthetic_ratio = 0.0
    scoring_notes: list[str] = []
    unrecognized_fabrics: list[str] = []
    product_type = _normalize_product_type(product_context)
    coefficients = PRODUCT_COEFFICIENTS.get(product_type, {})

    for item in composition:
        raw_fabric = str(item.get("fabric", ""))
        fabric = _normalize_fabric(raw_fabric)
        try:
            ratio = float(item.get("ratio", 0))
        except (TypeError, ValueError):
            continue

        kp_base = KP_BASE.get(fabric)
        sp_base = SP_BASE.get(fabric)
        if kp_base is None or sp_base is None:
            unrecognized_fabrics.append(raw_fabric)
            continue

        recognized_ratio_total += ratio
        ratio_fraction = ratio / 100.0
        performance_score += ratio_fraction * kp_base * coefficients.get(fabric, 1.0)
        sustainability_score += ratio_fraction * sp_base

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
            "scoring_notes": ["Tanınan lif bulunamadığı için skor hesaplanamadı."],
            "score_details": {
                "performance_score": 0.0,
                "sustainability_score": 0.0,
                "final_score": 0.0,
                "category": "Yetersiz",
                "product_type": product_type,
                "formula_version": FORMULA_VERSION,
            },
        }

    if recognized_ratio_total and recognized_ratio_total != 100:
        scale = 100.0 / recognized_ratio_total
        performance_score *= scale
        sustainability_score *= scale

    blend_adjustment, blend_notes = _blend_adjustment(composition, product_type)
    final_score = (PERFORMANCE_WEIGHT * performance_score) + (SUSTAINABILITY_WEIGHT * sustainability_score) + blend_adjustment
    final_score = round(max(0.0, min(100.0, final_score)), 1)
    quality_score = int(final_score)

    if product_type != "general":
        scoring_notes.append(f"Ürün tipi bağlamı: {product_type}.")
    scoring_notes.extend(blend_notes)
    if unrecognized_fabrics:
        unique_unknowns = ", ".join(dict.fromkeys(unrecognized_fabrics))
        scoring_notes.append(f"Tanınmayan lifler skora dahil edilmedi: {unique_unknowns}.")

    return {
        "quality_score": quality_score,
        "grade": _grade_for_score(quality_score),
        "natural_ratio": round(natural_ratio),
        "synthetic_ratio": round(synthetic_ratio),
        "scoring_notes": scoring_notes,
        "score_details": {
            "performance_score": round(performance_score, 1),
            "sustainability_score": round(sustainability_score, 1),
            "final_score": final_score,
            "category": _category_for_score(final_score),
            "product_type": product_type,
            "formula_version": FORMULA_VERSION,
        },
    }
