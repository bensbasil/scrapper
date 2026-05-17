import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()
db_url = os.getenv("DATABASE_URL")

try:
    conn = psycopg2.connect(db_url)
    cur = conn.cursor()
    cur.execute("SELECT count(*) FROM businesses")
    count = cur.fetchone()[0]
    print(f"Total businesses in DB: {count}")
    conn.close()
except Exception as e:
    print(f"Error checking data: {e}")
