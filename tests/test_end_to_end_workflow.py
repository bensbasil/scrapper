"""
tests/test_end_to_end_workflow.py
---------------------------------
Phase 4D Integration Test Suite: End-to-End Agent Workflow & Evaluation Gate.
Validates the complete platform lifecycle across Phases 2 through 4C:
1. Known-business workflow succeeds with sufficient evidence.
2. Discovery workflow qualifies and selects candidates correctly.
3. Multi-prospect workflow preserves prospect isolation.
4. Missing website produces an honest partial-evidence result.
5. Evidence-acquisition failure is handled without corrupting other prospects.
6. Failed AI evaluation blocks draft rendering.
7. Passing evaluation permits draft rendering.
8. Deterministic fallback is explicitly represented and evaluated.
9. Insufficient evidence cannot silently pass as grounded reasoning.
10. Ambiguous intent returns clarification rather than executing an invented plan.
11. Unsupported external-send requests cannot dispatch messages.
12. Repeated runs maintain independent state and telemetry.
13. Batch-size limits remain enforced.
14. Capability and evaluation errors are correctly categorized.
15. Batch-level evaluation gate failure isolation across candidates.
16. Downstream stages cannot execute before required upstream results exist.
17. Final response envelope accurately distinguishes status outcomes.
"""

import unittest
from unittest.mock import MagicMock, patch
from typing import Dict, Any, List

from schemas.business import Business
from schemas.context import ProspectContext, ScoreCard, EvidenceItem
from schemas.ai import OpportunityAnalysis, CommercialRecommendation, OutreachStrategy
from schemas.outreach import OutreachDraft
from evaluation.models import EvaluationResult, ComponentEvaluation
from evaluation.datasets.fixtures import (
    get_strong_evidence_good_reasoning_fixture,
    get_unsupported_hallucination_fixture,
    get_insufficient_evidence_fixture,
    get_deterministic_fallback_fixture,
)
from application.capabilities.registry import CapabilityRegistry
from application.contracts.base import CapabilityResult
from application.contracts.outputs import DiscoverProspectsOutput
from agent.policies import PolicyEnforcer, ExecutionPolicyConfig
from agent.telemetry import (
    InMemoryTelemetrySink,
    CapabilityTraceEvent,
    StepEventStatus,
    ErrorCategory,
)
from agent.models import AgentStatus, StepStatus
from agent.state import AgentState
from agent.agent import Agent
from agent.intent import GoalInterpreter, AgentIntent, IntentType
from agent.qualification import (
    DeterministicProspectQualifier,
    QualificationPolicy,
)
from agent.prospects import (
    ProspectSet,
    QualifiedProspectSet,
    ProspectSelection,
    ProspectExecutionResult,
    ProspectBatchResult,
    ProspectBatchExecutor,
    BatchSizeLimitExceededError,
)
from ai.opportunity_reasoner import OpportunityReasoner
from ai.outreach_reasoner import OutreachReasoner
from ai.client import LLMClient
from ai.exceptions import LLMUnavailableError
from evaluation.evaluators import OpportunityEvaluator, OutreachEvaluator, EvaluationRunner


def make_test_business(
    name: str = "Apex Plumbing Pros",
    website: str = "https://apexplumbingpros.com",
    rating: float = 3.8,
    reviews: int = 45,
    category: str = "Plumber",
    address: str = "123 Pipe Lane, Chicago, IL",
) -> Business:
    return Business(
        business_name=name,
        website=website,
        google_rating=rating,
        review_count=reviews,
        category=category,
        address=address,
        city="Chicago",
    )


class TestEndToEndAgentWorkflowAndEvaluationGate(unittest.TestCase):
    """Integration verification across discovery, qualification, evidence, reasoning, eval, and drafts."""

    def setUp(self):
        self.registry = CapabilityRegistry.default_registry()
        self.sink = InMemoryTelemetrySink()
        self.agent = Agent(
            registry=self.registry,
            telemetry_sink=self.sink,
            interpreter=GoalInterpreter(),
        )

    # -------------------------------------------------------------------------
    # 1. Known-Business Workflow Succeeds with Sufficient Evidence
    # -------------------------------------------------------------------------
    def test_01_known_business_workflow_succeeds_with_sufficient_evidence(self):
        """1. Full known-business pipeline executes to completion when evaluation passes."""
        fixture = get_strong_evidence_good_reasoning_fixture()
        ctx = fixture["context"]
        opp = fixture["opportunity_analysis"]
        strat = fixture["outreach_strategy"]
        eval_pass = EvaluationResult(
            overall_score=0.92,
            grounding_score=0.95,
            relevance_score=0.90,
            consistency_score=0.92,
            evidence_coverage_score=0.90,
            hallucination_flags=[],
            issues=[],
            passed=True,
            structural_validity=True,
        )
        draft = OutreachDraft(
            business_name="Apex Plumbing Pros",
            outreach_angles=["Transform your customer booking on iOS"],
            cold_email_draft="Hi team, we noticed mobile booking bottlenecks...",
            whatsapp_draft="Hi, loved your plumbing work in Chicago...",
        )

        with patch.object(self.registry, "execute") as mock_exec:
            mock_exec.side_effect = [
                CapabilityResult(success=True, capability_name="audit_website_tech", data={}),
                CapabilityResult(success=True, capability_name="enrich_leadership_social", data={}),
                CapabilityResult(success=True, capability_name="mine_business_intelligence", data={}),
                CapabilityResult(success=True, capability_name="calculate_health_and_scores", data={}),
                CapabilityResult(success=True, capability_name="assemble_prospect_context", data=ctx),
                CapabilityResult(success=True, capability_name="synthesize_opportunity_analysis", data=opp),
                CapabilityResult(success=True, capability_name="formulate_outreach_strategy", data=strat),
                CapabilityResult(success=True, capability_name="evaluate_ai_reasoning", data=eval_pass),
                CapabilityResult(success=True, capability_name="render_outreach_drafts", data=draft),
            ]
            state = self.agent.run(
                user_goal="Research Apex Plumbing Pros and prepare consultative outreach drafts",
                initial_params={"business_name": "Apex Plumbing Pros", "website_url": "https://apexplumbingpros.com"}
            )

        self.assertEqual(state.status, AgentStatus.COMPLETED)
        self.assertIsNotNone(state.prospect_context)
        self.assertEqual(state.prospect_context.business.business_name, "Apex Plumbing Pros")
        self.assertIsNotNone(state.opportunity_analysis)
        self.assertIsNotNone(state.outreach_strategy)
        self.assertIsNotNone(state.evaluation_result)
        self.assertTrue(state.evaluation_result.passed)
        self.assertIsNotNone(state.outreach_draft)
        self.assertIn("Transform your customer booking", state.outreach_draft.outreach_angles[0])

        # Verify step statuses
        step_eval = state.plan.get_step("step_eval")
        step_draft = state.plan.get_step("step_draft")
        self.assertEqual(step_eval.status, StepStatus.COMPLETED)
        self.assertEqual(step_draft.status, StepStatus.COMPLETED)

        # Telemetry verification: 9 capability steps
        events = self.sink.get_step_events(run_id=state.run_id)
        self.assertTrue(any(e.capability_name == "render_outreach_drafts" and e.status == StepEventStatus.COMPLETED for e in events))

    # -------------------------------------------------------------------------
    # 2. Discovery Workflow Qualifies and Selects Candidates Correctly
    # -------------------------------------------------------------------------
    def test_02_discovery_workflow_qualifies_and_selects_candidates_correctly(self):
        """2. Discovered prospects are deterministically qualified and prioritized by policy."""
        b1 = make_test_business("Qualified A", "https://qa.com", rating=4.2, reviews=50)
        b2 = make_test_business("Qualified B", "https://qb.com", rating=3.9, reviews=20)
        b3 = make_test_business("No Website C", website=None, rating=4.0, reviews=30)
        b4 = make_test_business("Zero Reviews D", "https://qd.com", rating=1.0, reviews=0)

        pset = ProspectSet(prospects=[b1, b2, b3, b4], query="plumbers in Chicago")
        qualifier = DeterministicProspectQualifier(
            policy=QualificationPolicy(require_website=True, min_reviews=5)
        )
        qualified_set = qualifier.qualify_set(pset)

        self.assertEqual(qualified_set.total_discovered, 4)
        self.assertEqual(qualified_set.qualified_count, 2)
        self.assertEqual(qualified_set.disqualified_count, 2)

        # Selection selects only qualified candidates
        selection = ProspectSelection(max_prospects=2, ranking="qualification_score_desc")
        selected = selection.select(qualified_set)
        self.assertEqual(len(selected), 2)
        self.assertEqual({s.business_name for s in selected}, {"Qualified A", "Qualified B"})

    # -------------------------------------------------------------------------
    # 3. Multi-Prospect Workflow Preserves Prospect Isolation
    # -------------------------------------------------------------------------
    def test_03_multi_prospect_workflow_preserves_prospect_isolation(self):
        """3. Multiple prospects maintain distinct contexts, analyses, and scores without cross-leakage."""
        b_alpha = make_test_business("Alpha Dental", "https://alphadental.com", rating=4.5)
        b_beta = make_test_business("Beta HVAC", "https://betahvac.com", rating=3.2)
        pset = ProspectSet(prospects=[b_alpha, b_beta])

        ctx_alpha = get_strong_evidence_good_reasoning_fixture()["context"]
        ctx_alpha.business.business_name = "Alpha Dental"
        ctx_alpha.scores.sales_opportunity_score = 40.0

        ctx_beta = get_strong_evidence_good_reasoning_fixture()["context"]
        ctx_beta.business.business_name = "Beta HVAC"
        ctx_beta.scores.sales_opportunity_score = 90.0

        with patch.object(self.registry, "execute") as mock_exec:
            mock_exec.side_effect = [
                # Alpha evidence
                CapabilityResult(success=True, capability_name="audit_website_tech", data={}),
                CapabilityResult(success=True, capability_name="enrich_leadership_social", data={}),
                CapabilityResult(success=True, capability_name="mine_business_intelligence", data={}),
                CapabilityResult(success=True, capability_name="calculate_health_and_scores", data={}),
                CapabilityResult(success=True, capability_name="assemble_prospect_context", data=ctx_alpha),
                CapabilityResult(success=True, capability_name="synthesize_opportunity_analysis", data=MagicMock(confidence_score=0.8)),
                # Beta evidence
                CapabilityResult(success=True, capability_name="audit_website_tech", data={}),
                CapabilityResult(success=True, capability_name="enrich_leadership_social", data={}),
                CapabilityResult(success=True, capability_name="mine_business_intelligence", data={}),
                CapabilityResult(success=True, capability_name="calculate_health_and_scores", data={}),
                CapabilityResult(success=True, capability_name="assemble_prospect_context", data=ctx_beta),
                CapabilityResult(success=True, capability_name="synthesize_opportunity_analysis", data=MagicMock(confidence_score=0.9)),
            ]
            state = self.agent.run_prospect_batch(pset, selection=ProspectSelection(max_prospects=2))

        self.assertEqual(state.status, AgentStatus.COMPLETED)
        self.assertEqual(len(state.prospect_contexts), 2)
        self.assertEqual(state.prospect_contexts["Alpha Dental"].business.business_name, "Alpha Dental")
        self.assertEqual(state.prospect_contexts["Beta HVAC"].business.business_name, "Beta HVAC")
        self.assertNotEqual(
            state.prospect_contexts["Alpha Dental"].scores.sales_opportunity_score,
            state.prospect_contexts["Beta HVAC"].scores.sales_opportunity_score,
        )

        # Ranked results must prioritize higher opportunity score (Beta HVAC = 90.0 vs Alpha Dental = 40.0)
        ranked = state.batch_result.ranked_results("opportunity_score")
        self.assertEqual(ranked[0].prospect_id, "Beta HVAC")
        self.assertEqual(ranked[1].prospect_id, "Alpha Dental")

    # -------------------------------------------------------------------------
    # 4. Missing Website Produces Honest Partial-Evidence Result
    # -------------------------------------------------------------------------
    def test_04_missing_website_produces_honest_partial_evidence_result(self):
        """4. Prospect without website skips audit cleanly and produces honest partial context."""
        b_noweb = make_test_business("Offline Repairs", website=None, rating=4.1, reviews=18)
        pset = ProspectSet(prospects=[b_noweb])

        ctx_noweb = get_strong_evidence_good_reasoning_fixture()["context"]
        ctx_noweb.business = b_noweb
        ctx_noweb.evidence = [
            EvidenceItem(category="reputation", claim="Strong local review rating (4.1 stars)", source="GoogleMaps", confidence=0.9)
        ]

        invoked_caps = []
        def mock_exec(cap_name, params):
            invoked_caps.append(cap_name)
            if cap_name == "assemble_prospect_context":
                return CapabilityResult(success=True, capability_name=cap_name, data=ctx_noweb)
            return CapabilityResult(success=True, capability_name=cap_name, data={})

        with patch.object(self.registry, "execute", side_effect=mock_exec):
            state = self.agent.run_prospect_batch(pset)

        self.assertEqual(state.status, AgentStatus.COMPLETED)
        self.assertNotIn("audit_website_tech", invoked_caps)
        self.assertNotIn("enrich_leadership_social", invoked_caps)
        self.assertIn("mine_business_intelligence", invoked_caps)
        self.assertIn("assemble_prospect_context", invoked_caps)
        self.assertIsNotNone(state.batch_result.results[0].prospect_context)
        self.assertIsNone(state.batch_result.results[0].prospect_context.business.website)

    # -------------------------------------------------------------------------
    # 5. Evidence-Acquisition Failure Handled Without Corrupting Other Prospects
    # -------------------------------------------------------------------------
    def test_05_evidence_acquisition_failure_handled_without_corrupting_other_prospects(self):
        """5. Unrecoverable scraping failure on Prospect B does not abort Prospect A or C."""
        b1 = make_test_business("Prospect 1 (OK)")
        b2 = make_test_business("Prospect 2 (Fails)")
        b3 = make_test_business("Prospect 3 (OK)")
        pset = ProspectSet(prospects=[b1, b2, b3])

        ctx1 = get_strong_evidence_good_reasoning_fixture()["context"]
        ctx3 = get_strong_evidence_good_reasoning_fixture()["context"]

        with patch.object(self.registry, "execute") as mock_exec:
            mock_exec.side_effect = [
                # Prospect 1: succeeds
                CapabilityResult(success=True, capability_name="audit_website_tech", data={}),
                CapabilityResult(success=True, capability_name="enrich_leadership_social", data={}),
                CapabilityResult(success=True, capability_name="mine_business_intelligence", data={}),
                CapabilityResult(success=True, capability_name="calculate_health_and_scores", data={}),
                CapabilityResult(success=True, capability_name="assemble_prospect_context", data=ctx1),
                CapabilityResult(success=True, capability_name="synthesize_opportunity_analysis", data=MagicMock()),
                # Prospect 2: audit fails
                CapabilityResult(success=False, capability_name="audit_website_tech", error="TCP connect timeout (110)"),
                # Prospect 3: succeeds
                CapabilityResult(success=True, capability_name="audit_website_tech", data={}),
                CapabilityResult(success=True, capability_name="enrich_leadership_social", data={}),
                CapabilityResult(success=True, capability_name="mine_business_intelligence", data={}),
                CapabilityResult(success=True, capability_name="calculate_health_and_scores", data={}),
                CapabilityResult(success=True, capability_name="assemble_prospect_context", data=ctx3),
                CapabilityResult(success=True, capability_name="synthesize_opportunity_analysis", data=MagicMock()),
            ]
            state = self.agent.run_prospect_batch(pset)

        self.assertEqual(state.batch_result.completed_count, 2)
        self.assertEqual(state.batch_result.failed_count, 1)

        res1 = next(r for r in state.batch_result.results if r.prospect_id == "Prospect 1 (OK)")
        res2 = next(r for r in state.batch_result.results if r.prospect_id == "Prospect 2 (Fails)")
        res3 = next(r for r in state.batch_result.results if r.prospect_id == "Prospect 3 (OK)")

        self.assertEqual(res1.status, "COMPLETED")
        self.assertEqual(res2.status, "FAILED")
        self.assertIn("audit_website_tech", res2.failed_steps)
        self.assertTrue(any("TCP connect timeout" in e for e in res2.errors))
        self.assertEqual(res3.status, "COMPLETED")

    # -------------------------------------------------------------------------
    # 6. Failed AI Evaluation Blocks Draft Rendering
    # -------------------------------------------------------------------------
    def test_06_failed_ai_evaluation_blocks_draft_rendering(self):
        """6. Execution controller stops cold outreach draft rendering when evaluation fails."""
        failing_eval = EvaluationResult(
            overall_score=0.45,
            grounding_score=0.30,
            relevance_score=0.60,
            consistency_score=0.40,
            evidence_coverage_score=0.50,
            hallucination_flags=["[CONTRADICTION] Fabricated missing SSL claim"],
            issues=["Severe hallucination regarding SSL certificate"],
            passed=False,
            structural_validity=True,
        )

        with patch.object(self.registry, "execute") as mock_exec:
            mock_exec.side_effect = [
                CapabilityResult(success=True, capability_name="audit_website_tech", data={}),
                CapabilityResult(success=True, capability_name="enrich_leadership_social", data={}),
                CapabilityResult(success=True, capability_name="mine_business_intelligence", data={}),
                CapabilityResult(success=True, capability_name="calculate_health_and_scores", data={}),
                CapabilityResult(success=True, capability_name="assemble_prospect_context", data=get_strong_evidence_good_reasoning_fixture()["context"]),
                CapabilityResult(success=True, capability_name="synthesize_opportunity_analysis", data=get_strong_evidence_good_reasoning_fixture()["opportunity_analysis"]),
                CapabilityResult(success=True, capability_name="formulate_outreach_strategy", data=get_strong_evidence_good_reasoning_fixture()["outreach_strategy"]),
                # Evaluation gate returns passed=False
                CapabilityResult(success=True, capability_name="evaluate_ai_reasoning", data=failing_eval),
            ]
            state = self.agent.run("Research Apex and prepare outreach")

        self.assertEqual(state.status, AgentStatus.FAILED)
        self.assertIsNone(state.outreach_draft)
        self.assertTrue(any("Evaluation gate failed" in err for err in state.errors))

        # Downstream draft step must be marked BLOCKED
        draft_step = state.plan.get_step("step_draft")
        self.assertEqual(draft_step.status, StepStatus.BLOCKED)

        # Telemetry must contain EVALUATION_ERROR
        events = self.sink.get_step_events(run_id=state.run_id)
        eval_event = next(e for e in events if e.capability_name == "evaluate_ai_reasoning" and e.status == StepEventStatus.FAILED)
        self.assertEqual(eval_event.error_type, ErrorCategory.EVALUATION_ERROR)

    # -------------------------------------------------------------------------
    # 7. Passing Evaluation Permits Draft Rendering
    # -------------------------------------------------------------------------
    def test_07_passing_evaluation_permits_draft_rendering(self):
        """7. High quality reasoning passing evaluation unlocks outreach draft rendering."""
        passing_eval = EvaluationResult(
            overall_score=0.88,
            grounding_score=0.90,
            relevance_score=0.85,
            consistency_score=0.90,
            evidence_coverage_score=0.85,
            hallucination_flags=[],
            issues=[],
            passed=True,
            structural_validity=True,
        )
        sample_draft = OutreachDraft(
            business_name="Apex",
            outreach_angles=["Streamline mobile booking for Apex Plumbing"],
            cold_email_draft="Verified conversion friction on iOS booking form...",
            whatsapp_draft="Connecting regarding digital conversion...",
        )

        with patch.object(self.registry, "execute") as mock_exec:
            mock_exec.side_effect = [
                CapabilityResult(success=True, capability_name="audit_website_tech", data={}),
                CapabilityResult(success=True, capability_name="enrich_leadership_social", data={}),
                CapabilityResult(success=True, capability_name="mine_business_intelligence", data={}),
                CapabilityResult(success=True, capability_name="calculate_health_and_scores", data={}),
                CapabilityResult(success=True, capability_name="assemble_prospect_context", data=get_strong_evidence_good_reasoning_fixture()["context"]),
                CapabilityResult(success=True, capability_name="synthesize_opportunity_analysis", data=get_strong_evidence_good_reasoning_fixture()["opportunity_analysis"]),
                CapabilityResult(success=True, capability_name="formulate_outreach_strategy", data=get_strong_evidence_good_reasoning_fixture()["outreach_strategy"]),
                CapabilityResult(success=True, capability_name="evaluate_ai_reasoning", data=passing_eval),
                CapabilityResult(success=True, capability_name="render_outreach_drafts", data=sample_draft),
            ]
            state = self.agent.run("Research Apex and prepare outreach")

        self.assertEqual(state.status, AgentStatus.COMPLETED)
        self.assertIsNotNone(state.outreach_draft)
        self.assertEqual(state.plan.get_step("step_draft").status, StepStatus.COMPLETED)

    # -------------------------------------------------------------------------
    # 8. Deterministic Fallback Is Explicitly Represented and Evaluated
    # -------------------------------------------------------------------------
    def test_08_deterministic_fallback_is_explicitly_represented_and_evaluated(self):
        """8. When LLM is unavailable, reasoners produce deterministic fallback with explicit metadata."""
        ctx = get_deterministic_fallback_fixture()["context"]
        mock_unavailable_llm = MagicMock(spec=LLMClient)
        mock_unavailable_llm.is_available = False

        opp_reasoner = OpportunityReasoner(llm_client=mock_unavailable_llm)
        opp_res = opp_reasoner.reason(ctx)
        self.assertEqual(opp_res.reasoning_mode, "deterministic_fallback")
        self.assertIsNotNone(opp_res.strategic_pitch_angle)

        out_reasoner = OutreachReasoner(llm_client=mock_unavailable_llm)
        out_res = out_reasoner.reason(ctx, opp_res)
        self.assertEqual(out_res.reasoning_mode, "deterministic_fallback")

        # Evaluate deterministic fallback
        eval_runner = EvaluationRunner()
        eval_res = eval_runner.evaluate(ctx, opp_res, out_res)
        self.assertTrue(eval_res.structural_validity)
        self.assertNotIn("must be 'ai' or 'deterministic_fallback'", "".join(eval_res.issues))

    # -------------------------------------------------------------------------
    # 9. Insufficient Evidence Cannot Silently Pass as Grounded Reasoning
    # -------------------------------------------------------------------------
    def test_09_insufficient_evidence_cannot_silently_pass_as_grounded_reasoning(self):
        """9. Prospect with zero evidence cannot produce high-confidence ungrounded diagnosis."""
        ctx = get_insufficient_evidence_fixture()["context"]
        ctx.evidence = []  # Zero evidence items
        ctx.scores.sales_opportunity_score = 0.0

        # Attempting ungrounded high-confidence reasoning
        hallucinated_opp = OpportunityAnalysis(
            executive_diagnosis="Prospect has broken SSL certificate, slow 9.2s load speed, and 50 negative reviews.",
            primary_pain_category="technical",
            recommendations=[
                CommercialRecommendation(
                    service_name="SSL Renewal",
                    target_problem="Missing SSL certificate",
                    commercial_impact="Fixes security warning",
                    suggested_pricing_tier="entry",
                )
            ],
            strategic_pitch_angle="Technical Emergency: Fix missing SSL",
            cited_evidence_points=["Missing SSL certificate", "Slow page speed 9.2s"],
            confidence_score=0.95,
            reasoning_mode="ai",
            evidence_sufficiency="sufficient",
        )

        evaluator = OpportunityEvaluator()
        comp_eval, flags = evaluator.evaluate(ctx, hallucinated_opp)
        self.assertFalse(comp_eval.passed)
        self.assertLess(comp_eval.grounding_score, 0.40)
        self.assertTrue(any("unsupported_cited_evidence" in f.flag_type for f in flags))

    # -------------------------------------------------------------------------
    # 10. Ambiguous Intent Returns Clarification Without Executing Plan
    # -------------------------------------------------------------------------
    def test_10_ambiguous_intent_returns_clarification_rather_than_executing_plan(self):
        """10. Underspecified goal halts immediately with structured clarification request."""
        state = self.agent.run("find businesses")
        self.assertEqual(state.status, AgentStatus.NEEDS_CLARIFICATION)
        self.assertIsNotNone(state.clarification_request)
        self.assertIn("location", state.clarification_request.missing_information)
        self.assertEqual(state.execution_count, 0)
        self.assertEqual(len(state.completed_steps), 0)

    # -------------------------------------------------------------------------
    # 11. Unsupported External-Send Requests Cannot Dispatch Messages
    # -------------------------------------------------------------------------
    def test_11_unsupported_external_send_requests_cannot_dispatch_messages(self):
        """11. Direct external dispatch/send requests are intercepted before execution."""
        state = self.agent.run("Send WhatsApp messages to all dentists in Austin")
        self.assertEqual(state.status, AgentStatus.FAILED)
        self.assertTrue(any("Unsupported external action" in e for e in state.errors))
        self.assertEqual(state.execution_count, 0)

    # -------------------------------------------------------------------------
    # 12. Repeated Runs Maintain Independent State and Telemetry
    # -------------------------------------------------------------------------
    def test_12_repeated_runs_maintain_independent_state_and_telemetry(self):
        """12. Consecutive runs with the same Agent instance do not leak state or trace events."""
        ctx1 = get_strong_evidence_good_reasoning_fixture()["context"]
        ctx1.business.business_name = "Company One"

        ctx2 = get_strong_evidence_good_reasoning_fixture()["context"]
        ctx2.business.business_name = "Company Two"

        with patch.object(self.registry, "execute") as mock_exec:
            mock_exec.side_effect = [
                CapabilityResult(success=True, capability_name="audit_website_tech", data={}),
                CapabilityResult(success=True, capability_name="enrich_leadership_social", data={}),
                CapabilityResult(success=True, capability_name="mine_business_intelligence", data={}),
                CapabilityResult(success=True, capability_name="calculate_health_and_scores", data={}),
                CapabilityResult(success=True, capability_name="assemble_prospect_context", data=ctx1),
                CapabilityResult(success=True, capability_name="synthesize_opportunity_analysis", data=MagicMock()),
            ]
            state1 = self.agent.run("Analyze Company One", initial_params={"business_name": "Company One"})

        with patch.object(self.registry, "execute") as mock_exec:
            mock_exec.side_effect = [
                CapabilityResult(success=True, capability_name="audit_website_tech", data={}),
                CapabilityResult(success=True, capability_name="enrich_leadership_social", data={}),
                CapabilityResult(success=True, capability_name="mine_business_intelligence", data={}),
                CapabilityResult(success=True, capability_name="calculate_health_and_scores", data={}),
                CapabilityResult(success=True, capability_name="assemble_prospect_context", data=ctx2),
                CapabilityResult(success=True, capability_name="synthesize_opportunity_analysis", data=MagicMock()),
            ]
            state2 = self.agent.run("Analyze Company Two", initial_params={"business_name": "Company Two"})

        self.assertNotEqual(state1.run_id, state2.run_id)
        self.assertEqual(state1.prospect_context.business.business_name, "Company One")
        self.assertEqual(state2.prospect_context.business.business_name, "Company Two")

        events1 = self.sink.get_step_events(run_id=state1.run_id)
        events2 = self.sink.get_step_events(run_id=state2.run_id)
        self.assertTrue(all(e.run_id == state1.run_id for e in events1))
        self.assertTrue(all(e.run_id == state2.run_id for e in events2))

    # -------------------------------------------------------------------------
    # 13. Batch-Size Limits Remain Enforced
    # -------------------------------------------------------------------------
    def test_13_batch_size_limits_remain_enforced(self):
        """13. Multi-prospect executor clamps batch count to safety boundary or raises with strict limit."""
        businesses = [make_test_business(f"Biz {i}") for i in range(25)]
        pset = ProspectSet(prospects=businesses)

        executor = ProspectBatchExecutor(registry=self.registry, max_prospects_per_run=10)
        selection = ProspectSelection(max_prospects=25)

        with patch.object(executor, "_execute_single_prospect") as mock_p:
            mock_p.return_value = ProspectExecutionResult(
                prospect_id="mock", business=businesses[0], status="COMPLETED"
            )
            batch_res = executor.execute_batch(pset, selection=selection)

        self.assertEqual(batch_res.selected_count, 10)
        self.assertEqual(len(batch_res.results), 10)

        # Strict limit mode
        strict_executor = ProspectBatchExecutor(registry=self.registry, max_prospects_per_run=10, strict_limit=True)
        with self.assertRaises(BatchSizeLimitExceededError):
            strict_executor.execute_batch(pset, selection=ProspectSelection(max_prospects=25))

    # -------------------------------------------------------------------------
    # 14. Capability and Evaluation Errors Correctly Categorized
    # -------------------------------------------------------------------------
    def test_14_capability_and_evaluation_errors_correctly_categorized(self):
        """14. Error categories distinguish CAPABILITY_ERROR from EVALUATION_ERROR and POLICY_ERROR."""
        # 1. Capability Error
        with patch.object(self.registry, "execute") as mock_exec:
            mock_exec.return_value = CapabilityResult(success=False, capability_name="audit_website_tech", error="Scraper failed")
            state = self.agent.run("Audit Apex Plumbing", initial_params={"business_name": "Apex", "website_url": "https://apex.com"})
            self.assertEqual(state.status, AgentStatus.FAILED)
            events = self.sink.get_step_events(run_id=state.run_id)
            err_event = next(e for e in events if e.status == StepEventStatus.FAILED)
            self.assertEqual(err_event.error_type, ErrorCategory.CAPABILITY_ERROR)

        # 2. Evaluation Gate Error
        self.sink.clear()
        failing_eval = EvaluationResult(
            overall_score=0.45,
            grounding_score=0.40,
            relevance_score=0.50,
            consistency_score=0.45,
            evidence_coverage_score=0.40,
            passed=False,
            issues=["Quality gate failed"],
            structural_validity=True
        )
        with patch.object(self.registry, "execute") as mock_exec:
            mock_exec.side_effect = [
                CapabilityResult(success=True, capability_name="audit_website_tech", data={}),
                CapabilityResult(success=True, capability_name="enrich_leadership_social", data={}),
                CapabilityResult(success=True, capability_name="mine_business_intelligence", data={}),
                CapabilityResult(success=True, capability_name="calculate_health_and_scores", data={}),
                CapabilityResult(success=True, capability_name="assemble_prospect_context", data=get_strong_evidence_good_reasoning_fixture()["context"]),
                CapabilityResult(success=True, capability_name="synthesize_opportunity_analysis", data=get_strong_evidence_good_reasoning_fixture()["opportunity_analysis"]),
                CapabilityResult(success=True, capability_name="formulate_outreach_strategy", data=get_strong_evidence_good_reasoning_fixture()["outreach_strategy"]),
                CapabilityResult(success=True, capability_name="evaluate_ai_reasoning", data=failing_eval),
            ]
            state2 = self.agent.run("Research Apex and prepare outreach")
            self.assertEqual(state2.status, AgentStatus.FAILED)
            events2 = self.sink.get_step_events(run_id=state2.run_id)
            eval_event = next(e for e in events2 if e.capability_name == "evaluate_ai_reasoning" and e.status == StepEventStatus.FAILED)
            self.assertEqual(eval_event.error_type, ErrorCategory.EVALUATION_ERROR)

    # -------------------------------------------------------------------------
    # 15. Batch-Level Evaluation Gate Failure Isolation Across Candidates
    # -------------------------------------------------------------------------
    def test_15_batch_level_evaluation_failure_isolation(self):
        """15. Candidate A failing evaluation does not block Candidate B from receiving outreach drafts."""
        b1 = make_test_business("Candidate A (Eval Fails)")
        b2 = make_test_business("Candidate B (Eval Passes)")
        pset = ProspectSet(prospects=[b1, b2])

        ctx1 = get_strong_evidence_good_reasoning_fixture()["context"]
        ctx2 = get_strong_evidence_good_reasoning_fixture()["context"]
        opp = get_strong_evidence_good_reasoning_fixture()["opportunity_analysis"]
        strat = get_strong_evidence_good_reasoning_fixture()["outreach_strategy"]

        eval_fail = EvaluationResult(
            overall_score=0.45,
            grounding_score=0.40,
            relevance_score=0.50,
            consistency_score=0.45,
            evidence_coverage_score=0.40,
            passed=False,
            issues=["Candidate A hallucinated BBB claims"],
            structural_validity=True
        )
        eval_pass = EvaluationResult(
            overall_score=0.90,
            grounding_score=0.92,
            relevance_score=0.88,
            consistency_score=0.90,
            evidence_coverage_score=0.90,
            passed=True,
            structural_validity=True
        )
        draft = OutreachDraft(
            business_name="Candidate B (Eval Passes)",
            outreach_angles=["Draft for Candidate B"],
            cold_email_draft="Body",
            whatsapp_draft="WhatsApp",
        )

        with patch.object(self.registry, "execute") as mock_exec:
            mock_exec.side_effect = [
                # Candidate A: evidence + opp + outreach + eval (fails, no draft)
                CapabilityResult(success=True, capability_name="audit_website_tech", data={}),
                CapabilityResult(success=True, capability_name="enrich_leadership_social", data={}),
                CapabilityResult(success=True, capability_name="mine_business_intelligence", data={}),
                CapabilityResult(success=True, capability_name="calculate_health_and_scores", data={}),
                CapabilityResult(success=True, capability_name="assemble_prospect_context", data=ctx1),
                CapabilityResult(success=True, capability_name="synthesize_opportunity_analysis", data=opp),
                CapabilityResult(success=True, capability_name="formulate_outreach_strategy", data=strat),
                CapabilityResult(success=True, capability_name="evaluate_ai_reasoning", data=eval_fail),
                # Candidate B: evidence + opp + outreach + eval (passes) + draft
                CapabilityResult(success=True, capability_name="audit_website_tech", data={}),
                CapabilityResult(success=True, capability_name="enrich_leadership_social", data={}),
                CapabilityResult(success=True, capability_name="mine_business_intelligence", data={}),
                CapabilityResult(success=True, capability_name="calculate_health_and_scores", data={}),
                CapabilityResult(success=True, capability_name="assemble_prospect_context", data=ctx2),
                CapabilityResult(success=True, capability_name="synthesize_opportunity_analysis", data=opp),
                CapabilityResult(success=True, capability_name="formulate_outreach_strategy", data=strat),
                CapabilityResult(success=True, capability_name="evaluate_ai_reasoning", data=eval_pass),
                CapabilityResult(success=True, capability_name="render_outreach_drafts", data=draft),
            ]
            state = self.agent.run_prospect_batch(pset, include_outreach=True)

        self.assertEqual(state.batch_result.completed_count, 1)
        self.assertEqual(state.batch_result.failed_count, 1)

        resA = next(r for r in state.batch_result.results if r.prospect_id == "Candidate A (Eval Fails)")
        resB = next(r for r in state.batch_result.results if r.prospect_id == "Candidate B (Eval Passes)")

        self.assertEqual(resA.status, "FAILED")
        self.assertIsNone(resA.outreach_draft)
        self.assertIn("evaluate_ai_reasoning", resA.failed_steps)

        self.assertEqual(resB.status, "COMPLETED")
        self.assertIsNotNone(resB.outreach_draft)
        self.assertEqual(resB.outreach_draft.outreach_angles[0], "Draft for Candidate B")

    # -------------------------------------------------------------------------
    # 16. Downstream Stages Cannot Execute Before Required Upstream Results
    # -------------------------------------------------------------------------
    def test_16_downstream_stages_cannot_execute_before_required_upstream_results(self):
        """16. Prerequisite step failure cascades BLOCKED status to all dependents in DAG."""
        with patch.object(self.registry, "execute") as mock_exec:
            # Audit fails immediately
            mock_exec.side_effect = [
                CapabilityResult(success=False, capability_name="audit_website_tech", error="Network DNS failure"),
            ]
            state = self.agent.run("Research Apex and prepare outreach")

        self.assertEqual(state.status, AgentStatus.FAILED)
        plan = state.plan
        # step_score depends on step_audit -> BLOCKED
        self.assertEqual(plan.get_step("step_score").status, StepStatus.BLOCKED)
        # step_context depends on step_score -> BLOCKED
        self.assertEqual(plan.get_step("step_context").status, StepStatus.BLOCKED)
        # step_opp depends on step_context -> BLOCKED
        self.assertEqual(plan.get_step("step_opp").status, StepStatus.BLOCKED)
        # step_draft depends on step_eval -> BLOCKED
        self.assertEqual(plan.get_step("step_draft").status, StepStatus.BLOCKED)

    # -------------------------------------------------------------------------
    # 17. Final Response Envelope Accurately Distinguishes Status Outcomes
    # -------------------------------------------------------------------------
    def test_17_final_response_distinguishes_status_outcomes(self):
        """17. AgentFinalResponse accurately reflects completed, failed, and clarification states."""
        # Completed (mocked to avoid external network requests)
        with patch.object(self.registry, "execute") as mock_exec:
            mock_exec.return_value = CapabilityResult(success=True, capability_name="audit_website_tech", data={})
            state_comp = self.agent.run("Analyze Apex Plumbing", initial_params={"business_name": "Apex", "website_url": "https://apex.com"})
        self.assertEqual(state_comp.final_response.status, "COMPLETED")

        # Clarification
        state_clar = self.agent.run("find businesses")
        self.assertEqual(state_clar.final_response.status, "NEEDS_CLARIFICATION")
        self.assertIsNotNone(state_clar.final_response.clarification_question)

        # Failed
        state_fail = self.agent.run("Send WhatsApp messages to all dentists")
        self.assertEqual(state_fail.final_response.status, "FAILED")
        self.assertTrue(len(state_fail.final_response.errors) > 0)


if __name__ == "__main__":
    unittest.main()
