"""
decision_maker_finder.py
------------------------
Responsibility:
    Identify potential decision-makers at a business (owners, founders,
    directors) from publicly accessible sources on the business website.

Sources checked (in order of reliability):
    1. /about or /team page — names with titles
    2. Schema.org Person markup — structured data on the page
    3. Footer copyright text — often contains owner name
    4. Google Maps "owner" response (future)

Architecture decision:
    Returns a list of candidates, not a single result, because a business
    may have multiple relevant contacts. Caller (pipeline_runner) decides
    which to store.

Output contract:
    Returns DecisionMakerResult — JSON/PostgreSQL compatible.

TODO:
    - Implement BeautifulSoup scrape of /about and /team pages
    - Parse schema.org Person JSON-LD blocks from <script> tags
    - Extract names + roles from footer text using simple NLP heuristics
    - Add LinkedIn profile URL discovery (future — requires separate connector)
    - Integrate with entity_resolver.py to deduplicate across sources
"""

import logging
from dataclasses import dataclass, asdict, field
from typing import Optional, List, Dict, Any

import requests
from bs4 import BeautifulSoup

from scraper.utils.logger import get_scraper_logger

logger = get_scraper_logger("DecisionMakerFinder")


# ---------------------------------------------------------
# Output Data Structures
# ---------------------------------------------------------
@dataclass
class ContactCandidate:
    """A single identified potential decision-maker."""
    name: Optional[str]
    role: Optional[str]                 # e.g. "Founder", "Owner", "Director"
    source: Optional[str]               # e.g. "about_page", "schema_org", "footer"
    confidence: float = 0.5             # 0.0 to 1.0


@dataclass
class DecisionMakerResult:
    """
    Full output for a business's decision-maker discovery.
    Designed for future INSERT into a `decision_makers` table.
    """
    business_name: str
    website_url: Optional[str]
    candidates: List[ContactCandidate] = field(default_factory=list)
    pages_checked: List[str] = field(default_factory=list)
    error: Optional[str] = None


# ---------------------------------------------------------
# Decision Maker Finder
# ---------------------------------------------------------
class DecisionMakerFinder:
    """
    Crawls business websites to surface likely decision-makers.

    Usage:
        finder = DecisionMakerFinder()
        result = finder.find("Acme Corp", "https://acmecorp.com")
    """

    ABOUT_PATHS = ["/about", "/about-us", "/team", "/our-team", "/management"]

    # Roles that indicate a decision-maker — case-insensitive substring match
    DECISION_ROLES = [
        "founder", "co-founder", "owner", "ceo", "director",
        "proprietor", "managing director", "md", "president", "head"
    ]

    def __init__(self, timeout: int = 10):
        self.timeout = timeout
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
            )
        }

    def _fetch(self, url: str) -> Optional[BeautifulSoup]:
        """Fetch a page and return a BeautifulSoup object."""
        try:
            r = requests.get(url, headers=self.headers, timeout=self.timeout)
            r.raise_for_status()
            return BeautifulSoup(r.text, "html.parser")
        except Exception as e:
            logger.warning(f"Could not fetch {url}: {e}")
            return None

    def _parse_about_page(self, soup: BeautifulSoup) -> List[ContactCandidate]:
        """
        Look for names and roles on /about or /team pages.
        """
        import re
        candidates = []
        # Find elements with class names commonly used for team profiles
        member_containers = soup.find_all(class_=re.compile(r"member|team|person|staff|card|profile|our-team", re.I))
        
        for container in member_containers:
            # Try to find header (name) and adjacent paragraph/span (role)
            name_el = container.find(["h1", "h2", "h3", "h4", "h5", "h6", "strong", "b"])
            role_el = container.find(["p", "span", "div", "small"], class_=re.compile(r"role|title|position|job", re.I))
            
            if not role_el:
                # Fallback: look for any paragraph or span containing a decision role
                for p in container.find_all(["p", "span", "div"]):
                    txt = p.get_text(strip=True).lower()
                    if any(role in txt for role in self.DECISION_ROLES):
                        role_el = p
                        break
                        
            if name_el and role_el:
                name = name_el.get_text(strip=True)
                role = role_el.get_text(strip=True)
                
                # Clean up text
                name = re.sub(r"\s+", " ", name).strip()
                role = re.sub(r"\s+", " ", role).strip()
                
                if name and role and len(name) < 50 and len(role) < 100:
                    role_lower = role.lower()
                    matched_role = None
                    for r in self.DECISION_ROLES:
                        if r in role_lower:
                            matched_role = r.title()
                            break
                    if matched_role:
                        candidates.append(ContactCandidate(
                            name=name,
                            role=role,
                            source="about_page",
                            confidence=0.8
                        ))
                        
        # Fallback text scan if no structured elements matched
        if not candidates:
            for p in soup.find_all(["p", "div", "h3", "h4"]):
                txt = p.get_text(strip=True)
                txt_lower = txt.lower()
                if any(role in txt_lower for role in self.DECISION_ROLES):
                    # Match pattern like "Name - Role" or "Role: Name" or "Name, Role"
                    match = re.search(r"^([^,:-]+)(?:,|-|:)\s*([a-zA-Z\s\-]+(?:founder|owner|ceo|director|proprietor|president|head)[a-zA-Z\s\-]*)$", txt, re.I)
                    if match:
                        name = match.group(1).strip()
                        role = match.group(2).strip()
                        if len(name) < 50 and len(role) < 100 and not any(w in name.lower() for w in ["we", "our", "about", "the"]):
                            candidates.append(ContactCandidate(
                                name=name,
                                role=role,
                                source="about_page_text",
                                confidence=0.6
                            ))
        return candidates

    def _parse_schema_org(self, soup: BeautifulSoup) -> List[ContactCandidate]:
        """
        Extract Person entities from schema.org JSON-LD <script> blocks.
        """
        import json
        candidates = []
        scripts = soup.find_all("script", type="application/ld+json")
        for script in scripts:
            try:
                if not script.string:
                    continue
                data = json.loads(script.string)
                
                entities = []
                if isinstance(data, list):
                    entities = data
                elif isinstance(data, dict):
                    if "@graph" in data:
                        entities = data["@graph"]
                    else:
                        entities = [data]
                        
                for entity in entities:
                    if entity.get("@type") == "Person":
                        name = entity.get("name")
                        job_title = entity.get("jobTitle")
                        if name and job_title:
                            role = str(job_title).strip()
                            role_lower = role.lower()
                            if any(r in role_lower for r in self.DECISION_ROLES):
                                candidates.append(ContactCandidate(
                                    name=str(name).strip(),
                                    role=role,
                                    source="schema_org",
                                    confidence=0.9
                                ))
            except Exception as e:
                logger.debug(f"Failed to parse schema.org script: {e}")
        return candidates

    def _parse_footer(self, soup: BeautifulSoup) -> List[ContactCandidate]:
        """
        Scan footer text for copyright lines that often include an owner name.
        """
        import re
        candidates = []
        footer = soup.find("footer")
        text = footer.get_text(strip=True) if footer else soup.get_text(strip=True)
        
        matches = re.finditer(r"(?:©|copyright|copr\.)\s*(?:\d{4}(?:\s*-\s*\d{4})?)?\s+([A-Z][a-zA-Z\s\.]+?)(?:\.|\s+all|\s+rights|\s*$)", text, re.I)
        for match in matches:
            name = match.group(1).strip()
            if name and len(name) < 40 and not any(w in name.lower() for w in ["all", "rights", "reserved", "inc", "ltd", "corp", "co", "theme", "website"]):
                candidates.append(ContactCandidate(
                    name=name,
                    role="Owner (from Copyright)",
                    source="footer",
                    confidence=0.7
                ))
        return candidates

    def find(self, business_name: str, website_url: Optional[str]) -> DecisionMakerResult:
        """
        Main entrypoint. Checks all sources and returns a ranked list of candidates.

        Args:
            business_name: Display name for logging.
            website_url:   Business homepage URL.

        Returns:
            DecisionMakerResult with candidates sorted by confidence.
        """
        result = DecisionMakerResult(
            business_name=business_name,
            website_url=website_url
        )

        if not website_url:
            result.error = "No website URL provided"
            return result

        base = website_url.rstrip("/")

        # Check about/team pages
        for path in self.ABOUT_PATHS:
            url = base + path
            soup = self._fetch(url)
            if soup:
                result.pages_checked.append(url)
                result.candidates.extend(self._parse_about_page(soup))
                result.candidates.extend(self._parse_schema_org(soup))
                result.candidates.extend(self._parse_footer(soup))
                logger.info(f"[{business_name}] Checked {path}")

        # Sort by confidence descending
        result.candidates.sort(key=lambda c: c.confidence, reverse=True)
        logger.info(
            f"[{business_name}] Found {len(result.candidates)} candidate(s)"
        )
        return result


# ---------------------------------------------------------
# Self-Test
# ---------------------------------------------------------
if __name__ == "__main__":
    import json
    finder = DecisionMakerFinder()
    test = finder.find("Example Corp", "https://example.com")
    print(json.dumps(asdict(test), indent=2))
