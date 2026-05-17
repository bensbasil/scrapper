"""
justdial.py
-----------
Responsibility:
    Scrape business listings from JustDial — one of India's largest local
    business directories. Supplements Google Maps data with JustDial-specific
    fields (verified badge, JD rating, service tags, etc.).

Why JustDial:
    - Many local Indian businesses are listed on JustDial but have no website
    - JustDial often has more granular categories for Indian SMBs
    - JD badges (Verified, Top Rated) are trust signals for outreach credibility
    - Phone numbers on JD are often more up-to-date than on Maps

Architecture decision:
    Extends BaseScraper to conform to the standard pipeline interface.
    Output is normalized to the standard BusinessData schema used by
    google_maps.py, ensuring entity_resolver.py can deduplicate across sources.

Data collected:
    - business_name, category, address, phone
    - jd_rating, jd_reviews_count
    - jd_verified (boolean)
    - website (when listed)
    - source_platform = "justdial"

LEGAL NOTE:
    Scraping JustDial may violate their Terms of Service.
    Review JD's robots.txt and ToS before enabling this connector in production.
    Consider using their official API if available.

TODO:
    - Implement Playwright-based search automation (JD is JS-heavy)
    - Map JD categories to standard category taxonomy
    - Handle JD's anti-bot measures (CAPTCHA, dynamic class names)
    - Normalize phone numbers from JD format (+91-XXX-XXXXXXX)
    - Store jd_rating and jd_verified in extended businesses table columns
    - Run entity_resolver.compare() on each result against existing DB records
"""

import logging
from dataclasses import dataclass, asdict
from typing import Optional, List, Any, Dict

from scraper.base_scraper import BaseScraper
from scraper.utils.logger import get_scraper_logger
from scraper.utils.exceptions import ScraperException, DOMChangeError

logger = get_scraper_logger("JustDialScraper")


# ---------------------------------------------------------
# Output Data Structure
# ---------------------------------------------------------
@dataclass
class JustDialBusinessData:
    """
    Business data scraped from JustDial.
    Normalized to be compatible with the standard BusinessData schema.
    """
    business_name: Optional[str] = None
    category: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    website: Optional[str] = None
    jd_rating: Optional[float] = None
    jd_reviews_count: Optional[int] = None
    jd_verified: bool = False
    source_platform: str = "justdial"


# ---------------------------------------------------------
# JustDial Scraper
# ---------------------------------------------------------
class JustDialScraper(BaseScraper):
    """
    Scrapes local business listings from JustDial.
    Implements the BaseScraper interface for pipeline compatibility.

    Usage:
        scraper = JustDialScraper(headless=True)
        businesses = scraper.scrape("Gyms in Trivandrum", max_results=20)
    """

    BASE_URL = "https://www.justdial.com"

    def __init__(self, headless: bool = True):
        self.headless = headless
        # TODO: Initialize Playwright browser context

    def fetch_raw(self, target: str, **kwargs) -> Any:
        """
        Navigate to JustDial search results for the given query and
        return raw HTML or a structured list of raw listing elements.

        Args:
            target: Search query string (e.g., "Gyms in Trivandrum, Kerala")

        TODO: Implement:
            - Launch Playwright browser
            - Navigate to justdial.com/search?q={target}
            - Wait for listing cards to load
            - Handle infinite scroll or pagination
            - Return raw page HTML or list of element handles
        """
        # TODO: Implement Playwright-based fetch
        logger.info(f"JustDialScraper.fetch_raw called for: {target}")
        raise NotImplementedError("JustDialScraper.fetch_raw not yet implemented")

    def parse_data(self, raw_data: Any, **kwargs) -> List[Dict[str, Any]]:
        """
        Parse raw HTML/elements into a list of semi-structured business dicts.

        TODO: Implement:
            - Find all listing card elements (CSS selectors — may change)
            - Extract business_name from title element
            - Extract rating, reviews from rating badge
            - Extract address, phone from info section
            - Extract website URL from external link button
            - Extract verified badge boolean

        NOTE: JustDial frequently updates class names. Add selectors to
              AI_MEMORY/selector_changes.md when they break.
        """
        # TODO: Implement parsing logic
        logger.info("JustDialScraper.parse_data called")
        raise NotImplementedError("JustDialScraper.parse_data not yet implemented")

    def normalize(self, parsed_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Normalize JustDial-specific fields to match the standard BusinessData schema.
        Ensures downstream pipeline_runner and entity_resolver work without modification.

        TODO: Implement field mapping:
            - Map JD category names to standard taxonomy
            - Normalize phone to E.164 format
            - Add source_platform = "justdial" to each record
        """
        # TODO: Implement normalization
        logger.info("JustDialScraper.normalize called")
        raise NotImplementedError("JustDialScraper.normalize not yet implemented")

    def scrape(self, search_query: str, max_results: int = 20) -> List[JustDialBusinessData]:
        """
        High-level method: search → parse → normalize → return.

        Args:
            search_query: Search string (e.g., "Gyms in Trivandrum, Kerala")
            max_results:  Maximum number of results to collect.

        Returns:
            List of JustDialBusinessData objects.

        TODO: Implement full scrape flow using BaseScraper.run() pattern
        """
        logger.info(f"JustDialScraper.scrape called: '{search_query}' (max: {max_results})")
        # TODO: Implement full scrape flow
        return []


# ---------------------------------------------------------
# Self-Test
# ---------------------------------------------------------
if __name__ == "__main__":
    scraper = JustDialScraper(headless=True)
    logger.info("JustDialScraper initialized. Scrape methods not yet implemented.")
    print("JustDial connector skeleton loaded successfully.")
