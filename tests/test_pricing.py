"""Pricing is network-gated and must never fabricate a quote, so the tests pin:
parsing only succeeds on a complete payload, the service caches and stays off
when disabled, and the summary is honest (equal-weighted, missing symbols
dropped)."""

from __future__ import annotations

from coruscant.pricing import PriceService, Quote, parse_chart, summarize


def _chart(symbol: str, price: float, prev: float) -> dict:
    return {
        "chart": {
            "result": [
                {
                    "meta": {
                        "symbol": symbol,
                        "regularMarketPrice": price,
                        "chartPreviousClose": prev,
                        "currency": "USD",
                        "marketState": "REGULAR",
                        "regularMarketTime": 1_700_000_000,
                    }
                }
            ]
        }
    }


def test_parse_chart_builds_quote() -> None:
    q = parse_chart("AAPL", _chart("AAPL", 110.0, 100.0))
    assert q is not None
    assert q.symbol == "AAPL" and q.price == 110.0 and q.previous_close == 100.0
    assert q.change == 10.0 and q.change_pct == 10.0
    assert q.currency == "USD" and q.market_state == "REGULAR" and q.as_of is not None


def test_parse_chart_returns_none_when_incomplete() -> None:
    assert parse_chart("X", {"chart": {"result": []}}) is None
    assert parse_chart("X", {"chart": {"result": [{"meta": {"regularMarketPrice": 5}}]}}) is None  # no prev
    assert parse_chart("X", {"chart": {"result": [{"meta": {"regularMarketPrice": 5, "chartPreviousClose": 0}}]}}) is None


def test_price_service_disabled_never_fetches() -> None:
    calls: list[list[str]] = []

    def fetcher(symbols):
        calls.append(list(symbols))
        return {}

    svc = PriceService(enabled=False, fetcher=fetcher)
    assert svc.quotes(["AAPL"]) == {}
    assert calls == []  # disabled => no network


def test_price_service_caches_within_ttl() -> None:
    calls: list[list[str]] = []
    now = [1000.0]

    def fetcher(symbols):
        calls.append(list(symbols))
        return {s: Quote(symbol=s, price=1.0, previous_close=1.0, change=0.0, change_pct=0.0) for s in symbols}

    svc = PriceService(enabled=True, fetcher=fetcher, ttl_seconds=60.0, clock=lambda: now[0])
    svc.quotes(["AAPL", "MSFT"])
    svc.quotes(["AAPL", "MSFT"])  # within TTL → cache hit, no refetch
    assert len(calls) == 1
    now[0] += 120.0  # past TTL
    svc.quotes(["AAPL", "MSFT"])
    assert len(calls) == 2


def test_summarize_disconnected_and_connected() -> None:
    meta = [("aapl", "Apple", "AAPL"), ("msft", "Microsoft", "MSFT"), ("zzz", "Zeta", "ZZZ")]
    off = summarize(meta, {}, total=3, connected=False)
    assert off.connected is False and off.priced == 0 and "not connected" in (off.note or "")

    quotes = {
        "AAPL": Quote(symbol="AAPL", price=110.0, previous_close=100.0, change=10.0, change_pct=10.0),
        "MSFT": Quote(symbol="MSFT", price=95.0, previous_close=100.0, change=-5.0, change_pct=-5.0),
    }  # ZZZ missing → dropped, not fabricated
    on = summarize(meta, quotes, total=3, connected=True)
    assert on.connected is True and on.priced == 2 and on.total == 3
    assert [h.symbol for h in on.holdings] == ["AAPL", "MSFT"]  # sorted by change desc
    assert on.avg_change_pct == 2.5 and on.gainers == 1 and on.losers == 1
