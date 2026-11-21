"""Tests for the localhost upload page. External calls are mocked."""

from __future__ import annotations

import io
from pathlib import Path
from unittest.mock import Mock

import pytest

import analyzer
import app as web_app

SETTINGS = {
    "LLM_PROVIDER": "regex",
    "GEMINI_API_KEY": "",
    "GEMINI_MODEL": "gemini-2.0-flash",
    "OLLAMA_HOST": "http://localhost:11434",
    "OLLAMA_MODEL": "llama3.2",
}
REPORT = {
    "file": "invoice.txt",
    "sentiment": "neutral",
    "key_phrases": ["invoice"],
    "redacted_text": "Vendor: Test Ltd.",
    "fields": {
        "vendor_name": "Test Ltd.",
        "invoice_date": "2026-01-15",
        "total_amount": "USD 1.00",
    },
}


@pytest.fixture
def client() -> object:
    """Return a Flask test client."""
    return web_app.app.test_client()


def test_form_loads(client: object) -> None:
    """The page shows the upload form on GET."""
    response = client.get("/")  # type: ignore[attr-defined]
    assert response.status_code == 200
    assert b"Analyze invoice" in response.data


def test_upload_shows_report_on_same_page(
    client: object, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A valid upload returns the report JSON in the page."""
    monkeypatch.setattr(web_app, "SAMPLES", tmp_path)
    monkeypatch.setattr(web_app.analyzer, "load_settings", lambda: SETTINGS)
    process = Mock(return_value=REPORT)
    monkeypatch.setattr(web_app.analyzer, "process", process)

    response = client.post(  # type: ignore[attr-defined]
        "/",
        data={"invoice": (io.BytesIO(b"Vendor: Test Ltd."), "invoice.txt")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    assert b"vendor_name" in response.data
    assert b"Test Ltd." in response.data
    assert b"Analyze invoice" in response.data
    process.assert_called_once()
    assert (tmp_path / "invoice.txt").exists()
    assert (tmp_path / "invoice.txt.report.json").exists()


def test_unsupported_file_is_rejected(
    client: object, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only the supported extensions are accepted."""
    monkeypatch.setattr(web_app, "SAMPLES", tmp_path)
    process = Mock(side_effect=AssertionError("must not process"))
    monkeypatch.setattr(web_app.analyzer, "process", process)

    response = client.post(  # type: ignore[attr-defined]
        "/",
        data={"invoice": (io.BytesIO(b"bad"), "virus.exe")},
        content_type="multipart/form-data",
    )

    assert b"Unsupported file" in response.data
    process.assert_not_called()
    assert not (tmp_path / "virus.exe").exists()


def test_missing_config_is_shown_on_page(
    client: object, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Config errors appear as a clear message instead of a crash."""
    monkeypatch.setattr(web_app, "SAMPLES", tmp_path)

    def fail() -> dict[str, str]:
        """Simulate missing config."""
        raise analyzer.ConfigError("Missing GEMINI_API_KEY. Add it to .env.")

    monkeypatch.setattr(web_app.analyzer, "load_settings", fail)
    response = client.post(  # type: ignore[attr-defined]
        "/",
        data={"invoice": (io.BytesIO(b"text"), "note.txt")},
        content_type="multipart/form-data",
    )
    assert b"Missing GEMINI_API_KEY" in response.data
