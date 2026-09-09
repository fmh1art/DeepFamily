from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from askdu.adapters.catalog import CatalogIntegrityError, FileCatalog
from askdu.adapters.provenance import ProvenanceManifestError, ProvenanceRegistry
from tests.conftest import write_test_provenance_manifest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROVENANCE_MANIFEST = PROJECT_ROOT / "data/manifests/coda-public-source-provenance-v1.json"


def test_catalog_attaches_audited_provenance_to_known_sources(
    sample_environment: Path,
    tmp_path: Path,
) -> None:
    manifest_path = write_test_provenance_manifest(
        sample_environment,
        tmp_path,
        tamper_relative_path=(
            "data_science_for_good/source/D5 SHSAT Registrations and Testers.csv"
        ),
    )
    unregistered = sample_environment / "data_science_for_good/source/rogue.csv"
    unregistered.write_text("column\nvalue\n", encoding="utf-8")
    registry = ProvenanceRegistry.from_file(manifest_path)
    catalog = FileCatalog(
        sample_environment,
        environment_id="coda-community-43",
        provenance_registry=registry,
    )

    assets = catalog.index().values()
    assert all(asset.name != "rogue.csv" for asset in assets)
    registration = next(
        asset for asset in assets if asset.name == "D5 SHSAT Registrations and Testers.csv"
    )
    provenance = registration.provenance

    assert provenance is not None
    assert provenance.dataset_key == "data_science_for_good"
    assert provenance.title == "Data Science for Good: PASSNYC"
    assert provenance.provider == "Kaggle"
    assert provenance.license_label == "CC0-1.0"
    assert provenance.redistribution_policy == "download_only"
    assert provenance.source_url.startswith("https://")
    assert registration.integrity_status == "unverified"
    assert registration.expected_sha256 == "0" * 64

    with pytest.raises(CatalogIntegrityError, match="differs from the pinned manifest"):
        catalog.profile(registration.asset_id)

    with pytest.raises(ValidationError):
        provenance.title = "Invented title"  # type: ignore[misc]


def test_catalog_exposes_environment_level_pin() -> None:
    registry = ProvenanceRegistry.from_file(PROVENANCE_MANIFEST)
    provenance = registry.catalog_for("coda-community-43")

    assert provenance is not None
    assert provenance.community_id == 43
    assert provenance.revision == "63828a2b652e26a9770555a0cc41e6c8aafdb5d9"
    assert provenance.archive_sha256 == (
        "30771af71c5a37c110b91f5e443e9c2f971ad50e6847bcb8385bee69a2a61aa0"
    )
    assert provenance.asset_manifest_sha256 == (
        "8cd2786b676548fd74c01c571403aeb4d1ecbe42400ae983cef66e53bc818c9d"
    )
    assert provenance.csv_asset_count == 10
    assert provenance.data_access_policy == "download_only"
    assert provenance.source_data_bundled is False


def test_registered_catalog_rejects_a_missing_manifest_asset(
    sample_environment: Path,
    tmp_path: Path,
) -> None:
    manifest_path = write_test_provenance_manifest(sample_environment, tmp_path)
    missing = sample_environment / "data_science_for_good/source/2016 School Explorer.csv"
    missing.unlink()
    catalog = FileCatalog(
        sample_environment,
        environment_id="coda-community-43",
        provenance_registry=ProvenanceRegistry.from_file(manifest_path),
    )

    with pytest.raises(CatalogIntegrityError, match="missing CSVs"):
        catalog.index()


def test_unknown_environment_does_not_invent_provenance(sample_environment: Path) -> None:
    registry = ProvenanceRegistry.from_file(PROVENANCE_MANIFEST)
    catalog = FileCatalog(
        sample_environment,
        environment_id="private-unregistered-catalog",
        provenance_registry=registry,
    )

    assert catalog.catalog_provenance is None
    assert all(asset.provenance is None for asset in catalog.index().values())


def test_manifest_rejects_inconsistent_counts(tmp_path: Path) -> None:
    payload = json.loads(PROVENANCE_MANIFEST.read_text(encoding="utf-8"))
    payload["environments"]["coda-community-43"]["source_count"] = 99
    path = tmp_path / "invalid-provenance.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ProvenanceManifestError, match="manifest is invalid"):
        ProvenanceRegistry.from_file(path)


def test_registry_rejects_a_modified_checksum_manifest(tmp_path: Path) -> None:
    payload = json.loads(PROVENANCE_MANIFEST.read_text(encoding="utf-8"))
    for environment in payload["environments"].values():
        filename = Path(environment["asset_manifest"]).name
        source = PROJECT_ROOT / environment["asset_manifest"]
        (tmp_path / filename).write_bytes(source.read_bytes())
    checksum_path = tmp_path / "coda-community-43-csv.sha256"
    checksum_path.write_bytes(checksum_path.read_bytes() + b"\n")
    path = tmp_path / "provenance.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ProvenanceManifestError, match="manifest is invalid"):
        ProvenanceRegistry.from_file(path)


def test_registry_rejects_missing_source_metadata(
    sample_environment: Path,
    tmp_path: Path,
) -> None:
    path = write_test_provenance_manifest(sample_environment, tmp_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    environment = payload["environments"]["coda-community-43"]
    environment["sources"].pop("nyc-school-district-breakdowns")
    environment["source_count"] -= 1
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ProvenanceManifestError, match="manifest is invalid"):
        ProvenanceRegistry.from_file(path)
