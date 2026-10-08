"""
ai package
----------
AI / LLM Intelligence Layer foundation for the Business Opportunity Intelligence Platform.
Provides provider-independent structured LLM access and context assembly.
"""

from ai.context_builder import ProspectContextBuilder
from ai.opportunity_reasoner import OpportunityReasoner
from ai.outreach_reasoner import OutreachReasoner
from ai.config import LLMConfig
from ai.client import LLMClient
from ai.exceptions import (
    LLMError,
    LLMUnavailableError,
    LLMProviderError,
    LLMResponseParsingError,
    LLMValidationError,
)

__all__ = [
    "ProspectContextBuilder",
    "OpportunityReasoner",
    "OutreachReasoner",
    "LLMConfig",
    "LLMClient",
    "LLMError",
    "LLMUnavailableError",
    "LLMProviderError",
    "LLMResponseParsingError",
    "LLMValidationError",
]
