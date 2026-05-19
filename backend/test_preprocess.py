# backend/test_preprocess.py
from ocr.preprocessor import preprocess_image
import cv2

result = preprocess_image("image.png")
print("Shape:", result.shape)
print("Dtype:", result.dtype)

# Sonucu kaydet ve gözle kontrol et
cv2.imwrite("processed_output.png", result)