"""Live equity pricing — a free, network-gated Yahoo Finance client and a small
caching service. Kept out of the document-ingestion pipeline (prices are quotes,
not filings) and behind an explicit enable flag, so the offline/test path never
touches the network and a missing quote is reported, never fabricated.

Boundary: WORKSPACE (Portfolio-Exposure) — see docs/PLATFORM.md §7."""

from coruscant.pricing.benchmark import (
    PortfolioBenchmark,
    SectorBenchmark,
    benchmark_symbols,
    sector_benchmarks,
)
from coruscant.pricing.service import (
    HoldingQuote,
    PortfolioPrices,
    PriceService,
    summarize,
)
from coruscant.pricing.yahoo import Quote, fetch_quotes, parse_chart

__all__ = [
    "HoldingQuote",
    "PortfolioBenchmark",
    "PortfolioPrices",
    "PriceService",
    "Quote",
    "SectorBenchmark",
    "benchmark_symbols",
    "fetch_quotes",
    "parse_chart",
    "sector_benchmarks",
    "summarize",
]
