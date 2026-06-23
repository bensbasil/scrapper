import logging
import requests
from bs4 import BeautifulSoup
from dataclasses import dataclass, asdict
from typing import Dict, Any, List, Optional

logger = logging.getLogger("TrustSignalDetector")
logger.setLevel(logging.INFO)

@dataclass
class TrustSignalResult:
    business_name: str
    trust_signals: List[str]
    trust_health_score: float

class TrustSignalDetector:
    def __init__(self, timeout: int = 10):
        self.timeout = timeout
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

    def detect(self, business_name: str, url: Optional[str]) -> TrustSignalResult:
        logger.info(f"[{business_name}] Detecting credibility and trust signals on website...")
        
        detected_signals = []
        
        if not url or str(url).strip() == "" or str(url).lower() == "none":
            return TrustSignalResult(
                business_name=business_name,
                trust_signals=["No website exists to display trust signals"],
                trust_health_score=0.0
            )

        # Clean redirect wrappers if present
        if url and ("url?q=" in url or "/url?q=" in url):
            try:
                from urllib.parse import urlparse, parse_qs
                parsed = urlparse(url)
                params = parse_qs(parsed.query)
                if "q" in params and params["q"]:
                    url = params["q"][0]
            except Exception as e:
                logger.debug(f"Failed to parse redirect wrapper URL {url}: {e}")

        try:
            response = requests.get(url, headers=self.headers, timeout=self.timeout, verify=False)
            response.raise_for_status()
            html = response.text.lower()
            soup = BeautifulSoup(html, "html.parser")
        except Exception as e:
            logger.warning(f"[{business_name}] Connection failed for trust analysis: {e}")
            return TrustSignalResult(
                business_name=business_name,
                trust_signals=[f"Access failed: {str(e)}"],
                trust_health_score=0.0
            )

        # 1. Testimonials
        testimonial_kws = ["testimonial", "what they say", "what our customer", "reviews", "hear from", "client feedback"]
        has_testimonials = any(kw in html for kw in testimonial_kws)
        if has_testimonials:
            detected_signals.append("Customer Testimonials / Reviews Section")

        # 2. Certifications & Licensing
        cert_kws = ["certified", "accredited", "license", "licence", "iso certified", "affiliated", "registered"]
        has_certs = any(kw in html for kw in cert_kws)
        if has_certs:
            detected_signals.append("Professional Certifications / Licenses")

        # 3. Trust Widgets
        widget_kws = ["trustpilot", "elfsight", "reviews.io", "google review widget", "tagembed", "sociablekit"]
        has_widgets = any(kw in html for kw in widget_kws)
        if has_widgets:
            detected_signals.append("Live Third-Party Review Widget Embeds")

        # 4. Awards & Accolades
        award_kws = ["award", "winner", "best of", "excellence award", "recognized", "honored"]
        has_awards = any(kw in html for kw in award_kws)
        if has_awards:
            detected_signals.append("Business Awards / Local Accolades")

        # 5. Trust Badges & Safety Polices
        badge_kws = ["satisfaction guarantee", "secure checkout", "privacy policy", "terms of service", "refund policy"]
        has_badges = any(kw in html for kw in badge_kws)
        if has_badges:
            detected_signals.append("Trust Badges / Legal Policies")

        # Calculate score (out of 100)
        score = 0.0
        if has_testimonials: score += 30.0
        if has_certs: score += 25.0
        if has_widgets: score += 20.0
        if has_awards: score += 15.0
        if has_badges: score += 10.0
        
        score = min(100.0, score)

        return TrustSignalResult(
            business_name=business_name,
            trust_signals=detected_signals,
            trust_health_score=score
        )
