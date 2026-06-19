import psycopg2
import os
import json
from dotenv import load_dotenv

load_dotenv()
db_url = os.getenv("DATABASE_URL")

try:
    conn = psycopg2.connect(db_url)
    cur = conn.cursor()
    
    print("=== CHECKING INTENT PROFILES ===")
    cur.execute("""
        SELECT ip.id, ip.business_id, b.business_name, ip.intent_score, ip.hiring_signal_score,
               ip.review_trend_score, ip.freshness_score, ip.opportunity_score,
               ip.top_intent_signals, ip.outreach_urgency, ip.evaluated_at
        FROM intent_profiles ip
        JOIN businesses b ON ip.business_id = b.id
        ORDER BY ip.id DESC
        LIMIT 3
    """)
    rows = cur.fetchall()
    if rows:
        for r in rows:
            print(f"ID: {r[0]} | Biz ID: {r[1]} | Name: {r[2]}")
            print(f"  Intent Score: {r[3]}/100 | Urgency: {r[9]}")
            print(f"  Scores: Hiring={r[4]}, Review={r[5]}, Freshness={r[6]}, Opp={r[7]}")
            print(f"  Signals: {r[8]}")
            print(f"  Evaluated At: {r[10]}")
            print("-" * 40)
    else:
        print("No intent profiles found.")
        
    print("\n=== CHECKING SOCIAL PROFILES ===")
    cur.execute("""
        SELECT sp.id, sp.business_id, b.business_name, sp.profiles,
               sp.social_activity_score, sp.total_platforms_found, sp.total_platforms_active, sp.analyzed_at
        FROM social_profiles sp
        JOIN businesses b ON sp.business_id = b.id
        ORDER BY sp.id DESC
        LIMIT 3
    """)
    rows = cur.fetchall()
    if rows:
        for r in rows:
            print(f"ID: {r[0]} | Biz ID: {r[1]} | Name: {r[2]}")
            print(f"  Social Activity Score: {r[4]}/100")
            print(f"  Platforms Found: {r[5]} | Active: {r[6]}")
            print(f"  Profiles: {r[3]}")
            print(f"  Analyzed At: {r[7]}")
            print("-" * 40)
    else:
        print("No social profiles found.")
        
    conn.close()
except Exception as e:
    print(f"Error checking Phase 2 DB tables: {e}")
