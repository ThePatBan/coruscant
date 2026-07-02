"""GLEIF LEI anchoring — the identity/keys pillar (architecture §3, pillar 1).

Attaches a stable external *anchor* (the LEI) to our surrogate-keyed nodes by
resolving Company/Subsidiary names against GLEIF (free, CC0). An LEI is an anchor,
never the primary key (it covers <1% of companies) — so a confirmed match enriches
a node and records a reversible resolver judgement; unmatched nodes are labelled
explicitly unresolved, never dropped (absence is signal). Same provider seam as
screening: an offline fixture provider for CI + a live GLEIF-API provider for
operators.

Boundary: PLATFORM (corporate-scoped identity) — see docs/PLATFORM.md §7.
"""

from coruscant.anchoring.provider import (
    AnchorMatch,
    AnchorQuery,
    GleifApiProvider,
    LeiProvider,
    LeiRecord,
    LocalGleifProvider,
    load_gleif,
)

__all__ = [
    "AnchorMatch",
    "AnchorQuery",
    "GleifApiProvider",
    "LeiProvider",
    "LeiRecord",
    "LocalGleifProvider",
    "load_gleif",
]
