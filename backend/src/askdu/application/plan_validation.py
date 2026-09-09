from __future__ import annotations

from collections.abc import Iterable

from askdu.domain import (
    AggregateAnalysis,
    AggregateFunction,
    ArithmeticAnalysis,
    CastStep,
    ConcatenateColumnsStep,
    ConcatStep,
    CorrelationAnalysis,
    DataAsset,
    DeclarativeAnalysisPlan,
    DeriveStep,
    DistinctAnalysis,
    DropColumnsStep,
    DropDuplicatesStep,
    DropMissingStep,
    ExplodeStep,
    ExtremeRowAnalysis,
    FilterStep,
    GroupAggregateAnalysis,
    GroupByStep,
    ImputeStep,
    JoinStep,
    MeltStep,
    PivotStep,
    ProjectStep,
    RenameStep,
    RowsAnalysis,
    ShareAnalysis,
    SortStep,
    SplitColumnStep,
    StandardizeStringStep,
    TopKStep,
)
from askdu.domain.plans import ColumnOperand


class PlanValidationError(ValueError):
    """Raised when a declarative plan escapes its catalog or schema boundary."""


def _require_columns(
    available: set[str],
    required: Iterable[str],
    context: str,
) -> None:
    missing = sorted(set(required) - available)
    if missing:
        raise PlanValidationError(f"{context} references missing columns: {missing}")


def _join_columns(left: set[str], right: set[str], step: JoinStep) -> set[str]:
    same_name_keys = {
        left_key
        for left_key, right_key in zip(step.left_on, step.right_on, strict=True)
        if left_key == right_key
    }
    overlapping = (left & right) - same_name_keys
    left_suffix = f"_{step.suffixes[0]}"
    right_suffix = f"_{step.suffixes[1]}"
    output = {f"{column}{left_suffix}" if column in overlapping else column for column in left}
    output.update(
        f"{column}{right_suffix}" if column in overlapping else column
        for column in right
        if column not in same_name_keys
    )
    return output


def validate_plan_against_catalog(
    plan: DeclarativeAnalysisPlan,
    assets: dict[str, DataAsset],
) -> None:
    """Statically validate asset and column references before any file is read."""

    tables: dict[str, set[str]] = {}
    for source in plan.sources:
        asset = assets.get(source.asset_id)
        if asset is None:
            raise PlanValidationError(f"source {source.alias!r} references an unknown asset_id")
        columns = set(asset.columns)
        _require_columns(columns, source.required_columns, f"source {source.alias!r}")
        tables[source.alias] = columns

    for index, step in enumerate(plan.preparation):
        context = f"preparation step {index} ({step.type})"
        if isinstance(step, JoinStep):
            left = tables[step.left_table]
            right = tables[step.right_table]
            _require_columns(left, step.left_on, context)
            _require_columns(right, step.right_on, context)
            output = _join_columns(left, right, step)
        elif isinstance(step, ConcatStep):
            inputs = [tables[name] for name in step.input_tables]
            output = set.intersection(*inputs) if step.join == "inner" else set.union(*inputs)
        else:
            columns = set(tables[step.input_table])
            if isinstance(step, FilterStep):
                _require_columns(columns, (item.column for item in step.predicates), context)
                output = columns
            elif isinstance(step, ProjectStep):
                _require_columns(columns, step.columns, context)
                output = set(step.columns)
            elif isinstance(step, RenameStep):
                _require_columns(columns, step.columns, context)
                output = {step.columns.get(column, column) for column in columns}
                if len(output) != len(columns):
                    raise PlanValidationError(f"{context} creates duplicate column names")
            elif isinstance(step, CastStep):
                _require_columns(columns, step.columns, context)
                output = columns
            elif isinstance(step, DeriveStep):
                operands = [step.left, step.right]
                operand_columns = [
                    operand.column for operand in operands if isinstance(operand, ColumnOperand)
                ]
                _require_columns(columns, operand_columns, context)
                if step.output_column in columns:
                    raise PlanValidationError(
                        f"{context} attempts to overwrite column {step.output_column!r}"
                    )
                output = columns | {step.output_column}
            elif isinstance(
                step,
                (
                    DropMissingStep,
                    DropDuplicatesStep,
                    ImputeStep,
                    StandardizeStringStep,
                ),
            ):
                _require_columns(columns, step.columns, context)
                output = columns
            elif isinstance(step, SortStep):
                _require_columns(columns, step.by, context)
                output = columns
            elif isinstance(step, TopKStep):
                _require_columns(columns, [step.by], context)
                output = columns
            elif isinstance(step, DropColumnsStep):
                _require_columns(columns, step.columns, context)
                output = columns - set(step.columns)
                if not output:
                    raise PlanValidationError(f"{context} cannot remove every column")
            elif isinstance(step, ExplodeStep):
                _require_columns(columns, step.columns, context)
                output = columns
            elif isinstance(step, SplitColumnStep):
                _require_columns(columns, [step.column], context)
                if len(step.into) != len(set(step.into)):
                    raise PlanValidationError(f"{context} creates duplicate column names")
                collisions = set(step.into) & columns
                if collisions:
                    raise PlanValidationError(
                        f"{context} attempts to overwrite columns: {sorted(collisions)}"
                    )
                output = columns | set(step.into)
            elif isinstance(step, ConcatenateColumnsStep):
                _require_columns(columns, step.columns, context)
                if step.output_column in columns:
                    raise PlanValidationError(
                        f"{context} attempts to overwrite column {step.output_column!r}"
                    )
                output = columns | {step.output_column}
            elif isinstance(step, GroupByStep):
                required = [
                    *step.group_by,
                    *(aggregation.column for aggregation in step.aggregations.values()),
                ]
                _require_columns(columns, required, context)
                if set(step.group_by) & set(step.aggregations):
                    raise PlanValidationError(
                        f"{context} aggregation names collide with grouping columns"
                    )
                output = set(step.group_by) | set(step.aggregations)
            elif isinstance(step, PivotStep):
                _require_columns(
                    columns,
                    [*step.index, step.columns, step.values],
                    context,
                )
                if len(step.output_columns) != len(set(step.output_columns)):
                    raise PlanValidationError(f"{context} output columns must be unique")
                output = set(step.output_columns)
            elif isinstance(step, MeltStep):
                _require_columns(columns, [*step.id_vars, *step.value_vars], context)
                if step.variable_name == step.value_name:
                    raise PlanValidationError(f"{context} variable_name and value_name must differ")
                if {step.variable_name, step.value_name} & set(step.id_vars):
                    raise PlanValidationError(
                        f"{context} output names collide with identifier columns"
                    )
                output = set(step.id_vars) | {step.variable_name, step.value_name}
            else:  # pragma: no cover - discriminated union exhaustiveness guard
                raise PlanValidationError(f"Unsupported preparation step: {type(step).__name__}")
        tables[step.output_table] = output

    for index, analysis in enumerate(plan.analyses):
        columns = tables[analysis.table]
        context = f"analysis {index} ({analysis.type})"
        if isinstance(analysis, AggregateAnalysis):
            _require_columns(
                columns,
                (predicate.column for predicate in analysis.predicates),
                context,
            )
            if analysis.function != AggregateFunction.COUNT_ROWS:
                _require_columns(columns, [analysis.column] if analysis.column else [], context)
        elif isinstance(analysis, GroupAggregateAnalysis):
            required = list(analysis.group_by)
            required.extend(predicate.column for predicate in analysis.predicates)
            if analysis.column is not None:
                required.append(analysis.column)
            _require_columns(columns, required, context)
        elif isinstance(analysis, DistinctAnalysis):
            _require_columns(columns, [analysis.column], context)
        elif isinstance(analysis, ExtremeRowAnalysis):
            _require_columns(columns, [analysis.order_by, *analysis.return_columns], context)
        elif isinstance(analysis, CorrelationAnalysis):
            _require_columns(columns, [analysis.x, analysis.y], context)
        elif isinstance(analysis, ShareAnalysis):
            predicates = [*analysis.numerator_predicates, *analysis.denominator_predicates]
            _require_columns(columns, (item.column for item in predicates), context)
        elif isinstance(analysis, RowsAnalysis):
            _require_columns(columns, [*analysis.columns, *analysis.order_by], context)
        elif isinstance(analysis, ArithmeticAnalysis):
            pass
        else:  # pragma: no cover - discriminated union exhaustiveness guard
            raise PlanValidationError(f"Unsupported analysis step: {type(analysis).__name__}")
