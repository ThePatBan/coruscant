from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
import logging
import secrets
from typing import Any

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from coruscant.apps import composition
from pydantic import BaseModel, Field

from coruscant.apps.runtime import (
    build_api_key_store,
    build_audit_store,
    build_auth_service,
    build_dead_letter_store,
    build_intelligence_store,
    build_org_store,
    build_saved_search_store,
    build_usage_store,
    build_workspace_store,
    load_engine,
    load_graph_store,
    load_run_status,
)
from coruscant.apps.workspace_runtime import (
    build_macro_service,
    build_news_service,
    build_portfolio_store,
    build_price_service,
    build_watchlist_store,
    source_monitoring,
)
from coruscant.commercial.models import (
    DEFAULT_PLAN,
    PLANS,
    BillingSummary,
    Organization,
    Plan,
    UsageSummary,
)
from coruscant.commercial.store import SqliteOrgStore, SqliteUsageStore
from coruscant.enterprise.api_keys import ApiKey, ApiKeyCreated, SqliteApiKeyStore
from coruscant.enterprise.audit import AuditEntry, SqliteAuditStore
from coruscant.infrastructure.dead_letter import DeadLetterEntry, SqliteDeadLetterStore
from coruscant.infrastructure.saved_searches import SavedSearch, SqliteSavedSearchStore
from coruscant.intelligence.changes import ReferenceChangeDetector
from coruscant.coverage.resolve import (
    ResolveReport,
    parse_brokerage_csv,
    resolve_positions,
)
from coruscant.portfolio.models import Holding, Portfolio, PortfolioBriefing
from coruscant.portfolio.store import SqlitePortfolioStore
from coruscant.workspaces.models import ITEM_TYPES, Workspace, WorkspaceItem
from coruscant.workspaces.store import SqliteWorkspaceStore
from coruscant.watchlists.matcher import match_watch_items
from coruscant.watchlists.models import WATCH_TYPES, Notification, Watchlist, WatchItem
from coruscant.watchlists.store import SqliteWatchlistStore
from coruscant.infrastructure.status import RunStatus
from coruscant.intelligence.reliability import SourceReliability
from coruscant.auth.service import AuthError, AuthService
from coruscant.auth.store import StoredUser
from coruscant.common.config import get_settings
from coruscant.exposure.domain_config import load_companies
from coruscant.common.types import SCHEMA_VERSION, NormalizedDocument, Provenance
from coruscant.infrastructure.intelligence_store import SqliteIntelligenceStore
from coruscant.exposure.sources import default_registry
from coruscant.intelligence.analyst import AnalysisReport, ReferenceAnalyst
from coruscant.intelligence.llm_analyst import LLMAnalyst
from coruscant.llm import LLMError
from coruscant.intelligence.signals import ReferenceSignalEngine, Signal
from coruscant.intelligence.models import ChangeSet
from coruscant.intelligence.models import DocumentSummary as AISummary
from coruscant.intelligence.models import ExtractedEvent
from coruscant.knowledge_graph.memory import InMemoryKnowledgeGraphStore
from coruscant.knowledge_graph.store import KnowledgeGraphStore
from coruscant import llm
from coruscant.llm import LLMGateway
from coruscant.exposure.queries import (
    CoExecutiveResult,
    CoverageOverview,
    EntityProfile,
    EntityRef,
    ExposureResult,
    CommodityExposure,
    CommodityRef,
    DebtRef,
    GicsSector,
    JurisdictionCount,
    JurisdictionExposure,
    FundHoldings,
    FundRef,
    MarketTierCount,
    MarketTierExposure,
    OwnershipOverview,
    CompanyOwners,
    PortfolioExposure,
    PortfolioProfile,
    ResolutionOverview,
    ScreeningOverview,
    SectorCount,
    CompanyNetwork,
    SectorExposure,
    co_executives,
    commodity_exposure,
    company_country_exposures,
    company_owners,
    coverage_overview,
    company_network,
    ownership_overview,
    debt_for_country,
    entity_profile,
    exposure_to_country,
    gics_breakdown,
    jurisdiction_exposure,
    list_commodities,
    list_debt_instruments,
    list_entities,
    list_jurisdictions,
    list_market_tiers,
    fund_holdings,
    list_funds,
    list_sectors,
    market_tier_exposure,
    portfolio_exposure,
    portfolio_profile,
    resolution_overview,
    screening_overview,
    sector_exposure,
)
from coruscant.exposure.ownership_graph import (
    CompanyOwnershipChains,
    GroupContagion,
    group_contagion,
    ownership_chains,
)
from coruscant.macro import CountryMacro, MacroService
from coruscant.news import NewsFeed, NewsService
from coruscant.exposure.taxonomy import company_gics
from coruscant.pricing import (
    PortfolioBenchmark,
    PortfolioPrices,
    PriceService,
    benchmark_symbols,
    sector_benchmarks,
    summarize,
)
from coruscant.search.hybrid import HybridRetrievalEngine
from coruscant.search.reference import TemplateReasoningLayer


logger = logging.getLogger(__name__)
API_VERSION = "1.0"  # frozen MVP API surface (ADR-0006); breaking changes bump this


class RetrieveRequest(BaseModel):
    query: str
    top_k: int = Field(default=3, ge=1, le=20)


class EvidenceItem(BaseModel):
    source_uri: str
    title: str | None = None
    excerpt: str | None = None
    section_title: str | None = None
    canonical_id: str | None = None


class RetrieveResult(BaseModel):
    title: str | None = None
    source_uri: str
    canonical_id: str
    evidence: list[EvidenceItem] = Field(default_factory=list)
    document_type: str | None = None


class RetrieveResponse(BaseModel):
    query: str
    answer: str
    results: list[RetrieveResult]


class AnswerResponse(BaseModel):
    query: str
    answer: str


class HealthResponse(BaseModel):
    status: str
    documents: int
    graph_nodes: int


class VersionResponse(BaseModel):
    api_version: str
    schema_version: str


class CompanyOut(BaseModel):
    slug: str
    name: str
    industry: str | None = None
    country: str | None = None


class SourceOut(BaseModel):
    source_type: str
    label: str
    document_type: str


class DocumentSummary(BaseModel):
    canonical_id: str
    title: str | None = None
    document_type: str
    source_uri: str
    published_at: str | None = None


class DocumentDetail(DocumentSummary):
    sections: list[dict[str, Any]] = Field(default_factory=list)
    entities: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    provenance: Provenance | None = None


class GraphNeighbor(BaseModel):
    relation: str
    target_kind: str
    target_key: str
    title: str | None = None


class GraphResponse(BaseModel):
    company_slug: str
    found: bool
    neighbors: list[GraphNeighbor] = Field(default_factory=list)


class DashboardResponse(BaseModel):
    companies: int
    documents: int
    events: int
    material_changes: int
    latest_documents: list[DocumentSummary] = Field(default_factory=list)
    recent_events: list[ExtractedEvent] = Field(default_factory=list)
    recent_risks: list[ExtractedEvent] = Field(default_factory=list)
    recent_opportunities: list[ExtractedEvent] = Field(default_factory=list)


RISK_EVENT_CATEGORIES = {"risk", "regulatory", "litigation", "supply_chain"}
OPPORTUNITY_EVENT_CATEGORIES = {"opportunity", "product", "capital_allocation"}


class RegisterRequest(BaseModel):
    email: str
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    token: str
    email: str


class UserOut(BaseModel):
    email: str
    created_at: str | None = None
    role: str = "analyst"


class ResetRequest(BaseModel):
    email: str


class ResetIssued(BaseModel):
    # The reset token is normally delivered by email; for the offline MVP it is
    # returned here so the flow is testable end to end.
    email: str
    reset_token: str | None = None


class ResetConfirm(BaseModel):
    token: str
    password: str


class AnalystRequest(BaseModel):
    question: str


class PortfolioCreate(BaseModel):
    name: str
    holdings: list[Holding] = Field(default_factory=list)


class HoldingsResolveRequest(BaseModel):
    """A raw brokerage/holdings CSV to resolve against the coverage universe. The
    frontend reads the user's uploaded file and posts its text here; the transport
    is JSON to stay consistent with the rest of the evidence-first API."""

    csv: str = Field(min_length=1)


class HoldingsUploadRequest(BaseModel):
    """Resolve a holdings CSV *and* persist the matched positions as a user-scoped
    portfolio. Unresolved rows are surfaced in the report, never persisted as
    holdings (a holding must point at a real Company node)."""

    name: str = Field(min_length=1)
    csv: str = Field(min_length=1)


class PortfolioUploadResult(BaseModel):
    """The outcome of an upload: the persisted portfolio (resolved holdings only)
    plus the full resolve report so the caller can show what did *not* match."""

    portfolio: Portfolio
    report: ResolveReport


class WorkspaceCreate(BaseModel):
    name: str
    members: list[str] = Field(default_factory=list)


class WorkspaceItemCreate(BaseModel):
    type: str
    title: str
    body: str = ""
    ref: str | None = None


class MemberAdd(BaseModel):
    email: str


class ApiKeyCreate(BaseModel):
    name: str


class SavedSearchCreate(BaseModel):
    name: str
    query: str
    source_type: str | None = None


class QuotaStatus(BaseModel):
    plan: str
    plan_label: str
    max_api_calls_per_day: int
    api_calls_today: int
    api_calls_remaining: int
    max_watchlists: int
    watchlists_used: int
    enforced: bool


class OrgCreate(BaseModel):
    name: str
    plan: str = "free"


class PlanUpdate(BaseModel):
    plan: str


class WatchlistCreate(BaseModel):
    name: str
    items: list[WatchItem] = Field(default_factory=list)


class WatchlistCreated(BaseModel):
    watchlist: Watchlist
    notifications_created: int


class NotificationSummary(BaseModel):
    total: int
    unread: int


class EvaluateAllResult(BaseModel):
    watchlists_evaluated: int
    notifications_created: int


@dataclass
class WorkspaceServices:
    """Portfolio-Exposure workspace services, held apart from the platform app-state.

    Phase 3 (docs/PLATFORM.md §9): the product-specific services no longer sit flat on
    ``_AppState``; the workspace routers reach them through ``state.workspace``. Built by
    ``apps.workspace_runtime``. (``engine``/``graph``/``intelligence`` stay on ``_AppState``
    as the shared core — read by both the platform and workspace routers.)
    """

    watchlists: SqliteWatchlistStore | None = None
    portfolios: SqlitePortfolioStore | None = None
    prices: PriceService | None = None
    macro: MacroService | None = None
    news: NewsService | None = None


@dataclass
class _AppState:
    engine: Any
    graph: KnowledgeGraphStore
    intelligence: SqliteIntelligenceStore | None = None
    auth: AuthService | None = None
    workspaces: SqliteWorkspaceStore | None = None
    audit: SqliteAuditStore | None = None
    api_keys: SqliteApiKeyStore | None = None
    dead_letters: SqliteDeadLetterStore | None = None
    saved_searches: SqliteSavedSearchStore | None = None
    orgs: SqliteOrgStore | None = None
    usage: SqliteUsageStore | None = None
    workspace: WorkspaceServices = field(default_factory=WorkspaceServices)


def _all_documents(engine: Any) -> list[NormalizedDocument]:
    if isinstance(engine, HybridRetrievalEngine):
        return engine.all_documents()
    documents = getattr(engine, "documents", [])
    return list(documents) if isinstance(documents, list) else []


def _document_count(engine: Any) -> int:
    return len(_all_documents(engine))


def _to_summary(document: NormalizedDocument) -> DocumentSummary:
    return DocumentSummary(
        canonical_id=document.canonical_id,
        title=document.title,
        document_type=document.document_type,
        source_uri=document.source_uri,
        published_at=str(document.published_at) if document.published_at is not None else None,
    )


def create_app(
    retrieval_engine: Any | None = None,
    graph_store: KnowledgeGraphStore | None = None,
    *,
    intelligence_store: SqliteIntelligenceStore | None = None,
    auth_service: AuthService | None = None,
    watchlist_store: SqliteWatchlistStore | None = None,
    portfolio_store: SqlitePortfolioStore | None = None,
    workspace_store: SqliteWorkspaceStore | None = None,
    audit_store: SqliteAuditStore | None = None,
    api_key_store: SqliteApiKeyStore | None = None,
    dead_letter_store: SqliteDeadLetterStore | None = None,
    saved_search_store: SqliteSavedSearchStore | None = None,
    org_store: SqliteOrgStore | None = None,
    usage_store: SqliteUsageStore | None = None,
    require_auth: bool = True,
    expose_reset_token: bool = False,
    load_from_storage: bool = False,
) -> FastAPI:
    """Compose the serving app: a shared PLATFORM router + registry-driven WORKSPACE routers.

    Phase 2 of the platform/workspace split (ADR-0013, docs/PLATFORM.md §6): every route
    is registered on one of two boundary routers instead of directly on the app —

    - ``plat`` — the shared platform surface: auth, reference corpus & retrieval, saved
      searches & compare, generic entity-graph reads (``/entities``, ``/graph/company``,
      ``/graph/company-network``, co-executives, resolution), collaboration workspaces,
      API keys, admin/RBAC, orgs/plans/billing, run status & source monitoring, document
      summaries, and the admin console.
    - ``pe`` — the Portfolio-Exposure workspace surface: the exposure engine
      (``/graph/*-exposure``, jurisdictions, sectors, market tiers, gics, commodities,
      debt), ownership/funds/screening/coverage reads, portfolio market data, watchlists
      & notifications, portfolios, and the company-scoped analyst/signals/dashboard.

    The routers are mounted at the end via the ``composition`` registry
    (``enabled_workspaces()``), not a hard-coded list — a new workspace edition is a
    registry entry + its router, not an edit here. Behavior-preserving: routers carry no
    prefix, so every path and method is identical to the pre-split surface (asserted by
    ``tests/test_api_composition.py`` and the route table). Per-route boundary is visible
    in the ``@plat``/``@pe`` decorators below.
    """
    settings = get_settings()
    # Fail closed: enforcement is on unless a caller explicitly opts out (tests).
    enforce_auth = require_auth or load_from_storage
    enforce_quotas = settings.enforce_quotas
    state = _AppState(
        engine=retrieval_engine if retrieval_engine is not None else HybridRetrievalEngine(),
        graph=graph_store if graph_store is not None else InMemoryKnowledgeGraphStore(),
        intelligence=intelligence_store,
        auth=auth_service,
        workspaces=workspace_store,
        audit=audit_store,
        api_keys=api_key_store,
        dead_letters=dead_letter_store,
        saved_searches=saved_search_store,
        orgs=org_store,
        usage=usage_store,
        workspace=WorkspaceServices(
            watchlists=watchlist_store,
            portfolios=portfolio_store,
            prices=build_price_service(settings),
            macro=build_macro_service(settings),
            news=build_news_service(settings),
        ),
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        if load_from_storage:
            state.engine = load_engine(settings)
            state.graph = load_graph_store(settings)
            state.intelligence = build_intelligence_store(settings)
            state.auth = build_auth_service(settings)
            state.workspace.watchlists = build_watchlist_store(settings)
            state.workspace.portfolios = build_portfolio_store(settings)
            state.workspaces = build_workspace_store(settings)
            state.audit = build_audit_store(settings)
            state.api_keys = build_api_key_store(settings)
            state.dead_letters = build_dead_letter_store(settings)
            state.saved_searches = build_saved_search_store(settings)
            state.orgs = build_org_store(settings)
            state.usage = build_usage_store(settings)
        yield

    app = FastAPI(title="Coruscant API", version=API_VERSION, lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Phase 2 (docs/PLATFORM.md §6): the app is composed from a shared PLATFORM router
    # plus one router per WORKSPACE (registry: coruscant.apps.composition). `plat` = the
    # shared platform surface; `pe` = the Portfolio-Exposure workspace. Behavior-preserving
    # — no prefixes, so every route path is unchanged; only the owning router differs.
    plat = APIRouter()
    workspace_routers: dict[str, APIRouter] = {
        ws.slug: APIRouter() for ws in composition.WORKSPACES
    }
    pe = workspace_routers[composition.PORTFOLIO_EXPOSURE.slug]

    def require_user(request: Request) -> StoredUser | None:
        if not enforce_auth:
            return None
        header = request.headers.get("Authorization", "")
        token = header[7:].strip() if header[:7].lower() == "bearer " else ""
        user = state.auth.user_from_token(token) if state.auth and token else None
        if user is None:
            # Programmatic / third-party access via an API key (X-API-Key).
            api_key = request.headers.get("X-API-Key", "")
            if api_key and state.api_keys is not None and state.auth is not None:
                owner = state.api_keys.resolve(api_key)
                if owner:
                    user = state.auth.store.get(owner)
        if user is None:
            raise HTTPException(status_code=401, detail="authentication required")
        return user

    protected = [Depends(require_user)]

    def current_email(user: StoredUser | None = Depends(require_user)) -> str:
        # When auth is enforced, user is a StoredUser; when disabled (tests) all
        # callers share a single anonymous scope.
        return user.email if user is not None else "anonymous@local"

    def require_admin(request: Request) -> StoredUser:
        user = require_user(request)
        if not enforce_auth:
            return user or StoredUser(
                email="anonymous@local", password_hash="", created_at="", role="admin"
            )
        if user is None or user.role != "admin":
            raise HTTPException(status_code=403, detail="admin role required")
        return user

    def _audit(email: str, action: str, detail: str = "") -> None:
        if state.audit is not None:
            state.audit.record(
                email, action, detail, created_at=datetime.now(tz=timezone.utc).isoformat()
            )

    def _record_usage(email: str, action: str) -> None:
        if state.usage is not None:
            state.usage.record(email, action, created_at=datetime.now(tz=timezone.utc).isoformat())

    def _today_since() -> str:
        # Quotas are per-day; count usage since today's UTC midnight.
        return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT00:00:00+00:00")

    def _quota_enforced() -> bool:
        # Enforcement is a multi-tenant concern: only active when an organization
        # store is configured (a real deployment). Single-tenant / offline use —
        # where no org store is wired — is never throttled, so existing behavior
        # is preserved.
        return enforce_quotas and state.orgs is not None

    def _effective_plan(email: str) -> Plan:
        # The most generous plan across the orgs the user belongs to; free by
        # default. Counting usage per-user keeps throttling simple and fair.
        plan = PLANS[DEFAULT_PLAN]
        if state.orgs is not None:
            for org in state.orgs.list_orgs(email):
                candidate = PLANS.get(org.plan, plan)
                if candidate.max_api_calls_per_day > plan.max_api_calls_per_day:
                    plan = candidate
        return plan

    def _api_calls_today(email: str) -> int:
        if state.usage is None:
            return 0
        return state.usage.summary([email], since_iso=_today_since()).total

    def _enforce_api_quota(email: str) -> None:
        if not _quota_enforced():
            return
        plan = _effective_plan(email)
        if _api_calls_today(email) >= plan.max_api_calls_per_day:
            raise HTTPException(
                status_code=429,
                detail=(
                    f"daily API quota reached ({plan.max_api_calls_per_day}/day on the "
                    f"{plan.label} plan); upgrade the plan or retry tomorrow"
                ),
            )

    def _enforce_watchlist_quota(email: str) -> None:
        if not _quota_enforced() or state.workspace.watchlists is None:
            return
        plan = _effective_plan(email)
        if len(state.workspace.watchlists.list_watchlists(email)) >= plan.max_watchlists:
            raise HTTPException(
                status_code=429,
                detail=f"watchlist limit reached ({plan.max_watchlists} on the {plan.label} plan)",
            )

    def _auth() -> AuthService:
        if state.auth is None:
            raise HTTPException(status_code=503, detail="authentication is not configured")
        return state.auth

    def _watchlists() -> SqliteWatchlistStore:
        if state.workspace.watchlists is None:
            raise HTTPException(status_code=503, detail="watchlists are not configured")
        return state.workspace.watchlists

    def _evaluate_watchlist(email: str, watchlist: Watchlist) -> int:
        if state.intelligence is None:
            return 0
        graph = state.graph if isinstance(state.graph, KnowledgeGraphStore) else None
        notifications = match_watch_items(
            watchlist.items,
            events=state.intelligence.list_events(),
            change_sets=state.intelligence.list_change_sets(),
            companies=load_companies(settings.config_dir),
            graph=graph,
            now_iso=datetime.now(tz=timezone.utc).isoformat(),
        )
        return _watchlists().add_notifications(email, watchlist.id, notifications)

    # ---- [PLATFORM] Authentication ----------------------------------------------------

    @plat.post("/auth/register", response_model=TokenResponse)
    def register(body: RegisterRequest) -> TokenResponse:
        service = _auth()
        try:
            user = service.register(body.email, body.password)
        except AuthError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return TokenResponse(token=service.issue_token(user.email), email=user.email)

    @plat.post("/auth/login", response_model=TokenResponse)
    def login(body: LoginRequest) -> TokenResponse:
        service = _auth()
        try:
            token = service.authenticate(body.email, body.password)
        except AuthError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        email = body.email.strip().lower()
        _audit(email, "login", "password login")
        return TokenResponse(token=token, email=email)

    @plat.post("/auth/logout")
    def logout() -> dict[str, bool]:
        # Tokens are stateless; the client discards the token on logout.
        return {"ok": True}

    @plat.get("/auth/me", response_model=UserOut)
    def me(user: StoredUser | None = Depends(require_user)) -> UserOut:
        if user is None:
            raise HTTPException(status_code=401, detail="authentication required")
        return UserOut(email=user.email, created_at=user.created_at, role=user.role)

    @plat.post("/auth/reset/request", response_model=ResetIssued)
    def reset_request(body: ResetRequest) -> ResetIssued:
        # Always returns an identical generic response (no account enumeration).
        # The token is included only when explicitly enabled for offline/dev use.
        service = _auth()
        token = service.request_reset(body.email)
        return ResetIssued(
            email=body.email.strip().lower(),
            reset_token=token if expose_reset_token else None,
        )

    @plat.post("/auth/reset/confirm")
    def reset_confirm(body: ResetConfirm) -> dict[str, bool]:
        service = _auth()
        try:
            ok = service.confirm_reset(body.token, body.password)
        except AuthError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if not ok:
            raise HTTPException(status_code=400, detail="invalid or expired reset token")
        return {"ok": True}

    @plat.get("/version", response_model=VersionResponse)
    def version() -> VersionResponse:
        return VersionResponse(api_version=API_VERSION, schema_version=SCHEMA_VERSION)

    @plat.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(
            status="ok",
            documents=_document_count(state.engine),
            graph_nodes=state.graph.node_count(),
        )

    # ---- [PLATFORM] Reference corpus & retrieval ---------------------------
    @plat.get("/companies", response_model=list[CompanyOut], dependencies=protected)
    def companies() -> list[CompanyOut]:
        return [
            CompanyOut(slug=c.slug, name=c.name, industry=c.industry, country=c.country)
            for c in load_companies(settings.config_dir)
        ]

    @plat.get("/sources", response_model=list[SourceOut], dependencies=protected)
    def sources() -> list[SourceOut]:
        return [
            SourceOut(
                source_type=definition.source_type,
                label=definition.label,
                document_type=definition.document_type,
            )
            for definition in default_registry().definitions()
        ]

    @plat.get("/documents", response_model=list[DocumentSummary], dependencies=protected)
    def documents(company: str | None = None, source_type: str | None = None) -> list[DocumentSummary]:
        results: list[DocumentSummary] = []
        for document in _all_documents(state.engine):
            slug = document.metadata.get("company_slug")
            if company is not None and slug != company:
                continue
            if source_type is not None and document.metadata.get("source_name") != source_type:
                continue
            results.append(_to_summary(document))
        return results

    @plat.get("/documents/{canonical_id}", response_model=DocumentDetail, dependencies=protected)
    def document_detail(canonical_id: str) -> DocumentDetail:
        for document in _all_documents(state.engine):
            if document.canonical_id == canonical_id:
                return DocumentDetail(
                    **_to_summary(document).model_dump(),
                    sections=document.sections,
                    entities=document.entities,
                    metadata=document.metadata,
                    provenance=document.provenance,
                )
        raise HTTPException(status_code=404, detail="document not found")

    @plat.post("/retrieve", response_model=RetrieveResponse, dependencies=protected)
    def retrieve(request: RetrieveRequest, email: str = Depends(current_email)) -> RetrieveResponse:
        _enforce_api_quota(email)
        _record_usage(email, "retrieve")
        reasoning = TemplateReasoningLayer(state.engine)
        matches = state.engine.retrieve_with_evidence(request.query, top_k=request.top_k)
        results = [
            RetrieveResult(
                title=document.title,
                source_uri=document.source_uri,
                canonical_id=document.canonical_id,
                document_type=document.document_type,
                evidence=[EvidenceItem.model_validate(item.model_dump()) for item in evidence],
            )
            for document, evidence in matches
        ]
        return RetrieveResponse(
            query=request.query, answer=reasoning.answer(request.query), results=results
        )

    @plat.get("/answer", response_model=AnswerResponse, dependencies=protected)
    def answer(q: str) -> AnswerResponse:
        reasoning = TemplateReasoningLayer(state.engine)
        return AnswerResponse(query=q, answer=reasoning.answer(q))

    # ---- [PLATFORM] Saved searches & document comparison (analyst workflow) -----------

    def _searches() -> SqliteSavedSearchStore:
        if state.saved_searches is None:
            raise HTTPException(status_code=503, detail="saved searches are not configured")
        return state.saved_searches

    @plat.post("/saved-searches", response_model=SavedSearch, dependencies=protected)
    def create_saved_search(body: SavedSearchCreate, email: str = Depends(current_email)) -> SavedSearch:
        return _searches().create(
            email,
            body.name,
            body.query,
            body.source_type,
            created_at=datetime.now(tz=timezone.utc).isoformat(),
        )

    @plat.get("/saved-searches", response_model=list[SavedSearch], dependencies=protected)
    def list_saved_searches(email: str = Depends(current_email)) -> list[SavedSearch]:
        return _searches().list_searches(email)

    @plat.delete("/saved-searches/{search_id}", dependencies=protected)
    def delete_saved_search(search_id: str, email: str = Depends(current_email)) -> dict[str, bool]:
        if not _searches().delete(email, search_id):
            raise HTTPException(status_code=404, detail="saved search not found")
        return {"ok": True}

    @plat.get("/compare", response_model=ChangeSet, dependencies=protected)
    def compare(a: str, b: str) -> ChangeSet:
        """Side-by-side comparison of two documents: what is in `a` but not `b`."""
        by_id = {d.canonical_id: d for d in _all_documents(state.engine)}
        doc_a, doc_b = by_id.get(a), by_id.get(b)
        if doc_a is None or doc_b is None:
            raise HTTPException(status_code=404, detail="document not found")
        return ReferenceChangeDetector().diff(
            doc_a,
            doc_b,
            company_slug=str(doc_a.metadata.get("company_slug") or ""),
            source_type=str(doc_a.metadata.get("source_name") or doc_a.document_type),
        )

    @plat.get("/graph/company/{slug}", response_model=GraphResponse, dependencies=protected)
    def graph_company(slug: str) -> GraphResponse:
        node = state.graph.get_node("Company", slug)
        if node is None:
            return GraphResponse(company_slug=slug, found=False)
        neighbors = [
            GraphNeighbor(
                relation=edge.relation,
                target_kind=edge.target_kind,
                target_key=edge.target_key,
                title=str(target.properties.get("title")) if target is not None else None,
            )
            for edge, target in state.graph.neighbors("Company", slug)
        ]
        return GraphResponse(company_slug=slug, found=True, neighbors=neighbors)

    # ---- [SHARED] Entity graph / relationship intelligence (generic reads + exposure engine) --------------------------

    @plat.get("/entities", response_model=list[EntityRef], dependencies=protected)
    def entities(kind: str | None = None) -> list[EntityRef]:
        graph = state.graph
        if not isinstance(graph, KnowledgeGraphStore):
            return []
        return list_entities(graph, kind)

    @plat.get("/entities/{kind}/{key}", response_model=EntityProfile, dependencies=protected)
    def entity(kind: str, key: str) -> EntityProfile:
        graph = state.graph
        profile = (
            entity_profile(graph, kind, key)
            if isinstance(graph, KnowledgeGraphStore)
            else None
        )
        if profile is None:
            raise HTTPException(status_code=404, detail="entity not found")
        return profile

    @pe.get("/graph/exposure", response_model=ExposureResult, dependencies=protected)
    def exposure(country: str) -> ExposureResult:
        graph = state.graph
        if not isinstance(graph, KnowledgeGraphStore):
            return ExposureResult(country=country)
        return exposure_to_country(graph, country)

    @pe.get("/graph/jurisdictions", response_model=list[JurisdictionCount], dependencies=protected)
    def jurisdictions() -> list[JurisdictionCount]:
        """The menu of geographic 'events' — jurisdictions where holdings have a
        legal footprint, by exposed-company count."""
        graph = state.graph
        if not isinstance(graph, KnowledgeGraphStore):
            return []
        return list_jurisdictions(graph)

    @pe.get(
        "/graph/jurisdiction-exposure",
        response_model=JurisdictionExposure,
        dependencies=protected,
    )
    def jurisdiction_exposure_endpoint(jurisdiction: str) -> JurisdictionExposure:
        """Event in `jurisdiction` -> who is exposed, with the Exhibit-21 evidence."""
        graph = state.graph
        if not isinstance(graph, KnowledgeGraphStore):
            return JurisdictionExposure(jurisdiction=jurisdiction)
        return jurisdiction_exposure(graph, jurisdiction)

    @pe.get("/graph/sectors", response_model=list[SectorCount], dependencies=protected)
    def sectors() -> list[SectorCount]:
        """The menu of thematic 'events' — sectors by company count."""
        graph = state.graph
        if not isinstance(graph, KnowledgeGraphStore):
            return []
        return list_sectors(graph)

    @pe.get("/graph/sector-exposure", response_model=SectorExposure, dependencies=protected)
    def sector_exposure_endpoint(sector: str) -> SectorExposure:
        """Thematic event on a GICS level `sector` (a sector like Information
        Technology or a sub-industry like Semiconductors) -> who is in it."""
        graph = state.graph
        if not isinstance(graph, KnowledgeGraphStore):
            return SectorExposure(sector=sector)
        return sector_exposure(graph, sector)

    @plat.get("/graph/company-network", response_model=CompanyNetwork, dependencies=protected)
    def company_network_endpoint(company: str, max_hops: int = 2) -> CompanyNetwork:
        """Multi-hop co-mention neighbourhood of `company` out to `max_hops`, each
        reachable company with a shortest evidence chain. Orientation, not exposure
        magnitude. Exercises the graph store's native variable-length traversal."""
        graph = state.graph
        if not isinstance(graph, KnowledgeGraphStore):
            return CompanyNetwork(
                company=EntityRef(kind="Company", key=company, name=company), max_hops=max_hops
            )
        return company_network(graph, company, max_hops)

    @pe.get("/graph/gics-breakdown", response_model=list[GicsSector], dependencies=protected)
    def gics_breakdown_endpoint() -> list[GicsSector]:
        """The portfolio's GICS composition: sector -> sub-industry -> holdings."""
        graph = state.graph
        if not isinstance(graph, KnowledgeGraphStore):
            return []
        return gics_breakdown(graph)

    @pe.get("/graph/market-tiers", response_model=list[MarketTierCount], dependencies=protected)
    def market_tiers() -> list[MarketTierCount]:
        """The portfolio's MSCI Developed/Emerging/Frontier composition (pathway 4)."""
        graph = state.graph
        if not isinstance(graph, KnowledgeGraphStore):
            return []
        return list_market_tiers(graph)

    @pe.get(
        "/graph/market-tier-exposure",
        response_model=MarketTierExposure,
        dependencies=protected,
    )
    def market_tier_exposure_endpoint(tier: str) -> MarketTierExposure:
        """The holdings classified in MSCI market tier `tier` (DM/EM/FM)."""
        graph = state.graph
        if not isinstance(graph, KnowledgeGraphStore):
            return MarketTierExposure(tier=tier, label="")
        return market_tier_exposure(graph, tier)

    @plat.get("/graph/co-executives", response_model=CoExecutiveResult, dependencies=protected)
    def graph_co_executives() -> CoExecutiveResult:
        graph = state.graph
        if not isinstance(graph, KnowledgeGraphStore):
            return CoExecutiveResult()
        return co_executives(graph)

    @pe.get("/graph/screening", response_model=ScreeningOverview, dependencies=protected)
    def graph_screening(as_of: str | None = None) -> ScreeningOverview:
        """PEP/sanctions screening of the people in the graph. ``connected: false``
        until a screen has run; optional ``as_of=YYYY-MM-DD`` answers "was this
        flagged on that date?". Clearance is server-decided (public tier) — never a
        client-supplied parameter."""
        graph = state.graph
        if not isinstance(graph, KnowledgeGraphStore):
            return ScreeningOverview(connected=False)
        return screening_overview(graph, as_of=as_of)

    @plat.get("/graph/resolution", response_model=ResolutionOverview, dependencies=protected)
    def graph_resolution(as_of: str | None = None) -> ResolutionOverview:
        """GLEIF LEI-anchoring coverage: how much of the graph is resolved to a
        stable identity. ``connected: false`` until an anchoring run; optional
        ``as_of=YYYY-MM-DD``."""
        graph = state.graph
        if not isinstance(graph, KnowledgeGraphStore):
            return ResolutionOverview(connected=False)
        return resolution_overview(graph, as_of=as_of)

    @pe.get("/graph/coverage", response_model=CoverageOverview, dependencies=protected)
    def graph_coverage() -> CoverageOverview:
        """Whole-exchange coverage: the size and shape of the resolvable universe by
        market/exchange. ``connected: false`` until a coverage run has ingested one."""
        graph = state.graph
        if not isinstance(graph, KnowledgeGraphStore):
            return CoverageOverview(connected=False)
        return coverage_overview(graph)

    @pe.get("/graph/ownership", response_model=OwnershipOverview, dependencies=protected)
    def graph_ownership() -> OwnershipOverview:
        """Ownership substrate: declared ownership, beneficial ownership, and
        accounting consolidation as three distinct edge types (never conflated).
        Access-tier aware — beneficial-owner edges are withheld from the public tier
        and reported only as a ``restricted`` count. ``connected: false`` until an
        ownership run has ingested statements."""
        graph = state.graph
        if not isinstance(graph, KnowledgeGraphStore):
            return OwnershipOverview(connected=False)
        return ownership_overview(graph)

    @pe.get(
        "/graph/company/{company_key}/owners",
        response_model=CompanyOwners,
        dependencies=protected,
    )
    def graph_company_owners(company_key: str, as_of: str | None = None) -> CompanyOwners:
        """The ownership/control statements pointing at a company, access-tier
        filtered; optional ``as_of=YYYY-MM-DD`` for the bitemporal "who controlled it
        then?" query. Withheld (restricted-tier) edges are counted, not shown."""
        graph = state.graph
        if not isinstance(graph, KnowledgeGraphStore):
            return CompanyOwners(
                company_key=company_key,
                connected=False,
                owners=[],
                restricted=0,
                provider=None,
                observed_at=None,
                market=None,
            )
        return company_owners(graph, company_key, as_of=as_of)

    @pe.get(
        "/graph/company/{company_key}/ownership-chain",
        response_model=CompanyOwnershipChains,
        dependencies=protected,
    )
    def graph_ownership_chain(company_key: str, as_of: str | None = None) -> CompanyOwnershipChains:
        """UBO chain-following: the ownership chains leading up to a company, each hop
        keeping its own basis (declared / beneficial / consolidation — never conflated)
        and its evidence. Chains are labelled resolved / unresolved / cycle / restricted;
        a beneficial-owner terminal appears only where the data states it. Access-tier
        filtered; optional ``as_of=YYYY-MM-DD``."""
        graph = state.graph
        if not isinstance(graph, KnowledgeGraphStore):
            return CompanyOwnershipChains(
                company=EntityRef(kind="Company", key=company_key, name=company_key)
            )
        return ownership_chains(graph, company_key, as_of=as_of)

    @pe.get(
        "/graph/company/{company_key}/contagion",
        response_model=GroupContagion,
        dependencies=protected,
    )
    def graph_contagion(company_key: str, as_of: str | None = None) -> GroupContagion:
        """Group / UBO contagion: given a directly-exposed company, the group members
        that inherit exposure through shared control (owns / consolidates / beneficial-
        owner ties), each with the ownership evidence path back to the seed. Direct and
        inherited exposure are kept distinct; beneficial-owner ties are withheld from
        unprivileged callers and only counted. Access-tier filtered; optional ``as_of``."""
        graph = state.graph
        if not isinstance(graph, KnowledgeGraphStore):
            return GroupContagion(
                seed=EntityRef(kind="Company", key=company_key, name=company_key)
            )
        return group_contagion(graph, company_key, as_of=as_of)

    @pe.get("/graph/funds", response_model=list[FundRef], dependencies=protected)
    def graph_funds() -> list[FundRef]:
        """Funds whose 13F holdings have been ingested (the books events trace into)."""
        graph = state.graph
        if not isinstance(graph, KnowledgeGraphStore):
            return []
        return list_funds(graph)

    @pe.get("/graph/fund/{fund_key}", response_model=FundHoldings, dependencies=protected)
    def graph_fund(fund_key: str, as_of: str | None = None) -> FundHoldings:
        """A fund's covered holdings; optional ``as_of=YYYY-MM-DD``."""
        graph = state.graph
        result = fund_holdings(graph, fund_key, as_of=as_of) if isinstance(graph, KnowledgeGraphStore) else None
        if result is None:
            raise HTTPException(status_code=404, detail="fund not found")
        return result

    @pe.get("/graph/fund/{fund_key}/exposure", response_model=PortfolioExposure, dependencies=protected)
    def graph_fund_exposure(fund_key: str, pathway: str, term: str, as_of: str | None = None) -> PortfolioExposure:
        """Event → this fund's exposed holdings. ``pathway`` ∈ sector | jurisdiction
        | market_tier | commodity | country; ``term`` is the event (e.g. "Energy",
        "Taiwan", "crude-oil"). The north-star "does it touch my book?" query."""
        graph = state.graph
        result = (portfolio_exposure(graph, fund_key, pathway=pathway, term=term, as_of=as_of)
                  if isinstance(graph, KnowledgeGraphStore) else None)
        if result is None:
            raise HTTPException(status_code=404, detail="fund not found")
        return result

    @pe.get("/graph/fund/{fund_key}/profile", response_model=PortfolioProfile, dependencies=protected)
    def graph_fund_profile(fund_key: str, as_of: str | None = None) -> PortfolioProfile:
        """The shape of a fund's book — value-weighted by sector and market tier."""
        graph = state.graph
        result = (portfolio_profile(graph, fund_key, as_of=as_of)
                  if isinstance(graph, KnowledgeGraphStore) else None)
        if result is None:
            raise HTTPException(status_code=404, detail="fund not found")
        return result

    @pe.get("/instruments/commodities", response_model=list[CommodityRef], dependencies=protected)
    def instruments_commodities() -> list[CommodityRef]:
        """The commodity inventory, each with the GICS sectors it drives."""
        graph = state.graph
        if not isinstance(graph, KnowledgeGraphStore):
            return []
        return list_commodities(graph)

    @pe.get("/instruments/debt", response_model=list[DebtRef], dependencies=protected)
    def instruments_debt() -> list[DebtRef]:
        """The debt inventory (sovereign/corporate), each with its issuer country."""
        graph = state.graph
        if not isinstance(graph, KnowledgeGraphStore):
            return []
        return list_debt_instruments(graph)

    @pe.get("/graph/commodity-exposure", response_model=CommodityExposure, dependencies=protected)
    def commodity_exposure_endpoint(commodity: str) -> CommodityExposure:
        """Event on `commodity` -> the equity holdings exposed via the sectors it drives."""
        graph = state.graph
        if not isinstance(graph, KnowledgeGraphStore):
            return CommodityExposure(slug=commodity, commodity=commodity, category="")
        return commodity_exposure(graph, commodity)

    @pe.get("/graph/country-debt", response_model=list[DebtRef], dependencies=protected)
    def country_debt_endpoint(country: str) -> list[DebtRef]:
        """Debt instruments issued by `country` — the debt side of a country event."""
        graph = state.graph
        if not isinstance(graph, KnowledgeGraphStore):
            return []
        return debt_for_country(graph, country)

    @pe.get("/portfolio/prices", response_model=PortfolioPrices, dependencies=protected)
    def portfolio_prices() -> PortfolioPrices:
        """Live "since yesterday" quotes for the tracked universe (Yahoo, free).
        Returns connected=false when live prices are off — never a fabricated feed.
        The aggregate is equal-weighted across the sample (no holdings/weights yet)."""
        companies = load_companies(settings.config_dir)
        holdings_meta = [(c.slug, c.name, c.ticker_symbol) for c in companies]
        service = state.workspace.prices
        if service is None or not service.enabled:
            return summarize(holdings_meta, {}, total=len(companies), connected=False)
        quotes = service.quotes([symbol for _, _, symbol in holdings_meta])
        return summarize(holdings_meta, quotes, total=len(companies), connected=True)

    @pe.get("/portfolio/benchmark", response_model=PortfolioBenchmark, dependencies=protected)
    def portfolio_benchmark() -> PortfolioBenchmark:
        """Benchmark each GICS sector's holdings against its sector-index proxy
        (SPDR Select Sector ETF — free; the licensed MSCI index is a later feed).
        Reuses the live price feed, so it needs prices connected."""
        service = state.workspace.prices
        if service is None or not service.enabled:
            return PortfolioBenchmark(
                connected=False,
                note="Benchmarking needs live prices — set CORUSCANT_ENABLE_LIVE_PRICES=true.",
            )
        companies = load_companies(settings.config_dir)
        rows: list[tuple[str, str, str]] = []
        for company in companies:
            gics = company_gics(company.slug)
            if gics is not None:
                rows.append((company.slug, gics.sector, company.ticker_symbol))
        holding_quotes = service.quotes([symbol for _, _, symbol in rows])
        etf_quotes = service.quotes(benchmark_symbols([sector for _, sector, _ in rows]))
        sectors = sector_benchmarks(rows, holding_quotes, etf_quotes, total=len(rows))
        as_of = max(
            (q.as_of for q in {**holding_quotes, **etf_quotes}.values() if q.as_of),
            default=None,
        )
        return PortfolioBenchmark(
            connected=True,
            as_of=as_of,
            sectors=sectors,
            note=(
                "Portfolio side is equal-weighted (no position weights yet); sector index = "
                "SPDR Select Sector ETF proxy (GICS/S&P), not the licensed MSCI index."
            ),
        )

    @pe.get("/macro", response_model=CountryMacro, dependencies=protected)
    def country_macro(country: str) -> CountryMacro:
        """Country macro for the World tab: World Bank GDP/inflation + the
        benchmark-index move. Returns connected=false when the feed is off."""
        service = state.workspace.macro
        if service is None:
            return CountryMacro(country=country, connected=False, note="Macro not configured.")
        return service.country_macro(country)

    @pe.get("/news", response_model=NewsFeed, dependencies=protected)
    def news(country: str | None = None) -> NewsFeed:
        """Business-news headlines: global, or scoped to `country` (free GDELT).
        Returns connected=false when the feed is off — never fabricated headlines."""
        service = state.workspace.news
        if service is None:
            return NewsFeed(connected=False, scope="global", note="News not configured.")
        return service.headlines(scope="country" if country else "global", country=country)

    # ---- [WORKSPACE] Watchlists & notifications ----------------------------------------

    @pe.post("/watchlists", response_model=WatchlistCreated, dependencies=protected)
    def create_watchlist(body: WatchlistCreate, email: str = Depends(current_email)) -> WatchlistCreated:
        store = _watchlists()
        for item in body.items:
            if item.type not in WATCH_TYPES:
                raise HTTPException(status_code=400, detail=f"unknown watch type: {item.type}")
        _enforce_watchlist_quota(email)
        watchlist = store.create_watchlist(
            email, body.name, body.items, created_at=datetime.now(tz=timezone.utc).isoformat()
        )
        created = _evaluate_watchlist(email, watchlist)
        _audit(email, "watchlist.create", body.name)
        return WatchlistCreated(watchlist=watchlist, notifications_created=created)

    @pe.get("/watchlists", response_model=list[Watchlist], dependencies=protected)
    def list_watchlists(email: str = Depends(current_email)) -> list[Watchlist]:
        return _watchlists().list_watchlists(email)

    @pe.post("/watchlists/evaluate-all", response_model=EvaluateAllResult, dependencies=protected)
    def evaluate_all_watchlists(email: str = Depends(current_email)) -> EvaluateAllResult:
        """Re-evaluate all of the user's watchlists in one pass (the "check for
        updates" action). Idempotent: notification de-dup means an unchanged
        corpus yields zero new notifications."""
        watchlists = _watchlists().list_watchlists(email)
        created = sum(_evaluate_watchlist(email, wl) for wl in watchlists)
        return EvaluateAllResult(watchlists_evaluated=len(watchlists), notifications_created=created)

    @pe.delete("/watchlists/{watchlist_id}", dependencies=protected)
    def delete_watchlist(watchlist_id: str, email: str = Depends(current_email)) -> dict[str, bool]:
        if not _watchlists().delete_watchlist(email, watchlist_id):
            raise HTTPException(status_code=404, detail="watchlist not found")
        _audit(email, "watchlist.delete", watchlist_id)
        return {"ok": True}

    @pe.post("/watchlists/{watchlist_id}/evaluate", dependencies=protected)
    def evaluate_watchlist(watchlist_id: str, email: str = Depends(current_email)) -> dict[str, int]:
        watchlist = _watchlists().get_watchlist(email, watchlist_id)
        if watchlist is None:
            raise HTTPException(status_code=404, detail="watchlist not found")
        return {"notifications_created": _evaluate_watchlist(email, watchlist)}

    @pe.get("/notifications/summary", response_model=NotificationSummary, dependencies=protected)
    def notifications_summary(email: str = Depends(current_email)) -> NotificationSummary:
        total, unread = _watchlists().summary(email)
        return NotificationSummary(total=total, unread=unread)

    @pe.get("/notifications", response_model=list[Notification], dependencies=protected)
    def notifications(unread_only: bool = False, email: str = Depends(current_email)) -> list[Notification]:
        return _watchlists().list_notifications(email, unread_only=unread_only)

    @pe.post("/notifications/read-all", dependencies=protected)
    def read_all_notifications(email: str = Depends(current_email)) -> dict[str, int]:
        return {"marked": _watchlists().mark_all_read(email)}

    @pe.post("/notifications/{notification_id}/read", dependencies=protected)
    def read_notification(notification_id: str, email: str = Depends(current_email)) -> dict[str, bool]:
        if not _watchlists().mark_read(email, notification_id):
            raise HTTPException(status_code=404, detail="notification not found")
        return {"ok": True}

    # ---- [WORKSPACE] Portfolios --------------------------------------------------------

    def _portfolios() -> SqlitePortfolioStore:
        if state.workspace.portfolios is None:
            raise HTTPException(status_code=503, detail="portfolios are not configured")
        return state.workspace.portfolios

    @pe.post("/portfolios", response_model=Portfolio, dependencies=protected)
    def create_portfolio(body: PortfolioCreate, email: str = Depends(current_email)) -> Portfolio:
        portfolio = _portfolios().create_portfolio(
            email, body.name, body.holdings, created_at=datetime.now(tz=timezone.utc).isoformat()
        )
        _audit(email, "portfolio.create", body.name)
        return portfolio

    def _resolve_csv(csv_text: str) -> ResolveReport:
        """Parse a holdings CSV and resolve it against the coverage universe.
        Precision-first and deterministic (ticker → ISIN → SEDOL → org-name); rows
        that clear nothing are reported unresolved, never fabricated into a match."""

        graph = state.graph
        positions = parse_brokerage_csv(csv_text)
        if not isinstance(graph, KnowledgeGraphStore):
            # No graph to resolve against: honest empty resolution, all unresolved.
            return resolve_positions(InMemoryKnowledgeGraphStore(), positions)
        return resolve_positions(graph, positions)

    @pe.post("/portfolios/resolve", response_model=ResolveReport, dependencies=protected)
    def resolve_holdings(body: HoldingsResolveRequest) -> ResolveReport:
        """Dry-run: resolve an uploaded holdings CSV against coverage and report the
        rate + which rows matched (by ticker/ISIN/SEDOL/name) and which did not.
        Nothing is persisted — this is the preview before an upload."""

        return _resolve_csv(body.csv)

    @pe.post("/portfolios/upload", response_model=PortfolioUploadResult, dependencies=protected)
    def upload_portfolio(
        body: HoldingsUploadRequest, email: str = Depends(current_email)
    ) -> PortfolioUploadResult:
        """Upload a holdings file: resolve it against coverage, then persist the
        matched positions as a new user-scoped portfolio. Unresolved rows are
        returned in the report (labelled, never fabricated) so the caller can show
        exactly what could not be matched — they are not saved as holdings."""

        report = _resolve_csv(body.csv)
        # One holding per resolved Company node (two share classes of one issuer,
        # e.g. GOOG + GOOGL, collapse to one node); first label wins.
        holdings: list[Holding] = []
        seen: set[str] = set()
        for pos in report.positions:
            if pos.company_key is None or pos.company_key in seen:
                continue
            seen.add(pos.company_key)
            label = pos.input_name or pos.input_ticker or pos.input_isin or pos.input_sedol
            holdings.append(Holding(company_slug=pos.company_key, label=label))
        portfolio = _portfolios().create_portfolio(
            email, body.name, holdings, created_at=datetime.now(tz=timezone.utc).isoformat()
        )
        _audit(email, "portfolio.upload", f"{body.name}: {len(holdings)}/{report.total} resolved")
        return PortfolioUploadResult(portfolio=portfolio, report=report)

    @pe.get("/portfolios", response_model=list[Portfolio], dependencies=protected)
    def list_portfolios(email: str = Depends(current_email)) -> list[Portfolio]:
        return _portfolios().list_portfolios(email)

    @pe.delete("/portfolios/{portfolio_id}", dependencies=protected)
    def delete_portfolio(portfolio_id: str, email: str = Depends(current_email)) -> dict[str, bool]:
        if not _portfolios().delete_portfolio(email, portfolio_id):
            raise HTTPException(status_code=404, detail="portfolio not found")
        _audit(email, "portfolio.delete", portfolio_id)
        return {"ok": True}

    @pe.get("/portfolios/{portfolio_id}/briefing", response_model=PortfolioBriefing, dependencies=protected)
    def portfolio_briefing(portfolio_id: str, email: str = Depends(current_email)) -> PortfolioBriefing:
        portfolio = _portfolios().get_portfolio(email, portfolio_id)
        if portfolio is None:
            raise HTTPException(status_code=404, detail="portfolio not found")
        material: list[ChangeSet] = []
        events: list[ExtractedEvent] = []
        changed: set[str] = set()
        if state.intelligence is not None:
            for holding in portfolio.holdings:
                holding_changes = [
                    cs
                    for cs in state.intelligence.list_change_sets(company_slug=holding.company_slug)
                    if cs.material
                ]
                if holding_changes:
                    changed.add(holding.company_slug)
                material.extend(holding_changes)
                events.extend(state.intelligence.list_events(company_slug=holding.company_slug, limit=5))
        events.sort(key=lambda e: e.occurred_at or "", reverse=True)
        headline = (
            f"{len(changed)} of your {len(portfolio.holdings)} holdings had material changes."
            if portfolio.holdings
            else "No holdings yet."
        )
        return PortfolioBriefing(
            portfolio_id=portfolio.id,
            name=portfolio.name,
            holdings=portfolio.holdings,
            headline=headline,
            material_changes=material,
            recent_events=events[:15],
            companies_with_changes=len(changed),
        )

    # ---- [PLATFORM] Workspaces (team collaboration; see docs/PLATFORM.md §5) -----------------------------------

    def _workspaces() -> SqliteWorkspaceStore:
        if state.workspaces is None:
            raise HTTPException(status_code=503, detail="workspaces are not configured")
        return state.workspaces

    @plat.post("/workspaces", response_model=Workspace, dependencies=protected)
    def create_workspace(body: WorkspaceCreate, email: str = Depends(current_email)) -> Workspace:
        members = [m.strip().lower() for m in body.members if m.strip()]
        workspace = _workspaces().create_workspace(
            email, body.name, members, created_at=datetime.now(tz=timezone.utc).isoformat()
        )
        _audit(email, "workspace.create", workspace.name)
        return workspace

    @plat.get("/workspaces", response_model=list[Workspace], dependencies=protected)
    def list_workspaces(email: str = Depends(current_email)) -> list[Workspace]:
        return _workspaces().list_workspaces(email)

    @plat.get("/workspaces/{workspace_id}", response_model=Workspace, dependencies=protected)
    def get_workspace(workspace_id: str, email: str = Depends(current_email)) -> Workspace:
        workspace = _workspaces().get_workspace(email, workspace_id)
        if workspace is None:
            raise HTTPException(status_code=404, detail="workspace not found")
        return workspace

    @plat.post("/workspaces/{workspace_id}/items", response_model=WorkspaceItem, dependencies=protected)
    def add_workspace_item(
        workspace_id: str, body: WorkspaceItemCreate, email: str = Depends(current_email)
    ) -> WorkspaceItem:
        if body.type not in ITEM_TYPES:
            raise HTTPException(status_code=400, detail=f"unknown item type: {body.type}")
        item = WorkspaceItem(
            id=secrets.token_hex(8),
            type=body.type,
            title=body.title,
            body=body.body,
            ref=body.ref,
            author_email=email,
            created_at=datetime.now(tz=timezone.utc).isoformat(),
        )
        stored = _workspaces().add_item(email, workspace_id, item)
        if stored is None:
            raise HTTPException(status_code=404, detail="workspace not found")
        return stored

    @plat.delete("/workspaces/{workspace_id}/items/{item_id}", dependencies=protected)
    def delete_workspace_item(
        workspace_id: str, item_id: str, email: str = Depends(current_email)
    ) -> dict[str, bool]:
        if not _workspaces().delete_item(email, workspace_id, item_id):
            raise HTTPException(status_code=404, detail="item not found")
        return {"ok": True}

    @plat.post("/workspaces/{workspace_id}/members", dependencies=protected)
    def add_workspace_member(
        workspace_id: str, body: MemberAdd, email: str = Depends(current_email)
    ) -> dict[str, bool]:
        member = body.email.strip().lower()
        if not _workspaces().add_member(email, workspace_id, member):
            raise HTTPException(status_code=403, detail="only the owner can add members")
        _audit(email, "workspace.member.add", f"{workspace_id}:{member}")
        return {"ok": True}

    @plat.delete("/workspaces/{workspace_id}", dependencies=protected)
    def delete_workspace(workspace_id: str, email: str = Depends(current_email)) -> dict[str, bool]:
        if not _workspaces().delete_workspace(email, workspace_id):
            raise HTTPException(status_code=404, detail="workspace not found")
        _audit(email, "workspace.delete", workspace_id)
        return {"ok": True}

    # ---- [PLATFORM] API keys (programmatic / ecosystem access) ------------------------

    def _api_keys() -> SqliteApiKeyStore:
        if state.api_keys is None:
            raise HTTPException(status_code=503, detail="api keys are not configured")
        return state.api_keys

    @plat.post("/api-keys", response_model=ApiKeyCreated, dependencies=protected)
    def create_api_key(body: ApiKeyCreate, email: str = Depends(current_email)) -> ApiKeyCreated:
        created = _api_keys().create(email, body.name, created_at=datetime.now(tz=timezone.utc).isoformat())
        _audit(email, "api_key.create", body.name)
        return created

    @plat.get("/api-keys", response_model=list[ApiKey], dependencies=protected)
    def list_api_keys(email: str = Depends(current_email)) -> list[ApiKey]:
        return _api_keys().list_keys(email)

    @plat.delete("/api-keys/{key_id}", dependencies=protected)
    def revoke_api_key(key_id: str, email: str = Depends(current_email)) -> dict[str, bool]:
        if not _api_keys().revoke(email, key_id):
            raise HTTPException(status_code=404, detail="api key not found")
        _audit(email, "api_key.revoke", key_id)
        return {"ok": True}

    # ---- [PLATFORM] Admin (RBAC) ------------------------------------------------------

    # ---- [PLATFORM] Organizations, plans, usage & billing (commercialization) ---------

    def _orgs() -> SqliteOrgStore:
        if state.orgs is None:
            raise HTTPException(status_code=503, detail="organizations are not configured")
        return state.orgs

    @plat.post("/organizations", response_model=Organization, dependencies=protected)
    def create_organization(body: OrgCreate, email: str = Depends(current_email)) -> Organization:
        plan = body.plan if body.plan in PLANS else "free"
        # Membership is owner-only at creation. Additional members must come through
        # an explicit invite/accept flow (not yet built) — never from a client-supplied
        # list, which would let a caller inject a victim's email and read their usage
        # (aggregated into the org's billing summary).
        org = _orgs().create_org(
            email, body.name, plan, [], created_at=datetime.now(tz=timezone.utc).isoformat()
        )
        _audit(email, "organization.create", org.name)
        return org

    @plat.get("/organizations", response_model=list[Organization], dependencies=protected)
    def list_organizations(email: str = Depends(current_email)) -> list[Organization]:
        return _orgs().list_orgs(email)

    @plat.post("/organizations/{org_id}/plan", response_model=Organization, dependencies=protected)
    def set_org_plan(org_id: str, body: PlanUpdate, email: str = Depends(current_email)) -> Organization:
        if body.plan not in PLANS:
            raise HTTPException(status_code=400, detail=f"unknown plan: {body.plan}")
        if not _orgs().set_plan(email, org_id, body.plan):
            raise HTTPException(status_code=403, detail="only the owner can change the plan")
        org = _orgs().get_org(email, org_id)
        if org is None:
            raise HTTPException(status_code=404, detail="organization not found")
        _audit(email, "organization.plan", f"{org_id}:{body.plan}")
        return org

    @plat.get("/organizations/{org_id}/billing", response_model=BillingSummary, dependencies=protected)
    def org_billing(org_id: str, email: str = Depends(current_email)) -> BillingSummary:
        org = _orgs().get_org(email, org_id)
        if org is None:
            raise HTTPException(status_code=404, detail="organization not found")
        if org.owner_email != email:  # billing (members, usage, plan) is owner-only
            raise HTTPException(status_code=403, detail="only the owner can view billing")
        plan = PLANS.get(org.plan, PLANS["free"])
        # Quotas are per-day; count usage since today's UTC midnight, not all time.
        since = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT00:00:00+00:00")
        usage = state.usage.summary(org.members, since_iso=since) if state.usage else UsageSummary()
        return BillingSummary(
            organization_id=org.id,
            plan=plan,
            members=len(org.members),
            usage=usage,
            api_calls=usage.total,
            within_limits=usage.total <= plan.max_api_calls_per_day,
        )

    @plat.get("/usage", response_model=UsageSummary, dependencies=protected)
    def usage(email: str = Depends(current_email)) -> UsageSummary:
        return state.usage.summary([email]) if state.usage else UsageSummary()

    @plat.get("/quota", response_model=QuotaStatus, dependencies=protected)
    def quota(email: str = Depends(current_email)) -> QuotaStatus:
        """The caller's effective plan, today's usage, and remaining headroom.

        Always available so clients can render limits even where enforcement is
        off; ``enforced`` says whether the limits are actually applied here.
        """
        plan = _effective_plan(email)
        used = _api_calls_today(email)
        watchlists_used = (
            len(state.workspace.watchlists.list_watchlists(email)) if state.workspace.watchlists is not None else 0
        )
        return QuotaStatus(
            plan=plan.name,
            plan_label=plan.label,
            max_api_calls_per_day=plan.max_api_calls_per_day,
            api_calls_today=used,
            api_calls_remaining=max(0, plan.max_api_calls_per_day - used),
            max_watchlists=plan.max_watchlists,
            watchlists_used=watchlists_used,
            enforced=_quota_enforced(),
        )

    @plat.get("/admin/audit", response_model=list[AuditEntry])
    def admin_audit(_: StoredUser = Depends(require_admin), limit: int = 200) -> list[AuditEntry]:
        return state.audit.list_entries(limit=limit) if state.audit else []

    @plat.get("/admin/dead-letter", response_model=list[DeadLetterEntry])
    def admin_dead_letter(_: StoredUser = Depends(require_admin), limit: int = 200) -> list[DeadLetterEntry]:
        return state.dead_letters.list_entries(limit=limit) if state.dead_letters else []

    # ---- [SHARED] Intelligence (generic doc-intelligence + product analysis) ------------------------------------------------------

    @plat.get("/documents/{canonical_id}/summary", response_model=AISummary, dependencies=protected)
    def document_summary(canonical_id: str) -> AISummary:
        summary = state.intelligence.get_summary(canonical_id) if state.intelligence else None
        if summary is None:
            raise HTTPException(status_code=404, detail="summary not available")
        return summary

    @pe.get("/companies/{slug}/timeline", response_model=list[ExtractedEvent], dependencies=protected)
    def company_timeline(slug: str, limit: int = 50) -> list[ExtractedEvent]:
        if state.intelligence is None:
            return []
        return state.intelligence.list_events(company_slug=slug, limit=limit)

    @pe.get("/companies/{slug}/changes", response_model=list[ChangeSet], dependencies=protected)
    def company_changes(slug: str) -> list[ChangeSet]:
        if state.intelligence is None:
            return []
        return state.intelligence.list_change_sets(company_slug=slug)

    @plat.get("/status", response_model=RunStatus | None, dependencies=protected)
    def status() -> RunStatus | None:
        return load_run_status(settings)

    @plat.get("/monitoring", response_model=list[SourceReliability], dependencies=protected)
    def monitoring() -> list[SourceReliability]:
        return source_monitoring(settings)

    @pe.post("/analyst/{slug}", response_model=AnalysisReport, dependencies=protected)
    def analyst(slug: str, body: AnalystRequest, email: str = Depends(current_email)) -> AnalysisReport:
        _enforce_api_quota(email)
        _record_usage(email, "analyst")
        company = next((c for c in load_companies(settings.config_dir) if c.slug == slug), None)
        name = company.name if company else slug
        change_sets = state.intelligence.list_change_sets(company_slug=slug) if state.intelligence else []
        events = state.intelligence.list_events(company_slug=slug) if state.intelligence else []
        exposures = (
            company_country_exposures(state.graph, slug)
            if isinstance(state.graph, KnowledgeGraphStore)
            else []
        )
        def _run(analyst: LLMAnalyst | ReferenceAnalyst) -> AnalysisReport:
            return analyst.analyze(
                company_slug=slug,
                company_name=name,
                question=body.question,
                change_sets=change_sets,
                events=events,
                country_exposures=exposures,
            )

        # Reason with the configured "complex" model when one is set; otherwise
        # fall back to the deterministic evidence scan. Any LLM failure (no key,
        # bad JSON, model down) degrades gracefully to the same fallback.
        gateway = LLMGateway(settings.data_dir)
        if gateway.available("complex"):
            try:
                return _run(LLMAnalyst(gateway))
            except LLMError as exc:
                logger.warning("LLM analyst unavailable (%s); using deterministic fallback.", exc)
        return _run(ReferenceAnalyst())

    @pe.get("/signals/{slug}", response_model=list[Signal], dependencies=protected)
    def signals(slug: str) -> list[Signal]:
        company = next((c for c in load_companies(settings.config_dir) if c.slug == slug), None)
        name = company.name if company else slug
        documents = [d for d in _all_documents(state.engine) if d.metadata.get("company_slug") == slug]
        change_sets = state.intelligence.list_change_sets(company_slug=slug) if state.intelligence else []
        events = state.intelligence.list_events(company_slug=slug) if state.intelligence else []
        exposures = (
            company_country_exposures(state.graph, slug)
            if isinstance(state.graph, KnowledgeGraphStore)
            else []
        )
        return ReferenceSignalEngine().signals_for(
            company_slug=slug,
            company_name=name,
            documents=documents,
            change_sets=change_sets,
            events=events,
            country_exposures=exposures,
        )

    @pe.get("/dashboard", response_model=DashboardResponse, dependencies=protected)
    def dashboard() -> DashboardResponse:
        documents = _all_documents(state.engine)
        latest = sorted(documents, key=lambda d: d.published_at or "", reverse=True)[:6]
        events: list[ExtractedEvent] = []
        change_sets: list[ChangeSet] = []
        if state.intelligence is not None:
            events = state.intelligence.list_events(limit=40)
            change_sets = state.intelligence.list_change_sets()
        material_changes = sum(1 for cs in change_sets if cs.material)
        risks = [e for e in events if e.category in RISK_EVENT_CATEGORIES][:6]
        opportunities = [e for e in events if e.category in OPPORTUNITY_EVENT_CATEGORIES][:6]
        return DashboardResponse(
            companies=len(load_companies(settings.config_dir)),
            documents=len(documents),
            events=len(events),
            material_changes=material_changes,
            latest_documents=[_to_summary(d) for d in latest],
            recent_events=events[:8],
            recent_risks=risks,
            recent_opportunities=opportunities,
        )

    # ---- [PLATFORM] Admin console (single pane): model routing + customers --------------
    class ProviderOut(BaseModel):
        kind: str
        base_url: str
        label: str
        has_key: bool  # never expose the key itself

    class RouteOut(BaseModel):
        provider: str
        model: str

    class LLMConfigOut(BaseModel):
        tiers: list[str]
        tier_hints: dict[str, str]
        providers: dict[str, ProviderOut]
        routes: dict[str, RouteOut]
        available: dict[str, bool]  # per-tier: route resolves + key present

    class ProviderIn(BaseModel):
        kind: str
        base_url: str
        label: str = ""
        api_key: str | None = None  # None = keep existing; "" = clear; str = set

    class LLMConfigIn(BaseModel):
        providers: dict[str, ProviderIn]
        routes: dict[str, RouteOut]

    class CustomerOut(BaseModel):
        email: str
        role: str
        created_at: str
        api_calls: int

    def _llm_config_out(config: llm.LLMRouterConfig) -> LLMConfigOut:
        gateway = LLMGateway(settings.data_dir)
        return LLMConfigOut(
            tiers=list(llm.TIERS),
            tier_hints=llm.TIER_HINTS,
            providers={
                key: ProviderOut(kind=p.kind, base_url=p.base_url, label=p.label, has_key=bool(p.api_key))
                for key, p in config.providers.items()
            },
            routes={key: RouteOut(provider=r.provider, model=r.model) for key, r in config.routes.items()},
            available={tier: gateway.available(tier) for tier in llm.TIERS},
        )

    @plat.get("/admin/llm", response_model=LLMConfigOut)
    def admin_llm_get(_: StoredUser = Depends(require_admin)) -> LLMConfigOut:
        return _llm_config_out(llm.load_config(settings.data_dir))

    @plat.put("/admin/llm", response_model=LLMConfigOut)
    def admin_llm_put(body: LLMConfigIn, _: StoredUser = Depends(require_admin)) -> LLMConfigOut:
        current = llm.load_config(settings.data_dir)
        providers: dict[str, llm.ProviderConfig] = {}
        for key, incoming in body.providers.items():
            existing = current.providers.get(key)
            api_key = existing.api_key if existing else ""
            if incoming.api_key is not None:  # explicit set (or clear with "")
                api_key = incoming.api_key
            providers[key] = llm.ProviderConfig(
                kind=incoming.kind, base_url=incoming.base_url, label=incoming.label, api_key=api_key
            )
        routes = {key: llm.Route(provider=r.provider, model=r.model) for key, r in body.routes.items()}
        updated = llm.LLMRouterConfig(providers=providers, routes=routes)
        llm.save_config(settings.data_dir, updated)
        return _llm_config_out(updated)

    @plat.post("/admin/llm/test/{tier}")
    def admin_llm_test(tier: str, _: StoredUser = Depends(require_admin)) -> dict[str, object]:
        return LLMGateway(settings.data_dir).test(tier)

    @plat.get("/admin/customers", response_model=list[CustomerOut])
    def admin_customers(_: StoredUser = Depends(require_admin)) -> list[CustomerOut]:
        users = state.auth.store.list_users() if state.auth is not None else []
        out: list[CustomerOut] = []
        for user in users:
            calls = state.usage.summary([user.email]).total if state.usage is not None else 0
            out.append(
                CustomerOut(email=user.email, role=user.role, created_at=user.created_at, api_calls=calls)
            )
        return out

    # Compose the app: the shared platform surface + each enabled workspace's router,
    # mounted from the registry (coruscant.apps.composition) rather than a hard-coded list.
    app.include_router(plat)
    for ws in composition.enabled_workspaces():
        app.include_router(workspace_routers[ws.slug])

    return app


app = create_app(load_from_storage=True)
