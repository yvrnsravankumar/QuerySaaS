import pytest

from querysaas import (
    AiProviderProfile,
    AiSqlExtractionError,
    AiSqlSafetyError,
    build_oracle_sql_prompt,
    classify_sql,
    enforce_read_only_sql,
    extract_sql,
    generate_oracle_sql,
)


class Response:
    status_code = 200
    ok = True
    headers = {"x-request-id": "req-1"}
    def __init__(self, text):
        self.text = text
    def json(self):
        return {
            "choices": [{"message": {"content": self.text}}],
            "usage": {"total_tokens": 10},
        }


class Session:
    def __init__(self, text):
        self.response = Response(text)
    def request(self, *args, **kwargs):
        return self.response


def test_extract_fenced_sql():
    text = "Result:\n```sql\nSELECT * FROM dual\n```\nExplanation"
    assert extract_sql(text) == "SELECT * FROM dual"


def test_extract_requires_sql():
    with pytest.raises(AiSqlExtractionError):
        extract_sql("No query available")


def test_select_is_allowed():
    result = classify_sql("SELECT ';' AS value FROM dual")
    assert result.allowed is True
    assert result.read_only is True
    assert result.statement_type == "QUERY"


def test_with_query_is_allowed():
    result = classify_sql("WITH x AS (SELECT 1 n FROM dual) SELECT n FROM x")
    assert result.allowed is True


@pytest.mark.parametrize("sql", [
    "DELETE FROM projects",
    "UPDATE projects SET status='A'",
    "DROP TABLE projects",
    "BEGIN NULL; END;",
    "SELECT * FROM projects FOR UPDATE",
    "SELECT * FROM dual; DELETE FROM projects",
])
def test_unsafe_sql_is_blocked(sql):
    result = classify_sql(sql)
    assert result.allowed is False
    with pytest.raises(AiSqlSafetyError):
        enforce_read_only_sql(sql)


def test_semicolon_inside_comment_or_literal_is_not_multiple():
    sql = "SELECT ';' value FROM dual -- ; ignored\n"
    result = classify_sql(sql)
    assert result.multiple_statements is False
    assert result.allowed is True


def test_prompt_contains_read_only_policy():
    prompt = build_oracle_sql_prompt(
        "List active projects",
        schema_context={"tables": ["PJF_PROJECTS_ALL_B"]},
    )
    assert "read-only Oracle SELECT or WITH" in prompt
    assert "PJF_PROJECTS_ALL_B" in prompt


def test_generate_oracle_sql_returns_structured_result():
    profile = AiProviderProfile(provider="ollama", model="qwen3:8b")
    session = Session(
        "```sql\nSELECT project_id FROM pjf_projects_all_b\n```\nUses the supplied table."
    )
    result = generate_oracle_sql(
        profile,
        "List projects",
        schema_context={"tables": ["PJF_PROJECTS_ALL_B"]},
        session=session,
    )
    assert result.sql == "SELECT project_id FROM pjf_projects_all_b"
    assert result.classification.allowed is True
    assert result.provider == "ollama"
    assert result.metadata["request_id"] == "req-1"


def test_generated_delete_is_blocked():
    profile = AiProviderProfile(provider="ollama", model="qwen3:8b")
    with pytest.raises(AiSqlSafetyError, match="blocked"):
        generate_oracle_sql(
            profile,
            "Delete projects",
            session=Session("```sql\nDELETE FROM projects\n```"),
        )