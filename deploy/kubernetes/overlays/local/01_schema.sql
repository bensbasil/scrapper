-- Database Schema for Business Opportunity Intelligence Platform
-- Designed for PostgreSQL

CREATE TABLE IF NOT EXISTS businesses (
    id SERIAL PRIMARY KEY,
    business_name VARCHAR(255) NOT NULL,
    category VARCHAR(100),
    website TEXT,
    google_rating NUMERIC(3, 2),
    review_count INTEGER,
    phone VARCHAR(50),
    address TEXT,
    jd_rating NUMERIC(3, 2),
    jd_reviews_count INTEGER,
    jd_verified BOOLEAN DEFAULT FALSE,
    im_rating NUMERIC(3, 2),
    im_verified BOOLEAN DEFAULT FALSE,
    im_gst_verified BOOLEAN DEFAULT FALSE,
    source_platforms JSONB DEFAULT '[]'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(business_name, address) -- Prevent exact duplicates during multiple scrape runs
);

CREATE TABLE IF NOT EXISTS website_analyses (
    id SERIAL PRIMARY KEY,
    business_id INTEGER NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
    website_exists BOOLEAN DEFAULT FALSE,
    ssl_enabled BOOLEAN DEFAULT FALSE,
    mobile_friendly BOOLEAN DEFAULT FALSE,
    meta_title_exists BOOLEAN DEFAULT FALSE,
    meta_title TEXT,
    meta_description_exists BOOLEAN DEFAULT FALSE,
    contact_form_exists BOOLEAN DEFAULT FALSE,
    whatsapp_integration BOOLEAN DEFAULT FALSE,
    social_links_found JSONB DEFAULT '[]'::jsonb,
    h1_exists BOOLEAN DEFAULT FALSE,
    error_message TEXT,
    analyzed_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS scoring_results (
    id SERIAL PRIMARY KEY,
    business_id INTEGER NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
    opportunity_score NUMERIC(5, 2) NOT NULL,
    website_quality_score NUMERIC(5, 2) NOT NULL,
    seo_score NUMERIC(5, 2) NOT NULL,
    automation_need_score NUMERIC(5, 2) NOT NULL,
    likely_service_match JSONB DEFAULT '[]'::jsonb,
    detected_pain_points JSONB DEFAULT '[]'::jsonb,
    scored_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS business_reports (
    id SERIAL PRIMARY KEY,
    business_id INTEGER NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
    overall_opportunity TEXT,
    website_quality_summary TEXT,
    seo_summary TEXT,
    automation_summary TEXT,
    suggested_services JSONB DEFAULT '[]'::jsonb,
    outreach_angles JSONB DEFAULT '[]'::jsonb,
    improvement_recommendations JSONB DEFAULT '[]'::jsonb,
    raw_text_report TEXT,
    generated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    -- Sig fix #11: one report per business — prevents duplicate rows on re-runs.
    UNIQUE(business_id)
);

CREATE TABLE IF NOT EXISTS outreach_drafts (
    id SERIAL PRIMARY KEY,
    business_id INTEGER NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
    pain_point_positioning TEXT,
    concise_audit_summary TEXT,
    cold_email_draft TEXT,
    whatsapp_draft TEXT,
    ai_prompt_template TEXT,
    generated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS email_intelligence (
    id SERIAL PRIMARY KEY,
    business_id INTEGER NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
    extracted_emails JSONB DEFAULT '[]'::jsonb,
    pages_checked JSONB DEFAULT '[]'::jsonb,
    extraction_method VARCHAR(50) DEFAULT 'regex',
    error_message TEXT,
    extracted_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS tech_stacks (
    id SERIAL PRIMARY KEY,
    business_id INTEGER NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
    cms VARCHAR(100),
    frontend_framework VARCHAR(100),
    analytics_tools JSONB DEFAULT '[]'::jsonb,
    payment_tools JSONB DEFAULT '[]'::jsonb,
    chat_tools JSONB DEFAULT '[]'::jsonb,
    raw_server_header VARCHAR(255),
    error_message TEXT,
    detected_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS social_profiles (
    id SERIAL PRIMARY KEY,
    business_id INTEGER NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
    profiles JSONB DEFAULT '[]'::jsonb,
    social_activity_score NUMERIC(5, 2) NOT NULL,
    total_platforms_found INTEGER DEFAULT 0,
    total_platforms_active INTEGER DEFAULT 0,
    error_message TEXT,
    analyzed_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS intent_profiles (
    id SERIAL PRIMARY KEY,
    business_id INTEGER NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
    intent_score NUMERIC(5, 2) NOT NULL,
    hiring_signal_score NUMERIC(5, 2) NOT NULL,
    review_trend_score NUMERIC(5, 2) NOT NULL,
    freshness_score NUMERIC(5, 2) NOT NULL,
    opportunity_score NUMERIC(5, 2) NOT NULL,
    top_intent_signals JSONB DEFAULT '[]'::jsonb,
    outreach_urgency VARCHAR(50) DEFAULT 'normal',
    evaluated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS decision_makers (
    id SERIAL PRIMARY KEY,
    business_id INTEGER NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    role VARCHAR(150),
    source VARCHAR(100),
    confidence NUMERIC(3, 2),
    discovered_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS company_registry (
    id SERIAL PRIMARY KEY,
    business_id INTEGER NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
    company_number VARCHAR(100),
    jurisdiction VARCHAR(50),
    jurisdiction_label VARCHAR(150),
    incorporation_date DATE,
    company_status VARCHAR(100),
    company_type VARCHAR(150),
    registered_address TEXT,
    opencorporates_url TEXT,
    source_platform VARCHAR(100) DEFAULT 'opencorporates',
    error_message TEXT,
    enriched_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for future analytics compatibility and fast querying
CREATE INDEX IF NOT EXISTS idx_businesses_name ON businesses(business_name);
CREATE INDEX IF NOT EXISTS idx_scoring_opportunity ON scoring_results(opportunity_score DESC);
CREATE INDEX IF NOT EXISTS idx_analysis_business_id ON website_analyses(business_id);
CREATE INDEX IF NOT EXISTS idx_scoring_business_id ON scoring_results(business_id);
CREATE INDEX IF NOT EXISTS idx_reports_business_id ON business_reports(business_id);
CREATE INDEX IF NOT EXISTS idx_outreach_business_id ON outreach_drafts(business_id);
CREATE INDEX IF NOT EXISTS idx_emails_business_id ON email_intelligence(business_id);
CREATE INDEX IF NOT EXISTS idx_tech_business_id ON tech_stacks(business_id);
CREATE INDEX IF NOT EXISTS idx_social_profiles_business_id ON social_profiles(business_id);
CREATE INDEX IF NOT EXISTS idx_intent_profiles_business_id ON intent_profiles(business_id);
CREATE INDEX IF NOT EXISTS idx_intent_profiles_intent_score ON intent_profiles(intent_score DESC);
CREATE INDEX IF NOT EXISTS idx_decision_makers_business_id ON decision_makers(business_id);
CREATE INDEX IF NOT EXISTS idx_company_registry_business_id ON company_registry(business_id);

-- Migrations to add columns to existing tables
ALTER TABLE businesses ADD COLUMN IF NOT EXISTS jd_rating NUMERIC(3, 2);
ALTER TABLE businesses ADD COLUMN IF NOT EXISTS jd_reviews_count INTEGER;
ALTER TABLE businesses ADD COLUMN IF NOT EXISTS jd_verified BOOLEAN DEFAULT FALSE;
ALTER TABLE businesses ADD COLUMN IF NOT EXISTS im_rating NUMERIC(3, 2);
ALTER TABLE businesses ADD COLUMN IF NOT EXISTS im_verified BOOLEAN DEFAULT FALSE;
ALTER TABLE businesses ADD COLUMN IF NOT EXISTS im_gst_verified BOOLEAN DEFAULT FALSE;
ALTER TABLE businesses ADD COLUMN IF NOT EXISTS source_platforms JSONB DEFAULT '[]'::jsonb;
ALTER TABLE businesses ADD COLUMN IF NOT EXISTS last_checked TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE businesses ADD COLUMN IF NOT EXISTS recrawl_tier VARCHAR(50) DEFAULT 'tier3';
ALTER TABLE businesses ADD COLUMN IF NOT EXISTS outreach_status VARCHAR(50) DEFAULT 'new';

-- Indexes for the new fields
CREATE INDEX IF NOT EXISTS idx_businesses_jd_rating ON businesses(jd_rating DESC);
CREATE INDEX IF NOT EXISTS idx_businesses_im_rating ON businesses(im_rating DESC);
CREATE INDEX IF NOT EXISTS idx_businesses_last_checked ON businesses(last_checked);

-- Sig fix #11 migration: add UNIQUE constraint to business_reports if not present.
-- This prevents duplicate report rows when the pipeline reruns for the same business.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'business_reports_business_id_key'
          AND conrelid = 'business_reports'::regclass
    ) THEN
        ALTER TABLE business_reports ADD CONSTRAINT business_reports_business_id_key UNIQUE (business_id);
    END IF;
END $$;


-- Phase 5 Monitoring Tables
CREATE TABLE IF NOT EXISTS pipeline_runs (
    id SERIAL PRIMARY KEY,
    run_id VARCHAR(100) UNIQUE NOT NULL,
    search_query VARCHAR(255) NOT NULL,
    started_at TIMESTAMP WITH TIME ZONE NOT NULL,
    finished_at TIMESTAMP WITH TIME ZONE,
    total_businesses INTEGER DEFAULT 0,
    successful_businesses INTEGER DEFAULT 0,
    failed_businesses INTEGER DEFAULT 0,
    success_rate NUMERIC(5, 2) DEFAULT 0.0,
    high_opportunity_count INTEGER DEFAULT 0,
    stage_failure_counts JSONB DEFAULT '{}'::jsonb,
    business_records JSONB DEFAULT '[]'::jsonb,
    notes JSONB DEFAULT '[]'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS change_events (
    id SERIAL PRIMARY KEY,
    business_id INTEGER NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
    changes JSONB DEFAULT '[]'::jsonb,
    previous_snapshot_at TIMESTAMP WITH TIME ZONE,
    current_snapshot_at TIMESTAMP WITH TIME ZONE,
    change_summary TEXT,
    detected_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_pipeline_runs_run_id ON pipeline_runs(run_id);
CREATE INDEX IF NOT EXISTS idx_change_events_business_id ON change_events(business_id);

-- Phase 4 Business Intelligence Tables
CREATE TABLE IF NOT EXISTS customer_pain_signals (
    id SERIAL PRIMARY KEY,
    business_id INTEGER NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
    recurring_complaints JSONB DEFAULT '[]'::jsonb,
    recurring_praise JSONB DEFAULT '[]'::jsonb,
    common_themes JSONB DEFAULT '[]'::jsonb,
    bottlenecks JSONB DEFAULT '[]'::jsonb,
    pain_summary TEXT,
    analyzed_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS competitor_analysis (
    id SERIAL PRIMARY KEY,
    business_id INTEGER NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
    competitors JSONB DEFAULT '[]'::jsonb, -- list of local competitors: name, website, rating, score gap
    competitor_gap_summary TEXT,
    analyzed_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS business_health_profiles (
    id SERIAL PRIMARY KEY,
    business_id INTEGER NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
    overall_health_score NUMERIC(5, 2) NOT NULL,
    website_health_score NUMERIC(5, 2) NOT NULL,
    review_health_score NUMERIC(5, 2) NOT NULL,
    trust_health_score NUMERIC(5, 2) NOT NULL,
    conversion_health_score NUMERIC(5, 2) NOT NULL,
    conversion_friction_score NUMERIC(5, 2) NOT NULL,
    conversion_issues JSONB DEFAULT '[]'::jsonb,
    trust_signals JSONB DEFAULT '[]'::jsonb,
    service_recommendations JSONB DEFAULT '[]'::jsonb,
    opportunity_reasoning TEXT,
    evaluated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_customer_pains_business ON customer_pain_signals(business_id);
CREATE INDEX IF NOT EXISTS idx_competitor_analysis_business ON competitor_analysis(business_id);
CREATE INDEX IF NOT EXISTS idx_business_health_business ON business_health_profiles(business_id);

-- New Tables for Advanced SEO and Review Trend Snapshots
CREATE TABLE IF NOT EXISTS seo_profiles (
    id SERIAL PRIMARY KEY,
    business_id INTEGER NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
    title_tag VARCHAR(255),
    title_length INTEGER,
    title_optimized BOOLEAN DEFAULT FALSE,
    meta_description TEXT,
    meta_description_length INTEGER,
    meta_description_optimized BOOLEAN DEFAULT FALSE,
    h1_count INTEGER DEFAULT 0,
    h2_count INTEGER DEFAULT 0,
    headings_structure JSONB DEFAULT '[]'::jsonb,
    images_count INTEGER DEFAULT 0,
    images_missing_alt INTEGER DEFAULT 0,
    open_graph_tags JSONB DEFAULT '{}'::jsonb,
    has_viewport_tag BOOLEAN DEFAULT FALSE,
    has_robots_txt BOOLEAN DEFAULT FALSE,
    has_sitemap BOOLEAN DEFAULT FALSE,
    load_time_ms INTEGER,
    checked_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS review_snapshots (
    id SERIAL PRIMARY KEY,
    business_id INTEGER NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
    rating NUMERIC(3, 2),
    review_count INTEGER,
    captured_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_seo_profiles_business_id ON seo_profiles(business_id);
CREATE INDEX IF NOT EXISTS idx_review_snapshots_business_id ON review_snapshots(business_id);

-- Deep Social Audit Table (SocialScraper — follower counts, bios, handles)
CREATE TABLE IF NOT EXISTS deep_social_audits (
    id SERIAL PRIMARY KEY,
    business_id INTEGER NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
    platform VARCHAR(50) NOT NULL,          -- 'instagram' | 'facebook'
    profile_url TEXT NOT NULL,
    is_reachable BOOLEAN DEFAULT FALSE,
    handle VARCHAR(255),
    follower_count VARCHAR(50),             -- stored as string (e.g. '1.2M', '45K')
    follower_count_normalized INTEGER,      -- Minor fix #15: numeric integer for sorting/ranking
    post_count VARCHAR(50),
    bio TEXT,
    error_message TEXT,
    scraped_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

ALTER TABLE deep_social_audits ADD COLUMN IF NOT EXISTS follower_count_normalized INTEGER;

CREATE INDEX IF NOT EXISTS idx_deep_social_audits_business_id ON deep_social_audits(business_id);
CREATE INDEX IF NOT EXISTS idx_deep_social_audits_followers ON deep_social_audits(follower_count_normalized DESC);
