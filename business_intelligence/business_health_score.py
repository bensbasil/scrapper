import logging
from dataclasses import dataclass, asdict
from typing import Dict, Any, List

logger = logging.getLogger("BusinessHealthScore")
logger.setLevel(logging.INFO)

@dataclass
class HealthProfileResult:
    business_name: str
    overall_health_score: float # 0 to 100 (high = healthy, low = bad/needs help)
    website_health_score: float # 100 - quality_score (since scoring_engine calculates quality_score as weakness/penalty)
    review_health_score: float
    trust_health_score: float
    conversion_health_score: float
    conversion_friction_score: float

class BusinessHealthScore:
    def __init__(self):
        pass

    def calculate_health(self, 
                         business_name: str, 
                         website_quality_score: float, # quality_score is weakness penalty (100 = poor, 0 = perfect)
                         seo_score: float,            # seo_score is weakness penalty (100 = poor, 0 = perfect)
                         review_health_score: float,  # review health (100 = high, 0 = low)
                         trust_health_score: float,   # trust health (100 = high, 0 = low)
                         conversion_health_score: float, # conversion health (100 = high, 0 = low)
                         conversion_friction_score: float) -> HealthProfileResult:
        logger.info(f"[{business_name}] Compiling composite business health scores...")

        # Invert website quality and SEO weakness scores to get health scores
        web_health = max(0.0, 100.0 - website_quality_score)
        seo_health = max(0.0, 100.0 - seo_score)

        # Composite Health score weights:
        # Website health: 30%, Conversion health: 30%, Reviews: 20%, SEO: 10%, Trust signals: 10%
        overall_health = (
            (web_health * 0.3) + 
            (conversion_health_score * 0.3) + 
            (review_health_score * 0.2) + 
            (seo_health * 0.1) + 
            (trust_health_score * 0.1)
        )

        return HealthProfileResult(
            business_name=business_name,
            overall_health_score=round(overall_health, 1),
            website_health_score=round(web_health, 1),
            review_health_score=round(review_health_score, 1),
            trust_health_score=round(trust_health_score, 1),
            conversion_health_score=round(conversion_health_score, 1),
            conversion_friction_score=round(conversion_friction_score, 1)
        )
