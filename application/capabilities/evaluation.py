"""
application/capabilities/evaluation.py
--------------------------------------
Typed application capability for evaluating AI reasoning quality.
Delegates to EvaluationRunner. Purely deterministic in-memory execution.
"""

import logging
from typing import Optional

from evaluation.models import EvaluationResult
from evaluation.evaluators import EvaluationRunner
from application.contracts.inputs import EvaluateAIReasoningInput
from application.policies.classification import PolicyClass

logger = logging.getLogger(__name__)


class EvaluateAIReasoningCapability:
    """
    Evaluates OpportunityAnalysis and OutreachStrategy quality, grounding, and hallucinations.
    Classified as READ: pure deterministic in-memory evaluation.
    """
    NAME = "evaluate_ai_reasoning"
    DESCRIPTION = "Evaluates AI opportunity analysis and outreach strategy for grounding, consistency, and hallucinations"
    POLICY_CLASS = PolicyClass.READ

    def __init__(self, runner: Optional[EvaluationRunner] = None):
        self._runner = runner or EvaluationRunner()

    def execute(self, params: EvaluateAIReasoningInput) -> EvaluationResult:
        """
        Executes deterministic evaluation checks on provided context and AI reasoning models.
        """
        b_name = params.context.business.business_name
        logger.info(f"[Capability:{self.NAME}] Evaluating AI reasoning quality for '{b_name}'")

        return self._runner.evaluate(
            context=params.context,
            opportunity_analysis=params.opportunity_analysis,
            outreach_strategy=params.outreach_strategy
        )
