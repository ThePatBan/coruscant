"""Macro is network-gated and must not fabricate: parsing only succeeds on a real
value, the service stays off when disabled, an unmapped country is an honest
answer, and results cache."""

from __future__ import annotations

from coruscant.macro import MacroService, fetch_indicator  # noqa: F401 (import surface)
from coruscant.macro.service import MacroService as _Svc
from coruscant.macro.worldbank import Indicator, parse_indicator
from coruscant.pricing.yahoo import Quote


def test_parse_indicator() -> None:
    payload = [{"page": 1}, [{"date": "2024", "value": 2.79}]]
    ind = parse_indicator("NY.GDP.MKTP.KD.ZG", payload)
    assert ind is not None and ind.value == 2.79 and ind.year == "2024"
    # Empty / null most-recent value -> None, never zero-filled.
    assert parse_indicator("X", [{}, [{"date": "2024", "value": None}]]) is None
    assert parse_indicator("X", [{}, []]) is None


def _indicators(country_code: str, indicator: str) -> Indicator | None:
    table = {
        ("US", "NY.GDP.MKTP.KD.ZG"): Indicator(code=indicator, value=2.8, year="2024"),
        ("US", "FP.CPI.TOTL.ZG"): Indicator(code=indicator, value=2.9, year="2024"),
    }
    return table.get((country_code, indicator))


def _index(symbols) -> dict[str, Quote]:
    return {"^GSPC": Quote(symbol="^GSPC", price=7500.0, previous_close=7400.0, change=100.0, change_pct=1.35)}


def test_macro_disabled_and_unmapped() -> None:
    off = _Svc(enabled=False).country_macro("United States")
    assert off.connected is False and "not connected" in (off.note or "")

    unmapped = _Svc(enabled=True, indicator_fetcher=_indicators, index_fetcher=_index).country_macro("Narnia")
    assert unmapped.connected is True and unmapped.metrics == [] and "No macro mapping" in (unmapped.note or "")


def test_macro_assembles_and_caches() -> None:
    calls = {"n": 0}

    def counting_indicator(cc: str, ind: str) -> Indicator | None:
        calls["n"] += 1
        return _indicators(cc, ind)

    now = [0.0]
    svc = _Svc(
        enabled=True,
        indicator_fetcher=counting_indicator,
        index_fetcher=_index,
        ttl_seconds=100.0,
        clock=lambda: now[0],
    )
    result = svc.country_macro("United States")
    assert result.connected is True
    metrics = {m.label: m.value for m in result.metrics}
    assert metrics == {"GDP growth": 2.8, "Inflation (CPI)": 2.9}
    assert result.index is not None and result.index.name == "S&P 500" and result.index.change_pct == 1.35
    after = calls["n"]
    svc.country_macro("United States")  # cache hit within TTL
    assert calls["n"] == after
    now[0] += 200.0
    svc.country_macro("United States")  # past TTL -> refetch
    assert calls["n"] > after
