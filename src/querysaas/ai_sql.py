"""Oracle-aware AI SQL extraction, classification, and read-only safeguards."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from .ai import AiProviderProfile, AiResponse, generate_ai_text
from .sql import OracleSqlPlanner


_READ_ONLY_WORDS = {"SELECT", "WITH"}
_WRITE_WORDS = {
    "INSERT", "UPDATE", "DELETE", "MERGE", "UPSERT", "REPLACE",
}
_DDL_WORDS = {
    "ALTER", "CREATE", "DROP", "TRUNCATE", "RENAME", "COMMENT", "GRANT", "REVOKE",
}
_PLSQL_WORDS = {"BEGIN", "DECLARE", "CALL", "EXEC", "EXECUTE"}
_TRANSACTION_WORDS = {"COMMIT", "ROLLBACK", "SAVEPOINT", "SET"}
_DANGEROUS_PATTERNS = (
    (re.compile(r"(?i)\bDBMS_SCHEDULER\b"), "scheduler package"),
    (re.compile(r"(?i)\bDBMS_JOB\b"), "job package"),
    (re.compile(r"(?i)\bUTL_HTTP\b"), "network package"),
    (re.compile(r"(?i)\bUTL_FILE\b"), "file package"),
    (re.compile(r"(?i)\bDBMS_PIPE\b"), "pipe package"),
    (re.compile(r"(?i)\bEXECUTE\s+IMMEDIATE\b"), "dynamic SQL"),
    (re.compile(r"(?i)\bFOR\s+UPDATE\b"), "row-locking clause"),
    (re.compile(r"(?i)\bINTO\s+OUTFILE\b"), "file output clause"),
)


class AiSqlError(RuntimeError):
    """Base AI SQL processing error."""


class AiSqlExtractionError(AiSqlError):
    """Raised when no usable SQL can be extracted."""


class AiSqlSafetyError(AiSqlError):
    """Raised when SQL violates the requested safety policy."""


@dataclass(frozen=True)
class AiSqlClassification:
    statement_type: str
    read_only: bool
    allowed: bool
    multiple_statements: bool
    has_comments: bool
    risk_level: str
    reasons: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self):
        return {
            "statement_type": self.statement_type,
            "read_only": self.read_only,
            "allowed": self.allowed,
            "multiple_statements": self.multiple_statements,
            "has_comments": self.has_comments,
            "risk_level": self.risk_level,
            "reasons": list(self.reasons),
        }


@dataclass(frozen=True)
class AiSqlResult:
    prompt: str
    sql: str
    classification: AiSqlClassification
    provider: str | None = None
    model: str | None = None
    explanation: str | None = None
    raw_text: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self, include_raw=False):
        result = {
            "prompt": self.prompt,
            "sql": self.sql,
            "classification": self.classification.to_dict(),
            "provider": self.provider,
            "model": self.model,
            "explanation": self.explanation,
            "metadata": dict(self.metadata),
        }
        if include_raw:
            result["raw_text"] = self.raw_text
        return result


def _mask_literals_and_comments(sql):
    """Replace comments and quoted text while preserving statement structure."""
    output = []
    index = 0
    length = len(sql)
    state = "normal"
    q_end = None
    pairs = {"[": "]", "{": "}", "(": ")", "<": ">"}
    while index < length:
        char = sql[index]
        nxt = sql[index + 1] if index + 1 < length else ""
        if state == "normal":
            if char == "-" and nxt == "-":
                output.extend("  "); index += 2; state = "line_comment"; continue
            if char == "/" and nxt == "*":
                output.extend("  "); index += 2; state = "block_comment"; continue
            if char == "'":
                output.append(" "); index += 1; state = "single"; continue
            if char == '"':
                output.append(" "); index += 1; state = "double"; continue
            if char.casefold() == "q" and nxt == "'" and index + 2 < length:
                delimiter = sql[index + 2]
                q_end = pairs.get(delimiter, delimiter)
                output.extend("   "); index += 3; state = "qquote"; continue
            output.append(char); index += 1; continue
        if state == "line_comment":
            if char in "\r\n":
                output.append(char); state = "normal"
            else:
                output.append(" ")
            index += 1; continue
        if state == "block_comment":
            if char == "*" and nxt == "/":
                output.extend("  "); index += 2; state = "normal"
            else:
                output.append(char if char in "\r\n" else " "); index += 1
            continue
        if state == "single":
            if char == "'" and nxt == "'":
                output.extend("  "); index += 2
            elif char == "'":
                output.append(" "); index += 1; state = "normal"
            else:
                output.append(char if char in "\r\n" else " "); index += 1
            continue
        if state == "double":
            if char == '"' and nxt == '"':
                output.extend("  "); index += 2
            elif char == '"':
                output.append(" "); index += 1; state = "normal"
            else:
                output.append(char if char in "\r\n" else " "); index += 1
            continue
        if state == "qquote":
            if char == q_end and nxt == "'":
                output.extend("  "); index += 2; state = "normal"
            else:
                output.append(char if char in "\r\n" else " "); index += 1
    return "".join(output)


def _strip_markdown_fence(value):
    value = value.strip()
    fence = re.fullmatch(r"```(?:sql|oracle|plsql)?\s*(.*?)\s*```", value, re.I | re.S)
    return fence.group(1).strip() if fence else value


def extract_sql(value, *, require_sql=True):
    """Extract the first fenced or apparent Oracle SQL statement from AI text."""
    if not isinstance(value, str):
        raise TypeError("AI SQL source must be text.")
    text = value.strip()
    if not text:
        if require_sql:
            raise AiSqlExtractionError("AI response did not contain SQL.")
        return ""
    blocks = re.findall(r"```(?:sql|oracle|plsql)?\s*(.*?)```", text, re.I | re.S)
    candidates = blocks or [text]
    keyword = re.compile(
        r"(?im)^\s*(WITH|SELECT|INSERT|UPDATE|DELETE|MERGE|ALTER|CREATE|DROP|TRUNCATE|BEGIN|DECLARE|CALL|EXEC(?:UTE)?)\b"
    )
    for candidate in candidates:
        cleaned = _strip_markdown_fence(candidate).strip()
        match = keyword.search(cleaned)
        if match:
            sql = cleaned[match.start():].strip()
            while sql.endswith("```"):
                sql = sql[:-3].rstrip()
            return sql
    if require_sql:
        raise AiSqlExtractionError("AI response did not contain a recognizable SQL statement.")
    return ""


def _first_word(masked):
    match = re.search(r"\b[A-Za-z]+\b", masked)
    return match.group(0).upper() if match else "UNKNOWN"


def classify_sql(sql, *, read_only=True):
    """Classify Oracle SQL without executing it."""
    if not isinstance(read_only, bool):
        raise ValueError("read_only must be True or False.")
    sql = extract_sql(sql)
    masked = _mask_literals_and_comments(sql)
    word = _first_word(masked)
    semicolons = [m.start() for m in re.finditer(r";", masked)]
    non_terminal = any(masked[pos + 1:].strip() for pos in semicolons)
    has_comments = bool(re.search(r"--|/\*", sql))
    reasons = []

    if word in _READ_ONLY_WORDS:
        statement_type = "QUERY"
        is_read_only = True
    elif word in _WRITE_WORDS:
        statement_type = "DML"
        is_read_only = False
        reasons.append(f"{word} changes data")
    elif word in _DDL_WORDS:
        statement_type = "DDL"
        is_read_only = False
        reasons.append(f"{word} changes database objects or privileges")
    elif word in _PLSQL_WORDS:
        statement_type = "PLSQL"
        is_read_only = False
        reasons.append(f"{word} may execute procedural operations")
    elif word in _TRANSACTION_WORDS:
        statement_type = "TRANSACTION"
        is_read_only = False
        reasons.append(f"{word} changes transaction or session state")
    else:
        statement_type = "UNKNOWN"
        is_read_only = False
        reasons.append("statement type is not recognized")

    for pattern, description in _DANGEROUS_PATTERNS:
        if pattern.search(masked):
            is_read_only = False
            reasons.append(f"contains {description}")

    if non_terminal:
        reasons.append("contains multiple statements")

    allowed = not non_terminal and (is_read_only if read_only else word != "UNKNOWN")
    if allowed and not reasons:
        risk = "LOW"
    elif statement_type == "QUERY" and not allowed:
        risk = "MEDIUM"
    else:
        risk = "HIGH"

    return AiSqlClassification(
        statement_type=statement_type,
        read_only=is_read_only,
        allowed=allowed,
        multiple_statements=non_terminal,
        has_comments=has_comments,
        risk_level=risk,
        reasons=tuple(dict.fromkeys(reasons)),
    )


def enforce_read_only_sql(sql):
    """Validate SQL as a single Oracle SELECT/WITH statement and return it."""
    extracted = extract_sql(sql)
    classification = classify_sql(extracted, read_only=True)
    if not classification.allowed:
        detail = "; ".join(classification.reasons) or "not a read-only query"
        raise AiSqlSafetyError(f"AI SQL was blocked: {detail}.")
    try:
        OracleSqlPlanner().validate_query(extracted)
    except Exception as exc:
        raise AiSqlSafetyError(f"AI SQL failed Oracle query validation: {exc}") from exc
    return extracted


def build_oracle_sql_prompt(request, *, schema_context=None, read_only=True):
    if not isinstance(request, str) or not request.strip():
        raise ValueError("SQL request cannot be empty.")
    policy = (
        "Return exactly one read-only Oracle SELECT or WITH statement. "
        "Do not use DML, DDL, PL/SQL, transaction commands, FOR UPDATE, dynamic SQL, "
        "scheduler, network, or file packages. Do not invent tables or columns."
        if read_only else
        "Return exactly one Oracle SQL statement and clearly state its effects."
    )
    context = ""
    if schema_context:
        context = "\nAllowed schema context:\n" + str(schema_context)
    return (
        "You are an Oracle SQL assistant.\n"
        + policy
        + "\nUse explicit joins and qualified aliases. Preserve Oracle syntax. "
          "Return SQL in one ```sql fenced block followed by a short explanation."
        + context
        + "\nUser request:\n"
        + request.strip()
    )


def generate_oracle_sql(
    profile: AiProviderProfile,
    request: str,
    *,
    schema_context=None,
    read_only=True,
    temperature=0,
    session=None,
):
    """Generate, extract, classify, and optionally enforce read-only Oracle SQL."""
    if not isinstance(read_only, bool):
        raise ValueError("read_only must be True or False.")
    prompt = build_oracle_sql_prompt(
        request,
        schema_context=schema_context,
        read_only=read_only,
    )
    response: AiResponse = generate_ai_text(
        profile,
        prompt,
        temperature=temperature,
        session=session,
    )
    sql = extract_sql(response.text)
    classification = classify_sql(sql, read_only=read_only)
    if not classification.allowed:
        detail = "; ".join(classification.reasons) or "statement violates policy"
        raise AiSqlSafetyError(f"AI SQL was blocked: {detail}.")
    if read_only:
        sql = enforce_read_only_sql(sql)
    explanation = re.sub(r"```(?:sql|oracle|plsql)?\s*.*?```", "", response.text, flags=re.I | re.S).strip() or None
    return AiSqlResult(
        prompt=request.strip(),
        sql=sql,
        classification=classification,
        provider=response.provider,
        model=response.model,
        explanation=explanation,
        raw_text=response.text,
        metadata={"request_id": response.request_id, "usage": dict(response.usage or {})},
    )

# QUERYSAAS-AI-DUCKDB-SQL-BEGIN

DUCKDB_EXECUTION_TARGET = "duckdb"
ORACLE_FUSION_EXECUTION_TARGET = "oracle_fusion"


def normalize_sql_execution_target(value):
    """Return the canonical SQL execution target."""
    target = str(value or "").strip().casefold()
    aliases = {
        "fusion": ORACLE_FUSION_EXECUTION_TARGET,
        "oracle": ORACLE_FUSION_EXECUTION_TARGET,
        "oracle_fusion": ORACLE_FUSION_EXECUTION_TARGET,
        "duckdb": DUCKDB_EXECUTION_TARGET,
    }
    try:
        return aliases[target]
    except KeyError as exc:
        raise ValueError(
            "execution_target must be 'oracle_fusion' or 'duckdb'."
        ) from exc


def build_duckdb_sql_prompt(request, *, schema_context=None, allow_multiple_statements=True):
    """Build a DuckDB-native prompt without Oracle Fusion read-only restrictions."""
    if not isinstance(request, str) or not request.strip():
        raise ValueError("SQL request cannot be empty.")
    if not isinstance(allow_multiple_statements, bool):
        raise ValueError("allow_multiple_statements must be True or False.")

    statement_policy = (
        "You may return one statement or a complete multi-statement DuckDB script."
        if allow_multiple_statements
        else "Return exactly one DuckDB statement."
    )
    context = ""
    if schema_context:
        context = "\nAvailable DuckDB schema context:\n" + str(schema_context)

    return (
        "You are a DuckDB SQL assistant.\n"
        "Generate valid DuckDB SQL for the user's request. "
        "DuckDB DDL, DML, transactions, COPY, ATTACH, DETACH, IMPORT, EXPORT, "
        "INSTALL, LOAD, PRAGMA, macros, views, schemas, sequences, indexes, "
        "CREATE OR REPLACE, ALTER, DROP, TRUNCATE, and RENAME are permitted. "
        + statement_policy
        + " Do not apply Oracle Fusion read-only restrictions. "
        "Return the SQL in a ```sql fenced block followed by a short explanation."
        + context
        + "\nUser request:\n"
        + request.strip()
    )


def classify_duckdb_sql(sql):
    """Classify DuckDB SQL for display without blocking valid DDL or DML."""
    if not isinstance(sql, str) or not sql.strip():
        raise ValueError("DuckDB SQL cannot be empty.")
    masked = _mask_literals_and_comments(sql)
    words = tuple(match.group(0).upper() for match in re.finditer(r"\b[A-Za-z]+\b", masked))
    first = words[0] if words else "UNKNOWN"
    multiple = any(masked[pos + 1:].strip() for pos in (m.start() for m in re.finditer(r";", masked)))
    ddl = first in {"CREATE", "ALTER", "DROP", "TRUNCATE", "RENAME", "COMMENT"}
    dml = first in {"INSERT", "UPDATE", "DELETE", "MERGE", "REPLACE"}
    transaction = first in {"BEGIN", "COMMIT", "ROLLBACK", "SAVEPOINT"}
    read_only = first in {"SELECT", "WITH", "SHOW", "DESCRIBE", "EXPLAIN"}
    destructive = first in {"DROP", "TRUNCATE"}
    return {
        "execution_target": DUCKDB_EXECUTION_TARGET,
        "dialect": "duckdb",
        "statement_type": first,
        "statement_types": words,
        "read_only": read_only,
        "changes_data": dml or destructive,
        "changes_schema": ddl,
        "transaction_control": transaction,
        "multiple_statements": multiple,
        "destructive": destructive,
        "allowed": True,
        "risk_level": "HIGH" if destructive else ("MEDIUM" if ddl or dml else "LOW"),
        "warnings": (),
    }


def generate_duckdb_sql(
    profile,
    request,
    *,
    schema_context=None,
    allow_multiple_statements=True,
    temperature=0,
    session=None,
):
    """Generate unrestricted DuckDB SQL and return a provider-independent result."""
    prompt = build_duckdb_sql_prompt(
        request,
        schema_context=schema_context,
        allow_multiple_statements=allow_multiple_statements,
    )
    response = generate_ai_text(
        profile,
        prompt,
        temperature=temperature,
        session=session,
    )
    sql = extract_sql(response.text)
    classification = classify_duckdb_sql(sql)
    if not allow_multiple_statements and classification["multiple_statements"]:
        raise AiSqlSafetyError("DuckDB response contained multiple statements.")
    explanation = re.sub(
        r"```(?:sql|duckdb)?\s*.*?```",
        "",
        response.text,
        flags=re.I | re.S,
    ).strip() or None
    return {
        "prompt": request.strip(),
        "sql": sql,
        "classification": classification,
        "provider": response.provider,
        "model": response.model,
        "explanation": explanation,
        "metadata": {
            "execution_target": DUCKDB_EXECUTION_TARGET,
            "request_id": response.request_id,
            "usage": dict(response.usage or {}),
            "automatic_execution": False,
        },
    }

# QUERYSAAS-AI-DUCKDB-SQL-END
