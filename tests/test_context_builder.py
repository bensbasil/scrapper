"""
tests/test_context_builder.py
-----------------------------
Unit tests for ProspectContext, EvidenceItem, ScoreCard, and ProspectContextBuilder.
Covers:
1. ProspectContext construction
2. Evidence preservation and provenance
3. Score polarity and semantics
4. Missing optional data handling
5. Serialization and token-efficient summary
6. Independence from LLM APIs
7. Independence from PostgreSQL / live databases
8. OutreachGenerator integration and backward compatibility
"""

import unittest
from schemas.context import ProspectContext, EvidenceItem, ScoreCard
from ai.context_builder import ProspectContextBuilder
from analyzer.outreach_generator import OutreachGenerator, OutreachDrafts


class TestProspectContextBuilder(unittest.TestCase):

    def setUp(self):
        self.builder = ProspectContextBuilder()

        # Rich sample pipeline stage data
        self.sample_business = {
            "business_name": "Zenith Fitness Club",
            "category": "Gym",
            "address": "123 MG Road, Kochi, Kerala",
            "city": "Kochi",
            "state": "Kerala",
            "phone": "+91 98765 43210",
            "website": "https://zenithfitness.com",
            "google_rating": 3.8,
            "review_count": 85,
        }

        self.sample_analysis = {
            "business_name": "Zenith Fitness Club",
            "website_url": "https://zenithfitness.com",
            "website_exists": True,
            "ssl_enabled": False,
            "mobile_friendly": False,
        }

        self.sample_scoring = {
            "business_name": "Zenith Fitness Club",
            "website_url": "https://zenithfitness.com",
            "opportunity_score": 75.0, # High digital deficiency = high sales pitch opportunity
            "website_quality_score": 70.0, # Weakness penalty
            "seo_score": 60.0, # Weakness penalty
            "automation_need_score": 80.0,
            "likely_service_match": ["web development", "automation"],
            "detected_pain_points": ["SSL missing (Not secure)", "Likely not mobile friendly"],
        }

        self.sample_tech = {
            "cms": "WordPress",
            "frontend_framework": "jQuery",
            "analytics_tools": ["Google Analytics 4"],
        }

        self.sample_emails = {
            "extracted_emails": [
                {"email": "contact@zenithfitness.com", "syntax_valid": True, "mx_record_exists": True, "confidence_score": 0.95}
            ]
        }

        self.sample_decision = {
            "decision_maker_name": "Vikram Seth",
            "candidates": [
                {"name": "Vikram Seth", "role": "Managing Director", "confidence": 0.88, "source": "/about"}
            ]
        }

        self.sample_conversion = {
            "conversion_friction_score": 85.0,
            "conversion_health_score": 25.0,
            "booking_flow_exists": False,
            "whatsapp_available": False,
            "conversion_issues": ["No online appointment booking or reservation engine", "No WhatsApp widget"],
        }

        self.sample_review_mine = {
            "review_health_score": 40.0,
            "recurring_complaints": ["Front desk never answers calls", "Cannot book trial classes online"],
            "recurring_praise": ["Great personal trainers"],
            "pain_summary": "Communication friction and booking bottleneck",
        }

        self.sample_competitors = {
            "competitor_gap_summary": "Rival Gym 'FitZone' has a direct 24/7 online booking system and higher 4.6 rating.",
            "competitors": [
                {"name": "FitZone", "rating": 4.6, "opportunity_score": 25.0, "score_gap": 50.0}
            ]
        }

        self.sample_intent = {
            "intent_score": 80.0,
            "hiring_signal_score": 70.0,
            "outreach_urgency": "urgent",
            "top_intent_signals": ["Active technical hiring: Receptionist / Lead Coordinator"],
        }

        self.sample_hiring = {
            "is_hiring": True,
            "hiring_roles": ["Lead Coordinator", "Front Desk Manager"],
        }

        self.sample_health = {
            "overall_health_score": 42.0, # Low health = struggling presence
            "website_health_score": 30.0,
        }

        self.sample_opportunity = {
            "service_recommendations": [
                {"service_name": "Automated Booking Engine", "impact_explanation": "Stop losing trial memberships after hours."}
            ],
            "opportunity_reasoning": "High friction in capturing leads via phone.",
        }

    def test_prospect_context_construction(self):
        """Test building full ProspectContext with complete stage data."""
        ctx = self.builder.build_context(
            business_data=self.sample_business,
            analysis_data=self.sample_analysis,
            scoring_data=self.sample_scoring,
            tech_data=self.sample_tech,
            email_data=self.sample_emails,
            decision_data=self.sample_decision,
            conversion_data=self.sample_conversion,
            review_mine_data=self.sample_review_mine,
            competitor_data=self.sample_competitors,
            intent_data=self.sample_intent,
            hiring_data=self.sample_hiring,
            health_data=self.sample_health,
            opportunity_data=self.sample_opportunity,
        )

        self.assertIsInstance(ctx, ProspectContext)
        self.assertEqual(ctx.business.business_name, "Zenith Fitness Club")
        self.assertEqual(ctx.business.address, "123 MG Road, Kochi, Kerala")
        self.assertEqual(ctx.enrichment.decision_maker_name, "Vikram Seth")
        self.assertEqual(ctx.enrichment.cms, "WordPress")
        self.assertFalse(ctx.intelligence.booking_flow_exists)
        self.assertEqual(ctx.intent.outreach_urgency, "urgent")
        self.assertGreater(len(ctx.evidence), 5)
        self.assertGreater(len(ctx.summary_bullets), 0)

    def test_evidence_preservation(self):
        """Test that factual observations from various stages are preserved as EvidenceItems."""
        ctx = self.builder.build_context(
            business_data=self.sample_business,
            analysis_data=self.sample_analysis,
            conversion_data=self.sample_conversion,
            review_mine_data=self.sample_review_mine,
            competitor_data=self.sample_competitors,
            hiring_data=self.sample_hiring,
        )

        # Technical evidence
        tech_items = ctx.get_evidence_by_category("technical")
        self.assertTrue(any("SSL" in item.claim for item in tech_items))
        self.assertTrue(any("mobile" in item.claim.lower() for item in tech_items))

        # Conversion evidence
        conv_items = ctx.get_evidence_by_category("conversion")
        self.assertTrue(any("booking" in item.claim.lower() for item in conv_items))

        # Reputation / Review evidence
        rep_items = ctx.get_evidence_by_category("reputation")
        self.assertTrue(any("Front desk never answers calls" in item.claim for item in rep_items))

        # Competition evidence
        comp_items = ctx.get_evidence_by_category("competition")
        self.assertTrue(any("FitZone" in item.claim for item in comp_items))

        # Intent evidence
        intent_items = ctx.get_evidence_by_category("intent")
        self.assertTrue(any("Lead Coordinator" in item.claim for item in intent_items))

    def test_score_polarity_and_semantics(self):
        """Verify sales_opportunity_score and digital_health_rating maintain explicit polarities."""
        ctx = self.builder.build_context(
            business_data=self.sample_business,
            scoring_data=self.sample_scoring, # opportunity_score = 75.0 (high need)
            health_data=self.sample_health,   # overall_health_score = 42.0 (poor health)
            intent_data=self.sample_intent,   # intent_score = 80.0 (urgent)
        )

        # sales_opportunity_score: higher = greater deficiency
        self.assertEqual(ctx.scores.sales_opportunity_score, 75.0)
        # digital_health_rating: higher = healthier
        self.assertEqual(ctx.scores.digital_health_rating, 42.0)
        # buying_intent_score
        self.assertEqual(ctx.scores.buying_intent_score, 80.0)
        self.assertEqual(ctx.scores.outreach_urgency, "urgent")

        # Subscore penalties
        self.assertEqual(ctx.scores.website_weakness_penalty, 70.0)
        self.assertEqual(ctx.scores.seo_weakness_penalty, 60.0)
        self.assertEqual(ctx.scores.automation_need_penalty, 80.0)

    def test_missing_optional_data(self):
        """Test building context when all optional stages are None (e.g. offline or unanalyzed)."""
        ctx = self.builder.build_context(
            business_data={"business_name": "Bare Minimum Store"}
        )

        self.assertIsInstance(ctx, ProspectContext)
        self.assertEqual(ctx.business.business_name, "Bare Minimum Store")
        self.assertEqual(ctx.scores.sales_opportunity_score, 0.0)
        self.assertEqual(ctx.scores.digital_health_rating, 0.0)
        self.assertIsNone(ctx.enrichment)
        self.assertIsNone(ctx.intelligence)
        self.assertIsNone(ctx.intent)
        self.assertIsNone(ctx.opportunity)
        self.assertGreater(len(ctx.summary_bullets), 0)

    def test_serialization(self):
        """Test serialization to dict, JSON, and token-efficient plain text summary."""
        ctx = self.builder.build_context(
            business_data=self.sample_business,
            analysis_data=self.sample_analysis,
            scoring_data=self.sample_scoring,
            decision_data=self.sample_decision,
            review_mine_data=self.sample_review_mine,
            competitor_data=self.sample_competitors,
            health_data=self.sample_health,
        )

        # JSON round-trip
        json_str = ctx.model_dump_json()
        self.assertIsInstance(json_str, str)
        reloaded = ProspectContext.model_validate_json(json_str)
        self.assertEqual(reloaded.business.business_name, "Zenith Fitness Club")
        self.assertEqual(reloaded.scores.sales_opportunity_score, 75.0)

        # Token-efficient summary
        summary = ctx.to_token_efficient_summary()
        self.assertIn("Zenith Fitness Club", summary)
        self.assertIn("Sales Opportunity Score: 75.0/100", summary)
        self.assertIn("Digital Health Rating: 42.0/100", summary)
        self.assertIn("Vikram Seth", summary)
        self.assertIn("Front desk never answers calls", summary)

    def test_context_builder_does_not_require_llm(self):
        """Verify context builder executes with zero external LLM API dependencies."""
        # Builder must not raise any exceptions even without API keys
        ctx = self.builder.build_context(
            business_data=self.sample_business,
            scoring_data=self.sample_scoring
        )
        self.assertIsNotNone(ctx)

    def test_context_builder_does_not_require_postgresql(self):
        """Verify context builder executes with zero database access."""
        # Operates purely in-memory
        ctx = self.builder.build_context(
            business_data={"business_name": "In Memory Corp", "city": "Bengaluru"}
        )
        self.assertEqual(ctx.business.business_name, "In Memory Corp")

    def test_outreach_generator_consumes_prospect_context(self):
        """Verify OutreachGenerator enriches outreach angles and prompt using ProspectContext."""
        ctx = self.builder.build_context(
            business_data=self.sample_business,
            analysis_data=self.sample_analysis,
            scoring_data=self.sample_scoring,
            decision_data=self.sample_decision,
            review_mine_data=self.sample_review_mine,
            competitor_data=self.sample_competitors,
            intent_data=self.sample_intent,
            opportunity_data=self.sample_opportunity,
        )

        generator = OutreachGenerator()
        drafts = generator.generate_outreach(
            score_data=self.sample_scoring,
            analysis_data=self.sample_analysis,
            prospect_context=ctx
        )

        self.assertIsInstance(drafts, OutreachDrafts)
        self.assertEqual(drafts.business_name, "Zenith Fitness Club")

        # Decision maker resolved from context
        self.assertIn("Vikram Seth", drafts.cold_email_draft)

        # Context-enriched angles
        angles_text = " ".join(drafts.outreach_angles)
        self.assertTrue(
            "Customer Voice" in angles_text or "Front desk never answers calls" in angles_text,
            "Outreach angles should include customer complaints from context"
        )
        self.assertTrue(
            "Competitor Pressure" in angles_text or "FitZone" in angles_text,
            "Outreach angles should include competitor gap from context"
        )

        # Enriched prompt template
        self.assertIn("Additional Evidence Context:", drafts.ai_prompt_template)
        self.assertIn("Zenith Fitness Club", drafts.ai_prompt_template)

    def test_outreach_generator_backward_compatibility(self):
        """Verify OutreachGenerator still functions with 2 positional arguments without context."""
        generator = OutreachGenerator()
        score_data = {
            "business_name": "Classic Gym",
            "opportunity_score": 80.0,
            "likely_service_match": ["web development"],
            "detected_pain_points": ["No website detected"]
        }
        analysis_data = {"category": "gym", "decision_maker_name": "Rajesh"}

        drafts = generator.generate_outreach(score_data, analysis_data)
        self.assertIsInstance(drafts, OutreachDrafts)
        self.assertIn("Rajesh", drafts.cold_email_draft)
        self.assertNotIn("Additional Evidence Context:", drafts.ai_prompt_template)


if __name__ == "__main__":
    unittest.main()
