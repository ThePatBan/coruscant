"""UK Companies House PSC — the first live national beneficial-ownership source.

Covers the honesty-critical mapping (individual → beneficial owner, corporate →
declared shareholding, super-secure → restricted-and-withheld, statement → not an
edge), disclosed-band parsing (never a fabricated exact %), the PUBLIC access tier
that distinguishes the UK register from the EU/BODS default, both wire shapes (API
response + bulk NDJSON), anchor resolution against LSE-covered nodes, and the
runtime/CLI wiring. Hermetic — PSC JSON is injected; no network."""

from __future__ import annotations

import json

import pytest

from coruscant.common.types import GraphNode
from coruscant.knowledge_graph import substrate
from coruscant.knowledge_graph.memory import InMemoryKnowledgeGraphStore
from coruscant.exposure.queries import company_owners, ownership_overview
from coruscant.ownership import (
    BENEFICIAL_OWNER_OF,
    CompaniesHousePscProvider,
    OwnershipBasis,
    ingest_ownership,
    parse_psc,
)
from coruscant.ownership.companies_house import COMPANIES_HOUSE_PSC_SOURCE

# A Companies House PSC API response for one company (09999999): an individual PSC
# (25-50% voting band), a corporate PSC that is itself a UK company (a declared
# shareholding, anchorable by company number), a super-secure PSC (details withheld),
# and a PSC *statement* (not an ownership edge).
_PSC_API = {
    "links": {"self": "/company/09999999/persons-with-significant-control"},
    "items": [
        {"kind": "individual-person-with-significant-control",
         "name": "Jane Q Owner",
         "natures_of_control": ["voting-rights-25-to-50-percent",
                                "ownership-of-shares-25-to-50-percent"],
         "notified_on": "2016-04-06"},
        {"kind": "corporate-entity-person-with-significant-control",
         "name": "ACME HOLDINGS LTD",
         "natures_of_control": ["ownership-of-shares-75-to-100-percent"],
         "notified_on": "2015-01-01",
         "identification": {"registration_number": "08888888",
                            "place_registered": "Companies House",
                            "country_registered": "United Kingdom"}},
        {"kind": "super-secure-person-with-significant-control",
         "natures_of_control": ["significant-influence-or-control"]},
        {"kind": "persons-with-significant-control-statement",
         "statement": "psc-exists-but-not-identified"},
    ],
}

# The bulk PSC snapshot shape: one {company_number, data} row per line (NDJSON).
_PSC_BULK = "\n".join(json.dumps(row) for row in [
    {"company_number": "09999999", "company_name": "ACME LTD",
     "data": {"kind": "individual-person-with-significant-control",
              "name_elements": {"forename": "Jane", "surname": "Owner"},
              "natures_of_control": ["ownership-of-shares-50-to-75-percent-as-trust"],
              "notified_on": "2016-04-06"}},
])


def _acme_gb_store() -> InMemoryKnowledgeGraphStore:
    store = InMemoryKnowledgeGraphStore()
    # An LSE-covered GB issuer carrying its Companies House number as a coverage anchor.
    store.upsert_node(GraphNode(kind="Company", key="acme", properties={
        "name": "ACME LTD", "market": "GB", "in_universe": True,
        "anchors": [{"scheme": "isin", "value": "GB00ACME0001"},
                    {"scheme": "company_number", "value": "09999999"}],
        "source": "uk-lse"}))
    return store


# -- parsing -------------------------------------------------------------------

def test_parse_psc_maps_kind_to_basis_and_tier() -> None:
    stats = parse_psc(json.dumps(_PSC_API))
    # individual → beneficial owner (Person); corporate → declared shareholding.
    person = next(r for r in stats.records if r.holder.name == "Jane Q Owner")
    corporate = next(r for r in stats.records if r.holder.kind == "Company")
    assert person.basis == OwnershipBasis.BENEFICIAL_OWNER
    assert corporate.basis == OwnershipBasis.DECLARED_SHAREHOLDING
    # A disclosed band, never a fabricated exact percentage.
    assert person.percentage is None and person.percentage_band == "25%-50%"
    assert person.interest in ("voting-rights", "shareholding")
    assert person.valid_from == "2016-04-06"
    # UK PSC is a PUBLIC register (unlike the EU/BODS legitimate-interest default).
    assert person.access_tier == substrate.AccessTier.PUBLIC.value
    # The statement is counted, never emitted as an edge.
    assert stats.statements == 1
    assert all(r.source == COMPANIES_HOUSE_PSC_SOURCE for r in stats.records)


def test_parse_psc_super_secure_is_withheld_and_restricted() -> None:
    stats = parse_psc(json.dumps(_PSC_API))
    secure = [r for r in stats.records if "withheld" in r.holder.name.lower()]
    assert len(secure) == 1
    rec = secure[0]
    assert rec.basis == OwnershipBasis.BENEFICIAL_OWNER  # still a person's control
    assert rec.access_tier == substrate.AccessTier.RESTRICTED_AUTHORITY.value
    assert rec.percentage is None  # never a fabricated figure


def test_parse_psc_corporate_anchors_by_company_number() -> None:
    stats = parse_psc(json.dumps(_PSC_API))
    corporate = next(r for r in stats.records if r.holder.kind == "Company")
    assert corporate.holder.anchor is not None
    assert corporate.holder.anchor.scheme == "company_number"
    assert corporate.holder.anchor.value == "08888888"
    # The subject is anchored by the response's own company number.
    assert corporate.subject.anchor.value == "09999999"


def test_parse_psc_accepts_bulk_ndjson_and_folds_holding_vehicle() -> None:
    stats = parse_psc(_PSC_BULK)
    assert len(stats.records) == 1
    rec = stats.records[0]
    assert rec.holder.name == "Jane Owner"  # assembled from name_elements
    # `-as-trust` suffix folded to the base band.
    assert rec.percentage_band == "50%-75%" and rec.percentage is None
    assert rec.subject.name == "ACME LTD"


def test_parse_psc_empty_is_honest() -> None:
    assert parse_psc("").records == []
    assert parse_psc("").statements == 0


# -- provider ------------------------------------------------------------------

def test_psc_provider_from_payloads_is_connected() -> None:
    provider = CompaniesHousePscProvider(payloads=[_PSC_API])
    assert provider.connected()
    records = provider.list_ownership()
    # 3 edges (individual + corporate + super-secure); the statement is not an edge.
    assert len(records) == 3
    assert provider.last_stats.statements == 1


def test_psc_provider_reports_market_for_generic_seam() -> None:
    # Tranche 6: providers are market-tagged so the seam stays generic.
    assert CompaniesHousePscProvider(payloads=[_PSC_API]).market == "GB"


def test_psc_provider_disconnected_without_key_or_data() -> None:
    assert CompaniesHousePscProvider().connected() is False


# -- ingestion: resolves against covered GB node, public tier ------------------

def test_ingest_psc_resolves_subject_by_company_number_public_beneficial() -> None:
    store = _acme_gb_store()
    provider = CompaniesHousePscProvider(payloads=[_PSC_API])
    summary = ingest_ownership(store, provider, observed_at="2026-07-02")
    assert summary.beneficial_owner_of == 2  # individual + super-secure
    assert summary.owns == 1  # corporate PSC = declared shareholding

    # The beneficial-owner edge resolved onto the covered LSE node by company number.
    bo = [e for e in store.edges_by_relation(BENEFICIAL_OWNER_OF) if e.target_key == "acme"]
    assert bo, "PSC subject should resolve to the covered GB company"
    # A public caller SEES the UK PSC individual beneficial owner (public register),
    # but NOT the super-secure one (restricted-authority).
    public = company_owners(store, "acme")
    relations = [o.relation for o in public.owners]
    assert relations.count("beneficial_owner_of") == 1  # only the non-secure individual
    assert relations.count("owns") == 1
    assert public.restricted == 1  # the super-secure PSC withheld but counted


def test_ownership_overview_counts_public_uk_beneficial_owner() -> None:
    store = _acme_gb_store()
    ingest_ownership(store, CompaniesHousePscProvider(payloads=[_PSC_API]),
                     observed_at="2026-07-02")
    # Even at the default PUBLIC clearance, the UK PSC individual is visible.
    public = ownership_overview(store)
    assert public.connected is True
    assert public.beneficial_owner_of == 1  # the public individual
    assert public.owns == 1
    assert public.restricted == 1  # super-secure withheld
    assert public.market == "GB"


def test_ingest_psc_is_idempotent() -> None:
    store = _acme_gb_store()
    provider = CompaniesHousePscProvider(payloads=[_PSC_API])
    ingest_ownership(store, provider, observed_at="2026-07-02")
    edges = store.edge_count()
    ingest_ownership(store, provider, observed_at="2026-07-03")
    assert store.edge_count() == edges


# -- runtime + CLI wiring ------------------------------------------------------

def test_run_ownership_psc_from_bulk_file(tmp_path) -> None:  # type: ignore[no-untyped-def]
    from coruscant.apps.workspace_runtime import run_ownership
    from coruscant.common.config import Settings
    from coruscant.knowledge_graph.persistence import load_graph, save_graph

    data_dir = tmp_path / "data"
    settings = Settings(data_dir=data_dir, database_url=f"sqlite:///{data_dir / 'c.db'}")
    save_graph(_acme_gb_store(), settings.graph_snapshot_path)
    feed = tmp_path / "psc.ndjson"
    feed.write_text(_PSC_BULK)

    summary = run_ownership(settings, file_path=feed, provider_name="psc")
    assert summary.beneficial_owner_of == 1 and summary.provider == COMPANIES_HOUSE_PSC_SOURCE
    graph = load_graph(settings.graph_snapshot_path)
    assert len(graph.edges_by_relation(BENEFICIAL_OWNER_OF)) == 1


def test_run_ownership_psc_requires_a_source(tmp_path) -> None:  # type: ignore[no-untyped-def]
    from coruscant.apps.workspace_runtime import run_ownership
    from coruscant.common.config import Settings
    from coruscant.knowledge_graph.persistence import save_graph

    data_dir = tmp_path / "data"
    settings = Settings(data_dir=data_dir, database_url=f"sqlite:///{data_dir / 'c.db'}")
    save_graph(_acme_gb_store(), settings.graph_snapshot_path)
    with pytest.raises(FileNotFoundError, match="No UK PSC source"):
        run_ownership(settings, file_path=None, provider_name="psc")


def test_cli_ownership_accepts_psc_provider() -> None:
    from coruscant.apps import cli

    ns = cli.build_parser().parse_args(["ownership", "--provider", "psc", "--file", "psc.ndjson"])
    assert ns.provider == "psc" and ns.file == "psc.ndjson"


def test_run_ownership_psc_live_scopes_to_covered_gb_numbers(monkeypatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    # With an API key set and GB coverage present, the live provider is built and
    # scoped to the covered company numbers (fetch itself is monkeypatched off).
    from coruscant.apps import workspace_runtime
    from coruscant.common.config import Settings
    from coruscant.knowledge_graph.persistence import save_graph
    from coruscant.ownership.companies_house import CompaniesHousePscProvider as Prov

    data_dir = tmp_path / "data"
    settings = Settings(data_dir=data_dir, database_url=f"sqlite:///{data_dir / 'c.db'}",
                        companies_house_api_key="test-key")
    save_graph(_acme_gb_store(), settings.graph_snapshot_path)

    def fake_fetch(self, number):  # noqa: ANN001
        assert number == "09999999"  # scoped to the covered GB number
        return _PSC_API

    monkeypatch.setattr(Prov, "_fetch_company", fake_fetch)
    summary = workspace_runtime.run_ownership(settings, file_path=None, provider_name="psc")
    assert summary.beneficial_owner_of == 2 and summary.owns == 1
