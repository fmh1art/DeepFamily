from __future__ import annotations

import argparse
import csv
import json
import platform
import time
from pathlib import Path
from typing import Any

import pandas as pd
from askdu import __version__
from askdu.adapters.catalog import FileCatalog
from askdu.adapters.coda_pilot import format_coda_pilot_answer
from askdu.adapters.provenance import ProvenanceRegistry
from askdu.adapters.repository import FileRunRepository
from askdu.application.orchestrator import RunService
from askdu.domain import EdgeKind, RunStatus

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_ROOT = (
    PROJECT_ROOT / "data/external/coda-bench/communities/community_52/full_community"
)
DEFAULT_BENCHMARK = PROJECT_ROOT / "data/external/coda-bench/coda_bench.json"
PROVENANCE_MANIFEST = (
    PROJECT_ROOT / "data/manifests/coda-public-source-provenance-v1.json"
)
CODA_REVISION = "63828a2b652e26a9770555a0cc41e6c8aafdb5d9"
TASK_IDS = (590, 591)
REQUIRED_SOURCE_NAMES = {
    590: "unemployed_population_1978-12_to_2023-07.csv",
    591: "wages_by_education.csv",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the two deterministic transfer tasks in CoDA community_52."
    )
    parser.add_argument("--data-root", type=Path, default=DEFAULT_DATA_ROOT)
    parser.add_argument("--benchmark", type=Path, default=DEFAULT_BENCHMARK)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "experiments/results/coda-community52-transfer",
    )
    return parser.parse_args()


def benchmark_tasks(path: Path) -> list[dict[str, Any]]:
    rows = json.loads(path.read_text(encoding="utf-8"))
    tasks = {int(row["instance_id"]): row for row in rows}
    return [tasks[task_id] for task_id in TASK_IDS]


def main() -> None:
    args = parse_args()
    data_root = args.data_root.expanduser().resolve()
    benchmark = args.benchmark.expanduser().resolve()
    output_dir = args.output_dir.expanduser().resolve()
    if not data_root.is_dir():
        raise SystemExit(f"Missing transfer data: {data_root}")
    if not benchmark.is_file():
        raise SystemExit(f"Missing benchmark metadata: {benchmark}")

    runtime_root = output_dir / "runtime"
    provenance_registry = ProvenanceRegistry.from_file(PROVENANCE_MANIFEST)
    service = RunService(
        environment_id="coda-community-52",
        data_root=data_root,
        runtime_root=runtime_root,
        repository=FileRunRepository(runtime_root / "state"),
        max_repair_rounds=2,
        catalog=FileCatalog(
            data_root,
            environment_id="coda-community-52",
            provenance_registry=provenance_registry,
        ),
    )
    results: list[dict[str, Any]] = []
    for task in benchmark_tasks(benchmark):
        task_id = int(task["instance_id"])
        started = time.perf_counter()
        state = service.run(str(task["question"]))
        elapsed_ms = (time.perf_counter() - started) * 1000
        answer = format_coda_pilot_answer(task_id, state)
        state_path = output_dir / "runs" / f"task-{task_id}.json"
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(state.model_dump_json(indent=2), encoding="utf-8")
        selected_names = [asset.name for asset in state.assets.values()]
        results.append(
            {
                "task_id": task_id,
                "status": state.status.value,
                "answer": answer,
                "expected_answer": task["answer"],
                "exact_match": state.status == RunStatus.COMPLETED
                and answer == task["answer"],
                "expected_source_selected": selected_names
                == [REQUIRED_SOURCE_NAMES[task_id]],
                "repair_edges": sum(
                    event.edge_kind == EdgeKind.REPAIR for event in state.events
                ),
                "logical_source_profiles": len(state.assets),
                "verified_source_profiles": sum(
                    asset.integrity_status == "verified"
                    for asset in state.assets.values()
                ),
                "logical_profile_bytes": sum(
                    asset.byte_size for asset in state.assets.values()
                ),
                "mandatory_human_interventions": 0,
                "elapsed_ms": round(elapsed_ms, 3),
                "run_id": state.run_id,
                "run_state": state_path.relative_to(PROJECT_ROOT).as_posix(),
            }
        )

    summary = {
        "experiment": "coda_community52_deterministic_transfer_probe",
        "system_version": __version__,
        "coda_revision": CODA_REVISION,
        "source_integrity": (
            "Every selected CSV is verified against the audited per-file SHA-256 manifest "
            "before preparation."
        ),
        "task_ids": list(TASK_IDS),
        "python": platform.python_version(),
        "pandas": pd.__version__,
        "aggregate": {
            "tasks": len(results),
            "reports_completed": sum(row["status"] == "completed" for row in results),
            "exact_matches": sum(row["exact_match"] for row in results),
            "expected_sources_selected": sum(
                row["expected_source_selected"] for row in results
            ),
            "repair_edges": sum(row["repair_edges"] for row in results),
            "logical_source_profiles": sum(
                row["logical_source_profiles"] for row in results
            ),
            "verified_source_profiles": sum(
                row["verified_source_profiles"] for row in results
            ),
            "logical_profile_bytes": sum(
                row["logical_profile_bytes"] for row in results
            ),
            "mandatory_human_interventions": 0,
        },
        "oracle_isolation": (
            "Benchmark answers and required-source names are visible only to this post-run "
            "evaluator; runtime components do not receive them."
        ),
        "reference_code_note": (
            "For task 590, the supplied reference code classifies only skewness below -1 and "
            "prints 0.00% on the pinned data. The question, answer guideline, and oracle use "
            "negative skewness (<0), yielding 2 of 120 attributes or 1.67%."
        ),
        "scope_warning": (
            "These two task families were registered after inspecting community_52. This is a "
            "cross-domain executability probe, not a held-out test of language or operator "
            "generalization."
        ),
        "results": results,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    with (output_dir / "summary.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(results[0]))
        writer.writeheader()
        writer.writerows(results)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
