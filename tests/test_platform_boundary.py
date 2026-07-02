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
