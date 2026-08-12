import { ScoringResult } from "@/types";

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

export const MOCK_BUSINESSES: ScoringResult[] = [
  {
    id: "1",
    business_name: "Apex Plumbing & Heating Services",
    category: "Plumbers",
    phone: "+91 98470 12345",
    address: "MG Road, Trivandrum, Kerala 695001",
    website_url: "http://apexplumbingkerala.com",
    google_rating: 4.8,
    review_count: 142,
    opportunity_score: 78,
    website_quality_score: 40,
    seo_score: 45,
    automation_need_score: 85,
    outreach_urgency: "high",
    outreach_status: "new",
    extracted_emails: ["contact@apexplumbingkerala.com", "info@apexplumbing.com"],
    cms: "WordPress 6.2",
    frontend_framework: "jQuery",
    analytics_tools: ["Google Analytics 4"],
    source_platforms: ["google_maps"],
    likely_service_match: ["Web Redesign", "SEO Audit", "WhatsApp Automation"],
    detected_pain_points: [
      "SSL Certificate expired (Browser warning)",
      "Website loading speed > 4.2s on mobile",
      "No automated online booking system",
      "Missing local schema markup"
    ]
  },
  {
    id: "2",
    business_name: "Smile Care Dental Clinic",
    category: "Dentists",
    phone: "+91 94471 88990",
    address: "Kaloor, Kochi, Kerala 682017",
    website_url: "https://smilecarekochi.com",
    google_rating: 4.9,
    review_count: 210,
    opportunity_score: 42,
    website_quality_score: 80,
    seo_score: 75,
    automation_need_score: 60,
    outreach_urgency: "medium",
    outreach_status: "contacted",
    extracted_emails: ["appointments@smilecarekochi.com"],
    cms: "Custom / React",
    frontend_framework: "Next.js",
    analytics_tools: ["Google Tag Manager", "Facebook Pixel"],
    source_platforms: ["google_maps", "justdial"],
    likely_service_match: ["Automated Appointment Reminders", "Review Management"],
    detected_pain_points: [
      "No instant WhatsApp chat widget",
      "No online review auto-responder"
    ]
  },
  {
    id: "3",
    business_name: "Grand Spice Family Restaurant",
    category: "Restaurants",
    phone: "+91 97452 33441",
    address: "East Fort, Trivandrum, Kerala 695023",
    website_url: null,
    google_rating: 4.3,
    review_count: 89,
    opportunity_score: 88,
    website_quality_score: 0,
    seo_score: 10,
    automation_need_score: 90,
    outreach_urgency: "high",
    outreach_status: "new",
    extracted_emails: ["grandspicetvm@gmail.com"],
    cms: "None",
    frontend_framework: "None",
    analytics_tools: [],
    source_platforms: ["google_maps", "indiamart"],
    likely_service_match: ["Web Development", "Google Business Profile Optimization", "Digital Menu & QR Code"],
    detected_pain_points: [
      "No website detected",
      "Missing Google Maps menu link",
      "Losing search traffic to local competitors"
    ]
  },
  {
    id: "4",
    business_name: "Elite Interior Design Studio",
    category: "Interior Designers",
    phone: "+91 98950 66778",
    address: "Jawahar Nagar, Calicut, Kerala 673006",
    website_url: "https://eliteinteriorscalicut.com",
    google_rating: 4.7,
    review_count: 64,
    opportunity_score: 65,
    website_quality_score: 60,
    seo_score: 50,
    automation_need_score: 70,
    outreach_urgency: "medium",
    outreach_status: "followed_up",
    extracted_emails: ["projects@eliteinteriors.com", "hello@eliteinteriors.com"],
    cms: "Wix",
    frontend_framework: "Wix Engine",
    analytics_tools: ["Wix Analytics"],
    source_platforms: ["google_maps"],
    likely_service_match: ["SEO Optimization", "Lead Capture Form", "Portfolio Showcase"],
    detected_pain_points: [
      "Heavy unoptimized high-res images causing slow load times",
      "Missing portfolio lead form",
      "Low Instagram integration"
    ]
  },
  {
    id: "5",
    business_name: "Star AC Repair & Electricals",
    category: "AC Repair Services",
    phone: "+91 91420 55112",
    address: "Pattom, Trivandrum, Kerala 695004",
    website_url: "http://staracservices.in",
    google_rating: 4.1,
    review_count: 45,
    opportunity_score: 82,
    website_quality_score: 30,
    seo_score: 35,
    automation_need_score: 80,
    outreach_urgency: "high",
    outreach_status: "new",
    extracted_emails: ["support@staracservices.in"],
    cms: "Basic HTML",
    frontend_framework: "Bootstrap 3",
    analytics_tools: [],
    source_platforms: ["justdial"],
    likely_service_match: ["Website Redesign", "Local SEO", "Emergency Booking Bot"],
    detected_pain_points: [
      "Not mobile responsive",
      "Outdated layout from 2014",
      "No SSL certificate"
    ]
  },
  {
    id: "6",
    business_name: "Vanguard Tax & Legal Consultants",
    category: "Tax Consultants",
    phone: "+91 98461 99001",
    address: "Vyttila, Kochi, Kerala 682019",
    website_url: "https://vanguardtax.in",
    google_rating: 4.9,
    review_count: 320,
    opportunity_score: 30,
    website_quality_score: 85,
    seo_score: 90,
    automation_need_score: 40,
    outreach_urgency: "normal",
    outreach_status: "closed",
    extracted_emails: ["info@vanguardtax.in"],
    cms: "WordPress 6.4",
    frontend_framework: "Elementor",
    analytics_tools: ["Google Analytics 4", "Hotjar"],
    source_platforms: ["google_maps", "indiamart"],
    likely_service_match: ["Client Portal Automation"],
    detected_pain_points: [
      "Document upload workflow could be automated"
    ]
  }
];
