"""Pipeline tests. All LLM and OCR calls are mocked; no network needed."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import Mock

import pytest
import requests

import analyzer
import services.content as content_service

SETTINGS = {
    "LLM_PROVIDER": "ollama",
    "GEMINI_API_KEY": "",
    "GEMINI_MODEL": "gemini-2.0-flash",
    "OLLAMA_HOST": "http://localhost:11434",
    "OLLAMA_MODEL": "llama3.2",
}
FIELDS = {
    "vendor_name": "Fabrikam Demo Ltd.",
    "invoice_date": "2026-01-15",
    "total_amount": "USD 120.00",
}
INVOICE_TEXT = (
    "FAKE SAMPLE INVOICE\nVendor: Fabrikam Demo Ltd.\n"
    "Invoice date: 2026-01-15\nTotal amount: USD 120.00\n"
)


def fake_language(text: str) -> dict[str, object]:
    """Stand-in for the language service."""
    return {"sentiment": "neutral", "key_phrases": ["sample"], "redacted_text": text}


def fake_fields(text: str, settings: object) -> dict[str, object]:
    """Stand-in for field extraction."""
    return dict(FIELDS)


def make_services(**overrides: object) -> dict[str, object]:
    """Return mocked service callables with optional replacements."""
    services: dict[str, object] = {
        "read_image_text": Mock(return_value="Image OCR text"),
        "read_pdf_text": Mock(return_value=INVOICE_TEXT),
        "analyze_text": Mock(side_effect=fake_language),
        "extract_fields": Mock(side_effect=fake_fields),
    }
    services.update(overrides)
    return services


def read_report(folder: Path, name: str) -> dict[str, object]:
    """Load a saved report from disk."""
    return json.loads((folder / f"{name}.report.json").read_text(encoding="utf-8"))


@pytest.fixture
def samples(tmp_path: Path) -> Path:
    """Create a temporary samples folder."""
    folder = tmp_path / "samples"
    folder.mkdir()
    return folder


def test_image_file_uses_ocr(samples: Path) -> None:
    """Images go through OCR, then language and field extraction."""
    (samples / "photo.png").write_bytes(b"fake png")
    ocr = Mock(return_value="Text from image")
    language = Mock(side_effect=fake_language)
    reports = analyzer.run_all(
        SETTINGS, samples, make_services(read_image_text=ocr, analyze_text=language)
    )

    assert reports[0]["file"] == "photo.png"
    assert reports[0]["fields"] == FIELDS
    ocr.assert_called_once()
    language.assert_called_once_with("Text from image")
    assert read_report(samples, "photo.png") == reports[0]


def test_text_file_is_read_directly(samples: Path) -> None:
    """.txt files do not need OCR."""
    (samples / "note.txt").write_text("A helpful sample text.", encoding="utf-8")
    ocr = Mock(side_effect=AssertionError("OCR must not run for .txt"))
    pdf = Mock(side_effect=AssertionError("PDF reader must not run for .txt"))
    reports = analyzer.run_all(
        SETTINGS, samples, make_services(read_image_text=ocr, read_pdf_text=pdf)
    )

    assert reports[0]["redacted_text"] == "A helpful sample text."
    ocr.assert_not_called()
    pdf.assert_not_called()


def test_pdf_uses_pdf_reader(samples: Path) -> None:
    """PDFs use the PDF text reader."""
    (samples / "invoice.pdf").write_bytes(b"fake pdf")
    pdf = Mock(return_value=INVOICE_TEXT)
    reports = analyzer.run_all(SETTINGS, samples, make_services(read_pdf_text=pdf))

    pdf.assert_called_once()
    assert reports[0]["fields"] == FIELDS
    assert (samples / "invoice.pdf.report.json").exists()


def test_empty_file_is_reported_and_skipped(samples: Path) -> None:
    """An empty file gets a clear error and no external calls."""
    (samples / "empty.txt").write_text("", encoding="utf-8")
    language = Mock(side_effect=AssertionError("No analysis for empty files"))
    reports = analyzer.run_all(SETTINGS, samples, make_services(analyze_text=language))

    assert reports == [{"file": "empty.txt", "error": "No text found in this file"}]
    language.assert_not_called()
    assert read_report(samples, "empty.txt")["error"] == "No text found in this file"


def test_one_bad_file_does_not_stop_the_run(samples: Path) -> None:
    """An exception on one file becomes an error report; others still finish."""
    (samples / "a_good.txt").write_text("Good text", encoding="utf-8")
    (samples / "b_bad.txt").write_text("Bad text", encoding="utf-8")

    def flaky(text: str) -> dict[str, object]:
        """Fail for one file only."""
        if text == "Bad text":
            raise RuntimeError("local model exploded")
        return fake_language(text)

    reports = analyzer.run_all(
        SETTINGS, samples, make_services(analyze_text=Mock(side_effect=flaky))
    )

    assert reports[0]["sentiment"] == "neutral"
    assert reports[1] == {
        "file": "b_bad.txt",
        "error": "RuntimeError: local model exploded",
    }
    assert (samples / "a_good.txt.report.json").exists()
    assert (samples / "b_bad.txt.report.json").exists()


def test_ollama_json_result_is_used(monkeypatch: pytest.MonkeyPatch) -> None:
    """Valid JSON from Ollama becomes the three report fields."""
    monkeypatch.setattr(
        content_service, "ask_ollama",
        lambda prompt, settings: json.dumps(FIELDS),
    )
    fields = content_service.extract_fields(INVOICE_TEXT, SETTINGS)
    assert fields == FIELDS


def test_gemini_json_result_is_used(monkeypatch: pytest.MonkeyPatch) -> None:
    """Valid JSON from Gemini becomes the three report fields."""
    monkeypatch.setattr(
        content_service, "ask_gemini",
        lambda prompt, settings: '{"vendor_name": "Gemini Ltd.", '
        '"invoice_date": "2026-02-01", "total_amount": "USD 9.00"}',
    )
    settings = dict(SETTINGS, LLM_PROVIDER="gemini", GEMINI_API_KEY="fake-key")
    fields = content_service.extract_fields(INVOICE_TEXT, settings)
    assert fields["vendor_name"] == "Gemini Ltd."


def test_bad_llm_json_falls_back_to_regex(monkeypatch: pytest.MonkeyPatch) -> None:
    """Invalid JSON is ignored and regex fields are returned."""
    monkeypatch.setattr(content_service, "ask_ollama", lambda prompt, settings: "not json")
    fields = content_service.extract_fields(INVOICE_TEXT, SETTINGS)
    assert fields == {
        "vendor_name": "Fabrikam Demo Ltd.",
        "invoice_date": "2026-01-15",
        "total_amount": "USD 120.00",
    }


def test_ollama_outage_falls_back_to_regex(monkeypatch: pytest.MonkeyPatch) -> None:
    """A local connection error does not stop the pipeline."""
    def boom(prompt: str, settings: object) -> str:
        """Simulate Ollama not running."""
        raise requests.ConnectionError("connection refused")

    monkeypatch.setattr(content_service, "ask_ollama", boom)
    fields = content_service.extract_fields(INVOICE_TEXT, SETTINGS)
    assert fields["vendor_name"] == "Fabrikam Demo Ltd."


def test_missing_gemini_key_has_clear_message(monkeypatch: pytest.MonkeyPatch) -> None:
    """Choosing Gemini without a key explains what to do."""
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "")
    with pytest.raises(analyzer.ConfigError, match="GEMINI_API_KEY"):
        analyzer.load_settings()


def test_invalid_provider_has_clear_message(monkeypatch: pytest.MonkeyPatch) -> None:
    """An unknown provider is rejected with the allowed values."""
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    with pytest.raises(analyzer.ConfigError, match="LLM_PROVIDER"):
        analyzer.load_settings()
