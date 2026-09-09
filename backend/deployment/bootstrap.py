from __future__ import annotations

from askdu.bootstrap import build_run_service as build_core_run_service
from deployment.config import DeploymentSettings
from deployment.repository import ManagedFileRunRepository
from deployment.service import DeploymentRunService


def build_deployment_run_service(settings: DeploymentSettings) -> DeploymentRunService:
    """Compose lifecycle controls around the unchanged analytical implementation."""

    core = build_core_run_service(settings)
    repository = ManagedFileRunRepository(
        settings.runtime_root / "state",
        settings.runtime_root / "runs",
    )
    # RunService deliberately exposes its persistence port. Substitute the managed
    # adapter before the service is shared or any run can be admitted.
    core.repository = repository
    return DeploymentRunService(core, repository, settings.run_retention_hours)
