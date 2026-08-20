from types import SimpleNamespace
import querysaas.ai as ai


class FakeResponse:
    def __init__(self, data, status=200):
        self._data = data
        self.status_code = status
        self.ok = status < 400
        self.headers = {}
    def json(self):
        return self._data


class FakeSession:
    def __init__(self):
        self.calls = []
    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        if url.endswith("/models"):
            return FakeResponse({"data": [{"id": "gpt-4o"}, {"id": "claude-sonnet-4-5"}]})
        if url.endswith("/chat/completions"):
            return FakeResponse({"choices": [{"message": {"content": "QUERYSAAS_AI_CONNECTED"}}]})
        raise AssertionError(url)


def test_normalizes_gateway_root_and_v1_root():
    assert ai.normalize_openai_compatible_api_root("https://example.com/ica") == "https://example.com/ica/v1"
    assert ai.normalize_openai_compatible_api_root("https://example.com/ica/v1") == "https://example.com/ica/v1"


def test_discovers_models_using_url_and_key_only():
    session = FakeSession()
    models = ai.list_ai_models_from_url("https://example.com/ica/v1", "secret", session=session)
    assert [item.model_id for item in models] == ["gpt-4o", "claude-sonnet-4-5"]
    assert session.calls[0][1] == "https://example.com/ica/v1/models"
    assert session.calls[0][2]["headers"]["Authorization"] == "Bearer secret"


def test_auto_selects_verified_preference():
    models = (ai.AiModelInfo("gpt-4o", "gpt-4o"), ai.AiModelInfo("claude-sonnet-4-5", "Claude"))
    assert ai.select_default_ai_model(models) == "claude-sonnet-4-5"
    assert ai.select_default_ai_model(models, previous_model="gpt-4o") == "gpt-4o"


def test_configure_discovers_selects_and_tests_chat():
    session = FakeSession()
    result = ai.configure_openai_compatible_provider("https://example.com/ica", "secret", session=session)
    assert result.selected_model == "claude-sonnet-4-5"
    assert result.profile.base_url == "https://example.com/ica/v1"
    assert [call[1] for call in session.calls] == [
        "https://example.com/ica/v1/models",
        "https://example.com/ica/v1/chat/completions",
    ]
    assert "api_key" not in result.to_dict()["profile"]
