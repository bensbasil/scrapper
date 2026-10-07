from typing import Optional, List
from pydantic import BaseModel, ConfigDict, Field


class ServiceRecommendation(BaseModel):
    """Specific commercial service recommendation mapped from identified weaknesses."""
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    service_name: str
    impact_explanation: str


class Opportunity(BaseModel):
    """
    Synthesized commercial opportunity analysis for a prospect.
    Combines deterministic digital presence deficiency scores, heuristic pain points,
    tailored service recommendations, and executive pitch rationale.
    """
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    business_name: str
    website_url: Optional[str] = None

    # Opportunity Scores (0-100, higher = greater deficiency / higher sales potential)
    opportunity_score: float = Field(default=0.0, ge=0.0, le=100.0)
    website_quality_score: float = Field(default=0.0, ge=0.0, le=100.0)
    seo_score: float = Field(default=0.0, ge=0.0, le=100.0)
    automation_need_score: float = Field(default=0.0, ge=0.0, le=100.0)

    # Deficiencies & Service Matches
    detected_pain_points: List[str] = Field(default_factory=list)
    likely_service_match: List[str] = Field(default_factory=list)

    # Concrete Commercial Pitch Mapping
    service_recommendations: List[ServiceRecommendation] = Field(default_factory=list)
    opportunity_reasoning: Optional[str] = None
    executive_summary: Optional[str] = None
