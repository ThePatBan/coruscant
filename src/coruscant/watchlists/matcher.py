"""Match watchlist items against material changes and events -> notifications.

Deterministic and fully source-linked: each notification points at the document
(source_uri + canonical_id) that triggered it.
"""

from __future__ import annotations

from hashlib import sha256

from coruscant.common.config import CompanyConfig
from coruscant.intelligence.models import ChangeSet, ExtractedEvent
from coruscant.knowledge_graph.queries import exposure_to_country
from coruscant.knowledge_graph.store import KnowledgeGraphStore
from coruscant.watchlists.models import Notification, WatchItem


def _nid(item: WatchItem, kind: str, canonical_id: str | None, title: str) -> str:
    raw = f"{item.type}|{item.value.lower()}|{kind}|{canonical_id}|{title}"
    return sha256(raw.encode("utf-8")).hexdigest()[:16]


def match_watch_items(
    items: list[WatchItem],
    *,
    events: list[ExtractedEvent],
    change_sets: list[ChangeSet],
    companies: list[CompanyConfig],
    graph: KnowledgeGraphStore | None,
    now_iso: str,
    per_item_limit: int = 25,
) -> list[Notification]:
    by_slug = {c.slug: c for c in companies}
    name_to_slug = {c.name.lower(): c.slug for c in companies}
    material = [cs for cs in change_sets if cs.material]
    out: dict[str, Notification] = {}

    def emit(
        item: WatchItem,
        kind: str,
        title: str,
        detail: str,
        category: str | None,
        source_uri: str | None,
        canonical_id: str | None,
    ) -> None:
        nid = _nid(item, kind, canonical_id, title)
        if nid in out:
            return
        out[nid] = Notification(
            id=nid,
            watch_type=item.type,
            watch_value=item.value,
            kind=kind,
            title=title,
            detail=detail,
            category=category,
            source_uri=source_uri,
            canonical_id=canonical_id,
            created_at=now_iso,
        )

    def company_label(slug: str) -> str:
        company = by_slug.get(slug)
        return company.name if company else slug

    def emit_change(item: WatchItem, cs: ChangeSet, reason: str) -> None:
        first = cs.changes[0]
        emit(
            item,
            "change",
            f"{company_label(cs.company_slug)}: {reason}",
            first.statement,
            first.category,
            first.evidence.source_uri,
            first.evidence.canonical_id,
        )

    def count(item: WatchItem) -> int:
        return sum(1 for n in out.values() if n.watch_type == item.type and n.watch_value == item.value)

    for item in items:
        value = item.value.strip().lower()

        if item.type == "company":
            target = value if value in by_slug else name_to_slug.get(value, value)
            for cs in material:
                if count(item) >= per_item_limit:
                    break
                if cs.company_slug == target:
                    emit_change(item, cs, f"{cs.added_count} material change(s)")

        elif item.type == "country":
            exposed = set()
            if graph is not None:
                exposure = exposure_to_country(graph, item.value)
                exposed = {p.company.key for p in exposure.exposed} | {d.key for d in exposure.direct}
            for cs in material:
                if count(item) >= per_item_limit:
                    break
                if cs.company_slug in exposed:
                    emit_change(item, cs, f"exposure to {item.value} — material change")

        elif item.type == "industry":
            slugs = {c.slug for c in companies if (c.industry or "").lower() == value}
            for cs in material:
                if count(item) >= per_item_limit:
                    break
                if cs.company_slug in slugs:
                    emit_change(item, cs, f"{item.value} — material change")

        elif item.type == "supply_chain":
            for cs in material:
                if count(item) >= per_item_limit:
                    break
                for change in cs.changes:
                    if change.category == "supply_chain" or "supply chain" in change.statement.lower():
                        emit_change(item, cs, "supply-chain change")
                        break

        else:  # executive, topic, keyword -> text match over changes and events
            for cs in material:
                if count(item) >= per_item_limit:
                    break
                for change in cs.changes:
                    if value in change.statement.lower():
                        emit_change(item, cs, f"matched '{item.value}'")
                        break
            for event in events:
                if count(item) >= per_item_limit:
                    break
                if value in event.description.lower() or value in event.title.lower():
                    emit(
                        item,
                        "event",
                        f"{company_label(event.company_slug)}: {event.title}",
                        event.description,
                        event.category,
                        event.source_uri,
                        event.canonical_id,
                    )

    return list(out.values())
