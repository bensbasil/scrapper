"""
application/capabilities/opportunity.py
---------------------------------------
Typed application capability for AI commercial opportunity reasoning.
Delegates to OpportunityReasoner.
"""

import logging
from typing import Optional

from schemas.ai import OpportunityAnalysis
from ai.opportunity_reasoner import OpportunityReasoner
from application.contracts.inputs import SynthesizeOpportunityInput
from application.policies.classification import PolicyClass

logger = logging.getLogger(__name__)


class SynthesizeOpportunityAnalysisCapability:
    """
    Synthesizes executive commercial diagnosis and prioritized service recommendations.
    Classified as READ: invokes LLMClient or safe deterministic fallback without side effects.
    """
    NAME = "synthesize_opportunity_analysis"
    DESCRIPTION = "Synthesizes AI executive commercial diagnosis and service recommendations from ProspectContext"
    POLICY_CLASS = PolicyClass.READ

    def __init__(self, reasoner: Optional[OpportunityReasoner] = None):
        self._reasoner = reasoner or OpportunityReasoner()

    def execute(self, params: SynthesizeOpportunityInput) -> OpportunityAnalysis:
        """
        Executes opportunity reasoning on the provided ProspectContext.
        """
        b_name = params.context.business.business_name
        logger.info(f"[Capability:{self.NAME}] Synthesizing opportunity analysis for '{b_name}'")

        analysis = self._reasoner.reason(params.context)
        # Cache back onto context if helpful
        params.context.opportunity_analysis = analysis
        return analysis
