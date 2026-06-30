"""Deterministic, fully-cited document summarization.

Every item in a summary is a :class:`Claim` lifted verbatim from a source
sentence, tagged with its section and source URI. Nothing is paraphrased or
invented, so a summary is auditable line by line.
"""

from __future__ import annotations

from collections.abc import Iterator

from coruscant.common.types import NormalizedDocument
from coruscant.intelligence.confidence import category_confidence
from coruscant.intelligence.models import Claim, DocumentSummary
from coruscant.intelligence.text import (
    CATEGORY_CUES,
    categories_of,
    is_disclosure_sentence,
    iso_date,
    primary_category,
    sentences,
)

RISK_CATEGORIES = {"risk", "supply_chain", "litigation", "regulatory"}
OPPORTUNITY_CATEGORIES = {"opportunity", "product"}
FINANCIAL_CATEGORIES = {"financial", "capital_allocation", "guidance"}
COMMENTARY_CATEGORIES = {"guidance", "executive"}
EVENT_CATEGORIES = {"product", "m&a", "executive", "regulatory", "capital_allocation", "litigation"}
COMMENTARY_SECTION_CUES = ("management", "discussion", "outlook", "remarks", "guidance")

_MAX_PER_BUCKET = 6


def _iter_sentences(document: NormalizedDocument) -> Iterator[tuple[str, str]]:
    for section in document.sections:
        title = str(section.get("title") or "")
        content = str(section.get("content") or "")
        for sentence in sentences(content):
            if is_disclosure_sentence(sentence):
                yield title, sentence


def _claim(document: NormalizedDocument, title: str, sentence: str, category: str) -> Claim:
    return Claim(
        text=sentence,
        source_uri=document.source_uri,
        section_title=title or None,
        canonical_id=document.canonical_id,
        category=category,
        confidence=category_confidence(category),
    )


def _bucket(
    document: NormalizedDocument,
    rows: list[tuple[str, str]],
    wanted: set[str],
    *,
    section_cues: tuple[str, ...] = (),
) -> list[Claim]:
    claims: list[Claim] = []
    seen: set[str] = set()
    for title, sentence in rows:
        cats = categories_of(sentence)
        title_match = any(cue in title.lower() for cue in section_cues)
        if not (cats & wanted) and not title_match:
            continue
        if sentence in seen:
            continue
        seen.add(sentence)
        # Deterministic: pick the first category in the canonical CATEGORY_CUES
        # order that is both wanted and present (set iteration order is unstable).
        category = next(
            (c for c in CATEGORY_CUES if c in wanted and c in cats),
            primary_category(sentence),
        )
        claims.append(_claim(document, title, sentence, category))
        if len(claims) >= _MAX_PER_BUCKET:
            break
    return claims


class ReferenceSummarizer:
    """Extractive summarizer that classifies source sentences into sections."""

    def summarize(
        self, document: NormalizedDocument, *, company_slug: str, source_type: str
    ) -> DocumentSummary:
        rows = list(_iter_sentences(document))

        key_points: list[Claim] = []
        seen_sections: set[str] = set()
        for title, sentence in rows:
            if title in seen_sections:
                continue
            seen_sections.add(title)
            key_points.append(_claim(document, title, sentence, primary_category(sentence)))
            if len(key_points) >= _MAX_PER_BUCKET:
                break

        # Overview is the first source sentence, kept as a cited Claim. For an
        # empty document it is a non-asserting empty Claim (nothing fabricated).
        if rows:
            overview = _claim(document, rows[0][0], rows[0][1], primary_category(rows[0][1]))
        else:
            overview = _claim(document, "", "", "general")

        return DocumentSummary(
            canonical_id=document.canonical_id,
            company_slug=company_slug,
            document_type=document.document_type,
            source_type=source_type,
            title=document.title,
            published_at=iso_date(document.published_at),
            source_uri=document.source_uri,
            overview=overview,
            key_points=key_points,
            risks=_bucket(document, rows, RISK_CATEGORIES),
            opportunities=_bucket(document, rows, OPPORTUNITY_CATEGORIES),
            management_commentary=_bucket(
                document, rows, COMMENTARY_CATEGORIES, section_cues=COMMENTARY_SECTION_CUES
            ),
            financial_highlights=_bucket(document, rows, FINANCIAL_CATEGORIES),
            events=_bucket(document, rows, EVENT_CATEGORIES),
        )
