import json
import logging
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import List, Dict, Any, Optional

# ---------------------------------------------------------
# 1. Structured Logging
# ---------------------------------------------------------
from scraper.utils.logger import get_scraper_logger

logger = get_scraper_logger(__name__)

# ---------------------------------------------------------
# 2. Data Structure (Prepares for PostgreSQL)
# ---------------------------------------------------------
@dataclass
class ScoringResult:
    """Matches DATA_DICTIONARY.md for Opportunity Intelligence."""
    business_name: str
    website_url: Optional[str]
    opportunity_score: float
    website_quality_score: float
    seo_score: float
    automation_need_score: float
    likely_service_match: List[str]
    detected_pain_points: List[str]

# ---------------------------------------------------------
# 3. Main Scoring Engine
# ---------------------------------------------------------
class ScoringEngine:
    """
    Heuristic rule-based scoring engine.
    Designed with a decoupled 'weights' matrix. This makes the logic
    trivial to modify and prepares the system for a future where these
    weights could be dynamically supplied by a Machine Learning model.
    """
    def __init__(self):
        # Configurable weights mapping weakness -> penalty points.
        # Higher score = poorer digital presence = greater opportunity for us to pitch.
        self.weights = {
            "no_website": 100.0,
            "no_ssl": 30.0,
            "not_mobile_friendly": 40.0,
            "no_social_links": 25.0,
            "missing_meta_title": 20.0,
            "missing_meta_desc": 20.0,
            "missing_h1": 20.0,
            "no_contact_form": 30.0,
            "no_whatsapp": 20.0
        }

    def _calculate_seo_score(self, data: Dict[str, Any], pain_points: List[str], seo_data: Optional[Dict[str, Any]] = None) -> float:
        """Calculate SEO weakness. 100 = terrible SEO, 0 = perfect SEO."""
        if not data.get("website_exists", False):
            return 100.0
            
        score = 0.0
        
        # 1. Base SEO checks (from static crawler)
        if not data.get("meta_title_exists", False):
            score += self.weights["missing_meta_title"]
            pain_points.append("Missing meta title")
        elif seo_data and not seo_data.get("title_optimized", False):
            score += 10.0
            pain_points.append("Meta title is not optimized (length out of range)")
            
        if not data.get("meta_description_exists", False):
            score += self.weights["missing_meta_desc"]
            pain_points.append("Missing meta description")
        elif seo_data and not seo_data.get("meta_description_optimized", False):
            score += 10.0
            pain_points.append("Meta description is not optimized (length out of range)")
            
        if not data.get("h1_exists", False):
            score += self.weights["missing_h1"]
            pain_points.append("Missing H1 tag")
        elif seo_data and seo_data.get("h1_count", 0) > 1:
            score += 10.0
            pain_points.append("Multiple H1 tags detected (bad for SEO)")

        # 2. Advanced SEO checks (from SEOChecker)
        if seo_data:
            if not seo_data.get("has_viewport_tag", False):
                score += 15.0
                pain_points.append("Missing mobile viewport configuration tag")
            
            if not seo_data.get("has_robots_txt", False):
                score += 10.0
                pain_points.append("Missing robots.txt file")
            if not seo_data.get("has_sitemap", False):
                score += 15.0
                pain_points.append("Missing sitemap.xml file")
                
            img_count = seo_data.get("images_count", 0)
            missing_alt = seo_data.get("images_missing_alt", 0)
            if img_count > 0 and (missing_alt / img_count) > 0.5:
                score += 10.0
                pain_points.append("More than 50% of website images are missing alt attributes")
                
            load_time = seo_data.get("load_time_ms")
            if load_time and load_time > 3000:
                score += 15.0
                pain_points.append("Slow page response latency (> 3 seconds)")

        return min(100.0, score)

    def _calculate_website_quality_score(self, data: Dict[str, Any], pain_points: List[str]) -> float:
        """Calculate Website weakness. 100 = terrible website, 0 = perfect website."""
        if not data.get("website_exists", False):
            pain_points.append("No website detected")
            return 100.0
            
        score = 0.0
        if not data.get("ssl_enabled", False):
            score += self.weights["no_ssl"]
            pain_points.append("SSL missing (Not secure)")
            
        if not data.get("mobile_friendly", False):
            score += self.weights["not_mobile_friendly"]
            pain_points.append("Likely not mobile friendly")
            
        # Check if the social links array is empty
        if not data.get("social_links_found"):
            score += self.weights["no_social_links"]
            pain_points.append("No social media links detected")
            
        return min(100.0, score)

    def _calculate_automation_need_score(self, data: Dict[str, Any], pain_points: List[str]) -> float:
        """Calculate Automation need. 100 = high need for automation."""
        if not data.get("website_exists", False):
            # If they don't have a website, they have a moderate need for automation, 
            # but their primary need is web development first.
            return 50.0 
            
        score = 0.0
        if not data.get("contact_form_exists", False):
            score += self.weights["no_contact_form"]
            pain_points.append("No contact form on site")
            
        if not data.get("whatsapp_integration", False):
            score += self.weights["no_whatsapp"]
            pain_points.append("No WhatsApp quick-contact integration")
            
        return min(100.0, score)

    def calculate_scores(self, analysis_data: Dict[str, Any], seo_data: Optional[Dict[str, Any]] = None) -> ScoringResult:
        """
        Process raw analysis data dictionary into a structured ScoringResult.
        """
        pain_points: List[str] = []
        
        # 1. Calculate component scores
        seo_score = self._calculate_seo_score(analysis_data, pain_points, seo_data)
        web_score = self._calculate_website_quality_score(analysis_data, pain_points)
        auto_score = self._calculate_automation_need_score(analysis_data, pain_points)
        
        # 2. Overall Opportunity Score (weighted average of component scores)
        # Logic: A bad website is the easiest sell (50%), SEO is next (30%), Automation is an upsell (20%).
        opportunity_score = (web_score * 0.5) + (seo_score * 0.3) + (auto_score * 0.2)
        
        # 3. Determine Likely Service Match heuristics
        services = []
        if web_score > 60:
            services.append("web development")
        if seo_score > 50:
            services.append("SEO")
        if auto_score > 40:
            services.append("automation")
            
        # Fallback if no specific high scores trigger but opportunity exists
        if not services and opportunity_score > 30:
            services.append("dashboard")
            
        # Deduplicate pain points while preserving order
        pain_points = list(dict.fromkeys(pain_points))
        
        return ScoringResult(
            business_name=analysis_data.get("business_name", "Unknown"),
            website_url=analysis_data.get("website_url"),
            opportunity_score=round(opportunity_score, 1),
            website_quality_score=round(web_score, 1),
            seo_score=round(seo_score, 1),
            automation_need_score=round(auto_score, 1),
            likely_service_match=services,
            detected_pain_points=pain_points
        )

    def process_file(self, input_json_path: str, output_dir: str = "data/processed") -> List[ScoringResult]:
        """
        Process a JSON array of analysis results (from website_analyzer) into final scores.
        Can be easily extended to read CSV rows if required.
        """
        logger.info(f"Starting scoring for {input_json_path}")
        results = []
        
        try:
            with open(input_json_path, 'r', encoding='utf-8') as f:
                data_list = json.load(f)
                
            for item in data_list:
                score = self.calculate_scores(item)
                results.append(score)
                logger.info(f"Scored {score.business_name} - Opportunity: {score.opportunity_score}/100")
                
        except Exception as e:
            logger.error(f"Error processing scoring file: {e}")
            return results
            
        # Export processed data
        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)
        # Create output filename based on input filename
        out_file = out_path / f"scores_{Path(input_json_path).stem}.json"
        
        try:
            with open(out_file, 'w', encoding='utf-8') as f:
                json.dump([asdict(r) for r in results], f, indent=4, ensure_ascii=False)
            logger.info(f"Saved {len(results)} scored records to {out_file}")
        except Exception as e:
            logger.error(f"Failed to save scored output: {e}")
            
        return results

if __name__ == "__main__":
    # Internal MVP Test logic
    test_analysis = {
        "business_name": "Old Plumbing Co",
        "website_url": "http://oldplumbing.com",
        "website_exists": True,
        "ssl_enabled": False, # Penalty
        "mobile_friendly": False, # Penalty
        "meta_title_exists": True,
        "meta_description_exists": False, # Penalty
        "contact_form_exists": False, # Penalty
        "whatsapp_integration": False, # Penalty
        "social_links_found": [], # Penalty
        "h1_exists": False # Penalty
    }
    
    engine = ScoringEngine()
    result = engine.calculate_scores(test_analysis)
    print("Test Execution Result:")
    print(json.dumps(asdict(result), indent=2))
