"""
schemas/ai.py
-------------
Canonical Pydantic models for structured AI/LLM intelligence outputs.
Defines OpportunityAnalysis, CommercialRecommendation, OutreachStrategy,
and OutreachDraftResponse for validated, typed AI consumption.
"""

from typing import Optional, List
from pydantic import BaseModel, ConfigDict, Field


class CommercialRecommendation(BaseModel):
    """Specific commercial service recommendation with reasoning and tier."""
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    service_name: str = Field(..., description="Service title e.g. 'Local SEO & Review Engine'")
    target_problem: str = Field(..., description="Identified problem or bottleneck this service solves")
    commercial_impact: str = Field(..., description="Expected business impact, revenue recovery, or ROI")
    suggested_pricing_tier: str = Field(
        default="core",
        description="Suggested packaging tier: 'entry', 'core', or 'premium'"
    )


class OpportunityAnalysis(BaseModel):
    """
    Structured AI diagnostic and commercial opportunity assessment.
    Grounds high-level synthesis and recommendations in verifiable evidence.
    """
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    executive_diagnosis: str = Field(
        ...,
        description="Synthesis of why this prospect is leaking revenue or failing to convert leads"
    )
    primary_pain_category: str = Field(
        ...,
        description="Primary weakness category: 'conversion', 'reputation', 'technical', 'visibility', or 'infrastructure'"
    )
    recommendations: List[CommercialRecommendation] = Field(
        default_factory=list,
        description="Ranked commercial service recommendations"
    )
    strategic_pitch_angle: str = Field(
        ...,
        description="High-level angle for commercial sales positioning"
    )
    cited_evidence_points: List[str] = Field(
        default_factory=list,
        description="Specific factual claims cited from prospect evidence to ground the diagnosis"
    )
    confidence_score: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Confidence score for this diagnostic assessment (0.0 to 1.0)"
    )
    reasoning_mode: str = Field(
        default="ai",
        description="Reasoning generation mode: 'ai' or 'deterministic_fallback'"
    )
    evidence_sufficiency: str = Field(
        default="sufficient",
        description="Evidence sufficiency assessment: 'sufficient' or 'insufficient'"
    )


class OutreachStrategy(BaseModel):
    """
    Structured AI consultative outreach strategy and personalized messaging.
    Contains cold email, short messaging, and objection handling.
    """
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    positioning_summary: str = Field(
        ...,
        description="Strategic positioning summary explaining how to approach the prospect"
    )
    primary_angle: str = Field(
        ...,
        description="Primary pitch angle e.g. 'Customer Voice', 'Invisible Business', 'Trust Deficit'"
    )
    target_decision_maker_type: Optional[str] = Field(
        default=None,
        description="Target persona or role e.g. 'Business Owner', 'General Manager', 'Marketing Director'"
    )
    strongest_pain_point: Optional[str] = Field(
        default=None,
        description="Primary customer friction point or technical flaw to lead with"
    )
    value_proposition: Optional[str] = Field(
        default=None,
        description="Core commercial ROI or value proposition offer"
    )
    recommended_service: Optional[str] = Field(
        default=None,
        description="Specific service intervention recommended to pitch"
    )
    cold_email_subject: str = Field(
        ...,
        description="Compelling, low-friction cold email subject line"
    )
    cold_email_body: str = Field(
        ...,
        description="Concise, personalized cold email body under 120 words"
    )
    whatsapp_message: str = Field(
        ...,
        description="Punchy, direct WhatsApp/DM message under 50 words"
    )
    call_opening_hook: Optional[str] = Field(
        default=None,
        description="1-sentence conversational opening hook for cold calls"
    )
    anticipated_objection: Optional[str] = Field(
        default=None,
        description="Most likely prospect objection (e.g., 'We already have someone handling this')"
    )
    objection_counter: Optional[str] = Field(
        default=None,
        description="Low-friction counter to the anticipated objection"
    )
    cited_evidence_points: List[str] = Field(
        default_factory=list,
        description="Specific evidence items directly referenced in the outreach copy"
    )
    confidence_score: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Confidence score for this outreach strategy (0.0 to 1.0)"
    )
    reasoning_mode: str = Field(
        default="ai",
        description="Generation mode: 'ai' or 'deterministic_fallback'"
    )
    evidence_sufficiency: str = Field(
        default="sufficient",
        description="Evidence sufficiency: 'sufficient' or 'insufficient'"
    )



class OutreachDraftResponse(BaseModel):
    """
    Structured output contract matching outreach draft generation.
    Used for validated extraction of personalized cold email and messaging.
    """
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    cold_email_draft: str = Field(..., description="Personalized cold email draft")
    whatsapp_draft: str = Field(..., description="Short WhatsApp / DM message draft")
