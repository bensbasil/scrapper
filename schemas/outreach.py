from typing import Optional, List
from pydantic import BaseModel, ConfigDict, Field


class OutreachDraft(BaseModel):
    """
    Generated personalized sales communication drafts.
    Contains cold email, WhatsApp pitch copy, identified outreach angles,
    and the structured audit summary used for positioning.
    """
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    business_name: str
    decision_maker_name: Optional[str] = None

    # Positioning & Angles
    outreach_angles: List[str] = Field(default_factory=list)
    pain_point_positioning: Optional[str] = None
    concise_audit_summary: Optional[str] = None

    # Draft Messages
    cold_email_draft: Optional[str] = None
    whatsapp_draft: Optional[str] = None

    # Generation Context
    ai_prompt_template: Optional[str] = None
    generation_mode: str = Field(default="template", pattern="^(gemini|openai|template)$")
