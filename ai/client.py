"""
ai/client.py
------------
Provider-independent structured LLM client.
Provides typed, validated generation for Google Gemini and OpenAI-compatible APIs
using Pydantic v2 response models.

Key Guarantees:
- Pure LLM communication and schema validation boundary.
- Zero database, SQL, scraper, or Playwright dependencies.
- Explicit, typed exceptions for failure observability.
- Safe markdown/code-block stripping for resilient JSON decoding.
"""

import json
import logging
from typing import Type, TypeVar, Optional, Any, Dict
import requests
from pydantic import BaseModel

from ai.config import LLMConfig
from ai.exceptions import (
    LLMError,
    LLMUnavailableError,
    LLMProviderError,
    LLMResponseParsingError,
    LLMValidationError,
)

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


def _clean_json_text(text: str) -> str:
    """Strips markdown code fences and extraneous whitespace from LLM output."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()
    return cleaned


class LLMClient:
    """
    Provider-agnostic LLM client for structured output generation.
    Supports Google Gemini and OpenAI-compatible chat endpoints.
    """

    def __init__(self, config: Optional[LLMConfig] = None):
        self.config = config or LLMConfig.from_env()

    @property
    def is_available(self) -> bool:
        """Returns True if a valid provider and API key are configured."""
        if not self.config:
            return False
        if self.config.provider in ("gemini", "openai"):
            return bool(self.config.api_key and self.config.api_key.strip())
        return False

    def generate_structured(
        self,
        prompt: str,
        response_model: Type[T],
        system_prompt: Optional[str] = None,
    ) -> T:
        """
        Executes a prompt against the configured provider and parses the result
        into the requested Pydantic response_model.

        Raises:
            LLMUnavailableError: If provider or API key is not configured.
            LLMProviderError: On upstream HTTP, connection, or timeout failures.
            LLMResponseParsingError: If response text is not valid JSON.
            LLMValidationError: If response JSON violates the response_model schema.
        """
        if not self.is_available:
            raise LLMUnavailableError(
                f"LLM provider '{self.config.provider}' is not available or has no API key."
            )

        if self.config.provider == "gemini":
            raw_text = self._call_gemini(prompt, response_model, system_prompt)
        elif self.config.provider == "openai":
            raw_text = self._call_openai(prompt, response_model, system_prompt)
        else:
            raise LLMUnavailableError(f"Unsupported provider: {self.config.provider}")

        # Parse JSON
        cleaned = _clean_json_text(raw_text)
        try:
            parsed_data = json.loads(cleaned)
        except Exception as e:
            raise LLMResponseParsingError(
                f"Failed to parse LLM response as JSON: {e}",
                raw_text=raw_text,
            ) from e

        # Validate against Pydantic model
        try:
            return response_model.model_validate(parsed_data)
        except Exception as e:
            raise LLMValidationError(
                f"Failed to validate LLM response against {response_model.__name__}: {e}",
                raw_data=parsed_data,
            ) from e

    def generate_structured_safe(
        self,
        prompt: str,
        response_model: Type[T],
        system_prompt: Optional[str] = None,
    ) -> Optional[T]:
        """
        Safely attempts structured generation. Catches LLMError and returns None
        so the caller can fall back to deterministic templates without raising.
        """
        try:
            return self.generate_structured(
                prompt=prompt,
                response_model=response_model,
                system_prompt=system_prompt,
            )
        except LLMError as e:
            logger.warning(f"Structured generation safe-fallback triggered: {e}")
            return None

    # -------------------------------------------------------------------------
    # Provider Implementations
    # -------------------------------------------------------------------------

    def _call_gemini(
        self,
        prompt: str,
        response_model: Type[T],
        system_prompt: Optional[str] = None,
    ) -> str:
        """Executes content generation via Google Gemini API."""
        model = self.config.model or "gemini-1.5-flash"
        api_key = self.config.api_key
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        headers = {"Content-Type": "application/json"}

        # Inject schema instruction into prompt
        schema_json = json.dumps(response_model.model_json_schema())
        instruction = (
            f"\n\nStrict Output Requirement:\n"
            f"You MUST respond ONLY with a valid JSON object matching this schema:\n"
            f"{schema_json}"
        )
        if system_prompt:
            full_text = f"{system_prompt}\n\n{prompt}{instruction}"
        else:
            full_text = f"{prompt}{instruction}"

        generation_config: Dict[str, Any] = {
            "responseMimeType": "application/json",
            "temperature": self.config.temperature,
        }
        if self.config.max_tokens:
            generation_config["maxOutputTokens"] = self.config.max_tokens

        payload = {
            "contents": [
                {
                    "parts": [{"text": full_text}]
                }
            ],
            "generationConfig": generation_config,
        }

        try:
            response = requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=self.config.timeout,
            )
        except requests.exceptions.Timeout as e:
            raise LLMProviderError(f"Gemini API request timed out after {self.config.timeout}s: {e}") from e
        except requests.exceptions.RequestException as e:
            raise LLMProviderError(f"Gemini network connection error: {e}") from e

        if response.status_code != 200:
            raise LLMProviderError(
                f"Gemini API returned HTTP {response.status_code}: {response.text}",
                status_code=response.status_code,
                response_body=response.text,
            )

        try:
            res_data = response.json()
            candidates = res_data.get("candidates", [])
            if not candidates:
                raise LLMResponseParsingError("Gemini response contained no candidates", raw_text=response.text)
            parts = candidates[0].get("content", {}).get("parts", [])
            if not parts:
                raise LLMResponseParsingError("Gemini candidate contained no parts", raw_text=response.text)
            return parts[0].get("text", "")
        except (KeyError, IndexError, ValueError) as e:
            raise LLMResponseParsingError(f"Failed to extract text from Gemini response: {e}", raw_text=response.text) from e

    def _call_openai(
        self,
        prompt: str,
        response_model: Type[T],
        system_prompt: Optional[str] = None,
    ) -> str:
        """Executes chat completion via OpenAI-compatible API."""
        base_url = (self.config.base_url or "https://api.openai.com/v1").rstrip("/")
        url = f"{base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }
        model = self.config.model or "gpt-4o-mini"

        schema_json = json.dumps(response_model.model_json_schema())
        sys_message = (
            system_prompt or "You are an expert sales and business intelligence AI."
        ) + f"\n\nStrict Output Requirement:\nYou MUST output valid JSON strictly adhering to this schema:\n{schema_json}"

        payload: Dict[str, Any] = {
            "model": model,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": sys_message},
                {"role": "user", "content": prompt},
            ],
            "temperature": self.config.temperature,
        }
        if self.config.max_tokens:
            payload["max_tokens"] = self.config.max_tokens

        try:
            response = requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=self.config.timeout,
            )
        except requests.exceptions.Timeout as e:
            raise LLMProviderError(f"OpenAI API request timed out after {self.config.timeout}s: {e}") from e
        except requests.exceptions.RequestException as e:
            raise LLMProviderError(f"OpenAI network connection error: {e}") from e

        if response.status_code != 200:
            raise LLMProviderError(
                f"OpenAI API returned HTTP {response.status_code}: {response.text}",
                status_code=response.status_code,
                response_body=response.text,
            )

        try:
            res_data = response.json()
            choices = res_data.get("choices", [])
            if not choices:
                raise LLMResponseParsingError("OpenAI response contained no choices", raw_text=response.text)
            return choices[0].get("message", {}).get("content", "")
        except (KeyError, IndexError, ValueError) as e:
            raise LLMResponseParsingError(f"Failed to extract content from OpenAI response: {e}", raw_text=response.text) from e
