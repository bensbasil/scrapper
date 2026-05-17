import csv
import json
import logging
import time
from pathlib import Path
from urllib.parse import urlparse
from dataclasses import dataclass, asdict
from typing import List, Dict, Any, Optional

import requests
from bs4 import BeautifulSoup

# ---------------------------------------------------------
# 1. Structured Logging
# ---------------------------------------------------------
class StructuredLogger:
    @staticmethod
    def get_logger(name: str):
        logger = logging.getLogger(name)
        if not logger.handlers:
            logger.setLevel(logging.INFO)
            formatter = logging.Formatter('%(asctime)s - %(levelname)s - [%(name)s] - %(message)s')
            
            # Console handler
            ch = logging.StreamHandler()
            ch.setFormatter(formatter)
            logger.addHandler(ch)
            
            # File handler
            log_dir = Path("logs")
            log_dir.mkdir(exist_ok=True)
            fh = logging.FileHandler(log_dir / "website_analyzer.log")
            fh.setFormatter(formatter)
            logger.addHandler(fh)
        return logger

logger = StructuredLogger.get_logger(__name__)

# ---------------------------------------------------------
# 2. Data Structure (Prepares for Scoring/PostgreSQL)
# ---------------------------------------------------------
@dataclass
class WebsiteAnalysisResult:
    """Matches DATA_DICTIONARY.md for Website Analysis."""
    business_name: str
    website_url: Optional[str] = None
    website_exists: bool = False
    ssl_enabled: bool = False
    mobile_friendly: bool = False
    meta_title_exists: bool = False
    meta_title: Optional[str] = None
    meta_description_exists: bool = False
    contact_form_exists: bool = False
    whatsapp_integration: bool = False
    social_links_found: List[str] = None
    h1_exists: bool = False
    error: Optional[str] = None

    def __post_init__(self):
        if self.social_links_found is None:
            self.social_links_found = []

# ---------------------------------------------------------
# 3. Main Analyzer Class
# ---------------------------------------------------------
class WebsiteAnalyzer:
    """
    Analyzes websites using requests/BeautifulSoup.
    Keeps MVP simplicity: avoids full headless browsers here for speed,
    as static analysis is sufficient for heuristic weakness detection.
    """
    def __init__(self, output_dir: str = "data/processed", timeout: int = 15):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.timeout = timeout
        # Headers to prevent basic bot blocking
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5"
        }

    def _normalize_url(self, url: str) -> str:
        """Ensure URL has a scheme."""
        url = url.strip()
        if not url.startswith(('http://', 'https://')):
            return f"https://{url}"
        return url

    def analyze_url(self, business_name: str, url: Optional[str]) -> WebsiteAnalysisResult:
        """
        Analyzes a single website URL and extracts digital weaknesses.
        Returns a structured WebsiteAnalysisResult.
        """
        result = WebsiteAnalysisResult(business_name=business_name, website_url=url)
        
        if not url or str(url).strip() == "" or str(url).lower() == "none":
            result.error = "No website provided"
            return result
            
        result.website_exists = True
        url = self._normalize_url(url)
        result.website_url = url
        
        try:
            # 1. Fetch & SSL Check
            # TODO: If HTTPS fails, implement fallback to HTTP to check if site exists without SSL.
            response = requests.get(url, headers=self.headers, timeout=self.timeout, verify=True)
            response.raise_for_status()
            
            # If we requested HTTPS and didn't get downgraded, SSL is active.
            result.ssl_enabled = response.url.startswith("https://")
            
            # 2. Parse HTML
            soup = BeautifulSoup(response.text, 'html.parser')
            html_text = response.text.lower()
            
            # 3. Basic SEO & Meta
            title_tag = soup.find('title')
            if title_tag and title_tag.text:
                result.meta_title_exists = True
                result.meta_title = title_tag.text.strip()
                
            meta_desc = soup.find('meta', attrs={'name': 'description'})
            if meta_desc and meta_desc.get('content'):
                result.meta_description_exists = True
                
            result.h1_exists = soup.find('h1') is not None
            
            # 4. Mobile Friendliness Heuristic
            viewport = soup.find('meta', attrs={'name': 'viewport'})
            if viewport and 'width=device-width' in viewport.get('content', '').lower():
                result.mobile_friendly = True
                
            # 5. Integrations & Forms Heuristics
            # We look for form tags, or 'contact' text as a broad fallback heuristic
            if soup.find('form') or 'contact' in html_text or 'get in touch' in html_text:
                result.contact_form_exists = True
                
            # Check WhatsApp
            if 'wa.me/' in html_text or 'api.whatsapp.com' in html_text or 'whatsapp' in html_text:
                result.whatsapp_integration = True
                
            # Check Socials
            social_domains = ['facebook.com', 'instagram.com', 'twitter.com', 'linkedin.com', 'tiktok.com']
            for link in soup.find_all('a', href=True):
                href = link['href'].lower()
                for domain in social_domains:
                    if domain in href and domain not in result.social_links_found:
                        result.social_links_found.append(domain)

        except requests.exceptions.SSLError:
            logger.warning(f"SSL Error for {url}. Site likely lacks valid HTTPS.")
            result.error = "SSL Certificate Invalid"
            result.ssl_enabled = False
        except requests.RequestException as e:
            logger.warning(f"Failed to access {url}: {e}")
            result.error = f"Connection failed: {str(e)}"
        except Exception as e:
            logger.error(f"Error parsing {url}: {e}")
            result.error = f"Parsing error: {str(e)}"
            
        return result

    def process_csv(self, input_csv_path: str) -> List[WebsiteAnalysisResult]:
        """
        Reads scraper CSV output and processes all websites.
        Saves output to a structured JSON file in data/processed/.
        """
        logger.info(f"Starting analysis from CSV: {input_csv_path}")
        results = []
        
        try:
            with open(input_csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    b_name = row.get('business_name', 'Unknown')
                    url = row.get('website')
                    
                    logger.info(f"Analyzing: {b_name} ({url})")
                    analysis = self.analyze_url(b_name, url)
                    results.append(analysis)
                    
                    # Be nice to servers - avoid rapid-fire requests
                    time.sleep(1)
                    
        except FileNotFoundError:
            logger.error(f"CSV file not found: {input_csv_path}")
            return results
        except Exception as e:
            logger.error(f"Failed to read CSV {input_csv_path}: {e}")
            return results
            
        # Export processed data
        output_file = self.output_dir / f"analysis_{int(time.time())}.json"
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump([asdict(r) for r in results], f, indent=4, ensure_ascii=False)
            logger.info(f"Saved {len(results)} analysis records to {output_file}")
        except Exception as e:
            logger.error(f"Failed to save JSON output: {e}")
            
        return results

if __name__ == "__main__":
    analyzer = WebsiteAnalyzer()
    
    # Simple self-test
    logger.info("Running analyzer self-test on example.com...")
    test_result = analyzer.analyze_url("Test Business", "https://example.com")
    print(json.dumps(asdict(test_result), indent=2))
