"""
agent/intent.py
---------------
Structured User-Goal Interpretation Layer.
Converts natural-language requests and initial parameters into a validated AgentIntent.
Identifies required capabilities, discovery needs, outreach goals, external action
boundaries, and ambiguities requiring clarification.
Pure Python + Pydantic v2 (no external LLM framework).
"""

import re
from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class IntentType(str, Enum):
    """Classified intention of the user request."""
    RESEARCH_KNOWN_BUSINESS = "RESEARCH_KNOWN_BUSINESS"
    RESEARCH_AND_OUTREACH = "RESEARCH_AND_OUTREACH"
    DISCOVER_PROSPECTS = "DISCOVER_PROSPECTS"
    DISCOVER_AND_ANALYZE = "DISCOVER_AND_ANALYZE"
    DISCOVER_AND_OUTREACH = "DISCOVER_AND_OUTREACH"
    AUDIT_ONLY = "AUDIT_ONLY"
    UNSUPPORTED_EXTERNAL_ACTION = "UNSUPPORTED_EXTERNAL_ACTION"
    AMBIGUOUS = "AMBIGUOUS"
    UNKNOWN = "UNKNOWN"


class ClarificationRequest(BaseModel):
    """
    Structured clarification request emitted when a goal lacks essential parameters.
    Halts autonomous execution safely before capabilities are dispatched.
    """
    model_config = ConfigDict(extra="ignore")

    question: str = Field(..., description="Targeted clarification question for the user")
    missing_information: List[str] = Field(
        default_factory=list,
        description="List of missing required parameters (e.g. 'location', 'industry')"
    )
    blocking: bool = Field(default=True, description="Whether execution is paused pending clarification")


class AgentIntent(BaseModel):
    """
    Typed, structured representation of the interpreted user request.
    Consumed by the dynamic planner to construct minimal, dependency-valid capability DAGs.
    """
    model_config = ConfigDict(extra="ignore")

    intent_type: IntentType = Field(..., description="Categorized user intent")
    objective: str = Field(..., description="Normalized statement of what needs to be accomplished")
    target_business: Optional[str] = Field(default=None, description="Known target business name if specified")
    target_businesses: List[str] = Field(default_factory=list, description="List of target businesses")
    location: Optional[str] = Field(default=None, description="Geographic location constraint")
    industry: Optional[str] = Field(default=None, description="Industry vertical or trade")
    search_query: Optional[str] = Field(default=None, description="Discovery search query string")
    requested_outputs: List[str] = Field(default_factory=list, description="Outputs explicitly requested")
    requested_actions: List[str] = Field(default_factory=list, description="Actions explicitly requested")
    constraints: Dict[str, Any] = Field(default_factory=dict, description="Execution constraints e.g. limit")

    # Capability Requirement Flags
    requires_discovery: bool = Field(default=False, description="Whether prospect discovery is needed")
    requires_research: bool = Field(default=False, description="Whether website audit, enrichment, scoring, and context assembly are needed")
    requires_opportunity_analysis: bool = Field(default=False, description="Whether AI opportunity reasoning is needed")
    requires_outreach: bool = Field(default=False, description="Whether consultative outreach strategy is needed")
    requires_evaluation: bool = Field(default=False, description="Whether reasoning quality evaluation is needed")
    requires_draft: bool = Field(default=False, description="Whether outreach draft rendering is needed")
    requires_external_action: bool = Field(default=False, description="Whether real-world external communication is requested")
    requires_clarification: bool = Field(default=False, description="Whether goal is ambiguous and requires user clarification")
    clarification_request: Optional[ClarificationRequest] = Field(default=None, description="Structured clarification details")

    @field_validator("intent_type", mode="before")
    @classmethod
    def normalize_intent_type(cls, v: Any) -> Any:
        """Allows case-insensitive strings to map to IntentType enum."""
        if isinstance(v, str):
            v_clean = v.strip().upper()
            for member in IntentType:
                if member.value == v_clean or member.name == v_clean:
                    return member
        return v

    @model_validator(mode="before")
    @classmethod
    def normalize_aliases(cls, data: Any) -> Any:
        """Normalizes common LLM field variations (e.g. requires_outreach_strategy)."""
        if isinstance(data, dict):
            if "requires_outreach_strategy" in data and "requires_outreach" not in data:
                data["requires_outreach"] = data["requires_outreach_strategy"]
        return data



class GoalInterpreter:
    """
    Interprets natural-language goals and initial parameters into typed AgentIntent.
    Enforces deterministic safety boundaries before planning occurs.
    """

    # Keyword patterns
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

    OUTREACH_KEYWORDS = [
        "outreach", "draft", "pitch", "message", "cold email", "whatsapp message",
        "copy", "campaign", "prepare outreach"
    ]

    RESEARCH_KEYWORDS = [
        "research", "analyze", "audit", "evaluate", "inspect", "check", "diagnose",
        "teardown", "opportunity"
    ]

    DISCOVERY_KEYWORDS = [
        "find", "discover", "search", "lookup", "prospect", "identify", "locate"
    ]

    def interpret(
        self,
        user_goal: str,
        initial_params: Optional[Dict[str, Any]] = None
    ) -> AgentIntent:
        """
        Translates raw user goal and optional parameters into an AgentIntent.
        """
        params = initial_params or {}
        goal_text = user_goal.strip()
        goal_lower = goal_text.lower()

        # Extract parameters from initial_params if present
        target_biz = params.get("business_name")
        location = params.get("location")
        industry = params.get("category") or params.get("industry")
        limit = params.get("limit")
        if limit is None:
            match_limit = re.search(r"\b(?:find|discover|analyze|inspect|audit|get)\s+(\d+)\b", goal_lower)
            limit = int(match_limit.group(1)) if match_limit else 10
        query = params.get("query")

        # 1. External Action Detection (Safety Interception)
        for pattern in self.EXTERNAL_ACTION_PATTERNS:
            if re.search(pattern, goal_lower):
                return AgentIntent(
                    intent_type=IntentType.UNSUPPORTED_EXTERNAL_ACTION,
                    objective=goal_text,
                    target_business=target_biz,
                    requires_external_action=True,
                    requested_actions=["external_communication"],
                    constraints={"unsupported_reason": "Direct external messaging/dispatching is not implemented."}
                )

        # 2. Extract entities from text if not provided in params
        if not target_biz:
            target_biz = self._extract_business_name(goal_text)

        if not location:
            location = self._extract_location(goal_text)

        if not industry:
            industry = self._extract_industry(goal_text)

        # 3. Check for Ambiguous / Underspecified Goals
        is_pure_discovery_phrase = any(
            goal_lower == phrase or goal_lower == f"{phrase}."
            for phrase in [
                "find businesses", "discover prospects", "search companies",
                "find leads", "get businesses", "find prospects", "search leads"
            ]
        )

        if is_pure_discovery_phrase and not location and not industry and not query:
            return AgentIntent(
                intent_type=IntentType.AMBIGUOUS,
                objective=goal_text,
                requires_clarification=True,
                clarification_request=ClarificationRequest(
                    question="Please specify the location and industry to discover prospects (e.g. 'Find dental clinics in Chicago').",
                    missing_information=["location", "industry"],
                    blocking=True
                )
            )

        # Missing location for a discovery request without explicit parameters
        has_discovery_word = any(re.search(rf"\b{k}\b", goal_lower) for k in self.DISCOVERY_KEYWORDS)
        if has_discovery_word and not target_biz:
            # If discovery is requested, verify if location is specified
            if not location and not query and not params.get("location"):
                # Goal mentions finding something, but lacks location
                return AgentIntent(
                    intent_type=IntentType.AMBIGUOUS,
                    objective=goal_text,
                    industry=industry,
                    requires_clarification=True,
                    clarification_request=ClarificationRequest(
                        question="Please provide a geographic location for discovery (e.g. 'Chicago' or 'Austin, TX').",
                        missing_information=["location"],
                        blocking=True
                    )
                )

        # 4. Classify Goal Categories
        has_outreach_intent = any(re.search(rf"\b{k}\b", goal_lower) for k in self.OUTREACH_KEYWORDS)
        has_research_intent = any(re.search(rf"\b{k}\b", goal_lower) for k in self.RESEARCH_KEYWORDS)

        # Category C & D: Discovery-driven
        has_plural_discovery = any(w in goal_lower for w in ["businesses", "prospects", "companies", "leads", "clinics", "dentists", "plumbers"])
        is_discovery_driven = (has_discovery_word or (has_plural_discovery and location)) and not target_biz
        if is_discovery_driven:
            search_query = query or (f"{industry} in {location}" if industry and location else (industry or location or goal_text))
            if has_outreach_intent:
                return AgentIntent(
                    intent_type=IntentType.DISCOVER_AND_OUTREACH,
                    objective=f"Discover prospects and formulate outreach drafts for {search_query}",
                    location=location,
                    industry=industry,
                    search_query=search_query,
                    constraints={"limit": limit},
                    requires_discovery=True,
                    requires_research=True,
                    requires_opportunity_analysis=True,
                    requires_outreach=True,
                    requires_evaluation=True,
                    requires_draft=True,
                )
            elif has_research_intent:
                return AgentIntent(
                    intent_type=IntentType.DISCOVER_AND_ANALYZE,
                    objective=f"Discover and analyze prospects for {search_query}",
                    location=location,
                    industry=industry,
                    search_query=search_query,
                    constraints={"limit": limit},
                    requires_discovery=True,
                    requires_research=True,
                    requires_opportunity_analysis=True,
                    requires_outreach=False,
                    requires_evaluation=False,
                    requires_draft=False,
                )
            else:
                return AgentIntent(
                    intent_type=IntentType.DISCOVER_PROSPECTS,
                    objective=f"Discover prospect businesses matching {search_query}",
                    location=location,
                    industry=industry,
                    search_query=search_query,
                    constraints={"limit": limit},
                    requires_discovery=True,
                    requires_research=False,
                    requires_opportunity_analysis=False,
                    requires_outreach=False,
                    requires_evaluation=False,
                    requires_draft=False,
                )

        # Check for completely unknown/unsupported domain goals
        if not has_research_intent and not has_discovery_word and not has_outreach_intent and not params.get("business_name"):
            return AgentIntent(
                intent_type=IntentType.UNKNOWN,
                objective=goal_text,
                constraints={"error": f"No deterministic workflow pattern found for goal: '{goal_text}'"}
            )

        # Category A & B: Known Business
        effective_target = target_biz or "Target Prospect"

        if has_outreach_intent:
            return AgentIntent(
                intent_type=IntentType.RESEARCH_AND_OUTREACH,
                objective=f"Research {effective_target} and prepare consultative outreach",
                target_business=effective_target,
                location=location,
                industry=industry,
                requires_discovery=False,
                requires_research=True,
                requires_opportunity_analysis=True,
                requires_outreach=True,
                requires_evaluation=True,
                requires_draft=True,
            )

        # Pure Audit
        if "audit" in goal_lower and not any(k in goal_lower for k in ["opportunity", "diagnose", "intelligence"]):
            return AgentIntent(
                intent_type=IntentType.AUDIT_ONLY,
                objective=f"Audit technical and website presence for {effective_target}",
                target_business=effective_target,
                location=location,
                industry=industry,
                requires_discovery=False,
                requires_research=True,
                requires_opportunity_analysis=False,
                requires_outreach=False,
                requires_evaluation=False,
                requires_draft=False,
            )

        # Research Known Business (Analysis only, no outreach)
        return AgentIntent(
            intent_type=IntentType.RESEARCH_KNOWN_BUSINESS,
            objective=f"Analyze {effective_target} commercial opportunity",
            target_business=effective_target,
            location=location,
            industry=industry,
            requires_discovery=False,
            requires_research=True,
            requires_opportunity_analysis=True,
            requires_outreach=False,
            requires_evaluation=False,
            requires_draft=False,
        )

    def _extract_business_name(self, text: str) -> Optional[str]:
        """Heuristic extractor for business names in phrases like 'Analyze ABC Tech'."""
        text_lower = text.lower()
        # If the goal is discovery-oriented, entities are discovery queries, not known businesses
        if any(re.search(rf"\b{k}\b", text_lower) for k in self.DISCOVERY_KEYWORDS):
            return None

        common_non_businesses = [
            "a business", "this business", "businesses", "prospects", "companies",
            "leads", "dentists", "plumbers", "clinics", "restaurants", "bakeries",
            "gyms", "lawyers", "contractors", "doctors", "salons"
        ]
        patterns = [
            r"(?:analyze|research|audit|inspect|check)\s+([A-Za-z0-9\s&]+?)(?:\s+and\b|\s+for\b|\s+to\b|\s+in\b|$)",
            r"(?:for|about)\s+([A-Za-z0-9\s&]+?)(?:\s+and\b|\s+in\b|$)"
        ]
        for pat in patterns:
            match = re.search(pat, text, re.IGNORECASE)
            if match:
                candidate = match.group(1).strip()
                cand_lower = candidate.lower()
                if re.match(r"^\d+\s+", cand_lower) and any(w in cand_lower for w in common_non_businesses):
                    continue
                if cand_lower not in common_non_businesses:
                    return candidate
        return None

    def _extract_location(self, text: str) -> Optional[str]:
        """Extracts location after 'in' or 'near' e.g. 'in Bangalore', 'in Austin, TX'."""
        match = re.search(r"\b(?:in|near|around)\s+([A-Za-z\s,]+?)(?:\s+that|\s+with|\s+and|$)", text, re.IGNORECASE)
        if match:
            loc = match.group(1).strip()
            if loc.lower() not in ["website development", "weak websites", "poor reviews", "a business", "outreach"]:
                return loc
        return None

    def _extract_industry(self, text: str) -> Optional[str]:
        """Extracts common trade or vertical keywords."""
        trades = [
            "plumbing", "plumber", "dentist", "dental", "bakery", "restaurant",
            "gym", "fitness", "legal", "lawyer", "clinic", "salon", "software",
            "technology", "roofing", "hvac", "mechanic"
        ]
        text_lower = text.lower()
        for trade in trades:
            if trade in text_lower:
                return trade.capitalize()
        return None
