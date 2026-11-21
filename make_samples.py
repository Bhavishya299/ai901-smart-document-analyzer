"""Generate fake sample files for the analyzer (no real personal data)."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.pagesizes import LETTER
from reportlab.pdfgen import canvas

SAMPLES = Path(__file__).parent / "samples"


def make_invoice_pdf() -> None:
    """Write a simple fake invoice as a text-based PDF."""
    path = SAMPLES / "fake_invoice.pdf"
    pdf = canvas.Canvas(str(path), pagesize=LETTER)
    pdf.setFont("Helvetica-Bold", 20)
    pdf.drawString(72, 740, "FAKE SAMPLE INVOICE")
    pdf.setFont("Helvetica", 12)
    pdf.drawString(72, 700, "Vendor: Fabrikam Demo Ltd.")
    pdf.drawString(72, 680, "Invoice date: 2026-01-15")
    pdf.drawString(72, 660, "Description: Consulting services")
    pdf.drawString(72, 640, "Total amount: USD 120.00")
    pdf.drawString(72, 600, "This is fictional data for testing only.")
    pdf.save()


def make_ocr_image() -> None:
    """Write a PNG with printed fake text for the Vision OCR step."""
    path = SAMPLES / "printed_text.png"
    image = Image.new("RGB", (900, 330), "white")
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("arial.ttf", 30)
    except OSError:
        font = ImageFont.load_default()

    lines = [
        "FAKE SAMPLE NOTICE",
        "Vendor: Fabrikam Demo Ltd.",
        "Invoice date: 2026-01-15",
        "Total: USD 120.00",
        "All details on this image are fictional.",
    ]
    for index, line in enumerate(lines):
        draw.text((40, 35 + index * 55), line, fill="black", font=font)
    image.save(path)


def make_feedback_txt() -> None:
    """Write a fake feedback paragraph with a phone number and email."""
    path = SAMPLES / "feedback.txt"
    text = (
        "I really enjoyed using the new document analyzer. The setup was quick "
        "and the reports are easy to read. Please contact me at "
        "fake.user@example.com or call 555-010-1234 if you need more feedback. "
        "All details here are fictional.\n"
    )
    path.write_text(text, encoding="utf-8")


def main() -> None:
    """Create the samples folder and all three fake samples."""
    SAMPLES.mkdir(exist_ok=True)
    make_invoice_pdf()
    make_ocr_image()
    make_feedback_txt()
    print(f"Created fake samples in {SAMPLES}")


if __name__ == "__main__":
    main()
