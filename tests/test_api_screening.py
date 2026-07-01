"""The /graph/screening endpoint: honest empty state + a post-screen panel."""

from __future__ import annotations

from fastapi.testclient import TestClient

from coruscant.apps.api import create_app
from coruscant.common.types import GraphNode
from coruscant.knowledge_graph.memory import InMemoryKnowledgeGraphStore
from coruscant.knowledge_graph.resolution import Resolver
from coruscant.screening.pipeline import screen_people
from coruscant.screening.provider import DeterministicScreeningProvider, WatchlistRecord


def test_screening_endpoint_reports_not_connected_before_a_run() -> None:
    app = create_app(graph_store=InMemoryKnowledgeGraphStore(), require_auth=False)
    body = TestClient(app).get("/graph/screening").json()
    assert body["connected"] is False
    assert body["confirmed"] == [] and body["needs_review"] == []


def test_screening_endpoint_serves_confirmed_and_review_after_a_run() -> None:
    graph = InMemoryKnowledgeGraphStore()
    graph.upsert_node(GraphNode(kind="Person", key="nicolas-maduro",
                                properties={"name": "Nicolás Maduro", "country": "Venezuela"}))
    graph.upsert_node(GraphNode(kind="Person", key="wang-wei", properties={"name": "Wang Wei"}))
    provider = DeterministicScreeningProvider([
        WatchlistRecord(id="os-9", name="Nicolas Maduro", topics=["sanction"],
                        countries=["Venezuela"], first_seen="2017-08-01T00:00:00"),
        WatchlistRecord(id="os-1", name="Wang Wei", topics=["sanction"]),
    ])
    screen_people(graph, provider, Resolver(), observed_at="2026-07-01", dataset="fixture")

    client = TestClient(create_app(graph_store=graph, require_auth=False))
    body = client.get("/graph/screening").json()
    assert body["connected"] is True and body["screened"] == 2
    assert body["sanctioned"] == 1 and len(body["confirmed"]) == 1
    assert body["confirmed"][0]["person"]["name"] == "Nicolás Maduro"
    assert len(body["needs_review"]) == 1  # the uncorroborated name-only match

    # Bitemporal: before the listing date, the confirmed hit is not returned.
    earlier = client.get("/graph/screening?as_of=2016-01-01").json()
    assert earlier["sanctioned"] == 0
