"""
application/capabilities/intelligence.py
----------------------------------------
Typed application capability for business intelligence mining.
Delegates to ReviewMiner, CustomerPainExtractor, ConversionAnalyzer, and CompetitorAnalyzer.
"""

import logging
from typing import Optional, Any
from dataclasses import asdict

from schemas.intelligence import BusinessIntelligence, CompetitorComparison
from application.contracts.inputs import MineBusinessIntelligenceInput
from application.policies.classification import PolicyClass

logger = logging.getLogger(__name__)


class MineBusinessIntelligenceCapability:
    """
    Synthesizes customer pain mining, conversion friction, and competitor benchmarks.
    Classified as READ: read-only analytical synthesis.
    """
    NAME = "mine_business_intelligence"
    DESCRIPTION = "Extracts customer complaints, conversion bottlenecks, and competitor gap summaries"
    POLICY_CLASS = PolicyClass.READ

    def __init__(
        self,
        review_miner: Optional[Any] = None,
        pain_extractor: Optional[Any] = None,
        conversion_analyzer: Optional[Any] = None,
        competitor_analyzer: Optional[Any] = None
    ):
        self._review_miner = review_miner
        self._pain_extractor = pain_extractor
        self._conversion_analyzer = conversion_analyzer
        self._competitor_analyzer = competitor_analyzer

    def execute(self, params: MineBusinessIntelligenceInput) -> BusinessIntelligence:
        """
        Executes business intelligence extraction across reviews, conversion, and competitors.
        """
        b_name = params.business_name.strip()
        url = params.website_url.strip() if params.website_url else None
        logger.info(f"[Capability:{self.NAME}] Mining business intelligence for '{b_name}'")

        miner = self._review_miner
        if miner is None:
            from business_intelligence.review_miner import ReviewMiner
            miner = ReviewMiner()

        pain_ext = self._pain_extractor
        if pain_ext is None:
            from business_intelligence.customer_pain_extractor import CustomerPainExtractor
            pain_ext = CustomerPainExtractor()

        conv_analyzer = self._conversion_analyzer
        if conv_analyzer is None:
            from business_intelligence.conversion_analyzer import ConversionAnalyzer
            conv_analyzer = ConversionAnalyzer()

        # 1. Review Mining
        recurring_complaints = []
        recurring_praise = []
        common_themes = []
        pain_summary = None
        review_health_score = 50.0
        pain_score = 50.0
        try:
            rm_obj = miner.mine_reviews(
                business_name=b_name,
                category=params.category,
                rating=params.rating,
                review_count=params.review_count
            )
            recurring_complaints = getattr(rm_obj, "recurring_complaints", [])
            recurring_praise = getattr(rm_obj, "recurring_praise", [])
            common_themes = getattr(rm_obj, "common_themes", [])
            pain_summary = getattr(rm_obj, "pain_summary", None)
            review_health_score = float(getattr(rm_obj, "review_health_score", 50.0))
            pain_score = float(getattr(rm_obj, "pain_score", 50.0))
        except Exception as e:
            logger.warning(f"[Capability:{self.NAME}] ReviewMiner failed: {e}")

        # 2. Customer Pain Extraction
        bottlenecks = []
        try:
            if recurring_complaints:
                p_obj = pain_ext.extract_pains(b_name, recurring_complaints)
                bottlenecks = getattr(p_obj, "bottlenecks", [])
        except Exception as e:
            logger.warning(f"[Capability:{self.NAME}] CustomerPainExtractor failed: {e}")

        # 3. Conversion Friction
        conv_friction = 0.0
        conv_health = 100.0
        conversion_issues = []
        booking_flow_exists = False
        try:
            c_obj = conv_analyzer.analyze(b_name, url)
            conv_friction = float(getattr(c_obj, "conversion_friction_score", 0.0))
            conv_health = float(getattr(c_obj, "conversion_health_score", 100.0))
            conversion_issues = getattr(c_obj, "conversion_issues", [])
            booking_flow_exists = getattr(c_obj, "booking_flow_exists", False)
        except Exception as e:
            logger.warning(f"[Capability:{self.NAME}] ConversionAnalyzer failed: {e}")

        # 4. Competitor Gap
        competitor_gap_summary = None
        competitors = []
        if self._competitor_analyzer is not None:
            try:
                comp_obj = self._competitor_analyzer.analyze(
                    business_id=0,
                    business_name=b_name,
                    category=params.category,
                    address=params.address,
                    opportunity_score=conv_friction
                )
                competitor_gap_summary = getattr(comp_obj, "competitor_gap_summary", None)
            except Exception as e:
                logger.warning(f"[Capability:{self.NAME}] CompetitorAnalyzer failed: {e}")

        return BusinessIntelligence(
            business_name=b_name,
            overall_health_score=round((conv_health + review_health_score) / 2.0, 1),
            conversion_health_score=conv_health,
            conversion_friction_score=conv_friction,
            booking_flow_exists=booking_flow_exists,
            conversion_issues=conversion_issues,
            review_health_score=review_health_score,
            pain_score=pain_score,
            recurring_complaints=recurring_complaints,
            recurring_praise=recurring_praise,
            common_themes=common_themes,
            bottlenecks=bottlenecks,
            pain_summary=pain_summary,
            competitor_gap_summary=competitor_gap_summary,
            competitors=competitors
        )
