"""
application/capabilities/context.py
-----------------------------------
Typed application capability for assembling ProspectContext.
Delegates to ProspectContextBuilder. Pure in-memory assembly.
"""

import logging
from typing import Optional

from schemas.context import ProspectContext
from ai.context_builder import ProspectContextBuilder
from application.contracts.inputs import AssembleProspectContextInput
from application.policies.classification import PolicyClass

logger = logging.getLogger(__name__)


class AssembleProspectContextCapability:
    """
    Assembles pipeline stage findings into a unified, token-efficient ProspectContext.
    Classified as READ: pure in-memory data transformation.
    """
    NAME = "assemble_prospect_context"
    DESCRIPTION = "Compiles verified facts, scores, complaints, and evidence items into unified ProspectContext"
    POLICY_CLASS = PolicyClass.READ

    def __init__(self, context_builder: Optional[ProspectContextBuilder] = None):
        self._builder = context_builder or ProspectContextBuilder()

    def execute(self, params: AssembleProspectContextInput) -> ProspectContext:
        """
        Assembles all stage dictionaries into a validated ProspectContext.
        """
        b_name = params.business_data.get("business_name", "Unknown")
        logger.info(f"[Capability:{self.NAME}] Assembling unified ProspectContext for '{b_name}'")

        health_data = params.health_data or params.intelligence_data

        return self._builder.build_context(
            business_data=params.business_data,
            analysis_data=params.analysis_data,
            seo_data=params.seo_data,
            scoring_data=params.scoring_data,
            tech_data=params.tech_data,
            email_data=params.email_data,
            decision_data=params.decision_data,
            social_data=params.social_data,
            registry_data=params.registry_data,
            freshness_data=params.freshness_data,
            hiring_data=params.hiring_data,
            review_trend_data=params.review_trend_data,
            intent_data=params.intent_data,
            conversion_data=params.conversion_data,
            review_mine_data=params.review_mine_data,
            pain_data=params.pain_data,
            competitor_data=params.competitor_data,
            trust_data=params.trust_data,
            health_data=health_data,
            opportunity_data=params.opportunity_data,
        )
