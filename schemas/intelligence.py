from typing import Optional, List
from pydantic import BaseModel, ConfigDict, Field


class CompetitorComparison(BaseModel):
    """Local competitor comparison metric."""
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    name: str
    website: Optional[str] = None
    rating: Optional[float] = None
    opportunity_score: float = Field(default=0.0, ge=0.0, le=100.0)
    score_gap: float = 0.0


class BusinessIntelligence(BaseModel):
    """
    Consolidated Business Intelligence analysis for a prospect.
    Synthesizes conversion friction analysis, customer pain mining,
    credibility trust signals, local competitor digital gaps, and composite health ratings.
    """
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    business_name: str

    # Overall Business Health Ratings (0-100, higher = healthier)
    overall_health_score: float = Field(default=0.0, ge=0.0, le=100.0)
    website_health_score: float = Field(default=0.0, ge=0.0, le=100.0)

    # Conversion Friction Analysis
    conversion_health_score: float = Field(default=0.0, ge=0.0, le=100.0)
    conversion_friction_score: float = Field(default=0.0, ge=0.0, le=100.0)
    booking_flow_exists: bool = False
    weak_ctas: bool = False
    lead_capture_form_exists: bool = False
    contact_friction: bool = False
    whatsapp_available: bool = False
    conversion_issues: List[str] = Field(default_factory=list)

    # Customer Pain & Review Mining
    review_health_score: float = Field(default=0.0, ge=0.0, le=100.0)
    pain_score: float = Field(default=0.0, ge=0.0, le=100.0)
    recurring_complaints: List[str] = Field(default_factory=list)
    recurring_praise: List[str] = Field(default_factory=list)
    common_themes: List[str] = Field(default_factory=list)
    bottlenecks: List[str] = Field(default_factory=list)
    pain_summary: Optional[str] = None

    # Trust & Credibility Signals
    trust_health_score: float = Field(default=0.0, ge=0.0, le=100.0)
    trust_signals: List[str] = Field(default_factory=list)

    # Competitive Analysis
    competitor_gap_summary: Optional[str] = None
    competitors: List[CompetitorComparison] = Field(default_factory=list)
