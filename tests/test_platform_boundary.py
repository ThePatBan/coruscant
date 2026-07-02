"""The platform/workspace boundary manifest stays complete and exclusive.

Guards ``coruscant.packages`` and ``docs/PLATFORM.md`` §7: every top-level package under
``coruscant`` must be classified exactly once, so the boundary cannot silently erode as
new packages are added.
"""

from __future__ import annotations

from pathlib import Path

import coruscant
from coruscant.packages import (
    BOUNDARY,
    MIXED_PACKAGES,
    PLATFORM_PACKAGES,
    WORKSPACE_PACKAGES,
)


def _discover_packages() -> set[str]:
    root = Path(coruscant.__file__).parent
    return {
        child.name
        for child in root.iterdir()
        if child.is_dir()
        and not child.name.startswith("_")
        and (child / "__init__.py").exists()
    }


def test_every_package_is_classified() -> None:
    discovered = _discover_packages()
    classified = set(BOUNDARY)
    assert discovered == classified, {
        "unclassified (add to coruscant.packages)": sorted(discovered - classified),
        "stale (remove from coruscant.packages)": sorted(classified - discovered),
    }


def test_buckets_are_disjoint_and_cover_everything() -> None:
    assert not (PLATFORM_PACKAGES & WORKSPACE_PACKAGES)
    assert not (PLATFORM_PACKAGES & MIXED_PACKAGES)
    assert not (WORKSPACE_PACKAGES & MIXED_PACKAGES)
    assert PLATFORM_PACKAGES | WORKSPACE_PACKAGES | MIXED_PACKAGES == set(BOUNDARY)


# ---- Field-level drift guard on the platform Settings (Phase 7, seam 1) -----------
#
# The package-level guards above cannot catch a workspace flag leaking BACK onto the
# platform `common.config.Settings` (they check package classification, not field
# contents). These two assert the split at field granularity so the resolved drift
# cannot silently reappear.

# Workspace-specific runtime flags — must live ONLY on
# `coruscant.exposure.settings.WorkspaceSettings`, never on the platform Settings.
_WORKSPACE_SETTINGS_FIELDS = frozenset(
    {
        "screening_dataset_path",
        "screening_provider",
        "yente_url",
        "yente_dataset",
        "yente_cutoff",
        "yente_limit",
        "anchor_provider",
        "gleif_dataset_path",
        "companies_house_api_key",
        "companies_house_api_url",
        "edgar_user_agent",
        "live_sources",
        "sec_rate_limit_per_second",
        "enable_live_prices",
        "enable_live_macro",
        "enable_live_news",
    }
)


def test_platform_settings_carry_no_workspace_flags() -> None:
    from coruscant.common.config import Settings

    leaked = _WORKSPACE_SETTINGS_FIELDS & set(Settings.model_fields)
    assert not leaked, (
        "workspace-specific flags leaked onto the platform common.config.Settings — "
        f"move them to coruscant.exposure.settings.WorkspaceSettings: {sorted(leaked)}"
    )


def test_workspace_settings_own_the_relocated_flags() -> None:
    from coruscant.exposure.settings import WorkspaceSettings

    missing = _WORKSPACE_SETTINGS_FIELDS - set(WorkspaceSettings.model_fields)
    assert not missing, f"WorkspaceSettings lost a relocated flag: {sorted(missing)}"
