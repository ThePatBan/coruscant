"""News service: builds the GDELT query for a scope (global business, or a
country), gates our request rate (GDELT 429s aggressively), and caches per key.

Network-gated by ``enabled``. On a miss while rate-limited, or on a failed fetch,
it serves whatever is cached and otherwise an empty feed with a note — never
fabricated headlines."""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence

from pydantic import BaseModel

from coruscant.news.gdelt import Article, fetch_articles

Fetcher = Callable[[str], Sequence[Article]]

# Business-relevance terms; ANDed with the scope (global or a country name).
_BUSINESS = "(economy OR markets OR stocks OR earnings OR \"central bank\" OR inflation)"


class NewsFeed(BaseModel):
    connected: bool
    scope: str  # "global" | "country"
    country: str | None = None
    articles: list[Article] = []
    note: str | None = None


def _query(scope: str, country: str | None) -> str:
    base = f"{_BUSINESS} sourcelang:english"
    if scope == "country" and country:
        # Quote the country so multi-word names ("United States") match as a phrase.
        return f'"{country}" {base}'
    return base


class NewsService:
    def __init__(
        self,
        *,
        enabled: bool,
        fetcher: Fetcher = fetch_articles,
        ttl_seconds: float = 900.0,
        min_interval_seconds: float = 6.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._enabled = enabled
        self._fetcher = fetcher
        self._ttl = ttl_seconds
        self._min_interval = min_interval_seconds
        self._clock = clock
        self._cache: dict[tuple[str, str], tuple[float, list[Article]]] = {}
        self._last_call: float | None = None

    @property
    def enabled(self) -> bool:
        return self._enabled

    def headlines(self, scope: str, country: str | None = None) -> NewsFeed:
        scope = "country" if (scope == "country" and country) else "global"
        if not self._enabled:
            return NewsFeed(
                connected=False,
                scope=scope,
                country=country,
                note="News not connected — set CORUSCANT_ENABLE_LIVE_NEWS=true.",
            )
        key = (scope, country or "")
        now = self._clock()
        cached = self._cache.get(key)
        if cached is not None and (now - cached[0]) <= self._ttl:
            return NewsFeed(connected=True, scope=scope, country=country, articles=cached[1])
        # Respect GDELT's rate limit without blocking the request: if we've called
        # too recently, serve stale cache or an empty feed with a note.
        if self._last_call is not None and (now - self._last_call) < self._min_interval:
            if cached is not None:
                return NewsFeed(connected=True, scope=scope, country=country, articles=cached[1])
            return NewsFeed(
                connected=True,
                scope=scope,
                country=country,
                note="News source is rate-limited right now — try again in a moment.",
            )
        self._last_call = now
        articles = list(self._fetcher(_query(scope, country)))
        if articles:
            self._cache[key] = (now, articles)
            return NewsFeed(connected=True, scope=scope, country=country, articles=articles)
        if cached is not None:
            return NewsFeed(connected=True, scope=scope, country=country, articles=cached[1])
        return NewsFeed(
            connected=True,
            scope=scope,
            country=country,
            note="No headlines available right now.",
        )
