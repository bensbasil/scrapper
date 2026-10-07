from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, ConfigDict, Field


class Business(BaseModel):
    """
    Core business prospect representation.
    Represents discovered candidate businesses across Google Maps, JustDial, IndiaMart,
    and the persistent PostgreSQL businesses table.
    """
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    # Identifiers & Primary Info
    id: Optional[int] = None
    business_name: str
    category: Optional[str] = None
    website: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None

    # Google Maps Metrics
    google_rating: Optional[float] = None
    review_count: Optional[int] = None

    # Directory Verification Signals (JustDial & IndiaMart)
    jd_rating: Optional[float] = None
    jd_reviews_count: Optional[int] = None
    jd_verified: bool = False
    im_rating: Optional[float] = None
    im_verified: bool = False
    im_gst_verified: bool = False

    # Source & Orchestration Metadata
    source_platforms: List[str] = Field(default_factory=list)
    outreach_status: str = Field(default="new", pattern="^(new|contacted|followed_up|closed)$")
    recrawl_tier: Optional[str] = Field(default="tier3", pattern="^(tier1|tier2|tier3)$")
    last_checked: Optional[datetime] = None
