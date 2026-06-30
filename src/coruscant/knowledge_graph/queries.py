"""Relationship-intelligence queries over the knowledge graph.

These answer the kind of cross-entity questions that isolated documents cannot —
who is exposed to a country through suppliers, which executives are connected
through shared companies, and what an entity is connected to.
"""

from __future__ import annotations

from pydantic import BaseModel

from coruscant.knowledge_graph.entities import entity_key
from coruscant.knowledge_graph.memory import InMemoryKnowledgeGraphStore


class EntityRef(BaseModel):
    kind: str
    key: str
    name: str


class Relationship(BaseModel):
    relation: str
    direction: str  # "out" | "in"
    other: EntityRef
    source: str | None = None  # provenance of the edge (e.g. "reference-entities")
    detail: str | None = None  # human-readable edge fact: officer role / subsidiary jurisdiction


class EntityProfile(BaseModel):
    entity: EntityRef
    properties: dict[str, object] = {}
    relationships: list[Relationship] = []
    mentioned_in: list[str] = []  # canonical ids of documents mentioning the entity


class ExposurePath(BaseModel):
    company: EntityRef
    via: EntityRef  # the supplier/operator in the country
    relation: str
    source: str | None = None  # provenance of the inferred exposure


class ExposureResult(BaseModel):
    country: str
    direct: list[EntityRef] = []  # entities operating in the country
    exposed: list[ExposurePath] = []  # companies exposed through a supplier


class JurisdictionCount(BaseModel):
    jurisdiction: str
    companies: int  # how many companies hold a legal entity there


class JurisdictionFootprint(BaseModel):
    """A company's legal footprint in the affected jurisdiction (Exhibit 21) —
    evidence-backed direct exposure to an event there."""

    company: EntityRef
    subsidiaries: list[str] = []  # subsidiary names registered in the jurisdiction
    source: str | None = None  # the Exhibit-21 filing URL (provenance)


class NetworkProximity(BaseModel):
    """A company whose filings name a directly-exposed peer. An orientation hint,
    NOT dollar exposure — co-mention is an undifferentiated competitor/customer/
    supplier signal, and we have no supply-chain weight data yet."""

    company: EntityRef
    names: EntityRef  # the directly-exposed company it references
    entity_name: str | None = None  # the name as written in the filing
    source: str | None = None  # filing URL


class JurisdictionExposure(BaseModel):
    jurisdiction: str
    direct: list[JurisdictionFootprint] = []  # legal footprint there (evidence-backed)
    network: list[NetworkProximity] = []  # peers that name an exposed company (weaker)


class SectorCount(BaseModel):
    sector: str
    companies: int


class SectorExposure(BaseModel):
    """Thematic exposure: an event on a sector (e.g. rare-earth controls -> semis)
    -> the companies in it. 'No exposure' is a first-class answer (you're agri)."""

    sector: str
    direct: list[EntityRef] = []  # companies operating in the sector
    network: list[NetworkProximity] = []  # peers that name an exposed company


class CoExecutiveGroup(BaseModel):
    company: EntityRef
    people: list[EntityRef] = []


class BridgePerson(BaseModel):
    person: EntityRef
    companies: list[EntityRef] = []


class CoExecutiveResult(BaseModel):
    shared_company_groups: list[CoExecutiveGroup] = []
    multi_company_people: list[BridgePerson] = []


def _name(store: InMemoryKnowledgeGraphStore, kind: str, key: str) -> str:
    node = store.get_node(kind, key)
    if node is not None:
        value = node.properties.get("name")
        if isinstance(value, str):
            return value
    return key


def _ref(store: InMemoryKnowledgeGraphStore, kind: str, key: str) -> EntityRef:
    return EntityRef(kind=kind, key=key, name=_name(store, kind, key))


def _source_of(properties: dict[str, object]) -> str | None:
    value = properties.get("source")
    return value if isinstance(value, str) else None


def _str_prop(properties: dict[str, object], key: str) -> str | None:
    value = properties.get(key)
    return value if isinstance(value, str) else None


def _normalize_jurisdiction(value: str) -> str:
    # Exhibit-21 jurisdictions arrive with non-breaking spaces and stray whitespace.
    return value.replace("\xa0", " ").strip()


def _detail_of(properties: dict[str, object]) -> str | None:
    """The most useful human-readable fact carried on the edge (officer role,
    subsidiary jurisdiction, insider shares). Stored on the edge but otherwise
    dropped by the API."""
    shares = properties.get("shares")
    if isinstance(shares, int):
        role = properties.get("role")
        held = f"{shares:,} shares"
        return f"{role} · {held}" if isinstance(role, str) and role else held
    for key in ("role", "jurisdiction"):
        value = properties.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def entity_profile(store: InMemoryKnowledgeGraphStore, kind: str, key: str) -> EntityProfile | None:
    node = store.get_node(kind, key)
    if node is None:
        return None
    relationships: list[Relationship] = []
    mentioned_in: list[str] = []
    for edge, _ in store.neighbors(kind, key):
        if edge.relation == "mentions":
            continue
        relationships.append(
            Relationship(
                relation=edge.relation,
                direction="out",
                other=_ref(store, edge.target_kind, edge.target_key),
                source=_source_of(edge.properties),
                detail=_detail_of(edge.properties),
            )
        )
    for edge in store.incoming(kind, key):
        if edge.relation == "mentions":
            mentioned_in.append(edge.source_key)
            continue
        relationships.append(
            Relationship(
                relation=edge.relation,
                direction="in",
                other=_ref(store, edge.source_kind, edge.source_key),
                source=_source_of(edge.properties),
                detail=_detail_of(edge.properties),
            )
        )
    return EntityProfile(
        entity=_ref(store, kind, key),
        properties=dict(node.properties),
        relationships=relationships,
        mentioned_in=sorted(set(mentioned_in)),
    )


def list_entities(store: InMemoryKnowledgeGraphStore, kind: str | None = None) -> list[EntityRef]:
    refs = [
        EntityRef(kind=node.kind, key=node.key, name=_name(store, node.kind, node.key))
        for node in store.nodes.values()
        if kind is None or node.kind == kind
    ]
    return sorted(refs, key=lambda r: (r.kind, r.name))


def exposure_to_country(store: InMemoryKnowledgeGraphStore, country: str) -> ExposureResult:
    country_key = entity_key(country)
    result = ExposureResult(country=_name(store, "Country", country_key))
    # Entities that operate in the country (incoming operates_in edges).
    for edge in store.incoming("Country", country_key):
        if edge.relation != "operates_in":
            continue
        operator = _ref(store, edge.source_kind, edge.source_key)
        result.direct.append(operator)
        # Companies that rely on this operator as a supplier are exposed.
        for in_edge in store.incoming(edge.source_kind, edge.source_key):
            if in_edge.relation == "relies_on_supplier":
                result.exposed.append(
                    ExposurePath(
                        company=_ref(store, in_edge.source_kind, in_edge.source_key),
                        via=operator,
                        relation="relies_on_supplier",
                        source=_source_of(in_edge.properties) or "reference-entities",
                    )
                )
    return result


def list_jurisdictions(store: InMemoryKnowledgeGraphStore) -> list[JurisdictionCount]:
    """Jurisdictions where companies hold subsidiaries, by exposed-company count —
    the menu of "events" the exposure demo can fire on."""
    companies_by_juris: dict[str, set[str]] = {}
    for edge in store.edges_by_relation("has_subsidiary"):
        juris = _normalize_jurisdiction(str(edge.properties.get("jurisdiction", "")))
        if juris:
            companies_by_juris.setdefault(juris, set()).add(edge.source_key)
    counts = [
        JurisdictionCount(jurisdiction=juris, companies=len(companies))
        for juris, companies in companies_by_juris.items()
    ]
    return sorted(counts, key=lambda c: (-c.companies, c.jurisdiction))


def jurisdiction_exposure(
    store: InMemoryKnowledgeGraphStore, jurisdiction: str
) -> JurisdictionExposure:
    """Who is exposed to an event in `jurisdiction`, on today's evidence.

    Direct exposure = a legal entity registered there (Exhibit 21), cited to the
    filing. Network = peers whose filings name a directly-exposed company (an
    orientation hint, not dollar magnitude — we have no supply-chain weight data).
    """
    target = _normalize_jurisdiction(jurisdiction)
    result = JurisdictionExposure(jurisdiction=target)

    subs_by_company: dict[str, list[str]] = {}
    source_by_company: dict[str, str | None] = {}
    for edge in store.edges_by_relation("has_subsidiary"):
        if _normalize_jurisdiction(str(edge.properties.get("jurisdiction", ""))) != target:
            continue
        subs_by_company.setdefault(edge.source_key, []).append(
            _name(store, edge.target_kind, edge.target_key)
        )
        source_by_company.setdefault(edge.source_key, _str_prop(edge.properties, "source_uri"))

    for company_key in sorted(subs_by_company):
        result.direct.append(
            JurisdictionFootprint(
                company=_ref(store, "Company", company_key),
                subsidiaries=sorted(subs_by_company[company_key]),
                source=source_by_company.get(company_key),
            )
        )

    exposed = set(subs_by_company)
    seen: set[tuple[str, str]] = set()
    for edge in store.edges_by_relation("references"):
        if edge.target_key in exposed and edge.source_key not in exposed:
            pair = (edge.source_key, edge.target_key)
            if pair in seen:
                continue
            seen.add(pair)
            result.network.append(
                NetworkProximity(
                    company=_ref(store, "Company", edge.source_key),
                    names=_ref(store, "Company", edge.target_key),
                    entity_name=_str_prop(edge.properties, "entity_name"),
                    source=_str_prop(edge.properties, "source_uri"),
                )
            )
    return result


def list_sectors(store: InMemoryKnowledgeGraphStore) -> list[SectorCount]:
    """Sectors with their company counts — the menu of thematic 'events'. Taxonomy-
    agnostic: reads whatever `in_sector` points to (SIC today, GICS once re-tagged)."""
    companies_by_sector: dict[str, set[str]] = {}
    for edge in store.edges_by_relation("in_sector"):
        sector = _name(store, edge.target_kind, edge.target_key).strip()
        if sector:
            companies_by_sector.setdefault(sector, set()).add(edge.source_key)
    counts = [
        SectorCount(sector=sector, companies=len(companies))
        for sector, companies in companies_by_sector.items()
    ]
    return sorted(counts, key=lambda c: (-c.companies, c.sector))


def sector_exposure(store: InMemoryKnowledgeGraphStore, sector: str) -> SectorExposure:
    """Thematic exposure to an event on `sector` (e.g. rare-earth controls -> semis):
    the companies operating in it, plus peers that name them. An empty result is a
    real answer — 'no exposure, you're agri' is the insight."""
    target = sector.strip().lower()
    result = SectorExposure(sector=sector.strip())

    exposed: set[str] = set()
    for edge in store.edges_by_relation("in_sector"):
        if _name(store, edge.target_kind, edge.target_key).strip().lower() == target:
            exposed.add(edge.source_key)
    for company_key in sorted(exposed):
        result.direct.append(_ref(store, "Company", company_key))

    seen: set[tuple[str, str]] = set()
    for edge in store.edges_by_relation("references"):
        if edge.target_key in exposed and edge.source_key not in exposed:
            pair = (edge.source_key, edge.target_key)
            if pair in seen:
                continue
            seen.add(pair)
            result.network.append(
                NetworkProximity(
                    company=_ref(store, "Company", edge.source_key),
                    names=_ref(store, "Company", edge.target_key),
                    entity_name=_str_prop(edge.properties, "entity_name"),
                    source=_str_prop(edge.properties, "source_uri"),
                )
            )
    return result


def company_country_exposures(
    store: InMemoryKnowledgeGraphStore, company_key: str
) -> list[tuple[str, str]]:
    """(country name, supplier name) the company is exposed to via its suppliers."""

    exposures: list[tuple[str, str]] = []
    for edge in store.outgoing("Company", company_key):
        if edge.relation != "relies_on_supplier":
            continue
        supplier_name = _name(store, edge.target_kind, edge.target_key)
        for supplier_edge in store.outgoing(edge.target_kind, edge.target_key):
            if supplier_edge.relation == "operates_in":
                country = _name(store, supplier_edge.target_kind, supplier_edge.target_key)
                exposures.append((country, supplier_name))
    return exposures


def co_executives(store: InMemoryKnowledgeGraphStore) -> CoExecutiveResult:
    # Build company -> people and person -> companies from employs / previously_at.
    company_people: dict[str, set[str]] = {}
    person_companies: dict[str, set[str]] = {}
    for edge in store.edges_by_relation("employs"):
        company_people.setdefault(edge.source_key, set()).add(edge.target_key)
        person_companies.setdefault(edge.target_key, set()).add(edge.source_key)
    for edge in store.edges_by_relation("previously_at"):
        company_people.setdefault(edge.target_key, set()).add(edge.source_key)
        person_companies.setdefault(edge.source_key, set()).add(edge.target_key)

    groups = [
        CoExecutiveGroup(
            company=_ref(store, "Company", company),
            people=[_ref(store, "Person", p) for p in sorted(people)],
        )
        for company, people in sorted(company_people.items())
        if len(people) >= 2
    ]
    bridges = [
        BridgePerson(
            person=_ref(store, "Person", person),
            companies=[_ref(store, "Company", c) for c in sorted(companies)],
        )
        for person, companies in sorted(person_companies.items())
        if len(companies) >= 2
    ]
    return CoExecutiveResult(shared_company_groups=groups, multi_company_people=bridges)
