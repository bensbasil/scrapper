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
    generated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
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

-- Indexes for future analytics compatibility and fast querying
CREATE INDEX IF NOT EXISTS idx_businesses_name ON businesses(business_name);
CREATE INDEX IF NOT EXISTS idx_scoring_opportunity ON scoring_results(opportunity_score DESC);
CREATE INDEX IF NOT EXISTS idx_analysis_business_id ON website_analyses(business_id);
CREATE INDEX IF NOT EXISTS idx_scoring_business_id ON scoring_results(business_id);
CREATE INDEX IF NOT EXISTS idx_reports_business_id ON business_reports(business_id);
CREATE INDEX IF NOT EXISTS idx_outreach_business_id ON outreach_drafts(business_id);
CREATE INDEX IF NOT EXISTS idx_emails_business_id ON email_intelligence(business_id);
CREATE INDEX IF NOT EXISTS idx_tech_business_id ON tech_stacks(business_id);

