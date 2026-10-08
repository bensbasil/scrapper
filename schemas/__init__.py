"""
schemas
-------
Canonical Pydantic data contracts for the Business Opportunity Intelligence Platform.
Defines clean, typed contracts between Discovery, Scraping, Enrichment, Intelligence,
Intent, Opportunity Scoring, Outreach, Persistence, and future AI Agent tools.
"""

from schemas.business import Business
from schemas.enrichment import (
    BusinessEnrichment,
    ValidatedEmail,
    DecisionMakerCandidate,
)
from schemas.intelligence import (
    BusinessIntelligence,
    CompetitorComparison,
)
from schemas.intent import (
    IntentProfile,
    IntentSignal,
)
from schemas.opportunity import (
    Opportunity,
    ServiceRecommendation,
)
from schemas.outreach import OutreachDraft
from schemas.pipeline import (
    PipelineResult,
    StageExecution,
)
from schemas.context import (
    EvidenceItem,
    ScoreCard,
    ProspectContext,
)
from schemas.ai import (
    CommercialRecommendation,
    OpportunityAnalysis,
    OutreachStrategy,
    OutreachDraftResponse,
)

__all__ = [
    "Business",
    "BusinessEnrichment",
    "ValidatedEmail",
    "DecisionMakerCandidate",
    "BusinessIntelligence",
    "CompetitorComparison",
    "IntentProfile",
    "IntentSignal",
    "Opportunity",
    "ServiceRecommendation",
    "OutreachDraft",
    "PipelineResult",
    "StageExecution",
    "EvidenceItem",
    "ScoreCard",
    "ProspectContext",
    "CommercialRecommendation",
    "OpportunityAnalysis",
    "OutreachStrategy",
    "OutreachDraftResponse",
]


