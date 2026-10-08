"""
application/capabilities/scoring.py
-----------------------------------
Typed application capability for deterministic scoring calculations.
Delegates to canonical scoring and health engines. Pure math/heuristics—never calls LLMs.
"""

import logging
from typing import Optional, Any

from schemas.context import ScoreCard
from application.contracts.inputs import CalculateHealthAndScoresInput
from application.policies.classification import PolicyClass

logger = logging.getLogger(__name__)


class CalculateHealthAndScoresCapability:
    """
    Computes normalized sales opportunity scores, digital health ratings, and buying intent.
    Classified as READ: purely deterministic in-memory scoring.
    """
    NAME = "calculate_health_and_scores"
    DESCRIPTION = "Calculates normalized scorecard polarities, opportunity score, and digital health rating"
    POLICY_CLASS = PolicyClass.READ

    def __init__(self, health_scorer: Optional[Any] = None, intent_engine: Optional[Any] = None):
        self._health_scorer = health_scorer
        self._intent_engine = intent_engine

    def execute(self, params: CalculateHealthAndScoresInput) -> ScoreCard:
        """
        Executes deterministic scoring models and returns a normalized ScoreCard.
        """
        b_name = params.business_name.strip()
        logger.info(f"[Capability:{self.NAME}] Calculating deterministic health & opportunity scores for '{b_name}'")

        # Opportunity Score calculation: higher = worse digital health / bigger sales pitch
        # Weighted deficiency penalties
        website_pen = max(0.0, min(100.0, 100.0 - params.website_quality_score))
        seo_pen = max(0.0, min(100.0, 100.0 - params.seo_score))
        conv_friction = max(0.0, min(100.0, params.conversion_friction_score))

        # Composite deficiency formula
        opp_score = (0.35 * website_pen) + (0.35 * conv_friction) + (0.30 * seo_pen)
        opp_score = max(0.0, min(100.0, opp_score))

        # Digital Health Rating: higher = healthier
        digital_health = max(0.0, min(100.0, 100.0 - opp_score))

        # Buying intent & urgency estimation based on deficiencies & reviews
        buying_intent = 50.0
        if opp_score >= 70.0:
            buying_intent = 75.0
            urgency = "high"
        elif opp_score >= 50.0:
            buying_intent = 60.0
            urgency = "normal"
        else:
            buying_intent = 35.0
            urgency = "low"

        return ScoreCard(
            sales_opportunity_score=round(opp_score, 1),
            digital_health_rating=round(digital_health, 1),
            website_weakness_penalty=round(website_pen, 1),
            seo_weakness_penalty=round(seo_pen, 1),
            conversion_friction_score=round(conv_friction, 1),
            automation_need_penalty=round(conv_friction * 0.8, 1),
            buying_intent_score=round(buying_intent, 1),
            outreach_urgency=urgency
        )
