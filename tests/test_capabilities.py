"""
tests/test_capabilities.py
--------------------------
Unit tests for Phase 3B Application Capability Layer.
Validates capability contracts, registry discovery, safety policies,
and execution wrapping without live network, browser, or database calls.
"""

import unittest
from unittest.mock import MagicMock

from application.policies.classification import PolicyClass
from application.contracts.base import CapabilityResult
from application.contracts.inputs import (
    DiscoverProspectsInput,
    AuditWebsiteTechInput,
    EnrichLeadershipSocialInput,
    MineBusinessIntelligenceInput,
    CalculateHealthAndScoresInput,
    AssembleProspectContextInput,
    SynthesizeOpportunityInput,
    FormulateOutreachStrategyInput,
    EvaluateAIReasoningInput,
    RenderOutreachDraftsInput,
)
from application.capabilities.registry import CapabilityRegistry
from evaluation.datasets.fixtures import get_strong_evidence_good_reasoning_fixture


class TestApplicationCapabilities(unittest.TestCase):
    """Test suite for application capability tool contracts and registry."""

    def setUp(self):
        self.registry = CapabilityRegistry.default_registry()
        self.fixture = get_strong_evidence_good_reasoning_fixture()
        self.context = self.fixture["context"]
        self.opp_analysis = self.fixture["opportunity_analysis"]
        self.outreach_strategy = self.fixture["outreach_strategy"]

    # -------------------------------------------------------------------------
    # 1. Registry Discovery & Metadata
    # -------------------------------------------------------------------------
    def test_registry_contains_all_ten_capabilities(self):
        capabilities = self.registry.list_capabilities()
        self.assertEqual(len(capabilities), 10)

        expected_names = {
            "discover_prospects",
            "audit_website_tech",
            "enrich_leadership_social",
            "mine_business_intelligence",
            "calculate_health_and_scores",
            "assemble_prospect_context",
            "synthesize_opportunity_analysis",
            "formulate_outreach_strategy",
            "evaluate_ai_reasoning",
            "render_outreach_drafts",
        }
        registered_names = {c.name for c in capabilities}
        self.assertEqual(registered_names, expected_names)

    def test_registry_get_descriptor(self):
        descriptor = self.registry.get("synthesize_opportunity_analysis")
        self.assertIsNotNone(descriptor)
        self.assertEqual(descriptor.name, "synthesize_opportunity_analysis")
        self.assertEqual(descriptor.policy_class, PolicyClass.READ)
        self.assertEqual(descriptor.input_schema, SynthesizeOpportunityInput)

    # -------------------------------------------------------------------------
    # 2. Safety Policy Classifications
    # -------------------------------------------------------------------------
    def test_safety_policy_classifications(self):
        # 9 READ capabilities
        read_capabilities = [
            "discover_prospects",
            "audit_website_tech",
            "enrich_leadership_social",
            "mine_business_intelligence",
            "calculate_health_and_scores",
            "assemble_prospect_context",
            "synthesize_opportunity_analysis",
            "formulate_outreach_strategy",
            "evaluate_ai_reasoning",
        ]
        for name in read_capabilities:
            desc = self.registry.get(name)
            self.assertEqual(desc.policy_class, PolicyClass.READ, f"{name} should be classified as READ")

        # 1 WRITE capability (staging output)
        draft_desc = self.registry.get("render_outreach_drafts")
        self.assertEqual(draft_desc.policy_class, PolicyClass.WRITE)

    # -------------------------------------------------------------------------
    # 3. Context Assembly Capability
    # -------------------------------------------------------------------------
    def test_assemble_prospect_context_capability(self):
        res = self.registry.execute(
            "assemble_prospect_context",
            {
                "business_data": {
                    "business_name": "Rapid Rooter Plumbing",
                    "category": "Plumber",
                    "website": "https://rapidrooter.com",
                    "google_rating": 3.8,
                    "review_count": 42
                },
                "scoring_data": {
                    "opportunity_score": 75.0,
                    "website_quality_score": 30.0,
                    "seo_score": 40.0
                }
            }
        )
        self.assertTrue(res.success)
        self.assertEqual(res.capability_name, "assemble_prospect_context")
        self.assertEqual(res.data.business.business_name, "Rapid Rooter Plumbing")
        self.assertEqual(res.data.scores.sales_opportunity_score, 75.0)

    # -------------------------------------------------------------------------
    # 4. Deterministic Scoring Calculation Capability
    # -------------------------------------------------------------------------
    def test_calculate_health_and_scores_capability(self):
        res = self.registry.execute(
            "calculate_health_and_scores",
            {
                "business_name": "Apex Dental",
                "website_quality_score": 20.0,
                "seo_score": 30.0,
                "conversion_friction_score": 80.0
            }
        )
        self.assertTrue(res.success)
        scorecard = res.data
        self.assertGreater(scorecard.sales_opportunity_score, 60.0)
        self.assertLess(scorecard.digital_health_rating, 40.0)
        self.assertEqual(scorecard.outreach_urgency, "high")

    # -------------------------------------------------------------------------
    # 5. Opportunity Analysis Reasoning Capability
    # -------------------------------------------------------------------------
    def test_synthesize_opportunity_analysis_capability(self):
        res = self.registry.execute(
            "synthesize_opportunity_analysis",
            {"context": self.context}
        )
        self.assertTrue(res.success)
        analysis = res.data
        self.assertIsNotNone(analysis.executive_diagnosis)
        self.assertEqual(analysis.primary_pain_category, "conversion")
        self.assertIn(analysis.reasoning_mode, {"ai", "deterministic_fallback"})

    # -------------------------------------------------------------------------
    # 6. Outreach Strategy Reasoning Capability
    # -------------------------------------------------------------------------
    def test_formulate_outreach_strategy_capability(self):
        res = self.registry.execute(
            "formulate_outreach_strategy",
            {
                "context": self.context,
                "opportunity_analysis": self.opp_analysis
            }
        )
        self.assertTrue(res.success)
        strategy = res.data
        self.assertIsNotNone(strategy.positioning_summary)
        self.assertIsNotNone(strategy.cold_email_subject)
        self.assertIsNotNone(strategy.cold_email_body)

    # -------------------------------------------------------------------------
    # 7. AI Reasoning Evaluation Capability
    # -------------------------------------------------------------------------
    def test_evaluate_ai_reasoning_capability(self):
        res = self.registry.execute(
            "evaluate_ai_reasoning",
            {
                "context": self.context,
                "opportunity_analysis": self.opp_analysis,
                "outreach_strategy": self.outreach_strategy
            }
        )
        self.assertTrue(res.success)
        eval_res = res.data
        self.assertTrue(eval_res.passed)
        self.assertGreaterEqual(eval_res.overall_score, 0.70)
        self.assertEqual(len(eval_res.hallucination_flags), 0)

    # -------------------------------------------------------------------------
    # 8. Render Outreach Drafts Capability
    # -------------------------------------------------------------------------
    def test_render_outreach_drafts_capability(self):
        res = self.registry.execute(
            "render_outreach_drafts",
            {
                "context": self.context,
                "outreach_strategy": self.outreach_strategy,
                "persist_to_db": False
            }
        )
        self.assertTrue(res.success)
        draft = res.data
        self.assertEqual(draft.business_name, self.context.business.business_name)
        self.assertIsNotNone(draft.cold_email_draft)
        self.assertIsNotNone(draft.whatsapp_draft)

    # -------------------------------------------------------------------------
    # 9. Mocked Website Audit Capability
    # -------------------------------------------------------------------------
    def test_audit_website_tech_capability(self):
        mock_w_analyzer = MagicMock()
        mock_w_analyzer.analyze.return_value = {
            "website_active": True,
            "mobile_friendly": True,
            "load_time_seconds": 1.2,
            "cms": "WordPress",
            "detected_technologies": ["WordPress", "Yoast"],
            "forms_detected": True,
            "phone_number": "+13125550199",
            "emails": ["info@apex.com"],
            "social_links_found": ["https://facebook.com/apex"]
        }

        mock_t_analyzer = MagicMock()
        mock_t_analyzer.analyze.return_value = {
            "ssl_valid": True,
            "dns_resolves": True
        }

        from application.capabilities.website_audit import AuditWebsiteTechCapability
        from unittest.mock import patch
        cap = AuditWebsiteTechCapability(
            website_analyzer=mock_w_analyzer,
            tech_analyzer=mock_t_analyzer
        )

        with patch("scraper.utils.ssrf.validate_url_for_ssrf", return_value=(True, "")):
            output = cap.execute(
                AuditWebsiteTechInput(
                    business_name="Apex Plumbing",
                    website_url="https://apex.com"
                )
            )
        self.assertTrue(output.is_active)
        self.assertTrue(output.has_ssl)
        self.assertTrue(output.is_mobile_friendly)
        self.assertEqual(output.cms, "WordPress")

    # -------------------------------------------------------------------------
    # 10. Mocked Discovery Capability
    # -------------------------------------------------------------------------
    def test_discover_prospects_capability(self):
        from schemas.business import Business
        mock_scraper = MagicMock()
        mock_scraper.scrape.return_value = [
            Business(
                business_name="City Plumbing Co",
                category="Plumber",
                website="https://cityplumbing.com",
                google_rating=4.2,
                review_count=80
            )
        ]

        from application.capabilities.discovery import DiscoverProspectsCapability
        cap = DiscoverProspectsCapability(gmaps_scraper=mock_scraper)
        output = cap.execute(
            DiscoverProspectsInput(
                query="plumbers",
                location="Chicago",
                limit=10,
                source="gmaps"
            )
        )
        self.assertEqual(output.total_found, 1)
        self.assertEqual(output.businesses[0].business_name, "City Plumbing Co")

    # -------------------------------------------------------------------------
    # 11. Error Handling & Validation
    # -------------------------------------------------------------------------
    def test_unregistered_capability_returns_failure(self):
        res = self.registry.execute("nonexistent_tool", {})
        self.assertFalse(res.success)
        self.assertIn("not registered", res.error)

    def test_invalid_parameters_rejected(self):
        # limit < 1 violates Pydantic constraint
        res = self.registry.execute("discover_prospects", {"query": "plumbers", "limit": 0})
        self.assertFalse(res.success)
        self.assertIsNotNone(res.error)


if __name__ == "__main__":
    unittest.main()
