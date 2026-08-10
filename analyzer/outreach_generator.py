import json
import logging
import os
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import List, Dict, Any, Optional
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


# ---------------------------------------------------------
# ---------------------------------------------------------
# 1. Structured Logging
# ---------------------------------------------------------
from scraper.utils.logger import get_scraper_logger

logger = get_scraper_logger(__name__)

# ---------------------------------------------------------
# 2. Data Structure
# ---------------------------------------------------------
@dataclass
class OutreachDrafts:
    business_name: str
    outreach_angles: List[str]
    pain_point_positioning: str
    concise_audit_summary: str
    cold_email_draft: str
    whatsapp_draft: str
    ai_prompt_template: str

# ---------------------------------------------------------
# 3. Outreach Engine
# ---------------------------------------------------------
class OutreachGenerator:
    """
    Generates non-spammy, highly contextual outreach drafts.
    Uses Google's Gemini API or OpenAI API when available, falling back to rule-based templates otherwise.
    """
    
    def _generate_via_gemini(self, prompt: str, api_key: str) -> Optional[Dict[str, str]]:
        """Calls Gemini API using structured JSON output to generate outreach drafts."""
        model = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        headers = {
            "Content-Type": "application/json"
        }
        
        # Request JSON structured output
        payload = {
            "contents": [
                {
                    "parts": [
                        {
                            "text": prompt + "\n\nProvide the response strictly in JSON format as specified."
                        }
                    ]
                }
            ],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseSchema": {
                    "type": "OBJECT",
                    "properties": {
                        "cold_email_draft": {
                            "type": "STRING",
                            "description": "Personalized cold email under 120 words."
                        },
                        "whatsapp_draft": {
                            "type": "STRING",
                            "description": "Short WhatsApp message under 50 words."
                        }
                    },
                    "required": ["cold_email_draft", "whatsapp_draft"]
                }
            }
        }
        
        try:
            logger.info(f"Sending request to Gemini API (model: {model})...")
            response = requests.post(url, headers=headers, json=payload, timeout=12)
            if response.status_code == 200:
                res_data = response.json()
                text_content = res_data["candidates"][0]["content"]["parts"][0]["text"]
                parsed = json.loads(text_content)
                if "cold_email_draft" in parsed and "whatsapp_draft" in parsed:
                    return parsed
                else:
                    logger.warning("Gemini JSON response is missing required fields.")
            else:
                logger.warning(f"Gemini API returned status code {response.status_code}: {response.text}")
        except Exception as e:
            logger.error(f"Failed to generate outreach via Gemini API: {e}")
        
        return None

    def _generate_via_openai(self, prompt: str, api_key: str) -> Optional[Dict[str, str]]:
        """Calls OpenAI Chat Completion API to generate structured JSON outreach drafts."""
        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        payload = {
            "model": model,
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "system",
                    "content": "You are a sales copywriter. Output JSON containing keys 'cold_email_draft' and 'whatsapp_draft'."
                },
                {"role": "user", "content": prompt}
            ]
        }
        try:
            logger.info(f"Sending request to OpenAI API (model: {model})...")
            response = requests.post(url, headers=headers, json=payload, timeout=12)
            if response.status_code == 200:
                res_data = response.json()
                text_content = res_data["choices"][0]["message"]["content"]
                parsed = json.loads(text_content)
                if "cold_email_draft" in parsed and "whatsapp_draft" in parsed:
                    return parsed
            else:
                logger.warning(f"OpenAI API returned status code {response.status_code}: {response.text}")
        except Exception as e:
            logger.error(f"Failed to generate outreach via OpenAI API: {e}")
        return None

    def _generate_pain_point_positioning(self, pain_points: List[str], services: List[str]) -> str:
        """Determines how to position your agency based on their biggest weakness."""
        if not pain_points:
            return "Position as a general technology partner for growth."
            
        primary_pain = pain_points[0]
        
        if "No website" in primary_pain:
            return "Position as a digital storefront builder. Focus on missed local searches and instant trust."
        if "SSL" in primary_pain:
            return "Position as a security and trust consultant. Focus on browser warnings driving away traffic."
        if "mobile" in primary_pain.lower():
            return "Position as a mobile-first designer. Focus on the frustrating experience mobile users are currently having."
        if "automation" in services or "WhatsApp" in primary_pain or "contact" in primary_pain:
            return "Position as an efficiency expert. Focus on stopping the leak of after-hours or uncaptured leads."
            
        return "Position as a technical optimization partner. Focus on improving their current digital foundations."

    def _generate_audit_summary(self, pain_points: List[str], score: float) -> str:
        """Creates a punchy 1-2 sentence summary of the audit."""
        if score < 40:
            return "Solid baseline. Minor optimization opportunities identified."
        if score < 70:
            summary = "Found a few technical bottlenecks costing them traffic: "
            return summary + ", ".join(pain_points[:2]) + "."
        
        summary = "Critical digital weaknesses detected: "
        return summary + ", ".join(pain_points[:3]) + "."

    def _generate_cold_email(self, business_name: str, category: str, primary_paint: str, service: str, contact_name: str = None, opp_reasoning: str = None) -> str:
        """Generates a human-sounding, low-friction cold email draft."""
        cat_text = category if category else "local businesses"
        salutation = f"Hi {contact_name}," if contact_name else "Hi team,"
        
        reasoning_text = f"\n\n{opp_reasoning}" if opp_reasoning else ""

        if "website" in primary_paint.lower() or "No website" in primary_paint:
            return f"""Subject: Question about {business_name}'s digital presence

{salutation}

I was looking for {cat_text} in the area and noticed {business_name} doesn't seem to have a dedicated website yet.{reasoning_text}

A lot of local searches are happening right now, and without a simple landing page, you might be losing those customers to competitors. I build clean, fast, 1-page websites specifically for {cat_text} to fix exactly this.

If you're open to it, I can send over a quick mockup of what it could look like. No pressure either way.

Best,
[Your Name]"""

        return f"""Subject: Quick thought regarding {business_name}'s website

{salutation}

I was browsing {business_name}'s site today while looking at {cat_text} in the area. I noticed a technical issue: {primary_paint.lower()}.{reasoning_text}

Usually, when this happens, it can directly impact how easily new customers can find or contact you. We specialize in fixing these exact types of bottlenecks through {service.lower() if service else 'targeted optimization'}.

Would you be opposed to me sending over a brief 2-minute video showing exactly how to fix it?

Best,
[Your Name]"""

    def _generate_whatsapp(self, business_name: str, primary_pain: str, contact_name: str = None) -> str:
        """Generates an ultra-short WhatsApp or LinkedIn DM draft."""
        salutation = f"Hi {contact_name}!" if contact_name else f"Hi {business_name} team!"
        if "website" in primary_pain.lower() or "No website" in primary_pain:
            return f"{salutation} I'm a local developer. I noticed you don't have a website set up yet. Would you be open to me sending over a quick, free mockup of what a simple landing page could look like for you?"
            
        return f"{salutation} I was just looking at your website and noticed an issue with {primary_pain.lower()}. It might be costing you some traffic. Mind if I send a quick screenshot of how to fix it?"

    def _generate_ai_prompt(self, b_name: str, score: float, pain_points: List[str], services: List[str], contact_name: str = None, opp_reasoning: str = None) -> str:
        """Generates the structured prompt that can be sent to OpenAI/Anthropic later."""
        contact_line = f"- Contact Decision-Maker: {contact_name}" if contact_name else "- Contact Decision-Maker: Not found (use generic salutation)"
        reasoning_line = f"- Opportunity Reasoning: {opp_reasoning}" if opp_reasoning else ""
        return f"""You are an expert, consultative B2B sales copywriter. 
Write a highly personalized, non-spammy cold email to '{b_name}'.

Context:
- Overall Opportunity Score: {score}/100 (Higher means they need more help)
- Key Pain Points Detected: {', '.join(pain_points)}
- Suggested Services to Pitch: {', '.join(services)}
{contact_line}
{reasoning_line}

Rules:
1. Do not use fake statistics or hyperbolic claims.
2. Focus strictly on how the pain points hurt their customer experience.
3. Keep it under 100 words.
4. End with a low-friction call to action (e.g., offering a free 2-minute audit video)."""

    def generate_outreach(self, score_data: Dict[str, Any], analysis_data: Dict[str, Any] = {}) -> OutreachDrafts:
        """
        Main orchestration function to generate all outreach materials.
        Takes data from scoring_engine and (optionally) basic scraper/analysis data.
        If GEMINI_API_KEY is present in env, generates using Gemini; otherwise, falls back to static templates.
        """
        b_name = score_data.get("business_name", "your business")
        category = analysis_data.get("category", "")
        opp_score = score_data.get("opportunity_score", 0.0)
        pain_points = score_data.get("detected_pain_points", [])
        services = score_data.get("likely_service_match", [])
        
        primary_pain = pain_points[0] if pain_points else "technical optimization opportunities"
        primary_service = services[0] if services else "digital consulting"

        # Extract decision maker name from score_data or analysis_data
        contact_name = analysis_data.get("decision_maker_name") or score_data.get("decision_maker_name")
        opp_reasoning = analysis_data.get("opportunity_reasoning")

        # 1. Strategy & Positioning
        positioning = self._generate_pain_point_positioning(pain_points, services)
        audit_summary = self._generate_audit_summary(pain_points, opp_score)
        
        angles = []
        if "website" in primary_pain.lower():
            angles.append("The 'Invisible Business' angle: Focus on lost local search traffic.")
        elif "automation" in services:
            angles.append("The 'Leaky Bucket' angle: Focus on lost leads due to friction in contacting them.")
        else:
            angles.append("The 'Trust & Security' angle: Focus on technical errors making the business look unprofessional.")

        # 2. AI Readiness (Always generate the template for database record)
        ai_prompt = self._generate_ai_prompt(b_name, opp_score, pain_points, services, contact_name, opp_reasoning)

        # 3. Actionable Drafts (Gemini with Rule-based fallback)
        email_draft = None
        wa_draft = None
        
        api_key = os.environ.get("GEMINI_API_KEY")
        if api_key:
            logger.info(f"[{b_name}] GEMINI_API_KEY found. Generating personalized outreach via AI...")
            prompt = f"""You are an expert, consultative B2B sales copywriter.
Write a highly personalized, professional, non-spammy cold email and a WhatsApp message for '{b_name}'.

Context:
- Business Name: {b_name}
- Industry/Category: {category if category else 'Local Business'}
- Overall Opportunity Score: {opp_score}/100 (A higher score indicates significant technical/digital gaps)
- Key Pain Points Detected: {', '.join(pain_points)}
- Suggested Services to Pitch: {', '.join(services)}
- Contact Decision-Maker: {contact_name if contact_name else 'Not found (use a warm generic greeting like "Hi Team" or "Hi there")'}
- Opportunity Analysis / Reasoning: {opp_reasoning if opp_reasoning else 'No detailed reasoning provided.'}

Requirements for Cold Email:
1. Warm, human, and direct tone. Do not use fake statistics, generic fluff, or hyperbolic marketing claims.
2. Specifically address how their detected pain points (e.g. {', '.join(pain_points)}) impact their business, website conversion, customer trust, or ranking.
3. Keep it extremely concise and under 120 words.
4. End with a low-friction call-to-action (e.g., offering a free 2-minute mockup or screencast showing how to fix the issue).
5. Ensure a clear placeholder for your name at the end (e.g., "[Your Name]").

Requirements for WhatsApp Message:
1. Keep it extremely short (under 50 words).
2. Direct, friendly, and informal but professional.
3. Briefly mention the most critical issue and ask if you can send a mockup or quick explanation.
4. Must not sound like a broadcast or bulk spam message.
"""
            gemini_drafts = self._generate_via_gemini(prompt, api_key)
            if gemini_drafts:
                email_draft = gemini_drafts.get("cold_email_draft")
                wa_draft = gemini_drafts.get("whatsapp_draft")
                logger.info(f"[{b_name}] Successfully generated AI personalized outreach drafts via Gemini.")

        openai_key = os.environ.get("OPENAI_API_KEY")
        if not email_draft and openai_key:
            logger.info(f"[{b_name}] OPENAI_API_KEY found. Generating personalized outreach via OpenAI...")
            prompt = f"""You are an expert, consultative B2B sales copywriter.
Write a highly personalized, professional, non-spammy cold email and a WhatsApp message for '{b_name}'.

Context:
- Business Name: {b_name}
- Industry/Category: {category if category else 'Local Business'}
- Overall Opportunity Score: {opp_score}/100
- Key Pain Points Detected: {', '.join(pain_points)}
- Suggested Services to Pitch: {', '.join(services)}
- Contact Decision-Maker: {contact_name if contact_name else 'Not found'}
- Opportunity Analysis / Reasoning: {opp_reasoning if opp_reasoning else 'No detailed reasoning provided.'}

Return JSON with keys 'cold_email_draft' and 'whatsapp_draft'.
"""
            openai_drafts = self._generate_via_openai(prompt, openai_key)
            if openai_drafts:
                email_draft = openai_drafts.get("cold_email_draft")
                wa_draft = openai_drafts.get("whatsapp_draft")
                logger.info(f"[{b_name}] Successfully generated AI personalized outreach drafts via OpenAI.")
        
        # If API keys are missing or generation fails, use the rule-based fallback
        if not email_draft or not wa_draft:
            if api_key or openai_key:
                logger.warning(f"[{b_name}] AI generation failed. Falling back to rule-based templates.")
            else:
                logger.info(f"[{b_name}] No AI API key found. Using rule-based templates.")
            email_draft = self._generate_cold_email(b_name, category, primary_pain, primary_service, contact_name, opp_reasoning)
            wa_draft = self._generate_whatsapp(b_name, primary_pain, contact_name)

        return OutreachDrafts(
            business_name=b_name,
            outreach_angles=angles,
            pain_point_positioning=positioning,
            concise_audit_summary=audit_summary,
            cold_email_draft=email_draft,
            whatsapp_draft=wa_draft,
            ai_prompt_template=ai_prompt
        )

if __name__ == "__main__":
    # MVP Test Execution
    test_analysis = {
        "business_name": "Old Plumbing Co",
        "category": "plumbers"
    }
    
    test_score = {
        "business_name": "Old Plumbing Co",
        "opportunity_score": 75.0,
        "likely_service_match": ["web development", "SEO", "automation"],
        "detected_pain_points": [
            "SSL missing (Not secure)",
            "Likely not mobile friendly",
            "No contact form on site"
        ]
    }

    generator = OutreachGenerator()
    drafts = generator.generate_outreach(test_score, test_analysis)
    
    print("--- Concise Audit Summary ---")
    print(drafts.concise_audit_summary)
    print("\n--- Cold Email Draft ---")
    print(drafts.cold_email_draft)
    print("\n--- AI Prompt for Future Integration ---")
    print(drafts.ai_prompt_template)
