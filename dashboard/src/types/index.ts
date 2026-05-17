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
  website_url: string | null;
  opportunity_score: number;
  website_quality_score: number;
  seo_score: number;
  automation_need_score: number;
  likely_service_match: string[];
  detected_pain_points: string[];
  report?: BusinessReport;
}
