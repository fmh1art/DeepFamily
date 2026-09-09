from __future__ import annotations

import importlib.util
import io
import os
import re
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
ARCHIVE_ROOT = "ask-dont-upload-v0.4.0"
spec = importlib.util.spec_from_file_location(
    "askdu_artifact_audit", ROOT / "scripts/audit_artifact_archive.py"
)
assert spec is not None and spec.loader is not None
AUDIT = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = AUDIT
spec.loader.exec_module(AUDIT)


def archive_with(tmp_path: Path, members: list[tuple[str, bytes | str]]) -> Path:
    archive = tmp_path / "input.tar.gz"
    with tarfile.open(archive, "w:gz") as bundle:
        for name, value in members:
            info = tarfile.TarInfo(name)
            if isinstance(value, str):
                info.type = tarfile.SYMTYPE
                info.linkname = value
                bundle.addfile(info)
            else:
                info.size = len(value)
                bundle.addfile(info, io.BytesIO(value))
    return archive


@pytest.mark.parametrize("syntax", ["plain", "quoted", "compose"])
def test_pinned_provider_is_internal_preview_only(tmp_path: Path, syntax: str) -> None:
    assignment = "ASKDU_LLM_BASE_URL"
    url = AUDIT.PREVIEW_PROVIDER
    config = {
        "plain": assignment + "=" + url,
        "quoted": "export " + assignment + "='" + url + "'",
        "compose": "${" + assignment + ":-" + url + "}",
    }[syntax]
    archive = archive_with(tmp_path, [(ARCHIVE_ROOT + "/.env.example", config.encode())])
    assert AUDIT.audit_archive(archive, expected_root=ARCHIVE_ROOT, mode="preview") == 1
    with pytest.raises(AUDIT.ArtifactAuditError, match="provider configuration"):
        AUDIT.audit_archive(archive, expected_root=ARCHIVE_ROOT, mode="public")


@pytest.mark.parametrize(
    "url",
    [
        "https://unknown.invalid/v1",
        "http://localhost.attacker.invalid/v1",
        "https://provider.example.attacker.invalid/v1",
        "https://person:password@provider.example/v1",
        AUDIT.PREVIEW_PROVIDER + "&extra=true",
        AUDIT.PREVIEW_PROVIDER + "#extra",
    ],
)
def test_preview_provider_exception_is_exact(tmp_path: Path, url: str) -> None:
    content = ("ASKDU_LLM_ENDPOINT=" + url).encode()
    archive = archive_with(tmp_path, [(ARCHIVE_ROOT + "/config.txt", content)])
    with pytest.raises(AUDIT.ArtifactAuditError, match="provider configuration"):
        AUDIT.audit_archive(archive, expected_root=ARCHIVE_ROOT, mode="preview")


@pytest.mark.parametrize("quoted", [False, True])
def test_actual_member_credentials_are_rejected_without_value_disclosure(
    tmp_path: Path, quoted: bool
) -> None:
    secret = "x" * 32
    content = ('"api_key": "' if quoted else "API_KEY=") + secret
    archive = archive_with(tmp_path, [(ARCHIVE_ROOT + "/.hidden.txt", content.encode())])
    with pytest.raises(AUDIT.ArtifactAuditError, match="credential-shaped") as exc:
        AUDIT.audit_archive(archive, expected_root=ARCHIVE_ROOT, mode="preview")
    assert secret not in str(exc.value)


def test_empty_key_does_not_consume_next_environment_assignment(tmp_path: Path) -> None:
    content = b"ASKDU_LLM_API_KEY=\nASKDU_LLM_API_STYLE=azure_chat\n"
    archive = archive_with(tmp_path, [(ARCHIVE_ROOT + "/.env.example", content)])
    assert AUDIT.audit_archive(archive, expected_root=ARCHIVE_ROOT, mode="public") == 1


@pytest.mark.parametrize(
    "name",
    [
        "/tmp/outside",
        ARCHIVE_ROOT + "/../outside",
        ARCHIVE_ROOT + "/a//b",
        ARCHIVE_ROOT + "/a\nb",
        ARCHIVE_ROOT + "/.env",
        ARCHIVE_ROOT + "/backend/.env.example",
        ARCHIVE_ROOT + "/data/external/private.txt",
        ARCHIVE_ROOT + "/data/pilots/heldout-v1-questions.json",
        ARCHIVE_ROOT + "/data/manifests/coda-community-45-extracted.sha256",
        ARCHIVE_ROOT + "/third_party/upstream/private.txt",
        ARCHIVE_ROOT + "/paper/acmart.cls",
        ARCHIVE_ROOT + "/runtime/run.json",
    ],
)
def test_unsafe_and_forbidden_archive_members_are_rejected(tmp_path: Path, name: str) -> None:
    archive = archive_with(tmp_path, [(name, b"fixture")])
    with pytest.raises(AUDIT.ArtifactAuditError):
        AUDIT.audit_archive(archive, expected_root=ARCHIVE_ROOT, mode="preview")


def test_links_and_duplicate_paths_are_rejected(tmp_path: Path) -> None:
    name = ARCHIVE_ROOT + "/README.md"
    for members in [[(name, "/etc/passwd")], [(name, b"first"), (name, b"second")]]:
        archive = archive_with(tmp_path, members)
        with pytest.raises(AUDIT.ArtifactAuditError, match=r"links|duplicate"):
            AUDIT.audit_archive(archive, expected_root=ARCHIVE_ROOT, mode="preview")


def test_archive_inspection_is_size_bounded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive = archive_with(tmp_path, [(ARCHIVE_ROOT + "/README.md", b"12345")])
    monkeypatch.setattr(AUDIT, "MAX_MEMBER_BYTES", 4)
    with pytest.raises(AUDIT.ArtifactAuditError, match="size limit"):
        AUDIT.audit_archive(archive, expected_root=ARCHIVE_ROOT, mode="preview")


def build_fixture(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    project.mkdir()
    # Exercise the actual shell allowlist and required-member contract without
    # copying local data, runtime records, browser binaries or credentials.
    sources = {
        name: (ROOT / "scripts" / name).read_text()
        for name in ["build_artifact_bundle.sh", "verify_artifact_bundle.sh"]
    }
    for name, variable in [
        ("build_artifact_bundle.sh", "bundle_members"),
        ("verify_artifact_bundle.sh", "required_members"),
    ]:
        block = re.search(rf"{variable}=\(\n(.*?)\n\)", sources[name], re.DOTALL)
        assert block is not None
        for member in block[1].split():
            target = project / member
            if (ROOT / member).is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("fixture\n")
    (project / "backend/pyproject.toml").write_text('version = "0.4.0"\n')
    for name in [*sources, "audit_artifact_archive.py"]:
        shutil.copy2(ROOT / "scripts" / name, project / "scripts" / name)
    return project


def build(project: Path, *, public: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "bash",
            str(project / "scripts/build_artifact_bundle.sh"),
            "--public" if public else "--preview",
        ],
        env={**os.environ, "ASKDU_ARTIFACT_OUTPUT_DIR": str(project / "artifacts/release")},
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )


def test_builder_excludes_private_state_and_reproduces_its_own_preview(tmp_path: Path) -> None:
    project = build_fixture(tmp_path)
    for relative in [
        ".env",
        "backend/.env",
        "runtime/run.json",
        "data/external/source.csv",
        "data/pilots/heldout-v1-questions.json",
        "data/manifests/coda-community-45-extracted.sha256",
    ]:
        target = project / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("API_KEY=" + "s" * 32)
    result = build(project)
    assert result.returncode == 0, result.stdout + result.stderr
    archive = project / "artifacts/release/ask-dont-upload-artifact-v0.4.0-preview.tar.gz"
    with tarfile.open(archive) as bundle:
        assert ARCHIVE_ROOT + "/.env.example" in bundle.getnames()
        assert all(not name.endswith("/.env") for name in bundle.getnames())
    result = subprocess.run(
        ["bash", str(project / "scripts/verify_artifact_bundle.sh"), str(archive)],
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "byte-for-byte" in result.stdout


def test_builder_scans_hidden_gitignored_members_and_preserves_prior_bundle(tmp_path: Path) -> None:
    project = build_fixture(tmp_path)
    assert build(project).returncode == 0
    archive = project / "artifacts/release/ask-dont-upload-artifact-v0.4.0-preview.tar.gz"
    previous = archive.read_bytes()
    checksum = archive.with_suffix(archive.suffix + ".sha256").read_bytes()
    (project / ".gitignore").write_text("docs/.private-note\n")
    (project / "docs/.private-note").write_text("API_KEY=" + "s" * 32)
    result = build(project)
    assert result.returncode != 0
    assert "credential-shaped" in result.stdout
    assert "s" * 32 not in result.stdout + result.stderr
    assert archive.read_bytes() == previous
    assert archive.with_suffix(archive.suffix + ".sha256").read_bytes() == checksum


def test_public_builder_retains_license_and_provider_gates(tmp_path: Path) -> None:
    project = build_fixture(tmp_path)
    result = build(project, public=True)
    assert result.returncode != 0
    assert "license" in result.stderr
    (project / "LICENSE").write_text("Synthetic fixture license; not a project license choice.\n")
    (project / ".env.example").write_text("ASKDU_LLM_BASE_URL=" + AUDIT.PREVIEW_PROVIDER)
    result = build(project, public=True)
    assert result.returncode != 0
    assert "provider configuration" in result.stdout
    assert build(project).returncode == 0


def test_builder_fails_closed_when_auditor_cannot_run(tmp_path: Path) -> None:
    project = build_fixture(tmp_path)
    (project / "scripts/audit_artifact_archive.py").write_text("raise SystemExit(2)\n")
    assert build(project).returncode != 0
    assert not list((project / "artifacts/release").glob("*.tar.gz"))


def test_verifier_requires_stage_code_and_root_environment_example(tmp_path: Path) -> None:
    project = build_fixture(tmp_path)
    (project / "backend/src/askdu/application/report_writer.py").unlink()
    assert build(project).returncode == 0
    archive = project / "artifacts/release/ask-dont-upload-artifact-v0.4.0-preview.tar.gz"
    result = subprocess.run(
        ["bash", str(project / "scripts/verify_artifact_bundle.sh"), str(archive)],
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )
    assert result.returncode != 0
    assert (
        "missing required member: backend/src/askdu/application/report_writer.py" in result.stderr
    )


def test_verifier_rejects_checksum_for_an_unrelated_file(tmp_path: Path) -> None:
    project = build_fixture(tmp_path)
    assert build(project).returncode == 0
    archive = project / "artifacts/release/ask-dont-upload-artifact-v0.4.0-preview.tar.gz"
    archive.with_suffix(archive.suffix + ".sha256").write_text("a" * 64 + "  unrelated-file\n")
    result = subprocess.run(
        ["bash", str(project / "scripts/verify_artifact_bundle.sh"), str(archive)],
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )
    assert result.returncode != 0
    assert "checksum must name this archive" in result.stderr


def test_public_bundle_with_synthetic_license_and_example_provider_rebuilds(tmp_path: Path) -> None:
    project = build_fixture(tmp_path)
    (project / "LICENSE").write_text("Synthetic fixture license; not a project license choice.\n")
    (project / ".env.example").write_text("ASKDU_LLM_BASE_URL=" + "https://provider.example/v1")
    result = build(project, public=True)
    assert result.returncode == 0, result.stdout + result.stderr
    archive = project / "artifacts/release/ask-dont-upload-artifact-v0.4.0-release.tar.gz"
    result = subprocess.run(
        ["bash", str(project / "scripts/verify_artifact_bundle.sh"), str(archive)],
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
