from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import sys
import tarfile
from pathlib import Path
from types import ModuleType

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _load_snapshot_module() -> ModuleType:
    path = PROJECT_ROOT / "scripts/runtime_snapshot.py"
    spec = importlib.util.spec_from_file_location("askdu_test_runtime_snapshot", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load runtime snapshot module")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


snapshot = _load_snapshot_module()


def _write_runtime(root: Path) -> None:
    (root / "runs" / "run_001" / "artifacts").mkdir(parents=True)
    (root / "runs" / "run_001" / "state.json").write_text(
        '{"status":"completed"}\n', encoding="utf-8"
    )
    (root / "runs" / "run_001" / "artifacts" / "answer.md").write_text(
        "# Verified answer\n\n42\n", encoding="utf-8"
    )
    (root / "empty-directory").mkdir()


def _tree(root: Path) -> tuple[list[str], dict[str, bytes]]:
    directories = sorted(
        path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_dir()
    )
    files = {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }
    return directories, files


def test_snapshot_is_deterministic_and_round_trips(tmp_path: Path) -> None:
    source = tmp_path / "runtime"
    source.mkdir()
    _write_runtime(source)
    first = tmp_path / "first.tar.gz"
    second = tmp_path / "second.tar.gz"

    created = snapshot.create_snapshot(source, first)
    snapshot.create_snapshot(source, second)

    assert first.read_bytes() == second.read_bytes()
    assert created == snapshot.verify_snapshot(first)
    assert created.total_bytes == sum(len(value) for value in _tree(source)[1].values())
    assert first.stat().st_mode & 0o777 == 0o600

    target = tmp_path / "restored"
    target.mkdir()
    restored = snapshot.restore_snapshot(first, target, confirm_empty_target=True)
    assert restored == created
    assert _tree(target) == _tree(source)


def test_snapshot_rejects_symlinked_runtime_member(tmp_path: Path) -> None:
    source = tmp_path / "runtime"
    source.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("not runtime data", encoding="utf-8")
    (source / "escape").symlink_to(outside)

    with pytest.raises(snapshot.SnapshotError, match="not a regular file"):
        snapshot.create_snapshot(source, tmp_path / "snapshot.tar.gz")


def test_snapshot_rejects_output_inside_runtime(tmp_path: Path) -> None:
    source = tmp_path / "runtime"
    source.mkdir()
    _write_runtime(source)

    with pytest.raises(snapshot.SnapshotError, match="outside the runtime source"):
        snapshot.create_snapshot(source, source / "snapshot.tar.gz")

    assert not (source / "snapshot.tar.gz").exists()


def test_snapshot_staging_requires_exact_digest_and_no_overwrite(
    tmp_path: Path,
) -> None:
    source = tmp_path / "runtime"
    source.mkdir()
    _write_runtime(source)
    archive = tmp_path / "snapshot.tar.gz"
    snapshot.create_snapshot(source, archive)
    payload = archive.read_bytes()
    expected = hashlib.sha256(payload).hexdigest()
    staged = tmp_path / "staging" / "runtime.tar.gz"

    manifest = snapshot.stage_snapshot(io.BytesIO(payload), staged, expected_sha256=expected)
    assert staged.read_bytes() == payload
    assert manifest == snapshot.verify_snapshot(archive)

    with pytest.raises(snapshot.SnapshotError, match="already exists"):
        snapshot.stage_snapshot(io.BytesIO(payload), staged, expected_sha256=expected)

    rejected = tmp_path / "rejected.tar.gz"
    with pytest.raises(snapshot.SnapshotError, match="does not match"):
        snapshot.stage_snapshot(io.BytesIO(payload), rejected, expected_sha256="0" * 64)
    assert not rejected.exists()


def test_restore_requires_an_empty_real_target(tmp_path: Path) -> None:
    source = tmp_path / "runtime"
    source.mkdir()
    _write_runtime(source)
    archive = tmp_path / "snapshot.tar.gz"
    snapshot.create_snapshot(source, archive)
    target = tmp_path / "target"
    target.mkdir()
    sentinel = target / "preserve.txt"
    sentinel.write_text("keep me", encoding="utf-8")

    with pytest.raises(snapshot.SnapshotError, match="completely empty"):
        snapshot.restore_snapshot(archive, target, confirm_empty_target=True)

    assert sentinel.read_text(encoding="utf-8") == "keep me"


def test_verify_rejects_payload_tampering(tmp_path: Path) -> None:
    source = tmp_path / "runtime"
    source.mkdir()
    _write_runtime(source)
    original = tmp_path / "original.tar.gz"
    tampered = tmp_path / "tampered.tar.gz"
    snapshot.create_snapshot(source, original)

    with tarfile.open(original, "r:gz") as archive:
        captured: list[tuple[tarfile.TarInfo, bytes | None]] = []
        for member in archive.getmembers():
            handle = archive.extractfile(member) if member.isreg() else None
            payload = handle.read() if handle is not None else None
            if member.name.endswith("answer.md") and payload is not None:
                payload = b"X" * len(payload)
            captured.append((member, payload))
    with tarfile.open(tampered, "w:gz") as archive:
        for member, payload in captured:
            archive.addfile(member, io.BytesIO(payload) if payload is not None else None)

    with pytest.raises(snapshot.SnapshotError, match="digest mismatch"):
        snapshot.verify_snapshot(tampered)


def test_verify_rejects_duplicate_archive_members(tmp_path: Path) -> None:
    archive_path = tmp_path / "duplicate.tar.gz"
    with tarfile.open(archive_path, "w:gz") as archive:
        for _ in range(2):
            member = tarfile.TarInfo(snapshot.ARCHIVE_ROOT)
            member.type = tarfile.DIRTYPE
            archive.addfile(member)

    with pytest.raises(snapshot.SnapshotError, match="duplicate archive member"):
        snapshot.verify_snapshot(archive_path)


def test_manifest_rejects_file_used_as_parent() -> None:
    payload = {
        "directories": ["run", "run/child"],
        "file_count": 1,
        "files": [
            {
                "path": "run",
                "sha256": hashlib.sha256(b"").hexdigest(),
                "size": 0,
            }
        ],
        "format": snapshot.FORMAT_VERSION,
        "total_bytes": 0,
    }

    with pytest.raises(snapshot.SnapshotError, match="both a file and a directory"):
        snapshot._parse_manifest(json.dumps(payload).encode())
