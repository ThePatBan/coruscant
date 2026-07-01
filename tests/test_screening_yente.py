"""YenteScreeningProvider: the /match HTTP contract + the drop-in swap.

Hermetic — `urlopen` is mocked, so CI never needs a running yente/OpenSearch. The
canned payload encodes yente's real response shape, and the pipeline runs against
the yente provider unchanged, proving the swap keeps the graph model identical."""

from __future__ import annotations

import json
from unittest.mock import patch

from coruscant.common.types import GraphNode
from coruscant.knowledge_graph.memory import InMemoryKnowledgeGraphStore
from coruscant.knowledge_graph.resolution import Resolver
from coruscant.screening.pipeline import SANCTIONED, screen_people
from coruscant.screening.provider import ScreeningQuery, YenteScreeningProvider

# yente's real /match response shape (results carry the OpenSanctions/FtM fields).
_RESPONSE = {
    "responses": {
        "nicolas-maduro": {
            "status": 200,
            "results": [
                {
                    "id": "Q8452", "schema": "Person", "caption": "Nicolás Maduro",
                    "properties": {
                        "name": ["Nicolás Maduro Moros"], "topics": ["sanction", "role.pep"],
                        "country": ["ve"], "birthDate": ["1962-11-23"],
                    },
                    "datasets": ["us_ofac_sdn", "peps"],
                    "first_seen": "2017-08-01T00:00:00", "last_seen": "2026-01-01T00:00:00",
                    "score": 0.97, "match": True,
                }
            ],
        },
        "jane-analyst": {"status": 200, "results": []},
    }
}


class _FakeResp:
    def __init__(self, payload: object, code: int = 200) -> None:
        self._payload = payload
        self._code = code

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")

    def getcode(self) -> int:
        return self._code

    def __enter__(self) -> "_FakeResp":
        return self

    def __exit__(self, *exc: object) -> bool:
        return False


def test_screen_builds_match_request_and_parses_results() -> None:
    captured: dict[str, object] = {}

    def fake_urlopen(req, timeout=None):  # type: ignore[no-untyped-def]
        captured["url"] = req.full_url
        captured["method"] = req.get_method()
        captured["body"] = json.loads(req.data.decode("utf-8"))
        return _FakeResp(_RESPONSE)

    provider = YenteScreeningProvider("http://yente:8000/", dataset="sanctions")
    queries = [
        ScreeningQuery(kind="Person", key="nicolas-maduro", name="Nicolás Maduro", birth_date="1962-11-23"),
        ScreeningQuery(kind="Person", key="jane-analyst", name="Jane Analyst"),
    ]
    with patch("coruscant.screening.provider.urlopen", fake_urlopen):
        matches = provider.screen(queries)

    assert captured["method"] == "POST"
    assert "/match/sanctions" in str(captured["url"])
    body = captured["body"]
    assert body["queries"]["nicolas-maduro"]["schema"] == "Person"  # type: ignore[index]
    assert body["queries"]["nicolas-maduro"]["properties"]["name"] == ["Nicolás Maduro"]  # type: ignore[index]

    assert len(matches) == 1  # the empty-results query yields nothing
    match = matches[0]
    assert match.query.key == "nicolas-maduro" and match.score == 0.97
    assert match.record.is_sanctioned() and match.record.is_pep()
    assert match.corroborated is True  # birth year 1962 agreed


def test_connected_reflects_healthz() -> None:
    provider = YenteScreeningProvider("http://yente:8000")
    with patch("coruscant.screening.provider.urlopen", lambda *a, **k: _FakeResp({}, 200)):
        assert provider.connected() is True

    def boom(*a: object, **k: object) -> None:
        raise OSError("connection refused")

    with patch("coruscant.screening.provider.urlopen", boom):
        assert provider.connected() is False


def test_yente_provider_is_a_drop_in_through_the_pipeline() -> None:
    # The whole point of the seam: swapping the provider changes only the scorer;
    # the precision gate, resolver, and projected edges are identical.
    store = InMemoryKnowledgeGraphStore()
    store.upsert_node(GraphNode(kind="Person", key="nicolas-maduro",
                                properties={"name": "Nicolás Maduro", "birth_date": "1962-11-23"}))
    store.upsert_node(GraphNode(kind="Person", key="jane-analyst", properties={"name": "Jane Analyst"}))
    provider = YenteScreeningProvider("http://yente:8000")

    with patch("coruscant.screening.provider.urlopen", lambda *a, **k: _FakeResp(_RESPONSE)):
        summary = screen_people(store, provider, Resolver(), observed_at="2026-07-01", dataset="yente:default")

    assert summary.confirmed == 1 and summary.sanctioned == 1
    edge = store.edges_by_relation(SANCTIONED)[0]
    assert edge.properties["review_status"] == "confirmed"
    assert edge.properties["valid_from"] == "2017-08-01"  # bitemporal, from yente first_seen
