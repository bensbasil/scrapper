"""
tests/test_prospect_batch.py
----------------------------
Unit test suite for Phase 4A Prospect Set & Controlled Multi-Prospect Execution.
Validates:
1. ProspectSet creation and methods
2. ProspectSelection creation and filtering
3. Empty prospect set handling
4. Single prospect batch processing
5. Multiple prospects batch processing
6. Batch size limit constraint
7. Requested count above limit with strict rejection
8. Successful multi-prospect batch execution
9. Single prospect failure isolation
10. Multiple prospect failures isolation
11. Failure isolation guarantees (no cross-prospect failure cascade)
12. Policy violation / safety handling in batch
13. ProspectExecutionResult creation and structure
14. ProspectBatchResult creation and structure
15. Ranking using existing opportunity signals (opportunity_score, rating_asc, etc.)
16. Strict reuse of canonical schemas.business.Business (no duplicate Business model)
17. Registry-exclusive capability execution (no infrastructure bypass)
18. Batch-level telemetry recording (batch_id in trace events)
19. Prospect-specific telemetry recording (prospect_id in trace events)
20. Agent run_prospect_batch integration
21. Agent constrains excessive batch requests (e.g. 5000 businesses)
22. Backward compatibility with state.prospects and existing discovery
"""

import unittest
from datetime import datetime
from unittest.mock import MagicMock, patch
from typing import Dict, Any, List

from schemas.business import Business
from schemas.context import ProspectContext, ScoreCard
from schemas.ai import OpportunityAnalysis, CommercialRecommendation, OutreachStrategy
from schemas.outreach import OutreachDraft
from evaluation.models import EvaluationResult
from evaluation.datasets.fixtures import get_strong_evidence_good_reasoning_fixture
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
from agent.state import AgentState
from agent.models import AgentStatus
from agent.agent import Agent
from agent.prospects import (
    ProspectSet,
    ProspectSelection,
    ProspectExecutionResult,
    ProspectBatchResult,
    ProspectBatchExecutor,
    BatchSizeLimitExceededError,
)


def create_sample_business(name: str, rating: float = 4.2, reviews: int = 40, website: str = "https://example.com", category: str = "Plumbing") -> Business:
    return Business(
        business_name=name,
        website=website,
        google_rating=rating,
        review_count=reviews,
        category=category,
        address="123 Main St, Chicago, IL",
        city="Chicago"
    )


def create_sample_context(score: float = 75.0) -> ProspectContext:
    fixture = get_strong_evidence_good_reasoning_fixture()
    ctx = fixture["context"]
    # Adjust sales opportunity score
    ctx.scores.sales_opportunity_score = score
    return ctx


def create_sample_opportunity(confidence: float = 0.95) -> OpportunityAnalysis:
    fixture = get_strong_evidence_good_reasoning_fixture()
    opp = fixture["opportunity_analysis"]
    opp.confidence_score = confidence
    return opp


class TestProspectSetAndBatchExecution(unittest.TestCase):
    """Phase 4A multi-prospect execution verification suite."""

    def setUp(self):
        self.registry = CapabilityRegistry.default_registry()
        self.sink = InMemoryTelemetrySink()

    def test_01_prospect_set_creation(self):
        """1. ProspectSet creation from raw businesses and from DiscoverProspectsOutput."""
        b1 = create_sample_business("Alpha Plumbing", rating=4.5)
        b2 = create_sample_business("Beta Plumbing", rating=3.8)

        pset = ProspectSet(
            query="plumbers in Chicago",
            location="Chicago",
            total_discovered=2,
            prospects=[b1, b2]
        )
        self.assertEqual(len(pset), 2)
        self.assertEqual(pset.total_discovered, 2)
        self.assertEqual(pset.get_prospect("Alpha Plumbing").business_name, "Alpha Plumbing")
        self.assertIsNone(pset.get_prospect("Gamma Plumbing"))

        # From discovery output
        disc_output = DiscoverProspectsOutput(
            query="plumbers",
            total_found=2,
            source="gmaps",
            businesses=[b1, b2]
        )
        pset_disc = ProspectSet.from_discovery_output(disc_output, location="Chicago")
        self.assertEqual(pset_disc.source, "gmaps")
        self.assertEqual(len(pset_disc.prospects), 2)

    def test_02_prospect_selection_creation(self):
        """2. ProspectSelection filters and sorts candidate prospects accurately."""
        b1 = create_sample_business("Alpha Plumbing", rating=4.8, reviews=10, category="Plumbing")
        b2 = create_sample_business("Beta Plumbing", rating=3.2, reviews=50, category="Plumbing")
        b3 = create_sample_business("Gamma Dental", rating=4.5, reviews=20, category="Dental")
        pset = ProspectSet(prospects=[b1, b2, b3])

        # Filter by required industry and sort by rating ascending (lowest first)
        sel = ProspectSelection(
            max_prospects=2,
            required_industry="Plumbing",
            ranking="rating_asc"
        )
        selected = sel.select(pset)
        self.assertEqual(len(selected), 2)
        self.assertEqual(selected[0].business_name, "Beta Plumbing")  # 3.2 rating first
        self.assertEqual(selected[1].business_name, "Alpha Plumbing")  # 4.8 rating second

        # Filter by minimum score
        sel_score = ProspectSelection(max_prospects=5, minimum_score=4.0)
        selected_score = sel_score.select(pset)
        self.assertEqual(len(selected_score), 2)  # b1 (4.8) and b3 (4.5)

    def test_03_empty_prospect_set(self):
        """3. Empty prospect set is safely handled without errors."""
        empty_pset = ProspectSet(prospects=[])
        sel = ProspectSelection(max_prospects=5)
        self.assertEqual(len(sel.select(empty_pset)), 0)

        executor = ProspectBatchExecutor(registry=self.registry, telemetry_sink=self.sink)
        result = executor.execute_batch(empty_pset, sel)
        self.assertEqual(result.selected_count, 0)
        self.assertEqual(result.completed_count, 0)
        self.assertEqual(len(result.results), 0)

    def test_04_single_prospect(self):
        """4. Single prospect batch processes through deep analysis and completes."""
        b1 = create_sample_business("Alpha Motors")
        pset = ProspectSet(prospects=[b1])

        with patch.object(self.registry, "execute") as mock_exec:
            mock_exec.side_effect = [
                CapabilityResult(success=True, capability_name="audit_website_tech", data={}),
                CapabilityResult(success=True, capability_name="enrich_leadership_social", data={}),
                CapabilityResult(success=True, capability_name="mine_business_intelligence", data={}),
                CapabilityResult(success=True, capability_name="calculate_health_and_scores", data={}),
                CapabilityResult(success=True, capability_name="assemble_prospect_context", data=create_sample_context(80.0)),
                CapabilityResult(success=True, capability_name="synthesize_opportunity_analysis", data=create_sample_opportunity()),
            ]
            executor = ProspectBatchExecutor(registry=self.registry, telemetry_sink=self.sink)
            batch_res = executor.execute_batch(pset)

        self.assertEqual(batch_res.selected_count, 1)
        self.assertEqual(batch_res.completed_count, 1)
        self.assertEqual(batch_res.failed_count, 0)
        self.assertEqual(batch_res.results[0].status, "COMPLETED")
        self.assertEqual(batch_res.results[0].opportunity_score, 80.0)

    def test_05_multiple_prospects(self):
        """5. Multiple prospects batch processes all candidates sequentially."""
        prospects = [
            create_sample_business(f"Business {i}", rating=4.0 + i * 0.1)
            for i in range(3)
        ]
        pset = ProspectSet(prospects=prospects)

        with patch.object(self.registry, "execute") as mock_exec:
            # 6 capabilities per prospect * 3 = 18 calls
            mock_exec.side_effect = [
                CapabilityResult(success=True, capability_name="audit_website_tech", data={}),
                CapabilityResult(success=True, capability_name="enrich_leadership_social", data={}),
                CapabilityResult(success=True, capability_name="mine_business_intelligence", data={}),
                CapabilityResult(success=True, capability_name="calculate_health_and_scores", data={}),
                CapabilityResult(success=True, capability_name="assemble_prospect_context", data=create_sample_context(70.0)),
                CapabilityResult(success=True, capability_name="synthesize_opportunity_analysis", data=create_sample_opportunity()),
            ] * 3
            executor = ProspectBatchExecutor(registry=self.registry, telemetry_sink=self.sink)
            batch_res = executor.execute_batch(pset)

        self.assertEqual(batch_res.selected_count, 3)
        self.assertEqual(batch_res.completed_count, 3)
        self.assertEqual(len(batch_res.results), 3)

    def test_06_batch_size_limit(self):
        """6. Batch size limit constrains selection to configured maximum."""
        prospects = [create_sample_business(f"Business {i}") for i in range(10)]
        pset = ProspectSet(prospects=prospects)

        executor = ProspectBatchExecutor(
            registry=self.registry,
            telemetry_sink=self.sink,
            max_prospects_per_run=3
        )
        sel = ProspectSelection(max_prospects=10)

        with patch.object(self.registry, "execute") as mock_exec:
            mock_exec.side_effect = [
                CapabilityResult(success=True, capability_name="audit_website_tech", data={}),
                CapabilityResult(success=True, capability_name="enrich_leadership_social", data={}),
                CapabilityResult(success=True, capability_name="mine_business_intelligence", data={}),
                CapabilityResult(success=True, capability_name="calculate_health_and_scores", data={}),
                CapabilityResult(success=True, capability_name="assemble_prospect_context", data=create_sample_context()),
                CapabilityResult(success=True, capability_name="synthesize_opportunity_analysis", data=create_sample_opportunity()),
            ] * 3
            batch_res = executor.execute_batch(pset, selection=sel)

        # Capped to 3
        self.assertEqual(batch_res.selected_count, 3)
        self.assertEqual(len(batch_res.results), 3)

    def test_07_requested_count_above_limit_strict(self):
        """7. Requested count above limit raises BatchSizeLimitExceededError in strict mode."""
        pset = ProspectSet(prospects=[create_sample_business("Biz")])
        executor = ProspectBatchExecutor(
            registry=self.registry,
            max_prospects_per_run=5,
            strict_limit=True
        )
        sel = ProspectSelection(max_prospects=20)

        with self.assertRaises(BatchSizeLimitExceededError):
            executor.execute_batch(pset, selection=sel)

    def test_08_successful_batch(self):
        """8. Fully successful batch sets all statuses to COMPLETED and returns results."""
        b1 = create_sample_business("Biz 1")
        b2 = create_sample_business("Biz 2")
        pset = ProspectSet(prospects=[b1, b2])

        with patch.object(self.registry, "execute") as mock_exec:
            mock_exec.side_effect = [
                CapabilityResult(success=True, capability_name="audit_website_tech", data={}),
                CapabilityResult(success=True, capability_name="enrich_leadership_social", data={}),
                CapabilityResult(success=True, capability_name="mine_business_intelligence", data={}),
                CapabilityResult(success=True, capability_name="calculate_health_and_scores", data={}),
                CapabilityResult(success=True, capability_name="assemble_prospect_context", data=create_sample_context(85.0)),
                CapabilityResult(success=True, capability_name="synthesize_opportunity_analysis", data=create_sample_opportunity()),
            ] * 2
            executor = ProspectBatchExecutor(registry=self.registry, telemetry_sink=self.sink)
            batch_res = executor.execute_batch(pset)

        self.assertEqual(batch_res.completed_count, 2)
        self.assertEqual(batch_res.failed_count, 0)
        self.assertTrue(all(r.status == "COMPLETED" for r in batch_res.results))

    def test_09_one_prospect_failure(self):
        """9. When one prospect fails, other prospects continue executing successfully."""
        b1 = create_sample_business("Good Biz 1")
        b2 = create_sample_business("Failing Biz")
        b3 = create_sample_business("Good Biz 2")
        pset = ProspectSet(prospects=[b1, b2, b3])

        with patch.object(self.registry, "execute") as mock_exec:
            mock_exec.side_effect = [
                # Good Biz 1 (6 calls)
                CapabilityResult(success=True, capability_name="audit_website_tech", data={}),
                CapabilityResult(success=True, capability_name="enrich_leadership_social", data={}),
                CapabilityResult(success=True, capability_name="mine_business_intelligence", data={}),
                CapabilityResult(success=True, capability_name="calculate_health_and_scores", data={}),
                CapabilityResult(success=True, capability_name="assemble_prospect_context", data=create_sample_context()),
                CapabilityResult(success=True, capability_name="synthesize_opportunity_analysis", data=create_sample_opportunity()),
                # Failing Biz (audit fails -> 1 call)
                CapabilityResult(success=False, capability_name="audit_website_tech", error="Website socket timeout"),
                # Good Biz 2 (6 calls)
                CapabilityResult(success=True, capability_name="audit_website_tech", data={}),
                CapabilityResult(success=True, capability_name="enrich_leadership_social", data={}),
                CapabilityResult(success=True, capability_name="mine_business_intelligence", data={}),
                CapabilityResult(success=True, capability_name="calculate_health_and_scores", data={}),
                CapabilityResult(success=True, capability_name="assemble_prospect_context", data=create_sample_context()),
                CapabilityResult(success=True, capability_name="synthesize_opportunity_analysis", data=create_sample_opportunity()),
            ]
            executor = ProspectBatchExecutor(registry=self.registry, telemetry_sink=self.sink)
            batch_res = executor.execute_batch(pset)

        self.assertEqual(batch_res.selected_count, 3)
        self.assertEqual(batch_res.completed_count, 2)
        self.assertEqual(batch_res.failed_count, 1)

        self.assertEqual(batch_res.results[0].status, "COMPLETED")
        self.assertEqual(batch_res.results[1].status, "FAILED")
        self.assertIn("audit_website_tech", batch_res.results[1].failed_steps)
        self.assertEqual(batch_res.results[2].status, "COMPLETED")

    def test_10_multiple_prospect_failures(self):
        """10. Multiple prospect failures are all recorded without crashing the batch."""
        b1 = create_sample_business("Fail Biz 1")
        b2 = create_sample_business("Fail Biz 2")
        b3 = create_sample_business("Good Biz")
        pset = ProspectSet(prospects=[b1, b2, b3])

        with patch.object(self.registry, "execute") as mock_exec:
            mock_exec.side_effect = [
                # Fail 1
                CapabilityResult(success=False, capability_name="audit_website_tech", error="DNS failure"),
                # Fail 2
                CapabilityResult(success=False, capability_name="audit_website_tech", error="SSL error"),
                # Good
                CapabilityResult(success=True, capability_name="audit_website_tech", data={}),
                CapabilityResult(success=True, capability_name="enrich_leadership_social", data={}),
                CapabilityResult(success=True, capability_name="mine_business_intelligence", data={}),
                CapabilityResult(success=True, capability_name="calculate_health_and_scores", data={}),
                CapabilityResult(success=True, capability_name="assemble_prospect_context", data=create_sample_context()),
                CapabilityResult(success=True, capability_name="synthesize_opportunity_analysis", data=create_sample_opportunity()),
            ]
            executor = ProspectBatchExecutor(registry=self.registry, telemetry_sink=self.sink)
            batch_res = executor.execute_batch(pset)

        self.assertEqual(batch_res.completed_count, 1)
        self.assertEqual(batch_res.failed_count, 2)

    def test_11_failure_isolation(self):
        """11. Failure isolation guarantees that failures do not leak state or cascade to other prospects."""
        b1 = create_sample_business("Error Prone")
        b2 = create_sample_business("Healthy")
        pset = ProspectSet(prospects=[b1, b2])

        with patch.object(self.registry, "execute") as mock_exec:
            mock_exec.side_effect = [
                CapabilityResult(success=False, capability_name="audit_website_tech", error="Scraper failure"),
                # Next prospect runs normally
                CapabilityResult(success=True, capability_name="audit_website_tech", data={}),
                CapabilityResult(success=True, capability_name="enrich_leadership_social", data={}),
                CapabilityResult(success=True, capability_name="mine_business_intelligence", data={}),
                CapabilityResult(success=True, capability_name="calculate_health_and_scores", data={}),
                CapabilityResult(success=True, capability_name="assemble_prospect_context", data=create_sample_context()),
                CapabilityResult(success=True, capability_name="synthesize_opportunity_analysis", data=create_sample_opportunity()),
            ]
            executor = ProspectBatchExecutor(registry=self.registry, telemetry_sink=self.sink)
            batch_res = executor.execute_batch(pset)

        self.assertEqual(len(batch_res.results[0].errors), 1)
        self.assertEqual(len(batch_res.results[1].errors), 0)

    def test_12_system_level_failure_handling(self):
        """12. Policy violation or unregistered capability records POLICY_ERROR / CAPABILITY_ERROR."""
        b1 = create_sample_business("Target")
        pset = ProspectSet(prospects=[b1])

        empty_registry = CapabilityRegistry()
        executor = ProspectBatchExecutor(registry=empty_registry, telemetry_sink=self.sink)
        batch_res = executor.execute_batch(pset)

        self.assertEqual(batch_res.failed_count, 1)
        self.assertIn("Unregistered capability", batch_res.results[0].errors[0])

    def test_13_prospect_execution_result_creation(self):
        """13. ProspectExecutionResult is typed, serializable, and holds execution metadata."""
        b1 = create_sample_business("Apex")
        ctx = create_sample_context(88.0)
        opp = create_sample_opportunity()

        res = ProspectExecutionResult(
            prospect_id="Apex",
            business=b1,
            status="COMPLETED",
            completed_steps=["audit_website_tech", "assemble_prospect_context"],
            failed_steps=[],
            prospect_context=ctx,
            opportunity_analysis=opp,
            opportunity_score=88.0,
            errors=[],
            duration_ms=45.2,
        )
        self.assertEqual(res.prospect_id, "Apex")
        self.assertEqual(res.opportunity_score, 88.0)
        self.assertEqual(res.status, "COMPLETED")
        dump = res.model_dump()
        self.assertIn("business", dump)

    def test_14_prospect_batch_result_creation(self):
        """14. ProspectBatchResult contains serializable counts and timestamps."""
        batch_res = ProspectBatchResult(
            batch_id="batch_test1",
            requested_count=5,
            selected_count=2,
            completed_count=2,
            failed_count=0,
            blocked_count=0,
            results=[],
            duration_ms=105.0,
        )
        self.assertEqual(batch_res.batch_id, "batch_test1")
        self.assertEqual(batch_res.selected_count, 2)
        self.assertIsNotNone(batch_res.started_at)

    def test_15_ranking_using_existing_opportunity_signals(self):
        """15. Ranking uses existing signals (sales_opportunity_score, rating) without new scoring engines."""
        b1 = create_sample_business("Low Opp", rating=4.8)
        b2 = create_sample_business("High Opp", rating=2.5)
        b3 = create_sample_business("Mid Opp", rating=3.5)

        r1 = ProspectExecutionResult(
            prospect_id="Low Opp", business=b1, status="COMPLETED", opportunity_score=35.0
        )
        r2 = ProspectExecutionResult(
            prospect_id="High Opp", business=b2, status="COMPLETED", opportunity_score=92.0
        )
        r3 = ProspectExecutionResult(
            prospect_id="Mid Opp", business=b3, status="COMPLETED", opportunity_score=68.0
        )

        batch_res = ProspectBatchResult(
            requested_count=3,
            selected_count=3,
            completed_count=3,
            results=[r1, r2, r3]
        )

        # Opportunity score ranking (higher opportunity first)
        ranked = batch_res.ranked_results("opportunity_score")
        self.assertEqual(ranked[0].prospect_id, "High Opp")
        self.assertEqual(ranked[1].prospect_id, "Mid Opp")
        self.assertEqual(ranked[2].prospect_id, "Low Opp")

        # Rating ascending ranking (lower rating first)
        ranked_rating = batch_res.ranked_results("rating_asc")
        self.assertEqual(ranked_rating[0].prospect_id, "High Opp")  # 2.5
        self.assertEqual(ranked_rating[1].prospect_id, "Mid Opp")   # 3.5
        self.assertEqual(ranked_rating[2].prospect_id, "Low Opp")   # 4.8

    def test_16_no_duplicate_business_model(self):
        """16. ProspectSet and results directly use canonical schemas.business.Business."""
        biz = create_sample_business("Original")
        pset = ProspectSet(prospects=[biz])
        self.assertIsInstance(pset.prospects[0], Business)
        self.assertEqual(pset.prospects[0].__class__.__module__, "schemas.business")

    def test_17_registry_only_capability_execution(self):
        """17. Batch executor delegates exclusively to CapabilityRegistry.execute."""
        pset = ProspectSet(prospects=[create_sample_business("Biz")])
        mock_registry = MagicMock(spec=CapabilityRegistry)
        mock_registry.get.return_value = self.registry.get("audit_website_tech")
        mock_registry.execute.return_value = CapabilityResult(success=True, capability_name="audit_website_tech", data={})

        executor = ProspectBatchExecutor(registry=mock_registry)
        executor.execute_batch(pset)

        self.assertTrue(mock_registry.execute.called)

    def test_18_batch_telemetry(self):
        """18. Batch execution emits telemetry events tagged with batch_id."""
        pset = ProspectSet(prospects=[create_sample_business("Telemetry Biz")])

        with patch.object(self.registry, "execute") as mock_exec:
            mock_exec.side_effect = [
                CapabilityResult(success=True, capability_name="audit_website_tech", data={}),
                CapabilityResult(success=True, capability_name="enrich_leadership_social", data={}),
                CapabilityResult(success=True, capability_name="mine_business_intelligence", data={}),
                CapabilityResult(success=True, capability_name="calculate_health_and_scores", data={}),
                CapabilityResult(success=True, capability_name="assemble_prospect_context", data=create_sample_context()),
                CapabilityResult(success=True, capability_name="synthesize_opportunity_analysis", data=create_sample_opportunity()),
            ]
            executor = ProspectBatchExecutor(registry=self.registry, telemetry_sink=self.sink)
            batch_res = executor.execute_batch(pset)

        events = self.sink.get_step_events(batch_id=batch_res.batch_id)
        self.assertGreater(len(events), 0)
        self.assertEqual(events[0].batch_id, batch_res.batch_id)

    def test_19_prospect_specific_telemetry(self):
        """19. Telemetry trace events distinguish between individual prospects."""
        b1 = create_sample_business("Prospect Alpha")
        b2 = create_sample_business("Prospect Beta")
        pset = ProspectSet(prospects=[b1, b2])

        with patch.object(self.registry, "execute") as mock_exec:
            mock_exec.side_effect = [
                CapabilityResult(success=True, capability_name="audit_website_tech", data={}),
                CapabilityResult(success=True, capability_name="enrich_leadership_social", data={}),
                CapabilityResult(success=True, capability_name="mine_business_intelligence", data={}),
                CapabilityResult(success=True, capability_name="calculate_health_and_scores", data={}),
                CapabilityResult(success=True, capability_name="assemble_prospect_context", data=create_sample_context()),
                CapabilityResult(success=True, capability_name="synthesize_opportunity_analysis", data=create_sample_opportunity()),
            ] * 2
            executor = ProspectBatchExecutor(registry=self.registry, telemetry_sink=self.sink)
            batch_res = executor.execute_batch(pset)

        alpha_events = self.sink.get_step_events(prospect_id="Prospect Alpha")
        beta_events = self.sink.get_step_events(prospect_id="Prospect Beta")
        self.assertGreater(len(alpha_events), 0)
        self.assertGreater(len(beta_events), 0)
        self.assertEqual(alpha_events[0].prospect_id, "Prospect Alpha")
        self.assertEqual(beta_events[0].prospect_id, "Prospect Beta")

    def test_20_agent_run_prospect_batch_integration(self):
        """20. Agent.run_prospect_batch coordinates with ProspectBatchExecutor and sets state."""
        b1 = create_sample_business("Agent Biz")
        pset = ProspectSet(prospects=[b1])
        agent = Agent(registry=self.registry, telemetry_sink=self.sink)

        with patch.object(self.registry, "execute") as mock_exec:
            mock_exec.side_effect = [
                CapabilityResult(success=True, capability_name="audit_website_tech", data={}),
                CapabilityResult(success=True, capability_name="enrich_leadership_social", data={}),
                CapabilityResult(success=True, capability_name="mine_business_intelligence", data={}),
                CapabilityResult(success=True, capability_name="calculate_health_and_scores", data={}),
                CapabilityResult(success=True, capability_name="assemble_prospect_context", data=create_sample_context()),
                CapabilityResult(success=True, capability_name="synthesize_opportunity_analysis", data=create_sample_opportunity()),
            ]
            state = agent.run_prospect_batch(pset)

        self.assertEqual(state.status, AgentStatus.COMPLETED)
        self.assertIsNotNone(state.batch_result)
        self.assertEqual(state.batch_result.completed_count, 1)
        self.assertEqual(state.final_response.batch_result.completed_count, 1)
        self.assertIsNotNone(state.final_response.prospect_set)

    def test_21_agent_constrains_excessive_batch_requests(self):
        """21. Agent constrains requests requesting excessive batch counts (e.g. 5000)."""
        agent = Agent(registry=self.registry, telemetry_sink=self.sink, max_prospects_per_run=15)
        goal = "Analyze 5000 businesses in Chicago"

        with patch.object(self.registry, "execute") as mock_exec:
            mock_biz = create_sample_business("Discovered Biz")
            mock_exec.return_value = CapabilityResult(
                success=True,
                capability_name="discover_prospects",
                data=DiscoverProspectsOutput(query="businesses in Chicago", total_found=1, source="gmaps", businesses=[mock_biz])
            )
            state = agent.run(goal)

        # Constrained from 5000 to 15
        self.assertEqual(state.intent.constraints.get("limit"), 15)
        self.assertEqual(state.intent.constraints.get("constrained_from"), 5000)
        self.assertTrue(any("exceeds maximum allowed" in err for err in state.errors))

    def test_22_existing_discovery_tests_remain_valid(self):
        """22. Normal discovery populates both state.prospects and state.prospect_set."""
        agent = Agent(registry=self.registry, telemetry_sink=self.sink)
        with patch.object(self.registry, "execute") as mock_exec:
            mock_biz = create_sample_business("Discovery Clinic")
            mock_exec.return_value = CapabilityResult(
                success=True,
                capability_name="discover_prospects",
                data=DiscoverProspectsOutput(query="Dental in Austin, TX", total_found=1, source="gmaps", businesses=[mock_biz])
            )
            state = agent.run("Find dental clinics in Austin, TX")

        self.assertEqual(len(state.prospects), 1)
        self.assertIsNotNone(state.prospect_set)
        self.assertEqual(len(state.prospect_set), 1)
        self.assertEqual(state.prospect_set.prospects[0].business_name, "Discovery Clinic")


if __name__ == "__main__":
    unittest.main()
