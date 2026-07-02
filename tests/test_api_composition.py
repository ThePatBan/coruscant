"""The API is composed from a platform router + registry-driven workspace routers.

Guards Phase 2 (docs/PLATFORM.md §6): platform and workspace endpoints are separate
router concerns, and which workspace routers mount is driven by
``coruscant.apps.composition``, not hard-coded — so this is a real composition layer,
not a cosmetic wrapper.
"""

from __future__ import annotations

from typing import Any

from coruscant.apps import composition
from coruscant.apps.api import create_app


def _paths(app: Any) -> set[str]:
    return {r.path for r in app.routes if hasattr(r, "methods")}


def test_platform_and_workspace_both_mounted() -> None:
    paths = _paths(create_app(require_auth=False))
    # platform surface
    assert "/health" in paths
    assert "/companies" in paths
    # portfolio-exposure workspace surface
    assert "/portfolios" in paths
    assert "/graph/sector-exposure" in paths
    assert "/portfolio/prices" in paths


def test_registry_drives_workspace_mounting(monkeypatch: Any) -> None:
    full = _paths(create_app(require_auth=False))
    # Disabling every workspace in the registry must drop the workspace surface while
    # leaving the platform surface intact — proving composition is registry-driven.
    monkeypatch.setattr(composition, "enabled_workspaces", lambda: [])
    reduced = _paths(create_app(require_auth=False))

    assert reduced < full  # workspace routes were dropped
    assert full - reduced  # the dropped set is non-empty
    # platform routes remain
    assert "/health" in reduced
    assert "/companies" in reduced
    # workspace routes are gone
    assert "/portfolios" not in reduced
    assert "/graph/sector-exposure" not in reduced
