import sys
import logging
from pathlib import Path
from dataclasses import asdict

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
            fh = logging.FileHandler(log_dir / "pipeline.log")
            fh.setFormatter(formatter)
            logger.addHandler(fh)
        return logger

logger = StructuredLogger.get_logger("MVP_Pipeline")

# ---------------------------------------------------------
# 2. Module Imports
# ---------------------------------------------------------
# Wrapped in a try-except to provide a clear error if run from the wrong directory
try:
    from scraper.connectors.public_web.google_maps import GoogleMapsScraper
    from scraper.connectors.public_web.company_website import WebsiteAnalyzer
    from analyzer.scoring_engine import ScoringEngine
    from analyzer.business_report_generator import ReportGenerator
    from analyzer.outreach_generator import OutreachGenerator
    from database.db import DatabaseManager, ScraperRepository
    
    # Phase 1 enrichment sub-modules
    from enrichment.tech_stack_detector import TechStackDetector
    from enrichment.email_extractor import EmailExtractor
    
    # Phase 2 enrichment & intent sub-modules
    from enrichment.social_analyzer import SocialAnalyzer
    from intent.hiring_signal_detector import HiringSignalDetector
    from intent.freshness_monitor import FreshnessMonitor
    from intent.review_trend_detector import ReviewTrendDetector
    from intent.intent_engine import IntentEngine

    # Phase 3 enrichment sub-modules
    from enrichment.email_validator import EmailValidator
    from enrichment.decision_maker_finder import DecisionMakerFinder
    from enrichment.entity_resolver import EntityResolver
except ImportError as e:
    logger.error(f"Failed to import modules. Ensure you run this script from the project root. Error: {e}")
    sys.exit(1)

# ---------------------------------------------------------
# 3. Pipeline Orchestrator
# ---------------------------------------------------------
class MVPPipeline:
    """
    Orchestrates the entire intelligence gathering process:
    Scraping -> DB Store -> Analysis -> Scoring -> Reporting -> DB Store.
    
    Architectural Decisions:
    - Linear execution: Avoids Celery/RabbitMQ for MVP simplicity.
    - Graceful degradation: If a single step fails for one business, the pipeline 
      catches the error and moves onto the next business automatically.
    """
    def __init__(self):
        logger.info("Initializing Pipeline Modules...")
        
        # Initialize modules once to reuse resources (connection pools, browser contexts)
        self.db_manager = DatabaseManager()
        self.repo = ScraperRepository(self.db_manager)
        
        self.scraper = GoogleMapsScraper(headless=True)
        self.analyzer = WebsiteAnalyzer()
        self.scorer = ScoringEngine()
        self.report_generator = ReportGenerator()
        self.outreach_generator = OutreachGenerator()
        
        # Phase 1 enrichment sub-modules
        self.tech_detector = TechStackDetector()
        self.email_extractor = EmailExtractor()
        
        # Phase 2 enrichment & intent sub-modules
        self.social_analyzer = SocialAnalyzer()
        self.hiring_detector = HiringSignalDetector()
        self.freshness_monitor = FreshnessMonitor()
        self.review_trend_detector = ReviewTrendDetector()
        self.intent_engine = IntentEngine()

        # Phase 3 enrichment sub-modules
        self.email_validator = EmailValidator()
        self.decision_finder = DecisionMakerFinder()
        self.entity_resolver = EntityResolver()
        
        # Ensure database tables exist before we start processing
        logger.info("Verifying database schema...")
        self.db_manager.execute_schema()

    def process_business(self, business_obj) -> bool:
        """
        Executes the analysis, scoring, and reporting pipeline for a single business.
        """
        b_dict = asdict(business_obj)
        b_name = b_dict.get("business_name", "Unknown")
        website = b_dict.get("website")
        
        try:
            # Step 1: Store Base Business (Upsert)
            # If the business exists, the repo simply returns the existing ID.
            business_id = self.repo.insert_business(b_dict)
            if not business_id:
                logger.error(f"[{b_name}] Failed to save business to database. Skipping downstream pipeline.")
                return False
                
            logger.info(f"[{b_name}] Stored. DB ID: {business_id}. Commencing analysis...")

            # Step 2: Analyze Website
            analysis_obj = self.analyzer.analyze_url(b_name, website)
            analysis_dict = asdict(analysis_obj)
            self.repo.insert_website_analysis(business_id, analysis_dict)

            # Step 3: Generate Scores
            score_obj = self.scorer.calculate_scores(analysis_dict)
            score_dict = asdict(score_obj)
            self.repo.insert_scoring_result(business_id, score_dict)

            # Step 4: Generate Human-Readable Report
            report_obj = self.report_generator.generate_report(analysis_dict, score_dict)
            report_dict = asdict(report_obj)
            self.repo.insert_business_report(business_id, report_dict)
            
            # Step 6: Tech Stack Detection
            if analysis_obj.website_url:
                logger.info(f"[{b_name}] Scanning website tech stack for {analysis_obj.website_url}...")
                tech_obj = self.tech_detector.detect(b_name, analysis_obj.website_url)
                tech_dict = asdict(tech_obj)
                self.repo.insert_tech_stack(business_id, tech_dict)

            # Step 7: Email Extraction & Verification
            if analysis_obj.website_url:
                logger.info(f"[{b_name}] Crawling website for email addresses on {analysis_obj.website_url}...")
                email_obj = self.email_extractor.extract(b_name, analysis_obj.website_url)
                
                # Perform validation
                validated_results = self.email_validator.validate_batch(email_obj.extracted_emails)
                validated_dicts = [asdict(r) for r in validated_results]
                
                email_dict = asdict(email_obj)
                email_dict["extracted_emails"] = validated_dicts
                self.repo.insert_email_intelligence(business_id, email_dict)

            # Step 7b: Decision-Maker Discovery
            decision_maker_name = None
            if analysis_obj.website_url:
                logger.info(f"[{b_name}] Discovering decision-makers on {analysis_obj.website_url}...")
                decision_obj = self.decision_finder.find(b_name, analysis_obj.website_url)
                decision_dict = asdict(decision_obj)
                self.repo.insert_decision_makers(business_id, decision_dict)
                
                # Find highest confidence decision-maker candidate
                if decision_obj.candidates:
                    # They are already sorted by confidence descending in finder.find()
                    highest_candidate = decision_obj.candidates[0]
                    decision_maker_name = highest_candidate.name
                    logger.info(f"[{b_name}] Found decision-maker: {decision_maker_name} (confidence: {highest_candidate.confidence})")

            # Step 5: Generate Outreach Drafts (moved to run after decision-maker discovery to support custom personalization)
            # Inject found decision-maker name into analysis context for personalization
            analysis_dict["decision_maker_name"] = decision_maker_name
            outreach_obj = self.outreach_generator.generate_outreach(score_dict, analysis_dict)
            outreach_dict = asdict(outreach_obj)
            self.repo.insert_outreach_draft(business_id, outreach_dict)

            # Step 8: Social Analysis
            social_activity_score = 0.0
            if analysis_obj.website_url:
                social_links = analysis_dict.get("social_links_found", [])
                if social_links:
                    logger.info(f"[{b_name}] Analyzing social profiles: {social_links}...")
                    social_obj = self.social_analyzer.analyze(b_name, social_links)
                    social_dict = asdict(social_obj)
                    self.repo.insert_social_profile(business_id, social_dict)
                    social_activity_score = social_dict.get("social_activity_score", 0.0)

            # Step 9: Freshness Monitoring
            freshness_score = 0.0
            if analysis_obj.website_url:
                logger.info(f"[{b_name}] Checking website freshness for {analysis_obj.website_url}...")
                fresh_obj = self.freshness_monitor.check(b_name, analysis_obj.website_url)
                fresh_dict = asdict(fresh_obj)
                freshness_score = fresh_dict.get("freshness_score", 0.0)

            # Step 10: Hiring Signal Detection
            hiring_signal_score = 0.0
            if analysis_obj.website_url:
                logger.info(f"[{b_name}] Detecting hiring signals for {analysis_obj.website_url}...")
                hiring_obj = self.hiring_detector.detect(b_name, analysis_obj.website_url)
                hiring_dict = asdict(hiring_obj)
                hiring_signal_score = hiring_dict.get("hiring_signal_score", 0.0)

            # Step 11: Review Trend Detection
            logger.info(f"[{b_name}] Analyzing review trends...")
            review_obj = self.review_trend_detector.analyze(
                business_name=b_name,
                current_rating=float(b_dict.get("google_rating")) if b_dict.get("google_rating") is not None else None,
                review_count=b_dict.get("review_count")
            )
            review_dict = asdict(review_obj)
            review_trend_score = review_dict.get("review_trend_score", 0.0)

            # Step 12: Intent Evaluation
            logger.info(f"[{b_name}] Evaluating composite buying intent...")
            intent_signals = {
                "hiring_signal_score": hiring_signal_score,
                "review_trend_score": review_trend_score,
                "freshness_score": freshness_score,
                "opportunity_score": float(score_dict.get("opportunity_score", 0.0))
            }
            intent_obj = self.intent_engine.evaluate(business_id, b_name, intent_signals)
            intent_dict = asdict(intent_obj)
            self.repo.insert_intent_profile(business_id, intent_dict)

            logger.info(f"[{b_name}] Pipeline completed successfully. Opportunity Score: {score_dict['opportunity_score']} | Intent Score: {intent_dict['intent_score']}")
            return True

        except Exception as e:
            # Graceful Failure: Catches unexpected crashes (e.g. database disconnect mid-run)
            logger.error(f"[{b_name}] Pipeline failed unexpectedly during processing: {e}")
            return False

    def run(self, search_query: str, max_results: int = 10):
        """
        Main execution loop.
        """
        logger.info(f"========== PIPELINE STARTED: '{search_query}' ==========")
        
        try:
            # Phase 1: Ingestion
            logger.info("Phase 1: Scraping Google Maps...")
            businesses = self.scraper.scrape(search_query, max_results=max_results)
            
            if not businesses:
                logger.warning("No businesses scraped. Pipeline halting.")
                return
                
            logger.info(f"Scraped {len(businesses)} businesses. Moving to processing phase.")

            # Phase 2: Processing Loop
            success_count = 0
            for i, business in enumerate(businesses, start=1):
                logger.info(f"--- Processing {i}/{len(businesses)}: {business.business_name} ---")
                
                is_success = self.process_business(business)
                if is_success:
                    success_count += 1
                    
            # Phase 3: Analytics Output
            logger.info(f"========== PIPELINE FINISHED ==========")
            logger.info(f"Successfully processed {success_count}/{len(businesses)} businesses end-to-end.")
            
            # Print a quick summary of the best leads found
            best_leads = self.repo.get_high_opportunity_businesses(min_score=60.0, limit=3)
            if best_leads:
                logger.info(f"Identified {len(best_leads)} high-priority leads:")
                for lead in best_leads:
                    logger.info(f"- {lead['business_name']} ({lead['opportunity_score']}/100 opportunity)")
            else:
                logger.info("No high-priority leads identified in this batch.")

        except Exception as e:
            logger.critical(f"Critical pipeline failure: {e}")

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Run the Business Intelligence Scraper Pipeline")
    parser.add_argument("query", nargs="?", help="Full custom search query")
    parser.add_argument("--category", help="Business category (e.g. 'Gyms')")
    parser.add_argument("--city", help="Target city (e.g. 'Trivandrum')")
    parser.add_argument("--state", help="Target state (e.g. 'Kerala')")
    parser.add_argument("--country", help="Target country (e.g. 'India')")
    parser.add_argument("--limit", type=int, default=3, help="Max results to process (default: 3)")
    
    args = parser.parse_args()
    
    # Prepare the list of categories to search
    categories_to_search = []
    if args.query:
        # If a raw query is provided, just use that as a single 'category' for the loop logic
        categories_to_search = [args.query]
    elif args.category:
        categories_to_search = [args.category]
    else:
        # User wants "everything"
        categories_to_search = [
            "companies", "shops", "hospitals", "clinics", "restaurants", 
            "retail stores", "agencies", "services", "factories"
        ]
        
    location_parts = [p for p in [args.city, args.state, args.country] if p]
    location_str = ", ".join(location_parts)
    
    # Set a massive limit if they want "everything"
    # (Assuming if limit is 0 or very large, it goes until the end)
    actual_limit = args.limit if args.limit > 0 else 9999
    
    logger.info(f"Starting pipeline. Location: '{location_str}'. Categories: {len(categories_to_search)}. Limit per category: {actual_limit}")
    
    pipeline = MVPPipeline()
    
    for cat in categories_to_search:
        if args.query:
            final_query = cat # The user provided a raw query
        else:
            if location_str:
                final_query = f"{cat} in {location_str}"
            else:
                final_query = cat
                
        logger.info(f"Executing search for: '{final_query}'")
        pipeline.run(final_query, max_results=actual_limit)
