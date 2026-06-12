from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.ocr.fabric_parser import parse_fabric_composition


def test_parse_polyacrylic_amazon_material_text() -> None:
    """Parse Amazon-style glued material composition text."""
    result = parse_fabric_composition("Malzeme Bileşimi%73POLYACRYLIC,%27POLYESTER")

    assert result["composition"] == [
        {"fabric": "akrilik", "ratio": 73},
        {"fabric": "polyester", "ratio": 27},
    ]
    assert result["total_ratio"] == 100
    assert result["is_valid"] is True


def test_parse_rotated_label_ocr_polyester_noise() -> None:
    """Parse noisy OCR text where percent and polyester are misread."""
    result = parse_fabric_composition(
        "EXTERIOR-EXTERIEUR-OUTER 1009 5=222 'J-poliaster-Ri#f#-#2Jol4 jy"
    )

    assert result["composition"] == [{"fabric": "polyester", "ratio": 100}]
    assert result["total_ratio"] == 100
    assert result["is_valid"] is True


def test_parse_noisy_label_poliesterra_suffix() -> None:
    """Parse polyester when OCR adds trailing letters after the material name."""
    result = parse_fabric_composition(
        "100% @@eeeiossn AUSSEN-YDRE LINING goyeste poliesi8Ao Mpolester 1009 uuadou pollester-poliesterra"
    )

    assert result["composition"] == [{"fabric": "polyester", "ratio": 100}]
    assert result["total_ratio"] == 100
    assert result["is_valid"] is True


def test_parser_selects_valid_product_subset_from_page_noise() -> None:
    """Ignore extra page text when one contiguous product composition totals 100."""
    result = parse_fabric_composition(
        "Materyal %17 naylon %74 akrilik %9 polyester Populer aramalar %100 pamuk %10 pamuk"
    )

    assert result["composition"] == [
        {"fabric": "naylon", "ratio": 17},
        {"fabric": "akrilik", "ratio": 74},
        {"fabric": "polyester", "ratio": 9},
    ]
    assert result["total_ratio"] == 100
    assert result["is_valid"] is True


def test_parser_ignores_spurious_label_ratio_when_exact_total_exists() -> None:
    """Prefer the valid 100% material over an OCR side-reading such as 24% polyester."""
    result = parse_fabric_composition("24% polyester EXTERIOR OUTER 1009 poliaster")

    assert result["composition"] == [{"fabric": "polyester", "ratio": 100}]
    assert result["total_ratio"] == 100
    assert result["is_valid"] is True


def test_parser_reads_fabric_first_percentages() -> None:
    """Parse labels where the fabric name appears before its percentage."""
    result = parse_fabric_composition("Cotton 98% Elastane 2%")

    assert result["composition"] == [
        {"fabric": "pamuk", "ratio": 98},
        {"fabric": "elastan", "ratio": 2},
    ]
    assert result["total_ratio"] == 100
    assert result["is_valid"] is True


def test_parser_keeps_small_elastane_ratio_in_ratio_first_text() -> None:
    """Keep small elastane percentages when OCR reads a normal ratio-first label."""
    result = parse_fabric_composition("98% Cotton 2% Elasthane")

    assert result["composition"] == [
        {"fabric": "pamuk", "ratio": 98},
        {"fabric": "elastan", "ratio": 2},
    ]
    assert result["total_ratio"] == 100
    assert result["is_valid"] is True


def test_parser_reads_english_ratio_first_composition() -> None:
    """Parse a common English product composition sentence."""
    result = parse_fabric_composition("83% viscose 15% polyamide 2% elastane")

    assert result["composition"] == [
        {"fabric": "viskoz", "ratio": 83},
        {"fabric": "poliamid", "ratio": 15},
        {"fabric": "elastan", "ratio": 2},
    ]
    assert result["total_ratio"] == 100
    assert result["confidence_label"] == "high"


def test_parser_reads_turkish_prefix_percent_composition() -> None:
    """Parse Turkish labels where percent appears before the number."""
    result = parse_fabric_composition("%83 viskoz %15 poliamid %2 elastan")

    assert result["composition"] == [
        {"fabric": "viskoz", "ratio": 83},
        {"fabric": "poliamid", "ratio": 15},
        {"fabric": "elastan", "ratio": 2},
    ]
    assert result["total_ratio"] == 100
    assert result["is_valid"] is True


def test_parser_repairs_l_digit_ocr_ratio_noise() -> None:
    """Repair OCR reading l5 as 15 before a fabric name."""
    result = parse_fabric_composition("83% viskoz l5 poliamid 2% elastan")

    assert {"fabric": "poliamid", "ratio": 15} in result["composition"]
    assert result["total_ratio"] == 100
    assert result["is_valid"] is True


def test_parser_normalizes_comma_decimal_total() -> None:
    """Support decimal comma percentages."""
    result = parse_fabric_composition("83,5% viscose 14,5% polyamide 2% elastane")

    assert result["composition"] == [
        {"fabric": "viskoz", "ratio": 83.5},
        {"fabric": "poliamid", "ratio": 14.5},
        {"fabric": "elastan", "ratio": 2},
    ]
    assert result["total_ratio"] == 100
    assert result["confidence_label"] == "high"


def test_parser_does_not_guess_without_fabric_composition() -> None:
    """Do not infer fabric from unrelated product text."""
    result = parse_fabric_composition("Siyah elbise regular fit kampanya fiyat")

    assert result["composition"] == []
    assert result["total_ratio"] == 0
    assert result["is_valid"] is False
    assert result["confidence_score"] == 0.0


def test_parser_repairs_noisy_polyester_from_long_label_ocr() -> None:
    """Parse polyester when long-label OCR distorts polyester heavily."""
    result = parse_fabric_composition("VEae 1009 68818g8s328isstonef8RE 59REYA Mpalesler-Rera")

    assert result["composition"] == [{"fabric": "polyester", "ratio": 100}]
    assert result["is_valid"] is True
    assert result["confidence_label"] == "high"


def test_parser_recovers_modal_polyester_from_scrambled_label_ocr() -> None:
    """Recover 84 modal / 16 polyester when OCR scrambles a multilingual label line."""
    result = parse_fabric_composition(
        "16% TonecTenere WABag 8884 ANA ModAE POCFESTER k ReNKLERUE"
    )

    assert result["composition"] == [
        {"fabric": "modal", "ratio": 84},
        {"fabric": "polyester", "ratio": 16},
    ]
    assert result["is_valid"] is True
