"""
application/contracts/inputs.py
-------------------------------
Typed Pydantic v2 input schemas for all 10 application capabilities.
Ensures the future Agent interacts exclusively with validated parameter contracts.
"""

from typing import Optional, List, Dict, Any
from pydantic import BaseModel, ConfigDict, Field

from schemas.context import ProspectContext
from schemas.ai import OpportunityAnalysis, OutreachStrategy


class DiscoverProspectsInput(BaseModel):
    """Input parameters for discover_prospects capability."""
    model_config = ConfigDict(extra="ignore")

    query: str = Field(..., description="Search query e.g. 'plumbers in Chicago' or 'dentists'")
    location: Optional[str] = Field(default=None, description="Optional geographic location constraint")
    limit: int = Field(default=10, ge=1, le=100, description="Maximum number of prospects to discover")
    source: str = Field(default="gmaps", description="Discovery source: 'gmaps', 'justdial', or 'indiamart'")


class AuditWebsiteTechInput(BaseModel):
    """Input parameters for audit_website_tech capability."""
    model_config = ConfigDict(extra="ignore")

    business_name: str = Field(..., description="Prospect business name")
    website_url: str = Field(..., description="Target website URL to analyze")


class EnrichLeadershipSocialInput(BaseModel):
    """Input parameters for enrich_leadership_social capability."""
    model_config = ConfigDict(extra="ignore")

    business_name: str = Field(..., description="Prospect business name")
    website_url: Optional[str] = Field(default=None, description="Website URL for email and leadership scraping")
    social_links: List[str] = Field(default_factory=list, description="List of social profile URLs already discovered")


class MineBusinessIntelligenceInput(BaseModel):
    """Input parameters for mine_business_intelligence capability."""
    model_config = ConfigDict(extra="ignore")

    business_name: str = Field(..., description="Prospect business name")
    category: Optional[str] = Field(default=None, description="Business vertical or category")
    website_url: Optional[str] = Field(default=None, description="Business website URL")
    rating: Optional[float] = Field(default=None, ge=0.0, le=5.0, description="Google / directory rating")
    review_count: Optional[int] = Field(default=None, ge=0, description="Total review count")
    address: Optional[str] = Field(default=None, description="Business address for competitor benchmarking")


class CalculateHealthAndScoresInput(BaseModel):
    """Input parameters for calculate_health_and_scores capability."""
    model_config = ConfigDict(extra="ignore")

    business_name: str = Field(..., description="Prospect business name")
    website_quality_score: float = Field(default=0.0, ge=0.0, le=100.0)
    seo_score: float = Field(default=0.0, ge=0.0, le=100.0)
    conversion_friction_score: float = Field(default=0.0, ge=0.0, le=100.0)
    trust_health_score: float = Field(default=0.0, ge=0.0, le=100.0)
    review_health_score: float = Field(default=0.0, ge=0.0, le=100.0)
    rating: Optional[float] = Field(default=None, ge=0.0, le=5.0)
    review_count: Optional[int] = Field(default=None, ge=0)


class AssembleProspectContextInput(BaseModel):
    """Input parameters for assemble_prospect_context capability."""
    model_config = ConfigDict(extra="ignore")

    business_data: Dict[str, Any] = Field(..., description="Core business identity dict or model dump")
    analysis_data: Optional[Dict[str, Any]] = Field(default=None, description="Website audit dictionary")
    seo_data: Optional[Dict[str, Any]] = Field(default=None, description="SEO audit dictionary")
    scoring_data: Optional[Dict[str, Any]] = Field(default=None, description="Scoring engine dictionary")
    tech_data: Optional[Dict[str, Any]] = Field(default=None, description="Technical signal dictionary")
    email_data: Optional[Dict[str, Any]] = Field(default=None, description="Extracted email dictionary")
    decision_data: Optional[Dict[str, Any]] = Field(default=None, description="Decision maker dictionary")
    social_data: Optional[Dict[str, Any]] = Field(default=None, description="Social media dictionary")
    registry_data: Optional[Dict[str, Any]] = Field(default=None, description="Company registry dictionary")
    freshness_data: Optional[Dict[str, Any]] = Field(default=None, description="Website freshness dictionary")
    hiring_data: Optional[Dict[str, Any]] = Field(default=None, description="Hiring signal dictionary")
    review_trend_data: Optional[Dict[str, Any]] = Field(default=None, description="Review trend dictionary")
    intent_data: Optional[Dict[str, Any]] = Field(default=None, description="Intent profile dictionary")
    conversion_data: Optional[Dict[str, Any]] = Field(default=None, description="Conversion friction dictionary")
    review_mine_data: Optional[Dict[str, Any]] = Field(default=None, description="Review mining dictionary")
    pain_data: Optional[Dict[str, Any]] = Field(default=None, description="Customer pain dictionary")
    competitor_data: Optional[Dict[str, Any]] = Field(default=None, description="Competitor gap dictionary")
    trust_data: Optional[Dict[str, Any]] = Field(default=None, description="Trust signal dictionary")
    health_data: Optional[Dict[str, Any]] = Field(default=None, description="Health profile dictionary")
    opportunity_data: Optional[Dict[str, Any]] = Field(default=None, description="Opportunity mapper dictionary")
    intelligence_data: Optional[Dict[str, Any]] = Field(default=None, description="Composite intelligence dictionary")


class SynthesizeOpportunityInput(BaseModel):
    """Input parameters for synthesize_opportunity_analysis capability."""
    model_config = ConfigDict(arbitrary_types_allowed=True)

    context: ProspectContext = Field(..., description="Unified Prospect Evidence Context")


class FormulateOutreachStrategyInput(BaseModel):
    """Input parameters for formulate_outreach_strategy capability."""
    model_config = ConfigDict(arbitrary_types_allowed=True)

    context: ProspectContext = Field(..., description="Unified Prospect Evidence Context")
    opportunity_analysis: Optional[OpportunityAnalysis] = Field(
        default=None,
        description="Optional OpportunityAnalysis instance; will be extracted from context if omitted"
    )


class EvaluateAIReasoningInput(BaseModel):
    """Input parameters for evaluate_ai_reasoning capability."""
    model_config = ConfigDict(arbitrary_types_allowed=True)

    context: ProspectContext = Field(..., description="Unified Prospect Evidence Context")
    opportunity_analysis: Optional[OpportunityAnalysis] = Field(
        default=None,
        description="OpportunityAnalysis instance to evaluate"
    )
    outreach_strategy: Optional[OutreachStrategy] = Field(
        default=None,
        description="OutreachStrategy instance to evaluate"
    )


class RenderOutreachDraftsInput(BaseModel):
    """Input parameters for render_outreach_drafts capability."""
    model_config = ConfigDict(arbitrary_types_allowed=True)

    context: ProspectContext = Field(..., description="Unified Prospect Evidence Context")
    outreach_strategy: Optional[OutreachStrategy] = Field(
        default=None,
        description="Strategic reasoning to consume for drafting"
    )
    persist_to_db: bool = Field(
        default=False,
        description="Whether to stage/persist draft to internal PostgreSQL database"
    )
    business_id: Optional[int] = Field(
        default=None,
        description="Database business_id foreign key if persisting"
    )
