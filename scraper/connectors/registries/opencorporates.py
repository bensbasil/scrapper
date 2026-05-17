"""
opencorporates.py
-----------------
Responsibility:
    Query OpenCorporates — the world's largest open database of company
    information — to enrich business records with official registration data.

Why OpenCorporates:
    - Provides company registration number, incorporation date, and official
      registered address from government records
    - Helps verify that a business is real and legally registered
    - Company age is a valuable signal: old companies = established but potentially
      digitally behind; new companies = growth stage, receptive to modern tooling

Data collected:
    - company_number (official registration number)
    - jurisdiction (e.g., "in_mh" for Maharashtra, India)
    - incorporation_date
    - company_status (active, dissolved, etc.)
    - registered_address
    - company_type (Private Limited, Proprietorship, LLP, etc.)
    - source_platform = "opencorporates"

Access method:
    OpenCorporates provides a free REST API (rate-limited).
    API key required for higher quotas.
    No scraping required — this is a clean API connector.

Architecture decision:
    Extends BaseScraper despite being an API connector — this ensures it
    plugs into the standard enrichment pipeline without modification.

TODO:
    - Register for OpenCorporates API key and store in .env as OC_API_KEY
    - Implement search_by_name(name, jurisdiction="in") using their REST API
    - Handle pagination in API responses
    - Map OpenCorporates jurisdiction codes to readable state/country names
    - Integrate with entity_resolver.py for company name matching
    - Store enrichment results in a new `company_registry` PostgreSQL table
"""

import os
import logging
from dataclasses import dataclass, asdict
from typing import Optional, List, Any, Dict

import requests

from scraper.base_scraper import BaseScraper
from scraper.utils.logger import get_scraper_logger
from scraper.utils.exceptions import ScraperException, SourceTimeoutError

logger = get_scraper_logger("OpenCorporatesScraper")

OC_API_BASE = "https://api.opencorporates.com/v0.4"


# ---------------------------------------------------------
# Output Data Structure
# ---------------------------------------------------------
@dataclass
class CompanyRegistryData:
    """
    Official company registration data from OpenCorporates.
    Designed for a future `company_registry` table in PostgreSQL.
    """
    business_name: Optional[str] = None
    company_number: Optional[str] = None
    jurisdiction: Optional[str] = None       # e.g. "in_mh" for Maharashtra
    jurisdiction_label: Optional[str] = None  # e.g. "Maharashtra, India"
    incorporation_date: Optional[str] = None  # ISO date string
    company_status: Optional[str] = None      # "active", "dissolved", etc.
    company_type: Optional[str] = None        # "Private Limited Company", etc.
    registered_address: Optional[str] = None
    opencorporates_url: Optional[str] = None
    source_platform: str = "opencorporates"
    error: Optional[str] = None


# ---------------------------------------------------------
# OpenCorporates Connector
# ---------------------------------------------------------
class OpenCorporatesScraper(BaseScraper):
    """
    Enriches business records with official company registration data
    from the OpenCorporates REST API.

    Usage:
        scraper = OpenCorporatesScraper()
        result = scraper.enrich("Acme Technologies Pvt Ltd", jurisdiction="in")
    """

    def __init__(self):
        self.api_key = os.getenv("OC_API_KEY")
        if not self.api_key:
            logger.warning(
                "OC_API_KEY not set in .env. "
                "Requests will be rate-limited to ~10/day without a key."
            )
        self.timeout = 15

    def _build_params(self, extra: Optional[Dict] = None) -> Dict[str, str]:
        """Build standard API request parameters."""
        params = {}
        if self.api_key:
            params["api_token"] = self.api_key
        if extra:
            params.update(extra)
        return params

    def fetch_raw(self, target: str, **kwargs) -> Any:
        """
        Search OpenCorporates API for a company by name.

        Args:
            target: Company name to search for.
            kwargs:
                jurisdiction (str): OC jurisdiction code, e.g. "in" for India.
                                    Leave empty to search globally.

        Returns:
            Raw API JSON response dict.

        TODO: Implement:
            params = self._build_params({
                "q": target,
                "jurisdiction_code": kwargs.get("jurisdiction", "in"),
                "per_page": 5,
            })
            response = requests.get(f"{OC_API_BASE}/companies/search", params=params)
            return response.json()
        """
        # TODO: Implement OpenCorporates API search
        logger.info(f"OpenCorporatesScraper.fetch_raw called for: {target}")
        raise NotImplementedError("OpenCorporatesScraper.fetch_raw not yet implemented")

    def parse_data(self, raw_data: Any, **kwargs) -> List[Dict[str, Any]]:
        """
        Parse API JSON response into a list of company record dicts.

        TODO: Implement:
            companies = raw_data.get("results", {}).get("companies", [])
            return [c.get("company", {}) for c in companies]
        """
        # TODO: Implement parsing logic
        logger.info("OpenCorporatesScraper.parse_data called")
        raise NotImplementedError("OpenCorporatesScraper.parse_data not yet implemented")

    def normalize(self, parsed_data: List[Dict[str, Any]]) -> CompanyRegistryData:
        """
        Normalize the first (best match) company record into CompanyRegistryData.

        TODO: Implement field mapping from OC API response structure:
            {
                "name": ...,
                "company_number": ...,
                "jurisdiction_code": ...,
                "incorporation_date": ...,
                "current_status": ...,
                "company_type": ...,
                "registered_address": {...},
                "opencorporates_url": ...
            }
        """
        # TODO: Implement normalization
        logger.info("OpenCorporatesScraper.normalize called")
        raise NotImplementedError("OpenCorporatesScraper.normalize not yet implemented")

    def enrich(
        self,
        business_name: str,
        jurisdiction: str = "in"
    ) -> CompanyRegistryData:
        """
        Convenience method: search + parse + normalize + return best match.

        Args:
            business_name: The company name to look up.
            jurisdiction:  OC jurisdiction code (default "in" for India).

        Returns:
            CompanyRegistryData for the best matching company, or an empty
            result with error set if not found.
        """
        logger.info(
            f"OpenCorporatesScraper.enrich: '{business_name}' (jurisdiction={jurisdiction})"
        )
        # TODO: Implement full enrich flow
        return CompanyRegistryData(
            business_name=business_name,
            error="Not yet implemented"
        )


# ---------------------------------------------------------
# Self-Test
# ---------------------------------------------------------
if __name__ == "__main__":
    import json
    scraper = OpenCorporatesScraper()
    logger.info("OpenCorporatesScraper initialized. API methods not yet implemented.")
    print("OpenCorporates connector skeleton loaded successfully.")
