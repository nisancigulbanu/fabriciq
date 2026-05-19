from scoring.quality_score import calculate_quality_score

testler = [
    [{"fabric": "pamuk", "ratio": 60}, {"fabric": "polyester", "ratio": 40}],
    [{"fabric": "ipek", "ratio": 100}],
    [{"fabric": "polyester", "ratio": 100}],
    [{"fabric": "pamuk", "ratio": 84}, {"fabric": "elastan", "ratio": 16}],
    [{"fabric": "yün", "ratio": 70}, {"fabric": "akrilik", "ratio": 30}],
]

for kompozisyon in testler:
    sonuc = calculate_quality_score(kompozisyon)
    print(f"Kumaş: {kompozisyon}")
    print(f"Skor: {sonuc['quality_score']} | Not: {sonuc['grade']} | Doğal: %{sonuc['natural_ratio']} | Sentetik: %{sonuc['synthetic_ratio']}\n")