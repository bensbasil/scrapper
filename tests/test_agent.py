"""
tests/test_agent.py
-------------------
Unit test suite for Phase 3C Agent Core & Controlled Orchestration.
Validates:
1. Planning (valid plan, unknown workflow, dependency validation, circular cycles)
2. Execution (registry dispatch, ordering, state population, failure cascade, unknown cap, policy rejection, safety limit)
3. State (valid transitions, illegal transitions, completed status, failed status)
4. Evaluation (passing gate continues, failing gate halts safely)
5. Safety (no infrastructure bypass, no registry bypass, external action gating)
"""

import unittest
from unittest.mock import MagicMock, patch
from typing import Dict, Any

from agent.models import (
    AgentStatus,
    StepStatus,
    ApprovalStatus,
    Plan,
    PlanStep,
    ExecutionRecord,
    ApprovalRequest,
    AgentFinalResponse,
)
from agent.state import AgentState, InvalidStateTransitionError
from agent.planner import AgentPlanner, PlanValidationError, UnknownWorkflowError
from agent.executor import AgentExecutor
from agent.policies import PolicyEnforcer, ExecutionPolicyConfig, PolicyViolationError
from agent.agent import Agent
from application.capabilities.registry import CapabilityRegistry, CapabilityDescriptor
from application.policies.classification import PolicyClass
from application.contracts.base import CapabilityResult

from schemas.context import ProspectContext, ScoreCard
from schemas.business import Business
from schemas.ai import OpportunityAnalysis, CommercialRecommendation, OutreachStrategy
from schemas.outreach import OutreachDraft
from evaluation.models import EvaluationResult
from evaluation.datasets.fixtures import get_strong_evidence_good_reasoning_fixture
from application.contracts.outputs import DiscoverProspectsOutput
from agent.intent import AgentIntent, IntentType, ClarificationRequest, GoalInterpreter
from agent.llm_intent import (
    LLMIntentInterpreter,
    DeterministicIntentValidator,
    IntentValidationError,
)
from ai.exceptions import (
    LLMUnavailableError,
    LLMProviderError,
    LLMResponseParsingError,
    LLMValidationError,
)
from ai.client import LLMClient
from pydantic import BaseModel, ConfigDict


class DummySchema(BaseModel):
    model_config = ConfigDict(extra="allow")


def create_sample_context() -> ProspectContext:
    fixture = get_strong_evidence_good_reasoning_fixture()
    return fixture["context"]


def create_sample_opportunity() -> OpportunityAnalysis:
    fixture = get_strong_evidence_good_reasoning_fixture()
    return fixture["opportunity_analysis"]


def create_sample_outreach() -> OutreachStrategy:
    fixture = get_strong_evidence_good_reasoning_fixture()
    return fixture["outreach_strategy"]





def create_sample_evaluation(passed: bool = True) -> EvaluationResult:
    return EvaluationResult(
        overall_score=0.88 if passed else 0.45,
        grounding_score=0.90 if passed else 0.40,
        relevance_score=0.85 if passed else 0.50,
        consistency_score=0.90 if passed else 0.45,
        evidence_coverage_score=0.85 if passed else 0.40,
        passed=passed,
        issues=[] if passed else ["Severe hallucination: unsupported claim regarding BBB rating"]
    )


def create_sample_draft() -> OutreachDraft:
    return OutreachDraft(
        business_name="Acme Plumbing",
        email_subject="Quick question",
        email_body="Draft cold email body",
        whatsapp_message="Draft whatsapp body"
    )


class TestAgentPlanning(unittest.TestCase):
    """Tests 1-4: Planning logic and dependency graph validation."""

    def setUp(self):
        self.registry = CapabilityRegistry.default_registry()
        self.planner = AgentPlanner(registry=self.registry)

    def test_01_valid_goal_produces_valid_plan(self):
        """1. Valid goal produces valid plan with structured dependencies."""
        goal = "Research a business and prepare an outreach opportunity"
        plan = self.planner.plan(goal, initial_params={"business_name": "Acme Plumbing"})
        self.assertIsInstance(plan, Plan)
        self.assertGreater(len(plan.steps), 0)
        # Verify planner validation succeeds
        self.planner.validate_plan(plan)
        # Check dependencies: assemble_prospect_context must depend on scoring
        ctx_step = plan.get_step("step_context")
        self.assertIsNotNone(ctx_step)
        self.assertIn("step_score", ctx_step.depends_on)

    def test_02_unknown_workflow_fails_safely(self):
        """2. Unknown workflow fails safely with UnknownWorkflowError."""
        with self.assertRaises(UnknownWorkflowError):
            self.planner.plan("Fly an autonomous drone across the ocean")

    def test_03_dependency_validation_works(self):
        """3. Missing step dependency is detected and raises PlanValidationError."""
        invalid_plan = Plan(
            plan_id="test_missing_dep",
            steps=[
                PlanStep(
                    step_id="step_1",
                    capability_name="audit_website_tech",
                    depends_on=["non_existent_step_99"]
                )
            ]
        )
        with self.assertRaises(PlanValidationError) as ctx:
            self.planner.validate_plan(invalid_plan)
        self.assertIn("missing step 'non_existent_step_99'", str(ctx.exception))

    def test_04_circular_dependency_is_detected(self):
        """4. Circular dependencies are detected and raise PlanValidationError."""
        cyclic_plan = Plan(
            plan_id="test_cycle",
            steps=[
                PlanStep(
                    step_id="step_a",
                    capability_name="audit_website_tech",
                    depends_on=["step_b"]
                ),
                PlanStep(
                    step_id="step_b",
                    capability_name="calculate_health_and_scores",
                    depends_on=["step_a"]
                ),
            ]
        )
        with self.assertRaises(PlanValidationError) as ctx:
            self.planner.validate_plan(cyclic_plan)
        self.assertIn("Circular dependency detected", str(ctx.exception))


class TestAgentExecution(unittest.TestCase):
    """Tests 5-11: Controlled capability execution and safety limits."""

    def setUp(self):
        self.registry = MagicMock(spec=CapabilityRegistry)
        self.policy_enforcer = PolicyEnforcer()
        self.executor = AgentExecutor(
            registry=self.registry,
            policy_enforcer=self.policy_enforcer,
            max_executions=15
        )

    def test_05_capabilities_execute_through_registry(self):
        """5. Capabilities execute strictly through CapabilityRegistry.execute()."""
        descriptor = CapabilityDescriptor(
            name="audit_website_tech",
            description="Audit website",
            policy_class=PolicyClass.READ,
            input_schema=DummySchema,
            output_schema=DummySchema
        )
        self.registry.get.return_value = descriptor
        self.registry.execute.return_value = CapabilityResult(
            success=True,
            capability_name="audit_website_tech",
            data={"status": "ok"}
        )

        state = AgentState(
            task_id="task_01",
            user_goal="Audit",
            status=AgentStatus.EXECUTING,
            plan=Plan(
                steps=[
                    PlanStep(
                        step_id="step_1",
                        capability_name="audit_website_tech",
                        depends_on=[]
                    )
                ]
            )
        )
        self.executor.run(state)
        self.registry.execute.assert_called_once()
        self.assertEqual(state.status, AgentStatus.COMPLETED)

    def test_06_correct_dependency_ordering(self):
        """6. Steps execute strictly in topological dependency order."""
        execution_order = []

        def mock_execute(cap_name, params):
            execution_order.append(cap_name)
            return CapabilityResult(success=True, capability_name=cap_name, data={})

        def mock_get(name):
            return CapabilityDescriptor(
                name=name,
                description=name,
                policy_class=PolicyClass.READ,
                input_schema=DummySchema,
                output_schema=DummySchema
            )

        self.registry.get.side_effect = mock_get
        self.registry.execute.side_effect = mock_execute

        state = AgentState(
            task_id="task_order",
            user_goal="Order test",
            status=AgentStatus.EXECUTING,
            plan=Plan(
                steps=[
                    PlanStep(step_id="step_2", capability_name="step_second", depends_on=["step_1"]),
                    PlanStep(step_id="step_1", capability_name="step_first", depends_on=[]),
                ]
            )
        )
        self.executor.run(state)
        self.assertEqual(execution_order, ["step_first", "step_second"])

    def test_07_capability_outputs_populate_agent_state(self):
        """7. Typed capability outputs populate state attributes directly."""
        sample_ctx = create_sample_context()
        sample_opp = create_sample_opportunity()

        def mock_get(name):
            return CapabilityDescriptor(
                name=name,
                description=name,
                policy_class=PolicyClass.READ,
                input_schema=DummySchema,
                output_schema=DummySchema
            )

        def mock_execute(name, params):
            if name == "assemble_prospect_context":
                return CapabilityResult(success=True, capability_name=name, data=sample_ctx)
            elif name == "synthesize_opportunity_analysis":
                return CapabilityResult(success=True, capability_name=name, data=sample_opp)
            return CapabilityResult(success=True, capability_name=name, data={})

        self.registry.get.side_effect = mock_get
        self.registry.execute.side_effect = mock_execute

        state = AgentState(
            task_id="task_populate",
            user_goal="Populate test",
            status=AgentStatus.EXECUTING,
            plan=Plan(
                steps=[
                    PlanStep(step_id="s1", capability_name="assemble_prospect_context", depends_on=[]),
                    PlanStep(step_id="s2", capability_name="synthesize_opportunity_analysis", depends_on=["s1"]),
                ]
            )
        )
        self.executor.run(state)
        self.assertEqual(state.prospect_context, sample_ctx)
        self.assertEqual(state.opportunity_analysis, sample_opp)

    def test_08_capability_failure_stops_dependent_work(self):
        """8. Capability failure halts execution and marks dependent steps as BLOCKED."""
        def mock_get(name):
            return CapabilityDescriptor(
                name=name,
                description=name,
                policy_class=PolicyClass.READ,
                input_schema=DummySchema,
                output_schema=DummySchema
            )

        def mock_execute(name, params):
            if name == "step_failure":
                return CapabilityResult(success=False, capability_name=name, error="Connection timeout")
            return CapabilityResult(success=True, capability_name=name, data={})

        self.registry.get.side_effect = mock_get
        self.registry.execute.side_effect = mock_execute

        state = AgentState(
            task_id="task_fail",
            user_goal="Failure test",
            status=AgentStatus.EXECUTING,
            plan=Plan(
                steps=[
                    PlanStep(step_id="s1", capability_name="step_failure", depends_on=[]),
                    PlanStep(step_id="s2", capability_name="step_dependent", depends_on=["s1"]),
                ]
            )
        )
        self.executor.run(state)
        self.assertEqual(state.status, AgentStatus.FAILED)
        self.assertEqual(state.plan.get_step("s1").status, StepStatus.FAILED)
        self.assertEqual(state.plan.get_step("s2").status, StepStatus.BLOCKED)
        self.assertTrue(any("Connection timeout" in err for err in state.errors))

    def test_09_unknown_capability_is_rejected(self):
        """9. Unknown capability stops execution safely and marks step failed."""
        self.registry.get.return_value = None

        state = AgentState(
            task_id="task_unk",
            user_goal="Unknown cap",
            status=AgentStatus.EXECUTING,
            plan=Plan(
                steps=[PlanStep(step_id="s1", capability_name="unregistered_cap", depends_on=[])]
            )
        )
        self.executor.run(state)
        self.assertEqual(state.status, AgentStatus.FAILED)
        self.assertTrue(any("Unknown capability" in err for err in state.errors))

    def test_10_policy_violation_is_rejected(self):
        """10. Policy violation halts execution safely when write permissions are denied."""
        strict_config = ExecutionPolicyConfig(allow_staged_writes=False, require_approval_for_write=True)
        strict_enforcer = PolicyEnforcer(config=strict_config)
        strict_executor = AgentExecutor(registry=self.registry, policy_enforcer=strict_enforcer)

        descriptor = CapabilityDescriptor(
            name="render_outreach_drafts",
            description="Render drafts",
            policy_class=PolicyClass.WRITE,
            input_schema=DummySchema,
            output_schema=DummySchema
        )
        self.registry.get.return_value = descriptor

        state = AgentState(
            task_id="task_policy",
            user_goal="Write draft",
            status=AgentStatus.EXECUTING,
            plan=Plan(
                steps=[PlanStep(step_id="s1", capability_name="render_outreach_drafts", depends_on=[])]
            )
        )
        strict_executor.run(state)
        # Should pause for human approval
        self.assertEqual(state.status, AgentStatus.WAITING_FOR_APPROVAL)
        self.assertIsNotNone(state.approval_request)
        self.assertEqual(state.approval_request.capability_name, "render_outreach_drafts")

    def test_11_execution_limit_works(self):
        """11. Hard execution limit (max 15) halts runaway execution safely."""
        limited_executor = AgentExecutor(registry=self.registry, max_executions=2)

        def mock_get(name):
            return CapabilityDescriptor(
                name=name,
                description=name,
                policy_class=PolicyClass.READ,
                input_schema=DummySchema,
                output_schema=DummySchema
            )

        self.registry.get.side_effect = mock_get
        self.registry.execute.return_value = CapabilityResult(success=True, capability_name="test", data={})

        state = AgentState(
            task_id="task_limit",
            user_goal="Runaway loop test",
            status=AgentStatus.EXECUTING,
            plan=Plan(
                steps=[
                    PlanStep(step_id=f"step_{i}", capability_name=f"cap_{i}", depends_on=[])
                    for i in range(5)
                ]
            )
        )
        limited_executor.run(state)
        self.assertEqual(state.status, AgentStatus.FAILED)
        self.assertEqual(state.execution_count, 2)
        self.assertTrue(any("Safety execution limit exceeded" in err for err in state.errors))


class TestAgentStateTransitions(unittest.TestCase):
    """Tests 12-15: State machine lifecycle and transition integrity."""

    def test_12_valid_state_transitions(self):
        """12. Valid lifecycle progression PLANNING -> EXECUTING -> COMPLETED."""
        state = AgentState(task_id="t1", user_goal="goal")
        self.assertEqual(state.status, AgentStatus.PLANNING)

        state.transition_to(AgentStatus.EXECUTING, reason="starting")
        self.assertEqual(state.status, AgentStatus.EXECUTING)

        state.transition_to(AgentStatus.COMPLETED, reason="finished")
        self.assertEqual(state.status, AgentStatus.COMPLETED)

    def test_13_invalid_state_transitions_rejected(self):
        """13. Illegal state transitions raise InvalidStateTransitionError."""
        state = AgentState(task_id="t2", user_goal="goal")
        # Direct PLANNING -> COMPLETED is illegal
        with self.assertRaises(InvalidStateTransitionError):
            state.transition_to(AgentStatus.COMPLETED)

        # Transitioning out of COMPLETED is illegal
        state.transition_to(AgentStatus.EXECUTING)
        state.transition_to(AgentStatus.COMPLETED)
        with self.assertRaises(InvalidStateTransitionError):
            state.transition_to(AgentStatus.EXECUTING)

    def test_14_completed_task_reaches_completed(self):
        """14. End-to-end successful execution reaches COMPLETED."""
        registry = CapabilityRegistry.default_registry()
        # Mock all capability executions
        with patch.object(registry, "execute") as mock_exec:
            mock_exec.side_effect = [
                CapabilityResult(success=True, capability_name="audit_website_tech", data={}),
                CapabilityResult(success=True, capability_name="enrich_leadership_social", data={}),
                CapabilityResult(success=True, capability_name="mine_business_intelligence", data={}),
                CapabilityResult(success=True, capability_name="calculate_health_and_scores", data={}),
                CapabilityResult(success=True, capability_name="assemble_prospect_context", data=create_sample_context()),
                CapabilityResult(success=True, capability_name="synthesize_opportunity_analysis", data=create_sample_opportunity()),
                CapabilityResult(success=True, capability_name="formulate_outreach_strategy", data=create_sample_outreach()),
                CapabilityResult(success=True, capability_name="evaluate_ai_reasoning", data=create_sample_evaluation(passed=True)),
                CapabilityResult(success=True, capability_name="render_outreach_drafts", data=create_sample_draft()),
            ]
            agent = Agent(registry=registry)
            state = agent.run("Research a business and prepare an outreach opportunity")
            self.assertEqual(state.status, AgentStatus.COMPLETED)
            self.assertIsNotNone(state.final_response)
            self.assertEqual(state.final_response.status, AgentStatus.COMPLETED)
            self.assertEqual(len(state.final_response.completed_capabilities), 9)

    def test_15_failed_task_reaches_failed(self):
        """15. Task with unrecoverable failure reaches FAILED."""
        agent = Agent()
        # Unknown goal triggers planning failure
        state = agent.run("Totally unknown nonsensical instruction")
        self.assertEqual(state.status, AgentStatus.FAILED)
        self.assertIsNotNone(state.final_response)
        self.assertEqual(state.final_response.status, AgentStatus.FAILED)


class TestAgentEvaluationGate(unittest.TestCase):
    """Tests 16-17: Quality gate enforcement based on EvaluationResult."""

    def setUp(self):
        self.registry = CapabilityRegistry.default_registry()

    def test_16_successful_evaluation_allows_completion(self):
        """16. Successful evaluation (passed=True) allows pipeline to complete outreach drafting."""
        with patch.object(self.registry, "execute") as mock_exec:
            mock_exec.side_effect = [
                CapabilityResult(success=True, capability_name="audit_website_tech", data={}),
                CapabilityResult(success=True, capability_name="enrich_leadership_social", data={}),
                CapabilityResult(success=True, capability_name="mine_business_intelligence", data={}),
                CapabilityResult(success=True, capability_name="calculate_health_and_scores", data={}),
                CapabilityResult(success=True, capability_name="assemble_prospect_context", data=create_sample_context()),
                CapabilityResult(success=True, capability_name="synthesize_opportunity_analysis", data=create_sample_opportunity()),
                CapabilityResult(success=True, capability_name="formulate_outreach_strategy", data=create_sample_outreach()),
                CapabilityResult(success=True, capability_name="evaluate_ai_reasoning", data=create_sample_evaluation(passed=True)),
                CapabilityResult(success=True, capability_name="render_outreach_drafts", data=create_sample_draft()),
            ]
            agent = Agent(registry=self.registry)
            state = agent.run("Research a business and prepare an outreach opportunity")
            self.assertEqual(state.status, AgentStatus.COMPLETED)
            self.assertIsNotNone(state.outreach_draft)

    def test_17_failed_evaluation_stops_execution(self):
        """17. Failed evaluation (passed=False) halts execution safely before outreach drafting."""
        with patch.object(self.registry, "execute") as mock_exec:
            mock_exec.side_effect = [
                CapabilityResult(success=True, capability_name="audit_website_tech", data={}),
                CapabilityResult(success=True, capability_name="enrich_leadership_social", data={}),
                CapabilityResult(success=True, capability_name="mine_business_intelligence", data={}),
                CapabilityResult(success=True, capability_name="calculate_health_and_scores", data={}),
                CapabilityResult(success=True, capability_name="assemble_prospect_context", data=create_sample_context()),
                CapabilityResult(success=True, capability_name="synthesize_opportunity_analysis", data=create_sample_opportunity()),
                CapabilityResult(success=True, capability_name="formulate_outreach_strategy", data=create_sample_outreach()),
                # Evaluation gate fails
                CapabilityResult(success=True, capability_name="evaluate_ai_reasoning", data=create_sample_evaluation(passed=False)),
            ]
            agent = Agent(registry=self.registry)
            state = agent.run("Research a business and prepare an outreach opportunity")
            self.assertEqual(state.status, AgentStatus.FAILED)
            self.assertIsNone(state.outreach_draft)
            self.assertTrue(any("Evaluation gate failed" in err for err in state.errors))
            # Verify draft step was BLOCKED
            draft_step = state.plan.get_step("step_draft")
            self.assertEqual(draft_step.status, StepStatus.BLOCKED)


class TestAgentSafetyGuarantees(unittest.TestCase):
    """Tests 18-20: Safety invariants, policy enforcement, and infrastructure isolation."""

    def test_18_agent_cannot_directly_call_infrastructure(self):
        """18. Agent and Executor do not import or hold infrastructure handles."""
        import agent.agent as agent_mod
        import agent.executor as exec_mod

        # Ensure database/scraping/networking libraries are not imported in agent core
        forbidden_modules = ["psycopg2", "playwright", "requests", "urllib.request", "socket"]
        for mod in forbidden_modules:
            self.assertNotIn(mod, dir(agent_mod))
            self.assertNotIn(mod, dir(exec_mod))

    def test_19_agent_cannot_bypass_capability_registry(self):
        """19. All capability executions require registration in CapabilityRegistry."""
        registry = CapabilityRegistry()  # Empty registry
        agent = Agent(registry=registry)
        state = agent.run("Research a business and prepare an outreach opportunity")
        # Fails because capabilities are unregistered
        self.assertEqual(state.status, AgentStatus.FAILED)
        self.assertTrue(any("references unknown capability" in err for err in state.errors))

    def test_20_no_external_communication_can_occur(self):
        """20. EXTERNAL_ACTION capabilities strictly pause for human approval."""
        registry = CapabilityRegistry()
        descriptor = CapabilityDescriptor(
            name="send_external_email",
            description="Send live email",
            policy_class=PolicyClass.EXTERNAL_ACTION,
            input_schema=DummySchema,
            output_schema=DummySchema
        )
        registry.register(
            MagicMock(
                NAME="send_external_email",
                DESCRIPTION="Send live email",
                POLICY_CLASS=PolicyClass.EXTERNAL_ACTION
            ),
            DummySchema,
            DummySchema
        )

        enforcer = PolicyEnforcer()
        res = enforcer.evaluate(registry.get("send_external_email"))
        self.assertFalse(res.is_allowed)
        self.assertTrue(res.requires_approval)


class TestAgentIntelligenceAndDynamicPlanning(unittest.TestCase):
    """Tests 21-36: Phase 3D Agent Intelligence, Intent Interpretation & Dynamic Planning."""

    def setUp(self):
        self.registry = CapabilityRegistry.default_registry()
        self.interpreter = GoalInterpreter()
        self.planner = AgentPlanner(registry=self.registry, interpreter=self.interpreter)
        self.agent = Agent(registry=self.registry, planner=self.planner, interpreter=self.interpreter)

    def test_21_known_business_research_plan(self):
        """21. Known business research generates 6 analysis capabilities without discovery or outreach."""
        goal = "Analyze Acme Plumbing and evaluate commercial opportunity"
        intent = self.interpreter.interpret(goal)
        self.assertEqual(intent.intent_type, IntentType.RESEARCH_KNOWN_BUSINESS)
        self.assertFalse(intent.requires_discovery)
        self.assertTrue(intent.requires_research)
        self.assertTrue(intent.requires_opportunity_analysis)
        self.assertFalse(intent.requires_outreach)
        self.assertFalse(intent.requires_draft)

        plan = self.planner.plan(goal)
        self.planner.validate_plan(plan)
        step_caps = [s.capability_name for s in plan.steps]
        self.assertNotIn("discover_prospects", step_caps)
        self.assertNotIn("render_outreach_drafts", step_caps)
        self.assertIn("synthesize_opportunity_analysis", step_caps)
        self.assertEqual(len(plan.steps), 6)

    def test_22_known_business_outreach_preparation(self):
        """22. Known business outreach preparation includes full research, outreach, and draft rendering."""
        goal = "Research Acme Plumbing and prepare an outreach opportunity"
        intent = self.interpreter.interpret(goal)
        self.assertEqual(intent.intent_type, IntentType.RESEARCH_AND_OUTREACH)
        self.assertTrue(intent.requires_outreach)
        self.assertTrue(intent.requires_draft)

        plan = self.planner.plan(goal)
        step_caps = [s.capability_name for s in plan.steps]
        self.assertIn("formulate_outreach_strategy", step_caps)
        self.assertIn("evaluate_ai_reasoning", step_caps)
        self.assertIn("render_outreach_drafts", step_caps)
        self.assertEqual(len(plan.steps), 9)

    def test_23_discovery_only_request(self):
        """23. Discovery-only request generates minimal 1-step plan and populates state prospects."""
        goal = "Find dental clinics in Austin, TX"
        intent = self.interpreter.interpret(goal)
        self.assertEqual(intent.intent_type, IntentType.DISCOVER_PROSPECTS)
        self.assertTrue(intent.requires_discovery)
        self.assertFalse(intent.requires_research)

        plan = self.planner.plan(goal)
        self.assertEqual(len(plan.steps), 1)
        self.assertEqual(plan.steps[0].capability_name, "discover_prospects")

        # Mock execution of discovery
        with patch.object(self.registry, "execute") as mock_exec:
            mock_biz = Business(business_name="Austin Dental Care", website="https://austindental.com", google_rating=4.5)
            mock_exec.return_value = CapabilityResult(
                success=True,
                capability_name="discover_prospects",
                data=DiscoverProspectsOutput(query="Dentist in Austin, TX", total_found=1, source="gmaps", businesses=[mock_biz])
            )
            state = self.agent.run(goal)
            self.assertEqual(state.status, AgentStatus.COMPLETED)
            self.assertEqual(len(state.prospects), 1)
            self.assertEqual(state.prospects[0].business_name, "Austin Dental Care")
            self.assertEqual(state.execution_count, 1)

    def test_24_discovery_plus_analysis(self):
        """24. Discovery + analysis generates 7 steps with research depending on discovery."""
        goal = "Discover and analyze dentists in Chicago"
        intent = self.interpreter.interpret(goal)
        self.assertEqual(intent.intent_type, IntentType.DISCOVER_AND_ANALYZE)
        self.assertTrue(intent.requires_discovery)
        self.assertTrue(intent.requires_research)
        self.assertFalse(intent.requires_outreach)

        plan = self.planner.plan(goal)
        self.assertEqual(len(plan.steps), 7)
        self.assertEqual(plan.steps[0].capability_name, "discover_prospects")
        # Ensure audit depends on discover
        audit_step = plan.get_step("step_audit")
        self.assertIn("step_discover", audit_step.depends_on)

    def test_25_discovery_plus_outreach(self):
        """25. Discovery + outreach generates 10 steps starting with discovery and ending with drafting."""
        goal = "Find 5 plumbers in Chicago with weak websites and prepare outreach drafts"
        intent = self.interpreter.interpret(goal)
        self.assertEqual(intent.intent_type, IntentType.DISCOVER_AND_OUTREACH)
        self.assertTrue(intent.requires_discovery)
        self.assertTrue(intent.requires_outreach)

        plan = self.planner.plan(goal)
        self.assertEqual(len(plan.steps), 10)
        self.assertEqual(plan.steps[0].capability_name, "discover_prospects")
        self.assertEqual(plan.steps[-1].capability_name, "render_outreach_drafts")
        self.assertIn("step_discover", plan.get_step("step_audit").depends_on)

    def test_26_missing_location_clarification(self):
        """26. Missing location in discovery goal pauses with NEEDS_CLARIFICATION without executing tools."""
        goal = "Find dental clinics"
        state = self.agent.run(goal)
        self.assertEqual(state.status, AgentStatus.NEEDS_CLARIFICATION)
        self.assertIsNotNone(state.clarification_request)
        self.assertIn("location", state.clarification_request.missing_information)
        self.assertEqual(state.execution_count, 0)
        self.assertEqual(len(state.completed_steps), 0)

    def test_27_unsupported_external_action(self):
        """27. Unsupported real-world external communication safely transitions to FAILED without dispatching."""
        goal = "Send WhatsApp messages to all prospects in Chicago"
        state = self.agent.run(goal)
        self.assertEqual(state.status, AgentStatus.FAILED)
        self.assertTrue(any("Unsupported external action" in err for err in state.errors))
        self.assertEqual(state.execution_count, 0)

    def test_28_dynamic_plan_generation_varies_by_intent(self):
        """28. Planner constructs dynamically sized plans matching capability requirements."""
        plan_disc = self.planner.plan("Find dentists in Chicago")
        plan_research = self.planner.plan("Analyze Apex Plumbing commercial opportunity")
        plan_outreach = self.planner.plan("Research Apex Plumbing and prepare outreach")
        plan_full = self.planner.plan("Find dentists in Chicago and prepare outreach drafts")

        self.assertEqual(len(plan_disc.steps), 1)
        self.assertEqual(len(plan_research.steps), 6)
        self.assertEqual(len(plan_outreach.steps), 9)
        self.assertEqual(len(plan_full.steps), 10)

    def test_29_capability_ordering_prerequisites_precede_dependents(self):
        """29. Dynamic plan adheres to strict topological ordering."""
        plan = self.planner.plan("Find dentists in Chicago and prepare outreach drafts")
        step_ids = [s.step_id for s in plan.steps]

        self.assertLess(step_ids.index("step_discover"), step_ids.index("step_audit"))
        self.assertLess(step_ids.index("step_audit"), step_ids.index("step_score"))
        self.assertLess(step_ids.index("step_score"), step_ids.index("step_context"))
        self.assertLess(step_ids.index("step_context"), step_ids.index("step_opp"))
        self.assertLess(step_ids.index("step_opp"), step_ids.index("step_outreach"))
        self.assertLess(step_ids.index("step_outreach"), step_ids.index("step_eval"))
        self.assertLess(step_ids.index("step_eval"), step_ids.index("step_draft"))

    def test_30_discovery_appearing_before_analysis(self):
        """30. Discovery step is strictly marked as a dependency for downstream analysis in discovery workflows."""
        plan = self.planner.plan("Discover and analyze dentists in Chicago")
        for step_id in ["step_audit", "step_enrich", "step_intel"]:
            step = plan.get_step(step_id)
            self.assertIn("step_discover", step.depends_on)

    def test_31_existing_phase_3c_workflow_remains_valid(self):
        """31. Standard Phase 3C research and outreach goal remains completely operational."""
        with patch.object(self.registry, "execute") as mock_exec:
            mock_exec.side_effect = [
                CapabilityResult(success=True, capability_name="audit_website_tech", data={}),
                CapabilityResult(success=True, capability_name="enrich_leadership_social", data={}),
                CapabilityResult(success=True, capability_name="mine_business_intelligence", data={}),
                CapabilityResult(success=True, capability_name="calculate_health_and_scores", data={}),
                CapabilityResult(success=True, capability_name="assemble_prospect_context", data=create_sample_context()),
                CapabilityResult(success=True, capability_name="synthesize_opportunity_analysis", data=create_sample_opportunity()),
                CapabilityResult(success=True, capability_name="formulate_outreach_strategy", data=create_sample_outreach()),
                CapabilityResult(success=True, capability_name="evaluate_ai_reasoning", data=create_sample_evaluation(passed=True)),
                CapabilityResult(success=True, capability_name="render_outreach_drafts", data=create_sample_draft()),
            ]
            state = self.agent.run("Research a business and prepare an outreach opportunity", initial_params={"business_name": "Acme Plumbing"})
            self.assertEqual(state.status, AgentStatus.COMPLETED)
            self.assertEqual(len(state.completed_steps), 9)

    def test_32_registry_only_execution_remains_enforced(self):
        """32. Dynamically planned capabilities route strictly through CapabilityRegistry.execute()."""
        with patch.object(self.registry, "execute") as mock_exec:
            mock_exec.return_value = CapabilityResult(
                success=True,
                capability_name="discover_prospects",
                data=DiscoverProspectsOutput(query="q", total_found=0, source="gmaps", businesses=[])
            )
            state = self.agent.run("Find dentists in Chicago")
            self.assertTrue(mock_exec.called)
            self.assertEqual(mock_exec.call_args[0][0], "discover_prospects")

    def test_33_evaluation_gate_remains_enforced(self):
        """33. Evaluation quality gate halts discovery + outreach plan if reasoning fails."""
        with patch.object(self.registry, "execute") as mock_exec:
            mock_biz = Business(business_name="Dentist A", website="https://dentista.com")
            mock_exec.side_effect = [
                CapabilityResult(success=True, capability_name="discover_prospects", data=DiscoverProspectsOutput(query="q", total_found=1, source="gmaps", businesses=[mock_biz])),
                CapabilityResult(success=True, capability_name="audit_website_tech", data={}),
                CapabilityResult(success=True, capability_name="enrich_leadership_social", data={}),
                CapabilityResult(success=True, capability_name="mine_business_intelligence", data={}),
                CapabilityResult(success=True, capability_name="calculate_health_and_scores", data={}),
                CapabilityResult(success=True, capability_name="assemble_prospect_context", data=create_sample_context()),
                CapabilityResult(success=True, capability_name="synthesize_opportunity_analysis", data=create_sample_opportunity()),
                CapabilityResult(success=True, capability_name="formulate_outreach_strategy", data=create_sample_outreach()),
                # Gate fails here
                CapabilityResult(success=True, capability_name="evaluate_ai_reasoning", data=create_sample_evaluation(passed=False)),
            ]
            state = self.agent.run("Find dentists in Chicago and prepare outreach drafts")
            self.assertEqual(state.status, AgentStatus.FAILED)
            self.assertIsNone(state.outreach_draft)
            self.assertEqual(state.plan.get_step("step_draft").status, StepStatus.BLOCKED)

    def test_34_ambiguous_goal_does_not_execute_capabilities(self):
        """34. Purely ambiguous goal produces NEEDS_CLARIFICATION with zero executions."""
        goal = "Find businesses"
        state = self.agent.run(goal)
        self.assertEqual(state.status, AgentStatus.NEEDS_CLARIFICATION)
        self.assertEqual(state.execution_count, 0)
        self.assertEqual(len(state.completed_steps), 0)

    def test_35_unknown_capability_cannot_enter_plan(self):
        """35. Injected plan step with unregistered capability fails plan validation."""
        plan = Plan(
            plan_id="test_bad_cap",
            steps=[
                PlanStep(step_id="s1", capability_name="unregistered_super_tool", depends_on=[])
            ]
        )
        with self.assertRaises(PlanValidationError):
            self.planner.validate_plan(plan, registry=self.registry)

    def test_36_discovery_output_populates_state_prospects_and_hydrates_downstream(self):
        """36. Discovered prospect dynamically hydrates downstream website audit parameters."""
        mock_biz = Business(business_name="Dynamic Discovered Clinic", website="https://discoveredclinic.com", google_rating=4.2)

        with patch.object(self.registry, "execute") as mock_exec:
            def side_effect(cap_name, params):
                if cap_name == "discover_prospects":
                    return CapabilityResult(
                        success=True,
                        capability_name=cap_name,
                        data=DiscoverProspectsOutput(query="q", total_found=1, source="gmaps", businesses=[mock_biz])
                    )
                elif cap_name == "audit_website_tech":
                    # Verify hydration took place
                    self.assertEqual(params.get("business_name"), "Dynamic Discovered Clinic")
                    self.assertEqual(params.get("website_url"), "https://discoveredclinic.com")
                    return CapabilityResult(success=True, capability_name=cap_name, data={})
                return CapabilityResult(success=True, capability_name=cap_name, data={})

            mock_exec.side_effect = side_effect
            state = self.agent.run("Discover and analyze dentists in Chicago")
            self.assertEqual(len(state.prospects), 1)
            self.assertEqual(state.prospects[0].business_name, "Dynamic Discovered Clinic")


class TestLLMIntentInterpretation(unittest.TestCase):
    """
    Unit test suite for Phase 3E LLM-Powered Intent Interpretation.
    Validates:
    1. Valid structured LLM intent interpretation
    2. Deterministic validation of LLM outputs (missing location, entity extraction)
    3. Malformed LLM output -> deterministic fallback
    4. Missing required fields -> deterministic fallback
    5. Unsupported intent handling
    6. LLM unavailable -> deterministic fallback
    7. LLM timeout -> deterministic fallback
    8. LLM provider error 500 -> deterministic fallback
    9. Both interpreters fail -> controlled safe failure
    10. LLM cannot inject capability names
    11. LLM cannot inject execution steps
    12. LLM cannot bypass registry
    13. Discovery intent produces discovery-first plan
    14. Outreach intent produces evaluation gate
    15. External action intent remains policy-controlled
    16. Semantic contradiction rejection by validator
    17. Standalone deterministic interpreter mode
    """

    def setUp(self):
        self.registry = CapabilityRegistry.default_registry()

    def test_37_valid_structured_llm_intent(self):
        """37. Valid structured LLM output produces executable plan with intent_source='llm'."""
        mock_llm = MagicMock(spec=LLMClient)
        mock_llm.is_available = True
        mock_llm.generate_structured.return_value = AgentIntent(
            intent_type=IntentType.RESEARCH_KNOWN_BUSINESS,
            objective="Analyze Apex Plumbing",
            target_business="Apex Plumbing",
            requires_research=True,
            requires_opportunity_analysis=True,
        )

        agent = Agent(registry=self.registry, llm_client=mock_llm)
        state = agent.run("Analyze Apex Plumbing")

        self.assertEqual(state.status, AgentStatus.COMPLETED)
        self.assertEqual(state.intent_source, "llm")
        self.assertEqual(state.final_response.intent_source, "llm")
        self.assertTrue(mock_llm.generate_structured.called)

    def test_38_llm_intent_validation_missing_location(self):
        """38. LLM discovery intent missing location is caught by validator and triggers NEEDS_CLARIFICATION."""
        mock_llm = MagicMock(spec=LLMClient)
        mock_llm.is_available = True
        mock_llm.generate_structured.return_value = AgentIntent(
            intent_type=IntentType.DISCOVER_PROSPECTS,
            objective="Find dental clinics",
            requires_discovery=True,
            location=None,
            search_query=None,
        )

        agent = Agent(registry=self.registry, llm_client=mock_llm)
        state = agent.run("Find dental clinics")

        self.assertEqual(state.status, AgentStatus.NEEDS_CLARIFICATION)
        self.assertIsNotNone(state.clarification_request)
        self.assertIn("location", state.clarification_request.missing_information)
        self.assertEqual(state.execution_count, 0)

    def test_39_malformed_llm_output_triggers_fallback(self):
        """39. Malformed LLM response (JSON decoding failure) triggers deterministic fallback."""
        mock_llm = MagicMock(spec=LLMClient)
        mock_llm.is_available = True
        mock_llm.generate_structured.side_effect = LLMResponseParsingError("Invalid JSON text")

        agent = Agent(registry=self.registry, llm_client=mock_llm)
        state = agent.run("Analyze Apex Plumbing and prepare outreach")

        self.assertEqual(state.intent_source, "deterministic_fallback")
        self.assertEqual(state.status, AgentStatus.COMPLETED)
        self.assertEqual(state.intent.intent_type, IntentType.RESEARCH_AND_OUTREACH)

    def test_40_missing_required_fields_in_llm_output(self):
        """40. LLM output missing required schema fields triggers deterministic fallback."""
        mock_llm = MagicMock(spec=LLMClient)
        mock_llm.is_available = True
        mock_llm.generate_structured.side_effect = LLMValidationError("Missing required field: objective")

        agent = Agent(registry=self.registry, llm_client=mock_llm)
        state = agent.run("Analyze Apex Plumbing")

        self.assertEqual(state.intent_source, "deterministic_fallback")
        self.assertEqual(state.status, AgentStatus.COMPLETED)

    def test_41_unsupported_intent_from_llm(self):
        """41. LLM returning UNKNOWN intent safely transitions state to FAILED without executions."""
        mock_llm = MagicMock(spec=LLMClient)
        mock_llm.is_available = True
        mock_llm.generate_structured.return_value = AgentIntent(
            intent_type=IntentType.UNKNOWN,
            objective="Fly to Mars",
        )

        agent = Agent(registry=self.registry, llm_client=mock_llm)
        state = agent.run("Fly to Mars")

        self.assertEqual(state.status, AgentStatus.FAILED)
        self.assertEqual(state.execution_count, 0)
        self.assertTrue(any("No deterministic workflow pattern" in e for e in state.errors))

    def test_42_llm_unavailable_triggers_fallback(self):
        """42. Unconfigured/unavailable LLM client immediately falls back to deterministic interpreter."""
        mock_llm = MagicMock(spec=LLMClient)
        mock_llm.is_available = False

        agent = Agent(registry=self.registry, llm_client=mock_llm)
        state = agent.run("Analyze Apex Plumbing")

        self.assertEqual(mock_llm.generate_structured.call_count, 0)
        self.assertEqual(state.intent_source, "deterministic_fallback")
        self.assertEqual(state.status, AgentStatus.COMPLETED)

    def test_43_llm_timeout_triggers_fallback(self):
        """43. LLM request timeout raises LLMProviderError and triggers deterministic fallback."""
        mock_llm = MagicMock(spec=LLMClient)
        mock_llm.is_available = True
        mock_llm.generate_structured.side_effect = LLMProviderError("Request timed out after 15.0s")

        agent = Agent(registry=self.registry, llm_client=mock_llm)
        state = agent.run("Analyze Apex Plumbing")

        self.assertEqual(state.intent_source, "deterministic_fallback")
        self.assertEqual(state.status, AgentStatus.COMPLETED)

    def test_44_llm_provider_500_triggers_fallback(self):
        """44. LLM provider HTTP 500 error triggers deterministic fallback."""
        mock_llm = MagicMock(spec=LLMClient)
        mock_llm.is_available = True
        mock_llm.generate_structured.side_effect = LLMProviderError("Provider 500 Internal Server Error")

        agent = Agent(registry=self.registry, llm_client=mock_llm)
        state = agent.run("Analyze Apex Plumbing")

        self.assertEqual(state.intent_source, "deterministic_fallback")
        self.assertEqual(state.status, AgentStatus.COMPLETED)

    def test_45_both_interpreters_fail_safe_failure(self):
        """45. When both LLM and fallback interpreter fail, Agent halts safely in FAILED state."""
        mock_llm = MagicMock(spec=LLMClient)
        mock_llm.is_available = True
        mock_llm.generate_structured.side_effect = LLMProviderError("LLM network down")

        mock_fallback = MagicMock(spec=GoalInterpreter)
        mock_fallback.interpret.side_effect = RuntimeError("Fallback internal failure")

        llm_interpreter = LLMIntentInterpreter(llm_client=mock_llm, fallback_interpreter=mock_fallback)
        agent = Agent(registry=self.registry, interpreter=llm_interpreter)
        state = agent.run("Some complex query")

        self.assertEqual(state.status, AgentStatus.FAILED)
        self.assertEqual(state.intent_source, "failed")
        self.assertEqual(state.execution_count, 0)
        self.assertTrue(any("Complete interpretation failure" in e for e in state.errors))

    def test_46_llm_cannot_inject_capability_names(self):
        """46. Arbitrary capabilities injected in LLM response are discarded and not scheduled."""
        injected_payload = {
            "intent_type": "RESEARCH_KNOWN_BUSINESS",
            "objective": "Analyze Apex Plumbing",
            "target_business": "Apex Plumbing",
            "tools": ["drop_database", "shell_exec"],
            "capabilities": ["format_hard_drive"],
            "requires_research": True,
            "requires_opportunity_analysis": True,
        }
        intent = AgentIntent.model_validate(injected_payload)
        self.assertNotIn("tools", intent.model_dump())
        self.assertNotIn("capabilities", intent.model_dump())

        planner = AgentPlanner(registry=self.registry)
        plan = planner.plan_from_intent(intent)
        step_caps = [s.capability_name for s in plan.steps]
        self.assertNotIn("drop_database", step_caps)
        self.assertNotIn("shell_exec", step_caps)

    def test_47_llm_cannot_inject_execution_steps(self):
        """47. Injected execution_steps array is ignored; planner deterministically constructs DAG."""
        injected_payload = {
            "intent_type": "AUDIT_ONLY",
            "objective": "Audit Apex",
            "target_business": "Apex",
            "execution_steps": [{"step_id": "hack_step", "capability_name": "malicious"}],
            "requires_research": True,
        }
        intent = AgentIntent.model_validate(injected_payload)
        self.assertNotIn("execution_steps", intent.model_dump())

        planner = AgentPlanner(registry=self.registry)
        plan = planner.plan_from_intent(intent)
        self.assertEqual(len(plan.steps), 1)
        self.assertEqual(plan.steps[0].capability_name, "audit_website_tech")
        self.assertEqual(plan.steps[0].step_id, "step_audit")

    def test_48_llm_cannot_bypass_registry(self):
        """48. Even if a plan step references an unregistered capability, plan validation rejects it."""
        plan = Plan(
            plan_id="bad_plan",
            steps=[PlanStep(step_id="s1", capability_name="unregistered_tool", depends_on=[])]
        )
        planner = AgentPlanner(registry=self.registry)
        with self.assertRaises(PlanValidationError):
            planner.validate_plan(plan, registry=self.registry)

    def test_49_discovery_intent_produces_discovery_first_plan(self):
        """49. LLM DISCOVER_AND_ANALYZE intent ensures discovery is the first executed step."""
        mock_llm = MagicMock(spec=LLMClient)
        mock_llm.is_available = True
        mock_llm.generate_structured.return_value = AgentIntent(
            intent_type=IntentType.DISCOVER_AND_ANALYZE,
            objective="Discover and analyze dentists in Chicago",
            location="Chicago",
            industry="Dentists",
            search_query="Dentists in Chicago",
            requires_discovery=True,
            requires_research=True,
            requires_opportunity_analysis=True,
        )

        mock_biz = Business(business_name="Chicago Smiles", website="https://chicagosmiles.com", google_rating=4.5)
        with patch.object(self.registry, "execute") as mock_exec:
            mock_exec.side_effect = lambda cap, params: CapabilityResult(
                success=True,
                capability_name=cap,
                data=DiscoverProspectsOutput(query="Dentists in Chicago", total_found=1, source="gmaps", businesses=[mock_biz]) if cap == "discover_prospects" else {}
            )
            agent = Agent(registry=self.registry, llm_client=mock_llm)
            state = agent.run("Discover and analyze dentists in Chicago")

            self.assertEqual(state.status, AgentStatus.COMPLETED)
            self.assertEqual(state.plan.steps[0].capability_name, "discover_prospects")
            self.assertIn("step_discover", state.plan.get_step("step_audit").depends_on)
            self.assertEqual(len(state.prospects), 1)

    def test_50_outreach_intent_produces_evaluation_gate(self):
        """50. LLM RESEARCH_AND_OUTREACH intent includes evaluation step gating the draft step."""
        mock_llm = MagicMock(spec=LLMClient)
        mock_llm.is_available = True
        mock_llm.generate_structured.return_value = AgentIntent(
            intent_type=IntentType.RESEARCH_AND_OUTREACH,
            objective="Analyze Apex and prepare outreach",
            target_business="Apex",
            requires_research=True,
            requires_opportunity_analysis=True,
            requires_outreach=True,
            requires_evaluation=True,
            requires_draft=True,
        )

        failing_eval = create_sample_evaluation(passed=False)

        with patch.object(self.registry, "execute") as mock_exec:
            mock_exec.side_effect = lambda cap, params: CapabilityResult(
                success=True,
                capability_name=cap,
                data=failing_eval if cap == "evaluate_ai_reasoning" else {}
            )
            agent = Agent(registry=self.registry, llm_client=mock_llm)
            state = agent.run("Analyze Apex and prepare outreach")

            self.assertEqual(state.status, AgentStatus.FAILED)
            draft_step = state.plan.get_step("step_draft")
            self.assertEqual(draft_step.status, StepStatus.BLOCKED)

    def test_51_external_action_intent_remains_policy_controlled(self):
        """51. LLM attempting to bypass external action policy is overridden by deterministic validator."""
        mock_llm = MagicMock(spec=LLMClient)
        mock_llm.is_available = True
        mock_llm.generate_structured.return_value = AgentIntent(
            intent_type=IntentType.RESEARCH_KNOWN_BUSINESS,
            objective="Send WhatsApp messages to all prospects",
            requires_external_action=False,
            requires_research=True,
        )

        agent = Agent(registry=self.registry, llm_client=mock_llm)
        state = agent.run("Send WhatsApp messages to all prospects")

        self.assertEqual(state.status, AgentStatus.FAILED)
        self.assertTrue(any("Unsupported external action" in e for e in state.errors))
        self.assertEqual(state.execution_count, 0)

    def test_52_semantic_contradictions_rejected_by_validator(self):
        """52. Deterministic validator raises IntentValidationError on contradictory requirement flags."""
        validator = DeterministicIntentValidator()

        bad_intent1 = AgentIntent(
            intent_type=IntentType.RESEARCH_AND_OUTREACH,
            objective="Bad",
            target_business="Biz",
            requires_draft=True,
            requires_outreach=False
        )
        with self.assertRaises(IntentValidationError):
            validator.validate(bad_intent1, "Bad")

        bad_intent2 = AgentIntent(
            intent_type=IntentType.RESEARCH_AND_OUTREACH,
            objective="Bad",
            target_business="Biz",
            requires_outreach=True,
            requires_opportunity_analysis=False
        )
        with self.assertRaises(IntentValidationError):
            validator.validate(bad_intent2, "Bad")

        bad_intent3 = AgentIntent(
            intent_type=IntentType.DISCOVER_PROSPECTS,
            objective="Bad",
            location="Chicago",
            requires_discovery=True,
            requires_outreach=True,
            requires_opportunity_analysis=True,
            requires_research=True,
            requires_draft=True
        )
        with self.assertRaises(IntentValidationError):
            validator.validate(bad_intent3, "Bad")

    def test_53_deterministic_interpreter_standalone_mode(self):
        """53. Agent explicitly initialized with GoalInterpreter runs with intent_source='deterministic'."""
        agent = Agent(registry=self.registry, interpreter=GoalInterpreter())
        state = agent.run("Analyze Apex Plumbing")

        self.assertEqual(state.status, AgentStatus.COMPLETED)
        self.assertEqual(state.intent_source, "deterministic")
        self.assertEqual(state.final_response.intent_source, "deterministic")


if __name__ == "__main__":
    unittest.main()
