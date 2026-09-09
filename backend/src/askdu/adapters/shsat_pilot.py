from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from askdu.adapters.catalog import FileCatalog
from askdu.application.compiler import (
    SHSAT_CORRELATION_FAMILY,
    SHSAT_ECONOMIC_NEED_COUNT_FAMILY,
    SHSAT_OFFER_DEMOGRAPHICS_FAMILY,
)
from askdu.domain import (
    AnalysisArtifact,
    AnalyticalContract,
    AnalyticalObligation,
    DataAsset,
    EvidenceRef,
    MaterializedState,
    ObligationStatus,
    ObligationType,
    Report,
    ReportClaim,
    Stage,
    SufficiencyViolation,
)

TARGET_COLUMN = "Number of students who took the SHSAT"
ECONOMIC_NEED_COLUMN = "Economic Need Index"
OFFER_COUNT_COLUMN = "Number of students who received offer"
OFFER_TEST_COLUMN = "Number of students who took test"
DEMOGRAPHIC_COLUMNS = ["Percent Asian", "Percent Black / Hispanic", "Percent White"]
OFFER_DEMOGRAPHIC_COLUMNS = [
    "Percent Black / Hispanic",
    "Percent White",
    "Percent Asian",
]
REGISTRATION_COLUMNS = {
    "DBN",
    "School name",
    "Year of SHST",
    "Grade level",
    TARGET_COLUMN,
}
OFFER_COLUMNS = {"School DBN", OFFER_TEST_COLUMN, OFFER_COUNT_COLUMN}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _frame_schema(frame: pd.DataFrame) -> dict[str, str]:
    """Return the executed dataframe schema using bounded, JSON-safe strings."""

    return {str(column): str(dtype) for column, dtype in frame.dtypes.items()}


def _frame_preview(frame: pd.DataFrame, rows: int = 5) -> list[dict[str, Any]]:
    """Serialize a small table preview without leaking pandas-only scalar types."""

    payload = frame.head(rows).to_json(orient="records", date_format="iso")
    preview = json.loads(payload)
    if not isinstance(preview, list):  # pragma: no cover - pandas orient invariant
        raise TypeError("dataframe preview did not serialize to records")
    return preview


@dataclass
class PreparedBundle:
    frame: pd.DataFrame
    state: MaterializedState
    evidence: list[EvidenceRef]
    tables: dict[str, pd.DataFrame] = field(default_factory=dict)


@dataclass
class AnalysisOutcome:
    artifacts: list[AnalysisArtifact]
    evidence: list[EvidenceRef]
    violation: SufficiencyViolation | None = None


class ShsatPilotEngine:
    """Executable adapters for three CoDA SHSAT tasks.

    The engine reads source tables and never sees benchmark answers. It is
    intentionally task-family scoped while the lifecycle contract stabilizes.
    """

    def __init__(self, catalog: FileCatalog, runtime_root: Path):
        self.catalog = catalog
        self.runtime_root = runtime_root.expanduser().resolve()

    def prepare(
        self,
        run_id: str,
        iteration: int,
        assets: list[DataAsset],
        contract: AnalyticalContract,
        parent_state_ids: list[str],
    ) -> PreparedBundle:
        if contract.task_family in {
            SHSAT_CORRELATION_FAMILY,
            SHSAT_ECONOMIC_NEED_COUNT_FAMILY,
        }:
            return self._prepare_registration_task(
                run_id,
                iteration,
                assets,
                contract,
                parent_state_ids,
            )
        if contract.task_family == SHSAT_OFFER_DEMOGRAPHICS_FAMILY:
            return self._prepare_offer_task(
                run_id,
                iteration,
                assets,
                parent_state_ids,
            )
        raise ValueError(f"Unsupported task family: {contract.task_family}")

    def analyze(
        self,
        run_id: str,
        bundle: PreparedBundle,
        contract: AnalyticalContract,
    ) -> AnalysisOutcome:
        missing_outcome = self._missing_columns_outcome(bundle, contract)
        if missing_outcome is not None:
            return missing_outcome

        if contract.task_family == SHSAT_CORRELATION_FAMILY:
            return self._analyze_correlations(run_id, bundle, contract)
        if contract.task_family == SHSAT_ECONOMIC_NEED_COUNT_FAMILY:
            return self._analyze_final_count(run_id, bundle)
        if contract.task_family == SHSAT_OFFER_DEMOGRAPHICS_FAMILY:
            return self._analyze_offer_demographics(run_id, bundle, contract)
        raise ValueError(f"Unsupported task family: {contract.task_family}")

    def render_report(
        self,
        run_id: str,
        question: str,
        assets: list[DataAsset],
        state: MaterializedState,
        artifacts: list[AnalysisArtifact],
        contract: AnalyticalContract,
    ) -> tuple[Report, EvidenceRef]:
        if contract.task_family == SHSAT_CORRELATION_FAMILY:
            title, markdown, claims = self._correlation_report(question, assets, state, artifacts)
        elif contract.task_family == SHSAT_ECONOMIC_NEED_COUNT_FAMILY:
            title, markdown, claims = self._count_report(question, assets, state, artifacts)
        elif contract.task_family == SHSAT_OFFER_DEMOGRAPHICS_FAMILY:
            title, markdown, claims = self._offer_report(question, assets, state, artifacts)
        else:
            raise ValueError(f"Unsupported task family: {contract.task_family}")

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
        report = Report(
            title=title,
            markdown=markdown,
            claims=claims,
            evidence_refs=[evidence.ref_id],
        )
        return report, evidence

    def _prepare_registration_task(
        self,
        run_id: str,
        iteration: int,
        assets: list[DataAsset],
        contract: AnalyticalContract,
        parent_state_ids: list[str],
    ) -> PreparedBundle:
        registration_asset = self._asset_with_columns(assets, REGISTRATION_COLUMNS)
        if registration_asset is None:
            raise ValueError("Selected sources do not contain an SHSAT registration table")

        registration = pd.read_csv(self.catalog.resolve(registration_asset))
        input_rows = len(registration)
        if contract.task_family == SHSAT_ECONOMIC_NEED_COUNT_FAMILY:
            registration = registration.drop_duplicates(subset=["School name", "Year of SHST"])
        coverage = self._coverage_obligation(contract)
        year = int(coverage.expected["year"])
        grade = int(coverage.expected["grade"])
        frame = registration.loc[
            (pd.to_numeric(registration["Year of SHST"], errors="coerce") == year)
            & (pd.to_numeric(registration["Grade level"], errors="coerce") == grade)
        ].copy()
        metrics: dict[str, Any] = {
            "input_registration_rows": input_rows,
            "deduplicated_registration_rows": len(registration),
            "filtered_year": year,
            "filtered_grade": grade,
            "registration_rows": len(frame),
        }

        required_school_columns = (
            {"Location Code", ECONOMIC_NEED_COLUMN}
            if contract.task_family == SHSAT_ECONOMIC_NEED_COUNT_FAMILY
            else {"Location Code", *DEMOGRAPHIC_COLUMNS}
        )
        school_asset = self._asset_with_columns(assets, required_school_columns)
        if school_asset is not None:
            schools = pd.read_csv(self.catalog.resolve(school_asset))
            selected_columns = ["Location Code"]
            if contract.task_family == SHSAT_CORRELATION_FAMILY:
                for column in DEMOGRAPHIC_COLUMNS:
                    schools[column] = self._percentage_to_fraction(schools[column])
                selected_columns.extend(DEMOGRAPHIC_COLUMNS)
            else:
                schools[ECONOMIC_NEED_COLUMN] = pd.to_numeric(
                    schools[ECONOMIC_NEED_COLUMN], errors="coerce"
                )
                selected_columns.append(ECONOMIC_NEED_COLUMN)

            frame = frame.merge(
                schools[selected_columns],
                how="left",
                left_on="DBN",
                right_on="Location Code",
                validate="many_to_one",
                indicator=True,
            )
            matched = int((frame["_merge"] == "both").sum())
            metrics.update(
                {
                    "join_left_rows": len(frame),
                    "join_matched_rows": matched,
                    "join_coverage": matched / len(frame) if len(frame) else 0.0,
                    "join_keys": ["DBN", "Location Code"],
                }
            )
            frame = frame.drop(columns=["_merge"])
            if contract.task_family == SHSAT_ECONOMIC_NEED_COUNT_FAMILY:
                frame = frame.loc[frame[ECONOMIC_NEED_COLUMN].notna()].copy()
                metrics["rows_after_missing_value_filter"] = len(frame)

        return self._materialize(run_id, iteration, assets, parent_state_ids, frame, metrics)

    def _prepare_offer_task(
        self,
        run_id: str,
        iteration: int,
        assets: list[DataAsset],
        parent_state_ids: list[str],
    ) -> PreparedBundle:
        offer_asset = self._asset_with_columns(assets, OFFER_COLUMNS)
        if offer_asset is None:
            raise ValueError("Selected sources do not contain an SHSAT offer table")
        offers = pd.read_csv(self.catalog.resolve(offer_asset))
        frame = offers.dropna(subset=[OFFER_TEST_COLUMN, OFFER_COUNT_COLUMN]).copy()
        metrics: dict[str, Any] = {
            "input_offer_rows": len(offers),
            "eligible_offer_rows": len(frame),
        }

        school_columns = {"Location Code", "City", *OFFER_DEMOGRAPHIC_COLUMNS}
        school_asset = self._asset_with_columns(assets, school_columns)
        if school_asset is not None:
            schools = pd.read_csv(self.catalog.resolve(school_asset))
            for column in OFFER_DEMOGRAPHIC_COLUMNS:
                schools[column] = self._percentage_to_fraction(schools[column])
            frame = frame.merge(
                schools[["Location Code", "City", *OFFER_DEMOGRAPHIC_COLUMNS]],
                how="left",
                left_on="School DBN",
                right_on="Location Code",
                validate="many_to_one",
                indicator=True,
            )
            matched = int((frame["_merge"] == "both").sum())
            metrics.update(
                {
                    "join_left_rows": len(frame),
                    "join_matched_rows": matched,
                    "join_coverage": matched / len(frame) if len(frame) else 0.0,
                    "join_keys": ["School DBN", "Location Code"],
                }
            )
            frame = frame.loc[frame["City"].notna()].drop(columns=["_merge"]).copy()
            metrics["analysis_rows"] = len(frame)

        return self._materialize(run_id, iteration, assets, parent_state_ids, frame, metrics)

    def _materialize(
        self,
        run_id: str,
        iteration: int,
        assets: list[DataAsset],
        parent_state_ids: list[str],
        frame: pd.DataFrame,
        metrics: dict[str, Any],
        tables: dict[str, pd.DataFrame] | None = None,
    ) -> PreparedBundle:
        state = MaterializedState(
            iteration=iteration,
            parent_state_ids=parent_state_ids,
            source_ids=[asset.asset_id for asset in assets],
            row_count=len(frame),
            columns=[str(column) for column in frame.columns],
            column_schema=_frame_schema(frame),
            preview_rows=_frame_preview(frame),
            metrics=metrics,
        )
        state_dir = self.runtime_root / "runs" / run_id / "states"
        state_dir.mkdir(parents=True, exist_ok=True)
        state_path = state_dir / f"{state.state_id}.csv"
        frame.to_csv(state_path, index=False)
        evidence = EvidenceRef(
            kind="materialized_table",
            locator=f"runtime://{state_path.relative_to(self.runtime_root).as_posix()}",
            sha256=_sha256(state_path),
            description=f"Prepared table for iteration {iteration}",
        )
        state.evidence_refs.append(evidence.ref_id)
        return PreparedBundle(
            frame=frame,
            state=state,
            evidence=[evidence],
            tables=tables or {},
        )

    @staticmethod
    def _missing_columns_outcome(
        bundle: PreparedBundle,
        contract: AnalyticalContract,
    ) -> AnalysisOutcome | None:
        required_columns = [
            str(obligation.expected["column"])
            for obligation in contract.obligations
            if obligation.type in {ObligationType.MEASURE, ObligationType.DIMENSION}
            and "column" in obligation.expected
        ]
        missing_columns = [column for column in required_columns if column not in bundle.frame]
        if not missing_columns:
            return None
        obligation_ids = [
            obligation.obligation_id
            for obligation in contract.obligations
            if obligation.expected.get("column") in missing_columns
        ]
        return AnalysisOutcome(
            artifacts=[],
            evidence=[],
            violation=SufficiencyViolation(
                obligation_ids=obligation_ids,
                type="missing_analytical_columns",
                observed={"available_columns": list(bundle.frame.columns)},
                expected={"required_columns": missing_columns},
                detected_stage=Stage.ANALYSIS,
                responsible_stage=Stage.DISCOVERY,
                evidence_refs=list(bundle.state.evidence_refs),
            ),
        )

    def _analyze_correlations(
        self,
        run_id: str,
        bundle: PreparedBundle,
        contract: AnalyticalContract,
    ) -> AnalysisOutcome:
        analysis_frame = bundle.frame[[TARGET_COLUMN, *DEMOGRAPHIC_COLUMNS]].copy()
        for column in analysis_frame:
            analysis_frame[column] = pd.to_numeric(analysis_frame[column], errors="coerce")

        correlations: dict[str, float] = {}
        complete_counts: dict[str, int] = {}
        for column in DEMOGRAPHIC_COLUMNS:
            complete = analysis_frame[[TARGET_COLUMN, column]].dropna()
            complete_counts[column] = len(complete)
            if len(complete) < 2:
                return self._statistical_violation(
                    contract,
                    bundle,
                    column,
                    len(complete),
                    minimum=2,
                )
            correlations[column] = float(complete[TARGET_COLUMN].corr(complete[column]))

        evidence = self._write_analysis_evidence(
            run_id,
            "pearson_correlations.json",
            {"correlations": correlations, "complete_pair_counts": complete_counts},
            "Executed Pearson correlation results and complete-pair counts",
        )
        artifacts = [
            AnalysisArtifact(
                kind="scalar",
                name=f"pearson_{self._slug(column)}",
                value=value,
                display_precision=6,
                source_state_ids=[bundle.state.state_id],
                evidence_refs=[evidence.ref_id],
            )
            for column, value in correlations.items()
        ]
        return AnalysisOutcome(artifacts=artifacts, evidence=[evidence])

    def _analyze_final_count(
        self,
        run_id: str,
        bundle: PreparedBundle,
    ) -> AnalysisOutcome:
        final_count = len(bundle.frame)
        evidence = self._write_analysis_evidence(
            run_id,
            "final_record_count.json",
            {
                "final_record_count": final_count,
                "filters": {"year": 2016, "grade": 8, "economic_need_index": "not null"},
            },
            "Executed final record count after filtering and joining",
        )
        artifact = AnalysisArtifact(
            kind="scalar",
            name="final_record_count",
            value=final_count,
            unit="records",
            display_precision=0,
            source_state_ids=[bundle.state.state_id],
            evidence_refs=[evidence.ref_id],
        )
        return AnalysisOutcome(artifacts=[artifact], evidence=[evidence])

    def _analyze_offer_demographics(
        self,
        run_id: str,
        bundle: PreparedBundle,
        contract: AnalyticalContract,
    ) -> AnalysisOutcome:
        means: dict[str, float] = {}
        complete_counts: dict[str, int] = {}
        for column in OFFER_DEMOGRAPHIC_COLUMNS:
            values = pd.to_numeric(bundle.frame[column], errors="coerce").dropna()
            complete_counts[column] = len(values)
            if len(values) < 1:
                return self._statistical_violation(
                    contract,
                    bundle,
                    column,
                    len(values),
                    minimum=1,
                )
            means[column] = float(values.mean() * 100.0)

        evidence = self._write_analysis_evidence(
            run_id,
            "offer_demographic_means.json",
            {"means_percent": means, "complete_value_counts": complete_counts},
            "Executed demographic means for schools with recorded SHSAT offers",
        )
        artifacts = [
            AnalysisArtifact(
                kind="scalar",
                name=f"mean_{self._slug(column)}",
                value=value,
                unit="%",
                display_precision=2,
                source_state_ids=[bundle.state.state_id],
                evidence_refs=[evidence.ref_id],
            )
            for column, value in means.items()
        ]
        return AnalysisOutcome(artifacts=artifacts, evidence=[evidence])

    def _write_analysis_evidence(
        self,
        run_id: str,
        filename: str,
        payload: dict[str, Any],
        description: str,
    ) -> EvidenceRef:
        analysis_dir = self.runtime_root / "runs" / run_id / "artifacts"
        analysis_dir.mkdir(parents=True, exist_ok=True)
        analysis_path = analysis_dir / filename
        analysis_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return EvidenceRef(
            kind="analysis_result",
            locator=f"runtime://{analysis_path.relative_to(self.runtime_root).as_posix()}",
            sha256=_sha256(analysis_path),
            description=description,
        )

    @staticmethod
    def _statistical_violation(
        contract: AnalyticalContract,
        bundle: PreparedBundle,
        column: str,
        observed_count: int,
        minimum: int,
    ) -> AnalysisOutcome:
        statistical_ids = [
            obligation.obligation_id
            for obligation in contract.obligations
            if obligation.type == ObligationType.STATISTICAL
        ]
        return AnalysisOutcome(
            artifacts=[],
            evidence=[],
            violation=SufficiencyViolation(
                obligation_ids=statistical_ids,
                type="insufficient_complete_values",
                observed={"column": column, "complete_values": observed_count},
                expected={"minimum": minimum},
                detected_stage=Stage.ANALYSIS,
                responsible_stage=Stage.DISCOVERY,
                evidence_refs=list(bundle.state.evidence_refs),
            ),
        )

    @staticmethod
    def _correlation_report(
        question: str,
        assets: list[DataAsset],
        state: MaterializedState,
        artifacts: list[AnalysisArtifact],
    ) -> tuple[str, str, list[ReportClaim]]:
        labels = {
            "pearson_percent_asian": "Asian",
            "pearson_percent_black_hispanic": "Black/Hispanic",
            "pearson_percent_white": "White",
        }
        claims: list[ReportClaim] = []
        result_lines: list[str] = []
        for artifact in artifacts:
            label = labels[artifact.name]
            value = float(artifact.value)
            result_lines.append(f"| {label} | {value:.6f} |")
            claims.append(
                ReportClaim(
                    text=(
                        "The Pearson correlation between SHSAT test-taker count and "
                        f"the {label} student percentage is {value:.6f}."
                    ),
                    value=value,
                    artifact_refs=[artifact.artifact_id],
                    evidence_refs=list(artifact.evidence_refs),
                )
            )
        sources = ShsatPilotEngine._source_markdown(assets)
        markdown = "\n".join(
            [
                "# SHSAT participation and school demographics",
                "",
                f"**Question.** {question}",
                "",
                "## Result",
                "",
                "| Demographic percentage | Pearson correlation |",
                "|---|---:|",
                *result_lines,
                "",
                "## Data sufficiency evidence",
                "",
                f"- Prepared rows: {state.row_count}",
                f"- Join coverage: {float(state.metrics.get('join_coverage', 0.0)):.1%}",
                "- Joined on: `DBN` ↔ `Location Code`",
                "",
                "## Sources",
                "",
                sources,
                "",
                "Every numeric claim above references the executed correlation artifact.",
            ]
        )
        return "SHSAT participation and school demographics", markdown, claims

    @staticmethod
    def _count_report(
        question: str,
        assets: list[DataAsset],
        state: MaterializedState,
        artifacts: list[AnalysisArtifact],
    ) -> tuple[str, str, list[ReportClaim]]:
        artifact = artifacts[0]
        value = int(artifact.value)
        claim = ReportClaim(
            text=(
                "After deduplication, filtering to 2016 and Grade 8, joining school "
                "metadata, and removing missing Economic Need Index values, "
                f"{value} records remain."
            ),
            value=value,
            artifact_refs=[artifact.artifact_id],
            evidence_refs=list(artifact.evidence_refs),
        )
        markdown = "\n".join(
            [
                "# SHSAT records with Economic Need Index",
                "",
                f"**Question.** {question}",
                "",
                "## Result",
                "",
                f"**Final record count: {value}.**",
                "",
                "## Data sufficiency evidence",
                "",
                f"- Prepared rows: {state.row_count}",
                f"- Join coverage: {float(state.metrics.get('join_coverage', 0.0)):.1%}",
                "- Joined on: `DBN` ↔ `Location Code`",
                "",
                "## Sources",
                "",
                ShsatPilotEngine._source_markdown(assets),
                "",
                "The count references the executed filtered-table artifact.",
            ]
        )
        return "SHSAT records with Economic Need Index", markdown, [claim]

    @staticmethod
    def _offer_report(
        question: str,
        assets: list[DataAsset],
        state: MaterializedState,
        artifacts: list[AnalysisArtifact],
    ) -> tuple[str, str, list[ReportClaim]]:
        labels = {
            "mean_percent_black_hispanic": "Black/Hispanic",
            "mean_percent_white": "White",
            "mean_percent_asian": "Asian",
        }
        claims: list[ReportClaim] = []
        result_lines: list[str] = []
        for artifact in artifacts:
            label = labels[artifact.name]
            value = float(artifact.value)
            result_lines.append(f"| {label} | {value:.2f}% |")
            claims.append(
                ReportClaim(
                    text=(
                        f"The average {label} student percentage among schools with "
                        f"recorded SHSAT offers is {value:.2f}%."
                    ),
                    value=value,
                    artifact_refs=[artifact.artifact_id],
                    evidence_refs=list(artifact.evidence_refs),
                )
            )
        markdown = "\n".join(
            [
                "# Demographics of schools with SHSAT offers",
                "",
                f"**Question.** {question}",
                "",
                "## Result",
                "",
                "| Demographic group | Average percentage |",
                "|---|---:|",
                *result_lines,
                "",
                "## Data sufficiency evidence",
                "",
                f"- Prepared rows: {state.row_count}",
                f"- Join coverage: {float(state.metrics.get('join_coverage', 0.0)):.1%}",
                "- Joined on: `School DBN` ↔ `Location Code`",
                "",
                "## Sources",
                "",
                ShsatPilotEngine._source_markdown(assets),
                "",
                "Every numeric claim above references the executed mean artifact.",
            ]
        )
        return "Demographics of schools with SHSAT offers", markdown, claims

    @staticmethod
    def _source_markdown(assets: list[DataAsset]) -> str:
        lines: list[str] = []
        for asset in assets:
            digest = asset.sha256 or "unprofiled"
            provenance = asset.provenance
            if provenance is None:
                lines.append(
                    f"- `{asset.relative_path}` — SHA-256 `{digest}`; provenance "
                    "unregistered; no license inferred."
                )
                continue

            title = ShsatPilotEngine._markdown_label(provenance.title)
            provider = ShsatPilotEngine._markdown_label(provenance.provider)
            creator = ShsatPilotEngine._markdown_label(provenance.creator)
            license_label = ShsatPilotEngine._markdown_label(provenance.license_label)
            license_text = (
                f"[{license_label}]({provenance.license_url})"
                if provenance.license_url is not None
                else license_label
            )
            lines.append(
                f"- [{title}]({provenance.source_url}) — `{asset.relative_path}`; "
                f"provider: {provider}; creator: {creator}; license metadata: "
                f"{license_text} ({provenance.license_status}); SHA-256 `{digest}`; "
                "integrity "
                f"{asset.integrity_status}; {provenance.redistribution_policy.replace('_', '-')}."
            )
        return "\n".join(lines)

    @staticmethod
    def _markdown_label(value: str) -> str:
        return value.replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]")

    @staticmethod
    def _asset_with_columns(
        assets: list[DataAsset], required_columns: set[str]
    ) -> DataAsset | None:
        return next(
            (asset for asset in assets if required_columns.issubset(set(asset.columns))),
            None,
        )

    @staticmethod
    def _coverage_obligation(contract: AnalyticalContract) -> AnalyticalObligation:
        return next(
            obligation
            for obligation in contract.obligations
            if obligation.type == ObligationType.COVERAGE
        )

    @staticmethod
    def _percentage_to_fraction(series: pd.Series) -> pd.Series:
        cleaned = series.astype("string").str.replace("%", "", regex=False).str.strip()
        numeric = pd.to_numeric(cleaned, errors="coerce")
        non_null = numeric.dropna()
        if not non_null.empty and float(non_null.abs().median()) > 1.0:
            numeric = numeric / 100.0
        return numeric

    @staticmethod
    def _slug(column: str) -> str:
        return "_".join(
            part
            for part in "".join(
                character.lower() if character.isalnum() else " " for character in column
            ).split()
        )


def mark_analysis_obligations_satisfied(
    contract: AnalyticalContract, state: MaterializedState
) -> None:
    for obligation in contract.obligations:
        if obligation.type in {
            ObligationType.MEASURE,
            ObligationType.DIMENSION,
            ObligationType.COVERAGE,
            ObligationType.GRAIN,
            ObligationType.STATISTICAL,
            ObligationType.EVIDENCE,
        }:
            obligation.status = ObligationStatus.SATISFIED
            obligation.evidence_refs.extend(state.evidence_refs)
        elif obligation.type == ObligationType.JOIN:
            minimum = float(obligation.expected.get("minimum_coverage", 0.0))
            observed = float(state.metrics.get("join_coverage", 0.0))
            obligation.status = (
                ObligationStatus.SATISFIED if observed >= minimum else ObligationStatus.VIOLATED
            )
            obligation.evidence_refs.extend(state.evidence_refs)
