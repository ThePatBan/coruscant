"""The /graph/funds + /graph/fund endpoints."""

from __future__ import annotations

from fastapi.testclient import TestClient

from coruscant.apps.api import create_app
from coruscant.common.types import GraphNode
from coruscant.knowledge_graph.memory import InMemoryKnowledgeGraphStore
from coruscant.portfolio.holdings import ingest_fund_holdings
from coruscant.portfolio.thirteenf import FundFiling, FundHolding


def _client() -> TestClient:
    graph = InMemoryKnowledgeGraphStore()
    graph.upsert_node(GraphNode(kind="Company", key="apple", properties={"name": "Apple"}))
    filing = FundFiling(cik="1067983", name="Berkshire Hathaway Inc", period="2024-12-31",
                        holdings=[FundHolding(issuer="APPLE INC", value=75, shares=300)])
    ingest_fund_holdings(graph, filing, observed_at="2026-07-01")
    return TestClient(create_app(graph_store=graph, require_auth=False))


def test_funds_and_fund_holdings_endpoints() -> None:
    client = _client()
    funds = client.get("/graph/funds").json()
    assert len(funds) == 1 and funds[0]["key"] == "fund-1067983" and funds[0]["resolved"] == 1

    body = client.get("/graph/fund/fund-1067983").json()
    assert body["fund"]["name"] == "Berkshire Hathaway Inc"
    assert [h["company"]["key"] for h in body["holdings"]] == ["apple"]

    assert client.get("/graph/fund/nope").status_code == 404
