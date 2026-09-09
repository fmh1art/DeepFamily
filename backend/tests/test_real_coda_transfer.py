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
from askdu.domain import EdgeKind, ObligationStatus, RunStatus

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_ROOT = PROJECT_ROOT / "data/external/coda-bench/communities/community_52/full_community"
BENCHMARK_PATH = PROJECT_ROOT / "data/external/coda-bench/coda_bench.json"
PROVENANCE_MANIFEST = PROJECT_ROOT / "data/manifests/coda-public-source-provenance-v1.json"
TASK_IDS = (590, 591)
EXPECTED_SOURCES = {
    590: "unemployed_population_1978-12_to_2023-07.csv",
    591: "wages_by_education.csv",
}

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not DATA_ROOT.is_dir(), reason="CoDA community_52 is not downloaded"),
]


@pytest.fixture(scope="module")
def tasks_by_id() -> dict[int, dict[str, Any]]:
    rows = json.loads(BENCHMARK_PATH.read_text(encoding="utf-8"))
    return {int(row["instance_id"]): row for row in rows if int(row["instance_id"]) in TASK_IDS}


@pytest.fixture(scope="module")
def service(tmp_path_factory: pytest.TempPathFactory) -> RunService:
    runtime_root = tmp_path_factory.mktemp("community52-transfer")
    registry = ProvenanceRegistry.from_file(PROVENANCE_MANIFEST)
    return RunService(
        environment_id="coda-community-52",
        data_root=DATA_ROOT,
        runtime_root=runtime_root,
        repository=FileRunRepository(runtime_root / "state"),
        max_repair_rounds=2,
        catalog=FileCatalog(
            DATA_ROOT,
            environment_id="coda-community-52",
            provenance_registry=registry,
        ),
    )


@pytest.mark.parametrize("task_id", TASK_IDS)
def test_community52_transfer_tasks_match_the_benchmark(
    task_id: int,
    tasks_by_id: dict[int, dict[str, Any]],
    service: RunService,
) -> None:
    task = tasks_by_id[task_id]

    state = service.run(str(task["question"]))

    assert state.status == RunStatus.COMPLETED, state.error
    assert state.error is None
    assert format_coda_pilot_answer(task_id, state) == task["answer"]
    assert [asset.name for asset in state.assets.values()] == [EXPECTED_SOURCES[task_id]]
    assert not any(event.edge_kind == EdgeKind.REPAIR for event in state.events)
    assert state.contract is not None
    assert all(
        not obligation.required or obligation.status == ObligationStatus.SATISFIED
        for obligation in state.contract.obligations
    )
    assert state.report is not None
    assert all(asset.integrity_status == "verified" for asset in state.assets.values())
    assert all(asset.provenance is not None for asset in state.assets.values())
    assert "download-only" in state.report.markdown
    assert all(claim.artifact_refs and claim.evidence_refs for claim in state.report.claims)
