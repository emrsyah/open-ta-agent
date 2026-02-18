"""
Custom exceptions for the application.
"""


class PaperResearchException(Exception):
    """Base exception for the application."""
    pass


class ConfigurationError(PaperResearchException):
    """Raised when there's a configuration error."""
    pass


class RetrieverError(PaperResearchException):
    """Raised when paper retrieval fails."""
    pass


class LLMError(PaperResearchException):
    """Raised when LLM interaction fails."""
    pass


class StreamingError(PaperResearchException):
    """Raised when streaming fails."""
    pass
