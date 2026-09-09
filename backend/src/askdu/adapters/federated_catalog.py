from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from askdu.adapters.catalog import FileCatalog
from askdu.adapters.coda_release import CodaReleaseRegistry
from askdu.domain import CatalogProvenance, DataAsset


def _federated_asset_id(relative_path: str) -> str:
    digest = hashlib.sha256(relative_path.encode("utf-8")).hexdigest()[:16]
    return f"asset_{digest}"


class FederatedFileCatalog(FileCatalog):
    """Allowlisted virtual catalog across installed open CoDA communities.

    The registry manifest is the authority. Directly walking the release's
    communities directory would risk entering a sealed or unpinned environment,
    so this adapter constructs children only from open manifest entries.
    """

    def __init__(self, registry: CodaReleaseRegistry) -> None:
        self.registry = registry
        self.root = registry.release_root
        self.environment_id = "coda-open-v1"
        self.provenance_registry = None
        self._assets: dict[str, DataAsset] | None = None
        self._children: dict[int, FileCatalog] = {}
        self._asset_origins: dict[str, tuple[int, str]] = {}
        for installation in registry.installations():
            if installation.data_root is not None:
                self._children[installation.community_id] = FileCatalog(
                    installation.data_root,
                    environment_id=f"coda-community-{installation.community_id}",
                )

    @property
    def catalog_provenance(self) -> CatalogProvenance | None:
        return None

    @property
    def installed_community_ids(self) -> tuple[int, ...]:
        return tuple(sorted(self._children))

    def index(self) -> dict[str, DataAsset]:
        if self._assets is not None:
            return self._assets
        assets: dict[str, DataAsset] = {}
        origins: dict[str, tuple[int, str]] = {}
        for community_id, child in sorted(self._children.items()):
            prefix = f"community_{community_id}"
            for local in child.index().values():
                relative_path = f"{prefix}/{local.relative_path}"
                asset_id = _federated_asset_id(relative_path)
                if asset_id in assets:
                    raise ValueError("Federated asset ID collision")
                assets[asset_id] = local.model_copy(
                    update={
                        "asset_id": asset_id,
                        "relative_path": relative_path,
                    }
                )
                origins[asset_id] = (community_id, local.asset_id)
        self._assets = assets
        self._asset_origins = origins
        return assets

    def rank(
        self,
        search_terms: list[str],
        excluded_ids: set[str] | None = None,
    ) -> list[tuple[DataAsset, float]]:
        self.index()
        excluded = excluded_ids or set()
        ranked: list[tuple[DataAsset, float]] = []
        for community_id, child in sorted(self._children.items()):
            prefix = f"community_{community_id}"
            excluded_local = {
                local_id
                for federated_id, (origin_id, local_id) in self._asset_origins.items()
                if origin_id == community_id and federated_id in excluded
            }
            for local, score in child.rank(search_terms, excluded_local):
                relative_path = f"{prefix}/{local.relative_path}"
                federated_id = _federated_asset_id(relative_path)
                ranked.append((self.index()[federated_id], score))
        return sorted(ranked, key=lambda item: (-item[1], item[0].relative_path))

    def rank_paths(
        self,
        search_terms: list[str],
        excluded_ids: set[str] | None = None,
    ) -> list[tuple[DataAsset, float]]:
        self.index()
        excluded = excluded_ids or set()
        ranked: list[tuple[DataAsset, float]] = []
        for community_id, child in sorted(self._children.items()):
            excluded_local = {
                local_id
                for federated_id, (origin_id, local_id) in self._asset_origins.items()
                if origin_id == community_id and federated_id in excluded
            }
            for local, score in child.rank_paths(search_terms, excluded_local):
                relative_path = f"community_{community_id}/{local.relative_path}"
                ranked.append((self.index()[_federated_asset_id(relative_path)], score))
        return sorted(ranked, key=lambda item: (-item[1], item[0].relative_path))

    def list_directory(self, relative_directory: str = "", limit: int = 50) -> list[dict[str, Any]]:
        if not relative_directory:
            return [
                {
                    "name": f"community_{community_id}",
                    "relative_path": f"community_{community_id}",
                    "kind": "directory",
                }
                for community_id in self.installed_community_ids[:limit]
            ]
        path = Path(relative_directory)
        if path.is_absolute() or ".." in path.parts or not path.parts:
            raise ValueError("directory must name an installed open community")
        head = path.parts[0]
        if not head.startswith("community_"):
            raise ValueError("directory must name an installed open community")
        try:
            community_id = int(head.removeprefix("community_"))
        except ValueError:
            raise ValueError("invalid community directory") from None
        child = self._children.get(community_id)
        if child is None:
            raise ValueError("community is not installed in the open catalog")
        local_directory = Path(*path.parts[1:]).as_posix() if len(path.parts) > 1 else ""
        entries = child.list_directory(local_directory, limit)
        rendered: list[dict[str, Any]] = []
        for entry in entries:
            relative_path = f"community_{community_id}/{entry['relative_path']}"
            updated = {**entry, "relative_path": relative_path}
            if "asset_id" in entry:
                updated["asset_id"] = _federated_asset_id(relative_path)
            rendered.append(updated)
        return rendered

    def preview(self, asset_id: str, rows: int = 5) -> dict[str, Any]:
        community_id, child, local_id = self._origin(asset_id)
        preview = child.preview(local_id, rows)
        local = child.index()[local_id]
        updated = self.index()[asset_id].model_copy(update={"columns": list(local.columns)})
        assert self._assets is not None
        self._assets[asset_id] = updated
        return {
            **preview,
            "asset_id": asset_id,
            "relative_path": f"community_{community_id}/{preview['relative_path']}",
        }

    def profile(self, asset_id: str) -> DataAsset:
        community_id, child, local_id = self._origin(asset_id)
        local = child.profile(local_id)
        relative_path = f"community_{community_id}/{local.relative_path}"
        profiled = local.model_copy(
            update={
                "asset_id": asset_id,
                "relative_path": relative_path,
            }
        )
        assert self._assets is not None
        self._assets[asset_id] = profiled
        return profiled

    def resolve(self, asset: DataAsset) -> Path:
        _, child, local_id = self._origin(asset.asset_id)
        return child.resolve(child.index()[local_id])

    def selection_scope(self, asset: DataAsset) -> str | None:
        community_id, _, _ = self._origin(asset.asset_id)
        return f"community_{community_id}"

    def _origin(self, asset_id: str) -> tuple[int, FileCatalog, str]:
        self.index()
        try:
            community_id, local_id = self._asset_origins[asset_id]
            return community_id, self._children[community_id], local_id
        except KeyError:
            raise KeyError(f"Unknown federated asset ID: {asset_id}") from None
