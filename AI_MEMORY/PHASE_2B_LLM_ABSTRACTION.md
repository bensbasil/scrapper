# Phase 2B — LLM Abstraction & Structured AI Contracts

**Date:** 2026-10-08  
**Scope:** Provider-Independent LLM Boundary, Configuration Contract, Typed Structured Outputs, and Outreach Decoupling  
**Status:** COMPLETE  

---

## 1. Objective

Phase 2B introduces a clean, provider-independent LLM boundary that consumes prospect data and returns validated, typed structured AI outputs. This milestone establishes the **AI infrastructure foundation** without implementing full opportunity reasoning workflows yet.

Key achievements:
1. Audited and eliminated direct provider coupling and duplicated HTTP logic in [`analyzer/outreach_generator.py`](file:///Users/ashik/Bens%20Repository/scrapper/analyzer/outreach_generator.py).
2. Defined typed Pydantic v2 output schemas in [`schemas/ai.py`](file:///Users/ashik/Bens%20Repository/scrapper/schemas/ai.py): [`OpportunityAnalysis`](file:///Users/ashik/Bens%20Repository/scrapper/schemas/ai.py), [`CommercialRecommendation`](file:///Users/ashik/Bens%20Repository/scrapper/schemas/ai.py), [`OutreachStrategy`](file:///Users/ashik/Bens%20Repository/scrapper/schemas/ai.py), and [`OutreachDraftResponse`](file:///Users/ashik/Bens%20Repository/scrapper/schemas/ai.py).
3. Created [`ai/config.py`](file:///Users/ashik/Bens%20Repository/scrapper/ai/config.py) (`LLMConfig`) for provider, credential, model, temperature, timeout, and token management via environment variables without hardcoded secrets.
4. Created [`ai/exceptions.py`](file:///Users/ashik/Bens%20Repository/scrapper/ai/exceptions.py) with typed, observable failure exceptions: `LLMUnavailableError`, `LLMProviderError`, `LLMResponseParsingError`, and `LLMValidationError`.
5. Created [`ai/client.py`](file:///Users/ashik/Bens%20Repository/scrapper/ai/client.py) (`LLMClient`) supporting Google Gemini and OpenAI-compatible endpoints with automatic schema injection, markdown code fence stripping, JSON parsing, and Pydantic validation.
6. Refactored `OutreachGenerator` to delegate to `LLMClient`, maintaining 100% backward compatibility and deterministic fallback.
7. Verified with 17 focused unit tests with mocked provider responses (0 live API calls).

---

## 2. Current LLM Integration Audit

Prior to Phase 2B, LLM interactions were tightly coupled inside `analyzer/outreach_generator.py`:

| Dimension | Gemini Integration (`_generate_via_gemini`) | OpenAI Integration (`_generate_via_openai`) | Identified Architectural Issues |
| :--- | :--- | :--- | :--- |
| **Request Construction** | Ad-hoc `requests.post()` with Google-specific payload hierarchy (`contents[].parts[].text`, `generationConfig.responseMimeType`, `generationConfig.responseSchema`). | Ad-hoc `requests.post()` with OpenAI chat completion payload (`model`, `response_format`, `messages`). | Duplicated HTTP transport; tightly couples caller to provider wire formats. |
| **Authentication** | Direct `os.environ.get("GEMINI_API_KEY")` passed in query param `?key=...`. | Direct `os.environ.get("OPENAI_API_KEY")` passed in header `Authorization: Bearer ...`. | Decentralized env reading; credentials exposed directly inside generator methods. |
| **Model Config** | `GEMINI_MODEL` (default: `gemini-1.5-flash`). Hardcoded 12s timeout. No temperature control. | `OPENAI_MODEL` (default: `gpt-4o-mini`). Hardcoded 12s timeout. No temperature control. | Inflexible, scattered model configurations without unified defaults or overrides. |
| **Prompt Construction** | Duplicated prompt string with interpolated context. | Nearly identical duplicated prompt string with slightly different instructions. | Code duplication; difficult to iterate on prompt templates without updating multiple branches. |
| **Response Parsing** | Custom JSON extraction from `candidates[0].content.parts[0].text`. Checked dict keys manually. | Custom JSON extraction from `choices[0].message.content`. Checked dict keys manually. | Untyped dictionary returns (`Dict[str, str]`); zero Pydantic validation; runtime crashes if keys missing. |
| **Error Handling** | Bare `except Exception as e` logging error and returning `None`. | Bare `except Exception as e` logging error and returning `None`. | Failure modes (rate limit vs bad JSON vs timeout) are hidden from callers; unobservable failure states. |
| **Fallback** | Cascaded to OpenAI, then fell back to rule-based template generation. | Cascaded to rule-based template generation. | Good concept, but hardcoded into the business logic layer instead of abstracted behind an infrastructure boundary. |

---

## 3. Provider-Independent LLM Boundary

```text
Application / Pipelines
       │
       ▼
AI Intelligence / Reasoners (e.g. OutreachGenerator, future OpportunityReasoner)
       │
       ▼
   LLMClient  (ai/client.py)
   ├── Configuration (ai/config.py)
   ├── Schema Validation & Parsing (pydantic)
   ├── Failure Observability (ai/exceptions.py)
   └── Provider Adapters
       ├── Gemini Adapter (REST v1beta)
       └── OpenAI Adapter (REST v1 chat/completions)
```

### Boundary Responsibilities:
- `LLMClient` handles only provider communication, schema injection, response parsing, and validation.
- `LLMClient` **never** queries PostgreSQL, executes SQL, scrapes websites, launches Playwright, or decides business rules.

---

## 4. Provider Configuration Contract

Implemented in [`ai/config.py`](file:///Users/ashik/Bens%20Repository/scrapper/ai/config.py):

```python
class LLMConfig(BaseModel):
    provider: str = Field(default="auto") # 'gemini', 'openai', 'auto', 'none'
    api_key: Optional[str] = None
    model: Optional[str] = None
    temperature: float = 0.2
    timeout: float = 15.0
    max_tokens: Optional[int] = 1024
    base_url: Optional[str] = None
```

### Resolution Logic:
1. `LLMConfig.from_env()` checks explicit overrides, then `LLM_PROVIDER`.
2. In `auto` mode:
   - If `GEMINI_API_KEY` is present, selects provider `"gemini"` (`GEMINI_MODEL` or `"gemini-1.5-flash"`).
   - If `OPENAI_API_KEY` is present, selects provider `"openai"` (`OPENAI_MODEL` or `"gpt-4o-mini"`).
   - If neither is present, selects provider `"none"`.
3. Never hardcodes secrets or commits API keys.

---

## 5. Structured AI Output Contracts

Defined in [`schemas/ai.py`](file:///Users/ashik/Bens%20Repository/scrapper/schemas/ai.py) and re-exported in [`schemas/__init__.py`](file:///Users/ashik/Bens%20Repository/scrapper/schemas/__init__.py):

### 1. `OpportunityAnalysis`
```python
class CommercialRecommendation(BaseModel):
    service_name: str
    target_problem: str
    commercial_impact: str
    suggested_pricing_tier: str = "core"  # "entry" | "core" | "premium"

class OpportunityAnalysis(BaseModel):
    executive_diagnosis: str
    primary_pain_category: str  # "conversion" | "reputation" | "technical" | "visibility" | "infrastructure"
    recommendations: List[CommercialRecommendation]
    strategic_pitch_angle: str
    cited_evidence_points: List[str]
    confidence_score: float = 1.0
```

### 2. `OutreachStrategy`
```python
class OutreachStrategy(BaseModel):
    positioning_summary: str
    primary_angle: str
    cold_email_subject: str
    cold_email_body: str
    whatsapp_message: str
    call_opening_hook: Optional[str] = None
    anticipated_objection: Optional[str] = None
    objection_counter: Optional[str] = None
    cited_evidence_points: List[str] = Field(default_factory=list)
```

### 3. `OutreachDraftResponse`
```python
class OutreachDraftResponse(BaseModel):
    cold_email_draft: str
    whatsapp_draft: str
```

All models inherit from Pydantic v2 `BaseModel` with `ConfigDict(from_attributes=True, populate_by_name=True)`.

---

## 6. Structured Generation Interface

Implemented in [`ai/client.py`](file:///Users/ashik/Bens%20Repository/scrapper/ai/client.py):

```python
class LLMClient:
    def __init__(self, config: Optional[LLMConfig] = None): ...

    @property
    def is_available(self) -> bool: ...

    def generate_structured(
        self,
        prompt: str,
        response_model: Type[T],
        system_prompt: Optional[str] = None,
    ) -> T: ...

    def generate_structured_safe(
        self,
        prompt: str,
        response_model: Type[T],
        system_prompt: Optional[str] = None,
    ) -> Optional[T]: ...
```

### Features:
- **Resilient JSON Decoding**: Strips markdown code blocks (````json ... ````) automatically.
- **Dynamic Schema Injection**: Injects Pydantic `model_json_schema()` directly into system prompts and generation configs.
- **Strong Typing**: Returns instances of `response_model`, not arbitrary dictionaries.

---

## 7. Failure & Fallback Behavior

Implemented in [`ai/exceptions.py`](file:///Users/ashik/Bens%20Repository/scrapper/ai/exceptions.py):
- `LLMUnavailableError`: Raised when provider is `"none"` or API key is missing.
- `LLMProviderError`: Raised on HTTP errors (e.g. 429, 500), connection errors, or timeouts. Carries `status_code` and `response_body`.
- `LLMResponseParsingError`: Raised when provider response is not valid JSON. Carries `raw_text`.
- `LLMValidationError`: Raised when JSON does not conform to the Pydantic schema. Carries `raw_data`.

For callers requiring non-raising fallbacks (such as `OutreachGenerator`), `generate_structured_safe()` logs the specific error and returns `None`, allowing deterministic rule-based template generation to proceed seamlessly.

---

## 8. OutreachGenerator Refactoring & Compatibility

In [`analyzer/outreach_generator.py`](file:///Users/ashik/Bens%20Repository/scrapper/analyzer/outreach_generator.py):
- Initialized with `self.llm_client = llm_client or LLMClient()`.
- Uses `self.llm_client.generate_structured_safe(..., OutreachDraftResponse)`.
- If `self.llm_client.is_available` is False or generation fails, falls back immediately to `self._generate_cold_email()` and `self._generate_whatsapp()`.
- Legacy methods `_generate_via_gemini` and `_generate_via_openai` retained as thin wrappers around `LLMClient` for 100% backward compatibility.

---

## 9. Test Coverage & Verification

Created [`tests/test_llm_client.py`](file:///Users/ashik/Bens%20Repository/scrapper/tests/test_llm_client.py) with 17 mocked unit tests:

| Test Case | Focus | Result |
| :--- | :--- | :--- |
| `test_default_config` | Default configuration settings | **PASS** |
| `test_from_env_no_keys_defaults_to_none` | Provider defaults to `"none"` when no keys exist | **PASS** |
| `test_from_env_detects_gemini` | Auto-detection of Gemini from `GEMINI_API_KEY` | **PASS** |
| `test_from_env_detects_openai` | Auto-detection of OpenAI from `OPENAI_API_KEY` | **PASS** |
| `test_from_env_explicit_provider_selection_and_overrides` | Explicit provider and timeout/temperature overrides | **PASS** |
| `test_client_is_available_flag` | Availability flags and `LLMUnavailableError` raising | **PASS** |
| `test_successful_gemini_structured_response` | Gemini mock response parsing into Pydantic model | **PASS** |
| `test_successful_openai_structured_response` | OpenAI mock response parsing into `OutreachStrategy` | **PASS** |
| `test_opportunity_analysis_structured_parsing` | Markdown-wrapped JSON parsing into `OpportunityAnalysis` | **PASS** |
| `test_malformed_json_response_raises_parsing_error` | Observability of non-JSON responses (`LLMResponseParsingError`) | **PASS** |
| `test_schema_validation_failure_raises_validation_error` | Observability of schema violations (`LLMValidationError`) | **PASS** |
| `test_provider_http_error_raises_provider_error` | Observability of upstream 500 error (`LLMProviderError`) | **PASS** |
| `test_provider_timeout_raises_provider_error` | Observability of request timeout (`LLMProviderError`) | **PASS** |
| `test_generate_structured_safe_returns_none_on_error` | Safe fallback without raising on 429 rate limit | **PASS** |
| `test_outreach_generator_falls_back_when_no_llm_available` | OutreachGenerator fallback with disabled LLMClient | **PASS** |
| `test_outreach_generator_uses_structured_ai_when_client_succeeds` | OutreachGenerator utilizing structured AI output | **PASS** |
| `test_outreach_generator_falls_back_when_ai_generation_returns_none` | OutreachGenerator fallback on AI generation failure | **PASS** |

### Complete Core Test Suite Execution
`./.venv/bin/python3 -m unittest tests.test_schemas tests.test_refactored_interfaces tests.test_context_builder tests.test_llm_client`  
**Result:** 46 tests, 0 failures, 0 errors (**OK** in 0.153s).

---

## 10. Architectural Decisions

1. **Pure REST without Heavy Vendor SDKs**:
   Built using Python's standard `requests` and `pydantic` libraries. Avoids heavyweight SDK dependencies (`google-generativeai`, `openai`, `langchain`) while fully supporting Gemini and OpenAI endpoints.
2. **Schema-Enforced Outputs**:
   All LLM responses must conform to Pydantic models. Dict-based outputs are prohibited across the AI boundary.
3. **Decoupled Outreach**:
   `OutreachGenerator` no longer initiates HTTP connections directly; all external provider requests occur through `LLMClient`.
4. **Deterministic Fallback Preservation**:
   Missing API keys or network outages never break pipeline execution.

---

## 11. Explicitly Excluded Components

- No LangChain / LangGraph
- No autonomous agents or agent controller loops
- No RAG / vector databases / pgvector
- No Redis / Celery / background brokers
- No live API calls during unit tests

---

## 12. Next Steps

- **Phase 2C**: Implement `OpportunityReasoner` and `OutreachReasoner` to synthesize commercial diagnoses and consultative messaging from `ProspectContext`.
