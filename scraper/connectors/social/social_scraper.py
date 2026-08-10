import re
import logging
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Optional, Dict, Any

import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

from scraper.utils.logger import get_scraper_logger

logger = get_scraper_logger("SocialScraper")

@dataclass
class SocialScraperResult:
    platform: str
    url: str
    is_reachable: bool = False
    handle: Optional[str] = None
    follower_count: Optional[str] = None
    post_count: Optional[str] = None
    bio: Optional[str] = None
    error_message: Optional[str] = None

class SocialScraper:
    """
    Scrapes deep profile details from Instagram and Facebook public pages.
    Combines fast requests-based OG parsing with Playwright automation fallbacks.
    Reuses a cached Playwright browser instance across scrape calls for efficiency.
    """
    def __init__(self, timeout: int = 15):
        self.timeout = timeout
        self.headers = {
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.5 Mobile/15E148 Safari/604.1",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5"
        }
        self._playwright = None
        self._browser = None

    def _get_browser(self):
        """Lazily instantiates and returns a reusable Chromium browser instance."""
        if self._browser is None or not self._browser.is_connected():
            self._playwright = sync_playwright().start()
            self._browser = self._playwright.chromium.launch(headless=True)
        return self._browser

    def close(self):
        """Cleanly closes open browser and Playwright context."""
        if self._browser:
            try:
                self._browser.close()
            except Exception:
                pass
            self._browser = None
        if self._playwright:
            try:
                self._playwright.stop()
            except Exception:
                pass
            self._playwright = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def _detect_platform(self, url: str) -> Optional[str]:
        url_lower = url.lower()
        if "instagram.com" in url_lower:
            return "instagram"
        if "facebook.com" in url_lower or "fb.com" in url_lower:
            return "facebook"
        return None

    def scrape(self, url: str) -> SocialScraperResult:
        """
        Main entry point to scrape a social profile.
        """
        platform = self._detect_platform(url)
        if not platform:
            return SocialScraperResult(platform="unknown", url=url, error_message="Unsupported social platform URL.")

        logger.info(f"Scraping social profile: {url} ({platform})...")
        
        # 1. Attempt fast requests-based scrape
        result = self._scrape_via_requests(url, platform)
        if result.is_reachable and (result.follower_count or result.bio):
            logger.info(f"[{platform}] Successfully scraped via requests (Open Graph).")
            return result

        # 2. Fall back to Playwright if requests check is incomplete
        logger.info(f"[{platform}] Requests scrape incomplete. Falling back to Playwright...")
        pw_result = self._scrape_via_playwright(url, platform)
        if pw_result.is_reachable:
            return pw_result
            
        # Return requests result if playwright fails (at least tells us reachability)
        return result

    def _scrape_via_requests(self, url: str, platform: str) -> SocialScraperResult:
        result = SocialScraperResult(platform=platform, url=url)
        try:
            try:
                res = requests.get(url, headers=self.headers, timeout=self.timeout, verify=True)
            except requests.exceptions.SSLError as ssl_err:
                logger.warning(f"SSL verification failed for {url}: {ssl_err}. Retrying with verify=False...")
                res = requests.get(url, headers=self.headers, timeout=self.timeout, verify=False)

            result.is_reachable = res.status_code == 200

            if res.status_code == 200:
                soup = BeautifulSoup(res.content, "html.parser")
                
                # Parse Open Graph metadata (commonly available without login walls)
                og_desc = soup.find("meta", property="og:description")
                og_title = soup.find("meta", property="og:title")
                
                desc_content = og_desc.get("content", "") if og_desc else ""
                title_content = og_title.get("content", "") if og_title else ""

                if platform == "instagram":
                    # Instagram OG Desc format: "1,234 Followers, 567 Following, 89 Posts - See Instagram photos..."
                    match = re.search(r"([\d,.]+K?M?)\s*Followers", desc_content, re.IGNORECASE)
                    if match:
                        result.follower_count = match.group(1)
                    
                    posts_match = re.search(r"([\d,.]+K?M?)\s*Posts", desc_content, re.IGNORECASE)
                    if posts_match:
                        result.post_count = posts_match.group(1)

                    # Extract handle from title
                    # Instagram OG Title format: "Name (@handle) • Instagram photos and videos"
                    handle_match = re.search(r"\((@[\w_.]+)\)", title_content)
                    if handle_match:
                        result.handle = handle_match.group(1)
                    
                    result.bio = desc_content.split(" - ")[0] if desc_content else None
                    
                elif platform == "facebook":
                    # Facebook OG Desc format: "Name. 1,234 likes · 567 talking about this..."
                    likes_match = re.search(r"([\d,.]+K?M?)\s*likes", desc_content, re.IGNORECASE)
                    if likes_match:
                        result.follower_count = likes_match.group(1)
                    
                    result.handle = title_content.split(" | ")[0] if title_content else None
                    result.bio = desc_content

        except Exception as e:
            result.error_message = str(e)
            logger.debug(f"Requests-based social scrape failed: {e}")

        return result

    def _scrape_via_playwright(self, url: str, platform: str) -> SocialScraperResult:
        result = SocialScraperResult(platform=platform, url=url)
        try:
            browser = self._get_browser()
            context = browser.new_context(
                user_agent=self.headers["User-Agent"],
                viewport={"width": 375, "height": 667}
            )
            try:
                page = context.new_page()
                page.goto(url, timeout=20000, wait_until="domcontentloaded")
                
                result.is_reachable = True
                
                if platform == "instagram":
                    # Try to extract elements on mobile layout
                    page.wait_for_timeout(2000)
                    html = page.content()
                    soup = BeautifulSoup(html, "html.parser")
                    
                    # Look for follower text
                    text = page.locator("body").inner_text()
                    followers_match = re.search(r"([\d,.]+K?M?)\s*followers", text, re.IGNORECASE)
                    if followers_match:
                        result.follower_count = followers_match.group(1)
                    
                    posts_match = re.search(r"([\d,.]+K?M?)\s*posts", text, re.IGNORECASE)
                    if posts_match:
                        result.post_count = posts_match.group(1)
                        
                    # Handle extraction
                    meta_tag = soup.find("meta", property="og:title")
                    if meta_tag and meta_tag.get("content"):
                        h_match = re.search(r"\((@[\w_.]+)\)", meta_tag.get("content"))
                        if h_match:
                            result.handle = h_match.group(1)
                            
                elif platform == "facebook":
                    page.wait_for_timeout(2000)
                    text = page.locator("body").inner_text()
                    
                    # Matches "12K followers" or "1,234 followers"
                    followers_match = re.search(r"([\d,.]+K?M?)\s*followers", text, re.IGNORECASE)
                    if followers_match:
                        result.follower_count = followers_match.group(1)
                    else:
                        likes_match = re.search(r"([\d,.]+K?M?)\s*likes", text, re.IGNORECASE)
                        if likes_match:
                            result.follower_count = likes_match.group(1)
            finally:
                context.close()
        except Exception as e:
            result.error_message = str(e)
            logger.warning(f"Playwright-based social scrape failed: {e}")

        return result

if __name__ == "__main__":
    import json
    scraper = SocialScraper()
    # Test on a public Instagram profile (like Nike)
    res = scraper.scrape("https://www.instagram.com/nike")
    print(json.dumps(asdict(res), indent=2))
