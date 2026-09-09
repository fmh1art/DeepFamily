from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[3]
PROJECT_LLM_ENDPOINT = (
    "https://aidp.bytedance.net/api/modelhub/online/v2/crawl?api-version=2024-03-01-preview"
)
PROJECT_LLM_MODEL = "gpt-5.5-2026-04-24"


class Settings(BaseSettings):
    """Server-side configuration. Secrets are never exposed through API models."""

    model_config = SettingsConfigDict(
        env_prefix="ASKDU_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Ask, Don't Upload"
    environment_id: str = "coda-community-43"
    catalog_mode: Literal["single", "coda_open_release"] = "single"
    data_root: Path = (
        PROJECT_ROOT / "data/external/coda-bench/communities/community_43/full_community"
    )
    provenance_manifest: Path | None = (
        PROJECT_ROOT / "data/manifests/coda-public-source-provenance-v1.json"
    )
    coda_release_manifest: Path = PROJECT_ROOT / "data/manifests/coda-bench-v1-open-release.json"
    coda_release_root: Path = PROJECT_ROOT / "data/external/coda-bench"
    runtime_root: Path = PROJECT_ROOT / "runtime"
    max_repair_rounds: int = Field(default=3, ge=0, le=20)
    max_concurrent_runs: int = Field(default=2, ge=1, le=16)
    cors_origins: str = "http://localhost:5173,http://localhost:8080"
    trusted_hosts: str = "localhost,127.0.0.1,testserver,api"
    planner_mode: Literal["registry", "model", "agentic"] = "registry"
    planner_max_attempts: int = Field(default=2, ge=1, le=3)
    discovery_max_turns: int = Field(default=16, ge=2, le=40)
    preparation_max_turns: int = Field(default=6, ge=2, le=20)

    # All model-backed project stages use this one pinned provider profile. The
    # deterministic pilot does not require an LLM and therefore never reads a key.
    llm_base_url: str | None = PROJECT_LLM_ENDPOINT
    llm_model: str | None = PROJECT_LLM_MODEL
    llm_api_key: str | None = Field(default=None, repr=False)
    llm_api_style: Literal["azure_chat", "openai_base_url", "direct_chat_completions"] = (
        "azure_chat"
    )
    llm_auth_scheme: Literal["bearer", "api_key"] = "api_key"
    llm_token_field: Literal["max_tokens", "max_completion_tokens"] = "max_completion_tokens"
    # Used only by isolated loopback provider-contract tests. Production
    # preflight rejects this escape hatch.
    llm_allow_test_provider: bool = False
    llm_trust_env_proxy: bool = False
    llm_timeout_seconds: float = Field(default=120.0, ge=1.0, le=600.0)
    llm_max_retries: int = Field(default=2, ge=0, le=10)

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def allowed_hosts(self) -> list[str]:
        hosts = [host.strip() for host in self.trusted_hosts.split(",") if host.strip()]
        if not hosts:
            raise ValueError("ASKDU_TRUSTED_HOSTS must contain at least one host")
        return hosts

    @property
    def llm_configured(self) -> bool:
        return bool(self.llm_base_url and self.llm_model and self.llm_api_key)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
