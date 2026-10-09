"""
tests/test_gemini_key_handling.py
---------------------------------
Comprehensive regression tests for Phase 5B P0-3: Gemini API Key Handling.
Verifies:
1. Gemini API key is passed via the 'x-goog-api-key' HTTP header, NOT in URL query parameters.
2. Request URLs never contain the secret key.
3. Timeout exceptions do not leak the configured secret.
4. HTTP error responses and provider exceptions do not leak the configured secret.
5. Malformed candidate responses do not leak the secret in error messages or diagnostic text.
6. Fallback and provider-independent client behavior remain functional.
"""

import json
import pytest
from unittest.mock import patch, MagicMock

import requests
from ai.config import LLMConfig
from ai.client import LLMClient
from ai.exceptions import LLMProviderError, LLMResponseParsingError
from schemas.ai import OutreachDraftResponse


def test_gemini_api_key_sent_via_header_not_query_param():
    """Verify Gemini API key is sent via x-goog-api-key header and never in URL query."""
    secret_key = "AIzaSySecretGeminiKey123456789"
    client = LLMClient(config=LLMConfig(provider="gemini", api_key=secret_key, model="gemini-1.5-flash"))

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = json.dumps({
        "candidates": [{
            "content": {"parts": [{"text": json.dumps({"cold_email_draft": "Hello", "whatsapp_draft": "Hi"})}]}
        }]
    })
    mock_resp.json.return_value = json.loads(mock_resp.text)

    with patch("requests.post", return_value=mock_resp) as mock_post:
        res = client.generate_structured(prompt="test", response_model=OutreachDraftResponse)
        assert res.cold_email_draft == "Hello"

        mock_post.assert_called_once()
        call_args, call_kwargs = mock_post.call_args

        # Verify URL has NO key query parameter
        called_url = call_args[0] if call_args else call_kwargs.get("url")
        assert "key=" not in called_url
        assert secret_key not in called_url
        assert called_url == "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"

        # Verify header contains x-goog-api-key
        headers = call_kwargs.get("headers", {})
        assert headers.get("x-goog-api-key") == secret_key


def test_gemini_timeout_sanitizes_secret():
    """Verify timeout exception messages scrub the API key."""
    secret_key = "super-secret-gemini-token-999"
    client = LLMClient(config=LLMConfig(provider="gemini", api_key=secret_key, timeout=5.0))

    with patch("requests.post", side_effect=requests.exceptions.Timeout(f"Timeout on key={secret_key}")):
        with pytest.raises(LLMProviderError) as exc:
            client.generate_structured(prompt="test", response_model=OutreachDraftResponse)

        err_msg = str(exc.value)
        assert secret_key not in err_msg
        assert "[REDACTED]" in err_msg


def test_gemini_network_error_sanitizes_secret():
    """Verify connection error messages scrub the API key."""
    secret_key = "super-secret-gemini-token-888"
    client = LLMClient(config=LLMConfig(provider="gemini", api_key=secret_key))

    with patch("requests.post", side_effect=requests.exceptions.ConnectionError(f"Connection refused to {secret_key}")):
        with pytest.raises(LLMProviderError) as exc:
            client.generate_structured(prompt="test", response_model=OutreachDraftResponse)

        err_msg = str(exc.value)
        assert secret_key not in err_msg
        assert "[REDACTED]" in err_msg


def test_gemini_http_error_response_sanitizes_secret():
    """Verify non-200 HTTP response bodies scrub the API key."""
    secret_key = "super-secret-gemini-token-777"
    client = LLMClient(config=LLMConfig(provider="gemini", api_key=secret_key))

    mock_resp = MagicMock()
    mock_resp.status_code = 403
    mock_resp.text = f'{{"error": {{"message": "API key {secret_key} is invalid", "code": 403}}}}'

    with patch("requests.post", return_value=mock_resp):
        with pytest.raises(LLMProviderError) as exc:
            client.generate_structured(prompt="test", response_model=OutreachDraftResponse)

        err_msg = str(exc.value)
        assert secret_key not in err_msg
        assert "[REDACTED]" in err_msg


def test_gemini_parsing_error_sanitizes_secret():
    """Verify parsing errors with malformed body scrub the API key."""
    secret_key = "super-secret-gemini-token-666"
    client = LLMClient(config=LLMConfig(provider="gemini", api_key=secret_key))

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = f'{{"candidates": [], "debug": "{secret_key}"}}'
    mock_resp.json.return_value = {"candidates": [], "debug": secret_key}

    with patch("requests.post", return_value=mock_resp):
        with pytest.raises(LLMResponseParsingError) as exc:
            client.generate_structured(prompt="test", response_model=OutreachDraftResponse)

        assert secret_key not in str(exc.value)
        assert secret_key not in (exc.value.raw_text or "")
        assert "[REDACTED]" in (exc.value.raw_text or "")


def test_openai_sanitization_also_active():
    """Verify OpenAI requests also sanitize secrets on error."""
    secret_key = "sk-openai-super-secret-555"
    client = LLMClient(config=LLMConfig(provider="openai", api_key=secret_key))

    with patch("requests.post", side_effect=requests.exceptions.Timeout(f"Timeout on key={secret_key}")):
        with pytest.raises(LLMProviderError) as exc:
            client.generate_structured(prompt="test", response_model=OutreachDraftResponse)

        assert secret_key not in str(exc.value)
        assert "[REDACTED]" in str(exc.value)
