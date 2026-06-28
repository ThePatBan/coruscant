class CoruscantError(Exception):
    """Base application error."""


class ConfigurationError(CoruscantError):
    """Raised when repository configuration is invalid."""
