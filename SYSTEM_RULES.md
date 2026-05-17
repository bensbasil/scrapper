# System Rules

## General Rules

* Keep architecture modular
* Keep code readable
* Avoid unnecessary abstractions
* Prefer reusable functions
* Add logging and exception handling
* Use environment variables for secrets
* Preserve working functionality during refactors
* Prefer incremental changes over rewrites
* Build one module at a time
* Add TODO markers instead of speculative implementations

---

## Scraper Rules

Every scraper must:

* handle failures gracefully
* support retries
* save partial progress
* export structured data
* support future PostgreSQL integration
* use centralized logging
* avoid hardcoded selectors when possible
* fail without crashing the whole pipeline

---

## Analyzer Rules

All analyzers should:

* return structured outputs
* remain reusable
* support future scoring systems
* avoid direct database coupling
* separate business logic from parsing logic

---

## Data Rules

* Keep raw and processed data separated
* Normalize repeated entities
* Deduplicate businesses
* Keep outputs JSON and CSV compatible
* Store timestamps on collected records

---

## Architecture Rules

* Keep MVP simplicity first
* Refactor only when duplication becomes painful
* Preserve current working modules
* Prefer connectors over massive files
* Use starter skeletons before full implementation

---

## AI Rules

AI-generated modules should:

* explain architecture decisions
* include TODO comments where needed
* avoid hallucinated assumptions
* avoid fake business claims

---

## MVP Focus

Current MVP:

* scraping
* enrichment
* analysis
* scoring
* opportunity intelligence

Do NOT add:

* microservices
* Kubernetes
* distributed systems
* unnecessary AI agents
* premature optimization
