"""Tiny localhost web UI: upload an invoice, click a button, see its report."""

from __future__ import annotations

import json
from pathlib import Path

from flask import Flask, render_template, request
from werkzeug.utils import secure_filename

import analyzer

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024  # 20 MB
SAMPLES = Path(__file__).parent / "samples"


@app.route("/", methods=["GET", "POST"])
def index() -> str:
    """Show the upload form and, after a POST, the report for one file."""
    report: dict[str, object] | None = None
    error: str | None = None

    if request.method == "POST":
        uploaded = request.files.get("invoice")
        if uploaded is None or not uploaded.filename:
            error = "Choose a file first."
        else:
            filename = secure_filename(uploaded.filename)
            suffix = Path(filename).suffix.lower() if filename else ""
            if not filename or suffix not in analyzer.SUPPORTED_EXTENSIONS:
                error = "Unsupported file. Use PDF, PNG, JPG, JPEG or TXT."
            else:
                SAMPLES.mkdir(exist_ok=True)
                path = SAMPLES / filename
                uploaded.save(path)
                try:
                    settings = analyzer.load_settings()
                    report = analyzer.process(path, settings)
                except analyzer.ConfigError as exc:
                    error = str(exc)
                except Exception as exc:  # keep the page usable on any failure
                    report = {"file": filename, "error": analyzer.friendly_error(exc)}

                if report is not None:
                    output = json.dumps(report, indent=2, ensure_ascii=False)
                    (SAMPLES / f"{filename}.report.json").write_text(
                        output, encoding="utf-8"
                    )

    return render_template(
        "index.html",
        error=error,
        report=report,
        report_json=json.dumps(report, indent=2, ensure_ascii=False) if report else None,
    )


@app.errorhandler(413)
def too_large(exc: object) -> tuple[str, int]:
    """Return a readable message when an uploaded file is too big."""
    return render_template(
        "index.html", error="That file is too large (maximum 20 MB).", report=None,
        report_json=None,
    ), 413


def main() -> None:
    """Start the local web server on 127.0.0.1:5000."""
    app.run(host="127.0.0.1", port=5000, debug=False)


if __name__ == "__main__":
    main()
