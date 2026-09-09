from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
from askdu import __version__
from askdu.adapters.declarative import format_declarative_answer
from askdu.application.model_compiler import PLANNER_SYSTEM_PROMPT
from askdu.bootstrap import build_run_service
from askdu.config import Settings
from askdu.domain import DeclarativeAnalysisPlan, EdgeKind
from askdu.heldout_integrity import (
    HeldoutIntegrityError,
    ManifestVerification,
    atomic_write_json,
    atomic_write_text,
    build_seal,
    canonical_json_sha256,
    load_frozen_plan,
    load_json_mapping,
    project_relative,
    require_mapping,
    require_matching_plan_section,
    resolve_recorded_path,
    sha256_file,
    transition_protocol,
    validate_execution_settings,
    verify_data_manifest,
    verify_seal,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_ROOT = (
    PROJECT_ROOT / "data/external/coda-bench/communities/community_45/full_community"
)
DEFAULT_QUESTIONS = PROJECT_ROOT / "data/pilots/heldout-v1-questions.json"
DEFAULT_PROTOCOL = PROJECT_ROOT / "data/pilots/heldout-v1.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "experiments/results/coda-community45-heldout-v1"
TASK_IDS = (31, 32, 260, 261, 262, 263, 264, 265, 266, 267, 268, 269, 270)


def current_surface_hash() -> str:
    result = subprocess.run(
        [str(PROJECT_ROOT / "scripts/hash_evaluation_surface.sh")],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the sealed first-pass model evaluation on held-out community_45."
    )
    parser.add_argument("--data-root", type=Path, default=DEFAULT_DATA_ROOT)
    parser.add_argument("--questions", type=Path, default=DEFAULT_QUESTIONS)
    parser.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def load_questions(
    path: Path, protocol_id: str, plan_sha256: str
) -> list[dict[str, Any]]:
    payload = load_json_mapping(path, "held-out questions")
    if payload.get("protocol_id") != protocol_id:
        raise HeldoutIntegrityError("Held-out question protocol ID mismatch")
    if payload.get("plan_sha256") != plan_sha256:
        raise HeldoutIntegrityError("Held-out question frozen-plan checksum mismatch")
    declared_ids = payload.get("task_ids")
    if not isinstance(declared_ids, list) or tuple(declared_ids) != TASK_IDS:
        raise HeldoutIntegrityError(
            "Held-out question task census differs from the freeze"
        )
    tasks = payload.get("tasks")
    if not isinstance(tasks, list):
        raise HeldoutIntegrityError("Held-out questions must contain a task list")
    normalized: list[dict[str, Any]] = []
    for task in tasks:
        row = require_mapping(task, "held-out question")
        question = row.get("question")
        if not isinstance(question, str) or not question.strip():
            raise HeldoutIntegrityError("Held-out question text is empty")
        normalized.append(row)
    observed_ids = tuple(int(task["task_id"]) for task in normalized)
    if observed_ids != TASK_IDS:
        raise HeldoutIntegrityError(
            f"Held-out questions do not match the frozen ordered task IDs: {observed_ids}"
        )
    return normalized


def verify_protocol_inputs(
    protocol: dict[str, Any],
    plan: dict[str, Any],
    *,
    data_root: Path,
    questions_path: Path,
    output_dir: Path,
) -> ManifestVerification:
    unblinding = require_mapping(protocol.get("unblinding"), "unblinding record")
    results = require_mapping(protocol.get("results"), "held-out results record")
    paths = require_mapping(plan.get("paths"), "frozen plan paths")
    if unblinding.get("status") != "complete":
        raise HeldoutIntegrityError("Held-out unblinding record is incomplete")
    plan_sha256 = require_mapping(
        protocol.get("frozen_plan"), "frozen plan record"
    ).get("sha256")
    if unblinding.get("plan_sha256") != plan_sha256:
        raise HeldoutIntegrityError("Unblinding record differs from the frozen plan")

    recorded_questions = resolve_recorded_path(
        PROJECT_ROOT, unblinding.get("questions_file"), "recorded questions file"
    )
    recorded_data_root = resolve_recorded_path(
        PROJECT_ROOT, unblinding.get("data_root"), "recorded analysis data root"
    )
    extracted_root = resolve_recorded_path(
        PROJECT_ROOT, unblinding.get("extracted_root"), "recorded extracted root"
    )
    manifest_path = resolve_recorded_path(
        PROJECT_ROOT,
        unblinding.get("extracted_manifest"),
        "recorded extracted-data manifest",
    )
    planned_run = resolve_recorded_path(
        PROJECT_ROOT,
        results.get("planned_run_directory"),
        "planned first-pass run directory",
    )
    plan_questions = resolve_recorded_path(
        PROJECT_ROOT, paths.get("questions_file"), "planned questions file"
    )
    plan_data_root = resolve_recorded_path(
        PROJECT_ROOT, paths.get("data_root"), "planned analysis data root"
    )
    plan_extracted_root = resolve_recorded_path(
        PROJECT_ROOT, paths.get("extracted_root"), "planned extracted root"
    )
    plan_manifest = resolve_recorded_path(
        PROJECT_ROOT, paths.get("extracted_manifest"), "planned extracted-data manifest"
    )
    plan_run = resolve_recorded_path(
        PROJECT_ROOT, paths.get("run_directory"), "planned first-pass run directory"
    )
    if (
        recorded_questions != plan_questions
        or recorded_data_root != plan_data_root
        or extracted_root != plan_extracted_root
        or manifest_path != plan_manifest
        or planned_run != plan_run
    ):
        raise HeldoutIntegrityError(
            "Mutable protocol paths differ from the frozen plan"
        )
    if questions_path != recorded_questions:
        raise HeldoutIntegrityError("Question path differs from the unblinding record")
    if data_root != recorded_data_root:
        raise HeldoutIntegrityError(
            "Analysis data root differs from the unblinding record"
        )
    if output_dir != planned_run:
        raise HeldoutIntegrityError("Output directory differs from the frozen run plan")
    if not data_root.is_relative_to(extracted_root):
        raise HeldoutIntegrityError(
            "Analysis data root is outside the extracted-data seal"
        )
    if sha256_file(questions_path) != unblinding.get("questions_sha256"):
        raise HeldoutIntegrityError("Held-out question file checksum mismatch")
    return verify_data_manifest(
        data_root=extracted_root,
        manifest_path=manifest_path,
        project_root=PROJECT_ROOT,
        expected_manifest_sha256=unblinding.get("extracted_manifest_sha256"),
        expected_file_count=unblinding.get("extracted_file_count"),
    )


def required_seal_paths() -> tuple[str, ...]:
    return (
        "FIRST_PASS_STARTED.json",
        "sealed-summary-without-oracle.json",
        *(f"runs/task-{task_id}.json" for task_id in TASK_IDS),
    )


def verify_unscored_census(
    output_dir: Path, verification: ManifestVerification
) -> None:
    actual: set[str] = set()
    for path in output_dir.rglob("*"):
        if path.is_symlink():
            raise HeldoutIntegrityError("First-pass output contains a symbolic link")
        if path.is_dir():
            continue
        if not path.is_file():
            raise HeldoutIntegrityError(
                "First-pass output contains a non-regular entry"
            )
        actual.add(path.relative_to(output_dir).as_posix())
    expected = set(verification.relative_paths) | {"seal.sha256"}
    if actual != expected:
        raise HeldoutIntegrityError(
            "Unscored first-pass output differs from its sealed census"
        )


def validate_first_pass_bundle(
    *,
    output_dir: Path,
    protocol: dict[str, Any],
    data_manifest: ManifestVerification,
    require_exact_census: bool,
    expected_seal_sha256: str | None = None,
) -> tuple[dict[str, Any], ManifestVerification]:
    plan = load_frozen_plan(protocol, PROJECT_ROOT)
    verification = verify_seal(
        output_dir,
        expected_seal_sha256=expected_seal_sha256,
        required_paths=required_seal_paths(),
    )
    if require_exact_census:
        verify_unscored_census(output_dir, verification)
    marker = load_json_mapping(
        output_dir / "FIRST_PASS_STARTED.json", "first-pass marker"
    )
    summary_path = output_dir / "sealed-summary-without-oracle.json"
    summary = load_json_mapping(summary_path, "sealed first-pass summary")
    protocol_id = str(protocol.get("protocol_id"))
    frozen_surface = require_mapping(
        protocol.get("implementation_freeze"), "implementation freeze"
    ).get("pre_unblinding_sha256")
    questions_sha256 = require_mapping(
        protocol.get("unblinding"), "unblinding record"
    ).get("questions_sha256")
    expected_bindings = {
        "protocol_id": protocol_id,
        "plan_sha256": require_mapping(
            protocol.get("frozen_plan"), "frozen plan record"
        ).get("sha256"),
        "surface_sha256": frozen_surface,
        "questions_sha256": questions_sha256,
        "data_manifest_sha256": data_manifest.manifest_sha256,
        "data_file_count": data_manifest.file_count,
        "execution_config_sha256": canonical_json_sha256(
            require_mapping(plan.get("execution"), "frozen execution configuration")
        ),
    }
    for key, expected in expected_bindings.items():
        if marker.get(key) != expected or summary.get(key) != expected:
            raise HeldoutIntegrityError(f"First-pass {key} binding mismatch")
    execution = require_mapping(plan.get("execution"), "frozen execution configuration")
    if tuple(marker.get("task_ids", ())) != TASK_IDS or marker.get(
        "model"
    ) != execution.get("model"):
        raise HeldoutIntegrityError("First-pass marker task/model binding mismatch")
    for key in ("model", "temperature", "planner_max_attempts", "max_repair_rounds"):
        if summary.get(key) != execution.get(key):
            raise HeldoutIntegrityError(
                f"First-pass summary {key} differs from the plan"
            )
    if tuple(summary.get("task_ids", ())) != TASK_IDS:
        raise HeldoutIntegrityError(
            "Sealed summary task IDs differ from the frozen protocol"
        )
    rows = summary.get("results")
    if not isinstance(rows, list):
        raise HeldoutIntegrityError("Sealed summary results are not a list")
    observed_ids = tuple(
        int(require_mapping(row, "sealed first-pass result")["task_id"]) for row in rows
    )
    if observed_ids != TASK_IDS:
        raise HeldoutIntegrityError(
            "Sealed first-pass result census is incomplete or reordered"
        )
    return summary, verification


def finalize_first_pass_protocol(
    *,
    protocol_path: Path,
    output_dir: Path,
    protocol: dict[str, Any],
    data_manifest: ManifestVerification,
) -> dict[str, Any]:
    summary, verification = validate_first_pass_bundle(
        output_dir=output_dir,
        protocol=protocol,
        data_manifest=data_manifest,
        require_exact_census=True,
    )
    summary_path = output_dir / "sealed-summary-without-oracle.json"
    seal_path = output_dir / "seal.sha256"
    completed_at = summary.get("completed_at")
    if not isinstance(completed_at, str) or not completed_at:
        raise HeldoutIntegrityError("Sealed first-pass completion time is missing")
    return transition_protocol(
        protocol_path,
        expected_status="unblinded_not_run",
        next_status="first_pass_sealed",
        expected_protocol_id=str(protocol["protocol_id"]),
        results_update={
            "run_directory": project_relative(
                output_dir, PROJECT_ROOT, "first-pass run directory"
            ),
            "artifact": project_relative(
                summary_path, PROJECT_ROOT, "sealed first-pass summary"
            ),
            "artifact_sha256": sha256_file(summary_path),
            "seal_file": project_relative(seal_path, PROJECT_ROOT, "first-pass seal"),
            "seal_sha256": verification.manifest_sha256,
            "sealed_file_count": verification.file_count,
            "sealed_at": completed_at,
        },
    )


def execute(args: argparse.Namespace) -> None:
    data_root = args.data_root.expanduser().resolve()
    questions_path = args.questions.expanduser().resolve()
    protocol_path = args.protocol.expanduser().resolve()
    output_dir = args.output_dir.expanduser().resolve()
    if (
        not data_root.is_dir()
        or not questions_path.is_file()
        or not protocol_path.is_file()
    ):
        raise HeldoutIntegrityError(
            "Held-out data, questions, or protocol is missing; unblind it first"
        )

    protocol = load_json_mapping(protocol_path, "held-out protocol")
    if protocol.get("status") == "first_pass_sealed":
        raise HeldoutIntegrityError(
            "The frozen first pass is already sealed; rerun refused"
        )
    if protocol.get("status") != "unblinded_not_run":
        raise HeldoutIntegrityError("Protocol is not in the unblinded, not-run state")
    plan = load_frozen_plan(protocol, PROJECT_ROOT)
    require_matching_plan_section(protocol, plan, "benchmark")
    require_matching_plan_section(protocol, plan, "selection")
    selection = require_mapping(plan.get("selection"), "frozen plan selection")
    if tuple(selection.get("task_ids", ())) != TASK_IDS or selection.get(
        "task_count"
    ) != len(TASK_IDS):
        raise HeldoutIntegrityError("Frozen plan task census differs from the runner")
    frozen_surface = require_mapping(
        protocol.get("implementation_freeze"), "implementation freeze"
    ).get("pre_unblinding_sha256")
    if not frozen_surface or current_surface_hash() != frozen_surface:
        raise HeldoutIntegrityError(
            "Evaluation surface changed after unblinding; first-pass run refused"
        )
    data_manifest = verify_protocol_inputs(
        protocol,
        plan,
        data_root=data_root,
        questions_path=questions_path,
        output_dir=output_dir,
    )
    plan_sha256 = str(
        require_mapping(protocol.get("frozen_plan"), "frozen plan record")["sha256"]
    )
    tasks = load_questions(questions_path, str(protocol["protocol_id"]), plan_sha256)

    marker_path = output_dir / "FIRST_PASS_STARTED.json"
    if output_dir.exists() and any(output_dir.iterdir()):
        if (
            marker_path.is_file()
            and (output_dir / "sealed-summary-without-oracle.json").is_file()
            and (output_dir / "seal.sha256").is_file()
        ):
            finalize_first_pass_protocol(
                protocol_path=protocol_path,
                output_dir=output_dir,
                protocol=protocol,
                data_manifest=data_manifest,
            )
            print("Recovered the protocol transition for an already sealed first pass.")
            return
        raise HeldoutIntegrityError(
            "This output directory contains an incomplete or previously started first pass"
        )

    settings = Settings(
        environment_id="coda-community-45-heldout-v1",
        data_root=data_root,
        runtime_root=output_dir / "runtime",
        planner_mode="model",
        max_repair_rounds=2,
        max_concurrent_runs=1,
        planner_max_attempts=2,
    )
    if not settings.llm_configured:
        raise HeldoutIntegrityError(
            "Model configuration is absent. Set server-side ASKDU_LLM_BASE_URL, "
            "ASKDU_LLM_MODEL, and ASKDU_LLM_API_KEY without committing them."
        )
    execution_configuration = validate_execution_settings(plan, settings)
    service = build_run_service(settings)

    output_dir.mkdir(parents=True, exist_ok=True)
    started_at = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    try:
        with marker_path.open("x", encoding="utf-8") as handle:
            json.dump(
                {
                    "protocol_id": protocol["protocol_id"],
                    "plan_sha256": plan_sha256,
                    "started_at": started_at,
                    "surface_sha256": frozen_surface,
                    "questions_sha256": sha256_file(questions_path),
                    "data_manifest_sha256": data_manifest.manifest_sha256,
                    "data_file_count": data_manifest.file_count,
                    "execution_config_sha256": canonical_json_sha256(
                        execution_configuration
                    ),
                    "task_ids": list(TASK_IDS),
                    "model": settings.llm_model,
                },
                handle,
                indent=2,
                sort_keys=True,
            )
            handle.write("\n")
    except FileExistsError as exc:
        raise HeldoutIntegrityError(
            "This output directory already started a first-pass run"
        ) from exc

    results: list[dict[str, Any]] = []
    for task in tasks:
        task_id = int(task["task_id"])
        started = time.perf_counter()
        state = service.run(str(task["question"]))
        elapsed_ms = (time.perf_counter() - started) * 1000
        state_path = output_dir / "runs" / f"task-{task_id}.json"
        atomic_write_text(state_path, state.model_dump_json(indent=2) + "\n")
        results.append(
            {
                "task_id": task_id,
                "status": state.status.value,
                "diagnosis_kind": state.diagnosis.kind.value
                if state.diagnosis
                else None,
                "report_title": state.report.title if state.report else None,
                "claim_values": [claim.value for claim in state.report.claims]
                if state.report
                else [],
                "prediction": format_declarative_answer(state.artifacts)
                if state.report
                else "",
                "planner_attempts_used": state.contract.compilation.attempts
                if state.contract
                else None,
                "selected_sources": [asset.name for asset in state.assets.values()],
                "repair_edges": sum(
                    event.edge_kind == EdgeKind.REPAIR for event in state.events
                ),
                "logical_source_profiles": len(state.assets),
                "logical_profile_bytes": sum(
                    asset.byte_size for asset in state.assets.values()
                ),
                "elapsed_ms": round(elapsed_ms, 3),
                "run_id": state.run_id,
                "run_state": project_relative(
                    state_path, PROJECT_ROOT, "held-out run state"
                ),
            }
        )

    completed_at = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    summary = {
        "experiment": "coda_community45_prospective_heldout_v1_first_pass",
        "protocol_id": protocol["protocol_id"],
        "plan_sha256": plan_sha256,
        "system_version": __version__,
        "surface_sha256": frozen_surface,
        "questions_sha256": sha256_file(questions_path),
        "data_manifest_sha256": data_manifest.manifest_sha256,
        "data_file_count": data_manifest.file_count,
        "execution_config_sha256": canonical_json_sha256(execution_configuration),
        "coda_revision": require_mapping(protocol.get("benchmark"), "benchmark record")[
            "revision"
        ],
        "task_ids": list(TASK_IDS),
        "started_at": started_at,
        "completed_at": completed_at,
        "python": platform.python_version(),
        "pandas": pd.__version__,
        "model": settings.llm_model,
        "temperature": 0.0,
        "planner_max_attempts": settings.planner_max_attempts,
        "max_repair_rounds": settings.max_repair_rounds,
        "planner_prompt_sha256": hashlib.sha256(
            PLANNER_SYSTEM_PROMPT.encode("utf-8")
        ).hexdigest(),
        "planner_schema_sha256": hashlib.sha256(
            json.dumps(
                DeclarativeAnalysisPlan.model_json_schema(),
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest(),
        "aggregate_without_oracle": {
            "tasks": len(results),
            "reports_completed": sum(row["status"] == "completed" for row in results),
            "explicit_abstentions": sum(
                row["status"] == "insufficient" for row in results
            ),
            "failed_runs": sum(row["status"] == "failed" for row in results),
            "repair_edges": sum(row["repair_edges"] for row in results),
            "logical_source_profiles": sum(
                row["logical_source_profiles"] for row in results
            ),
            "logical_profile_bytes": sum(
                row["logical_profile_bytes"] for row in results
            ),
        },
        "oracle_status": "not_opened_or_scored_by_this_runner",
        "results": results,
    }
    summary_path = output_dir / "sealed-summary-without-oracle.json"
    atomic_write_json(summary_path, summary)
    seal_path = output_dir / "seal.sha256"
    build_seal(output_dir, seal_path)
    finalize_first_pass_protocol(
        protocol_path=protocol_path,
        output_dir=output_dir,
        protocol=protocol,
        data_manifest=data_manifest,
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False, sort_keys=True))
    print(f"First-pass artifacts sealed by {seal_path}")


def main() -> None:
    try:
        execute(parse_args())
    except HeldoutIntegrityError as exc:
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    main()
