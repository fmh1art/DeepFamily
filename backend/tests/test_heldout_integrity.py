from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from askdu import heldout_integrity as integrity

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def load_script(directory: str, name: str) -> ModuleType:
    path = PROJECT_ROOT / directory / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"askdu_test_{name}", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load {name}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


runner = load_script("experiments", "run_coda_heldout_v1")
scorer = load_script("experiments", "score_coda_heldout_v1")
unblinder = load_script("scripts", "unblind_coda_heldout")


def write_manifest(project_root: Path, data_root: Path) -> Path:
    manifest = project_root / "data/manifests/extracted.sha256"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"{integrity.sha256_file(path)}  {path.relative_to(project_root).as_posix()}"
        for path in sorted(item for item in data_root.rglob("*") if item.is_file())
    ]
    manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return manifest


def test_checked_in_frozen_plan_is_checksum_bound_and_well_formed() -> None:
    protocol = integrity.load_json_mapping(
        PROJECT_ROOT / "data/pilots/heldout-v1.json", "checked-in protocol"
    )
    plan = integrity.load_frozen_plan(protocol, PROJECT_ROOT)
    integrity.require_matching_plan_section(protocol, plan, "benchmark")
    integrity.require_matching_plan_section(protocol, plan, "selection")
    assert tuple(plan["selection"]["task_ids"]) == runner.TASK_IDS


def attach_frozen_plan(
    project_root: Path,
    protocol: dict[str, object],
    *,
    paths: dict[str, object],
    execution: dict[str, object],
) -> dict[str, object]:
    benchmark = {
        "name": "FixtureBench",
        "repository": "fixture/repository",
        "revision": "a" * 40,
        "metadata_file": "data/fixture-benchmark.json",
        "metadata_sha256": "a" * 64,
        "archive_file": "data/fixture-archive.tar.zst",
        "archive_bytes": 1,
        "archive_sha256": "b" * 64,
        **dict(protocol.get("benchmark", {})),
    }
    raw_selection = dict(protocol.get("selection", {}))
    task_ids = list(raw_selection.get("task_ids", [1]))
    selection = {
        "community_id": raw_selection.get("community_id", 45),
        "task_ids": task_ids,
        "task_count": raw_selection.get("task_count", len(task_ids)),
        "selection_rule": raw_selection.get("selection_rule", "complete fixture set"),
    }
    run_directory = str(paths.get("run_directory", "experiments/results/heldout"))
    frozen_paths = {
        "questions_file": "data/pilots/questions.json",
        "extracted_root": "data/external/community_45",
        "data_root": "data/external/community_45/full_community",
        "extracted_manifest": "data/manifests/community_45.sha256",
        "run_directory": run_directory,
        "first_pass_marker": f"{run_directory}/FIRST_PASS_STARTED.json",
        "first_pass_summary": f"{run_directory}/sealed-summary-without-oracle.json",
        "first_pass_seal": f"{run_directory}/seal.sha256",
        "oracle_marker": f"{run_directory}/ORACLE_SCORING_STARTED.json",
        "score_artifact": f"{run_directory}/scored-after-oracle-unsealing.json",
        **paths,
    }
    frozen_execution = {
        "model": "fixture-model",
        "endpoint_sha256": "c" * 64,
        "api_style": "direct_chat_completions",
        "auth_scheme": "api_key",
        "token_field": "max_completion_tokens",
        "trust_environment_proxy": False,
        "timeout_seconds": 120.0,
        "transport_retries": 2,
        "temperature": 0.0,
        "planner_max_attempts": 2,
        "max_repair_rounds": 2,
        "max_concurrent_runs": 1,
        **execution,
    }
    protocol["benchmark"] = benchmark
    protocol["selection"] = selection
    plan = {
        "schema_version": "askdu-heldout-plan-v1",
        "protocol_id": protocol["protocol_id"],
        "benchmark": benchmark,
        "selection": selection,
        "paths": frozen_paths,
        "execution": frozen_execution,
    }
    plan_path = project_root / "data/pilots/heldout-v1-plan.json"
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    plan_path.write_text(
        json.dumps(plan, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    protocol["frozen_plan"] = {
        "file": plan_path.relative_to(project_root).as_posix(),
        "sha256": integrity.sha256_file(plan_path),
    }
    return plan


def test_extracted_manifest_requires_exact_untampered_census(tmp_path: Path) -> None:
    data_root = tmp_path / "data/extracted"
    (data_root / "nested").mkdir(parents=True)
    first = data_root / "first.csv"
    second = data_root / "nested/second.csv"
    first.write_text("a\n1\n", encoding="utf-8")
    second.write_text("b\n2\n", encoding="utf-8")
    manifest = write_manifest(tmp_path, data_root)
    manifest_sha256 = integrity.sha256_file(manifest)

    verified = integrity.verify_data_manifest(
        data_root=data_root,
        manifest_path=manifest,
        project_root=tmp_path,
        expected_manifest_sha256=manifest_sha256,
        expected_file_count=2,
    )
    assert verified.file_count == 2

    first.write_text("a\nchanged\n", encoding="utf-8")
    with pytest.raises(integrity.HeldoutIntegrityError, match="file checksum mismatch"):
        integrity.verify_data_manifest(
            data_root=data_root,
            manifest_path=manifest,
            project_root=tmp_path,
            expected_manifest_sha256=manifest_sha256,
            expected_file_count=2,
        )

    first.write_text("a\n1\n", encoding="utf-8")
    (data_root / "unrecorded.csv").write_text("c\n3\n", encoding="utf-8")
    with pytest.raises(integrity.HeldoutIntegrityError, match="census mismatch"):
        integrity.verify_data_manifest(
            data_root=data_root,
            manifest_path=manifest,
            project_root=tmp_path,
            expected_manifest_sha256=manifest_sha256,
            expected_file_count=2,
        )


def test_extracted_manifest_rejects_duplicate_and_symlink_entries(tmp_path: Path) -> None:
    data_root = tmp_path / "data/extracted"
    data_root.mkdir(parents=True)
    source = data_root / "source.csv"
    source.write_text("a\n1\n", encoding="utf-8")
    relative = source.relative_to(tmp_path).as_posix()
    line = f"{integrity.sha256_file(source)}  {relative}\n"
    manifest = tmp_path / "manifest.sha256"
    manifest.write_text(line + line, encoding="utf-8")

    with pytest.raises(integrity.HeldoutIntegrityError, match="repeats path"):
        integrity.verify_data_manifest(
            data_root=data_root,
            manifest_path=manifest,
            project_root=tmp_path,
            expected_manifest_sha256=integrity.sha256_file(manifest),
            expected_file_count=2,
        )

    manifest = write_manifest(tmp_path, data_root)
    link = data_root / "alias.csv"
    try:
        link.symlink_to(source)
    except OSError:
        pytest.skip("symbolic links are unavailable on this filesystem")
    with pytest.raises(integrity.HeldoutIntegrityError, match="symbolic link"):
        integrity.verify_data_manifest(
            data_root=data_root,
            manifest_path=manifest,
            project_root=tmp_path,
            expected_manifest_sha256=integrity.sha256_file(manifest),
            expected_file_count=1,
        )


def test_unblinding_redactor_orders_tasks_and_rejects_ambiguous_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(unblinder, "PROJECT_ROOT", tmp_path)
    metadata = tmp_path / "metadata.json"
    rows = [
        {"instance_id": task_id, "question": f"Question {task_id}?", "answer": "hidden"}
        for task_id in reversed(unblinder.TASK_IDS)
    ]
    metadata.write_text(json.dumps(rows) + "\n", encoding="utf-8")
    questions = unblinder.selected_questions(metadata)
    assert tuple(row["task_id"] for row in questions) == unblinder.TASK_IDS
    assert all(set(row) == {"task_id", "question"} for row in questions)

    rows.append(dict(rows[0]))
    metadata.write_text(json.dumps(rows) + "\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="repeats task ID"):
        unblinder.selected_questions(metadata)
    with pytest.raises(RuntimeError, match="unsafe paths"):
        unblinder.validate_members("data/community_45/file.csv\n../escape.csv\n")


def test_unblinding_manifest_covers_the_complete_extracted_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(unblinder, "PROJECT_ROOT", tmp_path)
    extracted = tmp_path / "data/community_45"
    nested = extracted / "full_community/source"
    nested.mkdir(parents=True)
    asset = nested / "fixture.csv"
    asset.write_text("a\n1\n", encoding="utf-8")
    assert unblinder.extracted_manifest(extracted) == (
        f"{integrity.sha256_file(asset)}  {asset.relative_to(tmp_path).as_posix()}\n"
    )


def test_seal_detects_mutation_and_incomplete_required_census(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    marker = run_dir / "FIRST_PASS_STARTED.json"
    summary = run_dir / "sealed-summary-without-oracle.json"
    marker.write_text("{}\n", encoding="utf-8")
    summary.write_text("{}\n", encoding="utf-8")
    verification = integrity.build_seal(run_dir, run_dir / "seal.sha256")
    assert verification.file_count == 2

    with pytest.raises(integrity.HeldoutIntegrityError, match="omits 1 required"):
        integrity.verify_seal(run_dir, required_paths=("runs/task-31.json",))

    summary.write_text('{"mutated": true}\n', encoding="utf-8")
    with pytest.raises(integrity.HeldoutIntegrityError, match="changed"):
        integrity.verify_seal(run_dir)


def test_protocol_transition_is_atomic_and_state_checked(tmp_path: Path) -> None:
    protocol_path = tmp_path / "heldout.json"
    protocol_path.write_text(
        json.dumps(
            {
                "protocol_id": "fixture",
                "status": "unblinded_not_run",
                "unblinding": {"status": "complete"},
                "results": {"status": "not_run", "preserved": True},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    transitioned = integrity.transition_protocol(
        protocol_path,
        expected_status="unblinded_not_run",
        next_status="first_pass_sealed",
        expected_protocol_id="fixture",
        results_update={"artifact": "result.json"},
    )
    assert transitioned["results"]["preserved"] is True
    assert transitioned["results"]["artifact"] == "result.json"
    assert transitioned["status"] == "first_pass_sealed"

    before = protocol_path.read_bytes()
    with pytest.raises(integrity.HeldoutIntegrityError, match="transition requires"):
        integrity.transition_protocol(
            protocol_path,
            expected_status="unblinded_not_run",
            next_status="first_pass_sealed",
            expected_protocol_id="fixture",
            results_update={},
        )
    assert protocol_path.read_bytes() == before


def test_frozen_plan_checksum_binds_selection_paths_and_execution(tmp_path: Path) -> None:
    protocol: dict[str, object] = {
        "protocol_id": "fixture",
        "benchmark": {"revision": "a" * 40},
        "selection": {"task_ids": [1, 2]},
    }
    plan = attach_frozen_plan(
        tmp_path,
        protocol,
        paths={"run_directory": "experiments/results/heldout"},
        execution={"model": "fixture-model"},
    )
    assert integrity.load_frozen_plan(protocol, tmp_path) == plan
    integrity.require_matching_plan_section(protocol, plan, "selection")

    plan_path = integrity.resolve_recorded_path(tmp_path, protocol["frozen_plan"]["file"], "plan")
    plan_path.write_text("{}\n", encoding="utf-8")
    with pytest.raises(integrity.HeldoutIntegrityError, match="checksum mismatch"):
        integrity.load_frozen_plan(protocol, tmp_path)


def test_frozen_model_configuration_is_exact_and_secret_free() -> None:
    endpoint = "https://provider.invalid/exact-endpoint?version=1"
    settings = SimpleNamespace(
        llm_base_url=endpoint,
        llm_model="fixture-model",
        llm_api_style="direct_chat_completions",
        llm_auth_scheme="api_key",
        llm_token_field="max_completion_tokens",
        llm_trust_env_proxy=False,
        llm_timeout_seconds=120.0,
        llm_max_retries=2,
        planner_max_attempts=2,
        max_repair_rounds=2,
        max_concurrent_runs=1,
    )
    plan = {
        "execution": {
            "model": "fixture-model",
            "endpoint_sha256": hashlib.sha256(endpoint.encode()).hexdigest(),
            "api_style": "direct_chat_completions",
            "auth_scheme": "api_key",
            "token_field": "max_completion_tokens",
            "trust_environment_proxy": False,
            "timeout_seconds": 120.0,
            "transport_retries": 2,
            "temperature": 0.0,
            "planner_max_attempts": 2,
            "max_repair_rounds": 2,
            "max_concurrent_runs": 1,
        }
    }
    assert integrity.validate_execution_settings(plan, settings) == plan["execution"]

    settings.llm_model = "different-model"
    with pytest.raises(integrity.HeldoutIntegrityError, match=r"plan: model$"):
        integrity.validate_execution_settings(plan, settings)


def test_runner_rejects_tampered_data_before_building_model_service(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(runner, "PROJECT_ROOT", tmp_path)
    frozen_surface = "2" * 64
    monkeypatch.setattr(runner, "current_surface_hash", lambda: frozen_surface)
    extracted_root = tmp_path / "data/community_45"
    data_root = extracted_root / "full_community"
    data_root.mkdir(parents=True)
    data_file = data_root / "fixture.csv"
    data_file.write_text("a\n1\n", encoding="utf-8")
    manifest = write_manifest(tmp_path, extracted_root)
    manifest_sha256 = integrity.sha256_file(manifest)
    questions = tmp_path / "data/heldout-questions.json"
    questions.write_text(
        json.dumps(
            {
                "protocol_id": "fixture",
                "task_ids": list(runner.TASK_IDS),
                "tasks": [
                    {"task_id": task_id, "question": f"Question {task_id}?"}
                    for task_id in runner.TASK_IDS
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    output_dir = tmp_path / "experiments/results/heldout"
    protocol = {
        "protocol_id": "fixture",
        "status": "unblinded_not_run",
        "benchmark": {"revision": "a" * 40},
        "selection": {
            "task_ids": list(runner.TASK_IDS),
            "task_count": len(runner.TASK_IDS),
        },
        "implementation_freeze": {"pre_unblinding_sha256": frozen_surface},
        "unblinding": {
            "status": "complete",
            "questions_file": questions.relative_to(tmp_path).as_posix(),
            "questions_sha256": integrity.sha256_file(questions),
            "extracted_root": extracted_root.relative_to(tmp_path).as_posix(),
            "data_root": data_root.relative_to(tmp_path).as_posix(),
            "extracted_manifest": manifest.relative_to(tmp_path).as_posix(),
            "extracted_manifest_sha256": manifest_sha256,
            "extracted_file_count": 1,
        },
        "results": {
            "status": "not_run",
            "planned_run_directory": output_dir.relative_to(tmp_path).as_posix(),
        },
    }
    attach_frozen_plan(
        tmp_path,
        protocol,
        paths={
            "questions_file": questions.relative_to(tmp_path).as_posix(),
            "extracted_root": extracted_root.relative_to(tmp_path).as_posix(),
            "data_root": data_root.relative_to(tmp_path).as_posix(),
            "extracted_manifest": manifest.relative_to(tmp_path).as_posix(),
            "run_directory": output_dir.relative_to(tmp_path).as_posix(),
        },
        execution={},
    )
    protocol["unblinding"]["plan_sha256"] = protocol["frozen_plan"]["sha256"]
    protocol_path = tmp_path / "data/protocol.json"
    protocol_path.write_text(json.dumps(protocol) + "\n", encoding="utf-8")
    data_file.write_text("a\ntampered\n", encoding="utf-8")
    service_built = False

    def forbidden_service_build(*args, **kwargs):  # type: ignore[no-untyped-def]
        nonlocal service_built
        service_built = True
        raise AssertionError("model service must not be built")

    monkeypatch.setattr(runner, "build_run_service", forbidden_service_build)
    args = argparse.Namespace(
        data_root=data_root,
        questions=questions,
        protocol=protocol_path,
        output_dir=output_dir,
    )
    with pytest.raises(integrity.HeldoutIntegrityError, match="file checksum mismatch"):
        runner.execute(args)
    assert service_built is False
    assert not (output_dir / "FIRST_PASS_STARTED.json").exists()


def test_first_pass_finalizer_seals_all_tasks_and_advances_protocol(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(runner, "PROJECT_ROOT", tmp_path)
    output_dir = tmp_path / "experiments/results/heldout"
    runs = output_dir / "runs"
    runs.mkdir(parents=True)
    questions_sha256 = "1" * 64
    surface_sha256 = "2" * 64
    data_manifest = integrity.ManifestVerification("3" * 64, 2, ())
    protocol = {
        "protocol_id": "fixture",
        "status": "unblinded_not_run",
        "implementation_freeze": {
            "pre_unblinding_sha256": surface_sha256,
        },
        "unblinding": {
            "questions_sha256": questions_sha256,
        },
        "results": {
            "status": "not_run",
            "planned_run_directory": "experiments/results/heldout",
        },
    }
    execution = {
        "model": "fixture-model",
        "temperature": 0.0,
        "planner_max_attempts": 2,
        "max_repair_rounds": 2,
    }
    plan = attach_frozen_plan(
        tmp_path,
        protocol,
        paths={"run_directory": "experiments/results/heldout"},
        execution=execution,
    )
    protocol_path = tmp_path / "protocol.json"
    protocol_path.write_text(json.dumps(protocol) + "\n", encoding="utf-8")
    bindings = {
        "protocol_id": "fixture",
        "plan_sha256": protocol["frozen_plan"]["sha256"],
        "surface_sha256": surface_sha256,
        "questions_sha256": questions_sha256,
        "data_manifest_sha256": data_manifest.manifest_sha256,
        "data_file_count": data_manifest.file_count,
        "execution_config_sha256": integrity.canonical_json_sha256(plan["execution"]),
        "task_ids": list(runner.TASK_IDS),
        "model": "fixture-model",
    }
    (output_dir / "FIRST_PASS_STARTED.json").write_text(
        json.dumps(bindings) + "\n", encoding="utf-8"
    )
    summary = {
        **bindings,
        "task_ids": list(runner.TASK_IDS),
        "temperature": 0.0,
        "planner_max_attempts": 2,
        "max_repair_rounds": 2,
        "completed_at": "2026-09-06T15:00:00+08:00",
        "results": [{"task_id": task_id, "prediction": "fixture"} for task_id in runner.TASK_IDS],
    }
    (output_dir / "sealed-summary-without-oracle.json").write_text(
        json.dumps(summary) + "\n", encoding="utf-8"
    )
    for task_id in runner.TASK_IDS:
        (runs / f"task-{task_id}.json").write_text("{}\n", encoding="utf-8")
    integrity.build_seal(output_dir, output_dir / "seal.sha256")

    updated = runner.finalize_first_pass_protocol(
        protocol_path=protocol_path,
        output_dir=output_dir,
        protocol=protocol,
        data_manifest=data_manifest,
    )
    assert updated["status"] == "first_pass_sealed"
    assert updated["results"]["sealed_file_count"] == len(runner.TASK_IDS) + 2
    assert integrity.sha256_file(output_dir / "seal.sha256") == updated["results"]["seal_sha256"]

    with pytest.raises(integrity.HeldoutIntegrityError, match="transition requires"):
        runner.finalize_first_pass_protocol(
            protocol_path=protocol_path,
            output_dir=output_dir,
            protocol=protocol,
            data_manifest=data_manifest,
        )


def test_duplicate_scoring_is_refused_before_oracle_access(tmp_path: Path) -> None:
    protocol = tmp_path / "protocol.json"
    protocol.write_text(
        json.dumps(
            {
                "protocol_id": "fixture",
                "status": "scored",
                "results": {"status": "scored"},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    missing_benchmark = tmp_path / "must-not-be-opened.json"
    args = argparse.Namespace(
        run_dir=tmp_path / "run",
        benchmark=missing_benchmark,
        protocol=protocol,
        output=None,
    )
    with pytest.raises(integrity.HeldoutIntegrityError, match="duplicate refused"):
        scorer.execute(args)
    assert not missing_benchmark.exists()


def test_score_finalizer_advances_once_and_preserves_first_pass_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(scorer, "PROJECT_ROOT", tmp_path)
    run_dir = tmp_path / "experiments/results/heldout"
    run_dir.mkdir(parents=True)
    summary_path = run_dir / "sealed-summary-without-oracle.json"
    summary_path.write_text("{}\n", encoding="utf-8")
    summary_sha256 = integrity.sha256_file(summary_path)
    benchmark_sha256 = "4" * 64
    seal_sha256 = "5" * 64
    marker_path = run_dir / scorer.SCORING_MARKER_FILENAME
    marker_path.write_text(
        json.dumps(
            {
                "protocol_id": "fixture",
                "seal_sha256": seal_sha256,
                "benchmark_metadata_sha256": benchmark_sha256,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    score_path = run_dir / scorer.SCORE_FILENAME
    score_path.write_text(
        json.dumps(
            {
                "protocol_id": "fixture",
                "task_ids": list(scorer.TASK_IDS),
                "scored_at": "2026-09-06T16:00:00+08:00",
                "sealed_summary_sha256": summary_sha256,
                "benchmark_metadata_sha256": benchmark_sha256,
                "scoring_semantics": "fixture semantics",
                "aggregate": {"tasks": len(scorer.TASK_IDS)},
                "results": [{"task_id": task_id} for task_id in scorer.TASK_IDS],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    protocol = {
        "protocol_id": "fixture",
        "status": "first_pass_sealed",
        "benchmark": {"metadata_sha256": benchmark_sha256},
        "results": {
            "status": "first_pass_sealed",
            "run_directory": "experiments/results/heldout",
            "planned_oracle_marker": ("experiments/results/heldout/ORACLE_SCORING_STARTED.json"),
            "planned_score_artifact": (
                "experiments/results/heldout/scored-after-oracle-unsealing.json"
            ),
            "artifact": ("experiments/results/heldout/sealed-summary-without-oracle.json"),
            "artifact_sha256": summary_sha256,
            "seal_sha256": seal_sha256,
        },
    }
    attach_frozen_plan(
        tmp_path,
        protocol,
        paths={
            "run_directory": "experiments/results/heldout",
            "oracle_marker": ("experiments/results/heldout/ORACLE_SCORING_STARTED.json"),
            "score_artifact": ("experiments/results/heldout/scored-after-oracle-unsealing.json"),
        },
        execution={},
    )
    plan_sha256 = protocol["frozen_plan"]["sha256"]
    marker_payload = json.loads(marker_path.read_text(encoding="utf-8"))
    marker_payload["plan_sha256"] = plan_sha256
    marker_path.write_text(json.dumps(marker_payload) + "\n", encoding="utf-8")
    score_payload = json.loads(score_path.read_text(encoding="utf-8"))
    score_payload["plan_sha256"] = plan_sha256
    score_path.write_text(json.dumps(score_payload) + "\n", encoding="utf-8")
    protocol_path = tmp_path / "protocol.json"
    protocol_path.write_text(json.dumps(protocol) + "\n", encoding="utf-8")

    updated = scorer.finalize_scored_protocol(
        protocol_path=protocol_path,
        protocol=protocol,
        run_dir=run_dir,
        score_path=score_path,
        marker_path=marker_path,
    )
    assert updated["status"] == "scored"
    assert updated["results"]["artifact_sha256"] == summary_sha256
    assert updated["results"]["score_sha256"] == integrity.sha256_file(score_path)

    with pytest.raises(integrity.HeldoutIntegrityError, match="transition requires"):
        scorer.finalize_scored_protocol(
            protocol_path=protocol_path,
            protocol=protocol,
            run_dir=run_dir,
            score_path=score_path,
            marker_path=marker_path,
        )


def test_synthetic_first_pass_and_scoring_lifecycle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(runner, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(scorer, "PROJECT_ROOT", tmp_path)
    surface_sha256 = "6" * 64
    monkeypatch.setattr(runner, "current_surface_hash", lambda: surface_sha256)

    extracted_root = tmp_path / "data/external/community_45"
    data_root = extracted_root / "full_community"
    data_root.mkdir(parents=True)
    data_file = data_root / "fixture.csv"
    data_file.write_text("value\n42\n", encoding="utf-8")
    manifest = write_manifest(tmp_path, extracted_root)
    questions = tmp_path / "data/pilots/heldout-v1-questions.json"
    questions.parent.mkdir(parents=True)
    questions.write_text(
        json.dumps(
            {
                "protocol_id": "fixture",
                "task_ids": list(runner.TASK_IDS),
                "tasks": [
                    {"task_id": task_id, "question": f"Question {task_id}?"}
                    for task_id in runner.TASK_IDS
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    run_dir = tmp_path / "experiments/results/heldout"
    benchmark = tmp_path / "data/external/coda-bench.json"
    benchmark_payload = (
        json.dumps([{"instance_id": task_id, "answer": "42"} for task_id in runner.TASK_IDS]) + "\n"
    )
    benchmark_sha256 = hashlib.sha256(benchmark_payload.encode()).hexdigest()
    protocol = {
        "protocol_id": "fixture",
        "protocol_version": 2,
        "status": "unblinded_not_run",
        "benchmark": {
            "revision": "a" * 40,
            "metadata_file": benchmark.relative_to(tmp_path).as_posix(),
            "metadata_sha256": benchmark_sha256,
        },
        "selection": {
            "task_ids": list(runner.TASK_IDS),
            "task_count": len(runner.TASK_IDS),
        },
        "implementation_freeze": {"pre_unblinding_sha256": surface_sha256},
        "unblinding": {
            "status": "complete",
            "questions_file": questions.relative_to(tmp_path).as_posix(),
            "questions_sha256": integrity.sha256_file(questions),
            "extracted_root": extracted_root.relative_to(tmp_path).as_posix(),
            "data_root": data_root.relative_to(tmp_path).as_posix(),
            "extracted_manifest": manifest.relative_to(tmp_path).as_posix(),
            "extracted_manifest_sha256": integrity.sha256_file(manifest),
            "extracted_file_count": 1,
        },
        "results": {
            "status": "not_run",
            "planned_run_directory": run_dir.relative_to(tmp_path).as_posix(),
            "planned_oracle_marker": (run_dir / scorer.SCORING_MARKER_FILENAME)
            .relative_to(tmp_path)
            .as_posix(),
            "planned_score_artifact": (run_dir / scorer.SCORE_FILENAME)
            .relative_to(tmp_path)
            .as_posix(),
            "artifact": None,
        },
    }
    endpoint = "https://provider.invalid/exact"
    execution = {
        "model": "fixture-model",
        "endpoint_sha256": hashlib.sha256(endpoint.encode()).hexdigest(),
        "api_style": "direct_chat_completions",
        "auth_scheme": "api_key",
        "token_field": "max_completion_tokens",
        "trust_environment_proxy": False,
        "timeout_seconds": 120.0,
        "transport_retries": 2,
        "temperature": 0.0,
        "planner_max_attempts": 2,
        "max_repair_rounds": 2,
        "max_concurrent_runs": 1,
    }
    attach_frozen_plan(
        tmp_path,
        protocol,
        paths={
            "questions_file": questions.relative_to(tmp_path).as_posix(),
            "extracted_root": extracted_root.relative_to(tmp_path).as_posix(),
            "data_root": data_root.relative_to(tmp_path).as_posix(),
            "extracted_manifest": manifest.relative_to(tmp_path).as_posix(),
            "run_directory": run_dir.relative_to(tmp_path).as_posix(),
            "first_pass_summary": (run_dir / "sealed-summary-without-oracle.json")
            .relative_to(tmp_path)
            .as_posix(),
            "first_pass_seal": (run_dir / "seal.sha256").relative_to(tmp_path).as_posix(),
            "oracle_marker": (run_dir / scorer.SCORING_MARKER_FILENAME)
            .relative_to(tmp_path)
            .as_posix(),
            "score_artifact": (run_dir / scorer.SCORE_FILENAME).relative_to(tmp_path).as_posix(),
        },
        execution=execution,
    )
    plan_sha256 = protocol["frozen_plan"]["sha256"]
    question_payload = json.loads(questions.read_text(encoding="utf-8"))
    question_payload["plan_sha256"] = plan_sha256
    questions.write_text(json.dumps(question_payload) + "\n", encoding="utf-8")
    protocol["unblinding"]["plan_sha256"] = plan_sha256
    protocol["unblinding"]["questions_sha256"] = integrity.sha256_file(questions)
    protocol_path = tmp_path / "data/pilots/heldout-v1.json"
    protocol_path.write_text(json.dumps(protocol) + "\n", encoding="utf-8")

    class FakeService:
        def run(self, question: str) -> SimpleNamespace:
            task_id = int(question.removeprefix("Question ").removesuffix("?"))
            return SimpleNamespace(
                status=SimpleNamespace(value="completed"),
                diagnosis=None,
                report=SimpleNamespace(
                    title=f"Fixture {task_id}",
                    claims=[SimpleNamespace(value="42")],
                ),
                contract=SimpleNamespace(compilation=SimpleNamespace(attempts=1)),
                assets={"asset": SimpleNamespace(name="fixture.csv", byte_size=9)},
                events=[],
                artifacts=[],
                run_id=f"run_{task_id:016x}",
                model_dump_json=lambda indent: json.dumps(
                    {"task_id": task_id, "status": "completed"}, indent=indent
                ),
            )

    monkeypatch.setattr(
        runner,
        "Settings",
        lambda **kwargs: SimpleNamespace(
            llm_configured=True,
            llm_base_url=endpoint,
            llm_model="fixture-model",
            llm_api_style="direct_chat_completions",
            llm_auth_scheme="api_key",
            llm_token_field="max_completion_tokens",
            llm_trust_env_proxy=False,
            llm_timeout_seconds=120.0,
            llm_max_retries=2,
            planner_max_attempts=2,
            max_repair_rounds=2,
            max_concurrent_runs=1,
        ),
    )
    monkeypatch.setattr(runner, "build_run_service", lambda settings: FakeService())
    monkeypatch.setattr(runner, "format_declarative_answer", lambda artifacts: "42")
    runner.execute(
        argparse.Namespace(
            data_root=data_root,
            questions=questions,
            protocol=protocol_path,
            output_dir=run_dir,
        )
    )
    sealed_protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
    assert sealed_protocol["status"] == "first_pass_sealed"
    assert sealed_protocol["results"]["sealed_file_count"] == len(runner.TASK_IDS) + 2
    assert not benchmark.exists()

    benchmark.parent.mkdir(parents=True, exist_ok=True)
    benchmark.write_text(benchmark_payload, encoding="utf-8")
    scorer.execute(
        argparse.Namespace(
            run_dir=run_dir,
            benchmark=benchmark,
            protocol=protocol_path,
            output=None,
        )
    )
    scored_protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
    score = json.loads((run_dir / scorer.SCORE_FILENAME).read_text(encoding="utf-8"))
    assert scored_protocol["status"] == "scored"
    assert score["aggregate"] == {
        "tasks": len(runner.TASK_IDS),
        "exact_matches": len(runner.TASK_IDS),
        "numeric_matches": len(runner.TASK_IDS),
    }

    with pytest.raises(integrity.HeldoutIntegrityError, match="duplicate refused"):
        scorer.execute(
            argparse.Namespace(
                run_dir=run_dir,
                benchmark=benchmark,
                protocol=protocol_path,
                output=None,
            )
        )
