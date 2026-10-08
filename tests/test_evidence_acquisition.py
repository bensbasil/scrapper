"""
tests/test_evidence_acquisition.py
----------------------------------
Unit test suite for Phase 4C Evidence Acquisition & Canonical ProspectContext.
Validates:
1. evidence acquisition for one prospect
2. ProspectContext creation
3. existing context builder reuse
4. registry-only evidence acquisition
5. partial evidence handling
6. missing website handling
7. missing enrichment handling
8. evidence failure isolation
9. multiple prospect contexts
10. context size boundary (< 350 words summary)
11. evidence provenance preservation
12. insufficient evidence semantics
13. ProspectExecutionResult context integration
14. AgentState context mapping (prospect_contexts dictionary)
15. downstream OpportunityReasoner receives ProspectContext
16. downstream OutreachReasoner receives ProspectContext
17. evidence layer does not call LLM directly
18. evidence layer does not access infrastructure directly
19. telemetry integration
20. existing Phase 4A batch execution compatibility
21. existing Phase 4B qualification integration
22. existing Phase 2 context contract compatibility
"""

import sys
import unittest
from unittest.mock import MagicMock, patch
from typing import Dict, Any, List

from schemas.business import Business
from schemas.context import ProspectContext, EvidenceItem, ScoreCard
from schemas.ai import OpportunityAnalysis, OutreachStrategy
from application.capabilities.registry import CapabilityRegistry
from application.contracts.base import CapabilityResult
from agent.policies import PolicyEnforcer
from agent.telemetry import (
    InMemoryTelemetrySink,
    CapabilityTraceEvent,
    StepEventStatus,
    ErrorCategory,
)
from agent.state import AgentState, AgentStatus
from agent.prospects import (
    ProspectSet,
    QualifiedProspectSet,
    ProspectSelection,
    ProspectExecutionResult,
    ProspectBatchResult,
    ProspectBatchExecutor,
)
from agent.qualification import (
    DeterministicProspectQualifier,
    QualificationPolicy,
    ProspectQualification,
)
from agent.evidence import (
    EvidenceAcquisitionCoordinator,
    EvidenceAcquisitionResult,
)
from ai.opportunity_reasoner import OpportunityReasoner
from ai.outreach_reasoner import OutreachReasoner
from evaluation.datasets.fixtures import get_strong_evidence_good_reasoning_fixture


def make_business(
    name: str = "Apex Plumbing",
    website: str = "https://apexplumbing.com",
    rating: float = 4.3,
    reviews: int = 50,
    category: str = "Plumbing Service",
) -> Business:
    return Business(
        business_name=name,
        website=website,
        google_rating=rating,
        review_count=reviews,
        category=category,
        address="100 Commercial Way, Chicago, IL",
        city="Chicago",
    )


def make_canonical_context(name: str = "Apex Plumbing", opp_score: float = 78.0) -> ProspectContext:
    fixture = get_strong_evidence_good_reasoning_fixture()
    ctx = fixture["context"]
    ctx.business.business_name = name
    ctx.scores.sales_opportunity_score = opp_score
    return ctx


class TestEvidenceAcquisitionAndProspectContext(unittest.TestCase):
    """Phase 4C Evidence Acquisition test suite."""

    def setUp(self):
        self.registry = CapabilityRegistry.default_registry()
        self.sink = InMemoryTelemetrySink()
        self.coordinator = EvidenceAcquisitionCoordinator(
            registry=self.registry,
            telemetry_sink=self.sink,
        )

    def test_01_evidence_acquisition_single_prospect(self):
        """1. Evidence acquisition for a single prospect produces successful result."""
        biz = make_business("Zenith HVAC", website="https://zenithhvac.com")
        sample_ctx = make_canonical_context("Zenith HVAC")

        with patch.object(self.registry, "execute") as mock_exec:
            mock_exec.side_effect = [
                CapabilityResult(success=True, capability_name="audit_website_tech", data={"tech": ["WordPress"]}),
                CapabilityResult(success=True, capability_name="enrich_leadership_social", data={"decision_makers": []}),
                CapabilityResult(success=True, capability_name="mine_business_intelligence", data={"sentiment": "mixed"}),
                CapabilityResult(success=True, capability_name="calculate_health_and_scores", data={"health": 60}),
                CapabilityResult(success=True, capability_name="assemble_prospect_context", data=sample_ctx),
            ]
            result = self.coordinator.acquire_evidence(biz, run_id="run_101", batch_id="batch_101")

        self.assertTrue(result.success)
        self.assertEqual(result.prospect_id, "Zenith HVAC")
        self.assertIsNotNone(result.context)
        self.assertEqual(len(result.completed_capabilities), 5)
        self.assertIn("audit_website_tech", result.completed_capabilities)
        self.assertIn("assemble_prospect_context", result.completed_capabilities)
        self.assertEqual(len(result.failed_capabilities), 0)
        self.assertGreaterEqual(result.duration_ms, 0.0)

    def test_02_prospect_context_creation(self):
        """2. Assembled object is confirmed canonical ProspectContext with required attributes."""
        biz = make_business("Summit Roofing")
        sample_ctx = make_canonical_context("Summit Roofing")

        with patch.object(self.registry, "execute") as mock_exec:
            mock_exec.side_effect = [
                CapabilityResult(success=True, capability_name="audit_website_tech", data={}),
                CapabilityResult(success=True, capability_name="enrich_leadership_social", data={}),
                CapabilityResult(success=True, capability_name="mine_business_intelligence", data={}),
                CapabilityResult(success=True, capability_name="calculate_health_and_scores", data={}),
                CapabilityResult(success=True, capability_name="assemble_prospect_context", data=sample_ctx),
            ]
            result = self.coordinator.acquire_evidence(biz)

        ctx = result.context
        self.assertIsInstance(ctx, ProspectContext)
        self.assertEqual(ctx.business.business_name, "Summit Roofing")
        self.assertTrue(hasattr(ctx, "evidence"))
        self.assertTrue(hasattr(ctx, "scores"))
        self.assertTrue(hasattr(ctx, "to_token_efficient_summary"))

    def test_03_existing_context_builder_reuse(self):
        """3. Confirms assemble_prospect_context delegates to existing ProspectContextBuilder without duplication."""
        cap_desc = self.registry.get("assemble_prospect_context")
        self.assertIsNotNone(cap_desc)
        # Execute default capability implementation without mocks to verify real context assembly
        res = self.registry.execute(
            "assemble_prospect_context",
            {"business_data": {"business_name": "Real Test Co", "website": "https://test.com", "rating": 4.0}}
        )
        self.assertTrue(res.success)
        self.assertIsInstance(res.data, ProspectContext)
        self.assertEqual(res.data.business.business_name, "Real Test Co")

    def test_04_registry_only_evidence_acquisition(self):
        """4. Coordinator executes capabilities strictly through CapabilityRegistry.execute."""
        biz = make_business("Registry Only Co")
        sample_ctx = make_canonical_context("Registry Only Co")

        called_caps = []
        def spy_execute(cap_name, params):
            called_caps.append(cap_name)
            if cap_name == "assemble_prospect_context":
                return CapabilityResult(success=True, capability_name=cap_name, data=sample_ctx)
            return CapabilityResult(success=True, capability_name=cap_name, data={})

        with patch.object(self.registry, "execute", side_effect=spy_execute):
            result = self.coordinator.acquire_evidence(biz)

        self.assertTrue(result.success)
        expected_sequence = [
            "audit_website_tech",
            "enrich_leadership_social",
            "mine_business_intelligence",
            "calculate_health_and_scores",
            "assemble_prospect_context",
        ]
        self.assertEqual(called_caps, expected_sequence)

    def test_05_partial_evidence_handling(self):
        """5. Partial evidence (e.g. empty reviews/intel) still constructs valid ProspectContext."""
        biz = make_business("Partial Data Co")
        partial_ctx = make_canonical_context("Partial Data Co")

        with patch.object(self.registry, "execute") as mock_exec:
            mock_exec.side_effect = [
                CapabilityResult(success=True, capability_name="audit_website_tech", data={"tech": []}),
                CapabilityResult(success=True, capability_name="enrich_leadership_social", data={"decision_makers": [], "emails": []}),
                CapabilityResult(success=True, capability_name="mine_business_intelligence", data={"sentiment": None, "negative_themes": []}),
                CapabilityResult(success=True, capability_name="calculate_health_and_scores", data={"health": None}),
                CapabilityResult(success=True, capability_name="assemble_prospect_context", data=partial_ctx),
            ]
            result = self.coordinator.acquire_evidence(biz)

        self.assertTrue(result.success)
        self.assertIsNotNone(result.context)
        self.assertEqual(result.prospect_id, "Partial Data Co")

    def test_06_missing_website_handling(self):
        """6. Missing website cleanly skips website audit and enrichment without failing context."""
        biz = Business(
            business_name="No Web Corp",
            website=None,
            google_rating=4.5,
            review_count=30,
            category="Local Repair",
        )
        sample_ctx = make_canonical_context("No Web Corp")

        called_caps = []
        def mock_exec(cap_name, params):
            called_caps.append(cap_name)
            if cap_name == "assemble_prospect_context":
                return CapabilityResult(success=True, capability_name=cap_name, data=sample_ctx)
            return CapabilityResult(success=True, capability_name=cap_name, data={})

        with patch.object(self.registry, "execute", side_effect=mock_exec):
            result = self.coordinator.acquire_evidence(biz)

        self.assertTrue(result.success)
        # Website and enrichment capabilities should NOT have been invoked
        self.assertNotIn("audit_website_tech", called_caps)
        self.assertNotIn("enrich_leadership_social", called_caps)
        # Remaining capabilities should have been invoked
        self.assertIn("mine_business_intelligence", called_caps)
        self.assertIn("calculate_health_and_scores", called_caps)
        self.assertIn("assemble_prospect_context", called_caps)

    def test_07_missing_enrichment_handling(self):
        """7. Missing leadership enrichment signals does not abort evidence acquisition."""
        biz = make_business("No Leads Co")
        sample_ctx = make_canonical_context("No Leads Co")

        with patch.object(self.registry, "execute") as mock_exec:
            mock_exec.side_effect = [
                CapabilityResult(success=True, capability_name="audit_website_tech", data={}),
                CapabilityResult(success=True, capability_name="enrich_leadership_social", data={"decision_makers": []}),
                CapabilityResult(success=True, capability_name="mine_business_intelligence", data={}),
                CapabilityResult(success=True, capability_name="calculate_health_and_scores", data={}),
                CapabilityResult(success=True, capability_name="assemble_prospect_context", data=sample_ctx),
            ]
            result = self.coordinator.acquire_evidence(biz)

        self.assertTrue(result.success)
        self.assertIsNotNone(result.context)

    def test_08_evidence_failure_isolation(self):
        """8. Failure during evidence acquisition for one prospect does not cascade to subsequent prospects."""
        b1 = make_business("Prospect Alpha")
        b2 = make_business("Prospect Beta (Fail)")
        b3 = make_business("Prospect Gamma")
        pset = ProspectSet(prospects=[b1, b2, b3])

        ctx1 = make_canonical_context("Prospect Alpha")
        ctx3 = make_canonical_context("Prospect Gamma")

        with patch.object(self.registry, "execute") as mock_exec:
            mock_exec.side_effect = [
                # Prospect Alpha: 5 evidence caps + 1 opp analysis = 6
                CapabilityResult(success=True, capability_name="audit_website_tech", data={}),
                CapabilityResult(success=True, capability_name="enrich_leadership_social", data={}),
                CapabilityResult(success=True, capability_name="mine_business_intelligence", data={}),
                CapabilityResult(success=True, capability_name="calculate_health_and_scores", data={}),
                CapabilityResult(success=True, capability_name="assemble_prospect_context", data=ctx1),
                CapabilityResult(success=True, capability_name="synthesize_opportunity_analysis", data=MagicMock()),
                # Prospect Beta: website audit fails immediately
                CapabilityResult(success=False, capability_name="audit_website_tech", error="Connection refused"),
                # Prospect Gamma: 5 evidence caps + 1 opp analysis = 6
                CapabilityResult(success=True, capability_name="audit_website_tech", data={}),
                CapabilityResult(success=True, capability_name="enrich_leadership_social", data={}),
                CapabilityResult(success=True, capability_name="mine_business_intelligence", data={}),
                CapabilityResult(success=True, capability_name="calculate_health_and_scores", data={}),
                CapabilityResult(success=True, capability_name="assemble_prospect_context", data=ctx3),
                CapabilityResult(success=True, capability_name="synthesize_opportunity_analysis", data=MagicMock()),
            ]
            executor = ProspectBatchExecutor(registry=self.registry, telemetry_sink=self.sink)
            batch_res = executor.execute_batch(pset)

        self.assertEqual(batch_res.selected_count, 3)
        self.assertEqual(batch_res.completed_count, 2)
        self.assertEqual(batch_res.failed_count, 1)

        res_alpha = next(r for r in batch_res.results if r.prospect_id == "Prospect Alpha")
        res_beta = next(r for r in batch_res.results if r.prospect_id == "Prospect Beta (Fail)")
        res_gamma = next(r for r in batch_res.results if r.prospect_id == "Prospect Gamma")

        self.assertEqual(res_alpha.status, "COMPLETED")
        self.assertIsNotNone(res_alpha.prospect_context)
        self.assertEqual(res_beta.status, "FAILED")
        self.assertIn("audit_website_tech", res_beta.failed_steps)
        self.assertEqual(res_gamma.status, "COMPLETED")
        self.assertIsNotNone(res_gamma.prospect_context)

    def test_09_multiple_prospect_contexts(self):
        """9. Multiple prospects each receive their own distinct ProspectContext."""
        b1 = make_business("Shop 1")
        b2 = make_business("Shop 2")
        pset = ProspectSet(prospects=[b1, b2])

        ctx1 = make_canonical_context("Shop 1", opp_score=85.0)
        ctx2 = make_canonical_context("Shop 2", opp_score=45.0)

        with patch.object(self.registry, "execute") as mock_exec:
            mock_exec.side_effect = [
                CapabilityResult(success=True, capability_name="audit_website_tech", data={}),
                CapabilityResult(success=True, capability_name="enrich_leadership_social", data={}),
                CapabilityResult(success=True, capability_name="mine_business_intelligence", data={}),
                CapabilityResult(success=True, capability_name="calculate_health_and_scores", data={}),
                CapabilityResult(success=True, capability_name="assemble_prospect_context", data=ctx1),
                CapabilityResult(success=True, capability_name="synthesize_opportunity_analysis", data=MagicMock()),
                CapabilityResult(success=True, capability_name="audit_website_tech", data={}),
                CapabilityResult(success=True, capability_name="enrich_leadership_social", data={}),
                CapabilityResult(success=True, capability_name="mine_business_intelligence", data={}),
                CapabilityResult(success=True, capability_name="calculate_health_and_scores", data={}),
                CapabilityResult(success=True, capability_name="assemble_prospect_context", data=ctx2),
                CapabilityResult(success=True, capability_name="synthesize_opportunity_analysis", data=MagicMock()),
            ]
            executor = ProspectBatchExecutor(registry=self.registry, telemetry_sink=self.sink)
            batch_res = executor.execute_batch(pset)

        self.assertEqual(batch_res.completed_count, 2)
        r1, r2 = batch_res.results[0], batch_res.results[1]
        self.assertNotEqual(r1.prospect_context, r2.prospect_context)
        self.assertEqual(r1.prospect_context.business.business_name, "Shop 1")
        self.assertEqual(r2.prospect_context.business.business_name, "Shop 2")

    def test_10_context_size_boundary(self):
        """10. ProspectContext enforces bounded token footprint (< 350 words in summary)."""
        ctx = make_canonical_context("Bounded Context Co")
        summary = ctx.to_token_efficient_summary()
        word_count = len(summary.split())
        self.assertLess(word_count, 350, f"Context summary exceeded 350 words: {word_count} words")

    def test_11_evidence_provenance_preservation(self):
        """11. Evidence items retain atomic provenance (source, category, confidence)."""
        ctx = make_canonical_context("Provenance Co")
        self.assertTrue(len(ctx.evidence) > 0)
        for ev in ctx.evidence:
            self.assertIsInstance(ev, EvidenceItem)
            self.assertTrue(bool(ev.source), "Evidence source must be preserved")
            self.assertTrue(bool(ev.category), "Evidence category must be preserved")
            self.assertGreaterEqual(ev.confidence, 0.0)
            self.assertLessEqual(ev.confidence, 1.0)

    def test_12_insufficient_evidence_semantics(self):
        """12. Context with insufficient evidence (< 2 items) triggers conservative reasoning semantics."""
        ctx = make_canonical_context("Sparse Co")
        # Strip evidence and score to trigger insufficient evidence rule
        ctx.evidence = []
        ctx.scores.sales_opportunity_score = 0.0

        mock_llm = MagicMock()
        reasoner = OpportunityReasoner(llm_client=mock_llm)
        analysis = reasoner.reason(ctx)

        self.assertEqual(analysis.evidence_sufficiency, "insufficient")
        self.assertLessEqual(analysis.confidence_score, 0.4)
        self.assertIn("Insufficient", analysis.executive_diagnosis)

    def test_13_prospect_execution_result_context_integration(self):
        """13. ProspectExecutionResult retains canonical ProspectContext."""
        biz = make_business("Result Model Co")
        ctx = make_canonical_context("Result Model Co")
        p_res = ProspectExecutionResult(
            prospect_id="Result Model Co",
            business=biz,
            status="COMPLETED",
            prospect_context=ctx,
            opportunity_score=82.5,
        )
        self.assertEqual(p_res.prospect_context.business.business_name, "Result Model Co")
        self.assertEqual(p_res.opportunity_score, 82.5)

    def test_14_agent_state_context_mapping(self):
        """14. AgentState tracks bounded prospect_contexts mapping alongside primary prospect_context."""
        state = AgentState(
            task_id="t_ctx",
            user_goal="Batch context test",
        )
        ctx1 = make_canonical_context("Alpha Inc")
        ctx2 = make_canonical_context("Beta Inc")

        state.prospect_contexts["Alpha Inc"] = ctx1
        state.prospect_contexts["Beta Inc"] = ctx2
        state.prospect_context = ctx1

        self.assertEqual(len(state.prospect_contexts), 2)
        self.assertEqual(state.prospect_contexts["Alpha Inc"].business.business_name, "Alpha Inc")
        self.assertEqual(state.prospect_contexts["Beta Inc"].business.business_name, "Beta Inc")
        self.assertEqual(state.prospect_context.business.business_name, "Alpha Inc")

    def test_15_downstream_opportunity_reasoner_receives_prospect_context(self):
        """15. synthesize_opportunity_analysis capability receives canonical ProspectContext."""
        biz = make_business("Downstream Co")
        ctx = make_canonical_context("Downstream Co")
        pset = ProspectSet(prospects=[biz])

        received_context = None
        def mock_exec(cap_name, params):
            nonlocal received_context
            if cap_name == "assemble_prospect_context":
                return CapabilityResult(success=True, capability_name=cap_name, data=ctx)
            if cap_name == "synthesize_opportunity_analysis":
                received_context = params.get("context")
                return CapabilityResult(success=True, capability_name=cap_name, data=MagicMock())
            return CapabilityResult(success=True, capability_name=cap_name, data={})

        with patch.object(self.registry, "execute", side_effect=mock_exec):
            executor = ProspectBatchExecutor(registry=self.registry)
            executor.execute_batch(pset)

        self.assertIsInstance(received_context, ProspectContext)
        self.assertEqual(received_context.business.business_name, "Downstream Co")

    def test_16_downstream_outreach_reasoner_receives_prospect_context(self):
        """16. formulate_outreach_strategy capability receives canonical ProspectContext."""
        biz = make_business("Outreach Downstream Co")
        ctx = make_canonical_context("Outreach Downstream Co")
        fixture = get_strong_evidence_good_reasoning_fixture()
        opp = fixture["opportunity_analysis"]
        pset = ProspectSet(prospects=[biz])

        received_context = None
        def mock_exec(cap_name, params):
            nonlocal received_context
            if cap_name == "assemble_prospect_context":
                return CapabilityResult(success=True, capability_name=cap_name, data=ctx)
            if cap_name == "synthesize_opportunity_analysis":
                return CapabilityResult(success=True, capability_name=cap_name, data=opp)
            if cap_name == "formulate_outreach_strategy":
                received_context = params.get("context")
                return CapabilityResult(success=True, capability_name=cap_name, data=MagicMock())
            return CapabilityResult(success=True, capability_name=cap_name, data={})

        with patch.object(self.registry, "execute", side_effect=mock_exec):
            executor = ProspectBatchExecutor(registry=self.registry)
            executor.execute_batch(pset, include_outreach=True)

        self.assertIsInstance(received_context, ProspectContext)
        self.assertEqual(received_context.business.business_name, "Outreach Downstream Co")

    def test_17_evidence_layer_does_not_call_llm_directly(self):
        """17. EvidenceAcquisitionCoordinator does not directly invoke LLMClient or generate_structured."""
        with patch("ai.client.LLMClient.generate_structured") as mock_llm:
            biz = make_business("No LLM Direct Co")
            sample_ctx = make_canonical_context("No LLM Direct Co")

            with patch.object(self.registry, "execute") as mock_exec:
                mock_exec.side_effect = [
                    CapabilityResult(success=True, capability_name="audit_website_tech", data={}),
                    CapabilityResult(success=True, capability_name="enrich_leadership_social", data={}),
                    CapabilityResult(success=True, capability_name="mine_business_intelligence", data={}),
                    CapabilityResult(success=True, capability_name="calculate_health_and_scores", data={}),
                    CapabilityResult(success=True, capability_name="assemble_prospect_context", data=sample_ctx),
                ]
                self.coordinator.acquire_evidence(biz)

            # Strict assertion: Zero calls to LLM
            mock_llm.assert_not_called()

    def test_18_evidence_layer_does_not_access_infrastructure_directly(self):
        """18. Verify agent.evidence does not import raw infrastructure modules (playwright, bs4, sqlite3)."""
        import agent.evidence as ev_mod
        forbidden = ["playwright", "bs4", "sqlite3", "psycopg", "requests", "httpx"]
        for mod_name in forbidden:
            self.assertNotIn(mod_name, ev_mod.__dict__, f"agent.evidence directly imports '{mod_name}'")

    def test_19_telemetry_integration(self):
        """19. Telemetry records evidence acquisition lifecycle without dumping raw payloads."""
        biz = make_business("Telemetry Co")
        sample_ctx = make_canonical_context("Telemetry Co")

        with patch.object(self.registry, "execute") as mock_exec:
            mock_exec.side_effect = [
                CapabilityResult(success=True, capability_name="audit_website_tech", data={}),
                CapabilityResult(success=True, capability_name="enrich_leadership_social", data={}),
                CapabilityResult(success=True, capability_name="mine_business_intelligence", data={}),
                CapabilityResult(success=True, capability_name="calculate_health_and_scores", data={}),
                CapabilityResult(success=True, capability_name="assemble_prospect_context", data=sample_ctx),
            ]
            self.coordinator.acquire_evidence(biz, run_id="run_t1", batch_id="batch_t1")

        events = self.sink.get_step_events()
        self.assertGreater(len(events), 0)
        # Check overall acquire_evidence trace event
        overall_events = [e for e in events if e.capability_name == "acquire_evidence"]
        self.assertEqual(len(overall_events), 2)  # STARTED, COMPLETED
        self.assertEqual(overall_events[0].status, StepEventStatus.STARTED)
        self.assertEqual(overall_events[1].status, StepEventStatus.COMPLETED)
        self.assertEqual(overall_events[0].prospect_id, "Telemetry Co")
        self.assertEqual(overall_events[0].run_id, "run_t1")
        self.assertEqual(overall_events[0].batch_id, "batch_t1")

    def test_20_phase_4a_batch_execution_compatibility(self):
        """20. Phase 4A batch executor preserves ranking and batch limits with new coordinator."""
        b1 = make_business("High Opp", rating=3.5)
        b2 = make_business("Low Opp", rating=4.8)
        pset = ProspectSet(prospects=[b1, b2])

        ctx1 = make_canonical_context("High Opp", opp_score=90.0)
        ctx2 = make_canonical_context("Low Opp", opp_score=30.0)

        with patch.object(self.registry, "execute") as mock_exec:
            mock_exec.side_effect = [
                CapabilityResult(success=True, capability_name="audit_website_tech", data={}),
                CapabilityResult(success=True, capability_name="enrich_leadership_social", data={}),
                CapabilityResult(success=True, capability_name="mine_business_intelligence", data={}),
                CapabilityResult(success=True, capability_name="calculate_health_and_scores", data={}),
                CapabilityResult(success=True, capability_name="assemble_prospect_context", data=ctx1),
                CapabilityResult(success=True, capability_name="synthesize_opportunity_analysis", data=MagicMock()),
                CapabilityResult(success=True, capability_name="audit_website_tech", data={}),
                CapabilityResult(success=True, capability_name="enrich_leadership_social", data={}),
                CapabilityResult(success=True, capability_name="mine_business_intelligence", data={}),
                CapabilityResult(success=True, capability_name="calculate_health_and_scores", data={}),
                CapabilityResult(success=True, capability_name="assemble_prospect_context", data=ctx2),
                CapabilityResult(success=True, capability_name="synthesize_opportunity_analysis", data=MagicMock()),
            ]
            executor = ProspectBatchExecutor(registry=self.registry)
            batch_res = executor.execute_batch(pset)

        ranked = batch_res.ranked_results("opportunity_score")
        self.assertEqual(ranked[0].prospect_id, "High Opp")
        self.assertEqual(ranked[1].prospect_id, "Low Opp")

    def test_21_phase_4b_qualification_integration(self):
        """21. QualifiedProspectSet flows seamlessly into evidence acquisition and context assembly."""
        b1 = make_business("Qualified Co", website="https://qual.com", rating=4.2, reviews=25)
        b2 = make_business("Disqualified Co", website=None, rating=1.5, reviews=1)
        pset = ProspectSet(prospects=[b1, b2])

        qualifier = DeterministicProspectQualifier(
            policy=QualificationPolicy(require_website=True, min_reviews=5)
        )
        qualified_set = qualifier.qualify_set(pset)
        self.assertEqual(len(qualified_set.qualified_prospects), 1)

        ctx = make_canonical_context("Qualified Co")
        with patch.object(self.registry, "execute") as mock_exec:
            mock_exec.side_effect = [
                CapabilityResult(success=True, capability_name="audit_website_tech", data={}),
                CapabilityResult(success=True, capability_name="enrich_leadership_social", data={}),
                CapabilityResult(success=True, capability_name="mine_business_intelligence", data={}),
                CapabilityResult(success=True, capability_name="calculate_health_and_scores", data={}),
                CapabilityResult(success=True, capability_name="assemble_prospect_context", data=ctx),
                CapabilityResult(success=True, capability_name="synthesize_opportunity_analysis", data=MagicMock()),
            ]
            executor = ProspectBatchExecutor(registry=self.registry)
            batch_res = executor.execute_batch(qualified_set)

        self.assertEqual(batch_res.completed_count, 1)
        self.assertEqual(batch_res.results[0].prospect_id, "Qualified Co")
        self.assertIsNotNone(batch_res.results[0].prospect_context)

    def test_22_phase_2_context_contract_compatibility(self):
        """22. ProspectContext can be passed directly into Phase 2 reasoners without translation."""
        fixture = get_strong_evidence_good_reasoning_fixture()
        ctx = fixture["context"]

        mock_llm = MagicMock()
        mock_llm.generate_structured.return_value = fixture["opportunity_analysis"]
        opp_reasoner = OpportunityReasoner(llm_client=mock_llm)
        analysis = opp_reasoner.reason(ctx)
        self.assertIsInstance(analysis, OpportunityAnalysis)

        mock_llm.generate_structured.return_value = fixture["outreach_strategy"]
        outreach_reasoner = OutreachReasoner(llm_client=mock_llm)
        strat = outreach_reasoner.reason(ctx, analysis)
        self.assertIsInstance(strat, OutreachStrategy)


if __name__ == "__main__":
    unittest.main()
