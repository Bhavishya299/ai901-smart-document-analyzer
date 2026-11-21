"""Smart Document Analyzer: local, free file-to-JSON report pipeline.

Run:  python analyzer.py
Skip the LLM and use regex fields only:  python analyzer.py --no-llm
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import requests
from dotenv import load_dotenv
from pytesseract import TesseractNotFoundError

from services.content import extract_fields
from services.language import analyze_text
from services.ocr import read_image_text, read_pdf_text

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg"}
SUPPORTED_EXTENSIONS = IMAGE_EXTENSIONS | {".pdf", ".txt"}
VALID_PROVIDERS = {"ollama", "gemini", "regex"}

# Grouping calls makes them easy to replace in tests.
ServiceFunctions = Mapping[str, Callable[..., Any]]
DEFAULT_SERVICES: ServiceFunctions = {
    "read_image_text": read_image_text,
    "read_pdf_text": read_pdf_text,
    "analyze_text": analyze_text,
    "extract_fields": extract_fields,
}


class ConfigError(Exception):
    """Raised when the chosen configuration is incomplete or invalid."""


def load_settings() -> dict[str, str]:
    """Load .env and return settings with sensible local defaults."""
    load_dotenv()
    provider = os.getenv("LLM_PROVIDER", "ollama").strip().lower() or "ollama"
    if provider not in VALID_PROVIDERS:
        raise ConfigError(
            f"Invalid LLM_PROVIDER={provider!r}. Use 'ollama', 'gemini' or leave it blank for ollama."
        )

    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if provider == "gemini" and not api_key:
        raise ConfigError(
            "Missing GEMINI_API_KEY. Add your free key from "
            "https://aistudio.google.com/app/apikey to .env, or set LLM_PROVIDER=ollama."
        )

    return {
        "LLM_PROVIDER": provider,
        "GEMINI_API_KEY": api_key,
        "GEMINI_MODEL": os.getenv("GEMINI_MODEL", "gemini-2.0-flash").strip(),
        "OLLAMA_HOST": os.getenv("OLLAMA_HOST", "http://localhost:11434").strip(),
        "OLLAMA_MODEL": os.getenv("OLLAMA_MODEL", "llama3.2").strip(),
    }


def friendly_error(exc: Exception) -> str:
    """Turn common failures into short, readable messages."""
    if isinstance(exc, TesseractNotFoundError):
        return "Tesseract is not installed or not on PATH. See README for install steps."
    if isinstance(exc, requests.RequestException):
        return (
            f"Local LLM request failed: {exc}. Start Ollama with 'ollama serve' "
            "and pull the model with 'ollama pull llama3.2', or use --no-llm."
        )
    if isinstance(exc, FileNotFoundError):
        return f"Required external tool not found: {exc}"
    return f"{type(exc).__name__}: {exc}"


def read_text(path: Path, services: ServiceFunctions) -> str:
    """Read text from a .txt, image or PDF file."""
    suffix = path.suffix.lower()
    if suffix == ".txt":
        return path.read_text(encoding="utf-8", errors="ignore")
    if suffix in IMAGE_EXTENSIONS:
        return str(services["read_image_text"](path))
    return str(services["read_pdf_text"](path))


def process(
    path: str | Path,
    settings: Mapping[str, str],
    services: ServiceFunctions | None = None,
) -> dict[str, object]:
    """Build one report for one file."""
    svc = services if services is not None else DEFAULT_SERVICES
    file_path = Path(path)
    text = read_text(file_path, svc).strip()
    if not text:
        return {"file": file_path.name, "error": "No text found in this file"}

    language = svc["analyze_text"](text)
    fields = svc["extract_fields"](text, settings)
    return {
        "file": file_path.name,
        "sentiment": language["sentiment"],
        "key_phrases": language["key_phrases"],
        "redacted_text": language["redacted_text"],
        "fields": fields,
    }


def run_all(
    settings: Mapping[str, str],
    samples_dir: str | Path = "samples",
    services: ServiceFunctions | None = None,
) -> list[dict[str, object]]:
    """Process every supported file in a folder and save one report each."""
    folder = Path(samples_dir)
    if not folder.is_dir():
        print(f"Samples folder not found: {folder}")
        return []

    files = sorted(
        item for item in folder.iterdir()
        if item.is_file() and item.suffix.lower() in SUPPORTED_EXTENSIONS
    )
    reports: list[dict[str, object]] = []
    for file_path in files:
        try:
            report = process(file_path, settings, services)
        except Exception as exc:  # one bad file must not stop the run
            report = {"file": file_path.name, "error": friendly_error(exc)}

        output = json.dumps(report, indent=2, ensure_ascii=False)
        print(output)
        (folder / f"{file_path.name}.report.json").write_text(
            output, encoding="utf-8"
        )
        reports.append(report)
    return reports


def main(argv: Sequence[str] | None = None) -> int:
    """Command-line entry point. Returns a process exit code."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="Skip the LLM and use regex field extraction only.",
    )
    args = parser.parse_args(argv)

    try:
        settings = load_settings()
    except ConfigError as exc:
        print(exc)
        return 1
    if args.no_llm:
        settings["LLM_PROVIDER"] = "regex"

    reports = run_all(settings)
    print(f"Done: {len(reports)} report(s) written to the samples folder.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
