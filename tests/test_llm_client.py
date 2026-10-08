"""
tests/test_llm_client.py
------------------------
Unit tests for the provider-independent LLM boundary (Phase 2B).
Tests provider configuration, structured output generation, error handling,
validation failure observability, and backward compatibility.
All tests use mocked HTTP/responses - zero live network/API calls.
"""

import os
import json
import unittest
from unittest.mock import patch, MagicMock
import requests

from ai.config import LLMConfig
from ai.exceptions import (
    LLMError,
    LLMUnavailableError,
    LLMProviderError,
    LLMResponseParsingError,
    LLMValidationError,
)
from ai.client import LLMClient
from schemas.ai import (
    OpportunityAnalysis,
    CommercialRecommendation,
    OutreachStrategy,
    OutreachDraftResponse,
)
from analyzer.outreach_generator import OutreachGenerator, OutreachDrafts


class TestLLMConfig(unittest.TestCase):
    """Tests for LLMConfig resolution, environment parsing, and defaults."""

    def test_default_config(self):
        config = LLMConfig()
        self.assertEqual(config.provider, "auto")
        self.assertIsNone(config.api_key)
        self.assertIsNone(config.model)
        self.assertEqual(config.temperature, 0.2)
        self.assertEqual(config.timeout, 15.0)
        self.assertEqual(config.max_tokens, 1024)

    @patch.dict(os.environ, {}, clear=True)
    def test_from_env_no_keys_defaults_to_none(self):
        config = LLMConfig.from_env()
        self.assertEqual(config.provider, "none")
        self.assertIsNone(config.api_key)
        self.assertIsNone(config.model)

    @patch.dict(os.environ, {"GEMINI_API_KEY": "test-gemini-key"}, clear=True)
    def test_from_env_detects_gemini(self):
        config = LLMConfig.from_env()
        self.assertEqual(config.provider, "gemini")
        self.assertEqual(config.api_key, "test-gemini-key")
        self.assertEqual(config.model, "gemini-1.5-flash")

    @patch.dict(os.environ, {"OPENAI_API_KEY": "test-openai-key"}, clear=True)
    def test_from_env_detects_openai(self):
        config = LLMConfig.from_env()
        self.assertEqual(config.provider, "openai")
        self.assertEqual(config.api_key, "test-openai-key")
        self.assertEqual(config.model, "gpt-4o-mini")

    @patch.dict(
        os.environ,
        {
            "GEMINI_API_KEY": "gemini-key",
            "OPENAI_API_KEY": "openai-key",
            "LLM_PROVIDER": "openai",
            "OPENAI_MODEL": "gpt-4o",
            "LLM_TIMEOUT": "25.0",
            "LLM_TEMPERATURE": "0.5",
        },
        clear=True,
    )
    def test_from_env_explicit_provider_selection_and_overrides(self):
        config = LLMConfig.from_env()
        self.assertEqual(config.provider, "openai")
        self.assertEqual(config.api_key, "openai-key")
        self.assertEqual(config.model, "gpt-4o")
        self.assertEqual(config.timeout, 25.0)
        self.assertEqual(config.temperature, 0.5)


class TestLLMClientStructuredGeneration(unittest.TestCase):
    """Tests for structured generation, parsing, validation, and mocked responses."""

    def test_client_is_available_flag(self):
        unavailable_client = LLMClient(config=LLMConfig(provider="none"))
        self.assertFalse(unavailable_client.is_available)

        with self.assertRaises(LLMUnavailableError):
            unavailable_client.generate_structured(
                prompt="Hello",
                response_model=OutreachDraftResponse,
            )

        gemini_client = LLMClient(config=LLMConfig(provider="gemini", api_key="valid-key"))
        self.assertTrue(gemini_client.is_available)

        openai_client = LLMClient(config=LLMConfig(provider="openai", api_key="valid-key"))
        self.assertTrue(openai_client.is_available)

    @patch("requests.post")
    def test_successful_gemini_structured_response(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_payload = {
            "cold_email_draft": "Hi Dr. Smith, noticed your website is missing SSL. We can help.",
            "whatsapp_draft": "Hi Dr. Smith! Quick note: your website has an SSL issue. Want a free fix video?"
        }
        mock_response.json.return_value = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {"text": json.dumps(mock_payload)}
                        ]
                    }
                }
            ]
        }
        mock_post.return_value = mock_response

        client = LLMClient(config=LLMConfig(provider="gemini", api_key="mock-key"))
        result = client.generate_structured(
            prompt="Write outreach for dental clinic",
            response_model=OutreachDraftResponse,
        )

        self.assertIsInstance(result, OutreachDraftResponse)
        self.assertIn("SSL", result.cold_email_draft)
        self.assertIn("free fix video", result.whatsapp_draft)
        self.assertEqual(mock_post.call_count, 1)

    @patch("requests.post")
    def test_successful_openai_structured_response(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_payload = {
            "positioning_summary": "Position as a conversion and reputation specialist.",
            "primary_angle": "Customer Voice",
            "cold_email_subject": "Quick fix for Apex Plumbing's contact form",
            "cold_email_body": "Hi John, noticed several customers reported booking friction on your site. We fix this.",
            "whatsapp_message": "Hi John! Saw your contact form issue. Can I send a 2-min fix video?",
            "call_opening_hook": "Hey John, calling because your online booking flow is leaking inquiries.",
            "anticipated_objection": "We already have a web developer.",
            "objection_counter": "Totally understand - this is just a 2-minute fix your current dev can implement today.",
            "cited_evidence_points": ["Customer review: form submitted but never heard back", "Missing mobile CTA"],
        }
        mock_response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(mock_payload)
                    }
                }
            ]
        }
        mock_post.return_value = mock_response

        client = LLMClient(config=LLMConfig(provider="openai", api_key="mock-key"))
        result = client.generate_structured(
            prompt="Write outreach strategy for Apex Plumbing",
            response_model=OutreachStrategy,
        )

        self.assertIsInstance(result, OutreachStrategy)
        self.assertEqual(result.primary_angle, "Customer Voice")
        self.assertIn("Apex Plumbing", result.cold_email_subject)
        self.assertEqual(len(result.cited_evidence_points), 2)

    @patch("requests.post")
    def test_opportunity_analysis_structured_parsing(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_payload = {
            "executive_diagnosis": "Prospect has strong local reputation but loses 30% of traffic due to lack of online scheduling.",
            "primary_pain_category": "conversion",
            "recommendations": [
                {
                    "service_name": "Online Booking Flow Integration",
                    "target_problem": "Customers cannot book appointments after hours",
                    "commercial_impact": "Recovers estimated $4,000/mo in lost appointment requests",
                    "suggested_pricing_tier": "core"
                }
            ],
            "strategic_pitch_angle": "The Leaky Bucket: Turn missed after-hours searches into booked revenue",
            "cited_evidence_points": ["No online appointment widget found", "4 reviews complaining about phone wait times"],
            "confidence_score": 0.95
        }
        # Test markdown code block stripping (```json ... ```)
        wrapped_json = f"```json\n{json.dumps(mock_payload)}\n```"
        mock_response.json.return_value = {
            "choices": [
                {"message": {"content": wrapped_json}}
            ]
        }
        mock_post.return_value = mock_response

        client = LLMClient(config=LLMConfig(provider="openai", api_key="mock-key"))
        result = client.generate_structured(
            prompt="Diagnose commercial opportunities",
            response_model=OpportunityAnalysis,
        )

        self.assertIsInstance(result, OpportunityAnalysis)
        self.assertEqual(result.primary_pain_category, "conversion")
        self.assertEqual(len(result.recommendations), 1)
        self.assertIsInstance(result.recommendations[0], CommercialRecommendation)
        self.assertEqual(result.recommendations[0].suggested_pricing_tier, "core")

    @patch("requests.post")
    def test_malformed_json_response_raises_parsing_error(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [
                {"message": {"content": "This is plain conversational text, not JSON."}}
            ]
        }
        mock_post.return_value = mock_response

        client = LLMClient(config=LLMConfig(provider="openai", api_key="mock-key"))
        with self.assertRaises(LLMResponseParsingError) as ctx:
            client.generate_structured(
                prompt="Test prompt",
                response_model=OutreachDraftResponse,
            )
        self.assertIn("Failed to parse LLM response as JSON", str(ctx.exception))

    @patch("requests.post")
    def test_schema_validation_failure_raises_validation_error(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        # Missing required field 'whatsapp_draft'
        mock_payload = {"cold_email_draft": "Only email draft provided"}
        mock_response.json.return_value = {
            "choices": [
                {"message": {"content": json.dumps(mock_payload)}}
            ]
        }
        mock_post.return_value = mock_response

        client = LLMClient(config=LLMConfig(provider="openai", api_key="mock-key"))
        with self.assertRaises(LLMValidationError) as ctx:
            client.generate_structured(
                prompt="Test prompt",
                response_model=OutreachDraftResponse,
            )
        self.assertIn("Failed to validate LLM response against OutreachDraftResponse", str(ctx.exception))

    @patch("requests.post")
    def test_provider_http_error_raises_provider_error(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_post.return_value = mock_response

        client = LLMClient(config=LLMConfig(provider="gemini", api_key="mock-key"))
        with self.assertRaises(LLMProviderError) as ctx:
            client.generate_structured(
                prompt="Test prompt",
                response_model=OutreachDraftResponse,
            )
        self.assertEqual(ctx.exception.status_code, 500)

    @patch("requests.post")
    def test_provider_timeout_raises_provider_error(self, mock_post):
        mock_post.side_effect = requests.exceptions.Timeout("Connection timed out")

        client = LLMClient(config=LLMConfig(provider="gemini", api_key="mock-key"))
        with self.assertRaises(LLMProviderError) as ctx:
            client.generate_structured(
                prompt="Test prompt",
                response_model=OutreachDraftResponse,
            )
        self.assertIn("timed out", str(ctx.exception))

    @patch("requests.post")
    def test_generate_structured_safe_returns_none_on_error(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.text = "Rate limit exceeded"
        mock_post.return_value = mock_response

        client = LLMClient(config=LLMConfig(provider="gemini", api_key="mock-key"))
        result = client.generate_structured_safe(
            prompt="Test prompt",
            response_model=OutreachDraftResponse,
        )
        self.assertIsNone(result)


class TestOutreachGeneratorLLMIntegration(unittest.TestCase):
    """Tests for OutreachGenerator utilizing LLMClient with safe fallback."""

    def test_outreach_generator_falls_back_when_no_llm_available(self):
        # Create an OutreachGenerator with unavailable client
        disabled_client = LLMClient(config=LLMConfig(provider="none"))
        generator = OutreachGenerator(llm_client=disabled_client)

        score_data = {
            "business_name": "Acme Motors",
            "opportunity_score": 70.0,
            "likely_service_match": ["SEO", "Web Design"],
            "detected_pain_points": ["No mobile responsiveness", "Slow loading"],
        }
        analysis_data = {"category": "auto repair", "decision_maker_name": "Bob"}

        drafts = generator.generate_outreach(score_data, analysis_data)

        self.assertIsInstance(drafts, OutreachDrafts)
        self.assertEqual(drafts.business_name, "Acme Motors")
        self.assertIn("Bob", drafts.cold_email_draft)
        self.assertIn("Bob", drafts.whatsapp_draft)
        self.assertTrue(len(drafts.outreach_angles) > 0)

    def test_outreach_generator_uses_structured_ai_when_client_succeeds(self):
        mock_client = MagicMock(spec=LLMClient)
        mock_client.is_available = True
        mock_client.config = LLMConfig(provider="gemini", api_key="key")
        mock_client.generate_structured_safe.return_value = OutreachDraftResponse(
            cold_email_draft="AI-generated high-converting cold email for Acme Motors",
            whatsapp_draft="AI-generated punchy WhatsApp copy"
        )

        generator = OutreachGenerator(llm_client=mock_client)
        score_data = {
            "business_name": "Acme Motors",
            "opportunity_score": 85.0,
            "likely_service_match": ["Automation"],
            "detected_pain_points": ["Broken contact form"],
        }

        drafts = generator.generate_outreach(score_data)

        self.assertIsInstance(drafts, OutreachDrafts)
        self.assertEqual(drafts.cold_email_draft, "AI-generated high-converting cold email for Acme Motors")
        self.assertEqual(drafts.whatsapp_draft, "AI-generated punchy WhatsApp copy")
        mock_client.generate_structured_safe.assert_called_once()

    def test_outreach_generator_falls_back_when_ai_generation_returns_none(self):
        mock_client = MagicMock(spec=LLMClient)
        mock_client.is_available = True
        mock_client.config = LLMConfig(provider="openai", api_key="key")
        mock_client.generate_structured_safe.return_value = None  # Simulated failure

        generator = OutreachGenerator(llm_client=mock_client)
        score_data = {
            "business_name": "Acme Motors",
            "opportunity_score": 85.0,
            "likely_service_match": ["Automation"],
            "detected_pain_points": ["Broken contact form"],
        }

        drafts = generator.generate_outreach(score_data)

        # Should seamlessly fall back to rule-based templates
        self.assertIsInstance(drafts, OutreachDrafts)
        self.assertIn("Subject:", drafts.cold_email_draft)
        self.assertTrue(len(drafts.whatsapp_draft) > 10)


if __name__ == "__main__":
    unittest.main()
