"""Country-macro service: assembles World Bank GDP/inflation + the country's
benchmark-index move into one cached, network-gated view for the World tab.

Cached with a moderate TTL (macro barely moves; the index is refreshed on the
same tick, which is fine for an at-a-glance tile). Disabled by default so
offline/tests never hit the network, and every fetcher is injectable."""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor

from pydantic import BaseModel

from coruscant.macro.worldbank import Indicator, fetch_indicator
from coruscant.pricing.yahoo import Quote, fetch_quotes

# GDP growth (annual %) and CPI inflation (annual %).
_GDP = "NY.GDP.MKTP.KD.ZG"
_CPI = "FP.CPI.TOTL.ZG"

# Country (as the globe/exchange table names it) -> (World Bank ISO2, index
# symbol, index display name). The index symbols are verified against Yahoo.
COUNTRY_MACRO: dict[str, tuple[str, str, str]] = {
    "United States": ("US", "^GSPC", "S&P 500"),
    "Canada": ("CA", "^GSPTSE", "S&P/TSX"),
    "Brazil": ("BR", "^BVSP", "Bovespa"),
    "United Kingdom": ("GB", "^FTSE", "FTSE 100"),
    "France": ("FR", "^FCHI", "CAC 40"),
    "Germany": ("DE", "^GDAXI", "DAX"),
    "Switzerland": ("CH", "^SSMI", "SMI"),
    "South Africa": ("ZA", "^J203.JO", "JSE All Share"),
    "Saudi Arabia": ("SA", "^TASI.SR", "Tadawul"),
    "India": ("IN", "^NSEI", "Nifty 50"),
    "China": ("CN", "000001.SS", "SSE Composite"),
    "Hong Kong": ("HK", "^HSI", "Hang Seng"),
    "Singapore": ("SG", "^STI", "Straits Times"),
    "Japan": ("JP", "^N225", "Nikkei 225"),
    "Australia": ("AU", "^AXJO", "ASX 200"),
}

IndicatorFetcher = Callable[[str, str], Indicator | None]
IndexFetcher = Callable[[Sequence[str]], dict[str, Quote]]


class MacroMetric(BaseModel):
    label: str
    value: float | None = None
    unit: str = "%"
    period: str | None = None  # e.g. "2024"
    source: str = "World Bank"


class IndexQuote(BaseModel):
    name: str
    symbol: str
    price: float
    change_pct: float
    as_of: str | None = None


class CountryMacro(BaseModel):
    country: str
    connected: bool
    metrics: list[MacroMetric] = []
    index: IndexQuote | None = None
    note: str | None = None


class MacroService:
    def __init__(
        self,
        *,
        enabled: bool,
        indicator_fetcher: IndicatorFetcher = fetch_indicator,
        index_fetcher: IndexFetcher = fetch_quotes,
        ttl_seconds: float = 900.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._enabled = enabled
        self._indicator = indicator_fetcher
        self._index = index_fetcher
        self._ttl = ttl_seconds
        self._clock = clock
        self._cache: dict[str, tuple[float, CountryMacro]] = {}

    @property
    def enabled(self) -> bool:
        return self._enabled

    def country_macro(self, country: str) -> CountryMacro:
        name = country.strip()
        if not self._enabled:
            return CountryMacro(
                country=name,
                connected=False,
                note="Macro not connected — set CORUSCANT_ENABLE_LIVE_MACRO=true.",
            )
        entry = COUNTRY_MACRO.get(name)
        if entry is None:
            return CountryMacro(country=name, connected=True, note="No macro mapping for this country yet.")
        cached = self._cache.get(name)
        if cached is not None and (self._clock() - cached[0]) <= self._ttl:
            return cached[1]
        result = self._assemble(name, entry)
        self._cache[name] = (self._clock(), result)
        return result

    def _assemble(self, name: str, entry: tuple[str, str, str]) -> CountryMacro:
        wb_code, index_symbol, index_name = entry
        # GDP + CPI are independent slow calls — fetch them concurrently.
        with ThreadPoolExecutor(max_workers=2) as executor:
            gdp_future = executor.submit(self._indicator, wb_code, _GDP)
            cpi_future = executor.submit(self._indicator, wb_code, _CPI)
            gdp, cpi = gdp_future.result(), cpi_future.result()
        metrics = [
            MacroMetric(label="GDP growth", value=gdp.value if gdp else None, period=gdp.year if gdp else None),
            MacroMetric(label="Inflation (CPI)", value=cpi.value if cpi else None, period=cpi.year if cpi else None),
        ]
        index_quote = None
        quotes = self._index([index_symbol])
        quote = quotes.get(index_symbol)
        if quote is not None:
            index_quote = IndexQuote(
                name=index_name,
                symbol=index_symbol,
                price=quote.price,
                change_pct=quote.change_pct,
                as_of=quote.as_of,
            )
        return CountryMacro(country=name, connected=True, metrics=metrics, index=index_quote)
