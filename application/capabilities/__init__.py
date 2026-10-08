"""
application/capabilities
------------------------
Exposes typed application capability tool classes and central registry.
"""

from application.capabilities.discovery import DiscoverProspectsCapability
from application.capabilities.website_audit import AuditWebsiteTechCapability
from application.capabilities.enrichment import EnrichLeadershipSocialCapability
from application.capabilities.intelligence import MineBusinessIntelligenceCapability
from application.capabilities.scoring import CalculateHealthAndScoresCapability
from application.capabilities.context import AssembleProspectContextCapability
from application.capabilities.opportunity import SynthesizeOpportunityAnalysisCapability
from application.capabilities.outreach import (
    FormulateOutreachStrategyCapability,
    RenderOutreachDraftsCapability,
)
from application.capabilities.evaluation import EvaluateAIReasoningCapability
from application.capabilities.registry import (
    CapabilityDescriptor,
    CapabilityRegistry,
)

__all__ = [
    "DiscoverProspectsCapability",
    "AuditWebsiteTechCapability",
    "EnrichLeadershipSocialCapability",
    "MineBusinessIntelligenceCapability",
    "CalculateHealthAndScoresCapability",
    "AssembleProspectContextCapability",
    "SynthesizeOpportunityAnalysisCapability",
    "FormulateOutreachStrategyCapability",
    "RenderOutreachDraftsCapability",
    "EvaluateAIReasoningCapability",
    "CapabilityDescriptor",
    "CapabilityRegistry",
]
