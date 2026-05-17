import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()
db_url = os.getenv("DATABASE_URL")

try:
    conn = psycopg2.connect(db_url)
    cur = conn.cursor()
    
    tables = ["businesses", "website_analyses", "scoring_results", "business_reports", "outreach_drafts"]
    print("Database Record Counts:")
    for t in tables:
        cur.execute(f"SELECT count(*) FROM {t}")
        count = cur.fetchone()[0]
        print(f"- {t}: {count}")
        
    print("\nSample Business Record:")
    cur.execute("SELECT business_name, category, website, google_rating, review_count, phone, address FROM businesses LIMIT 1")
    row = cur.fetchone()
    if row:
        print(f"Name: {row[0]}")
        print(f"Category: {row[1]}")
        print(f"Website: {row[2]}")
        print(f"Google Rating: {row[3]}")
        print(f"Review Count: {row[4]}")
        print(f"Phone: {row[5]}")
        print(f"Address: {row[6]}")
        
    print("\nMost Common Business Categories:")
    cur.execute("SELECT category, count(*) FROM businesses GROUP BY category ORDER BY count(*) DESC LIMIT 5")
    for row in cur.fetchall():
        print(f"- {row[0]}: {row[1]}")
        
    conn.close()
except Exception as e:
    print(f"Error checking DB details: {e}")
