from typing import Optional, List
from pydantic import BaseModel, ConfigDict, Field


class IntentSignal(BaseModel):
    """An individual signal contributing to lead buying urgency."""
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    signal_name: str
    signal_score: float = Field(default=0.0, ge=0.0, le=100.0)
    details: Optional[str] = None


class IntentProfile(BaseModel):
    """
    Composite intent profile evaluating a business's receptivity and urgency for outreach.
    Synthesizes technical hiring signals, website freshness/maintenance decay,
    negative review trends, and baseline digital opportunity.
    """
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    business_id: Optional[int] = None
    business_name: str

    # Composite & Sub-module Intent Scores (0-100)
    intent_score: float = Field(default=0.0, ge=0.0, le=100.0)
    hiring_signal_score: float = Field(default=0.0, ge=0.0, le=100.0)
    review_trend_score: float = Field(default=0.0, ge=0.0, le=100.0)
    freshness_score: float = Field(default=0.0, ge=0.0, le=100.0)
    opportunity_score: float = Field(default=0.0, ge=0.0, le=100.0)

    # Narrative & Urgency
    top_intent_signals: List[str] = Field(default_factory=list)
    outreach_urgency: str = Field(default="normal", pattern="^(urgent|high|normal|low)$")
    evaluated_at: Optional[str] = None
