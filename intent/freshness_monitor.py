"""
freshness_monitor.py
--------------------
Responsibility:
    Detect whether a business's website appears outdated, abandoned, or
    stale — which is a strong signal that they need digital help.

Freshness signals to detect:
    1. Copyright year in footer (e.g., "© 2017" → very stale)
    2. Last-Modified HTTP header from web server
    3. Blog/news section with no recent posts
    4. "Coming soon" or "Under construction" pages
    5. SSL certificate expiry (near-expiry = neglected website)

Why this matters:
    A website that hasn't been updated in 3+ years is almost certainly
    not generating leads. The business owner may not even realize this.
    This makes freshness a high-confidence pitch hook.

Architecture decision:
    Returns FreshnessResult consumed by intent_engine.py as freshness_score.
    Does NOT modify any database records — read-only analysis.

TODO:
    - Implement copyright year extraction from footer text
    - Parse Last-Modified HTTP response header
    - Detect "under construction" page patterns
    - Check SSL certificate expiry date using ssl library
    - Calculate days_since_last_update where detectable
    - Build freshness_score formula from combined signals
"""

import re
import ssl
import socket
import logging
from dataclasses import dataclass, asdict, field
from typing import Optional, List
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

from scraper.utils.logger import get_scraper_logger

logger = get_scraper_logger("FreshnessMonitor")


# Phrases that indicate an abandoned or placeholder site
STALE_PAGE_PATTERNS = [
    "coming soon", "under construction", "site is under maintenance",
    "website is being updated", "check back soon",
    # TODO: Add patterns observed in target market sites
]


# ---------------------------------------------------------
# Output Data Structure
# ---------------------------------------------------------
@dataclass
class FreshnessResult:
    """
    Freshness intelligence for a business website.
    Designed for use by intent_engine.py.
    """
    business_name: str
    website_url: Optional[str]

    copyright_year: Optional[int] = None
    last_modified_header: Optional[str] = None
    ssl_expiry_date: Optional[str] = None
    ssl_days_until_expiry: Optional[int] = None
    is_under_construction: bool = False
    stale_signals: List[str] = field(default_factory=list)

    estimated_age_years: Optional[float] = None  # Rough estimate of site age
    freshness_score: float = 0.0                 # 0-100, higher = more stale
    error: Optional[str] = None


# ---------------------------------------------------------
# Freshness Monitor
# ---------------------------------------------------------
class FreshnessMonitor:
    """
    Passively analyzes website signals to estimate content freshness.

    Usage:
        monitor = FreshnessMonitor()
        result = monitor.check("Acme Corp", "https://acmecorp.com")
    """

    def __init__(self, timeout: int = 10):
        self.timeout = timeout
        self.current_year = datetime.now().year
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
            )
        }

    def _fetch(self, url: str):
        """Fetch page and return (soup, response_headers) or (None, {})."""
        try:
            r = requests.get(url, headers=self.headers, timeout=self.timeout)
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "html.parser")
            return soup, dict(r.headers)
        except Exception as e:
            logger.warning(f"Could not fetch {url}: {e}")
            return None, {}

    def _extract_copyright_year(self, soup: BeautifulSoup) -> Optional[int]:
        """
        Find the copyright year in the page footer.
        Typical patterns: "© 2019", "Copyright 2019", "2019 Acme Corp"
        """
        try:
            # Look for footer or sections commonly housing copyrights
            footer = soup.find(["footer", "div", "span", "p"], class_=re.compile(r"footer|copyright|copy", re.I))
            text = footer.get_text() if footer else soup.get_text()
            
            # Find copyright years (4 digits) following common copyright prefixes
            # Example: Copyright © 2017-2022 or ©2019
            matches = re.findall(r"(?:©|copyright|copr\.)\s*(?:[12]\d{3}\s*-\s*)?([12]\d{3})", text, re.I)
            if matches:
                years = [int(y) for y in matches if 1990 <= int(y) <= self.current_year + 1]
                if years:
                    return max(years)

            # Fallback regex search for any © followed by year
            fallback = re.search(r"©\s*(\d{4})", text)
            if fallback:
                yr = int(fallback.group(1))
                if 1990 <= yr <= self.current_year + 1:
                    return yr
        except Exception as e:
            logger.debug(f"Error extracting copyright year: {e}")
        return None

    def _check_stale_patterns(self, soup: BeautifulSoup) -> List[str]:
        """
        Check page text for construction/maintenance patterns.
        """
        try:
            text = soup.get_text().lower()
            return [p for p in STALE_PAGE_PATTERNS if p in text]
        except Exception:
            return []

    def _check_ssl_expiry(self, hostname: str) -> tuple[Optional[str], Optional[int]]:
        """
        Check SSL certificate expiry date for the domain.
        """
        try:
            context = ssl.create_default_context()
            context.check_hostname = True
            context.verify_mode = ssl.CERT_REQUIRED
            
            with socket.create_connection((hostname, 443), timeout=self.timeout) as sock:
                with context.wrap_socket(sock, server_hostname=hostname) as ssock:
                    cert = ssock.getpeercert()
                    if cert and 'notAfter' in cert:
                        expiry_str = cert['notAfter']
                        # Parse date like: 'May 17 23:59:59 2026 GMT'
                        expiry = datetime.strptime(expiry_str, '%b %d %H:%M:%S %Y %Z')
                        
                        # Match timezone-naive utc
                        now = datetime.now(timezone.utc).replace(tzinfo=None)
                        days_left = (expiry - now).days
                        return expiry.isoformat(), days_left
        except Exception as e:
            logger.warning(f"SSL expiry check failed for {hostname}: {e}")
        return None, None

    def _calculate_score(self, result: FreshnessResult) -> float:
        """
        Compute freshness_score (0-100). Higher = more stale = more intent signal.

        Scoring logic:
            - Copyright year 5+ years ago   → +50 points
            - Copyright year 3-4 years ago  → +30 points
            - Copyright year 1-2 years ago  → +10 points
            - SSL expiring within 30 days   → +20 points
            - SSL expired                   → +40 points
            - Under construction detected   → +30 points
            - Each stale pattern            → +10 points
        """
        score = 0.0

        if result.copyright_year:
            age = self.current_year - result.copyright_year
            if age >= 5:
                score += 50.0
            elif age >= 3:
                score += 30.0
            elif age >= 1:
                score += 10.0

        if result.is_under_construction:
            score += 30.0

        if result.stale_signals:
            score += len(result.stale_signals) * 10.0

        if result.ssl_days_until_expiry is not None:
            if result.ssl_days_until_expiry < 0:
                score += 40.0
            elif result.ssl_days_until_expiry <= 30:
                score += 20.0

        return round(min(100.0, score), 1)

    def check(self, business_name: str, website_url: Optional[str]) -> FreshnessResult:
        """
        Run all freshness checks against a business website.

        Args:
            business_name: Display name for logging.
            website_url:   Business homepage URL.

        Returns:
            FreshnessResult with freshness_score for intent_engine.
        """
        result = FreshnessResult(
            business_name=business_name,
            website_url=website_url
        )

        if not website_url:
            result.error = "No website URL provided"
            return result

        soup, response_headers = self._fetch(website_url)
        if not soup:
            result.error = "Failed to fetch website"
            return result

        result.last_modified_header = response_headers.get("Last-Modified")
        result.copyright_year = self._extract_copyright_year(soup)
        result.stale_signals = self._check_stale_patterns(soup)
        result.is_under_construction = len(result.stale_signals) > 0

        # SSL check (extract hostname from URL)
        try:
            from urllib.parse import urlparse
            hostname = urlparse(website_url).hostname
            if hostname:
                result.ssl_expiry_date, result.ssl_days_until_expiry = \
                    self._check_ssl_expiry(hostname)
        except Exception as e:
            logger.warning(f"SSL expiry check skipped for {website_url}: {e}")

        if result.copyright_year:
            result.estimated_age_years = round(self.current_year - result.copyright_year, 1)

        result.freshness_score = self._calculate_score(result)

        logger.info(
            f"[{business_name}] Copyright year: {result.copyright_year}, "
            f"Stale signals: {len(result.stale_signals)}, "
            f"Freshness score: {result.freshness_score}"
        )
        return result


# ---------------------------------------------------------
# Self-Test
# ---------------------------------------------------------
if __name__ == "__main__":
    import json
    monitor = FreshnessMonitor()
    test = monitor.check("Example Corp", "https://example.com")
    print(json.dumps(asdict(test), indent=2))
