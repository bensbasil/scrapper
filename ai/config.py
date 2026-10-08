"""
ai/config.py
------------
Configuration boundary for provider-independent LLM interactions.
Reads provider settings, credentials, timeouts, and models from environment variables.
"""

import os
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class LLMConfig(BaseModel):
    """Configuration for LLM client."""
    model_config = ConfigDict(extra="ignore")

    provider: str = Field(
        default="auto",
        description="Provider name: 'gemini', 'openai', 'auto', or 'none'"
    )
    api_key: Optional[str] = Field(
        default=None,
        description="Provider API key (never hardcoded)"
    )
    model: Optional[str] = Field(
        default=None,
        description="Model identifier (e.g. 'gemini-1.5-flash', 'gpt-4o-mini')"
    )
    temperature: float = Field(
        default=0.2,
        ge=0.0,
        le=2.0,
        description="Sampling temperature"
    )
    timeout: float = Field(
        default=15.0,
        gt=0.0,
        description="Request timeout in seconds"
    )
    max_tokens: Optional[int] = Field(
        default=1024,
        gt=0,
        description="Maximum tokens in generated response"
    )
    base_url: Optional[str] = Field(
        default=None,
        description="Optional custom base URL for OpenAI-compatible endpoints"
    )

    @classmethod
    def from_env(
        cls,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        temperature: Optional[float] = None,
        timeout: Optional[float] = None,
        max_tokens: Optional[int] = None,
        base_url: Optional[str] = None,
    ) -> "LLMConfig":
        """
        Builds LLMConfig from environment variables and optional explicit overrides.
        
        Resolution logic:
        1. If explicit provider is passed, use it.
        2. Else if LLM_PROVIDER is set in env, use it.
        3. Else (auto-detect):
           - If GEMINI_API_KEY is present, choose 'gemini'.
           - Else if OPENAI_API_KEY is present, choose 'openai'.
           - Otherwise, choose 'none'.
        """
        selected_provider = provider or os.getenv("LLM_PROVIDER", "auto")
        selected_provider = selected_provider.lower().strip()

        # Parse numeric overrides or env defaults
        temp_val = temperature if temperature is not None else float(os.getenv("LLM_TEMPERATURE", "0.2"))
        timeout_val = timeout if timeout is not None else float(os.getenv("LLM_TIMEOUT", "15.0"))
        
        max_tok_raw = os.getenv("LLM_MAX_TOKENS", "1024")
        max_tok_val = max_tokens if max_tokens is not None else (int(max_tok_raw) if max_tok_raw else None)

        if selected_provider == "gemini":
            key = api_key or os.getenv("GEMINI_API_KEY")
            mdl = model or os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
            return cls(
                provider="gemini",
                api_key=key,
                model=mdl,
                temperature=temp_val,
                timeout=timeout_val,
                max_tokens=max_tok_val,
                base_url=base_url,
            )

        if selected_provider == "openai":
            key = api_key or os.getenv("OPENAI_API_KEY")
            mdl = model or os.getenv("OPENAI_MODEL", "gpt-4o-mini")
            url = base_url or os.getenv("OPENAI_BASE_URL")
            return cls(
                provider="openai",
                api_key=key,
                model=mdl,
                temperature=temp_val,
                timeout=timeout_val,
                max_tokens=max_tok_val,
                base_url=url,
            )

        if selected_provider == "none":
            return cls(
                provider="none",
                api_key=None,
                model=None,
                temperature=temp_val,
                timeout=timeout_val,
                max_tokens=max_tok_val,
                base_url=None,
            )

        # Auto-detection
        gemini_key = api_key or os.getenv("GEMINI_API_KEY")
        if gemini_key:
            return cls(
                provider="gemini",
                api_key=gemini_key,
                model=model or os.getenv("GEMINI_MODEL", "gemini-1.5-flash"),
                temperature=temp_val,
                timeout=timeout_val,
                max_tokens=max_tok_val,
                base_url=base_url,
            )

        openai_key = api_key or os.getenv("OPENAI_API_KEY")
        if openai_key:
            return cls(
                provider="openai",
                api_key=openai_key,
                model=model or os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                temperature=temp_val,
                timeout=timeout_val,
                max_tokens=max_tok_val,
                base_url=base_url or os.getenv("OPENAI_BASE_URL"),
            )

        # Neither key present
        return cls(
            provider="none",
            api_key=None,
            model=None,
            temperature=temp_val,
            timeout=timeout_val,
            max_tokens=max_tok_val,
            base_url=None,
        )
