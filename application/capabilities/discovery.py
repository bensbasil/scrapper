"""
application/capabilities/discovery.py
-------------------------------------
Typed application capability for prospect discovery.
Delegates to canonical discovery connectors without exposing scraper internals.
"""

import logging
from typing import Optional, List, Any
from dataclasses import asdict

from schemas.business import Business
from application.contracts.inputs import DiscoverProspectsInput
from application.contracts.outputs import DiscoverProspectsOutput
from application.policies.classification import PolicyClass

logger = logging.getLogger(__name__)


class DiscoverProspectsCapability:
    """
    Exposes prospect discovery across Google Maps, JustDial, and IndiaMart.
    Classified as READ: zero database mutation or external messaging.
    """
    NAME = "discover_prospects"
    DESCRIPTION = "Discovers local candidate businesses by search query and location"
    POLICY_CLASS = PolicyClass.READ

    def __init__(self, gmaps_scraper: Optional[Any] = None, justdial_scraper: Optional[Any] = None, indiamart_scraper: Optional[Any] = None):
        self._gmaps = gmaps_scraper
        self._justdial = justdial_scraper
        self._indiamart = indiamart_scraper

    def execute(self, params: DiscoverProspectsInput) -> DiscoverProspectsOutput:
        """
        Executes discovery query and transforms results into typed Business entities.
        """
        src = params.source.lower().strip()
        limit = params.limit
        search_query = f"{params.query} {params.location}".strip() if params.location else params.query

        logger.info(f"[Capability:{self.NAME}] Querying source '{src}' for: '{search_query}' (limit={limit})")

        raw_items: List[Any] = []
        try:
            if src == "justdial":
                scraper = self._justdial
                if scraper is None:
                    from scraper.connectors.registries.justdial import JustDialScraper
                    scraper = JustDialScraper()
                raw_items = scraper.scrape(search_query, max_results=limit)
            elif src == "indiamart":
                scraper = self._indiamart
                if scraper is None:
                    from scraper.connectors.registries.indiamart import IndiaMartScraper
                    scraper = IndiaMartScraper()
                raw_items = scraper.scrape(search_query, max_results=limit)
            else:
                scraper = self._gmaps
                if scraper is None:
                    from scraper.connectors.public_web.google_maps import GoogleMapsScraper
                    scraper = GoogleMapsScraper()
                raw_items = scraper.scrape(search_query, max_results=limit)
        except Exception as e:
            logger.error(f"[Capability:{self.NAME}] Scraper execution failed: {e}")
            raw_items = []

        # Convert raw items to typed Business schemas safely
        businesses: List[Business] = []
        for item in raw_items:
            try:
                if isinstance(item, Business):
                    businesses.append(item)
                elif hasattr(item, "__dataclass_fields__"):
                    d = asdict(item)
                    businesses.append(Business.model_validate(d))
                elif isinstance(item, dict):
                    businesses.append(Business.model_validate(item))
            except Exception as val_err:
                logger.warning(f"[Capability:{self.NAME}] Failed to parse business item: {val_err}")

        return DiscoverProspectsOutput(
            query=search_query,
            total_found=len(businesses),
            source=src,
            businesses=businesses
        )
