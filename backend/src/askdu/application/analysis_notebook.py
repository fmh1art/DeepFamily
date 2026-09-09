from __future__ import annotations

import json
import math
import pprint
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

import pandas as pd

from askdu.domain import (
    AggregateAnalysis,
    AggregateFunction,
    ArithmeticAnalysis,
    ArithmeticOperator,
    CorrelationAnalysis,
    DistinctAnalysis,
    ExtremeRowAnalysis,
    FilterPredicate,
    GroupAggregateAnalysis,
    PredicateOperator,
    RowsAnalysis,
    ShareAnalysis,
)


@dataclass(frozen=True)
class CompiledAnalysisCell:
    """Executable code derived only from an already validated typed analysis."""

    language: Literal["sql", "python"]
    source: str
    parameters: dict[str, Any]
    runtime: str


def _quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


class _SqlPredicateCompiler:
    def __init__(self) -> None:
        self.parameters: dict[str, Any] = {}

    def _parameter(self, value: Any) -> str:
        name = f"p{len(self.parameters) + 1}"
        self.parameters[name] = value
        return f":{name}"

    def one(self, predicate: FilterPredicate) -> str:
        column = _quote_identifier(predicate.column)
        operator = predicate.operator
        value = predicate.value
        if operator == PredicateOperator.IS_NULL:
            return f"{column} IS NULL"
        if operator == PredicateOperator.NOT_NULL:
            return f"{column} IS NOT NULL"
        if operator == PredicateOperator.CONTAINS:
            assert isinstance(value, str)
            parameter = self._parameter(value)
            if predicate.case_sensitive:
                return f"INSTR(CAST({column} AS TEXT), {parameter}) > 0"
            return f"INSTR(LOWER(CAST({column} AS TEXT)), LOWER({parameter})) > 0"
        if operator in {PredicateOperator.IN, PredicateOperator.NOT_IN}:
            assert isinstance(value, list)
            parameters = ", ".join(self._parameter(item) for item in value)
            expression = column
            if not predicate.case_sensitive and all(isinstance(item, str) for item in value):
                expression = f"LOWER(CAST({column} AS TEXT))"
                lowered: list[str] = []
                for parameter_name, parameter_value in list(self.parameters.items())[-len(value) :]:
                    self.parameters[parameter_name] = str(parameter_value).casefold()
                    lowered.append(f":{parameter_name}")
                parameters = ", ".join(lowered)
            sql_operator = "NOT IN" if operator == PredicateOperator.NOT_IN else "IN"
            return f"{expression} {sql_operator} ({parameters})"

        assert not isinstance(value, list) and value is not None
        parameter = self._parameter(value)
        expression = column
        target = parameter
        if isinstance(value, str) and not predicate.case_sensitive:
            expression = f"LOWER(CAST({column} AS TEXT))"
            target = f"LOWER({parameter})"
        symbols = {
            PredicateOperator.EQ: "=",
            PredicateOperator.NE: "!=",
            PredicateOperator.GT: ">",
            PredicateOperator.GTE: ">=",
            PredicateOperator.LT: "<",
            PredicateOperator.LTE: "<=",
        }
        return f"{expression} {symbols[operator]} {target}"

    def many(self, predicates: list[FilterPredicate], combine: str) -> str:
        if not predicates:
            return "1 = 1"
        connector = " AND " if combine == "all" else " OR "
        return "(" + connector.join(self.one(predicate) for predicate in predicates) + ")"


def _aggregate_sql(function: AggregateFunction, column: str | None) -> str | None:
    if function == AggregateFunction.COUNT_ROWS:
        return "COUNT(*)"
    assert column is not None
    quoted = _quote_identifier(column)
    functions = {
        AggregateFunction.COUNT_NON_NULL: f"COUNT({quoted})",
        AggregateFunction.NUNIQUE: f"COUNT(DISTINCT {quoted})",
        AggregateFunction.SUM: f"SUM({quoted})",
        AggregateFunction.MEAN: f"AVG({quoted})",
        AggregateFunction.MIN: f"MIN({quoted})",
        AggregateFunction.MAX: f"MAX({quoted})",
    }
    return functions.get(function)


def compile_analysis_cell(analysis: Any) -> CompiledAnalysisCell:
    """Compile one typed analysis into a visible, bounded SQL or Python cell."""

    predicates = _SqlPredicateCompiler()
    query: str | None = None

    if isinstance(analysis, AggregateAnalysis):
        aggregate = _aggregate_sql(analysis.function, analysis.column)
        if aggregate is not None:
            where = predicates.many(analysis.predicates, analysis.predicate_combine)
            query = f"SELECT {aggregate} AS value\nFROM data\nWHERE {where};"
    elif isinstance(analysis, GroupAggregateAnalysis):
        aggregate = _aggregate_sql(analysis.function, analysis.column)
        if aggregate is not None:
            groups = ", ".join(_quote_identifier(column) for column in analysis.group_by)
            where = predicates.many(analysis.predicates, analysis.predicate_combine)
            direction = "ASC" if analysis.sort_direction == "ascending" else "DESC"
            query = (
                f"SELECT {groups}, {aggregate} AS value\n"
                f"FROM data\nWHERE {where}\nGROUP BY {groups}\n"
                f"ORDER BY value {direction}, {groups} ASC\nLIMIT {analysis.limit};"
            )
    elif isinstance(analysis, DistinctAnalysis):
        column = _quote_identifier(analysis.column)
        direction = "ASC" if analysis.sort_direction == "ascending" else "DESC"
        query = (
            f"SELECT DISTINCT {column}\nFROM data\nWHERE {column} IS NOT NULL\n"
            f"ORDER BY {column} {direction}\nLIMIT {analysis.limit};"
        )
    elif isinstance(analysis, ExtremeRowAnalysis):
        columns = ", ".join(_quote_identifier(column) for column in analysis.return_columns)
        order = _quote_identifier(analysis.order_by)
        direction = "ASC" if analysis.extreme == "minimum" else "DESC"
        query = (
            f"SELECT {columns}\nFROM data\nWHERE {order} IS NOT NULL\n"
            f"ORDER BY {order} {direction}\nLIMIT 1;"
        )
    elif isinstance(analysis, RowsAnalysis):
        columns = ", ".join(_quote_identifier(column) for column in analysis.columns)
        order = ""
        if analysis.order_by:
            direction = "ASC" if analysis.sort_direction == "ascending" else "DESC"
            order_columns = ", ".join(
                f"{_quote_identifier(column)} {direction}" for column in analysis.order_by
            )
            order = f"\nORDER BY {order_columns}"
        query = f"SELECT {columns}\nFROM data{order}\nLIMIT {analysis.limit};"
    elif isinstance(analysis, ShareAnalysis):
        denominator = predicates.many(
            analysis.denominator_predicates,
            analysis.denominator_combine,
        )
        numerator = predicates.many(
            analysis.numerator_predicates,
            analysis.numerator_combine,
        )
        scale = "100.0 * " if analysis.as_percentage else "1.0 * "
        query = (
            "SELECT "
            f"{scale}SUM(CASE WHEN ({denominator}) AND ({numerator}) THEN 1 ELSE 0 END) "
            f"/ NULLIF(SUM(CASE WHEN {denominator} THEN 1 ELSE 0 END), 0) AS value\n"
            "FROM data;"
        )

    if query is not None:
        return CompiledAnalysisCell(
            language="sql",
            source=query,
            parameters=predicates.parameters,
            runtime="sqlite_in_memory",
        )

    if isinstance(analysis, CorrelationAnalysis):
        source = "\n".join(
            [
                "pairs = pd.DataFrame({",
                f"    'x': pd.to_numeric(data[{analysis.x!r}], errors='coerce'),",
                f"    'y': pd.to_numeric(data[{analysis.y!r}], errors='coerce'),",
                "}).dropna()",
                f"result = float(pairs['x'].corr(pairs['y'], method={analysis.method!r}))",
            ]
        )
    elif isinstance(analysis, ArithmeticAnalysis):
        symbols = {
            ArithmeticOperator.ADD: "+",
            ArithmeticOperator.SUBTRACT: "-",
            ArithmeticOperator.MULTIPLY: "*",
            ArithmeticOperator.DIVIDE: "/",
        }
        source = (
            f"left = results[{analysis.left_analysis!r}]\n"
            f"right = results[{analysis.right_analysis!r}]\n"
            f"result = (left {symbols[analysis.operator]} right) * {analysis.scale!r}"
        )
    else:
        specification = pprint.pformat(
            analysis.model_dump(mode="json"),
            sort_dicts=False,
            width=88,
        )
        source = (
            f"analysis_spec = {specification}\nresult = bounded_dataframe_analysis(analysis_spec)"
        )
    return CompiledAnalysisCell(
        language="python",
        source=source,
        parameters={},
        runtime="bounded_python_cell",
    )


def execute_analysis_cell(
    cell: CompiledAnalysisCell,
    analysis: Any,
    frame: pd.DataFrame,
    computed: dict[str, Any],
    fallback: Callable[[], Any],
) -> Any:
    """Execute compiler-owned code; no model-authored source reaches this function."""

    if cell.language == "sql":
        with sqlite3.connect(":memory:") as connection:
            frame.to_sql("data", connection, index=False, if_exists="replace")
            cursor = connection.execute(cell.source, cell.parameters)
            rows = cursor.fetchall()
            columns = [str(item[0]) for item in cursor.description or []]
        if isinstance(analysis, (AggregateAnalysis, ShareAnalysis)):
            return rows[0][0] if rows else None
        if isinstance(analysis, GroupAggregateAnalysis):
            records = [dict(zip(columns, row, strict=True)) for row in rows]
            if not analysis.include_aggregate_value:
                return [
                    {column: record[column] for column in analysis.group_by} for record in records
                ]
            return records
        if isinstance(analysis, DistinctAnalysis):
            return [row[0] for row in rows]
        if isinstance(analysis, ExtremeRowAnalysis):
            return dict(zip(columns, rows[0], strict=True)) if rows else {}
        if isinstance(analysis, RowsAnalysis):
            return [dict(zip(columns, row, strict=True)) for row in rows]
        raise ValueError(f"Unsupported SQL result shape for {type(analysis).__name__}")

    namespace: dict[str, Any] = {
        "pd": pd,
        "float": float,
        "data": frame,
        "results": computed,
        "bounded_dataframe_analysis": lambda _spec: fallback(),
    }
    exec(compile(cell.source, "<validated-analysis-cell>", "exec"), {"__builtins__": {}}, namespace)
    return namespace.get("result")


def values_equivalent(left: Any, right: Any) -> bool:
    """Compare a compiled-cell observation with the authoritative bounded executor result."""

    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return math.isclose(float(left), float(right), rel_tol=1e-9, abs_tol=1e-9)
    try:
        return json.dumps(left, sort_keys=True, ensure_ascii=False, default=str) == json.dumps(
            right,
            sort_keys=True,
            ensure_ascii=False,
            default=str,
        )
    except (TypeError, ValueError):
        return str(left) == str(right)
