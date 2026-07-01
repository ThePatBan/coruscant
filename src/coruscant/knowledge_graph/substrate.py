"""Edge substrate: access-tier policy + bitemporal stamping.

The invariants in ``docs/global-exposure-architecture.md`` §2 made concrete. A
sensitive edge (PEP / sanctions / beneficial ownership) must carry, beyond the
``source`` statement every edge already has:

* ``access_tier`` — who is licensed to see it, *enforced at query time*, not just
  tagged. "A tag nobody enforces is worse than no tag." (§2.7)
* valid-time (``valid_from`` / ``valid_to``) and system-time (``observed_at``) —
  so "was this counterparty sanctioned *on the transaction date*?" is answerable.
  (§2.6, bitemporal)

These ride as ordinary keys on :attr:`GraphEdge.properties`, so the deliberately
generic ``Node``/``Edge`` schema — and the JSON-snapshot → Kùzu round-trip guarded
by the golden parity test — carries them verbatim, with no storage migration.
This module is the single place that writes and reads them so the convention stays
consistent across every connector.
"""

from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Any, Iterable


class AccessTier(str, Enum):
    """How restricted an edge's underlying data is. Ordered least → most
    restrictive; a caller sees an edge only if their clearance is at least as
    permissive as the edge's tier (see :func:`visible`)."""

    PUBLIC = "public"
    LEGITIMATE_INTEREST = "legitimate-interest"
    RESTRICTED_AUTHORITY = "restricted-authority"
    AGGREGATOR_LICENSED = "aggregator-licensed"


# Rank ascending in restrictiveness. A clearance of rank R sees tiers of rank ≤ R.
_TIER_RANK: dict[AccessTier, int] = {
    AccessTier.PUBLIC: 0,
    AccessTier.LEGITIMATE_INTEREST: 1,
    AccessTier.RESTRICTED_AUTHORITY: 2,
    AccessTier.AGGREGATOR_LICENSED: 3,
}

# Property keys the substrate owns. Kept as constants so readers/writers agree.
SOURCE = "source"
ACCESS_TIER = "access_tier"
OBSERVED_AT = "observed_at"
VALID_FROM = "valid_from"
VALID_TO = "valid_to"


def _coerce_tier(value: AccessTier | str) -> AccessTier:
    return value if isinstance(value, AccessTier) else AccessTier(value)


def _iso(value: date | str | None) -> str | None:
    if value is None:
        return None
    return value.isoformat() if isinstance(value, date) else value


def stamp(
    properties: dict[str, Any] | None = None,
    *,
    source: str,
    access_tier: AccessTier | str = AccessTier.PUBLIC,
    observed_at: date | str,
    valid_from: date | str | None = None,
    valid_to: date | str | None = None,
) -> dict[str, Any]:
    """Return an edge ``properties`` dict carrying the substrate fields.

    ``source`` is the provenance statement (Invariant #1); ``observed_at`` is
    system-time (when we recorded the belief); ``valid_from``/``valid_to`` are
    valid-time (when the fact was true in the world — open-ended when ``None``).
    Any extra facts (score, list, external_id …) are passed in ``properties`` and
    preserved. The substrate keys are written last so they are unambiguous, and
    ``None`` bounds are omitted rather than stored as null.
    """

    out: dict[str, Any] = dict(properties or {})
    out[SOURCE] = source
    out[ACCESS_TIER] = _coerce_tier(access_tier).value
    out[OBSERVED_AT] = _iso(observed_at)
    vf = _iso(valid_from)
    vt = _iso(valid_to)
    if vf is not None:
        out[VALID_FROM] = vf
    if vt is not None:
        out[VALID_TO] = vt
    return out


def tier_of(properties: dict[str, Any]) -> AccessTier:
    """The edge's access tier. An unlabelled edge is treated as ``PUBLIC`` — the
    existing reference edges (co-mention, sector) are public by nature; only
    sensitive edges are stamped, and they always carry a tier."""

    raw = properties.get(ACCESS_TIER)
    if isinstance(raw, str):
        try:
            return AccessTier(raw)
        except ValueError:
            return AccessTier.AGGREGATOR_LICENSED  # unknown label → fail closed
    return AccessTier.PUBLIC


def can_see(properties: dict[str, Any], clearance: AccessTier | str) -> bool:
    """Whether a caller with ``clearance`` may see an edge with these properties."""

    return _TIER_RANK[tier_of(properties)] <= _TIER_RANK[_coerce_tier(clearance)]


def visible(edges: Iterable[Any], *, clearance: AccessTier | str = AccessTier.PUBLIC) -> list[Any]:
    """Query-time policy engine: drop edges the caller is not cleared to see.

    Accepts anything with a ``properties`` mapping (a :class:`GraphEdge` or a
    match record), so the same gate guards graph reads and screening results."""

    allowed = _TIER_RANK[_coerce_tier(clearance)]
    return [e for e in edges if _TIER_RANK[tier_of(e.properties)] <= allowed]


def valid_on(properties: dict[str, Any], on: date | str) -> bool:
    """Whether the edge's valid-time interval contains ``on`` (ISO ``YYYY-MM-DD``
    dates sort lexicographically, so string comparison is correct). Missing bounds
    are open-ended."""

    moment = _iso(on)
    assert moment is not None  # `on` is required
    lo = properties.get(VALID_FROM)
    hi = properties.get(VALID_TO)
    if isinstance(lo, str) and moment < lo:
        return False
    if isinstance(hi, str) and moment > hi:
        return False
    return True


def as_of(edges: Iterable[Any], *, on: date | str) -> list[Any]:
    """Bitemporal filter: the edges whose valid-time interval contains ``on`` —
    the "was this true on date D?" query. Edges without valid-time bounds are
    always included (open-ended facts)."""

    return [e for e in edges if valid_on(e.properties, on)]
