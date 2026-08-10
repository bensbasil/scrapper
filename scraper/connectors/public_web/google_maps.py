import csv
import json
import functools
import time
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import List, Dict, Any, Optional, Callable

from playwright.sync_api import sync_playwright, Page, TimeoutError as PlaywrightTimeoutError

# Critical fix #3: use the shared logger utility instead of a copy-pasted StructuredLogger.
from scraper.utils.logger import get_scraper_logger

logger = get_scraper_logger(__name__)

# ---------------------------------------------------------
# 2. Data Structure (Prepares for PostgreSQL Integration)
# ---------------------------------------------------------
@dataclass
class BusinessData:
    """Matches DATA_DICTIONARY.md perfectly."""
    business_name: Optional[str] = None
    category: Optional[str] = None
    website: Optional[str] = None
    google_rating: Optional[float] = None
    review_count: Optional[int] = None
    phone: Optional[str] = None
    address: Optional[str] = None

# ---------------------------------------------------------
# 3. Utilities (Retry Handling)
# ---------------------------------------------------------
def retry(max_attempts: int = 3, delay: float = 2.0):
    """Decorator to retry flaky scraping actions."""
    def decorator(func: Callable):
        @functools.wraps(func)  # Preserves __name__, __doc__ and signature for logging.
        def wrapper(*args, **kwargs):
            attempts = 0
            while attempts < max_attempts:
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    attempts += 1
                    logger.warning(f"Attempt {attempts}/{max_attempts} failed for {func.__name__}: {e}")
                    if attempts == max_attempts:
                        logger.error(f"All {max_attempts} attempts failed for {func.__name__}")
                        raise e
                    time.sleep(delay)
        return wrapper
    return decorator

# ---------------------------------------------------------
# 4. Main Scraper Class
# ---------------------------------------------------------
class GoogleMapsScraper:
    def __init__(self, headless: bool = True, output_dir: str = "data/raw"):
        self.headless = headless
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
    def _save_csv(self, data: List[BusinessData], filename: str):
        """Export clean CSV data."""
        if not data:
            return
        filepath = self.output_dir / f"{filename}.csv"
        try:
            with open(filepath, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=data[0].__dict__.keys())
                writer.writeheader()
                writer.writerows([asdict(d) for d in data])
            logger.info(f"Saved {len(data)} records to CSV: {filepath}")
        except Exception as e:
            logger.error(f"Failed to save CSV: {e}")

    def _save_json(self, data: List[BusinessData], filename: str):
        """Save JSON for debugging and partial progress."""
        filepath = self.output_dir / f"{filename}.json"
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump([asdict(d) for d in data], f, indent=4, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to save JSON: {e}")

    def _safe_extract(self, page: Page, selector: str, attribute: str = "text") -> Optional[str]:
        """Safely extract text or attribute with fast fallbacks for missing fields."""
        try:
            element = page.locator(selector).first
            if element.is_visible(timeout=1000):
                if attribute == "text":
                    return element.inner_text().strip()
                return element.get_attribute(attribute)
        except Exception:
            pass
        return None

    @retry(max_attempts=3, delay=1.0)
    def _extract_business_details(self, page: Page) -> BusinessData:
        """Modular logic for extracting details from an open business pane."""
        data = BusinessData()
        
        # Robust Selectors with fallbacks
        title_selectors = ["h1.DUwDvf", "h1[class*='header-title']"]
        for sel in title_selectors:
            val = self._safe_extract(page, sel)
            if val:
                data.business_name = val
                break
                
        data.category = self._safe_extract(page, "button.DkEaL")
        
        # Rating & Reviews
        rating_text = self._safe_extract(page, "div.F7nice > span")
        if rating_text:
            try:
                parts = rating_text.split('(')
                data.google_rating = float(parts[0].strip())
                data.review_count = int(parts[1].replace(')', '').replace(',', '').strip())
            except (ValueError, IndexError):
                pass
                
        # Info buttons (Address, Website, Phone)
        data.address = self._safe_extract(page, "button[data-item-id='address'] div[class*='fontBodyMedium']")
        if not data.address:  # Fallback
            data.address = self._safe_extract(page, "button[data-item-id='address']")
            
        raw_website = self._safe_extract(page, "a[data-item-id='authority']", attribute="href")
        if raw_website:
            raw_website = raw_website.strip()
            if "url?q=" in raw_website or "/url?q=" in raw_website:
                try:
                    from urllib.parse import urlparse, parse_qs
                    parsed = urlparse(raw_website)
                    params = parse_qs(parsed.query)
                    if "q" in params and params["q"]:
                        raw_website = params["q"][0]
                except Exception as e:
                    logger.debug(f"Failed to parse redirect wrapper URL {raw_website}: {e}")
            data.website = raw_website
        else:
            data.website = None
        
        data.phone = self._safe_extract(page, "button[data-item-id^='phone:tel:'] div[class*='fontBodyMedium']")
        if not data.phone:  # Fallback
            data.phone = self._safe_extract(page, "button[data-item-id^='phone:tel:']")
            
        return data

    def _scroll_feed(self, page: Page, feed_selector: str = "div[role='feed']") -> bool:
        """Handle scrolling to load more results, returns False if end is reached."""
        try:
            page.hover(feed_selector)
            page.mouse.wheel(0, 5000)
            page.wait_for_timeout(2500)
            
            # Check for the Google Maps "end of list" message
            end_msg = page.locator("span:has-text(\"You've reached the end of the list.\")")
            if end_msg.is_visible(timeout=1000):
                logger.info("Reached the end of the results list.")
                return False
            return True
        except Exception as e:
            logger.warning(f"Scrolling issue: {e}")
            return True

    def scrape(self, search_query: str, max_results: int = 20) -> List[BusinessData]:
        logger.info(f"Starting scrape: '{search_query}' (max: {max_results})")
        results: List[BusinessData] = []
        base_filename = f"gmaps_{search_query.replace(' ', '_')}_{int(time.time())}"
        
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=self.headless,
                slow_mo=500
            )
            context = browser.new_context(
                viewport={'width': 1280, 'height': 800},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36"
            )
            page = context.new_page()
            
            try:
                # Force English and specific region to avoid localization issues
                page.goto("https://www.google.com/maps?hl=en", timeout=60000)
                page.wait_for_load_state("domcontentloaded")
                page.wait_for_timeout(2000)

                # Accept cookies if presented (common in EU and other regions)
                # Try multiple common labels for consent buttons
                for label in ['Accept all', 'I agree', 'Agree', 'Accept', 'OK']:
                    try:
                        btn = page.get_by_role("button", name=label, exact=False)
                        if btn.is_visible(timeout=2000):
                            btn.click()
                            logger.info(f"Clicked consent button: {label}")
                            page.wait_for_timeout(2000)
                            break
                    except Exception:
                        continue
                
                # Execute Search
                try:
                    # Try multiple selectors for the search input
                    search_input = page.locator("input#searchboxinput, input[name='q'], input[aria-label*='Search']").first
                    search_input.wait_for(state="visible", timeout=15000)
                    search_input.click()
                    search_input.fill(search_query)
                    page.wait_for_timeout(1000)
                    
                    # Press Enter and also try clicking the search button
                    search_input.press("Enter")
                    
                    # Fallback: Click the search button if Enter didn't work
                    try:
                        search_btn = page.locator("#searchbox-searchbutton, button[aria-label='Search']").first
                        if search_btn.is_visible(timeout=2000):
                            search_btn.click()
                    except Exception:
                        pass
                        
                    logger.info(f"Search query '{search_query}' submitted.")
                except Exception as e:
                    logger.error(f"Failed to find or fill search input: {e}")
                    page.screenshot(path="debug_search_error.png")
                    return results
                
                # Take screenshot after search to verify results are loading
                page.wait_for_timeout(5000)
                page.screenshot(path="debug_maps_after_search.png")
                
                # Minor fix #17: Use resilient fallback selectors alongside a.hfpxzc in case Google Maps updates class names
                listing_selector = "a.hfpxzc, a[href*='/maps/place/'], div[role='feed'] a[href*='/maps/place']"
                try:
                    page.wait_for_timeout(5000)
                    page.wait_for_selector(listing_selector, timeout=60000)
                except PlaywrightTimeoutError:
                    logger.error("Timeout: Results feed did not load.")
                    page.screenshot(path="debug_results_timeout.png")
                    return results

                processed_names = set()
                consecutive_scrolls_without_new = 0
                
                while len(results) < max_results and consecutive_scrolls_without_new < 5:
                    listings = page.locator(listing_selector).all()
                    found_new = False
                    
                    for i in range(len(listings)):
                        if len(results) >= max_results:
                            break
                            
                        try:
                            # Skip if element is not interactable
                            if not listings[i].bounding_box():
                                continue
                                
                            listings[i].click(timeout=3000)
                            page.wait_for_timeout(1500) # Buffer for details pane to load
                            
                            # Extract using the modularized method
                            data = self._extract_business_details(page)
                            
                            # Deduplication & Validation
                            if data.business_name and data.business_name not in processed_names:
                                processed_names.add(data.business_name)
                                results.append(data)
                                found_new = True
                                logger.info(f"Extracted ({len(results)}/{max_results}): {data.business_name}")
                                
                                # Intermittent Save
                                if len(results) % 5 == 0:
                                    self._save_csv(results, base_filename)
                                    self._save_json(results, base_filename)
                                    
                        except Exception as e:
                            logger.debug(f"Skipping listing due to click/extract error: {e}")
                            
                    if found_new:
                        consecutive_scrolls_without_new = 0
                    else:
                        consecutive_scrolls_without_new += 1
                        logger.info(f"No new listings found in view. Scroll attempt {consecutive_scrolls_without_new}/5...")
                        
                    # Trigger modular scrolling
                    if not self._scroll_feed(page):
                        break

            except Exception as e:
                logger.error(f"Critical scraping error: {e}")
            finally:
                browser.close()
                
        # Final Full Save
        self._save_csv(results, base_filename)
        self._save_json(results, base_filename)
        logger.info(f"Scrape completed. Total records: {len(results)}")
        
        return results

if __name__ == "__main__":
    # Example test
    scraper = GoogleMapsScraper(headless=False)
    data = scraper.scrape("coffee shops in manhattan", max_results=5)
    print(f"Extraction finished: {len(data)} rows.")
