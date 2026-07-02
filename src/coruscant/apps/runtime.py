"""Application runtime wiring shared by the API, CLI, and worker.

Centralizes how the durable stores (filesystem artifacts, SQLite catalog, graph
snapshot) are constructed and how an ingestion run is assembled and replayed.

Boundary: PLATFORM (assembly). This module still interleaves platform store builders
(``build_auth_service`` / ``build_org_store`` / ``build_api_key_store`` / …) with
workspace pipelines (``run_screening`` / ``run_anchor`` / ``run_portfolio`` /
``run_coverage`` / ``run_ownership``). Splitting the workspace pipelines into a workspace
runtime module is a follow-up to the Phase 2 API composition split (docs/PLATFORM.md §9);
the API surface was separated first because it is the higher-traffic boundary.
"""

from __future__ import annotations

from datetime import datetime, timezone
import logging
import secrets

from pathlib import Path
import tarfile
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

    from coruscant.anchoring.pipeline import AnchorSummary
    from coruscant.anchoring.provider import LeiProvider
    from coruscant.coverage.pipeline import CoverageSummary
    from coruscant.coverage.provider import CoverageProvider
    from coruscant.ownership.pipeline import OwnershipSummary
    from coruscant.ownership.provider import OwnershipProvider
    from coruscant.portfolio.holdings import FundSummary
    from coruscant.screening.pipeline import ScreeningSummary
    from coruscant.screening.provider import ScreeningProvider

from coruscant.auth.service import AuthService
from coruscant.auth.store import SqliteUserStore
from coruscant.commercial.store import SqliteOrgStore, SqliteUsageStore
from coruscant.common.config import (
    CompanyConfig,
    Settings,
    get_settings,
    load_companies,
    load_entities,
    load_instruments,
    load_sources,
)
from coruscant.connectors.sec_edgar import RateLimiter
from coruscant.infrastructure.catalog import SqliteDocumentCatalog
from coruscant.infrastructure.intelligence_store import SqliteIntelligenceStore
from coruscant.infrastructure.status import RunStatus, load_status, save_status
from coruscant.infrastructure.repositories import (
    FileSystemNormalizedDocumentRepository,
    FileSystemRawDocumentRepository,
)
from coruscant.ingestion.orchestrator import (
    IngestionOrchestrator,
    IngestionReport,
    IngestionTarget,
    SourceResolver,
    reference_targets,
)
from coruscant.ingestion.registry import SourceDefinition, SourceRegistry, default_registry
from coruscant.intelligence.reliability import (
    SourceReliability,
    errors_for_source,
    score_source,
)
from coruscant.knowledge_graph.extraction import extract_relationships
from coruscant.knowledge_graph.kuzu_store import KuzuKnowledgeGraphStore
from coruscant.knowledge_graph.memory import InMemoryKnowledgeGraphStore
from coruscant.knowledge_graph.persistence import (
    load_graph,
    load_resolver,
    save_graph,
    save_resolver,
)
from coruscant.knowledge_graph.store import KnowledgeGraphStore
from coruscant.enterprise.api_keys import SqliteApiKeyStore
from coruscant.enterprise.audit import SqliteAuditStore
from coruscant.infrastructure.dead_letter import SqliteDeadLetterStore
from coruscant.infrastructure.saved_searches import SqliteSavedSearchStore
from coruscant.infrastructure.schedule_store import SqliteScheduleStore
from coruscant.ingestion.scheduler import due_sources
from coruscant.portfolio.store import SqlitePortfolioStore
from coruscant.search.hybrid import HybridRetrievalEngine
from coruscant.watchlists.matcher import match_watch_items
from coruscant.watchlists.store import SqliteWatchlistStore
from coruscant.workspaces.store import SqliteWorkspaceStore


def build_catalog(settings: Settings | None = None) -> SqliteDocumentCatalog:
    settings = settings or get_settings()
    return SqliteDocumentCatalog(settings.database_url)


def build_intelligence_store(settings: Settings | None = None) -> SqliteIntelligenceStore:
    settings = settings or get_settings()
    return SqliteIntelligenceStore(settings.database_url)


def build_user_store(settings: Settings | None = None) -> SqliteUserStore:
    settings = settings or get_settings()
    return SqliteUserStore(settings.database_url)


def build_watchlist_store(settings: Settings | None = None) -> SqliteWatchlistStore:
    settings = settings or get_settings()
    return SqliteWatchlistStore(settings.database_url)


def build_portfolio_store(settings: Settings | None = None) -> SqlitePortfolioStore:
    settings = settings or get_settings()
    return SqlitePortfolioStore(settings.database_url)


def build_workspace_store(settings: Settings | None = None) -> SqliteWorkspaceStore:
    settings = settings or get_settings()
    return SqliteWorkspaceStore(settings.database_url)


def build_audit_store(settings: Settings | None = None) -> SqliteAuditStore:
    settings = settings or get_settings()
    return SqliteAuditStore(settings.database_url)


def build_api_key_store(settings: Settings | None = None) -> SqliteApiKeyStore:
    settings = settings or get_settings()
    return SqliteApiKeyStore(settings.database_url)


def build_dead_letter_store(settings: Settings | None = None) -> SqliteDeadLetterStore:
    settings = settings or get_settings()
    return SqliteDeadLetterStore(settings.database_url)


def build_schedule_store(settings: Settings | None = None) -> SqliteScheduleStore:
    settings = settings or get_settings()
    return SqliteScheduleStore(settings.database_url)


def build_saved_search_store(settings: Settings | None = None) -> SqliteSavedSearchStore:
    settings = settings or get_settings()
    return SqliteSavedSearchStore(settings.database_url)


def build_org_store(settings: Settings | None = None) -> SqliteOrgStore:
    settings = settings or get_settings()
    return SqliteOrgStore(settings.database_url)


def build_usage_store(settings: Settings | None = None) -> SqliteUsageStore:
    settings = settings or get_settings()
    return SqliteUsageStore(settings.database_url)


def backup(settings: Settings | None = None, *, out_path: Path | None = None) -> Path:
    """Create a tar.gz backup of the data directory (DB + artifacts + snapshots)."""

    settings = settings or get_settings()
    data_dir = settings.data_dir
    target = out_path or (data_dir.parent / f"{data_dir.name}-backup.tar.gz")
    target.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(target, "w:gz") as tar:
        if data_dir.exists():
            tar.add(data_dir, arcname=data_dir.name)
    return target


def due_source_types(settings: Settings | None = None, now: datetime | None = None) -> list[str]:
    """Source types whose cadence has elapsed (scheduler decision)."""

    settings = settings or get_settings()
    moment = now or datetime.now(tz=timezone.utc)
    last_runs = build_schedule_store(settings).last_runs()
    return due_sources(default_registry().definitions(), last_runs, moment)


logger = logging.getLogger(__name__)

_INSECURE_SECRETS = {"", "dev-insecure-secret-change-me"}
_ephemeral_secret: str | None = None


def _resolve_secret(settings: Settings) -> str:
    """Return the configured secret, or a per-process ephemeral one.

    Never falls back to a committed constant: an unset/placeholder secret yields
    a random secret generated once per process (tokens then last a process
    lifetime). Set CORUSCANT_SECRET_KEY for stable, secure tokens.
    """

    global _ephemeral_secret
    secret = settings.secret_key.strip()
    if secret not in _INSECURE_SECRETS:
        return secret
    if _ephemeral_secret is None:
        _ephemeral_secret = secrets.token_urlsafe(32)
        logger.warning(
            "CORUSCANT_SECRET_KEY is not set; using an ephemeral per-process secret. "
            "Set CORUSCANT_SECRET_KEY for stable, secure auth tokens."
        )
    return _ephemeral_secret


def build_auth_service(settings: Settings | None = None) -> AuthService:
    settings = settings or get_settings()
    return AuthService(
        store=build_user_store(settings),
        secret=_resolve_secret(settings),
        token_ttl_seconds=settings.token_ttl_seconds,
    )


def seed_demo_user(settings: Settings | None = None) -> bool:
    """Create the demo account if enabled and not already present.

    Returns True if a new account was created. Kept out of run_ingestion so the
    document pipeline has no user side effects; invoked by the CLI / worker.
    """

    from coruscant.auth.service import AuthError

    settings = settings or get_settings()
    if not settings.seed_demo_user or not settings.demo_password:
        return False
    service = build_auth_service(settings)
    if service.store.get(settings.demo_email) is not None:
        return False
    try:
        service.register(settings.demo_email, settings.demo_password, role="admin")
    except AuthError:
        return False
    return True


def build_registry(
    settings: Settings | None = None, *, rate_limiter: RateLimiter | None = None
) -> SourceRegistry:
    """Registry with live connectors swapped in for ``settings.live_sources``."""

    settings = settings or get_settings()
    return default_registry(
        settings.live_sources,
        edgar_user_agent=settings.edgar_user_agent,
        rate_limiter=rate_limiter,
    )


def build_source_resolver(settings: Settings | None = None) -> SourceResolver:
    """Choose how disclosures are located per source.

    Offline (default): synthetic reference targets. When ``sec_edgar`` is live,
    its targets are the company's configured real SEC filing URLs (oldest →
    newest so the change detector still sees a prior + current); a company with no
    configured filings (e.g. a private company with no 10-K) simply yields nothing
    — an observable zero, not an error. Every other source stays on reference.
    """

    settings = settings or get_settings()
    live = set(settings.live_sources)
    if "sec_edgar" not in live:
        return reference_targets

    def resolver(
        company: CompanyConfig, source_type: str, definition: SourceDefinition
    ) -> list[IngestionTarget]:
        if source_type != "sec_edgar":
            return reference_targets(company, source_type, definition)
        return [
            IngestionTarget(
                label=f"SEC filing {revision + 1}",
                published_at="",  # the real date comes from the parsed filing
                source_uri=url,
                revision=revision,
            )
            for revision, url in enumerate(company.sec_filings)
        ]

    return resolver


def run_ingestion(
    settings: Settings | None = None,
    *,
    respect_due: bool = False,
    now: datetime | None = None,
) -> IngestionReport:
    """Run the ingestion lifecycle and persist all derived stores.

    ``respect_due=True`` (the scheduled/worker path) ingests only sources whose
    cadence has elapsed and layers them onto the existing graph snapshot, so a
    partial run never drops not-due sources' projections. The default full run
    (CLI/one-shot) rebuilds everything from scratch — unchanged behavior.
    """

    settings = settings or get_settings()
    moment = now or datetime.now(tz=timezone.utc)
    # One shared limiter for the whole run keeps the aggregate SEC request rate
    # under the fair-access cap. Only constructed when something runs live.
    rate_limiter = (
        RateLimiter(1.0 / settings.sec_rate_limit_per_second)
        if settings.live_sources and settings.sec_rate_limit_per_second > 0
        else None
    )

    companies = load_companies(settings.config_dir)
    sources = load_sources(settings.config_dir)
    if respect_due:
        due = set(due_source_types(settings, now=moment))
        skipped = sorted(s.type for s in sources if s.enabled and s.type not in due)
        sources = [s for s in sources if s.type in due]
        if skipped:
            logger.info("Scheduler: skipping not-due sources: %s", ", ".join(skipped))

    # Incremental due-runs start from the persisted graph so not-due sources
    # survive; full runs start clean. Re-projection is idempotent (dedup by id).
    if respect_due and settings.graph_snapshot_path.exists():
        graph_store = load_graph(settings.graph_snapshot_path)
    else:
        graph_store = InMemoryKnowledgeGraphStore()

    orchestrator = IngestionOrchestrator(
        raw_repository=FileSystemRawDocumentRepository(settings.data_dir),
        normalized_repository=FileSystemNormalizedDocumentRepository(settings.data_dir),
        catalog=build_catalog(settings),
        graph_store=graph_store,
        engine=HybridRetrievalEngine(),
        registry=build_registry(settings, rate_limiter=rate_limiter),
        intelligence_store=build_intelligence_store(settings),
        entities=load_entities(settings.config_dir),
        dead_letter_store=build_dead_letter_store(settings),
        resolver=build_source_resolver(settings),
        max_attempts=settings.ingest_max_attempts,
    )
    report = orchestrator.run(companies, sources)
    # Deterministic relationship extraction over the ingested corpus: cross-company
    # co-mention bridges + SIC sector edges, each with provenance. This is what
    # turns a larger company set into a connected graph rather than isolated nodes.
    instruments = load_instruments(settings.config_dir)
    extraction = extract_relationships(graph_store, companies, settings.data_dir, instruments)
    logger.info(
        "Extraction: %d co-mention references, %d sector (GICS) edges, %d market-tier "
        "edges, %d subsidiaries, %d officer (people) edges, %d commodities, %d debt "
        "(over %d documents)",
        extraction["references"],
        extraction["in_sector"],
        extraction["market_tiers"],
        extraction["subsidiaries"],
        extraction["people"],
        extraction["commodities"],
        extraction["debt"],
        extraction["documents"],
    )
    save_graph(graph_store, settings.graph_snapshot_path)
    completed_at = moment.isoformat()
    save_status(RunStatus.from_report(report, completed_at=completed_at), settings.status_path)
    # Record last successful run per source so the scheduler can compute due-ness.
    schedule = build_schedule_store(settings)
    for source_type in report.source_types:
        schedule.record_run(source_type, completed_at)
    return report


def _build_screening_provider(
    settings: Settings, *, dataset_path: Path | None, provider_name: str | None
) -> "tuple[ScreeningProvider, str]":
    """Construct the configured screening provider. ``yente`` needs a running
    sidecar (no file); ``deterministic`` needs an OpenSanctions export file."""

    from coruscant.screening.provider import (
        DeterministicScreeningProvider,
        YenteScreeningProvider,
        load_opensanctions,
    )

    choice = (provider_name or settings.screening_provider).lower()
    if choice == "yente":
        provider = YenteScreeningProvider(
            settings.yente_url, dataset=settings.yente_dataset,
            cutoff=settings.yente_cutoff, limit=settings.yente_limit,
        )
        if not provider.connected():
            raise ConnectionError(
                f"yente is not reachable at {settings.yente_url}. Start the sidecar "
                "(docker-compose.screening.yml) or set CORUSCANT_YENTE_URL."
            )
        return provider, f"yente:{settings.yente_dataset}"

    path = dataset_path or settings.screening_dataset_path
    if path is None or not Path(path).exists():
        raise FileNotFoundError(
            "No OpenSanctions dataset configured. Set CORUSCANT_SCREENING_DATASET_PATH "
            "or pass --dataset (bulk targets.nested.json or a JSON array)."
        )
    return DeterministicScreeningProvider(load_opensanctions(Path(path))), str(path)


def run_screening(
    settings: Settings | None = None,
    *,
    dataset_path: Path | None = None,
    provider_name: str | None = None,
    now: datetime | None = None,
) -> "ScreeningSummary":
    """Screen the graph's people (deterministic file or yente sidecar) and persist
    the projected ``pep`` / ``sanctioned`` / ``screening_candidate`` edges plus the
    reversible resolver log. Opt-in and idempotent; leaves the rest of the graph
    untouched. Returns the run summary."""

    from coruscant.knowledge_graph.persistence import load_graph as _load_graph
    from coruscant.screening.pipeline import screen_people

    settings = settings or get_settings()
    moment = now or datetime.now(tz=timezone.utc)
    provider, dataset_label = _build_screening_provider(
        settings, dataset_path=dataset_path, provider_name=provider_name
    )

    store = _load_graph(settings.graph_snapshot_path)
    resolver = load_resolver(settings.resolver_snapshot_path)
    summary = screen_people(
        store, provider, resolver, observed_at=moment.date(), dataset=dataset_label
    )
    save_graph(store, settings.graph_snapshot_path)
    save_resolver(resolver, settings.resolver_snapshot_path)
    return summary


def _build_lei_provider(
    settings: Settings, *, gleif_path: Path | None, provider_name: str | None
) -> "LeiProvider":
    """Construct the configured LEI provider. ``gleif-api`` needs network (CC0,
    no key); ``gleif-local`` needs a GLEIF export file."""

    from coruscant.anchoring.provider import GleifApiProvider, LocalGleifProvider, load_gleif

    choice = (provider_name or settings.anchor_provider).lower()
    if choice == "gleif-local":
        path = gleif_path or settings.gleif_dataset_path
        if path is None or not Path(path).exists():
            raise FileNotFoundError(
                "No GLEIF dataset configured. Set CORUSCANT_GLEIF_DATASET_PATH or pass "
                "--gleif, or use --provider gleif-api for the free public API."
            )
        return LocalGleifProvider(load_gleif(Path(path)))
    provider = GleifApiProvider()
    if not provider.connected():
        raise ConnectionError(
            "GLEIF API is not reachable. Check network/SSL_CERT_FILE, or use "
            "--provider gleif-local with a downloaded GLEIF export."
        )
    return provider


def run_anchor(
    settings: Settings | None = None,
    *,
    gleif_path: Path | None = None,
    provider_name: str | None = None,
    now: datetime | None = None,
) -> "AnchorSummary":
    """Anchor the graph's Company/Subsidiary nodes to GLEIF LEIs and persist the
    enriched nodes, ``has_lei``/``lei_candidate`` edges, and reversible resolver
    judgements. Opt-in and idempotent; unmatched nodes are labelled unresolved."""

    from coruscant.anchoring.pipeline import anchor_entities
    from coruscant.knowledge_graph.persistence import load_graph as _load_graph

    settings = settings or get_settings()
    moment = now or datetime.now(tz=timezone.utc)
    provider = _build_lei_provider(settings, gleif_path=gleif_path, provider_name=provider_name)

    store = _load_graph(settings.graph_snapshot_path)
    resolver = load_resolver(settings.resolver_snapshot_path)
    summary = anchor_entities(store, provider, resolver, observed_at=moment.date())
    save_graph(store, settings.graph_snapshot_path)
    save_resolver(resolver, settings.resolver_snapshot_path)
    return summary


def run_portfolio(
    settings: Settings | None = None,
    *,
    cik: str | None = None,
    file_path: Path | None = None,
    name: str | None = None,
    now: datetime | None = None,
) -> "FundSummary":
    """Ingest a fund's 13F holdings into the graph as Fund -holds-> Company edges.
    Either fetch the filer's latest 13F live (``cik``) or parse a local info-table
    XML (``file_path``). Opt-in and idempotent."""

    from coruscant.knowledge_graph.persistence import load_graph as _load_graph
    from coruscant.portfolio.holdings import ingest_fund_holdings
    from coruscant.portfolio.thirteenf import FundFiling, fetch_latest_13f, parse_13f_info_table

    settings = settings or get_settings()
    moment = now or datetime.now(tz=timezone.utc)

    filing: FundFiling | None
    if file_path is not None:
        holdings = parse_13f_info_table(Path(file_path).read_text())
        filing = FundFiling(cik=(cik or "local"), name=(name or "Fund"),
                            period=None, source_url=str(file_path), holdings=holdings)
    elif cik is not None:
        filing = fetch_latest_13f(cik, user_agent=settings.edgar_user_agent)
        if filing is None:
            raise FileNotFoundError(f"No 13F-HR found on EDGAR for CIK {cik}.")
        if name:
            filing = filing.model_copy(update={"name": name})
    else:
        raise ValueError("run_portfolio needs either --cik (live 13F) or --file (local XML).")

    store = _load_graph(settings.graph_snapshot_path)
    summary = ingest_fund_holdings(store, filing, observed_at=moment.date())
    save_graph(store, settings.graph_snapshot_path)
    return summary


def _build_coverage_provider(
    settings: Settings,
    *,
    market: str,
    file_path: Path | None,
    sources: "Mapping[str, Path] | None" = None,
) -> "CoverageProvider":
    """Construct the coverage provider for ``market``.

    * ``us`` — SEC ``company_tickers_exchange.json`` (one request, live) or a
      downloaded copy (``file_path`` — the hermetic/operator path).
    * ``in`` — the NSE + BSE equity scrip lists, ISIN-unified, plus optional
      Nifty/Sensex constituent lists (``sources`` keyed by nse/bse/nifty/sensex).
      NSE blocks scripts, so the operator ``--file`` downloads are the primary path;
      the live fetch is best-effort.
    * ``gb``/``uk`` — the LSE "List of all companies" CSV, ISIN-identified, plus
      optional FTSE 100 / FTSE 250 constituent lists (``sources`` keyed by
      lse/ftse100/ftse250). The LSE site is JS-heavy, so ``--lse`` is the primary path."""

    from coruscant.coverage.provider import (
        IndiaCoverageProvider,
        UkLseCoverageProvider,
        UsEdgarCoverageProvider,
    )

    key = market.lower()
    files = dict(sources or {})
    if key == "in":
        if any(files.values()):
            return IndiaCoverageProvider.from_files(
                nse=files.get("nse"), bse=files.get("bse"),
                nifty=files.get("nifty"), sensex=files.get("sensex"),
                user_agent=settings.edgar_user_agent,
            )
        provider_in = IndiaCoverageProvider(user_agent=settings.edgar_user_agent)
        if not provider_in.connected():
            raise ConnectionError(
                "NSE is not reachable for coverage (it blocks scripts). Pass --nse/--bse "
                "with downloaded EQUITY_L.csv / BSE scrip-list CSVs (the primary path)."
            )
        return provider_in
    if key in ("gb", "uk"):
        if any(files.values()):
            return UkLseCoverageProvider.from_files(
                lse=files.get("lse"), ftse100=files.get("ftse100"), ftse250=files.get("ftse250"),
                user_agent=settings.edgar_user_agent,
            )
        provider_gb = UkLseCoverageProvider(user_agent=settings.edgar_user_agent)
        if not provider_gb.connected():
            raise ConnectionError(
                "The LSE list is not reachable for coverage (JS-heavy site). Pass --lse "
                "with a downloaded 'List of all companies' CSV (the primary path)."
            )
        return provider_gb
    if key != "us":
        raise ValueError(
            f"No coverage provider for market {market!r} yet. Implemented: us, in, gb."
        )
    # One shared limiter keeps the aggregate SEC request rate under the fair-access
    # cap (the US feed is a single request, but the seam stays consistent).
    rate_limiter = (
        RateLimiter(1.0 / settings.sec_rate_limit_per_second)
        if settings.sec_rate_limit_per_second > 0 else None
    )
    if file_path is not None:
        return UsEdgarCoverageProvider.from_file(
            Path(file_path), user_agent=settings.edgar_user_agent, rate_limiter=rate_limiter
        )
    provider = UsEdgarCoverageProvider(
        user_agent=settings.edgar_user_agent, rate_limiter=rate_limiter
    )
    if not provider.connected():
        raise ConnectionError(
            "SEC is not reachable for coverage. Check network/SSL_CERT_FILE, or pass "
            "--file with a downloaded company_tickers_exchange.json."
        )
    return provider


def run_coverage(
    settings: Settings | None = None,
    *,
    market: str = "us",
    file_path: Path | None = None,
    sources: "Mapping[str, Path] | None" = None,
    now: datetime | None = None,
) -> "CoverageSummary":
    """Ingest a market's full listed-issuer universe into the graph as lightweight
    Company nodes so uploaded portfolios resolve. Dedup is exact on the market's
    identity key (US→CIK, India→ISIN); enrich, don't duplicate; idempotent; writes
    the snapshot (serving rebuilds Kùzu on next open). ``sources`` supplies India's
    per-file paths (nse/bse/nifty/sensex).
    """

    from coruscant.coverage.pipeline import ingest_coverage
    from coruscant.knowledge_graph.persistence import load_graph as _load_graph

    settings = settings or get_settings()
    moment = now or datetime.now(tz=timezone.utc)
    provider = _build_coverage_provider(
        settings, market=market, file_path=file_path, sources=sources
    )

    store = _load_graph(settings.graph_snapshot_path)
    summary = ingest_coverage(store, provider, observed_at=moment.date())
    save_graph(store, settings.graph_snapshot_path)
    return summary


def _covered_gb_company_numbers(store: KnowledgeGraphStore) -> list[str]:
    """Company numbers of GB-covered issuers — the live UK PSC fetch target set.
    Read off the coverage anchors so PSC is pulled only for companies we can resolve
    against (enrich, don't duplicate); empty is honest, not an error."""

    numbers: list[str] = []
    seen: set[str] = set()
    for node in store.nodes_of_kind("Company"):
        for anchor in node.properties.get("anchors") or []:
            if isinstance(anchor, dict) and anchor.get("scheme") == "company_number":
                value = str(anchor.get("value") or "").strip()
                if value and value not in seen:
                    seen.add(value)
                    numbers.append(value)
    return numbers


def _anchored_leis(store: KnowledgeGraphStore) -> list[str]:
    """LEIs already anchored on the graph (Company/Subsidiary/LegalEntity) — the live
    GLEIF-L2 lookup set, so consolidation is fetched only for entities we can resolve."""

    leis: list[str] = []
    seen: set[str] = set()
    for kind in ("Company", "Subsidiary", "LegalEntity"):
        for node in store.nodes_of_kind(kind):
            value = node.properties.get("lei")
            if isinstance(value, str) and value.strip() and value.strip().upper() not in seen:
                seen.add(value.strip().upper())
                leis.append(value.strip())
    return leis


def _build_ownership_provider(
    settings: Settings,
    *,
    file_path: Path | None,
    provider_name: str | None,
    store: KnowledgeGraphStore | None = None,
) -> "OwnershipProvider":
    """Construct the ownership provider behind the generic ``OwnershipProvider`` seam.

    * ``bods`` (default) — a downloaded BODS / OpenOwnership export (``file_path``).
    * ``psc`` — UK Companies House PSC, a live PUBLIC beneficial-ownership register:
      the Public Data API (needs ``companies_house_api_key``, fetched for the GB-
      covered universe) or a downloaded bulk PSC snapshot (``file_path`` fallback).
    * ``gleif-l2`` — GLEIF Level-2 accounting consolidation for the anchored LEIs
      (live CC0 API) or a downloaded relationship-record export (``file_path``).

    File paths are the operator fallback, never the primary path; a source with no
    live key/anchors and no file raises an explicit, honest error (no fabricated run).
    """

    from coruscant.ownership.companies_house import CompaniesHousePscProvider
    from coruscant.ownership.gleif_l2 import GleifL2ConsolidationProvider
    from coruscant.ownership.provider import BodsOwnershipProvider

    choice = (provider_name or "bods").lower()
    if choice in ("psc", "companies-house", "companies-house-psc", "uk-psc"):
        if file_path is not None and Path(file_path).exists():
            return CompaniesHousePscProvider.from_file(Path(file_path))
        numbers = _covered_gb_company_numbers(store) if store is not None else []
        if settings.companies_house_api_key and numbers:
            return CompaniesHousePscProvider(
                api_key=settings.companies_house_api_key,
                company_numbers=numbers,
                base_url=settings.companies_house_api_url,
            )
        if settings.companies_house_api_key and not numbers:
            raise FileNotFoundError(
                "Companies House PSC is wired (API key set) but no GB-covered company "
                "numbers were found to fetch. Run `coruscant coverage --market gb` first, "
                "or pass --file with a bulk PSC snapshot."
            )
        raise FileNotFoundError(
            "No UK PSC source available. Set CORUSCANT_COMPANIES_HOUSE_API_KEY for the "
            "live Public Data API (fetches the GB-covered universe), or pass --file with "
            "a downloaded bulk PSC snapshot (NDJSON)."
        )
    if choice in ("gleif-l2", "gleif_l2", "l2", "consolidation"):
        if file_path is not None and Path(file_path).exists():
            return GleifL2ConsolidationProvider.from_file(Path(file_path))
        leis = _anchored_leis(store) if store is not None else []
        if leis:
            return GleifL2ConsolidationProvider(leis=leis)
        raise FileNotFoundError(
            "No GLEIF L2 source available. Anchor the graph first (`coruscant anchor`) so "
            "there are LEIs to look up, or pass --file with a downloaded GLEIF relationship-"
            "record export."
        )
    if choice != "bods":
        raise ValueError(
            f"No ownership provider {provider_name!r}. Implemented: bods, psc, gleif-l2."
        )
    if file_path is None or not Path(file_path).exists():
        raise FileNotFoundError(
            "No ownership dataset supplied. Pass --file with a BODS / OpenOwnership "
            "export (a statements JSON array or newline-delimited BODS), or use "
            "--provider psc (UK Companies House) / --provider gleif-l2 (consolidation)."
        )
    return BodsOwnershipProvider.from_file(Path(file_path))


def run_ownership(
    settings: Settings | None = None,
    *,
    file_path: Path | None = None,
    provider_name: str | None = None,
    now: datetime | None = None,
) -> "OwnershipSummary":
    """Ingest sourced ownership statements into the graph as the three distinct edge
    types (``owns`` / ``beneficial_owner_of`` / ``consolidates``), each substrate-
    stamped with provenance, access tier, and bitemporal validity. Opt-in and
    idempotent; parties resolve to existing nodes by anchor, the rest labelled
    unresolved — the foundation for UBO/contagion, not a completeness claim.

    Live sources (``psc``, ``gleif-l2``) scope their fetch to the graph's covered/
    anchored entities, so the store is loaded before the provider is built."""

    from coruscant.knowledge_graph.persistence import load_graph as _load_graph
    from coruscant.ownership.pipeline import ingest_ownership

    settings = settings or get_settings()
    moment = now or datetime.now(tz=timezone.utc)

    store = _load_graph(settings.graph_snapshot_path)
    provider = _build_ownership_provider(
        settings, file_path=file_path, provider_name=provider_name, store=store
    )
    summary = ingest_ownership(store, provider, observed_at=moment.date())
    save_graph(store, settings.graph_snapshot_path)
    return summary


def evaluate_all_watchlists(settings: Settings | None = None, *, now: datetime | None = None) -> int:
    """Re-evaluate every user's watchlists against the current intelligence.

    The background loop: the worker calls this after each ingestion run so new
    material changes and events become source-linked notifications with no user
    action. Idempotent (notification de-dup), so it is safe to run every tick; the
    on-demand API evaluators share the same matcher and remain fully intact.
    Returns the number of new notifications created.
    """

    settings = settings or get_settings()
    now_iso = (now or datetime.now(tz=timezone.utc)).isoformat()
    watchlist_store = build_watchlist_store(settings)
    intelligence = build_intelligence_store(settings)
    graph = load_graph_store(settings)
    companies = load_companies(settings.config_dir)
    events = intelligence.list_events()
    change_sets = intelligence.list_change_sets()
    created = 0
    for user_email, watchlist in watchlist_store.all_watchlists():
        notifications = match_watch_items(
            watchlist.items,
            events=events,
            change_sets=change_sets,
            companies=companies,
            graph=graph,
            now_iso=now_iso,
        )
        created += watchlist_store.add_notifications(user_email, watchlist.id, notifications)
    return created


def load_run_status(settings: Settings | None = None) -> RunStatus | None:
    settings = settings or get_settings()
    return load_status(settings.status_path)


def source_monitoring(settings: Settings | None = None) -> list[SourceReliability]:
    """Per-source reliability and counts, assembled from the catalog + last run."""

    settings = settings or get_settings()
    catalog = build_catalog(settings)
    status = load_status(settings.status_path)
    errors = status.errors if status else []
    reports = [
        score_source(
            source_type=definition.source_type,
            label=definition.label,
            authority=definition.authority,
            documents=catalog.list_documents(source_type=definition.source_type),
            error_count=errors_for_source(definition.source_type, errors),
        )
        for definition in default_registry().definitions()
    ]
    return sorted(reports, key=lambda r: r.score, reverse=True)


def load_engine(settings: Settings | None = None) -> HybridRetrievalEngine:
    """Rebuild a hybrid retrieval engine from the persisted catalog."""

    settings = settings or get_settings()
    engine = HybridRetrievalEngine()
    for document in build_catalog(settings).list_documents():
        engine.add(document)
    return engine


def load_graph_store(settings: Settings | None = None) -> KnowledgeGraphStore:
    """Open the graph store for the serving/query path, per settings.graph_backend.

    "kuzu" returns a read-only Kùzu store materialized from the JSON snapshot
    (rebuilt only when the snapshot is newer); "memory" returns the in-process
    prototype loaded straight from JSON. Ingestion is unaffected — it always
    projects into the in-memory store and writes the JSON snapshot."""
    settings = settings or get_settings()
    if settings.graph_backend == "kuzu":
        return KuzuKnowledgeGraphStore.open_synced(
            str(settings.graph_kuzu_path), settings.graph_snapshot_path
        )
    return load_graph(settings.graph_snapshot_path)
