"""Project the curated entity knowledge base into the knowledge graph.

Turns isolated companies into a connected graph of people, suppliers, customers,
competitors, partners, countries, products, technologies, and agencies. Shared
entities (an executive at two companies, a supplier in a country, a common
competitor) link companies together — the platform's relationship moat.

Every node and edge carries provenance (`source="reference-entities"`). Documents
are linked to entities they mention via :func:`link_document_mentions`, so the
graph also grows as documents are ingested.
"""

from __future__ import annotations

import re

from coruscant.common.config import CompanyEntities
from coruscant.common.types import GraphEdge, GraphNode, NormalizedDocument
from coruscant.knowledge_graph.store import KnowledgeGraphStore

_PROVENANCE = "reference-entities"


def entity_key(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "entity"


def _node(kind: str, name: str, **props: object) -> GraphNode:
    return GraphNode(
        kind=kind,
        key=entity_key(name),
        properties={"name": name, "source": _PROVENANCE, **props},
    )


def _edge(
    source_kind: str,
    source_key: str,
    relation: str,
    target_kind: str,
    target_key: str,
    *,
    company_slug: str,
    **props: object,
) -> GraphEdge:
    return GraphEdge(
        source_kind=source_kind,
        source_key=source_key,
        relation=relation,
        target_kind=target_kind,
        target_key=target_key,
        properties={"source": _PROVENANCE, "company_slug": company_slug, **props},
    )


def project_company_entities(
    store: KnowledgeGraphStore,
    *,
    company_slug: str,
    company_name: str,
    entities: CompanyEntities,
) -> None:
    """Upsert all entity nodes/edges for one company into the store."""

    store.upsert_node(GraphNode(kind="Company", key=company_slug, properties={"name": company_name}))

    def link(relation: str, kind: str, name: str, **node_props: object) -> str:
        node = _node(kind, name, **node_props)
        store.upsert_node(node)
        store.upsert_edge(
            _edge("Company", company_slug, relation, kind, node.key, company_slug=company_slug)
        )
        return node.key

    for person in entities.people:
        person_key = _node("Person", person.name).key
        store.upsert_node(_node("Person", person.name, role=person.role))
        store.upsert_edge(
            _edge(
                "Company",
                company_slug,
                "employs",
                "Person",
                person_key,
                company_slug=company_slug,
                role=person.role,
            )
        )
        for prior in person.previously:
            store.upsert_node(_node("Company", prior, is_external=True))
            store.upsert_edge(
                _edge(
                    "Person",
                    person_key,
                    "previously_at",
                    "Company",
                    entity_key(prior),
                    company_slug=company_slug,
                )
            )

    for supplier in entities.suppliers:
        supplier_key = link("relies_on_supplier", "Company", supplier.name, is_supplier=True)
        if supplier.country:
            store.upsert_node(_node("Country", supplier.country))
            store.upsert_edge(
                _edge(
                    "Company",
                    supplier_key,
                    "operates_in",
                    "Country",
                    entity_key(supplier.country),
                    company_slug=company_slug,
                )
            )

    for customer in entities.customers:
        link("supplies_to", "Company", customer, is_customer=True)
    for competitor in entities.competitors:
        link("competes_with", "Company", competitor)
    for partner in entities.partners:
        link("partners_with", "Company", partner)
    for country in entities.countries:
        link("operates_in", "Country", country)
    for product in entities.products:
        product_key = link("produces", "Product", product)
        for technology in entities.technologies:
            store.upsert_node(_node("Technology", technology))
            store.upsert_edge(
                _edge(
                    "Product",
                    product_key,
                    "uses_technology",
                    "Technology",
                    entity_key(technology),
                    company_slug=company_slug,
                )
            )
    for technology in entities.technologies:
        link("uses_technology", "Technology", technology)
    for agency in entities.agencies:
        link("engaged_with", "Agency", agency)


def entity_names_for(company_name: str, entities: CompanyEntities) -> dict[str, tuple[str, str]]:
    """Map a lowercased mention -> (kind, key) for gazetteer linking."""

    names: dict[str, tuple[str, str]] = {company_name.lower(): ("Company", company_name)}
    for person in entities.people:
        names[person.name.lower()] = ("Person", person.name)
    for supplier in entities.suppliers:
        names[supplier.name.lower()] = ("Company", supplier.name)
        if supplier.country:
            names[supplier.country.lower()] = ("Country", supplier.country)
    for name in entities.competitors + entities.partners + entities.customers:
        names[name.lower()] = ("Company", name)
    for country in entities.countries:
        names[country.lower()] = ("Country", country)
    for product in entities.products:
        names[product.lower()] = ("Product", product)
    for technology in entities.technologies:
        names[technology.lower()] = ("Technology", technology)
    for agency in entities.agencies:
        names[agency.lower()] = ("Agency", agency)
    return names


def link_document_mentions(
    store: KnowledgeGraphStore,
    document: NormalizedDocument,
    names: dict[str, tuple[str, str]],
) -> int:
    """Add Document -mentions-> Entity edges for entity names found in the text."""

    haystack = " ".join(str(s.get("content") or "") for s in document.sections).lower()
    haystack += " " + (document.title or "").lower()
    linked = 0
    for mention, (kind, name) in names.items():
        if mention and mention in haystack:
            store.upsert_edge(
                GraphEdge(
                    source_kind="Document",
                    source_key=document.canonical_id,
                    relation="mentions",
                    target_kind=kind,
                    target_key=entity_key(name),
                    properties={
                        "source_uri": document.source_uri,
                        "entity_name": name,
                    },
                )
            )
            linked += 1
    return linked
