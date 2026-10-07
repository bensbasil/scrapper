from typing import Optional, List
from pydantic import BaseModel, ConfigDict, Field


class ValidatedEmail(BaseModel):
    """Per-email syntax and DNS MX validation outcome."""
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    email: str
    syntax_valid: bool = False
    mx_record_exists: bool = False
    confidence_score: float = Field(default=0.0, ge=0.0, le=1.0)
    validation_error: Optional[str] = None


class DecisionMakerCandidate(BaseModel):
    """An identified potential owner, founder, director, or key decision-maker."""
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    name: str
    role: Optional[str] = None
    source: Optional[str] = None
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class BusinessEnrichment(BaseModel):
    """
    Composite enrichment data for a business.
    Consolidates technical stack signatures, validated email intelligence,
    discovered leadership contacts, social media audit, and company registry records.
    """
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    business_name: str
    website_url: Optional[str] = None

    # Tech Stack Signatures
    cms: Optional[str] = None
    frontend_framework: Optional[str] = None
    analytics_tools: List[str] = Field(default_factory=list)
    payment_tools: List[str] = Field(default_factory=list)
    chat_tools: List[str] = Field(default_factory=list)
    raw_server_header: Optional[str] = None

    # Contact Intelligence
    extracted_emails: List[str] = Field(default_factory=list)
    validated_emails: List[ValidatedEmail] = Field(default_factory=list)
    decision_maker_name: Optional[str] = None
    decision_makers: List[DecisionMakerCandidate] = Field(default_factory=list)

    # Social Presence
    social_links: List[str] = Field(default_factory=list)
    social_activity_score: float = Field(default=0.0, ge=0.0, le=100.0)
    total_platforms_found: int = 0
    total_platforms_active: int = 0

    # Registry Intelligence (OpenCorporates)
    company_number: Optional[str] = None
    jurisdiction: Optional[str] = None
    company_status: Optional[str] = None
    incorporation_date: Optional[str] = None
