"""Group / UBO contagion: the *separate* inherited-exposure path.

Direct exposure (the seed) and inherited exposure (group members reachable through
shared control) are kept visibly distinct; each inherited hit carries the ownership
evidence chain back to the seed; beneficial-owner ties are access-restricted and
only counted for an unprivileged caller. Contagion never rewrites the underlying
ownership edges. Hermetic; edges built via the ownership pipeline; API wiring too."""

from __future__ import annotations

from coruscant.common.types import GraphNode
from coruscant.knowledge_graph import substrate
from coruscant.knowledge_graph.memory import InMemoryKnowledgeGraphStore
from coruscant.exposure.ownership_graph import group_contagion, ownership_chains
from coruscant.ownership import (
    OWNS,
    OwnershipBasis,
    OwnershipParty,
    OwnershipRecord,
    StaticOwnershipProvider,
    ingest_ownership,
)


def _co(store: InMemoryKnowledgeGraphStore, key: str, name: str) -> None:
    store.upsert_node(GraphNode(kind="Company", key=key, properties={"name": name}))


def _person(store: InMemoryKnowledgeGraphStore, key: str, name: str) -> None:
    store.upsert_node(GraphNode(kind="Person", key=key, properties={"name": name}))


def _party(key: str, name: str, kind: str = "Company") -> OwnershipParty:
    return OwnershipParty(name=name, kind=kind, key=key)


def _rec(holder: OwnershipParty, subject: OwnershipParty, basis: OwnershipBasis,
         **kw: object) -> OwnershipRecord:
    return OwnershipRecord(holder=holder, subject=subject, basis=basis, source="test", **kw)  # type: ignore[arg-type]


def _ingest(store: InMemoryKnowledgeGraphStore, records: list[OwnershipRecord]) -> None:
    ingest_ownership(store, StaticOwnershipProvider(records), observed_at="2026-07-02")


# -- parent / subsidiary group -------------------------------------------------

def test_parent_and_subsidiary_inherit_exposure_distinct_from_direct() -> None:
    # parent --owns--> seed --owns--> child.
    store = InMemoryKnowledgeGraphStore()
    for key, name in [("parent", "Parent"), ("seed", "Seed Co"), ("child", "Child")]:
        _co(store, key, name)
    _ingest(store, [
        _rec(_party("parent", "Parent"), _party("seed", "Seed Co"), OwnershipBasis.DECLARED_SHAREHOLDING),
        _rec(_party("seed", "Seed Co"), _party("child", "Child"), OwnershipBasis.DECLARED_SHAREHOLDING),
    ])
    result = group_contagion(store, "seed")
    # Direct is the seed alone; inherited are the group peers, kept distinct.
    assert [d.key for d in result.direct] == ["seed"]
    by_key = {m.company.key: m for m in result.inherited}
    assert set(by_key) == {"parent", "child"}
    assert by_key["parent"].link == "parent" and by_key["parent"].hops == 1
    assert by_key["child"].link == "subsidiary" and by_key["child"].hops == 1
    # The evidence chain is surfaced with direction + provenance.
    assert by_key["parent"].path[0].direction == "up"
    assert by_key["child"].path[0].direction == "down"
    assert by_key["parent"].path[0].relation == "owns"


# -- siblings sharing a beneficial owner (UBO contagion) -----------------------

def test_siblings_sharing_beneficial_owner_inherit_but_gated_by_tier() -> None:
    # A natural person beneficially owns both alpha and beta → they are UBO siblings.
    store = InMemoryKnowledgeGraphStore()
    _co(store, "alpha", "Alpha Co")
    _co(store, "beta", "Beta Co")
    _person(store, "mogul", "The Mogul")
    _ingest(store, [
        _rec(_party("mogul", "The Mogul", "Person"), _party("alpha", "Alpha Co"),
             OwnershipBasis.BENEFICIAL_OWNER),
        _rec(_party("mogul", "The Mogul", "Person"), _party("beta", "Beta Co"),
             OwnershipBasis.BENEFICIAL_OWNER),
    ])
    # Privileged caller: beta inherits exposure from alpha via the shared owner.
    privileged = group_contagion(store, "alpha",
                                 clearance=substrate.AccessTier.LEGITIMATE_INTEREST)
    beta = next(m for m in privileged.inherited if m.company.key == "beta")
    assert beta.link == "shares-owner"
    assert beta.shared_owner is not None and beta.shared_owner.key == "mogul"
    assert beta.hops == 2  # alpha → mogul → beta
    assert [h.direction for h in beta.path] == ["up", "down"]

    # Public caller: the beneficial-owner ties are withheld → beta is NOT reachable,
    # and the withheld hop is transparently counted (not silently dropped).
    public = group_contagion(store, "alpha")
    assert all(m.company.key != "beta" for m in public.inherited)
    assert public.restricted >= 1


# -- consolidation group -------------------------------------------------------

def test_consolidation_group_members_inherit() -> None:
    # Accounting consolidation is a group tie too (a distinct basis, still a group).
    store = InMemoryKnowledgeGraphStore()
    _co(store, "topco", "TopCo SA")
    _co(store, "subco", "SubCo Ltd")
    _ingest(store, [
        _rec(_party("topco", "TopCo SA"), _party("subco", "SubCo Ltd"),
             OwnershipBasis.ACCOUNTING_CONSOLIDATION),
    ])
    result = group_contagion(store, "subco")
    assert [m.company.key for m in result.inherited] == ["topco"]
    assert result.inherited[0].path[0].relation == "consolidates"
    assert result.inherited[0].link == "parent"


# -- honest empties + non-destructiveness --------------------------------------

def test_isolated_company_has_no_inherited_exposure() -> None:
    store = InMemoryKnowledgeGraphStore()
    _co(store, "solo", "Solo Co")
    result = group_contagion(store, "solo")
    assert result.direct[0].key == "solo" and result.inherited == []


def test_contagion_does_not_mutate_ownership_edges() -> None:
    store = InMemoryKnowledgeGraphStore()
    _co(store, "parent", "Parent")
    _co(store, "seed", "Seed Co")
    _ingest(store, [
        _rec(_party("parent", "Parent"), _party("seed", "Seed Co"), OwnershipBasis.DECLARED_SHAREHOLDING),
    ])
    before = store.edge_count()
    group_contagion(store, "seed")
    ownership_chains(store, "seed")
    # Read-only: contagion is a distinct query, not new/rewritten edges.
    assert store.edge_count() == before
    assert len(store.edges_by_relation(OWNS)) == 1


# -- API wiring ----------------------------------------------------------------

def test_contagion_and_chain_endpoints() -> None:
    from fastapi.testclient import TestClient

    from coruscant.apps.api import create_app

    store = InMemoryKnowledgeGraphStore()
    for key, name in [("parent", "Parent"), ("seed", "Seed Co")]:
        _co(store, key, name)
    _ingest(store, [
        _rec(_party("parent", "Parent"), _party("seed", "Seed Co"), OwnershipBasis.DECLARED_SHAREHOLDING),
    ])
    client = TestClient(create_app(graph_store=store, require_auth=False))

    contagion = client.get("/graph/company/seed/contagion").json()
    assert contagion["seed"]["key"] == "seed"
    assert [m["company"]["key"] for m in contagion["inherited"]] == ["parent"]

    chain = client.get("/graph/company/seed/ownership-chain").json()
    assert chain["resolved_chains"] == 1
    assert chain["chains"][0]["terminal"] == "root"
