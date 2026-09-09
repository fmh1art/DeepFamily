from __future__ import annotations

import json
import math
import re
from collections.abc import Callable
from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from askdu.adapters.catalog import FileCatalog
from askdu.adapters.shsat_pilot import (
    AnalysisOutcome,
    PreparedBundle,
    ShsatPilotEngine,
    _frame_schema,
    _sha256,
)
from askdu.domain import (
    AggregateAnalysis,
    AggregateFunction,
    AnalysisArtifact,
    AnalyticalContract,
    ArithmeticAnalysis,
    ArithmeticOperator,
    CastStep,
    CastType,
    ConcatenateColumnsStep,
    ConcatStep,
    CorrelationAnalysis,
    DataAsset,
    DeclarativeAnalysisPlan,
    DeriveOperator,
    DeriveStep,
    DistinctAnalysis,
    DropColumnsStep,
    DropDuplicatesStep,
    DropMissingStep,
    EvidenceRef,
    ExplodeStep,
    ExtremeRowAnalysis,
    FilterPredicate,
    FilterStep,
    GroupAggregateAnalysis,
    GroupByStep,
    ImputeStep,
    JoinStep,
    MaterializedState,
    MeltStep,
    PivotStep,
    PredicateOperator,
    ProjectStep,
    RenameStep,
    Report,
    ReportClaim,
    ReportNarrative,
    ReportSection,
    RowsAnalysis,
    ShareAnalysis,
    SortStep,
    SplitColumnStep,
    Stage,
    StandardizeStringStep,
    SufficiencyViolation,
    TopKStep,
)
from askdu.domain.plans import ColumnOperand, LiteralOperand


class DeclarativeExecutionError(RuntimeError):
    """Raised when a validated plan violates a bounded runtime invariant."""


class AnalysisNotComputableError(ValueError):
    def __init__(self, analysis_name: str, reason: str) -> None:
        super().__init__(reason)
        self.analysis_name = analysis_name
        self.reason = reason


AnalysisStepObserver = Callable[[str, Any, Any, dict[str, Any]], None]


@dataclass(frozen=True)
class ExecutionLimits:
    max_total_source_bytes: int = 512 * 1024 * 1024
    max_rows_per_source: int = 2_000_000
    max_rows_per_table: int = 2_000_000
    max_columns_per_table: int = 512
    max_report_rows_per_analysis: int = 100


def format_declarative_answer(artifacts: list[AnalysisArtifact]) -> str:
    """Render the smallest stable answer string before any oracle is opened."""

    rendered: list[str] = []
    for artifact in artifacts:
        value = artifact.value
        rows = value if isinstance(value, list) else [value]
        rendered_rows: list[str] = []
        for row in rows:
            if isinstance(row, dict):
                apply_unit_to_all = len(row) == 1
                rendered_values = [
                    _format_answer_scalar(
                        item,
                        artifact,
                        apply_unit=apply_unit_to_all or key == "value",
                    )
                    for key, item in row.items()
                    if item is not None
                ]
            else:
                rendered_values = [_format_answer_scalar(row, artifact, apply_unit=True)]
            if rendered_values:
                rendered_rows.append(", ".join(rendered_values))
        if rendered_rows:
            rendered.append("; ".join(rendered_rows))
    return "; ".join(rendered)


def _format_answer_scalar(
    value: Any,
    artifact: AnalysisArtifact,
    *,
    apply_unit: bool,
) -> str:
    if isinstance(value, bool):
        return str(value).lower()
    is_number = isinstance(value, (int, float)) and not isinstance(value, bool)
    if isinstance(value, float) and artifact.display_precision is not None:
        rendered = f"{value:.{artifact.display_precision}f}"
    else:
        rendered = str(value)
    if apply_unit and is_number and artifact.unit == "%":
        return f"{rendered}%"
    if apply_unit and is_number and artifact.unit:
        return f"{rendered} {artifact.unit}"
    return rendered


class DeclarativeEngine(ShsatPilotEngine):
    """Execute a strict, non-Turing-complete dataframe plan over catalog assets."""

    def __init__(
        self,
        catalog: FileCatalog,
        runtime_root: Path,
        limits: ExecutionLimits | None = None,
    ) -> None:
        super().__init__(catalog, runtime_root)
        self.limits = limits or ExecutionLimits()

    def prepare(
        self,
        run_id: str,
        iteration: int,
        assets: list[DataAsset],
        contract: AnalyticalContract,
        parent_state_ids: list[str],
    ) -> PreparedBundle:
        plan = self._plan(contract)
        selected = {asset.asset_id: asset for asset in assets}
        missing_sources = [
            source.asset_id for source in plan.sources if source.asset_id not in selected
        ]
        if missing_sources:
            first = assets[0]
            frame = self._read_asset(first)
            return self._materialize(
                run_id,
                iteration,
                assets,
                parent_state_ids,
                frame,
                {
                    "planner": "declarative_v1",
                    "execution_deferred": True,
                    "missing_planned_source_ids": missing_sources,
                },
                tables={},
            )

        total_bytes = sum(asset.byte_size for asset in assets)
        if total_bytes > self.limits.max_total_source_bytes:
            raise DeclarativeExecutionError(
                f"planned sources total {total_bytes} bytes, above runtime limit"
            )
        workspace: dict[str, pd.DataFrame] = {}
        by_id = {asset.asset_id: asset for asset in assets}
        for source in plan.sources:
            workspace[source.alias] = self._read_asset(by_id[source.asset_id])
        for step in plan.preparation:
            output = self._execute_preparation_step(step, workspace)
            self._assert_table_limits(output, step.output_table)
            workspace[step.output_table] = output

        profiles = {
            name: {
                "rows": len(frame),
                "columns": [str(column) for column in frame.columns],
                "schema": _frame_schema(frame),
            }
            for name, frame in workspace.items()
        }
        primary = workspace[plan.primary_table]
        return self._materialize(
            run_id,
            iteration,
            assets,
            parent_state_ids,
            primary,
            {
                "planner": "declarative_v1",
                "execution_deferred": False,
                "executed_preparation_steps": len(plan.preparation),
                "primary_table": plan.primary_table,
                "table_profiles": profiles,
            },
            tables=workspace,
        )

    def analyze(
        self,
        run_id: str,
        bundle: PreparedBundle,
        contract: AnalyticalContract,
        observer: AnalysisStepObserver | None = None,
    ) -> AnalysisOutcome:
        plan = self._plan(contract)
        missing_sources = list(bundle.state.metrics.get("missing_planned_source_ids", []))
        if missing_sources:
            obligation = next(
                item for item in contract.obligations if item.check == "planned_sources_available"
            )
            missing_specs = [
                source for source in plan.sources if source.asset_id in missing_sources
            ]
            return AnalysisOutcome(
                artifacts=[],
                evidence=[],
                violation=SufficiencyViolation(
                    obligation_ids=[obligation.obligation_id],
                    type="missing_planned_sources",
                    observed={"selected_source_ids": list(bundle.state.source_ids)},
                    expected={
                        "required_source_ids": missing_sources,
                        "search_terms": [
                            term
                            for source in missing_specs
                            for term in [*source.required_columns, source.purpose]
                        ][:24],
                    },
                    detected_stage=Stage.PREPARATION,
                    responsible_stage=Stage.DISCOVERY,
                    evidence_refs=list(bundle.state.evidence_refs),
                ),
            )

        results: list[tuple[Any, Any]] = []
        computed: dict[str, Any] = {}
        try:
            for analysis in plan.analyses:
                if observer is not None:
                    observer("before", analysis, None, dict(computed))
                value = self._execute_analysis(analysis, bundle.tables, computed)
                computed[analysis.name] = value
                results.append((analysis, value))
                if observer is not None:
                    observer("after", analysis, self._json_safe(value), dict(computed))
        except AnalysisNotComputableError as exc:
            if observer is not None:
                observer("error", analysis, exc.reason, dict(computed))
            obligation_ids = [
                item.obligation_id
                for item in contract.obligations
                if item.expected.get("analysis_name") == exc.analysis_name
            ]
            return AnalysisOutcome(
                artifacts=[],
                evidence=[],
                violation=SufficiencyViolation(
                    obligation_ids=obligation_ids,
                    type="analysis_not_computable",
                    observed={"analysis_name": exc.analysis_name, "reason": exc.reason},
                    expected={"minimum_complete_results": 1},
                    detected_stage=Stage.ANALYSIS,
                    responsible_stage=Stage.DISCOVERY,
                    evidence_refs=list(bundle.state.evidence_refs),
                ),
            )
        except Exception as exc:
            if observer is not None:
                observer("error", analysis, f"{type(exc).__name__}: {exc}", dict(computed))
            raise

        payload = {
            "plan_schema_version": plan.schema_version,
            "results": {analysis.name: self._json_safe(value) for analysis, value in results},
        }
        evidence = self._write_analysis_evidence(
            run_id,
            "declarative_results.json",
            payload,
            "Results produced by the validated declarative analysis plan",
        )
        artifacts = [
            AnalysisArtifact(
                kind=self._artifact_kind(value),
                name=analysis.name,
                value=self._json_safe(value),
                unit=analysis.unit,
                display_precision=analysis.display_precision,
                source_state_ids=[bundle.state.state_id],
                evidence_refs=[evidence.ref_id],
            )
            for analysis, value in results
            if analysis.publish
        ]
        return AnalysisOutcome(artifacts=artifacts, evidence=[evidence])

    def render_report(
        self,
        run_id: str,
        question: str,
        assets: list[DataAsset],
        state: MaterializedState,
        artifacts: list[AnalysisArtifact],
        contract: AnalyticalContract,
        narrative: ReportNarrative | None = None,
    ) -> tuple[Report, EvidenceRef]:
        plan = self._plan(contract)
        claims: list[ReportClaim] = []
        for artifact in artifacts:
            label = artifact.name.replace("_", " ").strip().title()
            claims.append(
                ReportClaim(
                    text=f"{label}: {self._claim_value(artifact)}.",
                    value=artifact.value,
                    artifact_refs=[artifact.artifact_id],
                    evidence_refs=list(artifact.evidence_refs),
                )
            )

        effective_narrative = narrative or self._default_report_narrative(plan, artifacts)
        evidence_numbers = {
            artifact.artifact_id: index for index, artifact in enumerate(artifacts, start=1)
        }

        def evidence_links(refs: list[str]) -> str:
            numbers = dict.fromkeys(
                evidence_numbers[ref] for ref in refs if ref in evidence_numbers
            )
            return "**Evidence:** " + ", ".join(
                f"[E{number}](#evidence-{number})" for number in numbers
            )

        narrative_sections: list[str] = []
        for section in effective_narrative.sections:
            narrative_sections.extend([f"## {section.title}", "", section.narrative, ""])
            narrative_sections.extend([evidence_links(section.artifact_refs), ""])

        # Publish each result once. Prefixing a multiline table/fence with '- '
        # breaks Markdown block structure and duplicates evidence across sections.
        evidence_sections: list[str] = []
        for index, artifact in enumerate(artifacts, start=1):
            label = artifact.name.replace("_", " ").strip()
            label = label[:1].upper() + label[1:]
            evidence_sections.extend(
                [
                    f'<a id="evidence-{index}"></a>',
                    "",
                    f"### E{index} · {self._markdown_cell(label)}",
                    "",
                    self._render_value(artifact),
                    "",
                ]
            )
            if artifact.unit and isinstance(artifact.value, (dict, list)):
                evidence_sections.extend(
                    [f"Reported artifact unit: {self._markdown_cell(artifact.unit)}", ""]
                )

        markdown = "\n".join(
            [
                f"# {effective_narrative.title}",
                "",
                f"**Question.** {question}",
                "",
                "## Executive summary",
                "",
                effective_narrative.executive_summary,
                "",
                evidence_links(effective_narrative.executive_artifact_refs),
                "",
                *narrative_sections,
                "## Integrated conclusion",
                "",
                effective_narrative.conclusion,
                "",
                evidence_links(effective_narrative.conclusion_artifact_refs),
                "",
                "## Limitations",
                "",
                *(f"- {limitation}" for limitation in effective_narrative.limitations),
                "",
                "## Evidence results",
                "",
                "Displayed numbers may be rounded; "
                "exact artifact values remain in the evidence export.",
                "",
                *evidence_sections,
                "## Execution evidence",
                "",
                f"- Plan schema: `{plan.schema_version}`",
                f"- Prepared primary table: `{plan.primary_table}` ({state.row_count} rows)",
                f"- Materialized state: `{state.state_id}`",
                "",
                "## Sources",
                "",
                self._source_markdown(assets),
                "",
                "Every reported result links to a persisted execution artifact.",
            ]
        )
        report_dir = self.runtime_root / "runs" / run_id / "reports"
        report_dir.mkdir(parents=True, exist_ok=True)
        report_path = report_dir / "report.md"
        report_path.write_text(markdown, encoding="utf-8")
        evidence = EvidenceRef(
            kind="report",
            locator=f"runtime://{report_path.relative_to(self.runtime_root).as_posix()}",
            sha256=_sha256(report_path),
            description="Evidence-grounded Markdown report",
        )
        return (
            Report(
                title=effective_narrative.title,
                markdown=markdown,
                claims=claims,
                evidence_refs=[evidence.ref_id],
                executive_summary=effective_narrative.executive_summary,
                executive_artifact_refs=effective_narrative.executive_artifact_refs,
                sections=effective_narrative.sections,
                conclusion=effective_narrative.conclusion,
                conclusion_artifact_refs=effective_narrative.conclusion_artifact_refs,
                limitations=effective_narrative.limitations,
            ),
            evidence,
        )

    @staticmethod
    def _default_report_narrative(
        plan: DeclarativeAnalysisPlan,
        artifacts: list[AnalysisArtifact],
    ) -> ReportNarrative:
        refs = [artifact.artifact_id for artifact in artifacts]
        sections = [
            ReportSection(
                title=artifact.name.replace("_", " ").strip().title(),
                narrative=(
                    "This result was computed from the prepared table and retained as an "
                    "evidence-linked analysis artifact."
                ),
                artifact_refs=[artifact.artifact_id],
            )
            for artifact in artifacts
        ]
        return ReportNarrative(
            title=plan.report_title,
            executive_summary=(
                f"The workflow completed {len(artifacts)} requested analysis"
                f"{'es' if len(artifacts) != 1 else ''} over the prepared data."
            ),
            executive_artifact_refs=refs,
            sections=sections,
            conclusion=(
                "The executed results answer the defined analytical question within the "
                "available data scope."
            ),
            conclusion_artifact_refs=refs,
            limitations=[
                "The conclusion is limited to the authorized sources and executed dimensions."
            ],
        )

    def _read_asset(self, asset: DataAsset) -> pd.DataFrame:
        if asset.byte_size > self.limits.max_total_source_bytes:
            raise DeclarativeExecutionError(
                f"source {asset.asset_id} exceeds the per-run byte limit"
            )
        path = self.catalog.resolve(asset)
        if asset.file_format == "csv":
            frame = pd.read_csv(path, low_memory=False)
        elif asset.file_format == "tsv":
            frame = pd.read_csv(path, sep="\t", low_memory=False)
        elif asset.file_format == "jsonl":
            frame = pd.read_json(path, lines=True)
        elif asset.file_format == "json":
            frame = pd.read_json(path)
        elif asset.file_format == "parquet":
            frame = pd.read_parquet(path)
        elif asset.file_format in {"xlsx", "xls"}:
            frame = pd.read_excel(path)
        else:
            raise DeclarativeExecutionError(
                f"source {asset.asset_id} has unsupported format {asset.file_format!r}"
            )
        if len(frame) > self.limits.max_rows_per_source:
            raise DeclarativeExecutionError(f"source {asset.asset_id} exceeds the row limit")
        self._assert_table_limits(frame, asset.asset_id)
        return frame

    def _execute_preparation_step(
        self,
        step: Any,
        workspace: dict[str, pd.DataFrame],
    ) -> pd.DataFrame:
        if isinstance(step, FilterStep):
            frame = workspace[step.input_table]
            return frame.loc[self._predicate_mask(frame, step.predicates, step.combine)].copy()
        if isinstance(step, ProjectStep):
            return workspace[step.input_table].loc[:, step.columns].copy()
        if isinstance(step, RenameStep):
            return workspace[step.input_table].rename(columns=step.columns).copy()
        if isinstance(step, CastStep):
            frame = workspace[step.input_table].copy()
            for column, cast_type in step.columns.items():
                frame[column] = self._cast(frame[column], cast_type)
            return frame
        if isinstance(step, DeriveStep):
            frame = workspace[step.input_table].copy()
            frame[step.output_column] = self._derive(frame, step)
            return frame
        if isinstance(step, DropMissingStep):
            return workspace[step.input_table].dropna(subset=step.columns).copy()
        if isinstance(step, DropDuplicatesStep):
            return workspace[step.input_table].drop_duplicates(
                subset=step.columns,
                keep=step.keep,
            )
        if isinstance(step, JoinStep):
            left = workspace[step.left_table]
            right = workspace[step.right_table]
            projected_rows = self._project_join_rows(left, right, step)
            if projected_rows > self.limits.max_rows_per_table:
                raise DeclarativeExecutionError(
                    f"join {step.output_table!r} projects {projected_rows} rows above limit"
                )
            return left.merge(
                right,
                how=step.how,
                left_on=step.left_on,
                right_on=step.right_on,
                suffixes=(f"_{step.suffixes[0]}", f"_{step.suffixes[1]}"),
                sort=False,
            )
        if isinstance(step, ConcatStep):
            frames = [workspace[name] for name in step.input_tables]
            projected_rows = sum(len(frame) for frame in frames)
            if projected_rows > self.limits.max_rows_per_table:
                raise DeclarativeExecutionError(
                    f"concat {step.output_table!r} projects {projected_rows} rows above limit"
                )
            return pd.concat(frames, ignore_index=True, join=step.join, sort=False)
        if isinstance(step, ImputeStep):
            frame = workspace[step.input_table].copy()
            for column, specification in step.columns.items():
                series = frame[column]
                if specification.strategy == "constant":
                    replacement = specification.value
                elif specification.strategy == "mean":
                    numeric = pd.to_numeric(series, errors="coerce")
                    replacement = numeric.mean()
                    series = numeric
                elif specification.strategy == "median":
                    numeric = pd.to_numeric(series, errors="coerce")
                    replacement = numeric.median()
                    series = numeric
                else:
                    modes = series.mode(dropna=True)
                    if modes.empty:
                        raise DeclarativeExecutionError(
                            f"imputation column {column!r} has no observed mode"
                        )
                    replacement = modes.iloc[0]
                if pd.isna(replacement):
                    raise DeclarativeExecutionError(
                        f"imputation column {column!r} has no usable replacement"
                    )
                frame[column] = series.fillna(replacement)
            return frame
        if isinstance(step, StandardizeStringStep):
            frame = workspace[step.input_table].copy()
            for column in step.columns:
                series = frame[column].astype("string")
                if step.trim:
                    series = series.str.strip()
                if step.case == "lower":
                    series = series.str.lower()
                elif step.case == "upper":
                    series = series.str.upper()
                elif step.case == "title":
                    series = series.str.title()
                frame[column] = series
            return frame
        if isinstance(step, SortStep):
            return workspace[step.input_table].sort_values(
                step.by,
                ascending=step.ascending,
                na_position=step.na_position,
                kind="mergesort",
            )
        if isinstance(step, TopKStep):
            return (
                workspace[step.input_table]
                .sort_values(
                    step.by,
                    ascending=not step.largest,
                    na_position="last",
                    kind="mergesort",
                )
                .head(step.k)
                .copy()
            )
        if isinstance(step, DropColumnsStep):
            return workspace[step.input_table].drop(columns=step.columns).copy()
        if isinstance(step, ExplodeStep):
            return workspace[step.input_table].explode(
                step.columns,
                ignore_index=step.ignore_index,
            )
        if isinstance(step, SplitColumnStep):
            frame = workspace[step.input_table].copy()
            split = (
                frame[step.column]
                .astype("string")
                .str.split(
                    step.delimiter,
                    n=len(step.into) - 1,
                    expand=True,
                    regex=False,
                )
            )
            split = split.reindex(columns=range(len(step.into)))
            split.columns = step.into
            for column in step.into:
                frame[column] = split[column]
            return frame
        if isinstance(step, ConcatenateColumnsStep):
            frame = workspace[step.input_table].copy()
            values = frame.loc[:, step.columns].astype("string").fillna("")
            frame[step.output_column] = values.agg(step.separator.join, axis=1)
            return frame
        if isinstance(step, GroupByStep):
            named = {
                output: pd.NamedAgg(
                    column=aggregation.column,
                    aggfunc=aggregation.function,
                )
                for output, aggregation in step.aggregations.items()
            }
            return (
                workspace[step.input_table]
                .groupby(step.group_by, dropna=False, sort=True)
                .agg(**named)
                .reset_index()
            )
        if isinstance(step, PivotStep):
            pivoted = pd.pivot_table(
                workspace[step.input_table],
                index=step.index,
                columns=step.columns,
                values=step.values,
                aggfunc=step.aggregation,
                sort=True,
            ).reset_index()
            pivoted.columns = [
                "_".join(str(part) for part in column if str(part))
                if isinstance(column, tuple)
                else str(column)
                for column in pivoted.columns
            ]
            if set(pivoted.columns) != set(step.output_columns):
                raise DeclarativeExecutionError(
                    "pivot output columns differ from the declared output_columns"
                )
            return pivoted.loc[:, step.output_columns].copy()
        if isinstance(step, MeltStep):
            return workspace[step.input_table].melt(
                id_vars=step.id_vars,
                value_vars=step.value_vars,
                var_name=step.variable_name,
                value_name=step.value_name,
            )
        raise DeclarativeExecutionError(f"Unsupported preparation step: {type(step).__name__}")

    def _execute_analysis(
        self,
        analysis: Any,
        workspace: dict[str, pd.DataFrame],
        computed: dict[str, Any],
    ) -> Any:
        frame = workspace[analysis.table]
        if isinstance(analysis, AggregateAnalysis):
            filtered = frame.loc[
                self._predicate_mask(
                    frame,
                    analysis.predicates,
                    analysis.predicate_combine,
                )
            ]
            return self._aggregate(
                filtered,
                analysis.function,
                analysis.column,
                analysis.name,
            )
        if isinstance(analysis, GroupAggregateAnalysis):
            filtered = frame.loc[
                self._predicate_mask(
                    frame,
                    analysis.predicates,
                    analysis.predicate_combine,
                )
            ]
            grouped = filtered.groupby(analysis.group_by, dropna=False, sort=True)
            if analysis.function == AggregateFunction.COUNT_ROWS:
                grouped_values = grouped.size()
            else:
                assert analysis.column is not None
                series = filtered[analysis.column]
                if self._requires_numeric(analysis.function):
                    self._assert_numeric(series, analysis.name, analysis.column)
                grouped_column = grouped[analysis.column]
                if analysis.function == AggregateFunction.COUNT_NON_NULL:
                    grouped_values = grouped_column.count()
                elif analysis.function == AggregateFunction.NUNIQUE:
                    grouped_values = grouped_column.nunique(dropna=True)
                else:
                    grouped_values = grouped_column.agg(analysis.function.value)
            result = grouped_values.reset_index(name="value")
            result = result.sort_values(
                ["value", *analysis.group_by],
                ascending=[
                    analysis.sort_direction == "ascending",
                    *([True] * len(analysis.group_by)),
                ],
                kind="mergesort",
                na_position="last",
            ).head(analysis.limit)
            if result.empty:
                raise AnalysisNotComputableError(analysis.name, "grouped result is empty")
            if not analysis.include_aggregate_value:
                result = result.loc[:, analysis.group_by]
            return result.to_dict(orient="records")
        if isinstance(analysis, DistinctAnalysis):
            distinct_values = [
                self._json_safe(value) for value in frame[analysis.column].dropna().unique()
            ]
            distinct_values.sort(key=lambda value: str(value).casefold())
            if analysis.sort_direction == "descending":
                distinct_values.reverse()
            return distinct_values[: analysis.limit]
        if isinstance(analysis, ExtremeRowAnalysis):
            eligible = frame.dropna(subset=[analysis.order_by])
            if eligible.empty:
                raise AnalysisNotComputableError(analysis.name, "no non-null ordering values")
            index = (
                eligible[analysis.order_by].idxmin()
                if analysis.extreme == "minimum"
                else eligible[analysis.order_by].idxmax()
            )
            return {
                column: self._json_safe(eligible.loc[index, column])
                for column in analysis.return_columns
            }
        if isinstance(analysis, CorrelationAnalysis):
            complete = pd.DataFrame(
                {
                    "x": pd.to_numeric(frame[analysis.x], errors="coerce"),
                    "y": pd.to_numeric(frame[analysis.y], errors="coerce"),
                }
            ).dropna()
            if len(complete) < 2:
                raise AnalysisNotComputableError(analysis.name, "fewer than two complete pairs")
            value = float(complete["x"].corr(complete["y"], method=analysis.method))
            if not math.isfinite(value):
                raise AnalysisNotComputableError(analysis.name, "correlation is not finite")
            return value
        if isinstance(analysis, ShareAnalysis):
            denominator = self._predicate_mask(
                frame,
                analysis.denominator_predicates,
                analysis.denominator_combine,
            )
            numerator = denominator & self._predicate_mask(
                frame,
                analysis.numerator_predicates,
                analysis.numerator_combine,
            )
            denominator_count = int(denominator.sum())
            if denominator_count == 0:
                raise AnalysisNotComputableError(analysis.name, "denominator contains zero rows")
            value = float(numerator.sum()) / denominator_count
            return value * 100.0 if analysis.as_percentage else value
        if isinstance(analysis, RowsAnalysis):
            result = frame
            if analysis.order_by:
                result = result.sort_values(
                    analysis.order_by,
                    ascending=analysis.sort_direction == "ascending",
                    kind="mergesort",
                    na_position="last",
                )
            result = result.loc[:, analysis.columns].head(analysis.limit)
            return result.to_dict(orient="records")
        if isinstance(analysis, ArithmeticAnalysis):
            left = computed[analysis.left_analysis]
            right = computed[analysis.right_analysis]
            if not self._is_numeric_scalar(left) or not self._is_numeric_scalar(right):
                raise AnalysisNotComputableError(
                    analysis.name,
                    "arithmetic inputs must be numeric scalar analysis results",
                )
            if analysis.operator == ArithmeticOperator.ADD:
                value = float(left) + float(right)
            elif analysis.operator == ArithmeticOperator.SUBTRACT:
                value = float(left) - float(right)
            elif analysis.operator == ArithmeticOperator.MULTIPLY:
                value = float(left) * float(right)
            elif analysis.operator == ArithmeticOperator.DIVIDE:
                if float(right) == 0.0:
                    raise AnalysisNotComputableError(
                        analysis.name,
                        "arithmetic denominator is zero",
                    )
                value = float(left) / float(right)
            else:  # pragma: no cover - enum exhaustiveness guard
                raise DeclarativeExecutionError(
                    f"Unsupported arithmetic operator: {analysis.operator}"
                )
            value *= analysis.scale
            if not math.isfinite(value):
                raise AnalysisNotComputableError(
                    analysis.name,
                    "arithmetic result is not finite",
                )
            return value
        raise DeclarativeExecutionError(f"Unsupported analysis step: {type(analysis).__name__}")

    def _aggregate(
        self,
        frame: pd.DataFrame,
        function: AggregateFunction,
        column: str | None,
        analysis_name: str,
    ) -> Any:
        if function == AggregateFunction.COUNT_ROWS:
            return len(frame)
        assert column is not None
        series = frame[column]
        if function == AggregateFunction.COUNT_NON_NULL:
            return int(series.count())
        if function == AggregateFunction.NUNIQUE:
            return int(series.nunique(dropna=True))
        if self._requires_numeric(function):
            self._assert_numeric(series, analysis_name, column)
        complete = series.dropna()
        if complete.empty:
            raise AnalysisNotComputableError(
                analysis_name, f"column {column!r} has no complete values"
            )
        value = getattr(complete, function.value)()
        result = self._json_safe(value)
        if isinstance(result, float) and not math.isfinite(result):
            raise AnalysisNotComputableError(analysis_name, "aggregate result is not finite")
        return result

    def _predicate_mask(
        self,
        frame: pd.DataFrame,
        predicates: list[FilterPredicate],
        combine: str,
    ) -> pd.Series:
        if not predicates:
            return pd.Series(True, index=frame.index, dtype=bool)
        masks = [
            self._single_predicate(frame[predicate.column], predicate) for predicate in predicates
        ]
        result = masks[0]
        for mask in masks[1:]:
            result = result & mask if combine == "all" else result | mask
        return result.fillna(False).astype(bool)

    @staticmethod
    def _single_predicate(series: pd.Series, predicate: FilterPredicate) -> pd.Series:
        operator = predicate.operator
        value = predicate.value
        if operator == PredicateOperator.IS_NULL:
            return series.isna()
        if operator == PredicateOperator.NOT_NULL:
            return series.notna()
        if operator == PredicateOperator.CONTAINS:
            assert isinstance(value, str)
            return series.astype("string").str.contains(
                value,
                case=predicate.case_sensitive,
                regex=False,
                na=False,
            )
        if operator in {PredicateOperator.IN, PredicateOperator.NOT_IN}:
            assert isinstance(value, list)
            if predicate.case_sensitive or not all(isinstance(item, str) for item in value):
                mask = series.isin(value)
            else:
                normalized = {str(item).casefold() for item in value}
                mask = series.astype("string").str.casefold().isin(normalized)
            result = ~mask if operator == PredicateOperator.NOT_IN else mask
            return result & series.notna()
        assert not isinstance(value, list) and value is not None
        comparable = series
        target: Any = value
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            comparable = pd.to_numeric(series, errors="coerce")
        elif isinstance(value, str) and not predicate.case_sensitive:
            comparable = series.astype("string").str.casefold()
            target = value.casefold()
        operations = {
            PredicateOperator.EQ: comparable.eq,
            PredicateOperator.NE: comparable.ne,
            PredicateOperator.GT: comparable.gt,
            PredicateOperator.GTE: comparable.ge,
            PredicateOperator.LT: comparable.lt,
            PredicateOperator.LTE: comparable.le,
        }
        return operations[operator](target) & series.notna()

    @staticmethod
    def _cast(series: pd.Series, cast_type: CastType) -> pd.Series:
        if cast_type == CastType.NUMBER:
            return pd.to_numeric(series, errors="coerce")
        if cast_type == CastType.INTEGER:
            return pd.to_numeric(series, errors="coerce").astype("Int64")
        if cast_type == CastType.STRING:
            return series.astype("string")
        if cast_type == CastType.DATETIME:
            return pd.to_datetime(series, errors="coerce")
        if cast_type == CastType.BOOLEAN:
            normalized = series.astype("string").str.strip().str.casefold()
            return normalized.map(
                {
                    "true": True,
                    "yes": True,
                    "1": True,
                    "false": False,
                    "no": False,
                    "0": False,
                }
            ).astype("boolean")
        if cast_type == CastType.PERCENT_FRACTION:
            text = series.astype("string").str.strip()
            had_percent = text.str.contains("%", regex=False, na=False)
            numeric = pd.to_numeric(text.str.replace("%", "", regex=False), errors="coerce")
            non_null = numeric.dropna()
            if bool(had_percent.any()) or (
                not non_null.empty and float(non_null.abs().median()) > 1.0
            ):
                numeric = numeric / 100.0
            return numeric
        raise DeclarativeExecutionError(f"Unsupported cast: {cast_type}")

    def _derive(self, frame: pd.DataFrame, step: DeriveStep) -> Any:
        left = self._operand_value(frame, step.left)
        if step.operator == DeriveOperator.YEAR:
            return pd.to_datetime(left, errors="coerce").dt.year.astype("Int64")
        if step.operator == DeriveOperator.LOWER:
            return left.astype("string").str.lower()
        if step.operator == DeriveOperator.STRIP:
            return left.astype("string").str.strip()
        assert step.right is not None
        right = self._operand_value(frame, step.right)
        if step.operator == DeriveOperator.ADD:
            return left + right
        if step.operator == DeriveOperator.SUBTRACT:
            return left - right
        if step.operator == DeriveOperator.MULTIPLY:
            return left * right
        if step.operator == DeriveOperator.DIVIDE:
            denominator = right.replace(0, np.nan) if isinstance(right, pd.Series) else right
            if not isinstance(denominator, pd.Series) and denominator == 0:
                denominator = np.nan
            return left / denominator
        raise DeclarativeExecutionError(f"Unsupported derive operator: {step.operator}")

    @staticmethod
    def _operand_value(frame: pd.DataFrame, operand: Any) -> Any:
        if isinstance(operand, ColumnOperand):
            return frame[operand.column]
        if isinstance(operand, LiteralOperand):
            return operand.value
        raise DeclarativeExecutionError(f"Unsupported operand: {type(operand).__name__}")

    @staticmethod
    def _project_join_rows(left: pd.DataFrame, right: pd.DataFrame, step: JoinStep) -> int:
        left_counts = left.groupby(step.left_on, dropna=False).size().rename("left")
        right_counts = right.groupby(step.right_on, dropna=False).size().rename("right")
        common_names = [f"key_{index}" for index in range(len(step.left_on))]
        left_counts.index.names = common_names
        right_counts.index.names = common_names
        matched = left_counts.to_frame().join(right_counts.to_frame(), how="inner")
        matched_rows = int((matched["left"] * matched["right"]).sum())
        if step.how == "inner":
            return matched_rows
        left_matched = int(matched["left"].sum())
        right_matched = int(matched["right"].sum())
        left_unmatched = len(left) - left_matched
        right_unmatched = len(right) - right_matched
        if step.how == "left":
            return matched_rows + left_unmatched
        if step.how == "right":
            return matched_rows + right_unmatched
        return matched_rows + left_unmatched + right_unmatched

    @staticmethod
    def _requires_numeric(function: AggregateFunction) -> bool:
        return function in {
            AggregateFunction.SUM,
            AggregateFunction.MEAN,
            AggregateFunction.MEDIAN,
            AggregateFunction.STD,
            AggregateFunction.SKEW,
        }

    @staticmethod
    def _is_numeric_scalar(value: Any) -> bool:
        return isinstance(value, (int, float, np.integer, np.floating)) and not isinstance(
            value,
            (bool, np.bool_),
        )

    @staticmethod
    def _assert_numeric(series: pd.Series, analysis_name: str, column: str) -> None:
        if not pd.api.types.is_numeric_dtype(series):
            raise AnalysisNotComputableError(
                analysis_name,
                f"column {column!r} is not numeric; add an explicit cast step",
            )

    def _assert_table_limits(self, frame: pd.DataFrame, name: str) -> None:
        if len(frame) > self.limits.max_rows_per_table:
            raise DeclarativeExecutionError(f"table {name!r} exceeds the row limit")
        if len(frame.columns) > self.limits.max_columns_per_table:
            raise DeclarativeExecutionError(f"table {name!r} exceeds the column limit")

    @staticmethod
    def _artifact_kind(value: Any) -> str:
        if isinstance(value, list):
            return "table" if value and isinstance(value[0], dict) else "list"
        if isinstance(value, dict):
            return "record"
        return "scalar"

    @classmethod
    def _json_safe(cls, value: Any) -> Any:
        if value is None or value is pd.NA or value is pd.NaT:
            return None
        if isinstance(value, (np.integer,)):
            return int(value)
        if isinstance(value, (np.floating,)):
            result = float(value)
            return result if math.isfinite(result) else None
        if isinstance(value, (np.bool_,)):
            return bool(value)
        if isinstance(value, (pd.Timestamp,)):
            return value.isoformat()
        if isinstance(value, dict):
            return {str(key): cls._json_safe(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [cls._json_safe(item) for item in value]
        if isinstance(value, float) and not math.isfinite(value):
            return None
        return value

    @staticmethod
    def _render_value(artifact: AnalysisArtifact) -> str:
        value = artifact.value
        if isinstance(value, (dict, list)):
            if not value:
                return "No matching records." if isinstance(value, list) else "No recorded fields."
            records = [value] if isinstance(value, dict) else value
            if not all(isinstance(record, dict) for record in records):
                records = [{"Value": record} for record in records]
            # Use the union, not just the first row's keys: sparse result records
            # must not silently lose a column present only in subsequent rows.
            columns = list(dict.fromkeys(column for record in records for column in record))
            if not columns:
                return f"{len(records)} records with no recorded fields."
            rows = [
                "| "
                + " | ".join(
                    DeclarativeEngine._markdown_cell(
                        row.get(column), precision=artifact.display_precision
                    )
                    for column in columns
                )
                + " |"
                for row in records
            ]
            return "\n".join(
                [
                    "| "
                    + " | ".join(DeclarativeEngine._markdown_cell(column) for column in columns)
                    + " |",
                    "| " + " | ".join("---" for _ in columns) + " |",
                    *rows,
                ]
            )
        rendered = DeclarativeEngine._markdown_cell(value, precision=artifact.display_precision)
        unit = f" {DeclarativeEngine._markdown_cell(artifact.unit)}" if artifact.unit else ""
        return f"**{rendered}{unit}**"

    @staticmethod
    def _markdown_cell(value: Any, *, precision: int | None = None) -> str:
        if value is None or (isinstance(value, float) and not math.isfinite(value)):
            text = "Not available"
        elif isinstance(value, float):
            # General format removes binary-float noise without turning tiny
            # nonzero values into zero. Explicit display precision still wins.
            text = f"{value:.{precision}f}" if precision is not None else f"{value:.12g}"
        elif isinstance(value, (dict, list)):
            text = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        else:
            text = str(value)
        # Result values and column labels are data, not Markdown or HTML. This
        # also prevents table delimiters, code spans and remote images from
        # changing the structure when a downloaded report is rendered elsewhere.
        text = escape(text, quote=False).replace("\r\n", "\n").replace("\r", "\n")
        return re.sub(r"([\\`*_\[\]!|])", r"\\\1", text).replace("\n", "<br>")

    @staticmethod
    def _claim_value(artifact: AnalysisArtifact) -> str:
        if isinstance(artifact.value, (dict, list)):
            return json.dumps(artifact.value, ensure_ascii=False, separators=(",", ":"))[:500]
        if isinstance(artifact.value, float) and artifact.display_precision is not None:
            value = f"{artifact.value:.{artifact.display_precision}f}"
        else:
            value = str(artifact.value)
        return f"{value}{(' ' + artifact.unit) if artifact.unit else ''}"

    @staticmethod
    def _plan(contract: AnalyticalContract) -> DeclarativeAnalysisPlan:
        if contract.analysis_plan is None:
            raise DeclarativeExecutionError("Declarative contract has no analysis plan")
        return contract.analysis_plan
