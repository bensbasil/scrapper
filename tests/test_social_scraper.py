import pytest
from scraper.connectors.social.social_scraper import SocialScraper, SocialScraperResult

def test_social_scraper_platform_detection():
    scraper = SocialScraper()
    assert scraper._detect_platform("https://www.instagram.com/nike") == "instagram"
    assert scraper._detect_platform("https://facebook.com/nike") == "facebook"
    assert scraper._detect_platform("https://fb.com/nike") == "facebook"
    assert scraper._detect_platform("https://twitter.com/nike") is None

def test_social_scraper_unsupported_url():
    scraper = SocialScraper()
    res = scraper.scrape("https://unknown-platform.com/profile")
    assert isinstance(res, SocialScraperResult)
    assert res.platform == "unknown"
    assert res.is_reachable is False

def test_social_scraper_context_manager():
    with SocialScraper() as scraper:
        assert scraper._browser is None
        # Browser lazily initializes if playwright fallback is called
        scraper.close()
        assert scraper._browser is None
