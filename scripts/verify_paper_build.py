from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PDF_PATH = "paper/main.pdf"
BUILD_MANIFEST = "paper/main.build.json"
BUILDER = "askdu-paper:texlive-2024"
SYSTEM_FIGURE_MANIFEST = "paper/figures/system-overview.capture.json"
SYSTEM_FIGURE_SOURCE = "scripts/render_system_figure.py"
SYSTEM_FIGURE_OUTPUTS = {
    "paper/figures/system-overview.pdf": "vector-pdf",
    "paper/figures/system-overview.png": "png-300-dpi",
}
PAPER_INPUTS = (
    "paper/main.tex",
    "paper/references.bib",
    "paper/acmart.cls",
    "paper/pvldb.sty",
    "paper/ACM-Reference-Format.bst",
    "paper/Dockerfile",
    "paper/figures/system-overview.pdf",
    "paper/figures/system-overview.capture.json",
    "paper/figures/demo-ui.png",
    "paper/figures/demo-ui.capture.json",
    "paper/figures/agentic-replay-v1/overview.png",
    "paper/figures/agentic-replay-v1/capture.json",
    "frontend/e2e/capture-agentic-replay.mjs",
    "frontend/e2e/agentic-replay-plate.css",
    "experiments/evidence/agentic-question-only-smoke-2026-09-09.json",
    "scripts/render_system_figure.py",
    "scripts/verify_paper_capture.py",
    "scripts/verify_paper_build.py",
)


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


def file_record(path: Path) -> dict[str, int | str]:
    return {"sha256": sha256_file(path), "bytes": path.stat().st_size}


def validate_system_figure(project_root: Path) -> list[str]:
    failures: list[str] = []
    manifest_path = project_root / SYSTEM_FIGURE_MANIFEST
    manifest = as_mapping(
        json.loads(manifest_path.read_text(encoding="utf-8")),
        "system figure manifest",
    )
    if manifest.get("schema_version") != "askdu-system-figure-v1":
        failures.append("system figure manifest schema is invalid")
    if manifest.get("source_script") != SYSTEM_FIGURE_SOURCE:
        failures.append("system figure manifest identifies the wrong source script")
    source_digest = manifest.get("source_sha256")
    if (
        not isinstance(source_digest, str)
        or re.fullmatch(r"[0-9a-f]{64}", source_digest) is None
        or source_digest != sha256_file(project_root / SYSTEM_FIGURE_SOURCE)
    ):
        failures.append("system figure source has changed since rendering")
    outputs = as_mapping(manifest.get("outputs"), "system figure outputs")
    if set(outputs) != set(SYSTEM_FIGURE_OUTPUTS):
        failures.append("system figure manifest has an unexpected output set")
        return failures
    for relative_path, expected_format in SYSTEM_FIGURE_OUTPUTS.items():
        path = project_root / relative_path
        record = as_mapping(outputs.get(relative_path), relative_path)
        if not path.is_file():
            failures.append(f"system figure output is missing: {relative_path}")
            continue
        expected = file_record(path)
        if (
            record.get("format") != expected_format
            or record.get("sha256") != expected["sha256"]
            or record.get("bytes") != expected["bytes"]
        ):
            failures.append(f"system figure output drifted: {relative_path}")
    return failures


def validate_ui_capture(project_root: Path) -> list[str]:
    process = subprocess.run(
        [
            sys.executable,
            str(project_root / "scripts/verify_paper_capture.py"),
        ],
        cwd=project_root,
        check=False,
        capture_output=True,
        text=True,
        timeout=45,
    )
    if process.returncode == 0:
        return []
    detail = process.stdout.strip() or process.stderr.strip() or "unknown capture error"
    return [f"paper UI capture verification failed: {detail}"]


def validate_generated_assets(project_root: Path) -> list[str]:
    return validate_system_figure(project_root) + validate_ui_capture(project_root)


def build_record(project_root: Path) -> dict[str, object]:
    inputs: dict[str, dict[str, int | str]] = {}
    for relative_path in PAPER_INPUTS:
        path = project_root / relative_path
        if not path.is_file():
            raise FileNotFoundError(f"paper build input is missing: {relative_path}")
        inputs[relative_path] = file_record(path)
    pdf = project_root / PDF_PATH
    if not pdf.is_file():
        raise FileNotFoundError(f"paper output is missing: {PDF_PATH}")
    return {
        "schema_version": "askdu-paper-build-v1",
        "builder": BUILDER,
        "inputs": inputs,
        "output": {"path": PDF_PATH, **file_record(pdf)},
    }


def write_build_manifest(manifest_path: Path, project_root: Path) -> None:
    manifest_path.write_text(
        json.dumps(build_record(project_root), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def validate_build_manifest(manifest_path: Path, project_root: Path) -> list[str]:
    if not manifest_path.is_file():
        return ["paper build manifest is missing; run make pdf-modern"]
    recorded = as_mapping(
        json.loads(manifest_path.read_text(encoding="utf-8")),
        "paper build manifest",
    )
    current = build_record(project_root)
    failures: list[str] = []
    if recorded.get("schema_version") != current["schema_version"]:
        failures.append("paper build manifest schema is invalid")
    if recorded.get("builder") != BUILDER:
        failures.append("paper was not recorded with the pinned container builder")
    if recorded.get("inputs") != current["inputs"]:
        failures.append("paper inputs changed after the recorded PDF build")
    if recorded.get("output") != current["output"]:
        failures.append("paper PDF bytes changed after the recorded build")
    return failures


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Bind the submission PDF to its current source and figure inputs."
    )
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--manifest", type=Path, default=PROJECT_ROOT / BUILD_MANIFEST)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        failures = validate_generated_assets(PROJECT_ROOT)
        if not failures and args.write:
            write_build_manifest(args.manifest, PROJECT_ROOT)
        if not failures:
            failures.extend(validate_build_manifest(args.manifest, PROJECT_ROOT))
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
        raise SystemExit(f"FAILED: {len(failures)} paper-build assertion(s)")
    record = build_record(PROJECT_ROOT)
    output = as_mapping(record["output"], "paper output")
    action = "recorded" if args.write else "matches"
    print(
        f"PASS: paper PDF {action} the pinned builder and {len(PAPER_INPUTS)} inputs "
        f"(SHA-256 {output['sha256']})."
    )


if __name__ == "__main__":
    main()
