from ocr.fabric_parser import parse_fabric_composition

testler = [
    "%60 Pamuk %40 Polyester",
    "60% Cotton 40% PES",
    "84% POLYESTER 16% ELASTAN",
    "%100 Pamuk",
    "50% Viskon 30% Naylon 20% Elastan",
    "80% Cotton 10% Polyester",  # toplam 90, is_valid False olmalı
]

for metin in testler:
    sonuc = parse_fabric_composition(metin)
    print(f"\nGirdi: {metin}")
    print(f"Kompozisyon: {sonuc['composition']}")
    print(f"Toplam: {sonuc['total_ratio']} | Geçerli: {sonuc['is_valid']}")
    if sonuc['warning']:
        print(f"⚠️ {sonuc['warning']}")

        # Yeni test
metin = "DIş %84 VİSKOZ, %16 POLİAMİD"
sonuc = parse_fabric_composition(metin)
print(f"\nGirdi: {metin}")
print(f"Kompozisyon: {sonuc['composition']}")
print(f"Toplam: {sonuc['total_ratio']} | Geçerli: {sonuc['is_valid']}")
if sonuc['warning']:
    print(f"⚠️ {sonuc['warning']}")