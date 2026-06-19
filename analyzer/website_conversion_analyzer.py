from dataclasses import dataclass
from typing import Dict, Any, List, Optional
import logging
import re

logger = logging.getLogger("WebsiteConversionAnalyzer")

@dataclass
class ConversionMetrics:
    has_clear_cta: bool
    cta_visibility_score: float
    form_accessibility: float
    checkout_friction_score: float
    overall_conversion_score: float
    missing_elements: List[str]

class WebsiteConversionAnalyzer:
    """
    Analyzes website structure and copy to identify conversion bottlenecks.
    Helps flag sites that get traffic but fail to capture leads/sales.
    """
    def __init__(self):
        pass
        
    def analyze(self, html_content: str, website_url: str) -> ConversionMetrics:
        """
        Scan the website for common conversion optimization best practices.
        """
        logger.info(f"Analyzing conversion potential for {website_url}")
        
        has_cta = bool(re.search(r'(?i)(button|a)[^>]*>(sign up|get started|buy now|subscribe)', html_content))
        has_form = '<form' in html_content.lower()
        
        missing = []
        if not has_cta:
            missing.append("Primary CTA")
        if not has_form:
            missing.append("Lead Capture Form")
            
        score = 0.0
        if has_cta: score += 5.0
        if has_form: score += 5.0
        
        return ConversionMetrics(
            has_clear_cta=has_cta,
            cta_visibility_score=1.0 if has_cta else 0.0,
            form_accessibility=0.8 if has_form else 0.0,
            checkout_friction_score=0.2 if has_form else 1.0,
            overall_conversion_score=score,
            missing_elements=missing
        )
