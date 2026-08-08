import json

import pytest

from querysaas import (
    AiContextError,
    AiCredentialError,
    AiCredentialReference,
    AiNamedProfile,
    AiProfileError,
    AiProfileStore,
    AiProviderProfile,
    AiSqlSafetyError,
    OracleSchemaContext,
    extract_referenced_tables,
    preview_ai_sql_request,
    validate_sql_schema_context,
)


def test_environment_credential_reference():
    reference = AiCredentialReference(name="QUERYSAAS_AI_KEY")
    assert reference.resolve(environ={"QUERYSAAS_AI_KEY": "secret"}) == "secret"
    with pytest.raises(AiCredentialError):
        reference.resolve(environ={})


def test_named_profile_resolves_without_serializing_secret():
    profile = AiNamedProfile(
        name="local-ollama",
        provider="ollama",
        model="qwen3:8b",
        credential=AiCredentialReference(source="none"),
    )
    resolved = profile.resolve()
    assert resolved.provider == "ollama"
    assert "api_key" not in profile.to_dict()


def test_profile_store_round_trip(tmp_path):
    store = AiProfileStore(tmp_path / "profiles.json")
    profile = AiNamedProfile(
        name="gemini-dev",
        provider="gemini",
        model="gemini-test",
        credential=AiCredentialReference(name="GEMINI_API_KEY"),
    )
    store.save(profile)
    loaded = store.get("GEMINI-DEV")
    assert loaded.name == "gemini-dev"
    text = (tmp_path / "profiles.json").read_text()
    assert "GEMINI_API_KEY" in text
    assert "secret-value" not in text
    with pytest.raises(AiProfileError):
        store.save(profile)
    assert store.delete("gemini-dev") is True


def test_schema_context_normalizes_and_excludes_columns():
    context = OracleSchemaContext(
        tables={"pjf_projects_all_b": ["project_id", "segment1", "password", "segment1"]},
        excluded_columns=["password"],
    )
    assert context.tables["PJF_PROJECTS_ALL_B"] == ("PROJECT_ID", "SEGMENT1")
    assert context.to_dict()["column_count"] == 2


def test_schema_context_rejects_invalid_identifier():
    with pytest.raises(AiContextError):
        OracleSchemaContext(tables={"PJF PROJECTS": ["PROJECT_ID"]})


def test_referenced_tables():
    sql = "SELECT p.project_id FROM fusion.pjf_projects_all_b p JOIN pjf_tasks_v t ON t.project_id=p.project_id"
    assert extract_referenced_tables(sql) == (
        "FUSION.PJF_PROJECTS_ALL_B", "PJF_TASKS_V"
    )


def test_schema_context_validation():
    context = OracleSchemaContext(
        tables={"PJF_PROJECTS_ALL_B": ["PROJECT_ID"]}
    )
    valid = validate_sql_schema_context(
        "SELECT project_id FROM pjf_projects_all_b", context
    )
    assert valid["valid"] is True
    with pytest.raises(AiSqlSafetyError, match="outside"):
        validate_sql_schema_context("SELECT * FROM hz_parties", context)


def test_preview_redacts_prompt_and_shows_no_secret():
    profile = AiProviderProfile(
        provider="openai",
        model="test-model",
        api_key="secret-value",
    )
    context = OracleSchemaContext(
        tables={"PJF_PROJECTS_ALL_B": ["PROJECT_ID"]}
    )
    preview = preview_ai_sql_request(
        profile,
        "List projects. password=hidden-value",
        schema_context=context,
    )
    data = preview.to_dict()
    assert "hidden-value" not in json.dumps(data)
    assert "secret-value" not in json.dumps(data)
    assert data["credential_configured"] is True
    assert data["schema_context"]["table_count"] == 1