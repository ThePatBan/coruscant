"""Country macro for the World tab: free World Bank indicators (GDP growth,
inflation) + the country's benchmark-index move (reused from the pricing client).
Network-gated and cached, like pricing — a missing metric is reported, never
fabricated.

Boundary: WORKSPACE (Portfolio-Exposure) — see docs/PLATFORM.md §7."""

from coruscant.macro.service import (
    COUNTRY_MACRO,
    CountryMacro,
    IndexQuote,
    MacroMetric,
    MacroService,
)
from coruscant.macro.worldbank import Indicator, fetch_indicator

__all__ = [
    "COUNTRY_MACRO",
    "CountryMacro",
    "IndexQuote",
    "Indicator",
    "MacroMetric",
    "MacroService",
    "fetch_indicator",
]
