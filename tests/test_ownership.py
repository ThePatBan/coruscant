"""Ownership substrate: the three DISTINCT edge types (declared ownership ≠
beneficial ownership ≠ accounting consolidation), BODS parsing, anchor resolution
(enrich, don't duplicate), honesty (no fabricated percentage; unresolved labelled),
provenance + bitemporal validity + access-tier enforcement, and idempotency.

Hermetic — BODS is parsed from injected text; no network."""

from __future__ import annotations

import json

from coruscant.common.types import GraphNode
from coruscant.knowledge_graph import substrate
from coruscant.knowledge_graph.memory import InMemoryKnowledgeGraphStore
from coruscant.exposure.queries import company_owners, ownership_overview
from coruscant.ownership import (
    BENEFICIAL_OWNER_OF,
    CONSOLIDATES,
    OWNS,
    OwnershipBasis,
    OwnershipParty,
    OwnershipRecord,
    PartyAnchor,
    StaticOwnershipProvider,
    ingest_ownership,
    parse_bods,
)
from coruscant.ownership.provider import BodsOwnershipProvider

# A BODS export in miniature: ACME LTD (LEI-identified) is beneficially controlled
# by a person (a disclosed 25-50% voting band, no exact figure) and 75%-owned by an
# entity (an exact declared shareholding). Mirrors the OpenOwnership statement shape.
_BODS = [
    {"statementID": "e1", "statementType": "entityStatement", "name": "ACME LTD",
     "identifiers": [{"scheme": "XI-LEI", "id": "5493001KJTIIGC8Y1R12"}]},
    {"statementID": "e2", "statementType": "entityStatement", "name": "ACME HOLDINGS LTD",
     "identifiers": [{"schemeName": "GB-COH", "id": "09999999"}]},
    {"statementID": "p1", "statementType": "personStatement",
     "names": [{"fullName": "Jane Q Owner"}]},
    {"statementID": "o1", "statementType": "ownershipOrControlStatement",
     "subject": {"describedByEntityStatement": "e1"},
     "interestedParty": {"describedByPersonStatement": "p1"},
     "interests": [{"type": "voting-rights", "share": {"minimum": 25, "maximum": 50},
                    "startDate": "2016-04-06"}]},
    {"statementID": "o2", "statementType": "ownershipOrControlStatement",
     "subject": {"describedByEntityStatement": "e1"},
     "interestedParty": {"describedByEntityStatement": "e2"},
     "interests": [{"type": "shareholding", "share": {"exact": 75}, "startDate": "2015-01-01"}]},
]


def _acme_store() -> InMemoryKnowledgeGraphStore:
    store = InMemoryKnowledgeGraphStore()
    # A covered company already anchored to its LEI (as GLEIF anchoring leaves it).
    store.upsert_node(GraphNode(kind="Company", key="acme", properties={
        "name": "ACME LTD", "lei": "5493001KJTIIGC8Y1R12", "source": "tracked"}))
    return store


# -- BODS parsing --------------------------------------------------------------

def test_parse_bods_person_is_beneficial_entity_is_declared() -> None:
    records = parse_bods(json.dumps(_BODS))
    by_basis = {r.basis: r for r in records}
    assert set(by_basis) == {OwnershipBasis.BENEFICIAL_OWNER, OwnershipBasis.DECLARED_SHAREHOLDING}

    person = by_basis[OwnershipBasis.BENEFICIAL_OWNER]
    assert person.holder.kind == "Person" and person.holder.name == "Jane Q Owner"
    assert person.subject.name == "ACME LTD"
    assert person.subject.anchor == PartyAnchor(scheme="lei", value="5493001KJTIIGC8Y1R12")
    # Honesty: a disclosed band, never a fabricated exact percentage.
    assert person.percentage is None and person.percentage_band == "25%-50%"
    assert person.interest == "voting-rights" and person.valid_from == "2016-04-06"

    entity = by_basis[OwnershipBasis.DECLARED_SHAREHOLDING]
    assert entity.holder.kind == "Company" and entity.percentage == 75.0
    assert entity.percentage_band is None


def test_parse_bods_accepts_ndjson_and_envelope() -> None:
    ndjson = "\n".join(json.dumps(s) for s in _BODS)
    assert len(parse_bods(ndjson)) == 2
    assert len(parse_bods(json.dumps({"statements": _BODS}))) == 2
    assert parse_bods("") == []


def test_parse_bods_skips_dangling_statements() -> None:
    # An ownership statement whose subject/interested party do not resolve is skipped,
    # never emitted as a half-edge.
    broken = [
        {"statementID": "o9", "statementType": "ownershipOrControlStatement",
         "subject": {"describedByEntityStatement": "missing"},
         "interestedParty": {"describedByPersonStatement": "missing"},
         "interests": []},
    ]
    assert parse_bods(json.dumps(broken)) == []


# -- ingestion: three distinct edges, anchor resolution, honesty ---------------

def test_ingest_writes_three_distinct_edge_types_and_never_conflates() -> None:
    store = _acme_store()
    consolidation = OwnershipRecord(
        holder=OwnershipParty(name="ACME GLOBAL SA", kind="Company",
                              anchor=PartyAnchor(scheme="lei", value="ZZ00PARENT00LEI00000")),
        subject=OwnershipParty(name="ACME LTD", kind="Company",
                               anchor=PartyAnchor(scheme="lei", value="5493001KJTIIGC8Y1R12")),
        basis=OwnershipBasis.ACCOUNTING_CONSOLIDATION, source="gleif-l2", valid_from="2020-01-01")
    records = parse_bods(json.dumps(_BODS)) + [consolidation]

    summary = ingest_ownership(store, StaticOwnershipProvider(records, name="mixed"),
                               observed_at="2026-07-02")
    assert summary.owns == 1 and summary.beneficial_owner_of == 1 and summary.consolidates == 1
    assert len(store.edges_by_relation(OWNS)) == 1
    assert len(store.edges_by_relation(BENEFICIAL_OWNER_OF)) == 1
    assert len(store.edges_by_relation(CONSOLIDATES)) == 1
    # Declared shareholding (75%) and beneficial ownership are separate edges: the
    # 75% owner is NOT recorded as a beneficial owner (no derivation).
    bo = store.edges_by_relation(BENEFICIAL_OWNER_OF)[0]
    assert bo.properties["basis"] == "beneficial_owner" and "percentage" not in bo.properties
    owns = store.edges_by_relation(OWNS)[0]
    assert owns.properties["basis"] == "declared_shareholding" and owns.properties["percentage"] == 75.0


def test_ingest_resolves_subject_by_lei_without_duplicating() -> None:
    store = _acme_store()
    ingest_ownership(store, StaticOwnershipProvider(parse_bods(json.dumps(_BODS))),
                     observed_at="2026-07-02")
    # ACME resolved to the existing curated node by LEI (not a new surrogate).
    assert store.get_node("Company", "company-lei-5493001kjtiigc8y1r12") is None
    edges = store.edges_by_relation(BENEFICIAL_OWNER_OF)
    assert edges[0].target_key == "acme" and edges[0].properties["subject_resolved"] is True
    # The curated node keeps its authority (untouched).
    assert store.get_node("Company", "acme").properties["source"] == "tracked"


def test_unresolved_holder_gets_labelled_surrogate_counted() -> None:
    store = _acme_store()
    summary = ingest_ownership(store, StaticOwnershipProvider(parse_bods(json.dumps(_BODS))),
                               observed_at="2026-07-02")
    # Jane (person) and ACME HOLDINGS (entity) have no pre-existing node → surrogates.
    assert summary.holders_unresolved == 2 and summary.subjects_unresolved == 0
    jane = store.get_node("Person", "person-jane-q-owner")
    assert jane is not None and jane.properties["ownership_status"] == "unresolved"


def test_edges_carry_provenance_validity_and_access_tier() -> None:
    store = _acme_store()
    ingest_ownership(store, StaticOwnershipProvider(parse_bods(json.dumps(_BODS))),
                     observed_at="2026-07-02")
    bo = store.edges_by_relation(BENEFICIAL_OWNER_OF)[0]
    assert bo.properties[substrate.SOURCE] == "openownership-bods"
    assert bo.properties[substrate.OBSERVED_AT] == "2026-07-02"
    assert bo.properties[substrate.VALID_FROM] == "2016-04-06"
    # Beneficial ownership is access-restricted (legitimate-interest); declared
    # shareholding is public.
    assert bo.properties[substrate.ACCESS_TIER] == substrate.AccessTier.LEGITIMATE_INTEREST.value
    owns = store.edges_by_relation(OWNS)[0]
    assert owns.properties[substrate.ACCESS_TIER] == substrate.AccessTier.PUBLIC.value


def test_reingest_is_idempotent() -> None:
    store = _acme_store()
    provider = StaticOwnershipProvider(parse_bods(json.dumps(_BODS)))
    first = ingest_ownership(store, provider, observed_at="2026-07-02")
    edges1 = store.edge_count()
    nodes1 = {(n.kind, n.key) for n in store.all_nodes()}
    second = ingest_ownership(store, provider, observed_at="2026-07-03")  # re-run
    assert store.edge_count() == edges1
    assert {(n.kind, n.key) for n in store.all_nodes()} == nodes1
    # The summary metric is stable too: matching our own prior surrogate is not
    # counted as newly resolved (an honesty invariant, not just node/edge stability).
    assert second.holders_unresolved == first.holders_unresolved == 2
    assert second.subjects_unresolved == first.subjects_unresolved == 0


# -- queries: access-tier enforcement + bitemporal -----------------------------

def test_ownership_overview_hides_beneficial_from_public_but_counts_it() -> None:
    store = _acme_store()
    ingest_ownership(store, StaticOwnershipProvider(parse_bods(json.dumps(_BODS))),
                     observed_at="2026-07-02")
    public = ownership_overview(store)  # default PUBLIC clearance
    assert public.connected is True and public.owns == 1
    assert public.beneficial_owner_of == 0  # withheld from the public tier
    assert public.restricted == 1  # ...but its existence is transparent
    assert public.market == "*"

    privileged = ownership_overview(store, clearance=substrate.AccessTier.LEGITIMATE_INTEREST)
    assert privileged.beneficial_owner_of == 1 and privileged.restricted == 0


def test_ownership_overview_honest_empty_before_any_run() -> None:
    assert ownership_overview(InMemoryKnowledgeGraphStore()).connected is False


def test_company_owners_access_tier_and_as_of() -> None:
    store = _acme_store()
    ingest_ownership(store, StaticOwnershipProvider(parse_bods(json.dumps(_BODS))),
                     observed_at="2026-07-02")
    # Public caller sees only the declared shareholding; the beneficial owner is
    # withheld but counted.
    public = company_owners(store, "acme")
    assert [o.relation for o in public.owners] == ["owns"] and public.restricted == 1

    privileged = company_owners(store, "acme", clearance=substrate.AccessTier.LEGITIMATE_INTEREST)
    relations = {o.relation for o in privileged.owners}
    assert relations == {"owns", "beneficial_owner_of"} and privileged.restricted == 0

    # Bitemporal: before the beneficial interest began (2016-04-06), it is not in force.
    early = company_owners(store, "acme", clearance=substrate.AccessTier.LEGITIMATE_INTEREST,
                           as_of="2015-06-01")
    assert all(o.relation != "beneficial_owner_of" for o in early.owners)


# -- runtime + CLI wiring ------------------------------------------------------

def test_run_ownership_offline_file_is_idempotent(tmp_path) -> None:  # type: ignore[no-untyped-def]
    from coruscant.apps.workspace_runtime import run_ownership
    from coruscant.common.config import Settings
    from coruscant.knowledge_graph.persistence import load_graph, save_graph

    data_dir = tmp_path / "data"
    settings = Settings(data_dir=data_dir, database_url=f"sqlite:///{data_dir / 'c.db'}")
    save_graph(_acme_store(), settings.graph_snapshot_path)  # a curated node to resolve against
    feed = tmp_path / "bods.json"
    feed.write_text(json.dumps(_BODS))

    summary = run_ownership(settings, file_path=feed)
    assert summary.owns == 1 and summary.beneficial_owner_of == 1
    graph = load_graph(settings.graph_snapshot_path)
    assert len(graph.edges_by_relation(BENEFICIAL_OWNER_OF)) == 1

    run_ownership(settings, file_path=feed)  # re-run
    assert len(load_graph(settings.graph_snapshot_path).edges_by_relation(BENEFICIAL_OWNER_OF)) == 1


def test_run_ownership_requires_a_dataset() -> None:
    import pytest

    from coruscant.apps.workspace_runtime import run_ownership
    from coruscant.common.config import Settings

    settings = Settings(data_dir="/tmp/x", database_url="sqlite:///:memory:")
    with pytest.raises(FileNotFoundError, match="No ownership dataset"):
        run_ownership(settings, file_path=None)


def test_cli_ownership_parser_wires_command() -> None:
    from coruscant.apps import cli

    ns = cli.build_parser().parse_args(["ownership", "--file", "bods.json", "--provider", "bods"])
    assert ns.func is cli.cmd_ownership and ns.file == "bods.json" and ns.provider == "bods"


def test_bods_provider_from_file(tmp_path) -> None:  # type: ignore[no-untyped-def]
    feed = tmp_path / "bods.json"
    feed.write_text(json.dumps(_BODS))
    provider = BodsOwnershipProvider.from_file(feed)
    assert provider.connected() and len(provider.list_ownership()) == 2


# -- generic (market-plural) seam: new markets drop in additively --------------

def test_ownership_seam_is_market_tagged_and_market_agnostic_pipeline() -> None:
    # Tranche 6: the seam is market-plural (like CoverageProvider). A provider for a
    # *new* market ingests through the unchanged, anchor-driven pipeline — the core
    # graph has no per-market ownership logic to touch.
    store = InMemoryKnowledgeGraphStore()
    store.upsert_node(GraphNode(kind="Company", key="reliance", properties={
        "name": "RELIANCE INDUSTRIES LTD", "isin": "INE002A01018", "source": "india-nse-bse"}))
    india_record = OwnershipRecord(
        holder=OwnershipParty(name="Ambani Family Trust", kind="Entity"),
        subject=OwnershipParty(name="RELIANCE INDUSTRIES LTD", kind="Company",
                               anchor=PartyAnchor(scheme="isin", value="INE002A01018")),
        basis=OwnershipBasis.DECLARED_SHAREHOLDING, percentage=50.3, source="in-sast")
    provider = StaticOwnershipProvider([india_record], name="in-sast", market="IN")
    assert provider.market == "IN"  # market-tagged
    summary = ingest_ownership(store, provider, observed_at="2026-07-02")
    # Same distinct-edge machinery, resolving by anchor — no market branch anywhere.
    assert summary.owns == 1 and summary.subjects_unresolved == 0
    edge = store.edges_by_relation(OWNS)[0]
    assert edge.target_key == "reliance" and edge.properties["percentage"] == 50.3


# -- API -----------------------------------------------------------------------

def test_ownership_api_endpoints_enforce_public_tier() -> None:
    from fastapi.testclient import TestClient

    from coruscant.apps.api import create_app

    store = _acme_store()
    ingest_ownership(store, StaticOwnershipProvider(parse_bods(json.dumps(_BODS))),
                     observed_at="2026-07-02")
    client = TestClient(create_app(graph_store=store, require_auth=False))

    overview = client.get("/graph/ownership").json()
    assert overview["connected"] is True and overview["owns"] == 1
    assert overview["beneficial_owner_of"] == 0 and overview["restricted"] == 1

    owners = client.get("/graph/company/acme/owners").json()
    assert [o["relation"] for o in owners["owners"]] == ["owns"]
    assert owners["owners"][0]["percentage"] == 75.0 and owners["restricted"] == 1
