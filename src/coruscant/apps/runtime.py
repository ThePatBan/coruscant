"""Application runtime wiring shared by the API, CLI, and worker.

Centralizes how the durable stores (filesystem artifacts, SQLite catalog, graph
snapshot) are constructed and how an ingestion run is assembled and replayed.

Boundary: PLATFORM (assembly). Owns platform store builders (``build_auth_service`` /
``build_org_store`` / ``build_api_key_store`` / …), the generic intelligence store, and
the serving loaders (``load_engine`` / ``load_graph_store``). The workspace-specific store
builders, market-data services, and pipelines moved to ``coruscant.apps.workspace_runtime``
(Phase 3), and the finance ingestion assembly (``run_ingestion`` / ``build_registry`` /
``build_source_resolver`` / ``due_source_types`` / ``source_monitoring``) followed in
Phase 4 — so this module imports **nothing** from ``coruscant.exposure`` or the workspace
runtime. The dependency runs workspace -> platform only (docs/PLATFORM.md §9).
"""

from __future__ import annotations

import logging
import secrets

from pathlib import Path
import tarfile
from typing import TYPE_CHECKING

if TYPE_CHECKING:

    pass

from coruscant.auth.service import AuthService
from coruscant.auth.store import SqliteUserStore
from coruscant.commercial.store import SqliteOrgStore, SqliteUsageStore
from coruscant.common.config import (
    Settings,
    get_settings,
)
from coruscant.infrastructure.catalog import SqliteDocumentCatalog
from coruscant.infrastructure.intelligence_store import SqliteIntelligenceStore
from coruscant.infrastructure.status import RunStatus, load_status
from coruscant.knowledge_graph.kuzu_store import KuzuKnowledgeGraphStore
from coruscant.knowledge_graph.persistence import (
    load_graph,
)
from coruscant.knowledge_graph.store import KnowledgeGraphStore
from coruscant.enterprise.api_keys import SqliteApiKeyStore
from coruscant.enterprise.audit import SqliteAuditStore
from coruscant.infrastructure.dead_letter import SqliteDeadLetterStore
from coruscant.infrastructure.saved_searches import SqliteSavedSearchStore
from coruscant.infrastructure.schedule_store import SqliteScheduleStore
from coruscant.search.hybrid import HybridRetrievalEngine
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
