import pytest
from analyzer.outreach_generator import OutreachGenerator, OutreachDrafts

def test_outreach_generator_fallback():
    generator = OutreachGenerator()
    score_data = {
        "business_name": "Test Plumbing",
        "opportunity_score": 80.0,
        "likely_service_match": ["web development", "SEO"],
        "detected_pain_points": ["No website detected", "Missing meta title"]
    }
    analysis_data = {"category": "plumbers", "decision_maker_name": "John Doe"}
    
    drafts = generator.generate_outreach(score_data, analysis_data)
    
    assert isinstance(drafts, OutreachDrafts)
    assert drafts.business_name == "Test Plumbing"
    assert "John Doe" in drafts.cold_email_draft
    assert "Test Plumbing" in drafts.whatsapp_draft or "John Doe" in drafts.whatsapp_draft
    assert "John Doe" in drafts.ai_prompt_template
    assert len(drafts.outreach_angles) > 0

def test_outreach_ai_prompt_formatting():
    generator = OutreachGenerator()
    prompt = generator._generate_ai_prompt(
        b_name="Sample Dental",
        score=75.0,
        pain_points=["SSL missing", "Missing H1 tag"],
        services=["SEO", "web development"],
        contact_name="Dr. Smith",
        opp_reasoning="High friction for booking appointments"
    )
    
    assert "Sample Dental" in prompt
    assert "Dr. Smith" in prompt
    assert "High friction for booking appointments" in prompt
    assert "SSL missing" in prompt
