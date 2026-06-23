import logging
from dataclasses import dataclass, asdict
from typing import List, Dict, Any

logger = logging.getLogger("CustomerPainExtractor")
logger.setLevel(logging.INFO)

@dataclass
class PainExtractionResult:
    business_name: str
    bottlenecks: List[str]
    communication_issues: List[str]
    booking_complaints: List[str]
    trust_complaints: List[str]
    pain_score: float # 0 to 100 (high is worse/more pain)

class CustomerPainExtractor:
    def __init__(self):
        pass

    def extract_pains(self, business_name: str, complaints: List[str]) -> PainExtractionResult:
        logger.info(f"[{business_name}] Classifying and extracting customer pain signals...")
        
        bottlenecks = []
        communication_issues = []
        booking_complaints = []
        trust_complaints = []

        for complaint in complaints:
            c_lower = complaint.lower()
            
            # Heuristic classifications based on keywords
            if any(kw in c_lower for kw in ["crowd", "wait", "delay", "broken", "dirty", "unhygienic", "shower", "equipment", "slow", "treadmill"]):
                bottlenecks.append(complaint)
            
            if any(kw in c_lower for kw in ["rude", "reception", "staff", "unhelpful", "answer", "doctor", "consultation", "support"]):
                communication_issues.append(complaint)
            
            if any(kw in c_lower for kw in ["book", "reservation", "schedule", "appointment", "class"]):
                booking_complaints.append(complaint)
                
            if any(kw in c_lower for kw in ["bill", "charge", "refund", "fee", "hidden", "price", "overpriced"]):
                trust_complaints.append(complaint)

        # Calculate a composite pain score based on count of specific issues
        # Every classified issue adds weight to the pain metric
        total_issues_count = len(bottlenecks) + len(communication_issues) + len(booking_complaints) + len(trust_complaints)
        pain_score = min(100.0, total_issues_count * 25.0)

        return PainExtractionResult(
            business_name=business_name,
            bottlenecks=bottlenecks,
            communication_issues=communication_issues,
            booking_complaints=booking_complaints,
            trust_complaints=trust_complaints,
            pain_score=pain_score
        )
