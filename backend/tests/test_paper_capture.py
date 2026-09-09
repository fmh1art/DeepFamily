from __future__ import annotations

import importlib.util
import json
import shutil
import sys
from pathlib import Path
from types import ModuleType

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def load_verifier() -> ModuleType:
    path = PROJECT_ROOT / "scripts/verify_paper_capture.py"
    spec = importlib.util.spec_from_file_location("askdu_test_paper_capture", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load paper-capture verifier")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


VERIFIER = load_verifier()


def fixture_capture(tmp_path: Path) -> tuple[Path, Path, dict[str, object]]:
    source_test = tmp_path / "frontend/e2e/demo.spec.ts"
    source_test.parent.mkdir(parents=True)
    shutil.copy2(PROJECT_ROOT / "frontend/e2e/demo.spec.ts", source_test)
    screenshot = tmp_path / "paper/figures/demo-ui.png"
    screenshot.parent.mkdir(parents=True)
    shutil.copy2(PROJECT_ROOT / "paper/figures/demo-ui.png", screenshot)
    manifest = json.loads(
        (PROJECT_ROOT / "paper/figures/demo-ui.capture.json").read_text(encoding="utf-8")
    )
    manifest["demo_surface_sha256"] = "a" * 64
    manifest_path = screenshot.with_name("demo-ui.capture.json")
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return manifest_path, screenshot, manifest


def test_current_paper_capture_matches_demo_surface() -> None:
    assert VERIFIER.validate_capture(VERIFIER.DEFAULT_MANIFEST, PROJECT_ROOT) == []


def test_capture_verifier_detects_screenshot_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest_path, screenshot, _ = fixture_capture(tmp_path)
    monkeypatch.setattr(VERIFIER, "current_demo_surface_hash", lambda root: "a" * 64)
    assert VERIFIER.validate_capture(manifest_path, tmp_path) == []

    with screenshot.open("ab") as handle:
        handle.write(b"changed")

    failures = VERIFIER.validate_capture(manifest_path, tmp_path)
    assert "paper screenshot checksum differs from its capture manifest" in failures


def test_capture_verifier_detects_stale_demo_surface(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest_path, _, _ = fixture_capture(tmp_path)
    monkeypatch.setattr(VERIFIER, "current_demo_surface_hash", lambda root: "b" * 64)

    failures = VERIFIER.validate_capture(manifest_path, tmp_path)

    assert "paper screenshot was captured from a stale demo surface" in failures


def fixture_agentic_replay(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    paths = (
        VERIFIER.REPLAY_MANIFEST,
        VERIFIER.REPLAY_SOURCE,
        VERIFIER.REPLAY_STYLE,
        VERIFIER.REPLAY_EVIDENCE,
        *VERIFIER.REPLAY_OUTPUTS,
    )
    for relative_path in paths:
        destination = tmp_path / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(PROJECT_ROOT / relative_path, destination)
    manifest_path = tmp_path / VERIFIER.REPLAY_MANIFEST
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    monkeypatch.setattr(
        VERIFIER, "current_demo_surface_hash", lambda root: manifest["demo_surface_sha256"]
    )
    return manifest_path


def test_current_agentic_capture_matches_registered_observation() -> None:
    assert VERIFIER.validate_agentic_capture(PROJECT_ROOT) == []


def test_agentic_capture_can_be_checked_without_private_run_logs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture_agentic_replay(tmp_path, monkeypatch)
    assert not (tmp_path / VERIFIER.REPLAY_RUN).exists()
    assert VERIFIER.validate_agentic_capture(tmp_path) == []


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("capture_kind", "new_model_run"),
        ("model_calls_during_capture", 1),
        ("excerpt", {"graph_hop": 12}),
        ("visible_panels", ["A", "B", "C"]),
        ("original_run", {"run_id": "another_run"}),
        ("css_height", float("nan")),
    ],
)
def test_agentic_capture_rejects_misleading_or_invalid_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    replacement: object,
) -> None:
    path = fixture_agentic_replay(tmp_path, monkeypatch)
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest[field] = replacement
    path.write_text(json.dumps(manifest), encoding="utf-8")
    assert VERIFIER.validate_agentic_capture(tmp_path)


@pytest.mark.parametrize(
    "relative_path",
    [
        VERIFIER.REPLAY_SOURCE,
        VERIFIER.REPLAY_STYLE,
        VERIFIER.REPLAY_EVIDENCE,
        f"{VERIFIER.REPLAY_DIRECTORY}/overview.png",
    ],
)
def test_agentic_capture_rejects_modified_inputs_and_outputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, relative_path: str
) -> None:
    fixture_agentic_replay(tmp_path, monkeypatch)
    with (tmp_path / relative_path).open("ab") as handle:
        handle.write(b"\n")
    assert any("drifted" in failure for failure in VERIFIER.validate_agentic_capture(tmp_path))


def test_agentic_capture_rejects_stale_ui_and_changed_local_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture_agentic_replay(tmp_path, monkeypatch)
    monkeypatch.setattr(VERIFIER, "current_demo_surface_hash", lambda root: "a" * 64)
    local_run = tmp_path / VERIFIER.REPLAY_RUN
    local_run.parent.mkdir(parents=True)
    local_run.write_text("{}", encoding="utf-8")
    failures = VERIFIER.validate_agentic_capture(tmp_path)
    assert "agentic replay was captured from a stale demo surface" in failures
    assert "agentic replay historical run bytes have changed" in failures
