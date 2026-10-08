"""
application/contracts
---------------------
Pydantic contracts for application capabilities: envelopes, inputs, and outputs.
"""

from application.contracts.base import CapabilityResult
from application.contracts.inputs import (
    DiscoverProspectsInput,
    AuditWebsiteTechInput,
    EnrichLeadershipSocialInput,
    MineBusinessIntelligenceInput,
    CalculateHealthAndScoresInput,
    AssembleProspectContextInput,
    SynthesizeOpportunityInput,
    FormulateOutreachStrategyInput,
    EvaluateAIReasoningInput,
    RenderOutreachDraftsInput,
)
from application.contracts.outputs import (
    DiscoverProspectsOutput,
    AuditWebsiteTechOutput,
    EnrichLeadershipSocialOutput,
)

__all__ = [
    "CapabilityResult",
    "DiscoverProspectsInput",
    "AuditWebsiteTechInput",
    "EnrichLeadershipSocialInput",
    "MineBusinessIntelligenceInput",
    "CalculateHealthAndScoresInput",
    "AssembleProspectContextInput",
    "SynthesizeOpportunityInput",
    "FormulateOutreachStrategyInput",
    "EvaluateAIReasoningInput",
    "RenderOutreachDraftsInput",
    "DiscoverProspectsOutput",
    "AuditWebsiteTechOutput",
    "EnrichLeadershipSocialOutput",
]
