"""
tests/test_outreach_reasoner.py
-------------------------------
Unit tests for OutreachReasoner (Phase 2D).
Tests prompt construction, structured strategy synthesis with mock LLMClient,
insufficient evidence handling, provider failures, deterministic fallbacks,
and integration with OutreachGenerator (zero live API / database calls).
"""

import unittest
from unittest.mock import MagicMock

from schemas.business import Business
from schemas.context import ProspectContext, ScoreCard, EvidenceItem
from schemas.ai import (
    OpportunityAnalysis,
    CommercialRecommendation,
    OutreachStrategy,
)
from schemas.enrichment import BusinessEnrichment
from schemas.intelligence import BusinessIntelligence
from schemas.intent import IntentProfile
from schemas.opportunity import Opportunity, ServiceRecommendation
from ai.outreach_reasoner import OutreachReasoner
from ai.client import LLMClient
from ai.config import LLMConfig
from ai.exceptions import (
    LLMProviderError,
    LLMResponseParsingError,
    LLMValidationError,
)
from analyzer.outreach_generator import OutreachGenerator, OutreachDrafts


def _create_sample_context_and_analysis(name: str = "Apex Plumbing Co"):
    """Helper creating realistic ProspectContext and OpportunityAnalysis."""
    business = Business(
        business_name=name,
        category="Plumbing Contractor",
        address="123 Main St, Austin, TX",
        phone="+1-512-555-0199",
        website="https://apexplumbing.example.com",
    )
    scores = ScoreCard(
        sales_opportunity_score=80.0,
        digital_health_rating=35.0,
        website_weakness_penalty=70.0,
        seo_weakness_penalty=65.0,
        automation_need_penalty=85.0,
        conversion_friction_score=80.0,
        buying_intent_score=90.0,
        outreach_urgency="urgent",
    )
    enrichment = BusinessEnrichment(
        business_name=name,
        cms="WordPress",
        chat_tools=["Contact Form 7"],
        decision_maker_name="Sarah Jenkins",
    )
    intelligence = BusinessIntelligence(
        business_name=name,
        recurring_complaints=["Online form gives error", "Called twice but went to voicemail"],
        recurring_praise=["Skilled technicians", "Prompt dispatch"],
        competitor_gap_summary="Local competitors use instant 24/7 web booking widgets.",
        trust_signals=["SSL valid"],
    )
    intent = IntentProfile(
        business_name=name,
        is_hiring=True,
        hiring_roles=["Journeyman Plumber"],
        top_intent_signals=["Active technical hiring"],
    )
    opportunity = Opportunity(
        business_name=name,
        opportunity_score=80.0,
        detected_pain_points=["Broken appointment form", "Missing mobile CTA"],
        service_recommendations=[
            ServiceRecommendation(
                service_name="Online Booking & Scheduling Engine",
                impact_explanation="Stops after-hours customer loss and captures mobile inquiries.",
            )
        ],
        opportunity_reasoning="Critical lead capture friction identified on contact pages.",
    )
    evidence = [
        EvidenceItem(
            category="conversion",
            claim="Broken contact form submission flow",
            source="ConversionAnalyzer",
            value="form_error",
        ),
        EvidenceItem(
            category="reputation",
            claim="Verified complaints regarding unreturned voicemails",
            source="CustomerPainExtractor",
            value=2,
        ),
    ]

    context = ProspectContext(
        business=business,
        scores=scores,
        enrichment=enrichment,
        intelligence=intelligence,
        intent=intent,
        opportunity=opportunity,
        evidence=evidence,
    )

    opp_analysis = OpportunityAnalysis(
        executive_diagnosis="Apex Plumbing loses estimated 30% of emergency inquiries due to contact form errors.",
        primary_pain_category="conversion",
        recommendations=[
            CommercialRecommendation(
                service_name="Automated Instant Booking Engine",
                target_problem="Contact form fails on mobile submissions",
                commercial_impact="Recovers ~$4,000/mo in lost plumbing calls",
                suggested_pricing_tier="core",
            )
        ],
        strategic_pitch_angle="The Leaky Bucket: Turn missed emergency calls into scheduled jobs",
        cited_evidence_points=["Broken contact form submission flow"],
        confidence_score=0.9,
        reasoning_mode="ai",
        evidence_sufficiency="sufficient",
    )

    return context, opp_analysis


class TestOutreachReasoner(unittest.TestCase):
    """Test suite for OutreachReasoner."""

    def test_prompt_construction(self):
        reasoner = OutreachReasoner(llm_client=MagicMock(spec=LLMClient))
        context, opp_analysis = _create_sample_context_and_analysis()

        prompt = reasoner._build_outreach_prompt(context, opp_analysis)
        system_prompt = reasoner._build_system_prompt()

        # Business identity & verified decision maker
        self.assertIn("Apex Plumbing Co", prompt)
        self.assertIn("Sarah Jenkins", prompt)

        # Opportunity analysis diagnosis
        self.assertIn("Apex Plumbing loses estimated 30%", prompt)
        self.assertIn("The Leaky Bucket", prompt)
        self.assertIn("Automated Instant Booking Engine", prompt)

        # Intelligence & evidence items
        self.assertIn("Online form gives error", prompt)
        self.assertIn("Broken contact form submission flow", prompt)

        # System prompt anti-hallucination guidelines
        self.assertIn("STRICT FACTUAL GROUNDING", system_prompt)
        self.assertIn("COPYWRITING STANDARDS", system_prompt)

    def test_successful_structured_reasoning(self):
        mock_client = MagicMock(spec=LLMClient)
        mock_client.is_available = True
        mock_client.config = LLMConfig(provider="gemini", api_key="key")

        mock_strategy = OutreachStrategy(
            positioning_summary="Position as an emergency conversion specialist for local plumbing operators.",
            primary_angle="The Leaky Bucket Angle",
            target_decision_maker_type="Owner / Operator",
            strongest_pain_point="Contact form submission error costing after-hours jobs",
            value_proposition="Recover $4,000/mo in lost emergency calls with instant 24/7 scheduling",
            recommended_service="Automated Instant Booking Engine",
            cold_email_subject="Quick note regarding Apex Plumbing's contact form",
            cold_email_body="Hi Sarah, noticed your contact form has a mobile submission bug. We can fix this in 10 minutes.",
            whatsapp_message="Hi Sarah! Quick heads up: your contact form is throwing an error. Want a 2-min fix video?",
            call_opening_hook="Hey Sarah, calling because your online booking page is dropping mobile customer requests.",
            anticipated_objection="We already have a webmaster.",
            objection_counter="Totally understand — this is a quick 2-minute fix your webmaster can apply today.",
            cited_evidence_points=["Broken contact form submission flow"],
            confidence_score=0.95,
            reasoning_mode="ai",
            evidence_sufficiency="sufficient",
        )
        mock_client.generate_structured.return_value = mock_strategy

        reasoner = OutreachReasoner(llm_client=mock_client)
        context, opp_analysis = _create_sample_context_and_analysis()

        result = reasoner.reason(context, opp_analysis)

        self.assertIsInstance(result, OutreachStrategy)
        self.assertEqual(result.reasoning_mode, "ai")
        self.assertEqual(result.evidence_sufficiency, "sufficient")
        self.assertEqual(result.primary_angle, "The Leaky Bucket Angle")
        self.assertIn("Sarah", result.cold_email_body)
        self.assertIn("Apex Plumbing", result.cold_email_subject)
        mock_client.generate_structured.assert_called_once()

    def test_insufficient_evidence_handling(self):
        mock_client = MagicMock(spec=LLMClient)
        mock_client.is_available = True

        reasoner = OutreachReasoner(llm_client=mock_client)

        minimal_business = Business(business_name="Silent LLC", website=None)
        minimal_context = ProspectContext(
            business=minimal_business,
            scores=ScoreCard(sales_opportunity_score=0.0, digital_health_rating=0.0),
            evidence=[],
        )

        result = reasoner.reason(minimal_context)

        self.assertIsInstance(result, OutreachStrategy)
        self.assertEqual(result.evidence_sufficiency, "insufficient")
        self.assertEqual(result.reasoning_mode, "deterministic_fallback")
        self.assertLessEqual(result.confidence_score, 0.4)
        self.assertIn("Exploratory", result.positioning_summary)
        mock_client.generate_structured.assert_not_called()

    def test_provider_failure_triggers_deterministic_fallback(self):
        mock_client = MagicMock(spec=LLMClient)
        mock_client.is_available = True
        mock_client.config = LLMConfig(provider="openai", api_key="key")
        mock_client.generate_structured.side_effect = LLMProviderError("HTTP 500 server error", status_code=500)

        reasoner = OutreachReasoner(llm_client=mock_client)
        context, opp_analysis = _create_sample_context_and_analysis()

        result = reasoner.reason(context, opp_analysis)

        self.assertIsInstance(result, OutreachStrategy)
        self.assertEqual(result.reasoning_mode, "deterministic_fallback")
        self.assertEqual(result.evidence_sufficiency, "sufficient")
        self.assertIn("Sarah", result.cold_email_body)
        self.assertIn("Apex Plumbing Co", result.cold_email_subject)

    def test_malformed_llm_response_triggers_deterministic_fallback(self):
        mock_client = MagicMock(spec=LLMClient)
        mock_client.is_available = True
        mock_client.config = LLMConfig(provider="gemini", api_key="key")
        mock_client.generate_structured.side_effect = LLMResponseParsingError("Invalid JSON text")

        reasoner = OutreachReasoner(llm_client=mock_client)
        context, opp_analysis = _create_sample_context_and_analysis()

        result = reasoner.reason(context, opp_analysis)

        self.assertIsInstance(result, OutreachStrategy)
        self.assertEqual(result.reasoning_mode, "deterministic_fallback")

    def test_validation_failure_triggers_deterministic_fallback(self):
        mock_client = MagicMock(spec=LLMClient)
        mock_client.is_available = True
        mock_client.config = LLMConfig(provider="gemini", api_key="key")
        mock_client.generate_structured.side_effect = LLMValidationError("Missing required fields")

        reasoner = OutreachReasoner(llm_client=mock_client)
        context, opp_analysis = _create_sample_context_and_analysis()

        result = reasoner.reason(context, opp_analysis)

        self.assertIsInstance(result, OutreachStrategy)
        self.assertEqual(result.reasoning_mode, "deterministic_fallback")

    def test_no_configured_provider_uses_deterministic_fallback_immediately(self):
        mock_client = MagicMock(spec=LLMClient)
        mock_client.is_available = False

        reasoner = OutreachReasoner(llm_client=mock_client)
        context, opp_analysis = _create_sample_context_and_analysis()

        result = reasoner.reason(context, opp_analysis)

        self.assertIsInstance(result, OutreachStrategy)
        self.assertEqual(result.reasoning_mode, "deterministic_fallback")
        mock_client.generate_structured.assert_not_called()

    def test_pure_in_memory_no_db_or_network(self):
        reasoner = OutreachReasoner()
        self.assertFalse(hasattr(reasoner, "repo"))
        self.assertFalse(hasattr(reasoner, "db"))
        self.assertFalse(hasattr(reasoner, "conn"))

    def test_outreach_generator_consumes_outreach_strategy(self):
        context, opp_analysis = _create_sample_context_and_analysis()
        strategy = OutreachStrategy(
            positioning_summary="Specialized conversion optimization partner",
            primary_angle="The Emergency Leak Angle",
            target_decision_maker_type="Owner",
            strongest_pain_point="Contact form error",
            value_proposition="Recover lost plumbing calls",
            recommended_service="Instant Booking Engine",
            cold_email_subject="Quick note about Apex Plumbing",
            cold_email_body="Hi Sarah, custom strategized cold email body here.",
            whatsapp_message="Hi Sarah! Custom strategized WhatsApp copy here.",
            call_opening_hook="Hey Sarah, calling about your booking form.",
            anticipated_objection="Too busy.",
            objection_counter="Takes only 2 minutes.",
            cited_evidence_points=["Broken contact form"],
            confidence_score=0.9,
            reasoning_mode="ai",
            evidence_sufficiency="sufficient",
        )

        generator = OutreachGenerator(llm_client=MagicMock(is_available=False))
        score_data = {
            "business_name": "Apex Plumbing Co",
            "opportunity_score": 80.0,
            "likely_service_match": ["Automation"],
            "detected_pain_points": ["Broken contact form"],
        }
        analysis_data = {"category": "plumbers", "decision_maker_name": "Sarah Jenkins"}

        drafts = generator.generate_outreach(
            score_data,
            analysis_data,
            prospect_context=context,
            outreach_strategy=strategy,
        )

        self.assertIsInstance(drafts, OutreachDrafts)
        self.assertEqual(drafts.cold_email_draft, "Hi Sarah, custom strategized cold email body here.")
        self.assertEqual(drafts.whatsapp_draft, "Hi Sarah! Custom strategized WhatsApp copy here.")
        self.assertEqual(drafts.pain_point_positioning, "Specialized conversion optimization partner")
        self.assertIn("The Emergency Leak Angle", drafts.outreach_angles[0])


if __name__ == "__main__":
    unittest.main()
