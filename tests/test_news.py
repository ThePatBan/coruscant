"""News is network-gated and rate-limited, so the tests pin: parsing de-dupes and
skips junk, the query scopes by country, the service stays off when disabled, it
caches, and it degrades to a note (not fabricated headlines) when rate-limited."""

from __future__ import annotations

from coruscant.news import Article, parse_articles
from coruscant.news.service import NewsService, _query


def test_parse_articles_dedupes_and_skips_junk() -> None:
    payload = {
        "articles": [
            {
                "url": "http://a",
                "title": "  A headline  ",
                "domain": "a.com",
                "seendate": "20260701T113000Z",
                "sourcecountry": "France",
                "language": "English",
            },
            {"url": "http://a", "title": "duplicate url"},
            {"title": "no url — skipped"},
            {"url": "http://b", "title": "B headline"},
        ]
    }
    arts = parse_articles(payload, limit=10)
    assert [a.url for a in arts] == ["http://a", "http://b"]
    assert arts[0].title == "A headline"
    assert arts[0].published_at == "2026-07-01T11:30:00+00:00"
    assert arts[0].source_country == "France"
    assert parse_articles({"articles": "nope"}, limit=10) == []


def test_query_scopes_by_country() -> None:
    assert "sourcelang:english" in _query("global", None)
    assert "United States" not in _query("global", None)
    assert _query("country", "United States").startswith('"United States"')


def test_news_disabled() -> None:
    feed = NewsService(enabled=False).headlines("global")
    assert feed.connected is False and "not connected" in (feed.note or "")


def test_news_fetches_caches_and_rate_gates() -> None:
    calls = {"n": 0}
    now = [0.0]

    def fetcher(query: str):
        calls["n"] += 1
        return [Article(title="Markets rally", url="http://x")]

    svc = NewsService(
        enabled=True, fetcher=fetcher, ttl_seconds=100.0, min_interval_seconds=6.0, clock=lambda: now[0]
    )
    first = svc.headlines("global")
    assert first.connected is True and len(first.articles) == 1 and calls["n"] == 1
    svc.headlines("global")  # within TTL → cache hit, no refetch
    assert calls["n"] == 1


def test_news_rate_gate_degrades_without_fabricating() -> None:
    calls = {"n": 0}
    now = [0.0]

    def empty_fetcher(query: str):
        calls["n"] += 1
        return []  # e.g. GDELT 429 → no articles

    svc = NewsService(
        enabled=True, fetcher=empty_fetcher, ttl_seconds=100.0, min_interval_seconds=6.0, clock=lambda: now[0]
    )
    first = svc.headlines("country", "India")  # fetches, gets nothing
    assert first.articles == [] and calls["n"] == 1
    now[0] += 1.0  # within the rate window
    second = svc.headlines("country", "India")
    assert second.articles == [] and "rate-limited" in (second.note or "")
    assert calls["n"] == 1  # did NOT hit the source again
