"""
tech_stack_detector.py
----------------------
Responsibility:
    Detect the technology stack of a business website — CMS, frontend framework,
    analytics tools, payment integrations, and chat widgets.

Detection method:
    Fingerprint-based passive detection from HTTP response headers and HTML source.
    Does NOT require executing JavaScript (avoids Playwright dependency here).

Why this matters for the platform:
    A business running on Wix or an outdated WordPress theme is a stronger
    web-development lead than one on a custom React app. Tech stack detection
    dramatically improves outreach relevance.

Output contract:
    Returns TechStackResult — JSON/PostgreSQL compatible.

TODO:
    - Load fingerprint signatures from a YAML/JSON config file for easy updates
    - Detect from HTTP response headers: X-Powered-By, Server, Set-Cookie
    - Detect from HTML meta generators: <meta name="generator" content="WordPress 6.4">
    - Detect from script src patterns: /wp-content/, gtag.js, hotjar.io, etc.
    - Add confidence scores per detected technology
    - Integrate with scoring_engine to penalize outdated CMS versions
"""

import logging
from dataclasses import dataclass, asdict, field
from typing import Optional, List, Dict, Any

import requests
from bs4 import BeautifulSoup

from scraper.utils.logger import get_scraper_logger

logger = get_scraper_logger("TechStackDetector")


# ---------------------------------------------------------
# Fingerprint Signatures
# ---------------------------------------------------------
# Each entry: pattern to search for → technology label
# Search targets: html_source, script_srcs, response_headers, meta_generator

TECH_SIGNATURES: Dict[str, List[Dict[str, str]]] = {
    "cms": [
        {"pattern": "/wp-content/",       "name": "WordPress",  "target": "html_source"},
        {"pattern": "shopify",             "name": "Shopify",    "target": "html_source"},
        {"pattern": "wix.com",             "name": "Wix",        "target": "html_source"},
        {"pattern": "squarespace.com",     "name": "Squarespace","target": "html_source"},
        {"pattern": "webflow.io",          "name": "Webflow",    "target": "html_source"},
        # TODO: Add Joomla, Drupal, Magento, custom patterns
    ],
    "frontend": [
        {"pattern": "react",               "name": "React",      "target": "html_source"},
        {"pattern": "vue",                 "name": "Vue",        "target": "html_source"},
        {"pattern": "angular",             "name": "Angular",    "target": "html_source"},
        {"pattern": "next",                "name": "Next.js",    "target": "html_source"},
        # TODO: Detect from __next_data__, ng-version, __vue__ etc.
    ],
    "analytics": [
        {"pattern": "gtag.js",             "name": "Google Analytics", "target": "html_source"},
        {"pattern": "hotjar",              "name": "Hotjar",     "target": "html_source"},
        {"pattern": "fbq(",                "name": "Meta Pixel", "target": "html_source"},
        {"pattern": "clarity.ms",          "name": "MS Clarity", "target": "html_source"},
        # TODO: Detect GA4 vs UA, Mixpanel, Segment, Amplitude
    ],
    "payment": [
        {"pattern": "razorpay",            "name": "Razorpay",   "target": "html_source"},
        {"pattern": "stripe.com",          "name": "Stripe",     "target": "html_source"},
        {"pattern": "paypal",              "name": "PayPal",     "target": "html_source"},
        {"pattern": "paytm",               "name": "Paytm",      "target": "html_source"},
        # TODO: Detect PayU, CCAvenue, Cashfree (India-specific)
    ],
    "chat": [
        {"pattern": "tawk.to",             "name": "Tawk.to",    "target": "html_source"},
        {"pattern": "intercom",            "name": "Intercom",   "target": "html_source"},
        {"pattern": "crisp.chat",          "name": "Crisp",      "target": "html_source"},
        # TODO: Detect Freshchat, Zendesk Chat
    ],
}


# ---------------------------------------------------------
# Output Data Structure
# ---------------------------------------------------------
@dataclass
class TechStackResult:
    """
    Detected technology stack of a business website.
    Designed for a future `tech_stack` table in PostgreSQL.
    """
    business_name: str
    website_url: Optional[str]
    cms: Optional[str] = None
    frontend_framework: Optional[str] = None
    analytics_tools: List[str] = field(default_factory=list)
    payment_tools: List[str] = field(default_factory=list)
    chat_tools: List[str] = field(default_factory=list)
    raw_server_header: Optional[str] = None
    error: Optional[str] = None


# ---------------------------------------------------------
# Tech Stack Detector
# ---------------------------------------------------------
class TechStackDetector:
    """
    Passive fingerprint-based technology detector.
    Operates only on the static HTML source — no JS execution required.

    Usage:
        detector = TechStackDetector()
        result = detector.detect("Acme Corp", "https://acmecorp.com")
    """

    def __init__(self, timeout: int = 10):
        self.timeout = timeout
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
            )
        }

    def _fetch(self, url: str):
        """Fetch homepage and return (html_text, response_headers)."""
        try:
            r = requests.get(url, headers=self.headers, timeout=self.timeout)
            r.raise_for_status()
            return r.text, dict(r.headers)
        except Exception as e:
            logger.warning(f"Failed to fetch {url}: {e}")
            return None, {}

    def _scan_signatures(
        self,
        category: str,
        html: str,
        headers: Dict[str, str]
    ) -> List[str]:
        """
        Scan HTML source for fingerprint patterns in the given category.
        Also scan response headers (Server, X-Powered-By, Set-Cookie)
        and parse <meta name="generator"> tag for CMS version info.
        """
        detected = []
        html_lower = html.lower()

        # 1. Scan signatures in the specific category
        for sig in TECH_SIGNATURES.get(category, []):
            pattern = sig["pattern"].lower()
            target = sig.get("target", "html_source")

            if target == "html_source":
                if pattern in html_lower:
                    if sig["name"] not in detected:
                        detected.append(sig["name"])
            elif target == "headers":
                # Check header keys and values
                found = False
                for h_key, h_val in headers.items():
                    if pattern in h_key.lower() or pattern in str(h_val).lower():
                        found = True
                        break
                if found and sig["name"] not in detected:
                    detected.append(sig["name"])

        # 2. Category-specific heuristic parsing
        if category == "cms":
            # Check X-Powered-By header
            x_powered = headers.get("x-powered-by", headers.get("X-Powered-By", "")).lower()
            if "wordpress" in x_powered or "wp" in x_powered:
                if "WordPress" not in detected:
                    detected.append("WordPress")

            # Check Set-Cookie headers for WordPress/Shopify
            set_cookie = headers.get("set-cookie", headers.get("Set-Cookie", "")).lower()
            if "wp-" in set_cookie or "wordpress_" in set_cookie:
                if "WordPress" not in detected:
                    detected.append("WordPress")
            elif "shopify" in set_cookie:
                if "Shopify" not in detected:
                    detected.append("Shopify")

            # Parse <meta name="generator">
            try:
                soup = BeautifulSoup(html, "html.parser")
                generator_meta = soup.find("meta", attrs={"name": "generator"})
                if generator_meta and generator_meta.get("content"):
                    content = generator_meta.get("content").lower()
                    if "wordpress" in content:
                        if "WordPress" not in detected:
                            detected.append("WordPress")
                    elif "shopify" in content:
                        if "Shopify" not in detected:
                            detected.append("Shopify")
                    elif "wix" in content:
                        if "Wix" not in detected:
                            detected.append("Wix")
                    elif "squarespace" in content:
                        if "Squarespace" not in detected:
                            detected.append("Squarespace")
                    elif "webflow" in content:
                        if "Webflow" not in detected:
                            detected.append("Webflow")
            except Exception as e:
                logger.debug(f"Error parsing meta generator tag: {e}")

        return detected

    def detect(self, business_name: str, website_url: Optional[str]) -> TechStackResult:
        """
        Detect tech stack for a given business website.

        Args:
            business_name: Display name for logging.
            website_url:   Full URL to analyze.

        Returns:
            TechStackResult with all detected technologies.
        """
        result = TechStackResult(
            business_name=business_name,
            website_url=website_url
        )

        if not website_url:
            result.error = "No website URL provided"
            return result

        html, headers = self._fetch(website_url)
        if not html:
            result.error = "Failed to fetch website"
            return result

        result.raw_server_header = headers.get("Server")

        cms_hits = self._scan_signatures("cms", html, headers)
        if cms_hits:
            result.cms = cms_hits[0]  # Take the first (most likely) match

        frontend_hits = self._scan_signatures("frontend", html, headers)
        if frontend_hits:
            result.frontend_framework = frontend_hits[0]

        result.analytics_tools = self._scan_signatures("analytics", html, headers)
        result.payment_tools = self._scan_signatures("payment", html, headers)
        result.chat_tools = self._scan_signatures("chat", html, headers)

        logger.info(
            f"[{business_name}] Tech Stack — CMS: {result.cms}, "
            f"Analytics: {result.analytics_tools}, Payment: {result.payment_tools}"
        )
        return result


# ---------------------------------------------------------
# Self-Test
# ---------------------------------------------------------
if __name__ == "__main__":
    import json
    detector = TechStackDetector()
    test = detector.detect("Example Corp", "https://example.com")
    print(json.dumps(asdict(test), indent=2))
