"""
application/contracts/outputs.py
--------------------------------
Typed Pydantic v2 output schemas for capabilities requiring a dedicated contract.
Reuses existing domain entities (Business, DecisionMakerCandidate, ValidatedEmail)
to maintain semantic continuity without duplication.
"""

from typing import Optional, List, Dict, Any
from pydantic import BaseModel, ConfigDict, Field

from schemas.business import Business
from schemas.enrichment import DecisionMakerCandidate, ValidatedEmail


class DiscoverProspectsOutput(BaseModel):
    """Output contract for discover_prospects capability."""
    model_config = ConfigDict(from_attributes=True)

    query: str
    total_found: int
    source: str
    businesses: List[Business] = Field(default_factory=list)


class AuditWebsiteTechOutput(BaseModel):
    """Output contract for audit_website_tech capability."""
    model_config = ConfigDict(from_attributes=True)

    business_name: str
    website_url: str
    is_active: bool = False
    has_ssl: bool = False
    is_mobile_friendly: bool = False
    page_load_speed_seconds: Optional[float] = None
    cms: Optional[str] = None
    tech_stack: List[str] = Field(default_factory=list)
    forms_detected: bool = False
    phone_found: Optional[str] = None
    emails_found: List[str] = Field(default_factory=list)
    social_links_found: List[str] = Field(default_factory=list)
    raw_details: Dict[str, Any] = Field(default_factory=dict)


class EnrichLeadershipSocialOutput(BaseModel):
    """Output contract for enrich_leadership_social capability."""
    model_config = ConfigDict(from_attributes=True)

    business_name: str
    decision_maker_name: Optional[str] = None
    decision_makers: List[DecisionMakerCandidate] = Field(default_factory=list)
    validated_emails: List[ValidatedEmail] = Field(default_factory=list)
    social_activity_score: float = Field(default=0.0, ge=0.0, le=100.0)
    platforms_found: List[str] = Field(default_factory=list)
