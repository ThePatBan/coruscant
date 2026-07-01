"""PEP / sanctions screening — connector → normalize → block → score → judgement.

The offline half of the ER spine: match the entities we already hold against a
watchlist authority (OpenSanctions) and record the result as a reversible
:mod:`coruscant.knowledge_graph.resolution` judgement, projecting only confirmed
hits as ``pep`` / ``sanctioned`` edges. A :class:`ScreeningProvider` seam keeps the
matcher swappable: PR 1 ships a hermetic, zero-dependency deterministic provider;
PR 2 swaps in the ``yente`` HTTP service (nomenklatura's scaled scorer) behind the
same interface, with no change to the pipeline or the graph model.
"""

from coruscant.screening.provider import (
    DeterministicScreeningProvider,
    ScreeningMatch,
    ScreeningProvider,
    ScreeningQuery,
    WatchlistRecord,
    load_opensanctions,
    normalize_name,
)

__all__ = [
    "DeterministicScreeningProvider",
    "ScreeningMatch",
    "ScreeningProvider",
    "ScreeningQuery",
    "WatchlistRecord",
    "load_opensanctions",
    "normalize_name",
]
