from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from askdu.domain import CatalogProvenance


class RunCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=10, max_length=4000)


class ExampleQuestion(BaseModel):
    task_id: int
    label: str
    question: str


class ReleaseCoverage(BaseModel):
    revision: str
    published_communities: int
    open_runtime_communities: int
    installed_open_communities: int
    published_tasks: int
    open_runtime_tasks: int
    source_datasets: int
    sealed_evaluation_communities: int


class EnvironmentSummary(BaseModel):
    environment_id: str
    available: bool
    csv_assets: int
    asset_count: int
    tabular_assets: int
    file_formats: dict[str, int]
    planner_mode: Literal["registry", "model", "agentic"]
    catalog_provenance: CatalogProvenance | None
    release_coverage: ReleaseCoverage | None = None
    example_questions: list[ExampleQuestion]


class HealthResponse(BaseModel):
    status: str
    version: str


class ReadinessResponse(BaseModel):
    status: Literal["ready"]
    version: str
    environment_id: str
    csv_assets: int
