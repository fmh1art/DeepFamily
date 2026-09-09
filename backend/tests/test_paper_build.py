from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def load_verifier() -> ModuleType:
    path = PROJECT_ROOT / "scripts/verify_paper_build.py"
    spec = importlib.util.spec_from_file_location("askdu_test_paper_build", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load paper-build verifier")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


VERIFIER = load_verifier()


def build_fixture(tmp_path: Path) -> Path:
    for index, relative_path in enumerate(VERIFIER.PAPER_INPUTS):
        path = tmp_path / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(f"input-{index}\n".encode())
    pdf = tmp_path / VERIFIER.PDF_PATH
    pdf.write_bytes(b"fixture-pdf\n")
    manifest = tmp_path / VERIFIER.BUILD_MANIFEST
    VERIFIER.write_build_manifest(manifest, tmp_path)
    return manifest


def test_current_paper_build_matches_all_recorded_inputs() -> None:
    assert (
        VERIFIER.validate_generated_assets(PROJECT_ROOT)
        + VERIFIER.validate_build_manifest(PROJECT_ROOT / VERIFIER.BUILD_MANIFEST, PROJECT_ROOT)
        == []
    )


def test_paper_build_verifier_detects_source_drift(tmp_path: Path) -> None:
    manifest = build_fixture(tmp_path)
    assert VERIFIER.validate_build_manifest(manifest, tmp_path) == []

    (tmp_path / VERIFIER.PAPER_INPUTS[0]).write_text("changed\n", encoding="utf-8")

    assert "paper inputs changed after the recorded PDF build" in (
        VERIFIER.validate_build_manifest(manifest, tmp_path)
    )


def test_paper_build_verifier_detects_pdf_drift(tmp_path: Path) -> None:
    manifest = build_fixture(tmp_path)
    (tmp_path / VERIFIER.PDF_PATH).write_bytes(b"different-pdf\n")

    assert "paper PDF bytes changed after the recorded build" in (
        VERIFIER.validate_build_manifest(manifest, tmp_path)
    )
