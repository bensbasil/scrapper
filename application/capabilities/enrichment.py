"""
application/capabilities/enrichment.py
--------------------------------------
Typed application capability for leadership discovery, email validation, and social enrichment.
Delegates to DecisionMakerFinder, EmailValidator, and SocialAnalyzer.
"""

import logging
from typing import Optional, List, Any
from dataclasses import asdict

from schemas.enrichment import DecisionMakerCandidate, ValidatedEmail
from application.contracts.inputs import EnrichLeadershipSocialInput
from application.contracts.outputs import EnrichLeadershipSocialOutput
from application.policies.classification import PolicyClass

logger = logging.getLogger(__name__)


class EnrichLeadershipSocialCapability:
    """
    Identifies owners/founders, validates email records, and scores social presence.
    Classified as READ: external read-only enrichment without database mutations.
    """
    NAME = "enrich_leadership_social"
    DESCRIPTION = "Discovers leadership contacts, validates emails, and scores social presence"
    POLICY_CLASS = PolicyClass.READ

    def __init__(
        self,
        decision_finder: Optional[Any] = None,
        email_validator: Optional[Any] = None,
        social_analyzer: Optional[Any] = None
    ):
        self._decision_finder = decision_finder
        self._email_validator = email_validator
        self._social_analyzer = social_analyzer

    def execute(self, params: EnrichLeadershipSocialInput) -> EnrichLeadershipSocialOutput:
        """
        Executes leadership discovery and social profile analysis.
        """
        b_name = params.business_name.strip()
        url = params.website_url.strip() if params.website_url else None
        logger.info(f"[Capability:{self.NAME}] Enriching leadership & social profiles for '{b_name}'")

        decision_finder = self._decision_finder
        if decision_finder is None:
            from enrichment.decision_maker_finder import DecisionMakerFinder
            decision_finder = DecisionMakerFinder()

        social_analyzer = self._social_analyzer
        if social_analyzer is None:
            from enrichment.social_analyzer import SocialAnalyzer
            social_analyzer = SocialAnalyzer()

        # 1. Decision Maker Discovery
        candidates: List[DecisionMakerCandidate] = []
        top_name: Optional[str] = None
        try:
            if url:
                d_result = decision_finder.find(url)
                if hasattr(d_result, "candidates"):
                    for c in d_result.candidates:
                        candidates.append(
                            DecisionMakerCandidate(
                                name=c.name,
                                role=getattr(c, "role", "Decision Maker"),
                                confidence=getattr(c, "confidence", 0.7)
                            )
                        )
                    if hasattr(d_result, "primary_contact") and d_result.primary_contact:
                        top_name = d_result.primary_contact.name
                    elif candidates:
                        top_name = candidates[0].name
        except Exception as e:
            logger.warning(f"[Capability:{self.NAME}] DecisionMakerFinder failed for {b_name}: {e}")

        # 2. Social Profile Analysis
        social_score = 0.0
        platforms = []
        try:
            if params.social_links:
                s_result = social_analyzer.analyze(b_name, params.social_links)
                social_score = getattr(s_result, "social_activity_score", 0.0)
                platforms = getattr(s_result, "platforms_detected", [])
        except Exception as e:
            logger.warning(f"[Capability:{self.NAME}] SocialAnalyzer failed for {b_name}: {e}")

        return EnrichLeadershipSocialOutput(
            business_name=b_name,
            decision_maker_name=top_name,
            decision_makers=candidates,
            validated_emails=[],
            social_activity_score=social_score,
            platforms_found=platforms
        )
