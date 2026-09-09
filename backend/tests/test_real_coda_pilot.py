from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from askdu.adapters.catalog import FileCatalog
from askdu.adapters.coda_pilot import format_coda_pilot_answer
from askdu.adapters.provenance import ProvenanceRegistry
from askdu.adapters.repository import FileRunRepository
from askdu.application.orchestrator import RunService
from askdu.domain import (
    DiagnosisKind,
    DiscoveryMode,
    EdgeKind,
    ObligationStatus,
    RepairGuidance,
    RunStatus,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_ROOT = PROJECT_ROOT / "data/external/coda-bench/communities/community_43/full_community"
BENCHMARK_PATH = PROJECT_ROOT / "data/external/coda-bench/coda_bench.json"
PROVENANCE_MANIFEST = PROJECT_ROOT / "data/manifests/coda-public-source-provenance-v1.json"
TASK_IDS = (175, 176, 177, 178, 179, 180, 955, 956, 957, 958, 959, 960, 961, 962, 963)
EXPECTED_DATA_GAP_TASK_IDS = {179}
REPAIR_REQUIRED_TASK_IDS = {175, 955, 959, 960}

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not DATA_ROOT.is_dir(), reason="CoDA community_43 is not downloaded"),
]


@pytest.fixture(scope="module")
def tasks_by_id() -> dict[int, dict[str, Any]]:
    rows = json.loads(BENCHMARK_PATH.read_text(encoding="utf-8"))
    return {int(row["instance_id"]): row for row in rows if int(row["instance_id"]) in TASK_IDS}


@pytest.fixture(scope="module")
def closed_loop_service(tmp_path_factory: pytest.TempPathFactory) -> RunService:
    runtime_root = tmp_path_factory.mktemp("community43-closed-loop")
    registry = ProvenanceRegistry.from_file(PROVENANCE_MANIFEST)
    return RunService(
        environment_id="coda-community-43",
        data_root=DATA_ROOT,
        runtime_root=runtime_root,
        repository=FileRunRepository(runtime_root / "state"),
        max_repair_rounds=2,
        catalog=FileCatalog(
            DATA_ROOT,
            environment_id="coda-community-43",
            provenance_registry=registry,
        ),
    )


@pytest.mark.parametrize("task_id", TASK_IDS)
def test_all_community43_tasks_reach_the_expected_terminal_state(
    task_id: int,
    tasks_by_id: dict[int, dict[str, Any]],
    closed_loop_service: RunService,
) -> None:
    task = tasks_by_id[task_id]
    state = closed_loop_service.run(str(task["question"]))
    repair_edges = sum(event.edge_kind == EdgeKind.REPAIR for event in state.events)

    assert state.error is None
    assert repair_edges == (1 if task_id in REPAIR_REQUIRED_TASK_IDS else 0)

    if task_id in EXPECTED_DATA_GAP_TASK_IDS:
        assert state.status == RunStatus.INSUFFICIENT
        assert state.report is None
        assert state.diagnosis is not None
        assert state.diagnosis.kind == DiagnosisKind.DATA_GAP
        assert not state.assets
        return

    assert state.status == RunStatus.COMPLETED
    assert format_coda_pilot_answer(task_id, state) == task["answer"]
    assert state.diagnosis is None
    assert state.report is not None
    assert all(asset.integrity_status == "verified" for asset in state.assets.values())
    assert all(asset.provenance is not None for asset in state.assets.values())
    assert "download-only" in state.report.markdown
    assert state.contract is not None
    assert all(
        not obligation.required or obligation.status == ObligationStatus.SATISFIED
        for obligation in state.contract.obligations
    )

    artifact_ids = {artifact.artifact_id for artifact in state.artifacts}
    state_ids = {materialized.state_id for materialized in state.materialized_states}
    evidence_ids = set(state.evidence)
    assert artifact_ids
    assert state.report.claims
    assert set(state.report.evidence_refs) <= evidence_ids
    assert all(set(artifact.source_state_ids) <= state_ids for artifact in state.artifacts)
    assert all(set(artifact.evidence_refs) <= evidence_ids for artifact in state.artifacts)
    assert all(set(claim.artifact_refs) <= artifact_ids for claim in state.report.claims)
    assert all(set(claim.evidence_refs) <= evidence_ids for claim in state.report.claims)

    if task_id == 959:
        assert [asset.name for asset in state.assets.values()] == [
            "D5 SHSAT Registrations and Testers.csv",
            "2016 School Explorer.csv",
        ]
        assert "Data Science for Good: PASSNYC" in state.report.markdown
        assert "license metadata: [CC0-1.0]" in state.report.markdown
    if task_id == 960:
        assert [asset.name for asset in state.assets.values()] == [
            "shake shack nutrition.csv",
            "fastfood.csv",
        ]


def test_full_profile_baseline_resolves_coverage_and_preserves_honest_abstention(
    tmp_path: Path,
    tasks_by_id: dict[int, dict[str, Any]],
) -> None:
    runtime_root = tmp_path / "full-profile"
    registry = ProvenanceRegistry.from_file(PROVENANCE_MANIFEST)
    service = RunService(
        environment_id="coda-community-43",
        data_root=DATA_ROOT,
        runtime_root=runtime_root,
        repository=FileRunRepository(runtime_root / "state"),
        max_repair_rounds=0,
        discovery_mode=DiscoveryMode.FULL_CATALOG,
        catalog=FileCatalog(
            DATA_ROOT,
            environment_id="coda-community-43",
            provenance_registry=registry,
        ),
    )
    catalog_size = len(service.catalog.index())

    coverage_state = service.run(str(tasks_by_id[960]["question"]))
    gap_state = service.run(str(tasks_by_id[179]["question"]))

    assert catalog_size == 10
    assert coverage_state.status == RunStatus.COMPLETED
    assert format_coda_pilot_answer(960, coverage_state) == tasks_by_id[960]["answer"]
    assert len(coverage_state.assets) == catalog_size
    assert not any(event.edge_kind == EdgeKind.REPAIR for event in coverage_state.events)

    assert gap_state.status == RunStatus.INSUFFICIENT
    assert gap_state.diagnosis is not None
    assert gap_state.diagnosis.kind == DiagnosisKind.DATA_GAP
    assert len(gap_state.assets) == catalog_size
    assert not any(event.edge_kind == EdgeKind.REPAIR for event in gap_state.events)


def test_static_retry_ablation_reuses_initial_terms_and_misses_targeted_source(
    tmp_path: Path,
    tasks_by_id: dict[int, dict[str, Any]],
) -> None:
    runtime_root = tmp_path / "static-retry"
    registry = ProvenanceRegistry.from_file(PROVENANCE_MANIFEST)
    service = RunService(
        environment_id="coda-community-43",
        data_root=DATA_ROOT,
        runtime_root=runtime_root,
        repository=FileRunRepository(runtime_root / "state"),
        max_repair_rounds=2,
        repair_guidance=RepairGuidance.STATIC_QUERY,
        catalog=FileCatalog(
            DATA_ROOT,
            environment_id="coda-community-43",
            provenance_registry=registry,
        ),
    )

    state = service.run(str(tasks_by_id[959]["question"]))

    assert state.status == RunStatus.INSUFFICIENT
    assert state.diagnosis is not None
    assert state.diagnosis.kind == DiagnosisKind.BUDGET_EXHAUSTED
    assert [asset.name for asset in state.assets.values()] == [
        "D5 SHSAT Registrations and Testers.csv",
        "2017-2018 SHSAT Admissions Test Offers By Sending School.csv",
        "2010-2016-school-safety-report.csv",
    ]
    assert len(state.repair_goals) == 2
    assert all(goal.search_terms == state.contract.search_terms for goal in state.repair_goals)
    assert all("Static-retry ablation" in goal.instruction for goal in state.repair_goals)
    assert all(
        "unchanged initial question terms" in decision.reason
        for decision in state.source_decisions[1:]
    )
