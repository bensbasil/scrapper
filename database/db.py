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
        sources = data.get('source_platforms')
        if not sources:
            sources = [data.get('source_platform', 'google_maps')]
            
        query = """
            INSERT INTO businesses 
            (business_name, category, website, google_rating, review_count, phone, address,
             jd_rating, jd_reviews_count, jd_verified, im_rating, im_verified, im_gst_verified, source_platforms)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (business_name, address) 
            DO UPDATE SET 
                updated_at = CURRENT_TIMESTAMP,
                source_platforms = (
                    SELECT jsonb_agg(distinct val) 
                    FROM jsonb_array_elements(COALESCE(businesses.source_platforms, '[]'::jsonb) || EXCLUDED.source_platforms) as val
                ),
                website = COALESCE(EXCLUDED.website, businesses.website),
                phone = COALESCE(EXCLUDED.phone, businesses.phone),
                google_rating = COALESCE(EXCLUDED.google_rating, businesses.google_rating),
                review_count = COALESCE(EXCLUDED.review_count, businesses.review_count),
                jd_rating = COALESCE(EXCLUDED.jd_rating, businesses.jd_rating),
                jd_reviews_count = COALESCE(EXCLUDED.jd_reviews_count, businesses.jd_reviews_count),
                jd_verified = COALESCE(EXCLUDED.jd_verified, businesses.jd_verified),
                im_rating = COALESCE(EXCLUDED.im_rating, businesses.im_rating),
                im_verified = COALESCE(EXCLUDED.im_verified, businesses.im_verified),
                im_gst_verified = COALESCE(EXCLUDED.im_gst_verified, businesses.im_gst_verified)
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
                        data.get('address'),
                        data.get('jd_rating'),
                        data.get('jd_reviews_count'),
                        data.get('jd_verified', False),
                        data.get('im_rating'),
                        data.get('im_verified', False),
                        data.get('im_gst_verified', False),
                        json.dumps(sources)
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

    def insert_social_profile(self, business_id: int, data: Dict[str, Any]) -> bool:
        """Inserts the results of the social_analyzer.py module."""
        query = """
            INSERT INTO social_profiles 
            (business_id, profiles, social_activity_score, total_platforms_found, total_platforms_active, error_message)
            VALUES (%s, %s, %s, %s, %s, %s);
        """
        try:
            profiles_raw = data.get('profiles', [])
            profiles_list = []
            for p in profiles_raw:
                if hasattr(p, '__dataclass_fields__'):
                    from dataclasses import asdict
                    profiles_list.append(asdict(p))
                else:
                    profiles_list.append(p)

            with self.db.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, (
                        business_id,
                        json.dumps(profiles_list),
                        data.get('social_activity_score', 0.0),
                        data.get('total_platforms_found', 0),
                        data.get('total_platforms_active', 0),
                        data.get('error')
                    ))
            return True
        except Exception as e:
            logger.error(f"Error inserting social profiles for business {business_id}: {e}")
            return False

    def insert_intent_profile(self, business_id: int, data: Dict[str, Any]) -> bool:
        """Inserts the results of the intent_engine.py module."""
        query = """
            INSERT INTO intent_profiles 
            (business_id, intent_score, hiring_signal_score, review_trend_score, 
             freshness_score, opportunity_score, top_intent_signals, outreach_urgency)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
        """
        try:
            with self.db.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, (
                        business_id,
                        data.get('intent_score', 0.0),
                        data.get('hiring_signal_score', 0.0),
                        data.get('review_trend_score', 0.0),
                        data.get('freshness_score', 0.0),
                        data.get('opportunity_score', 0.0),
                        json.dumps(data.get('top_intent_signals', [])),
                        data.get('outreach_urgency', 'normal')
                    ))
            return True
        except Exception as e:
            logger.error(f"Error inserting intent profile for business {business_id}: {e}")
            return False

    def insert_decision_makers(self, business_id: int, data: Dict[str, Any]) -> bool:
        """Inserts the results of the decision_maker_finder.py module."""
        query = """
            INSERT INTO decision_makers (business_id, name, role, source, confidence)
            VALUES (%s, %s, %s, %s, %s);
        """
        try:
            candidates = data.get('candidates', [])
            with self.db.get_connection() as conn:
                with conn.cursor() as cur:
                    for c in candidates:
                        name = c.name if hasattr(c, 'name') else c.get('name')
                        role = c.role if hasattr(c, 'role') else c.get('role')
                        source = c.source if hasattr(c, 'source') else c.get('source')
                        confidence = c.confidence if hasattr(c, 'confidence') else c.get('confidence', 0.5)
                        cur.execute(query, (business_id, name, role, source, confidence))
            return True
        except Exception as e:
            logger.error(f"Error inserting decision makers for business {business_id}: {e}")
            return False

    def insert_company_registry(self, business_id: int, data: Dict[str, Any]) -> bool:
        """Inserts the results of the OpenCorporates (registries/opencorporates.py) module."""
        query = """
            INSERT INTO company_registry 
            (business_id, company_number, jurisdiction, jurisdiction_label, incorporation_date, 
             company_status, company_type, registered_address, opencorporates_url, source_platform, error_message)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
        """
        try:
            with self.db.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, (
                        business_id,
                        data.get('company_number'),
                        data.get('jurisdiction'),
                        data.get('jurisdiction_label'),
                        data.get('incorporation_date'),
                        data.get('company_status'),
                        data.get('company_type'),
                        data.get('registered_address'),
                        data.get('opencorporates_url'),
                        data.get('source_platform', 'opencorporates'),
                        data.get('error')
                    ))
            return True
        except Exception as e:
            logger.error(f"Error inserting company registry details for business {business_id}: {e}")
            return False

    def update_business_sources(self, business_id: int, source_data: Dict[str, Any]) -> bool:
        """
        Updates an existing business's metadata (like JustDial or IndiaMart scores)
        and appends the new source platform to the source_platforms JSONB array.
        """
        platform = source_data.get('source_platform', 'justdial')
        query = """
            UPDATE businesses 
            SET 
                jd_rating = COALESCE(%s, jd_rating),
                jd_reviews_count = COALESCE(%s, jd_reviews_count),
                jd_verified = COALESCE(%s, jd_verified),
                im_rating = COALESCE(%s, im_rating),
                im_verified = COALESCE(%s, im_verified),
                im_gst_verified = COALESCE(%s, im_gst_verified),
                phone = COALESCE(%s, phone),
                website = COALESCE(%s, website),
                source_platforms = (
                    SELECT jsonb_agg(distinct val)
                    FROM jsonb_array_elements(COALESCE(source_platforms, '[]'::jsonb) || %s::jsonb) as val
                ),
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s;
        """
        try:
            with self.db.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, (
                        source_data.get('jd_rating'),
                        source_data.get('jd_reviews_count'),
                        source_data.get('jd_verified'),
                        source_data.get('im_rating'),
                        source_data.get('im_verified'),
                        source_data.get('im_gst_verified'),
                        source_data.get('phone'),
                        source_data.get('website'),
                        json.dumps([platform]),
                        business_id
                    ))
            return True
        except Exception as e:
            logger.error(f"Error updating sources for business {business_id}: {e}")
            return False

    def insert_pipeline_run(self, data: Dict[str, Any]) -> bool:
        """Inserts a completed pipeline run metrics report."""
        query = """
            INSERT INTO pipeline_runs 
            (run_id, search_query, started_at, finished_at, total_businesses, 
             successful_businesses, failed_businesses, success_rate, 
             high_opportunity_count, stage_failure_counts, business_records, notes)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
        """
        try:
            with self.db.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, (
                        data.get('run_id'),
                        data.get('search_query'),
                        data.get('started_at'),
                        data.get('finished_at'),
                        data.get('total_businesses', 0),
                        data.get('successful_businesses', 0),
                        data.get('failed_businesses', 0),
                        data.get('success_rate', 0.0),
                        data.get('high_opportunity_count', 0),
                        json.dumps(data.get('stage_failure_counts', {})),
                        json.dumps(data.get('business_records', [])),
                        json.dumps(data.get('notes', []))
                    ))
            return True
        except Exception as e:
            logger.error(f"Error inserting pipeline run {data.get('run_id')}: {e}")
            return False

    def insert_change_event(
        self, 
        business_id: int, 
        previous_snapshot_at: Optional[str], 
        current_snapshot_at: Optional[str], 
        change_summary: str, 
        changes: List[Dict[str, Any]]
    ) -> bool:
        """Inserts a detected website change event."""
        query = """
            INSERT INTO change_events 
            (business_id, previous_snapshot_at, current_snapshot_at, change_summary, changes)
            VALUES (%s, %s, %s, %s, %s);
        """
        try:
            with self.db.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, (
                        business_id,
                        previous_snapshot_at,
                        current_snapshot_at,
                        change_summary,
                        json.dumps(changes)
                    ))
            return True
        except Exception as e:
            logger.error(f"Error inserting change event for business {business_id}: {e}")
            return False

    def get_latest_website_analysis(self, business_id: int) -> Optional[Dict[str, Any]]:
        """Retrieves the most recent website analysis for a business."""
        query = """
            SELECT website_exists, ssl_enabled, mobile_friendly, meta_title_exists, 
                   meta_title, meta_description_exists, contact_form_exists, 
                   whatsapp_integration, social_links_found, h1_exists, error_message, analyzed_at
            FROM website_analyses
            WHERE business_id = %s
            ORDER BY analyzed_at DESC
            LIMIT 1;
        """
        try:
            with self.db.get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(query, (business_id,))
                    row = cur.fetchone()
                    if row:
                        if 'social_links_found' in row and isinstance(row['social_links_found'], str):
                            row['social_links_found'] = json.loads(row['social_links_found'])
                        return dict(row)
                    return None
        except Exception as e:
            logger.error(f"Error retrieving latest website analysis for business {business_id}: {e}")
            return None

    def get_business_by_id(self, business_id: int) -> Optional[Dict[str, Any]]:
        """Retrieves a single business by its ID."""
        query = """
            SELECT id, business_name, category, website, google_rating, review_count, 
                   phone, address, jd_rating, jd_reviews_count, jd_verified,
                   im_rating, im_verified, im_gst_verified, source_platforms, outreach_status
            FROM businesses
            WHERE id = %s;
        """
        try:
            with self.db.get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(query, (business_id,))
                    row = cur.fetchone()
                    if row:
                        if 'source_platforms' in row and isinstance(row['source_platforms'], str):
                            row['source_platforms'] = json.loads(row['source_platforms'])
                        return dict(row)
                    return None
        except Exception as e:
            logger.error(f"Error retrieving business by ID {business_id}: {e}")
            return None

    def update_business_recrawl_status(self, business_id: int, recrawl_tier: str) -> bool:
        """Updates last_checked timestamp and recrawl tier for a business."""
        query = """
            UPDATE businesses 
            SET last_checked = CURRENT_TIMESTAMP,
                recrawl_tier = %s
            WHERE id = %s;
        """
        try:
            with self.db.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, (recrawl_tier, business_id))
            return True
        except Exception as e:
            logger.error(f"Error updating recrawl status for business {business_id}: {e}")
            return False

    def update_business_outreach_status(self, business_id: int, status: str) -> bool:
        """Updates the outreach status of a business."""
        query = """
            UPDATE businesses 
            SET outreach_status = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s;
        """
        try:
            with self.db.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, (status, business_id))
            return True
        except Exception as e:
            logger.error(f"Error updating outreach status for business {business_id}: {e}")
            return False

    def get_all_businesses(self) -> List[Dict[str, Any]]:
        """Retrieves all businesses for cross-source entity resolution."""
        query = """
            SELECT id, business_name, category, website, google_rating, review_count, 
                   phone, address, jd_rating, jd_reviews_count, jd_verified,
                   im_rating, im_verified, im_gst_verified, source_platforms, outreach_status
            FROM businesses;
        """
        try:
            with self.db.get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(query)
                    return cur.fetchall()
        except Exception as e:
            logger.error(f"Error retrieving all businesses: {e}")
            return []

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

    def insert_customer_pain_signals(self, business_id: int, data: Dict[str, Any]) -> bool:
        """Inserts Phase 4 customer pain insights."""
        query = """
            INSERT INTO customer_pain_signals 
            (business_id, recurring_complaints, recurring_praise, common_themes, bottlenecks, pain_summary)
            VALUES (%s, %s, %s, %s, %s, %s);
        """
        try:
            with self.db.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, (
                        business_id,
                        json.dumps(data.get('recurring_complaints', [])),
                        json.dumps(data.get('recurring_praise', [])),
                        json.dumps(data.get('common_themes', [])),
                        json.dumps(data.get('bottlenecks', [])),
                        data.get('pain_summary')
                    ))
            return True
        except Exception as e:
            logger.error(f"Error inserting customer pain signals for business {business_id}: {e}")
            return False

    def insert_competitor_analysis(self, business_id: int, data: Dict[str, Any]) -> bool:
        """Inserts Phase 4 competitor analysis."""
        query = """
            INSERT INTO competitor_analysis 
            (business_id, competitors, competitor_gap_summary)
            VALUES (%s, %s, %s);
        """
        try:
            with self.db.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, (
                        business_id,
                        json.dumps(data.get('competitors', [])),
                        data.get('competitor_gap_summary')
                    ))
            return True
        except Exception as e:
            logger.error(f"Error inserting competitor analysis for business {business_id}: {e}")
            return False

    def insert_business_health_profile(self, business_id: int, data: Dict[str, Any]) -> bool:
        """Inserts Phase 4 aggregated business health score profile."""
        query = """
            INSERT INTO business_health_profiles 
            (business_id, overall_health_score, website_health_score, review_health_score, 
             trust_health_score, conversion_health_score, conversion_friction_score, 
             conversion_issues, trust_signals, service_recommendations, opportunity_reasoning)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
        """
        try:
            with self.db.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, (
                        business_id,
                        data.get('overall_health_score', 0.0),
                        data.get('website_health_score', 0.0),
                        data.get('review_health_score', 0.0),
                        data.get('trust_health_score', 0.0),
                        data.get('conversion_health_score', 0.0),
                        data.get('conversion_friction_score', 0.0),
                        json.dumps(data.get('conversion_issues', [])),
                        json.dumps(data.get('trust_signals', [])),
                        json.dumps(data.get('service_recommendations', [])),
                        data.get('opportunity_reasoning')
                    ))
            return True
        except Exception as e:
            logger.error(f"Error inserting business health profile for business {business_id}: {e}")
            return False

    def get_local_competitors(self, city: str, category: str, exclude_id: int) -> List[Dict[str, Any]]:
        """Queries for local competitors in the same city and category."""
        query = """
            SELECT b.id, b.business_name, b.website, b.google_rating, b.review_count, s.opportunity_score
            FROM businesses b
            JOIN scoring_results s ON b.id = s.business_id
            WHERE LOWER(b.category) = LOWER(%s)
              AND (LOWER(b.address) LIKE LOWER('%%' || %s || '%%') OR LOWER(b.business_name) LIKE LOWER('%%' || %s || '%%'))
              AND b.id != %s
            ORDER BY s.opportunity_score ASC; -- low opportunity = strong digital competitors
        """
        try:
            with self.db.get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(query, (category, city, city, exclude_id))
                    return cur.fetchall()
        except Exception as e:
            logger.error(f"Error fetching local competitors for category={category}, city={city}: {e}")
            return []

if __name__ == "__main__":
    # Test DB Setup Execution Context
    logger.info("Database module loaded. To initialize tables, run db.execute_schema()")
    # Example Usage:
    # db_manager = DatabaseManager()
    # db_manager.execute_schema("database/schema.sql")
    # repo = ScraperRepository(db_manager)
    # new_id = repo.insert_business({"business_name": "Test Co", "address": "123 Test St"})
