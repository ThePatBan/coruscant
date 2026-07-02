"""Live EDGAR ingestion + due-aware execution (Priority 1).

Covers the production seam without any real network: connector selection by the
runtime switch, due-only orchestration, dead-lettered failures (fetch + resolve),
deterministic normalization, fair-access rate limiting, and a full live-path round
trip through the orchestrator with a mocked SEC endpoint.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
from urllib.error import URLError

from coruscant.apps.runtime import build_schedule_store
from coruscant.apps.workspace_runtime import (
    build_registry,
    build_source_resolver,
    run_ingestion,
)
from coruscant.common.config import CompanyConfig, Settings, SourceSetting, load_entities
from coruscant.connectors.base import FetchRequest, SourceConnector
from coruscant.connectors.sec_edgar import (
    EdgarHttpConnector,
    RateLimiter,
    ReferenceEdgarConnector,
    normalize_edgar_filing,
)
from coruscant.common.errors import FetchError
from coruscant.common.types import SourceDocument
from coruscant.infrastructure.catalog import SqliteDocumentCatalog
from coruscant.infrastructure.dead_letter import SqliteDeadLetterStore
from coruscant.infrastructure.intelligence_store import SqliteIntelligenceStore
from coruscant.infrastructure.repositories import (
    FileSystemNormalizedDocumentRepository,
    FileSystemRawDocumentRepository,
)
from coruscant.ingestion.orchestrator import (
    IngestionOrchestrator,
    IngestionTarget,
    reference_targets,
)
from coruscant.ingestion.registry import SourceDefinition, SourceRegistry
from coruscant.exposure.sources import default_registry
from coruscant.knowledge_graph.memory import InMemoryKnowledgeGraphStore
from coruscant.knowledge_graph.persistence import load_graph
from coruscant.search.hybrid import HybridRetrievalEngine

UTC = timezone.utc
APPLE = CompanyConfig(slug="apple", name="Apple", industry="Technology")
PRIMARY = Path("tests/fixtures/sec_edgar/10-k-primary.txt").read_text()


# ---- connector selection (the runtime switch) ------------------------------


def test_default_registry_is_offline_by_default() -> None:
    connector = default_registry().get("sec_edgar").connector_factory()
    assert isinstance(connector, ReferenceEdgarConnector)  # no network in dev/test


def test_live_sources_switch_selects_http_connector() -> None:
    registry = default_registry(["sec_edgar"], edgar_user_agent="Coruscant/test contact@x")
    connector = registry.get("sec_edgar").connector_factory()
    assert isinstance(connector, EdgarHttpConnector)
    assert connector.user_agent == "Coruscant/test contact@x"  # config UA is wired through
    # A source with no live connector is left on its reference connector even if
    # requested live, so an over-broad switch can't break offline ingestion.
    assert not isinstance(
        default_registry(["news"]).get("news").connector_factory(), EdgarHttpConnector
    )


def test_build_source_resolver_offline_vs_live() -> None:
    offline = Settings(config_dir=Path("config"))
    assert build_source_resolver(offline) is reference_targets

    live = Settings(config_dir=Path("config"), live_sources=["sec_edgar"])
    resolver = build_source_resolver(live)
    company = CompanyConfig(
        slug="apple", name="Apple", sec_filings=["https://sec.gov/a.htm", "https://sec.gov/b.htm"]
    )
    targets = resolver(company, "sec_edgar", default_registry().get("sec_edgar"))
    assert [t.source_uri for t in targets] == ["https://sec.gov/a.htm", "https://sec.gov/b.htm"]
    assert [t.revision for t in targets] == [0, 1]  # oldest -> newest for change detection
    # A private company with no filings yields nothing — an observable zero.
    assert resolver(CompanyConfig(slug="spacex", name="SpaceX"), "sec_edgar", default_registry().get("sec_edgar")) == []
    # Non-EDGAR sources still resolve to reference targets even in live mode.
    assert resolver(company, "news", default_registry().get("news"))[0].source_uri.startswith("reference://")


# ---- rate limiting (SEC fair-access) ---------------------------------------


def test_rate_limiter_spaces_requests() -> None:
    clock = {"t": 0.0}
    sleeps: list[float] = []

    def mono() -> float:
        return clock["t"]

    def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        clock["t"] += seconds

    limiter = RateLimiter(0.5, monotonic=mono, sleep=sleep)
    limiter.acquire()  # first request: no wait
    limiter.acquire()  # immediately after: must wait the full interval
    assert sleeps == [0.5]


def test_rate_limiter_noop_when_disabled() -> None:
    sleeps: list[float] = []
    limiter = RateLimiter(0.0, sleep=lambda s: sleeps.append(s))
    limiter.acquire()
    limiter.acquire()
    assert sleeps == []


def test_http_connector_rate_limits_and_declares_user_agent(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    seen_user_agents: list[str | None] = []

    class _Counter:
        def __init__(self) -> None:
            self.calls = 0

        def acquire(self) -> None:
            self.calls += 1

    class _Response:
        headers = {"content-type": "text/html"}

        def read(self) -> bytes:
            return PRIMARY.encode("utf-8")

        def __enter__(self) -> "_Response":
            return self

        def __exit__(self, *exc: object) -> None:
            return None

    def fake_urlopen(request, timeout=30):  # type: ignore[no-untyped-def]
        seen_user_agents.append(request.get_header("User-agent"))
        if request.full_url.endswith("index.json"):
            raise URLError("no index in this test")
        return _Response()

    monkeypatch.setattr("coruscant.connectors.sec_edgar.urlopen", fake_urlopen)
    limiter = _Counter()
    connector = EdgarHttpConnector("Coruscant/9.9 ops@x", rate_limiter=limiter)
    document = connector.fetch(
        FetchRequest(company_slug="apple", source_name="sec_edgar", source_uri="https://sec.gov/a.htm")
    )
    assert limiter.calls >= 1  # every outbound request passed through the limiter
    assert all(ua == "Coruscant/9.9 ops@x" for ua in seen_user_agents)  # SEC-required UA on each
    assert "Apple designs devices and services." in document.raw_content


# ---- failure handling: explicit, observable, dead-lettered -----------------


class _BoomConnector(SourceConnector):
    def fetch(self, request: FetchRequest) -> SourceDocument:
        raise FetchError("SEC unreachable")


def _orchestrator(tmp_path: Path, registry: SourceRegistry, *, resolver=None) -> tuple[IngestionOrchestrator, SqliteDeadLetterStore]:  # type: ignore[no-untyped-def]
    db = f"sqlite:///{tmp_path / 'c.db'}"
    dead = SqliteDeadLetterStore(db)
    orch = IngestionOrchestrator(
        raw_repository=FileSystemRawDocumentRepository(tmp_path),
        normalized_repository=FileSystemNormalizedDocumentRepository(tmp_path),
        catalog=SqliteDocumentCatalog(db),
        graph_store=InMemoryKnowledgeGraphStore(),
        engine=HybridRetrievalEngine(),
        registry=registry,
        intelligence_store=SqliteIntelligenceStore(db),
        entities=load_entities(Path("config")),
        dead_letter_store=dead,
        resolver=resolver,
        max_attempts=2,
    )
    return orch, dead


def _sec_registry(connector_factory) -> SourceRegistry:  # type: ignore[no-untyped-def]
    registry = SourceRegistry()
    registry.register(
        SourceDefinition(
            source_type="sec_edgar",
            label="SEC EDGAR",
            document_type="filing",
            connector_factory=connector_factory,
            normalizer=normalize_edgar_filing,
            periods=(("FY2025 10-K", "2025-01-31"),),
            authority=0.98,
        )
    )
    return registry


def test_fetch_failure_is_dead_lettered_not_swallowed(tmp_path: Path) -> None:
    orch, dead = _orchestrator(tmp_path, _sec_registry(_BoomConnector))
    report = orch.run([APPLE], [SourceSetting(type="sec_edgar")])
    assert report.document_count == 0
    assert any("SEC unreachable" in err for err in report.errors)  # surfaced in the run report
    entries = dead.list_entries()
    assert entries and entries[0].source_type == "sec_edgar"
    assert entries[0].attempts == 2  # retried per max_attempts before dead-lettering


def test_resolution_failure_is_dead_lettered(tmp_path: Path) -> None:
    def boom_resolver(company, source_type, definition):  # type: ignore[no-untyped-def]
        raise RuntimeError("discovery endpoint 503")

    orch, dead = _orchestrator(
        tmp_path, _sec_registry(ReferenceEdgarConnector), resolver=boom_resolver
    )
    report = orch.run([APPLE], [SourceSetting(type="sec_edgar")])
    assert report.document_count == 0
    assert any("discovery endpoint 503" in err for err in report.errors)
    entries = dead.list_entries()
    assert entries and entries[0].period == "resolve"  # the resolve step is attributed


def test_live_http_fetch_failure_dead_letters_through_orchestrator(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    def fake_urlopen(request, timeout=30):  # type: ignore[no-untyped-def]
        raise URLError("connection refused")

    monkeypatch.setattr("coruscant.connectors.sec_edgar.urlopen", fake_urlopen)
    registry = build_registry(Settings(live_sources=["sec_edgar"], config_dir=Path("config")))
    company = CompanyConfig(slug="apple", name="Apple", sec_filings=["https://sec.gov/a.htm"])

    def resolver(c, source_type, definition):  # type: ignore[no-untyped-def]
        return [IngestionTarget("FY2025", "", "https://sec.gov/a.htm", 0)]

    orch, dead = _orchestrator(tmp_path, registry, resolver=resolver)
    report = orch.run([company], [SourceSetting(type="sec_edgar")])
    assert report.document_count == 0
    assert report.errors  # explicit
    assert dead.list_entries()  # observable / queryable


# ---- live happy path + deterministic normalization -------------------------


def _mock_sec(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    class _Response:
        headers = {"content-type": "text/html"}

        def read(self) -> bytes:
            return PRIMARY.encode("utf-8")

        def __enter__(self) -> "_Response":
            return self

        def __exit__(self, *exc: object) -> None:
            return None

    def fake_urlopen(request, timeout=30):  # type: ignore[no-untyped-def]
        if request.full_url.endswith("index.json"):
            raise URLError("no index.json in this test")
        return _Response()

    monkeypatch.setattr("coruscant.connectors.sec_edgar.urlopen", fake_urlopen)


def test_live_path_ingests_real_urls_and_is_deterministic(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _mock_sec(monkeypatch)
    url_prior = "https://www.sec.gov/Archives/edgar/data/320193/0001/aapl-2024.htm"
    url_current = "https://www.sec.gov/Archives/edgar/data/320193/0002/aapl-2025.htm"
    company = CompanyConfig(
        slug="apple", name="Apple", cik="320193", sec_filings=[url_prior, url_current]
    )
    settings = Settings(live_sources=["sec_edgar"], config_dir=Path("config"))
    registry = build_registry(settings)
    db = f"sqlite:///{tmp_path / 'c.db'}"
    catalog = SqliteDocumentCatalog(db)
    orch = IngestionOrchestrator(
        raw_repository=FileSystemRawDocumentRepository(tmp_path),
        normalized_repository=FileSystemNormalizedDocumentRepository(tmp_path),
        catalog=catalog,
        graph_store=InMemoryKnowledgeGraphStore(),
        engine=HybridRetrievalEngine(),
        registry=registry,
        intelligence_store=SqliteIntelligenceStore(db),
        entities=load_entities(Path("config")),
        resolver=build_source_resolver(settings),
    )
    report = orch.run([company], [SourceSetting(type="sec_edgar")])

    assert report.document_count == 2  # both real filings fetched over (mocked) HTTP
    docs = {d.source_uri: d for d in catalog.list_documents(source_type="sec_edgar")}
    assert set(docs) == {url_prior, url_current}
    # canonical_id is sha256(source_uri): stable, real-URL provenance.
    assert docs[url_current].canonical_id == sha256(url_current.encode("utf-8")).hexdigest()
    assert docs[url_current].provenance is not None
    assert docs[url_current].provenance.source_uri == url_current

    # Deterministic normalization: re-normalizing the same fetched bytes yields an
    # identical canonical id, section count, and stable section ids.
    raw = SourceDocument(
        source_type="sec_edgar",
        source_uri=url_current,
        fetched_at=datetime.now(tz=UTC),
        raw_content=PRIMARY,
        metadata={"form_type": "10-K", "company_slug": "apple", "filing_date": "2025-01-31"},
    )
    first = normalize_edgar_filing(raw)
    second = normalize_edgar_filing(raw)
    assert first.canonical_id == second.canonical_id
    assert [s["id"] for s in first.sections] == [s["id"] for s in second.sections]
    assert len(first.sections) == 3


# ---- due-aware execution ----------------------------------------------------


def _settings(tmp_path: Path) -> Settings:
    data_dir = tmp_path / "data"
    return Settings(
        data_dir=data_dir,
        config_dir=Path("config"),
        database_url=f"sqlite:///{data_dir / 'c.db'}",
    )


def test_due_only_run_skips_recently_run_sources(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    full = run_ingestion(settings)  # records last-run for every source
    assert full.document_count > 0

    just_after = datetime.now(tz=UTC) + timedelta(seconds=1)
    nothing_due = run_ingestion(settings, respect_due=True, now=just_after)
    assert nothing_due.document_count == 0  # cadence not elapsed -> nothing ingested

    far_future = datetime.now(tz=UTC) + timedelta(days=400)
    due_again = run_ingestion(settings, respect_due=True, now=far_future)
    assert due_again.document_count > 0  # cadence elapsed -> ingested again


def test_due_only_run_preserves_not_due_sources_in_graph(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    run_ingestion(settings)  # full
    nodes_full = len(load_graph(settings.graph_snapshot_path).nodes)

    # Make only sec_edgar due (everything else just ran).
    schedule = build_schedule_store(settings)
    now = datetime.now(tz=UTC)
    for definition in default_registry().definitions():
        schedule.record_run(definition.source_type, now.isoformat())
    schedule.record_run("sec_edgar", (now - timedelta(days=30)).isoformat())

    report = run_ingestion(settings, respect_due=True, now=now)
    assert set(report.source_types) == {"sec_edgar"}  # only the due source ran
    nodes_after = len(load_graph(settings.graph_snapshot_path).nodes)
    assert nodes_after >= nodes_full  # not-due sources' projections were not dropped
