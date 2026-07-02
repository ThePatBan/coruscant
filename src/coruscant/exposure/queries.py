"""Relationship-intelligence queries over the knowledge graph.

These answer the kind of cross-entity questions that isolated documents cannot —
who is exposed to a country through suppliers, which executives are connected
through shared companies, and what an entity is connected to.
"""

from __future__ import annotations

from collections import deque
from datetime import date

from pydantic import BaseModel

from coruscant.common.types import GraphEdge
from coruscant.knowledge_graph import substrate
from coruscant.exposure.entities import entity_key
from coruscant.knowledge_graph.store import KnowledgeGraphStore


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
    """Thematic exposure: an event on a GICS level (a sector like Information
    Technology, or a finer sub-industry like Semiconductors) -> the companies in
    it. Matches at any level of the hierarchy. 'No exposure' is a first-class
    answer (you're agri)."""

    sector: str  # the queried term, echoed back
    matched_level: str | None = None  # "sector" | "industry_group" | "industry" | "sub_industry"
    direct: list[EntityRef] = []  # companies operating in the sector
    network: list[NetworkProximity] = []  # peers that name an exposed company


class GicsSubIndustry(BaseModel):
    sub_industry: str
    industry: str
    code: str | None = None
    companies: list[EntityRef] = []


class GicsSector(BaseModel):
    """One GICS sector with its sub-industry breakdown — the portfolio's sector
    composition, drillable to the holding level."""

    sector: str
    companies: int
    sub_industries: list[GicsSubIndustry] = []


class MarketTierCount(BaseModel):
    """One MSCI market tier and how many holdings sit in it — the portfolio's
    Developed/Emerging/Frontier composition (pathway 4)."""

    tier: str  # MSCI code: "DM" | "EM" | "FM"
    label: str  # "Developed market" etc.
    companies: int


class MarketTierExposure(BaseModel):
    """The holdings in one MSCI market tier — clicking "EM" shows your EM book.
    Like sector exposure, an empty result is a real answer (you hold no FM)."""

    tier: str
    label: str
    direct: list[EntityRef] = []  # companies classified in this tier


class CoExecutiveGroup(BaseModel):
    company: EntityRef
    people: list[EntityRef] = []


class BridgePerson(BaseModel):
    person: EntityRef
    companies: list[EntityRef] = []


class CoExecutiveResult(BaseModel):
    shared_company_groups: list[CoExecutiveGroup] = []
    multi_company_people: list[BridgePerson] = []


def _name(store: KnowledgeGraphStore, kind: str, key: str) -> str:
    node = store.get_node(kind, key)
    if node is not None:
        value = node.properties.get("name")
        if isinstance(value, str):
            return value
    return key


def _ref(store: KnowledgeGraphStore, kind: str, key: str) -> EntityRef:
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
    # For in_sector edges the target node is already the sub-industry, so the
    # useful complementary fact is the parent GICS sector.
    for key in ("role", "jurisdiction", "sector"):
        value = properties.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def entity_profile(
    store: KnowledgeGraphStore,
    kind: str,
    key: str,
    *,
    clearance: substrate.AccessTier | str = substrate.AccessTier.PUBLIC,
) -> EntityProfile | None:
    node = store.get_node(kind, key)
    if node is None:
        return None
    relationships: list[Relationship] = []
    mentioned_in: list[str] = []
    for edge, _ in store.neighbors(kind, key):
        if edge.relation == "mentions":
            continue
        # Access-tier gate: a sensitive edge (PEP/sanctions, beneficial ownership)
        # is withheld from callers below its clearance — never leaked through the
        # generic entity profile (default PUBLIC keeps anonymous readers evidence-safe).
        if not substrate.can_see(edge.properties, clearance):
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
            # A "mentions" edge exposes a source document id — gate it by tier too, so a
            # future private mention never leaks even the existence of its document.
            if substrate.can_see(edge.properties, clearance):
                mentioned_in.append(edge.source_key)
            continue
        if not substrate.can_see(edge.properties, clearance):
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


def list_entities(store: KnowledgeGraphStore, kind: str | None = None) -> list[EntityRef]:
    refs = [
        EntityRef(kind=node.kind, key=node.key, name=_name(store, node.kind, node.key))
        for node in store.all_nodes()
        if kind is None or node.kind == kind
    ]
    return sorted(refs, key=lambda r: (r.kind, r.name))


def exposure_to_country(store: KnowledgeGraphStore, country: str) -> ExposureResult:
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


def list_jurisdictions(store: KnowledgeGraphStore) -> list[JurisdictionCount]:
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
    store: KnowledgeGraphStore, jurisdiction: str
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


_GICS_LEVELS = ("sector", "industry_group", "industry", "sub_industry")


def _sector_of(store: KnowledgeGraphStore, edge: GraphEdge) -> str:
    """The GICS sector an `in_sector` edge rolls up to: the curated `sector`
    property, falling back to the target node's name (the SIC fallback case)."""
    sector = _str_prop(edge.properties, "sector")
    if sector:
        return sector.strip()
    return _name(store, edge.target_kind, edge.target_key).strip()


def _classification_terms(store: KnowledgeGraphStore, edge: GraphEdge) -> set[str]:
    """Every taxonomy term an `in_sector` edge can be matched against, lowercased:
    each GICS level name, the 8-digit code, and the target node name (so an
    uncurated SIC fallback still matches by its raw label)."""
    terms: set[str] = set()
    name = _name(store, edge.target_kind, edge.target_key)
    if name:
        terms.add(name.strip().lower())
    for key in (*_GICS_LEVELS, "code"):
        value = _str_prop(edge.properties, key)
        if value:
            terms.add(value.strip().lower())
    return terms


def list_sectors(store: KnowledgeGraphStore) -> list[SectorCount]:
    """GICS sectors with their company counts — the headline thematic menu. Reads
    the curated `sector` off each `in_sector` edge (or the target node name for an
    uncurated SIC fallback)."""
    companies_by_sector: dict[str, set[str]] = {}
    for edge in store.edges_by_relation("in_sector"):
        sector = _sector_of(store, edge)
        if sector:
            companies_by_sector.setdefault(sector, set()).add(edge.source_key)
    counts = [
        SectorCount(sector=sector, companies=len(companies))
        for sector, companies in companies_by_sector.items()
    ]
    return sorted(counts, key=lambda c: (-c.companies, c.sector))


def gics_breakdown(store: KnowledgeGraphStore) -> list[GicsSector]:
    """The portfolio's GICS composition as a sector -> sub-industry -> holdings
    tree, drillable on the World tab. Ordered by company count, descending."""
    # sector -> sub_industry -> (industry, code, {company keys})
    tree: dict[str, dict[str, tuple[str, str | None, set[str]]]] = {}
    for edge in store.edges_by_relation("in_sector"):
        sector = _sector_of(store, edge)
        if not sector:
            continue
        sub = _str_prop(edge.properties, "sub_industry") or _name(store, edge.target_kind, edge.target_key).strip()
        industry = _str_prop(edge.properties, "industry") or sub
        code = _str_prop(edge.properties, "code")
        _, _, members = tree.setdefault(sector, {}).setdefault(sub, (industry, code, set()))
        members.add(edge.source_key)

    sectors: list[GicsSector] = []
    for sector, subs in tree.items():
        sub_models = [
            GicsSubIndustry(
                sub_industry=sub,
                industry=industry,
                code=code,
                companies=[_ref(store, "Company", key) for key in sorted(members)],
            )
            for sub, (industry, code, members) in subs.items()
        ]
        sub_models.sort(key=lambda s: (-len(s.companies), s.sub_industry))
        total = len({key for _, _, members in subs.values() for key in members})
        sectors.append(GicsSector(sector=sector, companies=total, sub_industries=sub_models))
    sectors.sort(key=lambda s: (-s.companies, s.sector))
    return sectors


def sector_exposure(store: KnowledgeGraphStore, sector: str) -> SectorExposure:
    """Thematic exposure to an event on a GICS level `sector` — a sector
    (Information Technology), an industry group, an industry, or a sub-industry
    (Semiconductors), matched at whatever level the term names. Returns the
    companies in it plus peers that name them. An empty result is a real answer —
    'no exposure, you're agri' is the insight."""
    target = sector.strip().lower()
    result = SectorExposure(sector=sector.strip())

    exposed: set[str] = set()
    for edge in store.edges_by_relation("in_sector"):
        if target in _classification_terms(store, edge):
            exposed.add(edge.source_key)
            if result.matched_level is None:
                for level in _GICS_LEVELS:
                    value = _str_prop(edge.properties, level)
                    if value and value.strip().lower() == target:
                        result.matched_level = level
                        break
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


_TIER_ORDER = {"DM": 0, "EM": 1, "FM": 2}


def _tier_code(store: KnowledgeGraphStore, key: str) -> str:
    node = store.get_node("MarketTier", key)
    if node is not None:
        code = node.properties.get("code")
        if isinstance(code, str):
            return code
    return key.upper()


def list_market_tiers(store: KnowledgeGraphStore) -> list[MarketTierCount]:
    """The portfolio's MSCI Developed/Emerging/Frontier composition, by company
    count — the "you're X% EM" breakdown. Ordered DM -> EM -> FM."""
    companies_by_tier: dict[str, set[str]] = {}
    for edge in store.edges_by_relation("in_market_tier"):
        companies_by_tier.setdefault(edge.target_key, set()).add(edge.source_key)
    counts = [
        MarketTierCount(
            tier=_tier_code(store, tier_key),
            label=_name(store, "MarketTier", tier_key),
            companies=len(companies),
        )
        for tier_key, companies in companies_by_tier.items()
    ]
    return sorted(counts, key=lambda c: (_TIER_ORDER.get(c.tier, 9), c.tier))


def market_tier_exposure(store: KnowledgeGraphStore, tier: str) -> MarketTierExposure:
    """The holdings classified in MSCI market tier `tier` (a code like "EM" or a
    node key like "em"). An empty result is a real answer — no Frontier exposure
    is itself the insight."""
    target = tier.strip().lower()
    # Resolve the tier node by its key ("em") or its code ("EM").
    tier_key = None
    for node in store.nodes_of_kind("MarketTier"):
        code = node.properties.get("code")
        if node.key == target or (isinstance(code, str) and code.lower() == target):
            tier_key = node.key
            break
    result = MarketTierExposure(tier=tier.strip().upper(), label="")
    if tier_key is None:
        return result
    result.tier = _tier_code(store, tier_key)
    result.label = _name(store, "MarketTier", tier_key)
    members = sorted(
        {edge.source_key for edge in store.incoming("MarketTier", tier_key) if edge.relation == "in_market_tier"}
    )
    result.direct = [_ref(store, "Company", key) for key in members]
    return result


class CommodityRef(BaseModel):
    slug: str
    name: str
    category: str
    symbol: str | None = None
    affects_sectors: list[str] = []


class DebtRef(BaseModel):
    slug: str
    name: str
    debt_type: str
    issuer_country: str
    symbol: str | None = None


class CommodityExposure(BaseModel):
    """An event on a commodity -> the equity holdings exposed to it, via the GICS
    sectors it drives (e.g. crude oil -> Energy -> Chevron/Shell/BP)."""

    slug: str
    commodity: str
    category: str
    affects_sectors: list[str] = []
    holdings: list[EntityRef] = []  # equities in the affected sectors


def _companies_in_sector(store: KnowledgeGraphStore, sector: str) -> set[str]:
    target = sector.strip().lower()
    return {edge.source_key for edge in store.edges_by_relation("in_sector") if _sector_of(store, edge).lower() == target}


def _affected_sectors(store: KnowledgeGraphStore, commodity_key: str) -> list[str]:
    sectors: list[str] = []
    for edge in store.outgoing("Commodity", commodity_key):
        if edge.relation == "affects_sector":
            sectors.append(_str_prop(edge.properties, "sector") or _name(store, edge.target_kind, edge.target_key))
    return sectors


def list_commodities(store: KnowledgeGraphStore) -> list[CommodityRef]:
    """The commodity inventory, with the GICS sectors each drives."""
    refs: list[CommodityRef] = []
    for node in store.nodes_of_kind("Commodity"):
        refs.append(
            CommodityRef(
                slug=node.key,
                name=str(node.properties.get("name") or node.key),
                category=str(node.properties.get("category") or ""),
                symbol=_str_prop(node.properties, "symbol"),
                affects_sectors=_affected_sectors(store, node.key),
            )
        )
    return sorted(refs, key=lambda r: (r.category, r.name))


def list_debt_instruments(store: KnowledgeGraphStore) -> list[DebtRef]:
    """The debt inventory, with each instrument's issuer country."""
    refs: list[DebtRef] = []
    for node in store.nodes_of_kind("DebtInstrument"):
        refs.append(
            DebtRef(
                slug=node.key,
                name=str(node.properties.get("name") or node.key),
                debt_type=str(node.properties.get("debt_type") or ""),
                issuer_country=str(node.properties.get("issuer_country") or ""),
                symbol=_str_prop(node.properties, "symbol"),
            )
        )
    return sorted(refs, key=lambda r: (r.issuer_country, r.name))


def commodity_exposure(store: KnowledgeGraphStore, commodity: str) -> CommodityExposure:
    """Who is exposed to an event on `commodity` (slug or name): the equity
    holdings in the GICS sectors it drives. An empty result is a real answer."""
    target = commodity.strip().lower()
    node = store.get_node("Commodity", target)
    if node is None:
        for candidate in store.nodes_of_kind("Commodity"):
            if str(candidate.properties.get("name") or "").strip().lower() == target:
                node = candidate
                break
    if node is None:
        return CommodityExposure(slug=commodity, commodity=commodity, category="")
    sectors = _affected_sectors(store, node.key)
    exposed: set[str] = set()
    for sector in sectors:
        exposed |= _companies_in_sector(store, sector)
    return CommodityExposure(
        slug=node.key,
        commodity=str(node.properties.get("name") or node.key),
        category=str(node.properties.get("category") or ""),
        affects_sectors=sectors,
        holdings=[_ref(store, "Company", key) for key in sorted(exposed)],
    )


def debt_for_country(store: KnowledgeGraphStore, country: str) -> list[DebtRef]:
    """Debt instruments issued by `country` — the debt side of a country event."""
    country_key = entity_key(country)
    refs: list[DebtRef] = []
    for edge in store.incoming("Country", country_key):
        if edge.relation != "issued_by" or edge.source_kind != "DebtInstrument":
            continue
        node = store.get_node("DebtInstrument", edge.source_key)
        if node is None:
            continue
        refs.append(
            DebtRef(
                slug=node.key,
                name=str(node.properties.get("name") or node.key),
                debt_type=str(node.properties.get("debt_type") or ""),
                issuer_country=str(node.properties.get("issuer_country") or country),
                symbol=_str_prop(node.properties, "symbol"),
            )
        )
    return sorted(refs, key=lambda r: r.name)


def company_country_exposures(
    store: KnowledgeGraphStore, company_key: str
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


def co_executives(store: KnowledgeGraphStore) -> CoExecutiveResult:
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


class NetworkStep(BaseModel):
    """One hop of a co-mention evidence chain: `from_company`'s filing names
    `to_company`, cited to the filing (provenance)."""

    from_company: EntityRef
    to_company: EntityRef
    source: str | None = None  # the citing filing URL


class NetworkReach(BaseModel):
    company: EntityRef
    hops: int  # shortest co-mention distance from the queried company
    path: list[NetworkStep] = []  # one shortest evidence chain that connects them


class CompanyNetwork(BaseModel):
    """The co-mention neighbourhood of a company out to `max_hops` — the multi-hop
    "who is this connected to, and by what evidence" traversal the flat store
    couldn't do at scale. Orientation, NOT exposure magnitude: co-mention is an
    undifferentiated competitor/customer/supplier signal with no weight."""

    company: EntityRef
    max_hops: int
    reached: list[NetworkReach] = []
    note: str = "Co-mention network reach — orientation, not exposure magnitude."


def _reference_parents(
    store: KnowledgeGraphStore, source_key: str, max_hops: int
) -> dict[str, tuple[str, GraphEdge] | None]:
    """Single undirected BFS over `references` from `source_key`, returning a
    parent pointer per reachable company key (key -> (parent_key, citing edge)).
    Uses only port primitives + seq-ordered `edges_by_relation`, so the paths it
    reconstructs are identical on every backend."""
    adjacency: dict[str, list[tuple[str, GraphEdge]]] = {}
    for edge in store.edges_by_relation("references"):
        adjacency.setdefault(edge.source_key, []).append((edge.target_key, edge))
        adjacency.setdefault(edge.target_key, []).append((edge.source_key, edge))
    parents: dict[str, tuple[str, GraphEdge] | None] = {source_key: None}
    queue: deque[tuple[str, int]] = deque([(source_key, 0)])
    while queue:
        node, depth = queue.popleft()
        if depth >= max_hops:
            continue
        for neighbour, edge in adjacency.get(node, []):
            if neighbour not in parents:
                parents[neighbour] = (node, edge)
                queue.append((neighbour, depth + 1))
    return parents


def _path_from_parents(
    store: KnowledgeGraphStore, parents: dict[str, tuple[str, GraphEdge] | None], target_key: str
) -> list[NetworkStep]:
    steps: list[NetworkStep] = []
    cursor: str | None = target_key
    while cursor is not None and parents.get(cursor) is not None:
        parent_key, edge = parents[cursor]  # type: ignore[misc]
        steps.append(
            NetworkStep(
                from_company=_ref(store, "Company", parent_key),
                to_company=_ref(store, "Company", cursor),
                source=_str_prop(edge.properties, "source_uri"),
            )
        )
        cursor = parent_key
    steps.reverse()
    return steps


def company_network(
    store: KnowledgeGraphStore, company_key: str, max_hops: int = 2
) -> CompanyNetwork:
    """Companies within `max_hops` co-mention hops of `company_key`, each with a
    shortest evidence chain. The reachable set + distances come from the store's
    native multi-hop primitive (`reachable`); the display chain is reconstructed
    by a backend-agnostic BFS so it is identical whichever backend answers."""
    hops = max(1, min(max_hops, 6))  # bound the traversal; 6 is far beyond useful here
    result = CompanyNetwork(company=_ref(store, "Company", company_key), max_hops=hops)
    if store.get_node("Company", company_key) is None:
        return result
    reached = store.reachable("Company", company_key, "references", hops, direction="any")
    parents = _reference_parents(store, company_key, hops)
    records = [
        NetworkReach(
            company=_ref(store, "Company", key),
            hops=distance,
            path=_path_from_parents(store, parents, key),
        )
        for (kind, key), distance in reached.items()
        if kind == "Company"
    ]
    records.sort(key=lambda r: (r.hops, r.company.name))
    result.reached = records
    return result


# -- PEP / sanctions screening panel ------------------------------------------
# Graph vocabulary written by coruscant.screening.pipeline, mirrored here so the
# knowledge_graph layer stays independent of the screening layer.
_WATCHLIST_KIND = "WatchlistEntity"
_SCREENING_RUN_KIND = "ScreeningRun"
_SCREENING_RUN_KEY = "latest"
_PEP = "pep"
_SANCTIONED = "sanctioned"
_CANDIDATE = "screening_candidate"


class ScreeningHit(BaseModel):
    """One person ↔ watchlist edge, with the evidence needed to act or review it."""

    person: EntityRef
    listing: EntityRef
    relation: str  # "pep" | "sanctioned" | "screening_candidate"
    review_status: str
    score: float | None = None
    matched_name: str | None = None
    dataset: str | None = None
    source: str | None = None
    source_url: str | None = None
    valid_from: str | None = None
    access_tier: str = "public"


class ScreeningOverview(BaseModel):
    """The screening panel. ``connected: false`` is the honest state before a
    screen has run (no dataset wired) — never a placeholder. When it has run, a
    low or empty hit list is itself the answer: most of our people are US/UK/India
    public-company officers and Form-4 insiders, a low PEP/sanctions base rate."""

    connected: bool
    provider: str | None = None
    dataset: str | None = None
    screened: int = 0
    candidates: int = 0
    pep: int = 0
    sanctioned: int = 0
    confirmed: list[ScreeningHit] = []
    needs_review: list[ScreeningHit] = []
    note: str = (
        "Confirmed hits are corroborated beyond the name; the review queue is "
        "name-only and unconfirmed — a candidate, not a determination."
    )


def _hit(store: KnowledgeGraphStore, edge: GraphEdge) -> ScreeningHit:
    props = edge.properties
    listing_node = store.get_node(edge.target_kind, edge.target_key)
    source_url = _str_prop(listing_node.properties, "source_url") if listing_node is not None else None
    raw_score = props.get("score")
    datasets = props.get("datasets")
    return ScreeningHit(
        person=_ref(store, edge.source_kind, edge.source_key),
        listing=_ref(store, edge.target_kind, edge.target_key),
        relation=edge.relation,
        review_status=_str_prop(props, "review_status") or "",
        score=float(raw_score) if isinstance(raw_score, (int, float)) else None,
        matched_name=_str_prop(props, "matched_name"),
        dataset=", ".join(str(d) for d in datasets) if isinstance(datasets, list) and datasets else None,
        source=_source_of(props),
        source_url=source_url,
        valid_from=_str_prop(props, substrate.VALID_FROM),
        access_tier=substrate.tier_of(props).value,
    )


# -- GLEIF LEI anchoring panel --------------------------------------------------
# Graph vocabulary written by coruscant.anchoring.pipeline (mirrored here to keep
# the knowledge_graph layer independent of the anchoring layer).
_LEGAL_ENTITY_KIND = "LegalEntity"
_ANCHOR_RUN_KIND = "AnchorRun"
_ANCHOR_RUN_KEY = "latest"
_HAS_LEI = "has_lei"
_LEI_CANDIDATE = "lei_candidate"


class LeiAnchor(BaseModel):
    """One node ↔ LEI edge with the evidence to trust or review it."""

    entity: EntityRef
    lei: str
    legal_name: str | None = None
    country: str | None = None
    review_status: str = ""
    score: float | None = None
    matched_name: str | None = None
    source_url: str | None = None
    valid_from: str | None = None
    access_tier: str = "public"


class ResolutionOverview(BaseModel):
    """The identity/keys panel: how much of the graph is anchored to a stable LEI.
    ``connected: false`` before a run; an unresolved majority among the thin
    subsidiary records is the honest, expected outcome (§4.2), not a gap to hide."""

    connected: bool
    provider: str | None = None
    considered: int = 0
    resolved: int = 0
    review: int = 0
    unresolved: int = 0
    companies_resolved: int = 0
    subsidiaries_resolved: int = 0
    anchors: list[LeiAnchor] = []
    review_queue: list[LeiAnchor] = []
    note: str = "LEI is an anchor, never the primary key; unmatched nodes stay explicitly unresolved."


def _lei_anchor(store: KnowledgeGraphStore, edge: GraphEdge) -> LeiAnchor:
    props = edge.properties
    legal = store.get_node(edge.target_kind, edge.target_key)
    legal_props = legal.properties if legal is not None else {}
    raw_score = props.get("score")
    return LeiAnchor(
        entity=_ref(store, edge.source_kind, edge.source_key),
        lei=edge.target_key,
        legal_name=_str_prop(legal_props, "name"),
        country=_str_prop(legal_props, "country"),
        review_status=_str_prop(props, "review_status") or "",
        score=float(raw_score) if isinstance(raw_score, (int, float)) else None,
        matched_name=_str_prop(props, "matched_name"),
        source_url=_str_prop(legal_props, "source_url"),
        valid_from=_str_prop(props, substrate.VALID_FROM),
        access_tier=substrate.tier_of(props).value,
    )


def resolution_overview(
    store: KnowledgeGraphStore,
    *,
    clearance: substrate.AccessTier | str = substrate.AccessTier.PUBLIC,
    as_of: date | str | None = None,
) -> ResolutionOverview:
    """The GLEIF LEI-anchoring panel, tier-enforced and optionally as-of a date."""

    run = store.get_node(_ANCHOR_RUN_KIND, _ANCHOR_RUN_KEY)
    if run is None:
        return ResolutionOverview(connected=False)

    anchor_edges = store.edges_by_relation(_HAS_LEI)
    review_edges = store.edges_by_relation(_LEI_CANDIDATE)
    if as_of is not None:
        anchor_edges = substrate.as_of(anchor_edges, on=as_of)
        review_edges = substrate.as_of(review_edges, on=as_of)
    anchor_edges = substrate.visible(anchor_edges, clearance=clearance)
    review_edges = substrate.visible(review_edges, clearance=clearance)

    props = run.properties
    return ResolutionOverview(
        connected=True,
        provider=_str_prop(props, "provider"),
        considered=int(props.get("considered") or 0),
        # resolved/review reflect the tier- and as-of-filtered edges (like the
        # screening panel); considered/unresolved/breakdown are the run summary.
        resolved=len(anchor_edges),
        review=len(review_edges),
        unresolved=int(props.get("unresolved") or 0),
        companies_resolved=int(props.get("companies_resolved") or 0),
        subsidiaries_resolved=int(props.get("subsidiaries_resolved") or 0),
        anchors=[_lei_anchor(store, e) for e in anchor_edges],
        review_queue=[_lei_anchor(store, e) for e in review_edges],
    )


def screening_overview(
    store: KnowledgeGraphStore,
    *,
    clearance: substrate.AccessTier | str = substrate.AccessTier.PUBLIC,
    as_of: date | str | None = None,
) -> ScreeningOverview:
    """The PEP/sanctions screening panel, tier-enforced and optionally as-of a date.

    ``clearance`` runs the query-time access-tier policy (Invariant #7): an edge is
    only returned if the caller is cleared for its tier. ``as_of`` answers "was this
    flagged *on date D?*" via valid-time (Invariant #6)."""

    run = store.get_node(_SCREENING_RUN_KIND, _SCREENING_RUN_KEY)
    if run is None:
        return ScreeningOverview(connected=False)

    confirmed_edges = store.edges_by_relation(_PEP) + store.edges_by_relation(_SANCTIONED)
    review_edges = store.edges_by_relation(_CANDIDATE)
    if as_of is not None:
        confirmed_edges = substrate.as_of(confirmed_edges, on=as_of)
        review_edges = substrate.as_of(review_edges, on=as_of)
    confirmed_edges = substrate.visible(confirmed_edges, clearance=clearance)
    review_edges = substrate.visible(review_edges, clearance=clearance)

    props = run.properties
    return ScreeningOverview(
        connected=True,
        provider=_str_prop(props, "provider"),
        dataset=_str_prop(props, "dataset"),
        screened=int(props.get("screened") or 0),
        candidates=int(props.get("candidates") or 0),
        pep=sum(1 for e in confirmed_edges if e.relation == _PEP),
        sanctioned=sum(1 for e in confirmed_edges if e.relation == _SANCTIONED),
        confirmed=[_hit(store, e) for e in confirmed_edges],
        needs_review=[_hit(store, e) for e in review_edges],
    )


# -- Portfolio (13F fund holdings) panel ---------------------------------------
# Graph vocabulary written by coruscant.portfolio.holdings (mirrored here).
_FUND_KIND = "Fund"
_HOLDS = "holds"


class FundRef(BaseModel):
    key: str
    name: str
    cik: str | None = None
    period: str | None = None
    positions: int = 0  # line items on the 13F
    resolved: int = 0  # distinct holdings in our coverage
    out_of_coverage: int = 0


class FundHoldingView(BaseModel):
    company: EntityRef
    value: int = 0  # as reported on the 13F
    shares: int | None = None
    cusip: str | None = None
    score: float | None = None
    valid_from: str | None = None
    source: str | None = None
    access_tier: str = "public"


class FundHoldings(BaseModel):
    """A fund's holdings that fall inside our coverage — the book an event is
    traced into. Out-of-coverage positions are counted, not fabricated."""

    fund: FundRef
    holdings: list[FundHoldingView] = []
    note: str = "13F holdings resolved to covered companies; out-of-coverage positions are counted only."


def _fund_ref(store: KnowledgeGraphStore, node_key: str) -> FundRef:
    node = store.get_node(_FUND_KIND, node_key)
    props = node.properties if node is not None else {}
    return FundRef(
        key=node_key, name=_name(store, _FUND_KIND, node_key),
        cik=_str_prop(props, "cik"), period=_str_prop(props, "period"),
        positions=int(props.get("positions") or 0),
        resolved=int(props.get("resolved") or 0),
        out_of_coverage=int(props.get("out_of_coverage") or 0),
    )


def list_funds(store: KnowledgeGraphStore) -> list[FundRef]:
    """Every fund whose 13F has been ingested, by holdings-in-coverage, descending."""
    funds = [_fund_ref(store, node.key) for node in store.nodes_of_kind(_FUND_KIND)]
    return sorted(funds, key=lambda f: (-f.resolved, f.name))


def fund_holdings(
    store: KnowledgeGraphStore,
    fund_key: str,
    *,
    clearance: substrate.AccessTier | str = substrate.AccessTier.PUBLIC,
    as_of: date | str | None = None,
) -> FundHoldings | None:
    """A fund's covered holdings, tier-enforced and optionally as-of a date."""
    if store.get_node(_FUND_KIND, fund_key) is None:
        return None
    edges = [e for e in store.outgoing(_FUND_KIND, fund_key) if e.relation == _HOLDS]
    if as_of is not None:
        edges = substrate.as_of(edges, on=as_of)
    edges = substrate.visible(edges, clearance=clearance)

    def _int(value: object) -> int:
        return value if isinstance(value, int) else 0

    holdings: list[FundHoldingView] = []
    for edge in edges:
        props = edge.properties
        raw_score = props.get("score")
        shares = props.get("shares")
        holdings.append(
            FundHoldingView(
                company=_ref(store, edge.target_kind, edge.target_key),
                value=_int(props.get("value")),
                shares=shares if isinstance(shares, int) else None,
                cusip=_str_prop(props, "cusip"),
                score=float(raw_score) if isinstance(raw_score, (int, float)) else None,
                valid_from=_str_prop(props, substrate.VALID_FROM),
                source=_source_of(props),
                access_tier=substrate.tier_of(props).value,
            )
        )
    holdings.sort(key=lambda h: (-h.value, h.company.name))
    return FundHoldings(fund=_fund_ref(store, fund_key), holdings=holdings)


# -- Fund-scoped exposure (the north-star query) -------------------------------
# "An event happens somewhere — does it touch THIS fund's book, and how?"
# Reuses the pathway exposure queries and intersects with a fund's holds edges,
# attaching the held value so the answer carries in-book magnitude (orientation,
# not a P&L estimate).
_EXPOSURE_PATHWAYS = ("sector", "jurisdiction", "market_tier", "commodity", "country")


class PortfolioExposureHit(BaseModel):
    company: EntityRef
    value: int = 0  # the fund's holding value in this exposed company


class PortfolioExposure(BaseModel):
    fund: FundRef
    pathway: str  # one of _EXPOSURE_PATHWAYS
    event: str  # the queried term (a sector, country, commodity …)
    exposed: list[PortfolioExposureHit] = []
    exposed_value: int = 0  # summed value of exposed holdings
    total_value: int = 0  # the fund's total covered value
    holdings_in_coverage: int = 0
    note: str = "Which of this fund's covered holdings the event touches — orientation, not a P&L estimate."


def _exposed_company_keys(store: KnowledgeGraphStore, pathway: str, term: str) -> list[str]:
    if pathway == "sector":
        return [r.key for r in sector_exposure(store, term).direct]
    if pathway == "market_tier":
        return [r.key for r in market_tier_exposure(store, term).direct]
    if pathway == "commodity":
        return [r.key for r in commodity_exposure(store, term).holdings]
    if pathway == "jurisdiction":
        return [f.company.key for f in jurisdiction_exposure(store, term).direct]
    if pathway == "country":
        return [r.key for r in exposure_to_country(store, term).direct]
    return []


def portfolio_exposure(
    store: KnowledgeGraphStore,
    fund_key: str,
    *,
    pathway: str,
    term: str,
    clearance: substrate.AccessTier | str = substrate.AccessTier.PUBLIC,
    as_of: date | str | None = None,
) -> PortfolioExposure | None:
    """The exposed subset of a fund's holdings for an event on ``pathway``/``term``."""

    holdings = fund_holdings(store, fund_key, clearance=clearance, as_of=as_of)
    if holdings is None:
        return None
    value_by = {h.company.key: h.value for h in holdings.holdings}
    exposed_keys = _exposed_company_keys(store, pathway, term) if pathway in _EXPOSURE_PATHWAYS else []
    hits: list[PortfolioExposureHit] = []
    seen: set[str] = set()
    for key in exposed_keys:
        if key in value_by and key not in seen:
            seen.add(key)
            hits.append(PortfolioExposureHit(company=_ref(store, "Company", key), value=value_by[key]))
    hits.sort(key=lambda h: (-h.value, h.company.name))
    return PortfolioExposure(
        fund=holdings.fund, pathway=pathway, event=term, exposed=hits,
        exposed_value=sum(h.value for h in hits), total_value=sum(value_by.values()),
        holdings_in_coverage=len(value_by),
    )


class ProfileBucket(BaseModel):
    label: str
    value: int = 0  # summed holding value in this bucket
    companies: int = 0


class PortfolioProfile(BaseModel):
    """The shape of a fund's covered book — value-weighted by GICS sector and MSCI
    market tier — so a manager sees what an event *could* touch before it happens."""

    fund: FundRef
    total_value: int = 0
    by_sector: list[ProfileBucket] = []
    by_market_tier: list[ProfileBucket] = []


def _buckets(val: dict[str, int], cos: dict[str, set[str]]) -> list[ProfileBucket]:
    out = [ProfileBucket(label=label, value=val[label], companies=len(cos[label])) for label in val]
    out.sort(key=lambda b: (-b.value, b.label))
    return out


def portfolio_profile(
    store: KnowledgeGraphStore,
    fund_key: str,
    *,
    clearance: substrate.AccessTier | str = substrate.AccessTier.PUBLIC,
    as_of: date | str | None = None,
) -> PortfolioProfile | None:
    """A fund's book broken down by sector and market tier, value-weighted."""

    holdings = fund_holdings(store, fund_key, clearance=clearance, as_of=as_of)
    if holdings is None:
        return None
    value_by = {h.company.key: h.value for h in holdings.holdings}
    sector_val: dict[str, int] = {}
    sector_cos: dict[str, set[str]] = {}
    tier_val: dict[str, int] = {}
    tier_cos: dict[str, set[str]] = {}
    for key, value in value_by.items():
        for edge in store.outgoing("Company", key):
            if edge.relation == "in_sector":
                sector = _sector_of(store, edge)
                sector_val[sector] = sector_val.get(sector, 0) + value
                sector_cos.setdefault(sector, set()).add(key)
                break
        for edge in store.outgoing("Company", key):
            if edge.relation == "in_market_tier":
                tier = _tier_code(store, edge.target_key)
                tier_val[tier] = tier_val.get(tier, 0) + value
                tier_cos.setdefault(tier, set()).add(key)
                break
    return PortfolioProfile(
        fund=holdings.fund, total_value=sum(value_by.values()),
        by_sector=_buckets(sector_val, sector_cos),
        by_market_tier=_buckets(tier_val, tier_cos),
    )


# -- Whole-exchange coverage panel ---------------------------------------------
# "How much of the listed universe can a portfolio resolve against?" Counts are
# read live off the Company nodes (honest — they reflect the actual graph), with
# the per-market CoverageRun node supplying provider + last-run + what was
# excluded upstream (blank/OTC listings). Graph vocabulary written by
# coruscant.coverage.pipeline, mirrored here to keep this layer independent.
_COVERAGE_RUN_KIND = "CoverageRun"
_COMPANY_KIND = "Company"
_MARKET = "market"
_EXCHANGE = "exchange"
_IN_UNIVERSE = "in_universe"


class CoverageMarketCount(BaseModel):
    market: str
    companies: int  # total Company nodes tagged to this market
    in_universe: int  # of those, part of an ingested exchange universe
    provider: str | None = None
    considered: int = 0  # issuers the last run listed
    created: int = 0  # new surrogate nodes on the last run
    enriched: int = 0  # existing nodes enriched (external-key match) on the last run
    excluded: dict[str, int] = {}  # filtered upstream (blank/OTC), by reason
    indices: dict[str, int] = {}  # index name → constituents linked (Nifty/Sensex/FTSE)
    observed_at: str | None = None


class CoverageExchangeCount(BaseModel):
    exchange: str
    companies: int


class CoverageOverview(BaseModel):
    """The coverage panel: the size and shape of the resolvable universe.
    ``connected: false`` before any coverage run — the honest empty state."""

    connected: bool
    total_companies: int = 0
    in_universe: int = 0  # companies carrying an exchange-universe anchor
    curated: int = 0  # companies without one (curated/deep-ingested only)
    by_market: list[CoverageMarketCount] = []
    by_exchange: list[CoverageExchangeCount] = []
    note: str = (
        "Universe nodes are lightweight (identity + exchange); GICS is resolved "
        "only where curated, else labelled unresolved — never fabricated."
    )


def coverage_overview(store: KnowledgeGraphStore) -> CoverageOverview:
    """The whole-exchange coverage panel, counted live off the graph."""

    runs = {
        str(n.properties.get(_MARKET) or n.key).upper(): n.properties
        for n in store.nodes_of_kind(_COVERAGE_RUN_KIND)
    }
    companies = store.nodes_of_kind(_COMPANY_KIND)
    if not runs and not any(c.properties.get(_IN_UNIVERSE) for c in companies):
        return CoverageOverview(connected=False, total_companies=len(companies))

    market_total: dict[str, int] = {}
    market_universe: dict[str, int] = {}
    exchange_count: dict[str, int] = {}
    in_universe = 0
    for node in companies:
        props = node.properties
        market = props.get(_MARKET)
        if isinstance(market, str) and market:
            market_total[market] = market_total.get(market, 0) + 1
        if props.get(_IN_UNIVERSE):
            in_universe += 1
            if isinstance(market, str) and market:
                market_universe[market] = market_universe.get(market, 0) + 1
            exch = props.get(_EXCHANGE)
            if isinstance(exch, str) and exch:
                exchange_count[exch] = exchange_count.get(exch, 0) + 1

    def _market(m: str) -> CoverageMarketCount:
        run = runs.get(m, {})
        excluded = run.get("excluded")
        indices = run.get("indices")
        return CoverageMarketCount(
            market=m, companies=market_total.get(m, 0),
            in_universe=market_universe.get(m, 0),
            provider=_str_prop(run, "provider"),
            considered=int(run.get("considered") or 0),
            created=int(run.get("created") or 0),
            enriched=int(run.get("enriched") or 0),
            excluded={str(k): int(v) for k, v in excluded.items()} if isinstance(excluded, dict) else {},
            indices={str(k): int(v) for k, v in indices.items()} if isinstance(indices, dict) else {},
            observed_at=_str_prop(run, "observed_at"),
        )

    markets = sorted(set(market_total) | set(runs))
    by_exchange = [CoverageExchangeCount(exchange=e, companies=n) for e, n in exchange_count.items()]
    by_exchange.sort(key=lambda c: (-c.companies, c.exchange))
    return CoverageOverview(
        connected=True,
        total_companies=len(companies),
        in_universe=in_universe,
        curated=len(companies) - in_universe,
        by_market=[_market(m) for m in markets],
        by_exchange=by_exchange,
    )


# -- Ownership substrate panel -------------------------------------------------
# The three DISTINCT ownership edge types, never conflated (architecture §2.4).
# Access-tier aware: a public caller does not see beneficial-owner edges — they are
# counted as ``restricted`` so their existence is transparent without exposing them.
_OWNERSHIP_RUN_KIND = "OwnershipRun"
_OWNERSHIP_RELATIONS = ("owns", "beneficial_owner_of", "consolidates")


class OwnershipOverview(BaseModel):
    """The ownership panel: how much declared ownership / beneficial ownership /
    accounting consolidation the graph holds, at the caller's clearance.
    ``connected: false`` before any ownership run — the honest empty state."""

    connected: bool
    owns: int = 0  # declared %-shareholding edges visible to the caller
    beneficial_owner_of: int = 0  # beneficial-owner edges visible to the caller
    consolidates: int = 0  # accounting-consolidation edges visible to the caller
    restricted: int = 0  # edges withheld by access tier (their existence, not content)
    subjects_unresolved: int = 0  # last run: subjects with no anchored node
    holders_unresolved: int = 0  # last run: holders (people/entities) not yet resolved
    provider: str | None = None
    observed_at: str | None = None
    market: str | None = None
    note: str = (
        "Declared ownership, beneficial ownership, and accounting consolidation are "
        "distinct edge types and never equated; percentages appear only where sourced."
    )


class OwnerEdge(BaseModel):
    """One ownership statement about a company, with its basis and evidence."""

    holder_kind: str
    holder_key: str
    holder_name: str | None = None
    relation: str  # owns | beneficial_owner_of | consolidates
    basis: str | None = None
    percentage: float | None = None
    percentage_band: str | None = None
    interest: str | None = None
    source: str | None = None
    source_url: str | None = None
    access_tier: str | None = None
    valid_from: str | None = None
    valid_to: str | None = None
    holder_resolved: bool | None = None


class CompanyOwners(BaseModel):
    """The ownership statements pointing at one company, access-tier filtered.
    ``restricted`` counts edges the caller may not see (transparency without leak)."""

    company_key: str
    connected: bool = False
    owners: list[OwnerEdge] = []
    restricted: int = 0
    provider: str | None = None
    observed_at: str | None = None
    market: str | None = None


def ownership_overview(
    store: KnowledgeGraphStore,
    *,
    clearance: substrate.AccessTier | str = substrate.AccessTier.PUBLIC,
) -> OwnershipOverview:
    """The ownership panel, counted live off the graph at ``clearance``."""

    run = next(iter(store.nodes_of_kind(_OWNERSHIP_RUN_KIND)), None)
    all_edges = [e for rel in _OWNERSHIP_RELATIONS for e in store.edges_by_relation(rel)]
    if not all_edges and run is None:
        return OwnershipOverview(connected=False)

    visible = substrate.visible(all_edges, clearance=clearance)
    counts = {rel: 0 for rel in _OWNERSHIP_RELATIONS}
    for edge in visible:
        counts[edge.relation] = counts.get(edge.relation, 0) + 1
    props = run.properties if run is not None else {}
    return OwnershipOverview(
        connected=True,
        owns=counts["owns"],
        beneficial_owner_of=counts["beneficial_owner_of"],
        consolidates=counts["consolidates"],
        restricted=len(all_edges) - len(visible),
        subjects_unresolved=int(props.get("subjects_unresolved") or 0),
        holders_unresolved=int(props.get("holders_unresolved") or 0),
        provider=_str_prop(props, "provider"),
        observed_at=_str_prop(props, "observed_at"),
        market=_str_prop(props, "market"),
    )


def company_owners(
    store: KnowledgeGraphStore,
    company_key: str,
    *,
    clearance: substrate.AccessTier | str = substrate.AccessTier.PUBLIC,
    as_of: date | str | None = None,
) -> CompanyOwners:
    """Every ownership/control statement pointing *at* ``company_key`` (incoming
    ``owns`` / ``beneficial_owner_of`` / ``consolidates`` edges), access-tier
    filtered and optionally as-of a date. Withheld edges are counted, not shown."""

    incoming = [
        e for e in store.incoming("Company", company_key)
        if e.relation in _OWNERSHIP_RELATIONS
    ]
    if as_of is not None:
        incoming = substrate.as_of(incoming, on=as_of)
    visible = substrate.visible(incoming, clearance=clearance)
    owners = [
        OwnerEdge(
            holder_kind=e.source_kind, holder_key=e.source_key,
            holder_name=_str_prop(e.properties, "holder_name"),
            relation=e.relation, basis=_str_prop(e.properties, "basis"),
            percentage=(
                float(e.properties["percentage"])
                if isinstance(e.properties.get("percentage"), (int, float)) else None
            ),
            percentage_band=_str_prop(e.properties, "percentage_band"),
            interest=_str_prop(e.properties, "interest"),
            source=_str_prop(e.properties, substrate.SOURCE),
            source_url=_str_prop(e.properties, "source_url"),
            access_tier=substrate.tier_of(e.properties).value,
            valid_from=_str_prop(e.properties, substrate.VALID_FROM),
            valid_to=_str_prop(e.properties, substrate.VALID_TO),
            holder_resolved=(
                bool(e.properties["holder_resolved"])
                if isinstance(e.properties.get("holder_resolved"), bool) else None
            ),
        )
        for e in visible
    ]
    run = next(iter(store.nodes_of_kind(_OWNERSHIP_RUN_KIND)), None)
    props = run.properties if run is not None else {}
    return CompanyOwners(
        company_key=company_key,
        connected=bool(incoming),
        owners=owners,
        restricted=len(incoming) - len(visible),
        provider=_str_prop(props, "provider"),
        observed_at=_str_prop(props, "observed_at"),
        market=_str_prop(props, "market"),
    )
