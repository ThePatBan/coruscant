"""Sector-index benchmarking: compare each GICS sector's holdings to a sector
index, using the free prices we already fetch.

The *licensed* MSCI sector indexes are the eventual benchmark; until that feed is
bought, we proxy each GICS sector with its liquid **SPDR Select Sector ETF**
(same GICS taxonomy, free via Yahoo). The UX labels these as proxies — we do not
claim to be the MSCI index. The portfolio side is **equal-weighted** (no position
weights yet), so this is day-performance orientation, not attribution.
"""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel

from coruscant.pricing.yahoo import Quote

# GICS sector -> (proxy ETF symbol, display name). SPDR Select Sector funds track
# the S&P 500 GICS sectors; XLC/XLRE cover the 2018/2016 additions.
SECTOR_ETF: dict[str, tuple[str, str]] = {
    "Energy": ("XLE", "Energy Select (SPDR)"),
    "Materials": ("XLB", "Materials Select (SPDR)"),
    "Industrials": ("XLI", "Industrials Select (SPDR)"),
    "Consumer Discretionary": ("XLY", "Cons. Discretionary Select (SPDR)"),
    "Consumer Staples": ("XLP", "Cons. Staples Select (SPDR)"),
    "Health Care": ("XLV", "Health Care Select (SPDR)"),
    "Financials": ("XLF", "Financials Select (SPDR)"),
    "Information Technology": ("XLK", "Technology Select (SPDR)"),
    "Communication Services": ("XLC", "Comm. Services Select (SPDR)"),
    "Utilities": ("XLU", "Utilities Select (SPDR)"),
    "Real Estate": ("XLRE", "Real Estate Select (SPDR)"),
}


class SectorBenchmark(BaseModel):
    sector: str
    holdings: int
    weight_pct: float  # equal-weight share of the portfolio
    portfolio_change_pct: float | None = None  # avg move of this sector's holdings today
    benchmark_symbol: str | None = None
    benchmark_name: str | None = None
    benchmark_change_pct: float | None = None  # sector-index proxy move today
    delta_pct: float | None = None  # portfolio − benchmark (relative day performance)


class PortfolioBenchmark(BaseModel):
    connected: bool
    as_of: str | None = None
    sectors: list[SectorBenchmark] = []
    note: str | None = None


def benchmark_symbols(sectors: Sequence[str]) -> list[str]:
    """The proxy ETF symbols needed for these GICS sectors (deduped)."""
    return list(dict.fromkeys(SECTOR_ETF[s][0] for s in sectors if s in SECTOR_ETF))


def sector_benchmarks(
    company_sectors: Sequence[tuple[str, str, str]],  # (slug, gics_sector, ticker)
    holding_quotes: dict[str, Quote],
    etf_quotes: dict[str, Quote],
    *,
    total: int,
) -> list[SectorBenchmark]:
    """Fold holdings + sector-ETF quotes into a per-sector benchmark table.
    ``total`` is the denominator for the equal-weight share (all classified
    holdings, not just the priced ones)."""
    symbols_by_sector: dict[str, list[str]] = {}
    for _slug, sector, symbol in company_sectors:
        symbols_by_sector.setdefault(sector, []).append(symbol)

    rows: list[SectorBenchmark] = []
    for sector, symbols in symbols_by_sector.items():
        changes = [holding_quotes[s].change_pct for s in symbols if s in holding_quotes]
        portfolio_change = sum(changes) / len(changes) if changes else None
        etf = SECTOR_ETF.get(sector)
        benchmark_symbol = etf[0] if etf else None
        benchmark_name = etf[1] if etf else None
        etf_quote = etf_quotes.get(benchmark_symbol) if benchmark_symbol else None
        benchmark_change = etf_quote.change_pct if etf_quote is not None else None
        delta = (
            portfolio_change - benchmark_change
            if portfolio_change is not None and benchmark_change is not None
            else None
        )
        rows.append(
            SectorBenchmark(
                sector=sector,
                holdings=len(symbols),
                weight_pct=(len(symbols) / total * 100.0) if total else 0.0,
                portfolio_change_pct=portfolio_change,
                benchmark_symbol=benchmark_symbol,
                benchmark_name=benchmark_name,
                benchmark_change_pct=benchmark_change,
                delta_pct=delta,
            )
        )
    rows.sort(key=lambda r: (-r.weight_pct, r.sector))
    return rows
