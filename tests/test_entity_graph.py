from __future__ import annotations

from coruscant.common.config import CompanyEntities, PersonConfig, SupplierConfig
from coruscant.common.types import NormalizedDocument
from coruscant.knowledge_graph.entities import (
    entity_names_for,
    link_document_mentions,
    project_company_entities,
)
from coruscant.knowledge_graph.memory import InMemoryKnowledgeGraphStore
from coruscant.knowledge_graph.queries import (
    co_executives,
    entity_profile,
    exposure_to_country,
    list_entities,
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
