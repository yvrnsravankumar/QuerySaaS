"""Provider-neutral AI foundation for QuerySaaS.

This module intentionally keeps Oracle credentials and AI credentials separate.
It provides validated provider profiles, configurable base URLs, context
redaction, connection tests, and synchronous text generation through requests.
"""
from __future__ import annotations

import ipaddress
import json
import re
import socket
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence
from urllib.parse import urljoin, urlparse

import requests


DEFAULT_AI_BASE_URLS = {
    "openai": "https://api.openai.com/v1",
    "openai_compatible": None,
    "ollama": "http://127.0.0.1:11434/v1",
    "gemini": "https://generativelanguage.googleapis.com",
}
SUPPORTED_AI_PROVIDERS = tuple(DEFAULT_AI_BASE_URLS)

_SECRET_PATTERNS = (
    re.compile(r"(?i)(authorization\s*:\s*)(?:bearer|basic)\s+\S+"),
    re.compile(r"(?i)\b(api[_-]?key|access[_-]?token|password|secret)\b\s*[:=]\s*([^\s,;]+)"),
    re.compile(r"(?i)([?&](?:key|api_key|access_token)=)[^&\s]+"),
)


class AiError(RuntimeError):
    """Base AI integration error."""


class AiConfigurationError(AiError):
    """Raised for invalid provider settings."""


class AiSecurityError(AiConfigurationError):
    """Raised when an endpoint violates network security policy."""


class AiAuthenticationError(AiError):
    """Raised when a provider rejects authentication."""


class AiProviderError(AiError):
    """Raised when a provider request or response fails."""


@dataclass(frozen=True)
class AiProviderProfile:
    provider: str
    model: str
    base_url: str | None = None
    api_key: str | None = None
    timeout: int = 120
    allow_private_network: bool = False
    headers: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self):
        provider = str(self.provider or "").strip().lower()
        if provider not in SUPPORTED_AI_PROVIDERS:
            raise AiConfigurationError(
                "Unsupported AI provider. Supported values: "
                + ", ".join(SUPPORTED_AI_PROVIDERS)
            )
        model = str(self.model or "").strip()
        if not model:
            raise AiConfigurationError("AI model cannot be empty.")
        if not isinstance(self.timeout, int) or self.timeout <= 0:
            raise AiConfigurationError("AI timeout must be a positive integer.")
        if not isinstance(self.allow_private_network, bool):
            raise AiConfigurationError("allow_private_network must be True or False.")
        object.__setattr__(self, "provider", provider)
        object.__setattr__(self, "model", model)
        object.__setattr__(self, "base_url", normalize_ai_base_url(
            self.base_url or DEFAULT_AI_BASE_URLS[provider],
            allow_private_network=self.allow_private_network,
        ))
        object.__setattr__(self, "headers", dict(self.headers or {}))

    def safe_dict(self):
        return {
            "provider": self.provider,
            "model": self.model,
            "base_url": self.base_url,
            "api_key_configured": bool(self.api_key),
            "timeout": self.timeout,
            "allow_private_network": self.allow_private_network,
            "header_names": sorted(self.headers),
        }


@dataclass(frozen=True)
class AiResponse:
    provider: str
    model: str
    text: str
    request_id: str | None = None
    usage: Mapping[str, Any] | None = None
    raw: Mapping[str, Any] | None = None

    def to_dict(self, include_raw=False):
        result = {
            "provider": self.provider,
            "model": self.model,
            "text": self.text,
            "request_id": self.request_id,
            "usage": dict(self.usage or {}),
        }
        if include_raw:
            result["raw"] = dict(self.raw or {})
        return result


def _is_loopback(hostname):
    if hostname in {"localhost", "localhost.localdomain"}:
        return True
    try:
        return ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        return False


def _validate_host(hostname, allow_private_network):
    if not hostname:
        raise AiSecurityError("AI provider Base URL must include a hostname.")
    if hostname.casefold() in {"metadata.google.internal"}:
        raise AiSecurityError("Cloud metadata endpoints are not allowed.")
    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(hostname, None)}
    except socket.gaierror:
        addresses = set()
    for address in addresses:
        ip = ipaddress.ip_address(address)
        if ip.is_loopback:
            continue
        if ip.is_link_local or ip.is_multicast or ip.is_unspecified or ip.is_reserved:
            raise AiSecurityError(f"Unsafe AI provider address: {address}")
        if ip.is_private and not allow_private_network:
            raise AiSecurityError(
                "Private-network AI endpoints require allow_private_network=True."
            )


def normalize_ai_base_url(value, *, allow_private_network=False):
    if not value or not str(value).strip():
        raise AiConfigurationError(
            "AI provider Base URL is required for this provider."
        )
    parsed = urlparse(str(value).strip())
    if parsed.scheme not in {"http", "https"}:
        raise AiSecurityError("AI provider Base URL must use http or https.")
    if parsed.username or parsed.password:
        raise AiSecurityError("AI provider Base URL cannot contain credentials.")
    hostname = (parsed.hostname or "").casefold()
    loopback = _is_loopback(hostname)
    if parsed.scheme != "https" and not loopback:
        raise AiSecurityError("Remote AI provider Base URLs must use HTTPS.")
    _validate_host(hostname, allow_private_network)
    path = parsed.path.rstrip("/")
    port = f":{parsed.port}" if parsed.port else ""
    return f"{parsed.scheme}://{parsed.hostname}{port}{path}"


def redact_ai_context(value):
    """Redact common credentials from nested text, mappings, and sequences."""
    if isinstance(value, Mapping):
        redacted = {}
        for key, item in value.items():
            if re.search(r"(?i)(password|secret|token|authorization|api[_-]?key)", str(key)):
                redacted[key] = "[REDACTED]"
            else:
                redacted[key] = redact_ai_context(item)
        return redacted
    if isinstance(value, (list, tuple)):
        return [redact_ai_context(item) for item in value]
    if not isinstance(value, str):
        return value
    text = value
    for pattern in _SECRET_PATTERNS:
        if pattern.groups >= 2:
            text = pattern.sub(lambda match: match.group(1) + "=[REDACTED]", text)
        else:
            text = pattern.sub(lambda match: match.group(1) + "[REDACTED]", text)
    return text


def _join(base_url, path):
    return urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))


def _headers(profile):
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    headers.update(profile.headers)
    if profile.api_key and profile.provider != "gemini":
        headers.setdefault("Authorization", f"Bearer {profile.api_key}")
    return headers


def _send(profile, method, url, *, json_body=None, params=None, session=None):
    sender = session or requests
    try:
        response = sender.request(
            method,
            url,
            headers=_headers(profile),
            json=json_body,
            params=params,
            timeout=profile.timeout,
            verify=True,
            allow_redirects=False,
        )
    except requests.Timeout as exc:
        raise AiProviderError(f"AI provider request timed out after {profile.timeout} seconds.") from exc
    except requests.ConnectionError as exc:
        raise AiProviderError("AI provider connection failed.") from exc
    if response.status_code in {301, 302, 303, 307, 308}:
        raise AiSecurityError("AI provider redirects are not followed automatically.")
    if response.status_code in {401, 403}:
        raise AiAuthenticationError(
            f"AI provider authentication failed (HTTP {response.status_code})."
        )
    try:
        data = response.json()
    except ValueError as exc:
        raise AiProviderError(
            f"AI provider returned non-JSON HTTP {response.status_code}."
        ) from exc
    if not response.ok:
        safe = redact_ai_context(json.dumps(data, ensure_ascii=False))[:1000]
        raise AiProviderError(
            f"AI provider request failed (HTTP {response.status_code}): {safe}"
        )
    return response, data


def test_ai_connection(profile, *, session=None):
    if profile.provider == "gemini":
        url = _join(profile.base_url, "/v1beta/models")
        params = {"key": profile.api_key} if profile.api_key else None
    else:
        url = _join(profile.base_url, "/models")
        params = None
    response, data = _send(profile, "GET", url, params=params, session=session)
    models = data.get("data") or data.get("models") or []
    return {
        "success": True,
        "provider": profile.provider,
        "base_url": profile.base_url,
        "reachable": True,
        "authenticated": True,
        "models_found": len(models),
        "request_id": response.headers.get("x-request-id"),
    }


def generate_ai_text(profile, prompt, *, system_prompt=None, context=None, temperature=None, session=None):
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("AI prompt cannot be empty.")
    safe_context = redact_ai_context(context) if context is not None else None
    user_text = prompt.strip()
    if safe_context is not None:
        user_text += "\n\nContext:\n" + json.dumps(safe_context, ensure_ascii=False, indent=2)

    if profile.provider == "gemini":
        if not profile.api_key:
            raise AiConfigurationError("Gemini requires an API key.")
        url = _join(
            profile.base_url,
            f"/v1beta/models/{profile.model}:generateContent",
        )
        parts = [{"text": user_text}]
        body = {"contents": [{"role": "user", "parts": parts}]}
        if system_prompt:
            body["systemInstruction"] = {"parts": [{"text": system_prompt}]}
        if temperature is not None:
            body["generationConfig"] = {"temperature": temperature}
        response, data = _send(
            profile, "POST", url, json_body=body,
            params={"key": profile.api_key}, session=session,
        )
        candidates = data.get("candidates") or []
        try:
            text = "".join(
                part.get("text", "")
                for part in candidates[0]["content"]["parts"]
            ).strip()
        except (IndexError, KeyError, TypeError) as exc:
            raise AiProviderError("Gemini response contained no text candidate.") from exc
        usage = data.get("usageMetadata")
    else:
        url = _join(profile.base_url, "/chat/completions")
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_text})
        body = {"model": profile.model, "messages": messages, "stream": False}
        if temperature is not None:
            body["temperature"] = temperature
        response, data = _send(profile, "POST", url, json_body=body, session=session)
        try:
            text = data["choices"][0]["message"]["content"].strip()
        except (IndexError, KeyError, TypeError, AttributeError) as exc:
            raise AiProviderError("AI provider response contained no assistant text.") from exc
        usage = data.get("usage")

    return AiResponse(
        provider=profile.provider,
        model=profile.model,
        text=text,
        request_id=response.headers.get("x-request-id"),
        usage=usage,
        raw=data,
    )