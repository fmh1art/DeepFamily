from __future__ import annotations

import httpx

from askdu.adapters.catalog import FileCatalog
from askdu.adapters.coda_release import CodaReleaseRegistry
from askdu.adapters.federated_catalog import FederatedFileCatalog
from askdu.adapters.llm import (
    AzureChatCompletionsModel,
    DirectChatCompletionsModel,
    OpenAICompatibleChatModel,
)
from askdu.adapters.provenance import ProvenanceRegistry
from askdu.adapters.repository import FileRunRepository
from askdu.application.model_compiler import ModelQuestionCompiler
from askdu.application.orchestrator import RunService
from askdu.application.ports import ChatModel
from askdu.config import PROJECT_LLM_ENDPOINT, PROJECT_LLM_MODEL, Settings


def build_catalog(settings: Settings) -> FileCatalog:
    if settings.catalog_mode == "coda_open_release":
        catalog = FederatedFileCatalog(
            CodaReleaseRegistry(
                manifest_path=settings.coda_release_manifest,
                release_root=settings.coda_release_root,
            )
        )
        if not catalog.installed_community_ids:
            raise FileNotFoundError("No open CoDA community has been extracted")
        return catalog
    registry = (
        ProvenanceRegistry.from_file(settings.provenance_manifest)
        if settings.provenance_manifest is not None
        else None
    )
    return FileCatalog(
        settings.data_root,
        environment_id=settings.environment_id,
        provenance_registry=registry,
    )


def build_chat_model(settings: Settings, *, http_client: httpx.Client | None = None) -> ChatModel:
    """Construct the only model client shared by every agentic stage."""

    if not settings.llm_configured:
        raise ValueError("Model-backed mode requires server-side LLM base URL, model, and API key")
    assert settings.llm_base_url is not None
    assert settings.llm_api_key is not None
    assert settings.llm_model is not None
    project_profile = (
        settings.llm_base_url == PROJECT_LLM_ENDPOINT
        and settings.llm_model == PROJECT_LLM_MODEL
        and settings.llm_api_style == "azure_chat"
        and settings.llm_auth_scheme == "api_key"
        and settings.llm_token_field == "max_completion_tokens"
    )
    if not project_profile and not settings.llm_allow_test_provider:
        raise ValueError(
            "Model-backed project modes require the pinned ModelHub endpoint/model profile"
        )
    if http_client is not None and settings.llm_api_style != "azure_chat":
        raise ValueError("An injected evaluation HTTP client requires the Azure Chat profile")
    if settings.llm_api_style == "azure_chat":
        return AzureChatCompletionsModel(
            gateway_url=settings.llm_base_url,
            api_key=settings.llm_api_key,
            model=settings.llm_model,
            timeout_seconds=settings.llm_timeout_seconds,
            max_retries=settings.llm_max_retries,
            token_field=settings.llm_token_field,
            trust_env_proxy=settings.llm_trust_env_proxy,
            http_client=http_client,
        )
    if settings.llm_api_style == "direct_chat_completions":
        return DirectChatCompletionsModel(
            endpoint=settings.llm_base_url,
            api_key=settings.llm_api_key,
            model=settings.llm_model,
            timeout_seconds=settings.llm_timeout_seconds,
            max_retries=settings.llm_max_retries,
            auth_scheme=settings.llm_auth_scheme,
            token_field=settings.llm_token_field,
            trust_env_proxy=settings.llm_trust_env_proxy,
        )
    if settings.llm_auth_scheme != "bearer":
        raise ValueError(
            "openai_base_url mode supports bearer authentication only; "
            "use direct_chat_completions for api_key headers"
        )
    return OpenAICompatibleChatModel(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        model=settings.llm_model,
        timeout_seconds=settings.llm_timeout_seconds,
        max_retries=settings.llm_max_retries,
        token_field=settings.llm_token_field,
        trust_env_proxy=settings.llm_trust_env_proxy,
    )


def build_run_service(settings: Settings) -> RunService:
    """Build the runtime graph without exposing provider configuration to the API."""

    catalog = build_catalog(settings)
    compiler = None
    chat_model: ChatModel | None = None
    if settings.planner_mode in {"model", "agentic"}:
        chat_model = build_chat_model(settings)
    if settings.planner_mode == "model":
        assert chat_model is not None
        compiler = ModelQuestionCompiler(
            model=chat_model,
            catalog=catalog,
            max_attempts=settings.planner_max_attempts,
        )

    return RunService(
        environment_id=catalog.environment_id or settings.environment_id,
        data_root=settings.data_root,
        runtime_root=settings.runtime_root,
        repository=FileRunRepository(settings.runtime_root / "state"),
        max_repair_rounds=settings.max_repair_rounds,
        max_concurrent_runs=settings.max_concurrent_runs,
        compiler=compiler,
        catalog=catalog,
        agentic_model=chat_model if settings.planner_mode == "agentic" else None,
        discovery_max_turns=settings.discovery_max_turns,
        preparation_max_turns=settings.preparation_max_turns,
    )
