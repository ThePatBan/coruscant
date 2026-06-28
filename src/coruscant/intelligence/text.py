"""Deterministic text utilities for the intelligence layer.

Sentence splitting and keyword-cue classification underpin summarization, event
extraction, and change detection. Everything is rule-based and offline so each
derived statement can be traced back to the exact source sentence that produced
it.
"""

from __future__ import annotations

from datetime import date, datetime
import re

# Ordered so the most specific categories win when labelling a single sentence.
CATEGORY_CUES: dict[str, tuple[str, ...]] = {
    "executive": (
        "appointed",
        "named ceo",
        "named cfo",
        "chief executive",
        "chief financial",
        "resigned",
        "stepped down",
        "board of directors",
        "leadership change",
    ),
    "m&a": ("acquire", "acquisition", "merger", "merge with", "divest", "takeover"),
    "capital_allocation": (
        "dividend",
        "buyback",
        "repurchase",
        "share repurchase",
        "capital allocation",
        "capital return",
    ),
    "litigation": ("litigation", "lawsuit", "legal proceeding", "settlement", "court"),
    "regulatory": (
        "regulatory",
        "regulation",
        "antitrust",
        "investigation",
        "compliance",
        "sanction",
    ),
    "supply_chain": (
        "supply chain",
        "supplier",
        "logistics",
        "inventory",
        "manufacturing capacity",
        "shortage",
    ),
    "guidance": (
        "guidance",
        "outlook",
        "we expect",
        "forecast",
        "anticipate",
        "reaffirm",
        "full-year",
        "full year",
        "raised guidance",
        "lowered guidance",
    ),
    "product": (
        "launch",
        "launched",
        "unveiled",
        "new product",
        "introduced",
        "released",
        "product initiative",
    ),
    "financial": (
        "revenue",
        "margin",
        "operating income",
        "earnings",
        "cash flow",
        "expenditure",
        "profit",
        "financial performance",
    ),
    "opportunity": (
        "growth",
        "opportunity",
        "expand",
        "expansion",
        "demand",
        "investment",
        "record",
        "momentum",
    ),
    "risk": (
        "risk",
        "adverse",
        "uncertain",
        "decline",
        "headwind",
        "competition",
        "competitive",
        "disrupt",
        "challenge",
        "pressure",
    ),
}

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z(])")
_WS = re.compile(r"\s+")


def sentences(text: str) -> list[str]:
    """Split text into trimmed sentences, dropping empties."""

    cleaned = _WS.sub(" ", text).strip()
    if not cleaned:
        return []
    parts = _SENTENCE_SPLIT.split(cleaned)
    return [part.strip() for part in parts if part.strip()]


def categories_of(sentence: str) -> set[str]:
    """All categories whose cue terms appear in the sentence."""

    lowered = sentence.lower()
    found = {category for category, cues in CATEGORY_CUES.items() if any(c in lowered for c in cues)}
    return found


def primary_category(sentence: str) -> str:
    """The single most specific category for a sentence (CATEGORY_CUES order)."""

    lowered = sentence.lower()
    for category, cues in CATEGORY_CUES.items():
        if any(c in lowered for c in cues):
            return category
    return "general"


def normalize_statement(sentence: str) -> str:
    """Canonical form for set comparison in change detection."""

    lowered = sentence.lower()
    lowered = re.sub(r"[^a-z0-9 ]+", "", lowered)
    return _WS.sub(" ", lowered).strip()


def iso_date(value: object) -> str | None:
    """Normalize a date/datetime/string to a ``YYYY-MM-DD`` string (or None)."""

    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)[:10] or None


def headline(sentence: str, *, words: int = 9) -> str:
    """A short title derived from the first words of a sentence."""

    tokens = sentence.split()
    title = " ".join(tokens[:words])
    return title.rstrip(".,;:") + ("…" if len(tokens) > words else "")
