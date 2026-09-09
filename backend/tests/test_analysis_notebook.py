from __future__ import annotations

from typing import Any

import pandas as pd

from askdu.application.analysis_notebook import (
    compile_analysis_cell,
    execute_analysis_cell,
    values_equivalent,
)
from askdu.domain import (
    AggregateAnalysis,
    AggregateFunction,
    CorrelationAnalysis,
    FilterPredicate,
    GroupAggregateAnalysis,
    PredicateOperator,
)


def test_group_aggregate_compiles_to_and_executes_real_sql() -> None:
    frame = pd.DataFrame(
        {
            "tier": ["standard", "standard", "enterprise"],
            "revenue": [100, 10, 150],
            "status": ["complete", "cancelled", "complete"],
        }
    )
    analysis = GroupAggregateAnalysis(
        name="top_tier",
        table="prepared",
        group_by=["tier"],
        function=AggregateFunction.SUM,
        column="revenue",
        predicates=[
            FilterPredicate(
                column="status",
                operator=PredicateOperator.EQ,
                value="complete",
            )
        ],
        limit=1,
    )

    cell = compile_analysis_cell(analysis)
    result = execute_analysis_cell(cell, analysis, frame, {}, lambda: None)

    assert cell.language == "sql"
    assert "GROUP BY" in cell.source
    assert cell.parameters == {"p1": "complete"}
    assert result == [{"tier": "enterprise", "value": 150}]


def test_correlation_python_cell_is_compiler_owned_and_executable() -> None:
    frame = pd.DataFrame({"x": [1, 2, 3], "y": [2, 4, 6]})
    analysis = CorrelationAnalysis(
        name="xy",
        table="prepared",
        x="x",
        y="y",
    )

    cell = compile_analysis_cell(analysis)
    result = execute_analysis_cell(cell, analysis, frame, {}, lambda: None)

    assert cell.language == "python"
    assert "pd.to_numeric" in cell.source
    assert values_equivalent(result, 1.0)


def test_non_sql_statistic_calls_only_the_bounded_fallback() -> None:
    frame = pd.DataFrame({"value": [1, 3, 7]})
    analysis = AggregateAnalysis(
        name="median_value",
        table="prepared",
        function=AggregateFunction.MEDIAN,
        column="value",
    )
    calls: list[dict[str, Any]] = []

    def bounded() -> float:
        calls.append(analysis.model_dump())
        return 3.0

    cell = compile_analysis_cell(analysis)
    result = execute_analysis_cell(cell, analysis, frame, {}, bounded)

    assert cell.language == "python"
    assert "bounded_dataframe_analysis" in cell.source
    assert result == 3.0
    assert len(calls) == 1
