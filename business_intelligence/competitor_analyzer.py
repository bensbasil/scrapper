import logging
from dataclasses import dataclass, asdict
from typing import List, Dict, Any, Optional

logger = logging.getLogger("CompetitorAnalyzer")
logger.setLevel(logging.INFO)

@dataclass
class CompetitorComparison:
    name: str
    website: Optional[str]
    rating: Optional[float]
    opportunity_score: float
    score_gap: float # target_score - competitor_score (higher gap = we have much poorer digital presence than them)

@dataclass
class CompetitorAnalysisResult:
    business_name: str
    competitors: List[Dict[str, Any]]
    competitor_gap_summary: str

class CompetitorAnalyzer:
    def __init__(self, repo: Any):
        self.repo = repo

    def _extract_city(self, address: Optional[str]) -> str:
        if not address:
            return ""
        # Broad heuristics to find common cities in South India/general locales
        addr_lower = address.lower()
        for city in ["trivandrum", "kochi", "calicut", "bangalore", "mumbai", "delhi", "chennai"]:
            if city in addr_lower:
                return city.capitalize()
        # Fallback split
        parts = address.split(",")
        if len(parts) >= 2:
            return parts[-2].strip()
        return ""

    def analyze(self, business_id: int, business_name: str, category: Optional[str], address: Optional[str], opportunity_score: float) -> CompetitorAnalysisResult:
        logger.info(f"[{business_name}] Analyzing competitor gaps in local area...")
        
        city = self._extract_city(address)
        if not city or not category:
            return CompetitorAnalysisResult(
                business_name=business_name,
                competitors=[],
                competitor_gap_summary="Could not run local competitor search: category or city location details are missing."
            )

        # Query database for other businesses in same category and city
        raw_competitors = self.repo.get_local_competitors(city, category, business_id)
        
        comparisons: List[CompetitorComparison] = []
        for rc in raw_competitors:
            comp_opp_score = float(rc.get("opportunity_score", 0.0))
            score_gap = opportunity_score - comp_opp_score
            
            comparisons.append(CompetitorComparison(
                name=rc.get("business_name", "Unknown"),
                website=rc.get("website"),
                rating=float(rc.get("google_rating")) if rc.get("google_rating") is not None else None,
                opportunity_score=comp_opp_score,
                score_gap=round(score_gap, 1)
            ))

        # Convert to dictionary array
        competitors_list = [asdict(c) for c in comparisons]

        # Generate summary narrative
        if not comparisons:
            summary = f"No other local competitors in {city} are currently indexed in our database for the {category} category."
        else:
            # Sort by score gap descending (strongest gap = competitors with much better digital profiles)
            sorted_comps = sorted(comparisons, key=lambda x: x.score_gap, reverse=True)
            top_competitor = sorted_comps[0]
            
            if top_competitor.score_gap > 30:
                summary = f"Severe digital gap detected. Local competitor '{top_competitor.name}' has a highly optimized website (Opp score: {top_competitor.opportunity_score}/100) and is capturing local search rankings. Upgrading your web assets is urgent to stop losing traffic to them."
            elif top_competitor.score_gap > 10:
                summary = f"Digital disadvantage. Competitors like '{top_competitor.name}' maintain better online booking and web experiences (Opp score: {top_competitor.opportunity_score}/100)."
            else:
                summary = f"Competitive local market. Digital profiles are neck-and-neck. Small optimizations in SEO and booking conversions could help outrank '{top_competitor.name}'."

        return CompetitorAnalysisResult(
            business_name=business_name,
            competitors=competitors_list,
            competitor_gap_summary=summary
        )
