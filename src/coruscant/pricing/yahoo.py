"""Free live equity quotes from Yahoo Finance's public chart endpoint.

A deliberately small, dependency-free client: one HTTP call per symbol against
the unauthenticated v8 chart API (the v7 batch-quote endpoint now demands a
crumb/cookie), run concurrently. It returns only what the endpoint actually
gives us — last price and prior close — and yields ``None`` for any symbol it
cannot fetch rather than inventing a number (the platform's first rule). It is
network-gated by the caller (:class:`coruscant.pricing.service.PriceService`),
so the offline/test path never reaches the network.

Yahoo's free endpoint is unofficial and rate-limited; this is the "not real-time"
prices source the World tab promises, fine for "since yesterday" orientation.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from pydantic import BaseModel

_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=2d&interval=1d"
# A browser-like UA; Yahoo 401s the default urllib agent.
_USER_AGENT = "Mozilla/5.0 (compatible; Coruscant/0.1; +contact@coruscant.local)"


class Quote(BaseModel):
    symbol: str
    price: float
    previous_close: float
    change: float
    change_pct: float
    currency: str | None = None
    market_state: str | None = None  # PRE | REGULAR | POST | CLOSED
    as_of: str | None = None  # ISO-8601 of the last regular-market print


def parse_chart(symbol: str, payload: dict[str, Any]) -> Quote | None:
    """Build a :class:`Quote` from a Yahoo chart response, or ``None`` if the
    response is missing the last price or a usable prior close (no fabrication)."""
    try:
        meta = payload["chart"]["result"][0]["meta"]
    except (KeyError, IndexError, TypeError):
        return None
    if not isinstance(meta, dict):
        return None
    price = meta.get("regularMarketPrice")
    prev = meta.get("chartPreviousClose")
    if not isinstance(prev, (int, float)):
        prev = meta.get("previousClose")
    if not isinstance(price, (int, float)) or not isinstance(prev, (int, float)) or prev == 0:
        return None
    change = float(price) - float(prev)
    epoch = meta.get("regularMarketTime")
    as_of = (
        datetime.fromtimestamp(int(epoch), tz=timezone.utc).isoformat()
        if isinstance(epoch, (int, float))
        else None
    )
    return Quote(
        symbol=str(meta.get("symbol") or symbol),
        price=float(price),
        previous_close=float(prev),
        change=change,
        change_pct=change / float(prev) * 100.0,
        currency=meta.get("currency") if isinstance(meta.get("currency"), str) else None,
        market_state=meta.get("marketState") if isinstance(meta.get("marketState"), str) else None,
        as_of=as_of,
    )


def _fetch_one(symbol: str, *, timeout: float) -> Quote | None:
    url = _CHART_URL.format(symbol=symbol)
    try:
        with urlopen(Request(url, headers={"User-Agent": _USER_AGENT}), timeout=timeout) as resp:
            payload = json.load(resp)
    except (HTTPError, URLError, TimeoutError, ValueError, OSError):
        return None
    return parse_chart(symbol, payload)


def fetch_quotes(
    symbols: Sequence[str], *, max_workers: int = 8, timeout: float = 10.0
) -> dict[str, Quote]:
    """Fetch quotes for ``symbols`` concurrently. Symbols that fail are simply
    absent from the result — callers treat a missing symbol as "no data"."""
    unique = list(dict.fromkeys(s for s in symbols if s))
    if not unique:
        return {}
    workers = max(1, min(max_workers, len(unique)))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        results = executor.map(lambda s: _fetch_one(s, timeout=timeout), unique)
        return {symbol: quote for symbol, quote in zip(unique, results) if quote is not None}
