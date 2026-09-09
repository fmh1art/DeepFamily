from __future__ import annotations

from pathlib import Path

import pandas as pd

from askdu.adapters.catalog import FileCatalog


def test_initial_discovery_prefers_registration_table(sample_environment: Path) -> None:
    catalog = FileCatalog(sample_environment)
    ranking = catalog.rank(["SHSAT", "registrations", "testers", "grade level", "year"])

    assert ranking
    assert ranking[0][0].name == "D5 SHSAT Registrations and Testers.csv"


def test_repair_discovery_prefers_demographic_table(sample_environment: Path) -> None:
    catalog = FileCatalog(sample_environment)
    initial = catalog.rank(["SHSAT", "registrations", "testers"])[0][0]
    ranking = catalog.rank(
        ["Percent Asian", "Percent Black / Hispanic", "Percent White", "school demographics"],
        {initial.asset_id},
    )

    assert ranking
    assert ranking[0][0].name == "2016 School Explorer.csv"


def test_completed_source_profile_is_cached(sample_environment: Path) -> None:
    catalog = FileCatalog(sample_environment)
    indexed = next(iter(catalog.index().values()))

    first = catalog.profile(indexed.asset_id)
    second = catalog.profile(indexed.asset_id)

    assert first is second
    assert first.row_count is not None
    assert first.sha256 is not None


def test_catalog_indexes_and_previews_heterogeneous_tabular_files(tmp_path: Path) -> None:
    frame = pd.DataFrame({"name": ["A", "B"], "value": [1, 2]})
    frame.to_csv(tmp_path / "table.tsv", sep="\t", index=False)
    frame.to_json(tmp_path / "records.json", orient="records")
    frame.to_json(tmp_path / "records.jsonl", orient="records", lines=True)
    frame.to_parquet(tmp_path / "table.parquet", index=False)
    frame.to_excel(tmp_path / "table.xlsx", index=False)
    (tmp_path / "notes.pdf").write_bytes(b"not a real PDF")
    catalog = FileCatalog(tmp_path)

    assets = {asset.name: asset for asset in catalog.index().values()}

    assert set(assets) == {
        "notes.pdf",
        "records.json",
        "records.jsonl",
        "table.parquet",
        "table.tsv",
        "table.xlsx",
    }
    for name in ("records.json", "records.jsonl", "table.parquet", "table.tsv", "table.xlsx"):
        preview = catalog.preview(assets[name].asset_id, rows=1)
        assert preview["columns"] == ["name", "value"]
        assert preview["sample_rows"] == [{"name": "A", "value": 1}]
    binary_preview = catalog.preview(assets["notes.pdf"].asset_id)
    assert binary_preview["tabular"] is False


def test_malformed_csv_header_does_not_break_catalog_readiness(tmp_path: Path) -> None:
    malformed = tmp_path / "mislabeled.csv"
    malformed.write_bytes(b"column_a,\x00column_b\n1,2\n")

    catalog = FileCatalog(tmp_path)
    asset = next(iter(catalog.index().values()))
    profiled = catalog.profile(asset.asset_id)

    assert asset.relative_path == "mislabeled.csv"
    assert asset.columns == ["column_a", "column_b"]
    assert profiled.sha256 is not None
    assert profiled.row_count is None
