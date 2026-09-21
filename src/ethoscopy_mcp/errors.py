"""Public exception types raised by ethoscopy-mcp."""


class EthoscopyMCPError(Exception):
    """Base class for controlled ethoscopy-mcp failures."""


class ConfigurationError(EthoscopyMCPError):
    """The local service configuration is incomplete or invalid."""


class UnsafePathError(EthoscopyMCPError):
    """A requested path is outside the configured trusted roots."""


class UnsupportedSourceError(EthoscopyMCPError):
    """A source type or loaded object is not supported."""


class SourceChangedError(EthoscopyMCPError):
    """A registered source changed while an operation was running."""


class InvalidExperimentError(EthoscopyMCPError):
    """An experiment cannot be inspected or analyzed safely."""
