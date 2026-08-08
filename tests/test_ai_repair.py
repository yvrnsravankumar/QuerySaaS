import json

import pytest

from querysaas import (
    AiProviderProfile,
    AiSqlRepairError,
    AiSqlSafetyError,
    OracleSchemaContext,
    build_sql_repair_prompt,
    compare_sql,
    explain_oracle_sql,
    parse_oracle_error,
    repair_oracle_sql,
)


class Response:
    status_code = 200
    ok = True
    headers = {"x-request-id": "repair-1"}
    def __init__(self, text):
        self.text = text
    def json(self):
        return {
            "choices": [{"message": {"content": self.text}}],
            "usage": {"total_tokens": 20},
        }


class Session:
    def __init__(self, text):
        self.response = Response(text)
    def request(self, *args, **kwargs):
        return self.response


def profile():
    return AiProviderProfile(provider="ollama", model="qwen3:8b")


def context():
    return OracleSchemaContext(
        tables={"PJF_PROJECTS_ALL_B": ["PROJECT_ID", "SEGMENT1"]}
    )


def test_parse_oracle_error_and_redaction():
    result = parse_oracle_error(
        "ORA-00904: invalid identifier password=hidden"
    )
    assert result.code == "ORA-00904"
    assert "hidden" not in result.raw_text


def test_compare_sql_returns_diff():
    result = compare_sql(
        "SELECT project_id FROM pjf_projects_all_b",
        "SELECT project_id, segment1 FROM pjf_projects_all_b",
    )
    assert result["changed"] is True
    assert "original.sql" in result["unified_diff"]
    assert "+SELECT project_id, segment1" in result["unified_diff"]


def test_build_repair_prompt_contains_error_and_context():
    prompt = build_sql_repair_prompt(
        "SELECT bad_column FROM pjf_projects_all_b",
        "ORA-00904: BAD_COLUMN: invalid identifier",
        schema_context=context(),
    )
    assert "ORA-00904" in prompt
    assert "PJF_PROJECTS_ALL_B" in prompt
    assert "read-only" in prompt


def test_explain_oracle_sql():
    result = explain_oracle_sql(
        profile(),
        "SELECT project_id FROM pjf_projects_all_b",
        schema_context=context(),
        session=Session("Reads project identifiers from the projects table."),
    )
    assert result.classification.allowed is True
    assert "project identifiers" in result.explanation
    assert result.metadata["request_id"] == "repair-1"


def test_repair_oracle_sql():
    result = repair_oracle_sql(
        profile(),
        "SELECT bad_column FROM pjf_projects_all_b",
        "ORA-00904: BAD_COLUMN: invalid identifier",
        schema_context=context(),
        session=Session(
            "```sql\nSELECT project_id FROM pjf_projects_all_b\n```\nUses an approved column."
        ),
    )
    assert result.repaired_sql == "SELECT project_id FROM pjf_projects_all_b"
    assert result.oracle_error.code == "ORA-00904"
    assert result.changed is True
    assert result.schema_validation["valid"] is True
    assert "approved column" in result.explanation


def test_repair_blocks_write_sql():
    with pytest.raises(AiSqlSafetyError):
        repair_oracle_sql(
            profile(),
            "SELECT project_id FROM pjf_projects_all_b",
            "ORA-00904: invalid identifier",
            schema_context=context(),
            session=Session("```sql\nDELETE FROM pjf_projects_all_b\n```"),
        )


def test_repair_blocks_unknown_table():
    with pytest.raises(AiSqlSafetyError, match="outside"):
        repair_oracle_sql(
            profile(),
            "SELECT project_id FROM pjf_projects_all_b",
            "ORA-00904: invalid identifier",
            schema_context=context(),
            session=Session("```sql\nSELECT party_id FROM hz_parties\n```"),
        )


def test_repair_requires_change_by_default():
    with pytest.raises(AiSqlRepairError, match="unchanged"):
        repair_oracle_sql(
            profile(),
            "SELECT project_id FROM pjf_projects_all_b",
            "ORA-00904: invalid identifier",
            schema_context=context(),
            session=Session(
                "```sql\nSELECT project_id FROM pjf_projects_all_b\n```"
            ),
        )