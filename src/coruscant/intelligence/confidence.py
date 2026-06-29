"""Shared, bounded confidence scoring for intelligence outputs (M3).

A single deterministic mapping so every intelligence output (summary claims,
events, changes) records a confidence on the same scale. Confidence is always
< 1.0 — the platform never claims certainty.
"""

from __future__ import annotations

_CATEGORY_CONFIDENCE: dict[str, float] = {
    "guidance": 0.78,
    "regulatory": 0.78,
    "litigation": 0.76,
    "supply_chain": 0.74,
    "executive": 0.7,
    "m&a": 0.7,
    "capital_allocation": 0.66,
    "risk": 0.66,
    "financial": 0.6,
    "opportunity": 0.6,
    "product": 0.58,
}
_DEFAULT = 0.5
MAX_CONFIDENCE = 0.8


def category_confidence(category: str | None) -> float:
    return min(MAX_CONFIDENCE, _CATEGORY_CONFIDENCE.get(category or "", _DEFAULT))
