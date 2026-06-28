"""Deterministic change detection — the "what changed?" engine.

Compares the current document against the previous disclosure of the same
(company, source type) by diffing normalized source sentences. Added and removed
statements are categorized (risk, guidance, executive, supply chain, …) and each
keeps the exact source span as evidence on the side it came from.
"""

from __future__ import annotations

from coruscant.common.types import NormalizedDocument
from coruscant.intelligence.models import ChangeSet, Claim, DocumentChange
from coruscant.intelligence.text import normalize_statement, primary_category, sentences

# Category ordering for "most material first" presentation.
_MATERIALITY = [
    "guidance",
    "executive",
    "m&a",
    "litigation",
    "regulatory",
    "supply_chain",
    "capital_allocation",
    "risk",
    "product",
    "opportunity",
    "financial",
    "general",
]


def _statement_index(document: NormalizedDocument) -> dict[str, tuple[str, str]]:
    """Map normalized sentence -> (original sentence, section title)."""

    index: dict[str, tuple[str, str]] = {}
    for section in document.sections:
        title = str(section.get("title") or "")
        content = str(section.get("content") or "")
        for sentence in sentences(content):
            key = normalize_statement(sentence)
            if key and key not in index:
                index[key] = (sentence, title)
    return index


def _materiality_rank(category: str) -> int:
    try:
        return _MATERIALITY.index(category)
    except ValueError:
        return len(_MATERIALITY)


class ReferenceChangeDetector:
    def diff(
        self,
        current: NormalizedDocument,
        previous: NormalizedDocument | None,
        *,
        company_slug: str,
        source_type: str,
    ) -> ChangeSet:
        change_set = ChangeSet(
            company_slug=company_slug,
            source_type=source_type,
            current_canonical_id=current.canonical_id,
            previous_canonical_id=previous.canonical_id if previous else None,
            current_title=current.title,
            previous_title=previous.title if previous else None,
        )
        if previous is None:
            return change_set

        current_index = _statement_index(current)
        previous_index = _statement_index(previous)

        changes: list[DocumentChange] = []
        for key, (sentence, title) in current_index.items():
            if key not in previous_index:
                category = primary_category(sentence)
                changes.append(
                    DocumentChange(
                        kind="added",
                        category=category,
                        statement=sentence,
                        evidence=Claim(
                            text=sentence,
                            source_uri=current.source_uri,
                            section_title=title or None,
                            canonical_id=current.canonical_id,
                            category=category,
                        ),
                    )
                )
        for key, (sentence, title) in previous_index.items():
            if key not in current_index:
                category = primary_category(sentence)
                changes.append(
                    DocumentChange(
                        kind="removed",
                        category=category,
                        statement=sentence,
                        evidence=Claim(
                            text=sentence,
                            source_uri=previous.source_uri,
                            section_title=title or None,
                            canonical_id=previous.canonical_id,
                            category=category,
                        ),
                    )
                )

        changes.sort(key=lambda c: (_materiality_rank(c.category), c.kind))
        change_set.changes = changes
        return change_set
