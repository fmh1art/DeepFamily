"""Audit and summarize a completely sealed, scored open study without model calls."""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import statistics
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from askdu.adapters.provider_metering import read_usage_summary, summarize_calls
from askdu.heldout_integrity import canonical_json_sha256, sha256_file, verify_seal

ROOT = Path(__file__).resolve().parents[1]
MODES = ("no_cross_stage_repair", "closed_loop")
METRICS = (
    "judge_answer_correct",
    "judge_supported_report",
    "answer_exact_agreement",
    "numeric_sequence_agreement",
    "report_available",
    "reference_integrity",
)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def validate_rows(
    plan: dict[str, Any], sealed: list[dict[str, Any]], scores: dict[str, Any]
) -> list[dict[str, Any]]:
    rows = scores["results"]
    expected = [case["case_id"] for case in plan["schedule"]]
    require(len(expected) == len(set(expected)), "Duplicate scheduled case")
    require(
        [row["case_id"] for row in sealed] == expected, "Incomplete prediction census"
    )
    require([row["case_id"] for row in rows] == expected, "Incomplete scoring census")
    plan_sha = canonical_json_sha256(plan)
    for case, original, row in zip(plan["schedule"], sealed, rows, strict=True):
        require(
            all(original.get(k) == v for k, v in case.items()), "Case identity drift"
        )
        require(original.get("plan_sha256") == plan_sha, "Case plan digest drift")
        require(
            all(row.get(k) == v for k, v in original.items()), "Scored prediction drift"
        )
        require(
            row["judge"]["answer"]
            in {"correct", "partially_correct", "incorrect", "unscorable"},
            "Invalid answer grade",
        )
        require(
            row["judge"]["grounding"] in {"supported", "unsupported", "uncertain"},
            "Invalid grounding grade",
        )
        require(
            bool(row.get("report_available"))
            or (
                row["judge"]["answer"] in {"incorrect", "unscorable"}
                and row["judge"]["grounding"] == "uncertain"
            ),
            "A missing report cannot receive a successful grade",
        )
        require(
            row["judge_answer_correct"] is (row["judge"]["answer"] == "correct"),
            "Answer grade/count drift",
        )
        require(
            row["judge_supported_report"]
            is (
                bool(row.get("report_available"))
                and row["judge"]["grounding"] == "supported"
            ),
            "Grounding grade/count drift",
        )
        require(
            all(type(row.get(m, False)) is bool for m in METRICS), "Non-boolean metric"
        )
    return rows


def usage_totals(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Keep missing journals/receipts visible; unknown is never coerced to zero."""
    result: dict[str, Any] = {
        "cases": len(records),
        "availability": dict(
            Counter(r.get("availability", "missing") for r in records)
        ),
    }
    for field in (
        "logical_calls",
        "http_attempts_started",
        "additional_http_attempts",
        "http_attempts_not_sent",
        "unresolved_logical_calls",
        "unresolved_http_attempts",
    ):
        values = [r[field] for r in records if type(r.get(field)) is int]
        require(all(v >= 0 for v in values), "Negative usage counter")
        result[field] = {
            "observed_total": sum(values) if values else None,
            "cases_with_value": len(values),
            "cases_without_value": len(records) - len(values),
        }
    statuses: Counter[str] = Counter()
    for record in records:
        statuses.update(record.get("http_status_counts", {}))
    result["http_status_counts"] = dict(statuses)
    result["tokens"] = {}
    for field in ("prompt_tokens", "completion_tokens", "total_tokens"):
        counters = [r["tokens"][field] for r in records if field in r.get("tokens", {})]
        values = [
            c["observed_total"] for c in counters if c["observed_total"] is not None
        ]
        require(all(type(v) is int and v >= 0 for v in values), "Invalid token receipt")
        result["tokens"][field] = {
            "observed_total": sum(values) if values else None,
            "attempts_with_value": sum(c["attempts_with_value"] for c in counters),
            "attempts_without_value": sum(
                c["attempts_without_value"] for c in counters
            ),
            "cases_without_token_counters": len(records) - len(counters),
        }
    return result


def aggregate(plan: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    repeats = plan["repetitions"]
    modes = {}
    pairs = []
    for mode in MODES:
        subset = [r for r in rows if r["mode"] == mode]
        walls = [
            r["driver_wall_seconds"]
            for r in subset
            if r.get("driver_wall_seconds") is not None
        ]
        require(
            all(type(v) in (int, float) and math.isfinite(v) and v >= 0 for v in walls),
            "Invalid observed duration",
        )
        modes[mode] = {
            "cases": len(subset),
            "status_counts": dict(Counter(r["status"] for r in subset)),
            "answer_grades": dict(Counter(r["judge"]["answer"] for r in subset)),
            "grounding_grades": dict(Counter(r["judge"]["grounding"] for r in subset)),
            "counts": {m: sum(r.get(m, False) for r in subset) for m in METRICS},
            "driver_wall_seconds": {
                "observed_cases": len(walls),
                "missing_cases": len(subset) - len(walls),
                "sum": sum(walls) if walls else None,
                "median": statistics.median(walls) if walls else None,
            },
            "execution_usage": usage_totals([r["model_usage"] for r in subset]),
            "judge_usage": usage_totals([r["judge_usage"] for r in subset]),
        }
    for task in plan["tasks"]:
        rates = {}
        for mode in MODES:
            subset = [
                r for r in rows if r["task_id"] == task["task_id"] and r["mode"] == mode
            ]
            require(len(subset) == repeats, "Incomplete question/mode repetitions")
            require(
                {r["repetition"] for r in subset} == set(range(1, repeats + 1)),
                "Duplicate or missing repetition",
            )
            rates[mode] = {
                m: sum(r.get(m, False) for r in subset) / repeats for m in METRICS
            }
        pairs.append(
            {
                "task_id": task["task_id"],
                "community_id": task["community_id"],
                "rates": rates,
                "closed_loop_minus_no_repair": {
                    m: rates["closed_loop"][m] - rates["no_cross_stage_repair"][m]
                    for m in METRICS
                },
            }
        )
    require(len(rows) == len(plan["tasks"]) * repeats * len(MODES), "Extra cases")
    return {
        "modes": modes,
        "question_level_pairs": pairs,
        "paired_macro_differences": {
            m: sum(p["closed_loop_minus_no_repair"][m] for p in pairs) / len(pairs)
            for m in METRICS
        },
    }


def load_plan(study: Path) -> dict[str, Any]:
    spec = importlib.util.spec_from_file_location(
        "askdu_frozen_open_evaluation", ROOT / "experiments/agentic_open_evaluation.py"
    )
    assert spec is not None and spec.loader is not None
    evaluator = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = evaluator
    spec.loader.exec_module(evaluator)
    return evaluator.validate_plan(study)


def audit(study: Path) -> dict[str, Any]:
    plan = load_plan(study)
    require(
        len(plan["tasks"]) == 30 and len(plan["schedule"]) == 180,
        "Not the complete 180-case study",
    )
    seal = verify_seal(
        study / "predictions", required_paths=["plan.json", "summary.json"]
    )
    require(read_json(study / "predictions/plan.json") == plan, "Sealed plan drift")
    summary = read_json(study / "predictions/summary.json")
    require(summary["plan_sha256"] == canonical_json_sha256(plan), "Summary plan drift")
    scores = read_json(study / "scores.json")
    require(
        scores["prediction_seal_sha256"] == seal.manifest_sha256, "Scoring seal drift"
    )
    require(scores["source_sha256"] == plan["source_sha256"], "Scoring source drift")
    rows = validate_rows(plan, summary["results"], scores)
    for row in rows:
        case = row["case_id"]
        prediction = study / "predictions" / case
        judgement = study / "judgements" / case
        require(
            read_json(prediction / "result.json")
            == next(r for r in summary["results"] if r["case_id"] == case),
            "Result/summary drift",
        )
        require(
            read_usage_summary(prediction / "model-calls.json") == row["model_usage"],
            "Execution journal drift",
        )
        require(
            read_json(judgement / "grade.json") == row["judge"], "Judge grade drift"
        )
        require(
            read_json(judgement / "usage.json") == row["judge_usage"],
            "Judge usage drift",
        )
        expected_usage = read_usage_summary(judgement / "model-calls.json")
        if row["judge_usage"].get("availability") == "not_called":
            require(
                not row.get("report_available")
                and not (judgement / "model-calls.json").exists(),
                "Unproven zero-call judge",
            )
            expected_usage = {"availability": "not_called", **summarize_calls([])}
        require(row["judge_usage"] == expected_usage, "Judge journal drift")
    result = aggregate(plan, rows)
    require(
        result["question_level_pairs"] == scores["question_level_pairs"],
        "Question-level summary drift",
    )
    require(
        result["paired_macro_differences"] == scores["paired_macro_differences"],
        "Macro summary drift",
    )
    require(
        dict(Counter(r["judge"]["answer"] for r in rows))
        == scores["judge_verdict_counts"],
        "Verdict count drift",
    )
    return {
        "schema_version": "askdu-open-study-audit-v1",
        "protocol_id": plan["protocol_id"],
        "plan_sha256": canonical_json_sha256(plan),
        "source_sha256": plan["source_sha256"],
        "prediction_seal_sha256": seal.manifest_sha256,
        "scores_sha256": sha256_file(study / "scores.json"),
        "summarizer_sha256": sha256_file(Path(__file__)),
        "interpretation": "Descriptive open-set results, not held-out or confirmatory inference. Same-model judging is a proxy requiring independent human audit. Token receipts are observations, not billing amounts. Missing cases and receipts are not zero cost.",
        **result,
    }


def render_markdown(result: dict[str, Any]) -> str:
    lines = [
        "# Complete open agentic study",
        "",
        result["interpretation"],
        "",
        "30 questions × 2 controllers × 3 repetitions = 180 cases. All failures remain in the denominator.",
        "",
        "| Measure | No cross-stage repair | Closed loop |",
        "|---|---:|---:|",
    ]
    modes = result["modes"]
    for metric in METRICS:
        values = [f"{modes[m]['counts'][metric]} / {modes[m]['cases']}" for m in MODES]
        lines.append(f"| {metric} | {' | '.join(values)} |")
    lines.extend(
        [
            "",
            "## Paired descriptive differences",
            "",
            "Closed loop minus no cross-stage repair, in percentage points. Each question has equal weight; no significance test is claimed.",
            "",
            "| Measure | Difference (pp) |",
            "|---|---:|",
        ]
    )
    for metric, difference in result["paired_macro_differences"].items():
        lines.append(f"| {metric} | {100 * difference:+.2f} |")
    lines.extend(
        [
            "",
            "## Lifecycle and wall time",
            "",
            "Wall time includes worker launch and termination waiting, not just model inference. These medians use observed cases, with missing cases shown separately.",
            "",
            "| Controller | Lifecycle counts | Median seconds | Observed cases | Missing cases |",
            "|---|---|---:|---:|---:|",
        ]
    )
    for mode in MODES:
        wall = modes[mode]["driver_wall_seconds"]
        median = "Unknown" if wall["median"] is None else f"{wall['median']:.2f}"
        statuses = "; ".join(
            f"{k}: {v}" for k, v in sorted(modes[mode]["status_counts"].items())
        )
        lines.append(
            f"| {mode} | {statuses} | {median} | {wall['observed_cases']} | {wall['missing_cases']} |"
        )
    for field, label in (("execution_usage", "Execution"), ("judge_usage", "Judge")):
        lines.extend(
            [
                "",
                f"## {label} resource observations",
                "",
                "| Controller | Calls observed | HTTP attempts observed | Tokens observed | Attempts missing token receipts | Cases missing token counters |",
                "|---|---:|---:|---:|---:|---:|",
            ]
        )
        for mode in MODES:
            usage = modes[mode][field]
            tokens = usage["tokens"]["total_tokens"]
            values = [
                mode,
                usage["logical_calls"]["observed_total"],
                usage["http_attempts_started"]["observed_total"],
                tokens["observed_total"],
                tokens["attempts_without_value"],
                tokens["cases_without_token_counters"],
            ]
            lines.append(
                "| "
                + " | ".join("Unknown" if v is None else str(v) for v in values)
                + " |"
            )
    lines.extend(["", "## Traceability", ""])
    for field in (
        "plan_sha256",
        "source_sha256",
        "prediction_seal_sha256",
        "scores_sha256",
        "summarizer_sha256",
    ):
        lines.append(f"- {field}: `{result[field]}`")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--study", type=Path, default=ROOT / "experiments/results/agentic-open-v1"
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="New output directory; existing outputs are never overwritten.",
    )
    args = parser.parse_args()
    result = audit(args.study.resolve())
    if args.output is None:
        print(json.dumps(result, indent=2))
        return
    destination = args.output.resolve()
    require(
        not destination.is_relative_to(args.study.resolve() / "predictions"),
        "Cannot write inside sealed predictions",
    )
    json_text = json.dumps(result, indent=2) + "\n"
    markdown = render_markdown(result)
    if destination.exists():
        require(
            (destination / "summary.json").read_text(encoding="utf-8") == json_text
            and (destination / "summary.md").read_text(encoding="utf-8") == markdown,
            "Existing output differs; use a new versioned output directory",
        )
    else:
        destination.mkdir(parents=True, exist_ok=False)
        (destination / "summary.json").write_text(json_text, encoding="utf-8")
        (destination / "summary.md").write_text(markdown, encoding="utf-8")
    print(destination / "summary.md")


if __name__ == "__main__":
    try:
        main()
    except (KeyError, OSError, TypeError, ValueError) as exc:
        raise SystemExit(f"ERROR: complete-study audit failed: {exc}") from None
