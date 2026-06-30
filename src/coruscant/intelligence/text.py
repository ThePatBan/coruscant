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

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z(\"'$\d])")
_WS = re.compile(r"\s+")


def sentences(text: str) -> list[str]:
    """Split text into trimmed sentences, dropping empties."""

    cleaned = _WS.sub(" ", text).strip()
    if not cleaned:
        return []
    parts = _SENTENCE_SPLIT.split(cleaned)
    return [part.strip() for part in parts if part.strip()]


# A real disclosure sentence almost always carries a finite verb. Table-of-
# contents lines ("1 Overview 1 Business segments 2-6 Human capital 7-8 …"),
# financial-table rows, and bare headings do not — yet the raw splitter emits
# them, and they then get keyword-matched into phantom "risk signals". This gate
# keeps prose and drops the scaffolding, at the cost of a few rare verb-less
# sentences (an acceptable trade for not surfacing a TOC as a 72%-confidence
# regulatory concern).
_VERB_LEXICON = frozenset(
    """is are was were be been being am will would shall should may might can could must
    has have had do does did expect expects expected anticipate anticipates believe believes
    intend intends plan plans seek seeks include includes included provide provides provided
    operate operates result results resulted affect affects affected require requires required
    continue continues remain remains face faces depend depends increase increased decrease
    decreased grow grew reduce reduced incur incurred recognize recognized estimate estimated
    assume rely relies maintain generate generated invest report reported issue issued offer
    represent represents drive driven impact impacts experience experienced use uses used
    contributed declined rose fell expanded launched acquired entered agreed announced reflect
    reflects exceed exceeds arise arises subject relates related cause causes caused""".split()
)
_VERBISH = re.compile(r"\b[a-z]{3,}(?:ed|ing)\b")
_NUMERIC_TOKEN = re.compile(r"^\(?[$£€]?\d[\d,.–/%-]*\)?$")


def is_disclosure_sentence(sentence: str) -> bool:
    """True if the fragment reads as a disclosure sentence (not a TOC line / table
    row / heading). Used to keep change-detection, events, and summaries from
    surfacing document scaffolding as signal."""
    tokens = sentence.split()
    if len(tokens) < 6:
        return False
    if sum(1 for t in tokens if _NUMERIC_TOKEN.match(t)) / len(tokens) > 0.4:
        return False  # financial-table row / number run
    lowered = sentence.lower()
    words = re.findall(r"\b[a-z][a-z']+\b", lowered)
    if len(words) < 4:
        return False  # mostly Title-Case heading or numbers
    return any(w in _VERB_LEXICON for w in words) or bool(_VERBISH.search(lowered))


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
