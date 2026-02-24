class ConfigError(Exception):
    """Raised when config loading or validation fails."""


class AgentUnavailable(Exception):
    """Raised when an agent cannot be reached or returns error."""


class ValidationError(Exception):
    """Raised when request/response validation fails."""
