from types import SimpleNamespace

import pytest

from querysaas import (
    build_duckdb_sql_prompt,
    classify_duckdb_sql,
    generate_duckdb_sql,
    normalize_sql_execution_target,
)


def test_execution_targets_are_explicit():
    assert normalize_sql_execution_target("fusion") == "oracle_fusion"
    assert normalize_sql_execution_target("oracle_fusion") == "oracle_fusion"
    assert normalize_sql_execution_target("duckdb") == "duckdb"
    with pytest.raises(ValueError):
        normalize_sql_execution_target("unknown")


def test_duckdb_prompt_explicitly_allows_ddl_and_dml():
    prompt = build_duckdb_sql_prompt("Create and populate a reporting table")
    assert "DuckDB DDL, DML" in prompt
    assert "CREATE OR REPLACE" in prompt
    assert "Do not apply Oracle Fusion read-only restrictions" in prompt


@pytest.mark.parametrize(
    "sql, statement_type, changes_schema, destructive",
    [
        ("CREATE TABLE x(id INTEGER)", "CREATE", True, False),
        ("ALTER TABLE x ADD COLUMN name VARCHAR", "ALTER", True, False),
        ("DROP TABLE x", "DROP", True, True),
        ("TRUNCATE x", "TRUNCATE", True, True),
        ("INSERT INTO x VALUES (1)", "INSERT", False, False),
        ("UPDATE x SET id = 2", "UPDATE", False, False),
        ("DELETE FROM x", "DELETE", False, False),
    ],
)
def test_duckdb_classification_never_blocks_ddl_or_dml(
    sql, statement_type, changes_schema, destructive
):
    result = classify_duckdb_sql(sql)
    assert result["statement_type"] == statement_type
    assert result["changes_schema"] is changes_schema
    assert result["destructive"] is destructive
    assert result["allowed"] is True


def test_duckdb_multi_statement_script_is_allowed():
    result = classify_duckdb_sql(
        "CREATE TABLE x(id INTEGER); INSERT INTO x VALUES (1); SELECT * FROM x;"
    )
    assert result["multiple_statements"] is True
    assert result["allowed"] is True


def test_generate_duckdb_sql_does_not_apply_oracle_safety(monkeypatch):
    response = SimpleNamespace(
        text="```sql\nDROP TABLE IF EXISTS old_data;\nCREATE TABLE new_data AS SELECT 1 AS id;\n```",
        provider="test",
        model="test-model",
        request_id="request-1",
        usage={},
    )
    monkeypatch.setattr("querysaas.ai_sql.generate_ai_text", lambda *a, **k: response)
    result = generate_duckdb_sql(object(), "Replace the local table")
    assert "DROP TABLE" in result["sql"]
    assert result["classification"]["allowed"] is True
    assert result["classification"]["multiple_statements"] is True
    assert result["metadata"]["automatic_execution"] is False
