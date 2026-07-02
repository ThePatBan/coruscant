"""Reconcile sourced ownership statements into the graph as three DISTINCT edge
types — never conflated (``docs/global-exposure-architecture.md`` §2.4):

* ``owns``                — a declared %-shareholding (public disclosure)
* ``beneficial_owner_of`` — a natural person's ultimate ownership/control (access-restricted)
* ``consolidates``        — accounting consolidation, parent → subsidiary (GLEIF L2; NOT %-ownership)

Every edge is substrate-stamped (:mod:`coruscant.knowledge_graph.substrate`):
``source`` (Invariant #1), ``access_tier`` (enforced at query time, not just
tagged), and bitemporal validity so "was this owner in control *on date D*?" is
answerable. Subjects/holders resolve to existing nodes by external anchor where
possible (enrich, don't duplicate — Invariant #2); the rest get a stable surrogate
labelled ``ownership_status: unresolved`` — counted, never fabricated.

This is the FOUNDATION for UBO/contagion work, not a completeness claim. Crucially:
no beneficial owner is *derived* from a shareholding here — declared %-ownership and
beneficial ownership stay separate edges from separate sources; the chain-following
inference that turns one into the other is deliberate future work.
"""

from __future__ import annotations

import re
from datetime import date

from pydantic import BaseModel, Field

from coruscant.common.types import GraphEdge, GraphNode
from coruscant.knowledge_graph import substrate
from coruscant.knowledge_graph.store import KnowledgeGraphStore
from coruscant.ownership.models import OwnershipBasis, OwnershipParty
from coruscant.ownership.provider import OwnershipProvider

OWNS = "owns"  # declared %-shareholding: holder --owns--> subject
BENEFICIAL_OWNER_OF = "beneficial_owner_of"  # UBO / control: person --beneficial_owner_of--> company
CONSOLIDATES = "consolidates"  # accounting consolidation: parent --consolidates--> subsidiary

OWNERSHIP_RUN_KIND = "OwnershipRun"
OWNERSHIP_STATUS = "ownership_status"  # "unresolved" on a party surrogate we could not anchor

# Basis → relation, and basis → default access tier. Declared shareholding and GLEIF
# consolidation are public; beneficial ownership is legitimate-interest (post-CJEU
# C-37/20, EU BO access is restricted) — the tier the query gate enforces.
_RELATION_BY_BASIS = {
    OwnershipBasis.DECLARED_SHAREHOLDING: OWNS,
    OwnershipBasis.BENEFICIAL_OWNER: BENEFICIAL_OWNER_OF,
    OwnershipBasis.ACCOUNTING_CONSOLIDATION: CONSOLIDATES,
}
_DEFAULT_TIER_BY_BASIS = {
    OwnershipBasis.DECLARED_SHAREHOLDING: substrate.AccessTier.PUBLIC,
    OwnershipBasis.BENEFICIAL_OWNER: substrate.AccessTier.LEGITIMATE_INTEREST,
    OwnershipBasis.ACCOUNTING_CONSOLIDATION: substrate.AccessTier.PUBLIC,
}

_ANCHOR_KINDS = ("Company", "Subsidiary", "Person", "Entity", "Fund")


class OwnershipSummary(BaseModel):
    connected: bool
    provider: str
    considered: int = 0  # statements the provider listed
    edges: int = 0  # edges present after this run (deduped)
    owns: int = 0
    beneficial_owner_of: int = 0
    consolidates: int = 0
    subjects_unresolved: int = 0  # subjects we could not anchor → surrogate
    holders_unresolved: int = 0  # holders (people/entities) with no matching node
    by_access_tier: dict[str, int] = Field(default_factory=dict)


def _slug(text: str) -> str:
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", text.strip().lower())).strip("-") or "x"


def _anchor_index(store: KnowledgeGraphStore) -> dict[tuple[str, str], str]:
    """``{(scheme, VALUE) → node key}`` across the resolvable node kinds — the ER
    hook that lets an ownership statement's LEI/CIK/ISIN land on the covered node."""

    index: dict[tuple[str, str], str] = {}
    for kind in _ANCHOR_KINDS:
        for node in store.nodes_of_kind(kind):
            props = node.properties
            for scheme in ("cik", "lei", "isin"):
                val = props.get(scheme)
                if isinstance(val, str) and val.strip():
                    index.setdefault((scheme, val.strip().upper()), node.key)
            for a in props.get("anchors") or []:
                if isinstance(a, dict) and a.get("scheme") and a.get("value"):
                    index.setdefault(
                        (str(a["scheme"]), str(a["value"]).strip().upper()), node.key
                    )
    return index


def _surrogate_key(party: OwnershipParty) -> str:
    if party.anchor is not None:
        return f"{party.kind.lower()}-{_slug(party.anchor.scheme)}-{_slug(party.anchor.value)}"
    return f"{party.kind.lower()}-{_slug(party.name)}"


def _resolve_party(
    store: KnowledgeGraphStore,
    party: OwnershipParty,
    index: dict[tuple[str, str], str],
    *,
    source: str,
) -> tuple[str, str, bool]:
    """Resolve a party to ``(kind, key, resolved)``. Prefer an exact anchor match
    against an existing node (enrich, don't duplicate); then an explicit key; else a
    stable surrogate labelled unresolved. A resolved existing node is left untouched
    (its curated authority stands)."""

    # Matching a *prior ownership surrogate* (our own placeholder from an earlier run)
    # is not resolution — reuse its key for stability, but keep it counted unresolved
    # so the summary metric is honest and stable across re-runs.
    if party.anchor is not None:
        hit = index.get((party.anchor.scheme, party.anchor.value.strip().upper()))
        if hit is not None:
            existing = _find_node(store, hit)
            if existing is not None:
                resolved = existing.properties.get(OWNERSHIP_STATUS) != "unresolved"
                return existing.kind, existing.key, resolved
    if party.key is not None:
        existing = store.get_node(party.kind, party.key)
        if existing is not None:
            resolved = existing.properties.get(OWNERSHIP_STATUS) != "unresolved"
            return party.kind, party.key, resolved

    # Unresolved → create/refresh a lightweight surrogate. Deterministic key so a
    # re-run reuses it; identity anchor recorded so a later ER pass can merge it.
    key = _surrogate_key(party)
    if store.get_node(party.kind, key) is None:
        props: dict[str, object] = {"name": party.name, "source": source, OWNERSHIP_STATUS: "unresolved"}
        if party.anchor is not None:
            props["anchors"] = [{"scheme": party.anchor.scheme, "value": party.anchor.value}]
        store.upsert_node(GraphNode(kind=party.kind, key=key, properties=props))
    return party.kind, key, False


def _find_node(store: KnowledgeGraphStore, key: str) -> GraphNode | None:
    for kind in _ANCHOR_KINDS:
        node = store.get_node(kind, key)
        if node is not None:
            return node
    return None


def ingest_ownership(
    store: KnowledgeGraphStore,
    provider: OwnershipProvider,
    *,
    observed_at: date | str,
) -> OwnershipSummary:
    """Ingest ``provider``'s ownership statements as substrate-stamped edges of the
    three distinct types, resolving parties to existing nodes by anchor. Idempotent
    (edge identity dedups); records an ``OwnershipRun`` summary."""

    records = provider.list_ownership()
    index = _anchor_index(store)

    by_relation = {OWNS: 0, BENEFICIAL_OWNER_OF: 0, CONSOLIDATES: 0}
    by_tier: dict[str, int] = {}
    subjects_unresolved = 0
    holders_unresolved = 0

    for record in records:
        relation = _RELATION_BY_BASIS[record.basis]
        tier = record.access_tier or _DEFAULT_TIER_BY_BASIS[record.basis].value

        holder_kind, holder_key, holder_ok = _resolve_party(
            store, record.holder, index, source=record.source
        )
        subject_kind, subject_key, subject_ok = _resolve_party(
            store, record.subject, index, source=record.source
        )
        if not holder_ok:
            holders_unresolved += 1
        if not subject_ok:
            subjects_unresolved += 1

        # Only sourced facts are stamped — no invented percentage. None-valued
        # optional facts are dropped so the edge carries only what the source stated.
        base: dict[str, object] = {
            "holder_name": record.holder.name,
            "subject_name": record.subject.name,
            "basis": record.basis.value,
            "holder_resolved": holder_ok,
            "subject_resolved": subject_ok,
            "review_status": "confirmed",
        }
        if record.percentage is not None:
            base["percentage"] = record.percentage
        if record.percentage_band is not None:
            base["percentage_band"] = record.percentage_band
        if record.interest is not None:
            base["interest"] = record.interest
        if record.source_url is not None:
            base["source_url"] = record.source_url

        store.upsert_edge(GraphEdge(
            source_kind=holder_kind, source_key=holder_key,
            relation=relation, target_kind=subject_kind, target_key=subject_key,
            properties=substrate.stamp(
                base, source=record.source, access_tier=tier,
                observed_at=observed_at, valid_from=record.valid_from, valid_to=record.valid_to,
            ),
        ))
        by_relation[relation] += 1
        by_tier[tier] = by_tier.get(tier, 0) + 1

    total_edges = (
        len(store.edges_by_relation(OWNS))
        + len(store.edges_by_relation(BENEFICIAL_OWNER_OF))
        + len(store.edges_by_relation(CONSOLIDATES))
    )
    observed = observed_at if isinstance(observed_at, str) else observed_at.isoformat()
    store.upsert_node(GraphNode(
        kind=OWNERSHIP_RUN_KIND, key="ownership",
        properties={
            "name": "ownership run", "source": "ownership", "provider": provider.name,
            "market": provider.market,
            "considered": len(records), "edges": total_edges,
            "owns": by_relation[OWNS], "beneficial_owner_of": by_relation[BENEFICIAL_OWNER_OF],
            "consolidates": by_relation[CONSOLIDATES],
            "subjects_unresolved": subjects_unresolved, "holders_unresolved": holders_unresolved,
            "observed_at": observed,
        },
    ))
    return OwnershipSummary(
        connected=provider.connected(), provider=provider.name, considered=len(records),
        edges=total_edges, owns=by_relation[OWNS],
        beneficial_owner_of=by_relation[BENEFICIAL_OWNER_OF], consolidates=by_relation[CONSOLIDATES],
        subjects_unresolved=subjects_unresolved, holders_unresolved=holders_unresolved,
        by_access_tier=by_tier,
    )
