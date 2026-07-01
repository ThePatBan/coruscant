"""Screening pipeline: gate candidates, record reversible judgements, project edges.

Turns a provider's candidate matches into graph facts under a strict precision
gate (§4.3):

* **Nothing auto-confirms on a name alone.** A match is confirmed only when a
  second attribute corroborates (country / birth year); Form-4 insiders — a
  different PEP base rate — clear a higher bar. Everything else routes to human
  review as a labelled ``screening_candidate`` edge (never a ``pep`` / ``sanctioned``
  one), so an unreviewed guess is never dressed up as a confirmed hit.
* **Every decision is a reversible resolver judgement** (``same`` for confirmed,
  ``undecided`` for needs-review), so a reviewer can later confirm or reject and
  the graph re-projects from the log.
* **Every edge carries provenance + access_tier + valid-time** via
  :mod:`coruscant.knowledge_graph.substrate`.

A ``ScreeningRun`` node records the denominator (how many were screened) so the
panel can show an honest "N screened, 0 confirmed, M in review" state.
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel

from coruscant.common.types import GraphEdge, GraphNode
from coruscant.knowledge_graph import substrate
from coruscant.knowledge_graph.entities import entity_key
from coruscant.knowledge_graph.resolution import Resolver, Verdict
from coruscant.knowledge_graph.store import KnowledgeGraphStore
from coruscant.screening.provider import ScreeningMatch, ScreeningProvider, ScreeningQuery

WATCHLIST_KIND = "WatchlistEntity"
SCREENING_RUN_KIND = "ScreeningRun"
SCREENING_RUN_KEY = "latest"
PEP = "pep"
SANCTIONED = "sanctioned"
CANDIDATE = "screening_candidate"
SCREENING_SOURCE = "opensanctions"

# Form-4 insider-holders are a different PEP base rate than officers/directors;
# name-only noise is worse there, so they clear a higher confirmation bar — only
# an exact-name match (the deterministic scorer is precision-first: a reversed-order
# match scores 0.98, so this floor holds those for review while confirming officers).
_INSIDER_HINTS = ("form4", "form-4", "holding", "insider")
_INSIDER_CONFIRM_FLOOR = 0.99


class ScreeningSummary(BaseModel):
    connected: bool
    screened: int  # people put through the screen (the denominator)
    candidates: int  # candidate matches the provider surfaced
    confirmed: int  # matches that passed the precision gate
    needs_review: int  # matches routed to human review
    pep: int  # confirmed pep edges written
    sanctioned: int  # confirmed sanctioned edges written
    dataset: str | None = None


def _is_insider(source: str | None) -> bool:
    low = (source or "").lower()
    return any(hint in low for hint in _INSIDER_HINTS)


def _passes_gate(match: ScreeningMatch, confirm_threshold: float) -> bool:
    if not match.corroborated:  # name-only never auto-confirms (§4.3)
        return False
    floor = max(confirm_threshold, _INSIDER_CONFIRM_FLOOR) if _is_insider(match.query.source) else confirm_threshold
    return match.score >= floor


def _watchlist_key(record_id: str) -> str:
    return entity_key(f"os-{record_id}")


def _ensure_watchlist_node(store: KnowledgeGraphStore, match: ScreeningMatch, key: str) -> None:
    record = match.record
    store.upsert_node(
        GraphNode(
            kind=WATCHLIST_KIND,
            key=key,
            properties={
                "name": record.name,
                "source": SCREENING_SOURCE,
                "schema": record.schema_,
                "topics": record.topics,
                "datasets": record.datasets,
                "countries": record.countries,
                "external_id": record.id,
                "source_url": record.source_url,
            },
        )
    )


def _edge_props(match: ScreeningMatch, review_status: str, observed_at: date | str) -> dict[str, object]:
    record = match.record
    valid_from = record.first_seen[:10] if record.first_seen else None
    return substrate.stamp(
        {
            "score": match.score,
            "matched_name": match.matched_name,
            "topics": record.topics,
            "datasets": record.datasets,
            "external_id": record.id,
            "review_status": review_status,
            "corroborated": match.corroborated,
        },
        source=SCREENING_SOURCE,
        access_tier=substrate.AccessTier.PUBLIC,
        observed_at=observed_at,
        valid_from=valid_from,
    )


def _confirmed_relations(match: ScreeningMatch) -> list[str]:
    relations: list[str] = []
    if match.record.is_sanctioned():
        relations.append(SANCTIONED)
    if match.record.is_pep():
        relations.append(PEP)
    return relations


def screen_people(
    store: KnowledgeGraphStore,
    provider: ScreeningProvider,
    resolver: Resolver,
    *,
    observed_at: date | str,
    confirm_threshold: float = 0.90,
    dataset: str | None = None,
) -> ScreeningSummary:
    """Screen every ``Person`` node against ``provider`` and project the results."""

    people = store.nodes_of_kind("Person")
    queries = [
        ScreeningQuery(
            kind="Person",
            key=node.key,
            name=str(node.properties.get("name") or node.key),
            source=(str(node.properties.get("source")) if node.properties.get("source") else None),
            country=(str(node.properties.get("country")) if node.properties.get("country") else None),
            birth_date=(str(node.properties.get("birth_date")) if node.properties.get("birth_date") else None),
        )
        for node in people
    ]
    matches = provider.screen(queries)

    confirmed = needs_review = pep = sanctioned = 0
    for match in matches:
        w_key = _watchlist_key(match.record.id)
        _ensure_watchlist_node(store, match, w_key)
        person = ("Person", match.query.key)
        listing = (WATCHLIST_KIND, w_key)

        relations = _confirmed_relations(match) if _passes_gate(match, confirm_threshold) else []
        if relations:
            resolver.decide(person, listing, Verdict.SAME, decided_at=observed_at,
                            score=match.score, method=provider.name, decided_by="screen")
            props = _edge_props(match, "confirmed", observed_at)
            for relation in relations:
                store.upsert_edge(
                    GraphEdge(source_kind="Person", source_key=match.query.key, relation=relation,
                              target_kind=WATCHLIST_KIND, target_key=w_key, properties=props)
                )
                if relation == PEP:
                    pep += 1
                elif relation == SANCTIONED:
                    sanctioned += 1
            confirmed += 1
        else:
            # No corroboration, below the bar, or no clear topic → human review, not
            # a fabricated confirmed hit.
            resolver.decide(person, listing, Verdict.UNDECIDED, decided_at=observed_at,
                            score=match.score, method=provider.name, decided_by="screen")
            store.upsert_edge(
                GraphEdge(source_kind="Person", source_key=match.query.key, relation=CANDIDATE,
                          target_kind=WATCHLIST_KIND, target_key=w_key,
                          properties=_edge_props(match, "needs-review", observed_at))
            )
            needs_review += 1

    store.upsert_node(
        GraphNode(
            kind=SCREENING_RUN_KIND,
            key=SCREENING_RUN_KEY,
            properties={
                "name": "Latest screening run",
                "source": "screening",
                "provider": provider.name,
                "dataset": dataset,
                "screened": len(people),
                "candidates": len(matches),
                "confirmed": confirmed,
                "needs_review": needs_review,
                "pep": pep,
                "sanctioned": sanctioned,
                "observed_at": observed_at if isinstance(observed_at, str) else observed_at.isoformat(),
            },
        )
    )
    return ScreeningSummary(
        connected=provider.connected(), screened=len(people), candidates=len(matches),
        confirmed=confirmed, needs_review=needs_review, pep=pep, sanctioned=sanctioned, dataset=dataset,
    )
