from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from askdu.adapters.repository import FileRunRepository
from askdu.application.compiler import QuestionCompiler
from askdu.application.orchestrator import RunCapacityError, RunService
from askdu.domain import AnalyticalContract, DiagnosisKind, EdgeKind, RunStatus, Stage
from tests.conftest import (
    ECONOMIC_NEED_QUESTION,
    OFFER_DEMOGRAPHICS_QUESTION,
    PILOT_QUESTION,
)


def build_service(data_root: Path, runtime_root: Path) -> RunService:
    return RunService(
        environment_id="test-community",
        data_root=data_root,
        runtime_root=runtime_root,
        repository=FileRunRepository(runtime_root / "state"),
        max_repair_rounds=2,
    )


def test_question_only_vertical_slice_closes_the_loop(
    sample_environment: Path, tmp_path: Path
) -> None:
    service = build_service(sample_environment, tmp_path / "runtime")

    state = service.run(PILOT_QUESTION)

    assert state.status == RunStatus.COMPLETED
    assert state.report is not None
    assert "provenance unregistered; no license inferred" in state.report.markdown
    assert len(state.source_decisions) == 2
    assert [asset.name for asset in state.assets.values()] == [
        "D5 SHSAT Registrations and Testers.csv",
        "2016 School Explorer.csv",
    ]
    assert len(state.violations) == 1
    assert state.violations[0].type == "missing_analytical_columns"
    assert state.violations[0].resolved is True
    assert any(
        event.edge_kind == EdgeKind.REPAIR
        and event.from_stage == Stage.ANALYSIS
        and event.to_stage == Stage.DISCOVERY
        for event in state.events
    )
    values = {artifact.name: artifact.value for artifact in state.artifacts}
    assert values == pytest.approx(
        {
            "pearson_percent_asian": 1.0,
            "pearson_percent_black_hispanic": -1.0,
            "pearson_percent_white": 1.0,
        }
    )
    persisted = service.get(state.run_id)
    assert persisted is not None
    assert persisted.model_dump() == state.model_dump()


def test_unsupported_question_returns_explicit_diagnosis(
    sample_environment: Path, tmp_path: Path
) -> None:
    service = build_service(sample_environment, tmp_path / "runtime")

    state = service.run("How many library branches are open on Sunday?")

    assert state.status == RunStatus.INSUFFICIENT
    assert state.report is None
    assert state.diagnosis is not None
    assert state.diagnosis.kind == DiagnosisKind.CAPABILITY_GAP
    assert "no executable analysis adapter" in state.diagnosis.summary.lower()


def test_concurrent_run_admission_is_bounded(
    sample_environment: Path,
    tmp_path: Path,
) -> None:
    started = threading.Event()
    release = threading.Event()
    delegate = QuestionCompiler()

    class BlockingCompiler:
        def compile(self, question: str) -> AnalyticalContract:
            started.set()
            if not release.wait(timeout=5):
                raise RuntimeError("test compiler was not released")
            return delegate.compile(question)

    runtime_root = tmp_path / "runtime"
    service = RunService(
        environment_id="test-community",
        data_root=sample_environment,
        runtime_root=runtime_root,
        repository=FileRunRepository(runtime_root / "state"),
        max_concurrent_runs=1,
        compiler=BlockingCompiler(),
    )

    with ThreadPoolExecutor(max_workers=1) as executor:
        first = executor.submit(service.run, PILOT_QUESTION)
        assert started.wait(timeout=2)
        try:
            with pytest.raises(RunCapacityError, match="currently occupied"):
                service.run(PILOT_QUESTION)
        finally:
            release.set()
        assert first.result(timeout=10).status == RunStatus.COMPLETED


def test_economic_need_count_repairs_missing_school_dimension(
    sample_environment: Path, tmp_path: Path
) -> None:
    service = build_service(sample_environment, tmp_path / "runtime")

    state = service.run(ECONOMIC_NEED_QUESTION)

    assert state.status == RunStatus.COMPLETED, state.error
    assert [asset.name for asset in state.assets.values()] == [
        "D5 SHSAT Registrations and Testers.csv",
        "2016 School Explorer.csv",
    ]
    assert state.artifacts[0].name == "final_record_count"
    assert state.artifacts[0].value == 4
    assert state.materialized_states[-1].metrics["join_coverage"] == 1.0
    assert state.violations[0].type == "missing_analytical_columns"


def test_offer_demographics_repairs_missing_percentage_dimensions(
    sample_environment: Path, tmp_path: Path
) -> None:
    service = build_service(sample_environment, tmp_path / "runtime")

    state = service.run(OFFER_DEMOGRAPHICS_QUESTION)

    assert state.status == RunStatus.COMPLETED, state.error
    assert [asset.name for asset in state.assets.values()] == [
        "2017-2018 SHSAT Admissions Test Offers By Sending School.csv",
        "2016 School Explorer.csv",
    ]
    values = {artifact.name: artifact.value for artifact in state.artifacts}
    assert values == pytest.approx(
        {
            "mean_percent_black_hispanic": 25.0,
            "mean_percent_white": 30.0,
            "mean_percent_asian": 25.0,
        }
    )
    assert state.materialized_states[-1].metrics["join_coverage"] == 1.0
    assert state.violations[0].type == "missing_analytical_columns"
