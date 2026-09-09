from __future__ import annotations

import json
import math
import statistics
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_PATH = PROJECT_ROOT / "experiments/evidence/demo-path-latency-v0.4.0.json"
PAPER_PATH = PROJECT_ROOT / "paper/main.tex"
EVALUATION_PATH = PROJECT_ROOT / "docs/evaluation.md"
EXPECTED_SCENARIOS = {
    959: ("Join repair", "completed", None, [1]),
    960: ("Coverage repair", "completed", None, [1]),
    176: ("Direct answer", "completed", None, [0]),
    179: ("Honest data gap", "insufficient", "data_gap", [0]),
}


def summarize(samples: list[float]) -> dict[str, float | int]:
    if not samples:
        raise ValueError("latency evidence contains an empty sample set")
    if any(not math.isfinite(value) or value <= 0 for value in samples):
        raise ValueError("latency samples must be positive finite numbers")
    ordered = sorted(samples)
    p95_rank = max(1, math.ceil(0.95 * len(ordered)))
    return {
        "count": len(ordered),
        "min": round(ordered[0], 3),
        "median": round(statistics.median(ordered), 3),
        "p95": round(ordered[p95_rank - 1], 3),
        "max": round(ordered[-1], 3),
    }


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def validate_evidence(evidence: dict[str, Any]) -> dict[str, float | int]:
    require(evidence.get("schema_version") == "1.0", "unexpected evidence schema")
    service = evidence.get("service")
    require(isinstance(service, dict), "missing service metadata")
    require(service.get("version") == "0.4.0", "unexpected service version")
    require(
        service.get("environment_id") == "coda-community-43",
        "unexpected measured environment",
    )
    require(service.get("planner_mode") == "registry", "measurement used model mode")
    require(service.get("csv_assets") == 10, "unexpected catalog size")

    protocol = evidence.get("protocol")
    require(isinstance(protocol, dict), "missing measurement protocol")
    require(protocol.get("warmups_per_scenario") == 1, "unexpected warm-up count")
    repetitions = protocol.get("repetitions_per_scenario")
    require(repetitions == 10, "unexpected repetition count")
    require(protocol.get("interval_seconds") == 2.05, "unexpected request pacing")
    require(
        protocol.get("percentile_definition") == "nearest-rank P95",
        "unexpected percentile definition",
    )
    require(
        protocol.get("proxy_environment_inherited") is False,
        "measurement unexpectedly inherited a proxy",
    )

    scenarios = evidence.get("scenarios")
    require(isinstance(scenarios, list), "missing scenario measurements")
    require(len(scenarios) == len(EXPECTED_SCENARIOS), "unexpected scenario count")
    observed_ids = {
        record.get("task_id") for record in scenarios if isinstance(record, dict)
    }
    require(observed_ids == set(EXPECTED_SCENARIOS), "scenario census mismatch")

    all_samples: list[float] = []
    for record in scenarios:
        require(isinstance(record, dict), "scenario record is not an object")
        task_id = record["task_id"]
        expected_label, expected_status, expected_diagnosis, expected_edges = (
            EXPECTED_SCENARIOS[task_id]
        )
        require(record.get("label") == expected_label, f"task {task_id} label mismatch")
        require(
            record.get("terminal_status") == expected_status,
            f"task {task_id} terminal mismatch",
        )
        require(
            record.get("diagnosis_kind") == expected_diagnosis,
            f"task {task_id} diagnosis mismatch",
        )
        require(
            record.get("observed_repair_edges") == expected_edges,
            f"task {task_id} repair-edge mismatch",
        )
        raw_samples = record.get("samples_ms")
        require(isinstance(raw_samples, list), f"task {task_id} has no raw samples")
        require(
            len(raw_samples) == repetitions,
            f"task {task_id} repetition count mismatch",
        )
        samples = [float(value) for value in raw_samples]
        require(
            record.get("latency_ms") == summarize(samples),
            f"task {task_id} latency summary does not match raw samples",
        )
        all_samples.extend(samples)

    expected_overall = summarize(all_samples)
    require(
        evidence.get("overall_latency_ms") == expected_overall,
        "overall latency summary does not match raw samples",
    )
    require(expected_overall["count"] == 40, "expected exactly 40 measured requests")
    limitations = evidence.get("limitations")
    require(
        isinstance(limitations, list) and len(limitations) >= 4, "missing limitations"
    )
    return expected_overall


def main() -> None:
    evidence = json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))
    if not isinstance(evidence, dict):
        raise SystemExit("latency evidence must be a JSON object")
    try:
        summary = validate_evidence(evidence)
    except (KeyError, TypeError, ValueError) as exc:
        raise SystemExit(f"Latency evidence verification failed: {exc}") from exc

    paper = PAPER_PATH.read_text(encoding="utf-8")
    paper_value = (
        f"${float(summary['median']):.1f}/{float(summary['p95']):.1f}/"
        f"{float(summary['max']):.1f}$\\,ms"
    )
    if paper_value not in paper:
        raise SystemExit(f"paper is not synchronized to latency value {paper_value}")

    evaluation = EVALUATION_PATH.read_text(encoding="utf-8")
    evaluation_row = (
        f"| **All 40 requests** | — | **{float(summary['median']):.3f}** | "
        f"**{float(summary['p95']):.3f}** | **{float(summary['max']):.3f}** |"
    )
    if evaluation_row not in evaluation:
        raise SystemExit("evaluation record is not synchronized to latency evidence")
    print(
        "PASS: 40 raw production-path latency samples reproduce the scenario and "
        "paper summaries."
    )


if __name__ == "__main__":
    main()
