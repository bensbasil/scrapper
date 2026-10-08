"""
application/capabilities/outreach.py
------------------------------------
Typed application capabilities for consultative outreach reasoning and copy drafting.
Provides FormulateOutreachStrategyCapability and RenderOutreachDraftsCapability.
"""

import logging
from typing import Optional, Any
from dataclasses import asdict

from schemas.ai import OutreachStrategy
from schemas.outreach import OutreachDraft
from ai.outreach_reasoner import OutreachReasoner
from analyzer.outreach_generator import OutreachGenerator
from application.contracts.inputs import FormulateOutreachStrategyInput, RenderOutreachDraftsInput
from application.policies.classification import PolicyClass

logger = logging.getLogger(__name__)


class FormulateOutreachStrategyCapability:
    """
    Formulates consultative positioning angles, objection handling, and messaging copy strategy.
    Classified as READ: strategic planning without persistent mutations.
    """
    NAME = "formulate_outreach_strategy"
    DESCRIPTION = "Synthesizes consultative outreach strategy, angles, and objection handling from ProspectContext"
    POLICY_CLASS = PolicyClass.READ

    def __init__(self, reasoner: Optional[OutreachReasoner] = None):
        self._reasoner = reasoner or OutreachReasoner()

    def execute(self, params: FormulateOutreachStrategyInput) -> OutreachStrategy:
        """
        Executes outreach strategy reasoning on ProspectContext and OpportunityAnalysis.
        """
        b_name = params.context.business.business_name
        logger.info(f"[Capability:{self.NAME}] Formulating outreach strategy for '{b_name}'")

        strategy = self._reasoner.reason(
            context=params.context,
            opportunity_analysis=params.opportunity_analysis
        )
        params.context.outreach_strategy = strategy
        return strategy


class RenderOutreachDraftsCapability:
    """
    Renders finalized personalized cold email and WhatsApp messaging drafts.
    Classified as WRITE: stages/persists an outreach communication artifact in the database.
    Does NOT dispatch or transmit any messages externally.
    """
    NAME = "render_outreach_drafts"
    DESCRIPTION = "Renders finalized cold email and WhatsApp outreach copy, staging artifacts internally"
    POLICY_CLASS = PolicyClass.WRITE

    def __init__(self, generator: Optional[OutreachGenerator] = None, repo: Optional[Any] = None):
        self._generator = generator or OutreachGenerator()
        self._repo = repo

    def execute(self, params: RenderOutreachDraftsInput) -> OutreachDraft:
        """
        Generates personalized messaging drafts and optionally stages them to database.
        """
        context = params.context
        b_name = context.business.business_name
        logger.info(f"[Capability:{self.NAME}] Rendering outreach drafts for '{b_name}'")

        strategy = params.outreach_strategy or getattr(context, "outreach_strategy", None)
        opp_analysis = getattr(context, "opportunity_analysis", None)

        score_dict = {
            "business_name": b_name,
            "opportunity_score": context.scores.sales_opportunity_score,
            "likely_service_match": [strategy.recommended_service] if strategy and strategy.recommended_service else [],
            "detected_pain_points": [strategy.strongest_pain_point] if strategy and strategy.strongest_pain_point else []
        }

        analysis_dict = {
            "business_name": b_name,
            "category": context.business.category or "Local Business",
            "decision_maker_name": context.enrichment.decision_maker_name if context.enrichment else None,
            "opportunity_reasoning": opp_analysis.executive_diagnosis if opp_analysis else None
        }

        drafts_obj = self._generator.generate_outreach(
            score_data=score_dict,
            analysis_data=analysis_dict,
            prospect_context=context,
            outreach_strategy=strategy
        )

        d_dict = asdict(drafts_obj) if hasattr(drafts_obj, "__dataclass_fields__") else dict(drafts_obj)

        # Optionally stage to PostgreSQL database if requested and repo is available
        if params.persist_to_db and self._repo is not None and params.business_id:
            try:
                self._repo.insert_outreach_draft(params.business_id, d_dict)
                logger.info(f"[Capability:{self.NAME}] Staged outreach draft to DB for business_id={params.business_id}")
            except Exception as e:
                logger.warning(f"[Capability:{self.NAME}] Failed to persist draft to DB: {e}")

        return OutreachDraft(
            business_name=b_name,
            decision_maker_name=analysis_dict.get("decision_maker_name"),
            outreach_angles=d_dict.get("outreach_angles", []),
            pain_point_positioning=d_dict.get("pain_point_positioning"),
            concise_audit_summary=d_dict.get("concise_audit_summary"),
            cold_email_draft=d_dict.get("cold_email_draft"),
            whatsapp_draft=d_dict.get("whatsapp_draft"),
            ai_prompt_template=d_dict.get("ai_prompt_template"),
            generation_mode="openai" if "ai" in str(d_dict.get("generation_mode", "")) else "template"
        )
