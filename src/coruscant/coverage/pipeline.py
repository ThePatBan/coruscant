"""Reconcile a market's listed-issuer universe into the graph.

The dedup contract (§2 invariants, US-first but market-plural):

* **Enrich, don't duplicate.** A bulk issuer whose external key (CIK for US)
  matches an existing Company node *enriches* that node — adds ticker/exchange and
  the universe anchors — and leaves the curated GICS/name/source authoritative.
  CIK is a near-perfect intra-US key, so this dedup is exact, not fuzzy (no
  reversible-resolver judgement needed).
* **Stable surrogate for the rest.** A new issuer becomes a Company node keyed by a
  deterministic surrogate (``us-<cik>``) that never moves across re-runs, so a
  bookmark to it stays valid. The external key is an *anchor* on the node, never the
  key (Invariant #2).
* **Sector honesty.** Bulk issuers carry no curated GICS — we label them
  ``gics_status: unresolved`` rather than invent a sector (Invariant #5). The coarse
  SIC can be attached later, clearly lower-authority.
* **Idempotent.** Descriptive fields enrich last-write-wins; identity anchors are
  first-write-wins (stable). Re-running never duplicates a node.

Coverage writes only nodes (the universe); sector/holdings/LEI edges are attached
on demand by the other pipelines.
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field

from coruscant.common.types import GraphEdge, GraphNode
from coruscant.coverage.provider import (
    ANCHOR_FIGI,
    ANCHOR_TICKER,
    CoverageProvider,
    IndexMembership,
    IssuerRecord,
    normalize_cik,
)
from coruscant.knowledge_graph.store import KnowledgeGraphStore

COMPANY_KIND = "Company"
COVERAGE_RUN_KIND = "CoverageRun"
INDEX_KIND = "Index"  # a market index (Nifty 50, BSE Sensex) — NOT an exchange
CONSTITUENT_OF = "constituent_of"  # Company -constituent_of-> Index (provenance-backed)
COVERAGE_SOURCE = "coverage"

# Node property keys the coverage layer owns.
MARKET = "market"
EXCHANGE = "exchange"
TICKER = "ticker"
CIK = "cik"
ANCHORS = "anchors"
IN_UNIVERSE = "in_universe"  # this node is part of an ingested exchange universe
GICS_STATUS = "gics_status"  # "unresolved" for bulk issuers — never a fabricated sector
COVERAGE_SOURCE_KEY = "coverage_source"  # which feed added the universe anchors

# Per-market identity anchor: the external key used for exact dedup. US uses CIK; a
# company listed on both NSE and BSE shares one ISIN, so India dedups (and unifies
# the two exchanges) on ISIN; the UK (LSE) is ISIN-identified too, with SEDOL and the
# Companies House number carried as extra anchors.
_MARKET_IDENTITY_SCHEME: dict[str, str] = {"US": "cik", "IN": "isin", "GB": "isin"}


class CoverageSummary(BaseModel):
    connected: bool
    market: str
    provider: str
    considered: int = 0  # issuers the provider listed (post exchange filter)
    enriched: int = 0  # existing Company nodes enriched by external-key match
    created: int = 0  # new surrogate Company nodes
    excluded: dict[str, int] = Field(default_factory=dict)  # filtered upstream, by reason
    by_exchange: dict[str, int] = Field(default_factory=dict)  # created+enriched, by venue
    indices: dict[str, int] = Field(default_factory=dict)  # index name → constituents linked
    universe_total: int = 0  # Company nodes carrying this market's universe anchor


def _has_gics(props: dict[str, object]) -> bool:
    return bool(props.get("gics_sector") or props.get("gics_code"))


# Identity anchors (cik/isin/sedol/company_number/lei) are single-valued and
# stable: first-write-wins by scheme so identity never moves across re-runs. A
# *ticker* (and FIGI) is NOT an identity key — one issuer legitimately lists
# several share classes under a single CIK (GOOG/GOOGL, FOX/FOXA, UA/UAA), so
# those schemes must accumulate *every* distinct value. Collapsing them to one
# would leave a held share class unresolvable — a fabricated "unresolved", the
# dishonest kind of gap (Invariant #5, honesty).
_MULTI_VALUED_ANCHOR_SCHEMES = frozenset({ANCHOR_TICKER, ANCHOR_FIGI})


def _merge_anchors(existing: object, incoming: list[dict[str, str]]) -> list[dict[str, str]]:
    """Union anchors. Identity schemes are first-write-wins by scheme (a present
    scheme is never overwritten → identity stays stable across re-runs); ``ticker``
    and ``figi`` accumulate every distinct value so each share class resolves."""

    out: list[dict[str, str]] = []
    seen_schemes: set[str] = set()  # single-valued identity schemes already present
    seen_pairs: set[tuple[str, str]] = set()  # (scheme, value) for multi-valued schemes

    def _add(scheme: str, value: str) -> None:
        if scheme in _MULTI_VALUED_ANCHOR_SCHEMES:
            pair = (scheme, value)
            if pair not in seen_pairs:
                out.append({"scheme": scheme, "value": value})
                seen_pairs.add(pair)
        elif scheme not in seen_schemes:
            out.append({"scheme": scheme, "value": value})
            seen_schemes.add(scheme)

    if isinstance(existing, list):
        for a in existing:
            if isinstance(a, dict) and a.get("scheme"):
                _add(str(a["scheme"]), str(a.get("value", "")))
    for a in incoming:
        if a.get("scheme"):
            _add(str(a["scheme"]), str(a.get("value", "")))
    return out


def _cik_index(store: KnowledgeGraphStore) -> dict[str, str]:
    """Map every Company node's normalized CIK → node key (curated *and* prior
    surrogate nodes), so a re-run enriches rather than duplicates."""

    index: dict[str, str] = {}
    for node in store.nodes_of_kind(COMPANY_KIND):
        cik = normalize_cik(node.properties.get(CIK))
        if cik is not None:
            index.setdefault(cik, node.key)  # first wins (curated seeded before bulk)
    return index


def ingest_coverage(
    store: KnowledgeGraphStore,
    provider: CoverageProvider,
    *,
    observed_at: date | str,
) -> CoverageSummary:
    """Ingest ``provider``'s issuer universe into the graph: enrich matched nodes,
    create stable surrogates for the rest, and record a ``CoverageRun`` summary."""

    market = provider.market.upper()
    identity_scheme = _MARKET_IDENTITY_SCHEME.get(market, "cik")
    issuers = provider.list_issuers()
    index = _cik_index(store) if identity_scheme == "cik" else _anchor_index(store, identity_scheme)

    enriched = created = 0
    by_exchange: dict[str, int] = {}
    # Maps for index-membership linking (constituent ISIN/symbol → node key), built
    # over the nodes this run touches so Nifty/Sensex constituents link to real nodes.
    key_by_isin: dict[str, str] = {}
    key_by_ticker: dict[str, str] = {}
    for issuer in issuers:
        key_value = issuer.anchor(identity_scheme)
        if identity_scheme == "cik":
            key_value = normalize_cik(key_value)
        if not key_value:
            continue
        anchors = [a.model_dump() for a in issuer.anchors]
        existing_key = index.get(key_value)
        if existing_key is not None:
            _enrich(store, existing_key, issuer, anchors)
            node_key = existing_key
            enriched += 1
        else:
            node_key = f"{market.lower()}-{key_value}"
            _create(store, node_key, issuer, anchors)
            index[key_value] = node_key  # so a duplicate row in the same feed also dedups
            created += 1
        if issuer.exchange:
            by_exchange[issuer.exchange] = by_exchange.get(issuer.exchange, 0) + 1
        isin_val = issuer.anchor("isin")
        if isin_val:
            key_by_isin.setdefault(isin_val, node_key)
        if issuer.ticker:
            key_by_ticker.setdefault(issuer.ticker.strip().upper(), node_key)

    indices = _ingest_index_memberships(
        store, provider, key_by_isin, key_by_ticker, market=market, observed_at=observed_at
    )
    excluded = dict(getattr(provider, "last_drops", {}) or {})
    universe_total = sum(
        1 for n in store.nodes_of_kind(COMPANY_KIND)
        if n.properties.get(MARKET) == market and n.properties.get(IN_UNIVERSE)
    )
    store.upsert_node(
        GraphNode(
            kind=COVERAGE_RUN_KIND, key=market.lower(),
            properties={
                "name": f"{market} coverage run", "source": COVERAGE_SOURCE,
                "provider": provider.name, MARKET: market,
                "considered": len(issuers), "enriched": enriched, "created": created,
                "excluded": excluded, "by_exchange": by_exchange, "indices": indices,
                "universe_total": universe_total,
                "observed_at": observed_at if isinstance(observed_at, str) else observed_at.isoformat(),
            },
        )
    )
    return CoverageSummary(
        connected=provider.connected(), market=market, provider=provider.name,
        considered=len(issuers), enriched=enriched, created=created,
        excluded=excluded, by_exchange=by_exchange, indices=indices,
        universe_total=universe_total,
    )


def _anchor_index(store: KnowledgeGraphStore, scheme: str) -> dict[str, str]:
    """Generic external-key index for non-US markets: read the anchor of ``scheme``
    off each Company node. US uses the faster flat-CIK path."""

    index: dict[str, str] = {}
    for node in store.nodes_of_kind(COMPANY_KIND):
        for a in node.properties.get(ANCHORS) or []:
            if isinstance(a, dict) and a.get("scheme") == scheme and a.get("value"):
                index.setdefault(str(a["value"]), node.key)
    return index


def _ingest_index_memberships(
    store: KnowledgeGraphStore,
    provider: CoverageProvider,
    key_by_isin: dict[str, str],
    key_by_ticker: dict[str, str],
    *,
    market: str,
    observed_at: date | str,
) -> dict[str, int]:
    """Turn a provider's index constituents into ``Index`` nodes + ``constituent_of``
    edges (Company → Index), linking each constituent to a covered Company by ISIN
    (exact) then symbol. A constituent outside the ingested universe is counted as
    unresolved on the Index node, never fabricated. Returns ``{index name → linked}``.

    An index is not an exchange: this is the "event on the Nifty → which holdings are
    in it" pathway, kept provenance-backed. Providers without indices are a no-op."""

    lister = getattr(provider, "list_index_memberships", None)
    if lister is None:
        return {}
    memberships: list[IndexMembership] = list(lister())
    if not memberships:
        return {}
    observed = observed_at if isinstance(observed_at, str) else observed_at.isoformat()

    linked: dict[str, int] = {}
    unresolved: dict[str, int] = {}
    display: dict[str, str] = {}
    source_by_index: dict[str, str] = {}
    for m in memberships:
        display[m.index_key] = m.index_name
        source_by_index[m.index_key] = m.source
        node_key = (
            (m.isin and key_by_isin.get(m.isin))
            or (m.symbol and key_by_ticker.get(m.symbol.strip().upper()))
        )
        if not node_key:
            unresolved[m.index_key] = unresolved.get(m.index_key, 0) + 1
            continue
        store.upsert_edge(GraphEdge(
            source_kind=COMPANY_KIND, source_key=node_key,
            relation=CONSTITUENT_OF, target_kind=INDEX_KIND, target_key=m.index_key,
            properties={"source": m.source, "source_url": m.source_url,
                        "index_name": m.index_name, "observed_at": observed},
        ))
        linked[m.index_key] = linked.get(m.index_key, 0) + 1

    for index_key, name in display.items():
        store.upsert_node(GraphNode(
            kind=INDEX_KIND, key=index_key,
            properties={
                "name": name, "source": source_by_index[index_key], MARKET: market,
                "provider": provider.name, "constituents": linked.get(index_key, 0),
                "constituents_unresolved": unresolved.get(index_key, 0),
                "observed_at": observed,
            },
        ))
    return {display[k]: v for k, v in linked.items()}


def _enrich(store: KnowledgeGraphStore, key: str, issuer: IssuerRecord, anchors: list[dict[str, str]]) -> None:
    """Add the universe anchors to an existing node without disturbing curated
    authority: name, source, and any curated GICS are preserved."""

    node = store.get_node(COMPANY_KIND, key)
    if node is None:
        return
    props = dict(node.properties)
    props[MARKET] = issuer.market.upper()
    props[IN_UNIVERSE] = True
    props[COVERAGE_SOURCE_KEY] = issuer.source
    if issuer.exchange:
        props[EXCHANGE] = issuer.exchange  # last-write-wins (a venue move is fresh info)
    if issuer.ticker and not props.get(TICKER):
        props[TICKER] = issuer.ticker  # first-write-wins: don't clobber a curated ticker
    props[ANCHORS] = _merge_anchors(props.get(ANCHORS), anchors)
    # Sector honesty: only label unresolved when there is no curated GICS to defer to.
    if not _has_gics(props) and not props.get(GICS_STATUS):
        props[GICS_STATUS] = "unresolved"
    store.upsert_node(GraphNode(kind=COMPANY_KIND, key=key, properties=props))


def _create(store: KnowledgeGraphStore, key: str, issuer: IssuerRecord, anchors: list[dict[str, str]]) -> None:
    """Create/refresh a surrogate universe node. Key is stable; descriptive fields
    enrich last-write-wins; identity anchors are first-write-wins."""

    existing = store.get_node(COMPANY_KIND, key)
    props: dict[str, object] = dict(existing.properties) if existing is not None else {}
    props.update(
        {
            "name": issuer.name or key,
            "source": issuer.source,
            COVERAGE_SOURCE_KEY: issuer.source,
            MARKET: issuer.market.upper(),
            IN_UNIVERSE: True,
        }
    )
    if issuer.ticker:
        props[TICKER] = issuer.ticker
    if issuer.exchange:
        props[EXCHANGE] = issuer.exchange
    cik = normalize_cik(issuer.anchor("cik"))  # unpadded, matching the curated convention
    if cik:
        props[CIK] = cik
    props[ANCHORS] = _merge_anchors(props.get(ANCHORS), anchors)
    # No curated sector for a bulk issuer → labelled unresolved, never fabricated.
    if not _has_gics(props):
        props[GICS_STATUS] = "unresolved"
    props.setdefault("source_url", issuer.source_url)
    store.upsert_node(GraphNode(kind=COMPANY_KIND, key=key, properties=props))
