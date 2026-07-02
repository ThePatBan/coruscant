"""Workspace composition registry for the serving API.

Phase 2 of the platform/workspace split (ADR-0013, docs/PLATFORM.md §6-7): the FastAPI
app is composed from a shared **platform** router plus one router per **workspace**
application. Which workspace routers mount is driven by *this registry*, not hard-coded in
``create_app`` — adding a workspace edition later means adding an entry here and building
its router, not editing the composition root.

Today there is exactly one workspace: the Portfolio-Exposure Workspace (the
investment-research product). This module is behavior-neutral data — it declares
composition, it does not itself define routes.

Boundary: PLATFORM (assembly/composition) — see docs/PLATFORM.md §7.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class WorkspaceApp:
    """A workspace application composed onto the platform.

    ``slug`` keys the workspace's :class:`fastapi.APIRouter` at composition time in
    ``create_app``; ``enabled`` gates whether it is mounted.
    """

    slug: str
    name: str
    description: str
    enabled: bool = True


#: The current (and only) workspace: the investment-research product.
PORTFOLIO_EXPOSURE = WorkspaceApp(
    slug="portfolio-exposure",
    name="Portfolio-Exposure Workspace",
    description=(
        "Investment-research product on the Coruscant Intelligence Platform: whole-exchange "
        "coverage, portfolios (13F + upload), the exposure engine (geographic/sector/market-"
        "tier/commodity/debt/ownership-contagion), live market data, watchlists, and the "
        "company-scoped analyst/signals/dashboard surfaces."
    ),
)

#: Registry of workspaces, in mount order. Add future editions (Public / Professional /
#: Enterprise, or new domains) here — see docs/PLATFORM.md §4.
WORKSPACES: tuple[WorkspaceApp, ...] = (PORTFOLIO_EXPOSURE,)


def enabled_workspaces() -> list[WorkspaceApp]:
    """The workspaces to mount, in order. ``create_app`` iterates this, not a hard-coded list."""
    return [w for w in WORKSPACES if w.enabled]
