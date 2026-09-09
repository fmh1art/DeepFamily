from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import subprocess
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit

from askdu.heldout_integrity import (
    HeldoutIntegrityError,
    canonical_json_sha256,
    load_frozen_plan,
    require_matching_plan_section,
    resolve_recorded_path,
    verify_data_manifest,
)
from askdu.heldout_integrity import verify_seal as verify_first_pass_seal

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CFP_SNAPSHOT = PROJECT_ROOT / "docs/vldb2027-status.json"
LICENSE_INVENTORY = (
    PROJECT_ROOT / "experiments/evidence/dependency-license-inventory-v0.4.0.json"
)
PROTOCOL = PROJECT_ROOT / "data/pilots/heldout-v1.json"
HELDOUT_QUESTIONS = PROJECT_ROOT / "data/pilots/heldout-v1-questions.json"
HELDOUT_DATA = PROJECT_ROOT / "data/external/coda-bench/communities/community_45"
HELDOUT_MANIFEST = PROJECT_ROOT / "data/manifests/coda-community-45-extracted.sha256"
HELDOUT_RUN = PROJECT_ROOT / "experiments/results/coda-community45-heldout-v1"
TRIAL_DIRECTORY = PROJECT_ROOT / "docs/user-trials"
NARRATED_VIDEO = PROJECT_ROOT / "artifacts/demo/submission-walkthrough.mp4"
VIDEO_REVIEW = PROJECT_ROOT / "artifacts/demo/submission-walkthrough.review.json"
PAPER_SOURCE = PROJECT_ROOT / "paper/main.tex"
MEDIA_CHECKER = PROJECT_ROOT / "scripts/check_demo_video.py"
DEMO_SURFACE_HASHER = PROJECT_ROOT / "scripts/hash_demo_surface.sh"
TRIAL_PROTOCOL_HASHER = PROJECT_ROOT / "scripts/hash_user_trial_protocol.sh"
TRIAL_PROTOCOL_ID = "askdu-non-author-rehearsal-v1"
TASK_IDS = (31, 32, 260, 261, 262, 263, 264, 265, 266, 267, 268, 269, 270)
TRIAL_TASK_IDS = (
    "identify_question_only_input",
    "launch_verified_question",
    "explain_insufficient_initial_source",
    "locate_backward_repair_edge",
    "trace_report_claim_to_evidence",
    "explain_honest_data_gap",
)
TRIAL_TIMING_KEYS = (
    "time_to_first_run",
    "time_to_locate_repair_edge",
    "time_to_locate_claim_evidence",
)
EMAIL_PATTERN = re.compile(r"\b[^\s@]+@[^\s@]+\.[^\s@]+\b")
AVAILABILITY_PATTERN = re.compile(
    r"\\renewcommand\s*\\vldbavailabilityurl\s*\{(?P<url>[^}]*)\}"
)
GateStatus = Literal["pass", "pending", "fail"]
PLACEHOLDER_SUFFIXES = (".example", ".example.com", ".example.net", ".example.org")


@dataclass(frozen=True)
class GateResult:
    name: str
    status: GateStatus
    detail: str


def result(name: str, status: GateStatus, detail: str) -> GateResult:
    return GateResult(name=name, status=status, detail=detail)


def as_mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise TypeError(f"{label} must be an object")
    return value


def load_mapping(path: Path) -> Mapping[str, Any]:
    return as_mapping(json.loads(path.read_text(encoding="utf-8")), path.as_posix())


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def cfp_gate() -> GateResult:
    name = "official_demo_cfp"
    snapshot = load_mapping(CFP_SNAPSHOT)
    checked_at = date.fromisoformat(str(snapshot.get("checked_at", "")))
    today = datetime.now(timezone.utc).date()
    if checked_at > today:
        return result(name, "fail", "CFP snapshot date is in the future")
    expected = as_mapping(snapshot.get("expected"), "CFP expected state")
    cfp_present = expected.get("demo_cfp_link_present")
    dates_present = expected.get("demo_dates_row_present")
    if not isinstance(cfp_present, bool) or not isinstance(dates_present, bool):
        return result(name, "fail", "CFP snapshot flags are not Boolean")
    if cfp_present != dates_present:
        return result(name, "fail", "CFP link and Important Dates snapshot disagree")
    age_days = (today - checked_at).days
    if not cfp_present:
        return result(
            name,
            "pending",
            f"VLDB 2027 Demo CFP/dates were absent when checked {checked_at.isoformat()}",
        )
    official_urls = as_mapping(snapshot.get("official_urls"), "CFP official URLs")
    demo_url = str(official_urls.get("demo_cfp", ""))
    parsed = urlsplit(demo_url)
    if parsed.scheme != "https" or not parsed.hostname:
        return result(
            name, "fail", "published CFP snapshot lacks its official HTTPS URL"
        )
    if age_days > 31:
        return result(name, "pending", f"CFP snapshot is stale ({age_days} days old)")
    return result(
        name, "pass", f"official Demo CFP and dates checked {checked_at.isoformat()}"
    )


def license_gate() -> GateResult:
    name = "release_licensing"
    license_paths = [
        path
        for path in (
            PROJECT_ROOT / "LICENSE",
            PROJECT_ROOT / "LICENSE.txt",
            PROJECT_ROOT / "LICENSE.md",
        )
        if path.is_file()
    ]
    if not license_paths:
        return result(name, "pending", "authors have not selected a root code license")
    if any(path.stat().st_size == 0 for path in license_paths):
        return result(name, "fail", "root code license file is empty")
    inventory = load_mapping(LICENSE_INVENTORY)
    gates = as_mapping(inventory.get("release_gates"), "dependency release gates")
    required = (
        "root_project_license_present",
        "application_license_metadata_complete",
        "debian_copyright_files_present",
        "alpine_license_metadata_complete",
        "container_os_legal_review_complete",
    )
    missing = [key for key in required if gates.get(key) is not True]
    if missing:
        return result(
            name,
            "pending",
            "license inventory/manual review still open: " + ", ".join(missing),
        )
    return result(
        name, "pass", f"root license and {len(required)} release gates are recorded"
    )


def current_surface_hash() -> str:
    process = subprocess.run(
        [str(PROJECT_ROOT / "scripts/hash_evaluation_surface.sh")],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return process.stdout.strip()


def current_demo_surface_hash() -> str:
    process = subprocess.run(
        [str(DEMO_SURFACE_HASHER)],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    digest = process.stdout.strip()
    if re.fullmatch(r"[0-9a-f]{64}", digest) is None:
        raise ValueError("demo surface hasher returned an invalid SHA-256 digest")
    return digest


def current_trial_protocol_hash() -> str:
    process = subprocess.run(
        [str(TRIAL_PROTOCOL_HASHER)],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    digest = process.stdout.strip()
    if re.fullmatch(r"[0-9a-f]{64}", digest) is None:
        raise ValueError("trial protocol hasher returned an invalid SHA-256 digest")
    return digest


def verify_seal(run_directory: Path) -> None:
    try:
        verify_first_pass_seal(run_directory)
    except HeldoutIntegrityError as exc:
        raise ValueError(
            f"sealed first-pass artifact drifted or is invalid: {exc}"
        ) from exc


def heldout_gate() -> GateResult:
    name = "prospective_heldout"
    protocol = load_mapping(PROTOCOL)
    if protocol.get("protocol_version") != 2:
        return result(name, "fail", "held-out protocol version is not 2")
    plan = load_frozen_plan(protocol, PROJECT_ROOT)
    require_matching_plan_section(protocol, plan, "benchmark")
    require_matching_plan_section(protocol, plan, "selection")
    plan_paths = as_mapping(plan.get("paths"), "frozen plan paths")
    frozen_hash = str(
        as_mapping(protocol.get("implementation_freeze"), "implementation freeze").get(
            "pre_unblinding_sha256", ""
        )
    )
    if not frozen_hash or current_surface_hash() != frozen_hash:
        return result(
            name, "fail", "current evaluation surface differs from the recorded freeze"
        )
    status = str(protocol.get("status", ""))
    results = as_mapping(protocol.get("results"), "held-out results record")
    planned_run = resolve_recorded_path(
        PROJECT_ROOT,
        results.get("planned_run_directory"),
        "planned first-pass run directory",
    )
    planned_marker = resolve_recorded_path(
        PROJECT_ROOT,
        results.get("planned_oracle_marker"),
        "planned oracle marker",
    )
    score_path = resolve_recorded_path(
        PROJECT_ROOT,
        results.get("planned_score_artifact"),
        "planned score artifact",
    )
    if (
        planned_run != HELDOUT_RUN
        or planned_marker != HELDOUT_RUN / "ORACLE_SCORING_STARTED.json"
        or score_path != HELDOUT_RUN / "scored-after-oracle-unsealing.json"
        or planned_run
        != resolve_recorded_path(
            PROJECT_ROOT, plan_paths.get("run_directory"), "planned run directory"
        )
        or planned_marker
        != resolve_recorded_path(
            PROJECT_ROOT, plan_paths.get("oracle_marker"), "planned oracle marker"
        )
        or score_path
        != resolve_recorded_path(
            PROJECT_ROOT, plan_paths.get("score_artifact"), "planned score artifact"
        )
    ):
        return result(name, "fail", "held-out output paths differ from the frozen plan")
    leaked_paths = [
        path
        for path in (HELDOUT_QUESTIONS, HELDOUT_DATA, HELDOUT_MANIFEST, HELDOUT_RUN)
        if path.exists()
    ]
    if status == "implementation_frozen_blinded":
        unblinding = as_mapping(protocol.get("unblinding"), "unblinding record")
        if (
            unblinding.get("status") != "not_started"
            or results.get("status") != "not_run"
        ):
            return result(
                name, "fail", "blinded protocol has inconsistent state records"
            )
        if leaked_paths:
            return result(
                name,
                "fail",
                "held-out payload/result exists while protocol says blinded",
            )
        return result(
            name, "pending", "community_45 remains safely blinded and has not been run"
        )
    if status not in {"unblinded_not_run", "first_pass_sealed", "scored"}:
        return result(name, "fail", f"unsupported held-out protocol status: {status!r}")
    unblinding = as_mapping(protocol.get("unblinding"), "unblinding record")
    questions_path = resolve_recorded_path(
        PROJECT_ROOT, unblinding.get("questions_file"), "recorded questions file"
    )
    extracted_root = resolve_recorded_path(
        PROJECT_ROOT, unblinding.get("extracted_root"), "recorded extracted root"
    )
    data_root = resolve_recorded_path(
        PROJECT_ROOT, unblinding.get("data_root"), "recorded analysis data root"
    )
    manifest_path = resolve_recorded_path(
        PROJECT_ROOT,
        unblinding.get("extracted_manifest"),
        "recorded extracted-data manifest",
    )
    if (
        unblinding.get("status") != "complete"
        or unblinding.get("plan_sha256")
        != as_mapping(protocol.get("frozen_plan"), "frozen plan record").get("sha256")
        or questions_path != HELDOUT_QUESTIONS
        or extracted_root != HELDOUT_DATA
        or manifest_path != HELDOUT_MANIFEST
        or questions_path
        != resolve_recorded_path(
            PROJECT_ROOT, plan_paths.get("questions_file"), "planned questions file"
        )
        or extracted_root
        != resolve_recorded_path(
            PROJECT_ROOT, plan_paths.get("extracted_root"), "planned extracted root"
        )
        or data_root
        != resolve_recorded_path(
            PROJECT_ROOT, plan_paths.get("data_root"), "planned analysis data root"
        )
        or manifest_path
        != resolve_recorded_path(
            PROJECT_ROOT,
            plan_paths.get("extracted_manifest"),
            "planned extracted-data manifest",
        )
        or not data_root.is_relative_to(extracted_root)
        or not questions_path.is_file()
        or not data_root.is_dir()
    ):
        return result(
            name, "fail", "unblinded protocol paths or payloads are incomplete"
        )
    if sha256_file(questions_path) != unblinding.get("questions_sha256"):
        return result(name, "fail", "held-out question checksum mismatch")
    verify_data_manifest(
        data_root=extracted_root,
        manifest_path=manifest_path,
        project_root=PROJECT_ROOT,
        expected_manifest_sha256=unblinding.get("extracted_manifest_sha256"),
        expected_file_count=unblinding.get("extracted_file_count"),
    )

    marker = HELDOUT_RUN / "FIRST_PASS_STARTED.json"
    summary = HELDOUT_RUN / "sealed-summary-without-oracle.json"
    seal = HELDOUT_RUN / "seal.sha256"
    if status == "unblinded_not_run":
        if results.get("status") != "not_run":
            return result(name, "fail", "unrun protocol has inconsistent result state")
        if any(
            path.exists()
            for path in (marker, summary, seal, planned_marker, score_path)
        ):
            return result(
                name,
                "fail",
                "first-pass or scoring artifacts exist before their protocol transition",
            )
        return result(
            name, "pending", "held-out data is unblinded but first pass has not started"
        )
    if results.get("status") != status:
        return result(name, "fail", "held-out protocol/result states disagree")
    if not marker.is_file() or not summary.is_file() or not seal.is_file():
        return result(
            name, "fail", "held-out first pass started but was not completely sealed"
        )
    recorded_summary = resolve_recorded_path(
        PROJECT_ROOT, results.get("artifact"), "recorded first-pass summary"
    )
    recorded_seal = resolve_recorded_path(
        PROJECT_ROOT, results.get("seal_file"), "recorded first-pass seal"
    )
    if recorded_summary != summary or recorded_seal != seal:
        return result(name, "fail", "sealed artifact paths differ from the protocol")
    required_paths = (
        "FIRST_PASS_STARTED.json",
        "sealed-summary-without-oracle.json",
        *(f"runs/task-{task_id}.json" for task_id in TASK_IDS),
    )
    seal_verification = verify_first_pass_seal(
        HELDOUT_RUN,
        seal_path=seal,
        expected_seal_sha256=results.get("seal_sha256"),
        required_paths=required_paths,
    )
    if seal_verification.file_count != results.get("sealed_file_count") or sha256_file(
        summary
    ) != results.get("artifact_sha256"):
        return result(name, "fail", "first-pass protocol checksums or census disagree")
    sealed_summary = load_mapping(summary)
    first_pass_marker = load_mapping(marker)
    summary_rows = sealed_summary.get("results")
    summary_ids = (
        tuple(
            int(as_mapping(row, "first-pass result")["task_id"]) for row in summary_rows
        )
        if isinstance(summary_rows, list)
        else ()
    )
    if (
        tuple(sealed_summary.get("task_ids", ())) != TASK_IDS
        or summary_ids != TASK_IDS
        or sealed_summary.get("protocol_id") != protocol.get("protocol_id")
        or sealed_summary.get("plan_sha256")
        != as_mapping(protocol.get("frozen_plan"), "frozen plan record").get("sha256")
        or sealed_summary.get("execution_config_sha256")
        != canonical_json_sha256(as_mapping(plan.get("execution"), "plan execution"))
        or sealed_summary.get("surface_sha256") != frozen_hash
        or sealed_summary.get("questions_sha256") != unblinding.get("questions_sha256")
        or sealed_summary.get("data_manifest_sha256")
        != unblinding.get("extracted_manifest_sha256")
        or sealed_summary.get("data_file_count")
        != unblinding.get("extracted_file_count")
    ):
        return result(name, "fail", "sealed first-pass summary bindings are invalid")
    if (
        first_pass_marker.get("protocol_id") != protocol.get("protocol_id")
        or first_pass_marker.get("plan_sha256") != sealed_summary.get("plan_sha256")
        or first_pass_marker.get("surface_sha256") != frozen_hash
        or first_pass_marker.get("questions_sha256")
        != unblinding.get("questions_sha256")
        or first_pass_marker.get("data_manifest_sha256")
        != unblinding.get("extracted_manifest_sha256")
        or first_pass_marker.get("execution_config_sha256")
        != sealed_summary.get("execution_config_sha256")
    ):
        return result(name, "fail", "first-pass marker bindings are invalid")
    if status == "first_pass_sealed":
        if planned_marker.exists() or score_path.exists():
            return result(
                name,
                "fail",
                "oracle scoring artifacts exist before the scored-state transition",
            )
        return result(
            name,
            "pending",
            "first-pass predictions are sealed but oracle scoring is pending",
        )
    if not planned_marker.is_file() or not score_path.is_file():
        return result(name, "fail", "scored protocol is missing scoring artifacts")
    recorded_score = results.get("score_artifact")
    if recorded_score != score_path.relative_to(PROJECT_ROOT).as_posix():
        return result(
            name, "fail", f"recorded score path is invalid: {recorded_score!r}"
        )
    if (
        results.get("oracle_marker")
        != planned_marker.relative_to(PROJECT_ROOT).as_posix()
        or sha256_file(planned_marker) != results.get("oracle_marker_sha256")
        or sha256_file(score_path) != results.get("score_sha256")
    ):
        return result(name, "fail", "scoring artifact checksums or paths disagree")
    oracle_marker = load_mapping(planned_marker)
    if (
        oracle_marker.get("protocol_id") != protocol.get("protocol_id")
        or oracle_marker.get("plan_sha256")
        != as_mapping(protocol.get("frozen_plan"), "frozen plan record").get("sha256")
        or oracle_marker.get("seal_sha256") != results.get("seal_sha256")
        or oracle_marker.get("benchmark_metadata_sha256")
        != as_mapping(protocol.get("benchmark"), "benchmark record").get(
            "metadata_sha256"
        )
    ):
        return result(name, "fail", "oracle-scoring marker bindings are invalid")
    score = load_mapping(score_path)
    aggregate = as_mapping(score.get("aggregate"), "held-out score aggregate")
    rows = score.get("results")
    if (
        aggregate.get("tasks") != len(TASK_IDS)
        or not isinstance(rows, list)
        or score.get("protocol_id") != protocol.get("protocol_id")
        or score.get("plan_sha256")
        != as_mapping(protocol.get("frozen_plan"), "frozen plan record").get("sha256")
        or score.get("sealed_summary_sha256") != results.get("artifact_sha256")
        or score.get("benchmark_metadata_sha256")
        != as_mapping(protocol.get("benchmark"), "benchmark record").get(
            "metadata_sha256"
        )
    ):
        return result(name, "fail", "held-out score has an invalid task census")
    observed_ids = tuple(
        int(as_mapping(row, "held-out result")["task_id"]) for row in rows
    )
    if observed_ids != TASK_IDS:
        return result(
            name, "fail", "held-out score task IDs differ from the frozen protocol"
        )
    return result(
        name,
        "pass",
        "all 13 prospective tasks have sealed and scored first-pass results",
    )


def contains_email(value: Any) -> bool:
    return EMAIL_PATTERN.search(json.dumps(value, ensure_ascii=False)) is not None


def contains_identity_field(value: Any) -> bool:
    if isinstance(value, dict):
        if any(str(key).lower() in {"name", "email", "contact"} for key in value):
            return True
        return any(contains_identity_field(child) for child in value.values())
    if isinstance(value, list):
        return any(contains_identity_field(child) for child in value)
    return False


def is_plain_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def trial_acceptance_failures(record: Mapping[str, Any]) -> tuple[str, ...]:
    participant = as_mapping(record.get("participant"), "trial participant")
    outcomes = as_mapping(record.get("outcomes"), "trial outcomes")
    timings = as_mapping(record.get("timings_seconds"), "trial timings")
    conditions = (
        (
            participant.get("prior_project_exposure") is False,
            "participant had no prior project exposure",
        ),
        (
            outcomes.get("completed_without_facilitator_correction")
            == len(TRIAL_TASK_IDS),
            "all six tasks were completed without facilitator correction",
        ),
        (
            outcomes.get("repeat_core_path_without_facilitator_correction") is True,
            "the core path was repeated without facilitator correction",
        ),
        (
            outcomes.get("correctly_distinguished_report_and_diagnosis") is True,
            "the participant distinguished a report from a diagnosis",
        ),
        (
            outcomes.get("blocking_issues_remaining") == 0,
            "no blocking issue remained open",
        ),
        (
            record.get("consent_recorded") is True,
            "participation consent was recorded",
        ),
        (
            all(timings.get(key) is not None for key in TRIAL_TIMING_KEYS),
            "all three task timings were recorded",
        ),
    )
    return tuple(detail for passed, detail in conditions if not passed)


def validate_trial(record: Mapping[str, Any], path: Path) -> bool:
    if record.get("schema_version") != "askdu-user-trial-v3":
        raise ValueError(f"{path.name}: unsupported trial schema")
    if record.get("is_example") is not False:
        raise ValueError(
            f"{path.name}: example record must use the .example.json suffix"
        )
    if contains_email(record) or contains_identity_field(record):
        raise ValueError(f"{path.name}: trial record contains a direct identity field")
    occurred_at = datetime.fromisoformat(
        str(record.get("occurred_at", "")).replace("Z", "+00:00")
    )
    if occurred_at.tzinfo is None or occurred_at.utcoffset() is None:
        raise ValueError(f"{path.name}: occurred_at must include a timezone")
    filename_match = re.fullmatch(
        r"(?P<date>\d{4}-\d{2}-\d{2})-[A-Za-z0-9][A-Za-z0-9_-]{1,39}\.json",
        path.name,
    )
    if (
        filename_match is None
        or filename_match.group("date") != occurred_at.date().isoformat()
    ):
        raise ValueError(
            f"{path.name}: use a date-matched YYYY-MM-DD-<session>.json filename"
        )
    session_id = str(record.get("session_id", "")).strip()
    deployment = str(record.get("deployment", "")).strip()
    browser = str(record.get("browser", "")).strip()
    if (
        not session_id
        or "example" in session_id.lower()
        or not deployment
        or not browser
    ):
        raise ValueError(f"{path.name}: session ID or deployment is invalid")
    if record.get("build_version") != project_version():
        raise ValueError(
            f"{path.name}: build version differs from the current artifact"
        )
    if (
        record.get("trial_protocol_id") != TRIAL_PROTOCOL_ID
        or record.get("trial_protocol_sha256") != current_trial_protocol_hash()
    ):
        raise ValueError(
            f"{path.name}: trial protocol ID or digest differs from the current protocol"
        )
    surface_hash = record.get("demo_surface_sha256")
    if (
        not isinstance(surface_hash, str)
        or re.fullmatch(r"[0-9a-f]{64}", surface_hash) is None
        or surface_hash != current_demo_surface_hash()
    ):
        raise ValueError(
            f"{path.name}: demo surface digest differs from the current implementation"
        )
    viewport = as_mapping(record.get("viewport_css_px"), f"{path.name}.viewport")
    width = viewport.get("width")
    height = viewport.get("height")
    zoom = record.get("zoom_percent")
    if (
        not is_plain_int(width)
        or not is_plain_int(height)
        or not 320 <= width <= 10000
        or not 240 <= height <= 10000
        or not is_plain_int(zoom)
        or not 50 <= zoom <= 500
    ):
        raise ValueError(f"{path.name}: viewport or browser zoom is invalid")
    participant = as_mapping(record.get("participant"), f"{path.name}.participant")
    outcomes = as_mapping(record.get("outcomes"), f"{path.name}.outcomes")
    participant_code = str(participant.get("code", "")).strip()
    familiarity = participant.get("data_analysis_familiarity_1_to_5")
    if (
        re.fullmatch(r"[A-Za-z0-9_-]{2,40}", participant_code) is None
        or participant.get("non_author") is not True
        or not isinstance(familiarity, int)
        or isinstance(familiarity, bool)
        or not 1 <= familiarity <= 5
    ):
        raise ValueError(
            f"{path.name}: a pseudonymous non-author participant is required"
        )
    if not isinstance(participant.get("prior_project_exposure"), bool):
        raise TypeError(f"{path.name}: prior project exposure must be Boolean")

    task_results = as_mapping(record.get("task_results"), f"{path.name}.task_results")
    if set(task_results) != set(TRIAL_TASK_IDS) or any(
        not isinstance(value, bool) for value in task_results.values()
    ):
        raise ValueError(f"{path.name}: task results must contain six Boolean outcomes")
    completed_tasks = sum(value is True for value in task_results.values())

    completed = outcomes.get("completed_without_facilitator_correction")
    blockers = outcomes.get("blocking_issues_remaining")
    repeat = outcomes.get("repeat_core_path_without_facilitator_correction")
    distinguished = outcomes.get("correctly_distinguished_report_and_diagnosis")
    if (
        outcomes.get("tasks_total") != len(TRIAL_TASK_IDS)
        or not is_plain_int(completed)
        or not 0 <= completed <= len(TRIAL_TASK_IDS)
        or completed != completed_tasks
        or not isinstance(repeat, bool)
        or not isinstance(distinguished, bool)
        or not is_plain_int(blockers)
        or blockers < 0
        or not isinstance(record.get("consent_recorded"), bool)
    ):
        raise ValueError(f"{path.name}: aggregate trial outcomes are inconsistent")

    timings = as_mapping(record.get("timings_seconds"), f"{path.name}.timings")
    if set(timings) != set(TRIAL_TIMING_KEYS):
        raise ValueError(f"{path.name}: trial timing fields are incomplete")
    for value in timings.values():
        if value is not None and (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or not 0 < value <= 3600
        ):
            raise ValueError(
                f"{path.name}: trial timings must be 1–3600 seconds or null"
            )

    issues = record.get("issues")
    if not isinstance(issues, list):
        raise TypeError(f"{path.name}: issues must be an array")
    open_blockers = 0
    issue_codes: set[str] = set()
    for index, value in enumerate(issues):
        issue = as_mapping(value, f"{path.name}.issues[{index}]")
        code = str(issue.get("code", "")).strip()
        severity = issue.get("severity")
        status = issue.get("status")
        summary = str(issue.get("summary", "")).strip()
        if (
            re.fullmatch(r"[A-Za-z0-9_-]{2,40}", code) is None
            or code in issue_codes
            or severity not in {"blocks", "confuses", "cosmetic"}
            or status not in {"open", "resolved"}
            or not summary
            or len(summary) > 500
        ):
            raise ValueError(f"{path.name}: issue {index + 1} is invalid")
        issue_codes.add(code)
        if severity == "blocks" and status == "open":
            open_blockers += 1
    if blockers != open_blockers:
        raise ValueError(f"{path.name}: open blocking-issue count is inconsistent")

    return not trial_acceptance_failures(record)


def trial_record_gate(path: Path) -> GateResult:
    name = "non_author_rehearsal_record"
    record = load_mapping(path)
    if validate_trial(record, path):
        return result(
            name,
            "pass",
            f"{path.name} meets the protocol-bound six-task and repeat gate",
        )
    missing = "; ".join(trial_acceptance_failures(record))
    return result(name, "pending", f"{path.name} is valid but not accepted: {missing}")


def rehearsal_gate() -> GateResult:
    name = "non_author_rehearsal"
    records = sorted(
        path
        for path in TRIAL_DIRECTORY.glob("*.json")
        if not path.name.endswith(".example.json")
    )
    if not records:
        return result(
            name, "pending", "no completed non-author rehearsal record exists"
        )
    accepted = [validate_trial(load_mapping(path), path) for path in records]
    if not any(accepted):
        return result(
            name,
            "pending",
            "rehearsals exist but none meets the six-task acceptance gate",
        )
    return result(
        name,
        "pass",
        f"{sum(accepted)} of {len(records)} rehearsal records meets the gate",
    )


def run_media_check(path: Path) -> None:
    process = subprocess.run(
        [sys.executable, str(MEDIA_CHECKER), "--mode", "submission", str(path)],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=90,
    )
    if process.returncode != 0:
        detail = (
            process.stderr.strip() or process.stdout.strip() or "unknown media error"
        )
        raise ValueError(detail)


def narrated_video_gate() -> GateResult:
    name = "narrated_video"
    if not NARRATED_VIDEO.is_file():
        if VIDEO_REVIEW.exists():
            return result(
                name, "fail", "video review exists without its reviewed video"
            )
        return result(
            name, "pending", "author-recorded narrated submission video is absent"
        )
    run_media_check(NARRATED_VIDEO)
    if not VIDEO_REVIEW.is_file():
        return result(
            name, "pending", "video passes technical checks but lacks two-author review"
        )
    review = load_mapping(VIDEO_REVIEW)
    if review.get("schema_version") != "askdu-video-review-v1":
        return result(name, "fail", "video review schema is invalid")
    if contains_email(review):
        return result(
            name, "fail", "video review must use author codes, not email addresses"
        )
    reviewed_at = datetime.fromisoformat(
        str(review.get("reviewed_at", "")).replace("Z", "+00:00")
    )
    if reviewed_at.tzinfo is None or reviewed_at.utcoffset() is None:
        return result(name, "fail", "video review timestamp must include a timezone")
    if review.get("video_sha256") != sha256_file(NARRATED_VIDEO):
        return result(name, "fail", "video changed after human review")
    reviewers = review.get("reviewers")
    reviewer_codes = {str(reviewer).strip() for reviewer in reviewers or []}
    if (
        not isinstance(reviewers, list)
        or len(reviewer_codes) < 2
        or "" in reviewer_codes
        or any("example" in reviewer.lower() for reviewer in reviewer_codes)
    ):
        return result(
            name, "pending", "two distinct author reviewer codes are required"
        )
    checks = as_mapping(review.get("checks"), "video review checks")
    required_checks = (
        "audio_intelligible",
        "synchronization_correct",
        "claims_match_paper",
        "captions_legible",
        "data_gap_ending_present",
        "artifact_url_verified",
    )
    incomplete = [key for key in required_checks if checks.get(key) is not True]
    if incomplete:
        return result(
            name, "pending", "video human-review checks open: " + ", ".join(incomplete)
        )
    return result(
        name, "pass", "submission video passed technical and two-author review"
    )


def availability_url() -> str:
    match = AVAILABILITY_PATTERN.search(PAPER_SOURCE.read_text(encoding="utf-8"))
    if match is None:
        raise ValueError("paper availability command is missing")
    return match.group("url").strip()


def project_version() -> str:
    text = (PROJECT_ROOT / "backend/pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^version\s*=\s*"([^"]+)"', text, flags=re.MULTILINE)
    if match is None:
        raise ValueError("project version is unavailable")
    return match.group(1)


def public_artifact_gate() -> GateResult:
    name = "public_artifact"
    version = project_version()
    archive = (
        PROJECT_ROOT
        / "artifacts/release"
        / f"ask-dont-upload-artifact-v{version}-release.tar.gz"
    )
    checksum = archive.with_name(f"{archive.name}.sha256")
    url = availability_url()
    if not archive.exists() and checksum.exists():
        return result(
            name, "fail", "public artifact checksum exists without its archive"
        )
    if not archive.is_file():
        return result(name, "pending", "sanitized public artifact has not been built")
    if not checksum.is_file():
        return result(name, "fail", "public artifact checksum is missing")
    parts = checksum.read_text(encoding="utf-8").split()
    if len(parts) != 2 or parts[0] != sha256_file(archive) or parts[1] != archive.name:
        return result(name, "fail", "public artifact checksum does not match")
    verification = subprocess.run(
        [str(PROJECT_ROOT / "scripts/verify_artifact_bundle.sh"), str(archive)],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=90,
    )
    if verification.returncode != 0:
        return result(name, "fail", "public artifact failed clean-room verification")
    if not url:
        return result(name, "pending", "paper artifact availability URL is empty")
    parsed = urlsplit(url)
    hostname = parsed.hostname or ""
    if parsed.scheme != "https" or not hostname or parsed.username or parsed.password:
        return result(name, "fail", "paper artifact URL must be credential-free HTTPS")
    if hostname == "example.com" or hostname.endswith(PLACEHOLDER_SUFFIXES):
        return result(name, "pending", "paper artifact URL is still a placeholder")
    return result(
        name, "pass", "public archive checksum and paper HTTPS URL are present"
    )


def evaluate(name: str, check: Callable[[], GateResult]) -> GateResult:
    try:
        return check()
    except (
        json.JSONDecodeError,
        KeyError,
        OSError,
        subprocess.SubprocessError,
        TypeError,
        ValueError,
    ) as exc:
        return result(name, "fail", str(exc))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit non-paper evidence required before calling the demo submission-ready."
    )
    parser.add_argument("--mode", choices=("draft", "submission"), default="draft")
    action = parser.add_mutually_exclusive_group()
    action.add_argument(
        "--trial-record",
        type=Path,
        help="validate a rehearsal record against the current demo and trial protocol",
    )
    action.add_argument(
        "--print-demo-surface-sha256",
        action="store_true",
        help="print the current user-visible implementation digest",
    )
    action.add_argument(
        "--print-trial-protocol-sha256",
        action="store_true",
        help="print the current participant-prompt and scoring-protocol digest",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.print_demo_surface_sha256:
        print(current_demo_surface_hash())
        return
    if args.print_trial_protocol_sha256:
        print(current_trial_protocol_hash())
        return
    if args.trial_record is not None:
        gate = evaluate(
            "non_author_rehearsal_record",
            lambda: trial_record_gate(args.trial_record),
        )
        print(f"{gate.status.upper()}: [{gate.name}] {gate.detail}")
        if gate.status != "pass":
            raise SystemExit(1)
        return
    checks: tuple[tuple[str, Callable[[], GateResult]], ...] = (
        ("official_demo_cfp", cfp_gate),
        ("release_licensing", license_gate),
        ("prospective_heldout", heldout_gate),
        ("non_author_rehearsal", rehearsal_gate),
        ("narrated_video", narrated_video_gate),
        ("public_artifact", public_artifact_gate),
    )
    results = [evaluate(name, check) for name, check in checks]
    for gate in results:
        print(f"{gate.status.upper()}: [{gate.name}] {gate.detail}")
    counts = {
        status: sum(gate.status == status for gate in results)
        for status in ("pass", "pending", "fail")
    }
    print(
        f"SUMMARY: {counts['pass']} pass, {counts['pending']} pending, "
        f"{counts['fail']} fail ({args.mode} mode)."
    )
    blocking = counts["fail"] > 0 or (
        args.mode == "submission" and counts["pending"] > 0
    )
    if blocking:
        raise SystemExit(1)
    print("PASS: draft readiness state is internally consistent.")


if __name__ == "__main__":
    main()
