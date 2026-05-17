import os
import json
import logging
from pathlib import Path
from contextlib import contextmanager
from typing import Dict, Any, List, Optional

from dotenv import load_dotenv

load_dotenv()

# Assumes psycopg2 or psycopg2-binary is installed
import psycopg2
from psycopg2.pool import SimpleConnectionPool
from psycopg2.extras import RealDictCursor

# ---------------------------------------------------------
# 1. Structured Logging
# ---------------------------------------------------------
class StructuredLogger:
    @staticmethod
    def get_logger(name: str):
        logger = logging.getLogger(name)
        if not logger.handlers:
            logger.setLevel(logging.INFO)
            formatter = logging.Formatter('%(asctime)s - %(levelname)s - [%(name)s] - %(message)s')
            ch = logging.StreamHandler()
            ch.setFormatter(formatter)
            logger.addHandler(ch)
            log_dir = Path("logs")
            log_dir.mkdir(exist_ok=True)
            fh = logging.FileHandler(log_dir / "database.log")
            fh.setFormatter(formatter)
            logger.addHandler(fh)
        return logger

logger = StructuredLogger.get_logger(__name__)

# ---------------------------------------------------------
# 2. Database Connection Manager
# ---------------------------------------------------------
class DatabaseManager:
    """
    Manages PostgreSQL connections via a simple connection pool.
    Adheres to MVP rules by avoiding heavy ORM frameworks like SQLAlchemy.
    Uses environment variables for secure connection string passing.
    """
    def __init__(self):
        # Default connection string, override in production via .env
        self.db_url = os.getenv("DATABASE_URL", "postgresql://postgres:password@localhost:5432/scraper_db")
        self.pool = None
        try:
            self.pool = SimpleConnectionPool(1, 10, dsn=self.db_url)
            logger.info("Database connection pool initialized.")
        except Exception as e:
            logger.error(f"Failed to initialize database connection pool. Ensure PostgreSQL is running. Error: {e}")

    @contextmanager
    def get_connection(self):
        """Context manager for safely acquiring and releasing database connections."""
        if not self.pool:
            raise Exception("Database pool is not initialized. Check connection credentials.")
            
        conn = self.pool.getconn()
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Database transaction failed: {e}")
            raise
        finally:
            self.pool.putconn(conn)

    def execute_schema(self, schema_path: str = "database/schema.sql"):
        """Run the schema.sql file to initialize or update tables."""
        try:
            with open(schema_path, 'r') as f:
                schema_sql = f.read()
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(schema_sql)
            logger.info("Database schema executed successfully.")
        except Exception as e:
            logger.error(f"Failed to execute schema: {e}")

# ---------------------------------------------------------
# 3. Data Access Repository
# ---------------------------------------------------------
class ScraperRepository:
    """
    Provides structured reusable helper functions to insert and query data.
    Decoupled from the scraping logic to allow future FastAPI integration.
    """
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager

    def insert_business(self, data: Dict[str, Any]) -> Optional[int]:
        """
        Inserts a business. Uses ON CONFLICT to avoid duplicates, 
        returning the ID regardless of whether it's new or updated.
        """
        query = """
            INSERT INTO businesses 
            (business_name, category, website, google_rating, review_count, phone, address)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (business_name, address) 
            DO UPDATE SET updated_at = CURRENT_TIMESTAMP
            RETURNING id;
        """
        try:
            with self.db.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, (
                        data.get('business_name'),
                        data.get('category'),
                        data.get('website'),
                        data.get('google_rating'),
                        data.get('review_count'),
                        data.get('phone'),
                        data.get('address')
                    ))
                    result = cur.fetchone()
                    return result[0] if result else None
        except Exception as e:
            logger.error(f"Error inserting business {data.get('business_name')}: {e}")
            return None

    def insert_website_analysis(self, business_id: int, data: Dict[str, Any]) -> bool:
        """Inserts the results of the website_analyzer.py module."""
        query = """
            INSERT INTO website_analyses 
            (business_id, website_exists, ssl_enabled, mobile_friendly, meta_title_exists, 
             meta_title, meta_description_exists, contact_form_exists, whatsapp_integration, 
             social_links_found, h1_exists, error_message)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
        """
        try:
            with self.db.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, (
                        business_id,
                        data.get('website_exists', False),
                        data.get('ssl_enabled', False),
                        data.get('mobile_friendly', False),
                        data.get('meta_title_exists', False),
                        data.get('meta_title'),
                        data.get('meta_description_exists', False),
                        data.get('contact_form_exists', False),
                        data.get('whatsapp_integration', False),
                        json.dumps(data.get('social_links_found', [])),
                        data.get('h1_exists', False),
                        data.get('error')
                    ))
            return True
        except Exception as e:
            logger.error(f"Error inserting analysis for business {business_id}: {e}")
            return False

    def insert_scoring_result(self, business_id: int, data: Dict[str, Any]) -> bool:
        """Inserts the results of the scoring_engine.py module."""
        query = """
            INSERT INTO scoring_results 
            (business_id, opportunity_score, website_quality_score, seo_score, 
             automation_need_score, likely_service_match, detected_pain_points)
            VALUES (%s, %s, %s, %s, %s, %s, %s);
        """
        try:
            with self.db.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, (
                        business_id,
                        data.get('opportunity_score', 0.0),
                        data.get('website_quality_score', 0.0),
                        data.get('seo_score', 0.0),
                        data.get('automation_need_score', 0.0),
                        json.dumps(data.get('likely_service_match', [])),
                        json.dumps(data.get('detected_pain_points', []))
                    ))
            return True
        except Exception as e:
            logger.error(f"Error inserting score for business {business_id}: {e}")
            return False

    def insert_business_report(self, business_id: int, data: Dict[str, Any]) -> bool:
        """Inserts the results of the business_report_generator.py module."""
        query = """
            INSERT INTO business_reports 
            (business_id, overall_opportunity, website_quality_summary, seo_summary, 
             automation_summary, suggested_services, outreach_angles, 
             improvement_recommendations, raw_text_report)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s);
        """
        try:
            with self.db.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, (
                        business_id,
                        data.get('overall_opportunity'),
                        data.get('website_quality_summary'),
                        data.get('seo_summary'),
                        data.get('automation_summary'),
                        json.dumps(data.get('suggested_services', [])),
                        json.dumps(data.get('outreach_angles', [])),
                        json.dumps(data.get('improvement_recommendations', [])),
                        data.get('raw_text_report')
                    ))
            return True
        except Exception as e:
            logger.error(f"Error inserting report for business {business_id}: {e}")
            return False

    def insert_outreach_draft(self, business_id: int, data: Dict[str, Any]) -> bool:
        """Inserts the results of the outreach_generator.py module."""
        query = """
            INSERT INTO outreach_drafts 
            (business_id, pain_point_positioning, concise_audit_summary, 
             cold_email_draft, whatsapp_draft, ai_prompt_template)
            VALUES (%s, %s, %s, %s, %s, %s);
        """
        try:
            with self.db.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, (
                        business_id,
                        data.get('pain_point_positioning'),
                        data.get('concise_audit_summary'),
                        data.get('cold_email_draft'),
                        data.get('whatsapp_draft'),
                        data.get('ai_prompt_template')
                    ))
            return True
        except Exception as e:
            logger.error(f"Error inserting outreach drafts for business {business_id}: {e}")
            return False

    def insert_email_intelligence(self, business_id: int, data: Dict[str, Any]) -> bool:
        """Inserts the results of the email_extractor.py module."""
        query = """
            INSERT INTO email_intelligence 
            (business_id, extracted_emails, pages_checked, extraction_method, error_message)
            VALUES (%s, %s, %s, %s, %s);
        """
        try:
            with self.db.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, (
                        business_id,
                        json.dumps(data.get('extracted_emails', [])),
                        json.dumps(data.get('pages_checked', [])),
                        data.get('extraction_method', 'regex'),
                        data.get('error')
                    ))
            return True
        except Exception as e:
            logger.error(f"Error inserting email intelligence for business {business_id}: {e}")
            return False

    def insert_tech_stack(self, business_id: int, data: Dict[str, Any]) -> bool:
        """Inserts the results of the tech_stack_detector.py module."""
        query = """
            INSERT INTO tech_stacks 
            (business_id, cms, frontend_framework, analytics_tools, payment_tools, chat_tools, raw_server_header, error_message)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
        """
        try:
            with self.db.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, (
                        business_id,
                        data.get('cms'),
                        data.get('frontend_framework'),
                        json.dumps(data.get('analytics_tools', [])),
                        json.dumps(data.get('payment_tools', [])),
                        json.dumps(data.get('chat_tools', [])),
                        data.get('raw_server_header'),
                        data.get('error')
                    ))
            return True
        except Exception as e:
            logger.error(f"Error inserting tech stack for business {business_id}: {e}")
            return False

    # ---------------------------------------------------------
    # Helper Query Methods for Analytics/Outreach
    # ---------------------------------------------------------
    def get_high_opportunity_businesses(self, min_score: float = 60.0, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Finds the best prospects for outreach. 
        Joins businesses, scores, and reports to return a complete package.
        """
        query = """
            SELECT b.business_name, b.website, b.phone, s.opportunity_score, 
                   s.likely_service_match, r.raw_text_report
            FROM businesses b
            JOIN scoring_results s ON b.id = s.business_id
            LEFT JOIN business_reports r ON b.id = r.business_id
            WHERE s.opportunity_score >= %s
            ORDER BY s.opportunity_score DESC
            LIMIT %s;
        """
        try:
            with self.db.get_connection() as conn:
                # RealDictCursor returns rows as dictionaries instead of tuples
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(query, (min_score, limit))
                    return cur.fetchall()
        except Exception as e:
            logger.error(f"Error querying high opportunity businesses: {e}")
            return []

if __name__ == "__main__":
    # Test DB Setup Execution Context
    logger.info("Database module loaded. To initialize tables, run db.execute_schema()")
    # Example Usage:
    # db_manager = DatabaseManager()
    # db_manager.execute_schema("database/schema.sql")
    # repo = ScraperRepository(db_manager)
    # new_id = repo.insert_business({"business_name": "Test Co", "address": "123 Test St"})
