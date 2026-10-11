export interface BusinessReport {
  business_name: string;
  overall_opportunity: string;
  website_quality_summary: string;
  seo_summary: string;
  automation_summary: string;
  suggested_services: string[];
  outreach_angles: string[];
  improvement_recommendations: string[];
  raw_text_report: string;
}

export interface ScoringResult {
  id: string;
  business_name: string;
  category?: string | null;
  phone?: string | null;
  address?: string | null;
  website_url: string | null;
  opportunity_score: number;
  website_quality_score: number;
  seo_score: number;
  automation_need_score: number;
  likely_service_match: string[];
  detected_pain_points: string[];
  source_platforms?: string[];
  google_rating?: number;
  review_count?: number;
  jd_rating?: number;
  jd_reviews_count?: number;
  jd_verified?: boolean;
  im_rating?: number;
  im_verified?: boolean;
  im_gst_verified?: boolean;
  outreach_status?: string;
  report?: BusinessReport;
  extracted_emails?: string[] | null;
  cms?: string | null;
  frontend_framework?: string | null;
  analytics_tools?: string[] | null;
  decision_makers?: { name: string; role: string; confidence: number }[] | null;
  overall_health_score?: number;
  website_health_score?: number;
  review_health_score?: number;
  trust_health_score?: number;
  conversion_health_score?: number;
  conversion_friction_score?: number;
  conversion_issues?: string[] | null;
  trust_signals?: string[] | null;
  service_recommendations?: { service_name: string; impact_explanation: string }[] | null;
  opportunity_reasoning?: string;
  competitors?: any[] | null;
  competitor_gap_summary?: string;
  recurring_complaints?: string[] | null;
  recurring_praise?: string[] | null;
  common_themes?: string[] | null;
  bottlenecks?: string[] | null;
  pain_summary?: string;
  // Intent profile fields (joined from intent_profiles table)
  intent_score?: number | null;
  outreach_urgency?: string | null;
}

export interface ChangeEvent {
  id: number;
  business_id: number;
  changes: any[];
  previous_snapshot_at: string | null;
  current_snapshot_at: string | null;
  change_summary: string | null;
  detected_at: string;
}

export interface OutreachDraft {
  id?: number;
  pain_point_positioning?: string | null;
  concise_audit_summary?: string | null;
  cold_email_draft?: string | null;
  whatsapp_draft?: string | null;
  ai_prompt_template?: string | null;
  generated_at?: string | null;
}

export interface PipelineRun {
  id: string;
  run_id: string;
  search_query: string;
  started_at: string | Date;
  finished_at: string | Date | null;
  total_businesses: number;
  successful_businesses: number;
  failed_businesses: number;
  success_rate: number;
  high_opportunity_count: number;
  stage_failure_counts: Record<string, number>;
  business_records?: any[];
  notes?: string[];
  created_at?: string;
}

