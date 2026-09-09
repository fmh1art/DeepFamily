from __future__ import annotations

from pathlib import Path

from askdu.adapters.coda_release import CodaReleaseRegistry
from askdu.adapters.federated_catalog import FederatedFileCatalog
from askdu.config import PROJECT_ROOT

MANIFEST = PROJECT_ROOT / "data/manifests/coda-bench-v1-open-release.json"


def _write_community(release_root: Path, community_id: int, payload: str) -> None:
    directory = release_root / "communities" / f"community_{community_id}" / "full_community"
    directory.mkdir(parents=True)
    (directory / "dataset.csv").write_text(payload, encoding="utf-8")


def test_federated_catalog_uses_only_manifest_admitted_installed_roots(tmp_path: Path) -> None:
    _write_community(tmp_path, 17, "value\n17\n")
    _write_community(tmp_path, 18, "value\n18\n")
    _write_community(tmp_path, 999, "private\nnever-index\n")
    registry = CodaReleaseRegistry(manifest_path=MANIFEST, release_root=tmp_path)
    catalog = FederatedFileCatalog(registry)

    assets = list(catalog.index().values())

    assert catalog.installed_community_ids == (17, 18)
    assert len(assets) == 2
    assert len({asset.asset_id for asset in assets}) == 2
    assert {asset.relative_path for asset in assets} == {
        "community_17/dataset.csv",
        "community_18/dataset.csv",
    }
    assert all("999" not in asset.relative_path for asset in assets)
    assert [entry["name"] for entry in catalog.list_directory()] == [
        "community_17",
        "community_18",
    ]


def test_federated_asset_resolves_through_its_allowlisted_child(tmp_path: Path) -> None:
    _write_community(tmp_path, 17, "value\n17\n")
    catalog = FederatedFileCatalog(
        CodaReleaseRegistry(manifest_path=MANIFEST, release_root=tmp_path)
    )
    asset = next(iter(catalog.index().values()))

    preview = catalog.preview(asset.asset_id)

    assert preview["sample_rows"] == [{"value": 17}]
    assert catalog.resolve(asset).read_text(encoding="utf-8") == "value\n17\n"
    assert catalog.selection_scope(asset) == "community_17"
