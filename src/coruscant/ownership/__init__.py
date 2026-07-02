"""Ownership substrate: real ownership / control / beneficial-owner edges.

The foundation the graph has never had (``docs/global-exposure-architecture.md``
Phase 3). Three DISTINCT edge types, never conflated (§2.4): ``owns`` (declared
%-shareholding), ``beneficial_owner_of`` (a person's ultimate ownership/control),
``consolidates`` (accounting consolidation). Each edge carries provenance,
bitemporal validity, and an ``access_tier`` the query gate enforces — so this sets
up UBO and contagion work without faking completeness.

:class:`~coruscant.ownership.provider.OwnershipProvider` is the seam (a provider
lists sourced ownership statements); :func:`~coruscant.ownership.pipeline.ingest_ownership`
reconciles them into the graph, resolving parties to existing nodes by anchor.

Boundary: WORKSPACE (corporate-ownership domain) — see docs/PLATFORM.md §7.
"""

from __future__ import annotations

from coruscant.ownership.models import (
    OwnershipBasis,
    OwnershipParty,
    OwnershipRecord,
    PartyAnchor,
)
from coruscant.ownership.pipeline import (
    BENEFICIAL_OWNER_OF,
    CONSOLIDATES,
    OWNS,
    OwnershipSummary,
    ingest_ownership,
)
from coruscant.ownership.provider import (
    BodsOwnershipProvider,
    OwnershipProvider,
    StaticOwnershipProvider,
    parse_bods,
)
from coruscant.ownership.companies_house import (
    COMPANIES_HOUSE_PSC_SOURCE,
    CompaniesHousePscProvider,
    parse_psc,
)
from coruscant.ownership.gleif_l2 import (
    GLEIF_L2_SOURCE,
    GleifL2ConsolidationProvider,
    parse_gleif_relationships,
)

__all__ = [
    "BENEFICIAL_OWNER_OF",
    "BodsOwnershipProvider",
    "COMPANIES_HOUSE_PSC_SOURCE",
    "CONSOLIDATES",
    "CompaniesHousePscProvider",
    "GLEIF_L2_SOURCE",
    "GleifL2ConsolidationProvider",
    "OWNS",
    "OwnershipBasis",
    "OwnershipParty",
    "OwnershipProvider",
    "OwnershipRecord",
    "OwnershipSummary",
    "PartyAnchor",
    "StaticOwnershipProvider",
    "ingest_ownership",
    "parse_bods",
    "parse_gleif_relationships",
    "parse_psc",
]
