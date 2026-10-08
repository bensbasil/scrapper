"""
tests/test_telemetry.py
-----------------------
Unit test suite for Phase 3F Agent Observability & Execution Tracing.
Validates:
1. Run trace creation and metadata
2. Run start timestamp ISO format
3. Run completion timestamp ISO format
4. Total duration monotonic measurement
5. Intent source recorded (LLM vs deterministic)
6. LLM fallback recorded and flagged
7. Planning trace recorded with serializable DAG steps
8. Capability START event recorded
9. Capability COMPLETED event recorded with duration
10. Capability FAILED event recorded with error classification
11. Blocked dependency trace and cascade tracking
12. Evaluation gate failure trace and halted execution
13. Policy rejection trace and classification
14. Execution ordering preserved across multiple events
15. Telemetry does not bypass CapabilityRegistry
16. Telemetry does not contain raw capability payloads (HTML, DB rows, etc.)
17. Telemetry does not contain secrets or authorization credentials
18. Existing AgentState behavior remains unchanged
19. Telemetry sink recording, retrieval, and clearing
20. Ambiguous / clarification request tracing
"""

import unittest
from datetime import datetime
from unittest.mock import MagicMock, patch
from typing import Dict, Any

from agent.models import (
    AgentStatus,
    StepStatus,
    Plan,
    PlanStep,
    AgentFinalResponse,
)
from agent.state import AgentState
from agent.intent import AgentIntent, IntentType, GoalInterpreter
from agent.llm_intent import LLMIntentInterpreter
from agent.planner import AgentPlanner
from agent.executor import AgentExecutor
from agent.policies import PolicyEnforcer, ExecutionPolicyConfig
from agent.agent import Agent
from agent.telemetry import (
    AgentRunTrace,
    CapabilityTraceEvent,
    IntentTrace,
    PlanTrace,
    ErrorCategory,
    StepEventStatus,
    AgentTelemetrySink,
    InMemoryTelemetrySink,
)
from application.capabilities.registry import CapabilityRegistry
from application.contracts.base import CapabilityResult
from application.contracts.outputs import DiscoverProspectsOutput
from schemas.business import Business
from schemas.context import ProspectContext
from schemas.ai import OpportunityAnalysis, OutreachStrategy
from schemas.outreach import OutreachDraft
from evaluation.models import EvaluationResult
from evaluation.datasets.fixtures import get_strong_evidence_good_reasoning_fixture
from ai.exceptions import LLMUnavailableError, LLMProviderError
from ai.client import LLMClient


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


class TestAgentObservabilityAndTracing(unittest.TestCase):
    """Phase 3F telemetry and execution tracing verification suite."""

    def setUp(self):
        self.registry = CapabilityRegistry.default_registry()
        self.sink = InMemoryTelemetrySink()

    def test_01_run_trace_creation(self):
        """1. Agent run creates an AgentRunTrace accessible via telemetry sink and state."""
        agent = Agent(registry=self.registry, telemetry_sink=self.sink)

        with patch.object(self.registry, "execute") as mock_exec:
            mock_biz = Business(business_name="Apex Plumbing", website="https://apex.com", google_rating=4.5)
            mock_exec.return_value = CapabilityResult(
                success=True,
                capability_name="discover_prospects",
                data=DiscoverProspectsOutput(query="Dentist in Austin, TX", total_found=1, source="gmaps", businesses=[mock_biz])
            )
            state = agent.run("Find dental clinics in Austin, TX")

        self.assertEqual(state.status, AgentStatus.COMPLETED)
        self.assertIsNotNone(state.trace)
        self.assertIsInstance(state.trace, AgentRunTrace)

        # Telemetry sink stores the trace
        sink_trace = self.sink.get_run(state.run_id)
        self.assertIsNotNone(sink_trace)
        self.assertEqual(sink_trace.run_id, state.run_id)
        self.assertEqual(sink_trace.task_id, state.task_id)
        self.assertEqual(sink_trace.user_goal, "Find dental clinics in Austin, TX")
        self.assertEqual(sink_trace.status, "COMPLETED")
        self.assertEqual(sink_trace.executed_step_count, 1)

    def test_02_run_start_timestamp(self):
        """2. Run trace contains a valid ISO start timestamp."""
        agent = Agent(registry=self.registry, telemetry_sink=self.sink)
        state = agent.run("Analyze Acme Plumbing and evaluate commercial opportunity")
        trace = self.sink.get_run(state.run_id)

        self.assertIsNotNone(trace.started_at)
        # Verify it parses as an ISO timestamp
        parsed_start = datetime.fromisoformat(trace.started_at)
        self.assertIsInstance(parsed_start, datetime)

    def test_03_run_completion_timestamp(self):
        """3. Run trace contains a valid ISO completion timestamp greater than or equal to started_at."""
        agent = Agent(registry=self.registry, telemetry_sink=self.sink)
        state = agent.run("Analyze Acme Plumbing and evaluate commercial opportunity")
        trace = self.sink.get_run(state.run_id)

        self.assertIsNotNone(trace.completed_at)
        parsed_start = datetime.fromisoformat(trace.started_at)
        parsed_completed = datetime.fromisoformat(trace.completed_at)
        self.assertGreaterEqual(parsed_completed, parsed_start)

    def test_04_total_duration_measurement(self):
        """4. Run trace records duration_ms as a positive float using monotonic clock."""
        agent = Agent(registry=self.registry, telemetry_sink=self.sink)
        state = agent.run("Analyze Acme Plumbing and evaluate commercial opportunity")
        trace = self.sink.get_run(state.run_id)

        self.assertIsInstance(trace.duration_ms, float)
        self.assertGreaterEqual(trace.duration_ms, 0.0)

    def test_05_intent_source_recorded(self):
        """5. Intent source is properly recorded in the trace (llm vs deterministic)."""
        # Test deterministic source
        interpreter = GoalInterpreter()
        agent = Agent(registry=self.registry, interpreter=interpreter, telemetry_sink=self.sink)
        with patch.object(self.registry, "execute") as mock_exec:
            mock_biz = Business(business_name="Austin Dental", website="https://austin.com", google_rating=4.5)
            mock_exec.return_value = CapabilityResult(
                success=True,
                capability_name="discover_prospects",
                data=DiscoverProspectsOutput(query="Dentist in Austin, TX", total_found=1, source="gmaps", businesses=[mock_biz])
            )
            state = agent.run("Find dental clinics in Austin, TX")
        trace = self.sink.get_run(state.run_id)

        self.assertEqual(trace.intent_source, "deterministic")
        self.assertIsNotNone(trace.intent_trace)
        self.assertEqual(trace.intent_trace.intent_source, "deterministic")
        self.assertEqual(trace.intent_type, IntentType.DISCOVER_PROSPECTS.value)
        self.assertFalse(trace.fallback_used)

    def test_06_llm_fallback_recorded(self):
        """6. When LLM interpretation fails, fallback is recorded in the trace."""
        mock_client = MagicMock(spec=LLMClient)
        mock_client.is_available = True
        mock_client.config = MagicMock(provider="gemini", model="gemini-2.5-pro")
        mock_client.generate_structured.side_effect = LLMUnavailableError("API rate limit exceeded")

        llm_interpreter = LLMIntentInterpreter(llm_client=mock_client)
        agent = Agent(registry=self.registry, interpreter=llm_interpreter, telemetry_sink=self.sink)

        with patch.object(self.registry, "execute") as mock_exec:
            mock_biz = Business(business_name="Austin Dental", website="https://austin.com", google_rating=4.5)
            mock_exec.return_value = CapabilityResult(
                success=True,
                capability_name="discover_prospects",
                data=DiscoverProspectsOutput(query="Dentist in Austin, TX", total_found=1, source="gmaps", businesses=[mock_biz])
            )
            state = agent.run("Find dental clinics in Austin, TX")

        trace = self.sink.get_run(state.run_id)
        self.assertEqual(trace.intent_source, "deterministic_fallback")
        self.assertTrue(trace.fallback_used)
        self.assertIsNotNone(trace.intent_trace)
        self.assertTrue(trace.intent_trace.fallback_used)
        self.assertEqual(trace.intent_trace.provider, "gemini")
        self.assertEqual(trace.intent_trace.model, "gemini-2.5-pro")
        self.assertIn("rate limit exceeded", trace.intent_trace.error)

    def test_07_planning_trace(self):
        """7. Planning phase records serializable PlanTrace with step counts and dependencies."""
        agent = Agent(registry=self.registry, telemetry_sink=self.sink)
        state = agent.run("Analyze Acme Plumbing and evaluate commercial opportunity")
        trace = self.sink.get_run(state.run_id)

        self.assertIsNotNone(trace.plan_trace)
        self.assertIsInstance(trace.plan_trace, PlanTrace)
        self.assertEqual(trace.plan_trace.step_count, 6)
        self.assertTrue(trace.plan_trace.validation_succeeded)
        self.assertGreater(len(trace.plan_trace.steps), 0)

        # Verify serializable PlanStepTrace structure
        step_trace = trace.plan_trace.steps[0]
        self.assertIsNotNone(step_trace.step_id)
        self.assertIsNotNone(step_trace.capability_name)
        self.assertIsInstance(step_trace.depends_on, list)

    def test_08_capability_start_event(self):
        """8. Capability execution records a STARTED event before calling the capability."""
        agent = Agent(registry=self.registry, telemetry_sink=self.sink)
        with patch.object(self.registry, "execute") as mock_exec:
            mock_biz = Business(business_name="Austin Dental", website="https://austin.com", google_rating=4.5)
            mock_exec.return_value = CapabilityResult(
                success=True,
                capability_name="discover_prospects",
                data=DiscoverProspectsOutput(query="Dentist in Austin, TX", total_found=1, source="gmaps", businesses=[mock_biz])
            )
            state = agent.run("Find dental clinics in Austin, TX")

        events = self.sink.get_step_events(state.run_id)
        start_events = [e for e in events if e.status == StepEventStatus.STARTED]
        self.assertGreater(len(start_events), 0)
        first_start = start_events[0]
        self.assertEqual(first_start.step_id, "step_discover")
        self.assertEqual(first_start.capability_name, "discover_prospects")
        self.assertEqual(first_start.capability_classification, "READ")
        self.assertIsNotNone(first_start.started_at)

    def test_09_capability_completion_event(self):
        """9. Successful capability execution records a COMPLETED event with duration_ms."""
        agent = Agent(registry=self.registry, telemetry_sink=self.sink)
        with patch.object(self.registry, "execute") as mock_exec:
            mock_biz = Business(business_name="Austin Dental", website="https://austin.com", google_rating=4.5)
            mock_exec.return_value = CapabilityResult(
                success=True,
                capability_name="discover_prospects",
                data=DiscoverProspectsOutput(query="Dentist in Austin, TX", total_found=1, source="gmaps", businesses=[mock_biz])
            )
            state = agent.run("Find dental clinics in Austin, TX")

        events = self.sink.get_step_events(state.run_id)
        comp_events = [e for e in events if e.status == StepEventStatus.COMPLETED]
        self.assertEqual(len(comp_events), 1)
        comp = comp_events[0]
        self.assertEqual(comp.step_id, "step_discover")
        self.assertEqual(comp.capability_name, "discover_prospects")
        self.assertIsNotNone(comp.completed_at)
        self.assertGreaterEqual(comp.duration_ms, 0.0)

    def test_10_capability_failure_event(self):
        """10. Failed capability execution records a FAILED event with ErrorCategory.CAPABILITY_ERROR."""
        agent = Agent(registry=self.registry, telemetry_sink=self.sink)
        with patch.object(self.registry, "execute") as mock_exec:
            mock_exec.return_value = CapabilityResult(
                success=False,
                capability_name="discover_prospects",
                error="Network timeout reaching directory API"
            )
            state = agent.run("Find dental clinics in Austin, TX")

        self.assertEqual(state.status, AgentStatus.FAILED)
        events = self.sink.get_step_events(state.run_id)
        fail_events = [e for e in events if e.status == StepEventStatus.FAILED]
        self.assertEqual(len(fail_events), 1)
        fail = fail_events[0]
        self.assertEqual(fail.error_type, ErrorCategory.CAPABILITY_ERROR)
        self.assertIn("Network timeout", fail.error_message)

        # Run trace should reflect failure
        trace = self.sink.get_run(state.run_id)
        self.assertEqual(trace.status, "FAILED")
        self.assertEqual(trace.failed_step_count, 1)
        self.assertEqual(trace.error_category, ErrorCategory.CAPABILITY_ERROR)

    def test_11_blocked_dependency_trace(self):
        """11. When a prerequisite step fails, dependent steps are recorded as BLOCKED events."""
        agent = Agent(registry=self.registry, telemetry_sink=self.sink)
        with patch.object(self.registry, "execute") as mock_exec:
            # Step 1 (discover_prospects) fails
            mock_exec.return_value = CapabilityResult(
                success=False,
                capability_name="discover_prospects",
                error="Google Maps scraping blocked"
            )
            # Goal requires discover + analyze
            state = agent.run("Discover and analyze dentists in Chicago")

        self.assertEqual(state.status, AgentStatus.FAILED)
        events = self.sink.get_step_events(state.run_id)
        blocked_events = [e for e in events if e.status == StepEventStatus.BLOCKED]
        self.assertGreater(len(blocked_events), 0)

        # Verify audit step was marked BLOCKED because discover failed
        audit_blocked = next((e for e in blocked_events if e.step_id == "step_audit"), None)
        self.assertIsNotNone(audit_blocked)
        self.assertEqual(audit_blocked.status, StepEventStatus.BLOCKED)
        self.assertEqual(audit_blocked.dependency_status.get("step_discover"), "FAILED")

        trace = self.sink.get_run(state.run_id)
        self.assertGreater(trace.blocked_step_count, 0)

    def test_12_evaluation_failure_trace(self):
        """12. Evaluation gate failure is categorized as EVALUATION_ERROR and blocks downstream drafting."""
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
            agent = Agent(registry=self.registry, telemetry_sink=self.sink)
            state = agent.run("Research a business and prepare an outreach opportunity")

        self.assertEqual(state.status, AgentStatus.FAILED)
        trace = self.sink.get_run(state.run_id)
        self.assertFalse(trace.evaluation_passed)
        self.assertEqual(trace.error_category, ErrorCategory.EVALUATION_ERROR)

        # Step events should contain the evaluation failure
        events = self.sink.get_step_events(state.run_id)
        eval_event = next((e for e in events if e.capability_name == "evaluate_ai_reasoning" and e.status == StepEventStatus.FAILED), None)
        self.assertIsNotNone(eval_event)
        self.assertEqual(eval_event.error_type, ErrorCategory.EVALUATION_ERROR)

        # Outreach draft step should be marked BLOCKED
        draft_event = next((e for e in events if e.capability_name == "render_outreach_drafts" and e.status == StepEventStatus.BLOCKED), None)
        self.assertIsNotNone(draft_event)

    def test_13_policy_rejection_trace(self):
        """13. Policy violation (unsupported external action) records POLICY_ERROR in trace."""
        agent = Agent(registry=self.registry, telemetry_sink=self.sink)
        # Direct email sending request violates safety policy
        state = agent.run("Find 5 dentists in Miami and blast them cold emails automatically")

        self.assertEqual(state.status, AgentStatus.FAILED)
        trace = self.sink.get_run(state.run_id)
        self.assertEqual(trace.error_category, ErrorCategory.POLICY_ERROR)
        self.assertIn("Unsupported external action", trace.final_outcome)
        self.assertIsNotNone(trace.intent_trace)
        self.assertTrue(trace.intent_trace.external_action_detected)

    def test_14_multiple_capability_events_preserve_execution_order(self):
        """14. Step events preserve precise sequential execution ordering."""
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
            agent = Agent(registry=self.registry, telemetry_sink=self.sink)
            state = agent.run("Research a business and prepare an outreach opportunity")

        events = self.sink.get_step_events(state.run_id)
        # 9 steps * 2 (STARTED + COMPLETED) = 18 events
        self.assertEqual(len(events), 18)

        # Verify alternating STARTED -> COMPLETED for each step
        for i in range(0, 18, 2):
            self.assertEqual(events[i].status, StepEventStatus.STARTED)
            self.assertEqual(events[i + 1].status, StepEventStatus.COMPLETED)
            self.assertEqual(events[i].step_id, events[i + 1].step_id)

    def test_15_telemetry_does_not_bypass_capability_registry(self):
        """15. Telemetry is purely observational; execution cannot bypass CapabilityRegistry."""
        empty_registry = CapabilityRegistry()
        agent = Agent(registry=empty_registry, telemetry_sink=self.sink)
        state = agent.run("Analyze Acme Plumbing and evaluate commercial opportunity")

        self.assertEqual(state.status, AgentStatus.FAILED)
        trace = self.sink.get_run(state.run_id)
        self.assertEqual(trace.status, "FAILED")
        self.assertEqual(trace.error_category, ErrorCategory.VALIDATION_ERROR)
        # Empty registry means 0 capability executions took place
        self.assertEqual(len(self.sink.get_step_events(state.run_id)), 0)

    def test_16_telemetry_does_not_contain_raw_capability_payloads(self):
        """16. Telemetry models contain strictly execution metadata, NOT raw HTML or DB rows."""
        sample_context = create_sample_context()
        with patch.object(self.registry, "execute") as mock_exec:
            mock_exec.side_effect = [
                CapabilityResult(success=True, capability_name="audit_website_tech", data={}),
                CapabilityResult(success=True, capability_name="enrich_leadership_social", data={}),
                CapabilityResult(success=True, capability_name="mine_business_intelligence", data={}),
                CapabilityResult(success=True, capability_name="calculate_health_and_scores", data={}),
                CapabilityResult(success=True, capability_name="assemble_prospect_context", data=sample_context),
                CapabilityResult(success=True, capability_name="synthesize_opportunity_analysis", data=create_sample_opportunity()),
                CapabilityResult(success=True, capability_name="formulate_outreach_strategy", data=create_sample_outreach()),
                CapabilityResult(success=True, capability_name="evaluate_ai_reasoning", data=create_sample_evaluation(passed=True)),
                CapabilityResult(success=True, capability_name="render_outreach_drafts", data=create_sample_draft()),
            ]
            agent = Agent(registry=self.registry, telemetry_sink=self.sink)
            state = agent.run("Research a business and prepare an outreach opportunity")

        trace = self.sink.get_run(state.run_id)
        dump = trace.model_dump()

        # Telemetry trace should not contain raw database tables or entire context structures
        self.assertNotIn("raw_html", dump)
        self.assertNotIn("scraped_content", dump)
        self.assertNotIn("evidence_store", dump)

        for event in trace.step_events:
            event_dump = event.model_dump()
            self.assertNotIn("result_payload", event_dump)
            self.assertNotIn("data", event_dump)

    def test_17_telemetry_does_not_contain_secrets(self):
        """17. Telemetry does not retain secrets or sensitive credential keys."""
        agent = Agent(registry=self.registry, telemetry_sink=self.sink)
        secret_params = {"api_key": "sk-super-secret-key-12345", "token": "bearer-token-abc"}
        with patch.object(self.registry, "execute") as mock_exec:
            mock_biz = Business(business_name="Austin Dental", website="https://austin.com", google_rating=4.5)
            mock_exec.return_value = CapabilityResult(
                success=True,
                capability_name="discover_prospects",
                data=DiscoverProspectsOutput(query="Dentist in Austin, TX", total_found=1, source="gmaps", businesses=[mock_biz])
            )
            state = agent.run("Find dental clinics in Austin, TX", initial_params=secret_params)
        trace = self.sink.get_run(state.run_id)

        dump_str = trace.model_dump_json()
        self.assertNotIn("sk-super-secret-key-12345", dump_str)
        self.assertNotIn("bearer-token-abc", dump_str)

    def test_18_existing_agent_state_behavior_remains_unchanged(self):
        """18. AgentState continues to expose all business models without modification."""
        sample_context = create_sample_context()
        sample_opp = create_sample_opportunity()
        sample_outreach = create_sample_outreach()
        sample_eval = create_sample_evaluation(passed=True)
        sample_draft = create_sample_draft()

        with patch.object(self.registry, "execute") as mock_exec:
            mock_exec.side_effect = [
                CapabilityResult(success=True, capability_name="audit_website_tech", data={}),
                CapabilityResult(success=True, capability_name="enrich_leadership_social", data={}),
                CapabilityResult(success=True, capability_name="mine_business_intelligence", data={}),
                CapabilityResult(success=True, capability_name="calculate_health_and_scores", data={}),
                CapabilityResult(success=True, capability_name="assemble_prospect_context", data=sample_context),
                CapabilityResult(success=True, capability_name="synthesize_opportunity_analysis", data=sample_opp),
                CapabilityResult(success=True, capability_name="formulate_outreach_strategy", data=sample_outreach),
                CapabilityResult(success=True, capability_name="evaluate_ai_reasoning", data=sample_eval),
                CapabilityResult(success=True, capability_name="render_outreach_drafts", data=sample_draft),
            ]
            agent = Agent(registry=self.registry, telemetry_sink=self.sink)
            state = agent.run("Research a business and prepare an outreach opportunity")

        # Existing AgentState fields remain fully intact
        self.assertEqual(state.status, AgentStatus.COMPLETED)
        self.assertEqual(state.prospect_context, sample_context)
        self.assertEqual(state.opportunity_analysis, sample_opp)
        self.assertEqual(state.outreach_strategy, sample_outreach)
        self.assertEqual(state.evaluation_result, sample_eval)
        self.assertEqual(state.outreach_draft, sample_draft)
        self.assertIsNotNone(state.final_response)
        self.assertEqual(state.final_response.run_id, state.run_id)

    def test_19_in_memory_telemetry_sink_filtering_and_clearing(self):
        """19. InMemoryTelemetrySink allows filtering by run_id, listing runs, and clearing."""
        sink = InMemoryTelemetrySink()
        t1 = AgentRunTrace(
            run_id="run_1",
            task_id="task_1",
            user_goal="Goal 1",
            status="COMPLETED",
            started_at=datetime.utcnow().isoformat(),
            completed_at=datetime.utcnow().isoformat(),
            duration_ms=10.0,
        )
        t2 = AgentRunTrace(
            run_id="run_2",
            task_id="task_2",
            user_goal="Goal 2",
            status="FAILED",
            started_at=datetime.utcnow().isoformat(),
            completed_at=datetime.utcnow().isoformat(),
            duration_ms=15.0,
        )
        e1 = CapabilityTraceEvent(
            run_id="run_1",
            step_id="s1",
            capability_name="audit_website_tech",
            status=StepEventStatus.COMPLETED,
        )
        e2 = CapabilityTraceEvent(
            run_id="run_2",
            step_id="s1",
            capability_name="audit_website_tech",
            status=StepEventStatus.FAILED,
        )

        sink.record_run(t1)
        sink.record_run(t2)
        sink.record_step(e1)
        sink.record_step(e2)

        self.assertEqual(len(sink.get_runs()), 2)
        self.assertEqual(sink.get_run("run_1").user_goal, "Goal 1")
        self.assertEqual(sink.get_run("run_2").status, "FAILED")

        # Filter step events by run_id
        r1_events = sink.get_step_events("run_1")
        self.assertEqual(len(r1_events), 1)
        self.assertEqual(r1_events[0].status, StepEventStatus.COMPLETED)

        # Clear sink
        sink.clear()
        self.assertEqual(len(sink.get_runs()), 0)
        self.assertEqual(len(sink.get_step_events()), 0)

    def test_20_ambiguous_goal_clarification_trace(self):
        """20. Ambiguous user requests emit clarification traces and state NEEDS_CLARIFICATION."""
        agent = Agent(registry=self.registry, telemetry_sink=self.sink)
        state = agent.run("Find dental clinics")

        self.assertEqual(state.status, AgentStatus.NEEDS_CLARIFICATION)
        trace = self.sink.get_run(state.run_id)
        self.assertEqual(trace.status, "NEEDS_CLARIFICATION")
        self.assertIsNotNone(trace.intent_trace)
        self.assertTrue(trace.intent_trace.clarification_required)
        self.assertIn("location", trace.final_outcome.lower())


if __name__ == "__main__":
    unittest.main()
