"""Application runtime wiring shared by the API, CLI, and worker.

Centralizes how the durable stores (filesystem artifacts, SQLite catalog, graph
snapshot) are constructed and how an ingestion run is assembled and replayed.
"""

from __future__ import annotations

from datetime import datetime, timezone

from coruscant.auth.service import AuthService
from coruscant.auth.store import SqliteUserStore
from coruscant.common.config import Settings, get_settings, load_companies, load_sources
from coruscant.infrastructure.catalog import SqliteDocumentCatalog
from coruscant.infrastructure.intelligence_store import SqliteIntelligenceStore
from coruscant.infrastructure.status import RunStatus, load_status, save_status
from coruscant.infrastructure.repositories import (
    FileSystemNormalizedDocumentRepository,
    FileSystemRawDocumentRepository,
)
from coruscant.ingestion.orchestrator import IngestionOrchestrator, IngestionReport
from coruscant.knowledge_graph.memory import InMemoryKnowledgeGraphStore
from coruscant.knowledge_graph.persistence import load_graph, save_graph
from coruscant.search.hybrid import HybridRetrievalEngine


def build_catalog(settings: Settings | None = None) -> SqliteDocumentCatalog:
    settings = settings or get_settings()
    return SqliteDocumentCatalog(settings.database_url)


def build_intelligence_store(settings: Settings | None = None) -> SqliteIntelligenceStore:
    settings = settings or get_settings()
    return SqliteIntelligenceStore(settings.database_url)


def build_user_store(settings: Settings | None = None) -> SqliteUserStore:
    settings = settings or get_settings()
    return SqliteUserStore(settings.database_url)


def build_auth_service(settings: Settings | None = None) -> AuthService:
    settings = settings or get_settings()
    return AuthService(
        store=build_user_store(settings),
        secret=settings.secret_key,
        token_ttl_seconds=settings.token_ttl_seconds,
    )


def seed_demo_user(settings: Settings | None = None) -> bool:
    """Create the demo account if enabled and not already present.

    Returns True if a new account was created. Kept out of run_ingestion so the
    document pipeline has no user side effects; invoked by the CLI / worker.
    """

    from coruscant.auth.service import AuthError

    settings = settings or get_settings()
    if not settings.seed_demo_user:
        return False
    service = build_auth_service(settings)
    if service.store.get(settings.demo_email) is not None:
        return False
    try:
        service.register(settings.demo_email, settings.demo_password)
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
        max_attempts=settings.ingest_max_attempts,
    )
    companies = load_companies(settings.config_dir)
    sources = load_sources(settings.config_dir)
    report = orchestrator.run(companies, sources)
    save_graph(graph_store, settings.graph_snapshot_path)
    status = RunStatus.from_report(
        report, completed_at=datetime.now(tz=timezone.utc).isoformat()
    )
    save_status(status, settings.status_path)
    return report


def load_run_status(settings: Settings | None = None) -> RunStatus | None:
    settings = settings or get_settings()
    return load_status(settings.status_path)


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
