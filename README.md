# FabricIQ

FabricIQ is a FastAPI backend that analyzes textile labels and e-commerce product pages. It extracts fabric composition, normalizes material names, and calculates a rule-based quality score.

## Current Capabilities

| Feature | Status |
|---|---|
| Health check endpoint | Done |
| Label image analysis endpoint | Done |
| Image preprocessing | Done |
| OCR engine integration | Done |
| Fabric composition parser | Done |
| Quality scoring | Done |
| Static URL analysis | Done |
| Dynamic URL analysis | Planned |
| LLM advisor | Planned |

## Architecture

```text
Image upload or product URL
        |
        v
OCR / URL scraper
        |
        v
Fabric parser
        |
        v
Quality scorer
        |
        v
API response
```

The fabric parser is shared by OCR and URL flows. URL scrapers must return plain text; `backend/ocr/fabric_parser.py` remains the single source of truth for composition normalization.

## Setup

Run commands from the project root:

```powershell
cd C:\Users\gulba\Desktop\fabriciq
python -m pip install -r backend\requirements.txt
uvicorn backend.main:app --reload
```

Open API docs:

```text
http://127.0.0.1:8000/docs
```

## API

### `GET /health`

Returns service status.

### `POST /analyze/label`

Request: `multipart/form-data` with a `file` field.

```powershell
curl -X POST "http://127.0.0.1:8000/analyze/label" `
  -F "file=@etiket_foto.jpg"
```

### `POST /analyze/url`

Request body:

```json
{
  "url": "https://www.koton.com/uzun-kollu-bisiklet-yaka-viskon-triko-kazak-sari-4166045-2/"
}
```

Example response:

```json
{
  "success": true,
  "ocr": {
    "raw_text": "",
    "confident_text": "",
    "avg_confidence": 0.0
  },
  "fabric": {
    "composition": [
      { "fabric": "viskon", "ratio": 84 },
      { "fabric": "naylon", "ratio": 16 }
    ],
    "total_ratio": 100,
    "is_valid": true,
    "warning": null
  },
  "score": {
    "quality_score": 51,
    "grade": "F",
    "natural_ratio": 0,
    "synthetic_ratio": 100
  },
  "advice": null
}
```

Dynamic pages are not supported yet. Current dynamic fallback response:

```json
{
  "success": false,
  "error": "Dynamic pages not supported yet"
}
```

## URL Parser Flow

1. `backend/url_parser/detector.py` fetches the page with `requests`.
2. It checks for JSON-LD or product detail areas that include fabric-related terms.
3. If static fabric data is available, `backend/url_parser/static.py` extracts plain text from JSON-LD and CSS-selected product detail blocks.
4. `backend/url_parser/extractor.py` returns that plain text to the shared fabric parser.
5. If the page appears dynamic, dynamic scraping is currently not implemented.

## Testing

```powershell
pytest backend\tests\test_analyze_label.py
```

Current verified status:

```text
6 passed
```

## Next Work

1. Add `backend/url_parser/dynamic.py` with Playwright.
2. Route dynamic pages from `extractor.py` to the Playwright scraper.
3. Add clearer URL error classes for timeout, blocked pages, and no fabric text.
4. Add site-specific selector tuning for Zara, Trendyol, H&M, and similar dynamic stores.
