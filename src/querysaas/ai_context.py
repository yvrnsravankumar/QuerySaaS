"""Named AI profiles, credential references, schema context, and previews."""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

from .ai import AiConfigurationError, AiProviderProfile, redact_ai_context
from .ai_sql import AiSqlSafetyError, build_oracle_sql_prompt, extract_sql


_IDENTIFIER = re.compile(r"^[A-Za-z][A-Za-z0-9_$#]*$")
_TABLE_REFERENCE = re.compile(
    r"(?i)\b(?:FROM|JOIN)\s+((?:[A-Za-z][A-Za-z0-9_$#]*\.)?[A-Za-z][A-Za-z0-9_$#]*)"
)


class AiProfileError(AiConfigurationError):
    """Raised when a stored profile is invalid or unavailable."""


class AiCredentialError(AiConfigurationError):
    """Raised when a credential reference cannot be resolved."""


class AiContextError(ValueError):
    """Raised when schema context is invalid or exceeds policy."""


@dataclass(frozen=True)
class AiCredentialReference:
    source: str = "environment"
    name: str | None = None

    def __post_init__(self):
        source = str(self.source or "").strip().lower()
        if source not in {"environment", "none"}:
            raise AiCredentialError(
                "Unsupported credential source. Supported values: environment, none."
            )
        name = str(self.name or "").strip() or None
        if source == "environment" and not name:
            raise AiCredentialError("Environment credential reference requires a variable name.")
        object.__setattr__(self, "source", source)
        object.__setattr__(self, "name", name)

    def resolve(self, *, environ=None):
        if self.source == "none":
            return None
        values = os.environ if environ is None else environ
        value = values.get(self.name)
        if not value:
            raise AiCredentialError(
                f"AI credential environment variable is not set: {self.name}"
            )
        return value

    def to_dict(self):
        return {"source": self.source, "name": self.name}


@dataclass(frozen=True)
class AiNamedProfile:
    name: str
    provider: str
    model: str
    base_url: str | None = None
    timeout: int = 120
    allow_private_network: bool = False
    credential: AiCredentialReference | None = None
    headers: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self):
        name = str(self.name or "").strip()
        if not name or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", name):
            raise AiProfileError(
                "Profile name must use 1-64 letters, numbers, dots, underscores, or hyphens."
            )
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "headers", dict(self.headers or {}))

    def resolve(self, *, environ=None):
        api_key = self.credential.resolve(environ=environ) if self.credential else None
        return AiProviderProfile(
            provider=self.provider,
            model=self.model,
            base_url=self.base_url,
            api_key=api_key,
            timeout=self.timeout,
            allow_private_network=self.allow_private_network,
            headers=self.headers,
        )

    def to_dict(self):
        return {
            "name": self.name,
            "provider": self.provider,
            "model": self.model,
            "base_url": self.base_url,
            "timeout": self.timeout,
            "allow_private_network": self.allow_private_network,
            "credential": self.credential.to_dict() if self.credential else None,
            "headers": dict(self.headers),
        }

    @classmethod
    def from_dict(cls, value):
        if not isinstance(value, Mapping):
            raise AiProfileError("AI profile must be a JSON object.")
        credential = value.get("credential")
        if credential is not None:
            credential = AiCredentialReference(**credential)
        return cls(
            name=value.get("name"),
            provider=value.get("provider"),
            model=value.get("model"),
            base_url=value.get("base_url"),
            timeout=value.get("timeout", 120),
            allow_private_network=value.get("allow_private_network", False),
            credential=credential,
            headers=value.get("headers") or {},
        )


class AiProfileStore:
    """JSON profile store that never serializes resolved credential values."""

    def __init__(self, path):
        self.path = Path(path).expanduser().resolve()

    def load_all(self):
        if not self.path.exists():
            return {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise AiProfileError(f"Unable to read AI profile store: {self.path}") from exc
        if not isinstance(data, Mapping) or data.get("version") != 1:
            raise AiProfileError("AI profile store must use version 1.")
        profiles = {}
        for item in data.get("profiles") or []:
            profile = AiNamedProfile.from_dict(item)
            if profile.name.casefold() in profiles:
                raise AiProfileError(f"Duplicate AI profile name: {profile.name}")
            profiles[profile.name.casefold()] = profile
        return profiles

    def list(self):
        return sorted(self.load_all().values(), key=lambda item: item.name.casefold())

    def get(self, name):
        key = str(name or "").strip().casefold()
        profile = self.load_all().get(key)
        if profile is None:
            raise AiProfileError(f"AI profile was not found: {name}")
        return profile

    def save(self, profile, *, overwrite=False):
        if not isinstance(profile, AiNamedProfile):
            raise TypeError("profile must be an AiNamedProfile.")
        if not isinstance(overwrite, bool):
            raise ValueError("overwrite must be True or False.")
        profiles = self.load_all()
        key = profile.name.casefold()
        if key in profiles and not overwrite:
            raise AiProfileError(f"AI profile already exists: {profile.name}")
        profiles[key] = profile
        payload = {
            "version": 1,
            "profiles": [item.to_dict() for item in sorted(
                profiles.values(), key=lambda value: value.name.casefold()
            )],
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary.replace(self.path)
        return profile

    def delete(self, name, *, missing_ok=False):
        if not isinstance(missing_ok, bool):
            raise ValueError("missing_ok must be True or False.")
        key = str(name or "").strip().casefold()
        profiles = self.load_all()
        if key not in profiles:
            if missing_ok:
                return False
            raise AiProfileError(f"AI profile was not found: {name}")
        profiles.pop(key)
        payload = {
            "version": 1,
            "profiles": [item.to_dict() for item in sorted(
                profiles.values(), key=lambda value: value.name.casefold()
            )],
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return True


@dataclass(frozen=True)
class OracleSchemaContext:
    tables: Mapping[str, Sequence[str]]
    excluded_columns: Sequence[str] = field(default_factory=tuple)
    max_tables: int = 100
    max_columns: int = 2000

    def __post_init__(self):
        if not isinstance(self.tables, Mapping) or not self.tables:
            raise AiContextError("Schema context requires at least one table.")
        if not isinstance(self.max_tables, int) or self.max_tables <= 0:
            raise AiContextError("max_tables must be a positive integer.")
        if not isinstance(self.max_columns, int) or self.max_columns <= 0:
            raise AiContextError("max_columns must be a positive integer.")
        excluded = {self._identifier(value) for value in self.excluded_columns}
        normalized = {}
        for raw_table, raw_columns in self.tables.items():
            table = self._qualified_identifier(raw_table)
            if isinstance(raw_columns, str) or not isinstance(raw_columns, Sequence):
                raise AiContextError(f"Columns for {table} must be a sequence.")
            columns = []
            for raw_column in raw_columns:
                column = self._identifier(raw_column)
                if column not in excluded and column not in columns:
                    columns.append(column)
            normalized[table] = tuple(columns)
        normalized = dict(sorted(normalized.items()))
        if len(normalized) > self.max_tables:
            raise AiContextError("Schema context exceeds the table limit.")
        if sum(len(value) for value in normalized.values()) > self.max_columns:
            raise AiContextError("Schema context exceeds the column limit.")
        object.__setattr__(self, "tables", normalized)
        object.__setattr__(self, "excluded_columns", tuple(sorted(excluded)))

    @staticmethod
    def _identifier(value):
        name = str(value or "").strip().upper()
        if not _IDENTIFIER.fullmatch(name):
            raise AiContextError(f"Invalid Oracle identifier: {value}")
        return name

    @classmethod
    def _qualified_identifier(cls, value):
        parts = str(value or "").strip().split(".")
        if len(parts) not in {1, 2}:
            raise AiContextError(f"Invalid Oracle table identifier: {value}")
        return ".".join(cls._identifier(part) for part in parts)

    def to_dict(self):
        return {
            "tables": {key: list(value) for key, value in self.tables.items()},
            "excluded_columns": list(self.excluded_columns),
            "table_count": len(self.tables),
            "column_count": sum(len(value) for value in self.tables.values()),
        }

    def to_prompt_text(self):
        lines = []
        for table, columns in self.tables.items():
            lines.append(f"{table}: {', '.join(columns) if columns else '[columns not supplied]'}")
        return "\n".join(lines)

    def allows_table(self, table):
        normalized = self._qualified_identifier(table)
        if normalized in self.tables:
            return True
        unqualified = normalized.split(".")[-1]
        matches = [key for key in self.tables if key.split(".")[-1] == unqualified]
        return len(matches) == 1


@dataclass(frozen=True)
class AiRequestPreview:
    provider: str
    model: str
    base_url: str
    prompt: str
    schema_context: Mapping[str, Any] | None
    read_only: bool
    credential_configured: bool
    estimated_characters: int
    redactions_applied: bool

    def to_dict(self):
        return {
            "provider": self.provider,
            "model": self.model,
            "base_url": self.base_url,
            "prompt": self.prompt,
            "schema_context": self.schema_context,
            "read_only": self.read_only,
            "credential_configured": self.credential_configured,
            "estimated_characters": self.estimated_characters,
            "redactions_applied": self.redactions_applied,
        }


def extract_referenced_tables(sql):
    sql = extract_sql(sql)
    masked = re.sub(r"(?s)/\*.*?\*/|--[^\r\n]*|'(?:''|[^'])*'", " ", sql)
    tables = []
    for match in _TABLE_REFERENCE.finditer(masked):
        name = match.group(1).upper()
        if name not in tables:
            tables.append(name)
    return tuple(tables)


def validate_sql_schema_context(sql, schema_context, *, strict=True):
    if not isinstance(schema_context, OracleSchemaContext):
        raise TypeError("schema_context must be an OracleSchemaContext.")
    if not isinstance(strict, bool):
        raise ValueError("strict must be True or False.")
    referenced = extract_referenced_tables(sql)
    unknown = tuple(table for table in referenced if not schema_context.allows_table(table))
    result = {
        "referenced_tables": referenced,
        "unknown_tables": unknown,
        "valid": not unknown,
    }
    if strict and unknown:
        raise AiSqlSafetyError(
            "Generated SQL references tables outside the approved schema context: "
            + ", ".join(unknown)
        )
    return result


def preview_ai_sql_request(profile, request, *, schema_context=None, read_only=True):
    if isinstance(profile, AiNamedProfile):
        provider_profile = profile.resolve()
    elif isinstance(profile, AiProviderProfile):
        provider_profile = profile
    else:
        raise TypeError("profile must be an AiProviderProfile or AiNamedProfile.")
    context_text = None
    context_dict = None
    if schema_context is not None:
        if not isinstance(schema_context, OracleSchemaContext):
            raise TypeError("schema_context must be an OracleSchemaContext.")
        context_text = schema_context.to_prompt_text()
        context_dict = schema_context.to_dict()
    original_prompt = build_oracle_sql_prompt(
        request, schema_context=context_text, read_only=read_only
    )
    safe_prompt = redact_ai_context(original_prompt)
    return AiRequestPreview(
        provider=provider_profile.provider,
        model=provider_profile.model,
        base_url=provider_profile.base_url,
        prompt=safe_prompt,
        schema_context=context_dict,
        read_only=read_only,
        credential_configured=bool(provider_profile.api_key),
        estimated_characters=len(safe_prompt),
        redactions_applied=safe_prompt != original_prompt,
    )