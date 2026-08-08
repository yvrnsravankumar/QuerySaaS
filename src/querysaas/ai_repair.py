"""Safe Oracle SQL explanation, error parsing, comparison, and AI repair."""
from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from typing import Any, Mapping

from .ai import AiProviderProfile, AiResponse, generate_ai_text, redact_ai_context
from .ai_context import (
    AiNamedProfile,
    OracleSchemaContext,
    validate_sql_schema_context,
)
from .ai_sql import (
    AiSqlClassification,
    AiSqlResult,
    AiSqlSafetyError,
    classify_sql,
    enforce_read_only_sql,
    extract_sql,
)


_ORACLE_ERROR = re.compile(
    r"(?i)\b(ORA-\d{5})\s*:\s*([^\r\n]+)"
)


class AiSqlRepairError(RuntimeError):
    """Raised when SQL explanation or repair cannot be completed safely."""


@dataclass(frozen=True)
class OracleErrorContext:
    code: str | None
    message: str
    raw_text: str

    def to_dict(self):
        return {
            "code": self.code,
            "message": self.message,
            "raw_text": self.raw_text,
        }


@dataclass(frozen=True)
class AiSqlExplanation:
    sql: str
    explanation: str
    classification: AiSqlClassification
    provider: str
    model: str
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self):
        return {
            "sql": self.sql,
            "explanation": self.explanation,
            "classification": self.classification.to_dict(),
            "provider": self.provider,
            "model": self.model,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class AiSqlRepairResult:
    original_sql: str
    repaired_sql: str
    oracle_error: OracleErrorContext
    explanation: str | None
    classification: AiSqlClassification
    changed: bool
    unified_diff: str
    schema_validation: Mapping[str, Any] | None
    provider: str
    model: str
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self):
        return {
            "original_sql": self.original_sql,
            "repaired_sql": self.repaired_sql,
            "oracle_error": self.oracle_error.to_dict(),
            "explanation": self.explanation,
            "classification": self.classification.to_dict(),
            "changed": self.changed,
            "unified_diff": self.unified_diff,
            "schema_validation": (
                dict(self.schema_validation)
                if self.schema_validation is not None
                else None
            ),
            "provider": self.provider,
            "model": self.model,
            "metadata": dict(self.metadata),
        }


def parse_oracle_error(value):
    """Parse and redact an Oracle error without exposing credentials."""
    if isinstance(value, BaseException):
        value = str(value)
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Oracle error text cannot be empty.")
    safe = str(redact_ai_context(value.strip()))
    match = _ORACLE_ERROR.search(safe)
    if match:
        code = match.group(1).upper()
        message = match.group(2).strip()
    else:
        code = None
        message = safe.splitlines()[0].strip()
    return OracleErrorContext(code=code, message=message, raw_text=safe)


def compare_sql(original_sql, repaired_sql):
    """Return deterministic before-and-after comparison metadata."""
    original = enforce_read_only_sql(original_sql)
    repaired = enforce_read_only_sql(repaired_sql)
    diff = "\n".join(difflib.unified_diff(
        original.splitlines(),
        repaired.splitlines(),
        fromfile="original.sql",
        tofile="repaired.sql",
        lineterm="",
    ))
    return {
        "changed": original.strip() != repaired.strip(),
        "unified_diff": diff,
        "original_length": len(original),
        "repaired_length": len(repaired),
    }


def _resolve_profile(profile):
    if isinstance(profile, AiProviderProfile):
        return profile
    if isinstance(profile, AiNamedProfile):
        return profile.resolve()
    raise TypeError("profile must be an AiProviderProfile or AiNamedProfile.")


def _context_text(schema_context):
    if schema_context is None:
        return None
    if not isinstance(schema_context, OracleSchemaContext):
        raise TypeError("schema_context must be an OracleSchemaContext.")
    return schema_context.to_prompt_text()


def build_sql_explanation_prompt(sql, *, schema_context=None):
    sql = enforce_read_only_sql(sql)
    context = _context_text(schema_context)
    prompt = (
        "Explain this read-only Oracle SQL query. Cover its purpose, source "
        "tables, joins, filters, aggregations, ordering, assumptions, and likely "
        "performance risks. Do not execute the SQL and do not propose write "
        "operations. Return a concise technical explanation.\n\nSQL:\n```sql\n"
        + sql
        + "\n```"
    )
    if context:
        prompt += "\n\nApproved schema context:\n" + context
    return prompt


def explain_oracle_sql(profile, sql, *, schema_context=None, session=None):
    """Generate a safe technical explanation for read-only Oracle SQL."""
    resolved = _resolve_profile(profile)
    safe_sql = enforce_read_only_sql(sql)
    if schema_context is not None:
        validate_sql_schema_context(safe_sql, schema_context, strict=True)
    prompt = build_sql_explanation_prompt(
        safe_sql,
        schema_context=schema_context,
    )
    response: AiResponse = generate_ai_text(
        resolved,
        prompt,
        temperature=0,
        session=session,
    )
    explanation = response.text.strip()
    if not explanation:
        raise AiSqlRepairError("AI provider returned an empty SQL explanation.")
    return AiSqlExplanation(
        sql=safe_sql,
        explanation=explanation,
        classification=classify_sql(safe_sql),
        provider=response.provider,
        model=response.model,
        metadata={
            "request_id": response.request_id,
            "usage": dict(response.usage or {}),
        },
    )


def build_sql_repair_prompt(
    original_sql,
    oracle_error,
    *,
    schema_context=None,
):
    sql = enforce_read_only_sql(original_sql)
    error = parse_oracle_error(oracle_error)
    context = _context_text(schema_context)
    prompt = (
        "Repair the following read-only Oracle SQL query using only the supplied "
        "Oracle error and approved schema context. Preserve the original intent. "
        "Return exactly one read-only SELECT or WITH statement in a single ```sql "
        "block, followed by a brief explanation. Do not use DML, DDL, PL/SQL, "
        "FOR UPDATE, dynamic SQL, scheduler, network, or file packages. Do not "
        "invent tables or columns.\n\nOriginal SQL:\n```sql\n"
        + sql
        + "\n```\n\nOracle error:\n"
        + (f"{error.code}: " if error.code else "")
        + error.message
    )
    if context:
        prompt += "\n\nApproved schema context:\n" + context
    return prompt


def repair_oracle_sql(
    profile,
    original_sql,
    oracle_error,
    *,
    schema_context=None,
    require_change=True,
    session=None,
):
    """Repair SQL without execution and validate the repaired query."""
    if not isinstance(require_change, bool):
        raise ValueError("require_change must be True or False.")
    resolved = _resolve_profile(profile)
    safe_original = enforce_read_only_sql(original_sql)
    error = parse_oracle_error(oracle_error)
    if schema_context is not None:
        validate_sql_schema_context(safe_original, schema_context, strict=True)
    prompt = build_sql_repair_prompt(
        safe_original,
        error.raw_text,
        schema_context=schema_context,
    )
    response: AiResponse = generate_ai_text(
        resolved,
        prompt,
        temperature=0,
        session=session,
    )
    repaired = extract_sql(response.text)
    repaired = enforce_read_only_sql(repaired)
    classification = classify_sql(repaired)
    schema_validation = None
    if schema_context is not None:
        schema_validation = validate_sql_schema_context(
            repaired,
            schema_context,
            strict=True,
        )
    comparison = compare_sql(safe_original, repaired)
    if require_change and not comparison["changed"]:
        raise AiSqlRepairError(
            "AI repair returned SQL that is unchanged from the original query."
        )
    explanation = re.sub(
        r"```(?:sql|oracle|plsql)?\s*.*?```",
        "",
        response.text,
        flags=re.I | re.S,
    ).strip() or None
    return AiSqlRepairResult(
        original_sql=safe_original,
        repaired_sql=repaired,
        oracle_error=error,
        explanation=explanation,
        classification=classification,
        changed=comparison["changed"],
        unified_diff=comparison["unified_diff"],
        schema_validation=schema_validation,
        provider=response.provider,
        model=response.model,
        metadata={
            "request_id": response.request_id,
            "usage": dict(response.usage or {}),
        },
    )