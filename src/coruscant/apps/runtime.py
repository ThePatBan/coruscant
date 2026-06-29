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

from coruscant.auth.service import AuthService
from coruscant.auth.store import SqliteUserStore
from coruscant.commercial.store import SqliteOrgStore, SqliteUsageStore
from coruscant.common.config import (
    Settings,
    get_settings,
    load_companies,
    load_entities,
    load_sources,
)
from coruscant.infrastructure.catalog import SqliteDocumentCatalog
from coruscant.infrastructure.intelligence_store import SqliteIntelligenceStore
from coruscant.infrastructure.status import RunStatus, load_status, save_status
from coruscant.infrastructure.repositories import (
    FileSystemNormalizedDocumentRepository,
    FileSystemRawDocumentRepository,
)
from coruscant.ingestion.orchestrator import IngestionOrchestrator, IngestionReport
from coruscant.ingestion.registry import default_registry
from coruscant.intelligence.reliability import (
    SourceReliability,
    errors_for_source,
    score_source,
)
from coruscant.knowledge_graph.memory import InMemoryKnowledgeGraphStore
from coruscant.knowledge_graph.persistence import load_graph, save_graph
from coruscant.enterprise.api_keys import SqliteApiKeyStore
from coruscant.enterprise.audit import SqliteAuditStore
from coruscant.infrastructure.dead_letter import SqliteDeadLetterStore
from coruscant.infrastructure.saved_searches import SqliteSavedSearchStore
from coruscant.infrastructure.schedule_store import SqliteScheduleStore
from coruscant.ingestion.scheduler import due_sources
from coruscant.portfolio.store import SqlitePortfolioStore
from coruscant.search.hybrid import HybridRetrievalEngine
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


def run_ingestion(settings: Settings | None = None) -> IngestionReport:
    """Run the full ingestion lifecycle and persist all derived stores."""

    settings = settings or get_settings()
    graph_store = InMemoryKnowledgeGraphStore()
    orchestrator = IngestionOrchestrator(
        raw_repository=FileSystemRawDocumentRepository(settings.data_dir),
        normalized_repository=FileSystemNormalizedDocumentRepository(settings.data_dir),
        catalog=build_catalog(settings),
        graph_store=graph_store,
        engine=HybridRetrievalEngine(),
        intelligence_store=build_intelligence_store(settings),
        entities=load_entities(settings.config_dir),
        dead_letter_store=build_dead_letter_store(settings),
        max_attempts=settings.ingest_max_attempts,
    )
    companies = load_companies(settings.config_dir)
    sources = load_sources(settings.config_dir)
    report = orchestrator.run(companies, sources)
    save_graph(graph_store, settings.graph_snapshot_path)
    completed_at = datetime.now(tz=timezone.utc).isoformat()
    save_status(RunStatus.from_report(report, completed_at=completed_at), settings.status_path)
    # Record last successful run per source so the scheduler can compute due-ness.
    schedule = build_schedule_store(settings)
    for source_type in report.source_types:
        schedule.record_run(source_type, completed_at)
    return report


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


def load_graph_store(settings: Settings | None = None) -> InMemoryKnowledgeGraphStore:
    settings = settings or get_settings()
    return load_graph(settings.graph_snapshot_path)
