import pytest
from analyzer.scoring_engine import ScoringEngine, ScoringResult

def test_scoring_engine_no_website():
    engine = ScoringEngine()
    analysis_data = {
        "business_name": "Ghost Business",
        "website_exists": False
    }
    result = engine.calculate_scores(analysis_data)
    
    assert isinstance(result, ScoringResult)
    assert result.business_name == "Ghost Business"
    assert result.website_quality_score == 100.0
    assert result.seo_score == 100.0
    assert result.opportunity_score > 70.0
    assert "No website detected" in result.detected_pain_points
    assert "web development" in result.likely_service_match

def test_scoring_engine_perfect_site():
    engine = ScoringEngine()
    analysis_data = {
        "business_name": "Perfect Corp",
        "website_exists": True,
        "ssl_enabled": True,
        "mobile_friendly": True,
        "meta_title_exists": True,
        "meta_description_exists": True,
        "h1_exists": True,
        "contact_form_exists": True,
        "whatsapp_integration": True,
        "social_links_found": ["https://facebook.com/perfect"]
    }
    seo_data = {
        "title_optimized": True,
        "meta_description_optimized": True,
        "h1_count": 1,
        "has_viewport_tag": True,
        "has_robots_txt": True,
        "has_sitemap": True,
        "images_count": 5,
        "images_missing_alt": 0,
        "load_time_ms": 500
    }
    result = engine.calculate_scores(analysis_data, seo_data)
    
    assert result.website_quality_score == 0.0
    assert result.seo_score == 0.0
    assert result.automation_need_score == 0.0
    assert result.opportunity_score == 0.0
    assert len(result.detected_pain_points) == 0

def test_scoring_engine_partial_weaknesses():
    engine = ScoringEngine()
    analysis_data = {
        "business_name": "Partial Co",
        "website_exists": True,
        "ssl_enabled": False,  # 30 penalty
        "mobile_friendly": True,
        "meta_title_exists": False, # 20 penalty
        "meta_description_exists": True,
        "h1_exists": True,
        "contact_form_exists": False, # 30 penalty
        "whatsapp_integration": False, # 20 penalty
        "social_links_found": [] # 25 penalty
    }
    result = engine.calculate_scores(analysis_data)
    
    assert result.website_quality_score > 0
    assert result.seo_score > 0
    assert result.automation_need_score > 0
    assert len(result.detected_pain_points) > 0
