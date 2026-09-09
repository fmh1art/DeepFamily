from __future__ import annotations

from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator
from typing_extensions import Self

Identifier = Annotated[
    str,
    StringConstraints(min_length=1, max_length=64, pattern=r"^[A-Za-z][A-Za-z0-9_]*$"),
]
ColumnName = Annotated[str, StringConstraints(min_length=1, max_length=256)]
Scalar = str | int | float | bool | None


class StrictPlanModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PredicateOperator(str, Enum):
    EQ = "eq"
    NE = "ne"
    GT = "gt"
    GTE = "gte"
    LT = "lt"
    LTE = "lte"
    IN = "in"
    NOT_IN = "not_in"
    CONTAINS = "contains"
    IS_NULL = "is_null"
    NOT_NULL = "not_null"


class FilterPredicate(StrictPlanModel):
    column: ColumnName
    operator: PredicateOperator
    value: Scalar | list[Scalar] = None
    case_sensitive: bool = False

    @model_validator(mode="after")
    def validate_value_shape(self) -> Self:
        nullary = {PredicateOperator.IS_NULL, PredicateOperator.NOT_NULL}
        membership = {PredicateOperator.IN, PredicateOperator.NOT_IN}
        if self.operator in nullary and self.value is not None:
            raise ValueError(f"{self.operator.value} does not accept a value")
        if self.operator in membership:
            if not isinstance(self.value, list) or not self.value:
                raise ValueError(f"{self.operator.value} requires a non-empty value list")
        elif self.operator not in nullary and (self.value is None or isinstance(self.value, list)):
            raise ValueError(f"{self.operator.value} requires one non-null scalar value")
        if self.operator == PredicateOperator.CONTAINS and not isinstance(self.value, str):
            raise ValueError("contains requires a string value")
        return self


class PlanSource(StrictPlanModel):
    alias: Identifier
    asset_id: Annotated[str, StringConstraints(pattern=r"^asset_[0-9a-f]{16}$")]
    required_columns: list[ColumnName] = Field(default_factory=list, max_length=64)
    purpose: Annotated[str, StringConstraints(min_length=1, max_length=240)]


class FilterStep(StrictPlanModel):
    type: Literal["filter"] = "filter"
    input_table: Identifier
    output_table: Identifier
    predicates: list[FilterPredicate] = Field(min_length=1, max_length=16)
    combine: Literal["all", "any"] = "all"


class ProjectStep(StrictPlanModel):
    type: Literal["project"] = "project"
    input_table: Identifier
    output_table: Identifier
    columns: list[ColumnName] = Field(min_length=1, max_length=64)


class RenameStep(StrictPlanModel):
    type: Literal["rename"] = "rename"
    input_table: Identifier
    output_table: Identifier
    columns: dict[ColumnName, ColumnName] = Field(min_length=1, max_length=32)


class CastType(str, Enum):
    NUMBER = "number"
    INTEGER = "integer"
    STRING = "string"
    DATETIME = "datetime"
    BOOLEAN = "boolean"
    PERCENT_FRACTION = "percent_fraction"


class CastStep(StrictPlanModel):
    type: Literal["cast"] = "cast"
    input_table: Identifier
    output_table: Identifier
    columns: dict[ColumnName, CastType] = Field(min_length=1, max_length=32)


class ColumnOperand(StrictPlanModel):
    kind: Literal["column"] = "column"
    column: ColumnName


class LiteralOperand(StrictPlanModel):
    kind: Literal["literal"] = "literal"
    value: str | int | float | bool


Operand = Annotated[ColumnOperand | LiteralOperand, Field(discriminator="kind")]


class DeriveOperator(str, Enum):
    ADD = "add"
    SUBTRACT = "subtract"
    MULTIPLY = "multiply"
    DIVIDE = "divide"
    YEAR = "year"
    LOWER = "lower"
    STRIP = "strip"


class DeriveStep(StrictPlanModel):
    type: Literal["derive"] = "derive"
    input_table: Identifier
    output_table: Identifier
    output_column: ColumnName
    operator: DeriveOperator
    left: Operand
    right: Operand | None = None

    @model_validator(mode="after")
    def validate_operands(self) -> Self:
        unary = {DeriveOperator.YEAR, DeriveOperator.LOWER, DeriveOperator.STRIP}
        if self.operator in unary and self.right is not None:
            raise ValueError(f"{self.operator.value} accepts only the left operand")
        if self.operator not in unary and self.right is None:
            raise ValueError(f"{self.operator.value} requires a right operand")
        if self.operator in unary and not isinstance(self.left, ColumnOperand):
            raise ValueError(f"{self.operator.value} requires a column operand")
        return self


class DropMissingStep(StrictPlanModel):
    type: Literal["drop_missing"] = "drop_missing"
    input_table: Identifier
    output_table: Identifier
    columns: list[ColumnName] = Field(min_length=1, max_length=32)


class DropDuplicatesStep(StrictPlanModel):
    type: Literal["drop_duplicates"] = "drop_duplicates"
    input_table: Identifier
    output_table: Identifier
    columns: list[ColumnName] = Field(min_length=1, max_length=16)
    keep: Literal["first", "last"] = "first"


class JoinStep(StrictPlanModel):
    type: Literal["join"] = "join"
    left_table: Identifier
    right_table: Identifier
    output_table: Identifier
    left_on: list[ColumnName] = Field(min_length=1, max_length=4)
    right_on: list[ColumnName] = Field(min_length=1, max_length=4)
    how: Literal["inner", "left", "right", "outer"] = "inner"
    suffixes: tuple[Identifier, Identifier] = ("left", "right")

    @model_validator(mode="after")
    def validate_join_keys(self) -> Self:
        if len(self.left_on) != len(self.right_on):
            raise ValueError("left_on and right_on must contain the same number of columns")
        if self.suffixes[0] == self.suffixes[1]:
            raise ValueError("join suffixes must differ")
        return self


class ConcatStep(StrictPlanModel):
    type: Literal["concat"] = "concat"
    input_tables: list[Identifier] = Field(min_length=2, max_length=8)
    output_table: Identifier
    join: Literal["inner", "outer"] = "outer"


class ImputationSpec(StrictPlanModel):
    strategy: Literal["constant", "mean", "median", "mode"]
    value: Scalar = None

    @model_validator(mode="after")
    def validate_constant(self) -> Self:
        if self.strategy == "constant" and self.value is None:
            raise ValueError("constant imputation requires a non-null value")
        if self.strategy != "constant" and self.value is not None:
            raise ValueError(f"{self.strategy} imputation does not accept a value")
        return self


class ImputeStep(StrictPlanModel):
    type: Literal["impute"] = "impute"
    input_table: Identifier
    output_table: Identifier
    columns: dict[ColumnName, ImputationSpec] = Field(min_length=1, max_length=32)


class StandardizeStringStep(StrictPlanModel):
    type: Literal["standardize_string"] = "standardize_string"
    input_table: Identifier
    output_table: Identifier
    columns: list[ColumnName] = Field(min_length=1, max_length=32)
    trim: bool = True
    case: Literal["preserve", "lower", "upper", "title"] = "preserve"


class SortStep(StrictPlanModel):
    type: Literal["sort"] = "sort"
    input_table: Identifier
    output_table: Identifier
    by: list[ColumnName] = Field(min_length=1, max_length=8)
    ascending: bool = True
    na_position: Literal["first", "last"] = "last"


class TopKStep(StrictPlanModel):
    type: Literal["top_k"] = "top_k"
    input_table: Identifier
    output_table: Identifier
    by: ColumnName
    k: int = Field(ge=1, le=10_000)
    largest: bool = True


class DropColumnsStep(StrictPlanModel):
    type: Literal["drop_columns"] = "drop_columns"
    input_table: Identifier
    output_table: Identifier
    columns: list[ColumnName] = Field(min_length=1, max_length=128)


class ExplodeStep(StrictPlanModel):
    type: Literal["explode"] = "explode"
    input_table: Identifier
    output_table: Identifier
    columns: list[ColumnName] = Field(min_length=1, max_length=8)
    ignore_index: bool = True


class SplitColumnStep(StrictPlanModel):
    type: Literal["split_column"] = "split_column"
    input_table: Identifier
    output_table: Identifier
    column: ColumnName
    into: list[ColumnName] = Field(min_length=2, max_length=16)
    delimiter: str = Field(min_length=1, max_length=32)


class ConcatenateColumnsStep(StrictPlanModel):
    type: Literal["concatenate_columns"] = "concatenate_columns"
    input_table: Identifier
    output_table: Identifier
    columns: list[ColumnName] = Field(min_length=2, max_length=16)
    output_column: ColumnName
    separator: str = Field(default=" ", max_length=32)


class PreparationAggregation(StrictPlanModel):
    column: ColumnName
    function: Literal["count", "nunique", "sum", "mean", "median", "min", "max", "std"]


class GroupByStep(StrictPlanModel):
    type: Literal["group_by"] = "group_by"
    input_table: Identifier
    output_table: Identifier
    group_by: list[ColumnName] = Field(min_length=1, max_length=8)
    aggregations: dict[Identifier, PreparationAggregation] = Field(min_length=1, max_length=32)


class PivotStep(StrictPlanModel):
    type: Literal["pivot"] = "pivot"
    input_table: Identifier
    output_table: Identifier
    index: list[ColumnName] = Field(min_length=1, max_length=8)
    columns: ColumnName
    values: ColumnName
    aggregation: Literal["sum", "mean", "median", "min", "max", "count"] = "sum"
    output_columns: list[ColumnName] = Field(min_length=2, max_length=256)


class MeltStep(StrictPlanModel):
    type: Literal["melt"] = "melt"
    input_table: Identifier
    output_table: Identifier
    id_vars: list[ColumnName] = Field(min_length=1, max_length=32)
    value_vars: list[ColumnName] = Field(min_length=1, max_length=128)
    variable_name: ColumnName = "variable"
    value_name: ColumnName = "value"


PreparationStep = Annotated[
    FilterStep
    | ProjectStep
    | RenameStep
    | CastStep
    | DeriveStep
    | DropMissingStep
    | DropDuplicatesStep
    | JoinStep
    | ConcatStep
    | ImputeStep
    | StandardizeStringStep
    | SortStep
    | TopKStep
    | DropColumnsStep
    | ExplodeStep
    | SplitColumnStep
    | ConcatenateColumnsStep
    | GroupByStep
    | PivotStep
    | MeltStep,
    Field(discriminator="type"),
]


class AggregateFunction(str, Enum):
    COUNT_ROWS = "count_rows"
    COUNT_NON_NULL = "count_non_null"
    NUNIQUE = "nunique"
    SUM = "sum"
    MEAN = "mean"
    MEDIAN = "median"
    MIN = "min"
    MAX = "max"
    STD = "std"
    SKEW = "skew"


class AnalysisBase(StrictPlanModel):
    name: Identifier
    table: Identifier
    unit: Annotated[str, StringConstraints(max_length=32)] | None = None
    display_precision: int | None = Field(default=None, ge=0, le=12)
    publish: bool = True


class AggregateAnalysis(AnalysisBase):
    type: Literal["aggregate"] = "aggregate"
    function: AggregateFunction
    column: ColumnName | None = None
    predicates: list[FilterPredicate] = Field(default_factory=list, max_length=16)
    predicate_combine: Literal["all", "any"] = "all"

    @model_validator(mode="after")
    def validate_column(self) -> Self:
        if self.function == AggregateFunction.COUNT_ROWS and self.column is not None:
            raise ValueError("count_rows does not accept a column")
        if self.function != AggregateFunction.COUNT_ROWS and self.column is None:
            raise ValueError(f"{self.function.value} requires a column")
        return self


class GroupAggregateAnalysis(AnalysisBase):
    type: Literal["group_aggregate"] = "group_aggregate"
    group_by: list[ColumnName] = Field(min_length=1, max_length=3)
    function: AggregateFunction
    column: ColumnName | None = None
    sort_direction: Literal["ascending", "descending"] = "descending"
    limit: int = Field(default=10, ge=1, le=100)
    include_aggregate_value: bool = True
    predicates: list[FilterPredicate] = Field(default_factory=list, max_length=16)
    predicate_combine: Literal["all", "any"] = "all"

    @model_validator(mode="after")
    def validate_column(self) -> Self:
        if self.function == AggregateFunction.COUNT_ROWS and self.column is not None:
            raise ValueError("count_rows does not accept a column")
        if self.function != AggregateFunction.COUNT_ROWS and self.column is None:
            raise ValueError(f"{self.function.value} requires a column")
        return self


class DistinctAnalysis(AnalysisBase):
    type: Literal["distinct"] = "distinct"
    column: ColumnName
    sort_direction: Literal["ascending", "descending"] = "ascending"
    limit: int = Field(default=100, ge=1, le=100)


class ExtremeRowAnalysis(AnalysisBase):
    type: Literal["extreme_row"] = "extreme_row"
    extreme: Literal["minimum", "maximum"]
    order_by: ColumnName
    return_columns: list[ColumnName] = Field(min_length=1, max_length=16)


class CorrelationAnalysis(AnalysisBase):
    type: Literal["correlation"] = "correlation"
    x: ColumnName
    y: ColumnName
    method: Literal["pearson", "spearman"] = "pearson"


class ShareAnalysis(AnalysisBase):
    type: Literal["share"] = "share"
    numerator_predicates: list[FilterPredicate] = Field(min_length=1, max_length=16)
    numerator_combine: Literal["all", "any"] = "all"
    denominator_predicates: list[FilterPredicate] = Field(default_factory=list, max_length=16)
    denominator_combine: Literal["all", "any"] = "all"
    as_percentage: bool = True


class RowsAnalysis(AnalysisBase):
    type: Literal["rows"] = "rows"
    columns: list[ColumnName] = Field(min_length=1, max_length=16)
    order_by: list[ColumnName] = Field(default_factory=list, max_length=4)
    sort_direction: Literal["ascending", "descending"] = "ascending"
    limit: int = Field(default=20, ge=1, le=100)


class ArithmeticOperator(str, Enum):
    ADD = "add"
    SUBTRACT = "subtract"
    MULTIPLY = "multiply"
    DIVIDE = "divide"


class ArithmeticAnalysis(AnalysisBase):
    type: Literal["arithmetic"] = "arithmetic"
    left_analysis: Identifier
    right_analysis: Identifier
    operator: ArithmeticOperator
    scale: float = Field(default=1.0, gt=-1_000_000_000, lt=1_000_000_000)


AnalysisStep = Annotated[
    ArithmeticAnalysis
    | AggregateAnalysis
    | GroupAggregateAnalysis
    | DistinctAnalysis
    | ExtremeRowAnalysis
    | CorrelationAnalysis
    | ShareAnalysis
    | RowsAnalysis,
    Field(discriminator="type"),
]


class DeclarativeAnalysisPlan(StrictPlanModel):
    schema_version: Literal["1.0"] = "1.0"
    summary: Annotated[str, StringConstraints(min_length=1, max_length=500)]
    search_terms: list[Annotated[str, StringConstraints(min_length=1, max_length=128)]] = Field(
        min_length=1,
        max_length=20,
    )
    sources: list[PlanSource] = Field(min_length=1, max_length=8)
    preparation: list[PreparationStep] = Field(default_factory=list, max_length=24)
    analyses: list[AnalysisStep] = Field(min_length=1, max_length=12)
    primary_table: Identifier
    report_title: Annotated[str, StringConstraints(min_length=1, max_length=120)]

    @model_validator(mode="after")
    def validate_graph(self) -> Self:
        source_aliases = [source.alias for source in self.sources]
        if len(source_aliases) != len(set(source_aliases)):
            raise ValueError("source aliases must be unique")

        available = set(source_aliases)
        for index, step in enumerate(self.preparation):
            if isinstance(step, JoinStep):
                inputs = [step.left_table, step.right_table]
            elif isinstance(step, ConcatStep):
                inputs = list(step.input_tables)
            else:
                inputs = [step.input_table]
            missing = [name for name in inputs if name not in available]
            if missing:
                raise ValueError(
                    f"preparation step {index} references unavailable tables: {missing}"
                )
            if step.output_table in available:
                raise ValueError(
                    f"preparation step {index} attempts to overwrite table {step.output_table!r}"
                )
            available.add(step.output_table)

        if self.primary_table not in available:
            raise ValueError(f"primary_table {self.primary_table!r} is unavailable")
        analysis_names = [analysis.name for analysis in self.analyses]
        if len(analysis_names) != len(set(analysis_names)):
            raise ValueError("analysis names must be unique")
        if not any(analysis.publish for analysis in self.analyses):
            raise ValueError("at least one analysis must be published")
        unavailable = sorted({analysis.table for analysis in self.analyses} - available)
        if unavailable:
            raise ValueError(f"analyses reference unavailable tables: {unavailable}")
        non_primary = sorted(
            {analysis.table for analysis in self.analyses if analysis.table != self.primary_table}
        )
        if non_primary:
            raise ValueError(
                "every analysis must read primary_table so artifact lineage references the "
                f"materialized analytical state; non-primary tables: {non_primary}"
            )
        preceding: set[str] = set()
        for analysis in self.analyses:
            if isinstance(analysis, ArithmeticAnalysis):
                missing_inputs = {
                    analysis.left_analysis,
                    analysis.right_analysis,
                } - preceding
                if missing_inputs:
                    raise ValueError(
                        f"arithmetic analysis {analysis.name!r} must reference prior analyses; "
                        f"unavailable inputs: {sorted(missing_inputs)}"
                    )
            preceding.add(analysis.name)
        return self
