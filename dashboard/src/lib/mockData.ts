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

export const MOCK_BUSINESSES: ScoringResult[] = [
  {
    id: "1",
    business_name: "Old Plumbing Co",
    website_url: "http://oldplumbing.com",
    opportunity_score: 75.0,
    website_quality_score: 70.0,
    seo_score: 60.0,
    automation_need_score: 50.0,
    likely_service_match: ["web development", "SEO", "automation"],
    detected_pain_points: [
      "SSL missing (Not secure)",
      "Likely not mobile friendly",
      "No social media links detected",
      "Missing meta description",
      "Missing H1 tag",
      "No contact form on site"
    ],
    report: {
      business_name: "Old Plumbing Co",
      overall_opportunity: "High Priority Prospect. Their digital presence is severely lacking, causing an immediate loss of revenue and credibility.",
      website_quality_summary: "The business has a website, but it lacks basic security (no SSL) and is not optimized for mobile phones.",
      seo_summary: "The site is missing critical metadata and missing primary page headings. They are likely losing valuable local search traffic.",
      automation_summary: "Lead capture is weak. There is no way for customers to easily request quotes and no modern instant messaging.",
      suggested_services: ["Web Development", "SEO", "Automation"],
      outreach_angles: [
        "Highlight the 'Not Secure' browser warning and offer a quick security fix.",
        "Show them how their site looks broken on mobile phones and pitch a responsive redesign."
      ],
      improvement_recommendations: [
        "Build a high-converting, mobile-friendly 1-page website.",
        "Install an SSL certificate to secure customer data."
      ],
      raw_text_report: ""
    }
  },
  {
    id: "2",
    business_name: "Modern Dentists NYC",
    website_url: "https://moderndentists.nyc",
    opportunity_score: 35.0,
    website_quality_score: 10.0,
    seo_score: 30.0,
    automation_need_score: 65.0,
    likely_service_match: ["automation", "dashboard"],
    detected_pain_points: [
      "No WhatsApp quick-contact integration",
      "Missing meta description"
    ],
    report: {
      business_name: "Modern Dentists NYC",
      overall_opportunity: "Moderate Opportunity. Their digital fundamentals are solid, but they are lacking modern automation.",
      website_quality_summary: "The website appears structurally sound and secure from a high-level technical view.",
      seo_summary: "The site is missing critical metadata. They could improve their local search rankings slightly.",
      automation_summary: "Lead capture could be improved. There is no modern instant messaging or chat options.",
      suggested_services: ["Automation", "Dashboard"],
      outreach_angles: [
        "Pitch an automated WhatsApp booking bot to stop losing after-hours appointments."
      ],
      improvement_recommendations: [
        "Implement a smart contact form connected directly to their CRM."
      ],
      raw_text_report: ""
    }
  },
  {
    id: "3",
    business_name: "Joe's Corner Bakery",
    website_url: null,
    opportunity_score: 85.0,
    website_quality_score: 100.0,
    seo_score: 100.0,
    automation_need_score: 50.0,
    likely_service_match: ["web development", "SEO"],
    detected_pain_points: [
      "No website detected"
    ],
    report: {
      business_name: "Joe's Corner Bakery",
      overall_opportunity: "High Priority Prospect. Complete lack of digital presence.",
      website_quality_summary: "This business does not have a professional website, severely limiting their online visibility.",
      seo_summary: "Cannot rank on Google without a central website.",
      automation_summary: "Lead capture is non-existent without a website.",
      suggested_services: ["Web Development", "SEO"],
      outreach_angles: [
        "Pitch a simple, modern landing page to instantly establish trust and appear on Google Maps."
      ],
      improvement_recommendations: [
        "Build a high-converting, mobile-friendly 1-page website."
      ],
      raw_text_report: ""
    }
  }
];
