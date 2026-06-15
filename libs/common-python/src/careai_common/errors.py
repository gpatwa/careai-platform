class CareAIError(Exception):
    """Base error for expected platform failures."""


class ConfigurationError(CareAIError):
    """Raised when required configuration is missing or invalid."""


class DependencyUnavailableError(CareAIError):
    """Raised when a platform dependency is not reachable."""

