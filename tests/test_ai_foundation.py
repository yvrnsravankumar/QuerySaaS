import json

import pytest

from querysaas import (
    AiConfigurationError,
    AiProviderProfile,
    AiSecurityError,
    generate_ai_text,
    normalize_ai_base_url,
    redact_ai_context,
    test_ai_connection as check_ai_connection,
)


class Response:
    def __init__(self, data, status=200, headers=None):
        self._data = data
        self.status_code = status
        self.ok = 200 <= status < 300
        self.headers = headers or {}
    def json(self):
        return self._data


class Session:
    def __init__(self, response):
        self.response = response
        self.calls = []
    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return self.response


def test_ollama_default_profile():
    profile = AiProviderProfile(provider="ollama", model="qwen3:8b")
    assert profile.base_url == "http://127.0.0.1:11434/v1"
    assert profile.safe_dict()["api_key_configured"] is False


def test_remote_http_is_blocked():
    with pytest.raises(AiSecurityError, match="HTTPS"):
        normalize_ai_base_url("http://example.com/v1")


def test_custom_provider_requires_base_url():
    with pytest.raises(AiConfigurationError, match="Base URL"):
        AiProviderProfile(provider="openai_compatible", model="model")


def test_redaction_nested_context():
    value = redact_ai_context({
        "password": "hello",
        "sql": "select 1",
        "note": "Authorization: Bearer abc123",
    })
    assert value["password"] == "[REDACTED]"
    assert "abc123" not in json.dumps(value)
    assert value["sql"] == "select 1"


def test_ollama_generation_uses_configured_base_url():
    session = Session(Response({
        "choices": [{"message": {"content": "SELECT 1 FROM dual"}}],
        "usage": {"total_tokens": 8},
    }))
    profile = AiProviderProfile(
        provider="ollama",
        model="qwen3:8b",
        base_url="http://localhost:11434/v1/",
    )
    result = generate_ai_text(profile, "Generate SQL", session=session)
    assert result.text == "SELECT 1 FROM dual"
    assert session.calls[0][1] == "http://localhost:11434/v1/chat/completions"


def test_gemini_generation():
    session = Session(Response({
        "candidates": [{"content": {"parts": [{"text": "SELECT 1"}]}}],
        "usageMetadata": {"totalTokenCount": 5},
    }))
    profile = AiProviderProfile(
        provider="gemini",
        model="gemini-test",
        api_key="secret",
    )
    result = generate_ai_text(profile, "Generate SQL", session=session)
    assert result.text == "SELECT 1"
    assert session.calls[0][1].endswith(
        "/v1beta/models/gemini-test:generateContent"
    )
    assert session.calls[0][2]["params"] == {"key": "secret"}


def test_connection_uses_models_endpoint():
    session = Session(Response({"data": [{"id": "model-a"}]}))
    profile = AiProviderProfile(provider="openai", model="model-a", api_key="key")
    result = check_ai_connection(profile, session=session)
    assert result["models_found"] == 1
    assert session.calls[0][1] == "https://api.openai.com/v1/models"