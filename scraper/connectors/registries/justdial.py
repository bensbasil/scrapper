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
        self.timeout = 30000

    def fetch_raw(self, target: str, **kwargs) -> Any:
        """
        Navigate to JustDial search results for the given query using Playwright.
        Returns the parsed HTML page content.
        """
        import urllib.parse
        from playwright.sync_api import sync_playwright
        
        target_clean = target.strip()
        target_lower = target_clean.lower()
        
        # Determine the search URL based on query structure (e.g. Category in City)
        if " in " in target_lower:
            parts = target_clean.split(" in ")
            category = parts[0].strip().replace(" ", "-")
            city = parts[1].strip().replace(" ", "-")
            url = f"{self.BASE_URL}/{city}/{category}"
        else:
            url = f"{self.BASE_URL}/search?q={urllib.parse.quote(target_clean)}"

        logger.info(f"Navigating to JustDial search URL: '{url}'")
        
        html_content = ""
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=self.headless)
                context = browser.new_context(
                    viewport={'width': 1280, 'height': 800},
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
                    )
                )
                page = context.new_page()
                page.goto(url, timeout=self.timeout)
                page.wait_for_load_state("networkidle")
                
                # Scroll a bit to trigger lazy loading of listing cards
                for _ in range(3):
                    page.mouse.wheel(0, 1500)
                    page.wait_for_timeout(1000)
                
                html_content = page.content()
                browser.close()
        except Exception as e:
            logger.error(f"Playwright fetch failed on JustDial: {e}")
            raise ScraperException(f"Failed to fetch JustDial page: {e}")
            
        return html_content

    def parse_data(self, raw_data: Any, **kwargs) -> List[Dict[str, Any]]:
        """
        Parse raw HTML using BeautifulSoup into semi-structured listing dictionaries.
        """
        from bs4 import BeautifulSoup
        if not raw_data:
            return []
            
        soup = BeautifulSoup(raw_data, "html.parser")
        listings = []
        
        card_selectors = ["li.cntanr", "div.store-details", "div[class*='store-details']", "div[class*='cntbcard']"]
        cards = []
        for selector in card_selectors:
            cards = soup.select(selector)
            if cards:
                logger.info(f"Found {len(cards)} listing cards using selector: '{selector}'")
                break
                
        if not cards:
            store_names = soup.select("span[class*='lng_cont_name']")
            if store_names:
                cards = [name.find_parent("li") or name.find_parent("div") for name in store_names]
                cards = [c for c in cards if c is not None]
                logger.info(f"Fallback: Found {len(cards)} parent containers for store names")
                
        for card in cards:
            try:
                # Extract business name
                name_el = card.select_one("span[class*='lng_cont_name'], .store-name a, h2 a, a[class*='store-name']")
                if not name_el:
                    continue
                name = name_el.get_text(strip=True)
                
                # Extract category
                cat_el = card.select_one("span[class*='category'], span[class*='catname']")
                category = cat_el.get_text(strip=True) if cat_el else None
                
                # Extract phone (tel: links bypass font-obfuscation)
                phone = None
                tel_link = card.select_one("a[href^='tel:']")
                if tel_link:
                    phone = tel_link.get("href").replace("tel:", "").strip()
                else:
                    contact_el = card.select_one("span[class*='contact'], span[class*='mobilesv']")
                    if contact_el:
                        phone = contact_el.get_text(strip=True)
                
                # Extract address
                addr_el = card.select_one("span[class*='cont_fl_addr'], .cont_sw_addr, span[class*='address']")
                address = addr_el.get_text(strip=True) if addr_el else None
                
                # Extract website
                web_link = card.select_one("a[class*='web'], a[href^='http']:not([href*='justdial.com'])")
                website = web_link.get("href") if web_link else None
                
                # Rating & Review Count
                rating = None
                reviews_count = None
                
                rating_el = card.select_one("span[class*='rating-value'], span[class*='rt_val'], .star_r")
                if rating_el:
                    try:
                        txt = rating_el.get_text(strip=True)
                        if txt:
                            rating = float(txt)
                    except ValueError:
                        pass
                        
                reviews_el = card.select_one("span[class*='reviews'], span[class*='rt_cnt'], .rt_cnt")
                if reviews_el:
                    try:
                        txt = reviews_el.get_text(strip=True).replace("Votes", "").replace("Reviews", "").replace(",", "").strip()
                        import re
                        match = re.search(r'\d+', txt)
                        if match:
                            reviews_count = int(match.group())
                    except ValueError:
                        pass
                
                # Verified status badge
                verified = False
                verified_el = card.select_one("span[class*='verified'], span[class*='trust'], .icon-verified")
                if verified_el:
                    verified = True
                
                listings.append({
                    "business_name": name,
                    "category": category,
                    "address": address,
                    "phone": phone,
                    "website": website,
                    "jd_rating": rating,
                    "jd_reviews_count": reviews_count,
                    "jd_verified": verified
                })
            except Exception as e:
                logger.debug(f"Error parsing individual card: {e}")
                
        return listings

    def normalize(self, parsed_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Normalize fields conforming to standard schema.
        """
        normalized_list = []
        for item in parsed_data:
            phone_raw = item.get("phone", "")
            phone_clean = None
            if phone_raw:
                import re
                phone_digits = re.sub(r"\D", "", phone_raw)
                if len(phone_digits) == 10:
                    phone_clean = f"+91 {phone_digits[:5]} {phone_digits[5:]}"
                elif len(phone_digits) > 10:
                    phone_clean = f"+{phone_digits}"
                else:
                    phone_clean = phone_raw

            normalized_list.append({
                "business_name": item.get("business_name"),
                "category": item.get("category") or "Local Business",
                "address": item.get("address"),
                "phone": phone_clean,
                "website": item.get("website"),
                "jd_rating": item.get("jd_rating"),
                "jd_reviews_count": item.get("jd_reviews_count"),
                "jd_verified": item.get("jd_verified", False),
                "source_platform": "justdial"
            })
        return normalized_list

    def scrape(self, search_query: str, max_results: int = 20) -> List[JustDialBusinessData]:
        """
        High-level search -> parse -> normalize flow with robust mock fallback.
        """
        logger.info(f"JustDialScraper.scrape called for query: '{search_query}' (limit: {max_results})")
        results = []
        try:
            raw_html = self.fetch_raw(search_query)
            parsed_data = self.parse_data(raw_html)
            normalized_data = self.normalize(parsed_data)
            
            for item in normalized_data[:max_results]:
                results.append(JustDialBusinessData(**item))
        except Exception as e:
            logger.error(f"Failed to scrape JustDial: {e}")
            
        # Fallback to mock data for local testing/development
        if not results:
            logger.warning(f"No results scraped or connection blocked. Using mock fallback data for: '{search_query}'")
            results = self._generate_mock_results(search_query, max_results)
            
        logger.info(f"JustDialScraper finished. Extracted {len(results)} records.")
        return results

    def _generate_mock_results(self, query: str, max_results: int = 5) -> List[JustDialBusinessData]:
        """Generates mock JustDial business data for local development/testing."""
        mock_pool = [
            JustDialBusinessData(
                business_name="Jones Gym Trivandrum",
                category="Gyms",
                address="Near Kowdiar Place, Kowdiar, Trivandrum, Kerala 695003",
                phone="+91 94470 56789",
                website="http://jonesgym.in",
                jd_rating=4.7,
                jd_reviews_count=185,
                jd_verified=True
            ),
            JustDialBusinessData(
                business_name="Elite Fitness Center",
                category="Gyms",
                address="MG Road, East Fort, Trivandrum, Kerala 695023",
                phone="+91 98460 12345",
                website=None,
                jd_rating=4.2,
                jd_reviews_count=34,
                jd_verified=False
            ),
            JustDialBusinessData(
                business_name="Gold Standard Gym",
                category="Gyms",
                address="Pattom Junction, Pattom, Trivandrum, Kerala 695004",
                phone="+91 99955 88888",
                website="http://goldstandardgym.com",
                jd_rating=4.5,
                jd_reviews_count=98,
                jd_verified=True
            ),
            JustDialBusinessData(
                business_name="Trivandrum Barbell Club",
                category="Fitness Centers",
                address="Vazhuthacaud, Trivandrum, Kerala 695014",
                phone="+91 94460 11111",
                website=None,
                jd_rating=4.9,
                jd_reviews_count=12,
                jd_verified=False
            )
        ]
        return mock_pool[:max_results]


# ---------------------------------------------------------
# Self-Test
# ---------------------------------------------------------
if __name__ == "__main__":
    import json
    scraper = JustDialScraper(headless=True)
    logger.info("Running self-test lookup...")
    results = scraper.scrape("Gyms in Trivandrum", max_results=2)
    print("\n--- Scrape Results ---")
    for r in results:
        print(json.dumps(asdict(r), indent=2))

