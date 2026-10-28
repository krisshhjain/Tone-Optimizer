from types import SimpleNamespace

import pytest

from core.model_client import GenerationSettings, ModelConfig, ModelError, create_completion, generate_reply


def config(**kwargs):
    values = {"api_key": "test-secret-never-logged", "base_url": "https://example.invalid/v1", "model": "test-model"}
    values.update(kwargs)
    return ModelConfig(settings=GenerationSettings(), **values)


class FakeClient:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.kwargs = None
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **kwargs):
        self.kwargs = kwargs
        if self.error:
            raise self.error
        return self.response


def response(content):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


def test_successful_response_and_generation_metadata():
    client = FakeClient(response("Namaste!"))
    prompt = [{"role": "system", "content": "system"}, {"role": "user", "content": "नमस्ते"}]
    assert generate_reply(prompt, config(), client) == "Namaste!"
    assert client.kwargs["model"] == "test-model"
    assert client.kwargs["messages"] == prompt
    assert client.kwargs["stream"] is False
    assert config().settings.as_metadata() == {
        "temperature": 1.0, "top_p": 0.95, "max_tokens": 16384, "timeout_seconds": 60.0,
    }


def test_missing_api_key_is_handled_without_sdk_or_network(monkeypatch):
    # A developer's real .env must not turn this offline test into a configured test.
    import dotenv

    monkeypatch.setattr(dotenv, "load_dotenv", lambda *args, **kwargs: False)
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    monkeypatch.setenv("NVIDIA_BASE_URL", "https://example.invalid/v1")
    monkeypatch.setenv("NVIDIA_MODEL", "test-model")
    with pytest.raises(ModelError, match="NVIDIA_API_KEY"):
        ModelConfig.from_env()


def test_config_reads_all_required_environment_values(monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", "synthetic-test-key")
    monkeypatch.setenv("NVIDIA_BASE_URL", "https://example.invalid/v1")
    monkeypatch.setenv("NVIDIA_MODEL", "synthetic-model")
    monkeypatch.setenv("NVIDIA_TEMPERATURE", "0.4")
    monkeypatch.setenv("NVIDIA_TOP_P", "0.8")
    monkeypatch.setenv("NVIDIA_MAX_TOKENS", "256")
    monkeypatch.setenv("NVIDIA_TIMEOUT_SECONDS", "12")
    loaded = ModelConfig.from_env()
    assert (loaded.api_key, loaded.base_url, loaded.model) == (
        "synthetic-test-key", "https://example.invalid/v1", "synthetic-model",
    )
    assert loaded.settings.as_metadata() == {
        "temperature": 0.4, "top_p": 0.8, "max_tokens": 256, "timeout_seconds": 12.0,
    }
    assert "synthetic-test-key" not in str(loaded.settings.as_metadata())


@pytest.mark.parametrize(
    "error,expected",
    [
        (TimeoutError("contains test-secret-never-logged"), "timed out"),
        (type("RateLimitError", (Exception,), {})("rate limited"), "rate limited"),
        (ConnectionError("endpoint down"), "unavailable"),
    ],
)
def test_timeout_and_api_failures_are_sanitized(error, expected):
    with pytest.raises(ModelError) as exc:
        generate_reply([{"role": "user", "content": "hello"}], config(), FakeClient(error=error))
    assert expected in str(exc.value)
    assert "test-secret-never-logged" not in str(exc.value)


@pytest.mark.parametrize("api_response", [None, SimpleNamespace(choices=[]), response("  "), SimpleNamespace(choices=[SimpleNamespace(message=None)])])
def test_empty_or_malformed_responses_are_rejected(api_response):
    with pytest.raises(ModelError, match="response"):
        generate_reply([{"role": "user", "content": "hello"}], config(), FakeClient(response=api_response))


def test_credentials_never_enter_completion_payload():
    client = FakeClient(response("Reply"))
    generate_reply([{"role": "user", "content": "hello"}], config(), client)
    assert all("test-secret-never-logged" not in str(value) for value in client.kwargs.values())


def test_completion_sends_structured_tool_schema_and_choice():
    client = FakeClient(response("unused"))
    tools = [{"type": "function", "function": {"name": "probe", "parameters": {"type": "object"}}}]
    create_completion(
        [{"role": "user", "content": "Call probe"}], config(), client,
        tools=tools, tool_choice="required", max_tokens=128,
    )
    assert client.kwargs["tools"] == tools
    assert client.kwargs["tool_choice"] == "required"
    assert client.kwargs["max_tokens"] == 128
