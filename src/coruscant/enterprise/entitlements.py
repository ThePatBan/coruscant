"""Enterprise entitlement policy (Phase 7, Scope B).

The single backend answer to "may this account use the enterprise surface?". Kept a
pure function of ``(role, plan)`` so the same rule backs the API dependency
(``require_entitlement`` in ``apps/api.py``) and is mirrored by the frontend gate
(``frontend/src/workspaces.ts``). The entitlement *source* is deliberately minimal
today — an ``admin`` role OR membership of an org on the ``enterprise`` plan — but this
module is the seam a richer source (org membership, per-seat licensing, feature flags)
slots into without touching a single route.

Boundary: PLATFORM primitive — see docs/PLATFORM.md §7.
"""

from __future__ import annotations

#: The one entitlement today: access to the enterprise workspace surface.
ENTERPRISE = "enterprise"

#: The complete entitlement vocabulary (kept small; grows as real tiers are added).
ENTITLEMENTS: frozenset[str] = frozenset({ENTERPRISE})


def entitlements_for(*, role: str, plan: str) -> frozenset[str]:
    """The entitlements an account with this ``role`` and effective ``plan`` holds.

    Enterprise is granted to admins (operators) and to any account whose most-generous
    org plan is ``enterprise``. Everyone else (anonymous, free/pro authenticated) holds
    no entitlement — the enterprise surface is gated, not merely styled differently."""
    granted: set[str] = set()
    if role == "admin" or plan == "enterprise":
        granted.add(ENTERPRISE)
    return frozenset(granted)


def has_entitlement(name: str, *, role: str, plan: str) -> bool:
    """Whether an account with this ``role``/``plan`` holds the named entitlement."""
    return name in entitlements_for(role=role, plan=plan)
