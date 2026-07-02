"""Deterministic relationship extraction from the ingested corpus.

The curated entity graph (``entities.py``) is hand-authored and does not scale.
These edges are instead *derived at scale* from the documents and structured
metadata the platform already ingested — and, like the curated ones, every edge
carries provenance back to the source it came from. This is what lets a larger
company set reveal cross-company structure (companies that name one another,
shared sectors) without anyone hand-writing relationships.

Two deterministic signals, both auditable:
  * ``in_sector``  — Company → Industry, from the SEC SIC classification.
  * ``references`` — Company A → Company B, when A's filing names B. Provenance
    is the filing's ``source_uri``. Precision-first: only distinctive, multi-word
    or unambiguous single-word names are matched, so a co-mention is real, never
    a coincidental common word (a fabricated edge would violate the platform's
    first principle).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from coruscant.common.config import CompanyConfig, InstrumentsConfig
from coruscant.common.types import GraphEdge, GraphNode, NormalizedDocument
from coruscant.exposure.entities import entity_key
from coruscant.knowledge_graph.memory import InMemoryKnowledgeGraphStore
from coruscant.exposure.taxonomy import (
    company_gics,
    country_msci_tier,
    msci_tier_label,
)

_SECTOR_PROV = "sec-metadata"
_GICS_PROV = "gics-curated"
_MARKET_TIER_PROV = "msci-classification"
_COMMODITY_PROV = "commodity-inventory"
_COMMODITY_SECTOR_PROV = "commodity-sector-linkage"
_DEBT_PROV = "debt-inventory"
_COMENTION_PROV = "sec-co-mention"
_SUBSIDIARY_PROV = "sec-exhibit21"
_OFFICER_PROV = "sec-10k-officers"
_DIRECTOR_PROV = "sec-10k-signatures"
_HOLDING_PROV = "sec-form4"

# Pure legal-form tokens stripped to get a company's distinctive core name. We
# deliberately KEEP words like "companies" / "group" — they make a name precise
# ("travelers companies", "goldman sachs group") rather than collapsing it to an
# ambiguous common word ("travelers").
_SUFFIXES = {
    "corp", "corporation", "inc", "incorporated", "co", "com",
    "plc", "ltd", "lp", "sa", "ag", "nv",
}
# Single-word cores that are also common English words, or that collide across
# distinct companies — excluded from the gazetteer so a coincidental word never
# asserts a co-mention. A fabricated edge would violate the platform's first
# principle. "shell" → "shell company/corporation"; "prudential" → the UK
# Prudential plc vs the US Prudential Financial are different firms; "salesforce"
# → a company's "sales force" / "salesforce training" (verified to false-positive
# in AstraZeneca, BAT, and Prudential filings).
_AMBIGUOUS = {"visa", "shell", "prudential", "salesforce"}

# Specific (source, target) co-mention pairs verified to be false positives by
# reading the matched sentence: the distinctive name matched a non-company use.
# Each carries its reason; this is an evidence-based exclusion, the opposite of
# fabrication. (See the UK/US cross-border verification, 2026-06.)
_FALSE_COMENTIONS: set[tuple[str, str]] = {
    ("deo", "aapl"),  # Diageo: "Captain Morgan Sliced Apple" — the fruit/flavour, not Apple Inc.
    ("shel", "amzn"),  # Shell: "the Peruvian Amazon" — the rainforest, not Amazon.com
    ("bti", "mrk"),  # BAT: "Merck Group" = Merck KGaA (Germany), not Merck & Co (US)
    ("hdb", "aapl"),  # HDFC Bank: a director's prior employer "Apple Industries Ltd" (India), not Apple Inc.
    ("ytra", "aapl"),  # Yatra: shareholder "Apple Orange LLC" (a fund), not Apple Inc.
}


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _core_name(name: str) -> str:
    """Distinctive core of a company name, legal suffixes removed."""
    tokens = [t for t in _norm(name).split() if t]
    while tokens and tokens[-1] in _SUFFIXES:
        tokens.pop()
    if tokens and tokens[0] == "the":
        tokens = tokens[1:]
    return " ".join(tokens)


def project_company_nodes(store: InMemoryKnowledgeGraphStore, companies: list[CompanyConfig]) -> None:
    """Upsert each tracked company node with its authoritative display name.

    The per-document projector keys company nodes by slug and, when a live filing's
    metadata carries no clean company name, falls back to the slug. This restores
    the real name (and industry) so the graph reads as companies, not tickers.
    """
    for company in companies:
        gics = company_gics(company.slug)
        tier = country_msci_tier(company.country)
        properties: dict[str, object] = {
            "name": company.name,
            "source": "tracked",
            "industry": company.industry,
            "cik": company.cik,
        }
        # Allocator-view attributes so the company node reads in GICS/MSCI terms
        # (used by the Atlas and exposure surfaces) without losing the raw SIC. The
        # 8-digit code is the canonical anchor for joining to MSCI sector indexes.
        if gics is not None:
            properties["gics_sector"] = gics.sector
            properties["gics_sub_industry"] = gics.sub_industry
            properties["gics_code"] = gics.code
        if tier is not None:
            properties["market_tier"] = tier
        store.upsert_node(GraphNode(kind="Company", key=company.slug, properties=properties))


def project_sector_edges(store: InMemoryKnowledgeGraphStore, companies: list[CompanyConfig]) -> int:
    """Company -in_sector-> Industry, tagged with the full curated GICS path.

    The target ``Industry`` node is the company's GICS *sub-industry* (the most
    specific level); the full path — sector / industry group / industry /
    sub-industry + the 8-digit code — rides both the node and the edge. That lets
    the exposure engine match an event at *any* level (sector, group, industry or
    sub-industry) off one edge. An uncurated company falls back to its raw SIC
    ``industry`` so an edge is never dropped or a sector invented; the raw SIC
    label always rides the edge as ``sic_industry`` for provenance.
    """
    count = 0
    for company in companies:
        gics = company_gics(company.slug)
        sic = (company.industry or "").strip()
        if gics is not None:
            node_name, prov, taxonomy = gics.sub_industry, _GICS_PROV, "GICS"
            path: dict[str, object] = {
                "code": gics.code,
                "sector": gics.sector,
                "industry_group": gics.industry_group,
                "industry": gics.industry,
                "sub_industry": gics.sub_industry,
            }
        elif sic:
            # No curated GICS path: the raw SIC label is both the node and the
            # (single-level) "sector" the headline query groups by.
            node_name, prov, taxonomy = sic, _SECTOR_PROV, "SIC"
            path = {"sector": sic}
        else:
            continue
        key = entity_key(node_name)
        if store.get_node("Industry", key) is None:
            store.upsert_node(
                GraphNode(
                    kind="Industry",
                    key=key,
                    properties={"name": node_name, "source": prov, "taxonomy": taxonomy, **path},
                )
            )
        properties: dict[str, object] = {"source": prov, "company_slug": company.slug, **path}
        if sic:
            properties["sic_industry"] = sic
        store.upsert_edge(
            GraphEdge(
                source_kind="Company",
                source_key=company.slug,
                relation="in_sector",
                target_kind="Industry",
                target_key=key,
                properties=properties,
            )
        )
        count += 1
    return count


def project_market_tier_edges(store: InMemoryKnowledgeGraphStore, companies: list[CompanyConfig]) -> int:
    """Company -in_market_tier-> MarketTier (MSCI Developed/Emerging/Frontier).

    Keyed on the company's listing country; the evidence is the company's
    domicile plus MSCI's public market classification. This is the substrate for
    the market-tier exposure pathway ("you're 15% EM, heavy India")."""
    count = 0
    for company in companies:
        tier = country_msci_tier(company.country)
        if tier is None:
            continue
        key = entity_key(tier)  # "dm" / "em" / "fm"
        if store.get_node("MarketTier", key) is None:
            store.upsert_node(
                GraphNode(
                    kind="MarketTier",
                    key=key,
                    properties={"name": msci_tier_label(tier), "code": tier, "source": _MARKET_TIER_PROV},
                )
            )
        store.upsert_edge(
            GraphEdge(
                source_kind="Company",
                source_key=company.slug,
                relation="in_market_tier",
                target_kind="MarketTier",
                target_key=key,
                properties={
                    "source": _MARKET_TIER_PROV,
                    "company_slug": company.slug,
                    "country": company.country,
                    "tier": tier,
                },
            )
        )
        count += 1
    return count


def _gazetteer(companies: list[CompanyConfig]) -> list[tuple[re.Pattern[str], str, str]]:
    """(word-boundary pattern, target slug, display name) for co-mention matching."""
    patterns: list[tuple[re.Pattern[str], str, str]] = []
    for company in companies:
        core = _core_name(company.name)
        if len(core) < 4 or core in _AMBIGUOUS:
            continue
        patterns.append((re.compile(rf"\b{re.escape(core)}\b"), company.slug, company.name))
    return patterns


def project_cross_company_references(
    store: InMemoryKnowledgeGraphStore,
    companies: list[CompanyConfig],
    documents: list[NormalizedDocument],
) -> int:
    """Company A -references-> Company B when A's filing names B (deduped, with provenance)."""
    gazetteer = _gazetteer(companies)
    docs_by_slug: dict[str, list[NormalizedDocument]] = {}
    for doc in documents:
        slug = str(doc.metadata.get("company_slug") or "")
        if slug:
            docs_by_slug.setdefault(slug, []).append(doc)

    count = 0
    seen: set[tuple[str, str]] = set()
    for company in companies:
        for doc in docs_by_slug.get(company.slug, []):
            haystack = _norm(
                " ".join(str(s.get("content") or "") for s in doc.sections) + " " + (doc.title or "")
            )
            for pattern, target_slug, target_name in gazetteer:
                if target_slug == company.slug:
                    continue
                pair = (company.slug, target_slug)
                if pair in seen or pair in _FALSE_COMENTIONS:
                    continue
                if pattern.search(haystack):
                    seen.add(pair)
                    store.upsert_edge(
                        GraphEdge(
                            source_kind="Company",
                            source_key=company.slug,
                            relation="references",
                            target_kind="Company",
                            target_key=target_slug,
                            properties={
                                "source": _COMENTION_PROV,
                                "company_slug": company.slug,
                                "source_uri": doc.source_uri,
                                "entity_name": target_name,
                            },
                        )
                    )
                    count += 1
    return count


def project_subsidiary_edges(
    store: InMemoryKnowledgeGraphStore,
    companies: list[CompanyConfig],
    documents: list[NormalizedDocument],
) -> int:
    """Company -has_subsidiary-> Subsidiary, from each filing's parsed Exhibit 21.

    This is the platform's first *declared* ownership edge (vs the inferred control
    proxies). Provenance is the Exhibit 21 filing; the registrant's self-entry is
    filtered out by core-name match.
    """
    docs_by_slug: dict[str, list[NormalizedDocument]] = {}
    for doc in documents:
        slug = str(doc.metadata.get("company_slug") or "")
        if slug:
            docs_by_slug.setdefault(slug, []).append(doc)

    count = 0
    for company in companies:
        parent_core = _core_name(company.name)
        seen: set[str] = set()
        for doc in docs_by_slug.get(company.slug, []):
            subs = doc.metadata.get("subsidiaries")
            if not isinstance(subs, list):
                continue
            for sub in subs:
                if not isinstance(sub, dict):
                    continue
                name = str(sub.get("name") or "").strip()
                if not name:
                    continue
                norm = _norm(name)
                if parent_core and parent_core in norm:
                    continue
                key = entity_key(name)
                if key in seen:
                    continue
                seen.add(key)
                jurisdiction = str(sub.get("jurisdiction") or "").strip()
                if store.get_node("Subsidiary", key) is None:
                    store.upsert_node(
                        GraphNode(
                            kind="Subsidiary",
                            key=key,
                            properties={"name": name, "jurisdiction": jurisdiction, "source": _SUBSIDIARY_PROV},
                        )
                    )
                store.upsert_edge(
                    GraphEdge(
                        source_kind="Company",
                        source_key=company.slug,
                        relation="has_subsidiary",
                        target_kind="Subsidiary",
                        target_key=key,
                        properties={
                            "source": _SUBSIDIARY_PROV,
                            "company_slug": company.slug,
                            "source_uri": doc.source_uri,
                            "jurisdiction": jurisdiction,
                        },
                    )
                )
                count += 1
    return count


def project_people_edges(
    store: InMemoryKnowledgeGraphStore,
    companies: list[CompanyConfig],
    documents: list[NormalizedDocument],
) -> int:
    """Company -employs-> Person (officers) and -board_member-> Person (directors).

    The people layer. Two deterministic sources, both in the 10-K:
      - the executive-officers table (``parse_officers``) → officers, and
      - the signature page (``parse_signers``) → officers + every director.
    The signature page closes the coverage gap (filings that incorporate Item 10
    by reference still sign) and surfaces directors, so a person who signs two
    companies' 10-Ks becomes a *bridge* — the board-interlock network (e.g. Tim
    Cook on Apple + Nike, Alex Gorsky on Apple + JPMorgan). Provenance is the
    filing; an officer classification always wins over a director one for the same
    person at the same company.
    """
    from coruscant.connectors.sec_edgar import parse_officers, parse_signers  # local: avoid import cycle

    docs_by_slug: dict[str, list[NormalizedDocument]] = {}
    for doc in documents:
        slug = str(doc.metadata.get("company_slug") or "")
        if slug:
            docs_by_slug.setdefault(slug, []).append(doc)

    count = 0
    for company in companies:
        # Collect one record per person: key -> (name, relation, role, source_uri).
        people: dict[str, tuple[str, str, str, str]] = {}

        def record(name: str, relation: str, role: str, uri: str) -> None:
            name = name.strip()
            if not name:
                return
            key = entity_key(name)
            existing = people.get(key)
            # An officer (employs) edge wins over a board_member one for the same person.
            if existing is not None and not (existing[1] == "board_member" and relation == "employs"):
                return
            people[key] = (name, relation, role.strip(), uri)

        for doc in docs_by_slug.get(company.slug, []):
            text = "\n".join(str(s.get("content") or "") for s in doc.sections)
            for officer in parse_officers(text):
                record(officer["name"], "employs", officer["role"], doc.source_uri)
            for signer in parse_signers(text):
                relation = "employs" if signer["kind"] == "officer" else "board_member"
                record(signer["name"], relation, signer["role"], doc.source_uri)

        for key, (name, relation, role, uri) in people.items():
            prov = _OFFICER_PROV if relation == "employs" else _DIRECTOR_PROV
            if store.get_node("Person", key) is None:
                store.upsert_node(
                    GraphNode(kind="Person", key=key, properties={"name": name, "source": prov})
                )
            store.upsert_edge(
                GraphEdge(
                    source_kind="Company",
                    source_key=company.slug,
                    relation=relation,
                    target_kind="Person",
                    target_key=key,
                    properties={
                        "source": prov,
                        "company_slug": company.slug,
                        "role": role,
                        "source_uri": uri,
                    },
                )
            )
            count += 1
    return count


def project_instrument_edges(
    store: InMemoryKnowledgeGraphStore, instruments: InstrumentsConfig
) -> dict[str, int]:
    """Project the non-equity inventory so the exposure engine reaches it.

    Commodity -affects_sector-> Sector links a commodity to the GICS sectors it
    drives (a commodity event then reaches the equity holdings in those sectors).
    DebtInstrument -issued_by-> Country links debt to its issuer (a country event
    then reaches its sovereign/corporate debt). Every node/edge carries its
    provenance, distinct from the SEC-derived edges."""
    commodities = 0
    for commodity in instruments.commodities:
        store.upsert_node(
            GraphNode(
                kind="Commodity",
                key=commodity.slug,
                properties={
                    "name": commodity.name,
                    "category": commodity.category,
                    "symbol": commodity.symbol,
                    "source": _COMMODITY_PROV,
                },
            )
        )
        for sector in commodity.affects_sectors:
            sector_key = entity_key(sector)
            if store.get_node("Sector", sector_key) is None:
                store.upsert_node(
                    GraphNode(kind="Sector", key=sector_key, properties={"name": sector, "source": _COMMODITY_SECTOR_PROV})
                )
            store.upsert_edge(
                GraphEdge(
                    source_kind="Commodity",
                    source_key=commodity.slug,
                    relation="affects_sector",
                    target_kind="Sector",
                    target_key=sector_key,
                    properties={"source": _COMMODITY_SECTOR_PROV, "commodity": commodity.name, "sector": sector},
                )
            )
        commodities += 1

    debt = 0
    for instrument in instruments.debt:
        store.upsert_node(
            GraphNode(
                kind="DebtInstrument",
                key=instrument.slug,
                properties={
                    "name": instrument.name,
                    "debt_type": instrument.debt_type,
                    "issuer_country": instrument.issuer_country,
                    "symbol": instrument.symbol,
                    "source": _DEBT_PROV,
                },
            )
        )
        country_key = entity_key(instrument.issuer_country)
        if store.get_node("Country", country_key) is None:
            store.upsert_node(
                GraphNode(kind="Country", key=country_key, properties={"name": instrument.issuer_country, "source": _DEBT_PROV})
            )
        store.upsert_edge(
            GraphEdge(
                source_kind="DebtInstrument",
                source_key=instrument.slug,
                relation="issued_by",
                target_kind="Country",
                target_key=country_key,
                properties={"source": _DEBT_PROV, "debt_type": instrument.debt_type, "issuer_country": instrument.issuer_country},
            )
        )
        debt += 1
    return {"commodities": commodities, "debt": debt}


def project_holdings_edges(
    store: InMemoryKnowledgeGraphStore, company_slug: str, holdings: list[dict[str, object]]
) -> int:
    """Company -insider_holding-> Person {shares}, from parsed Form 4 filings.

    The holdings layer. ``holdings`` is the output of
    ``sec_edgar.fetch_recent_form4_holdings`` (network); kept separate from the
    offline projectors so this stays a pure, testable transform. People are keyed
    by name, so an insider who is already an officer/director (parsed from the
    10-K) is enriched in place rather than duplicated.
    """
    count = 0
    for holding in holdings:
        owner = str(holding.get("owner") or "").strip()
        shares = holding.get("shares")
        if not owner or not isinstance(shares, int):
            continue
        key = entity_key(owner)
        if store.get_node("Person", key) is None:
            store.upsert_node(GraphNode(kind="Person", key=key, properties={"name": owner, "source": _HOLDING_PROV}))
        role = (
            str(holding.get("title") or "").strip()
            or ("Director" if holding.get("is_director") else "")
            or ("10% owner" if holding.get("is_ten_percent") else "")
            or "Insider"
        )
        store.upsert_edge(
            GraphEdge(
                source_kind="Company",
                source_key=company_slug,
                relation="insider_holding",
                target_kind="Person",
                target_key=key,
                properties={"source": _HOLDING_PROV, "company_slug": company_slug, "role": role, "shares": shares},
            )
        )
        count += 1
    return count


def load_normalized_documents(data_dir: Path) -> list[NormalizedDocument]:
    """Load every persisted normalized document under ``{data_dir}/normalized``."""
    root = Path(data_dir) / "normalized"
    docs: list[NormalizedDocument] = []
    if not root.exists():
        return docs
    for path in sorted(root.rglob("*.json")):
        try:
            docs.append(NormalizedDocument.model_validate_json(path.read_text()))
        except (ValueError, OSError, json.JSONDecodeError):
            continue
    return docs


def extract_relationships(
    store: InMemoryKnowledgeGraphStore,
    companies: list[CompanyConfig],
    data_dir: Path,
    instruments: InstrumentsConfig | None = None,
) -> dict[str, int]:
    """Run the deterministic extractors and project their edges. Returns counts."""
    documents = load_normalized_documents(data_dir)
    project_company_nodes(store, companies)
    sector = project_sector_edges(store, companies)
    market_tiers = project_market_tier_edges(store, companies)
    references = project_cross_company_references(store, companies, documents)
    subsidiaries = project_subsidiary_edges(store, companies, documents)
    people = project_people_edges(store, companies, documents)
    instrument_counts = (
        project_instrument_edges(store, instruments) if instruments is not None else {"commodities": 0, "debt": 0}
    )
    return {
        "in_sector": sector,
        "market_tiers": market_tiers,
        "references": references,
        "subsidiaries": subsidiaries,
        "people": people,
        "commodities": instrument_counts["commodities"],
        "debt": instrument_counts["debt"],
        "documents": len(documents),
    }
