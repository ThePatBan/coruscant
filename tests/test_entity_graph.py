from __future__ import annotations

from coruscant.exposure.domain_config import (
    CompanyConfig,
    CompanyEntities,
    PersonConfig,
    SupplierConfig,
)
from coruscant.common.types import NormalizedDocument
from coruscant.exposure.entities import (
    entity_names_for,
    link_document_mentions,
    project_company_entities,
)
from coruscant.common.types import GraphEdge, GraphNode
from coruscant.exposure.extraction import (
    project_company_nodes,
    project_market_tier_edges,
    project_sector_edges,
)
from coruscant.knowledge_graph.memory import InMemoryKnowledgeGraphStore
from coruscant.exposure.queries import (
    co_executives,
    entity_profile,
    exposure_to_country,
    gics_breakdown,
    jurisdiction_exposure,
    list_entities,
    list_jurisdictions,
    list_market_tiers,
    list_sectors,
    market_tier_exposure,
    sector_exposure,
)


def _seed() -> InMemoryKnowledgeGraphStore:
    store = InMemoryKnowledgeGraphStore()
    project_company_entities(
        store,
        company_slug="apple",
        company_name="Apple",
        entities=CompanyEntities(
            people=[PersonConfig(name="Tim Cook", role="CEO", previously=["IBM"])],
            suppliers=[SupplierConfig(name="TSMC", country="Taiwan")],
            competitors=["Microsoft"],
            countries=["United States"],
            products=["iPhone"],
            technologies=["Semiconductors"],
        ),
    )
    project_company_entities(
        store,
        company_slug="microsoft",
        company_name="Microsoft",
        entities=CompanyEntities(
            people=[PersonConfig(name="Satya Nadella", role="CEO", previously=["IBM"])],
            suppliers=[SupplierConfig(name="TSMC", country="Taiwan")],
            partners=["OpenAI"],
        ),
    )
    return store


def test_projection_creates_typed_entities_and_edges() -> None:
    store = _seed()
    assert store.get_node("Person", "tim-cook") is not None
    assert store.get_node("Country", "taiwan") is not None
    assert store.get_node("Company", "tsmc") is not None
    relations = {e.relation for e in store.edges}
    assert {"employs", "relies_on_supplier", "operates_in", "competes_with", "produces"} <= relations


def test_exposure_to_country_via_supplier() -> None:
    result = exposure_to_country(_seed(), "Taiwan")
    assert {r.name for r in result.direct} == {"TSMC"}
    exposed = {p.company.name for p in result.exposed}
    assert exposed == {"Apple", "Microsoft"}  # both rely on TSMC which operates in Taiwan


def test_co_executives_finds_shared_companies() -> None:
    result = co_executives(_seed())
    # Tim Cook and Satya Nadella both previously at IBM -> co-executives there.
    ibm = next((g for g in result.shared_company_groups if g.company.key == "ibm"), None)
    assert ibm is not None
    assert {p.name for p in ibm.people} == {"Tim Cook", "Satya Nadella"}


def test_entity_profile_includes_relationships_and_mentions() -> None:
    store = _seed()
    document = NormalizedDocument(
        document_type="filing",
        source_uri="reference://sec_edgar/apple/2025",
        canonical_id="doc1",
        title="Apple 10-K",
        sections=[{"title": "Risk", "content": "Apple depends on TSMC in Taiwan."}],
    )
    names = entity_names_for("Apple", CompanyEntities(suppliers=[SupplierConfig(name="TSMC")]))
    linked = link_document_mentions(store, document, names)
    assert linked >= 1

    tsmc = entity_profile(store, "Company", "tsmc")
    assert tsmc is not None
    assert "doc1" in tsmc.mentioned_in
    apple = entity_profile(store, "Company", "apple")
    assert apple is not None
    assert any(r.relation == "relies_on_supplier" and r.other.name == "TSMC" for r in apple.relationships)


def test_external_reference_does_not_clobber_tracked_company() -> None:
    # Apple lists Microsoft as a competitor; Microsoft is itself tracked. The
    # tracked node must keep its authoritative properties regardless of order.
    for order in (("apple", "microsoft"), ("microsoft", "apple")):
        store = InMemoryKnowledgeGraphStore()
        defs = {
            "apple": CompanyEntities(competitors=["Microsoft"]),
            "microsoft": CompanyEntities(people=[PersonConfig(name="Satya Nadella", role="CEO")]),
        }
        names = {"apple": "Apple", "microsoft": "Microsoft"}
        for slug in order:
            project_company_entities(
                store, company_slug=slug, company_name=names[slug], entities=defs[slug]
            )
        node = store.get_node("Company", "microsoft")
        assert node is not None
        assert node.properties.get("name") == "Microsoft"
        assert node.properties.get("source") == "tracked"
        assert node.properties.get("is_external") is None


def test_mention_edge_kind_matches_projected_document_node() -> None:
    from coruscant.knowledge_graph.reference import document_node_kind

    store = InMemoryKnowledgeGraphStore()
    project_company_entities(
        store, company_slug="apple", company_name="Apple", entities=CompanyEntities()
    )
    document = NormalizedDocument(
        document_type="filing",
        source_uri="reference://sec_edgar/apple/2025",
        canonical_id="docF",
        title="Apple 10-K",
        sections=[{"title": "Risk", "content": "Apple disclosed risks."}],
    )
    link_document_mentions(store, document, entity_names_for("Apple", CompanyEntities()))
    mentions = [e for e in store.edges if e.relation == "mentions"]
    assert mentions
    # Edge source kind matches the kind the document node is projected as ("Filing").
    assert all(e.source_kind == document_node_kind("filing") for e in mentions)


def test_list_entities_by_kind() -> None:
    store = _seed()
    people = list_entities(store, "Person")
    assert {p.name for p in people} == {"Tim Cook", "Satya Nadella"}
    assert all(p.kind == "Person" for p in people)


def _exposure_store() -> InMemoryKnowledgeGraphStore:
    """Seeds the edge types the real loaded graph carries: has_subsidiary (with a
    jurisdiction), in_sector, and references."""
    store = InMemoryKnowledgeGraphStore()
    for slug, name in [("hon", "Honeywell"), ("pg", "P&G"), ("mmm", "3M"), ("ko", "Coca-Cola")]:
        store.upsert_node(GraphNode(kind="Company", key=slug, properties={"name": name}))
    store.upsert_node(GraphNode(kind="Subsidiary", key="hon-china", properties={"name": "Honeywell China Co."}))
    store.upsert_node(GraphNode(kind="Subsidiary", key="pg-shanghai", properties={"name": "Gillette (Shanghai) Ltd."}))
    store.upsert_node(GraphNode(kind="Industry", key="semis", properties={"name": "Semiconductors & Related Devices"}))
    # Honeywell + P&G hold a legal entity in China (note the non-breaking space).
    store.upsert_edge(GraphEdge(source_kind="Company", source_key="hon", relation="has_subsidiary",
        target_kind="Subsidiary", target_key="hon-china",
        properties={"jurisdiction": "China\xa0", "source_uri": "https://sec.gov/hon-ex21"}))
    store.upsert_edge(GraphEdge(source_kind="Company", source_key="pg", relation="has_subsidiary",
        target_kind="Subsidiary", target_key="pg-shanghai", properties={"jurisdiction": "China"}))
    # 3M references Honeywell; Honeywell is in the semiconductors sector.
    store.upsert_edge(GraphEdge(source_kind="Company", source_key="mmm", relation="references",
        target_kind="Company", target_key="hon",
        properties={"entity_name": "Honeywell International", "source_uri": "https://sec.gov/mmm-10k"}))
    store.upsert_edge(GraphEdge(source_kind="Company", source_key="hon", relation="in_sector",
        target_kind="Industry", target_key="semis"))
    return store


def test_jurisdiction_exposure_uses_exhibit21_footprint() -> None:
    store = _exposure_store()
    assert [(j.jurisdiction, j.companies) for j in list_jurisdictions(store)] == [("China", 2)]
    result = jurisdiction_exposure(store, "China")  # nbsp normalized away
    assert {fp.company.name for fp in result.direct} == {"Honeywell", "P&G"}
    hon = next(fp for fp in result.direct if fp.company.name == "Honeywell")
    assert hon.subsidiaries == ["Honeywell China Co."]
    assert hon.source == "https://sec.gov/hon-ex21"  # provenance preserved
    # 3M names Honeywell (an exposed peer) but has no China footprint -> network, not direct.
    assert {n.company.name for n in result.network} == {"3M"}


def test_sector_exposure_and_no_exposure_is_an_answer() -> None:
    store = _exposure_store()
    assert ("Semiconductors & Related Devices", 1) in [(s.sector, s.companies) for s in list_sectors(store)]
    semis = sector_exposure(store, "Semiconductors & Related Devices")
    assert {c.name for c in semis.direct} == {"Honeywell"}
    assert {n.company.name for n in semis.network} == {"3M"}  # names the exposed company
    # An agri portfolio: a sector we don't touch returns empty — itself the insight.
    assert sector_exposure(store, "Agricultural Production").direct == []


def _taxonomy_store() -> InMemoryKnowledgeGraphStore:
    """Two mapped companies (Apple/US, Infosys/India) and one uncurated company
    with only a raw SIC industry, run through the real projectors."""
    store = InMemoryKnowledgeGraphStore()
    companies = [
        CompanyConfig(slug="aapl", name="Apple Inc.", industry="Electronic Computers", country="United States"),
        CompanyConfig(slug="infy", name="Infosys Ltd", industry="Services-Computer Programming", country="India"),
        CompanyConfig(slug="zzz", name="Zeta Mining Co", industry="Metal Mining", country="Narnia"),
    ]
    project_company_nodes(store, companies)
    project_sector_edges(store, companies)
    project_market_tier_edges(store, companies)
    return store


def test_sector_edges_retag_to_gics_with_sic_fallback() -> None:
    store = _taxonomy_store()
    # Apple + Infosys both curate to the GICS sector, replacing their raw SIC labels.
    sectors = {s.sector: s.companies for s in list_sectors(store)}
    assert sectors.get("Information Technology") == 2
    assert "Electronic Computers" not in sectors
    # The curated edge carries GICS provenance + the raw SIC for audit.
    edge = next(e for e in store.edges_by_relation("in_sector") if e.source_key == "aapl")
    assert edge.properties["source"] == "gics-curated"
    assert edge.properties["sic_industry"] == "Electronic Computers"
    assert store.get_node("Company", "aapl").properties["gics_sector"] == "Information Technology"
    # An uncurated company falls back to its raw SIC sector (never dropped/invented).
    assert sectors.get("Metal Mining") == 1
    fallback = next(e for e in store.edges_by_relation("in_sector") if e.source_key == "zzz")
    assert fallback.properties["source"] == "sec-metadata"


def test_gics_hierarchy_exposure_at_any_level() -> None:
    store = _taxonomy_store()
    # Sector-level event hits both IT holdings...
    it = sector_exposure(store, "Information Technology")
    assert {c.key for c in it.direct} == {"aapl", "infy"}
    assert it.matched_level == "sector"
    # ...but a sub-industry event is specific: only Infosys is IT Consulting.
    consult = sector_exposure(store, "IT Consulting & Other Services")
    assert {c.key for c in consult.direct} == {"infy"}
    assert consult.matched_level == "sub_industry"
    # The 8-digit code resolves too (Apple's Technology Hardware code).
    assert {c.key for c in sector_exposure(store, "45202030").direct} == {"aapl"}
    # A level we don't hold is a real, empty answer.
    assert sector_exposure(store, "Semiconductors").direct == []


def test_gics_breakdown_tree() -> None:
    store = _taxonomy_store()
    tree = {s.sector: s for s in gics_breakdown(store)}
    it = tree["Information Technology"]
    assert it.companies == 2
    subs = {s.sub_industry: [c.key for c in s.companies] for s in it.sub_industries}
    assert subs["IT Consulting & Other Services"] == ["infy"]
    assert subs["Technology Hardware, Storage & Peripherals"] == ["aapl"]
    # The sub-industry carries its 8-digit code (the MSCI-index join key).
    infy_sub = next(s for s in it.sub_industries if s.sub_industry == "IT Consulting & Other Services")
    assert infy_sub.code == "45102010"


def test_market_tier_projection_and_exposure() -> None:
    store = _taxonomy_store()
    # US + Narnia(unmapped→skipped)? Narnia has no MSCI tier, so only US (DM) + India (EM).
    breakdown = [(t.tier, t.label, t.companies) for t in list_market_tiers(store)]
    assert breakdown == [("DM", "Developed market", 1), ("EM", "Emerging market", 1)]
    # Tier resolvable by code ("EM") regardless of case.
    em = market_tier_exposure(store, "em")
    assert em.tier == "EM" and {c.key for c in em.direct} == {"infy"}
    assert store.get_node("Company", "infy").properties["market_tier"] == "EM"
    # No Frontier exposure is a real answer.
    assert market_tier_exposure(store, "FM").direct == []
    # An unmapped country carries no tier edge.
    assert store.get_node("Company", "zzz").properties.get("market_tier") is None
