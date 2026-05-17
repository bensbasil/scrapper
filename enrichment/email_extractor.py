"""
email_extractor.py
------------------
Responsibility:
    Crawl a business website and extract all email addresses found on the page.
    Checks homepage, contact page, about page, and footer links.

Architecture decision:
    Kept separate from company_website.py so extraction logic can be
    independently tested, updated, or swapped without affecting the main
    website audit pipeline.

Output contract:
    Returns EmailExtractionResult dataclass — JSON/PostgreSQL compatible.

TODO:
    - Implement multi-page crawl (homepage → /contact → /about)
    - Add regex-based extraction from visible text AND mailto: href attributes
    - Detect obfuscated emails (e.g. "user [at] domain [dot] com")
    - Rate-limit requests to respect server load
"""

import re
import logging
from dataclasses import dataclass, asdict, field
from typing import List, Optional, Any

import requests
from bs4 import BeautifulSoup

from scraper.utils.logger import get_scraper_logger

logger = get_scraper_logger("EmailExtractor")

# ---------------------------------------------------------
# Output Data Structure
# ---------------------------------------------------------
@dataclass
class EmailExtractionResult:
    """
    Structured output for extracted emails.
    Designed for direct INSERT into a future `email_intelligence` table.
    """
    business_name: str
    website_url: Optional[str]
    extracted_emails: List[str] = field(default_factory=list)
    pages_checked: List[str] = field(default_factory=list)
    extraction_method: str = "regex"
    error: Optional[str] = None


# ---------------------------------------------------------
# Email Extractor
# ---------------------------------------------------------
class EmailExtractor:
    """
    Extracts emails from business websites using static HTTP requests.

    Usage:
        extractor = EmailExtractor()
        result = extractor.extract("Acme Corp", "https://acmecorp.com")
    """

    EMAIL_REGEX = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")

    # Common subpaths to check for contact info
    CONTACT_PATHS = ["/", "/contact", "/contact-us", "/about", "/about-us"]

    def __init__(self, timeout: int = 10):
        self.timeout = timeout
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
            )
        }

    def _fetch_page(self, url: str) -> Optional[str]:
        """Fetch a single page's HTML. Returns None on failure."""
        try:
            response = requests.get(url, headers=self.headers, timeout=self.timeout)
            response.raise_for_status()
            return response.text
        except Exception as e:
            logger.warning(f"Failed to fetch {url}: {e}")
            return None

    def _extract_from_html(self, html: str) -> List[str]:
        """
        Extract email addresses from raw HTML using two strategies:
        1. Regex scan over full HTML text
        2. <a href="mailto:..."> link scanning
        """
        emails = set()

        # Strategy 1: Regex scan over the entire HTML text
        matches = self.EMAIL_REGEX.findall(html)
        for email in matches:
            emails.add(email.strip().lower())

        # Strategy 2: BeautifulSoup scan for mailto: links
        try:
            soup = BeautifulSoup(html, "html.parser")
            for a_tag in soup.find_all("a", href=True):
                href = a_tag["href"].strip()
                if href.lower().startswith("mailto:"):
                    # Handle queries or subjects in mailto (e.g. mailto:sales@corp.com?subject=hi)
                    email = href[7:].split("?")[0].strip().lower()
                    if email:
                        emails.add(email)
        except Exception as e:
            logger.debug(f"Error parsing BeautifulSoup tags for mailto: {e}")

        # Filter out common false positives (e.g. image extensions, CSS/JS files)
        filtered_emails = []
        invalid_extensions = ('.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.pdf', '.css', '.js', '.ico')
        
        for email in emails:
            # Skip invalid extensions
            if email.endswith(invalid_extensions):
                continue
            
            # Simple validation: must contain exactly one @ and at least one dot in domain name
            if "@" in email:
                parts = email.split("@")
                if len(parts) == 2 and "." in parts[1] and len(parts[1].split(".")[-1]) >= 2:
                    filtered_emails.append(email)

        return filtered_emails

    def extract(self, business_name: str, website_url: Optional[str]) -> EmailExtractionResult:
        """
        Main entrypoint. Crawls common subpages and aggregates found emails.

        Args:
            business_name: Display name for logging and output.
            website_url:   Base URL of the business site.

        Returns:
            EmailExtractionResult with deduplicated emails.
        """
        result = EmailExtractionResult(
            business_name=business_name,
            website_url=website_url
        )

        if not website_url:
            result.error = "No website URL provided"
            return result

        # Normalize base URL
        base = website_url.rstrip("/")

        all_emails: set = set()

        for path in self.CONTACT_PATHS:
            page_url = base + path
            html = self._fetch_page(page_url)
            if html:
                result.pages_checked.append(page_url)
                found = self._extract_from_html(html)
                all_emails.update(found)
                logger.info(f"[{business_name}] {path}: found {len(found)} email(s)")

        result.extracted_emails = list(all_emails)
        logger.info(
            f"[{business_name}] Extraction complete. Total unique emails: {len(result.extracted_emails)}"
        )
        return result


# ---------------------------------------------------------
# Self-Test
# ---------------------------------------------------------
if __name__ == "__main__":
    import json
    extractor = EmailExtractor()
    test = extractor.extract("Example Corp", "https://example.com")
    print(json.dumps(asdict(test), indent=2))
