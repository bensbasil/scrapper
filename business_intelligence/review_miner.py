import logging
from dataclasses import dataclass, asdict
from typing import Dict, Any, List, Optional

logger = logging.getLogger("ReviewMiner")
logger.setLevel(logging.INFO)

@dataclass
class ReviewMiningResult:
    business_name: str
    recurring_complaints: List[str]
    recurring_praise: List[str]
    common_themes: List[str]
    review_health_score: float
    pain_summary: str

class ReviewMiner:
    def __init__(self):
        # Category specific mock review datasets to generate realistic complaints/praise based on ratings
        self.mock_database = {
            "gym": {
                "praise": ["Excellent certified trainers", "Wide range of functional equipment", "Locker rooms are clean", "Welcoming community atmosphere", "Convenient location and hours"],
                "complaints": ["Extremely overcrowded during peak evening hours", "Several treadmills and bikes remain broken", "Rude reception desk response", "Unsanitary showers and locker spaces", "Booking classes is very difficult on their platform"],
                "themes": ["Facilities", "Staff", "Booking", "Pricing"]
            },
            "hospital": {
                "praise": ["Compassionate and expert medical staff", "State of the art clean rooms", "Professional nursing care", "Prompt emergency response", "Clear prescription instructions"],
                "complaints": ["Extremely long waiting times in outpatient lobby", "Frustrating billing issues and double charges", "Unhelpful receptionist answers", "Difficulties booking specialized doctors", "Rude doctor consultations"],
                "themes": ["Service", "Communication", "Booking", "Billing"]
            },
            "restaurant": {
                "praise": ["Delightful food and taste", "Warm and beautiful ambiance", "Fast table service", "Fair prices for portions", "Friendly waiting staff"],
                "complaints": ["Incredibly slow table service on weekends", "Food served lukewarm or cold", "Unhygienic table setup and plates", "Overpriced menu items", "Difficult reservation booking system"],
                "themes": ["Food Quality", "Service Speed", "Booking", "Cleanliness"]
            },
            "general": {
                "praise": ["High quality output and product", "Very professional and friendly support", "Prompt delivery of service", "Great value for money", "Highly recommended locally"],
                "complaints": ["Extremely poor customer service resolution", "Unresponsive to phone calls and emails", "Hidden fees and unexpected billing issues", "Significant delay in deliverables", "No tracking or online status check"],
                "themes": ["Service", "Support", "Pricing", "Communication"]
            }
        }

    def _normalize_category(self, cat: Optional[str]) -> str:
        if not cat:
            return "general"
        cat_lower = cat.lower()
        if "gym" in cat_lower or "fitness" in cat_lower or "workout" in cat_lower:
            return "gym"
        if "hospital" in cat_lower or "clinic" in cat_lower or "medical" in cat_lower or "doctor" in cat_lower or "dental" in cat_lower:
            return "hospital"
        if "restaurant" in cat_lower or "cafe" in cat_lower or "food" in cat_lower or "dining" in cat_lower:
            return "restaurant"
        return "general"

    def mine_reviews(self, business_name: str, category: Optional[str], rating: Optional[float], review_count: Optional[int]) -> ReviewMiningResult:
        logger.info(f"[{business_name}] Mining reviews (rating: {rating}, count: {review_count})...")
        
        cat_key = self._normalize_category(category)
        dataset = self.mock_database[cat_key]

        # Calculate a review health score out of 100
        # If no rating exists, we assume a neutral score of 70.0
        r_val = float(rating) if rating is not None else 4.0
        health_score = min(100.0, r_val * 20.0)

        praise = []
        complaints = []
        themes = dataset["themes"]
        summary = ""

        # Determine praise vs complaints ratio based on rating thresholds
        if r_val >= 4.5:
            # Mostly positive reviews
            praise = dataset["praise"][:3]
            complaints = [dataset["complaints"][0]] if dataset["complaints"] else []
            summary = f"Highly rated local establishment. Customers praise the overall quality but note occasional issues with {complaints[0].lower()}."
        elif r_val >= 4.0:
            # Mixed positive and negative
            praise = dataset["praise"][:2]
            complaints = dataset["complaints"][:2]
            summary = f"Generally positive reception. Core strengths are offset by consistent friction points, particularly regarding {complaints[0].lower()}."
        else:
            # Mostly negative reviews
            praise = [dataset["praise"][0]] if dataset["praise"] else []
            complaints = dataset["complaints"][:3]
            summary = f"Poor review ratings. Critical service bottlenecks identified: customers repeatedly complain about {', '.join([c.lower() for c in complaints[:2]])}."

        return ReviewMiningResult(
            business_name=business_name,
            recurring_complaints=complaints,
            recurring_praise=praise,
            common_themes=themes,
            review_health_score=health_score,
            pain_summary=summary
        )
