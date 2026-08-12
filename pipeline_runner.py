import sys
import time
from datetime import datetime
from pathlib import Path
from dataclasses import asdict
from typing import Optional, List, Dict, Any

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')


# Critical fix #3: use the shared logger utility instead of a copy-pasted StructuredLogger.
from scraper.utils.logger import get_scraper_logger

logger = get_scraper_logger("MVP_Pipeline")

# ---------------------------------------------------------
# 2. Module Imports
# ---------------------------------------------------------
# Wrapped in a try-except to provide a clear error if run from the wrong directory
try:
    from scraper.connectors.public_web.google_maps import GoogleMapsScraper
    from scraper.connectors.public_web.company_website import WebsiteAnalyzer
    from analyzer.scoring_engine import ScoringEngine
    from analyzer.seo_checker import SEOChecker
    from analyzer.business_report_generator import ReportGenerator
    from analyzer.outreach_generator import OutreachGenerator
    from database.db import DatabaseManager, ScraperRepository
    
    # Phase 1 enrichment sub-modules
    from enrichment.tech_stack_detector import TechStackDetector
    from enrichment.email_extractor import EmailExtractor
    
    # Phase 2 enrichment & intent sub-modules
    from enrichment.social_analyzer import SocialAnalyzer
    from scraper.connectors.social.social_scraper import SocialScraper
    from intent.hiring_signal_detector import HiringSignalDetector
    from intent.freshness_monitor import FreshnessMonitor
    from intent.review_trend_detector import ReviewTrendDetector
    from intent.intent_engine import IntentEngine

    # Phase 3 enrichment sub-modules
    from enrichment.email_validator import EmailValidator
    from enrichment.decision_maker_finder import DecisionMakerFinder
    from enrichment.entity_resolver import EntityResolver

    # Phase 4 registry connectors
    from scraper.connectors.registries.opencorporates import OpenCorporatesScraper
    from scraper.connectors.registries.justdial import JustDialScraper
    from scraper.connectors.registries.indiamart import IndiaMartScraper

    # Phase 5 monitoring & scheduling
    from monitoring.change_detector import ChangeDetector
    from monitoring.pipeline_monitor import PipelineMonitor, StageResult
    from monitoring.recrawl_scheduler import RecrawlScheduler

    # Phase 4 Business Intelligence sub-modules
    from business_intelligence.conversion_analyzer import ConversionAnalyzer
    from business_intelligence.review_miner import ReviewMiner
    from business_intelligence.customer_pain_extractor import CustomerPainExtractor
    from business_intelligence.competitor_analyzer import CompetitorAnalyzer
    from business_intelligence.trust_signal_detector import TrustSignalDetector
    from business_intelligence.opportunity_mapper import OpportunityMapper
    from business_intelligence.business_health_score import BusinessHealthScore
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
        self.seo_checker = SEOChecker()
        self.report_generator = ReportGenerator()
        self.outreach_generator = OutreachGenerator()
        
        # Phase 1 enrichment sub-modules
        self.tech_detector = TechStackDetector()
        self.email_extractor = EmailExtractor()
        
        # Phase 2 enrichment & intent sub-modules
        self.social_analyzer = SocialAnalyzer()
        self.social_scraper = SocialScraper()     # Deep profile audit (followers, bio, handle)
        self.hiring_detector = HiringSignalDetector()
        self.freshness_monitor = FreshnessMonitor()
        self.review_trend_detector = ReviewTrendDetector(repo=self.repo)
        self.intent_engine = IntentEngine()

        # Phase 3 enrichment sub-modules
        self.email_validator = EmailValidator()
        self.decision_finder = DecisionMakerFinder()
        self.entity_resolver = EntityResolver()

        # Phase 4 registry connectors
        self.opencorporates_scraper = OpenCorporatesScraper()
        self.justdial_scraper = JustDialScraper()
        self.indiamart_scraper = IndiaMartScraper()

        # Phase 5 monitoring & scheduling
        self.change_detector = ChangeDetector()
        self.pipeline_monitor = PipelineMonitor(db_manager=self.db_manager)
        self.recrawl_scheduler = RecrawlScheduler(db_manager=self.db_manager)
        
        # Phase 4 Business Intelligence sub-modules
        self.conversion_analyzer = ConversionAnalyzer()
        self.review_miner = ReviewMiner()
        self.customer_pain_extractor = CustomerPainExtractor()
        self.competitor_analyzer = CompetitorAnalyzer(repo=self.repo)
        self.trust_signal_detector = TrustSignalDetector()
        self.opportunity_mapper = OpportunityMapper()
        self.business_health_score = BusinessHealthScore()
        
        # Ensure database tables exist before we start processing
        logger.info("Verifying database schema...")
        self.db_manager.execute_schema()

    def _resolve_and_save_business(self, b_dict: Dict[str, Any], source: str) -> Optional[int]:
        """Performs targeted entity resolution using SQL candidate matching before inserting/updating."""
        b_name = b_dict.get("business_name", "Unknown")
        business_id = b_dict.get("id")

        if business_id:
            return business_id

        if source in ("justdial", "indiamart"):
            logger.info(f"[{b_name}] Running targeted cross-source entity resolution...")
            candidates = self.repo.find_candidate_matches(b_dict)
            matched_id = None
            highest_conf = 0.0

            for existing in candidates:
                match_result = self.entity_resolver.compare(existing, b_dict)
                if match_result.is_match and match_result.confidence > highest_conf:
                    matched_id = existing["id"]
                    highest_conf = match_result.confidence

            if matched_id:
                logger.info(f"[{b_name}] Match found with existing business (ID: {matched_id}, confidence: {highest_conf}). Merging profiles...")
                b_dict["source_platform"] = source
                self.repo.update_business_sources(matched_id, b_dict)
                return matched_id
            else:
                logger.info(f"[{b_name}] No match found. Ingesting as new business from {source}...")
                b_dict["source_platforms"] = [source]
                return self.repo.insert_business(b_dict)
        elif source == "recrawl":
            return self.repo.insert_business(b_dict)
        else:
            # Default: Google Maps ingestion
            b_dict["source_platforms"] = [source or "gmaps"]
            return self.repo.insert_business(b_dict)


    def process_business(
        self,
        business_obj,
        source: str = "gmaps",
        scrape_duration_ms: Optional[float] = None,
        existing_businesses_snapshot: Optional[List[Dict[str, Any]]] = None,
    ) -> bool:
        """
        Executes the analysis, scoring, and reporting pipeline for a single business.
        """
        if hasattr(business_obj, "__dataclass_fields__"):
            b_dict = asdict(business_obj)
        else:
            b_dict = dict(business_obj)

        b_name = b_dict.get("business_name", "Unknown")
        website = b_dict.get("website")
        
        stages_results = []
        stages_results.append(StageResult(
            stage="scrape",
            success=True,
            duration_ms=scrape_duration_ms
        ))

        try:
            # Step 1: Store Base Business (Upsert / Merge with Entity Resolution)
            business_id = self._resolve_and_save_business(b_dict, source)
                
            if not business_id:
                logger.error(f"[{b_name}] Failed to save business to database. Skipping downstream pipeline.")
                return False
                
            logger.info(f"[{b_name}] Database record ready. DB ID: {business_id}. Commencing analysis...")

            # Fetch previous website analysis snapshot to perform change detection
            previous_analysis = self.repo.get_latest_website_analysis(business_id)

            # Step 2: Analyze Website
            start_t = time.time()
            analysis_obj = self.analyzer.analyze_url(b_name, website)
            analysis_dict = asdict(analysis_obj)
            self.repo.insert_website_analysis(business_id, analysis_dict)
            
            analyze_success = not analysis_obj.error
            stages_results.append(StageResult(
                stage="analyze",
                success=analyze_success,
                duration_ms=(time.time() - start_t) * 1000.0,
                error_message=analysis_obj.error
            ))

            # Run change detection if a previous website analysis is found
            if previous_analysis:
                try:
                    logger.info(f"[{b_name}] Running ChangeDetector against previous crawl...")
                    change_report = self.change_detector.compare(
                        business_id=business_id,
                        business_name=b_name,
                        previous=previous_analysis,
                        current=analysis_dict,
                        previous_at=previous_analysis.get("analyzed_at").isoformat() if hasattr(previous_analysis.get("analyzed_at"), "isoformat") else str(previous_analysis.get("analyzed_at")),
                        current_at=datetime.utcnow().isoformat()
                    )
                    if change_report.changes_detected:
                        self.repo.insert_change_event(
                            business_id=business_id,
                            previous_snapshot_at=change_report.previous_snapshot_at,
                            current_snapshot_at=change_report.current_snapshot_at,
                            change_summary=change_report.change_summary,
                            changes=[asdict(c) for c in change_report.changes]
                        )
                except Exception as ex:
                    logger.error(f"[{b_name}] Failed to run ChangeDetector: {ex}")

            # Run advanced SEO checks
            seo_dict = {}
            if analysis_obj.website_exists and website:
                try:
                    logger.info(f"[{b_name}] Running advanced SEO audit for {website}...")
                    seo_obj = self.seo_checker.audit(b_name, website)
                    seo_dict = asdict(seo_obj)
                    self.repo.insert_seo_profile(business_id, seo_dict)
                except Exception as seo_err:
                    logger.error(f"[{b_name}] Failed to run SEOChecker: {seo_err}")

            # Step 3: Generate Scores
            start_t = time.time()
            score_obj = self.scorer.calculate_scores(analysis_dict, seo_dict if seo_dict else None)
            score_dict = asdict(score_obj)
            self.repo.insert_scoring_result(business_id, score_dict)
            stages_results.append(StageResult(
                stage="score",
                success=True,
                duration_ms=(time.time() - start_t) * 1000.0
            ))

            # Step 4: Generate Human-Readable Report
            start_t = time.time()
            report_obj = self.report_generator.generate_report(analysis_dict, score_dict)
            report_dict = asdict(report_obj)
            self.repo.insert_business_report(business_id, report_dict)
            stages_results.append(StageResult(
                stage="report",
                success=True,
                duration_ms=(time.time() - start_t) * 1000.0
            ))
            
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

            # Step 7c: OpenCorporates Enrichment
            logger.info(f"[{b_name}] Querying OpenCorporates for company registration details...")
            oc_obj = self.opencorporates_scraper.enrich(b_name, jurisdiction="in")
            oc_dict = asdict(oc_obj)
            self.repo.insert_company_registry(business_id, oc_dict)

            # Step 8: Social Analysis (reachability + activity score via SocialAnalyzer)
            social_activity_score = 0.0
            if analysis_obj.website_url:
                social_links = analysis_dict.get("social_links_found", [])
                if social_links:
                    logger.info(f"[{b_name}] Analyzing social profiles: {social_links}...")
                    social_obj = self.social_analyzer.analyze(b_name, social_links)
                    social_dict = asdict(social_obj)
                    self.repo.insert_social_profile(business_id, social_dict)
                    social_activity_score = social_dict.get("social_activity_score", 0.0)

                    # Step 8b: Deep Social Audit (follower counts, bios, handles via SocialScraper)
                    # Only scrape Instagram and Facebook links detected on the website.
                    deep_social_platforms = ["instagram.com", "facebook.com", "fb.com"]
                    deep_links = [
                        link for link in social_links
                        if any(p in link.lower() for p in deep_social_platforms)
                    ]
                    if deep_links:
                        logger.info(f"[{b_name}] Running deep social audit on {len(deep_links)} profile(s)...")
                        for profile_url in deep_links:
                            try:
                                deep_result = self.social_scraper.scrape(profile_url)
                                self.repo.insert_deep_social_audit(business_id, asdict(deep_result))
                                logger.info(
                                    f"[{b_name}] Deep scrape: {deep_result.platform} | "
                                    f"handle={deep_result.handle} | followers={deep_result.follower_count}"
                                )
                            except Exception as deep_err:
                                logger.warning(f"[{b_name}] Deep social scrape failed for {profile_url}: {deep_err}")

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
                review_count=b_dict.get("review_count"),
                business_id=business_id
            )
            review_dict = asdict(review_obj)
            review_trend_score = review_dict.get("review_trend_score", 0.0)

            # Step 12: Intent Evaluation
            logger.info(f"[{b_name}] Evaluating composite buying intent...")
            opp_score = float(score_dict.get("opportunity_score", 0.0))
            intent_signals = {
                "hiring_signal_score": hiring_signal_score,
                "review_trend_score": review_trend_score,
                "freshness_score": freshness_score,
                "opportunity_score": opp_score
            }
            intent_obj = self.intent_engine.evaluate(business_id, b_name, intent_signals)
            intent_dict = asdict(intent_obj)
            self.repo.insert_intent_profile(business_id, intent_dict)

            # Step 13: Business Intelligence Layer (Phase 4)
            logger.info(f"[{b_name}] Executing Business Intelligence analysis...")
            # 1. Conversion friction analysis
            conversion_obj = self.conversion_analyzer.analyze(b_name, website)
            conversion_dict = asdict(conversion_obj)
            
            # 2. Review mining & customer pain signals
            review_mine_obj = self.review_miner.mine_reviews(
                business_name=b_name, 
                category=b_dict.get("category"), 
                rating=float(b_dict.get("google_rating")) if b_dict.get("google_rating") is not None else None,
                review_count=b_dict.get("review_count")
            )
            
            # 3. Customer pain extraction
            pain_obj = self.customer_pain_extractor.extract_pains(b_name, review_mine_obj.recurring_complaints)
            pain_dict = asdict(pain_obj)
            pain_dict["recurring_complaints"] = review_mine_obj.recurring_complaints
            pain_dict["recurring_praise"] = review_mine_obj.recurring_praise
            pain_dict["common_themes"] = review_mine_obj.common_themes
            pain_dict["pain_summary"] = review_mine_obj.pain_summary
            self.repo.insert_customer_pain_signals(business_id, pain_dict)

            # 4. Competitor analysis
            comp_obj = self.competitor_analyzer.analyze(
                business_id=business_id,
                business_name=b_name,
                category=b_dict.get("category"),
                address=b_dict.get("address"),
                opportunity_score=opp_score
            )
            comp_dict = asdict(comp_obj)
            self.repo.insert_competitor_analysis(business_id, comp_dict)

            # 5. Trust signal detection
            trust_obj = self.trust_signal_detector.detect(b_name, website)
            trust_dict = asdict(trust_obj)

            # 6. Business health profile scoring
            health_obj = self.business_health_score.calculate_health(
                business_name=b_name,
                website_quality_score=float(score_dict.get("website_quality_score", 0.0)),
                seo_score=float(score_dict.get("seo_score", 0.0)),
                review_health_score=float(review_mine_obj.review_health_score),
                trust_health_score=float(trust_obj.trust_health_score),
                conversion_health_score=float(conversion_obj.conversion_health_score),
                conversion_friction_score=float(conversion_obj.conversion_friction_score)
            )
            health_dict = asdict(health_obj)
            
            # 7. Opportunity mapping to recommended services & reasoning
            opt_map_obj = self.opportunity_mapper.map_opportunities(
                business_name=b_name,
                web_score=float(score_dict.get("website_quality_score", 0.0)),
                seo_score=float(score_dict.get("seo_score", 0.0)),
                conversion_friction_score=float(conversion_obj.conversion_friction_score),
                trust_health_score=float(trust_obj.trust_health_score),
                conversion_issues=conversion_obj.conversion_issues,
                competitors_gap=comp_obj.competitor_gap_summary
            )
            
            # Save health profile in database
            health_dict["conversion_issues"] = conversion_obj.conversion_issues
            health_dict["trust_signals"] = trust_obj.trust_signals
            health_dict["service_recommendations"] = opt_map_obj.service_recommendations
            health_dict["opportunity_reasoning"] = opt_map_obj.opportunity_reasoning
            self.repo.insert_business_health_profile(business_id, health_dict)

            # Step 5: Generate Outreach Drafts (moved to run after Business Intelligence Opportunity Mapping)
            # Inject found decision-maker name & opportunity reasoning into analysis context for personalization
            start_t = time.time()
            analysis_dict["decision_maker_name"] = decision_maker_name
            analysis_dict["opportunity_reasoning"] = opt_map_obj.opportunity_reasoning
            outreach_obj = self.outreach_generator.generate_outreach(score_dict, analysis_dict)
            outreach_dict = asdict(outreach_obj)
            self.repo.insert_outreach_draft(business_id, outreach_dict)
            stages_results.append(StageResult(
                stage="outreach",
                success=True,
                duration_ms=(time.time() - start_t) * 1000.0
            ))

            # Update recrawl tier and last checked timestamp in businesses table
            opp_score = float(score_dict.get("opportunity_score", 0.0))
            recrawl_tier = self.recrawl_scheduler._classify_tier(opp_score)
            self.repo.update_business_recrawl_status(business_id, recrawl_tier)

            # Record business metrics in run summary
            if hasattr(self, "current_run") and self.current_run:
                self.pipeline_monitor.record_business(
                    run=self.current_run,
                    business_name=b_name,
                    business_id=business_id,
                    stages=stages_results,
                    opportunity_score=opp_score
                )

            logger.info(f"[{b_name}] Pipeline completed successfully. Opportunity Score: {score_dict['opportunity_score']} | Intent Score: {intent_dict['intent_score']}")
            return True

        except Exception as e:
            # Graceful Failure: Catches unexpected crashes (e.g. database disconnect mid-run)
            logger.error(f"[{b_name}] Pipeline failed unexpectedly during processing: {e}")
            if hasattr(self, "current_run") and self.current_run:
                self.pipeline_monitor.record_business(
                    run=self.current_run,
                    business_name=b_name,
                    business_id=business_id if 'business_id' in locals() else None,
                    stages=stages_results
                )
            return False

    def run(self, search_query: str, max_results: int = 10, source: str = "gmaps"):
        """
        Main execution loop.
        """
        logger.info(f"========== PIPELINE STARTED (Source: {source}): '{search_query}' ==========")
        self.current_run = self.pipeline_monitor.start_run(search_query)
        
        try:
            # Phase 1: Ingestion
            if source == "recrawl":
                logger.info("Phase 1: Fetching overdue businesses from scheduler...")
                tasks = self.recrawl_scheduler.get_overdue_businesses(limit=max_results)
                
                if not tasks:
                    logger.warning("No overdue businesses found to recrawl. Pipeline halting.")
                    self.pipeline_monitor.finish_run(self.current_run)
                    self.pipeline_monitor.save_run_summary(self.current_run)
                    return
                
                businesses = []
                for t in tasks:
                    biz_data = self.repo.get_business_by_id(t.business_id)
                    if biz_data:
                        businesses.append(biz_data)
                
                scrape_duration_ms = 0.0
                logger.info(f"Loaded {len(businesses)} overdue businesses for recrawl processing.")
            else:
                start_scrape_t = time.time()
                if source == "justdial":
                    logger.info("Phase 1: Scraping JustDial...")
                    businesses = self.justdial_scraper.scrape(search_query, max_results=max_results)
                elif source == "indiamart":
                    logger.info("Phase 1: Scraping IndiaMart...")
                    businesses = self.indiamart_scraper.scrape(search_query, max_results=max_results)
                else:
                    logger.info("Phase 1: Scraping Google Maps...")
                    businesses = self.scraper.scrape(search_query, max_results=max_results)
                
                scrape_duration_ms = (time.time() - start_scrape_t) * 1000.0
            
            if not businesses:
                logger.warning("No businesses found/scraped. Pipeline halting.")
                self.pipeline_monitor.finish_run(self.current_run)
                self.pipeline_monitor.save_run_summary(self.current_run)
                return
                
            logger.info(f"Loaded {len(businesses)} businesses. Moving to processing phase.")

            # Pre-populate all scraped businesses in the database first so they show up on the dashboard in real-time
            logger.info("Pre-populating scraped businesses in the database...")
            pre_populated_businesses = []

            for i, business in enumerate(businesses, start=1):
                if hasattr(business, "__dataclass_fields__"):
                    b_dict = asdict(business)
                else:
                    b_dict = dict(business)
                b_name = b_dict.get("business_name", "Unknown")

                try:
                    business_id = self._resolve_and_save_business(b_dict, source)
                    if business_id:
                        b_dict["id"] = business_id
                    pre_populated_businesses.append(b_dict)
                except Exception as pe:
                    logger.error(f"[{b_name}] Failed to pre-populate: {pe}")
                    pre_populated_businesses.append(b_dict)
            
            businesses = pre_populated_businesses

            per_business_scrape_ms = scrape_duration_ms / len(businesses) if businesses else 0.0

            # Phase 2: Processing Loop
            success_count = 0
            for i, business in enumerate(businesses, start=1):
                name = business.get("business_name", "Unknown")
                logger.info(f"--- Processing {i}/{len(businesses)}: {name} ---")

                is_success = self.process_business(
                    business,
                    source=source,
                    scrape_duration_ms=per_business_scrape_ms,
                )
                if is_success:
                    success_count += 1
                    
            # Phase 3: Analytics Output
            logger.info(f"========== PIPELINE FINISHED ==========")
            logger.info(f"Successfully processed {success_count}/{len(businesses)} businesses end-to-end.")
            
            # Clean up social scraper browser instance if instantiated
            if hasattr(self, "social_scraper") and self.social_scraper:
                self.social_scraper.close()

            # Finalize pipeline monitoring and save run report
            self.pipeline_monitor.finish_run(self.current_run)
            self.pipeline_monitor.print_run_report(self.current_run)
            self.pipeline_monitor.save_run_summary(self.current_run)
            
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
            if hasattr(self, "social_scraper") and self.social_scraper:
                self.social_scraper.close()
            if hasattr(self, "current_run") and self.current_run:
                self.pipeline_monitor.finish_run(self.current_run)
                self.pipeline_monitor.save_run_summary(self.current_run)

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Run the Business Intelligence Scraper Pipeline")
    parser.add_argument("query", nargs="?", help="Full custom search query")
    parser.add_argument("--category", help="Business category (e.g. 'Gyms')")
    parser.add_argument("--city", help="Target city (e.g. 'Trivandrum')")
    parser.add_argument("--state", help="Target state (e.g. 'Kerala')")
    parser.add_argument("--country", help="Target country (e.g. 'India')")
    parser.add_argument("--limit", type=int, default=3, help="Max results to process (default: 3)")
    parser.add_argument("--source", default="gmaps", choices=["gmaps", "justdial", "indiamart"], help="Scraping source (default: gmaps)")
    parser.add_argument("--recrawl", action="store_true", help="Run in recrawl mode to process overdue businesses")
    
    args = parser.parse_args()
    
    # If in recrawl mode, run the pipeline over scheduler task list
    if args.recrawl:
        actual_limit = args.limit if args.limit > 0 else 9999
        logger.info(f"Starting pipeline in Recrawl Mode. Limit: {actual_limit}")
        pipeline = MVPPipeline()
        pipeline.run("Recrawl Mode", max_results=actual_limit, source="recrawl")
        sys.exit(0)
        
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
                
        logger.info(f"Executing search for: '{final_query}' using source: '{args.source}'")
        pipeline.run(final_query, max_results=actual_limit, source=args.source)
