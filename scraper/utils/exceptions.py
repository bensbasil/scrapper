class ScraperException(Exception):
    """Base exception for scraper errors."""
    pass

class SourceTimeoutError(ScraperException):
    """Raised when a source takes too long to respond."""
    pass

class RateLimitExceeded(ScraperException):
    """Raised when the scraper is blocked due to rate limiting."""
    pass

class DOMChangeError(ScraperException):
    """Raised when expected HTML selectors are not found (site updated)."""
    pass

class ParseError(ScraperException):
    """Raised when raw data cannot be parsed correctly."""
    pass
