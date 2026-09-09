from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from askdu.heldout_integrity import (
    HeldoutIntegrityError,
    atomic_write_json,
    canonical_json_sha256,
    load_frozen_plan,
    load_json_mapping,
    project_relative,
    require_mapping,
    require_matching_plan_section,
    resolve_recorded_path,
    sha256_file,
    transition_protocol,
    verify_seal,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUN_DIR = PROJECT_ROOT / "experiments/results/coda-community45-heldout-v1"
DEFAULT_BENCHMARK = PROJECT_ROOT / "data/external/coda-bench/coda_bench.json"
DEFAULT_PROTOCOL = PROJECT_ROOT / "data/pilots/heldout-v1.json"
SCORE_FILENAME = "scored-after-oracle-unsealing.json"
SCORING_MARKER_FILENAME = "ORACLE_SCORING_STARTED.json"
TASK_IDS = (31, 32, 260, 261, 262, 263, 264, 265, 266, 267, 268, 269, 270)


def normalize_answer(value: str) -> str:
    return re.sub(r"\s+", " ", str(value).strip()).lower()


def numeric_tokens(value: str) -> list[float]:
    return [
        float(token)
        for token in re.findall(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", str(value))
    ]


def numeric_match(prediction: str, gold: str, tolerance: float = 1e-6) -> bool:
    predicted = numeric_tokens(prediction)
    expected = numeric_tokens(gold)
    return (
        bool(predicted)
        and len(predicted) == len(expected)
        and all(
            abs(left - right) <= tolerance
            for left, right in zip(predicted, expected, strict=True)
        )
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Score already sealed held-out predictions after oracle unsealing."
    )
    parser.add_argument("--run-dir", type=Path, default=DEFAULT_RUN_DIR)
    parser.add_argument("--benchmark", type=Path, default=DEFAULT_BENCHMARK)
    parser.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def required_seal_paths() -> tuple[str, ...]:
    return (
        "FIRST_PASS_STARTED.json",
        "sealed-summary-without-oracle.json",
        *(f"runs/task-{task_id}.json" for task_id in TASK_IDS),
    )


def validate_sealed_first_pass(
    protocol: dict[str, Any], run_dir: Path
) -> dict[str, Any]:
    plan = load_frozen_plan(protocol, PROJECT_ROOT)
    require_matching_plan_section(protocol, plan, "benchmark")
    require_matching_plan_section(protocol, plan, "selection")
    paths = require_mapping(plan.get("paths"), "frozen plan paths")
    selection = require_mapping(plan.get("selection"), "frozen plan selection")
    if tuple(selection.get("task_ids", ())) != TASK_IDS:
        raise HeldoutIntegrityError("Frozen plan task IDs differ from the scorer")
    results = require_mapping(protocol.get("results"), "held-out results record")
    unblinding = require_mapping(protocol.get("unblinding"), "unblinding record")
    implementation = require_mapping(
        protocol.get("implementation_freeze"), "implementation freeze"
    )
    benchmark = require_mapping(protocol.get("benchmark"), "benchmark record")
    recorded_run = resolve_recorded_path(
        PROJECT_ROOT, results.get("run_directory"), "recorded first-pass run directory"
    )
    summary_path = resolve_recorded_path(
        PROJECT_ROOT, results.get("artifact"), "recorded first-pass summary"
    )
    seal_path = resolve_recorded_path(
        PROJECT_ROOT, results.get("seal_file"), "recorded first-pass seal"
    )
    plan_run = resolve_recorded_path(
        PROJECT_ROOT, paths.get("run_directory"), "planned first-pass run directory"
    )
    plan_summary = resolve_recorded_path(
        PROJECT_ROOT, paths.get("first_pass_summary"), "planned first-pass summary"
    )
    plan_seal = resolve_recorded_path(
        PROJECT_ROOT, paths.get("first_pass_seal"), "planned first-pass seal"
    )
    if (
        recorded_run != plan_run
        or summary_path != plan_summary
        or seal_path != plan_seal
    ):
        raise HeldoutIntegrityError("First-pass paths differ from the frozen plan")
    if run_dir != recorded_run:
        raise HeldoutIntegrityError("Run directory differs from the sealed protocol")
    if summary_path != run_dir / "sealed-summary-without-oracle.json":
        raise HeldoutIntegrityError("Recorded first-pass summary path is unexpected")
    if seal_path != run_dir / "seal.sha256":
        raise HeldoutIntegrityError("Recorded first-pass seal path is unexpected")
    verification = verify_seal(
        run_dir,
        seal_path=seal_path,
        expected_seal_sha256=results.get("seal_sha256"),
        required_paths=required_seal_paths(),
    )
    if verification.file_count != results.get("sealed_file_count"):
        raise HeldoutIntegrityError("Recorded first-pass sealed-file count mismatch")
    if sha256_file(summary_path) != results.get("artifact_sha256"):
        raise HeldoutIntegrityError("Recorded first-pass summary checksum mismatch")

    summary = load_json_mapping(summary_path, "sealed first-pass summary")
    expected_bindings = {
        "protocol_id": protocol.get("protocol_id"),
        "plan_sha256": require_mapping(
            protocol.get("frozen_plan"), "frozen plan record"
        ).get("sha256"),
        "surface_sha256": implementation.get("pre_unblinding_sha256"),
        "questions_sha256": unblinding.get("questions_sha256"),
        "data_manifest_sha256": unblinding.get("extracted_manifest_sha256"),
        "data_file_count": unblinding.get("extracted_file_count"),
        "coda_revision": benchmark.get("revision"),
        "execution_config_sha256": canonical_json_sha256(
            require_mapping(plan.get("execution"), "frozen execution configuration")
        ),
    }
    for key, expected in expected_bindings.items():
        if summary.get(key) != expected:
            raise HeldoutIntegrityError(f"Sealed first-pass {key} binding mismatch")
    if tuple(summary.get("task_ids", ())) != TASK_IDS:
        raise HeldoutIntegrityError(
            "Sealed summary task IDs differ from the frozen protocol"
        )
    rows = summary.get("results")
    if not isinstance(rows, list):
        raise HeldoutIntegrityError("Sealed first-pass results are not a list")
    observed_ids = tuple(
        int(require_mapping(row, "sealed first-pass result")["task_id"]) for row in rows
    )
    if observed_ids != TASK_IDS:
        raise HeldoutIntegrityError(
            "Sealed first-pass result census is incomplete or reordered"
        )
    return summary


def load_gold_answers(benchmark_path: Path) -> dict[int, str]:
    payload = json.loads(benchmark_path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise HeldoutIntegrityError("Benchmark metadata must be a JSON list")
    gold_by_id: dict[int, str] = {}
    for raw_row in payload:
        row = require_mapping(raw_row, "benchmark row")
        task_id = int(row["instance_id"])
        if task_id not in TASK_IDS:
            continue
        if task_id in gold_by_id:
            raise HeldoutIntegrityError(f"Benchmark repeats held-out task ID {task_id}")
        if "answer" not in row:
            raise HeldoutIntegrityError(
                f"Benchmark has no answer for held-out task {task_id}"
            )
        gold_by_id[task_id] = str(row["answer"])
    if set(gold_by_id) != set(TASK_IDS):
        raise HeldoutIntegrityError("Benchmark is missing one or more held-out answers")
    return gold_by_id


def build_score(
    *,
    protocol: dict[str, Any],
    summary: dict[str, Any],
    gold_by_id: dict[int, str],
    scored_at: str,
) -> dict[str, Any]:
    rows = summary["results"]
    prediction_by_id = {
        int(require_mapping(row, "sealed first-pass result")["task_id"]): str(
            require_mapping(row, "sealed first-pass result").get("prediction", "")
        )
        for row in rows
    }
    per_task = []
    for task_id in TASK_IDS:
        prediction = prediction_by_id[task_id]
        gold = gold_by_id[task_id]
        exact = normalize_answer(prediction) == normalize_answer(gold)
        numeric = exact or numeric_match(prediction, gold)
        per_task.append(
            {
                "task_id": task_id,
                "prediction": prediction,
                "gold": gold,
                "exact_match": exact,
                "numeric_match": numeric,
            }
        )
    return {
        "experiment": "coda_community45_prospective_heldout_v1_scored",
        "protocol_id": protocol["protocol_id"],
        "plan_sha256": require_mapping(
            protocol.get("frozen_plan"), "frozen plan record"
        )["sha256"],
        "task_ids": list(TASK_IDS),
        "scored_at": scored_at,
        "sealed_summary_sha256": sha256_file(
            resolve_recorded_path(
                PROJECT_ROOT,
                require_mapping(protocol["results"], "held-out results record")[
                    "artifact"
                ],
                "recorded first-pass summary",
            )
        ),
        "benchmark_metadata_sha256": require_mapping(
            protocol.get("benchmark"), "benchmark record"
        )["metadata_sha256"],
        "scoring_semantics": (
            "Case-insensitive whitespace-normalized exact match and ordered numeric-token "
            "match, following the pinned CoDA-Bench evaluator."
        ),
        "aggregate": {
            "tasks": len(TASK_IDS),
            "exact_matches": sum(row["exact_match"] for row in per_task),
            "numeric_matches": sum(row["numeric_match"] for row in per_task),
        },
        "results": per_task,
    }


def finalize_scored_protocol(
    *,
    protocol_path: Path,
    protocol: dict[str, Any],
    run_dir: Path,
    score_path: Path,
    marker_path: Path,
) -> dict[str, Any]:
    plan = load_frozen_plan(protocol, PROJECT_ROOT)
    paths = require_mapping(plan.get("paths"), "frozen plan paths")
    results_record = require_mapping(protocol.get("results"), "held-out results record")
    benchmark_record = require_mapping(protocol.get("benchmark"), "benchmark record")
    recorded_run = resolve_recorded_path(
        PROJECT_ROOT,
        results_record.get("run_directory"),
        "recorded first-pass run directory",
    )
    recorded_score = resolve_recorded_path(
        PROJECT_ROOT,
        results_record.get("planned_score_artifact"),
        "planned score artifact",
    )
    recorded_marker = resolve_recorded_path(
        PROJECT_ROOT,
        results_record.get("planned_oracle_marker"),
        "planned oracle marker",
    )
    plan_run = resolve_recorded_path(
        PROJECT_ROOT, paths.get("run_directory"), "planned first-pass run directory"
    )
    plan_score = resolve_recorded_path(
        PROJECT_ROOT, paths.get("score_artifact"), "planned score artifact"
    )
    plan_marker = resolve_recorded_path(
        PROJECT_ROOT, paths.get("oracle_marker"), "planned oracle marker"
    )
    if (
        run_dir != recorded_run
        or score_path != recorded_score
        or marker_path != recorded_marker
        or recorded_run != plan_run
        or recorded_score != plan_score
        or recorded_marker != plan_marker
    ):
        raise HeldoutIntegrityError("Scoring paths differ from the sealed protocol")
    score = load_json_mapping(score_path, "held-out score artifact")
    if score.get("protocol_id") != protocol.get("protocol_id"):
        raise HeldoutIntegrityError("Held-out score protocol ID mismatch")
    if score.get("plan_sha256") != require_mapping(
        protocol.get("frozen_plan"), "frozen plan record"
    ).get("sha256"):
        raise HeldoutIntegrityError("Held-out score frozen-plan binding mismatch")
    if score.get("sealed_summary_sha256") != results_record.get("artifact_sha256"):
        raise HeldoutIntegrityError(
            "Held-out score is bound to a different first-pass summary"
        )
    if score.get("benchmark_metadata_sha256") != benchmark_record.get(
        "metadata_sha256"
    ):
        raise HeldoutIntegrityError(
            "Held-out score is bound to different benchmark metadata"
        )
    if tuple(score.get("task_ids", ())) != TASK_IDS:
        raise HeldoutIntegrityError("Held-out score task census mismatch")
    rows = score.get("results")
    if not isinstance(rows, list):
        raise HeldoutIntegrityError("Held-out score results are not a list")
    observed_ids = tuple(
        int(require_mapping(row, "held-out score result")["task_id"]) for row in rows
    )
    if observed_ids != TASK_IDS:
        raise HeldoutIntegrityError("Held-out score rows are incomplete or reordered")
    aggregate = require_mapping(score.get("aggregate"), "held-out score aggregate")
    if aggregate.get("tasks") != len(TASK_IDS):
        raise HeldoutIntegrityError("Held-out score aggregate task count mismatch")
    scored_at = score.get("scored_at")
    if not isinstance(scored_at, str) or not scored_at:
        raise HeldoutIntegrityError("Held-out score timestamp is missing")
    if not isinstance(score.get("scoring_semantics"), str):
        raise HeldoutIntegrityError("Held-out scoring semantics are missing")
    marker = load_json_mapping(marker_path, "oracle-scoring marker")
    if marker.get("protocol_id") != protocol.get("protocol_id") or marker.get(
        "seal_sha256"
    ) != results_record.get("seal_sha256"):
        raise HeldoutIntegrityError("Oracle-scoring marker binding mismatch")
    if marker.get("plan_sha256") != score.get("plan_sha256"):
        raise HeldoutIntegrityError(
            "Oracle-scoring marker frozen-plan binding mismatch"
        )
    if marker.get("benchmark_metadata_sha256") != benchmark_record.get(
        "metadata_sha256"
    ):
        raise HeldoutIntegrityError("Oracle-scoring marker benchmark binding mismatch")
    return transition_protocol(
        protocol_path,
        expected_status="first_pass_sealed",
        next_status="scored",
        expected_protocol_id=str(protocol["protocol_id"]),
        results_update={
            "oracle_marker": project_relative(
                marker_path, PROJECT_ROOT, "oracle-scoring marker"
            ),
            "oracle_marker_sha256": sha256_file(marker_path),
            "score_artifact": project_relative(
                score_path, PROJECT_ROOT, "held-out score artifact"
            ),
            "score_sha256": sha256_file(score_path),
            "scored_at": scored_at,
            "scoring_semantics": score["scoring_semantics"],
        },
    )


def execute(args: argparse.Namespace) -> None:
    run_dir = args.run_dir.expanduser().resolve()
    benchmark_path = args.benchmark.expanduser().resolve()
    protocol_path = args.protocol.expanduser().resolve()
    if not protocol_path.is_file():
        raise HeldoutIntegrityError("Held-out protocol is missing")
    protocol = load_json_mapping(protocol_path, "held-out protocol")
    if protocol.get("status") == "scored":
        raise HeldoutIntegrityError(
            "Held-out first pass is already scored; duplicate refused"
        )
    if protocol.get("status") != "first_pass_sealed":
        raise HeldoutIntegrityError("Protocol is not in the sealed first-pass state")
    plan = load_frozen_plan(protocol, PROJECT_ROOT)
    summary = validate_sealed_first_pass(protocol, run_dir)
    results = require_mapping(protocol.get("results"), "held-out results record")
    expected_output = resolve_recorded_path(
        PROJECT_ROOT, results.get("planned_score_artifact"), "planned score artifact"
    )
    marker_path = resolve_recorded_path(
        PROJECT_ROOT, results.get("planned_oracle_marker"), "planned oracle marker"
    )
    paths = require_mapping(plan.get("paths"), "frozen plan paths")
    plan_output = resolve_recorded_path(
        PROJECT_ROOT, paths.get("score_artifact"), "planned score artifact"
    )
    plan_marker = resolve_recorded_path(
        PROJECT_ROOT, paths.get("oracle_marker"), "planned oracle marker"
    )
    output_path = args.output.expanduser().resolve() if args.output else expected_output
    if (
        expected_output != run_dir / SCORE_FILENAME
        or output_path != expected_output
        or expected_output != plan_output
    ):
        raise HeldoutIntegrityError(
            f"The score artifact path is frozen as {expected_output}"
        )
    if marker_path != run_dir / SCORING_MARKER_FILENAME or marker_path != plan_marker:
        raise HeldoutIntegrityError(
            "The oracle-scoring marker path differs from the freeze"
        )

    benchmark_record = require_mapping(protocol.get("benchmark"), "benchmark record")
    recorded_benchmark = resolve_recorded_path(
        PROJECT_ROOT,
        benchmark_record.get("metadata_file"),
        "recorded benchmark metadata",
    )
    if benchmark_path != recorded_benchmark:
        raise HeldoutIntegrityError("Benchmark path differs from the frozen protocol")
    plan_benchmark = resolve_recorded_path(
        PROJECT_ROOT,
        require_mapping(plan.get("benchmark"), "frozen plan benchmark").get(
            "metadata_file"
        ),
        "planned benchmark metadata",
    )
    if benchmark_path != plan_benchmark:
        raise HeldoutIntegrityError("Benchmark path differs from the frozen plan")
    if not benchmark_path.is_file():
        raise HeldoutIntegrityError("Benchmark metadata is missing")

    existing_score: dict[str, Any] | None = None
    if output_path.exists():
        if not marker_path.is_file():
            raise HeldoutIntegrityError(
                "Score artifact exists without an oracle-scoring marker"
            )
        existing_score = load_json_mapping(output_path, "held-out score artifact")
    else:
        if marker_path.exists():
            raise HeldoutIntegrityError(
                "Oracle scoring previously started without a complete score artifact"
            )
        started_at = (
            datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
        )
        try:
            with marker_path.open("x", encoding="utf-8") as handle:
                json.dump(
                    {
                        "protocol_id": protocol["protocol_id"],
                        "plan_sha256": require_mapping(
                            protocol.get("frozen_plan"), "frozen plan record"
                        )["sha256"],
                        "started_at": started_at,
                        "seal_sha256": require_mapping(
                            protocol.get("results"), "held-out results record"
                        )["seal_sha256"],
                        "benchmark_metadata_sha256": benchmark_record[
                            "metadata_sha256"
                        ],
                    },
                    handle,
                    indent=2,
                    sort_keys=True,
                )
                handle.write("\n")
        except FileExistsError as exc:
            raise HeldoutIntegrityError("Oracle scoring already started") from exc

    if sha256_file(benchmark_path) != benchmark_record.get("metadata_sha256"):
        raise HeldoutIntegrityError("Benchmark metadata checksum mismatch")
    gold_by_id = load_gold_answers(benchmark_path)
    scored_at = (
        str(existing_score.get("scored_at"))
        if existing_score is not None
        else datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    )
    scored = build_score(
        protocol=protocol,
        summary=summary,
        gold_by_id=gold_by_id,
        scored_at=scored_at,
    )
    if existing_score is not None:
        if existing_score != scored:
            raise HeldoutIntegrityError(
                "Existing score artifact does not reproduce from the sealed predictions"
            )
    else:
        atomic_write_json(output_path, scored)
    finalize_scored_protocol(
        protocol_path=protocol_path,
        protocol=protocol,
        run_dir=run_dir,
        score_path=output_path,
        marker_path=marker_path,
    )
    print(json.dumps(scored, indent=2, ensure_ascii=False, sort_keys=True))


def main() -> None:
    try:
        execute(parse_args())
    except (HeldoutIntegrityError, KeyError, TypeError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    main()
