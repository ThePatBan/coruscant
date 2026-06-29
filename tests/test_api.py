from coruscant.common.types import NormalizedDocument
from coruscant.apps.api import create_app
from coruscant.search.reference import InMemoryRetrievalEngine
from fastapi.testclient import TestClient


def test_health_route() -> None:
    app = create_app()
    routes = [route.path for route in app.routes]
    assert "/health" in routes


def test_retrieve_route_returns_evidence() -> None:
    engine = InMemoryRetrievalEngine()
    engine.add(
        NormalizedDocument(
            document_type="filing",
            source_uri="https://example.com/filing",
            canonical_id="abc123",
            title="Apple 10-K",
            sections=[
                {
                    "title": "Business",
                    "content": "Apple entered a new market",
                    "evidence": [
                        {
                            "source_uri": "https://example.com/filing",
                            "excerpt": "Apple entered a new market",
                            "section_title": "Business",
                        }
                    ],
                }
            ],
        )
    )
    client = TestClient(create_app(engine, require_auth=False))

    response = client.post("/retrieve", json={"query": "Apple market", "top_k": 3})

    assert response.status_code == 200
    body = response.json()
    assert "Apple 10-K" in body["answer"]
    assert body["results"][0]["evidence"][0]["section_title"] == "Business"
