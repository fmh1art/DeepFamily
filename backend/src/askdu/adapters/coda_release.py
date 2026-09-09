from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class CodaReleaseError(ValueError):
    """Raised when the pinned CoDA release or a local installation is inconsistent."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class FilePin:
    path: str
    bytes: int
    sha256: str


@dataclass(frozen=True)
class CommunityPin(FilePin):
    community_id: int

    @property
    def environment_id(self) -> str:
        return f"coda-community-{self.community_id}"


@dataclass(frozen=True)
class ReleaseScope:
    task_count: int
    community_count: int
    source_dataset_count: int
    compressed_archive_bytes: int | None = None
    compressed_storage_bytes: int | None = None


@dataclass(frozen=True)
class CodaReleaseManifest:
    repository: str
    repository_type: str
    revision: str
    metadata: tuple[FilePin, ...]
    archives: tuple[CommunityPin, ...]
    published: ReleaseScope
    open_runtime: ReleaseScope
    sealed_community_count: int

    @classmethod
    def from_file(cls, path: Path) -> CodaReleaseManifest:
        try:
            payload: object = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise CodaReleaseError(f"Could not read CoDA release manifest: {path}") from exc
        if not isinstance(payload, dict):
            raise CodaReleaseError("CoDA release manifest must be a JSON object")
        if payload.get("schema_version") != "askdu-coda-release-v1":
            raise CodaReleaseError("Unsupported CoDA release manifest schema")

        benchmark = _mapping(payload.get("benchmark"), "benchmark")
        if benchmark.get("name") != "CoDA-Bench":
            raise CodaReleaseError("Unexpected benchmark identity")
        repository = _nonempty_string(benchmark.get("repository"), "benchmark.repository")
        repository_type = _nonempty_string(
            benchmark.get("repository_type"), "benchmark.repository_type"
        )
        revision = _sha(benchmark.get("revision"), "benchmark.revision", length=40)
        metadata = tuple(
            _file_pin(item, f"benchmark.metadata[{index}]")
            for index, item in enumerate(_list(benchmark.get("metadata"), "benchmark.metadata"))
        )

        published = _scope(payload.get("published_release"), "published_release")
        open_runtime = _scope(payload.get("open_runtime_scope"), "open_runtime_scope")
        sealed = _mapping(payload.get("sealed_evaluation_scope"), "sealed_evaluation_scope")
        sealed_count = _positive_int(
            sealed.get("community_count"), "sealed_evaluation_scope.community_count"
        )
        if sealed.get("policy") != "excluded_from_development_index_and_open_runtime":
            raise CodaReleaseError("The sealed evaluation policy is not enforced")

        archives: list[CommunityPin] = []
        for index, raw in enumerate(_list(payload.get("archives"), "archives")):
            label = f"archives[{index}]"
            item = _mapping(raw, label)
            file_pin = _file_pin(item, label)
            community_id = _positive_int(item.get("community_id"), f"{label}.community_id")
            expected_path = f"archives/community_{community_id}.tar.zst"
            if file_pin.path != expected_path:
                raise CodaReleaseError(f"{label}.path does not match its community ID")
            archives.append(
                CommunityPin(
                    community_id=community_id,
                    path=file_pin.path,
                    bytes=file_pin.bytes,
                    sha256=file_pin.sha256,
                )
            )

        ids = [item.community_id for item in archives]
        if ids != sorted(ids) or len(ids) != len(set(ids)):
            raise CodaReleaseError("Open community IDs must be unique and sorted")
        if open_runtime.community_count != len(archives):
            raise CodaReleaseError("Open community count differs from archive pins")
        if open_runtime.compressed_archive_bytes != sum(item.bytes for item in archives):
            raise CodaReleaseError("Open compressed byte total differs from archive pins")
        if published.community_count != open_runtime.community_count + sealed_count:
            raise CodaReleaseError("Published/open/sealed community counts are inconsistent")

        return cls(
            repository=repository,
            repository_type=repository_type,
            revision=revision,
            metadata=metadata,
            archives=tuple(archives),
            published=published,
            open_runtime=open_runtime,
            sealed_community_count=sealed_count,
        )

    def community(self, community_id: int) -> CommunityPin:
        match = next(
            (item for item in self.archives if item.community_id == community_id),
            None,
        )
        if match is None:
            raise CodaReleaseError(f"Community {community_id} is outside the open runtime manifest")
        return match


@dataclass(frozen=True)
class CommunityInstallation:
    community_id: int
    archive_downloaded: bool
    archive_verified: bool
    extracted: bool
    data_root: Path | None


class CodaReleaseRegistry:
    """Read the immutable open-release pins without entering a sealed environment."""

    def __init__(self, *, manifest_path: Path, release_root: Path) -> None:
        self.manifest_path = manifest_path.expanduser().resolve()
        self.release_root = release_root.expanduser().resolve()
        self.manifest = CodaReleaseManifest.from_file(self.manifest_path)

    def installation(
        self,
        community_id: int,
        *,
        verify_archive: bool = False,
    ) -> CommunityInstallation:
        pin = self.manifest.community(community_id)
        archive = self.release_root / pin.path
        extracted = self.release_root / "communities" / f"community_{community_id}"
        data_root = extracted / "full_community"
        archive_downloaded = archive.is_file() and archive.stat().st_size == pin.bytes
        archive_verified = archive_downloaded and (
            not verify_archive or sha256_file(archive) == pin.sha256
        )
        return CommunityInstallation(
            community_id=community_id,
            archive_downloaded=archive_downloaded,
            archive_verified=archive_verified,
            extracted=data_root.is_dir(),
            data_root=data_root if data_root.is_dir() else None,
        )

    def installations(self, *, verify_archives: bool = False) -> tuple[CommunityInstallation, ...]:
        return tuple(
            self.installation(item.community_id, verify_archive=verify_archives)
            for item in self.manifest.archives
        )

    def require_data_root(self, community_id: int) -> Path:
        installation = self.installation(community_id)
        if installation.data_root is None:
            raise CodaReleaseError(f"Open community {community_id} is not extracted")
        return installation.data_root


def _mapping(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise CodaReleaseError(f"{label} must be a JSON object")
    return value


def _list(value: object, label: str) -> list[object]:
    if not isinstance(value, list) or not value:
        raise CodaReleaseError(f"{label} must be a non-empty JSON array")
    return value


def _nonempty_string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise CodaReleaseError(f"{label} must be a non-empty string")
    return value


def _positive_int(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise CodaReleaseError(f"{label} must be a positive integer")
    return value


def _sha(value: object, label: str, *, length: int = 64) -> str:
    rendered = _nonempty_string(value, label)
    invalid_character = any(character not in "0123456789abcdef" for character in rendered)
    if len(rendered) != length or invalid_character:
        raise CodaReleaseError(f"{label} must be a lowercase hexadecimal digest")
    return rendered


def _file_pin(value: object, label: str) -> FilePin:
    item = _mapping(value, label)
    relative = _nonempty_string(item.get("path"), f"{label}.path")
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts or path.as_posix() != relative:
        raise CodaReleaseError(f"{label}.path must be canonical and relative")
    return FilePin(
        path=relative,
        bytes=_positive_int(item.get("bytes"), f"{label}.bytes"),
        sha256=_sha(item.get("sha256"), f"{label}.sha256"),
    )


def _scope(value: object, label: str) -> ReleaseScope:
    item = _mapping(value, label)
    compressed_archive_bytes = item.get("compressed_archive_bytes")
    compressed_storage_bytes = item.get("compressed_storage_bytes")
    return ReleaseScope(
        task_count=_positive_int(item.get("task_count"), f"{label}.task_count"),
        community_count=_positive_int(item.get("community_count"), f"{label}.community_count"),
        source_dataset_count=_positive_int(
            item.get("source_dataset_count"), f"{label}.source_dataset_count"
        ),
        compressed_archive_bytes=(
            _positive_int(compressed_archive_bytes, f"{label}.compressed_archive_bytes")
            if compressed_archive_bytes is not None
            else None
        ),
        compressed_storage_bytes=(
            _positive_int(compressed_storage_bytes, f"{label}.compressed_storage_bytes")
            if compressed_storage_bytes is not None
            else None
        ),
    )
