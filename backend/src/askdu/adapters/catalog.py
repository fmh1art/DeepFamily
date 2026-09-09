from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import re
from pathlib import Path
from typing import Any

import ijson  # type: ignore[import-untyped]
import pandas as pd
import pyarrow.parquet as pq  # type: ignore[import-untyped]

from askdu.adapters.provenance import ProvenanceRegistry
from askdu.domain import CatalogProvenance, DataAsset


class CatalogIntegrityError(ValueError):
    """Raised when a selected file differs from its pinned public manifest."""


TABULAR_FORMATS = {"csv", "tsv", "json", "jsonl", "parquet", "xlsx", "xls"}
FORMAT_BY_SUFFIX = {
    ".csv": "csv",
    ".tsv": "tsv",
    ".json": "json",
    ".jsonl": "jsonl",
    ".ndjson": "jsonl",
    ".parquet": "parquet",
    ".xlsx": "xlsx",
    ".xls": "xls",
    ".pdf": "pdf",
    ".png": "image",
    ".jpg": "image",
    ".jpeg": "image",
    ".webp": "image",
}


def _canonical(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", text.lower()))


def _asset_id(relative_path: str) -> str:
    digest = hashlib.sha256(relative_path.encode("utf-8")).hexdigest()[:16]
    return f"asset_{digest}"


class FileCatalog:
    """Read-only catalog over files contained by one authorized environment root."""

    def __init__(
        self,
        root: Path,
        *,
        environment_id: str | None = None,
        provenance_registry: ProvenanceRegistry | None = None,
    ):
        self.root = root.expanduser().resolve()
        if not self.root.is_dir():
            raise FileNotFoundError(f"Data environment does not exist: {self.root}")
        self._assets: dict[str, DataAsset] | None = None
        self.environment_id = environment_id
        self.provenance_registry = provenance_registry

    @property
    def catalog_provenance(self) -> CatalogProvenance | None:
        if self.environment_id is None or self.provenance_registry is None:
            return None
        return self.provenance_registry.catalog_for(self.environment_id)

    def index(self) -> dict[str, DataAsset]:
        if self._assets is not None:
            return self._assets
        assets: dict[str, DataAsset] = {}
        registered_environment = self.catalog_provenance is not None
        candidates = (
            sorted(self.root.rglob("*.csv"))
            if registered_environment
            else sorted(path for path in self.root.rglob("*") if path.is_file())
        )
        for path in candidates:
            resolved = path.resolve()
            if not resolved.is_file() or not resolved.is_relative_to(self.root):
                continue
            relative = resolved.relative_to(self.root).as_posix()
            expected_sha256 = (
                self.provenance_registry.expected_asset_sha256(self.environment_id, relative)
                if self.environment_id is not None and self.provenance_registry is not None
                else None
            )
            if registered_environment and expected_sha256 is None:
                continue
            file_format = FORMAT_BY_SUFFIX.get(resolved.suffix.casefold(), "other")
            columns = self._initial_columns(resolved, file_format)
            asset = DataAsset(
                asset_id=_asset_id(relative),
                relative_path=relative,
                name=resolved.name,
                columns=columns,
                byte_size=resolved.stat().st_size,
                file_format=file_format,
                tabular=file_format in TABULAR_FORMATS,
                expected_sha256=expected_sha256,
                integrity_status="unverified" if expected_sha256 is not None else "unregistered",
                provenance=(
                    self.provenance_registry.source_for(self.environment_id, relative)
                    if self.environment_id is not None and self.provenance_registry is not None
                    else None
                ),
            )
            assets[asset.asset_id] = asset
        if registered_environment and self.environment_id is not None:
            assert self.provenance_registry is not None
            expected_paths = self.provenance_registry.registered_asset_paths(self.environment_id)
            observed_paths = {asset.relative_path for asset in assets.values()}
            missing_paths = expected_paths - observed_paths
            if missing_paths:
                raise CatalogIntegrityError(
                    "Authorized catalog is missing CSVs required by the pinned manifest"
                )
        self._assets = assets
        return assets

    def list_directory(self, relative_directory: str = "", limit: int = 50) -> list[dict[str, Any]]:
        if not 1 <= limit <= 200:
            raise ValueError("directory listing limit must be between 1 and 200")
        relative = Path(relative_directory or ".")
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("directory must be relative to the authorized root")
        directory = (self.root / relative).resolve()
        if not directory.is_relative_to(self.root) or not directory.is_dir():
            raise ValueError("directory is outside the authorized root or does not exist")
        by_relative_path = {asset.relative_path: asset for asset in self.index().values()}
        entries: list[dict[str, Any]] = []
        for child in sorted(directory.iterdir(), key=lambda item: item.name.casefold()):
            resolved = child.resolve()
            if not resolved.is_relative_to(self.root):
                continue
            entry: dict[str, Any] = {
                "name": child.name,
                "relative_path": resolved.relative_to(self.root).as_posix(),
                "kind": "directory" if resolved.is_dir() else "file",
            }
            if resolved.is_file():
                entry["bytes"] = resolved.stat().st_size
                entry["format"] = FORMAT_BY_SUFFIX.get(resolved.suffix.casefold(), "other")
                asset = by_relative_path.get(resolved.relative_to(self.root).as_posix())
                if asset is not None:
                    entry["asset_id"] = asset.asset_id
            entries.append(entry)
            if len(entries) >= limit:
                break
        return entries

    def rank_paths(
        self,
        search_terms: list[str],
        excluded_ids: set[str] | None = None,
    ) -> list[tuple[DataAsset, float]]:
        """Rank only path text, preserving the no-schema-before-inspection boundary."""

        excluded = excluded_ids or set()
        terms = [_canonical(term) for term in search_terms if _canonical(term)]
        ranked: list[tuple[DataAsset, float]] = []
        for asset in self.index().values():
            if asset.asset_id in excluded:
                continue
            path_text = _canonical(asset.relative_path)
            path_tokens = set(path_text.split())
            score = 0.0
            for term in terms:
                if term in path_text:
                    score += 12.0
                score += 2.0 * len(set(term.split()) & path_tokens)
            if score > 0:
                ranked.append((asset, score))
        return sorted(ranked, key=lambda item: (-item[1], item[0].relative_path))

    def preview(self, asset_id: str, rows: int = 5) -> dict[str, Any]:
        if not 1 <= rows <= 20:
            raise ValueError("preview rows must be between 1 and 20")
        asset = self.index()[asset_id]
        if not asset.tabular:
            return {
                "asset_id": asset.asset_id,
                "relative_path": asset.relative_path,
                "format": asset.file_format,
                "bytes": asset.byte_size,
                "tabular": False,
            }
        path = self.resolve(asset)
        frame = self._read_preview(path, asset.file_format, rows)
        columns = [str(column) for column in frame.columns]
        if columns and columns != asset.columns:
            asset = asset.model_copy(update={"columns": columns})
            if self._assets is not None:
                self._assets[asset_id] = asset
        return {
            "asset_id": asset.asset_id,
            "relative_path": asset.relative_path,
            "format": asset.file_format,
            "bytes": asset.byte_size,
            "tabular": True,
            "columns": columns,
            "dtypes": {str(column): str(dtype) for column, dtype in frame.dtypes.items()},
            "sample_rows": self._json_records(frame),
        }

    def rank(
        self,
        search_terms: list[str],
        excluded_ids: set[str] | None = None,
    ) -> list[tuple[DataAsset, float]]:
        excluded = excluded_ids or set()
        terms = [_canonical(term) for term in search_terms if _canonical(term)]
        ranked: list[tuple[DataAsset, float]] = []
        for asset in self.index().values():
            if asset.asset_id in excluded:
                continue
            path_text = _canonical(asset.relative_path)
            column_texts = [_canonical(column) for column in asset.columns]
            score = 0.0
            for term in terms:
                if term in path_text:
                    score += 12.0
                if any(term == column or term in column for column in column_texts):
                    score += 7.0
                term_tokens = set(term.split())
                path_tokens = set(path_text.split())
                score += 2.0 * len(term_tokens & path_tokens)
                best_column_overlap = max(
                    (len(term_tokens & set(column.split())) for column in column_texts),
                    default=0,
                )
                score += float(best_column_overlap)
            if score > 0:
                ranked.append((asset, score))
        return sorted(ranked, key=lambda item: (-item[1], item[0].relative_path))

    def profile(self, asset_id: str) -> DataAsset:
        asset = self.index()[asset_id]
        if asset.row_count is not None and asset.sha256 is not None:
            return asset
        path = self.resolve(asset)
        digest = hashlib.sha256()
        row_count: int | None = -1
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        sha256 = digest.hexdigest()
        if asset.expected_sha256 is not None and sha256 != asset.expected_sha256:
            raise CatalogIntegrityError(
                f"Asset checksum differs from the pinned manifest: {asset.relative_path}"
            )
        if asset.file_format in {"csv", "tsv"}:
            delimiter = "\t" if asset.file_format == "tsv" else ","
            try:
                with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as handle:
                    row_count = max(
                        sum(1 for _ in csv.reader(handle, delimiter=delimiter)) - 1,
                        0,
                    )
            except csv.Error:
                row_count = None
        else:
            frame = self._read_preview(path, asset.file_format, 20)
            row_count = len(frame) if path.stat().st_size <= 8 * 1024 * 1024 else None
        profiled = asset.model_copy(
            update={
                "row_count": row_count,
                "sha256": sha256,
                "integrity_status": (
                    "verified" if asset.expected_sha256 is not None else "unregistered"
                ),
            }
        )
        if self._assets is not None:
            self._assets[asset_id] = profiled
        return profiled

    def resolve(self, asset: DataAsset) -> Path:
        candidate = (self.root / asset.relative_path).resolve()
        if not candidate.is_relative_to(self.root) or not candidate.is_file():
            raise ValueError(f"Asset escaped authorized root: {asset.asset_id}")
        return candidate

    def selection_scope(self, asset: DataAsset) -> str | None:
        """Return a grouping boundary when selected assets must share one scope."""

        return None

    @staticmethod
    def _initial_columns(path: Path, file_format: str) -> list[str]:
        if file_format in {"csv", "tsv"}:
            delimiter = "\t" if file_format == "tsv" else ","
            with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as handle:
                prefix = handle.read(1024 * 1024).replace("\x00", "")
            try:
                return next(csv.reader(io.StringIO(prefix), delimiter=delimiter), [])
            except csv.Error:
                # Real discovery pools contain mislabeled or malformed CSVs. Keep the
                # path discoverable and defer a controlled read failure to inspection.
                return []
        if file_format == "jsonl":
            with path.open("r", encoding="utf-8-sig", errors="replace") as handle:
                first = handle.readline(256 * 1024)
            try:
                value = json.loads(first)
            except json.JSONDecodeError:
                return []
            return [str(key) for key in value] if isinstance(value, dict) else []
        return []

    @staticmethod
    def _read_preview(path: Path, file_format: str, rows: int) -> pd.DataFrame:
        if file_format == "csv":
            return pd.read_csv(path, nrows=rows, low_memory=False)
        if file_format == "tsv":
            return pd.read_csv(path, sep="\t", nrows=rows, low_memory=False)
        if file_format == "jsonl":
            return pd.read_json(path, lines=True, nrows=rows)
        if file_format == "json":
            with path.open("rb") as handle:
                records = list(ijson.items(handle, "item", use_float=True))[:rows]
            if not records:
                return pd.DataFrame()
            if not all(isinstance(record, dict) for record in records):
                return pd.DataFrame({"value": records})
            return pd.DataFrame(records)
        if file_format == "parquet":
            parquet = pq.ParquetFile(path)
            batch = next(parquet.iter_batches(batch_size=rows), None)
            return batch.to_pandas() if batch is not None else pd.DataFrame()
        if file_format in {"xlsx", "xls"}:
            return pd.read_excel(path, nrows=rows)
        raise ValueError(f"Unsupported tabular format: {file_format}")

    @staticmethod
    def _json_records(frame: pd.DataFrame) -> list[dict[str, Any]]:
        records = frame.to_dict(orient="records")
        return [
            {str(key): FileCatalog._json_scalar(value) for key, value in record.items()}
            for record in records
        ]

    @staticmethod
    def _json_scalar(value: Any) -> Any:
        if value is pd.NA or value is pd.NaT:
            return None
        if isinstance(value, float) and math.isnan(value):
            return None
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value
        if hasattr(value, "isoformat"):
            return value.isoformat()
        return str(value)
