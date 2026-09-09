from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import ANY, MagicMock, patch

import pytest

from askdu.adapters.llm import (
    AzureChatCompletionsModel,
    ChatModelError,
    OpenAICompatibleChatModel,
)
from askdu.bootstrap import build_run_service
from askdu.config import PROJECT_LLM_ENDPOINT, PROJECT_LLM_MODEL, Settings


@patch("askdu.adapters.llm.OpenAI")
def test_openai_compatible_adapter_uses_server_configuration(openai: MagicMock) -> None:
    client = openai.return_value
    client.chat.completions.create.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="  valid output  "))]
    )

    model = OpenAICompatibleChatModel(
        base_url="https://provider.example/v1",
        api_key="server-only-secret",
        model="test-model",
    )
    result = model.complete(system="Compile a contract.", user="Analyze this question.")

    assert result == "valid output"
    openai.assert_called_once_with(
        base_url="https://provider.example/v1",
        api_key="server-only-secret",
        timeout=120.0,
        max_retries=2,
        http_client=ANY,
    )
    request = client.chat.completions.create.call_args.kwargs
    assert request["model"] == "test-model"
    assert request["max_completion_tokens"] == 2_000
    assert "max_tokens" not in request
    assert request["messages"] == [
        {"role": "system", "content": "Compile a contract."},
        {"role": "user", "content": "Analyze this question."},
    ]


@patch("askdu.adapters.llm.OpenAI")
def test_openai_compatible_adapter_can_use_legacy_token_field(openai: MagicMock) -> None:
    client = openai.return_value
    client.chat.completions.create.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="{}"))]
    )
    model = OpenAICompatibleChatModel(
        base_url="https://provider.example/v1",
        api_key="server-only-secret",
        model="legacy-model",
        token_field="max_tokens",
    )

    model.complete(system="Compile a contract.", user="Analyze this question.")

    request = client.chat.completions.create.call_args.kwargs
    assert request["max_tokens"] == 2_000
    assert "max_completion_tokens" not in request


@patch("askdu.adapters.llm.OpenAI")
def test_openai_compatible_adapter_rejects_empty_output(openai: MagicMock) -> None:
    openai.return_value.chat.completions.create.return_value = SimpleNamespace(choices=[])
    model = OpenAICompatibleChatModel(
        base_url="https://provider.example/v1",
        api_key="server-only-secret",
        model="test-model",
    )

    with pytest.raises(ChatModelError, match="no textual completion"):
        model.complete(system="System", user="Question")


@patch("askdu.adapters.llm.AzureOpenAI")
def test_azure_gateway_adapter_builds_deployment_route_without_temperature(
    azure_openai: MagicMock,
) -> None:
    client = azure_openai.return_value
    client.chat.completions.create.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="  valid output  "))]
    )
    model = AzureChatCompletionsModel(
        gateway_url=(
            "https://aidp.bytedance.net/api/modelhub/online/v2/crawl?api-version=2024-03-01-preview"
        ),
        api_key="server-only-secret",
        model="gpt-5.5-2026-04-24",
    )

    result = model.complete(system="Discover sources.", user="分析这个问题")

    assert result == "valid output"
    azure_openai.assert_called_once_with(
        api_key="server-only-secret",
        api_version="2024-03-01-preview",
        azure_endpoint="https://aidp.bytedance.net/api/modelhub/online/v2/crawl",
        timeout=120.0,
        max_retries=2,
        http_client=ANY,
    )
    request = client.chat.completions.create.call_args.kwargs
    assert request["model"] == "gpt-5.5-2026-04-24"
    assert request["max_completion_tokens"] == 2_000
    assert "temperature" not in request
    assert request["messages"][-1]["content"] == "分析这个问题"


def test_azure_gateway_adapter_requires_one_api_version() -> None:
    with pytest.raises(ValueError, match="exactly one non-empty api-version"):
        AzureChatCompletionsModel(
            gateway_url="https://provider.example/gateway",
            api_key="server-only-secret",
            model="test-model",
        )


def test_openai_base_mode_rejects_a_complete_queried_endpoint() -> None:
    with pytest.raises(ValueError, match="direct_chat_completions"):
        OpenAICompatibleChatModel(
            base_url="https://provider.example/complete?api-version=preview",
            api_key="server-only-secret",
            model="test-model",
        )


def test_provider_endpoint_rejects_cleartext_non_loopback_url() -> None:
    with pytest.raises(ValueError, match="must use HTTPS"):
        OpenAICompatibleChatModel(
            base_url="http://provider.example/v1",
            api_key="server-only-secret",
            model="test-model",
        )


def test_settings_repr_does_not_include_llm_secret(tmp_path: object) -> None:
    settings = Settings(
        data_root=".",
        runtime_root="runtime",
        llm_base_url="https://provider.example/v1",
        llm_model="test-model",
        llm_api_key="do-not-print-this",
    )

    assert settings.llm_configured is True
    assert "do-not-print-this" not in repr(settings)


def test_model_planner_mode_requires_complete_server_configuration(tmp_path: object) -> None:
    settings = Settings(
        data_root=".",
        runtime_root="runtime",
        planner_mode="model",
        _env_file=None,
    )

    with pytest.raises(ValueError, match="requires server-side LLM"):
        build_run_service(settings)


@patch.dict("os.environ", {}, clear=True)
def test_project_model_profile_is_pinned_by_default() -> None:
    # _env_file=None disables dotenv, not process variables. Check actual defaults
    # independently of the isolated artifact guide's loopback provider override.
    settings = Settings(data_root=".", runtime_root="runtime", _env_file=None)

    assert settings.llm_base_url == PROJECT_LLM_ENDPOINT
    assert settings.llm_model == PROJECT_LLM_MODEL
    assert settings.llm_api_style == "azure_chat"
    assert settings.llm_auth_scheme == "api_key"
    assert settings.llm_token_field == "max_completion_tokens"
    assert settings.llm_allow_test_provider is False


def test_model_profile_environment_overrides_are_loaded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ASKDU_LLM_BASE_URL", "http://127.0.0.1:9")
    monkeypatch.setenv("ASKDU_LLM_MODEL", "contract-test-model")
    monkeypatch.setenv("ASKDU_LLM_API_STYLE", "openai_base_url")
    monkeypatch.setenv("ASKDU_LLM_AUTH_SCHEME", "bearer")
    monkeypatch.setenv("ASKDU_LLM_TOKEN_FIELD", "max_tokens")
    monkeypatch.setenv("ASKDU_LLM_ALLOW_TEST_PROVIDER", "false")
    settings = Settings(data_root=".", runtime_root="runtime", _env_file=None)

    assert settings.llm_base_url == "http://127.0.0.1:9"
    assert settings.llm_model == "contract-test-model"
    assert settings.llm_api_style == "openai_base_url"
    assert settings.llm_auth_scheme == "bearer"
    assert settings.llm_token_field == "max_tokens"
    # Loading configuration does not authorize a non-project runtime provider.
    assert settings.llm_allow_test_provider is False


def test_model_backed_runtime_rejects_nonproject_provider(tmp_path: object) -> None:
    settings = Settings(
        data_root=".",
        runtime_root="runtime",
        planner_mode="agentic",
        llm_base_url="https://provider.example/v1/chat/completions",
        llm_model="unapproved-model",
        llm_api_key="test-only-secret",
    )

    with pytest.raises(ValueError, match="pinned ModelHub endpoint/model"):
        build_run_service(settings)
