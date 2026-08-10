"""
social_analyzer.py
------------------
Responsibility:
    Audit a business's social media presence — validating that detected
    social links are active, checking account health, and estimating
    post recency / activity level.

Architecture decision:
    This module operates as a post-enrichment step AFTER company_website.py
    has already identified which social links exist. It takes those URLs as
    input rather than re-crawling the business website.

    Lives in `enrichment/` rather than `analyzer/` because its primary purpose
    is data collection (enriching raw social signals), not scoring.

Sources supported (Phase 1):
    - Facebook public page (HTTP HEAD check for existence)
    - Instagram basic presence check

TODO:
    - Implement HTTP reachability check for each social URL
    - Detect broken/deactivated accounts (301 redirects to login pages)
    - Estimate post recency from open-graph metadata where available
    - Add LinkedIn public page validation
    - Compute a social_activity_score (0-100) for the scoring_engine
    - Consider using a separate scraper (Playwright) for deeper Instagram checks
"""

import logging
from dataclasses import dataclass, asdict, field
from typing import Optional, List, Dict, Any

import requests

from scraper.utils.logger import get_scraper_logger

logger = get_scraper_logger("SocialAnalyzer")


# ---------------------------------------------------------
# Output Data Structure
# ---------------------------------------------------------
@dataclass
class SocialProfile:
    """Represents one social media profile's audit result."""
    platform: str                       # e.g. "facebook", "instagram"
    url: str
    is_reachable: bool = False
    is_active: Optional[bool] = None    # None = unable to determine
    last_post_estimate: Optional[str] = None  # e.g. "< 30 days", "> 6 months"
    follower_estimate: Optional[str] = None   # Rough range when detectable
    error: Optional[str] = None


@dataclass
class SocialAnalysisResult:
    """
    Full social presence audit for a business.
    Designed for a future `social_analysis` table in PostgreSQL.
    """
    business_name: str
    profiles: List[SocialProfile] = field(default_factory=list)
    social_activity_score: float = 0.0   # 0-100, higher = more active
    total_platforms_found: int = 0
    total_platforms_active: int = 0
    error: Optional[str] = None


# ---------------------------------------------------------
# Social Analyzer
# ---------------------------------------------------------
class SocialAnalyzer:
    """
    Audits social media links discovered on a business website.

    Usage:
        analyzer = SocialAnalyzer()
        social_urls = ["https://facebook.com/acmecorp", "https://instagram.com/acmecorp"]
        result = analyzer.analyze("Acme Corp", social_urls)
    """

    PLATFORM_PATTERNS = {
        "facebook": ["facebook.com", "fb.com"],
        "instagram": ["instagram.com"],
        "twitter": ["twitter.com", "x.com"],
        "linkedin": ["linkedin.com"],
        "youtube": ["youtube.com"],
        "tiktok": ["tiktok.com"],
    }

    def __init__(self, timeout: int = 8):
        self.timeout = timeout
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
            )
        }

    def _identify_platform(self, url: str) -> str:
        """Determine which platform a social URL belongs to."""
        url_lower = url.lower()
        for platform, patterns in self.PLATFORM_PATTERNS.items():
            if any(p in url_lower for p in patterns):
                return platform
        return "unknown"

    def _check_reachability(self, url: str) -> tuple[bool, Optional[str]]:
        """
        Make an HTTP GET request to check if the social URL is reachable and active.
        Detects soft-404 redirects to login/auth pages.
        """
        try:
            # Using GET for better support across modern platforms that block HEAD requests
            r = requests.get(url, headers=self.headers, timeout=self.timeout, allow_redirects=True)
            if r.status_code >= 400:
                return False, f"HTTP {r.status_code}"
            
            # Detect login redirects (soft-404 / inactive profiles)
            final_url = r.url.lower()
            login_indicators = [
                "/login", "/signup", "login.php", "accounts/login", "auth", 
                "signin", "checkpoint/block"
            ]
            if any(ind in final_url for ind in login_indicators) and not any(ind in url.lower() for ind in login_indicators):
                return False, "Redirected to auth/login (account may be private, invalid, or deleted)"
                
            return True, None
        except Exception as e:
            return False, str(e)

    def _estimate_activity(self, url: str, platform: str) -> Optional[bool]:
        """
        Heuristic check for whether a social account appears active.
        """
        # Default to True for reachable accounts since deep Playwright scanning is a future phase.
        return True

    def _calculate_activity_score(self, profiles: List[SocialProfile]) -> float:
        """
        Score from 0-100 based on number and activity of social profiles.
        Scoring logic:
            +20 per reachable platform (max 100)
            -10 per platform that is unreachable
        """
        if not profiles:
            return 0.0
            
        score = 0.0
        for p in profiles:
            if p.is_reachable:
                score += 20.0
            else:
                score -= 10.0
                
        score = max(0.0, min(100.0, score))
        return round(score, 1)

    def analyze(self, business_name: str, social_urls: List[str]) -> SocialAnalysisResult:
        """
        Audit a list of social URLs for a business.

        Args:
            business_name: Display name for logging.
            social_urls:   List of social media profile URLs.

        Returns:
            SocialAnalysisResult with per-platform audit outcomes.
        """
        result = SocialAnalysisResult(business_name=business_name)

        if not social_urls:
            result.error = "No social URLs provided"
            return result

        from scraper.connectors.social.social_scraper import SocialScraper
        scraper = SocialScraper()

        for url in social_urls:
            platform = self._identify_platform(url)
            profile = SocialProfile(platform=platform, url=url)

            try:
                scrap_res = scraper.scrape(url)
                profile.is_reachable = scrap_res.is_reachable
                profile.error = scrap_res.error_message
                profile.is_active = scrap_res.is_reachable
                profile.follower_estimate = scrap_res.follower_count
                if scrap_res.post_count:
                    profile.last_post_estimate = f"{scrap_res.post_count} posts"
                if scrap_res.bio:
                    profile.error = f"Bio: {scrap_res.bio[:60]}" if not profile.error else profile.error
            except Exception as se:
                logger.error(f"[{business_name}] Deep social scraper failed for {url}: {se}")
                # Fall back to simple reachability check
                is_reachable, err = self._check_reachability(url)
                profile.is_reachable = is_reachable
                profile.error = err
                profile.is_active = self._estimate_activity(url, platform) if is_reachable else False

            result.profiles.append(profile)
            logger.info(
                f"[{business_name}] {platform}: reachable={profile.is_reachable}, active={profile.is_active}, followers={profile.follower_estimate}"
            )

        result.total_platforms_found = len(result.profiles)
        result.total_platforms_active = sum(1 for p in result.profiles if p.is_active)
        result.social_activity_score = self._calculate_activity_score(result.profiles)

        return result


# ---------------------------------------------------------
# Self-Test
# ---------------------------------------------------------
if __name__ == "__main__":
    import json
    analyzer = SocialAnalyzer()
    test_urls = ["https://facebook.com/example", "https://instagram.com/example"]
    test = analyzer.analyze("Example Corp", test_urls)
    print(json.dumps(asdict(test), indent=2))
