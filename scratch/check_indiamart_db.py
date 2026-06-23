import psycopg2
import os
import json
from dotenv import load_dotenv

load_dotenv()
db_url = os.getenv("DATABASE_URL")

try:
    conn = psycopg2.connect(db_url)
    cur = conn.cursor()
    
    print("Querying database for IndiaMart business entries...")
    cur.execute("""
        SELECT id, business_name, category, phone, website, address, 
               im_rating, im_verified, im_gst_verified, source_platforms
        FROM businesses
        WHERE 'indiamart' = ANY(SELECT jsonb_array_elements_text(source_platforms))
        ORDER BY id DESC
        LIMIT 5;
    """)
    
    rows = cur.fetchall()
    if rows:
        print(f"\nFound {len(rows)} businesses with 'indiamart' in source_platforms:")
        for row in rows:
            print("-" * 50)
            print(f"ID: {row[0]}")
            print(f"Name: {row[1]}")
            print(f"Category: {row[2]}")
            print(f"Phone: {row[3]}")
            print(f"Website: {row[4]}")
            print(f"Address: {row[5]}")
            print(f"IM Rating: {row[6]}")
            print(f"IM Verified: {row[7]}")
            print(f"IM GST Verified: {row[8]}")
            print(f"Source Platforms: {row[9]}")
    else:
        print("No business found with 'indiamart' in source_platforms.")
        
    conn.close()
except Exception as e:
    print(f"Error checking IndiaMart DB rows: {e}")
