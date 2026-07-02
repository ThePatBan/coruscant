"""Package boundary markers for the monorepo layout.

Machine-readable companion to ``docs/PLATFORM.md`` (§7): every top-level package under
``coruscant`` is classified as part of the shared **platform** substrate, the
**workspace** (today's Portfolio-Exposure product), or a **mixed** seam that fuses both
and is slated to split in a later phase (``docs/PLATFORM.md`` §9).

This is documentation-as-data, not a runtime dependency — nothing imports it to change
behavior. ``tests/test_platform_boundary.py`` asserts the classification stays complete
and exclusive, so a new package cannot land without being placed on one side of the
boundary.
"""

from __future__ import annotations

from enum import Enum


class Boundary(str, Enum):
    """Which side of the platform/workspace boundary a package sits on."""

    PLATFORM = "platform"
    WORKSPACE = "workspace"
    MIXED = "mixed"


#: Shared, domain-neutral substrate — reusable by any workspace.
PLATFORM_PACKAGES: frozenset[str] = frozenset(
    {
        "anchoring",  # corporate-scoped identity / LEI anchoring
        "apps",  # HTTP/CLI/worker/runtime assembly (also wires product pipelines — seam 2)
        "auth",
        "commercial",
        "enterprise",
        "infrastructure",
        "llm",
        "search",
        "workspaces",  # collaboration space, NOT a product workspace (docs/PLATFORM.md §5)
    }
)

#: The Portfolio-Exposure Workspace — investment-research domain.
WORKSPACE_PACKAGES: frozenset[str] = frozenset(
    {
        "coverage",
        "macro",
        "news",
        "ownership",
        "portfolio",
        "pricing",
        "screening",
        "watchlists",
    }
)

#: Packages fusing platform substrate and workspace domain — named seams to split later.
MIXED_PACKAGES: frozenset[str] = frozenset(
    {
        "common",  # types/errors/logging (platform) + domain config (workspace) — seam 1
        "connectors",  # interfaces (platform) + finance connectors (workspace)
        "ingestion",  # orchestrator/registry (platform) + finance defaults (workspace) — seam 4
        "intelligence",  # summarize/diff (platform) + event taxonomy (workspace) — seam 5
        "knowledge_graph",  # store/substrate (platform) + exposure engine (workspace) — seam 3
    }
)

#: Flat lookup: package name -> boundary.
BOUNDARY: dict[str, Boundary] = {
    **{name: Boundary.PLATFORM for name in PLATFORM_PACKAGES},
    **{name: Boundary.WORKSPACE for name in WORKSPACE_PACKAGES},
    **{name: Boundary.MIXED for name in MIXED_PACKAGES},
}
