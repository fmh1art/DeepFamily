from __future__ import annotations

import copy
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import Any

import pytest

from askdu.adapters.provider_metering import METER_SCHEMA, read_usage_summary, summarize_calls
from askdu.heldout_integrity import (
    HeldoutIntegrityError,
    build_seal,
    canonical_json_sha256,
)

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "study_summary_tests", ROOT / "scripts/summarize_agentic_study.py"
)
assert SPEC is not None and SPEC.loader is not None
SUMMARY = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = SUMMARY
SPEC.loader.exec_module(SUMMARY)


def paired_fixture(count: int = 1) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    tasks = [
        {"task_id": n, "community_id": n, "question": "Synthetic question"}
        for n in range(1, count + 1)
    ]
    cases = [
        {
            "case_id": f"task-{t['task_id']}-r{repeat}-{mode}",
            "task_id": t["task_id"],
            "mode": mode,
            "repetition": repeat,
        }
        for t in tasks
        for repeat in range(1, 4)
        for mode in SUMMARY.MODES
    ]
    plan = {
        "protocol_id": "askdu-agentic-open-v1",
        "source_sha256": "a" * 64,
        "tasks": tasks,
        "schedule": cases,
        "repetitions": 3,
    }
    sealed = [
        {
            **case,
            "plan_sha256": canonical_json_sha256(plan),
            "status": "timeout",
            "driver_wall_seconds": 900,
            "model_usage": {
                "availability": "missing",
                "logical_calls": None,
                "http_attempts_started": None,
            },
        }
        for case in cases
    ]
    rows = [
        {
            **row,
            "judge": {"answer": "incorrect", "grounding": "uncertain", "reason": "No report"},
            "judge_answer_correct": False,
            "judge_supported_report": False,
            "answer_exact_agreement": False,
            "numeric_sequence_agreement": False,
            "judge_usage": {"availability": "not_called", **summarize_calls([])},
        }
        for row in sealed
    ]
    return plan, sealed, {"results": rows}


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def complete_fixture(root: Path) -> dict[str, Any]:
    plan, sealed, scores = paired_fixture(30)
    for original, row in zip(sealed, scores["results"], strict=True):
        directory = root / "predictions" / row["case_id"]
        write_json(directory / "model-calls.json", {"schema_version": METER_SCHEMA, "calls": []})
        usage = read_usage_summary(directory / "model-calls.json")
        original["model_usage"] = usage
        row["model_usage"] = usage
        write_json(directory / "result.json", original)
        write_json(root / "judgements" / row["case_id"] / "grade.json", row["judge"])
        write_json(root / "judgements" / row["case_id"] / "usage.json", row["judge_usage"])
    write_json(root / "predictions/plan.json", plan)
    write_json(
        root / "predictions/summary.json",
        {"plan_sha256": canonical_json_sha256(plan), "results": sealed},
    )
    seal = build_seal(root / "predictions", root / "predictions/seal.sha256")
    summary = SUMMARY.aggregate(plan, scores["results"])
    scores.update(
        {
            "source_sha256": plan["source_sha256"],
            "prediction_seal_sha256": seal.manifest_sha256,
            "question_level_pairs": summary["question_level_pairs"],
            "paired_macro_differences": summary["paired_macro_differences"],
            "judge_verdict_counts": {"incorrect": 180},
        }
    )
    write_json(root / "scores.json", scores)
    return plan


def test_failed_missing_and_unscorable_cases_remain_in_denominator() -> None:
    plan, sealed, scores = paired_fixture()
    scores["results"][0]["judge"]["answer"] = "unscorable"
    sealed[1].update(status="completed", report_available=True)
    scores["results"][1].update(status="completed", report_available=True)
    scores["results"][1]["judge"]["answer"] = "correct"
    scores["results"][1]["judge_answer_correct"] = True
    rows = SUMMARY.validate_rows(plan, sealed, scores)
    result = SUMMARY.aggregate(plan, rows)
    assert result["modes"]["closed_loop"]["cases"] == 3
    assert result["modes"]["no_cross_stage_repair"]["answer_grades"] == {
        "unscorable": 1,
        "incorrect": 2,
    }
    assert result["paired_macro_differences"]["judge_answer_correct"] == pytest.approx(1 / 3)


def test_report_absence_cannot_become_a_successful_judgement() -> None:
    plan, sealed, scores = paired_fixture()
    scores["results"][0]["judge"].update(answer="correct", grounding="supported")
    scores["results"][0]["judge_answer_correct"] = True
    with pytest.raises(ValueError, match="missing report"):
        SUMMARY.validate_rows(plan, sealed, scores)


@pytest.mark.parametrize(
    "change", ["drop", "duplicate", "original", "identity", "boolean", "grade"]
)
def test_changed_or_incomplete_rows_are_rejected(change: str) -> None:
    plan, sealed, scores = paired_fixture()
    if change == "drop":
        scores["results"].pop()
    elif change == "duplicate":
        scores["results"][-1] = copy.deepcopy(scores["results"][0])
    elif change == "original":
        scores["results"][0]["status"] = "completed"
    elif change == "identity":
        sealed[0]["mode"] = "unrecognized"
    elif change == "boolean":
        scores["results"][0]["answer_exact_agreement"] = 1
    else:
        scores["results"][0]["judge_answer_correct"] = True
    with pytest.raises(ValueError):
        SUMMARY.validate_rows(plan, sealed, scores)


def test_missing_usage_and_missing_receipts_are_not_zero() -> None:
    _, sealed, _ = paired_fixture()
    result = SUMMARY.usage_totals([row["model_usage"] for row in sealed])
    assert result["logical_calls"]["observed_total"] is None
    assert result["tokens"]["total_tokens"]["observed_total"] is None
    assert result["tokens"]["total_tokens"]["cases_without_token_counters"] == 6
    known = {"availability": "available", **summarize_calls([])}
    known["logical_calls"] = 1
    known["http_attempts_started"] = 2
    known["tokens"]["total_tokens"] = {
        "observed_total": 20,
        "attempts_with_value": 1,
        "attempts_without_value": 1,
    }
    partial = SUMMARY.usage_totals([known, sealed[0]["model_usage"]])
    assert partial["tokens"]["total_tokens"] == {
        "observed_total": 20,
        "attempts_with_value": 1,
        "attempts_without_value": 1,
        "cases_without_token_counters": 1,
    }
    assert partial["logical_calls"]["cases_without_value"] == 1


def test_all_failed_study_has_no_success_only_latency_bias() -> None:
    plan, _, scores = paired_fixture()
    scores["results"][0]["driver_wall_seconds"] = None
    result = SUMMARY.aggregate(plan, scores["results"])
    wall = result["modes"]["no_cross_stage_repair"]["driver_wall_seconds"]
    assert wall == {"observed_cases": 2, "missing_cases": 1, "sum": 1800, "median": 900}


def test_incomplete_seal_is_rejected_before_scores(tmp_path: Path, monkeypatch: Any) -> None:
    plan, _, _ = paired_fixture(30)
    monkeypatch.setattr(SUMMARY, "load_plan", lambda _: plan)
    with pytest.raises(HeldoutIntegrityError):
        SUMMARY.audit(tmp_path)


def test_complete_synthetic_audit_and_readable_report(tmp_path: Path, monkeypatch: Any) -> None:
    plan = complete_fixture(tmp_path)
    monkeypatch.setattr(SUMMARY, "load_plan", lambda _: plan)
    result = SUMMARY.audit(tmp_path)
    assert result["modes"]["closed_loop"]["cases"] == 90
    markdown = SUMMARY.render_markdown(result)
    assert "180 cases" in markdown
    assert "proxy requiring independent human audit" in markdown
    assert "Median seconds" in markdown
    assert "judge_answer_correct | 0 / 90 | 0 / 90" in markdown


def test_cli_output_is_idempotent_but_never_overwrites_changes(
    tmp_path: Path, monkeypatch: Any
) -> None:
    study = tmp_path / "study"
    plan = complete_fixture(study)
    monkeypatch.setattr(SUMMARY, "load_plan", lambda _: plan)
    destination = tmp_path / "report"
    monkeypatch.setattr(
        sys, "argv", ["summary", "--study", str(study), "--output", str(destination)]
    )
    SUMMARY.main()
    before = (destination / "summary.md").read_bytes()
    SUMMARY.main()
    assert (destination / "summary.md").read_bytes() == before
    (destination / "summary.md").write_text("User edit; do not overwrite")
    with pytest.raises(ValueError, match="Existing output differs"):
        SUMMARY.main()
    assert (destination / "summary.md").read_text() == "User edit; do not overwrite"


@pytest.mark.parametrize("change", ["prediction", "judge", "usage", "paired", "seal"])
def test_audit_binds_real_files_to_summary(tmp_path: Path, monkeypatch: Any, change: str) -> None:
    plan = complete_fixture(tmp_path)
    monkeypatch.setattr(SUMMARY, "load_plan", lambda _: plan)
    case = plan["schedule"][0]["case_id"]
    if change == "prediction":
        write_json(tmp_path / "predictions" / case / "result.json", {})
    elif change == "judge":
        write_json(tmp_path / "judgements" / case / "grade.json", {})
    elif change == "usage":
        write_json(tmp_path / "judgements" / case / "usage.json", {})
    else:
        scores = SUMMARY.read_json(tmp_path / "scores.json")
        if change == "paired":
            scores["paired_macro_differences"]["judge_answer_correct"] = 1
        else:
            scores["prediction_seal_sha256"] = "f" * 64
        write_json(tmp_path / "scores.json", scores)
    with pytest.raises(ValueError):
        SUMMARY.audit(tmp_path)


@pytest.mark.parametrize("failure", ["none", "auth", "malformed", "runner", "judge"])
def test_supervisor_sequences_bounded_phases_and_stops_on_errors(
    tmp_path: Path, failure: str
) -> None:
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    shutil.copyfile(
        ROOT / "scripts/run_agentic_open_study.sh", scripts / "run_agentic_open_study.sh"
    )
    study = tmp_path / "experiments/results/agentic-open-v1"
    study.mkdir(parents=True)
    (study / "freeze.json").write_text("{}")
    commands = tmp_path / "test-bin"
    commands.mkdir()
    stub = commands / "uv"
    stub.write_text(
        f"#!{sys.executable}\n"
        + textwrap.dedent("""
        import json
        import os
        import pathlib
        import sys
        study = pathlib.Path("experiments/results/agentic-open-v1")
        failure = os.environ["ASKDU_TEST_STUDY_FAILURE"]
        args = sys.argv[1:]
        phase = "run" if "run" in args[5:] else "score" if "score" in args else "summary"
        with pathlib.Path("test-invocations.jsonl").open("a") as out:
            out.write(json.dumps({"phase": phase, "args": args}) + "\\n")
        if phase == "run":
            if failure == "runner":
                sys.exit(7)
            assert args[-2:] == ["--max-new-cases", "6"]
            directory = study / "predictions/case"
            directory.mkdir(parents=True)
            status = "401" if failure == "auth" else "200"
            value = {"model_usage": {"http_status_counts": {status: 1}}}
            text = "not json" if failure == "malformed" else json.dumps(value)
            (directory / "result.json").write_text(text)
            (study / "predictions/seal.sha256").write_text("fixture seal")
        elif phase == "score":
            if failure == "judge":
                sys.exit(8)
            assert (study / "predictions/seal.sha256").is_file()
            assert args[-2:] == ["--max-new-judgements", "6"]
            directory = study / "judgements/case"
            directory.mkdir(parents=True)
            (directory / "usage.json").write_text(json.dumps({"http_status_counts": {"200": 1}}))
            (study / "scores.json").write_text("{}")
        else:
            assert (study / "scores.json").is_file()
    """)
    )
    stub.chmod(0o700)
    env = {
        **os.environ,
        "PATH": f"{commands}:{os.environ['PATH']}",
        "ASKDU_TEST_STUDY_FAILURE": failure,
    }
    result = subprocess.run(
        ["bash", str(scripts / "run_agentic_open_study.sh"), "run"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
    )
    phases = [
        json.loads(line)["phase"]
        for line in (tmp_path / "test-invocations.jsonl").read_text().splitlines()
    ]
    if failure == "none":
        assert result.returncode == 0, result.stderr
        assert phases == ["run", "score", "summary"]
    elif failure == "judge":
        assert result.returncode != 0
        assert phases == ["run", "score"]
    else:
        assert result.returncode != 0
        assert phases == ["run"]
