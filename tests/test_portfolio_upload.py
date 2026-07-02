"""User-facing portfolio upload: resolve an uploaded holdings CSV against the
coverage universe and persist the matches as a portfolio.

The honesty contract mirrors the coverage layer: matching is deterministic
(ticker → ISIN → SEDOL → org-name), unresolved rows are surfaced explicitly and
never fabricated into a match, and only resolved positions become persisted
holdings. Hermetic — a small US coverage universe is ingested in-memory."""

from __future__ import annotations

from fastapi.testclient import TestClient

from coruscant.apps.api import create_app
from coruscant.coverage.pipeline import ingest_coverage
from coruscant.coverage.provider import UsEdgarCoverageProvider
from coruscant.common.types import GraphNode
from coruscant.knowledge_graph.memory import InMemoryKnowledgeGraphStore
from coruscant.portfolio.store import SqlitePortfolioStore

# A miniature US universe with a multi-class issuer (Alphabet: GOOGL + GOOG on one
# CIK) so the upload path exercises share-class resolution end to end.
_SEC_PAYLOAD = {
    "fields": ["cik", "name", "ticker", "exchange"],
    "data": [
        [320193, "Apple Inc.", "AAPL", "Nasdaq"],
        [789019, "Microsoft Corp", "MSFT", "Nasdaq"],
        [1652044, "Alphabet Inc.", "GOOGL", "Nasdaq"],
        [1652044, "Alphabet Inc.", "GOOG", "Nasdaq"],
    ],
}


def _client(tmp_path) -> TestClient:  # type: ignore[no-untyped-def]
    graph = InMemoryKnowledgeGraphStore()
    # A curated Apple node so a resolved holding can point at a friendly slug too.
    graph.upsert_node(GraphNode(kind="Company", key="aapl", properties={
        "name": "Apple Inc.", "cik": "320193", "source": "tracked"}))
    ingest_coverage(graph, UsEdgarCoverageProvider(payload=_SEC_PAYLOAD), observed_at="2026-07-01")
    db = f"sqlite:///{tmp_path / 'c.db'}"
    return TestClient(create_app(
        graph_store=graph, portfolio_store=SqlitePortfolioStore(db), require_auth=False))


_BROKERAGE_CSV = (
    "Symbol,Description,Quantity\n"
    "AAPL,Apple Inc,10\n"
    "GOOG,Alphabet Inc Class C,5\n"       # multi-class: resolves to the Alphabet node
    "GOOGL,Alphabet Inc Class A,5\n"      # ...as does the other class
    "ZZZZ,Mystery Holdings LLC,1\n"       # not covered → unresolved, surfaced
    "Total,,21\n"                          # footer, no identifiers → skipped by parser
)


def test_resolve_endpoint_reports_matches_and_unresolved(tmp_path) -> None:  # type: ignore[no-untyped-def]
    client = _client(tmp_path)
    report = client.post("/portfolios/resolve", json={"csv": _BROKERAGE_CSV}).json()
    # AAPL, GOOG, GOOGL resolve by ticker; ZZZZ is unresolved; the footer became a
    # row with a symbol-ish "Total" and also fails to resolve (honest, not dropped).
    assert report["by_ticker"] == 3
    assert report["resolved"] == 3
    unresolved = [p for p in report["positions"] if p["method"] == "unresolved"]
    assert any(p["input_ticker"] == "ZZZZ" for p in unresolved)
    # Both Alphabet share classes point at the single issuer node.
    alpha = [p["company_key"] for p in report["positions"]
             if p["input_ticker"] in ("GOOG", "GOOGL")]
    assert alpha == ["us-1652044", "us-1652044"]


def test_resolve_does_not_persist_anything(tmp_path) -> None:  # type: ignore[no-untyped-def]
    client = _client(tmp_path)
    client.post("/portfolios/resolve", json={"csv": _BROKERAGE_CSV})
    assert client.get("/portfolios").json() == []  # dry run only


def test_upload_persists_resolved_holdings_and_surfaces_unresolved(tmp_path) -> None:  # type: ignore[no-untyped-def]
    client = _client(tmp_path)
    result = client.post(
        "/portfolios/upload", json={"name": "My Brokerage", "csv": _BROKERAGE_CSV}
    ).json()

    # The report surfaces the full picture, including what did not match.
    assert result["report"]["resolved"] == 3
    assert any(p["input_ticker"] == "ZZZZ" and p["method"] == "unresolved"
               for p in result["report"]["positions"])

    # The persisted portfolio holds only resolved companies, deduped by node
    # (Alphabet's two share classes collapse to one holding), never the unmatched row.
    portfolio = result["portfolio"]
    assert portfolio["name"] == "My Brokerage"
    slugs = {h["company_slug"] for h in portfolio["holdings"]}
    assert slugs == {"aapl", "us-1652044"}
    assert "ZZZZ" not in str(portfolio["holdings"])

    # It is a real, retrievable user portfolio.
    listed = client.get("/portfolios").json()
    assert len(listed) == 1 and listed[0]["id"] == portfolio["id"]


def test_upload_with_no_matches_creates_empty_portfolio_honestly(tmp_path) -> None:  # type: ignore[no-untyped-def]
    client = _client(tmp_path)
    result = client.post(
        "/portfolios/upload",
        json={"name": "All Misses", "csv": "Symbol,Quantity\nNOPE1,1\nNOPE2,2\n"},
    ).json()
    assert result["report"]["total"] == 2 and result["report"]["resolved"] == 0
    assert result["portfolio"]["holdings"] == []  # nothing fabricated


def test_upload_requires_a_name_and_nonempty_csv(tmp_path) -> None:  # type: ignore[no-untyped-def]
    client = _client(tmp_path)
    assert client.post("/portfolios/upload", json={"name": "", "csv": _BROKERAGE_CSV}).status_code == 422
    assert client.post("/portfolios/upload", json={"name": "x", "csv": ""}).status_code == 422
