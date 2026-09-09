from __future__ import annotations

from typing import Literal

from pydantic import Field

from askdu.api.schemas import EnvironmentSummary


class DeploymentEnvironmentSummary(EnvironmentSummary):
    """Environment metadata needed for informed public submissions."""

    run_retention_hours: int = Field(ge=0, le=720)
    run_deletion_supported: Literal[True] = True
