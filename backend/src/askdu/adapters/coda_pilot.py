from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from askdu.adapters.catalog import FileCatalog
from askdu.adapters.shsat_pilot import (
    AnalysisOutcome,
    PreparedBundle,
    ShsatPilotEngine,
    _sha256,
)
from askdu.application.compiler import (
    ATTENDANCE_BY_GRADE_FAMILY,
    BURGER_CALORIE_EXTREMES_FAMILY,
    COMMUNITY_SCHOOL_PROFILE_FAMILY,
    SCHOOL_ABSENTEEISM_PROFILE_FAMILY,
    SCHOOL_CITY_COUNTS_FAMILY,
    SCHOOL_NEED_DEMOGRAPHIC_CORRELATIONS_FAMILY,
    SCHOOL_PROFICIENCY_DEMOGRAPHICS_FAMILY,
    SCHOOL_TYPE_SHARE_FAMILY,
    SHSAT_CORRELATION_FAMILY,
    SHSAT_ECONOMIC_NEED_COUNT_FAMILY,
    SHSAT_GRADE_LEVEL_COUNT_FAMILY,
    SHSAT_LOW_RATIO_SCHOOLS_FAMILY,
    SHSAT_MIN_RATIO_FAMILY,
    SHSAT_OFFER_DEMOGRAPHICS_FAMILY,
    SHSAT_PEAK_REGISTRATION_FAMILY,
    SINGLE_SOURCE_REQUIRED_COLUMNS,
    UNEMPLOYMENT_NEGATIVE_SKEW_SHARE_FAMILY,
    WAGE_SKEW_DIRECTION_SHARE_FAMILY,
)
from askdu.domain import (
    AnalysisArtifact,
    AnalyticalContract,
    DataAsset,
    EvidenceRef,
    MaterializedState,
    ObligationType,
    Report,
    ReportClaim,
    RunState,
    RunStatus,
    Stage,
    SufficiencyViolation,
)

CORE_SHSAT_FAMILIES = {
    SHSAT_CORRELATION_FAMILY,
    SHSAT_ECONOMIC_NEED_COUNT_FAMILY,
    SHSAT_OFFER_DEMOGRAPHICS_FAMILY,
}

FAMILY_TITLES = {
    SHSAT_MIN_RATIO_FAMILY: "Minimum SHSAT participation ratio",
    SHSAT_GRADE_LEVEL_COUNT_FAMILY: "SHSAT grade-level coverage",
    SCHOOL_TYPE_SHARE_FAMILY: "Charter and Community Schools",
    ATTENDANCE_BY_GRADE_FAMILY: "Attendance by grade",
    SHSAT_LOW_RATIO_SCHOOLS_FAMILY: "Schools with low SHSAT participation",
    SCHOOL_NEED_DEMOGRAPHIC_CORRELATIONS_FAMILY: ("Economic need and school demographics"),
    SCHOOL_CITY_COUNTS_FAMILY: "Cities with the most schools",
    SHSAT_PEAK_REGISTRATION_FAMILY: "Peak SHSAT registration year",
    BURGER_CALORIE_EXTREMES_FAMILY: "Burger calorie extremes",
    SCHOOL_ABSENTEEISM_PROFILE_FAMILY: "Absenteeism, economic need, and income",
    SCHOOL_PROFICIENCY_DEMOGRAPHICS_FAMILY: ("Proficiency by Black/Hispanic population share"),
    COMMUNITY_SCHOOL_PROFILE_FAMILY: "Community School profile",
    UNEMPLOYMENT_NEGATIVE_SKEW_SHARE_FAMILY: "Negative skew after yearly averaging",
    WAGE_SKEW_DIRECTION_SHARE_FAMILY: "Wage attribute skewness",
}

ARTIFACT_LABELS = {
    "minimum_participation_ratio": "Minimum test-taker/registrant ratio",
    "distinct_grade_levels": "Distinct grade levels",
    "charter_school_count": "Charter Schools",
    "community_school_count": "Community Schools",
    "combined_school_share": "Combined share",
    "pre_k_attendance": "Pre-Kindergarten attendance",
    "grade_5_attendance": "Grade 5 attendance",
    "grade_9_attendance": "Grade 9 attendance",
    "low_ratio_school_names": "Schools with ratio between 0 and 0.2",
    "pearson_economic_need_percent_asian": "Economic need vs. Asian",
    "pearson_economic_need_percent_black_hispanic": ("Economic need vs. Black/Hispanic"),
    "pearson_economic_need_percent_white": "Economic need vs. White",
    "top_city_1": "Top city 1",
    "top_city_1_school_count": "Top city 1 count",
    "top_city_2": "Top city 2",
    "top_city_2_school_count": "Top city 2 count",
    "top_city_3": "Top city 3",
    "top_city_3_school_count": "Top city 3 count",
    "peak_registration_year": "Peak registration year",
    "peak_registration_count": "Peak registration total",
    "highest_calorie_item": "Highest-calorie burger",
    "highest_calorie_count": "Highest calorie count",
    "lowest_shake_shack_item": "Lowest-calorie Shake Shack burger",
    "high_absenteeism_economic_need": "High-absenteeism Economic Need Index",
    "high_absenteeism_income": "High-absenteeism income",
    "low_absenteeism_economic_need": "Low-absenteeism Economic Need Index",
    "low_absenteeism_income": "Low-absenteeism income",
    "high_black_hispanic_ela": "ELA, >=70% Black/Hispanic",
    "high_black_hispanic_math": "Math, >=70% Black/Hispanic",
    "low_black_hispanic_ela": "ELA, <=30% Black/Hispanic",
    "low_black_hispanic_math": "Math, <=30% Black/Hispanic",
    "community_school_income": "Community School income",
    "community_school_black_hispanic": "Community School Black/Hispanic share",
    "non_community_school_income": "Non-Community School income",
    "non_community_school_black_hispanic": ("Non-Community School Black/Hispanic share"),
    "negative_skew_share_after_yearly_averaging": (
        "Negatively skewed attributes after yearly averaging"
    ),
    "positive_skew_attribute_share": "Positively skewed wage attributes",
    "negative_skew_attribute_share": "Negatively skewed wage attributes",
}


@dataclass(frozen=True)
class ResultValue:
    name: str
    value: Any
    unit: str | None = None
    precision: int | None = None


class CodaPilotEngine(ShsatPilotEngine):
    """Trusted operators for the revision-pinned CoDA pilot communities.

    The engine never receives benchmark answers. Task-specific operators are
    intentionally explicit so that controller and discovery experiments are
    deterministic; they are evaluation scaffolding, not a general planner.
    """

    def __init__(self, catalog: FileCatalog, runtime_root: Path):
        super().__init__(catalog, runtime_root)

    def prepare(
        self,
        run_id: str,
        iteration: int,
        assets: list[DataAsset],
        contract: AnalyticalContract,
        parent_state_ids: list[str],
    ) -> PreparedBundle:
        if contract.task_family in CORE_SHSAT_FAMILIES:
            return super().prepare(
                run_id,
                iteration,
                assets,
                contract,
                parent_state_ids,
            )
        if contract.task_family == BURGER_CALORIE_EXTREMES_FAMILY:
            return self._prepare_burgers(
                run_id,
                iteration,
                assets,
                parent_state_ids,
            )
        if contract.task_family in SINGLE_SOURCE_REQUIRED_COLUMNS:
            return self._prepare_single_source(
                run_id,
                iteration,
                assets,
                contract,
                parent_state_ids,
            )
        raise ValueError(f"Unsupported task family: {contract.task_family}")

    def analyze(
        self,
        run_id: str,
        bundle: PreparedBundle,
        contract: AnalyticalContract,
    ) -> AnalysisOutcome:
        if contract.task_family in CORE_SHSAT_FAMILIES:
            return super().analyze(run_id, bundle, contract)

        missing_outcome = self._missing_columns_outcome(bundle, contract)
        if missing_outcome is not None:
            return missing_outcome
        if contract.task_family == BURGER_CALORIE_EXTREMES_FAMILY:
            coverage_outcome = self._burger_coverage_outcome(bundle, contract)
            if coverage_outcome is not None:
                return coverage_outcome

        analyzers: dict[
            str,
            Callable[[str, PreparedBundle, AnalyticalContract], AnalysisOutcome],
        ] = {
            SHSAT_MIN_RATIO_FAMILY: self._analyze_minimum_ratio,
            SHSAT_GRADE_LEVEL_COUNT_FAMILY: self._analyze_grade_levels,
            SCHOOL_TYPE_SHARE_FAMILY: self._analyze_school_types,
            ATTENDANCE_BY_GRADE_FAMILY: self._analyze_attendance,
            SHSAT_LOW_RATIO_SCHOOLS_FAMILY: self._analyze_low_ratio_schools,
            SCHOOL_NEED_DEMOGRAPHIC_CORRELATIONS_FAMILY: (
                self._analyze_need_demographic_correlations
            ),
            SCHOOL_CITY_COUNTS_FAMILY: self._analyze_city_counts,
            SHSAT_PEAK_REGISTRATION_FAMILY: self._analyze_peak_registration,
            BURGER_CALORIE_EXTREMES_FAMILY: self._analyze_burger_extremes,
            SCHOOL_ABSENTEEISM_PROFILE_FAMILY: self._analyze_absenteeism_profile,
            SCHOOL_PROFICIENCY_DEMOGRAPHICS_FAMILY: (self._analyze_proficiency_demographics),
            COMMUNITY_SCHOOL_PROFILE_FAMILY: self._analyze_community_school_profile,
            UNEMPLOYMENT_NEGATIVE_SKEW_SHARE_FAMILY: (
                self._analyze_unemployment_negative_skew_share
            ),
            WAGE_SKEW_DIRECTION_SHARE_FAMILY: self._analyze_wage_skew_direction_share,
        }
        analyzer = analyzers.get(contract.task_family)
        if analyzer is None:
            raise ValueError(f"Unsupported task family: {contract.task_family}")
        return analyzer(run_id, bundle, contract)

    def render_report(
        self,
        run_id: str,
        question: str,
        assets: list[DataAsset],
        state: MaterializedState,
        artifacts: list[AnalysisArtifact],
        contract: AnalyticalContract,
    ) -> tuple[Report, EvidenceRef]:
        if contract.task_family in CORE_SHSAT_FAMILIES:
            return super().render_report(
                run_id,
                question,
                assets,
                state,
                artifacts,
                contract,
            )

        title = FAMILY_TITLES[contract.task_family]
        rows: list[str] = []
        claims: list[ReportClaim] = []
        for artifact in artifacts:
            label = ARTIFACT_LABELS.get(artifact.name, artifact.name.replace("_", " "))
            rendered = self._format_artifact(artifact)
            rows.append(f"| {label} | {rendered} |")
            claims.append(
                ReportClaim(
                    text=f"{label}: {rendered}.",
                    value=artifact.value,
                    artifact_refs=[artifact.artifact_id],
                    evidence_refs=list(artifact.evidence_refs),
                )
            )
        markdown = "\n".join(
            [
                f"# {title}",
                "",
                f"**Question.** {question}",
                "",
                "## Result",
                "",
                "| Measure | Executed result |",
                "|---|---:|",
                *rows,
                "",
                "## Data sufficiency evidence",
                "",
                f"- Prepared rows: {state.row_count}",
                f"- Materialized state: {state.state_id}",
                "",
                "## Sources",
                "",
                self._source_markdown(assets),
                "",
                "Every result above references the executed analysis artifact.",
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
                title=title,
                markdown=markdown,
                claims=claims,
                evidence_refs=[evidence.ref_id],
            ),
            evidence,
        )

    def _prepare_single_source(
        self,
        run_id: str,
        iteration: int,
        assets: list[DataAsset],
        contract: AnalyticalContract,
        parent_state_ids: list[str],
    ) -> PreparedBundle:
        required = set(SINGLE_SOURCE_REQUIRED_COLUMNS[contract.task_family])
        chosen = max(
            assets,
            key=lambda asset: (
                len(required & set(asset.columns)),
                -asset.byte_size,
                asset.relative_path,
            ),
        )
        frame = pd.read_csv(self.catalog.resolve(chosen))
        metrics: dict[str, Any] = {
            "input_rows": len(frame),
            "active_source_id": chosen.asset_id,
            "required_column_coverage": (
                len(required & set(frame.columns)) / len(required) if required else 1.0
            ),
        }
        return self._materialize(
            run_id,
            iteration,
            assets,
            parent_state_ids,
            frame,
            metrics,
        )

    def _prepare_burgers(
        self,
        run_id: str,
        iteration: int,
        assets: list[DataAsset],
        parent_state_ids: list[str],
    ) -> PreparedBundle:
        frames: list[pd.DataFrame] = []
        source_rows: dict[str, int] = {}
        for asset in assets:
            columns = set(asset.columns)
            if {"Category", "Menu", "Calories"}.issubset(columns):
                raw = pd.read_csv(self.catalog.resolve(asset))
                shake = raw.loc[
                    raw["Category"].eq("Burgers"),
                    ["Menu", "Calories"],
                ].head(35)
                normalized = pd.DataFrame(
                    {
                        "restaurant": "Shake Shack",
                        "item": shake["Menu"].astype("string"),
                        "calories": pd.to_numeric(shake["Calories"], errors="coerce"),
                    }
                )
            elif {"restaurant", "item", "calories"}.issubset(columns):
                raw = pd.read_csv(self.catalog.resolve(asset))
                candidates = raw.loc[
                    raw["restaurant"]
                    .astype("string")
                    .str.contains(
                        "Mcdonalds|Burger King",
                        case=False,
                        na=False,
                    )
                    & raw["item"]
                    .astype("string")
                    .str.contains(
                        "burger|whopper|mac|quarter pounder|king",
                        case=False,
                        na=False,
                    ),
                    ["restaurant", "item", "calories"],
                ].copy()
                candidates["calories"] = pd.to_numeric(
                    candidates["calories"],
                    errors="coerce",
                )
                normalized = candidates
            else:
                continue
            normalized = normalized.dropna(subset=["restaurant", "item", "calories"])
            frames.append(normalized)
            source_rows[asset.asset_id] = len(normalized)
        frame = (
            pd.concat(frames, ignore_index=True)
            if frames
            else pd.DataFrame(columns=["restaurant", "item", "calories"])
        )
        metrics: dict[str, Any] = {
            "eligible_rows_by_source": source_rows,
            "restaurant_coverage": sorted(
                str(value) for value in frame["restaurant"].dropna().unique()
            ),
        }
        return self._materialize(
            run_id,
            iteration,
            assets,
            parent_state_ids,
            frame,
            metrics,
        )

    @staticmethod
    def _burger_coverage_outcome(
        bundle: PreparedBundle,
        contract: AnalyticalContract,
    ) -> AnalysisOutcome | None:
        obligation = next(
            item for item in contract.obligations if item.type == ObligationType.COVERAGE
        )
        required = {str(value).casefold() for value in obligation.expected["required_categories"]}
        observed = {str(value).casefold() for value in bundle.frame["restaurant"].dropna().unique()}
        missing = sorted(required - observed)
        if not missing:
            return None
        return AnalysisOutcome(
            artifacts=[],
            evidence=[],
            violation=SufficiencyViolation(
                obligation_ids=[obligation.obligation_id],
                type="missing_category_coverage",
                observed={"available_categories": sorted(observed)},
                expected={
                    "required_categories": missing,
                    "search_terms": [*missing, "restaurant", "item", "calories"],
                },
                detected_stage=Stage.ANALYSIS,
                responsible_stage=Stage.DISCOVERY,
                evidence_refs=list(bundle.state.evidence_refs),
            ),
        )

    def _analyze_minimum_ratio(
        self,
        run_id: str,
        bundle: PreparedBundle,
        contract: AnalyticalContract,
    ) -> AnalysisOutcome:
        registered = pd.to_numeric(
            bundle.frame["Number of students who registered for the SHSAT"],
            errors="coerce",
        )
        took = pd.to_numeric(
            bundle.frame["Number of students who took the SHSAT"],
            errors="coerce",
        )
        ratios = (took / registered).loc[lambda values: values > 0].dropna()
        if ratios.empty:
            return self._statistical_violation(contract, bundle, "ratio", 0, 1)
        denominator = round(1.0 / float(ratios.min()))
        return self._result_outcome(
            run_id,
            bundle,
            "minimum_participation_ratio.json",
            [ResultValue("minimum_participation_ratio", f"1 out of {denominator}")],
        )

    def _analyze_grade_levels(
        self,
        run_id: str,
        bundle: PreparedBundle,
        contract: AnalyticalContract,
    ) -> AnalysisOutcome:
        count = int(bundle.frame["Grade level"].nunique(dropna=True))
        if count == 0:
            return self._statistical_violation(contract, bundle, "Grade level", 0, 1)
        return self._result_outcome(
            run_id,
            bundle,
            "distinct_grade_levels.json",
            [ResultValue("distinct_grade_levels", count, "levels", 0)],
        )

    def _analyze_school_types(
        self,
        run_id: str,
        bundle: PreparedBundle,
        contract: AnalyticalContract,
    ) -> AnalysisOutcome:
        names = bundle.frame["School Name"].astype("string")
        charter_count = int(names.str.contains("charter school", case=False, na=False).sum())
        community_count = int(bundle.frame["Community School?"].eq("Yes").sum())
        total = len(bundle.frame)
        if total == 0:
            return self._statistical_violation(contract, bundle, "School Name", 0, 1)
        combined_share = round((charter_count + community_count) / total * 100)
        return self._result_outcome(
            run_id,
            bundle,
            "school_type_share.json",
            [
                ResultValue("charter_school_count", charter_count, "schools", 0),
                ResultValue("community_school_count", community_count, "schools", 0),
                ResultValue("combined_school_share", combined_share, "%", 0),
            ],
        )

    def _analyze_attendance(
        self,
        run_id: str,
        bundle: PreparedBundle,
        contract: AnalyticalContract,
    ) -> AnalysisOutcome:
        results = []
        for name, column in (
            ("pre_k_attendance", "ATTPCTPRK"),
            ("grade_5_attendance", "ATTPCTG05"),
            ("grade_9_attendance", "ATTPCTG09"),
        ):
            values = pd.to_numeric(bundle.frame[column], errors="coerce").dropna()
            if values.empty:
                return self._statistical_violation(contract, bundle, column, 0, 1)
            results.append(ResultValue(name, float(values.mean()), "%", 2))
        return self._result_outcome(run_id, bundle, "attendance_by_grade.json", results)

    def _analyze_low_ratio_schools(
        self,
        run_id: str,
        bundle: PreparedBundle,
        contract: AnalyticalContract,
    ) -> AnalysisOutcome:
        registered = pd.to_numeric(
            bundle.frame["Number of students who registered for the SHSAT"],
            errors="coerce",
        )
        took = pd.to_numeric(
            bundle.frame["Number of students who took the SHSAT"],
            errors="coerce",
        )
        ratio = (took / registered).round(3)
        names = sorted(
            str(value)
            for value in bundle.frame.loc[
                ratio.between(0, 0.2),
                "School name",
            ]
            .dropna()
            .unique()
        )
        if not names:
            return self._statistical_violation(contract, bundle, "ratio", 0, 1)
        return self._result_outcome(
            run_id,
            bundle,
            "low_ratio_schools.json",
            [ResultValue("low_ratio_school_names", "; ".join(names))],
        )

    def _analyze_need_demographic_correlations(
        self,
        run_id: str,
        bundle: PreparedBundle,
        contract: AnalyticalContract,
    ) -> AnalysisOutcome:
        need = pd.to_numeric(bundle.frame["Economic Need Index"], errors="coerce")
        results: list[ResultValue] = []
        for name, column in (
            ("pearson_economic_need_percent_asian", "Percent Asian"),
            (
                "pearson_economic_need_percent_black_hispanic",
                "Percent Black / Hispanic",
            ),
            ("pearson_economic_need_percent_white", "Percent White"),
        ):
            demographic = self._percentage_to_fraction(bundle.frame[column])
            complete = pd.DataFrame({"need": need, "demographic": demographic}).dropna()
            if len(complete) < 2:
                return self._statistical_violation(
                    contract,
                    bundle,
                    column,
                    len(complete),
                    2,
                )
            results.append(
                ResultValue(
                    name,
                    float(complete["need"].corr(complete["demographic"])),
                    precision=6,
                )
            )
        return self._result_outcome(
            run_id,
            bundle,
            "need_demographic_correlations.json",
            results,
        )

    def _analyze_city_counts(
        self,
        run_id: str,
        bundle: PreparedBundle,
        contract: AnalyticalContract,
    ) -> AnalysisOutcome:
        counts = (
            bundle.frame.groupby("City", dropna=True)["Zip"]
            .count()
            .sort_values(ascending=False)
            .head(3)
        )
        if len(counts) < 3:
            return self._statistical_violation(contract, bundle, "City", len(counts), 3)
        results: list[ResultValue] = []
        for rank, (city, count) in enumerate(counts.items(), start=1):
            results.extend(
                [
                    ResultValue(f"top_city_{rank}", str(city)),
                    ResultValue(
                        f"top_city_{rank}_school_count",
                        int(count),
                        "schools",
                        0,
                    ),
                ]
            )
        return self._result_outcome(run_id, bundle, "top_school_cities.json", results)

    def _analyze_peak_registration(
        self,
        run_id: str,
        bundle: PreparedBundle,
        contract: AnalyticalContract,
    ) -> AnalysisOutcome:
        frame = bundle.frame.copy()
        frame["_year"] = pd.to_numeric(frame["Year of SHST"], errors="coerce")
        frame["_registrations"] = pd.to_numeric(
            frame["Number of students who registered for the SHSAT"],
            errors="coerce",
        )
        totals = (
            frame.dropna(subset=["_year", "_registrations"])
            .groupby("_year")["_registrations"]
            .sum()
        )
        if totals.empty:
            return self._statistical_violation(
                contract,
                bundle,
                "Year of SHST",
                0,
                1,
            )
        year = int(totals.idxmax())
        count = int(totals.loc[year])
        return self._result_outcome(
            run_id,
            bundle,
            "peak_registration.json",
            [
                ResultValue("peak_registration_year", year, "year", 0),
                ResultValue(
                    "peak_registration_count",
                    count,
                    "registrations",
                    0,
                ),
            ],
        )

    def _analyze_burger_extremes(
        self,
        run_id: str,
        bundle: PreparedBundle,
        contract: AnalyticalContract,
    ) -> AnalysisOutcome:
        frame = bundle.frame.dropna(subset=["restaurant", "item", "calories"]).copy()
        shake = frame.loc[frame["restaurant"].astype("string").str.casefold() == "shake shack"]
        if frame.empty or shake.empty:
            return self._statistical_violation(
                contract,
                bundle,
                "burger rows",
                0,
                1,
            )
        highest = frame.loc[frame["calories"].idxmax()]
        lowest_shake = shake.loc[shake["calories"].idxmin()]
        return self._result_outcome(
            run_id,
            bundle,
            "burger_calorie_extremes.json",
            [
                ResultValue("highest_calorie_item", str(highest["item"])),
                ResultValue(
                    "highest_calorie_count",
                    int(highest["calories"]),
                    "kcal",
                    0,
                ),
                ResultValue("lowest_shake_shack_item", str(lowest_shake["item"])),
            ],
        )

    def _analyze_absenteeism_profile(
        self,
        run_id: str,
        bundle: PreparedBundle,
        contract: AnalyticalContract,
    ) -> AnalysisOutcome:
        absent = self._percentage_to_fraction(
            bundle.frame["Percent of Students Chronically Absent"]
        )
        need = pd.to_numeric(bundle.frame["Economic Need Index"], errors="coerce")
        income = self._income_to_numeric(bundle.frame["School Income Estimate"])
        high = absent >= 0.30
        low = absent <= 0.11
        high_income = income.loc[high & income.gt(0)].mean()
        low_income = income.loc[low & income.gt(0)].mean()
        values = [need.loc[high].mean(), high_income, need.loc[low].mean(), low_income]
        if any(pd.isna(value) for value in values):
            return self._statistical_violation(
                contract,
                bundle,
                "cohort values",
                0,
                1,
            )
        return self._result_outcome(
            run_id,
            bundle,
            "absenteeism_profile.json",
            [
                ResultValue(
                    "high_absenteeism_economic_need",
                    round(float(values[0]) * 100),
                    "%",
                    0,
                ),
                ResultValue(
                    "high_absenteeism_income",
                    round(float(values[1])),
                    "USD",
                    0,
                ),
                ResultValue(
                    "low_absenteeism_economic_need",
                    round(float(values[2]) * 100),
                    "%",
                    0,
                ),
                ResultValue(
                    "low_absenteeism_income",
                    round(float(values[3])),
                    "USD",
                    0,
                ),
            ],
        )

    def _analyze_proficiency_demographics(
        self,
        run_id: str,
        bundle: PreparedBundle,
        contract: AnalyticalContract,
    ) -> AnalysisOutcome:
        share = self._percentage_to_fraction(bundle.frame["Percent Black / Hispanic"])
        ela = pd.to_numeric(
            bundle.frame["Average ELA Proficiency"],
            errors="coerce",
        )
        math = pd.to_numeric(
            bundle.frame["Average Math Proficiency"],
            errors="coerce",
        )
        high = share >= 0.70
        low = share <= 0.30
        values = [
            ela.loc[high].mean(),
            math.loc[high].mean(),
            ela.loc[low].mean(),
            math.loc[low].mean(),
        ]
        if any(pd.isna(value) for value in values):
            return self._statistical_violation(
                contract,
                bundle,
                "proficiency cohorts",
                0,
                1,
            )
        return self._result_outcome(
            run_id,
            bundle,
            "proficiency_demographics.json",
            [
                ResultValue("high_black_hispanic_ela", float(values[0]), precision=2),
                ResultValue(
                    "high_black_hispanic_math",
                    float(values[1]),
                    precision=2,
                ),
                ResultValue("low_black_hispanic_ela", float(values[2]), precision=2),
                ResultValue(
                    "low_black_hispanic_math",
                    float(values[3]),
                    precision=2,
                ),
            ],
        )

    def _analyze_community_school_profile(
        self,
        run_id: str,
        bundle: PreparedBundle,
        contract: AnalyticalContract,
    ) -> AnalysisOutcome:
        status = bundle.frame["Community School?"].astype("string")
        income = self._income_to_numeric(bundle.frame["School Income Estimate"])
        share = self._percentage_to_fraction(bundle.frame["Percent Black / Hispanic"])
        community = status.eq("Yes")
        non_community = status.eq("No")
        values = [
            income.loc[community].mean(),
            share.loc[community].mean(),
            income.loc[non_community].mean(),
            share.loc[non_community].mean(),
        ]
        if any(pd.isna(value) for value in values):
            return self._statistical_violation(
                contract,
                bundle,
                "school status",
                0,
                1,
            )
        return self._result_outcome(
            run_id,
            bundle,
            "community_school_profile.json",
            [
                ResultValue(
                    "community_school_income",
                    int(round(float(values[0]), -3)),
                    "USD",
                    0,
                ),
                ResultValue(
                    "community_school_black_hispanic",
                    round(float(values[1]) * 100),
                    "%",
                    0,
                ),
                ResultValue(
                    "non_community_school_income",
                    int(round(float(values[2]), -3)),
                    "USD",
                    0,
                ),
                ResultValue(
                    "non_community_school_black_hispanic",
                    round(float(values[3]) * 100),
                    "%",
                    0,
                ),
            ],
        )

    def _analyze_unemployment_negative_skew_share(
        self,
        run_id: str,
        bundle: PreparedBundle,
        contract: AnalyticalContract,
    ) -> AnalysisOutcome:
        frame = bundle.frame.copy()
        dates = pd.to_datetime(frame["date"], errors="coerce")
        frame = frame.loc[dates.notna()].copy()
        frame["_year"] = dates.loc[frame.index].dt.year
        yearly_counts = frame.groupby("_year").size()
        complete_years = yearly_counts.loc[lambda counts: counts == 12].index
        yearly = (
            frame.loc[frame["_year"].isin(complete_years)]
            .drop(columns="date")
            .groupby("_year")
            .mean(numeric_only=True)
        )
        skewness = yearly.skew().drop(labels=["population_over_16"], errors="ignore").dropna()
        if skewness.empty:
            return self._statistical_violation(
                contract,
                bundle,
                "yearly numeric attributes",
                0,
                1,
            )
        negative_share = float(skewness.lt(0).mean() * 100)
        return self._result_outcome(
            run_id,
            bundle,
            "unemployment_negative_skew_share.json",
            [
                ResultValue(
                    "negative_skew_share_after_yearly_averaging",
                    round(negative_share, 2),
                    "%",
                    2,
                )
            ],
        )

    def _analyze_wage_skew_direction_share(
        self,
        run_id: str,
        bundle: PreparedBundle,
        contract: AnalyticalContract,
    ) -> AnalysisOutcome:
        numeric = bundle.frame.select_dtypes(include=["number"]).drop(
            columns=["year"],
            errors="ignore",
        )
        skewness = numeric.skew().dropna()
        if skewness.empty:
            return self._statistical_violation(
                contract,
                bundle,
                "numeric wage attributes",
                0,
                1,
            )
        positive_share = round(float(skewness.gt(0).mean() * 100))
        negative_share = round(float(skewness.lt(0).mean() * 100))
        return self._result_outcome(
            run_id,
            bundle,
            "wage_skew_direction_share.json",
            [
                ResultValue("positive_skew_attribute_share", positive_share, "%", 0),
                ResultValue("negative_skew_attribute_share", negative_share, "%", 0),
            ],
        )

    def _result_outcome(
        self,
        run_id: str,
        bundle: PreparedBundle,
        filename: str,
        results: list[ResultValue],
    ) -> AnalysisOutcome:
        evidence = self._write_analysis_evidence(
            run_id,
            filename,
            {"results": {result.name: result.value for result in results}},
            "Executed deterministic analysis results",
        )
        artifacts = [
            AnalysisArtifact(
                kind="scalar",
                name=result.name,
                value=result.value,
                unit=result.unit,
                display_precision=result.precision,
                source_state_ids=[bundle.state.state_id],
                evidence_refs=[evidence.ref_id],
            )
            for result in results
        ]
        return AnalysisOutcome(artifacts=artifacts, evidence=[evidence])

    @staticmethod
    def _income_to_numeric(series: pd.Series) -> pd.Series:
        return pd.to_numeric(
            series.astype("string")
            .str.replace(",", "", regex=False)
            .str.replace("$", "", regex=False)
            .str.strip(),
            errors="coerce",
        )

    @staticmethod
    def _format_artifact(artifact: AnalysisArtifact) -> str:
        if not isinstance(artifact.value, (int, float)):
            return str(artifact.value)
        precision = artifact.display_precision or 0
        if artifact.unit == "%":
            return f"{float(artifact.value):.{precision}f}%"
        if artifact.unit == "USD":
            return "$" + f"{float(artifact.value):,.{precision}f}"
        rendered = f"{float(artifact.value):.{precision}f}"
        return f"{rendered} {artifact.unit}" if artifact.unit else rendered


def format_coda_pilot_answer(task_id: int, state: RunState) -> str | None:
    """Render structured artifacts in the answer format used by registered CoDA pilots."""
    if state.status != RunStatus.COMPLETED:
        return None
    values = {artifact.name: artifact.value for artifact in state.artifacts}
    if task_id == 175:
        return str(int(values["final_record_count"]))
    if task_id == 176:
        return str(values["minimum_participation_ratio"])
    if task_id == 177:
        return str(int(values["distinct_grade_levels"]))
    if task_id == 178:
        return (
            f"{int(values['charter_school_count'])}; "
            f"{int(values['community_school_count'])}; "
            f"{int(values['combined_school_share'])}%"
        )
    if task_id == 180:
        return str(values["low_ratio_school_names"])
    if task_id == 955:
        return (
            f"Black/Hispanic: {float(values['mean_percent_black_hispanic']):.2f}%; "
            f"White: {float(values['mean_percent_white']):.2f}%; "
            f"Asian: {float(values['mean_percent_asian']):.2f}%"
        )
    if task_id == 956:
        need_correlations = (
            float(values["pearson_economic_need_percent_asian"]),
            float(values["pearson_economic_need_percent_black_hispanic"]),
            float(values["pearson_economic_need_percent_white"]),
        )
        return "; ".join(f"{value:.6f}" for value in need_correlations)
    if task_id == 957:
        return "; ".join(
            [
                str(values["top_city_1"]),
                str(int(values["top_city_1_school_count"])),
                str(values["top_city_2"]),
                str(int(values["top_city_2_school_count"])),
                str(values["top_city_3"]),
                str(int(values["top_city_3_school_count"])),
            ]
        )
    if task_id == 958:
        return f"{int(values['peak_registration_year'])}; {int(values['peak_registration_count'])}"
    if task_id == 959:
        shsat_correlations = (
            float(values["pearson_percent_asian"]),
            float(values["pearson_percent_black_hispanic"]),
            float(values["pearson_percent_white"]),
        )
        return "; ".join(f"{value:.6f}" for value in shsat_correlations)
    if task_id == 960:
        return (
            f"{values['highest_calorie_item']}; "
            f"{int(values['highest_calorie_count'])}; "
            f"{values['lowest_shake_shack_item']}"
        )
    if task_id == 961:
        return (
            "High Absenteeism (>= 30%): {}% Economic Need Index, $"
            "{:,} Income; Low Absenteeism (<= 11%): {}% Economic Need Index, $"
            "{:,} Income"
        ).format(
            int(values["high_absenteeism_economic_need"]),
            int(values["high_absenteeism_income"]),
            int(values["low_absenteeism_economic_need"]),
            int(values["low_absenteeism_income"]),
        )
    if task_id == 962:
        proficiency_values = (
            float(values["high_black_hispanic_ela"]),
            float(values["high_black_hispanic_math"]),
            float(values["low_black_hispanic_ela"]),
            float(values["low_black_hispanic_math"]),
        )
        return "; ".join(f"{value:.2f}" for value in proficiency_values)
    if task_id == 963:
        return ("Community Schools: ${:,}, {}%; Non-Community Schools: ${:,}, {}%").format(
            int(values["community_school_income"]),
            int(values["community_school_black_hispanic"]),
            int(values["non_community_school_income"]),
            int(values["non_community_school_black_hispanic"]),
        )
    if task_id == 590:
        return f"{float(values['negative_skew_share_after_yearly_averaging']):.2f}%"
    if task_id == 591:
        return (
            f"{int(values['positive_skew_attribute_share'])}%; "
            f"{int(values['negative_skew_attribute_share'])}%"
        )
    if task_id == 179:
        raise AssertionError("The known missing-source task unexpectedly completed")
    raise ValueError(f"No answer formatter for task {task_id}")
