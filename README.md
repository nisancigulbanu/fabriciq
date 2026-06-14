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
| LLM advisor | Done |

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

Optional Gemini configuration for the FabricIQ assistant:

```powershell
GEMINI_API_KEY=your_google_ai_studio_key
GEMINI_MODEL=gemini-3-flash-preview
GEMINI_MAX_OUTPUT_TOKENS=4096
GEMINI_THINKING_BUDGET=0
```

Gemini is not called automatically during URL or label analysis. The web UI sends an assistant request only when the user clicks the recommendation button or submits a question. If the Gemini API key is missing or the provider returns an unusable response, FabricIQ falls back to the deterministic local recommendation logic.

Open API docs:

```text
http://127.0.0.1:8000/docs
```

Open the local web interface. It supports both product URL analysis and label image upload:

```text
http://127.0.0.1:8000/
```

Backend logs are written to:

```text
logs/fabriciq.log
```

Follow them live in PowerShell:

```powershell
Get-Content logs\fabriciq.log -Wait
```

## API

### `GET /health`

Returns service status.

### `GET /`

Serves the local analysis interface for product URLs and label image uploads.

### `POST /analyze/label`

Request: `multipart/form-data` with a `file` field. Optional `product_type` values:

```text
general, activewear, knitwear, tshirt_underwear, shirt_blouse, denim,
outerwear, swimwear, socks, officewear, baby_kids, home_textile
```

```powershell
curl -X POST "http://127.0.0.1:8000/analyze/label" `
  -F "file=@etiket_foto.jpg" `
  -F "product_type=activewear"
```

If OCR confidence is low or no valid fabric composition can be parsed, the response includes an `advice` message asking the user to retake the label photo with better lighting, a straight angle, and sharper text.

### `POST /analyze/url`

Request body:

```json
{
  "url": "https://www.koton.com/uzun-kollu-bisiklet-yaka-viskon-triko-kazak-sari-4166045-2/",
  "product_type": "general"
}
```

`product_type` is optional. Use `general` or omit it to let FabricIQ infer context from the URL and scraped product text. Send one of the supported product types to override automatic URL context detection.

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
    "quality_score": 50,
    "grade": "D",
    "natural_ratio": 0,
    "synthetic_ratio": 100,
    "scoring_notes": [
      "Ürün tipi bağlamı: activewear."
    ],
    "score_details": {
      "performance_score": 57.2,
      "sustainability_score": 40.0,
      "final_score": 50.3,
      "category": "Düşük",
      "product_type": "activewear",
      "formula_version": "kp_sp_v1"
    }
  },
  "advice": null
}
```

Quality scoring uses a product-aware KP/SP model:

```text
final_score = 0.6 * performance_score + 0.4 * sustainability_score
```

The legacy `quality_score` and `grade` fields are preserved for clients, while `score_details` exposes the underlying performance, sustainability, category, product type, and formula version.

For URL analysis, product context is inferred from the URL slug, URL text, and scraped product-page text unless the request includes an explicit `product_type`. Explicit baby/kids signals such as `bebek` and `zibin` are prioritized over generic t-shirt or underwear terms during automatic detection.

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
- `POST /debug/label-ocr`: shows OCR text, confidence, and parsed fabric result for each label preprocessing variant.

## Testing

```powershell
pytest backend\tests\test_quality_score.py backend\tests\test_analyze_label.py backend\tests\test_fabric_parser.py
```

Current verified status:

```text
41 passed
```

## Next Work

1. Add richer dynamic-page extraction for product detail accordions and lazy content.
2. Add site-specific selector tuning for Zara, Trendyol, H&M, and similar dynamic stores.
3. Add integration tests for Playwright/Selenium fallback where browser runtime is available.
4. Add optional browser profile support for sites that require a real logged-in/localized session.
