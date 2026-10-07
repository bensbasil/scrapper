import unittest
from dataclasses import dataclass
from pydantic import ValidationError

from schemas import (
    Business,
    BusinessEnrichment,
    ValidatedEmail,
    DecisionMakerCandidate,
    BusinessIntelligence,
    CompetitorComparison,
    IntentProfile,
    IntentSignal,
    Opportunity,
    ServiceRecommendation,
    OutreachDraft,
    PipelineResult,
    StageExecution,
)


class TestSchemas(unittest.TestCase):

    def test_business_schema_defaults_and_validation(self):
        b = Business(business_name="Test Cafe")
        self.assertEqual(b.business_name, "Test Cafe")
        self.assertEqual(b.outreach_status, "new")
        self.assertEqual(b.recrawl_tier, "tier3")
        self.assertEqual(b.source_platforms, [])

        with self.assertRaises(ValidationError):
            Business(business_name="Test Cafe", outreach_status="invalid_status")

    def test_business_enrichment_schema(self):
        email = ValidatedEmail(
            email="contact@testcafe.com",
            syntax_valid=True,
            mx_record_exists=True,
            confidence_score=0.95
        )
        dm = DecisionMakerCandidate(
            name="John Doe",
            role="Founder",
            source="about_page",
            confidence=0.85
        )
        enrichment = BusinessEnrichment(
            business_name="Test Cafe",
            website_url="https://testcafe.com",
            cms="WordPress",
            frontend_framework="React",
            analytics_tools=["Google Analytics 4"],
            validated_emails=[email],
            decision_maker_name="John Doe",
            decision_makers=[dm],
            social_activity_score=45.0
        )

        data = enrichment.model_dump()
        self.assertEqual(data["cms"], "WordPress")
        self.assertEqual(len(data["validated_emails"]), 1)
        self.assertEqual(data["validated_emails"][0]["confidence_score"], 0.95)
        self.assertEqual(data["decision_makers"][0]["name"], "John Doe")

    def test_business_intelligence_schema(self):
        comp = CompetitorComparison(
            name="Rival Gym",
            website="https://rivalgym.com",
            rating=4.8,
            opportunity_score=35.0,
            score_gap=25.0
        )
        bi = BusinessIntelligence(
            business_name="Test Gym",
            overall_health_score=72.5,
            website_health_score=65.0,
            conversion_friction_score=30.0,
            booking_flow_exists=True,
            conversion_issues=["Missing WhatsApp CTA"],
            recurring_complaints=["Crowded evenings"],
            competitors=[comp]
        )

        self.assertEqual(bi.overall_health_score, 72.5)
        self.assertTrue(bi.booking_flow_exists)
        self.assertEqual(len(bi.competitors), 1)
        self.assertEqual(bi.competitors[0].score_gap, 25.0)

    def test_intent_profile_schema(self):
        profile = IntentProfile(
            business_id=101,
            business_name="Test Dental Clinic",
            intent_score=85.0,
            hiring_signal_score=90.0,
            outreach_urgency="urgent",
            top_intent_signals=["Active tech hiring: React Developer", "Stale copyright: 2021"]
        )

        self.assertEqual(profile.intent_score, 85.0)
        self.assertEqual(profile.outreach_urgency, "urgent")

        with self.assertRaises(ValidationError):
            IntentProfile(business_name="Test", outreach_urgency="invalid_urgency")

    def test_opportunity_schema(self):
        rec = ServiceRecommendation(
            service_name="Custom Web Redesign",
            impact_explanation="Fix mobile responsiveness to capture mobile visitors."
        )
        opp = Opportunity(
            business_name="Test Clinic",
            opportunity_score=75.0,
            website_quality_score=70.0,
            service_recommendations=[rec],
            opportunity_reasoning="Website is not mobile responsive and has no booking flow."
        )

        self.assertEqual(opp.opportunity_score, 75.0)
        self.assertEqual(len(opp.service_recommendations), 1)
        self.assertEqual(opp.service_recommendations[0].service_name, "Custom Web Redesign")

    def test_outreach_draft_schema(self):
        draft = OutreachDraft(
            business_name="Test Salon",
            decision_maker_name="Alice Smith",
            outreach_angles=["Online booking friction"],
            cold_email_draft="Hi Alice,\n\nI noticed your salon...",
            whatsapp_draft="Hi Alice! Quick question about your booking flow...",
            generation_mode="gemini"
        )

        self.assertEqual(draft.decision_maker_name, "Alice Smith")
        self.assertEqual(draft.generation_mode, "gemini")

    def test_pipeline_result_with_nested_models(self):
        b = Business(business_name="Omni Studio", website="https://omnistudio.com")
        stage1 = StageExecution(stage="scrape", success=True, duration_ms=120.5)
        stage2 = StageExecution(stage="analyze", success=True, duration_ms=450.0)

        result = PipelineResult(
            business_id=55,
            business_name="Omni Studio",
            success=True,
            opportunity_score=68.0,
            intent_score=80.0,
            outreach_urgency="high",
            stages=[stage1, stage2],
            business=b
        )

        serialized = result.model_dump()
        self.assertEqual(serialized["business_name"], "Omni Studio")
        self.assertEqual(len(serialized["stages"]), 2)
        self.assertEqual(serialized["business"]["website"], "https://omnistudio.com")

    def test_from_dataclass_adapter(self):
        @dataclass
        class MockLegacyDataclass:
            business_name: str
            category: str
            website: str

        mock_obj = MockLegacyDataclass(
            business_name="Legacy Bar",
            category="Bar",
            website="https://legacybar.com"
        )

        # Validates that Pydantic V2 from_attributes=True works on existing dataclasses
        b = Business.model_validate(mock_obj)
        self.assertEqual(b.business_name, "Legacy Bar")
        self.assertEqual(b.website, "https://legacybar.com")


if __name__ == "__main__":
    unittest.main()
