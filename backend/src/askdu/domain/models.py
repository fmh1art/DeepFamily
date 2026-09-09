from __future__ import annotations

from datetime import date, datetime, timezone
from enum import Enum
from typing import Any, Literal
from uuid import uuid4

from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from askdu.domain.plans import DeclarativeAnalysisPlan


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:16]}"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ImmutableStrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Stage(str, Enum):
    QUESTION = "question"
    DISCOVERY = "discovery"
    PREPARATION = "preparation"
    ANALYSIS = "analysis"
    VALIDATION = "validation"
    REPORT = "report"
    STOPPED = "stopped"


class EdgeKind(str, Enum):
    FORWARD = "forward"
    REPAIR = "repair"
    TERMINAL = "terminal"


class RunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    INSUFFICIENT = "insufficient"
    FAILED = "failed"


class DiagnosisKind(str, Enum):
    CAPABILITY_GAP = "capability_gap"
    DATA_GAP = "data_gap"
    BUDGET_EXHAUSTED = "budget_exhausted"


class DiscoveryMode(str, Enum):
    PROGRESSIVE = "progressive"
    FULL_CATALOG = "full_catalog"


class RepairGuidance(str, Enum):
    VIOLATION = "violation"
    STATIC_QUERY = "static_query"


class ObligationType(str, Enum):
    MEASURE = "measure"
    DIMENSION = "dimension"
    COVERAGE = "coverage"
    GRAIN = "grain"
    JOIN = "join"
    STATISTICAL = "statistical"
    EVIDENCE = "evidence"


class ObligationStatus(str, Enum):
    PENDING = "pending"
    SATISFIED = "satisfied"
    VIOLATED = "violated"


class RepairStatus(str, Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"


class AgentRole(str, Enum):
    DISCOVERY = "discovery"
    PREPARATION = "preparation"
    ANALYSIS = "analysis"


class AgentTurnStatus(str, Enum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    OBSERVED = "observed"


class PreparationAttemptStatus(str, Enum):
    MATERIALIZED = "materialized"
    REJECTED = "rejected"
    SELECTED = "selected"


class AnalysisNotebookPhase(str, Enum):
    ANALYZE = "analyze"
    UNDERSTAND = "understand"
    CODE = "code"
    EXECUTE = "execute"
    DEBUG = "debug"
    ANSWER = "answer"
    REPORT = "report"


class AnalysisNotebookStatus(str, Enum):
    PLANNED = "planned"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class EvidenceRef(StrictModel):
    ref_id: str = Field(default_factory=lambda: new_id("evidence"))
    kind: str
    locator: str
    sha256: str | None = None
    description: str


class AnalyticalObligation(StrictModel):
    obligation_id: str = Field(default_factory=lambda: new_id("obligation"))
    type: ObligationType
    description: str
    required: bool = True
    status: ObligationStatus = ObligationStatus.PENDING
    check: str
    expected: dict[str, Any] = Field(default_factory=dict)
    evidence_refs: list[str] = Field(default_factory=list)


class CompilationTrace(StrictModel):
    kind: Literal["registry", "model"] = "registry"
    attempts: int = Field(default=1, ge=1, le=3)
    request_sha256s: list[str] = Field(default_factory=list, max_length=3)
    response_sha256s: list[str] = Field(default_factory=list, max_length=3)
    plan_schema_version: str | None = None


class AnalyticalContract(StrictModel):
    contract_id: str = Field(default_factory=lambda: new_id("contract"))
    question: str
    task_family: str
    search_terms: list[str]
    obligations: list[AnalyticalObligation]
    analysis_plan: DeclarativeAnalysisPlan | None = None
    compilation: CompilationTrace = Field(default_factory=CompilationTrace)
    created_at: datetime = Field(default_factory=utc_now)


class CatalogProvenance(ImmutableStrictModel):
    benchmark_name: str
    benchmark_url: str
    revision: str = Field(pattern=r"^[0-9a-f]{40}$")
    community_id: int = Field(gt=0)
    archive_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    archive_bytes: int = Field(gt=0)
    asset_manifest: str
    asset_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    csv_asset_count: int = Field(gt=0)
    audit_date: date
    data_access_policy: Literal["download_only"]
    source_data_bundled: Literal[False] = False


class SourceProvenance(ImmutableStrictModel):
    dataset_key: str
    title: str
    provider: str
    creator: str
    source_url: str
    license_label: str
    license_status: Literal["declared", "unknown"]
    license_url: str | None = None
    redistribution_policy: Literal["download_only"] = "download_only"


class DataAsset(StrictModel):
    asset_id: str
    relative_path: str
    name: str
    columns: list[str]
    byte_size: int
    file_format: str = "csv"
    tabular: bool = True
    row_count: int | None = None
    sha256: str | None = None
    expected_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    integrity_status: Literal["unregistered", "unverified", "verified"] = "unregistered"
    provenance: SourceProvenance | None = None


class SourceDecision(StrictModel):
    decision_id: str = Field(default_factory=lambda: new_id("source_decision"))
    iteration: int
    selected_source_ids: list[str]
    newly_selected_source_ids: list[str]
    candidate_scores: dict[str, float]
    reason: str
    trigger_violation_id: str | None = None
    evidence_refs: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)


class AgentTrace(StrictModel):
    """Persisted, non-sensitive audit record for one model/tool turn."""

    trace_id: str = Field(default_factory=lambda: new_id("trace"))
    agent: AgentRole
    turn: int = Field(ge=1)
    action: str
    status: AgentTurnStatus
    request_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    response_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    summary: str
    parent_state_ids: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)


class DiscoveryCandidate(StrictModel):
    """One bounded path candidate exposed by a discovery tool observation."""

    asset_id: str | None = None
    relative_path: str
    name: str
    kind: Literal["directory", "file"]
    community: str | None = None
    file_format: str | None = None
    byte_size: int | None = Field(default=None, ge=0)
    score: float | None = None


class DiscoveryHop(StrictModel):
    """A CoDA-style incremental move through the authorized data environment."""

    hop_id: str = Field(default_factory=lambda: new_id("hop"))
    iteration: int = Field(ge=0)
    turn: int = Field(ge=0)
    parent_hop_id: str | None = None
    action: str
    status: AgentTurnStatus
    scope: str
    destination: str | None = None
    query_terms: list[str] = Field(default_factory=list)
    candidates: list[DiscoveryCandidate] = Field(default_factory=list, max_length=100)
    inspected_asset_id: str | None = None
    inspected_path: str | None = None
    inspected_schema: dict[str, str] = Field(default_factory=dict)
    selected_asset_ids: list[str] = Field(default_factory=list)
    summary: str
    error: str | None = None
    created_at: datetime = Field(default_factory=utc_now)


class PreparationOperatorTrace(StrictModel):
    """One DeepPrep-aligned physical operator inside a candidate chain."""

    operator_id: str
    position: int = Field(ge=1)
    operator_type: str
    operator_family: Literal[
        "data_cleaning",
        "column_transformation",
        "table_transformation",
        "other",
    ]
    input_tables: list[str] = Field(default_factory=list)
    output_table: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    input_rows: list[int] = Field(default_factory=list)
    output_rows: int | None = Field(default=None, ge=0)
    output_columns: list[str] = Field(default_factory=list)
    added_columns: list[str] = Field(default_factory=list)
    removed_columns: list[str] = Field(default_factory=list)
    summary: str


class PreparationAttempt(StrictModel):
    """An execution-observed branch in the tree-based preparation search."""

    attempt_id: str = Field(default_factory=lambda: new_id("prep_attempt"))
    turn: int = Field(ge=1)
    candidate_id: str | None = None
    parent_candidate_id: str | None = None
    status: PreparationAttemptStatus
    reason: str
    source_aliases: list[str] = Field(default_factory=list)
    operators: list[PreparationOperatorTrace] = Field(default_factory=list)
    state_id: str | None = None
    output_table: str | None = None
    output_rows: int | None = Field(default=None, ge=0)
    output_columns: list[str] = Field(default_factory=list)
    observation: str
    violation_type: str | None = None
    error: str | None = None
    request_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    response_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    created_at: datetime = Field(default_factory=utc_now)


class AnalysisNotebookStep(StrictModel):
    """A public, execution-grounded DeepAnalyze-style notebook event."""

    step_id: str = Field(default_factory=lambda: new_id("analysis_step"))
    sequence: int = Field(ge=1)
    turn: int = Field(ge=1)
    phase: AnalysisNotebookPhase
    status: AnalysisNotebookStatus
    title: str
    summary: str
    analysis_name: str | None = None
    language: Literal["markdown", "python", "sql", "json", "text"] = "text"
    source_code: str | None = Field(default=None, max_length=30_000)
    parameters: dict[str, Any] = Field(default_factory=dict)
    output: Any = None
    runtime: str | None = None
    duration_ms: float | None = Field(default=None, ge=0)
    state_refs: list[str] = Field(default_factory=list)
    artifact_refs: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)


class MaterializedState(StrictModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True, serialize_by_alias=True)

    state_id: str = Field(default_factory=lambda: new_id("state"))
    iteration: int
    parent_state_ids: list[str] = Field(default_factory=list)
    source_ids: list[str]
    row_count: int
    columns: list[str]
    column_schema: dict[str, str] = Field(
        default_factory=dict,
        validation_alias=AliasChoices("schema", "column_schema"),
        serialization_alias="schema",
    )
    preview_rows: list[dict[str, Any]] = Field(default_factory=list, max_length=8)
    metrics: dict[str, Any] = Field(default_factory=dict)
    evidence_refs: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)


class AnalysisArtifact(StrictModel):
    artifact_id: str = Field(default_factory=lambda: new_id("artifact"))
    kind: str
    name: str
    value: Any
    unit: str | None = None
    display_precision: int | None = Field(default=None, ge=0, le=12)
    source_state_ids: list[str]
    evidence_refs: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)


class SufficiencyViolation(StrictModel):
    violation_id: str = Field(default_factory=lambda: new_id("violation"))
    obligation_ids: list[str]
    type: str
    observed: dict[str, Any]
    expected: dict[str, Any]
    detected_stage: Stage
    responsible_stage: Stage
    evidence_refs: list[str] = Field(default_factory=list)
    resolved: bool = False
    created_at: datetime = Field(default_factory=utc_now)


class RepairGoal(StrictModel):
    repair_goal_id: str = Field(default_factory=lambda: new_id("repair"))
    violation_id: str
    target_stage: Stage
    instruction: str
    search_terms: list[str] = Field(default_factory=list)
    status: RepairStatus = RepairStatus.PENDING
    selected_source_ids: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)


class ReportClaim(StrictModel):
    claim_id: str = Field(default_factory=lambda: new_id("claim"))
    text: str
    value: Any
    artifact_refs: list[str]
    evidence_refs: list[str] = Field(default_factory=list)


class ReportSection(StrictModel):
    """One narrative block grounded in one or more executed artifacts."""

    title: str = Field(min_length=1, max_length=120)
    narrative: str = Field(min_length=1, max_length=2_000)
    artifact_refs: list[str] = Field(min_length=1, max_length=12)


class ReportNarrative(StrictModel):
    """A bounded DeepAnalyze-style synthesis over executed artifacts."""

    title: str = Field(min_length=1, max_length=120)
    executive_summary: str = Field(min_length=1, max_length=2_000)
    executive_artifact_refs: list[str] = Field(min_length=1, max_length=12)
    sections: list[ReportSection] = Field(min_length=1, max_length=8)
    conclusion: str = Field(min_length=1, max_length=2_000)
    conclusion_artifact_refs: list[str] = Field(min_length=1, max_length=12)
    limitations: list[str] = Field(min_length=1, max_length=8)


class Report(StrictModel):
    report_id: str = Field(default_factory=lambda: new_id("report"))
    title: str
    markdown: str
    claims: list[ReportClaim]
    evidence_refs: list[str]
    executive_summary: str = ""
    executive_artifact_refs: list[str] = Field(default_factory=list)
    sections: list[ReportSection] = Field(default_factory=list, max_length=8)
    conclusion: str = ""
    conclusion_artifact_refs: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list, max_length=8)
    created_at: datetime = Field(default_factory=utc_now)


class InsufficiencyDiagnosis(StrictModel):
    diagnosis_id: str = Field(default_factory=lambda: new_id("diagnosis"))
    kind: DiagnosisKind
    summary: str
    unresolved_obligation_ids: list[str]
    attempted_repairs: list[str]
    evidence_refs: list[str]
    created_at: datetime = Field(default_factory=utc_now)


class LifecycleEvent(StrictModel):
    event_id: str = Field(default_factory=lambda: new_id("event"))
    sequence: int
    from_stage: Stage
    to_stage: Stage
    edge_kind: EdgeKind
    summary: str
    object_refs: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)


class RunState(StrictModel):
    run_id: str = Field(default_factory=lambda: new_id("run"))
    environment_id: str
    question: str
    status: RunStatus = RunStatus.PENDING
    current_stage: Stage = Stage.QUESTION
    contract: AnalyticalContract | None = None
    evidence: dict[str, EvidenceRef] = Field(default_factory=dict)
    assets: dict[str, DataAsset] = Field(default_factory=dict)
    agent_traces: list[AgentTrace] = Field(default_factory=list)
    discovery_hops: list[DiscoveryHop] = Field(default_factory=list)
    preparation_attempts: list[PreparationAttempt] = Field(default_factory=list)
    analysis_notebook: list[AnalysisNotebookStep] = Field(default_factory=list)
    source_decisions: list[SourceDecision] = Field(default_factory=list)
    materialized_states: list[MaterializedState] = Field(default_factory=list)
    artifacts: list[AnalysisArtifact] = Field(default_factory=list)
    violations: list[SufficiencyViolation] = Field(default_factory=list)
    repair_goals: list[RepairGoal] = Field(default_factory=list)
    events: list[LifecycleEvent] = Field(default_factory=list)
    report: Report | None = None
    diagnosis: InsufficiencyDiagnosis | None = None
    error: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    def add_event(
        self,
        from_stage: Stage,
        to_stage: Stage,
        edge_kind: EdgeKind,
        summary: str,
        object_refs: list[str] | None = None,
    ) -> LifecycleEvent:
        event = LifecycleEvent(
            sequence=len(self.events) + 1,
            from_stage=from_stage,
            to_stage=to_stage,
            edge_kind=edge_kind,
            summary=summary,
            object_refs=object_refs or [],
        )
        self.events.append(event)
        self.current_stage = to_stage
        self.updated_at = utc_now()
        return event
