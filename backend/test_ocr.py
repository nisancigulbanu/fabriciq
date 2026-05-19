import easyocr

reader = easyocr.Reader(["tr", "en"])

result = reader.readtext("image.png",
                         detail=1,
                         paragraph=True)

for detection in result:
    bbox, text = detection  # paragraph modunda conf yok
    print(f"Metin: {text}")