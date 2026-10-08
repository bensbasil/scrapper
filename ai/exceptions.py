"""
ai/exceptions.py
----------------
Domain exceptions for provider-independent LLM interactions.
Provides typed, observable failure representations for upstream callers.
"""

from typing import Optional, Any


class LLMError(Exception):
    """Base exception for all LLM client errors."""
    pass


class LLMUnavailableError(LLMError):
    """Raised when no provider or API key is configured or available."""
    pass


class LLMProviderError(LLMError):
    """Raised when an upstream provider API fails (HTTP error, network error, timeout)."""

    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        response_body: Optional[str] = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body


class LLMResponseParsingError(LLMError):
    """Raised when the provider response cannot be extracted or parsed as JSON."""

    def __init__(self, message: str, raw_text: Optional[str] = None):
        super().__init__(message)
        self.raw_text = raw_text


class LLMValidationError(LLMError):
    """Raised when parsed JSON fails Pydantic schema validation."""

    def __init__(self, message: str, raw_data: Optional[Any] = None):
        super().__init__(message)
        self.raw_data = raw_data
