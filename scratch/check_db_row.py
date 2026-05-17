import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()
db_url = os.getenv("DATABASE_URL")

try:
    conn = psycopg2.connect(db_url)
    cur = conn.cursor()
    
    cur.execute("""
        SELECT b.id, b.business_name, b.category, b.website, b.google_rating, b.review_count, b.address,
               wa.ssl_enabled, wa.mobile_friendly, wa.contact_form_exists, wa.whatsapp_integration, wa.social_links_found,
               sr.opportunity_score, sr.website_quality_score, sr.seo_score, sr.automation_need_score, sr.likely_service_match, sr.detected_pain_points,
               od.cold_email_draft, od.whatsapp_draft
        FROM businesses b
        JOIN website_analyses wa ON b.id = wa.business_id
        JOIN scoring_results sr ON b.id = sr.business_id
        JOIN outreach_drafts od ON b.id = od.business_id
        WHERE sr.opportunity_score > 60
        LIMIT 1
    """)
    
    row = cur.fetchone()
    if row:
        print("=== ENRICHED BUSINESS DATA ENTITY SAMPLE ===")
        print(f"ID: {row[0]}")
        print(f"Name: {row[1]}")
        print(f"Category: {row[2]}")
        print(f"Website: {row[3]}")
        print(f"Google Rating: {row[4]}")
        print(f"Review Count: {row[5]}")
        print(f"Address: {row[6]}")
        print(f"SSL Enabled: {row[7]}")
        print(f"Mobile Friendly: {row[8]}")
        print(f"Contact Form Exists: {row[9]}")
        print(f"WhatsApp Integration: {row[10]}")
        print(f"Social Links Found: {row[11]}")
        print(f"Opportunity Score: {row[12]}/100")
        print(f"Website Quality Score: {row[13]}/100")
        print(f"SEO Score: {row[14]}/100")
        print(f"Automation Need Score: {row[15]}/100")
        print(f"Likely Service Matches: {row[16]}")
        print(f"Detected Pain Points: {row[17]}")
        print("--------------------------------------------")
        print(f"Cold Email Draft Preview:\n{row[18][:300]}...")
        print("--------------------------------------------")
        print(f"WhatsApp Draft Preview:\n{row[19][:300]}...")
    else:
        print("No business found matching criteria.")
        
    conn.close()
except Exception as e:
    print(f"Error checking DB row: {e}")
