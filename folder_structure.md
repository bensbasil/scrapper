scraper-project/
│
├── PROJECT_CONTEXT.md
├── SYSTEM_RULES.md
├── ROADMAP.md
├── TASKS.md
├── DATA_DICTIONARY.md
│
├── AI_MEMORY/
│   ├── lessons_learned.md
│   ├── scraper_problems.md
│   ├── selector_changes.md
│   └── architecture_decisions.md
│
├── scraper/
│   ├── base_scraper.py
│   ├── pipeline.py
│   │
│   ├── utils/
│   │   ├── logger.py
│   │   └── exceptions.py
│   │
│   └── connectors/
│       ├── google_maps.py
│       ├── website_scraper.py
│       ├── tech_signals.py
│       ├── justdial.py
│       └── indiamart.py
│
├── enrichment/
│   ├── email_extractor.py
│   ├── email_validator.py
│   ├── decision_maker_finder.py
│   ├── tech_stack_detector.py
│   ├── social_analyzer.py
│   └── entity_resolver.py
│
├── analyzer/
│   ├── website_analyzer.py
│   ├── seo_checker.py
│   ├── scoring_engine.py
│   ├── business_report_generator.py
│   └── intent_engine.py
│
├── monitoring/
│   ├── recrawl_scheduler.py
│   ├── change_detector.py
│   └── freshness_monitor.py
│
├── database/
│   ├── schema.sql
│   └── db.py
│
├── data/
│   ├── raw/
│   ├── processed/
│   ├── exports/
│   └── cache/
│
├── logs/
│
├── requirements.txt
└── .env