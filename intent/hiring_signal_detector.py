"""
hiring_signal_detector.py
--------------------------
Responsibility:
    Detect whether a business is actively hiring technical roles, which is a
    strong signal that they have growth momentum or technical pain points.

Why this matters:
    A business hiring for "Social Media Manager", "Website Developer", or
    "IT Support" is explicitly communicating an unmet technical need.
    This is a high-confidence buying signal for our services.

Sources to check (in priority order):
    1. Business website /careers or /jobs page
    2. LinkedIn Jobs (requires separate connector — future)
    3. Naukri.com / Indeed India listings (future)

Architecture decision:
    Returns a HiringSignalResult that the intent_engine consumes.
    The module does NOT perform any scoring — it only surfaces signals.

TODO:
    - Implement /careers and /jobs page crawler
    - Parse job listing titles and classify by technical relevance
    - Add Naukri/Indeed API or scraper connector
    - Define TECHNICAL_ROLES list from domain-specific hiring vocabulary
    - Return hiring_signal_score (0-100) based on number and recency of listings
"""

import logging
import re
from dataclasses import dataclass, asdict, field
from typing import Optional, List

import requests
from bs4 import BeautifulSoup

from scraper.utils.logger import get_scraper_logger

logger = get_scraper_logger("HiringSignalDetector")


# Roles that indicate unmet technical needs — highest outreach relevance
TECHNICAL_ROLES = [
    "web developer", "website developer", "ui developer", "frontend developer",
    "social media manager", "digital marketing", "seo specialist",
    "graphic designer", "content writer", "it support", "software developer",
    "app developer", "e-commerce manager", "data analyst",
    # TODO: Expand this list based on observed job titles in target markets
]

# Pages to check for job listings
CAREER_PATHS = ["/careers", "/jobs", "/join-us", "/work-with-us", "/vacancies"]


# ---------------------------------------------------------
# Output Data Structure
# ---------------------------------------------------------
@dataclass
class JobListing:
    """A single detected job listing."""
    title: str
    is_technical: bool = False
    source_url: Optional[str] = None


@dataclass
class HiringSignalResult:
    """
    Hiring intelligence for a business.
    Designed for use by intent_engine.py.
    """
    business_name: str
    website_url: Optional[str]
    is_actively_hiring: bool = False
    technical_roles_found: List[JobListing] = field(default_factory=list)
    all_roles_found: List[JobListing] = field(default_factory=list)
    pages_checked: List[str] = field(default_factory=list)
    hiring_signal_score: float = 0.0    # 0-100
    error: Optional[str] = None


# ---------------------------------------------------------
# Hiring Signal Detector
# ---------------------------------------------------------
class HiringSignalDetector:
    """
    Crawls business websites for active job listings as buying intent signals.

    Usage:
        detector = HiringSignalDetector()
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

    def _fetch(self, url: str) -> Optional[BeautifulSoup]:
        """Fetch a page and return BeautifulSoup soup or None on failure."""
        try:
            r = requests.get(url, headers=self.headers, timeout=self.timeout)
            r.raise_for_status()
            return BeautifulSoup(r.text, "html.parser")
        except Exception as e:
            logger.warning(f"Could not fetch {url}: {e}")
            return None

    def _parse_job_listings(self, soup: BeautifulSoup, source_url: str) -> List[JobListing]:
        """
        Extract job listing titles from a careers/jobs page.
        """
        listings = []
        seen_titles = set()
        candidates = []
        
        # 1. Collect potential elements containing job titles
        for h in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"]):
            candidates.append(h)
            
        for li in soup.find_all("li"):
            candidates.append(li)
            
        job_classes = re.compile(r"job|career|position|vacancy|listing|role|title", re.I)
        for el in soup.find_all(["div", "span", "p", "a"], class_=job_classes):
            candidates.append(el)

        for a in soup.find_all("a", href=re.compile(r"job|career|vacancy|position", re.I)):
            candidates.append(a)

        # 2. Filter and classify candidate text
        for el in candidates:
            title_text = el.get_text(strip=True)
            title_text = re.sub(r"\s+", " ", title_text)
            
            if not title_text or len(title_text) < 4 or len(title_text) > 80:
                continue
                
            title_lower = title_text.lower()
            generic_phrases = [
                "apply now", "view job", "read more", "search", "careers", "jobs", 
                "join our team", "join us", "work with us", "contact us", "about us", 
                "all rights reserved", "copyright", "send resume", "submit", "apply today",
                "current openings", "open positions", "departments", "find a job"
            ]
            if any(p in title_lower for p in generic_phrases):
                continue
                
            if title_text in seen_titles:
                continue
                
            # Classify using a broad range of role keywords to catch non-technical roles
            role_indicators = TECHNICAL_ROLES + [
                "sales", "manager", "accountant", "receptionist", "representative", "hr",
                "operations", "admin", "clerk", "associate", "consultant", "officer",
                "executive", "support", "lead", "specialist", "engineer", "designer",
                "developer", "writer", "marketing", "analyst", "assistant", "director",
                "supervisor", "coordinator", "intern", "trainer"
            ]
            
            is_job = any(role in title_lower for role in role_indicators)
            if not is_job:
                continue
                
            seen_titles.add(title_text)
            is_tech = any(role in title_lower for role in TECHNICAL_ROLES)
            
            listings.append(JobListing(
                title=title_text,
                is_technical=is_tech,
                source_url=source_url
            ))
            
        return listings

    def _calculate_score(self, result: HiringSignalResult) -> float:
        """
        Score hiring intent from 0 to 100.
        Logic:
            - Each technical role adds 25 points (max 100)
            - Non-technical roles add 5 points (max 15)
        """
        tech_score = len(result.technical_roles_found) * 25.0
        non_tech_roles = [r for r in result.all_roles_found if not r.is_technical]
        non_tech_score = min(15.0, len(non_tech_roles) * 5.0)
        
        score = min(100.0, tech_score + non_tech_score)
        return round(score, 1)

    def detect(self, business_name: str, website_url: Optional[str]) -> HiringSignalResult:
        """
        Check website for active job listings and classify their technical relevance.

        Args:
            business_name: Display name for logging.
            website_url:   Business homepage URL.

        Returns:
            HiringSignalResult with found listings and hiring_signal_score.
        """
        result = HiringSignalResult(
            business_name=business_name,
            website_url=website_url
        )

        if not website_url:
            result.error = "No website URL provided"
            return result

        base = website_url.rstrip("/")

        for path in CAREER_PATHS:
            url = base + path
            soup = self._fetch(url)
            if soup:
                result.pages_checked.append(url)
                listings = self._parse_job_listings(soup, url)
                result.all_roles_found.extend(listings)
                result.technical_roles_found.extend(
                    [j for j in listings if j.is_technical]
                )
                logger.info(
                    f"[{business_name}] {path}: found {len(listings)} listing(s)"
                )

        result.is_actively_hiring = len(result.all_roles_found) > 0
        result.hiring_signal_score = self._calculate_score(result)

        logger.info(
            f"[{business_name}] Hiring score: {result.hiring_signal_score}, "
            f"technical roles: {len(result.technical_roles_found)}"
        )
        return result


# ---------------------------------------------------------
# Self-Test
# ---------------------------------------------------------
if __name__ == "__main__":
    import json
    detector = HiringSignalDetector()
    test = detector.detect("Example Corp", "https://example.com")
    print(json.dumps(asdict(test), indent=2))
