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
