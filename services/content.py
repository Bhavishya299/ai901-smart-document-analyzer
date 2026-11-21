"""Field extraction with a local Ollama model or the Gemini API.

The model must return JSON with exactly vendor_name, invoice_date and
total_amount. If anything fails, simple regex rules are used instead.
"""

from __future__ import annotations

import json
import re
from typing import Any, Mapping

import requests

FIELDS = ("vendor_name", "invoice_date", "total_amount")
ALIASES = {
    "vendor_name": ("vendor_name", "vendor", "vendorname", "companyname", "supplier", "from"),
    "invoice_date": ("invoice_date", "date", "invoicedate", "documentdate"),
    "total_amount": ("total_amount", "total", "totalamount", "invoicetotal", "amountdue", "amount"),
}

PROMPT = """Read the text below and return ONLY a JSON object with exactly these keys:
"vendor_name", "invoice_date", "total_amount".
Use null for a value you cannot find. Do not add any explanation.

TEXT:
{text}
"""


def build_prompt(text: str) -> str:
    """Build the JSON-only prompt for the LLM."""
    return PROMPT.format(text=text[:6000])  # keep the prompt a reasonable size


def regex_fallback(text: str) -> dict[str, object]:
    """Find the three fields with simple regular expressions."""
    patterns = {
        "vendor_name": r"(?:Vendor|Company|From|Supplier)\s*[:\-]\s*([^\n]+)",
        "invoice_date": r"(?:Invoice\s+)?Date\s*[:\-]\s*([0-9]{4}-[0-9]{2}-[0-9]{2}|[0-9]{1,2}/[0-9]{1,2}/[0-9]{2,4}|[A-Za-z]+\s+\d{1,2},\s*\d{4})",
        "total_amount": r"Total(?:\s+Amount)?\s*[:\-]\s*((?:[A-Z]{3}\s*)?\d[\d,]*(?:\.\d{2})?)",
    }
    fields: dict[str, object] = {}
    for name, pattern in patterns.items():
        match = re.search(pattern, text, re.IGNORECASE)
        fields[name] = match.group(1).strip() if match else None
    return fields


def _clean_json_text(raw: str) -> str:
    """Remove markdown fences some models add around JSON."""
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    return raw.strip()


def validate_fields(raw: str) -> dict[str, object] | None:
    """Parse and validate LLM output; return None if it is not usable."""
    try:
        data: Any = json.loads(_clean_json_text(raw))
    except (ValueError, TypeError):
        return None
    if not isinstance(data, dict):
        return None

    lookup = {str(key).lower().replace(" ", "_"): value for key, value in data.items()}
    fields: dict[str, object] = {}
    for name in FIELDS:
        value = None
        for alias in ALIASES[name]:
            candidate = lookup.get(alias.replace(" ", "_"))
            if candidate is not None:
                value = candidate
                break
        fields[name] = (
            str(value).strip()
            if isinstance(value, (str, int, float)) and str(value).strip()
            else None
        )
    return fields if any(fields.values()) else None


def ask_ollama(prompt: str, settings: Mapping[str, str]) -> str:
    """Ask a locally running Ollama server for a completion."""
    host = settings.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
    model = settings.get("OLLAMA_MODEL", "llama3.2")
    response = requests.post(
        f"{host}/api/generate",
        json={"model": model, "prompt": prompt, "format": "json", "stream": False},
        timeout=120,
    )
    response.raise_for_status()
    return str(response.json().get("response", ""))


def ask_gemini(prompt: str, settings: Mapping[str, str]) -> str:
    """Ask the Gemini API for a JSON completion."""
    from google import genai

    client = genai.Client(api_key=settings["GEMINI_API_KEY"])
    response = client.models.generate_content(
        model=settings.get("GEMINI_MODEL", "gemini-2.0-flash"),
        contents=prompt,
        config={"response_mime_type": "application/json"},
    )
    return response.text or ""


def extract_fields(text: str, settings: Mapping[str, str]) -> dict[str, object]:
    """Return the three report fields, preferring the LLM over regex."""
    fallback = regex_fallback(text)
    provider = settings.get("LLM_PROVIDER", "ollama").lower()
    prompt = build_prompt(text)

    if provider == "regex":
        return fallback

    try:
        if provider == "ollama":
            raw = ask_ollama(prompt, settings)
        elif provider == "gemini":
            raw = ask_gemini(prompt, settings)
        else:
            raise ValueError(f"Unknown LLM_PROVIDER: {provider!r}")
        fields = validate_fields(raw)
    except Exception as exc:
        print(f"  Warning: LLM extraction failed ({exc}); using regex fallback.")
        return fallback

    if fields is None:
        print("  Warning: LLM did not return valid JSON; using regex fallback.")
        return fallback

    # Fill any field the model left blank from the regex result.
    return {name: fields[name] or fallback[name] for name in FIELDS}
