"""Typed application errors.

A small, explicit hierarchy so failures are never swallowed: connectors and the
pipeline raise these, the orchestrator records them (dead-letter + run report),
and callers can distinguish failure modes.
"""


class CoruscantError(Exception):
    """Base application error."""


class ConfigurationError(CoruscantError):
    """Raised when repository configuration is invalid."""


class IngestionError(CoruscantError):
    """Base for failures in the ingestion lifecycle."""


class FetchError(IngestionError):
    """A source connector could not fetch the requested document."""


class NormalizationError(IngestionError):
    """A document could not be normalized into the canonical model."""
