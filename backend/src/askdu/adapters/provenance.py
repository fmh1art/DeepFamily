from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path, PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator

from askdu.domain import CatalogProvenance, SourceProvenance


class ProvenanceManifestError(ValueError):
    """Raised when a configured provenance manifest is absent or inconsistent."""


class _ManifestModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class _BenchmarkEntry(_ManifestModel):
    name: str
    upstream_url: HttpUrl
    revision: str = Field(pattern=r"^[0-9a-f]{40}$")

    @field_validator("upstream_url")
    @classmethod
    def upstream_url_uses_https(cls, value: HttpUrl) -> HttpUrl:
        if value.scheme != "https":
            raise ValueError("benchmark upstream_url must use HTTPS")
        return value


class _SourceEntry(_ManifestModel):
    title: str
    provider: str
    creator: str
    source_url: HttpUrl
    license_label: str
    license_status: Literal["declared", "unknown"]
    license_url: HttpUrl | None

    @field_validator("source_url", "license_url")
    @classmethod
    def public_urls_use_https(cls, value: HttpUrl | None) -> HttpUrl | None:
        if value is not None and value.scheme != "https":
            raise ValueError("public provenance URLs must use HTTPS")
        return value


class _EnvironmentEntry(_ManifestModel):
    community_id: int = Field(gt=0)
    archive_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    archive_bytes: int = Field(gt=0)
    asset_manifest: str
    asset_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    csv_asset_count: int = Field(gt=0)
    source_count: int = Field(gt=0)
    sources: dict[str, _SourceEntry]

    @field_validator("asset_manifest")
    @classmethod
    def asset_manifest_is_safe_relative_path(cls, value: str) -> str:
        path = PurePosixPath(value)
        if path.is_absolute() or ".." in path.parts or path.parts[:2] != ("data", "manifests"):
            raise ValueError("asset_manifest must be a safe data/manifests path")
        return value

    @model_validator(mode="after")
    def source_count_matches_entries(self) -> _EnvironmentEntry:
        if self.source_count != len(self.sources):
            raise ValueError("source_count does not match the number of source entries")
        return self


class _ProvenanceManifest(_ManifestModel):
    schema_version: Literal["1.0"]
    audit_date: date
    benchmark: _BenchmarkEntry
    data_access_policy: Literal["download_only"]
    source_data_bundled: Literal[False]
    environments: dict[str, _EnvironmentEntry]

    @model_validator(mode="after")
    def environment_ids_match_communities(self) -> _ProvenanceManifest:
        for environment_id, environment in self.environments.items():
            if environment_id != f"coda-community-{environment.community_id}":
                raise ValueError("environment ID does not match its community_id")
            if any(not key or "/" in key or key in {".", ".."} for key in environment.sources):
                raise ValueError("source keys must be single safe path components")
        return self


class ProvenanceRegistry:
    """Immutable provenance lookup loaded from an audited, versioned manifest."""

    def __init__(
        self,
        manifest: _ProvenanceManifest,
        asset_hashes: dict[str, dict[str, str]],
    ):
        self._manifest = manifest
        self._asset_hashes = asset_hashes

    @classmethod
    def from_file(cls, path: Path) -> ProvenanceRegistry:
        resolved = path.expanduser().resolve()
        if not resolved.is_file():
            raise ProvenanceManifestError(f"Provenance manifest does not exist: {resolved}")
        try:
            payload = json.loads(resolved.read_text(encoding="utf-8"))
            manifest = _ProvenanceManifest.model_validate(payload)
            asset_hashes = {
                environment_id: cls._load_asset_hashes(resolved, environment)
                for environment_id, environment in manifest.environments.items()
            }
            cls._validate_source_coverage(manifest, asset_hashes)
        except (OSError, ValueError) as exc:
            raise ProvenanceManifestError("Provenance manifest is invalid") from exc
        return cls(manifest, asset_hashes)

    @staticmethod
    def _validate_source_coverage(
        manifest: _ProvenanceManifest,
        asset_hashes: dict[str, dict[str, str]],
    ) -> None:
        for environment_id, environment in manifest.environments.items():
            registered_sources = {
                PurePosixPath(relative_path).parts[0]
                for relative_path in asset_hashes[environment_id]
            }
            if registered_sources != set(environment.sources):
                raise ValueError("source entries must exactly cover the registered CSV datasets")

    @staticmethod
    def _load_asset_hashes(
        provenance_path: Path,
        environment: _EnvironmentEntry,
    ) -> dict[str, str]:
        checksum_path = provenance_path.parent / PurePosixPath(environment.asset_manifest).name
        payload = checksum_path.read_bytes()
        if hashlib.sha256(payload).hexdigest() != environment.asset_manifest_sha256:
            raise ValueError("asset manifest checksum does not match its provenance record")

        prefix = PurePosixPath(f"communities/community_{environment.community_id}/full_community")
        hashes: dict[str, str] = {}
        for line in payload.decode("utf-8").splitlines():
            if len(line) < 67 or line[64:66] != "  ":
                raise ValueError("asset manifest contains a malformed checksum line")
            digest, raw_path = line[:64], line[66:]
            path = PurePosixPath(raw_path)
            if (
                len(digest) != 64
                or any(character not in "0123456789abcdef" for character in digest)
                or path.is_absolute()
                or ".." in path.parts
                or path.suffix.lower() != ".csv"
                or path.parts[: len(prefix.parts)] != prefix.parts
            ):
                raise ValueError("asset manifest contains an unsafe or unexpected entry")
            relative_path = path.relative_to(prefix).as_posix()
            if relative_path in hashes:
                raise ValueError("asset manifest contains a duplicate path")
            hashes[relative_path] = digest
        if len(hashes) != environment.csv_asset_count:
            raise ValueError("csv_asset_count does not match the asset manifest")
        return hashes

    def catalog_for(self, environment_id: str) -> CatalogProvenance | None:
        environment = self._manifest.environments.get(environment_id)
        if environment is None:
            return None
        return CatalogProvenance(
            benchmark_name=self._manifest.benchmark.name,
            benchmark_url=str(self._manifest.benchmark.upstream_url),
            revision=self._manifest.benchmark.revision,
            community_id=environment.community_id,
            archive_sha256=environment.archive_sha256,
            archive_bytes=environment.archive_bytes,
            asset_manifest=environment.asset_manifest,
            asset_manifest_sha256=environment.asset_manifest_sha256,
            csv_asset_count=environment.csv_asset_count,
            audit_date=self._manifest.audit_date,
            data_access_policy=self._manifest.data_access_policy,
            source_data_bundled=self._manifest.source_data_bundled,
        )

    def expected_asset_sha256(self, environment_id: str, relative_path: str) -> str | None:
        return self._asset_hashes.get(environment_id, {}).get(relative_path)

    def registered_asset_paths(self, environment_id: str) -> frozenset[str]:
        return frozenset(self._asset_hashes.get(environment_id, {}))

    def source_for(self, environment_id: str, relative_path: str) -> SourceProvenance | None:
        environment = self._manifest.environments.get(environment_id)
        parts = PurePosixPath(relative_path).parts
        if (
            environment is None
            or not parts
            or relative_path not in self._asset_hashes.get(environment_id, {})
        ):
            return None
        dataset_key = parts[0]
        source = environment.sources.get(dataset_key)
        if source is None:
            return None
        return SourceProvenance(
            dataset_key=dataset_key,
            title=source.title,
            provider=source.provider,
            creator=source.creator,
            source_url=str(source.source_url),
            license_label=source.license_label,
            license_status=source.license_status,
            license_url=str(source.license_url) if source.license_url is not None else None,
            redistribution_policy=self._manifest.data_access_policy,
        )
