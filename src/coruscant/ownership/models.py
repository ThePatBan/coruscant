"""Ownership substrate models — the honesty-critical distinctions.

Declared ownership ≠ beneficial ownership ≠ accounting consolidation
(``docs/global-exposure-architecture.md`` §2.4). These are three *different claims*
about control, from different sources, at different access tiers, and must never be
silently equated. The distinction is encoded as an explicit :class:`OwnershipBasis`
that selects the graph relation and the default access tier. A record NEVER carries
an invented percentage: an exact figure goes in ``percentage`` only when the source
states it; a disclosed range (a PSC "25%-50%" band) goes verbatim in
``percentage_band``.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel


class OwnershipBasis(str, Enum):
    """What kind of claim an ownership statement makes — selects the edge relation.

    Kept deliberately narrow: three bases mapping 1:1 to the three edge types in the
    architecture. A new basis is a deliberate, reviewed addition, never an alias."""

    DECLARED_SHAREHOLDING = "declared_shareholding"  # a disclosed %-shareholding (SEC 13D/G, a BODS entity interest)
    BENEFICIAL_OWNER = "beneficial_owner"  # a natural person's ultimate ownership/control (UK PSC, a BODS person)
    ACCOUNTING_CONSOLIDATION = "accounting_consolidation"  # parent consolidates a sub (GLEIF L2) — NOT %-ownership


class PartyAnchor(BaseModel):
    """An external identifier used to resolve a party to an existing graph node —
    ``lei``/``cik``/``isin`` for companies; a registry or person id for people. The
    same "anchor, never the primary key" discipline the rest of the graph uses."""

    scheme: str
    value: str


class OwnershipParty(BaseModel):
    """One end of an ownership statement. ``kind`` ∈ {``Person``, ``Company``,
    ``Entity``}. Resolution prefers ``anchor`` (exact external-key match against an
    existing node), then an explicit ``key``, then a stable name surrogate."""

    name: str
    kind: str = "Entity"
    anchor: PartyAnchor | None = None
    key: str | None = None


class OwnershipRecord(BaseModel):
    """A single sourced ownership/control statement: ``holder`` (the owner or parent)
    has an interest of ``basis`` in ``subject`` (the owned company or subsidiary).

    Provenance (``source``) and validity (``valid_from``/``valid_to``) are required
    substrate. ``access_tier`` may override the basis default (e.g. an aggregator's
    licensed feed). ``interest`` names the nature of control (shareholding /
    voting-rights / appoint-directors) without which a beneficial-owner edge is
    ambiguous."""

    holder: OwnershipParty
    subject: OwnershipParty
    basis: OwnershipBasis
    percentage: float | None = None
    percentage_band: str | None = None
    interest: str | None = None
    source: str
    source_url: str | None = None
    valid_from: str | None = None
    valid_to: str | None = None
    access_tier: str | None = None
