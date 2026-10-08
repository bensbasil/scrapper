"""
schemas/context.py
------------------
Canonical Pydantic models for the unified Prospect Evidence Context.
Defines EvidenceItem, ScoreCard, and ProspectContext for downstream
AI/LLM intelligence consumption and deterministic reporting.
"""

from typing import Optional, List, Dict, Any
from pydantic import BaseModel, ConfigDict, Field

from schemas.business import Business
from schemas.enrichment import BusinessEnrichment
from schemas.intelligence import BusinessIntelligence
from schemas.intent import IntentProfile
from schemas.opportunity import Opportunity
from schemas.ai import OpportunityAnalysis, OutreachStrategy


class EvidenceItem(BaseModel):
    """
    Atomic factual observation with verifiable provenance.
    Preserves the exact source attributing why an issue, friction point, or signal was claimed.
    """
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    category: str = Field(
        ...,
        description="Evidence category: identity, technical, conversion, reputation, competition, intent, opportunity, credibility"
    )
    claim: str = Field(
        ...,
        description="Human-readable verifiable assertion e.g. 'Missing online booking flow detected'"
    )
    source: str = Field(
        ...,
        description="Generating module name e.g. 'ConversionAnalyzer', 'ReviewMiner', 'HiringSignalDetector'"
    )
    value: Any = Field(
        default=None,
        description="Underlying raw data point or extracted value"
    )
    confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Confidence level of this observation (0.0 to 1.0)"
    )


class ScoreCard(BaseModel):
    """
    Normalized scorecard resolving semantic polarities across all platform metrics.

    Explicit Semantic Rules:
    - sales_opportunity_score: HIGHER value -> greater digital deficiency / sales pitch opportunity (0-100)
    - digital_health_rating:   HIGHER value -> healthier digital/business presence (0-100)
    """
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    # Core Polarity Metrics
    sales_opportunity_score: float = Field(
        default=0.0,
        ge=0.0,
        le=100.0,
        description="0-100: Higher = greater digital deficiency and sales pitch opportunity"
    )
    digital_health_rating: float = Field(
        default=0.0,
        ge=0.0,
        le=100.0,
        description="0-100: Higher = healthier digital and business presence"
    )

    # Granular Component Penalties (0-100, higher = worse digital state)
    website_weakness_penalty: float = Field(
        default=0.0,
        ge=0.0,
        le=100.0,
        description="Raw website weakness penalty from scoring engine (100 = poor, 0 = perfect)"
    )
    seo_weakness_penalty: float = Field(
        default=0.0,
        ge=0.0,
        le=100.0,
        description="Raw SEO weakness penalty from scoring engine (100 = poor, 0 = perfect)"
    )
    automation_need_penalty: float = Field(
        default=0.0,
        ge=0.0,
        le=100.0,
        description="Raw automation deficiency penalty (100 = high need, 0 = low need)"
    )
    conversion_friction_score: float = Field(
        default=0.0,
        ge=0.0,
        le=100.0,
        description="Conversion friction index (100 = acute friction, 0 = seamless)"
    )

    # Buying Intent & Urgency (0-100, higher = more urgent receptivity)
    buying_intent_score: float = Field(
        default=0.0,
        ge=0.0,
        le=100.0,
        description="Composite buying readiness score (0-100)"
    )
    outreach_urgency: str = Field(
        default="normal",
        pattern="^(urgent|high|normal|low)$",
        description="Urgency classification: urgent, high, normal, low"
    )


class ProspectContext(BaseModel):
    """
    Unified, AI-ready prospect evidence context.
    Encapsulates verified facts, structured domain intelligence, normalized scores,
    and atomic evidence items into a compact, explainable data structure.
    """
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    # Core Prospect Identity & Normalized Scores
    business: Business
    scores: ScoreCard

    # Structured Domain Intelligence Models
    enrichment: Optional[BusinessEnrichment] = None
    intelligence: Optional[BusinessIntelligence] = None
    intent: Optional[IntentProfile] = None
    opportunity: Optional[Opportunity] = None
    opportunity_analysis: Optional[OpportunityAnalysis] = None
    outreach_strategy: Optional[OutreachStrategy] = None

    # Atomic Evidence & Provenance
    evidence: List[EvidenceItem] = Field(default_factory=list)
    summary_bullets: List[str] = Field(default_factory=list)

    def get_evidence_by_category(self, category: str) -> List[EvidenceItem]:
        """Returns all evidence items matching the specified category."""
        return [item for item in self.evidence if item.category.lower() == category.lower()]

    def to_token_efficient_summary(self) -> str:
        """
        Produces a compact, token-efficient plain text summary (< 350 words)
        suitable for direct injection into LLM prompts without token bloat.
        """
        lines = [
            f"# Prospect Evidence: {self.business.business_name}",
            f"- Category: {self.business.category or 'Local Business'}",
            f"- Location: {self.business.address or 'Unknown'}",
            f"- Website: {self.business.website or 'None'}",
            f"- Sales Opportunity Score: {self.scores.sales_opportunity_score}/100 (Higher = greater digital deficiency)",
            f"- Digital Health Rating: {self.scores.digital_health_rating}/100 (Higher = healthier presence)",
            f"- Buying Intent: {self.scores.buying_intent_score}/100 (Urgency: {self.scores.outreach_urgency})",
        ]

        if self.enrichment and self.enrichment.decision_maker_name:
            lines.append(f"- Decision Maker: {self.enrichment.decision_maker_name}")

        if self.summary_bullets:
            lines.append("\n## Key Verified Findings:")
            for b in self.summary_bullets:
                lines.append(f"- {b}")

        # Top 3 complaints if available
        if self.intelligence and self.intelligence.recurring_complaints:
            lines.append(f"- Top Customer Complaints: {', '.join(self.intelligence.recurring_complaints[:3])}")

        # Competitor gap summary if available
        if self.intelligence and self.intelligence.competitor_gap_summary:
            lines.append(f"- Local Competitor Gap: {self.intelligence.competitor_gap_summary}")

        # Service recommendations if available
        if self.opportunity and self.opportunity.service_recommendations:
            recs = [r.service_name for r in self.opportunity.service_recommendations]
            lines.append(f"- Recommended Pitch Services: {', '.join(recs)}")

        return "\n".join(lines)
