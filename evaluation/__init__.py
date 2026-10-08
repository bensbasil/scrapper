"""
evaluation package
------------------
Deterministic evaluation layer for AI reasoning models (OpportunityAnalysis and OutreachStrategy).
Provides typed evaluation contracts, evaluators, and test fixtures.
"""

from evaluation.models import (
    EvaluationResult,
    ComponentEvaluation,
    HeuristicFlag,
    BatchEvaluationSummary,
)
from evaluation.evaluators import (
    OpportunityEvaluator,
    OutreachEvaluator,
    EvaluationRunner,
)

__all__ = [
    "EvaluationResult",
    "ComponentEvaluation",
    "HeuristicFlag",
    "BatchEvaluationSummary",
    "OpportunityEvaluator",
    "OutreachEvaluator",
    "EvaluationRunner",
]
