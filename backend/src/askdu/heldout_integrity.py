from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
MANIFEST_LINE_PATTERN = re.compile(r"(?P<digest>[0-9a-f]{64})  (?P<path>.+)")


class HeldoutIntegrityError(ValueError):
    """Raised when a held-out artifact violates the frozen evidence protocol."""


@dataclass(frozen=True)
class ManifestVerification:
    manifest_sha256: str
    file_count: int
    relative_paths: tuple[str, ...]


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


def atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    atomic_write_text(
        path,
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
    )


def load_json_mapping(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HeldoutIntegrityError(f"Could not read {label}: {path}") from exc
    if not isinstance(payload, dict):
        raise HeldoutIntegrityError(f"{label} must be a JSON object")
    return payload


def require_mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise HeldoutIntegrityError(f"{label} must be a JSON object")
    return value


def validate_sha256(value: Any, label: str) -> str:
    digest = str(value)
    if SHA256_PATTERN.fullmatch(digest) is None:
        raise HeldoutIntegrityError(f"{label} must be a lowercase SHA-256 digest")
    return digest


def canonical_json_sha256(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def resolve_recorded_path(project_root: Path, recorded: Any, label: str) -> Path:
    root = project_root.resolve()
    relative = str(recorded)
    pure = PurePosixPath(relative)
    if (
        not relative
        or "\\" in relative
        or pure.is_absolute()
        or ".." in pure.parts
        or pure.as_posix() != relative
    ):
        raise HeldoutIntegrityError(f"{label} is not a canonical project-relative path")
    resolved = (root / Path(*pure.parts)).resolve()
    if not resolved.is_relative_to(root):
        raise HeldoutIntegrityError(f"{label} escapes the project root")
    return resolved


def project_relative(path: Path, project_root: Path, label: str) -> str:
    root = project_root.resolve()
    resolved = path.resolve()
    if not resolved.is_relative_to(root):
        raise HeldoutIntegrityError(f"{label} is outside the project root")
    return resolved.relative_to(root).as_posix()


def _require_exact_keys(value: Mapping[str, Any], expected: set[str], label: str) -> None:
    if set(value) != expected:
        raise HeldoutIntegrityError(f"{label} fields differ from the frozen schema")


def _positive_integer(value: Any, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise HeldoutIntegrityError(f"{label} must be a positive integer")
    return value


def validate_frozen_plan_shape(plan: Mapping[str, Any], project_root: Path) -> None:
    _require_exact_keys(
        plan,
        {"schema_version", "protocol_id", "benchmark", "selection", "paths", "execution"},
        "Frozen plan",
    )
    if plan.get("schema_version") != "askdu-heldout-plan-v1":
        raise HeldoutIntegrityError("Frozen held-out plan schema is unsupported")
    if not isinstance(plan.get("protocol_id"), str) or not plan["protocol_id"]:
        raise HeldoutIntegrityError("Frozen plan protocol ID is missing")

    benchmark = require_mapping(plan.get("benchmark"), "frozen plan benchmark")
    _require_exact_keys(
        benchmark,
        {
            "name",
            "repository",
            "revision",
            "metadata_file",
            "metadata_sha256",
            "archive_file",
            "archive_bytes",
            "archive_sha256",
        },
        "Frozen plan benchmark",
    )
    if not all(
        isinstance(benchmark.get(key), str) and bool(benchmark[key])
        for key in ("name", "repository")
    ):
        raise HeldoutIntegrityError("Frozen plan benchmark identity is invalid")
    if re.fullmatch(r"[0-9a-f]{40}", str(benchmark.get("revision"))) is None:
        raise HeldoutIntegrityError("Frozen plan benchmark revision is invalid")
    validate_sha256(benchmark.get("metadata_sha256"), "Frozen metadata checksum")
    validate_sha256(benchmark.get("archive_sha256"), "Frozen archive checksum")
    _positive_integer(benchmark.get("archive_bytes"), "Frozen archive size")
    resolve_recorded_path(project_root, benchmark.get("metadata_file"), "Frozen metadata path")
    resolve_recorded_path(project_root, benchmark.get("archive_file"), "Frozen archive path")

    selection = require_mapping(plan.get("selection"), "frozen plan selection")
    _require_exact_keys(
        selection,
        {"community_id", "task_ids", "task_count", "selection_rule"},
        "Frozen plan selection",
    )
    _positive_integer(selection.get("community_id"), "Frozen community ID")
    task_ids = selection.get("task_ids")
    if (
        not isinstance(task_ids, list)
        or not task_ids
        or any(
            not isinstance(task_id, int) or isinstance(task_id, bool) or task_id < 1
            for task_id in task_ids
        )
        or len(set(task_ids)) != len(task_ids)
        or selection.get("task_count") != len(task_ids)
        or not isinstance(selection.get("selection_rule"), str)
        or not selection["selection_rule"]
    ):
        raise HeldoutIntegrityError("Frozen plan task selection is invalid")

    paths = require_mapping(plan.get("paths"), "frozen plan paths")
    path_keys = {
        "questions_file",
        "extracted_root",
        "data_root",
        "extracted_manifest",
        "run_directory",
        "first_pass_marker",
        "first_pass_summary",
        "first_pass_seal",
        "oracle_marker",
        "score_artifact",
    }
    _require_exact_keys(paths, path_keys, "Frozen plan paths")
    resolved_paths = {
        key: resolve_recorded_path(project_root, paths.get(key), f"Frozen plan {key}")
        for key in path_keys
    }
    if not resolved_paths["data_root"].is_relative_to(resolved_paths["extracted_root"]):
        raise HeldoutIntegrityError("Frozen analysis root is outside the extracted root")
    run_directory = resolved_paths["run_directory"]
    expected_names = {
        "first_pass_marker": "FIRST_PASS_STARTED.json",
        "first_pass_summary": "sealed-summary-without-oracle.json",
        "first_pass_seal": "seal.sha256",
        "oracle_marker": "ORACLE_SCORING_STARTED.json",
        "score_artifact": "scored-after-oracle-unsealing.json",
    }
    if any(
        resolved_paths[key].parent != run_directory or resolved_paths[key].name != expected_name
        for key, expected_name in expected_names.items()
    ):
        raise HeldoutIntegrityError("Frozen run artifact paths are inconsistent")

    execution = require_mapping(plan.get("execution"), "frozen plan execution")
    execution_keys = {
        "model",
        "endpoint_sha256",
        "api_style",
        "auth_scheme",
        "token_field",
        "trust_environment_proxy",
        "timeout_seconds",
        "transport_retries",
        "temperature",
        "planner_max_attempts",
        "max_repair_rounds",
        "max_concurrent_runs",
    }
    _require_exact_keys(execution, execution_keys, "Frozen plan execution")
    if not isinstance(execution.get("model"), str) or not execution["model"]:
        raise HeldoutIntegrityError("Frozen model name is missing")
    validate_sha256(execution.get("endpoint_sha256"), "Frozen endpoint checksum")
    if execution.get("api_style") not in {
        "azure_chat",
        "openai_base_url",
        "direct_chat_completions",
    }:
        raise HeldoutIntegrityError("Frozen provider API style is invalid")
    if execution.get("auth_scheme") not in {"bearer", "api_key"}:
        raise HeldoutIntegrityError("Frozen provider authentication scheme is invalid")
    if execution.get("token_field") not in {"max_tokens", "max_completion_tokens"}:
        raise HeldoutIntegrityError("Frozen provider token field is invalid")
    if not isinstance(execution.get("trust_environment_proxy"), bool):
        raise HeldoutIntegrityError("Frozen proxy policy is not Boolean")
    timeout = execution.get("timeout_seconds")
    temperature = execution.get("temperature")
    if (
        not isinstance(timeout, (int, float))
        or isinstance(timeout, bool)
        or timeout <= 0
        or not isinstance(temperature, (int, float))
        or isinstance(temperature, bool)
        or temperature != 0
    ):
        raise HeldoutIntegrityError("Frozen decoding or timeout value is invalid")
    for key, minimum in (
        ("transport_retries", 0),
        ("planner_max_attempts", 1),
        ("max_repair_rounds", 0),
        ("max_concurrent_runs", 1),
    ):
        value = execution.get(key)
        if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
            raise HeldoutIntegrityError(f"Frozen {key} is invalid")


def load_frozen_plan(protocol: Mapping[str, Any], project_root: Path) -> dict[str, Any]:
    record = require_mapping(protocol.get("frozen_plan"), "frozen plan record")
    plan_path = resolve_recorded_path(project_root, record.get("file"), "frozen held-out plan")
    if plan_path.is_symlink() or not plan_path.is_file():
        raise HeldoutIntegrityError("Frozen held-out plan is missing or is a symlink")
    expected_sha256 = validate_sha256(record.get("sha256"), "Frozen plan checksum")
    if sha256_file(plan_path) != expected_sha256:
        raise HeldoutIntegrityError("Frozen held-out plan checksum mismatch")
    plan = load_json_mapping(plan_path, "frozen held-out plan")
    validate_frozen_plan_shape(plan, project_root)
    if plan.get("protocol_id") != protocol.get("protocol_id"):
        raise HeldoutIntegrityError("Frozen plan and protocol IDs differ")
    return plan


def require_matching_plan_section(
    protocol: Mapping[str, Any], plan: Mapping[str, Any], section: str
) -> None:
    protocol_section = require_mapping(protocol.get(section), f"protocol {section}")
    plan_section = require_mapping(plan.get(section), f"frozen plan {section}")
    for key, expected in plan_section.items():
        if protocol_section.get(key) != expected:
            raise HeldoutIntegrityError(f"Protocol {section}.{key} differs from the frozen plan")


def validate_execution_settings(plan: Mapping[str, Any], settings: Any) -> dict[str, Any]:
    expected = require_mapping(plan.get("execution"), "frozen execution configuration")
    endpoint = settings.llm_base_url or ""
    actual = {
        "model": settings.llm_model,
        "endpoint_sha256": hashlib.sha256(endpoint.encode("utf-8")).hexdigest(),
        "api_style": settings.llm_api_style,
        "auth_scheme": settings.llm_auth_scheme,
        "token_field": settings.llm_token_field,
        "trust_environment_proxy": settings.llm_trust_env_proxy,
        "timeout_seconds": settings.llm_timeout_seconds,
        "transport_retries": settings.llm_max_retries,
        "temperature": 0.0,
        "planner_max_attempts": settings.planner_max_attempts,
        "max_repair_rounds": settings.max_repair_rounds,
        "max_concurrent_runs": settings.max_concurrent_runs,
    }
    if actual != expected:
        mismatches = sorted(
            key for key in set(expected) | set(actual) if expected.get(key) != actual.get(key)
        )
        raise HeldoutIntegrityError(
            "Server-side model configuration differs from the frozen plan: " + ", ".join(mismatches)
        )
    return actual


def parse_checksum_manifest(payload: str, label: str) -> list[tuple[str, str]]:
    if not payload or not payload.endswith("\n"):
        raise HeldoutIntegrityError(f"{label} must be non-empty and newline-terminated")
    entries: list[tuple[str, str]] = []
    seen: set[str] = set()
    for line_number, line in enumerate(payload.splitlines(), start=1):
        match = MANIFEST_LINE_PATTERN.fullmatch(line)
        if match is None:
            raise HeldoutIntegrityError(
                f"{label} line {line_number} is not '<sha256><two spaces><path>'"
            )
        relative = match.group("path")
        pure = PurePosixPath(relative)
        if (
            "\\" in relative
            or pure.is_absolute()
            or ".." in pure.parts
            or pure.as_posix() != relative
        ):
            raise HeldoutIntegrityError(
                f"{label} line {line_number} has a non-canonical relative path"
            )
        if relative in seen:
            raise HeldoutIntegrityError(f"{label} repeats path: {relative}")
        seen.add(relative)
        entries.append((match.group("digest"), relative))
    return entries


def _regular_files_beneath(root: Path, project_root: Path, label: str) -> dict[str, Path]:
    project = project_root.resolve()
    if root.is_symlink() or not root.is_dir():
        raise HeldoutIntegrityError(f"{label} is missing or is a symbolic link")
    resolved_root = root.resolve()
    if not resolved_root.is_relative_to(project):
        raise HeldoutIntegrityError(f"{label} is outside the project root")
    files: dict[str, Path] = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise HeldoutIntegrityError(f"{label} contains a symbolic link")
        if path.is_dir():
            continue
        if not path.is_file():
            raise HeldoutIntegrityError(f"{label} contains a non-regular entry")
        resolved = path.resolve()
        if not resolved.is_relative_to(resolved_root):
            raise HeldoutIntegrityError(f"{label} contains an escaping path")
        relative = resolved.relative_to(project).as_posix()
        files[relative] = path
    if not files:
        raise HeldoutIntegrityError(f"{label} contains no regular files")
    return files


def verify_data_manifest(
    *,
    data_root: Path,
    manifest_path: Path,
    project_root: Path,
    expected_manifest_sha256: Any,
    expected_file_count: Any,
) -> ManifestVerification:
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise HeldoutIntegrityError("Extracted-data manifest is missing or is a symlink")
    project = project_root.resolve()
    resolved_manifest = manifest_path.resolve()
    if not resolved_manifest.is_relative_to(project):
        raise HeldoutIntegrityError("Extracted-data manifest is outside the project root")
    expected_digest = validate_sha256(
        expected_manifest_sha256, "Recorded extracted-data manifest checksum"
    )
    manifest_digest = sha256_file(manifest_path)
    if manifest_digest != expected_digest:
        raise HeldoutIntegrityError("Extracted-data manifest checksum mismatch")
    if (
        not isinstance(expected_file_count, int)
        or isinstance(expected_file_count, bool)
        or expected_file_count < 1
    ):
        raise HeldoutIntegrityError("Recorded extracted-data file count is invalid")

    entries = parse_checksum_manifest(
        manifest_path.read_text(encoding="utf-8"), "Extracted-data manifest"
    )
    if len(entries) != expected_file_count:
        raise HeldoutIntegrityError("Extracted-data manifest file count mismatch")
    actual = _regular_files_beneath(data_root, project, "Extracted held-out data")
    recorded = {relative: digest for digest, relative in entries}
    if set(recorded) != set(actual):
        missing = len(set(recorded) - set(actual))
        extra = len(set(actual) - set(recorded))
        raise HeldoutIntegrityError(
            f"Extracted-data manifest census mismatch ({missing} missing, {extra} unrecorded)"
        )
    for relative, expected in recorded.items():
        if sha256_file(actual[relative]) != expected:
            raise HeldoutIntegrityError(f"Extracted held-out file checksum mismatch: {relative}")
    return ManifestVerification(
        manifest_sha256=manifest_digest,
        file_count=len(entries),
        relative_paths=tuple(relative for _, relative in entries),
    )


def build_seal(run_dir: Path, seal_path: Path) -> ManifestVerification:
    if run_dir.is_symlink() or not run_dir.is_dir():
        raise HeldoutIntegrityError("First-pass run directory is missing or is a symlink")
    resolved_run = run_dir.resolve()
    resolved_seal = seal_path.resolve()
    if resolved_seal.parent != resolved_run or seal_path.name != "seal.sha256":
        raise HeldoutIntegrityError("First-pass seal must be run_dir/seal.sha256")
    entries: list[tuple[str, str]] = []
    for path in sorted(run_dir.rglob("*")):
        if path.is_symlink():
            raise HeldoutIntegrityError("First-pass run directory contains a symbolic link")
        if path.is_dir():
            continue
        if not path.is_file():
            raise HeldoutIntegrityError("First-pass run directory has a non-regular entry")
        if path.resolve() == resolved_seal:
            continue
        relative = path.resolve().relative_to(resolved_run).as_posix()
        entries.append((sha256_file(path), relative))
    if not entries:
        raise HeldoutIntegrityError("No first-pass artifacts exist to seal")
    atomic_write_text(
        seal_path,
        "".join(f"{digest}  {relative}\n" for digest, relative in entries),
    )
    return verify_seal(run_dir, seal_path=seal_path)


def verify_seal(
    run_dir: Path,
    *,
    seal_path: Path | None = None,
    expected_seal_sha256: Any | None = None,
    required_paths: Sequence[str] = (),
) -> ManifestVerification:
    if run_dir.is_symlink() or not run_dir.is_dir():
        raise HeldoutIntegrityError("First-pass run directory is missing or is a symlink")
    root = run_dir.resolve()
    unresolved_seal = seal_path or run_dir / "seal.sha256"
    if unresolved_seal.is_symlink():
        raise HeldoutIntegrityError("The first-pass seal may not be a symbolic link")
    seal = unresolved_seal.resolve()
    if seal.parent != root or seal.name != "seal.sha256" or not seal.is_file():
        raise HeldoutIntegrityError("The first-pass seal is missing or outside its run directory")
    seal_digest = sha256_file(seal)
    if expected_seal_sha256 is not None:
        expected_digest = validate_sha256(expected_seal_sha256, "Recorded seal checksum")
        if seal_digest != expected_digest:
            raise HeldoutIntegrityError("First-pass seal checksum mismatch")
    entries = parse_checksum_manifest(seal.read_text(encoding="utf-8"), "First-pass seal")
    observed: set[str] = set()
    for expected, relative in entries:
        unresolved_path = root / Path(*PurePosixPath(relative).parts)
        if unresolved_path.is_symlink():
            raise HeldoutIntegrityError(f"Sealed artifact is a symlink: {relative}")
        path = unresolved_path.resolve()
        if not path.is_relative_to(root) or path == seal:
            raise HeldoutIntegrityError(f"Sealed artifact path is unsafe: {relative}")
        if not path.is_file():
            raise HeldoutIntegrityError(f"Sealed artifact is missing: {relative}")
        if sha256_file(path) != expected:
            raise HeldoutIntegrityError(f"Sealed artifact changed: {relative}")
        observed.add(relative)
    missing_required = sorted(set(required_paths) - observed)
    if missing_required:
        raise HeldoutIntegrityError(
            f"First-pass seal omits {len(missing_required)} required artifact(s)"
        )
    return ManifestVerification(
        manifest_sha256=seal_digest,
        file_count=len(entries),
        relative_paths=tuple(relative for _, relative in entries),
    )


def transition_protocol(
    protocol_path: Path,
    *,
    expected_status: str,
    next_status: str,
    results_update: Mapping[str, Any],
    expected_protocol_id: str,
) -> dict[str, Any]:
    protocol = load_json_mapping(protocol_path, "held-out protocol")
    if protocol.get("protocol_id") != expected_protocol_id:
        raise HeldoutIntegrityError("Held-out protocol ID changed during evaluation")
    if protocol.get("status") != expected_status:
        raise HeldoutIntegrityError(
            f"Held-out protocol transition requires {expected_status!r}, "
            f"found {protocol.get('status')!r}"
        )
    results = dict(require_mapping(protocol.get("results"), "held-out protocol results"))
    results.update(results_update)
    results["status"] = next_status
    protocol["status"] = next_status
    protocol["results"] = results
    atomic_write_json(protocol_path, protocol)
    return protocol
