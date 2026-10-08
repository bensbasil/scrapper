"""
tests/test_opportunity_reasoner.py
----------------------------------
Unit tests for OpportunityReasoner (Phase 2C).
Tests prompt construction, structured reasoning with mock LLMClient,
insufficient evidence handling, provider failures, deterministic fallbacks,
and pure in-memory execution (zero live API / database calls).
"""

import unittest
from unittest.mock import MagicMock, patch

from schemas.business import Business
from schemas.context import ProspectContext, ScoreCard, EvidenceItem
from schemas.ai import OpportunityAnalysis, CommercialRecommendation
from schemas.opportunity import Opportunity, ServiceRecommendation
from schemas.intelligence import BusinessIntelligence
from schemas.enrichment import BusinessEnrichment
from schemas.intent import IntentProfile
from ai.opportunity_reasoner import OpportunityReasoner
from ai.client import LLMClient
from ai.config import LLMConfig
from ai.exceptions import (
    LLMProviderError,
    LLMResponseParsingError,
    LLMValidationError,
    LLMUnavailableError,
)


def _create_sample_context(
    name: str = "Apex Plumbing Co",
    sales_opp_score: float = 78.0,
    health_score: float = 42.0,
    has_website: bool = True,
    empty_evidence: bool = False,
) -> ProspectContext:
    """Helper to construct realistic sample ProspectContext."""
    business = Business(
        business_name=name,
        category="Plumbing Contractor",
        address="123 Main St, Austin, TX",
        phone="+1-512-555-0199",
        website="https://apexplumbing.example.com" if has_website else None,
    )
    scores = ScoreCard(
        sales_opportunity_score=sales_opp_score,
        digital_health_rating=health_score,
        website_weakness_penalty=65.0,
        seo_weakness_penalty=70.0,
        automation_need_penalty=80.0,
        conversion_friction_score=75.0,
        buying_intent_score=85.0,
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
        recurring_complaints=["Hard to schedule online", "No response to contact forms", "Slow quote delivery"],
        recurring_praise=["Great in-person technicians", "Fair pricing"],
        competitor_gap_summary="Local competitors have automated instant booking widgets and 4.8 star average vs 4.2.",
        trust_signals=["SSL certificate valid", "Licensed plumber badge missing"],
    )
    intent = IntentProfile(
        business_name=name,
        is_hiring=True,
        hiring_roles=["Journeyman Plumber", "Dispatcher"],
        top_intent_signals=["Active job hiring", "Recent surge in local service demand"],
    )
    opportunity = Opportunity(
        business_name=name,
        opportunity_score=sales_opp_score,
        detected_pain_points=["No online booking engine", "Missing mobile CTA"],
        service_recommendations=[
            ServiceRecommendation(
                service_name="Online Booking & Scheduling Engine",
                impact_explanation="Enables 24/7 lead capture and stops customer leakage after hours.",
            ),
            ServiceRecommendation(
                service_name="Local SEO Domination Campaign",
                impact_explanation="Optimizes metadata and schema to outrank local competitors.",
            ),
        ],
        opportunity_reasoning=f"We audited {name}'s digital presence and identified critical conversion bottlenecks.",
    )

    evidence_items = []
    if not empty_evidence:
        evidence_items = [
            EvidenceItem(
                category="technical",
                claim="Missing online appointment booking system",
                source="ConversionAnalyzer",
                value="no_booking_flow",
            ),
            EvidenceItem(
                category="reputation",
                claim="Verified reviews cite difficulty booking online",
                source="CustomerPainExtractor",
                value=3,
            ),
            EvidenceItem(
                category="competition",
                claim="Competitors outperform on instant booking accessibility",
                source="CompetitorAnalyzer",
                value="4.8 vs 4.2 rating gap",
            ),
        ]

    return ProspectContext(
        business=business,
        scores=scores,
        enrichment=enrichment,
        intelligence=intelligence,
        intent=intent,
        opportunity=opportunity,
        evidence=evidence_items,
        summary_bullets=[
            "Critical conversion friction: No online appointment flow.",
            "Recurring customer reviews complain about booking delays.",
            "Competitor gap: Nearby plumbers offer instant scheduling.",
        ],
    )


class TestOpportunityReasoner(unittest.TestCase):
    """Test suite for OpportunityReasoner."""

    def test_prompt_construction(self):
        reasoner = OpportunityReasoner(llm_client=MagicMock(spec=LLMClient))
        context = _create_sample_context()

        prompt = reasoner._build_reasoning_prompt(context)
        system_prompt = reasoner._build_system_prompt()

        # Verify identity in prompt
        self.assertIn("Apex Plumbing Co", prompt)
        self.assertIn("Plumbing Contractor", prompt)

        # Verify scores and explicit polarities
        self.assertIn("Sales Opportunity Score: 78.0/100", prompt)
        self.assertIn("Digital Health Rating: 42.0/100", prompt)
        self.assertIn("Higher = greater digital weakness", prompt)
        self.assertIn("Higher = healthier presence", prompt)

        # Verify intelligence and evidence items
        self.assertIn("Hard to schedule online", prompt)
        self.assertIn("Sarah Jenkins", prompt)
        self.assertIn("WordPress", prompt)
        self.assertIn("Missing online appointment booking system", prompt)

        # Verify system prompt guidelines
        self.assertIn("STRICT FACTUAL GROUNDING", system_prompt)
        self.assertIn("SCORE POLARITY ADHERENCE", system_prompt)

    def test_successful_structured_reasoning(self):
        mock_client = MagicMock(spec=LLMClient)
        mock_client.is_available = True
        mock_client.config = LLMConfig(provider="gemini", api_key="key")

        mock_analysis = OpportunityAnalysis(
            executive_diagnosis="Apex Plumbing loses an estimated 25% of after-hours leads due to absence of online booking.",
            primary_pain_category="conversion",
            recommendations=[
                CommercialRecommendation(
                    service_name="Automated Scheduling Integration",
                    target_problem="Customers cannot book appointments after hours",
                    commercial_impact="Recovers ~$3,500/mo in lost job bookings",
                    suggested_pricing_tier="core",
                )
            ],
            strategic_pitch_angle="The After-Hours Revenue Leak: Turn missed calls into booked jobs",
            cited_evidence_points=[
                "Missing online appointment booking system",
                "Verified reviews cite difficulty booking online",
            ],
            confidence_score=0.95,
            reasoning_mode="ai",
            evidence_sufficiency="sufficient",
        )
        mock_client.generate_structured.return_value = mock_analysis

        reasoner = OpportunityReasoner(llm_client=mock_client)
        context = _create_sample_context()

        result = reasoner.reason(context)

        self.assertIsInstance(result, OpportunityAnalysis)
        self.assertEqual(result.reasoning_mode, "ai")
        self.assertEqual(result.evidence_sufficiency, "sufficient")
        self.assertEqual(result.primary_pain_category, "conversion")
        self.assertEqual(len(result.recommendations), 1)
        self.assertIn("Apex Plumbing", result.executive_diagnosis)
        mock_client.generate_structured.assert_called_once()

    def test_insufficient_evidence_handling(self):
        mock_client = MagicMock(spec=LLMClient)
        mock_client.is_available = True

        reasoner = OpportunityReasoner(llm_client=mock_client)

        # Context with 0 scores and empty evidence
        minimal_business = Business(business_name="Ghost Store", website=None)
        minimal_context = ProspectContext(
            business=minimal_business,
            scores=ScoreCard(sales_opportunity_score=0.0, digital_health_rating=0.0),
            evidence=[],
        )

        result = reasoner.reason(minimal_context)

        self.assertIsInstance(result, OpportunityAnalysis)
        self.assertEqual(result.evidence_sufficiency, "insufficient")
        self.assertEqual(result.reasoning_mode, "deterministic_fallback")
        self.assertLessEqual(result.confidence_score, 0.4)
        self.assertIn("Insufficient verified data", result.executive_diagnosis)
        # LLM client should NOT even be called when evidence is insufficient
        mock_client.generate_structured.assert_not_called()

    def test_provider_failure_triggers_deterministic_fallback(self):
        mock_client = MagicMock(spec=LLMClient)
        mock_client.is_available = True
        mock_client.config = LLMConfig(provider="openai", api_key="key")
        mock_client.generate_structured.side_effect = LLMProviderError("Upstream API 500", status_code=500)

        reasoner = OpportunityReasoner(llm_client=mock_client)
        context = _create_sample_context()

        result = reasoner.reason(context)

        self.assertIsInstance(result, OpportunityAnalysis)
        self.assertEqual(result.reasoning_mode, "deterministic_fallback")
        self.assertEqual(result.evidence_sufficiency, "sufficient")
        self.assertIn("Apex Plumbing Co", result.executive_diagnosis)
        self.assertTrue(len(result.recommendations) > 0)
        self.assertEqual(result.recommendations[0].service_name, "Online Booking & Scheduling Engine")

    def test_malformed_llm_response_triggers_deterministic_fallback(self):
        mock_client = MagicMock(spec=LLMClient)
        mock_client.is_available = True
        mock_client.config = LLMConfig(provider="gemini", api_key="key")
        mock_client.generate_structured.side_effect = LLMResponseParsingError("Invalid JSON from LLM")

        reasoner = OpportunityReasoner(llm_client=mock_client)
        context = _create_sample_context()

        result = reasoner.reason(context)

        self.assertIsInstance(result, OpportunityAnalysis)
        self.assertEqual(result.reasoning_mode, "deterministic_fallback")

    def test_validation_failure_triggers_deterministic_fallback(self):
        mock_client = MagicMock(spec=LLMClient)
        mock_client.is_available = True
        mock_client.config = LLMConfig(provider="gemini", api_key="key")
        mock_client.generate_structured.side_effect = LLMValidationError("Field 'executive_diagnosis' missing")

        reasoner = OpportunityReasoner(llm_client=mock_client)
        context = _create_sample_context()

        result = reasoner.reason(context)

        self.assertIsInstance(result, OpportunityAnalysis)
        self.assertEqual(result.reasoning_mode, "deterministic_fallback")

    def test_no_configured_provider_uses_deterministic_fallback_immediately(self):
        mock_client = MagicMock(spec=LLMClient)
        mock_client.is_available = False

        reasoner = OpportunityReasoner(llm_client=mock_client)
        context = _create_sample_context()

        result = reasoner.reason(context)

        self.assertIsInstance(result, OpportunityAnalysis)
        self.assertEqual(result.reasoning_mode, "deterministic_fallback")
        mock_client.generate_structured.assert_not_called()

    def test_pure_in_memory_no_db_or_network(self):
        """Verifies reasoner has zero database, SQL, or network socket dependencies."""
        reasoner = OpportunityReasoner()
        self.assertFalse(hasattr(reasoner, "repo"))
        self.assertFalse(hasattr(reasoner, "db"))
        self.assertFalse(hasattr(reasoner, "conn"))
        self.assertFalse(hasattr(reasoner, "page"))

    def test_backward_compatibility_with_opportunity_pipeline(self):
        """Verifies existing Opportunity recommendations map cleanly to OpportunityAnalysis."""
        context = _create_sample_context()
        reasoner = OpportunityReasoner(llm_client=MagicMock(is_available=False))

        fallback = reasoner._build_deterministic_fallback(context)

        self.assertEqual(fallback.primary_pain_category, "conversion")
        self.assertEqual(len(fallback.recommendations), 2)
        self.assertEqual(
            fallback.recommendations[0].service_name,
            context.opportunity.service_recommendations[0].service_name,
        )
        self.assertEqual(
            fallback.recommendations[0].commercial_impact,
            context.opportunity.service_recommendations[0].impact_explanation,
        )


if __name__ == "__main__":
    unittest.main()
