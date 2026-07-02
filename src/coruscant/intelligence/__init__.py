"""Coruscant intelligence layer: summaries, events, and change detection.

Deterministic, fully-cited reference implementations behind Protocol ports so a
Claude-backed adapter can be substituted without changing callers.

Boundary: MIXED (seam 5) — platform mechanism + workspace event taxonomy; docs/PLATFORM.md §9.
"""

from coruscant.intelligence.changes import ReferenceChangeDetector
from coruscant.intelligence.events import ReferenceEventExtractor
from coruscant.intelligence.models import (
    ChangeSet,
    Claim,
    DocumentChange,
    DocumentSummary,
    ExtractedEvent,
)
from coruscant.intelligence.summarizer import ReferenceSummarizer

__all__ = [
    "ReferenceChangeDetector",
    "ReferenceEventExtractor",
    "ReferenceSummarizer",
    "ChangeSet",
    "Claim",
    "DocumentChange",
    "DocumentSummary",
    "ExtractedEvent",
]
