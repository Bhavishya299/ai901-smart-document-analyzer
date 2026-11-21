"""Text extraction with Tesseract OCR (no cloud service)."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytesseract
from PIL import Image


def _configure_tesseract() -> None:
    """Point pytesseract at the usual Windows install path if needed."""
    current = pytesseract.pytesseract.tesseract_cmd
    if current and current != "tesseract":
        return
    if shutil.which("tesseract"):
        return
    for candidate in (
        Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe"),
        Path(r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"),
    ):
        if candidate.exists():
            pytesseract.pytesseract.tesseract_cmd = str(candidate)
            return


def read_image_text(path: str | Path) -> str:
    """Return text found in one image using Tesseract."""
    _configure_tesseract()
    with Image.open(path) as image:
        return pytesseract.image_to_string(image).strip()


def _poppler_path() -> str | None:
    """Find Poppler's bin folder for winget installs not yet on PATH."""
    if shutil.which("pdfinfo"):
        return None
    local = os.getenv("LOCALAPPDATA", "")
    root = Path(local) / "Microsoft" / "WinGet" / "Packages"
    for folder in root.glob("oschwartz10612.Poppler*"):
        for bin_dir in folder.glob("poppler-*/Library/bin"):
            if (bin_dir / "pdfinfo.exe").exists():
                return str(bin_dir)
    return None


def read_pdf_text(path: str | Path) -> str:
    """Return text from a PDF: fast text layer first, then OCR with Poppler."""
    # Text-based PDFs do not need OCR at all.
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        text = "\n".join(page.extract_text() or "" for page in reader.pages).strip()
        if text:
            return text
    except Exception:
        pass  # Fall through to OCR.

    # Scanned PDFs: render pages with Poppler, then OCR each page.
    _configure_tesseract()
    try:
        from pdf2image import convert_from_path

        pages = convert_from_path(str(path), dpi=200, poppler_path=_poppler_path())
        return "\n".join(
            pytesseract.image_to_string(page).strip() for page in pages
        ).strip()
    except Exception as exc:
        raise RuntimeError(
            "Could not read this PDF. Install Poppler (see README) so pdf2image "
            f"can render pages. Original error: {exc}"
        ) from exc
