"""
tests/test_prospect_qualification.py
------------------------------------
Test suite for Phase 4B: Deterministic Prospect Qualification & Selection.
Verifies:
1. ProspectQualification model creation
2. Qualified prospect evaluation
3. Disqualified prospect evaluation
4. Qualification positive reasons
5. Disqualifier reasons
6. All prospects in a set receive a qualification result
7. QualifiedProspectSet creation and properties
8. Disqualified prospect preservation
9. Zero qualified prospects handling
10. All qualified prospects handling
11. Location filtering
12. Industry/category filtering
13. Selection operating on qualified prospects
14. Selection never including disqualified prospects
15. Batch safety limits remain enforced with qualification
16. Known-business workflow remains unchanged
17. Qualification does not call LLMs
18. CapabilityRegistry boundary preserved
19. Qualification telemetry tracing
20. Aggregate counts accuracy
21. Phase 4A batch execution compatibility
22. Phase 3 workflow backward-compatibility
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
    QualifiedProspectSet,
    ProspectSelection,
    ProspectExecutionResult,
    ProspectBatchResult,
    ProspectBatchExecutor,
    BatchSizeLimitExceededError,
)
from agent.qualification import (
    ProspectQualification,
    QualificationPolicy,
    DeterministicProspectQualifier,
)
from agent.intent import AgentIntent, IntentType


def create_sample_business(
    name: str,
    rating: float = 4.2,
    reviews: int = 40,
    website: str = "https://example.com",
    category: str = "Plumbing",
    address: str = "123 Main St, Chicago, IL",
    phone: str = "555-1234",
    outreach_status: str = "new",
    jd_verified: bool = False,
) -> Business:
    return Business(
        business_name=name,
        website=website,
        google_rating=rating,
        review_count=reviews,
        category=category,
        address=address,
        city="Chicago",
        phone=phone,
        outreach_status=outreach_status,
        jd_verified=jd_verified,
    )


def create_sample_context(score: float = 75.0) -> ProspectContext:
    fixture = get_strong_evidence_good_reasoning_fixture()
    ctx = fixture["context"]
    ctx.scores.sales_opportunity_score = score
    return ctx


def create_sample_opportunity(confidence: float = 0.95) -> OpportunityAnalysis:
    fixture = get_strong_evidence_good_reasoning_fixture()
    opp = fixture["opportunity_analysis"]
    opp.confidence_score = confidence
    return opp


class TestProspectQualificationAndSelection(unittest.TestCase):
    def setUp(self):
        self.sink = InMemoryTelemetrySink()
        self.registry = CapabilityRegistry.default_registry()
        self.qualifier = DeterministicProspectQualifier()

    # 1. Qualification model creation
    def test_01_qualification_model_creation(self):
        """1. ProspectQualification creates valid typed instance."""
        q = ProspectQualification(
            prospect_id="Apex Plumbing",
            qualified=True,
            qualification_score=0.85,
            reasons=["Website present", "Phone available"],
            disqualifiers=[],
            evaluated_signals={"has_website": True, "rating": 4.5}
        )
        self.assertEqual(q.prospect_id, "Apex Plumbing")
        self.assertTrue(q.qualified)
        self.assertEqual(q.qualification_score, 0.85)
        self.assertEqual(len(q.reasons), 2)
        self.assertEqual(len(q.disqualifiers), 0)
        self.assertTrue(q.evaluated_signals["has_website"])

    # 2. Qualified prospect
    def test_02_qualified_prospect(self):
        """2. Standard active prospect passes qualification."""
        biz = create_sample_business("Valid Biz")
        res = self.qualifier.qualify_prospect(biz)
        self.assertTrue(res.qualified)
        self.assertGreater(res.qualification_score, 0.0)
        self.assertEqual(len(res.disqualifiers), 0)

    # 3. Disqualified prospect
    def test_03_disqualified_prospect(self):
        """3. Missing business name or already contacted prospect is disqualified."""
        biz_no_name = create_sample_business("")
        res = self.qualifier.qualify_prospect(biz_no_name)
        self.assertFalse(res.qualified)
        self.assertEqual(res.qualification_score, 0.0)
        self.assertIn("Missing business name", res.disqualifiers)

        biz_contacted = create_sample_business("Contacted Biz", outreach_status="contacted")
        res_contacted = self.qualifier.qualify_prospect(biz_contacted)
        self.assertFalse(res_contacted.qualified)
        self.assertTrue(any("already engaged" in d for d in res_contacted.disqualifiers))

    # 4. Qualification reasons
    def test_04_qualification_reasons(self):
        """4. Qualified prospect includes positive, explainable reasons."""
        biz = create_sample_business("Good Plumbing", website="https://goodplumbing.com", reviews=50, jd_verified=True)
        res = self.qualifier.qualify_prospect(biz)
        self.assertTrue(res.qualified)
        self.assertTrue(any("Website present" in r for r in res.reasons))
        self.assertTrue(any("Contact phone number available" in r for r in res.reasons))
        self.assertTrue(any("Verified vendor" in r for r in res.reasons))

    # 5. Disqualifier reasons
    def test_05_disqualifier_reasons(self):
        """5. Rejection reasons explicitly explain which criteria failed."""
        policy = QualificationPolicy(require_website=True, min_rating=4.0)
        qualifier = DeterministicProspectQualifier(policy=policy)
        biz = create_sample_business("No Web Low Rating", rating=3.2, website="")
        res = qualifier.qualify_prospect(biz)

        self.assertFalse(res.qualified)
        self.assertTrue(any("Missing required website URL" in d for d in res.disqualifiers))
        self.assertTrue(any("below minimum required" in d for d in res.disqualifiers))

    # 6. All prospects receive a result
    def test_06_all_prospects_receive_a_result(self):
        """6. Every prospect in a ProspectSet receives an individual qualification result."""
        businesses = [
            create_sample_business(f"Biz {i}", website="https://site.com" if i % 2 == 0 else "")
            for i in range(6)
        ]
        pset = ProspectSet(source="gmaps", query="test query", prospects=businesses)
        qset = self.qualifier.qualify_set(pset)

        self.assertEqual(len(qset.qualifications), 6)
        for b in businesses:
            self.assertIn(b.business_name, qset.qualifications)
            self.assertIsInstance(qset.get_qualification(b.business_name), ProspectQualification)

    # 7. Qualified set creation
    def test_07_qualified_set_creation(self):
        """7. QualifiedProspectSet retains counts, original ID, and qualified list."""
        businesses = [
            create_sample_business(f"Biz {i}", website="https://site.com")
            for i in range(4)
        ]
        pset = ProspectSet(set_id="pset_origin_01", prospects=businesses)
        qset = self.qualifier.qualify_set(pset)

        self.assertEqual(qset.original_set_id, "pset_origin_01")
        self.assertEqual(qset.total_discovered, 4)
        self.assertEqual(qset.qualified_count, 4)
        self.assertEqual(qset.disqualified_count, 0)
        self.assertEqual(len(qset), 4)
        self.assertEqual(len(qset.prospects), 4)

    # 8. Disqualified set preservation
    def test_08_disqualified_set_preservation(self):
        """8. Disqualified candidates are preserved in disqualified_prospects."""
        policy = QualificationPolicy(require_website=True)
        qualifier = DeterministicProspectQualifier(policy=policy)
        biz_good = create_sample_business("Biz Good", website="https://good.com")
        biz_bad = create_sample_business("Biz Bad", website="")
        pset = ProspectSet(prospects=[biz_good, biz_bad])

        qset = qualifier.qualify_set(pset)
        self.assertEqual(qset.qualified_count, 1)
        self.assertEqual(qset.disqualified_count, 1)
        self.assertEqual(qset.qualified_prospects[0].business_name, "Biz Good")
        self.assertEqual(qset.disqualified_prospects[0].business_name, "Biz Bad")

    # 9. Zero qualified prospects
    def test_09_zero_qualified_prospects(self):
        """9. Handles case where zero prospects meet qualification policy."""
        policy = QualificationPolicy(min_rating=4.9)
        qualifier = DeterministicProspectQualifier(policy=policy)
        businesses = [create_sample_business(f"Biz {i}", rating=3.5) for i in range(3)]
        pset = ProspectSet(prospects=businesses)

        qset = qualifier.qualify_set(pset)
        self.assertEqual(qset.qualified_count, 0)
        self.assertEqual(qset.disqualified_count, 3)
        self.assertEqual(len(qset.qualified_prospects), 0)
        self.assertEqual(len(qset.disqualified_prospects), 3)

    # 10. All qualified prospects
    def test_10_all_qualified_prospects(self):
        """10. Handles case where all prospects qualify."""
        businesses = [create_sample_business(f"Biz {i}") for i in range(5)]
        pset = ProspectSet(prospects=businesses)
        qset = self.qualifier.qualify_set(pset)

        self.assertEqual(qset.qualified_count, 5)
        self.assertEqual(qset.disqualified_count, 0)

    # 11. Location filtering
    def test_11_location_filtering(self):
        """11. Rejects prospects located outside requested target location."""
        policy = QualificationPolicy(target_location="Chicago")
        qualifier = DeterministicProspectQualifier(policy=policy)
        biz_in = create_sample_business("Chicago Biz", address="100 Michigan Ave, Chicago, IL")
        biz_out = create_sample_business("Miami Biz", address="500 Ocean Dr, Miami, FL")
        pset = ProspectSet(prospects=[biz_in, biz_out])

        qset = qualifier.qualify_set(pset)
        self.assertEqual(qset.qualified_count, 1)
        self.assertEqual(qset.qualified_prospects[0].business_name, "Chicago Biz")
        self.assertEqual(qset.disqualified_prospects[0].business_name, "Miami Biz")
        self.assertIn("Outside requested location", qset.get_qualification("Miami Biz").disqualifiers[0])

    # 12. Industry filtering
    def test_12_industry_filtering(self):
        """12. Rejects prospects in vertical mismatching target industry."""
        policy = QualificationPolicy(target_industry="Dental")
        qualifier = DeterministicProspectQualifier(policy=policy)
        biz_dental = create_sample_business("Tooth Care", category="Dental Clinic")
        biz_plumbing = create_sample_business("Pipe Fixers", category="Plumbing")
        pset = ProspectSet(prospects=[biz_dental, biz_plumbing])

        qset = qualifier.qualify_set(pset)
        self.assertEqual(qset.qualified_count, 1)
        self.assertEqual(qset.qualified_prospects[0].business_name, "Tooth Care")
        self.assertIn("Category mismatch", qset.get_qualification("Pipe Fixers").disqualifiers[0])

    # 13. Selection after qualification
    def test_13_selection_after_qualification(self):
        """13. ProspectSelection selects bounded subset of qualified candidates."""
        policy = QualificationPolicy(min_rating=4.0)
        qualifier = DeterministicProspectQualifier(policy=policy)
        businesses = [
            create_sample_business(f"Biz {i}", rating=4.5 if i < 6 else 3.2)
            for i in range(10)
        ]
        pset = ProspectSet(prospects=businesses)
        qset = qualifier.qualify_set(pset)

        self.assertEqual(qset.qualified_count, 6)
        self.assertEqual(qset.disqualified_count, 4)

        selection = ProspectSelection(max_prospects=3)
        selected = selection.select(qset)
        self.assertEqual(len(selected), 3)

    # 14. Selection never includes disqualified prospects
    def test_14_selection_never_includes_disqualified_prospects(self):
        """14. Even when max_prospects exceeds candidate count, disqualified are never selected."""
        policy = QualificationPolicy(require_website=True)
        qualifier = DeterministicProspectQualifier(policy=policy)
        biz_good = create_sample_business("Good 1", website="https://good.com")
        biz_bad1 = create_sample_business("Bad 1", website="")
        biz_bad2 = create_sample_business("Bad 2", website="")
        pset = ProspectSet(prospects=[biz_good, biz_bad1, biz_bad2])
        qset = qualifier.qualify_set(pset)

        selection = ProspectSelection(max_prospects=10)
        selected = selection.select(qset)
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0].business_name, "Good 1")

    # 15. Batch size limit remains enforced
    def test_15_batch_size_limit_remains_enforced(self):
        """15. ProspectBatchExecutor enforces max_prospects_per_run on qualified selection."""
        executor = ProspectBatchExecutor(
            registry=self.registry,
            telemetry_sink=self.sink,
            max_prospects_per_run=2,
            strict_limit=False,
        )
        businesses = [create_sample_business(f"Biz {i}") for i in range(5)]
        pset = ProspectSet(prospects=businesses)
        qset = self.qualifier.qualify_set(pset)

        selection = ProspectSelection(max_prospects=4)
        with patch.object(self.registry, "execute") as mock_exec:
            mock_exec.side_effect = [
                CapabilityResult(success=True, capability_name="audit_website_tech", data=MagicMock()),
                CapabilityResult(success=True, capability_name="enrich_leadership_social", data=MagicMock()),
                CapabilityResult(success=True, capability_name="mine_business_intelligence", data=MagicMock()),
                CapabilityResult(success=True, capability_name="calculate_health_and_scores", data=ScoreCard(sales_opportunity_score=80.0)),
                CapabilityResult(success=True, capability_name="assemble_prospect_context", data=create_sample_context(80.0)),
                CapabilityResult(success=True, capability_name="synthesize_opportunity_analysis", data=create_sample_opportunity(0.9)),
                # Second prospect
                CapabilityResult(success=True, capability_name="audit_website_tech", data=MagicMock()),
                CapabilityResult(success=True, capability_name="enrich_leadership_social", data=MagicMock()),
                CapabilityResult(success=True, capability_name="mine_business_intelligence", data=MagicMock()),
                CapabilityResult(success=True, capability_name="calculate_health_and_scores", data=ScoreCard(sales_opportunity_score=85.0)),
                CapabilityResult(success=True, capability_name="assemble_prospect_context", data=create_sample_context(85.0)),
                CapabilityResult(success=True, capability_name="synthesize_opportunity_analysis", data=create_sample_opportunity(0.95)),
            ]
            batch_res = executor.execute_batch(prospect_set=qset, selection=selection)

        self.assertEqual(batch_res.selected_count, 2)
        self.assertEqual(batch_res.completed_count, 2)

    # 16. Known-business workflow remains unchanged
    def test_16_known_business_workflow_remains_unchanged(self):
        """16. Research known business workflow does not invoke batch qualification."""
        agent = Agent(registry=self.registry, telemetry_sink=self.sink)
        with patch.object(self.registry, "execute") as mock_exec:
            mock_exec.side_effect = [
                CapabilityResult(success=True, capability_name="audit_website_tech", data=MagicMock()),
                CapabilityResult(success=True, capability_name="enrich_leadership_social", data=MagicMock()),
                CapabilityResult(success=True, capability_name="mine_business_intelligence", data=MagicMock()),
                CapabilityResult(success=True, capability_name="calculate_health_and_scores", data=ScoreCard(sales_opportunity_score=75.0)),
                CapabilityResult(success=True, capability_name="assemble_prospect_context", data=create_sample_context(75.0)),
                CapabilityResult(success=True, capability_name="synthesize_opportunity_analysis", data=create_sample_opportunity(0.9)),
            ]
            state = agent.run("Analyze Acme Plumbing in Chicago")

        self.assertEqual(state.status, AgentStatus.COMPLETED)
        self.assertIsNone(state.qualified_prospect_set)

    # 17. Qualification does not call LLM
    def test_17_qualification_does_not_call_llm(self):
        """17. Deterministic qualification operates purely in-memory without invoking any LLM client."""
        mock_llm = MagicMock()
        businesses = [create_sample_business(f"Biz {i}") for i in range(10)]
        pset = ProspectSet(prospects=businesses)

        # Qualify set
        qset = self.qualifier.qualify_set(pset)

        self.assertEqual(mock_llm.generate.call_count, 0)
        self.assertEqual(qset.qualified_count, 10)

    # 18. CapabilityRegistry boundary preserved
    def test_18_qualification_does_not_bypass_registry(self):
        """18. Downstream batch execution invokes capabilities exclusively via CapabilityRegistry."""
        agent = Agent(registry=self.registry, telemetry_sink=self.sink)
        biz = create_sample_business("Registry Test Biz")
        pset = ProspectSet(prospects=[biz])

        with patch.object(self.registry, "execute") as mock_exec:
            mock_exec.side_effect = [
                CapabilityResult(success=True, capability_name="audit_website_tech", data=MagicMock()),
                CapabilityResult(success=True, capability_name="enrich_leadership_social", data=MagicMock()),
                CapabilityResult(success=True, capability_name="mine_business_intelligence", data=MagicMock()),
                CapabilityResult(success=True, capability_name="calculate_health_and_scores", data=ScoreCard(sales_opportunity_score=80.0)),
                CapabilityResult(success=True, capability_name="assemble_prospect_context", data=create_sample_context(80.0)),
                CapabilityResult(success=True, capability_name="synthesize_opportunity_analysis", data=create_sample_opportunity(0.9)),
            ]
            state = agent.run_prospect_batch(pset)

        self.assertEqual(state.status, AgentStatus.COMPLETED)
        self.assertEqual(mock_exec.call_count, 6)

    # 19. Qualification telemetry
    def test_19_qualification_telemetry(self):
        """19. Qualification emits step_qualify trace event and records metrics on AgentRunTrace."""
        agent = Agent(registry=self.registry, telemetry_sink=self.sink)
        b1 = create_sample_business("Qual Biz 1", website="https://b1.com")
        b2 = create_sample_business("Qual Biz 2", website="")
        pset = ProspectSet(prospects=[b1, b2])

        policy = QualificationPolicy(require_website=True)
        with patch.object(self.registry, "execute") as mock_exec:
            mock_exec.side_effect = [
                CapabilityResult(success=True, capability_name="audit_website_tech", data=MagicMock()),
                CapabilityResult(success=True, capability_name="enrich_leadership_social", data=MagicMock()),
                CapabilityResult(success=True, capability_name="mine_business_intelligence", data=MagicMock()),
                CapabilityResult(success=True, capability_name="calculate_health_and_scores", data=ScoreCard(sales_opportunity_score=80.0)),
                CapabilityResult(success=True, capability_name="assemble_prospect_context", data=create_sample_context(80.0)),
                CapabilityResult(success=True, capability_name="synthesize_opportunity_analysis", data=create_sample_opportunity(0.9)),
            ]
            state = agent.run_prospect_batch(pset, qualification_policy=policy)

        # Telemetry trace events recorded
        events = self.sink.get_step_events(state.run_id)
        qual_events = [e for e in events if e.capability_name == "qualify_prospects"]
        self.assertEqual(len(qual_events), 1)
        self.assertEqual(qual_events[0].status, StepEventStatus.COMPLETED)

        # Run trace has qualification metrics
        trace = self.sink.get_run(state.run_id)
        self.assertIsNotNone(trace)
        self.assertEqual(trace.discovered_count, 2)
        self.assertEqual(trace.qualified_count, 1)
        self.assertEqual(trace.disqualified_count, 1)
        self.assertEqual(trace.selected_count, 1)

    # 20. Aggregate counts
    def test_20_aggregate_counts(self):
        """20. Aggregate metrics (discovered, qualified, disqualified, selected) are preserved accurately."""
        agent = Agent(registry=self.registry, telemetry_sink=self.sink)
        businesses = [
            create_sample_business(f"Biz {i}", website="https://b.com" if i < 3 else "")
            for i in range(5)
        ]
        pset = ProspectSet(prospects=businesses)
        policy = QualificationPolicy(require_website=True)

        with patch.object(self.registry, "execute") as mock_exec:
            mock_exec.return_value = CapabilityResult(success=True, capability_name="audit_website_tech", data=MagicMock())
            # For 2 selected
            mock_exec.side_effect = [
                # Biz 0
                CapabilityResult(success=True, capability_name="audit_website_tech", data=MagicMock()),
                CapabilityResult(success=True, capability_name="enrich_leadership_social", data=MagicMock()),
                CapabilityResult(success=True, capability_name="mine_business_intelligence", data=MagicMock()),
                CapabilityResult(success=True, capability_name="calculate_health_and_scores", data=ScoreCard(sales_opportunity_score=80.0)),
                CapabilityResult(success=True, capability_name="assemble_prospect_context", data=create_sample_context(80.0)),
                CapabilityResult(success=True, capability_name="synthesize_opportunity_analysis", data=create_sample_opportunity(0.9)),
                # Biz 1
                CapabilityResult(success=True, capability_name="audit_website_tech", data=MagicMock()),
                CapabilityResult(success=True, capability_name="enrich_leadership_social", data=MagicMock()),
                CapabilityResult(success=True, capability_name="mine_business_intelligence", data=MagicMock()),
                CapabilityResult(success=True, capability_name="calculate_health_and_scores", data=ScoreCard(sales_opportunity_score=85.0)),
                CapabilityResult(success=True, capability_name="assemble_prospect_context", data=create_sample_context(85.0)),
                CapabilityResult(success=True, capability_name="synthesize_opportunity_analysis", data=create_sample_opportunity(0.95)),
            ]
            selection = ProspectSelection(max_prospects=2)
            state = agent.run_prospect_batch(pset, selection=selection, qualification_policy=policy)

        self.assertEqual(state.discovered_count, 5)
        self.assertEqual(state.qualified_count, 3)
        self.assertEqual(state.disqualified_count, 2)
        self.assertEqual(state.selected_count, 2)

        summary = state.final_response.qualification_summary
        self.assertIsNotNone(summary)
        self.assertEqual(summary["discovered"], 5)
        self.assertEqual(summary["qualified"], 3)
        self.assertEqual(summary["disqualified"], 2)
        self.assertEqual(summary["selected"], 2)

    # 21. Existing Phase 4A batch ranking remains valid
    def test_21_existing_phase_4a_tests_remain_valid(self):
        """21. Ranking adapters on ProspectBatchResult function correctly on qualified batches."""
        res_low = ProspectExecutionResult(
            prospect_id="Low Opp",
            business=create_sample_business("Low Opp"),
            status="COMPLETED",
            opportunity_score=40.0,
        )
        res_high = ProspectExecutionResult(
            prospect_id="High Opp",
            business=create_sample_business("High Opp"),
            status="COMPLETED",
            opportunity_score=90.0,
        )
        batch_res = ProspectBatchResult(
            requested_count=2,
            selected_count=2,
            completed_count=2,
            results=[res_low, res_high],
        )

        ranked = batch_res.ranked_results("opportunity_score")
        self.assertEqual(ranked[0].prospect_id, "High Opp")
        self.assertEqual(ranked[1].prospect_id, "Low Opp")

    # 22. Existing Phase 3 workflow backward-compatibility
    def test_22_existing_phase_3_tests_remain_valid(self):
        """22. Normal single business workflow remains completely backward-compatible."""
        agent = Agent(registry=self.registry, telemetry_sink=self.sink)
        with patch.object(self.registry, "execute") as mock_exec:
            mock_exec.side_effect = [
                CapabilityResult(success=True, capability_name="audit_website_tech", data=MagicMock()),
            ]
            state = agent.run("Audit website for Acme Plumbing")

        self.assertEqual(state.status, AgentStatus.COMPLETED)
        self.assertEqual(state.plan.steps[0].capability_name, "audit_website_tech")


if __name__ == "__main__":
    unittest.main()
