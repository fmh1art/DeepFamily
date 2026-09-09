from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = PROJECT_ROOT / "paper/figures/demo-ui.capture.json"
EXPECTED_SCREENSHOT = "paper/figures/demo-ui.png"
EXPECTED_CALLOUTS = ["A", "B", "C", "D", "E"]
REPLAY_DIRECTORY = "paper/figures/agentic-replay-v1"
REPLAY_MANIFEST = f"{REPLAY_DIRECTORY}/capture.json"
REPLAY_SOURCE = "frontend/e2e/capture-agentic-replay.mjs"
REPLAY_STYLE = "frontend/e2e/agentic-replay-plate.css"
REPLAY_EVIDENCE = "experiments/evidence/agentic-question-only-smoke-2026-09-09.json"
REPLAY_RUN = "runtime/stage-io-report-smoke-schema-20260909.json"
REPLAY_RUN_ID = "run_e2f9348452df475c"
REPLAY_OUTPUTS = {
    f"{REPLAY_DIRECTORY}/{name}": "png"
    for name in (
        "overview.png",
        "overview-gray.png",
        "discovery.png",
        "preparation.png",
        "analysis.png",
        "report.png",
    )
} | {f"{REPLAY_DIRECTORY}/overview.pdf": "browser-vector-pdf"}


def as_mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise TypeError(f"{label} must be an object")
    return value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def png_dimensions(path: Path) -> tuple[int, int]:
    with path.open("rb") as handle:
        header = handle.read(24)
    if (
        len(header) != 24
        or header[:8] != b"\x89PNG\r\n\x1a\n"
        or header[12:16] != b"IHDR"
    ):
        raise ValueError("paper screenshot does not have a valid PNG IHDR header")
    return int.from_bytes(header[16:20], "big"), int.from_bytes(header[20:24], "big")


def current_demo_surface_hash(project_root: Path) -> str:
    process = subprocess.run(
        [str(project_root / "scripts/hash_demo_surface.sh")],
        cwd=project_root,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    digest = process.stdout.strip()
    if re.fullmatch(r"[0-9a-f]{64}", digest) is None:
        raise ValueError("demo surface hasher returned an invalid SHA-256 digest")
    return digest


def validate_capture(manifest_path: Path, project_root: Path) -> list[str]:
    failures: list[str] = []
    manifest = as_mapping(
        json.loads(manifest_path.read_text(encoding="utf-8")), "capture manifest"
    )
    if manifest.get("schema_version") != "askdu-paper-capture-v1":
        failures.append("capture manifest schema is invalid")
    if (
        manifest.get("scenario") != "coda-community43-task959"
        or manifest.get("task_id") != 959
    ):
        failures.append("capture manifest is not bound to the task-959 scenario")
    if manifest.get("source_test") != "frontend/e2e/demo.spec.ts":
        failures.append("capture manifest does not identify its executable source test")
    source_test = project_root / "frontend/e2e/demo.spec.ts"
    source_test_sha256 = manifest.get("source_test_sha256")
    if (
        not source_test.is_file()
        or not isinstance(source_test_sha256, str)
        or re.fullmatch(r"[0-9a-f]{64}", source_test_sha256) is None
        or source_test_sha256 != sha256_file(source_test)
    ):
        failures.append("paper screenshot capture procedure has changed")
    if manifest.get("visible_callouts") != EXPECTED_CALLOUTS:
        failures.append("capture manifest does not bind callouts A through E")

    recorded_surface = manifest.get("demo_surface_sha256")
    if (
        not isinstance(recorded_surface, str)
        or re.fullmatch(r"[0-9a-f]{64}", recorded_surface) is None
        or recorded_surface != current_demo_surface_hash(project_root)
    ):
        failures.append("paper screenshot was captured from a stale demo surface")

    screenshot = as_mapping(manifest.get("screenshot"), "capture screenshot")
    if screenshot.get("path") != EXPECTED_SCREENSHOT:
        failures.append("capture manifest points to an unexpected screenshot path")
        return failures
    screenshot_path = project_root / EXPECTED_SCREENSHOT
    if not screenshot_path.is_file():
        failures.append("paper screenshot is missing")
        return failures

    expected_digest = screenshot.get("sha256")
    if (
        not isinstance(expected_digest, str)
        or re.fullmatch(r"[0-9a-f]{64}", expected_digest) is None
        or expected_digest != sha256_file(screenshot_path)
    ):
        failures.append("paper screenshot checksum differs from its capture manifest")

    actual_width, actual_height = png_dimensions(screenshot_path)
    pixel_width = screenshot.get("pixel_width")
    pixel_height = screenshot.get("pixel_height")
    css_width = screenshot.get("css_width")
    css_height = screenshot.get("css_height")
    scale = screenshot.get("device_scale_factor")
    values = (pixel_width, pixel_height, css_width, css_height)
    if any(
        not isinstance(value, int) or isinstance(value, bool) or value <= 0
        for value in values
    ):
        failures.append("capture dimensions must be positive integers")
        return failures
    if (pixel_width, pixel_height) != (actual_width, actual_height):
        failures.append("paper screenshot dimensions differ from its capture manifest")
    if actual_width < 2400 or actual_height < 1200:
        failures.append("paper screenshot resolution is below the publication floor")
    aspect_ratio = actual_width / actual_height
    if not 1.6 <= aspect_ratio <= 2.2:
        failures.append("paper screenshot aspect ratio is outside the reviewed range")
    if (
        isinstance(scale, bool)
        or not isinstance(scale, (int, float))
        or not math.isfinite(scale)
        or not 1 <= scale <= 4
        or abs(actual_width / css_width - scale) > 0.01
        or abs(actual_height / css_height - scale) > 0.01
    ):
        failures.append("capture device scale and CSS dimensions are inconsistent")
    return failures


def validate_agentic_capture(project_root: Path) -> list[str]:
    """Check a historical observation's current-UI replay, not a new model run.

    Raw run logs are intentionally absent from public artifacts. Their identity
    is bound to the registered observation; verify local bytes too when present.
    Checksums establish traceability, not factual correctness of model prose.
    """
    manifest = as_mapping(
        json.loads((project_root / REPLAY_MANIFEST).read_text(encoding="utf-8")),
        "agentic replay manifest",
    )
    failures: list[str] = []
    expected_fields = {
        "schema_version": "askdu-agentic-replay-capture-v1",
        "capture_kind": "historical_model_run_in_current_ui",
        "visible_panels": ["a", "b", "c"],
        "model_calls_during_capture": 0,
        "replayed_post_requests": 1,
        "browser_errors": [],
        "excerpt": {
            "graph_hop": 5,
            "selected_source_hop": 12,
            "preview_rows": 3,
            "preview_columns": 2,
        },
    }
    for field, expected in expected_fields.items():
        if manifest.get(field) != expected:
            failures.append(f"agentic replay has invalid {field}")
    for field, digest_field, relative_path in (
        ("source_script", "source_sha256", REPLAY_SOURCE),
        ("style_path", "style_sha256", REPLAY_STYLE),
        ("evidence_path", "evidence_sha256", REPLAY_EVIDENCE),
    ):
        path = project_root / relative_path
        if (
            manifest.get(field) != relative_path
            or not path.is_file()
            or manifest.get(digest_field) != sha256_file(path)
        ):
            failures.append(f"agentic replay input drifted: {relative_path}")
    if manifest.get("demo_surface_sha256") != current_demo_surface_hash(project_root):
        failures.append("agentic replay was captured from a stale demo surface")

    evidence = as_mapping(
        json.loads((project_root / REPLAY_EVIDENCE).read_text(encoding="utf-8")),
        "registered model observation",
    )
    observations = evidence.get("runs")
    if not isinstance(observations, list):
        raise TypeError("registered observations must be a list")
    matches = [
        item
        for item in observations
        if isinstance(item, dict) and item.get("run_id") == REPLAY_RUN_ID
    ]
    if len(matches) != 1:
        failures.append("agentic replay has no unique registered historical run")
    else:
        observation = matches[0]
        expected_run = {
            "path": REPLAY_RUN,
            "run_id": REPLAY_RUN_ID,
            "sha256": observation.get("sha256"),
        }
        if (
            observation.get("status") != "completed"
            or observation.get("path") != REPLAY_RUN
            or manifest.get("original_run") != expected_run
            or manifest.get("original_report_sha256")
            != observation.get("report_sha256")
            or not isinstance(observation.get("sha256"), str)
            or re.fullmatch(r"[0-9a-f]{64}", observation["sha256"]) is None
        ):
            failures.append(
                "agentic replay is not bound to the registered run and report"
            )
        local_run = project_root / REPLAY_RUN
        if local_run.exists() and sha256_file(local_run) != observation.get("sha256"):
            failures.append("agentic replay historical run bytes have changed")

    outputs = as_mapping(manifest.get("outputs"), "agentic replay outputs")
    if set(outputs) != set(REPLAY_OUTPUTS):
        failures.append("agentic replay has an unexpected output set")
        return failures
    for relative_path, expected_format in REPLAY_OUTPUTS.items():
        path = project_root / relative_path
        record = as_mapping(outputs[relative_path], relative_path)
        if not path.is_file():
            failures.append(f"agentic replay output is missing: {relative_path}")
            continue
        if (
            record.get("format") != expected_format
            or record.get("sha256") != sha256_file(path)
            or record.get("bytes") != path.stat().st_size
        ):
            failures.append(f"agentic replay output drifted: {relative_path}")
        if expected_format != "png":
            continue
        width, height = png_dimensions(path)
        if (width, height) != (record.get("pixel_width"), record.get("pixel_height")):
            failures.append(f"agentic replay dimensions drifted: {relative_path}")
        if relative_path.endswith(("overview.png", "overview-gray.png")):
            css_height = manifest.get("css_height")
            if (
                manifest.get("css_width") != 1000
                or manifest.get("device_scale_factor") != 3
                or not isinstance(css_height, (float, int))
                or isinstance(css_height, bool)
                or not math.isfinite(css_height)
                or not 400 <= css_height <= 750
                or width != 3000
                or abs(height - css_height * 3) > 3
            ):
                failures.append(
                    "agentic replay print dimensions are outside reviewed bounds"
                )
    return failures


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify that the paper UI screenshot matches the current demo surface."
    )
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        failures = validate_capture(args.manifest, PROJECT_ROOT)
        failures.extend(validate_agentic_capture(PROJECT_ROOT))
    except (
        json.JSONDecodeError,
        OSError,
        subprocess.SubprocessError,
        TypeError,
        ValueError,
    ) as exc:
        failures = [str(exc)]
    if failures:
        for failure in failures:
            print(f"ERROR: {failure}")
        raise SystemExit(f"FAILED: {len(failures)} paper-capture assertion(s)")
    screenshot = as_mapping(
        json.loads(args.manifest.read_text(encoding="utf-8")), "capture manifest"
    )["screenshot"]
    details = as_mapping(screenshot, "capture screenshot")
    print(
        "PASS: paper UI screenshot matches the current demo surface "
        f"({details['pixel_width']}x{details['pixel_height']}, callouts A-E); "
        "agentic replay a-c is bound to its historical run, current UI, and output bytes."
    )


if __name__ == "__main__":
    main()
