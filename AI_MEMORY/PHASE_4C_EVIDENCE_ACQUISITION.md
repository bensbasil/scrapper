# Phase 4C — Evidence Acquisition & Canonical ProspectContext

**Date:** 2026-10-08  
**Scope:** Phase 4C Implementation & Architectural Guarantees  
**Status:** COMPLETE  

---

## 1. Executive Summary

Phase 4C establishes [`ProspectContext`](file:///Users/ashik/Bens%20Repository/scrapper/schemas/context.py) as the single, canonical evidence contract for each selected prospect entering deep AI reasoning.

The target architecture is:

```text
Discovery
   ↓
Qualification
   ↓
Selection
   ↓
Evidence Acquisition (agent/evidence.py)
   ↓
ProspectContext (schemas/context.py)
   ↓
Opportunity Reasoning (ai/opportunity_reasoner.py)
   ↓
Outreach Strategy (ai/outreach_reasoner.py)
   ↓
Evaluation (evaluation/models.py)
```

The core design principle is:
> **AI reasoning operates exclusively on a structured, bounded evidence contract rather than directly consuming arbitrary domain objects, raw database rows, or raw scraper output.**

---

## 2. The Evidence Acquisition Boundary

Phase 4C introduces [`EvidenceAcquisitionCoordinator`](file:///Users/ashik/Bens%20Repository/scrapper/agent/evidence.py) and [`EvidenceAcquisitionResult`](file:///Users/ashik/Bens%20Repository/scrapper/agent/evidence.py) in `agent/evidence.py`.

### Core Responsibilities:
- Answers the architectural question: *"Given one selected prospect, what canonical evidence is available for AI reasoning?"*
- Coordinates domain capabilities strictly through [`CapabilityRegistry.execute(...)`](file:///Users/ashik/Bens%20Repository/scrapper/application/capabilities/registry.py).
- Assembles and returns the canonical [`ProspectContext`](file:///Users/ashik/Bens%20Repository/scrapper/schemas/context.py).
- Never acts as a scraper, crawler, or database client itself.
- Never invokes `LLMClient`, `OpportunityReasoner`, or `OutreachReasoner` directly. Evidence acquisition prepares the verified evidence; downstream AI capabilities perform reasoning.

---

## 3. Capability Execution Order & Pipeline

Evidence acquisition respects strict domain boundaries and dependency order:

```text
selected prospect (Business)
      ↓
audit_website_tech (website & technology evidence)
      ↓
enrich_leadership_social (decision maker & email evidence)
      ↓
mine_business_intelligence (reviews & customer sentiment evidence)
      ↓
calculate_health_and_scores (deterministic scoring evidence)
      ↓
assemble_prospect_context (delegates to ProspectContextBuilder)
      ↓
canonical ProspectContext
```

All 5 steps execute via `CapabilityRegistry.execute`, honoring safety policies and capturing telemetry events.

---

## 4. Strict Registry-Only Boundary

The evidence acquisition layer never directly imports or accesses:
- Playwright / Chromium
- BeautifulSoup
- PostgreSQL / SQLite / SQL queries
- HTTP clients (`requests`, `httpx`, `aiohttp`, `urllib`)
- LLM clients (`openai`, `anthropic`, `google-genai`)
- Scraper internal classes

All domain interactions are strictly mediated by the typed application capabilities registered in [`CapabilityRegistry`](file:///Users/ashik/Bens%20Repository/scrapper/application/capabilities/registry.py).

---

## 5. Canonical ProspectContext Reuse

No competing context schemas were created. Existing schemas were inspected and verified:
- `schemas/context.py` defines the canonical [`ProspectContext`](file:///Users/ashik/Bens%20Repository/scrapper/schemas/context.py), [`EvidenceItem`](file:///Users/ashik/Bens%20Repository/scrapper/schemas/context.py), and [`ScoreCard`](file:///Users/ashik/Bens%20Repository/scrapper/schemas/context.py).
- `ai/context_builder.py` defines the canonical [`ProspectContextBuilder`](file:///Users/ashik/Bens%20Repository/scrapper/ai/context_builder.py).
- Strictly avoided creating redundant models such as `ProspectEvidence`, `BusinessEvidence`, `AIContext`, or `ReasoningContext`.

---

## 6. Partial Evidence Handling

Real-world prospects frequently have incomplete or unavailable data:
- **Missing Website:** When a business has no website (`website=None` or empty), `audit_website_tech` and `enrich_leadership_social` are cleanly skipped. Customer intelligence, scoring, and context assembly continue unhindered.
- **Missing Decision Makers / Enrichment:** If enrichment finds 0 decision makers or emails, context assembly succeeds with empty lists.
- **Rule:** A prospect is **never discarded** simply because one enrichment signal is unavailable. The system constructs a valid, bounded `ProspectContext` reflecting the partial data.

---

## 7. Evidence Sufficiency Semantics

Phase 4C reuses the established Phase 2 sufficiency contracts:
- If a prospect has 0 evidence items and 0 penalty scores, `context.evidence_sufficiency = "insufficient"`.
- Downstream [`OpportunityReasoner`](file:///Users/ashik/Bens%20Repository/scrapper/ai/opportunity_reasoner.py) detects insufficient evidence, avoids hallucinating digital defects, clamps confidence to `<= 0.4`, and generates a conservative exploratory discovery recommendation.
- Missing evidence is never silently fabricated.

---

## 8. Failure Isolation

Evidence acquisition failure for one prospect cannot abort other prospects in a batch:
- If Prospect B encounters a scraping timeout or policy rejection, Prospect B is marked `FAILED` with execution errors recorded.
- Subsequent prospects (Prospect C, D, E) continue normal evidence acquisition and reasoning.
- Batch aggregation retains per-prospect outcomes (`results: List[ProspectExecutionResult]`) and aggregate metrics (`completed_count`, `failed_count`).

---

## 9. Context Size Boundary & Token Efficiency

To protect downstream LLM context windows and inference costs:
- [`ProspectContext.to_token_efficient_summary()`](file:///Users/ashik/Bens%20Repository/scrapper/schemas/context.py) produces a compact, high-signal prompt representation strictly bounded under 350 words.
- Raw HTML, full page scrapes, unbounded text dumps, and complete database records are forbidden from entering `ProspectContext`.

---

## 10. Evidence Provenance Preservation

Every item in `context.evidence` is typed as [`EvidenceItem`](file:///Users/ashik/Bens%20Repository/scrapper/schemas/context.py):
- `source`: exact provenance (e.g., `"website_audit"`, `"reviews"`, `"google_maps"`, `"tech_stack"`).
- `category`: classification (e.g., `"technical"`, `"reputation"`, `"conversion"`, `"leadership"`).
- `claim`: verified, atomic factual statement.
- `confidence`: confidence weight `[0.0, 1.0]`.

Downstream AI reasoners cite these exact claims in their output (`cited_evidence_points`), guaranteeing factual grounding.

---

## 11. State & Result Integration

- **`AgentState` Extension:**
  Added bounded mapping:
  ```python
  prospect_contexts: Dict[str, ProspectContext] = Field(default_factory=dict)
  ```
  While preserving primary `prospect_context` for single-prospect workflows or the top-ranked prospect in multi-prospect batches.
- **`ProspectExecutionResult` Integration:**
  Retains `prospect_context: Optional[ProspectContext]`, `opportunity_analysis`, `outreach_strategy`, and `opportunity_score`.

---

## 12. Observability & Telemetry

Using the Phase 3F telemetry infrastructure ([`AgentTelemetrySink`](file:///Users/ashik/Bens%20Repository/scrapper/agent/telemetry.py)):
- Records `STARTED` and `COMPLETED`/`FAILED` events for `acquire_evidence` with `prospect_id`, `run_id`, `batch_id`, and `duration_ms`.
- Records per-capability events for each underlying step (`audit_website_tech`, `enrich_leadership_social`, etc.).
- Never logs raw HTML, large payloads, or full `ProspectContext` dumps to telemetry.

---

## 13. Why RAG Is Intentionally Deferred

Phase 4C explicitly rejects introducing RAG (Retrieval-Augmented Generation), vector databases (`pgvector`, `chromadb`), chunk retrieval, embeddings, LangChain, or LangGraph:
1. **Low Volume / High Density:** Prospect evidence for local B2B businesses fits comfortably into a bounded, deterministic summary (< 350 words). Chunking would fragment structured business metrics (ratings, speed, ssl, tech stack).
2. **Deterministic Grounding:** Structured Pydantic contracts guarantee 100% predictable field schemas, whereas vector similarity search introduces non-deterministic retrieval failures and chunk boundaries.
3. **Architectural Discipline:** RAG will only be considered if future phases introduce unstructured document ingestion (e.g. 50-page financial audits or full contract libraries).

---

## 14. Test Verification Summary

The test suite in [`tests/test_evidence_acquisition.py`](file:///Users/ashik/Bens%20Repository/scrapper/tests/test_evidence_acquisition.py) contains 22 targeted unit tests covering all required constraints:
- Single prospect evidence acquisition
- Canonical ProspectContext creation
- Existing context builder reuse
- Registry-only execution boundary
- Partial evidence tolerance
- Missing website handling
- Missing leadership enrichment handling
- Evidence failure isolation across batches
- Multiple prospect contexts mapping
- Context size boundaries (< 350 words)
- Evidence provenance preservation
- Insufficient evidence semantics
- ProspectExecutionResult integration
- AgentState context mapping
- Downstream OpportunityReasoner receives ProspectContext
- Downstream OutreachReasoner receives ProspectContext
- Evidence layer does not call LLM directly
- Evidence layer does not access infrastructure directly
- Telemetry recording
- Phase 4A batch execution compatibility
- Phase 4B qualification integration
- Phase 2 context contract compatibility

**Total platform test count:** **227 passing tests** (100% pass rate in 0.30s).
