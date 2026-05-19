from __future__ import annotations

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
