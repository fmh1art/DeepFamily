from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from askdu import heldout_integrity

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def load_readiness_module() -> ModuleType:
    path = PROJECT_ROOT / "scripts/audit_submission_readiness.py"
    spec = importlib.util.spec_from_file_location("askdu_test_submission_readiness", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load submission readiness checker")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


READINESS = load_readiness_module()


def attach_frozen_plan(
    project_root: Path,
    protocol: dict[str, Any],
    *,
    paths: dict[str, str],
    execution: dict[str, Any] | None = None,
) -> dict[str, Any]:
    benchmark = {
        "name": "FixtureBench",
        "repository": "fixture/repository",
        "revision": "a" * 40,
        "metadata_file": "data/benchmark.json",
        "metadata_sha256": "a" * 64,
        "archive_file": "data/archive.tar.zst",
        "archive_bytes": 1,
        "archive_sha256": "b" * 64,
        **dict(protocol.get("benchmark", {})),
    }
    selection = {
        "community_id": 45,
        "task_ids": list(READINESS.TASK_IDS),
        "task_count": len(READINESS.TASK_IDS),
        "selection_rule": "complete fixture community",
        **dict(protocol.get("selection", {})),
    }
    run_directory = paths["run_directory"]
    frozen_paths = {
        "questions_file": "data/questions.json",
        "extracted_root": "data/community_45",
        "data_root": "data/community_45/full_community",
        "extracted_manifest": "data/community_45.sha256",
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
        **(execution or {}),
    }
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
    plan_path.write_text(json.dumps(plan) + "\n", encoding="utf-8")
    protocol["benchmark"] = benchmark
    protocol["selection"] = selection
    protocol["frozen_plan"] = {
        "file": plan_path.relative_to(project_root).as_posix(),
        "sha256": heldout_integrity.sha256_file(plan_path),
    }
    return plan


def accepted_trial() -> dict[str, Any]:
    return {
        "schema_version": "askdu-user-trial-v3",
        "is_example": False,
        "session_id": "P01-20260906",
        "occurred_at": "2026-09-06T14:00:00+08:00",
        "build_version": "0.4.0",
        "trial_protocol_id": "askdu-non-author-rehearsal-v1",
        "trial_protocol_sha256": "c" * 64,
        "demo_surface_sha256": "a" * 64,
        "deployment": "local-compose",
        "browser": "Chromium 140.0.0",
        "viewport_css_px": {"width": 1600, "height": 900},
        "zoom_percent": 100,
        "consent_recorded": True,
        "participant": {
            "code": "P01",
            "non_author": True,
            "prior_project_exposure": False,
            "data_analysis_familiarity_1_to_5": 3,
        },
        "task_results": {task_id: True for task_id in READINESS.TRIAL_TASK_IDS},
        "outcomes": {
            "tasks_total": 6,
            "completed_without_facilitator_correction": 6,
            "repeat_core_path_without_facilitator_correction": True,
            "correctly_distinguished_report_and_diagnosis": True,
            "blocking_issues_remaining": 0,
        },
        "timings_seconds": {
            "time_to_first_run": 18.2,
            "time_to_locate_repair_edge": 42.1,
            "time_to_locate_claim_evidence": 71.4,
        },
        "issues": [],
    }


def test_trial_gate_accepts_only_complete_pseudonymous_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    validate_trial = READINESS.validate_trial
    monkeypatch.setattr(READINESS, "current_demo_surface_hash", lambda: "a" * 64)
    monkeypatch.setattr(READINESS, "current_trial_protocol_hash", lambda: "c" * 64)
    record = accepted_trial()
    path = tmp_path / "2026-09-06-p01.json"
    assert validate_trial(record, path) is True

    record["notes"] = "contact participant@example.com"
    with pytest.raises(ValueError, match="identity field"):
        validate_trial(record, path)


def test_trial_gate_rejects_stale_surface_and_inconsistent_counts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "2026-09-06-p01.json"
    record = accepted_trial()
    monkeypatch.setattr(READINESS, "current_demo_surface_hash", lambda: "b" * 64)
    monkeypatch.setattr(READINESS, "current_trial_protocol_hash", lambda: "c" * 64)
    with pytest.raises(ValueError, match="demo surface digest"):
        READINESS.validate_trial(record, path)

    monkeypatch.setattr(READINESS, "current_demo_surface_hash", lambda: "a" * 64)
    record["task_results"]["locate_backward_repair_edge"] = False
    with pytest.raises(ValueError, match="aggregate trial outcomes"):
        READINESS.validate_trial(record, path)

    record["outcomes"]["completed_without_facilitator_correction"] = 5
    assert READINESS.validate_trial(record, path) is False
    assert READINESS.trial_acceptance_failures(record) == (
        "all six tasks were completed without facilitator correction",
    )

    record = accepted_trial()
    record["trial_protocol_sha256"] = "d" * 64
    with pytest.raises(ValueError, match="trial protocol ID or digest"):
        READINESS.validate_trial(record, path)


def test_trial_gate_checks_open_blockers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "2026-09-06-p01.json"
    record = accepted_trial()
    record["issues"] = [
        {
            "code": "NAV-01",
            "severity": "blocks",
            "status": "open",
            "summary": "Could not return to the question composer.",
        }
    ]
    monkeypatch.setattr(READINESS, "current_demo_surface_hash", lambda: "a" * 64)
    monkeypatch.setattr(READINESS, "current_trial_protocol_hash", lambda: "c" * 64)

    with pytest.raises(ValueError, match="blocking-issue count"):
        READINESS.validate_trial(record, path)

    record["outcomes"]["blocking_issues_remaining"] = 1
    assert READINESS.validate_trial(record, path) is False


def test_trial_record_cli_binds_current_demo_surface(tmp_path: Path) -> None:
    record = accepted_trial()
    record["demo_surface_sha256"] = READINESS.current_demo_surface_hash()
    record["trial_protocol_sha256"] = READINESS.current_trial_protocol_hash()
    path = tmp_path / "2026-09-06-p01.json"
    path.write_text(json.dumps(record), encoding="utf-8")

    process = subprocess.run(
        [
            sys.executable,
            str(PROJECT_ROOT / "scripts/audit_submission_readiness.py"),
            "--trial-record",
            str(path),
        ],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert process.returncode == 0
    assert "PASS: [non_author_rehearsal_record]" in process.stdout

    record["demo_surface_sha256"] = "b" * 64
    path.write_text(json.dumps(record), encoding="utf-8")
    process = subprocess.run(
        [
            sys.executable,
            str(PROJECT_ROOT / "scripts/audit_submission_readiness.py"),
            "--trial-record",
            str(path),
        ],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert process.returncode == 1
    assert "FAIL: [non_author_rehearsal_record]" in process.stdout
    assert "demo surface digest differs" in process.stdout


def test_trial_protocol_cli_matches_the_protocol_hasher() -> None:
    process = subprocess.run(
        [
            sys.executable,
            str(PROJECT_ROOT / "scripts/audit_submission_readiness.py"),
            "--print-trial-protocol-sha256",
        ],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert process.returncode == 0
    assert process.stdout.strip() == READINESS.current_trial_protocol_hash()


def test_seal_verifier_detects_mutation(tmp_path: Path) -> None:
    payload = tmp_path / "sealed-summary-without-oracle.json"
    payload.write_text("{}\n", encoding="utf-8")
    seal = tmp_path / "seal.sha256"
    seal.write_text(
        f"{READINESS.sha256_file(payload)}  {payload.name}\n",
        encoding="utf-8",
    )
    READINESS.verify_seal(tmp_path)

    payload.write_text('{"changed": true}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="drifted"):
        READINESS.verify_seal(tmp_path)


def test_public_artifact_gate_binds_checksum_and_paper_url(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "backend").mkdir()
    (tmp_path / "backend/pyproject.toml").write_text(
        '[project]\nversion = "0.4.0"\n',
        encoding="utf-8",
    )
    paper = tmp_path / "main.tex"
    paper.write_text(
        "\\renewcommand\\vldbavailabilityurl{https://zenodo.org/records/123}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(READINESS, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(READINESS, "PAPER_SOURCE", paper)

    assert READINESS.public_artifact_gate().status == "pending"

    release = tmp_path / "artifacts/release"
    release.mkdir(parents=True)
    archive = release / "ask-dont-upload-artifact-v0.4.0-release.tar.gz"
    archive.write_bytes(b"sanitized artifact fixture")
    archive.with_name(f"{archive.name}.sha256").write_text(
        f"{READINESS.sha256_file(archive)}  {archive.name}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        READINESS.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args=[], returncode=0),
    )

    assert READINESS.public_artifact_gate().status == "pass"

    archive.write_bytes(b"mutated")
    assert READINESS.public_artifact_gate().status == "fail"


def test_blinded_gate_rejects_premature_payload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    protocol_path = tmp_path / "heldout-v1.json"
    questions = tmp_path / "heldout-v1-questions.json"
    heldout_data = tmp_path / "community_45"
    heldout_manifest = tmp_path / "community_45.sha256"
    run = tmp_path / "run"
    protocol: dict[str, Any] = {
        "protocol_id": "fixture",
        "protocol_version": 2,
        "status": "implementation_frozen_blinded",
        "implementation_freeze": {"pre_unblinding_sha256": "frozen"},
        "unblinding": {"status": "not_started"},
        "results": {
            "status": "not_run",
            "planned_run_directory": "run",
            "planned_oracle_marker": "run/ORACLE_SCORING_STARTED.json",
            "planned_score_artifact": "run/scored-after-oracle-unsealing.json",
        },
    }
    attach_frozen_plan(
        tmp_path,
        protocol,
        paths={
            "run_directory": "run",
            "oracle_marker": "run/ORACLE_SCORING_STARTED.json",
            "score_artifact": "run/scored-after-oracle-unsealing.json",
        },
    )
    protocol_path.write_text(json.dumps(protocol), encoding="utf-8")
    monkeypatch.setattr(READINESS, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(READINESS, "PROTOCOL", protocol_path)
    monkeypatch.setattr(READINESS, "HELDOUT_QUESTIONS", questions)
    monkeypatch.setattr(READINESS, "HELDOUT_DATA", heldout_data)
    monkeypatch.setattr(READINESS, "HELDOUT_MANIFEST", heldout_manifest)
    monkeypatch.setattr(READINESS, "HELDOUT_RUN", run)
    monkeypatch.setattr(READINESS, "current_surface_hash", lambda: "frozen")

    assert READINESS.heldout_gate().status == "pending"

    questions.write_text("{}\n", encoding="utf-8")
    assert READINESS.heldout_gate().status == "fail"


def test_heldout_gate_requires_coherent_unblinded_sealed_and_scored_states(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    frozen = "1" * 64
    protocol_path = tmp_path / "data/pilots/heldout-v1.json"
    questions = tmp_path / "data/pilots/heldout-v1-questions.json"
    extracted = tmp_path / "data/external/community_45"
    data_root = extracted / "full_community"
    data_root.mkdir(parents=True)
    data_file = data_root / "fixture.csv"
    data_file.write_text("a\n1\n", encoding="utf-8")
    manifest = tmp_path / "data/manifests/community-45.sha256"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        f"{heldout_integrity.sha256_file(data_file)}  "
        f"{data_file.relative_to(tmp_path).as_posix()}\n",
        encoding="utf-8",
    )
    questions.parent.mkdir(parents=True)
    questions.write_text('{"redacted": true}\n', encoding="utf-8")
    run = tmp_path / "experiments/results/heldout"
    planned_marker = run / "ORACLE_SCORING_STARTED.json"
    score_path = run / "scored-after-oracle-unsealing.json"
    benchmark_sha256 = "2" * 64
    protocol: dict[str, Any] = {
        "protocol_id": "fixture",
        "protocol_version": 2,
        "status": "unblinded_not_run",
        "benchmark": {"metadata_sha256": benchmark_sha256},
        "selection": {},
        "implementation_freeze": {"pre_unblinding_sha256": frozen},
        "unblinding": {
            "status": "complete",
            "questions_file": questions.relative_to(tmp_path).as_posix(),
            "questions_sha256": heldout_integrity.sha256_file(questions),
            "extracted_root": extracted.relative_to(tmp_path).as_posix(),
            "data_root": data_root.relative_to(tmp_path).as_posix(),
            "extracted_manifest": manifest.relative_to(tmp_path).as_posix(),
            "extracted_manifest_sha256": heldout_integrity.sha256_file(manifest),
            "extracted_file_count": 1,
        },
        "results": {
            "status": "not_run",
            "planned_run_directory": run.relative_to(tmp_path).as_posix(),
            "planned_oracle_marker": planned_marker.relative_to(tmp_path).as_posix(),
            "planned_score_artifact": score_path.relative_to(tmp_path).as_posix(),
            "artifact": None,
        },
    }
    plan = attach_frozen_plan(
        tmp_path,
        protocol,
        paths={
            "questions_file": questions.relative_to(tmp_path).as_posix(),
            "extracted_root": extracted.relative_to(tmp_path).as_posix(),
            "data_root": data_root.relative_to(tmp_path).as_posix(),
            "extracted_manifest": manifest.relative_to(tmp_path).as_posix(),
            "run_directory": run.relative_to(tmp_path).as_posix(),
            "oracle_marker": planned_marker.relative_to(tmp_path).as_posix(),
            "score_artifact": score_path.relative_to(tmp_path).as_posix(),
        },
    )
    protocol["unblinding"]["plan_sha256"] = protocol["frozen_plan"]["sha256"]

    def write_protocol() -> None:
        protocol_path.parent.mkdir(parents=True, exist_ok=True)
        protocol_path.write_text(json.dumps(protocol) + "\n", encoding="utf-8")

    write_protocol()
    monkeypatch.setattr(READINESS, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(READINESS, "PROTOCOL", protocol_path)
    monkeypatch.setattr(READINESS, "HELDOUT_QUESTIONS", questions)
    monkeypatch.setattr(READINESS, "HELDOUT_DATA", extracted)
    monkeypatch.setattr(READINESS, "HELDOUT_MANIFEST", manifest)
    monkeypatch.setattr(READINESS, "HELDOUT_RUN", run)
    monkeypatch.setattr(READINESS, "current_surface_hash", lambda: frozen)
    assert READINESS.heldout_gate().status == "pending"

    run.mkdir(parents=True)
    marker = run / "FIRST_PASS_STARTED.json"
    marker.write_text("{}\n", encoding="utf-8")
    assert READINESS.heldout_gate().status == "fail"

    bindings = {
        "protocol_id": "fixture",
        "plan_sha256": protocol["frozen_plan"]["sha256"],
        "surface_sha256": frozen,
        "questions_sha256": protocol["unblinding"]["questions_sha256"],
        "data_manifest_sha256": protocol["unblinding"]["extracted_manifest_sha256"],
        "data_file_count": 1,
        "execution_config_sha256": heldout_integrity.canonical_json_sha256(plan["execution"]),
    }
    marker.write_text(json.dumps(bindings) + "\n", encoding="utf-8")
    summary = run / "sealed-summary-without-oracle.json"
    summary.write_text(
        json.dumps(
            {
                **bindings,
                "task_ids": list(READINESS.TASK_IDS),
                "results": [{"task_id": task_id} for task_id in READINESS.TASK_IDS],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    runs = run / "runs"
    runs.mkdir()
    for task_id in READINESS.TASK_IDS:
        (runs / f"task-{task_id}.json").write_text("{}\n", encoding="utf-8")
    seal_verification = heldout_integrity.build_seal(run, run / "seal.sha256")
    result_record = protocol["results"]
    result_record.update(
        {
            "status": "first_pass_sealed",
            "run_directory": run.relative_to(tmp_path).as_posix(),
            "artifact": summary.relative_to(tmp_path).as_posix(),
            "artifact_sha256": heldout_integrity.sha256_file(summary),
            "seal_file": (run / "seal.sha256").relative_to(tmp_path).as_posix(),
            "seal_sha256": seal_verification.manifest_sha256,
            "sealed_file_count": seal_verification.file_count,
        }
    )
    protocol["status"] = "first_pass_sealed"
    write_protocol()
    assert READINESS.heldout_gate().status == "pending"

    planned_marker.write_text(
        json.dumps(
            {
                "protocol_id": "fixture",
                "plan_sha256": protocol["frozen_plan"]["sha256"],
                "seal_sha256": seal_verification.manifest_sha256,
                "benchmark_metadata_sha256": benchmark_sha256,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    score = {
        "protocol_id": "fixture",
        "plan_sha256": protocol["frozen_plan"]["sha256"],
        "sealed_summary_sha256": heldout_integrity.sha256_file(summary),
        "benchmark_metadata_sha256": benchmark_sha256,
        "aggregate": {"tasks": len(READINESS.TASK_IDS)},
        "results": [{"task_id": task_id} for task_id in READINESS.TASK_IDS],
    }
    score_path.write_text(json.dumps(score) + "\n", encoding="utf-8")
    result_record.update(
        {
            "status": "scored",
            "oracle_marker": planned_marker.relative_to(tmp_path).as_posix(),
            "oracle_marker_sha256": heldout_integrity.sha256_file(planned_marker),
            "score_artifact": score_path.relative_to(tmp_path).as_posix(),
            "score_sha256": heldout_integrity.sha256_file(score_path),
        }
    )
    protocol["status"] = "scored"
    write_protocol()
    assert READINESS.heldout_gate().status == "pass"

    score_path.write_text('{"tampered": true}\n', encoding="utf-8")
    assert READINESS.heldout_gate().status == "fail"
