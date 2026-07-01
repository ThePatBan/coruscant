"""Application runtime wiring shared by the API, CLI, and worker.

Centralizes how the durable stores (filesystem artifacts, SQLite catalog, graph
snapshot) are constructed and how an ingestion run is assembled and replayed.
"""

from __future__ import annotations

from datetime import datetime, timezone
import logging
import secrets

from pathlib import Path
import tarfile
from typing import TYPE_CHECKING

if TYPE_CHECKING:
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
