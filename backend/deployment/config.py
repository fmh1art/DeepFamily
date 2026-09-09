from __future__ import annotations

from functools import lru_cache

from pydantic import Field

from askdu.config import Settings


class DeploymentSettings(Settings):
    """Public-service settings kept outside the frozen evaluation surface."""

    run_retention_hours: int = Field(default=0, ge=0, le=720)


@lru_cache(maxsize=1)
def get_deployment_settings() -> DeploymentSettings:
    return DeploymentSettings()
