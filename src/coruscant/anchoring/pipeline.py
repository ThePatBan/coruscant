"""Anchoring pipeline: resolve nodes to LEIs, enrich, label the rest unresolved.

Per-kind precision gate (thin records demand conservatism, §4.2):

* **Company** — confirm on an exact/core legal-name match to an *active* LEI. Our
  node names are common labels ("Apple", "3M"); GLEIF holds canonical legal names
  ("Apple Inc.", "3M COMPANY"), so a suffix-aware core match is itself strong.
* **Subsidiary** — a name + a US state, no key: confirm only when the name matches
  *and* the jurisdiction corroborates the LEI's country. Everything else is routed
  to review or left **explicitly unresolved** (`lei_status`), never dropped —
  absence is signal (Invariant #5). This is where real precision is far lower, by
  design.

Every confirmed match enriches the node (`lei`), adds a `LegalEntity` anchor node
+ a `has_lei` edge (substrate: provenance + access_tier + valid-time), and records
a reversible `same` resolver judgement. The LEI is an *anchor*, never the PK (§2.2).
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel

from coruscant.anchoring.provider import AnchorMatch, AnchorQuery, LeiProvider
from coruscant.common.types import GraphEdge, GraphNode
from coruscant.knowledge_graph import substrate
from coruscant.knowledge_graph.resolution import Resolver, Verdict
from coruscant.knowledge_graph.store import KnowledgeGraphStore

LEGAL_ENTITY_KIND = "LegalEntity"
ANCHOR_RUN_KIND = "AnchorRun"
ANCHOR_RUN_KEY = "latest"
HAS_LEI = "has_lei"
LEI_CANDIDATE = "lei_candidate"
GLEIF_SOURCE = "gleif"
LEI = "lei"
LEI_STATUS = "lei_status"  # "resolved" | "review" | "unresolved"

_DEFAULT_FLOOR = 0.97  # exact- or core-name match; below this is not a confirmation


class AnchorSummary(BaseModel):
    connected: bool
    considered: int
    resolved: int
    review: int
    unresolved: int
    companies_resolved: int
    subsidiaries_resolved: int
    provider: str | None = None


def _confirm(match: AnchorMatch, *, floor: float) -> bool:
    if not match.record.is_active():
        return False
    if match.query.kind == "Subsidiary":  # thin records → also need jurisdiction agreement
        return match.score >= floor and match.corroborated
    return match.score >= floor


def _set_node_prop(store: KnowledgeGraphStore, kind: str, key: str, updates: dict[str, object]) -> None:
    node = store.get_node(kind, key)
    if node is None:
        return
    props = dict(node.properties)
    props.update(updates)
    store.upsert_node(GraphNode(kind=kind, key=key, properties=props))


def _ensure_legal_entity(store: KnowledgeGraphStore, match: AnchorMatch) -> None:
    record = match.record
    store.upsert_node(
        GraphNode(
            kind=LEGAL_ENTITY_KIND, key=record.lei,
            properties={
                "name": record.name, "source": GLEIF_SOURCE, "lei": record.lei,
                "country": record.country, "jurisdiction": record.jurisdiction,
                "status": record.status, "source_url": record.source_url,
            },
        )
    )


def anchor_entities(
    store: KnowledgeGraphStore,
    provider: LeiProvider,
    resolver: Resolver,
    *,
    observed_at: date | str,
    kinds: tuple[str, ...] = ("Company", "Subsidiary"),
    floor: float = _DEFAULT_FLOOR,
) -> AnchorSummary:
    """Anchor every node of ``kinds`` to a GLEIF LEI where confirmable."""

    queries: list[AnchorQuery] = []
    for kind in kinds:
        for node in store.nodes_of_kind(kind):
            queries.append(
                AnchorQuery(
                    kind=kind, key=node.key,
                    name=str(node.properties.get("name") or node.key),
                    jurisdiction=(str(node.properties.get("jurisdiction"))
                                  if node.properties.get("jurisdiction") else None),
                )
            )
    considered = len(queries)
    best_by_node: dict[tuple[str, str], AnchorMatch] = {}
    for match in provider.resolve(queries):
        node_id = (match.query.kind, match.query.key)
        prior = best_by_node.get(node_id)
        if prior is None or match.score > prior.score:
            best_by_node[node_id] = match

    resolved = review = companies_resolved = subsidiaries_resolved = 0
    for kind in kinds:
        for node in store.nodes_of_kind(kind):
            node_id = (kind, node.key)
            candidate = best_by_node.get(node_id)
            if candidate is None:
                _set_node_prop(store, kind, node.key,
                               {LEI_STATUS: "unresolved", "lei_reason": "no_candidate"})
                continue
            match = candidate
            legal = (LEGAL_ENTITY_KIND, match.record.lei)
            if _confirm(match, floor=floor):
                _ensure_legal_entity(store, match)
                _set_node_prop(store, kind, node.key, {LEI: match.record.lei, LEI_STATUS: "resolved"})
                resolver.decide(node_id, legal, Verdict.SAME, decided_at=observed_at,
                                score=match.score, method=provider.name, decided_by="anchor")
                store.upsert_edge(
                    GraphEdge(
                        source_kind=kind, source_key=node.key, relation=HAS_LEI,
                        target_kind=LEGAL_ENTITY_KIND, target_key=match.record.lei,
                        properties=substrate.stamp(
                            {"score": match.score, "matched_name": match.matched_name,
                             "corroborated": match.corroborated, "review_status": "confirmed"},
                            source=GLEIF_SOURCE, access_tier=substrate.AccessTier.PUBLIC,
                            observed_at=observed_at, valid_from=match.record.registered_at,
                        ),
                    )
                )
                resolved += 1
                if kind == "Subsidiary":
                    subsidiaries_resolved += 1
                else:
                    companies_resolved += 1
            else:
                _ensure_legal_entity(store, match)
                _set_node_prop(store, kind, node.key,
                               {LEI_STATUS: "review", "lei_candidate": match.record.lei})
                resolver.decide(node_id, legal, Verdict.UNDECIDED, decided_at=observed_at,
                                score=match.score, method=provider.name, decided_by="anchor")
                store.upsert_edge(
                    GraphEdge(
                        source_kind=kind, source_key=node.key, relation=LEI_CANDIDATE,
                        target_kind=LEGAL_ENTITY_KIND, target_key=match.record.lei,
                        properties=substrate.stamp(
                            {"score": match.score, "matched_name": match.matched_name,
                             "corroborated": match.corroborated, "review_status": "needs-review"},
                            source=GLEIF_SOURCE, access_tier=substrate.AccessTier.PUBLIC,
                            observed_at=observed_at, valid_from=match.record.registered_at,
                        ),
                    )
                )
                review += 1

    unresolved = considered - resolved - review
    store.upsert_node(
        GraphNode(
            kind=ANCHOR_RUN_KIND, key=ANCHOR_RUN_KEY,
            properties={
                "name": "Latest anchoring run", "source": "anchoring", "provider": provider.name,
                "considered": considered, "resolved": resolved, "review": review,
                "unresolved": unresolved, "companies_resolved": companies_resolved,
                "subsidiaries_resolved": subsidiaries_resolved,
                "observed_at": observed_at if isinstance(observed_at, str) else observed_at.isoformat(),
            },
        )
    )
    return AnchorSummary(
        connected=provider.connected(), considered=considered, resolved=resolved, review=review,
        unresolved=unresolved, companies_resolved=companies_resolved,
        subsidiaries_resolved=subsidiaries_resolved, provider=provider.name,
    )
