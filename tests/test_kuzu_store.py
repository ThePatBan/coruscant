"""Golden cross-backend parity: the Kùzu store must return byte-identical results
to the in-memory prototype for every exposure-engine query, so swapping the
serving backend never changes what the API serves. Plus Kùzu-specific unit tests
(upsert semantics, snapshot round-trip, staleness-synced open)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from coruscant.common.types import GraphEdge, GraphNode
from coruscant.knowledge_graph import queries as Q
from coruscant.knowledge_graph.kuzu_store import KuzuKnowledgeGraphStore
from coruscant.knowledge_graph.memory import InMemoryKnowledgeGraphStore
from coruscant.knowledge_graph.store import KnowledgeGraphStore


def _node(kind: str, key: str, **props: object) -> GraphNode:
    return GraphNode(kind=kind, key=key, properties={"name": props.pop("name", key), **props})


def _edge(sk: str, s: str, rel: str, tk: str, t: str, **props: object) -> GraphEdge:
    return GraphEdge(source_kind=sk, source_key=s, relation=rel, target_kind=tk, target_key=t, properties=dict(props))


def _rich_graph() -> InMemoryKnowledgeGraphStore:
    """A seed exercising every relation the exposure engine reads, so parity is
    tested across the whole query surface (not just a happy path)."""
    s = InMemoryKnowledgeGraphStore()
    # Companies
    for slug, name in [("apple", "Apple"), ("microsoft", "Microsoft"), ("chevron", "Chevron"),
                       ("jpmorgan", "JPMorgan"), ("shell", "Shell")]:
        s.upsert_node(_node("Company", slug, name=name))
    # GICS sectors (in_sector edges carry the curated hierarchy on the edge)
    s.upsert_node(_node("Industry", "semiconductors", name="Semiconductors"))
    s.upsert_node(_node("Industry", "oil-gas", name="Integrated Oil & Gas"))
    s.upsert_node(_node("Industry", "banks", name="Diversified Banks"))
    s.upsert_edge(_edge("Company", "apple", "in_sector", "Industry", "semiconductors",
                        sector="Information Technology", industry_group="Semiconductors & Equipment",
                        industry="Semiconductors", sub_industry="Semiconductors", code="45301020"))
    s.upsert_edge(_edge("Company", "microsoft", "in_sector", "Industry", "semiconductors",
                        sector="Information Technology", sub_industry="Systems Software", code="45103020"))
    s.upsert_edge(_edge("Company", "chevron", "in_sector", "Industry", "oil-gas",
                        sector="Energy", sub_industry="Integrated Oil & Gas", code="10102010"))
    s.upsert_edge(_edge("Company", "shell", "in_sector", "Industry", "oil-gas",
                        sector="Energy", sub_industry="Integrated Oil & Gas", code="10102010"))
    s.upsert_edge(_edge("Company", "jpmorgan", "in_sector", "Industry", "banks",
                        sector="Financials", sub_industry="Diversified Banks", code="40101010"))
    # MSCI market tiers
    s.upsert_node(_node("MarketTier", "dm", name="Developed market", code="DM"))
    s.upsert_node(_node("MarketTier", "em", name="Emerging market", code="EM"))
    for slug, tier in [("apple", "dm"), ("microsoft", "dm"), ("chevron", "dm"), ("jpmorgan", "dm"), ("shell", "em")]:
        s.upsert_edge(_edge("Company", slug, "in_market_tier", "MarketTier", tier))
    # Subsidiaries in jurisdictions (Exhibit 21)
    for i, (co, sub, juris) in enumerate([
        ("apple", "apple-ireland", "Ireland"), ("apple", "braeburn", "Delaware"),
        ("microsoft", "ms-ireland", "Ireland"), ("chevron", "chev-uk", "England and Wales"),
        ("shell", "shell-nl", "Netherlands")]):
        s.upsert_node(_node("Subsidiary", sub, name=sub.replace("-", " ").title()))
        s.upsert_edge(_edge("Company", co, "has_subsidiary", "Subsidiary", sub,
                            jurisdiction=juris, source_uri=f"https://sec.gov/{co}/ex21"))
    # Co-mention references (network proximity). A directed chain
    # microsoft -> apple -> jpmorgan -> chevron -> shell exercises multi-hop reach.
    s.upsert_edge(_edge("Company", "microsoft", "references", "Company", "apple",
                        entity_name="Apple Inc.", source_uri="https://sec.gov/msft/10k"))
    s.upsert_edge(_edge("Company", "apple", "references", "Company", "jpmorgan",
                        entity_name="JPMorgan Chase & Co.", source_uri="https://sec.gov/aapl/10k"))
    s.upsert_edge(_edge("Company", "jpmorgan", "references", "Company", "chevron",
                        entity_name="Chevron Corp", source_uri="https://sec.gov/jpm/10k"))
    s.upsert_edge(_edge("Company", "shell", "references", "Company", "chevron",
                        entity_name="Chevron Corp", source_uri="https://sec.gov/shell/20f"))
    # Countries + supplier chain (exposure_to_country / company_country_exposures)
    s.upsert_node(_node("Country", "taiwan", name="Taiwan"))
    s.upsert_node(_node("Country", "united-states", name="United States"))
    s.upsert_node(_node("Company", "tsmc", name="TSMC"))
    s.upsert_edge(_edge("Company", "tsmc", "operates_in", "Country", "taiwan", source="reference-entities"))
    s.upsert_edge(_edge("Company", "apple", "relies_on_supplier", "Company", "tsmc", source="reference-entities"))
    # People (employs / previously_at / board_member / insider_holding)
    for pid, name in [("tim-cook", "Tim Cook"), ("jane-fraser", "Jane Fraser"), ("bridge-person", "Bridge Person")]:
        s.upsert_node(_node("Person", pid, name=name))
    s.upsert_edge(_edge("Company", "apple", "employs", "Person", "tim-cook", role="CEO"))
    s.upsert_edge(_edge("Company", "jpmorgan", "employs", "Person", "jane-fraser", role="CEO"))
    s.upsert_edge(_edge("Company", "apple", "employs", "Person", "bridge-person", role="Director"))
    s.upsert_edge(_edge("Company", "microsoft", "employs", "Person", "bridge-person", role="Director"))
    s.upsert_edge(_edge("Person", "tim-cook", "previously_at", "Company", "chevron", role="Analyst"))
    s.upsert_edge(_edge("Person", "tim-cook", "insider_holding", "Company", "apple", shares=837_374, role="CEO"))
    # Commodities + debt instruments
    s.upsert_node(_node("Commodity", "crude-oil", name="Crude Oil", category="energy", symbol="CL=F"))
    s.upsert_node(_node("Commodity", "gold", name="Gold", category="metals", symbol="GC=F"))
    s.upsert_edge(_edge("Commodity", "crude-oil", "affects_sector", "Industry", "oil-gas", sector="Energy"))
    s.upsert_node(_node("DebtInstrument", "ust-10y", name="US 10Y Treasury", debt_type="sovereign",
                        issuer_country="United States", symbol="^TNX"))
    s.upsert_edge(_edge("DebtInstrument", "ust-10y", "issued_by", "Country", "united-states"))
    # A filing that mentions companies (entity_profile.mentioned_in)
    s.upsert_node(_node("Filing", "aapl-10k", name="Apple 10-K"))
    s.upsert_edge(_edge("Filing", "aapl-10k", "mentions", "Company", "apple"))
    s.upsert_edge(_edge("Company", "apple", "filed", "Filing", "aapl-10k"))
    # PEP/sanctions screening on synthetic subjects (never a real person). Edges
    # carry the substrate: access_tier (query-time policy) + valid-time (bitemporal).
    for pid, name in [("screen-subject", "Screen Subject"), ("review-subject", "Review Subject")]:
        s.upsert_node(_node("Person", pid, name=name))
    s.upsert_node(_node("WatchlistEntity", "os-sdn-1", name="Listed Entity One", source="opensanctions",
                        external_id="sdn-1", source_url="https://www.opensanctions.org/entities/sdn-1/",
                        topics=["sanction"], datasets=["us_ofac_sdn"]))
    s.upsert_node(_node("WatchlistEntity", "os-pep-1", name="Exposed Person One", source="opensanctions",
                        external_id="pep-1", source_url="https://www.opensanctions.org/entities/pep-1/",
                        topics=["role.pep"], datasets=["peps"]))
    s.upsert_edge(_edge("Person", "screen-subject", "sanctioned", "WatchlistEntity", "os-sdn-1",
                        source="opensanctions", access_tier="public", observed_at="2026-07-01",
                        valid_from="2020-01-01", score=1.0, matched_name="Screen Subject",
                        review_status="confirmed", datasets=["us_ofac_sdn"], external_id="sdn-1"))
    s.upsert_edge(_edge("Person", "review-subject", "screening_candidate", "WatchlistEntity", "os-pep-1",
                        source="opensanctions", access_tier="public", observed_at="2026-07-01",
                        valid_from="2019-01-01", score=0.9, matched_name="Review Subject",
                        review_status="needs-review", datasets=["peps"], external_id="pep-1"))
    s.upsert_node(_node("ScreeningRun", "latest", name="Latest screening run", source="screening",
                        provider="deterministic-name-v1", dataset="fixture", screened=3, candidates=2,
                        confirmed=1, needs_review=1, pep=0, sanctioned=1, observed_at="2026-07-01"))
    # Resolver canonical projection: two spellings of one company merged, with the
    # `resolves_to` relation the multi-hop primitive traverses (like `references`).
    s.upsert_node(_node("Company", "acme-holdings", name="ACME Holdings LLC"))
    s.upsert_node(_node("Company", "acme-hldgs", name="ACME HLDGS"))
    s.upsert_node(_node("Canonical", "cid-acme", name="cid-acme", source="resolver", members=2))
    for slug in ("acme-holdings", "acme-hldgs"):
        s.upsert_edge(_edge("Company", slug, "resolves_to", "Canonical", "cid-acme",
                            source="resolver", access_tier="public", observed_at="2026-07-01"))
    return s


def _both_stores() -> tuple[KnowledgeGraphStore, KnowledgeGraphStore]:
    data = _rich_graph().to_dict()
    return InMemoryKnowledgeGraphStore.from_dict(data), KuzuKnowledgeGraphStore.from_dict(data)


def _j(obj: object) -> str:
    if hasattr(obj, "model_dump_json"):
        return obj.model_dump_json()  # type: ignore[attr-defined]
    return json.dumps([o.model_dump() for o in obj], sort_keys=False)  # type: ignore[union-attr]


# One case per query function; parametrized args cover multiple concrete inputs.
_SCALAR_QUERIES = [
    "list_sectors", "gics_breakdown", "list_jurisdictions", "list_market_tiers",
    "co_executives", "list_commodities", "list_debt_instruments",
]


@pytest.mark.parametrize("fn_name", _SCALAR_QUERIES)
def test_parity_scalar_queries(fn_name: str) -> None:
    mem, kz = _both_stores()
    fn = getattr(Q, fn_name)
    assert _j(fn(mem)) == _j(fn(kz)), fn_name


@pytest.mark.parametrize("kind", [None, "Company", "Person", "Subsidiary", "Commodity"])
def test_parity_list_entities(kind: str | None) -> None:
    mem, kz = _both_stores()
    assert _j(Q.list_entities(mem, kind)) == _j(Q.list_entities(kz, kind))


@pytest.mark.parametrize("juris", ["Ireland", "Delaware", "England and Wales", "Nowhere"])
def test_parity_jurisdiction_exposure(juris: str) -> None:
    mem, kz = _both_stores()
    assert _j(Q.jurisdiction_exposure(mem, juris)) == _j(Q.jurisdiction_exposure(kz, juris))


@pytest.mark.parametrize("sector", ["Information Technology", "Energy", "Semiconductors", "Financials", "Agriculture"])
def test_parity_sector_exposure(sector: str) -> None:
    mem, kz = _both_stores()
    assert _j(Q.sector_exposure(mem, sector)) == _j(Q.sector_exposure(kz, sector))


@pytest.mark.parametrize("tier", ["DM", "EM", "FM"])
def test_parity_market_tier_exposure(tier: str) -> None:
    mem, kz = _both_stores()
    assert _j(Q.market_tier_exposure(mem, tier)) == _j(Q.market_tier_exposure(kz, tier))


@pytest.mark.parametrize("commodity", ["crude-oil", "gold", "Crude Oil", "unknown"])
def test_parity_commodity_exposure(commodity: str) -> None:
    mem, kz = _both_stores()
    assert _j(Q.commodity_exposure(mem, commodity)) == _j(Q.commodity_exposure(kz, commodity))


def test_parity_country_and_debt() -> None:
    mem, kz = _both_stores()
    assert _j(Q.exposure_to_country(mem, "Taiwan")) == _j(Q.exposure_to_country(kz, "Taiwan"))
    assert Q.company_country_exposures(mem, "apple") == Q.company_country_exposures(kz, "apple")
    assert _j(Q.debt_for_country(mem, "United States")) == _j(Q.debt_for_country(kz, "United States"))


@pytest.mark.parametrize("company,max_hops", [
    ("microsoft", 1), ("microsoft", 2), ("microsoft", 3), ("microsoft", 4),
    ("apple", 2), ("shell", 2), ("chevron", 2), ("nonexistent", 2)])
def test_parity_company_network(company: str, max_hops: int) -> None:
    mem, kz = _both_stores()
    assert (Q.company_network(mem, company, max_hops).model_dump_json()
            == Q.company_network(kz, company, max_hops).model_dump_json())


@pytest.mark.parametrize("direction", ["out", "in", "any"])
@pytest.mark.parametrize("max_hops", [1, 2, 3, 4])
def test_parity_reachable(direction: str, max_hops: int) -> None:
    mem, kz = _both_stores()
    for company in ("microsoft", "chevron", "apple"):
        assert (mem.reachable("Company", company, "references", max_hops, direction=direction)
                == kz.reachable("Company", company, "references", max_hops, direction=direction))


def test_reachable_distances_and_relation_filter() -> None:
    # The multi-hop primitive: shortest distances along the co-mention chain, and
    # `employs` edges must NOT bridge (relation filter).
    mem, kz = _both_stores()
    for store in (mem, kz):
        r = store.reachable("Company", "microsoft", "references", 4, direction="any")
        assert r[("Company", "apple")] == 1
        assert r[("Company", "jpmorgan")] == 2
        assert r[("Company", "chevron")] == 3
        assert r[("Company", "shell")] == 4
        assert not any(kind == "Person" for kind, _ in r)  # relation filter holds
        assert set(store.reachable("Company", "microsoft", "references", 1, direction="any")) == {
            ("Company", "apple")
        }  # depth bound


def test_reachable_direction() -> None:
    mem, kz = _both_stores()
    for store in (mem, kz):
        # microsoft -> apple is directed: reachable OUT from microsoft, not IN.
        assert ("Company", "apple") in store.reachable("Company", "microsoft", "references", 1, direction="out")
        assert store.reachable("Company", "microsoft", "references", 1, direction="in") == {}
        assert ("Company", "microsoft") in store.reachable("Company", "apple", "references", 1, direction="in")


def test_company_network_evidence_chain() -> None:
    net = Q.company_network(_rich_graph(), "microsoft", 3)
    reached = {r.company.key: r for r in net.reached}
    assert reached["chevron"].hops == 3
    chain = reached["chevron"].path
    assert [(s.from_company.key, s.to_company.key) for s in chain] == [
        ("microsoft", "apple"), ("apple", "jpmorgan"), ("jpmorgan", "chevron")]
    assert all(step.source for step in chain)  # every hop cites a filing (provenance)
    # reached is ordered by (hops, name); shell is beyond 3 hops, absent.
    assert [r.company.key for r in net.reached] == ["apple", "jpmorgan", "chevron"]


@pytest.mark.parametrize("as_of", [None, "2019-06-01", "2021-01-01", "2026-07-01"])
def test_parity_screening_overview(as_of: str | None) -> None:
    # The screening panel (incl. its bitemporal `as_of` filter) is byte-identical
    # across backends, so serving from Kùzu never changes what the panel shows.
    mem, kz = _both_stores()
    assert _j(Q.screening_overview(mem, as_of=as_of)) == _j(Q.screening_overview(kz, as_of=as_of))


def test_parity_reachable_resolves_to() -> None:
    # The canonical-cluster traversal reuses the multi-hop primitive over a new
    # relation: acme-holdings -resolves_to-> Canonical <-resolves_to- acme-hldgs.
    mem, kz = _both_stores()
    for store in (mem, kz):
        reached = store.reachable("Company", "acme-holdings", "resolves_to", 2, direction="any")
        assert reached[("Canonical", "cid-acme")] == 1
        assert reached[("Company", "acme-hldgs")] == 2
    assert (mem.reachable("Company", "acme-holdings", "resolves_to", 2, direction="any")
            == kz.reachable("Company", "acme-holdings", "resolves_to", 2, direction="any"))


def test_parity_entity_profile_every_node() -> None:
    mem, kz = _both_stores()
    for node in mem.all_nodes():
        a = Q.entity_profile(mem, node.kind, node.key)
        b = Q.entity_profile(kz, node.kind, node.key)
        assert a is not None and b is not None
        assert a.model_dump_json() == b.model_dump_json(), f"{node.kind}:{node.key}"


# -- Kùzu-specific unit tests -------------------------------------------------

def test_snapshot_roundtrip_preserves_provenance() -> None:
    data = _rich_graph().to_dict()
    kz = KuzuKnowledgeGraphStore.from_dict(data)
    assert kz.node_count() == len(data["nodes"])
    assert kz.edge_count() == len(data["edges"])
    # to_dict round-trips node-for-node and edge-for-edge, provenance intact.
    assert kz.to_dict() == InMemoryKnowledgeGraphStore.from_dict(data).to_dict()
    ex21 = next(e for e in kz.edges_by_relation("has_subsidiary"))
    assert ex21.properties["source_uri"].startswith("https://sec.gov/")


def test_edge_first_write_wins() -> None:
    kz = KuzuKnowledgeGraphStore()
    kz.upsert_node(_node("Company", "a"))
    kz.upsert_node(_node("Company", "b"))
    kz.upsert_edge(_edge("Company", "a", "references", "Company", "b", source="first"))
    kz.upsert_edge(_edge("Company", "a", "references", "Company", "b", source="second"))
    edges = kz.edges_by_relation("references")
    assert len(edges) == 1 and edges[0].properties["source"] == "first"


def test_node_last_write_wins() -> None:
    kz = KuzuKnowledgeGraphStore()
    kz.upsert_node(_node("Company", "a", name="Old"))
    kz.upsert_node(_node("Company", "a", name="New"))
    node = kz.get_node("Company", "a")
    assert node is not None and node.properties["name"] == "New"
    assert len(kz.nodes_of_kind("Company")) == 1


def test_open_synced_rebuilds_when_snapshot_newer(tmp_path: Path) -> None:
    json_path = tmp_path / "graph.json"
    db_path = tmp_path / "graph.kz"
    json_path.write_text(json.dumps(_rich_graph().to_dict()))
    store = KuzuKnowledgeGraphStore.open_synced(str(db_path), json_path)
    assert store.node_count() > 0
    assert db_path.exists()
    # Re-open without touching the snapshot: served from the cached DB, same data.
    reopened = KuzuKnowledgeGraphStore.open_synced(str(db_path), json_path)
    assert reopened.node_count() == store.node_count()


def test_open_synced_missing_snapshot_is_empty(tmp_path: Path) -> None:
    store = KuzuKnowledgeGraphStore.open_synced(str(tmp_path / "graph.kz"), tmp_path / "absent.json")
    assert store.node_count() == 0
    assert store.all_nodes() == []
