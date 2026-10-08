"""
agent/llm_intent.py
-------------------
LLM-Powered Intent Interpretation Layer (Phase 3E).
Converts natural-language user goals into structured AgentIntent using provider-independent LLMClient.
Enforces strict deterministic validation, automatic fallback to GoalInterpreter on failure or unavailability,
and guarantees that the LLM cannot plan, select capabilities, execute tools, or bypass safety policies.
"""

import logging
import re
import time
from typing import Optional, Dict, Any, Tuple

from ai.client import LLMClient
from ai.exceptions import (
    LLMError,
    LLMUnavailableError,
    LLMProviderError,
    LLMResponseParsingError,
    LLMValidationError,
)
from agent.intent import (
    AgentIntent,
    IntentType,
    ClarificationRequest,
    GoalInterpreter,
)
from agent.telemetry import IntentTrace

logger = logging.getLogger(__name__)


class IntentValidationError(Exception):
    """Raised when structured LLM output fails deterministic intent validation."""
    pass


class DeterministicIntentValidator:
    """
    Deterministic validation layer for interpreted AgentIntent.
    Ensures that LLM outputs conform to domain safety, consistency, and completeness rules
    BEFORE passing to AgentPlanner.
    """

    EXTERNAL_ACTION_PATTERNS = [
        r"\bsend\s+email\b",
        r"\bsend\s+whatsapp\b",
        r"\bdispatch\b",
        r"\bblast\b",
        r"\bbroadcast\b",
        r"\bmessage\s+to\b",
        r"\bdeliver\s+messages?\b",
        r"\bpush\s+to\s+crm\b",
    ]

    def validate(
        self,
        intent: AgentIntent,
        user_goal: str,
        initial_params: Optional[Dict[str, Any]] = None,
    ) -> AgentIntent:
        """
        Validates and sanitizes AgentIntent.
        Raises IntentValidationError on irrecoverable semantic errors or contradictions.
        """
        params = initial_params or {}
        goal_text = user_goal.strip()
        goal_lower = goal_text.lower()

        # 1. Objective sanity
        if not intent.objective or not intent.objective.strip():
            intent.objective = goal_text

        # 2. Hard Security Override: External Action Detection
        # Never allow an LLM to disguise an external dispatch request as a read/research action.
        has_external_keyword = any(re.search(pat, goal_lower) for pat in self.EXTERNAL_ACTION_PATTERNS)
        if has_external_keyword or intent.requires_external_action:
            intent.requires_external_action = True
            intent.intent_type = IntentType.UNSUPPORTED_EXTERNAL_ACTION
            # Turn off all execution flags so no capabilities can be planned
            intent.requires_discovery = False
            intent.requires_research = False
            intent.requires_opportunity_analysis = False
            intent.requires_outreach = False
            intent.requires_evaluation = False
            intent.requires_draft = False
            intent.constraints["unsupported_reason"] = "Direct external messaging/dispatching is blocked by safety policy."
            return intent

        # 3. Ambiguity & Missing Information Check
        if intent.intent_type == IntentType.AMBIGUOUS or intent.requires_clarification:
            intent.requires_clarification = True
            if not intent.clarification_request:
                intent.clarification_request = ClarificationRequest(
                    question="Please provide additional details (e.g. location or industry) to clarify your goal.",
                    missing_information=["details"],
                    blocking=True,
                )
            # Turn off execution flags
            intent.requires_discovery = False
            intent.requires_research = False
            intent.requires_opportunity_analysis = False
            intent.requires_outreach = False
            intent.requires_evaluation = False
            intent.requires_draft = False
            return intent

        # If discovery is required, verify location/search criteria
        if intent.requires_discovery:
            effective_loc = intent.location or params.get("location")
            effective_query = intent.search_query or params.get("query")
            effective_biz = intent.target_business or params.get("business_name")

            # Check if discovery is requested with no location, no search query, and no biz
            if not effective_loc and not effective_query and not effective_biz:
                intent.intent_type = IntentType.AMBIGUOUS
                intent.requires_clarification = True
                intent.clarification_request = ClarificationRequest(
                    question="Please provide a geographic location for discovery (e.g. 'Chicago' or 'Bangalore').",
                    missing_information=["location"],
                    blocking=True,
                )
                intent.requires_discovery = False
                intent.requires_research = False
                intent.requires_opportunity_analysis = False
                intent.requires_outreach = False
                intent.requires_evaluation = False
                intent.requires_draft = False
                return intent

        # 4. Known Business Entity Validation
        if intent.intent_type in [
            IntentType.RESEARCH_KNOWN_BUSINESS,
            IntentType.RESEARCH_AND_OUTREACH,
            IntentType.AUDIT_ONLY,
        ]:
            if not intent.target_business:
                biz = params.get("business_name")
                if biz:
                    intent.target_business = biz
                else:
                    # Attempt heuristic extraction from goal text
                    extracted = GoalInterpreter()._extract_business_name(goal_text)
                    if extracted:
                        intent.target_business = extracted
                    else:
                        intent.intent_type = IntentType.AMBIGUOUS
                        intent.requires_clarification = True
                        intent.clarification_request = ClarificationRequest(
                            question="Please specify the business name you would like to analyze.",
                            missing_information=["target_business"],
                            blocking=True,
                        )
                        intent.requires_research = False
                        intent.requires_opportunity_analysis = False
                        intent.requires_outreach = False
                        intent.requires_evaluation = False
                        intent.requires_draft = False
                        return intent

        # 5. Semantic Contradiction / Consistency Checks
        if intent.requires_draft and not intent.requires_outreach:
            raise IntentValidationError("Contradictory intent: requires_draft=True but requires_outreach=False")

        if intent.requires_outreach and not intent.requires_opportunity_analysis:
            raise IntentValidationError("Contradictory intent: requires_outreach=True but requires_opportunity_analysis=False")

        if intent.requires_opportunity_analysis and not intent.requires_research:
            raise IntentValidationError("Contradictory intent: requires_opportunity_analysis=True but requires_research=False")

        if intent.intent_type == IntentType.DISCOVER_PROSPECTS:
            if intent.requires_research or intent.requires_outreach or intent.requires_draft:
                raise IntentValidationError("Contradictory intent: DISCOVER_PROSPECTS cannot have research or outreach flags")

        if intent.intent_type == IntentType.AUDIT_ONLY:
            if intent.requires_opportunity_analysis or intent.requires_outreach or intent.requires_draft:
                raise IntentValidationError("Contradictory intent: AUDIT_ONLY cannot have opportunity or outreach flags")

        if intent.requires_draft and not intent.requires_evaluation:
            intent.requires_evaluation = True

        return intent


class LLMIntentInterpreter:
    """
    LLM-powered goal interpreter with deterministic fallback.
    Calls LLMClient to convert natural language into structured AgentIntent.
    Enforces deterministic validation and falls back to GoalInterpreter on any failure.
    """

    SYSTEM_PROMPT = (
        "You are the Goal Interpretation Engine for the Business Opportunity Intelligence Platform.\n"
        "Your ONLY role is to translate user natural-language requests into a structured AgentIntent JSON object.\n\n"
        "Supported Intent Types:\n"
        "- RESEARCH_KNOWN_BUSINESS: Technical audit and opportunity analysis of a known business.\n"
        "- RESEARCH_AND_OUTREACH: Technical audit, opportunity analysis, and personalized outreach drafts for a known business.\n"
        "- DISCOVER_PROSPECTS: Finding/discovering candidate businesses in an area/industry without deep analysis.\n"
        "- DISCOVER_AND_ANALYZE: Finding candidate businesses AND performing technical/opportunity analysis.\n"
        "- DISCOVER_AND_OUTREACH: Finding candidate businesses, analyzing them, AND preparing personalized outreach drafts.\n"
        "- AUDIT_ONLY: Only website/technical audit of a known business.\n"
        "- UNSUPPORTED_EXTERNAL_ACTION: Request asks to send emails, send WhatsApp, dispatch messages, or push to external CRM.\n"
        "- AMBIGUOUS: Goal lacks essential criteria (e.g. discovery with no location or industry).\n"
        "- UNKNOWN: Goal is outside the platform's domain.\n\n"
        "Rules:\n"
        "1. Do NOT select tools, capabilities, execution steps, Python functions, or SQL.\n"
        "2. Only extract intent_type, entities (target_business, location, industry, search_query), and requirement flags.\n"
        "3. Requirement flags: requires_discovery, requires_research, requires_opportunity_analysis, requires_outreach, requires_evaluation, requires_draft, requires_external_action, requires_clarification.\n"
        "4. Output MUST be valid JSON adhering strictly to the AgentIntent schema."
    )

    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        fallback_interpreter: Optional[GoalInterpreter] = None,
        validator: Optional[DeterministicIntentValidator] = None,
    ):
        self.llm_client = llm_client or LLMClient()
        self.fallback_interpreter = fallback_interpreter or GoalInterpreter()
        self.validator = validator or DeterministicIntentValidator()
        self.last_trace: Optional[IntentTrace] = None

    def interpret(
        self,
        user_goal: str,
        initial_params: Optional[Dict[str, Any]] = None,
    ) -> Tuple[AgentIntent, str]:
        """
        Translates a natural-language user goal into a validated AgentIntent.
        Returns a tuple of (AgentIntent, intent_source).
        intent_source is one of: 'llm', 'deterministic_fallback', 'failed'.
        """
        params = initial_params or {}
        start_mono = time.monotonic()

        # If LLMClient is not configured or unavailable, immediately use deterministic fallback
        if not self.llm_client.is_available:
            logger.info("[LLMIntentInterpreter] LLMClient is unavailable; using deterministic fallback.")
            fallback_intent = self.fallback_interpreter.interpret(user_goal, params)
            duration_ms = (time.monotonic() - start_mono) * 1000.0
            self.last_trace = IntentTrace(
                intent_source="deterministic_fallback",
                intent_type=fallback_intent.intent_type.value if fallback_intent.intent_type else None,
                validation_succeeded=True,
                clarification_required=fallback_intent.requires_clarification,
                external_action_detected=fallback_intent.requires_external_action,
                duration_ms=duration_ms,
                fallback_used=True,
            )
            return fallback_intent, "deterministic_fallback"

        prompt = (
            f"User Goal: \"{user_goal}\"\n"
            f"Initial Parameters: {params}\n\n"
            "Interpret the user's goal into a structured AgentIntent JSON object."
        )

        provider = getattr(self.llm_client.config, "provider", None) if getattr(self.llm_client, "config", None) else None
        model = getattr(self.llm_client.config, "model", None) if getattr(self.llm_client, "config", None) else None

        try:
            # 1. Call LLM for structured output
            raw_intent = self.llm_client.generate_structured(
                prompt=prompt,
                response_model=AgentIntent,
                system_prompt=self.SYSTEM_PROMPT,
            )

            # 2. Deterministic Validation
            validated_intent = self.validator.validate(raw_intent, user_goal, params)
            duration_ms = (time.monotonic() - start_mono) * 1000.0
            self.last_trace = IntentTrace(
                intent_source="llm",
                intent_type=validated_intent.intent_type.value if validated_intent.intent_type else None,
                validation_succeeded=True,
                clarification_required=validated_intent.requires_clarification,
                external_action_detected=validated_intent.requires_external_action,
                duration_ms=duration_ms,
                fallback_used=False,
                provider=provider,
                model=model,
            )
            return validated_intent, "llm"

        except Exception as e:
            logger.warning(
                f"[LLMIntentInterpreter] LLM interpretation or validation failed: {e}. "
                "Falling back to deterministic GoalInterpreter."
            )
            try:
                fallback_intent = self.fallback_interpreter.interpret(user_goal, params)
                duration_ms = (time.monotonic() - start_mono) * 1000.0
                self.last_trace = IntentTrace(
                    intent_source="deterministic_fallback",
                    intent_type=fallback_intent.intent_type.value if fallback_intent.intent_type else None,
                    validation_succeeded=True,
                    clarification_required=fallback_intent.requires_clarification,
                    external_action_detected=fallback_intent.requires_external_action,
                    duration_ms=duration_ms,
                    fallback_used=True,
                    provider=provider,
                    model=model,
                    error=str(e),
                )
                return fallback_intent, "deterministic_fallback"
            except Exception as fallback_err:
                duration_ms = (time.monotonic() - start_mono) * 1000.0
                logger.error(
                    f"[LLMIntentInterpreter] Deterministic fallback also failed: {fallback_err}"
                )
                failed_intent = AgentIntent(
                    intent_type=IntentType.UNKNOWN,
                    objective=user_goal,
                    constraints={
                        "error": f"Complete interpretation failure: LLM ({e}), Fallback ({fallback_err})"
                    },
                )
                self.last_trace = IntentTrace(
                    intent_source="failed",
                    intent_type=IntentType.UNKNOWN.value,
                    validation_succeeded=False,
                    clarification_required=False,
                    external_action_detected=False,
                    duration_ms=duration_ms,
                    fallback_used=True,
                    provider=provider,
                    model=model,
                    error=f"LLM ({e}), Fallback ({fallback_err})",
                )
                return failed_intent, "failed"
