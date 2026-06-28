"""Deterministic event extraction for the company timeline.

Sentences whose primary category is an action-bearing one (product, M&A,
executive, regulatory, litigation, guidance, capital allocation) become timeline
events, each retaining the source sentence and section as evidence.
"""

from __future__ import annotations

from coruscant.common.types import NormalizedDocument
from coruscant.intelligence.models import ExtractedEvent
from coruscant.intelligence.text import headline, iso_date, primary_category, sentences

EVENT_CATEGORIES = {
    "product",
    "m&a",
    "executive",
    "regulatory",
    "litigation",
    "guidance",
    "capital_allocation",
    "supply_chain",
}


class ReferenceEventExtractor:
    def extract(
        self, document: NormalizedDocument, *, company_slug: str, source_type: str
    ) -> list[ExtractedEvent]:
        occurred_at = iso_date(document.published_at)
        events: list[ExtractedEvent] = []
        seen: set[str] = set()
        for section in document.sections:
            title = str(section.get("title") or "")
            content = str(section.get("content") or "")
            for sentence in sentences(content):
                category = primary_category(sentence)
                if category not in EVENT_CATEGORIES or sentence in seen:
                    continue
                seen.add(sentence)
                events.append(
                    ExtractedEvent(
                        canonical_id=document.canonical_id,
                        company_slug=company_slug,
                        source_type=source_type,
                        category=category,
                        title=headline(sentence),
                        description=sentence,
                        occurred_at=occurred_at,
                        source_uri=document.source_uri,
                        section_title=title or None,
                    )
                )
        return events
