"""
application/capabilities/registry.py
------------------------------------
Capability registry and discovery boundary for the Agent.
Maintains registered application capabilities, their safety policies,
and typed input/output schemas.
"""

import time
import logging
from typing import Dict, Any, Optional, List, Type, Callable
from pydantic import BaseModel, ConfigDict, Field

from application.policies.classification import PolicyClass
from application.contracts.base import CapabilityResult

# Import all capabilities
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

logger = logging.getLogger(__name__)


class CapabilityDescriptor(BaseModel):
    """
    Metadata representation of an application capability tool for Agent inspection.
    """
    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str = Field(..., description="Stable unique identifier for the capability")
    description: str = Field(..., description="Human- and LLM-readable description of what this capability does")
    policy_class: PolicyClass = Field(..., description="Safety classification: READ, WRITE, or EXTERNAL_ACTION")
    input_schema: Type[BaseModel] = Field(..., description="Pydantic class for input validation")
    output_schema: Type[BaseModel] = Field(..., description="Pydantic class for output validation")


class CapabilityRegistry:
    """
    Central discovery and dispatch registry for application capabilities.
    Does NOT execute capabilities automatically in autonomous loops.
    Acts as the controlled boundary between the Agent and platform services.
    """

    def __init__(self):
        self._capabilities: Dict[str, Any] = {}
        self._descriptors: Dict[str, CapabilityDescriptor] = {}

    def register(
        self,
        capability: Any,
        input_schema: Type[BaseModel],
        output_schema: Type[BaseModel]
    ) -> None:
        """
        Registers a capability instance into the registry.
        """
        name = getattr(capability, "NAME", capability.__class__.__name__)
        desc = getattr(capability, "DESCRIPTION", capability.__doc__ or "Application capability")
        policy = getattr(capability, "POLICY_CLASS", PolicyClass.READ)

        descriptor = CapabilityDescriptor(
            name=name,
            description=desc,
            policy_class=policy,
            input_schema=input_schema,
            output_schema=output_schema
        )

        self._capabilities[name] = capability
        self._descriptors[name] = descriptor
        logger.debug(f"[CapabilityRegistry] Registered '{name}' ({policy.value})")

    def get(self, name: str) -> Optional[CapabilityDescriptor]:
        """
        Retrieves capability metadata descriptor by name.
        """
        return self._descriptors.get(name)

    def get_capability(self, name: str) -> Optional[Any]:
        """
        Retrieves the underlying capability instance.
        """
        return self._capabilities.get(name)

    def list_capabilities(self) -> List[CapabilityDescriptor]:
        """
        Returns all registered capability descriptors.
        """
        return list(self._descriptors.values())

    def execute(self, name: str, params: Any) -> CapabilityResult[Any]:
        """
        Validates input parameters, invokes the capability, and returns a typed CapabilityResult.
        """
        descriptor = self.get(name)
        capability = self.get_capability(name)

        if not descriptor or not capability:
            return CapabilityResult(
                success=False,
                capability_name=name,
                error=f"Capability '{name}' is not registered.",
                metadata={"status": "not_found"}
            )

        start_time = time.time()
        try:
            # Validate input if passed as dict
            if isinstance(params, dict):
                validated_params = descriptor.input_schema.model_validate(params)
            elif isinstance(params, descriptor.input_schema):
                validated_params = params
            else:
                validated_params = descriptor.input_schema.model_validate(params)

            # Execute capability
            raw_output = capability.execute(validated_params)
            duration_ms = (time.time() - start_time) * 1000.0

            return CapabilityResult(
                success=True,
                capability_name=name,
                data=raw_output,
                metadata={
                    "duration_ms": round(duration_ms, 2),
                    "policy_class": descriptor.policy_class.value
                }
            )
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000.0
            logger.error(f"[CapabilityRegistry] Execution error in '{name}': {e}", exc_info=True)
            return CapabilityResult(
                success=False,
                capability_name=name,
                error=str(e),
                metadata={
                    "duration_ms": round(duration_ms, 2),
                    "policy_class": descriptor.policy_class.value
                }
            )

    @classmethod
    def default_registry(cls) -> "CapabilityRegistry":
        """
        Constructs and returns the canonical registry with all 10 standard capabilities pre-registered.
        """
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
        from schemas.intelligence import BusinessIntelligence
        from schemas.context import ScoreCard, ProspectContext
        from schemas.ai import OpportunityAnalysis, OutreachStrategy
        from schemas.outreach import OutreachDraft
        from evaluation.models import EvaluationResult

        registry = cls()

        # 1. discover_prospects
        registry.register(DiscoverProspectsCapability(), DiscoverProspectsInput, DiscoverProspectsOutput)
        # 2. audit_website_tech
        registry.register(AuditWebsiteTechCapability(), AuditWebsiteTechInput, AuditWebsiteTechOutput)
        # 3. enrich_leadership_social
        registry.register(EnrichLeadershipSocialCapability(), EnrichLeadershipSocialInput, EnrichLeadershipSocialOutput)
        # 4. mine_business_intelligence
        registry.register(MineBusinessIntelligenceCapability(), MineBusinessIntelligenceInput, BusinessIntelligence)
        # 5. calculate_health_and_scores
        registry.register(CalculateHealthAndScoresCapability(), CalculateHealthAndScoresInput, ScoreCard)
        # 6. assemble_prospect_context
        registry.register(AssembleProspectContextCapability(), AssembleProspectContextInput, ProspectContext)
        # 7. synthesize_opportunity_analysis
        registry.register(SynthesizeOpportunityAnalysisCapability(), SynthesizeOpportunityInput, OpportunityAnalysis)
        # 8. formulate_outreach_strategy
        registry.register(FormulateOutreachStrategyCapability(), FormulateOutreachStrategyInput, OutreachStrategy)
        # 9. evaluate_ai_reasoning
        registry.register(EvaluateAIReasoningCapability(), EvaluateAIReasoningInput, EvaluationResult)
        # 10. render_outreach_drafts
        registry.register(RenderOutreachDraftsCapability(), RenderOutreachDraftsInput, OutreachDraft)

        return registry
