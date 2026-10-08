"""
evaluation/models.py
--------------------
Pydantic v2 contracts for AI reasoning evaluation.
Defines EvaluationResult, ComponentEvaluation, HeuristicFlag, and BatchEvaluationSummary
for evaluating OpportunityAnalysis and OutreachStrategy against ProspectContext.
"""

from typing import Optional, List, Dict, Any
from pydantic import BaseModel, ConfigDict, Field


class HeuristicFlag(BaseModel):
    """
    Explainable heuristic indicator flagging potential hallucinations, contradictions,
    or unsupported factual claims.
    """
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    flag_type: str = Field(
        ...,
        description="Type of check e.g. 'contradiction_website_exists', 'unsupported_claim', 'polarity_contradiction'"
    )
    status: str = Field(
        ...,
        pattern="^(confirmed_supported|potentially_unsupported)$",
        description="Grounding status: 'confirmed_supported' or 'potentially_unsupported'"
    )
    claim: str = Field(
        ...,
        description="The specific claim, cited point, or sentence being flagged"
    )
    reason: str = Field(
        ...,
        description="Explanation detailing why this claim is flagged or confirmed against context evidence"
    )
    severity: str = Field(
        default="warning",
        pattern="^(info|warning|error)$",
        description="Severity level of the flag: 'info', 'warning', or 'error'"
    )


class ComponentEvaluation(BaseModel):
    """
    Evaluation breakdown for a single AI reasoning component (Opportunity or Outreach).
    """
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    component_name: str = Field(
        ...,
        description="Component being evaluated: 'opportunity_analysis' or 'outreach_strategy'"
    )
    score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Overall component score (0.0 to 1.0)"
    )
    structural_validity: bool = Field(
        default=True,
        description="Whether required fields, types, and constraints are valid"
    )
    grounding_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Factual grounding score against context evidence (0.0 to 1.0)"
    )
    relevance_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Commercial relevance and problem-solution alignment score (0.0 to 1.0)"
    )
    consistency_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Scorecard polarity and internal consistency score (0.0 to 1.0)"
    )
    evidence_coverage_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Coverage of verified negative findings in context (0.0 to 1.0)"
    )
    supported_claims: List[str] = Field(
        default_factory=list,
        description="List of cited points verified as supported by context"
    )
    unsupported_claims: List[str] = Field(
        default_factory=list,
        description="List of cited points lacking verifiable support in context"
    )
    issues: List[str] = Field(
        default_factory=list,
        description="Identified structural, factual, or logical issues"
    )
    passed: bool = Field(
        default=True,
        description="Whether this component satisfies pass thresholds"
    )


class EvaluationResult(BaseModel):
    """
    Canonical evaluation contract for AI reasoning quality across the pipeline.
    Combines structural validity, evidence grounding, scorecard consistency,
    commercial relevance, and conservative heuristic hallucination flags.
    """
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    overall_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Composite quality score bounded between 0.0 and 1.0"
    )
    grounding_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Evidence grounding fidelity score bounded between 0.0 and 1.0"
    )
    relevance_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Commercial relevance score bounded between 0.0 and 1.0"
    )
    consistency_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Internal and scorecard polarity consistency score bounded between 0.0 and 1.0"
    )
    evidence_coverage_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Context evidence utilization coverage bounded between 0.0 and 1.0"
    )
    hallucination_flags: List[str] = Field(
        default_factory=list,
        description="Human-readable warning flags for potential hallucinations or contradictions"
    )
    issues: List[str] = Field(
        default_factory=list,
        description="List of detected defects, mismatches, or quality failures"
    )
    passed: bool = Field(
        ...,
        description="True if reasoning passes production quality and grounding thresholds"
    )

    # Granular breakdown attributes
    structural_validity: bool = Field(
        default=True,
        description="Whether all evaluated outputs passed structural schema checks"
    )
    opportunity_evaluation: Optional[ComponentEvaluation] = Field(
        default=None,
        description="Detailed evaluation of OpportunityAnalysis if present"
    )
    outreach_evaluation: Optional[ComponentEvaluation] = Field(
        default=None,
        description="Detailed evaluation of OutreachStrategy if present"
    )
    heuristic_details: List[HeuristicFlag] = Field(
        default_factory=list,
        description="Structured heuristic hallucination flags"
    )


class BatchEvaluationSummary(BaseModel):
    """
    Aggregated evaluation report across multiple test fixtures or prospects.
    """
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    total_evaluated: int = Field(default=0, ge=0)
    passed_count: int = Field(default=0, ge=0)
    failed_count: int = Field(default=0, ge=0)
    average_overall_score: float = Field(default=0.0, ge=0.0, le=1.0)
    average_grounding_score: float = Field(default=0.0, ge=0.0, le=1.0)
    average_consistency_score: float = Field(default=0.0, ge=0.0, le=1.0)
    average_relevance_score: float = Field(default=0.0, ge=0.0, le=1.0)
    average_evidence_coverage_score: float = Field(default=0.0, ge=0.0, le=1.0)
    total_hallucination_flags: int = Field(default=0, ge=0)
    results: List[EvaluationResult] = Field(default_factory=list)
