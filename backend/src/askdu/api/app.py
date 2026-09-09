from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Response, status
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from askdu import __version__
from askdu.api.redaction import public_run_state
from askdu.api.schemas import (
    EnvironmentSummary,
    ExampleQuestion,
    HealthResponse,
    ReadinessResponse,
    ReleaseCoverage,
    RunCreate,
)
from askdu.application.examples import demo_questions_for_environment
from askdu.application.orchestrator import RunCapacityError, RunService
from askdu.bootstrap import build_run_service
from askdu.config import Settings, get_settings
from askdu.domain import RunState


@lru_cache(maxsize=1)
def get_run_service() -> RunService:
    return build_run_service(get_settings())


RunServiceDependency = Annotated[RunService, Depends(get_run_service)]
_public_run_state = public_run_state


def _asset_summary(service: RunService) -> tuple[int, int, dict[str, int]]:
    assets = service.catalog.index().values()
    formats: dict[str, int] = {}
    tabular = 0
    for asset in assets:
        formats[asset.file_format] = formats.get(asset.file_format, 0) + 1
        tabular += int(asset.tabular)
    return sum(formats.values()), tabular, dict(sorted(formats.items()))


def _release_coverage(service: RunService) -> ReleaseCoverage | None:
    registry = getattr(service.catalog, "registry", None)
    installed = getattr(service.catalog, "installed_community_ids", None)
    if registry is None or installed is None:
        return None
    manifest = registry.manifest
    return ReleaseCoverage(
        revision=manifest.revision,
        published_communities=manifest.published.community_count,
        open_runtime_communities=manifest.open_runtime.community_count,
        installed_open_communities=len(installed),
        published_tasks=manifest.published.task_count,
        open_runtime_tasks=manifest.open_runtime.task_count,
        source_datasets=manifest.open_runtime.source_dataset_count,
        sealed_evaluation_communities=manifest.sealed_community_count,
    )


def create_app(settings: Settings | None = None) -> FastAPI:
    active_settings = settings or get_settings()
    configured_service: RunService | None = None
    if settings is not None:
        configured_service = build_run_service(active_settings)

    application = FastAPI(
        title=active_settings.app_name,
        version=__version__,
        description="Question-only analytics with execution-grounded cross-stage repair.",
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=active_settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )
    application.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=active_settings.allowed_hosts,
    )

    @application.get("/healthz", response_model=HealthResponse, tags=["operations"])
    def health() -> HealthResponse:
        return HealthResponse(status="ok", version=__version__)

    @application.get("/readyz", response_model=ReadinessResponse, tags=["operations"])
    def readiness(service: RunServiceDependency) -> ReadinessResponse:
        assets = service.catalog.index()
        return ReadinessResponse(
            status="ready",
            version=__version__,
            environment_id=service.environment_id,
            csv_assets=sum(asset.file_format == "csv" for asset in assets.values()),
        )

    @application.get(
        "/api/v1/environments/current",
        response_model=EnvironmentSummary,
        tags=["environments"],
    )
    def environment(
        service: RunServiceDependency,
    ) -> EnvironmentSummary:
        assets = service.catalog.index()
        asset_count, tabular_assets, file_formats = _asset_summary(service)
        return EnvironmentSummary(
            environment_id=service.environment_id,
            available=True,
            csv_assets=sum(asset.file_format == "csv" for asset in assets.values()),
            asset_count=asset_count,
            tabular_assets=tabular_assets,
            file_formats=file_formats,
            planner_mode=service.planner_mode,
            catalog_provenance=service.catalog.catalog_provenance,
            release_coverage=_release_coverage(service),
            example_questions=[
                ExampleQuestion(
                    task_id=example.task_id,
                    label=example.label,
                    question=example.question,
                )
                for example in demo_questions_for_environment(
                    service.environment_id,
                    service.planner_mode,
                )
            ],
        )

    @application.post(
        "/api/v1/runs",
        response_model=RunState,
        status_code=status.HTTP_201_CREATED,
        tags=["runs"],
    )
    def create_run(
        request: RunCreate,
        response: Response,
        service: RunServiceDependency,
        background: bool = False,
    ) -> RunState:
        try:
            run = service.submit(request.question) if background else service.run(request.question)
        except RunCapacityError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Run capacity is busy; retry shortly.",
                headers={"Retry-After": "5"},
            ) from exc
        if background:
            response.status_code = status.HTTP_202_ACCEPTED
        return _public_run_state(run)

    @application.get("/api/v1/runs/{run_id}", response_model=RunState, tags=["runs"])
    def get_run(
        run_id: str,
        service: RunServiceDependency,
    ) -> RunState:
        try:
            run = service.get(run_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if run is None:
            raise HTTPException(status_code=404, detail="Run not found")
        return _public_run_state(run)

    if configured_service is not None:
        application.dependency_overrides[get_run_service] = lambda: configured_service
    return application


app = create_app()
