from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import pytest
from markdown_it import MarkdownIt

from askdu.adapters.catalog import FileCatalog
from askdu.adapters.declarative import DeclarativeEngine, format_declarative_answer
from askdu.domain import (
    AnalysisArtifact,
    AnalyticalContract,
    DeclarativeAnalysisPlan,
    MaterializedState,
    ReportNarrative,
    ReportSection,
)

# The CommonMark parser is already pinned in backend/uv.lock through Rich.
# Enable the GFM-style table rule, and allow HTML so the test catches unsafe
# result-cell markup rather than relying on a renderer's default escaping.
MARKDOWN = MarkdownIt("commonmark", {"html": True}).enable("table")


def artifact(value: Any, *, precision: int | None = None) -> AnalysisArtifact:
    return AnalysisArtifact(
        artifact_id="artifact_country",
        name="country_comparison",
        kind="table",
        value=value,
        display_precision=precision,
        source_state_ids=["state_country"],
    )


def table_cells(markdown: str, kind: str) -> list[str]:
    tokens = MARKDOWN.parse(markdown)
    return [
        "".join(child.content for child in tokens[index + 1].children or [])
        for index, token in enumerate(tokens)
        if token.type == kind
    ]


@pytest.mark.parametrize(
    ("value", "columns", "cells"),
    [
        (
            {"Country": "Finland", "Score": 7.824000000000001},
            ["Country", "Score"],
            ["Finland", "7.824"],
        ),
        (
            [{"Country": "A"}, {"Country": "B", "Score": 8.0}],
            ["Country", "Score"],
            ["A", "Not available", "B", "8"],
        ),
        (["A", "B", None], ["Value"], ["A", "B", "Not available"]),
    ],
)
def test_result_records_are_real_markdown_tables(
    value: Any, columns: list[str], cells: list[str]
) -> None:
    rendered = DeclarativeEngine._render_value(artifact(value))
    assert table_cells(rendered, "th_open") == columns
    assert table_cells(rendered, "td_open") == cells
    assert not any(token.type == "fence" for token in MARKDOWN.parse(rendered))


@pytest.mark.parametrize(
    ("value", "precision", "expected"),
    [
        (7.824000000000001, None, "7.824"),
        (7.824000000000001, 2, "7.82"),
        (0.000000000123, None, "1.23e-10"),
        (9007199254740993, None, "9007199254740993"),
        (None, None, "Not available"),
        (False, None, "False"),
    ],
)
def test_markdown_display_keeps_raw_values_and_tiny_numbers(
    value: Any, precision: int | None, expected: str
) -> None:
    item = artifact(value, precision=precision)
    before = item.model_dump_json()
    answer_before = format_declarative_answer([item])
    assert expected in MARKDOWN.render(DeclarativeEngine._render_value(item))
    assert item.model_dump_json() == before
    assert format_declarative_answer([item]) == answer_before


def test_data_cells_cannot_inject_html_images_code_or_extra_columns() -> None:
    column = "Country|region"
    value = '<img src="https://example.invalid/beacon">![x](https://example.invalid/x)`a|b`\\|'
    rendered = DeclarativeEngine._render_value(artifact([{column: value, "note": "a\r\nb"}]))
    html = MARKDOWN.render(rendered)
    assert "<img" not in html
    assert "<code>" not in html
    assert "<br>" in html
    assert table_cells(rendered, "th_open") == [column, "note"]
    assert table_cells(rendered, "td_open")[0] == value
    assert html.count("<td>") == 2


@pytest.mark.parametrize("value", [[], {}])
def test_empty_result_is_not_a_zero_or_a_json_block(value: Any) -> None:
    html = MARKDOWN.render(DeclarativeEngine._render_value(artifact(value)))
    assert "No matching records" in html or "No recorded fields" in html
    assert "<pre>" not in html
    assert "<table>" not in html


def test_report_links_to_each_result_once_and_persists_exact_download_bytes(tmp_path: Path) -> None:
    item = artifact([{"Country": "A", "Score": 8.0}, {"Country": "B", "Score": 7.0}])
    plan = DeclarativeAnalysisPlan.model_validate(
        {
            "summary": "Compare countries using the recorded score.",
            "search_terms": ["country", "score"],
            "sources": [
                {
                    "alias": "countries",
                    "asset_id": "asset_0123456789abcdef",
                    "required_columns": ["Country", "Score"],
                    "purpose": "Compare countries",
                }
            ],
            "analyses": [
                {
                    "type": "rows",
                    "name": item.name,
                    "table": "countries",
                    "columns": ["Country", "Score"],
                }
            ],
            "primary_table": "countries",
            "report_title": "Country comparison",
        }
    )
    contract = AnalyticalContract(
        question="Which country has the highest recorded score?",
        task_family="declarative",
        search_terms=plan.search_terms,
        obligations=[],
        analysis_plan=plan,
    )
    state = MaterializedState(
        state_id="state_country",
        iteration=0,
        source_ids=[],
        row_count=2,
        columns=["Country", "Score"],
    )
    narrative = ReportNarrative(
        title="Country comparison",
        executive_summary="A has the highest recorded score.",
        executive_artifact_refs=[item.artifact_id],
        sections=[
            ReportSection(
                title="Ranking",
                narrative="A scores 8 and B scores 7.",
                artifact_refs=[item.artifact_id],
            ),
            ReportSection(
                title="Comparison",
                narrative="A leads B in this metric.",
                artifact_refs=[item.artifact_id],
            ),
        ],
        conclusion="A leads within this dataset and metric.",
        conclusion_artifact_refs=[item.artifact_id],
        limitations=["One metric only."],
    )
    engine = DeclarativeEngine(catalog=FileCatalog(tmp_path), runtime_root=tmp_path / "runtime")
    report, evidence = engine.render_report(
        run_id="run_markdown",
        question=contract.question,
        assets=[],
        state=state,
        artifacts=[item],
        contract=contract,
        narrative=narrative,
    )
    tokens = MARKDOWN.parse(report.markdown)
    assert sum(token.type == "table_open" for token in tokens) == 1
    assert report.markdown.count('<a id="evidence-1"></a>') == 1
    assert report.markdown.count("[E1](#evidence-1)") == 4
    assert report.markdown.index("## Integrated conclusion") < report.markdown.index("<a id=")
    assert not any(line.startswith("- |") for line in report.markdown.splitlines())
    assert report.claims[0].value == item.value
    assert report.sections == narrative.sections
    stored = tmp_path / "runtime/runs/run_markdown/reports/report.md"
    assert stored.read_text() == report.markdown
    assert hashlib.sha256(stored.read_bytes()).hexdigest() == evidence.sha256
