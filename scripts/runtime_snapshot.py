from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import os
import re
import shutil
import stat
import sys
import tarfile
import tempfile
import uuid
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, BinaryIO

FORMAT_VERSION = "askdu-runtime-snapshot-v1"
ARCHIVE_ROOT = "askdu-runtime"
PAYLOAD_ROOT = f"{ARCHIVE_ROOT}/payload"
MANIFEST_MEMBER = f"{ARCHIVE_ROOT}/manifest.json"
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
MAX_FILES = 100_000
MAX_MANIFEST_BYTES = 16 * 1024 * 1024
MAX_TOTAL_BYTES = 100 * 1024 * 1024 * 1024
MAX_ARCHIVE_BYTES = MAX_TOTAL_BYTES + MAX_MANIFEST_BYTES + 1024 * 1024


@dataclass(frozen=True)
class SnapshotFile:
    path: str
    size: int
    sha256: str

    def as_json(self) -> dict[str, str | int]:
        return {"path": self.path, "sha256": self.sha256, "size": self.size}


@dataclass(frozen=True)
class SnapshotManifest:
    directories: tuple[str, ...]
    files: tuple[SnapshotFile, ...]

    @property
    def total_bytes(self) -> int:
        return sum(item.size for item in self.files)

    def as_json(self) -> dict[str, Any]:
        return {
            "directories": list(self.directories),
            "file_count": len(self.files),
            "files": [item.as_json() for item in self.files],
            "format": FORMAT_VERSION,
            "total_bytes": self.total_bytes,
        }


class SnapshotError(ValueError):
    pass


def _canonical_json(value: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def _validate_relative_path(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise SnapshotError(f"{label} must be a non-empty string")
    if "\\" in value or any(ord(character) < 32 for character in value):
        raise SnapshotError(f"{label} contains an unsafe character")
    path = PurePosixPath(value)
    if path.is_absolute() or value != path.as_posix():
        raise SnapshotError(f"{label} must be a canonical relative POSIX path")
    if any(part in {"", ".", ".."} for part in path.parts):
        raise SnapshotError(f"{label} contains an unsafe path component")
    if path.parts[0].startswith(".askdu-restore-"):
        raise SnapshotError(f"{label} uses a reserved restore path")
    return value


def _safe_open(path: Path) -> BinaryIO:
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags)
    handle = os.fdopen(descriptor, "rb")
    if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
        handle.close()
        raise SnapshotError(f"runtime member is not a regular file: {path.name}")
    return handle


def _digest_file(path: Path) -> tuple[int, str]:
    digest = hashlib.sha256()
    with _safe_open(path) as handle:
        before = os.fstat(handle.fileno())
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
        after = os.fstat(handle.fileno())
    if (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
    ) != (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    ):
        raise SnapshotError(f"runtime file changed while hashing: {path.name}")
    return before.st_size, digest.hexdigest()


def _read_chunks(handle: BinaryIO) -> Iterator[bytes]:
    while True:
        chunk = handle.read(1024 * 1024)
        if not chunk:
            return
        yield chunk


def census_runtime(source: Path) -> SnapshotManifest:
    source = source.expanduser()
    if source.is_symlink():
        raise SnapshotError("runtime source must not be a symbolic link")
    source = source.resolve(strict=True)
    source_status = source.lstat()
    if source.is_symlink() or not stat.S_ISDIR(source_status.st_mode):
        raise SnapshotError("runtime source must be a real directory")

    directories: list[str] = []
    files: list[SnapshotFile] = []
    for current, directory_names, file_names in os.walk(source, followlinks=False):
        directory_names.sort()
        file_names.sort()
        current_path = Path(current)

        for directory_name in directory_names:
            directory = current_path / directory_name
            status = directory.lstat()
            if directory.is_symlink() or not stat.S_ISDIR(status.st_mode):
                raise SnapshotError(
                    f"runtime directory entry is not a real directory: {directory_name}"
                )
            relative = directory.relative_to(source).as_posix()
            directories.append(_validate_relative_path(relative, "directory path"))

        for file_name in file_names:
            path = current_path / file_name
            status = path.lstat()
            if path.is_symlink() or not stat.S_ISREG(status.st_mode):
                raise SnapshotError(f"runtime entry is not a regular file: {file_name}")
            relative = _validate_relative_path(
                path.relative_to(source).as_posix(), "file path"
            )
            size, digest = _digest_file(path)
            files.append(SnapshotFile(relative, size, digest))
            if len(files) > MAX_FILES:
                raise SnapshotError(f"runtime snapshot exceeds {MAX_FILES} files")

    directories.sort()
    files.sort(key=lambda item: item.path)
    manifest = SnapshotManifest(tuple(directories), tuple(files))
    if manifest.total_bytes > MAX_TOTAL_BYTES:
        raise SnapshotError("runtime snapshot exceeds the maximum total byte budget")
    return manifest


def _tar_info(name: str, *, is_directory: bool, size: int = 0) -> tarfile.TarInfo:
    info = tarfile.TarInfo(name)
    info.mtime = 0
    info.uid = 0
    info.gid = 0
    info.uname = ""
    info.gname = ""
    info.mode = 0o750 if is_directory else 0o640
    info.type = tarfile.DIRTYPE if is_directory else tarfile.REGTYPE
    info.size = 0 if is_directory else size
    return info


class _DigestingReader:
    def __init__(self, handle: BinaryIO) -> None:
        self.handle = handle
        self.digest = hashlib.sha256()
        self.bytes_read = 0

    def read(self, size: int = -1) -> bytes:
        data = self.handle.read(size)
        self.digest.update(data)
        self.bytes_read += len(data)
        return data


def _write_archive(stream: BinaryIO, source: Path, manifest: SnapshotManifest) -> None:
    with (
        gzip.GzipFile(
            filename="", mode="wb", compresslevel=9, fileobj=stream, mtime=0
        ) as compressed,
        tarfile.open(
            fileobj=compressed, mode="w|", format=tarfile.PAX_FORMAT
        ) as archive,
    ):
        archive.addfile(_tar_info(ARCHIVE_ROOT, is_directory=True))
        archive.addfile(_tar_info(PAYLOAD_ROOT, is_directory=True))
        for relative in manifest.directories:
            archive.addfile(_tar_info(f"{PAYLOAD_ROOT}/{relative}", is_directory=True))
        for record in manifest.files:
            path = source / PurePosixPath(record.path)
            with _safe_open(path) as handle:
                status = os.fstat(handle.fileno())
                if status.st_size != record.size:
                    raise SnapshotError(
                        f"runtime file size changed before archiving: {record.path}"
                    )
                reader = _DigestingReader(handle)
                archive.addfile(
                    _tar_info(
                        f"{PAYLOAD_ROOT}/{record.path}",
                        is_directory=False,
                        size=record.size,
                    ),
                    reader,
                )
                if handle.read(1):
                    raise SnapshotError(
                        f"runtime file grew while archiving: {record.path}"
                    )
                if (
                    reader.bytes_read != record.size
                    or reader.digest.hexdigest() != record.sha256
                ):
                    raise SnapshotError(
                        f"runtime file changed while archiving: {record.path}"
                    )
        manifest_bytes = _canonical_json(manifest.as_json())
        archive.addfile(
            _tar_info(
                MANIFEST_MEMBER,
                is_directory=False,
                size=len(manifest_bytes),
            ),
            io.BytesIO(manifest_bytes),
        )


def create_snapshot(source: Path, output: str | Path) -> SnapshotManifest:
    source = source.expanduser()
    if source.is_symlink():
        raise SnapshotError("runtime source must not be a symbolic link")
    source = source.resolve(strict=True)
    manifest = census_runtime(source)
    if str(output) == "-":
        _write_archive(sys.stdout.buffer, source, manifest)
        return manifest

    output_path = Path(output).expanduser().resolve()
    try:
        output_path.relative_to(source)
    except ValueError:
        pass
    else:
        raise SnapshotError("snapshot output must be outside the runtime source")
    output_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if output_path.exists() or output_path.is_symlink():
        raise SnapshotError("snapshot output already exists")

    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{output_path.name}.", suffix=".tmp", dir=output_path.parent
    )
    temporary = Path(temporary_name)
    os.chmod(temporary, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            _write_archive(stream, source, manifest)
            stream.flush()
            os.fsync(stream.fileno())
        verify_snapshot(temporary)
        os.link(temporary, output_path)
        temporary.unlink()
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return manifest


def stage_snapshot(
    stream: BinaryIO, output: Path, *, expected_sha256: str
) -> SnapshotManifest:
    if SHA256_PATTERN.fullmatch(expected_sha256) is None:
        raise SnapshotError("expected SHA-256 must be lowercase hexadecimal")
    output = output.expanduser().resolve()
    if output.exists() or output.is_symlink():
        raise SnapshotError("staged snapshot output already exists")
    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{output.name}.", suffix=".tmp", dir=output.parent
    )
    temporary = Path(temporary_name)
    os.chmod(temporary, 0o600)
    digest = hashlib.sha256()
    bytes_written = 0
    try:
        with os.fdopen(descriptor, "wb") as handle:
            for chunk in _read_chunks(stream):
                bytes_written += len(chunk)
                if bytes_written > MAX_ARCHIVE_BYTES:
                    raise SnapshotError(
                        "snapshot archive exceeds the staging byte budget"
                    )
                handle.write(chunk)
                digest.update(chunk)
            handle.flush()
            os.fsync(handle.fileno())
        if digest.hexdigest() != expected_sha256:
            raise SnapshotError("staged snapshot SHA-256 does not match")
        manifest = verify_snapshot(temporary)
        os.link(temporary, output)
        temporary.unlink()
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return manifest


def _parse_manifest(raw: bytes) -> SnapshotManifest:
    if len(raw) > MAX_MANIFEST_BYTES:
        raise SnapshotError("snapshot manifest is too large")
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SnapshotError("snapshot manifest is not valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise SnapshotError("snapshot manifest must be an object")
    expected_keys = {"directories", "file_count", "files", "format", "total_bytes"}
    if set(value) != expected_keys:
        raise SnapshotError("snapshot manifest keys are invalid")
    if value["format"] != FORMAT_VERSION:
        raise SnapshotError("snapshot format version is unsupported")

    raw_directories = value["directories"]
    raw_files = value["files"]
    if not isinstance(raw_directories, list) or not isinstance(raw_files, list):
        raise SnapshotError("snapshot directories and files must be arrays")
    if len(raw_files) > MAX_FILES:
        raise SnapshotError(f"snapshot exceeds {MAX_FILES} files")

    directories = tuple(
        _validate_relative_path(item, "manifest directory") for item in raw_directories
    )
    if list(directories) != sorted(set(directories)):
        raise SnapshotError("snapshot directories must be unique and sorted")

    files: list[SnapshotFile] = []
    for item in raw_files:
        if not isinstance(item, dict) or set(item) != {"path", "sha256", "size"}:
            raise SnapshotError("snapshot file record is invalid")
        path = _validate_relative_path(item["path"], "manifest file")
        size = item["size"]
        digest = item["sha256"]
        if not isinstance(size, int) or isinstance(size, bool) or size < 0:
            raise SnapshotError(f"snapshot file size is invalid: {path}")
        if not isinstance(digest, str) or SHA256_PATTERN.fullmatch(digest) is None:
            raise SnapshotError(f"snapshot file digest is invalid: {path}")
        files.append(SnapshotFile(path, size, digest))
    if [item.path for item in files] != sorted({item.path for item in files}):
        raise SnapshotError("snapshot files must be unique and sorted")

    manifest = SnapshotManifest(directories, tuple(files))
    if (
        not isinstance(value["file_count"], int)
        or isinstance(value["file_count"], bool)
        or value["file_count"] != len(files)
    ):
        raise SnapshotError("snapshot file count disagrees with its manifest")
    if (
        not isinstance(value["total_bytes"], int)
        or isinstance(value["total_bytes"], bool)
        or value["total_bytes"] != manifest.total_bytes
    ):
        raise SnapshotError("snapshot byte count disagrees with its manifest")
    if manifest.total_bytes > MAX_TOTAL_BYTES:
        raise SnapshotError("snapshot exceeds the maximum total byte budget")

    directory_set = set(directories)
    file_set = {item.path for item in files}
    if directory_set & file_set:
        raise SnapshotError("snapshot path is both a file and a directory")
    for directory in directories:
        for parent in PurePosixPath(directory).parents:
            if str(parent) == ".":
                continue
            if parent.as_posix() not in directory_set:
                raise SnapshotError(f"snapshot directory parent is absent: {directory}")
            if parent.as_posix() in file_set:
                raise SnapshotError(
                    f"snapshot file is also a directory parent: {directory}"
                )
    for record in files:
        parents = PurePosixPath(record.path).parents
        for parent in parents:
            if str(parent) == ".":
                continue
            if parent.as_posix() in file_set:
                raise SnapshotError(
                    f"snapshot file is also a path parent: {record.path}"
                )
            if parent.as_posix() not in directory_set:
                raise SnapshotError(
                    f"snapshot file parent is absent from directory census: {record.path}"
                )
    return manifest


def _validate_archive_members(
    archive: tarfile.TarFile,
) -> tuple[SnapshotManifest, dict[str, tarfile.TarInfo]]:
    members: dict[str, tarfile.TarInfo] = {}
    for member in archive.getmembers():
        if member.name in members:
            raise SnapshotError(f"duplicate archive member: {member.name}")
        path = PurePosixPath(member.name)
        if (
            path.is_absolute()
            or member.name != path.as_posix()
            or any(part in {"", ".", ".."} for part in path.parts)
        ):
            raise SnapshotError(f"unsafe archive member path: {member.name}")
        if not (member.isdir() or member.isreg()):
            raise SnapshotError(f"unsupported archive member type: {member.name}")
        members[member.name] = member

    manifest_member = members.get(MANIFEST_MEMBER)
    if manifest_member is None or not manifest_member.isreg():
        raise SnapshotError("snapshot manifest member is missing")
    if manifest_member.size > MAX_MANIFEST_BYTES:
        raise SnapshotError("snapshot manifest is too large")
    manifest_handle = archive.extractfile(manifest_member)
    if manifest_handle is None:
        raise SnapshotError("snapshot manifest cannot be read")
    with manifest_handle:
        manifest = _parse_manifest(manifest_handle.read(MAX_MANIFEST_BYTES + 1))

    expected_directories = {ARCHIVE_ROOT, PAYLOAD_ROOT} | {
        f"{PAYLOAD_ROOT}/{path}" for path in manifest.directories
    }
    expected_files = {MANIFEST_MEMBER} | {
        f"{PAYLOAD_ROOT}/{item.path}" for item in manifest.files
    }
    if set(members) != expected_directories | expected_files:
        raise SnapshotError("archive member census disagrees with its manifest")
    if any(not members[name].isdir() for name in expected_directories):
        raise SnapshotError("archive directory member has the wrong type")
    if any(not members[name].isreg() for name in expected_files):
        raise SnapshotError("archive file member has the wrong type")
    return manifest, members


def verify_snapshot(archive_path: Path) -> SnapshotManifest:
    archive_path = archive_path.expanduser()
    if archive_path.is_symlink():
        raise SnapshotError("snapshot archive must not be a symbolic link")
    archive_path = archive_path.resolve(strict=True)
    if not archive_path.is_file():
        raise SnapshotError("snapshot archive must be a regular file")
    try:
        with tarfile.open(archive_path, mode="r:gz") as archive:
            manifest, members = _validate_archive_members(archive)
            for record in manifest.files:
                member = members[f"{PAYLOAD_ROOT}/{record.path}"]
                if member.size != record.size:
                    raise SnapshotError(
                        f"archive size disagrees for runtime file: {record.path}"
                    )
                handle = archive.extractfile(member)
                if handle is None:
                    raise SnapshotError(f"runtime file cannot be read: {record.path}")
                digest = hashlib.sha256()
                bytes_read = 0
                with handle:
                    for chunk in _read_chunks(handle):
                        bytes_read += len(chunk)
                        digest.update(chunk)
                if bytes_read != record.size or digest.hexdigest() != record.sha256:
                    raise SnapshotError(f"runtime file digest mismatch: {record.path}")
    except (tarfile.TarError, EOFError, OSError) as exc:
        raise SnapshotError("snapshot archive is corrupt or unreadable") from exc
    return manifest


def _remove_created_path(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink(missing_ok=True)
    elif path.is_dir():
        shutil.rmtree(path)


def restore_snapshot(
    archive_path: Path, target: Path, *, confirm_empty_target: bool
) -> SnapshotManifest:
    if not confirm_empty_target:
        raise SnapshotError("restore requires --confirm-empty-target")
    archive_path = archive_path.expanduser()
    if archive_path.is_symlink():
        raise SnapshotError("snapshot archive must not be a symbolic link")
    archive_path = archive_path.resolve(strict=True)
    manifest = verify_snapshot(archive_path)
    target = target.expanduser()
    if target.is_symlink():
        raise SnapshotError("restore target must not be a symbolic link")
    target = target.resolve(strict=True)
    target_status = target.lstat()
    if target.is_symlink() or not stat.S_ISDIR(target_status.st_mode):
        raise SnapshotError("restore target must be a real directory")
    if any(target.iterdir()):
        raise SnapshotError("restore target must be completely empty")

    staging = target / f".askdu-restore-{uuid.uuid4().hex}"
    staging.mkdir(mode=0o700)
    promoted: list[Path] = []
    try:
        for relative in sorted(
            manifest.directories,
            key=lambda value: (len(PurePosixPath(value).parts), value),
        ):
            (staging / PurePosixPath(relative)).mkdir(mode=0o750, parents=True)

        with tarfile.open(archive_path, mode="r:gz") as archive:
            _, members = _validate_archive_members(archive)
            for record in manifest.files:
                destination = staging / PurePosixPath(record.path)
                destination.parent.mkdir(mode=0o750, parents=True, exist_ok=True)
                source = archive.extractfile(members[f"{PAYLOAD_ROOT}/{record.path}"])
                if source is None:
                    raise SnapshotError(f"runtime file cannot be read: {record.path}")
                digest = hashlib.sha256()
                bytes_written = 0
                with source, destination.open("xb") as output:
                    for chunk in _read_chunks(source):
                        output.write(chunk)
                        digest.update(chunk)
                        bytes_written += len(chunk)
                    output.flush()
                    os.fsync(output.fileno())
                os.chmod(destination, 0o640)
                if bytes_written != record.size or digest.hexdigest() != record.sha256:
                    raise SnapshotError(
                        f"restored runtime file digest mismatch: {record.path}"
                    )

        for child in sorted(staging.iterdir(), key=lambda item: item.name):
            destination = target / child.name
            if destination.exists() or destination.is_symlink():
                raise SnapshotError(f"restore destination appeared: {child.name}")
            child.rename(destination)
            promoted.append(destination)
        staging.rmdir()
    except BaseException:
        for path in reversed(promoted):
            _remove_created_path(path)
        if staging.exists():
            shutil.rmtree(staging)
        raise
    return manifest


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create, verify, or safely restore an Ask, Don't Upload runtime snapshot."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    create = subparsers.add_parser("create")
    create.add_argument("--source", type=Path, required=True)
    create.add_argument("--output", required=True)

    verify = subparsers.add_parser("verify")
    verify.add_argument("--archive", type=Path, required=True)

    stage = subparsers.add_parser("stage")
    stage.add_argument("--output", type=Path, required=True)
    stage.add_argument("--expected-sha256", required=True)

    restore = subparsers.add_parser("restore")
    restore.add_argument("--archive", type=Path, required=True)
    restore.add_argument("--target", type=Path, required=True)
    restore.add_argument("--confirm-empty-target", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    args = _parser().parse_args(argv)
    if args.command == "create":
        manifest = create_snapshot(args.source, args.output)
        destination = "stdout" if args.output == "-" else args.output
        print(
            f"PASS: wrote {len(manifest.files)} files "
            f"({manifest.total_bytes} bytes) to {destination}.",
            file=sys.stderr,
        )
    elif args.command == "verify":
        manifest = verify_snapshot(args.archive)
        print(
            f"PASS: verified {len(manifest.files)} files "
            f"({manifest.total_bytes} bytes) in {args.archive}."
        )
    elif args.command == "stage":
        manifest = stage_snapshot(
            sys.stdin.buffer,
            args.output,
            expected_sha256=args.expected_sha256,
        )
        print(
            f"PASS: securely staged {len(manifest.files)} files "
            f"({manifest.total_bytes} bytes)."
        )
    else:
        manifest = restore_snapshot(
            args.archive,
            args.target,
            confirm_empty_target=args.confirm_empty_target,
        )
        print(
            f"PASS: restored {len(manifest.files)} files "
            f"({manifest.total_bytes} bytes) into an empty target."
        )


if __name__ == "__main__":
    try:
        main()
    except (OSError, SnapshotError) as exc:
        print(f"ERROR: runtime snapshot operation failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from None
