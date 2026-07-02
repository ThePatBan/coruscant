"""Shared utilities.

Boundary: PLATFORM — domain-neutral types/errors/logging + platform ``Settings``
(``config.py``). Phase 5 (docs/PLATFORM.md §9, seam 1) relocated every workspace-
specific runtime flag to ``coruscant.exposure.settings.WorkspaceSettings``; Phase 7
removed the last dead duplicates from ``config.py``. Nothing here knows the words
"portfolio", "GICS", "13F", "GLEIF", or "yente".
"""
