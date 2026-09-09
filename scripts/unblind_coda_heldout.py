#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

from askdu.config import Settings
from askdu.heldout_integrity import (
    HeldoutIntegrityError,
    load_frozen_plan,
    require_mapping,
    require_matching_plan_section,
    resolve_recorded_path,
    validate_execution_settings,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROTOCOL_PATH = PROJECT_ROOT / "data/pilots/heldout-v1.json"
ARCHIVE_PATH = PROJECT_ROOT / "data/external/coda-bench/archives/community_45.tar.zst"
METADATA_PATH = PROJECT_ROOT / "data/external/coda-bench/coda_bench.json"
TARGET_PATH = PROJECT_ROOT / "data/external/coda-bench/communities/community_45"
DATA_ROOT_PATH = TARGET_PATH / "full_community"
QUESTIONS_PATH = PROJECT_ROOT / "data/pilots/heldout-v1-questions.json"
EXTRACTED_MANIFEST_PATH = (
    PROJECT_ROOT / "data/manifests/coda-community-45-extracted.sha256"
)
TASK_IDS = (31, 32, 260, 261, 262, 263, 264, 265, 266, 267, 268, 269, 270)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_write_text(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        temporary_path.replace(path)
    finally:
        temporary_path.unlink(missing_ok=True)


def current_surface_hash() -> str:
    result = subprocess.run(
        [str(PROJECT_ROOT / "scripts/hash_evaluation_surface.sh")],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def tar_with_zstd(archive: Path, arguments: list[str], *, capture: bool) -> str:
    decompressor = subprocess.Popen(
        ["zstd", "-dc", "--", str(archive)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert decompressor.stdout is not None
    tar = subprocess.run(
        ["tar", *arguments, "-f", "-"],
        stdin=decompressor.stdout,
        check=False,
        capture_output=capture,
        text=capture,
    )
    decompressor.stdout.close()
    _, decompressor_error = decompressor.communicate()
    if decompressor.returncode != 0:
        raise RuntimeError(decompressor_error.decode("utf-8", errors="replace"))
    if tar.returncode != 0:
        stderr = tar.stderr if capture else "tar extraction failed"
        raise RuntimeError(str(stderr))
    return tar.stdout if capture else ""


def selected_questions(metadata: Path) -> list[dict[str, Any]]:
    rows = json.loads(metadata.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise TypeError("Pinned benchmark metadata is not a JSON list")
    by_id: dict[int, dict[str, Any]] = {}
    for raw_row in rows:
        if not isinstance(raw_row, dict):
            raise TypeError("Pinned benchmark metadata contains a non-object row")
        task_id = int(raw_row["instance_id"])
        if task_id in by_id:
            raise RuntimeError(f"Pinned metadata repeats task ID: {task_id}")
        by_id[task_id] = raw_row
    missing = sorted(set(TASK_IDS) - set(by_id))
    if missing:
        raise RuntimeError(f"Pinned metadata is missing held-out task IDs: {missing}")
    questions = []
    for task_id in TASK_IDS:
        question = by_id[task_id].get("question")
        if not isinstance(question, str) or not question.strip():
            raise RuntimeError(
                f"Pinned metadata has no question for task ID: {task_id}"
            )
        questions.append({"task_id": task_id, "question": question})
    return questions


def validate_members(listing: str) -> None:
    members = listing.splitlines()
    unsafe = [
        member
        for member in members
        if PurePosixPath(member).is_absolute() or ".." in PurePosixPath(member).parts
    ]
    if unsafe:
        raise RuntimeError(f"Archive contains unsafe paths: {unsafe[:5]}")


def extracted_manifest(root: Path) -> str:
    lines = []
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
            raise RuntimeError(f"Extracted path escapes the held-out root: {path}")
        relative = path.relative_to(PROJECT_ROOT).as_posix()
        lines.append(f"{sha256_file(path)}  {relative}")
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Irreversibly unblind the frozen CoDA held-out community."
    )
    parser.add_argument(
        "--confirm-pre-unblinding-sha256",
        required=True,
        help="Must equal the frozen implementation-surface digest.",
    )
    parser.add_argument(
        "--preflight-only",
        action="store_true",
        help="Validate the frozen surface, opaque inputs, and model configuration without unblinding.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    started_at = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    for executable in ("zstd", "tar"):
        if shutil.which(executable) is None:
            raise SystemExit(f"Required executable is unavailable: {executable}")
    protocol = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
    try:
        plan = load_frozen_plan(protocol, PROJECT_ROOT)
        require_matching_plan_section(protocol, plan, "benchmark")
        require_matching_plan_section(protocol, plan, "selection")
        paths = require_mapping(plan.get("paths"), "frozen plan paths")
        expected_paths = {
            "questions_file": QUESTIONS_PATH,
            "extracted_root": TARGET_PATH,
            "data_root": DATA_ROOT_PATH,
            "extracted_manifest": EXTRACTED_MANIFEST_PATH,
        }
        for key, expected in expected_paths.items():
            if (
                resolve_recorded_path(PROJECT_ROOT, paths.get(key), f"planned {key}")
                != expected
            ):
                raise HeldoutIntegrityError(f"Frozen plan {key} differs from the guard")
    except HeldoutIntegrityError as exc:
        raise SystemExit(str(exc)) from exc
    expected_surface = protocol["implementation_freeze"]["pre_unblinding_sha256"]
    if protocol["status"] != "implementation_frozen_blinded" or not expected_surface:
        raise SystemExit(
            "The protocol has no completed pre-unblinding implementation freeze"
        )
    current_surface = current_surface_hash()
    if args.confirm_pre_unblinding_sha256 != expected_surface:
        raise SystemExit("Confirmation digest does not match the frozen protocol")
    if current_surface != expected_surface:
        raise SystemExit("Evaluation surface changed after freeze; refusing to unblind")
    benchmark = protocol.get("benchmark", {})
    selection = protocol.get("selection", {})
    if not isinstance(benchmark, dict) or sha256_file(METADATA_PATH) != benchmark.get(
        "metadata_sha256"
    ):
        raise SystemExit(
            "Benchmark metadata checksum does not match the frozen protocol"
        )
    if (
        not isinstance(selection, dict)
        or tuple(selection.get("task_ids", ())) != TASK_IDS
        or selection.get("task_count") != len(TASK_IDS)
    ):
        raise SystemExit("Held-out task census differs from the frozen protocol")
    if sha256_file(ARCHIVE_PATH) != protocol["benchmark"]["archive_sha256"]:
        raise SystemExit("Held-out archive checksum does not match the frozen protocol")
    if (
        TARGET_PATH.exists()
        or QUESTIONS_PATH.exists()
        or EXTRACTED_MANIFEST_PATH.exists()
    ):
        raise SystemExit("Held-out content already exists; refusing to overwrite it")
    if (
        protocol.get("results", {}).get("planned_run_directory")
        != paths.get("run_directory")
        or protocol.get("results", {}).get("planned_oracle_marker")
        != paths.get("oracle_marker")
        or protocol.get("results", {}).get("planned_score_artifact")
        != paths.get("score_artifact")
    ):
        raise SystemExit("Mutable result paths differ from the frozen plan")

    settings = Settings(
        environment_id="coda-community-45-heldout-v1",
        data_root=DATA_ROOT_PATH,
        runtime_root=PROJECT_ROOT
        / "experiments/results/coda-community45-heldout-v1/runtime",
        planner_mode="model",
        max_repair_rounds=2,
        max_concurrent_runs=1,
        planner_max_attempts=2,
    )
    if not settings.llm_configured:
        raise SystemExit(
            "Model configuration is absent. Supply a fresh server-side credential before "
            "crossing the held-out gate."
        )
    try:
        validate_execution_settings(plan, settings)
    except HeldoutIntegrityError as exc:
        raise SystemExit(str(exc)) from exc
    if args.preflight_only:
        print(
            "PASS: frozen held-out surface, opaque inputs, paths, and model configuration "
            "are internally consistent; no archive member was listed or extracted."
        )
        return

    questions = selected_questions(METADATA_PATH)
    with tempfile.TemporaryDirectory(
        prefix=".community45-unblind-",
        dir=ARCHIVE_PATH.parents[1],
    ) as temporary:
        extraction_root = Path(temporary)
        listing = tar_with_zstd(ARCHIVE_PATH, ["-t"], capture=True)
        validate_members(listing)
        tar_with_zstd(ARCHIVE_PATH, ["-x", "-C", str(extraction_root)], capture=False)
        extracted = extraction_root / "data/community_45"
        if not (extracted / "full_community").is_dir():
            raise RuntimeError("Unexpected CoDA held-out archive layout")
        for path in extracted.rglob("*"):
            if path.is_symlink():
                raise RuntimeError(
                    f"Symbolic links are forbidden in held-out data: {path}"
                )
            if not path.is_dir() and not path.is_file():
                raise RuntimeError(
                    f"Non-regular entries are forbidden in held-out data: {path}"
                )
        TARGET_PATH.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(extracted), TARGET_PATH)

    question_payload = (
        json.dumps(
            {
                "protocol_id": protocol["protocol_id"],
                "plan_sha256": protocol["frozen_plan"]["sha256"],
                "task_ids": list(TASK_IDS),
                "tasks": questions,
            },
            indent=2,
            ensure_ascii=False,
            sort_keys=True,
        )
        + "\n"
    )
    manifest_payload = extracted_manifest(TARGET_PATH)
    atomic_write_text(QUESTIONS_PATH, question_payload)
    atomic_write_text(EXTRACTED_MANIFEST_PATH, manifest_payload)
    completed_at = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    protocol["status"] = "unblinded_not_run"
    protocol["unblinding"] = {
        "status": "complete",
        "started_at": started_at,
        "completed_at": completed_at,
        "redaction_boundary": (
            "This guard mechanically reads pinned benchmark metadata and emits only task IDs "
            "and question text; answers are not written to the runner input."
        ),
        "plan_sha256": protocol["frozen_plan"]["sha256"],
        "questions_file": QUESTIONS_PATH.relative_to(PROJECT_ROOT).as_posix(),
        "questions_sha256": sha256_file(QUESTIONS_PATH),
        "extracted_root": TARGET_PATH.relative_to(PROJECT_ROOT).as_posix(),
        "data_root": DATA_ROOT_PATH.relative_to(PROJECT_ROOT).as_posix(),
        "extracted_manifest": EXTRACTED_MANIFEST_PATH.relative_to(
            PROJECT_ROOT
        ).as_posix(),
        "extracted_manifest_sha256": sha256_file(EXTRACTED_MANIFEST_PATH),
        "extracted_file_count": len(manifest_payload.splitlines()),
    }
    atomic_write_text(
        PROTOCOL_PATH,
        json.dumps(protocol, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
    )
    print(
        f"Unblinded {len(questions)} questions and extracted the held-out environment."
    )


if __name__ == "__main__":
    main()
