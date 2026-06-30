"""Caching price service + portfolio-price summary.

The service caches Yahoo quotes with a TTL so the request path doesn't refetch on
every call, and is **network-gated**: when disabled (the default, and always in
tests/offline) it returns no quotes, so the endpoint reports ``connected=false``
instead of fabricating a feed. The fetcher is injectable for deterministic tests.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence

from pydantic import BaseModel

from coruscant.pricing.yahoo import Quote, fetch_quotes

Fetcher = Callable[[Sequence[str]], dict[str, Quote]]


class HoldingQuote(BaseModel):
    slug: str
    name: str
    symbol: str
    price: float
    change_pct: float
    currency: str | None = None


class PortfolioPrices(BaseModel):
    """The "since yesterday" view over the tracked universe. ``avg_change_pct`` is
    *equal-weighted* across the priced sample — honestly NOT a position-weighted
    return, because no holdings/weights exist yet (Phase 2 / 13F)."""

    connected: bool
    as_of: str | None = None
    priced: int = 0
    total: int = 0
    avg_change_pct: float | None = None
    gainers: int = 0
    losers: int = 0
    holdings: list[HoldingQuote] = []
    note: str | None = None


class PriceService:
    """TTL-cached, network-gated quote provider. ``enabled`` decides whether the
    fetcher is ever called; ``fetcher``/``clock`` are injectable for tests."""

    def __init__(
        self,
        *,
        enabled: bool,
        fetcher: Fetcher = fetch_quotes,
        ttl_seconds: float = 900.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._enabled = enabled
        self._fetcher = fetcher
        self._ttl = ttl_seconds
        self._clock = clock
        self._cache: dict[str, Quote] = {}
        self._fetched_at: float | None = None

    @property
    def enabled(self) -> bool:
        return self._enabled

    def quotes(self, symbols: Sequence[str]) -> dict[str, Quote]:
        if not self._enabled:
            return {}
        wanted = [s for s in symbols if s]
        now = self._clock()
        stale = self._fetched_at is None or (now - self._fetched_at) > self._ttl
        missing = any(s not in self._cache for s in wanted)
        if stale or missing:
            fetched = self._fetcher(wanted)
            if fetched:
                self._cache.update(fetched)
                self._fetched_at = now
        return {s: self._cache[s] for s in wanted if s in self._cache}


def summarize(
    holdings_meta: Sequence[tuple[str, str, str]],  # (slug, name, symbol)
    quotes: dict[str, Quote],
    *,
    total: int,
    connected: bool,
) -> PortfolioPrices:
    """Fold per-symbol quotes into the portfolio-level "since yesterday" view."""
    if not connected:
        return PortfolioPrices(
            connected=False,
            total=total,
            note="Live prices not connected — set CORUSCANT_ENABLE_LIVE_PRICES=true.",
        )
    holdings: list[HoldingQuote] = []
    for slug, name, symbol in holdings_meta:
        quote = quotes.get(symbol)
        if quote is None:
            continue
        holdings.append(
            HoldingQuote(
                slug=slug,
                name=name,
                symbol=quote.symbol,
                price=quote.price,
                change_pct=quote.change_pct,
                currency=quote.currency,
            )
        )
    holdings.sort(key=lambda h: h.change_pct, reverse=True)
    changes = [h.change_pct for h in holdings]
    avg = sum(changes) / len(changes) if changes else None
    as_of = max((q.as_of for q in quotes.values() if q.as_of), default=None)
    return PortfolioPrices(
        connected=bool(holdings),
        as_of=as_of,
        priced=len(holdings),
        total=total,
        avg_change_pct=avg,
        gainers=sum(1 for c in changes if c > 0),
        losers=sum(1 for c in changes if c < 0),
        holdings=holdings,
        note=(
            "Equal-weighted across the priced sample — not a position-weighted return "
            "(no holdings/weights yet)."
        )
        if holdings
        else "No quotes available right now.",
    )
