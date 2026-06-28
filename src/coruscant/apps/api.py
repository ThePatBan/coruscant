from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from coruscant.apps.runtime import build_intelligence_store, load_engine, load_graph_store
from coruscant.common.config import get_settings, load_companies
from coruscant.common.types import NormalizedDocument
from coruscant.infrastructure.intelligence_store import SqliteIntelligenceStore
from coruscant.ingestion.registry import default_registry
from coruscant.intelligence.models import ChangeSet
from coruscant.intelligence.models import DocumentSummary as AISummary
from coruscant.intelligence.models import ExtractedEvent
from coruscant.knowledge_graph.memory import InMemoryKnowledgeGraphStore
from coruscant.search.hybrid import HybridRetrievalEngine
from coruscant.search.reference import TemplateReasoningLayer


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
    data_dir: str


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


@dataclass
class _AppState:
    engine: Any
    graph: InMemoryKnowledgeGraphStore
    intelligence: SqliteIntelligenceStore | None = None


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
    graph_store: InMemoryKnowledgeGraphStore | None = None,
    *,
    intelligence_store: SqliteIntelligenceStore | None = None,
    load_from_storage: bool = False,
) -> FastAPI:
    settings = get_settings()
    state = _AppState(
        engine=retrieval_engine if retrieval_engine is not None else HybridRetrievalEngine(),
        graph=graph_store if graph_store is not None else InMemoryKnowledgeGraphStore(),
        intelligence=intelligence_store,
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        if load_from_storage:
            state.engine = load_engine(settings)
            state.graph = load_graph_store(settings)
            state.intelligence = build_intelligence_store(settings)
        yield

    app = FastAPI(title="Coruscant API", version="0.1.0", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(
            status="ok",
            documents=_document_count(state.engine),
            graph_nodes=len(state.graph.nodes),
            data_dir=str(settings.data_dir),
        )

    @app.get("/companies", response_model=list[CompanyOut])
    def companies() -> list[CompanyOut]:
        return [
            CompanyOut(slug=c.slug, name=c.name, industry=c.industry, country=c.country)
            for c in load_companies(settings.config_dir)
        ]

    @app.get("/sources", response_model=list[SourceOut])
    def sources() -> list[SourceOut]:
        return [
            SourceOut(
                source_type=definition.source_type,
                label=definition.label,
                document_type=definition.document_type,
            )
            for definition in default_registry().definitions()
        ]

    @app.get("/documents", response_model=list[DocumentSummary])
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

    @app.get("/documents/{canonical_id}", response_model=DocumentDetail)
    def document_detail(canonical_id: str) -> DocumentDetail:
        for document in _all_documents(state.engine):
            if document.canonical_id == canonical_id:
                return DocumentDetail(
                    **_to_summary(document).model_dump(),
                    sections=document.sections,
                    entities=document.entities,
                    metadata=document.metadata,
                )
        raise HTTPException(status_code=404, detail="document not found")

    @app.post("/retrieve", response_model=RetrieveResponse)
    def retrieve(request: RetrieveRequest) -> RetrieveResponse:
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

    @app.get("/answer", response_model=AnswerResponse)
    def answer(q: str) -> AnswerResponse:
        reasoning = TemplateReasoningLayer(state.engine)
        return AnswerResponse(query=q, answer=reasoning.answer(q))

    @app.get("/graph/company/{slug}", response_model=GraphResponse)
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

    # ---- Intelligence ------------------------------------------------------

    @app.get("/documents/{canonical_id}/summary", response_model=AISummary)
    def document_summary(canonical_id: str) -> AISummary:
        summary = state.intelligence.get_summary(canonical_id) if state.intelligence else None
        if summary is None:
            raise HTTPException(status_code=404, detail="summary not available")
        return summary

    @app.get("/companies/{slug}/timeline", response_model=list[ExtractedEvent])
    def company_timeline(slug: str, limit: int = 50) -> list[ExtractedEvent]:
        if state.intelligence is None:
            return []
        return state.intelligence.list_events(company_slug=slug, limit=limit)

    @app.get("/companies/{slug}/changes", response_model=list[ChangeSet])
    def company_changes(slug: str) -> list[ChangeSet]:
        if state.intelligence is None:
            return []
        return state.intelligence.list_change_sets(company_slug=slug)

    @app.get("/dashboard", response_model=DashboardResponse)
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

    return app


app = create_app(load_from_storage=True)
