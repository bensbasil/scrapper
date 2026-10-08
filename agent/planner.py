"""
agent/planner.py
----------------
Rule-based, deterministic planner for Agent task orchestration.
Converts high-level goals into typed Plan instances and validates
dependency graphs against circularity, missing steps, and unknown capabilities.
"""

import logging
import time
from typing import Optional, Dict, Any, List, Set
from collections import deque

from agent.models import Plan, PlanStep, StepStatus
from agent.intent import GoalInterpreter, AgentIntent, IntentType
from agent.telemetry import PlanTrace, PlanStepTrace
from application.capabilities.registry import CapabilityRegistry

logger = logging.getLogger(__name__)


class PlanValidationError(Exception):
    """Raised when a plan contains invalid dependencies or unregistered capabilities."""
    pass


class UnknownWorkflowError(Exception):
    """Raised when a user goal cannot be mapped to a known workflow pattern."""
    pass


class AgentPlanner:
    """
    Dynamic rule-based planner. Generates and validates typed execution plans from AgentIntent.
    """

    def __init__(
        self,
        registry: Optional[CapabilityRegistry] = None,
        interpreter: Optional[Any] = None
    ):
        self.registry = registry
        self.interpreter = interpreter or GoalInterpreter()
        self.last_trace: Optional[PlanTrace] = None

    def plan(
        self,
        user_goal: str,
        initial_params: Optional[Dict[str, Any]] = None
    ) -> Plan:
        """
        Translates a natural language user goal into a validated, typed Plan.
        """
        res = self.interpreter.interpret(user_goal, initial_params)
        if isinstance(res, tuple):
            intent = res[0]
        else:
            intent = res

        if intent.intent_type == IntentType.UNKNOWN:
            raise UnknownWorkflowError(f"No deterministic workflow pattern found for goal: '{user_goal}'")

        if intent.requires_clarification and intent.clarification_request:
            raise UnknownWorkflowError(f"Goal is ambiguous: {intent.clarification_request.question}")

        if intent.requires_external_action:
            raise UnknownWorkflowError("Direct external actions are unsupported and blocked by safety policy.")

        return self.plan_from_intent(intent, initial_params)

    def plan_from_intent(
        self,
        intent: AgentIntent,
        initial_params: Optional[Dict[str, Any]] = None
    ) -> Plan:
        """
        Dynamically constructs a capability execution plan based on interpreted intent requirements.
        """
        start_mono = time.monotonic()
        params = initial_params or {}
        b_name = intent.target_business or params.get("business_name", "Target Prospect")
        web_url = params.get("website_url", "")
        category = intent.industry or params.get("category", "Local Business")
        rating = params.get("rating", 4.0)
        review_count = params.get("review_count", 25)

        query = intent.search_query or (
            f"{category} in {intent.location}" if intent.location and category else (category or intent.location or "local businesses")
        )
        location = intent.location or params.get("location")
        limit = intent.constraints.get("limit") or params.get("limit", 10)

        steps: List[PlanStep] = []

        # 1. Discovery Requirement
        if intent.requires_discovery:
            steps.append(
                PlanStep(
                    step_id="step_discover",
                    capability_name="discover_prospects",
                    reason="Discover candidate businesses from directory sources matching query and location",
                    input_parameters={
                        "query": query,
                        "location": location,
                        "limit": limit
                    },
                    depends_on=[]
                )
            )
            research_deps = ["step_discover"]
        else:
            research_deps = []

        # 2. Audit-Only Shortcut
        if intent.intent_type == IntentType.AUDIT_ONLY:
            steps.append(
                PlanStep(
                    step_id="step_audit",
                    capability_name="audit_website_tech",
                    reason="Perform website and technical audit",
                    input_parameters={"business_name": b_name, "website_url": web_url or "https://example.com"},
                    depends_on=research_deps
                )
            )
            plan = Plan(
                plan_id="plan_audit_only",
                workflow_name="audit_website",
                steps=steps
            )
            duration_ms = (time.monotonic() - start_mono) * 1000.0
            self.last_trace = PlanTrace(
                plan_id=plan.plan_id,
                workflow_name=plan.workflow_name,
                step_count=len(steps),
                steps=[
                    PlanStepTrace(
                        step_id=s.step_id,
                        capability_name=s.capability_name,
                        depends_on=list(s.depends_on)
                    )
                    for s in steps
                ],
                duration_ms=duration_ms,
                validation_succeeded=True
            )
            return plan

        # 3. Research Requirements
        if intent.requires_research:
            audit_url = web_url if not intent.requires_discovery else (web_url or "")
            audit_name = b_name if not intent.requires_discovery else "Target Prospect"
            steps.extend([
                PlanStep(
                    step_id="step_audit",
                    capability_name="audit_website_tech",
                    reason="Audit website technical signals, responsiveness, and performance",
                    input_parameters={"business_name": audit_name, "website_url": audit_url or "https://example.com" if not intent.requires_discovery else ""},
                    depends_on=research_deps
                ),
                PlanStep(
                    step_id="step_enrich",
                    capability_name="enrich_leadership_social",
                    reason="Enrich decision-maker and leadership profiles",
                    input_parameters={"business_name": b_name, "website_url": web_url},
                    depends_on=research_deps
                ),
                PlanStep(
                    step_id="step_intel",
                    capability_name="mine_business_intelligence",
                    reason="Mine customer complaints and review sentiment intelligence",
                    input_parameters={
                        "business_name": b_name,
                        "category": category,
                        "website_url": web_url,
                        "rating": rating,
                        "review_count": review_count
                    },
                    depends_on=research_deps
                ),
                PlanStep(
                    step_id="step_score",
                    capability_name="calculate_health_and_scores",
                    reason="Compute deterministic digital health and sales opportunity scores",
                    input_parameters={
                        "business_name": b_name,
                        "rating": rating,
                        "review_count": review_count
                    },
                    depends_on=["step_audit", "step_intel"]
                ),
                PlanStep(
                    step_id="step_context",
                    capability_name="assemble_prospect_context",
                    reason="Assemble unified ProspectContext evidence boundary",
                    input_parameters={
                        "business_data": {
                            "business_name": b_name,
                            "website": web_url,
                            "category": category,
                            "rating": rating,
                            "review_count": review_count
                        }
                    },
                    depends_on=["step_audit", "step_enrich", "step_intel", "step_score"]
                ),
            ])

        # 4. Opportunity Reasoning Requirement
        if intent.requires_opportunity_analysis:
            steps.append(
                PlanStep(
                    step_id="step_opp",
                    capability_name="synthesize_opportunity_analysis",
                    reason="Synthesize AI commercial opportunity analysis and diagnostic recommendations",
                    input_parameters={},
                    depends_on=["step_context"]
                )
            )

        # 5. Outreach Reasoning Requirement
        if intent.requires_outreach:
            steps.append(
                PlanStep(
                    step_id="step_outreach",
                    capability_name="formulate_outreach_strategy",
                    reason="Formulate AI consultative outreach strategy and positioning",
                    input_parameters={},
                    depends_on=["step_opp"]
                )
            )

        # 6. Evaluation Gate Requirement
        if intent.requires_evaluation:
            steps.append(
                PlanStep(
                    step_id="step_eval",
                    capability_name="evaluate_ai_reasoning",
                    reason="Evaluate factual grounding and consistency of AI reasoning against context",
                    input_parameters={},
                    depends_on=["step_opp", "step_outreach"]
                )
            )

        # 7. Draft Rendering Requirement
        if intent.requires_draft:
            steps.append(
                PlanStep(
                    step_id="step_draft",
                    capability_name="render_outreach_drafts",
                    reason="Render and stage finalized cold outreach copy",
                    input_parameters={"persist_to_db": False},
                    depends_on=["step_outreach", "step_eval"]
                )
            )

        plan_id = f"plan_{intent.intent_type.value.lower()}"
        plan = Plan(
            plan_id=plan_id,
            workflow_name=intent.intent_type.value,
            steps=steps
        )
        duration_ms = (time.monotonic() - start_mono) * 1000.0
        self.last_trace = PlanTrace(
            plan_id=plan.plan_id,
            workflow_name=plan.workflow_name,
            step_count=len(steps),
            steps=[
                PlanStepTrace(
                    step_id=s.step_id,
                    capability_name=s.capability_name,
                    depends_on=list(s.depends_on)
                )
                for s in steps
            ],
            duration_ms=duration_ms,
            validation_succeeded=True
        )
        return plan

    def _build_research_and_outreach_plan(self, params: Dict[str, Any]) -> Plan:
        """
        Constructs the canonical 9-step research, reasoning, evaluation, and outreach plan.
        """
        b_name = params.get("business_name", "Target Prospect")
        web_url = params.get("website_url", "")
        category = params.get("category", "Local Business")
        rating = params.get("rating", 4.0)
        review_count = params.get("review_count", 25)

        steps = [
            PlanStep(
                step_id="step_audit",
                capability_name="audit_website_tech",
                reason="Audit website technical signals, responsiveness, and performance",
                input_parameters={"business_name": b_name, "website_url": web_url or "https://example.com"},
                depends_on=[]
            ),
            PlanStep(
                step_id="step_enrich",
                capability_name="enrich_leadership_social",
                reason="Enrich decision-maker and leadership profiles",
                input_parameters={"business_name": b_name, "website_url": web_url},
                depends_on=[]
            ),
            PlanStep(
                step_id="step_intel",
                capability_name="mine_business_intelligence",
                reason="Mine customer complaints and review sentiment intelligence",
                input_parameters={
                    "business_name": b_name,
                    "category": category,
                    "website_url": web_url,
                    "rating": rating,
                    "review_count": review_count
                },
                depends_on=[]
            ),
            PlanStep(
                step_id="step_score",
                capability_name="calculate_health_and_scores",
                reason="Compute deterministic digital health and sales opportunity scores",
                input_parameters={
                    "business_name": b_name,
                    "rating": rating,
                    "review_count": review_count
                },
                depends_on=["step_audit", "step_intel"]
            ),
            PlanStep(
                step_id="step_context",
                capability_name="assemble_prospect_context",
                reason="Assemble unified ProspectContext evidence boundary",
                input_parameters={
                    "business_data": {
                        "business_name": b_name,
                        "website": web_url,
                        "category": category,
                        "rating": rating,
                        "review_count": review_count
                    }
                },
                depends_on=["step_audit", "step_enrich", "step_intel", "step_score"]
            ),
            PlanStep(
                step_id="step_opp",
                capability_name="synthesize_opportunity_analysis",
                reason="Synthesize AI commercial opportunity analysis and diagnostic recommendations",
                input_parameters={},  # Dynamically hydrated with ProspectContext
                depends_on=["step_context"]
            ),
            PlanStep(
                step_id="step_outreach",
                capability_name="formulate_outreach_strategy",
                reason="Formulate AI consultative outreach strategy and positioning",
                input_parameters={},  # Dynamically hydrated with context & opportunity analysis
                depends_on=["step_opp"]
            ),
            PlanStep(
                step_id="step_eval",
                capability_name="evaluate_ai_reasoning",
                reason="Evaluate factual grounding and consistency of AI reasoning against context",
                input_parameters={},  # Dynamically hydrated with context, opp analysis, & outreach strategy
                depends_on=["step_opp", "step_outreach"]
            ),
            PlanStep(
                step_id="step_draft",
                capability_name="render_outreach_drafts",
                reason="Render and stage finalized cold outreach copy",
                input_parameters={"persist_to_db": False},
                depends_on=["step_outreach", "step_eval"]
            ),
        ]

        return Plan(
            plan_id="plan_research_and_outreach",
            workflow_name="research_and_outreach_opportunity",
            steps=steps
        )

    def _build_discovery_and_outreach_plan(self, params: Dict[str, Any]) -> Plan:
        """
        Constructs a plan starting from prospect discovery.
        """
        query = params.get("query", "local businesses")
        location = params.get("location")
        limit = params.get("limit", 5)

        steps = [
            PlanStep(
                step_id="step_discover",
                capability_name="discover_prospects",
                reason="Discover candidate businesses from directory sources",
                input_parameters={"query": query, "location": location, "limit": limit},
                depends_on=[]
            ),
            PlanStep(
                step_id="step_audit",
                capability_name="audit_website_tech",
                reason="Audit technical signals for discovered prospects",
                input_parameters={},
                depends_on=["step_discover"]
            ),
        ]

        return Plan(
            plan_id="plan_discovery_workflow",
            workflow_name="discovery_and_outreach",
            steps=steps
        )

    def _build_audit_only_plan(self, params: Dict[str, Any]) -> Plan:
        """
        Constructs an audit-only plan.
        """
        b_name = params.get("business_name", "Target Prospect")
        web_url = params.get("website_url", "https://example.com")

        steps = [
            PlanStep(
                step_id="step_audit",
                capability_name="audit_website_tech",
                reason="Perform website and technical audit",
                input_parameters={"business_name": b_name, "website_url": web_url},
                depends_on=[]
            )
        ]

        return Plan(
            plan_id="plan_audit_only",
            workflow_name="audit_website",
            steps=steps
        )

    def validate_plan(self, plan: Plan, registry: Optional[CapabilityRegistry] = None) -> None:
        """
        Validates the dependency graph and registered capabilities of a plan.
        Raises PlanValidationError if validation fails.
        """
        reg = registry or self.registry

        try:
            step_map: Dict[str, PlanStep] = {}
            # 1. Check for duplicate step IDs
            for step in plan.steps:
                if step.step_id in step_map:
                    raise PlanValidationError(f"Duplicate step_id '{step.step_id}' found in plan.")
                step_map[step.step_id] = step

            # 2. Check capabilities against registry if registry is provided
            if reg:
                for step in plan.steps:
                    if reg.get(step.capability_name) is None:
                        raise PlanValidationError(
                            f"Step '{step.step_id}' references unknown capability '{step.capability_name}'."
                        )

            # 3. Check for missing dependencies and self-dependencies
            for step in plan.steps:
                for dep in step.depends_on:
                    if dep == step.step_id:
                        raise PlanValidationError(f"Step '{step.step_id}' cannot depend on itself.")
                    if dep not in step_map:
                        raise PlanValidationError(
                            f"Step '{step.step_id}' depends on missing step '{dep}'."
                        )

            # 4. Circular dependency detection via Kahn's algorithm (Topological sort)
            in_degree: Dict[str, int] = {s_id: 0 for s_id in step_map}
            adj_list: Dict[str, List[str]] = {s_id: [] for s_id in step_map}

            for step in plan.steps:
                for dep in step.depends_on:
                    adj_list[dep].append(step.step_id)
                    in_degree[step.step_id] += 1

            queue = deque([s_id for s_id, deg in in_degree.items() if deg == 0])
            visited_count = 0

            while queue:
                node = queue.popleft()
                visited_count += 1
                for neighbor in adj_list[node]:
                    in_degree[neighbor] -= 1
                    if in_degree[neighbor] == 0:
                        queue.append(neighbor)

            if visited_count < len(step_map):
                cycle_steps = [s_id for s_id, deg in in_degree.items() if deg > 0]
                raise PlanValidationError(
                    f"Circular dependency detected in plan involving steps: {cycle_steps}"
                )

            if self.last_trace and self.last_trace.plan_id == plan.plan_id:
                self.last_trace.validation_succeeded = True

        except PlanValidationError as e:
            if self.last_trace and self.last_trace.plan_id == plan.plan_id:
                self.last_trace.validation_succeeded = False
                self.last_trace.validation_error = str(e)
            raise
