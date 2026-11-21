"""Sentiment, key phrases and PII redaction using free local libraries."""

from __future__ import annotations

import re

from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import OperatorConfig
from presidio_analyzer import AnalyzerEngine
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
from yake import KeywordExtractor

_sentiment = SentimentIntensityAnalyzer()
_keywords = KeywordExtractor(lan="en", n=2, top=8)

# Presidio needs a spaCy model. Fall back to simple regex rules if missing.
try:
    _pii = AnalyzerEngine()
    _anonymizer = AnonymizerEngine()
except Exception:  # pragma: no cover - depends on local spaCy model
    _pii = None
    _anonymizer = None


def _regex_redact(text: str) -> str:
    """Replace obvious emails and phone numbers with *** if Presidio is off."""
    text = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "***", text)
    text = re.sub(r"(?:\+?\d[\d(). -]{7,}\d)", "***", text)
    return text


def redact_pii(text: str) -> str:
    """Return text with detected personal information replaced by ***."""
    if _pii is None or _anonymizer is None:
        return _regex_redact(text)

    findings = _pii.analyze(text=text, language="en")
    result = _anonymizer.anonymize(
        text=text,
        analyzer_results=findings,
        operators={"DEFAULT": OperatorConfig("replace", {"new_value": "***"})},
    )
    return result.text


def analyze_text(text: str) -> dict[str, object]:
    """Analyze text and return sentiment, key phrases and redacted text."""
    score = _sentiment.polarity_scores(text)["compound"]
    if score >= 0.05:
        sentiment = "positive"
    elif score <= -0.05:
        sentiment = "negative"
    else:
        sentiment = "neutral"

    phrases = [phrase for phrase, _score in _keywords.extract_keywords(text)]

    return {
        "sentiment": sentiment,
        "key_phrases": phrases,
        "redacted_text": redact_pii(text),
    }
