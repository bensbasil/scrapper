"""
entity_resolver.py
------------------
Responsibility:
    Resolve whether two records from different data sources (e.g., Google Maps
    and JustDial) refer to the same real-world business entity, and merge them
    into a single canonical record.

Why this is needed:
    As we add more connectors (JustDial, IndiaMart, OpenCorporates), we will
    encounter the same business scraped from multiple sources with slightly
    different names, addresses, or URLs. Without resolution, we'll have
    duplicate business records that inflate our lead counts and pollute outreach.

Resolution strategy:
    1. Exact match — same name + same address (current DB UNIQUE constraint)
    2. Fuzzy name match — Levenshtein distance below a threshold
    3. Phone number match — same phone = same business
    4. Website match — same normalized domain = same business

Architecture decision:
    This module is a pure utility — it takes two business dicts as input and
    returns a match confidence score. The pipeline_runner or a future merge
    job decides whether to trigger a merge based on the threshold.

Output contract:
    Returns EntityMatchResult — JSON/PostgreSQL compatible.

TODO:
    - Implement fuzzy name matching using `rapidfuzz` library
    - Implement phone normalization (strip country codes, spaces, dashes)
    - Implement domain normalization (strip www, http, trailing slash)
    - Build a batch resolver that scans the DB for probable duplicates
    - Add a merge() method that combines two business records into one canonical record
    - Store a `source_platform` list on merged records to track data lineage
"""

import logging
import re
from dataclasses import dataclass, asdict
from typing import Optional, Dict, Any

from scraper.utils.logger import get_scraper_logger

logger = get_scraper_logger("EntityResolver")


# ---------------------------------------------------------
# Output Data Structure
# ---------------------------------------------------------
@dataclass
class EntityMatchResult:
    """
    Result of comparing two business records for identity resolution.
    """
    business_a_name: str
    business_b_name: str
    is_match: bool
    confidence: float               # 0.0 to 1.0
    match_reasons: list             # Which signals triggered the match
    suggested_action: str           # "merge", "review", "ignore"


# ---------------------------------------------------------
# Entity Resolver
# ---------------------------------------------------------
class EntityResolver:
    """
    Determines if two business records are the same real-world entity.

    Usage:
        resolver = EntityResolver()
        result = resolver.compare(record_a, record_b)
    """

    MATCH_THRESHOLD = 0.75  # Confidence above this triggers a merge suggestion

    def _normalize_name(self, name: Optional[str]) -> str:
        """Lowercase, strip punctuation, trim whitespace."""
        if not name:
            return ""
        return re.sub(r"[^a-z0-9\s]", "", name.lower()).strip()

    def _normalize_phone(self, phone: Optional[str]) -> str:
        """Strip all non-digit characters and return last 10 digits for comparison."""
        if not phone:
            return ""
        digits = re.sub(r"\D", "", phone)
        if len(digits) > 10:
            return digits[-10:]
        return digits

    def _normalize_domain(self, url: Optional[str]) -> str:
        """Extract and normalize domain from a URL, handling Google redirects."""
        if not url:
            return ""
        url = url.strip()
        
        # Extract target q parameter if it is a Google redirect URL
        if "/url?q=" in url or "/url?url=" in url:
            match = re.search(r"[?&](?:q|url)=([^&]+)", url)
            if match:
                import urllib.parse
                url = urllib.parse.unquote(match.group(1))
                
        url = url.lower()
        url = re.sub(r"^https?://", "", url)
        url = re.sub(r"^www\.", "", url)
        return url.split("/")[0]

    def _fuzzy_name_similarity(self, a: str, b: str) -> float:
        """
        Compute name similarity ratio between two normalized strings.
        """
        if not a or not b:
            return 0.0
        try:
            from rapidfuzz import fuzz
            return fuzz.token_sort_ratio(a, b) / 100.0
        except ImportError:
            logger.warning("rapidfuzz not installed, falling back to exact match")
            return 1.0 if a == b else 0.0

    def compare(
        self,
        record_a: Dict[str, Any],
        record_b: Dict[str, Any]
    ) -> EntityMatchResult:
        """
        Compare two business records and compute a match confidence score.

        Match signals (weighted):
            - Exact name match         → 0.5
            - Fuzzy name match (>90%)  → 0.4
            - Phone match              → 0.3
            - Website domain match     → 0.3
            - Address partial match    → 0.2

        Args:
            record_a: First business dict (at minimum has 'business_name').
            record_b: Second business dict.

        Returns:
            EntityMatchResult with confidence and suggested_action.
        """
        name_a = self._normalize_name(record_a.get("business_name"))
        name_b = self._normalize_name(record_b.get("business_name"))

        phone_a = self._normalize_phone(record_a.get("phone"))
        phone_b = self._normalize_phone(record_b.get("phone"))

        domain_a = self._normalize_domain(record_a.get("website"))
        domain_b = self._normalize_domain(record_b.get("website"))

        confidence = 0.0
        reasons = []

        # Name similarity
        name_sim = self._fuzzy_name_similarity(name_a, name_b)
        if name_sim >= 1.0:
            confidence += 0.5
            reasons.append("exact_name_match")
        elif name_sim >= 0.9:
            confidence += 0.4
            reasons.append("fuzzy_name_match")

        # Phone match
        if phone_a and phone_b and phone_a == phone_b:
            confidence += 0.3
            reasons.append("phone_match")

        # Domain match
        if domain_a and domain_b and domain_a == domain_b:
            confidence += 0.3
            reasons.append("domain_match")

        # Address partial match (extract and check matching pincodes)
        address_a = record_a.get("address", "")
        address_b = record_b.get("address", "")
        if address_a and address_b:
            pincodes_a = re.findall(r"\b\d{5,6}\b", address_a)
            pincodes_b = re.findall(r"\b\d{5,6}\b", address_b)
            if pincodes_a and pincodes_b and set(pincodes_a) & set(pincodes_b):
                confidence += 0.2
                reasons.append("address_pincode_match")

        confidence = round(min(1.0, confidence), 2)
        is_match = confidence >= self.MATCH_THRESHOLD

        if confidence >= self.MATCH_THRESHOLD:
            action = "merge"
        elif confidence >= 0.4:
            action = "review"
        else:
            action = "ignore"

        logger.info(
            f"Comparing '{record_a.get('business_name')}' vs "
            f"'{record_b.get('business_name')}': confidence={confidence}, action={action}"
        )

        return EntityMatchResult(
            business_a_name=record_a.get("business_name", ""),
            business_b_name=record_b.get("business_name", ""),
            is_match=is_match,
            confidence=confidence,
            match_reasons=reasons,
            suggested_action=action
        )

    def merge(
        self,
        primary: Dict[str, Any],
        secondary: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Merge two business records. Primary record wins on conflicts.
        Secondary fills in missing fields from primary.
        """
        merged = {**secondary, **{k: v for k, v in primary.items() if v is not None}}
        
        # Combine source_platform lists
        sp_a = primary.get("source_platform", [])
        sp_b = secondary.get("source_platform", [])
        if isinstance(sp_a, str): sp_a = [sp_a]
        if isinstance(sp_b, str): sp_b = [sp_b]
        merged["source_platform"] = list(set(sp_a + sp_b))
        
        logger.info(
            f"Merged canonical record: '{primary.get('business_name')}' ← '{secondary.get('business_name')}'"
        )
        return merged


# ---------------------------------------------------------
# Self-Test
# ---------------------------------------------------------
if __name__ == "__main__":
    import json
    resolver = EntityResolver()
    a = {"business_name": "Acme Corp", "phone": "+91 98765 43210", "website": "https://acme.com"}
    b = {"business_name": "Acme Corporation", "phone": "9876543210", "website": "http://www.acme.com"}
    result = resolver.compare(a, b)
    print(json.dumps(asdict(result), indent=2))
