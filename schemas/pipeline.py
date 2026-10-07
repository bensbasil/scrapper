from typing import Optional, List
from pydantic import BaseModel, ConfigDict, Field

from schemas.business import Business
from schemas.enrichment import BusinessEnrichment
from schemas.intelligence import BusinessIntelligence
from schemas.intent import IntentProfile
from schemas.opportunity import Opportunity
from schemas.outreach import OutreachDraft


class StageExecution(BaseModel):
    """Execution telemetry for a single pipeline stage."""
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    stage: str
    success: bool
    duration_ms: Optional[float] = None
    error_message: Optional[str] = None


class PipelineResult(BaseModel):
    """
    Holistic outcome of processing a single business lead through the intelligence pipeline.
    Combines stage execution health telemetry with the structured domain artifacts
    produced across Discovery, Enrichment, Intelligence, Intent, Opportunity, and Outreach.
    """
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    business_id: Optional[int] = None
    business_name: str
    success: bool = True

    # High-level Summary Metrics
    opportunity_score: float = Field(default=0.0, ge=0.0, le=100.0)
    intent_score: float = Field(default=0.0, ge=0.0, le=100.0)
    outreach_urgency: str = "normal"

    # Stage Execution Telemetry
    stages: List[StageExecution] = Field(default_factory=list)
    error_message: Optional[str] = None

    # Domain Layer Artifacts
    business: Optional[Business] = None
    enrichment: Optional[BusinessEnrichment] = None
    intelligence: Optional[BusinessIntelligence] = None
    intent: Optional[IntentProfile] = None
    opportunity: Optional[Opportunity] = None
    outreach: Optional[OutreachDraft] = None
