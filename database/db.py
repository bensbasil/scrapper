import os
import json
from contextlib import contextmanager
from typing import Dict, Any, List, Optional

from dotenv import load_dotenv

load_dotenv()

# Assumes psycopg2 or psycopg2-binary is installed
import psycopg2
from psycopg2.pool import ThreadedConnectionPool
from psycopg2.extras import RealDictCursor, Json as PgJson

# Minor fix #14: use psycopg2's Json adapter instead of json.dumps() for JSONB
# columns. json.dumps() produces a plain Python string that Postgres must then
# re-parse; PgJson passes a properly typed parameter that the driver handles
# natively, avoiding double-serialization overhead.
def jdump(value):
    """Wrap a Python list/dict for safe JSONB insertion via psycopg2."""
    return PgJson(value if value is not None else [])

# Critical fix #3: use the shared logger utility instead of a copy-pasted StructuredLogger.
from scraper.utils.logger import get_scraper_logger

logger = get_scraper_logger(__name__)

# ---------------------------------------------------------
# 2. Database Connection Manager
# ---------------------------------------------------------
class DatabaseManager:
    """
    Manages PostgreSQL connections via a thread-safe connection pool.
    Adheres to MVP rules by avoiding heavy ORM frameworks like SQLAlchemy.
    Uses environment variables for secure connection string passing.
    """
    def __init__(self):
        # Default connection string, override in production via .env
        self.db_url = os.getenv("DATABASE_URL", "postgresql://postgres:password@localhost:5432/scraper_db")
        self.pool = None
        try:
            self.pool = ThreadedConnectionPool(1, 10, dsn=self.db_url)
            logger.info("Thread-safe database connection pool initialized.")
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
                        jdump(sources)
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
                        jdump(data.get('social_links_found', [])),
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
                        jdump(data.get('likely_service_match', [])),
                        jdump(data.get('detected_pain_points', []))
                    ))
            return True
        except Exception as e:
            logger.error(f"Error inserting score for business {business_id}: {e}")
            return False

    def insert_business_report(self, business_id: int, data: Dict[str, Any]) -> bool:
        """Upserts the results of the business_report_generator.py module.
        Sig fix #11: uses ON CONFLICT so re-running the pipeline refreshes the
        existing report row rather than stacking duplicates.
        """
        query = """
            INSERT INTO business_reports
            (business_id, overall_opportunity, website_quality_summary, seo_summary,
             automation_summary, suggested_services, outreach_angles,
             improvement_recommendations, raw_text_report, generated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
            ON CONFLICT (business_id) DO UPDATE SET
                overall_opportunity          = EXCLUDED.overall_opportunity,
                website_quality_summary      = EXCLUDED.website_quality_summary,
                seo_summary                  = EXCLUDED.seo_summary,
                automation_summary           = EXCLUDED.automation_summary,
                suggested_services           = EXCLUDED.suggested_services,
                outreach_angles              = EXCLUDED.outreach_angles,
                improvement_recommendations  = EXCLUDED.improvement_recommendations,
                raw_text_report              = EXCLUDED.raw_text_report,
                generated_at                 = CURRENT_TIMESTAMP;
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
                        jdump(data.get('suggested_services', [])),
                        jdump(data.get('outreach_angles', [])),
                        jdump(data.get('improvement_recommendations', [])),
                        data.get('raw_text_report')
                    ))
            return True
        except Exception as e:
            logger.error(f"Error upserting report for business {business_id}: {e}")
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
                        jdump(data.get('extracted_emails', [])),
                        jdump(data.get('pages_checked', [])),
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
                        jdump(data.get('analytics_tools', [])),
                        jdump(data.get('payment_tools', [])),
                        jdump(data.get('chat_tools', [])),
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
                        jdump(profiles_list),
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
                        jdump(data.get('top_intent_signals', [])),
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
                        jdump([platform]),
                        business_id
                    ))
            return True
        except Exception as e:
            logger.error(f"Error updating sources for business {business_id}: {e}")
            return False

    def insert_pipeline_run(self, data: Dict[str, Any]) -> bool:
        """Inserts or updates a completed pipeline run metrics report."""
        query = """
            INSERT INTO pipeline_runs 
            (run_id, search_query, started_at, finished_at, total_businesses, 
             successful_businesses, failed_businesses, success_rate, 
             high_opportunity_count, stage_failure_counts, business_records, notes)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (run_id) DO UPDATE SET
                finished_at = EXCLUDED.finished_at,
                total_businesses = EXCLUDED.total_businesses,
                successful_businesses = EXCLUDED.successful_businesses,
                failed_businesses = EXCLUDED.failed_businesses,
                success_rate = EXCLUDED.success_rate,
                high_opportunity_count = EXCLUDED.high_opportunity_count,
                stage_failure_counts = EXCLUDED.stage_failure_counts,
                business_records = EXCLUDED.business_records,
                notes = EXCLUDED.notes;
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
                        jdump(data.get('stage_failure_counts', {})),
                        jdump(data.get('business_records', [])),
                        jdump(data.get('notes', []))
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
                        jdump(changes)
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

    def find_candidate_matches(self, data: Dict[str, Any], limit: int = 50) -> List[Dict[str, Any]]:
        """Finds potential matching businesses for entity resolution based on phone, website domain, or name similarity.
        
        This avoids loading the entire database into RAM during cross-source ingestion.
        """
        import re
        phone = data.get("phone")
        website = data.get("website")
        name = data.get("business_name")
        
        phone_digits = "".join(filter(str.isdigit, phone)) if phone else None
        
        domain = None
        if website:
            clean_url = website.strip().lower()
            clean_url = clean_url.replace("https://", "").replace("http://", "").replace("www.", "")
            domain = clean_url.split("/")[0]
        
        if not phone_digits and not domain and not name:
            return []

        conditions = []
        params = []

        if phone_digits and len(phone_digits) >= 7:
            conditions.append("(phone IS NOT NULL AND RIGHT(REGEXP_REPLACE(phone, '\\D', '', 'g'), 10) = RIGHT(%s, 10))")
            params.append(phone_digits)

        if domain and len(domain) > 3:
            conditions.append("(website IS NOT NULL AND LOWER(website) LIKE %s)")
            params.append(f"%{domain}%")

        if name and len(name.strip()) > 2:
            clean_name = re.sub(r"[^a-zA-Z0-9\s]", "", name.strip().lower())
            first_word = clean_name.split()[0] if clean_name.split() else clean_name
            if len(first_word) >= 3:
                conditions.append("(LOWER(business_name) LIKE %s)")
                params.append(f"%{first_word}%")

        if not conditions:
            return []

        query = f"""
            SELECT id, business_name, category, website, google_rating, review_count,
                   phone, address, jd_rating, jd_reviews_count, jd_verified,
                   im_rating, im_verified, im_gst_verified, source_platforms, outreach_status
            FROM businesses
            WHERE {" OR ".join(conditions)}
            ORDER BY id DESC
            LIMIT %s;
        """
        params.append(limit)

        try:
            with self.db.get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(query, tuple(params))
                    rows = cur.fetchall()
                    return [dict(r) for r in rows]
        except Exception as e:
            logger.error(f"Error finding candidate matches for entity resolution: {e}")
            return []

    def get_all_businesses(
        self, limit: int = 500, offset: int = 0
    ) -> List[Dict[str, Any]]:
        """Retrieves businesses for cross-source entity resolution.

        Sig fix #12: Added pagination (limit/offset) so this method never
        loads the entire table into memory at once. Callers that need all
        rows should page through results using increasing offset values.
        Default page size of 500 is a safe upper bound for local use.
        """
        query = """
            SELECT id, business_name, category, website, google_rating, review_count,
                   phone, address, jd_rating, jd_reviews_count, jd_verified,
                   im_rating, im_verified, im_gst_verified, source_platforms, outreach_status
            FROM businesses
            ORDER BY id
            LIMIT %s OFFSET %s;
        """
        try:
            with self.db.get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(query, (limit, offset))
                    return cur.fetchall()
        except Exception as e:
            logger.error(f"Error retrieving businesses (limit={limit}, offset={offset}): {e}")
            return []

    def iter_all_businesses(self, page_size: int = 500):
        """Generator that pages through all businesses without loading everything at once.
        Preferred over get_all_businesses() when the full table needs to be scanned.

        Usage:
            for page in repo.iter_all_businesses():
                for biz in page:
                    ...
        """
        offset = 0
        while True:
            page = self.get_all_businesses(limit=page_size, offset=offset)
            if not page:
                break
            yield page
            if len(page) < page_size:
                break
            offset += page_size


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
                        jdump(data.get('recurring_complaints', [])),
                        jdump(data.get('recurring_praise', [])),
                        jdump(data.get('common_themes', [])),
                        jdump(data.get('bottlenecks', [])),
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
                        jdump(data.get('competitors', [])),
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
                        jdump(data.get('conversion_issues', [])),
                        jdump(data.get('trust_signals', [])),
                        jdump(data.get('service_recommendations', [])),
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

    def insert_seo_profile(self, business_id: int, data: Dict[str, Any]) -> bool:
        """Inserts the results of the seo_checker.py module."""
        query = """
            INSERT INTO seo_profiles 
            (business_id, title_tag, title_length, title_optimized, meta_description, 
             meta_description_length, meta_description_optimized, h1_count, h2_count, 
             headings_structure, images_count, images_missing_alt, open_graph_tags, 
             has_viewport_tag, has_robots_txt, has_sitemap, load_time_ms)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
        """
        try:
            with self.db.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, (
                        business_id,
                        data.get('title_tag'),
                        data.get('title_length'),
                        data.get('title_optimized', False),
                        data.get('meta_description'),
                        data.get('meta_description_length'),
                        data.get('meta_description_optimized', False),
                        data.get('h1_count', 0),
                        data.get('h2_count', 0),
                        jdump(data.get('headings_structure', [])),
                        data.get('images_count', 0),
                        data.get('images_missing_alt', 0),
                        jdump(data.get('open_graph_tags', {})),
                        data.get('has_viewport_tag', False),
                        data.get('has_robots_txt', False),
                        data.get('has_sitemap', False),
                        data.get('load_time_ms')
                    ))
            return True
        except Exception as e:
            logger.error(f"Error inserting SEO profile for business {business_id}: {e}")
            return False

    def insert_review_snapshot(self, business_id: int, rating: Optional[float], review_count: Optional[int]) -> bool:
        """Captures a snapshot of the rating and review count for trend tracking."""
        query = """
            INSERT INTO review_snapshots (business_id, rating, review_count)
            VALUES (%s, %s, %s);
        """
        try:
            with self.db.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, (business_id, rating, review_count))
            return True
        except Exception as e:
            logger.error(f"Error inserting review snapshot for business {business_id}: {e}")
            return False

    def get_latest_review_snapshot(self, business_id: int) -> Optional[Dict[str, Any]]:
        """Retrieves the most recent review snapshot for historical comparison."""
        query = """
            SELECT rating, review_count, captured_at
            FROM review_snapshots
            WHERE business_id = %s
            ORDER BY captured_at DESC
            LIMIT 1;
        """
        try:
            with self.db.get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(query, (business_id,))
                    row = cur.fetchone()
                    return dict(row) if row else None
        except Exception as e:
            logger.error(f"Error fetching latest review snapshot for business {business_id}: {e}")
            return None

    @staticmethod
    def _parse_follower_count(raw_val: Optional[str]) -> Optional[int]:
        """Parses follower count strings like '1.2M', '45.5K', '1,200' into integers."""
        if not raw_val or not isinstance(raw_val, str):
            return None
        val = raw_val.strip().upper().replace(',', '')
        if not val:
            return None
        try:
            if val.endswith('M'):
                return int(float(val[:-1]) * 1_000_000)
            elif val.endswith('K'):
                return int(float(val[:-1]) * 1_000)
            elif val.endswith('B'):
                return int(float(val[:-1]) * 1_000_000_000)
            return int(float(val))
        except Exception:
            return None

    def insert_deep_social_audit(self, business_id: int, data: Dict[str, Any]) -> bool:
        """
        Inserts a single deep social audit result from SocialScraper
        (one row per platform profile scraped per business run).
        Minor fix #15: computes follower_count_normalized for numeric queries.
        """
        raw_followers = data.get("follower_count")
        norm_followers = self._parse_follower_count(raw_followers)
        query = """
            INSERT INTO deep_social_audits
            (business_id, platform, profile_url, is_reachable, handle,
             follower_count, follower_count_normalized, post_count, bio, error_message)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
        """
        try:
            with self.db.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, (
                        business_id,
                        data.get("platform", "unknown"),
                        data.get("url", ""),
                        data.get("is_reachable", False),
                        data.get("handle"),
                        raw_followers,
                        norm_followers,
                        data.get("post_count"),
                        data.get("bio"),
                        data.get("error_message"),
                    ))
            return True
        except Exception as e:
            logger.error(f"Error inserting deep social audit for business {business_id}: {e}")
            return False

    def get_businesses_for_dashboard(
        self, limit: Optional[int] = None, offset: int = 0
    ) -> List[Dict[str, Any]]:
        """Queries processed businesses with scoring, emails, tech stacks, and intent joined.
        Supports pagination via optional limit and offset.
        """
        query = """
            SELECT 
              b.id::text, 
              b.business_name, 
              b.category,
              b.phone,
              b.address,
              b.website as website_url, 
              s.opportunity_score, 
              s.website_quality_score, 
              s.seo_score, 
              s.automation_need_score, 
              s.likely_service_match, 
              s.detected_pain_points,
              b.source_platforms,
              b.google_rating,
              b.review_count,
              b.jd_rating,
              b.jd_reviews_count,
              b.jd_verified,
              b.im_rating,
              b.im_verified,
              b.im_gst_verified,
              COALESCE(b.outreach_status, 'new') AS outreach_status,
              e.extracted_emails,
              t.cms,
              t.analytics_tools,
              t.frontend_framework,
              i.intent_score,
              i.outreach_urgency,
              (SELECT json_agg(dm) FROM (SELECT name, role, confidence FROM decision_makers WHERE business_id = b.id ORDER BY discovered_at DESC) dm) AS decision_makers
            FROM businesses b
            LEFT JOIN (
              SELECT DISTINCT ON (business_id) business_id, opportunity_score, website_quality_score, seo_score, automation_need_score, likely_service_match, detected_pain_points 
              FROM scoring_results 
              ORDER BY business_id, scored_at DESC
            ) s ON b.id = s.business_id
            LEFT JOIN (
              SELECT DISTINCT ON (business_id) business_id, extracted_emails 
              FROM email_intelligence 
              ORDER BY business_id, extracted_at DESC
            ) e ON b.id = e.business_id
            LEFT JOIN (
              SELECT DISTINCT ON (business_id) business_id, cms, analytics_tools, frontend_framework 
              FROM tech_stacks 
              ORDER BY business_id, detected_at DESC
            ) t ON b.id = t.business_id
            LEFT JOIN (
              SELECT DISTINCT ON (business_id) business_id, intent_score, outreach_urgency
              FROM intent_profiles
              ORDER BY business_id, evaluated_at DESC
            ) i ON b.id = i.business_id
            ORDER BY b.id DESC
        """
        params = []
        if limit is not None:
            query += " LIMIT %s OFFSET %s"
            params.extend([limit, offset])

        query += ";"
        try:
            with self.db.get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(query, tuple(params) if params else None)
                    rows = cur.fetchall()
                    businesses = []
                    for r in rows:
                        d = dict(r)
                        # Sanitize detected_pain_points to guarantee string array for React
                        raw_points = d.get("detected_pain_points") or []
                        clean_points = []
                        for p in raw_points:
                            if isinstance(p, str):
                                clean_points.append(p)
                            elif isinstance(p, dict):
                                clean_points.append(p.get("validation_error") or p.get("issue") or p.get("error") or str(p))
                            else:
                                clean_points.append(str(p))
                        d["detected_pain_points"] = clean_points

                        # Sanitize likely_service_match
                        raw_services = d.get("likely_service_match") or []
                        d["likely_service_match"] = [s if isinstance(s, str) else str(s) for s in raw_services]

                        # Sanitize extracted_emails to guarantee string array for React
                        raw_emails = d.get("extracted_emails") or []
                        clean_emails = []
                        for em in raw_emails:
                            if isinstance(em, str):
                                clean_emails.append(em)
                            elif isinstance(em, dict):
                                email_val = em.get("email") or em.get("address") or em.get("value")
                                if isinstance(email_val, str):
                                    clean_emails.append(email_val)
                                elif email_val:
                                    clean_emails.append(str(email_val))
                        d["extracted_emails"] = clean_emails

                        if d.get("source_platforms") is None:
                            d["source_platforms"] = []
                        businesses.append(d)
                    return businesses


        except Exception as e:
            logger.error(f"Error fetching dashboard businesses: {e}")
            return []

    def get_business_detail_for_dashboard(self, business_id: int) -> Optional[Dict[str, Any]]:
        """Queries full business details with health profiles, competitor gap analysis, and pain points."""
        query = """
            SELECT 
              b.id::text, 
              b.business_name, 
              b.website as website_url, 
              s.opportunity_score, 
              s.website_quality_score, 
              s.seo_score, 
              s.automation_need_score, 
              s.likely_service_match, 
              s.detected_pain_points,
              r.overall_opportunity,
              r.website_quality_summary,
              r.seo_summary,
              r.automation_summary,
              r.suggested_services,
              r.outreach_angles,
              r.improvement_recommendations,
              r.raw_text_report,
              COALESCE(b.outreach_status, 'new') AS outreach_status,
              e.extracted_emails,
              t.cms,
              t.frontend_framework,
              t.analytics_tools,
              t.payment_tools,
              t.chat_tools,
              (SELECT json_agg(dm) FROM (SELECT name, role, confidence, source FROM decision_makers WHERE business_id = b.id ORDER BY discovered_at DESC) dm) AS decision_makers,
              h.overall_health_score,
              h.website_health_score,
              h.review_health_score,
              h.trust_health_score,
              h.conversion_health_score,
              h.conversion_friction_score,
              h.conversion_issues,
              h.trust_signals,
              h.service_recommendations,
              h.opportunity_reasoning,
              c_comp.competitors,
              c_comp.competitor_gap_summary,
              p.recurring_complaints,
              p.recurring_praise,
              p.common_themes,
              p.bottlenecks,
              p.pain_summary
            FROM businesses b
            LEFT JOIN (
              SELECT DISTINCT ON (business_id) business_id, opportunity_score, website_quality_score, seo_score, automation_need_score, likely_service_match, detected_pain_points 
              FROM scoring_results 
              ORDER BY business_id, scored_at DESC
            ) s ON b.id = s.business_id
            LEFT JOIN business_reports r ON b.id = r.business_id
            LEFT JOIN (
              SELECT DISTINCT ON (business_id) business_id, extracted_emails 
              FROM email_intelligence 
              ORDER BY business_id, extracted_at DESC
            ) e ON b.id = e.business_id
            LEFT JOIN (
              SELECT DISTINCT ON (business_id) business_id, cms, analytics_tools, frontend_framework, payment_tools, chat_tools 
              FROM tech_stacks 
              ORDER BY business_id, detected_at DESC
            ) t ON b.id = t.business_id
            LEFT JOIN (
              SELECT DISTINCT ON (business_id) business_id, overall_health_score, website_health_score, review_health_score, trust_health_score, conversion_health_score, conversion_friction_score, conversion_issues, trust_signals, service_recommendations, opportunity_reasoning
              FROM business_health_profiles
              ORDER BY business_id, evaluated_at DESC
            ) h ON b.id = h.business_id
            LEFT JOIN (
              SELECT DISTINCT ON (business_id) business_id, competitors, competitor_gap_summary
              FROM competitor_analysis
              ORDER BY business_id, analyzed_at DESC
            ) c_comp ON b.id = c_comp.business_id
            LEFT JOIN (
              SELECT DISTINCT ON (business_id) business_id, recurring_complaints, recurring_praise, common_themes, bottlenecks, pain_summary
              FROM customer_pain_signals
              ORDER BY business_id, analyzed_at DESC
            ) p ON b.id = p.business_id
            WHERE b.id = %s;
        """
        try:
            with self.db.get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(query, (business_id,))
                    row = cur.fetchone()
                    if row:
                        d = dict(row)
                        if d.get("likely_service_match") is None:
                            d["likely_service_match"] = []
                        if d.get("detected_pain_points") is None:
                            d["detected_pain_points"] = []
                        if d.get("extracted_emails") is None:
                            d["extracted_emails"] = []
                        if d.get("source_platforms") is None:
                            d["source_platforms"] = []
                        # Safeguard arrays/lists from other tables
                        for k in ["conversion_issues", "trust_signals", "service_recommendations", 
                                  "competitors", "recurring_complaints", "recurring_praise", "common_themes", "bottlenecks"]:
                            if d.get(k) is None:
                                d[k] = []
                        return d
                    return None
        except Exception as e:
            logger.error(f"Error fetching dashboard business detail for id={business_id}: {e}")
            return None

    def get_outreach_drafts(self, business_id: int) -> Optional[Dict[str, Any]]:
        """Returns the most recent outreach drafts for a business."""
        query_sql = """
            SELECT id, pain_point_positioning, concise_audit_summary,
                   cold_email_draft, whatsapp_draft, ai_prompt_template, generated_at
            FROM outreach_drafts
            WHERE business_id = %s
            ORDER BY generated_at DESC
            LIMIT 1;
        """
        try:
            with self.db.get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(query_sql, (business_id,))
                    row = cur.fetchone()
                    return dict(row) if row else None
        except Exception as e:
            logger.error(f"Error fetching outreach drafts for business {business_id}: {e}")
            return None

    def get_intent_profile(self, business_id: int) -> Optional[Dict[str, Any]]:
        """Returns the most recent intent profile for a business."""
        query_sql = """
            SELECT intent_score, hiring_signal_score, review_trend_score,
                   freshness_score, opportunity_score, top_intent_signals, outreach_urgency, evaluated_at
            FROM intent_profiles
            WHERE business_id = %s
            ORDER BY evaluated_at DESC
            LIMIT 1;
        """
        try:
            with self.db.get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(query_sql, (business_id,))
                    row = cur.fetchone()
                    if not row:
                        return None
                    d = dict(row)
                    if isinstance(d.get("top_intent_signals"), str):
                        try:
                            d["top_intent_signals"] = json.loads(d["top_intent_signals"])
                        except Exception:
                            d["top_intent_signals"] = []
                    return d
        except Exception as e:
            logger.error(f"Error fetching intent profile for business {business_id}: {e}")
            return None

    def get_pipeline_runs(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Returns recent pipeline run summaries ordered by most recent first."""
        query_sql = """
            SELECT run_id, search_query, started_at, finished_at,
                   total_businesses, successful_businesses, failed_businesses,
                   success_rate, high_opportunity_count, notes, created_at
            FROM pipeline_runs
            ORDER BY created_at DESC
            LIMIT %s;
        """
        try:
            with self.db.get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(query_sql, (limit,))
                    rows = cur.fetchall()
                    runs = []
                    for row in rows:
                        d = dict(row)
                        if isinstance(d.get("notes"), str):
                            try:
                                d["notes"] = json.loads(d["notes"])
                            except Exception:
                                d["notes"] = []
                        for dt_field in ("started_at", "finished_at", "created_at"):
                            if d.get(dt_field) and hasattr(d[dt_field], "isoformat"):
                                d[dt_field] = d[dt_field].isoformat()
                        runs.append(d)
                    return runs
        except Exception as e:
            logger.error(f"Error fetching pipeline runs: {e}")
            return []

    def get_pipeline_run_detail(self, run_id: str) -> Optional[Dict[str, Any]]:
        """Returns full detail of a specific pipeline run including per-business records."""
        query_sql = """
            SELECT run_id, search_query, started_at, finished_at,
                   total_businesses, successful_businesses, failed_businesses,
                   success_rate, high_opportunity_count, stage_failure_counts,
                   business_records, notes, created_at
            FROM pipeline_runs
            WHERE run_id = %s;
        """
        try:
            with self.db.get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(query_sql, (run_id,))
                    row = cur.fetchone()
                    if not row:
                        return None
                    d = dict(row)
                    for json_field in ("stage_failure_counts", "business_records", "notes"):
                        if isinstance(d.get(json_field), str):
                            try:
                                d[json_field] = json.loads(d[json_field])
                            except Exception:
                                d[json_field] = [] if json_field != "stage_failure_counts" else {}
                    for dt_field in ("started_at", "finished_at", "created_at"):
                        if d.get(dt_field) and hasattr(d[dt_field], "isoformat"):
                            d[dt_field] = d[dt_field].isoformat()
                    return d
        except Exception as e:
            logger.error(f"Error fetching pipeline run detail for run_id={run_id}: {e}")
            return None

if __name__ == "__main__":
    # Test DB Setup Execution Context
    logger.info("Database module loaded. To initialize tables, run db.execute_schema()")
    # Example Usage:
    # db_manager = DatabaseManager()
    # db_manager.execute_schema("database/schema.sql")
    # repo = ScraperRepository(db_manager)
    # new_id = repo.insert_business({"business_name": "Test Co", "address": "123 Test St"})
