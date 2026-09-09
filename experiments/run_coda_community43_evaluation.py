from __future__ import annotations

import argparse
import csv
import json
import platform
import statistics
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
from askdu.domain import DiagnosisKind, DiscoveryMode, RepairGuidance, RunStatus

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_ROOT = (
    PROJECT_ROOT / "data/external/coda-bench/communities/community_43/full_community"
)
DEFAULT_BENCHMARK = PROJECT_ROOT / "data/external/coda-bench/coda_bench.json"
PROVENANCE_MANIFEST = (
    PROJECT_ROOT / "data/manifests/coda-public-source-provenance-v1.json"
)
CODA_REVISION = "63828a2b652e26a9770555a0cc41e6c8aafdb5d9"
TASK_IDS = (175, 176, 177, 178, 179, 180, 955, 956, 957, 958, 959, 960, 961, 962, 963)
EXPECTED_DATA_GAP_TASK_IDS = {179}
REPAIR_REQUIRED_TASK_IDS = {175, 955, 959, 960}

REGISTRATION = "D5 SHSAT Registrations and Testers.csv"
SCHOOL_EXPLORER = "2016 School Explorer.csv"
OFFERS = "2017-2018 SHSAT Admissions Test Offers By Sending School.csv"
SHAKE_SHACK = "shake shack nutrition.csv"
FAST_FOOD = "fastfood.csv"

REQUIRED_SOURCE_NAMES: dict[int, set[str]] = {
    175: {REGISTRATION, SCHOOL_EXPLORER},
    176: {REGISTRATION},
    177: {REGISTRATION},
    178: {SCHOOL_EXPLORER},
    179: {"schma19962016.csv"},
    180: {REGISTRATION},
    955: {OFFERS, SCHOOL_EXPLORER},
    956: {SCHOOL_EXPLORER},
    957: {SCHOOL_EXPLORER},
    958: {REGISTRATION},
    959: {REGISTRATION, SCHOOL_EXPLORER},
    960: {SHAKE_SHACK, FAST_FOOD},
    961: {SCHOOL_EXPLORER},
    962: {SCHOOL_EXPLORER},
    963: {SCHOOL_EXPLORER},
}

MODES = (
    ("linear", 0, DiscoveryMode.PROGRESSIVE, RepairGuidance.VIOLATION),
    ("static_retry", 2, DiscoveryMode.PROGRESSIVE, RepairGuidance.STATIC_QUERY),
    ("closed_loop", 2, DiscoveryMode.PROGRESSIVE, RepairGuidance.VIOLATION),
    ("full_profile", 0, DiscoveryMode.FULL_CATALOG, RepairGuidance.VIOLATION),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate all 15 tasks in the downloaded CoDA community_43."
    )
    parser.add_argument("--data-root", type=Path, default=DEFAULT_DATA_ROOT)
    parser.add_argument("--benchmark", type=Path, default=DEFAULT_BENCHMARK)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "experiments/results/coda-community43",
    )
    return parser.parse_args()


def benchmark_tasks(path: Path) -> list[dict[str, Any]]:
    rows = json.loads(path.read_text(encoding="utf-8"))
    tasks = {int(row["instance_id"]): row for row in rows}
    return [tasks[task_id] for task_id in TASK_IDS]


def task_class(task_id: int) -> str:
    if task_id in EXPECTED_DATA_GAP_TASK_IDS:
        return "data_gap"
    if task_id in REPAIR_REQUIRED_TASK_IDS:
        return "cross_source_repair"
    return "no_repair"


def run_mode(
    name: str,
    service: RunService,
    task: dict[str, Any],
    output_dir: Path,
) -> dict[str, Any]:
    task_id = int(task["instance_id"])
    started = time.perf_counter()
    state = service.run(str(task["question"]))
    elapsed_ms = (time.perf_counter() - started) * 1000
    answer = format_coda_pilot_answer(task_id, state)
    expected_data_gap = task_id in EXPECTED_DATA_GAP_TASK_IDS
    correct_abstention = (
        expected_data_gap
        and state.status == RunStatus.INSUFFICIENT
        and state.diagnosis is not None
        and state.diagnosis.kind == DiagnosisKind.DATA_GAP
    )
    exact_match = not expected_data_gap and answer == task["answer"]
    selected_names = {asset.name for asset in state.assets.values()}
    required_names = REQUIRED_SOURCE_NAMES[task_id]
    source_precision = (
        len(selected_names & required_names) / len(selected_names)
        if selected_names and not expected_data_gap
        else None
    )
    source_recall = (
        len(selected_names & required_names) / len(required_names)
        if not expected_data_gap
        else None
    )
    state_path = output_dir / "runs" / f"task-{task_id}-{name}.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(state.model_dump_json(indent=2), encoding="utf-8")
    return {
        "mode": name,
        "task_id": task_id,
        "task_class": task_class(task_id),
        "status": state.status.value,
        "diagnosis_kind": state.diagnosis.kind.value if state.diagnosis else None,
        "answer": answer,
        "expected_answer": None if expected_data_gap else task["answer"],
        "exact_match": exact_match,
        "correct_abstention": correct_abstention,
        "resolved": exact_match or correct_abstention,
        "repair_edges": sum(
            event.edge_kind.value == "repair" for event in state.events
        ),
        "logical_source_profiles": len(state.assets),
        "verified_source_profiles": sum(
            asset.integrity_status == "verified" for asset in state.assets.values()
        ),
        "logical_profile_bytes": sum(
            asset.byte_size for asset in state.assets.values()
        ),
        "source_precision": source_precision,
        "source_recall": source_recall,
        "metadata_assets_indexed": len(service.catalog.index()),
        "materialized_states": len(state.materialized_states),
        "mandatory_human_interventions": 0,
        "elapsed_ms": round(elapsed_ms, 3),
        "run_id": state.run_id,
        "run_state": state_path.relative_to(PROJECT_ROOT).as_posix(),
    }


def aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    answerable = [row for row in rows if row["task_class"] != "data_gap"]
    precisions = [
        float(row["source_precision"])
        for row in answerable
        if row["source_precision"] is not None
    ]
    recalls = [
        float(row["source_recall"])
        for row in answerable
        if row["source_recall"] is not None
    ]
    return {
        "tasks": len(rows),
        "reports_completed": sum(row["status"] == "completed" for row in rows),
        "exact_matches": sum(row["exact_match"] for row in rows),
        "correct_abstentions": sum(row["correct_abstention"] for row in rows),
        "resolved": sum(row["resolved"] for row in rows),
        "repair_edges": sum(row["repair_edges"] for row in rows),
        "logical_source_profiles": sum(row["logical_source_profiles"] for row in rows),
        "verified_source_profiles": sum(
            row["verified_source_profiles"] for row in rows
        ),
        "logical_profile_bytes": sum(row["logical_profile_bytes"] for row in rows),
        "mean_source_precision": round(statistics.fmean(precisions), 6),
        "mean_source_recall": round(statistics.fmean(recalls), 6),
        "mandatory_human_interventions": sum(
            row["mandatory_human_interventions"] for row in rows
        ),
    }


def main() -> None:
    args = parse_args()
    data_root = args.data_root.expanduser().resolve()
    benchmark = args.benchmark.expanduser().resolve()
    output_dir = args.output_dir.expanduser().resolve()
    if not data_root.is_dir():
        raise SystemExit(f"Missing pilot data: {data_root}")
    if not benchmark.is_file():
        raise SystemExit(f"Missing benchmark metadata: {benchmark}")

    tasks = benchmark_tasks(benchmark)
    provenance_registry = ProvenanceRegistry.from_file(PROVENANCE_MANIFEST)
    services = {
        name: RunService(
            environment_id="coda-community-43",
            data_root=data_root,
            runtime_root=output_dir / "runtime" / name,
            repository=FileRunRepository(output_dir / "runtime" / name / "state"),
            max_repair_rounds=rounds,
            discovery_mode=discovery_mode,
            repair_guidance=repair_guidance,
            catalog=FileCatalog(
                data_root,
                environment_id="coda-community-43",
                provenance_registry=provenance_registry,
            ),
        )
        for name, rounds, discovery_mode, repair_guidance in MODES
    }
    results = [
        run_mode(name, services[name], task, output_dir)
        for task in tasks
        for name, _, _, _ in MODES
    ]
    modes = {
        name: [result for result in results if result["mode"] == name]
        for name, _, _, _ in MODES
    }
    summary = {
        "experiment": "coda_community43_stopping_and_repair_evaluation",
        "system_version": __version__,
        "coda_revision": CODA_REVISION,
        "source_integrity": (
            "Every selected CSV is verified against the audited per-file SHA-256 manifest "
            "before preparation."
        ),
        "task_ids": list(TASK_IDS),
        "task_classes": {
            "no_repair": sorted(
                set(TASK_IDS) - EXPECTED_DATA_GAP_TASK_IDS - REPAIR_REQUIRED_TASK_IDS
            ),
            "cross_source_repair": sorted(REPAIR_REQUIRED_TASK_IDS),
            "data_gap": sorted(EXPECTED_DATA_GAP_TASK_IDS),
        },
        "python": platform.python_version(),
        "pandas": pd.__version__,
        "mode_definitions": {
            "linear": "Progressive discovery with no downstream-to-upstream repair.",
            "static_retry": (
                "Progressive discovery with two repair rounds that reuse the unchanged "
                "initial search terms instead of violation-conditioned terms."
            ),
            "closed_loop": "Progressive discovery with up to two typed repair rounds.",
            "full_profile": (
                "Content-profiles every authorized CSV before analysis and performs no repair."
            ),
        },
        "aggregate": {name: aggregate(rows) for name, rows in modes.items()},
        "results": results,
        "oracle_isolation": (
            "Benchmark answers and required-source sets are read only by this post-run "
            "evaluator; compiler, discovery, preparation, analysis, and reporting do not "
            "receive them."
        ),
        "cost_metric_note": (
            "All modes first index authorized file paths and CSV headers. Logical source profiles "
            "count files whose full contents a task requests for hashing and row counting; logical "
            "profile bytes sum their file sizes independently per task and intentionally ignore the "
            "in-process profile cache. They are workload-exposure measures, not physical I/O or "
            "wall-clock measurements."
        ),
        "data_gap_note": (
            "Task 179 references schproma/source/schma19962016.csv, which is absent from "
            "the pinned community archive. The local-environment target is therefore a "
            "typed data-gap diagnosis rather than the benchmark's answer string."
        ),
        "scope_warning": (
            "All 15 tasks from one CoDA community use deterministic task-family adapters. "
            "This evaluates lifecycle control and stopping behavior, not open-ended "
            "language or analysis generalization."
        ),
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
