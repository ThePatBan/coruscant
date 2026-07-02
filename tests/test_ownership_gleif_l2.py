"""GLEIF Level-2 accounting consolidation as an auxiliary control signal.

Parses GLEIF relationship records into ``consolidates`` edges (never %-ownership,
never beneficial ownership), reconciles them to existing LEI-anchored nodes (enrich,
don't duplicate), dedups direct/ultimate duplicates, and — critically — never
overwrites an existing anchor or an ordinary ownership edge (a declared ``owns`` and
an accounting ``consolidates`` between the same pair coexist as distinct claims).

Hermetic — relationship JSON is injected; no network."""

from __future__ import annotations

import json

from coruscant.common.types import GraphNode
from coruscant.knowledge_graph.memory import InMemoryKnowledgeGraphStore
from coruscant.exposure.queries import company_owners
from coruscant.ownership import (
    CONSOLIDATES,
    OWNS,
    GleifL2ConsolidationProvider,
    OwnershipBasis,
    OwnershipParty,
    OwnershipRecord,
    PartyAnchor,
    StaticOwnershipProvider,
    ingest_ownership,
    parse_gleif_relationships,
)
from coruscant.ownership.gleif_l2 import GLEIF_L2_SOURCE

_PARENT_LEI = "PARENT00000000000001"
_CHILD_LEI = "CHILD000000000000001"

# GLEIF relationship records: a direct-consolidation and (redundant) ultimate one for
# the same pair, plus a non-consolidation relationship that must be ignored.
_RELATIONSHIPS = {
    "data": [
        {"type": "relationship-records", "attributes": {"relationship": {
            "startNode": {"id": _CHILD_LEI}, "endNode": {"id": _PARENT_LEI},
            "relationshipType": "IS_DIRECTLY_CONSOLIDATED_BY", "relationshipStatus": "ACTIVE",
            "relationshipPeriods": [
                {"startDate": "2019-01-01T00:00:00Z", "endDate": None, "periodType": "RELATIONSHIP_PERIOD"},
                {"startDate": "2020-01-01T00:00:00Z", "endDate": None, "periodType": "ACCOUNTING_PERIOD"}]}}},
        {"type": "relationship-records", "attributes": {"relationship": {
            "startNode": {"id": _CHILD_LEI}, "endNode": {"id": _PARENT_LEI},
            "relationshipType": "IS_ULTIMATELY_CONSOLIDATED_BY", "relationshipStatus": "ACTIVE",
            "relationshipPeriods": [
                {"startDate": "2020-01-01T00:00:00Z", "endDate": None, "periodType": "ACCOUNTING_PERIOD"}]}}},
        {"type": "relationship-records", "attributes": {"relationship": {
            "startNode": {"id": _CHILD_LEI}, "endNode": {"id": "FUNDMGR0000000000001"},
            "relationshipType": "IS_FUND_MANAGED_BY", "relationshipStatus": "ACTIVE"}}},
    ]
}


def _lei_store() -> InMemoryKnowledgeGraphStore:
    store = InMemoryKnowledgeGraphStore()
    store.upsert_node(GraphNode(kind="Company", key="parentco", properties={
        "name": "Parent SA", "lei": _PARENT_LEI, "source": "gleif-anchor"}))
    store.upsert_node(GraphNode(kind="Company", key="childco", properties={
        "name": "Child Ltd", "lei": _CHILD_LEI, "source": "uk-lse"}))
    return store


# -- parsing -------------------------------------------------------------------

def test_parse_maps_consolidation_parent_child_and_dedups() -> None:
    records = parse_gleif_relationships(json.dumps(_RELATIONSHIPS))
    # Direct + ultimate for the same pair dedup to one; the fund relationship is dropped.
    assert len(records) == 1
    rec = records[0]
    assert rec.basis == OwnershipBasis.ACCOUNTING_CONSOLIDATION
    # end node is the parent (holder); start node the child (subject).
    assert rec.holder.anchor == PartyAnchor(scheme="lei", value=_PARENT_LEI)
    assert rec.subject.anchor == PartyAnchor(scheme="lei", value=_CHILD_LEI)
    assert rec.source == GLEIF_L2_SOURCE
    assert rec.valid_from == "2020-01-01"  # the ACCOUNTING_PERIOD start
    # Never a percentage — consolidation is not %-ownership.
    assert rec.percentage is None and rec.percentage_band is None


def test_parse_skips_lapsed_and_dangling() -> None:
    lapsed = {"data": [{"attributes": {"relationship": {
        "startNode": {"id": _CHILD_LEI}, "endNode": {"id": _PARENT_LEI},
        "relationshipType": "IS_DIRECTLY_CONSOLIDATED_BY", "relationshipStatus": "LAPSED"}}}]}
    assert parse_gleif_relationships(json.dumps(lapsed)) == []
    dangling = {"data": [{"attributes": {"relationship": {
        "startNode": {"id": ""}, "endNode": {"id": _PARENT_LEI},
        "relationshipType": "IS_DIRECTLY_CONSOLIDATED_BY"}}}]}
    assert parse_gleif_relationships(json.dumps(dangling)) == []
    assert parse_gleif_relationships("") == []


# -- enrichment: resolves onto existing LEI-anchored nodes ---------------------

def test_ingest_enriches_existing_lei_nodes_without_duplicating() -> None:
    store = _lei_store()
    provider = GleifL2ConsolidationProvider(text=json.dumps(_RELATIONSHIPS))
    summary = ingest_ownership(store, provider, observed_at="2026-07-02")
    assert summary.consolidates == 1 and summary.owns == 0 and summary.beneficial_owner_of == 0
    # No LEI-surrogate nodes were created — both ends resolved to the covered nodes.
    assert store.get_node("Company", "company-lei-parent00000000000001") is None
    edge = store.edges_by_relation(CONSOLIDATES)[0]
    assert edge.source_key == "parentco" and edge.target_key == "childco"
    # Existing anchors/authority left intact (enrich, don't overwrite).
    assert store.get_node("Company", "childco").properties["source"] == "uk-lse"
    assert store.get_node("Company", "childco").properties["lei"] == _CHILD_LEI


# -- dedup / idempotency -------------------------------------------------------

def test_reingest_is_idempotent() -> None:
    store = _lei_store()
    provider = GleifL2ConsolidationProvider(text=json.dumps(_RELATIONSHIPS))
    ingest_ownership(store, provider, observed_at="2026-07-02")
    edges = store.edge_count()
    ingest_ownership(store, provider, observed_at="2026-07-03")
    assert store.edge_count() == edges
    assert len(store.edges_by_relation(CONSOLIDATES)) == 1


# -- conflict handling: consolidation is auxiliary, never a substitute ---------

def test_consolidation_and_declared_ownership_coexist_distinctly() -> None:
    # A declared shareholding already links parent→child. Adding GLEIF consolidation
    # for the same pair must NOT overwrite it: they are distinct claims, distinct edges.
    store = _lei_store()
    declared = OwnershipRecord(
        holder=OwnershipParty(name="Parent SA", kind="Company",
                              anchor=PartyAnchor(scheme="lei", value=_PARENT_LEI)),
        subject=OwnershipParty(name="Child Ltd", kind="Company",
                               anchor=PartyAnchor(scheme="lei", value=_CHILD_LEI)),
        basis=OwnershipBasis.DECLARED_SHAREHOLDING, percentage=80.0, source="sec-13d")
    ingest_ownership(store, StaticOwnershipProvider([declared]), observed_at="2026-07-01")
    ingest_ownership(store, GleifL2ConsolidationProvider(text=json.dumps(_RELATIONSHIPS)),
                     observed_at="2026-07-02")
    # Both edges present, distinct relations, neither clobbered.
    assert len(store.edges_by_relation(OWNS)) == 1
    assert len(store.edges_by_relation(CONSOLIDATES)) == 1
    assert store.edges_by_relation(OWNS)[0].properties["percentage"] == 80.0
    # A privileged/public read of the child's owners shows both, correctly separated.
    owners = company_owners(store, "childco")
    relations = sorted(o.relation for o in owners.owners)
    assert relations == ["consolidates", "owns"]


# -- provider / live scoping ---------------------------------------------------

def test_provider_from_file_and_market(tmp_path) -> None:  # type: ignore[no-untyped-def]
    feed = tmp_path / "rels.json"
    feed.write_text(json.dumps(_RELATIONSHIPS))
    provider = GleifL2ConsolidationProvider.from_file(feed)
    assert provider.connected() and provider.market == "*"
    assert len(provider.list_ownership()) == 1


def test_live_provider_scopes_to_supplied_leis(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    calls: list[str] = []

    def fake_get(self, path):  # noqa: ANN001
        calls.append(path)
        if path.endswith("direct-parent-relationship"):
            return _RELATIONSHIPS
        return {"data": []}

    monkeypatch.setattr(GleifL2ConsolidationProvider, "_get", fake_get)
    provider = GleifL2ConsolidationProvider(leis=[_CHILD_LEI])
    records = provider.list_ownership()
    assert len(records) == 1
    assert any(_CHILD_LEI in c for c in calls)


# -- runtime wiring ------------------------------------------------------------

def test_run_ownership_gleif_l2_from_file(tmp_path) -> None:  # type: ignore[no-untyped-def]
    from coruscant.apps.runtime import run_ownership
    from coruscant.common.config import Settings
    from coruscant.knowledge_graph.persistence import load_graph, save_graph

    data_dir = tmp_path / "data"
    settings = Settings(data_dir=data_dir, database_url=f"sqlite:///{data_dir / 'c.db'}")
    save_graph(_lei_store(), settings.graph_snapshot_path)
    feed = tmp_path / "rels.json"
    feed.write_text(json.dumps(_RELATIONSHIPS))

    summary = run_ownership(settings, file_path=feed, provider_name="gleif-l2")
    assert summary.consolidates == 1 and summary.provider == GLEIF_L2_SOURCE
    graph = load_graph(settings.graph_snapshot_path)
    assert len(graph.edges_by_relation(CONSOLIDATES)) == 1


def test_run_ownership_gleif_l2_live_scopes_to_anchored_leis(monkeypatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    from coruscant.apps.runtime import run_ownership
    from coruscant.common.config import Settings
    from coruscant.knowledge_graph.persistence import save_graph

    data_dir = tmp_path / "data"
    settings = Settings(data_dir=data_dir, database_url=f"sqlite:///{data_dir / 'c.db'}")
    save_graph(_lei_store(), settings.graph_snapshot_path)

    def fake_get(self, path):  # noqa: ANN001
        return _RELATIONSHIPS if path.endswith("direct-parent-relationship") else {"data": []}

    monkeypatch.setattr(GleifL2ConsolidationProvider, "_get", fake_get)
    summary = run_ownership(settings, file_path=None, provider_name="gleif-l2")
    assert summary.consolidates == 1


def test_cli_ownership_accepts_gleif_l2() -> None:
    from coruscant.apps import cli

    ns = cli.build_parser().parse_args(["ownership", "--provider", "gleif-l2", "--file", "r.json"])
    assert ns.provider == "gleif-l2"
