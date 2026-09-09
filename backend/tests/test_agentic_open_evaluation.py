from __future__ import annotations

import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import httpx
import pytest

from askdu.adapters.catalog import FileCatalog
from askdu.adapters.llm import ChatModelError
from askdu.config import Settings
from askdu.heldout_integrity import HeldoutIntegrityError

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "agentic_evaluation_tests", ROOT / "experiments/agentic_open_evaluation.py"
)
assert SPEC is not None and SPEC.loader is not None
EVAL = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = EVAL
SPEC.loader.exec_module(EVAL)


def test_question_extraction_excludes_answers_and_sealed_community(tmp_path: Path) -> None:
    metadata = tmp_path / "benchmark.json"
    metadata.write_text(
        json.dumps(
            [
                {
                    "instance_id": 1,
                    "question": "Allowed question",
                    "answer": "ORACLE_SENTINEL",
                    "release_community": "community_17",
                },
                {
                    "instance_id": 2,
                    "question": "SEALED_SENTINEL",
                    "answer": "SECRET_ORACLE",
                    "release_community": "community_45",
                },
                {
                    "instance_id": 3,
                    "question": "Another question",
                    "answer": "OTHER_ORACLE",
                    "release_community": "community_18",
                },
            ]
        )
    )
    census = EVAL.metadata_census(metadata)
    sample = EVAL.select_tasks(census, {17, 18})
    assert sample == EVAL.select_tasks(dict(reversed(list(census.items()))), {18, 17})
    assert {t["task_id"] for t in sample} == {1, 3}
    questions = EVAL.selected_field(metadata, {1, 3}, "question")
    assert questions == {1: "Allowed question", 3: "Another question"}
    with pytest.raises(ValueError, match="sealed"):
        EVAL.select_tasks(census, {17, 45})


def test_schedule_keeps_three_repetitions_paired_with_identical_questions() -> None:
    tasks = [{"task_id": n, "community_id": n + 17, "question": "q"} for n in range(30)]
    scheduled = EVAL.schedule(tasks)
    assert len(scheduled) == 180
    assert len({s["case_id"] for s in scheduled}) == 180
    assert set(Counter((s["task_id"], s["mode"]) for s in scheduled).values()) == {3}
    for left, right in zip(scheduled[::2], scheduled[1::2], strict=True):
        assert left["task_id"] == right["task_id"]
        assert left["repetition"] == right["repetition"]
        assert left["mode"] != right["mode"]


class StaticModel:
    def __init__(self, responses: list[str]):
        self.responses = responses
        self.calls = 0

    def complete(self, **kwargs: Any) -> str:
        self.calls += 1
        return self.responses.pop(0)


def test_model_meter_enforces_total_budget_without_logging_prompt(tmp_path: Path) -> None:
    model = StaticModel(["answer"])
    output = tmp_path / "calls.json"
    metered = EVAL.MeteredModel(model, output, cap=1)
    assert metered.complete(system="PRIVATE_PROMPT", user="PRIVATE_INPUT") == "answer"
    with pytest.raises(ChatModelError, match="budget"):
        metered.complete(system="PRIVATE_PROMPT", user="PRIVATE_INPUT")
    assert model.calls == 1
    assert "PRIVATE" not in output.read_text()
    assert EVAL.read_json(output)["calls"][0]["output_characters"] == 6


def test_plan_tamper_is_rejected_before_execution(tmp_path: Path, monkeypatch: Any) -> None:
    plan = {
        "protocol_id": EVAL.PROTOCOL,
        "modes": EVAL.MODES,
        "limits": EVAL.LIMITS,
        "tasks": [{"task_id": 1, "community_id": 17, "question": "q"}],
    }
    plan["schedule"] = EVAL.schedule(plan["tasks"])
    EVAL.exclusive_json(tmp_path / "plan.json", plan)
    EVAL.exclusive_json(tmp_path / "freeze.json", {"plan_sha256": EVAL.canonical_json_sha256(plan)})
    plan["tasks"][0]["question"] = "silently replace with an easier question"
    (tmp_path / "plan.json").write_text(json.dumps(plan))
    monkeypatch.setattr(EVAL, "source_hash", lambda: pytest.fail("Hash should not be reached"))
    with pytest.raises(ValueError, match="Plan drifted"):
        EVAL.validate_plan(tmp_path)


def test_interrupted_cases_stay_in_denominator_and_are_not_rerun(
    tmp_path: Path, monkeypatch: Any
) -> None:
    tasks = [{"task_id": 1, "community_id": 17, "question": "q"}]
    plan = {"tasks": tasks, "schedule": EVAL.schedule(tasks)}
    predictions = tmp_path / "predictions"
    predictions.mkdir()
    for case in plan["schedule"]:
        (predictions / case["case_id"]).mkdir()
    monkeypatch.setattr(EVAL, "validate_plan", lambda _: plan)
    monkeypatch.setattr(
        EVAL, "execute_worker", lambda *args: pytest.fail("Cannot replay started case")
    )
    EVAL.execute_schedule(tmp_path, plan, None, tmp_path / "not-read.env", max_new_cases=2)
    summary = EVAL.read_json(predictions / "summary.json")
    assert len(summary["results"]) == 6
    assert {row["status"] for row in summary["results"]} == {"interrupted"}
    EVAL.verify_seal(predictions)
    # A resumed completed sweep must only verify the seal.
    EVAL.execute_schedule(tmp_path, plan, None, tmp_path / "not-read.env", max_new_cases=2)


def test_scoring_cannot_open_oracle_before_complete_seal(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setattr(EVAL, "validate_plan", lambda _: {})
    monkeypatch.setattr(
        EVAL, "selected_field", lambda *args: pytest.fail("Oracle opened too early")
    )
    with pytest.raises(HeldoutIntegrityError):
        EVAL.score(tmp_path, tmp_path / "not-read.env", max_new_judgements=2)


def test_bounded_batches_resume_without_repeating_calls_or_sealing_early(
    tmp_path: Path, monkeypatch: Any
) -> None:
    tasks = [{"task_id": 1, "community_id": 17, "question": "q"}]
    plan = {"tasks": tasks, "schedule": EVAL.schedule(tasks)}
    started = []

    class ImmediateProcess:
        pid = 12345
        exitcode = 0

        def __init__(self, *, target: Any, args: tuple[Any, ...]):
            self.args = args

        def start(self) -> None:
            case, _, directory, _, _, plan_sha = self.args
            started.append(case["case_id"])
            EVAL.exclusive_json(
                directory / "result.json",
                {**case, "plan_sha256": plan_sha, "status": "completed"},
            )

        def join(self, timeout: int) -> None:
            pass

        def is_alive(self) -> bool:
            return False

    class ImmediateContext:
        Process = ImmediateProcess

    monkeypatch.setattr(EVAL, "validate_plan", lambda _: plan)
    monkeypatch.setattr(EVAL.multiprocessing, "get_context", lambda _: ImmediateContext())
    monkeypatch.setattr(EVAL, "selected_field", lambda *args: pytest.fail("No oracle access"))
    for batch in range(1, 4):
        EVAL.execute_schedule(tmp_path, plan, None, tmp_path / "unused.env", max_new_cases=2)
        assert len(started) == batch * 2
        assert len(set(started)) == len(started)
        progress = EVAL.read_json(tmp_path / "progress.json")
        assert progress["completed_cases"] == batch * 2
        if batch < 3:
            assert progress["status"] == "paused_at_batch_limit"
            assert not (tmp_path / "predictions/seal.sha256").exists()
            assert not (tmp_path / "predictions/summary.json").exists()
            with pytest.raises(HeldoutIntegrityError):
                EVAL.score(tmp_path, tmp_path / "unused.env", max_new_judgements=2)
        else:
            assert progress["status"] == "sealed"
            EVAL.verify_seal(tmp_path / "predictions")


def test_batch_budget_is_required_before_touching_runtime_or_provider(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="budget"):
        EVAL.run(tmp_path, tmp_path / "unused.env", max_new_cases=0)
    with pytest.raises(ValueError, match="budget"):
        EVAL.score(tmp_path, tmp_path / "unused.env", max_new_judgements=0)
    assert list(tmp_path.iterdir()) == []


def test_judgement_batches_preserve_grades_and_publish_only_complete_scores(
    tmp_path: Path, monkeypatch: Any
) -> None:
    tasks = [{"task_id": 1, "community_id": 17, "question": "q"}]
    metadata = tmp_path / "metadata.json"
    metadata.write_text("[]")
    plan = {
        "tasks": tasks,
        "schedule": EVAL.schedule(tasks),
        "metadata_sha256": EVAL.sha256_file(metadata),
    }
    rows = [{**case, "status": "failed", "report_available": False} for case in plan["schedule"]]
    predictions = tmp_path / "predictions"
    predictions.mkdir()
    EVAL.exclusive_json(predictions / "plan.json", plan)
    EVAL.exclusive_json(predictions / "summary.json", {"results": rows})
    EVAL.build_seal(predictions, predictions / "seal.sha256")
    monkeypatch.setattr(EVAL, "METADATA", metadata)
    monkeypatch.setattr(EVAL, "validate_plan", lambda _: plan)
    monkeypatch.setattr(EVAL, "source_hash", lambda: "a" * 64)
    monkeypatch.setattr(EVAL, "selected_field", lambda *args: {1: "answer"})
    monkeypatch.setattr(EVAL, "settings_for_worker", lambda *args: None)
    model = StaticModel([])
    monkeypatch.setattr(EVAL, "build_chat_model", lambda _: model)
    previous_grades: dict[Path, bytes] = {}
    for batch in range(1, 4):
        EVAL.score(tmp_path, tmp_path / "unused.env", max_new_judgements=2)
        for path, contents in previous_grades.items():
            assert path.read_bytes() == contents
        previous_grades = {
            path: path.read_bytes() for path in (tmp_path / "judgements").glob("*/grade.json")
        }
        assert len(previous_grades) == batch * 2
        assert (tmp_path / "scores.json").exists() is (batch == 3)
    scores = EVAL.read_json(tmp_path / "scores.json")
    assert len(scores["results"]) == 6
    assert scores["judge_verdict_counts"] == {"incorrect": 6}
    assert set(scores["paired_macro_differences"].values()) == {0}
    assert model.calls == 0
    # Repeated scoring of a completed sealed study never constructs a new client.
    monkeypatch.setattr(EVAL, "build_chat_model", lambda _: pytest.fail("No new client"))
    EVAL.score(tmp_path, tmp_path / "unused.env", max_new_judgements=2)


def test_judge_rejects_malformed_verdicts_and_records_unscorable() -> None:
    model = StaticModel(['{"answer":"correct"}', '{"answer":"correct"}'])
    grade = EVAL.judge_report(model, {"question": "q", "reference_answer": "a"})
    assert grade["answer"] == "unscorable"
    assert model.calls == 2
    oversized = StaticModel([])
    assert EVAL.judge_report(oversized, {"report": "x" * 180001})["answer"] == "unscorable"
    assert oversized.calls == 0


class SumAgent:
    def __init__(self, asset_id: str):
        self.asset_id = asset_id
        self.discovery = 0
        self.preparation = 0
        self.phases: list[str] = []

    def complete(self, *, system: str, user: str, **kwargs: Any) -> str:
        if system == EVAL.DISCOVERY_SYSTEM_PROMPT:
            self.phases.append("discovery")
            actions = [
                {"action": "search_catalog", "terms": ["sales"], "limit": 5},
                {"action": "inspect_asset", "asset_id": self.asset_id},
                {
                    "action": "select_sources",
                    "asset_ids": [self.asset_id],
                    "reason": "Inspected sales amounts",
                },
            ]
            action = actions[self.discovery]
            self.discovery += 1
            return json.dumps(action)
        if system == EVAL.PREPARATION_SYSTEM_PROMPT:
            self.phases.append("preparation")
            self.preparation += 1
            if self.preparation == 1:
                return json.dumps(
                    {
                        "action": "expand",
                        "reason": "Execute a sum of amount",
                        "plan": {
                            "summary": "Sum sales amounts",
                            "search_terms": ["sales"],
                            "sources": [
                                {
                                    "alias": "sales",
                                    "asset_id": self.asset_id,
                                    "required_columns": ["amount"],
                                    "purpose": "amounts",
                                }
                            ],
                            "analyses": [
                                {
                                    "type": "aggregate",
                                    "name": "total",
                                    "table": "sales",
                                    "function": "sum",
                                    "column": "amount",
                                }
                            ],
                            "primary_table": "sales",
                            "report_title": "Total sales",
                        },
                    }
                )
            return json.dumps(
                {
                    "action": "finish",
                    "candidate_id": "candidate_1",
                    "reason": "Executed sum is available",
                }
            )
        assert system == EVAL.REPORT_SYSTEM_PROMPT
        self.phases.append("report")
        refs = [a["artifact_id"] for a in json.loads(user)["evidence_packet"]["artifacts"]]
        return json.dumps(
            {
                "title": "Sales report",
                "executive_summary": "Total is 3.",
                "executive_artifact_refs": refs,
                "sections": [
                    {
                        "title": "Total",
                        "narrative": "The executed total is 3.",
                        "artifact_refs": refs,
                    }
                ],
                "conclusion": "Total sales amount is 3.",
                "conclusion_artifact_refs": refs,
                "limitations": ["Only the supplied sales records are covered."],
            }
        )


def test_evaluation_worker_runs_discovery_prep_analysis_and_report(
    tmp_path: Path, monkeypatch: Any
) -> None:
    data = tmp_path / "data"
    data.mkdir()
    (data / "sales.csv").write_text("amount\n1\n2\n")
    catalog = FileCatalog(data, environment_id="synthetic-eval")
    asset = next(iter(catalog.index().values()))
    model = SumAgent(asset.asset_id)
    monkeypatch.setattr(EVAL.resource, "setrlimit", lambda *args: None)
    monkeypatch.setattr(EVAL, "build_chat_model", lambda _, **kwargs: model)
    monkeypatch.setattr(
        EVAL,
        "settings_for_worker",
        lambda env, runtime, repairs: Settings(
            _env_file=None, runtime_root=runtime, max_repair_rounds=repairs
        ),
    )
    case = {"case_id": "synthetic", "task_id": 1, "mode": "closed_loop", "repetition": 1}
    directory = tmp_path / "case"
    directory.mkdir()
    EVAL.execute_worker(
        case, "What is the total sales amount?", directory, catalog, tmp_path / "unused", "f" * 64
    )
    result = EVAL.read_json(directory / "result.json")
    assert result["status"] == "completed", result
    assert result["prediction"] == "3"
    assert result["reference_integrity"] is True
    assert result["notebook_phase_counts"]["execute"] == 1
    assert result["notebook_phase_counts"]["report"] == 1
    assert set(model.phases) == {"discovery", "preparation", "report"}
    assert len(EVAL.read_json(directory / "model-calls.json")["calls"]) == 6
    assert result["model_usage"]["logical_calls"] == 6


def test_timeout_cases_retain_usage_and_racing_terminal_results(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    tasks = [{"task_id": 1, "community_id": 17, "question": "q"}]
    plan = {"tasks": tasks, "schedule": EVAL.schedule(tasks)}

    class TimedOutProcess:
        pid = 12345
        exitcode = -15

        def __init__(self, *, target: Any, args: tuple[Any, ...]):
            self.args, self.alive = args, True

        def start(self) -> None:
            case, _, directory, _, _, plan_sha = self.args
            EVAL.exclusive_json(
                directory / "model-calls.json",
                {
                    "schema_version": EVAL.METER_SCHEMA,
                    "calls": [
                        {
                            "status": "started",
                            "http_observed": True,
                            "http_attempts": [{"status": "started", "usage_status": "unavailable"}],
                        }
                    ],
                },
            )
            EVAL.exclusive_json(
                directory / "result.json",
                {
                    **case,
                    "status": "completed",
                    "plan_sha256": plan_sha,
                },
            )

        def join(self, timeout: int) -> None:
            pass

        def is_alive(self) -> bool:
            return self.alive

        def terminate(self) -> None:
            self.alive = False

    class Context:
        Process = TimedOutProcess

    monkeypatch.setattr(EVAL, "validate_plan", lambda _: plan)
    monkeypatch.setattr(EVAL.multiprocessing, "get_context", lambda _: Context())
    EVAL.execute_schedule(tmp_path, plan, None, tmp_path / "unused.env", max_new_cases=6)
    rows = EVAL.read_json(tmp_path / "predictions/summary.json")["results"]
    assert len(rows) == 6
    for row in rows:
        assert row["status"] == "timeout"
        assert row["driver_wall_seconds"] >= 0
        assert row["model_usage"]["unresolved_http_attempts"] == 1
        assert row["model_usage"]["tokens"]["total_tokens"]["observed_total"] is None
        retained = tmp_path / "predictions" / row["case_id"] / "worker-terminal-before-timeout.json"
        assert EVAL.read_json(retained)["status"] == "completed"
    EVAL.verify_seal(tmp_path / "predictions")


def test_judge_uses_the_same_metered_provider_without_rerunning_saved_grades(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "id": "mock",
                "object": "chat.completion",
                "created": 0,
                "model": EVAL.PROJECT_LLM_MODEL,
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {
                            "role": "assistant",
                            "content": json.dumps(
                                {
                                    "answer": "correct",
                                    "grounding": "supported",
                                    "reason": "Synthetic agreement",
                                }
                            ),
                        },
                    }
                ],
                "usage": {"prompt_tokens": 100, "completion_tokens": 30, "total_tokens": 130},
            },
        )

    original_client = EVAL.MeteredHttpClient
    monkeypatch.setattr(
        EVAL,
        "MeteredHttpClient",
        lambda **kwargs: original_client(
            timeout=1,
            transport=httpx.MockTransport(handler),
        ),
    )
    settings = Settings(
        _env_file=None,
        llm_base_url="https://not-called.invalid/api?api-version=test",
        llm_model=EVAL.PROJECT_LLM_MODEL,
        llm_api_key="synthetic-test-key",
        llm_api_style="azure_chat",
        llm_auth_scheme="api_key",
        llm_token_field="max_completion_tokens",
        llm_allow_test_provider=True,
    )
    row = {"case_id": "synthetic", "report_available": True}
    directory = tmp_path / "predictions/synthetic"
    directory.mkdir(parents=True)
    EVAL.exclusive_json(
        directory / "run.json",
        {
            "report": {
                "title": "Synthetic",
                "executive_summary": "One",
                "sections": [],
                "conclusion": "One",
                "limitations": [],
            },
            "artifacts": [],
        },
    )
    grade = EVAL.judge_case(tmp_path, row, "question", "one", settings)
    assert grade["answer"] == "correct"
    assert EVAL.judge_case(tmp_path, row, "question", "one", settings) == grade
    assert len(requests) == 1
    usage = EVAL.read_json(tmp_path / "judgements/synthetic/usage.json")
    assert usage["logical_calls"] == usage["http_attempts_started"] == 1
    assert usage["tokens"]["total_tokens"]["observed_total"] == 130
    journal = EVAL.read_json(tmp_path / "judgements/synthetic/model-calls.json")
    assert journal["calls"][0]["phase"] == "judge"
