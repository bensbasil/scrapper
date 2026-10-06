# Phase 1 — Duplicate Module Analysis Report (P2)

**Date:** 2026-10-06  
**Audited Modules:** `analyzer/`, `business_intelligence/`, `pipeline_runner.py`, `api_server.py`, `scraper/pipeline.py`, `tests/`

---

## 1. Executive Summary

A comprehensive trace of callers and imports across the entire repository reveals that:
1. **The `business_intelligence/` directory contains the true, active canonical implementations** for all business intelligence features (health scoring, competitor analysis, customer pain extraction, review mining, trust signal detection, and conversion friction analysis).
2. **The corresponding files in `analyzer/` are dead placeholder stubs** created early in project scaffolding, returning hardcoded zeros, empty lists, and `TODO` comments.
3. **No active code or test imports the duplicate stubs in `analyzer/`**, with the single exception of the orphaned file `scraper/pipeline.py`, which is itself never executed.
4. **`analyzer/` retains exactly 4 critical, non-duplicated canonical modules**: `scoring_engine.py`, `business_report_generator.py`, `outreach_generator.py`, and `seo_checker.py`.
5. **Zero tests exist for any of the 7 modules in `business_intelligence/`**, creating a test gap despite them being the production implementations.

---

## 2. Granular Module-by-Module Comparison

### Pair 1: Business Health Score
- **`analyzer/business_health_score.py`** (40 lines):
  - Class: `BusinessHealthScorer`
  - Dataclass: `HealthScore` (`overall_health`, `digital_presence_subscore`, `customer_satisfaction_subscore`, `operational_subscore`, `risk_factors`)
  - Method: `calculate_health(self, digital_data: Dict[str, Any], review_data: Any, trust_data: Any) -> HealthScore`
  - Logic: Pure stub with `TODO` comments; returns hardcoded `0.0` and empty lists.
  - Callers: **None**.
- **`business_intelligence/business_health_score.py`** (55 lines):
  - Class: `BusinessHealthScore`
  - Dataclass: `HealthProfileResult` (`overall_health_score`, `website_health_score`, `review_health_score`, `trust_health_score`, `conversion_health_score`, `conversion_friction_score`)
  - Method: `calculate_health(self, business_name, website_quality_score, seo_score, review_health_score, trust_health_score, conversion_health_score, conversion_friction_score) -> HealthProfileResult`
  - Logic: Active composite algorithm weighting website (30%), conversion (30%), reviews (20%), SEO (10%), and trust signals (10%).
  - Callers: [pipeline_runner.py:66, 132, 434](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/pipeline_runner.py#L66-L434).
- **Canonical Implementation:** `business_intelligence.business_health_score` (Class `BusinessHealthScore`).
- **Verdict:** `analyzer/business_health_score.py` is a dead stub.

---

### Pair 2: Competitor Analyzer
- **`analyzer/competitor_analyzer.py`** (40 lines):
  - Class: `CompetitorAnalyzer`
  - Dataclass: `CompetitorInsights` (`market_position`, `identified_competitors`, `competitor_advantages`, `business_advantages`, `threat_level`)
  - Method: `analyze_market_context(self, business_info: Dict[str, Any], location_data: Dict[str, Any]) -> CompetitorInsights`
  - Logic: Pure stub taking no constructor arguments; returns `market_position="unknown"`, `threat_level=0.0`.
  - Callers: **None**.
- **`business_intelligence/competitor_analyzer.py`** (90 lines):
  - Class: `CompetitorAnalyzer` (takes `repo: Any` in constructor)
  - Dataclass: `CompetitorComparison`, `CompetitorAnalysisResult`
  - Method: `analyze(self, business_id: int, business_name: str, category: Optional[str], address: Optional[str], opportunity_score: float) -> CompetitorAnalysisResult`
  - Logic: Queries `repo.get_local_competitors(city, category, business_id)`, calculates digital gap vs competitors, sorts by gap, and formats an actionable narrative.
  - Callers: [pipeline_runner.py:63, 129, 419](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/pipeline_runner.py#L63-L419).
- **Canonical Implementation:** `business_intelligence.competitor_analyzer` (Class `CompetitorAnalyzer`).
- **Verdict:** `analyzer/competitor_analyzer.py` is a dead stub with an incompatible API signature.

---

### Pair 3: Customer Pain Extractor
- **`analyzer/customer_pain_extractor.py`** (38 lines):
  - Class: `CustomerPainExtractor`
  - Dataclass: `PainPointProfile` (`primary_pain_points`, `operational_bottlenecks`, `customer_service_issues`, `urgency_level`)
  - Method: `extract_pain_points(self, business_data: Dict[str, Any], review_intelligence: Any) -> PainPointProfile`
  - Logic: Stub returning empty lists and `urgency_level="unknown"`.
  - Callers: **None**.
- **`business_intelligence/customer_pain_extractor.py`** (58 lines):
  - Class: `CustomerPainExtractor`
  - Dataclass: `PainExtractionResult` (`bottlenecks`, `communication_issues`, `booking_complaints`, `trust_complaints`, `pain_score`)
  - Method: `extract_pains(self, business_name: str, complaints: List[str]) -> PainExtractionResult`
  - Logic: Multi-keyword taxonomy scanning complaints to classify bottlenecks, communication friction, booking issues, and billing/trust complaints; computes composite `pain_score`.
  - Callers: [pipeline_runner.py:62, 128, 410](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/pipeline_runner.py#L62-L410).
- **Canonical Implementation:** `business_intelligence.customer_pain_extractor` (Class `CustomerPainExtractor`).
- **Verdict:** `analyzer/customer_pain_extractor.py` is a dead stub.

---

### Pair 4: Review Miner
- **`analyzer/review_miner.py`** (40 lines):
  - Class: `ReviewMiner`
  - Dataclass: `ReviewIntelligence` (`sentiment_score`, `common_complaints`, `common_praises`, `recent_trend`, `response_rate`)
  - Method: `analyze_reviews(self, reviews_data: List[Dict[str, Any]]) -> ReviewIntelligence`
  - Logic: Stub returning `sentiment_score=0.0` and empty lists.
  - Callers: **None**.
- **`business_intelligence/review_miner.py`** (96 lines):
  - Class: `ReviewMiner`
  - Dataclass: `ReviewMiningResult` (`recurring_complaints`, `recurring_praise`, `common_themes`, `review_health_score`, `pain_summary`)
  - Method: `mine_reviews(self, business_name: str, category: Optional[str], rating: Optional[float], review_count: Optional[int]) -> ReviewMiningResult`
  - Logic: Normalizes business category (gym, hospital, restaurant, general), references category-specific complaints/praise taxonomies, and generates review health metrics and pain summaries based on star ratings.
  - Callers: [pipeline_runner.py:61, 127, 402](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/pipeline_runner.py#L61-L402).
- **Canonical Implementation:** `business_intelligence.review_miner` (Class `ReviewMiner`).
- **Verdict:** `analyzer/review_miner.py` is a dead stub with an incompatible API signature.

---

### Pair 5: Trust Signal Detector
- **`analyzer/trust_signal_detector.py`** (39 lines):
  - Class: `TrustSignalDetector`
  - Dataclass: `TrustMetrics` (`has_ssl`, `has_privacy_policy`, `has_clear_contact_info`, `social_proof_elements`, `trust_score`)
  - Method: `detect_signals(self, html_content: str, parsed_data: Dict[str, Any]) -> TrustMetrics`
  - Logic: Stub returning `trust_score=0.0` and hardcoded `False` values.
  - Callers: **None**.
- **`business_intelligence/trust_signal_detector.py`** (104 lines):
  - Class: `TrustSignalDetector`
  - Dataclass: `TrustSignalResult` (`trust_signals`, `trust_health_score`)
  - Method: `detect(self, business_name: str, url: Optional[str]) -> TrustSignalResult`
  - Logic: Fetches website HTML using `requests` and parses with `BeautifulSoup` for testimonials, accreditation/certifications, third-party review widgets (Trustpilot, Elfsight), awards, and trust badges/privacy policies; calculates score out of 100.
  - Callers: [pipeline_runner.py:64, 130, 430](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/pipeline_runner.py#L64-L430).
- **Canonical Implementation:** `business_intelligence.trust_signal_detector` (Class `TrustSignalDetector`).
- **Verdict:** `analyzer/trust_signal_detector.py` is a dead stub.

---

### Pair 6: Conversion Analyzer
- **`analyzer/website_conversion_analyzer.py`** (52 lines):
  - Class: `WebsiteConversionAnalyzer`
  - Dataclass: `ConversionMetrics` (`has_clear_cta`, `cta_visibility_score`, `form_accessibility`, `checkout_friction_score`, `overall_conversion_score`, `missing_elements`)
  - Method: `analyze(self, html_content: str, website_url: str) -> ConversionMetrics`
  - Logic: Static regex search for `<button|a>` with sign-up keywords and presence of `<form>`.
  - Callers: Only referenced in [scraper/pipeline.py:46](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/scraper/pipeline.py#L46). Note: `scraper/pipeline.py` is completely unreferenced and never called anywhere.
- **`business_intelligence/conversion_analyzer.py`** (168 lines):
  - Class: `ConversionAnalyzer`
  - Dataclass: `ConversionAnalysisResult` (`booking_flow_exists`, `weak_ctas`, `lead_capture_form_exists`, `contact_friction`, `whatsapp_available`, `conversion_friction_score`, `conversion_health_score`, `conversion_issues`)
  - Method: `analyze(self, business_name: str, url: Optional[str]) -> ConversionAnalysisResult`
  - Logic: Direct HTTP fetcher and DOM auditor checking interactive booking widgets, lead capture forms, phone click-to-call links, WhatsApp integrations, and computing friction vs health scores.
  - Callers: [pipeline_runner.py:60, 126, 398](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/pipeline_runner.py#L60-L398).
- **Canonical Implementation:** `business_intelligence.conversion_analyzer` (Class `ConversionAnalyzer`).
- **Verdict:** `analyzer/website_conversion_analyzer.py` is a legacy module used only by dead code.

---

### Pair 7: Growth Signal Detector vs Hiring Signal Detector
- **`analyzer/growth_signal_detector.py`** (39 lines):
  - Class: `GrowthSignalDetector`
  - Dataclass: `GrowthSignals` (`is_hiring`, `recent_expansion`, `new_product_launches`, `ad_spend_detected`, `growth_score`)
  - Method: `detect_signals(self, web_data: Dict[str, Any], external_data: Dict[str, Any]) -> GrowthSignals`
  - Logic: Pure stub returning hardcoded zeros and `False`.
  - Callers: **None**.
- **`intent/hiring_signal_detector.py`** (249 lines):
  - Class: `HiringSignalDetector`
  - Dataclass: `HiringSignalResult`
  - Method: `detect(self, business_name: str, website_url: str) -> HiringSignalResult`
  - Logic: Actively crawls `/careers`, `/jobs`, `/vacancies` paths, scans for 14+ technical roles (`TECHNICAL_ROLES`), and computes `hiring_signal_score` (0-100).
  - Callers: [pipeline_runner.py:39, 105, 367](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/pipeline_runner.py#L39-L367) and `intent/intent_engine.py`.
- **Canonical Implementation:** `intent.hiring_signal_detector`.
- **Verdict:** `analyzer/growth_signal_detector.py` is an obsolete stub that was superseded by Phase 2 Intent modules.

---

### Pair 8: Social Analyzer Wrapper
- **`analyzer/social_analyzer.py`** (12 lines):
  - Logic: Backward compatibility re-export shim:
    ```python
    from enrichment.social_analyzer import SocialAnalyzer, SocialProfile, SocialAnalysisResult
    __all__ = ["SocialAnalyzer", "SocialProfile", "SocialAnalysisResult"]
    ```
  - Callers: **None**. [pipeline_runner.py:37](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/pipeline_runner.py#L37) imports directly from `enrichment.social_analyzer`.
- **`enrichment/social_analyzer.py`** (229 lines):
  - Canonical implementation of the social URL auditor.
- **Verdict:** `analyzer/social_analyzer.py` is a benign, unused backward-compatibility shim.

---

## 3. Inventory of True Canonical Modules

### Modules in `analyzer/` that MUST be preserved:
1. **`scoring_engine.py`**: The primary heuristic opportunity scoring engine ([ScoringEngine](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/analyzer/scoring_engine.py#L32)). Tested in `tests/test_scoring_engine.py`.
2. **`business_report_generator.py`**: Formats human-readable business opportunity reports ([ReportGenerator](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/analyzer/business_report_generator.py#L29)).
3. **`outreach_generator.py`**: Generates cold email and WhatsApp pitch templates via Gemini/OpenAI API or local templates ([OutreachGenerator](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/analyzer/outreach_generator.py#L39)). Tested in `tests/test_outreach_generator.py`.
4. **`seo_checker.py`**: Audits HTML metadata, robots.txt, and XML sitemaps ([SEOChecker](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/analyzer/seo_checker.py#L32)).

### Modules in `business_intelligence/` that MUST be preserved:
1. **`conversion_analyzer.py`**: Audits conversion friction, CTAs, forms, and WhatsApp widgets ([ConversionAnalyzer](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/business_intelligence/conversion_analyzer.py#L30)).
2. **`review_miner.py`**: Extracts category-specific praise, complaints, and review health ([ReviewMiner](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/business_intelligence/review_miner.py#L17)).
3. **`customer_pain_extractor.py`**: Classifies recurring operational bottlenecks and trust issues ([CustomerPainExtractor](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/business_intelligence/customer_pain_extractor.py#L17)).
4. **`competitor_analyzer.py`**: Computes local category competitive digital gaps ([CompetitorAnalyzer](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/business_intelligence/competitor_analyzer.py#L22)).
5. **`trust_signal_detector.py`**: Detects testimonials, accreditation, review widgets, and trust badges ([TrustSignalDetector](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/business_intelligence/trust_signal_detector.py#L16)).
6. **`opportunity_mapper.py`**: Maps detected technical friction to recommended service pitches ([OpportunityMapper](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/business_intelligence/opportunity_mapper.py#L19)).
7. **`business_health_score.py`**: Computes composite business health ratings combining all signals ([BusinessHealthScore](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/business_intelligence/business_health_score.py#L18)).

---

## 4. Risks & Ambiguities Identified

1. **Incompatible Signatures (Silent Crash Risk):**
   The stubs in `analyzer/` and the implementations in `business_intelligence/` share identical or similar module names, but have **entirely different method names, parameter lists, and return dataclasses**:
   - `analyzer/competitor_analyzer.py` expects `analyze_market_context(business_info, location_data)`, while `business_intelligence/competitor_analyzer.py` expects `analyze(business_id, business_name, category, address, opportunity_score)` and requires `repo` injected at `__init__`.
   - `analyzer/review_miner.py` expects `analyze_reviews(reviews_data: List[Dict])`, while `business_intelligence/review_miner.py` expects `mine_reviews(business_name, category, rating, review_count)`.
   - `analyzer/trust_signal_detector.py` expects `detect_signals(html, parsed_data)`, while `business_intelligence/trust_signal_detector.py` expects `detect(business_name, url)`.
   - *Risk:* If any developer or automated tool inadvertently switches an import to `analyzer.*`, it will produce immediate runtime `TypeError` exceptions.

2. **The `scraper/pipeline.py` Dependency Trap:**
   - [scraper/pipeline.py:46](file:///Users/bistto/This%20Mac/Bens%20Repository/scrapper/scraper/pipeline.py#L46) imports `analyzer.website_conversion_analyzer.WebsiteConversionAnalyzer`.
   - Although `scraper/pipeline.py` is unreferenced in the main flow, its presence gives the false impression that `analyzer/website_conversion_analyzer.py` is actively maintained.

3. **Complete Absence of Tests for Canonical Business Intelligence:**
   - `tests/test_scoring_engine.py` and `tests/test_outreach_generator.py` only test `analyzer/`.
   - There are **zero unit tests** for any of the 7 active modules in `business_intelligence/`.

4. **Directory Responsibility Ambiguity:**
   - Currently, `analyzer/` contains core heuristic scoring and copy generation, while `business_intelligence/` contains deeper heuristic analytics.
   - Without clear documentation or consolidation, future contributors are likely to continue adding duplicate or misplaced analyzers.
