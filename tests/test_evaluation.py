"""
tests/test_evaluation.py
------------------------
Comprehensive test suite for Phase 2E AI Evaluation Foundation.
Validates deterministic evaluation of OpportunityAnalysis and OutreachStrategy
against ProspectContext without LLM, network, or database dependencies.
"""

import unittest
from unittest.mock import patch

from schemas.business import Business
from schemas.context import ProspectContext, ScoreCard, EvidenceItem
from schemas.ai import OpportunityAnalysis, CommercialRecommendation, OutreachStrategy
from evaluation.models import EvaluationResult, ComponentEvaluation, HeuristicFlag, BatchEvaluationSummary
from evaluation.evaluators import OpportunityEvaluator, OutreachEvaluator, EvaluationRunner
from evaluation.datasets.fixtures import (
    get_strong_evidence_good_reasoning_fixture,
    get_strong_evidence_poor_reasoning_fixture,
    get_unsupported_hallucination_fixture,
    get_opportunity_consistent_outreach_inconsistent_fixture,
    get_insufficient_evidence_fixture,
    get_deterministic_fallback_fixture,
    get_all_synthetic_fixtures,
)


class TestAIEvaluationFoundation(unittest.TestCase):
    """Unit tests for Phase 2E evaluation models and deterministic evaluators."""

    def setUp(self):
        self.runner = EvaluationRunner()
        self.opp_evaluator = OpportunityEvaluator()
        self.outreach_evaluator = OutreachEvaluator()

    # -------------------------------------------------------------------------
    # 1. Structural validity passes for valid outputs
    # -------------------------------------------------------------------------
    def test_structural_validity_passes_for_valid_outputs(self):
        fixture = get_strong_evidence_good_reasoning_fixture()
        res = self.runner.evaluate(
            context=fixture["context"],
            opportunity_analysis=fixture["opportunity_analysis"],
            outreach_strategy=fixture["outreach_strategy"]
        )

        self.assertTrue(res.structural_validity)
        self.assertTrue(res.passed)
        self.assertGreaterEqual(res.overall_score, 0.70)
        self.assertEqual(len(res.issues), 0)
        self.assertIsNotNone(res.opportunity_evaluation)
        self.assertIsNotNone(res.outreach_evaluation)
        self.assertTrue(res.opportunity_evaluation.structural_validity)
        self.assertTrue(res.outreach_evaluation.structural_validity)

    # -------------------------------------------------------------------------
    # 2. Structural validity fails for malformed outputs
    # -------------------------------------------------------------------------
    def test_structural_validity_fails_for_malformed_outputs(self):
        fixture = get_strong_evidence_good_reasoning_fixture()
        context = fixture["context"]

        # Malformed opportunity analysis (too short diagnosis, invalid category, invalid confidence)
        malformed_opp = OpportunityAnalysis.model_construct(
            executive_diagnosis="Too short",
            primary_pain_category="nonexistent_category",
            strategic_pitch_angle="",
            confidence_score=1.5,  # out of bounds
            reasoning_mode="unknown_mode",
            evidence_sufficiency="unknown",
            recommendations=[]
        )

        opp_eval, flags = self.opp_evaluator.evaluate(context, malformed_opp)
        self.assertFalse(opp_eval.structural_validity)
        self.assertFalse(opp_eval.passed)
        self.assertLessEqual(opp_eval.score, 0.40)
        self.assertGreater(len(opp_eval.issues), 0)

        # Malformed outreach strategy (empty body and subject)
        malformed_outreach = OutreachStrategy.model_construct(
            positioning_summary="",
            primary_angle="",
            cold_email_subject="",
            cold_email_body="",
            whatsapp_message="",
            confidence_score=0.9,
            reasoning_mode="ai",
            evidence_sufficiency="sufficient"
        )

        out_eval, flags = self.outreach_evaluator.evaluate(context, malformed_outreach)
        self.assertFalse(out_eval.structural_validity)
        self.assertFalse(out_eval.passed)
        self.assertLessEqual(out_eval.score, 0.40)

        # Runner-level aggregation
        res = self.runner.evaluate(
            context=context,
            opportunity_analysis=malformed_opp,
            outreach_strategy=malformed_outreach
        )
        self.assertFalse(res.structural_validity)
        self.assertFalse(res.passed)

    # -------------------------------------------------------------------------
    # 3. Evidence grounding detects supported claims
    # -------------------------------------------------------------------------
    def test_evidence_grounding_detects_supported_claims(self):
        fixture = get_strong_evidence_good_reasoning_fixture()
        res = self.runner.evaluate(
            context=fixture["context"],
            opportunity_analysis=fixture["opportunity_analysis"],
            outreach_strategy=fixture["outreach_strategy"]
        )

        self.assertEqual(res.grounding_score, 1.0)
        self.assertEqual(len(res.opportunity_evaluation.unsupported_claims), 0)
        self.assertGreater(len(res.opportunity_evaluation.supported_claims), 0)

        # Verify heuristic details contain confirmed_supported flags
        supported_flags = [f for f in res.heuristic_details if f.status == "confirmed_supported"]
        self.assertGreater(len(supported_flags), 0)

    # -------------------------------------------------------------------------
    # 4. Evidence grounding detects unsupported claims
    # -------------------------------------------------------------------------
    def test_evidence_grounding_detects_unsupported_claims(self):
        fixture = get_unsupported_hallucination_fixture()
        res = self.runner.evaluate(
            context=fixture["context"],
            opportunity_analysis=fixture["opportunity_analysis"],
            outreach_strategy=fixture["outreach_strategy"]
        )

        # Grounding score must be low due to completely fabricated evidence citations
        self.assertLess(res.grounding_score, 0.5)
        self.assertGreater(len(res.opportunity_evaluation.unsupported_claims), 0)
        self.assertFalse(res.passed)

        # Contains flagged unsupported citations
        unsupported_flags = [f for f in res.heuristic_details if f.status == "potentially_unsupported"]
        self.assertGreater(len(unsupported_flags), 0)
        self.assertTrue(any("Missing SSL" in f.claim for f in unsupported_flags))

    # -------------------------------------------------------------------------
    # 5. Consistency checks detect contradictory pain points / services
    # -------------------------------------------------------------------------
    def test_consistency_checks_detect_contradictory_pain_points_and_services(self):
        fixture = get_opportunity_consistent_outreach_inconsistent_fixture()
        res = self.runner.evaluate(
            context=fixture["context"],
            opportunity_analysis=fixture["opportunity_analysis"],
            outreach_strategy=fixture["outreach_strategy"]
        )

        # Outreach consistency should be penalized because pain point and service diverged
        self.assertFalse(res.passed)
        self.assertLess(res.consistency_score, 0.8)
        self.assertTrue(any("diverges from OpportunityAnalysis" in issue for issue in res.issues))
        self.assertTrue(any("does not match OpportunityAnalysis" in issue for issue in res.issues))

    # -------------------------------------------------------------------------
    # 6. Hallucination detector catches obvious contradictions
    # -------------------------------------------------------------------------
    def test_hallucination_detector_catches_obvious_contradictions(self):
        fixture = get_unsupported_hallucination_fixture()
        res = self.runner.evaluate(
            context=fixture["context"],
            opportunity_analysis=fixture["opportunity_analysis"],
            outreach_strategy=fixture["outreach_strategy"]
        )

        self.assertFalse(res.passed)
        self.assertGreater(len(res.hallucination_flags), 0)

        # Specifically check website absence contradiction
        website_contradictions = [
            f for f in res.heuristic_details
            if f.flag_type == "contradiction_website_exists"
        ]
        self.assertGreater(len(website_contradictions), 0)
        self.assertTrue(any("https://radiantsmiledental.com" in f.reason for f in website_contradictions))

        # Check high rating contradiction
        rating_contradictions = [
            f for f in res.heuristic_details
            if f.flag_type == "contradiction_rating_high"
        ]
        self.assertGreater(len(rating_contradictions), 0)
        self.assertTrue(any("4.9" in f.reason for f in rating_contradictions))

    # -------------------------------------------------------------------------
    # 7. Polarity contradiction detection (praising deficient presence)
    # -------------------------------------------------------------------------
    def test_polarity_contradiction_detected(self):
        fixture = get_strong_evidence_poor_reasoning_fixture()
        res = self.runner.evaluate(
            context=fixture["context"],
            opportunity_analysis=fixture["opportunity_analysis"],
            outreach_strategy=fixture["outreach_strategy"]
        )

        self.assertFalse(res.passed)
        polarity_flags = [
            f for f in res.heuristic_details
            if f.flag_type == "polarity_contradiction_praised_deficiency"
        ]
        self.assertGreater(len(polarity_flags), 0)
        self.assertTrue(any("Polarity Contradiction" in issue for issue in res.issues))

    # -------------------------------------------------------------------------
    # 8. Insufficient evidence handled correctly
    # -------------------------------------------------------------------------
    def test_insufficient_evidence_handled_correctly(self):
        fixture = get_insufficient_evidence_fixture()
        res = self.runner.evaluate(
            context=fixture["context"],
            opportunity_analysis=fixture["opportunity_analysis"],
            outreach_strategy=fixture["outreach_strategy"]
        )

        self.assertTrue(res.passed)
        self.assertEqual(len(res.hallucination_flags), 0)
        self.assertEqual(len(res.issues), 0)
        self.assertGreaterEqual(res.overall_score, 0.70)
        self.assertTrue(res.structural_validity)

    # -------------------------------------------------------------------------
    # 9. Deterministic fallback handled correctly
    # -------------------------------------------------------------------------
    def test_deterministic_fallback_handled_correctly(self):
        fixture = get_deterministic_fallback_fixture()
        res = self.runner.evaluate(
            context=fixture["context"],
            opportunity_analysis=fixture["opportunity_analysis"],
            outreach_strategy=fixture["outreach_strategy"]
        )

        self.assertTrue(res.passed)
        self.assertEqual(len(res.hallucination_flags), 0)
        self.assertEqual(len(res.issues), 0)
        self.assertGreaterEqual(res.overall_score, 0.80)

    # -------------------------------------------------------------------------
    # 10. Score bounds: all scores between 0.0 and 1.0 across all scenarios
    # -------------------------------------------------------------------------
    def test_score_bounds_all_scores_between_zero_and_one(self):
        fixtures = get_all_synthetic_fixtures()
        for name, fix in fixtures.items():
            res = self.runner.evaluate(
                context=fix["context"],
                opportunity_analysis=fix.get("opportunity_analysis"),
                outreach_strategy=fix.get("outreach_strategy")
            )
            for score_name, score_val in [
                ("overall_score", res.overall_score),
                ("grounding_score", res.grounding_score),
                ("relevance_score", res.relevance_score),
                ("consistency_score", res.consistency_score),
                ("evidence_coverage_score", res.evidence_coverage_score),
            ]:
                self.assertGreaterEqual(
                    score_val, 0.0,
                    f"Fixture '{name}' metric {score_name} ({score_val}) < 0.0"
                )
                self.assertLessEqual(
                    score_val, 1.0,
                    f"Fixture '{name}' metric {score_name} ({score_val}) > 1.0"
                )

    # -------------------------------------------------------------------------
    # 11. Pure in-memory: 0 live LLM calls, 0 network, 0 database calls
    # -------------------------------------------------------------------------
    @patch("ai.client.LLMClient.generate_structured")
    @patch("database.db.DatabaseManager.get_connection")
    def test_pure_in_memory_no_network_no_llm_no_db(self, mock_db, mock_llm):
        fixtures = get_all_synthetic_fixtures()
        summary = self.runner.evaluate_batch(list(fixtures.values()))

        # Ensure no external calls occurred during evaluation
        mock_llm.assert_not_called()
        mock_db.assert_not_called()

        self.assertEqual(summary.total_evaluated, 6)
        self.assertEqual(summary.passed_count, 3)
        self.assertEqual(summary.failed_count, 3)
        self.assertGreater(summary.average_overall_score, 0.5)


if __name__ == "__main__":
    unittest.main()
