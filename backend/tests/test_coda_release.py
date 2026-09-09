from __future__ import annotations

import json
from pathlib import Path

import pytest

from askdu.adapters.coda_release import (
    CodaReleaseError,
    CodaReleaseManifest,
    CodaReleaseRegistry,
)
from askdu.config import PROJECT_ROOT

MANIFEST = PROJECT_ROOT / "data/manifests/coda-bench-v1-open-release.json"


def test_open_release_manifest_is_internally_consistent() -> None:
    manifest = CodaReleaseManifest.from_file(MANIFEST)

    assert manifest.revision == "63828a2b652e26a9770555a0cc41e6c8aafdb5d9"
    assert manifest.published.task_count == 1009
    assert manifest.published.community_count == 31
    assert manifest.published.source_dataset_count == 199
    assert manifest.open_runtime.task_count == 996
    assert manifest.open_runtime.community_count == 30
    assert manifest.open_runtime.source_dataset_count == 196
    assert manifest.sealed_community_count == 1
    assert len(manifest.archives) == 30
    assert sum(pin.bytes for pin in manifest.archives) == 45_593_031_762


def test_manifest_rejects_a_community_not_in_open_runtime_scope() -> None:
    manifest = CodaReleaseManifest.from_file(MANIFEST)

    with pytest.raises(CodaReleaseError, match="outside the open runtime"):
        manifest.community(999)


def test_registry_reports_only_manifest_admitted_communities(tmp_path: Path) -> None:
    manifest = CodaReleaseManifest.from_file(MANIFEST)
    installed = manifest.archives[0]
    data_root = tmp_path / "communities" / f"community_{installed.community_id}" / "full_community"
    data_root.mkdir(parents=True)
    registry = CodaReleaseRegistry(manifest_path=MANIFEST, release_root=tmp_path)

    installations = registry.installations()

    assert len(installations) == manifest.open_runtime.community_count
    assert sum(item.extracted for item in installations) == 1
    assert registry.require_data_root(installed.community_id) == data_root


def test_manifest_rejects_tampered_open_archive_total(tmp_path: Path) -> None:
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    payload["open_runtime_scope"]["compressed_archive_bytes"] += 1
    tampered = tmp_path / "manifest.json"
    tampered.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(CodaReleaseError, match="byte total"):
        CodaReleaseManifest.from_file(tampered)
