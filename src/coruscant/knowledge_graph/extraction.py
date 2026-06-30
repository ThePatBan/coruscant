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

from coruscant.common.config import CompanyConfig
from coruscant.common.types import GraphEdge, GraphNode, NormalizedDocument
from coruscant.knowledge_graph.entities import entity_key
from coruscant.knowledge_graph.memory import InMemoryKnowledgeGraphStore

_SECTOR_PROV = "sec-metadata"
_COMENTION_PROV = "sec-co-mention"
_SUBSIDIARY_PROV = "sec-exhibit21"
_OFFICER_PROV = "sec-10k-officers"
_DIRECTOR_PROV = "sec-10k-signatures"

# Pure legal-form tokens stripped to get a company's distinctive core name. We
# deliberately KEEP words like "companies" / "group" — they make a name precise
# ("travelers companies", "goldman sachs group") rather than collapsing it to an
# ambiguous common word ("travelers").
_SUFFIXES = {
    "corp", "corporation", "inc", "incorporated", "co", "com",
    "plc", "ltd", "lp", "sa", "ag", "nv",
}
# Single-word cores that are also common English words — excluded from the
# gazetteer so a coincidental word (e.g. a travel "visa") never asserts a
# co-mention. A fabricated edge would violate the platform's first principle.
_AMBIGUOUS = {"visa"}


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
        store.upsert_node(
            GraphNode(
                kind="Company",
                key=company.slug,
                properties={
                    "name": company.name,
                    "source": "tracked",
                    "industry": company.industry,
                    "cik": company.cik,
                },
            )
        )


def project_sector_edges(store: InMemoryKnowledgeGraphStore, companies: list[CompanyConfig]) -> int:
    """Company -in_sector-> Industry, from each company's SIC classification."""
    count = 0
    for company in companies:
        industry = (company.industry or "").strip()
        if not industry:
            continue
        key = entity_key(industry)
        if store.get_node("Industry", key) is None:
            store.upsert_node(
                GraphNode(kind="Industry", key=key, properties={"name": industry, "source": _SECTOR_PROV})
            )
        store.upsert_edge(
            GraphEdge(
                source_kind="Company",
                source_key=company.slug,
                relation="in_sector",
                target_kind="Industry",
                target_key=key,
                properties={"source": _SECTOR_PROV, "company_slug": company.slug, "industry": industry},
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
                if pair in seen:
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
) -> dict[str, int]:
    """Run the deterministic extractors and project their edges. Returns counts."""
    documents = load_normalized_documents(data_dir)
    project_company_nodes(store, companies)
    sector = project_sector_edges(store, companies)
    references = project_cross_company_references(store, companies, documents)
    subsidiaries = project_subsidiary_edges(store, companies, documents)
    people = project_people_edges(store, companies, documents)
    return {
        "in_sector": sector,
        "references": references,
        "subsidiaries": subsidiaries,
        "people": people,
        "documents": len(documents),
    }
