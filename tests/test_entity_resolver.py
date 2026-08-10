import pytest
from enrichment.entity_resolver import EntityResolver, EntityMatchResult

def test_entity_resolver_exact_match():
    resolver = EntityResolver()
    a = {"business_name": "Apex Gyms", "phone": "+91 98765 43210", "website": "https://apex.com"}
    b = {"business_name": "Apex Gyms", "phone": "9876543210", "website": "http://www.apex.com"}
    
    result = resolver.compare(a, b)
    assert isinstance(result, EntityMatchResult)
    assert result.is_match is True
    assert result.confidence >= 0.75
    assert result.suggested_action == "merge"
    assert "exact_name_match" in result.match_reasons
    assert "phone_match" in result.match_reasons
    assert "domain_match" in result.match_reasons

def test_entity_resolver_fuzzy_name_and_phone():
    resolver = EntityResolver()
    a = {"business_name": "Apex Fitness Center", "phone": "9876543210"}
    b = {"business_name": "Apex Fitness Centre", "phone": "9876543210"}
    
    result = resolver.compare(a, b)
    assert result.confidence >= 0.7
    assert result.suggested_action in ("review", "merge")
    assert "phone_match" in result.match_reasons

def test_entity_resolver_different_entities():
    resolver = EntityResolver()
    a = {"business_name": "Alpha Bakery", "phone": "1111111111", "website": "https://alphabakery.com"}
    b = {"business_name": "Beta Motors", "phone": "9999999999", "website": "https://betamotors.com"}
    
    result = resolver.compare(a, b)
    assert result.is_match is False
    assert result.confidence < 0.4
    assert result.suggested_action == "ignore"
