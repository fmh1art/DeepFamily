from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from askdu.adapters.catalog import FileCatalog
from askdu.adapters.declarative import DeclarativeEngine
from askdu.application.model_compiler import build_contract_from_plan
from askdu.application.plan_validation import validate_plan_against_catalog
from askdu.domain import CompilationTrace, DeclarativeAnalysisPlan


def _contract(question: str, plan: DeclarativeAnalysisPlan):
    return build_contract_from_plan(
        question,
        plan,
        CompilationTrace(kind="model", plan_schema_version="1.0"),
    )


def test_clean_reshape_and_group_operators_execute_as_one_bounded_plan(
    tmp_path: Path,
) -> None:
    source = tmp_path / "people.jsonl"
    records = [
        {"name": "Ada Lovelace", "city": " NY ", "score": 10, "tags": ["x", "y"]},
        {"name": "Grace Hopper", "city": "ny", "score": None, "tags": ["x"]},
        {"name": "Alan Turing", "city": "NY", "score": 20, "tags": ["y"]},
    ]
    source.write_text("".join(json.dumps(row) + "\n" for row in records), encoding="utf-8")
    catalog = FileCatalog(tmp_path)
    asset = next(iter(catalog.index().values()))
    catalog.preview(asset.asset_id)
    asset = catalog.index()[asset.asset_id]
    plan = DeclarativeAnalysisPlan.model_validate(
        {
            "summary": "Normalize people records and find the tag with the largest mean score.",
            "search_terms": ["people", "score", "tags"],
            "sources": [
                {
                    "alias": "people",
                    "asset_id": asset.asset_id,
                    "required_columns": ["name", "city", "score", "tags"],
                    "purpose": "People, score, and tag records",
                }
            ],
            "preparation": [
                {
                    "type": "standardize_string",
                    "input_table": "people",
                    "output_table": "normalized",
                    "columns": ["city"],
                    "trim": True,
                    "case": "lower",
                },
                {
                    "type": "impute",
                    "input_table": "normalized",
                    "output_table": "imputed",
                    "columns": {"score": {"strategy": "mean", "value": None}},
                },
                {
                    "type": "split_column",
                    "input_table": "imputed",
                    "output_table": "split_names",
                    "column": "name",
                    "into": ["first_name", "last_name"],
                    "delimiter": " ",
                },
                {
                    "type": "concatenate_columns",
                    "input_table": "split_names",
                    "output_table": "joined_names",
                    "columns": ["last_name", "first_name"],
                    "output_column": "display_name",
                    "separator": ", ",
                },
                {
                    "type": "explode",
                    "input_table": "joined_names",
                    "output_table": "one_tag_per_row",
                    "columns": ["tags"],
                },
                {
                    "type": "drop_columns",
                    "input_table": "one_tag_per_row",
                    "output_table": "projected",
                    "columns": ["name", "city", "first_name", "last_name", "display_name"],
                },
                {
                    "type": "group_by",
                    "input_table": "projected",
                    "output_table": "tag_means",
                    "group_by": ["tags"],
                    "aggregations": {"mean_score": {"column": "score", "function": "mean"}},
                },
                {
                    "type": "sort",
                    "input_table": "tag_means",
                    "output_table": "ordered",
                    "by": ["mean_score"],
                    "ascending": False,
                },
                {
                    "type": "top_k",
                    "input_table": "ordered",
                    "output_table": "winner",
                    "by": "mean_score",
                    "k": 1,
                    "largest": True,
                },
            ],
            "analyses": [
                {
                    "type": "rows",
                    "name": "top_tag",
                    "table": "winner",
                    "columns": ["tags", "mean_score"],
                    "limit": 1,
                }
            ],
            "primary_table": "winner",
            "report_title": "Top tag by mean score",
        }
    )
    validate_plan_against_catalog(plan, catalog.index())
    engine = DeclarativeEngine(catalog, tmp_path / "runtime")
    contract = _contract("Which tag has the largest mean score?", plan)

    bundle = engine.prepare("run_operator", 0, [asset], contract, [])
    outcome = engine.analyze("run_operator", bundle, contract)

    assert outcome.violation is None
    assert outcome.artifacts[0].value == [{"tags": "y", "mean_score": 15.0}]
    assert bundle.state.parent_state_ids == []


def test_pivot_and_melt_have_declared_deterministic_output_schema(tmp_path: Path) -> None:
    pd.DataFrame(
        {
            "year": [2024, 2024, 2025, 2025],
            "metric": ["a", "b", "a", "b"],
            "amount": [1, 2, 3, 4],
        }
    ).to_csv(tmp_path / "metrics.csv", index=False)
    catalog = FileCatalog(tmp_path)
    asset = next(iter(catalog.index().values()))
    plan = DeclarativeAnalysisPlan.model_validate(
        {
            "summary": "Round-trip metric records through a declared wide schema.",
            "search_terms": ["metrics", "year", "amount"],
            "sources": [
                {
                    "alias": "metrics",
                    "asset_id": asset.asset_id,
                    "required_columns": ["year", "metric", "amount"],
                    "purpose": "Long-form metric observations",
                }
            ],
            "preparation": [
                {
                    "type": "pivot",
                    "input_table": "metrics",
                    "output_table": "wide",
                    "index": ["year"],
                    "columns": "metric",
                    "values": "amount",
                    "aggregation": "sum",
                    "output_columns": ["year", "a", "b"],
                },
                {
                    "type": "melt",
                    "input_table": "wide",
                    "output_table": "long_again",
                    "id_vars": ["year"],
                    "value_vars": ["a", "b"],
                    "variable_name": "metric",
                    "value_name": "amount",
                },
            ],
            "analyses": [
                {
                    "type": "aggregate",
                    "name": "amount_sum",
                    "table": "long_again",
                    "function": "sum",
                    "column": "amount",
                }
            ],
            "primary_table": "long_again",
            "report_title": "Metric total",
        }
    )
    validate_plan_against_catalog(plan, catalog.index())
    engine = DeclarativeEngine(catalog, tmp_path / "runtime")
    contract = _contract("What is the total amount?", plan)

    bundle = engine.prepare("run_reshape", 0, [asset], contract, [])
    outcome = engine.analyze("run_reshape", bundle, contract)

    assert bundle.state.columns == ["year", "metric", "amount"]
    assert outcome.artifacts[0].value == 10
