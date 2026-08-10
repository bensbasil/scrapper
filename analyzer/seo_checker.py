import time
import logging
from pathlib import Path
from urllib.parse import urlparse
from dataclasses import dataclass, asdict
from typing import List, Dict, Any, Optional

import requests
from bs4 import BeautifulSoup

from scraper.utils.logger import get_scraper_logger

logger = get_scraper_logger("SEOChecker")

@dataclass
class SEOAuditResult:
    business_name: str
    website_url: Optional[str] = None
    title_tag: Optional[str] = None
    title_length: Optional[int] = None
    title_optimized: bool = False
    meta_description: Optional[str] = None
    meta_description_length: Optional[int] = None
    meta_description_optimized: bool = False
    h1_count: int = 0
    h2_count: int = 0
    headings_structure: List[Dict[str, str]] = None
    images_count: int = 0
    images_missing_alt: int = 0
    open_graph_tags: Dict[str, str] = None
    has_viewport_tag: bool = False
    has_robots_txt: bool = False
    has_sitemap: bool = False
    load_time_ms: Optional[int] = None
    error_message: Optional[str] = None

    def __post_init__(self):
        if self.headings_structure is None:
            self.headings_structure = []
        if self.open_graph_tags is None:
            self.open_graph_tags = {}

class SEOChecker:
    """
    Performs advanced static SEO audits on target websites using requests and BeautifulSoup.
    """
    def __init__(self, timeout: int = 12):
        self.timeout = timeout
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5"
        }

    def _clean_url(self, url: str) -> str:
        """Helper to format and clean the website URL."""
        url = url.strip()
        if not url.startswith(('http://', 'https://')):
            url = "http://" + url
        return url

    def audit(self, business_name: str, raw_url: str) -> SEOAuditResult:
        """
        Runs the full SEO audit suite on a business's homepage.
        """
        if not raw_url:
            return SEOAuditResult(business_name=business_name, error_message="Empty URL provided.")

        url = self._clean_url(raw_url)
        parsed_url = urlparse(url)
        base_domain = f"{parsed_url.scheme}://{parsed_url.netloc}"

        result = SEOAuditResult(business_name=business_name, website_url=url)
        start_time = time.time()

        try:
            # 1. Page Retrieval & Latency Check
            logger.info(f"[{business_name}] Auditing SEO for {url}...")
            response = requests.get(url, headers=self.headers, timeout=self.timeout, verify=False)
            result.load_time_ms = int((time.time() - start_time) * 1000.0)

            if response.status_code != 200:
                result.error_message = f"HTTP error {response.status_code}"
                logger.warning(f"[{business_name}] SEO Audit HTTP failure {response.status_code} for {url}")
                return result

            soup = BeautifulSoup(response.content, "html.parser")

            # 2. Title Tag Analysis
            title_node = soup.find("title")
            if title_node and title_node.string:
                title_text = title_node.string.strip()
                result.title_tag = title_text
                result.title_length = len(title_text)
                # Optimal title tag length is between 10 and 60 characters
                if 10 <= len(title_text) <= 60:
                    result.title_optimized = True
            
            # 3. Meta Description Analysis
            meta_desc = soup.find("meta", attrs={"name": "description"})
            if meta_desc and meta_desc.get("content"):
                desc_text = meta_desc.get("content").strip()
                result.meta_description = desc_text
                result.meta_description_length = len(desc_text)
                # Optimal meta description length is between 50 and 160 characters
                if 50 <= len(desc_text) <= 160:
                    result.meta_description_optimized = True

            # 4. Heading Tag Structure
            headings = soup.find_all(["h1", "h2", "h3"])
            h_struct = []
            for h in headings:
                tag = h.name.lower()
                text = h.get_text().strip()
                if not text:
                    continue
                if tag == "h1":
                    result.h1_count += 1
                elif tag == "h2":
                    result.h2_count += 1
                h_struct.append({"tag": tag, "text": text[:100]})
            result.headings_structure = h_struct[:20]  # Cap structure logging

            # 5. Image Alt attributes
            images = soup.find_all("img")
            result.images_count = len(images)
            for img in images:
                if not img.get("alt") or not img.get("alt").strip():
                    result.images_missing_alt += 1

            # 6. Open Graph Tags
            og_tags = {}
            for og_meta in soup.find_all("meta", property=True):
                prop = og_meta.get("property")
                if prop and prop.startswith("og:"):
                    og_tags[prop] = og_meta.get("content", "")
            result.open_graph_tags = og_tags

            # 7. Viewport Check
            viewport = soup.find("meta", attrs={"name": "viewport"})
            if viewport:
                result.has_viewport_tag = True

            # 8. robots.txt check
            robots_url = f"{base_domain}/robots.txt"
            try:
                robots_res = requests.get(robots_url, headers=self.headers, timeout=5, verify=False)
                if robots_res.status_code == 200:
                    result.has_robots_txt = True
                    # Simple sitemap check inside robots.txt
                    if "sitemap" in robots_res.text.lower():
                        result.has_sitemap = True
            except Exception:
                pass

            # 9. Direct Sitemap fallback check if sitemap wasn't flagged in robots.txt
            if not result.has_sitemap:
                sitemap_url = f"{base_domain}/sitemap.xml"
                try:
                    sitemap_res = requests.get(sitemap_url, headers=self.headers, timeout=5, verify=False)
                    if sitemap_res.status_code == 200:
                        result.has_sitemap = True
                except Exception:
                    pass

            logger.info(f"[{business_name}] SEO Audit complete. Title: {result.title_tag[:30] if result.title_tag else 'None'} | missing alts: {result.images_missing_alt}/{result.images_count}")

        except Exception as e:
            result.error_message = str(e)
            logger.error(f"[{business_name}] SEO Audit failed: {e}")

        return result

if __name__ == "__main__":
    import json
    checker = SEOChecker()
    res = checker.audit("Google", "https://www.google.com")
    print(json.dumps(asdict(res), indent=2))
