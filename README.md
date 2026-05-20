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
| Dynamic URL analysis | Done |
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
python -m playwright install chromium
python -m uvicorn backend.main:app --reload
```

Open API docs:

```text
http://127.0.0.1:8000/docs
```

Open the local web interface. It supports both product URL analysis and label image upload:

```text
http://127.0.0.1:8000/
```

## API

### `GET /health`

Returns service status.

### `GET /`

Serves the local analysis interface for product URLs and label image uploads.

### `POST /analyze/label`

Request: `multipart/form-data` with a `file` field.

```powershell
curl -X POST "http://127.0.0.1:8000/analyze/label" `
  -F "file=@etiket_foto.jpg"
```

If OCR confidence is low or no valid fabric composition can be parsed, the response includes an `advice` message asking the user to retake the label photo with better lighting, a straight angle, and sharper text.

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

Dynamic pages are handled with Selenium first and Playwright as a fallback. Some stores may still block browser-based scraping at the edge/CDN layer. Current blocked response:

```json
{
  "success": false,
  "error": "Page blocked browser-based scraping"
}
```

## URL Parser Flow

1. `backend/url_parser/detector.py` fetches the page with `requests`.
2. It checks for JSON-LD or product detail areas that include fabric-related terms.
3. If static fabric data is available, `backend/url_parser/static.py` extracts plain text from JSON-LD and CSS-selected product detail blocks.
4. `backend/url_parser/extractor.py` returns that plain text to the shared fabric parser.
5. If static text cannot be parsed into a composition, `backend/url_parser/selenium_dynamic.py` tries Selenium Chrome.
6. If Selenium cannot extract fabric text, `backend/url_parser/dynamic.py` tries Playwright.
7. If the site blocks browser-based scraping too, the API returns a clear blocked-page error.

## Debug Endpoints

These endpoints are for local development only:

- `GET /debug/runtime`: shows the Python executable and browser-scraping dependency availability.
- `POST /debug/url-text`: shows the raw text Selenium can see for a URL, plus fabric keyword matches.

## Testing

```powershell
pytest backend\tests\test_analyze_label.py
```

Current verified status:

```text
6 passed
```

## Next Work

1. Add richer dynamic-page extraction for product detail accordions and lazy content.
2. Add site-specific selector tuning for Zara, Trendyol, H&M, and similar dynamic stores.
3. Add integration tests for Playwright/Selenium fallback where browser runtime is available.
4. Add optional browser profile support for sites that require a real logged-in/localized session.
