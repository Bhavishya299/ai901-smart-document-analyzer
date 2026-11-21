# Smart Document Analyzer (free / local edition)

Reads every supported file in `samples/` (`.pdf`, `.png`, `.jpg`, `.jpeg`, `.txt`)
and writes one `<name>.report.json` per file:

```json
{
  "file": "fake_invoice.pdf",
  "sentiment": "positive",
  "key_phrases": ["..."],
  "redacted_text": "...",
  "fields": {
    "vendor_name": "...",
    "invoice_date": "...",
    "total_amount": "..."
  }
}
```

No Azure account is needed. Used libraries:

| Job | Tool |
| --- | --- |
| Image OCR | `pytesseract` + Pillow |
| PDF text | `pypdf` first, then `pdf2image` + Tesseract |
| Sentiment | `vaderSentiment` |
| Key phrases | `yake` |
| PII redaction | `presidio-analyzer` + `presidio-anonymizer` (`***`) |
| Invoice fields | LLM via **Ollama** (local) or **Gemini** (free key), with regex fallback |

## 1. Install Tesseract (required for images/scanned PDFs)

Tesseract is a free OCR binary. pip installs the Python wrapper, not the binary.

**Windows** (PowerShell):

```powershell
winget install --id UB-Mannheim.TesseractOCR
```

If you prefer Chocolatey:

```powershell
choco install tesseract
```

Install to the default `C:\Program Files\Tesseract-OCR` — the code checks that
path automatically. Restart VS Code/your terminal after installation so PATH
refreshes.

**macOS:**

```bash
brew install tesseract
```

**Ubuntu / Debian:**

```bash
sudo apt-get update
sudo apt-get install -y tesseract-ocr
```

Check with:

```bash
tesseract --version
```

### Install Poppler (needed only for scanned PDFs)

Text-based PDFs use `pypdf` and skip Poppler. Scanned PDFs need Poppler so
`pdf2image` can render pages before OCR.

```powershell
# Windows
winget install --id oschwartz10612.Poppler
```

```bash
# macOS
brew install poppler

# Ubuntu / Debian
sudo apt-get install -y poppler-utils
```

## 2. Install Python packages

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1   # Windows PowerShell
# source .venv/bin/activate    # macOS / Linux
python -m pip install -r requirements.txt
```

If PowerShell blocks activation, run:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

Presidio downloads a small spaCy English model on first use. That is local and
happens once.

## 3. Choose your field-extraction mode

Copy the example config:

```powershell
copy .env.example .env    # Windows
cp .env.example .env      # macOS / Linux
```

### Option A — Ollama (local, no account, default)

1. Install Ollama from <https://ollama.com>.
2. Start it: `ollama serve`
3. Pull the model: `ollama pull llama3.2`

`.env` can stay as the example:

```text
LLM_PROVIDER=ollama
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=llama3.2
```

If Ollama is not running, the tool prints a warning and uses regex extraction
instead — the reports are still created.

### Option B — Gemini (free API key)

1. Get a free key at <https://aistudio.google.com/app/apikey>.
2. Set in `.env`:

```text
LLM_PROVIDER=gemini
GEMINI_API_KEY=your-free-key
GEMINI_MODEL=gemini-2.0-flash
```

If `LLM_PROVIDER=gemini` and the key is missing, the tool stops with:
`Missing GEMINI_API_KEY. Add your free key ...`

### Option C — no LLM at all

```bash
python analyzer.py --no-llm
```

This uses only regex field extraction. No key, no model, no network.

Never hard-code keys. `.env` is gitignored. Old Azure variables in your `.env`
are simply ignored.

## 4. Run from the command line

```bash
python analyzer.py
```

Each report is printed as indented JSON and saved next to the file in
`samples/`. If one file fails, it gets `{"file": "...", "error": "..."}` and
the run continues.

## 5. Run the local web interface

```bash
python app.py
```

Then open <http://127.0.0.1:5000> in your browser. Choose an invoice
(PDF/PNG/JPG/JPEG/TXT), click **Analyze invoice**, and the report appears on the
same page. The uploaded file and its `.report.json` are saved in `samples/`.
Press `Ctrl+C` in the terminal to stop the server.

The web page uses the exact same pipeline as `python analyzer.py`, including the
Ollama/Gemini/regex field extraction and the `--no-llm`-style regex fallback
when the model is unavailable.

Regenerate the fake samples with:

```bash
python make_samples.py
```

Run the tests (all OCR/LLM calls are mocked):

```bash
python -m pytest -q
```

## Troubleshooting

- **`Tesseract is not installed or not on PATH`** — install Tesseract above and
  restart the terminal. On Windows the code also checks
  `C:\Program Files\Tesseract-OCR\tesseract.exe`.
- **`Could not read this PDF ... Install Poppler`** — install Poppler above.
- **`Local LLM request failed`** — start Ollama (`ollama serve`) and pull
  `llama3.2`, or run `python analyzer.py --no-llm`.
- **`Invalid LLM_PROVIDER`** — use `ollama`, `gemini`, or leave blank.
- **`Missing GEMINI_API_KEY`** — add the key to `.env` or switch to `ollama`.
- **Fields are `null`** — the regex rules could not find them and the LLM was
  unavailable. Invoice text with `Vendor:`, `Invoice date:` and `Total:` works
  best. Add more patterns in `services/content.py` if needed.
- **PII is not redacted** — Presidio should handle emails/phones. If its spaCy
  model is unavailable, a regex fallback replaces obvious emails and phone
  numbers with `***`.

## Files

- `analyzer.py` — CLI, settings, per-file pipeline, error handling
- `app.py` — localhost upload page using the same pipeline
- `templates/index.html` — the upload form and report display
- `services/ocr.py` — image/PDF text extraction
- `services/language.py` — sentiment, key phrases, PII redaction
- `services/content.py` — JSON-only LLM extraction + regex fallback
- `samples/` — fake invoice PDF, printed-text PNG, feedback TXT
- `make_samples.py` — regenerates the fake samples
- `tests/test_pipeline.py` — mocked pytest suite
- `requirements.txt`, `.env.example`, `.gitignore`
