from __future__ import annotations

import re

from askdu.domain import AnalyticalContract, AnalyticalObligation, ObligationType

SHSAT_CORRELATION_FAMILY = "coda_shsat_demographic_correlations"
SHSAT_ECONOMIC_NEED_COUNT_FAMILY = "coda_shsat_economic_need_count"
SHSAT_OFFER_DEMOGRAPHICS_FAMILY = "coda_shsat_offer_demographics"
SHSAT_MIN_RATIO_FAMILY = "coda_shsat_minimum_participation_ratio"
SHSAT_GRADE_LEVEL_COUNT_FAMILY = "coda_shsat_distinct_grade_levels"
SCHOOL_TYPE_SHARE_FAMILY = "coda_school_type_share"
ATTENDANCE_BY_GRADE_FAMILY = "coda_attendance_by_grade"
SHSAT_LOW_RATIO_SCHOOLS_FAMILY = "coda_shsat_low_participation_schools"
SCHOOL_NEED_DEMOGRAPHIC_CORRELATIONS_FAMILY = "coda_school_need_demographic_correlations"
SCHOOL_CITY_COUNTS_FAMILY = "coda_school_city_counts"
SHSAT_PEAK_REGISTRATION_FAMILY = "coda_shsat_peak_registration"
BURGER_CALORIE_EXTREMES_FAMILY = "coda_burger_calorie_extremes"
SCHOOL_ABSENTEEISM_PROFILE_FAMILY = "coda_school_absenteeism_profile"
SCHOOL_PROFICIENCY_DEMOGRAPHICS_FAMILY = "coda_school_proficiency_demographics"
COMMUNITY_SCHOOL_PROFILE_FAMILY = "coda_community_school_profile"
UNEMPLOYMENT_NEGATIVE_SKEW_SHARE_FAMILY = "coda_unemployment_negative_skew_share"
WAGE_SKEW_DIRECTION_SHARE_FAMILY = "coda_wage_skew_direction_share"
DECLARATIVE_TASK_FAMILY = "declarative_v1"

SUPPORTED_TASK_FAMILIES = {
    DECLARATIVE_TASK_FAMILY,
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
    UNEMPLOYMENT_NEGATIVE_SKEW_SHARE_FAMILY,
    WAGE_SKEW_DIRECTION_SHARE_FAMILY,
}

SINGLE_SOURCE_REQUIRED_COLUMNS: dict[str, tuple[str, ...]] = {
    SHSAT_MIN_RATIO_FAMILY: (
        "Number of students who registered for the SHSAT",
        "Number of students who took the SHSAT",
    ),
    SHSAT_GRADE_LEVEL_COUNT_FAMILY: ("Grade level",),
    SCHOOL_TYPE_SHARE_FAMILY: ("School Name", "Community School?"),
    ATTENDANCE_BY_GRADE_FAMILY: ("ATTPCTPRK", "ATTPCTG05", "ATTPCTG09"),
    SHSAT_LOW_RATIO_SCHOOLS_FAMILY: (
        "School name",
        "Number of students who registered for the SHSAT",
        "Number of students who took the SHSAT",
    ),
    SCHOOL_NEED_DEMOGRAPHIC_CORRELATIONS_FAMILY: (
        "Economic Need Index",
        "Percent Asian",
        "Percent Black / Hispanic",
        "Percent White",
    ),
    SCHOOL_CITY_COUNTS_FAMILY: ("City", "Zip"),
    SHSAT_PEAK_REGISTRATION_FAMILY: (
        "Year of SHST",
        "Number of students who registered for the SHSAT",
    ),
    SCHOOL_ABSENTEEISM_PROFILE_FAMILY: (
        "Percent of Students Chronically Absent",
        "Economic Need Index",
        "School Income Estimate",
    ),
    SCHOOL_PROFICIENCY_DEMOGRAPHICS_FAMILY: (
        "Percent Black / Hispanic",
        "Average ELA Proficiency",
        "Average Math Proficiency",
    ),
    COMMUNITY_SCHOOL_PROFILE_FAMILY: (
        "Community School?",
        "School Income Estimate",
        "Percent Black / Hispanic",
    ),
    UNEMPLOYMENT_NEGATIVE_SKEW_SHARE_FAMILY: ("date", "population_over_16"),
    WAGE_SKEW_DIRECTION_SHARE_FAMILY: ("year", "less_than_hs", "advanced_degree"),
}


class QuestionCompiler:
    """Compile the registered CoDA pilot questions into typed ASC.

    The rules make the current evaluation deterministic and auditable. A future
    model-based compiler must emit the same domain model and pass the same
    validators; this registry is not presented as general language coverage.
    """

    def compile(self, question: str) -> AnalyticalContract:
        normalized = " ".join(question.lower().split())
        family = self._match_family(normalized)
        if family is None:
            return self._unsupported_contract(question)
        if family == SHSAT_CORRELATION_FAMILY:
            return self._compile_shsat_correlation(question)
        if family == SHSAT_ECONOMIC_NEED_COUNT_FAMILY:
            return self._compile_economic_need_count(question)
        if family == SHSAT_OFFER_DEMOGRAPHICS_FAMILY:
            return self._compile_offer_demographics(question)
        if family == BURGER_CALORIE_EXTREMES_FAMILY:
            return self._compile_burger_extremes(question)
        return self._compile_single_source(question, family)

    @staticmethod
    def _match_family(normalized: str) -> str | None:
        if (
            ("pearson" in normalized or "correlation" in normalized)
            and "shsat" in normalized
            and "grade 8" in normalized
            and "2016" in normalized
        ):
            return SHSAT_CORRELATION_FAMILY
        if all(
            token in normalized
            for token in ("final count", "2016", "grade level 8", "economic need index")
        ):
            return SHSAT_ECONOMIC_NEED_COUNT_FAMILY
        if (
            "average" in normalized
            and "offer" in normalized
            and all(token in normalized for token in ("black", "hispanic", "white", "asian"))
        ):
            return SHSAT_OFFER_DEMOGRAPHICS_FAMILY
        if all(token in normalized for token in ("minimum ratio", "taking the test", "registered")):
            return SHSAT_MIN_RATIO_FAMILY
        if "distinct grade levels" in normalized and "shsat" in normalized:
            return SHSAT_GRADE_LEVEL_COUNT_FAMILY
        if "charter schools" in normalized and "community schools" in normalized:
            return SCHOOL_TYPE_SHARE_FAMILY
        if (
            "average attendance" in normalized
            and "pre-kindergarten" in normalized
            and "grade 9" in normalized
        ):
            return ATTENDANCE_BY_GRADE_FAMILY
        if "ratio" in normalized and "between 0 and 0.2" in normalized:
            return SHSAT_LOW_RATIO_SCHOOLS_FAMILY
        if (
            ("pearson" in normalized or "correlation" in normalized)
            and "economic need index" in normalized
            and "asian" in normalized
        ):
            return SCHOOL_NEED_DEMOGRAPHIC_CORRELATIONS_FAMILY
        if "three cities" in normalized and "highest frequency of schools" in normalized:
            return SCHOOL_CITY_COUNTS_FAMILY
        if "highest total registrations" in normalized and "which year" in normalized:
            return SHSAT_PEAK_REGISTRATION_FAMILY
        if (
            "burger" in normalized
            and "highest calorie" in normalized
            and "shake shack" in normalized
        ):
            return BURGER_CALORIE_EXTREMES_FAMILY
        if "chronic absenteeism" in normalized and "economic need" in normalized:
            return SCHOOL_ABSENTEEISM_PROFILE_FAMILY
        if "proficiency" in normalized and "black/hispanic" in normalized:
            return SCHOOL_PROFICIENCY_DEMOGRAPHICS_FAMILY
        if "community schools versus non-community schools" in normalized:
            return COMMUNITY_SCHOOL_PROFILE_FAMILY
        if (
            "yearly averages" in normalized
            and "unemployment" in normalized
            and "negatively skewed" in normalized
        ):
            return UNEMPLOYMENT_NEGATIVE_SKEW_SHARE_FAMILY
        if (
            "numeric attributes" in normalized
            and "positively skewed" in normalized
            and "negatively skewed" in normalized
            and "year column" in normalized
        ):
            return WAGE_SKEW_DIRECTION_SHARE_FAMILY
        return None

    @staticmethod
    def _compile_single_source(question: str, family: str) -> AnalyticalContract:
        columns = SINGLE_SOURCE_REQUIRED_COLUMNS[family]
        descriptions = {
            SHSAT_MIN_RATIO_FAMILY: "Minimum non-zero SHSAT test-taker/registrant ratio",
            SHSAT_GRADE_LEVEL_COUNT_FAMILY: "Distinct SHSAT grade-level count",
            SCHOOL_TYPE_SHARE_FAMILY: "Charter and Community School counts and share",
            ATTENDANCE_BY_GRADE_FAMILY: "Mean attendance for Pre-K, Grade 5, and Grade 9",
            SHSAT_LOW_RATIO_SCHOOLS_FAMILY: ("Schools with SHSAT participation ratio in [0, 0.2]"),
            SCHOOL_NEED_DEMOGRAPHIC_CORRELATIONS_FAMILY: (
                "Economic-need correlations with three demographic percentages"
            ),
            SCHOOL_CITY_COUNTS_FAMILY: "Top three cities by school frequency",
            SHSAT_PEAK_REGISTRATION_FAMILY: ("Year with the largest SHSAT registration total"),
            SCHOOL_ABSENTEEISM_PROFILE_FAMILY: (
                "Economic need and non-zero income means by absenteeism cohort"
            ),
            SCHOOL_PROFICIENCY_DEMOGRAPHICS_FAMILY: (
                "ELA and Math means by Black/Hispanic population cohort"
            ),
            COMMUNITY_SCHOOL_PROFILE_FAMILY: (
                "Income and Black/Hispanic means by Community School status"
            ),
            UNEMPLOYMENT_NEGATIVE_SKEW_SHARE_FAMILY: (
                "Share of yearly-averaged numeric attributes with negative skewness"
            ),
            WAGE_SKEW_DIRECTION_SHARE_FAMILY: (
                "Shares of wage attributes with positive and negative skewness"
            ),
        }
        obligations = [
            AnalyticalObligation(
                type=(ObligationType.MEASURE if index == 0 else ObligationType.DIMENSION),
                description=f"Required analytical column: {column}",
                check="column_present",
                expected={"column": column},
            )
            for index, column in enumerate(columns)
        ]
        obligations.extend(
            [
                AnalyticalObligation(
                    type=ObligationType.STATISTICAL,
                    description=descriptions[family],
                    check="eligible_rows_nonempty",
                    expected={"minimum": 1},
                ),
                AnalyticalObligation(
                    type=ObligationType.EVIDENCE,
                    description="Every reported result links to executed evidence",
                    check="claim_artifact_linkage",
                ),
            ]
        )
        search_terms = list(columns)
        if family in {
            SHSAT_MIN_RATIO_FAMILY,
            SHSAT_GRADE_LEVEL_COUNT_FAMILY,
            SHSAT_LOW_RATIO_SCHOOLS_FAMILY,
            SHSAT_PEAK_REGISTRATION_FAMILY,
        }:
            search_terms.extend(["SHSAT", "registrations", "testers"])
        elif family == ATTENDANCE_BY_GRADE_FAMILY:
            search_terms.append("schma19962016")
        elif family == UNEMPLOYMENT_NEGATIVE_SKEW_SHARE_FAMILY:
            search_terms.extend(["unemployment", "unemployed population", "demographics"])
        elif family == WAGE_SKEW_DIRECTION_SHARE_FAMILY:
            search_terms.extend(["wages", "education"])
        else:
            search_terms.extend(["school", "2016 School Explorer"])
        return AnalyticalContract(
            question=question,
            task_family=family,
            search_terms=search_terms,
            obligations=obligations,
        )

    @staticmethod
    def _compile_burger_extremes(question: str) -> AnalyticalContract:
        return AnalyticalContract(
            question=question,
            task_family=BURGER_CALORIE_EXTREMES_FAMILY,
            search_terms=["Shake Shack", "Burgers", "Menu", "Calories"],
            obligations=[
                AnalyticalObligation(
                    type=ObligationType.MEASURE,
                    description="Normalized burger calorie values",
                    check="column_present_and_numeric",
                    expected={"column": "calories"},
                ),
                AnalyticalObligation(
                    type=ObligationType.DIMENSION,
                    description="Restaurant and burger item identity",
                    check="columns_present",
                    expected={"columns": ["restaurant", "item"]},
                ),
                AnalyticalObligation(
                    type=ObligationType.COVERAGE,
                    description="Shake Shack, McDonald's, and Burger King are represented",
                    check="category_coverage",
                    expected={
                        "column": "restaurant",
                        "required_categories": [
                            "Shake Shack",
                            "Mcdonalds",
                            "Burger King",
                        ],
                    },
                ),
                AnalyticalObligation(
                    type=ObligationType.STATISTICAL,
                    description="At least one eligible burger exists for each requested extreme",
                    check="eligible_rows_nonempty",
                    expected={"minimum": 1},
                ),
                AnalyticalObligation(
                    type=ObligationType.EVIDENCE,
                    description="Every reported item and calorie count links to executed evidence",
                    check="claim_artifact_linkage",
                ),
            ],
        )

    @staticmethod
    def _compile_shsat_correlation(question: str) -> AnalyticalContract:
        obligations = [
            AnalyticalObligation(
                type=ObligationType.MEASURE,
                description="Number of students who took the SHSAT",
                check="column_present_and_numeric",
                expected={"column": "Number of students who took the SHSAT"},
            ),
            *[
                AnalyticalObligation(
                    type=ObligationType.DIMENSION,
                    description=f"{label} student percentage",
                    check="column_present_and_numeric",
                    expected={"column": column},
                )
                for label, column in (
                    ("Asian", "Percent Asian"),
                    ("Black/Hispanic", "Percent Black / Hispanic"),
                    ("White", "Percent White"),
                )
            ],
            AnalyticalObligation(
                type=ObligationType.COVERAGE,
                description="Grade 8 observations from 2016",
                check="filtered_rows_nonempty",
                expected={"grade": 8, "year": 2016},
            ),
            AnalyticalObligation(
                type=ObligationType.JOIN,
                description="SHSAT records align with school demographics",
                check="join_coverage",
                expected={
                    "left_key": "DBN",
                    "right_key": "Location Code",
                    "minimum_coverage": 0.8,
                },
            ),
            AnalyticalObligation(
                type=ObligationType.STATISTICAL,
                description="At least two complete observations per Pearson correlation",
                check="complete_pair_count",
                expected={"minimum": 2},
            ),
            AnalyticalObligation(
                type=ObligationType.EVIDENCE,
                description="Every reported correlation links to an executed artifact",
                check="claim_artifact_linkage",
            ),
        ]
        return AnalyticalContract(
            question=question,
            task_family=SHSAT_CORRELATION_FAMILY,
            search_terms=["SHSAT", "registrations", "testers", "grade level", "year"],
            obligations=obligations,
        )

    @staticmethod
    def _compile_economic_need_count(question: str) -> AnalyticalContract:
        return AnalyticalContract(
            question=question,
            task_family=SHSAT_ECONOMIC_NEED_COUNT_FAMILY,
            search_terms=["SHSAT", "registrations", "year", "2016", "grade level"],
            obligations=[
                AnalyticalObligation(
                    type=ObligationType.DIMENSION,
                    description="Economic Need Index is available before missing-value filtering",
                    check="column_present",
                    expected={"column": "Economic Need Index"},
                ),
                AnalyticalObligation(
                    type=ObligationType.COVERAGE,
                    description="Records are restricted to Grade 8 in 2016",
                    check="filtered_rows_nonempty",
                    expected={"grade": 8, "year": 2016},
                ),
                AnalyticalObligation(
                    type=ObligationType.GRAIN,
                    description="Duplicate school-year records are removed before filtering",
                    check="deduplicate",
                    expected={"keys": ["School name", "Year of SHST"]},
                ),
                AnalyticalObligation(
                    type=ObligationType.JOIN,
                    description="SHSAT records align with school Economic Need Index values",
                    check="join_coverage",
                    expected={
                        "left_key": "DBN",
                        "right_key": "Location Code",
                        "minimum_coverage": 0.8,
                    },
                ),
                AnalyticalObligation(
                    type=ObligationType.EVIDENCE,
                    description="The reported count links to the filtered materialization",
                    check="claim_artifact_linkage",
                ),
            ],
        )

    @staticmethod
    def _compile_offer_demographics(question: str) -> AnalyticalContract:
        obligations = [
            AnalyticalObligation(
                type=ObligationType.MEASURE,
                description="Number of students who received an SHSAT offer",
                check="column_present_and_numeric",
                expected={"column": "Number of students who received offer"},
            ),
            *[
                AnalyticalObligation(
                    type=ObligationType.DIMENSION,
                    description=f"{label} student percentage",
                    check="column_present_and_numeric",
                    expected={"column": column},
                )
                for label, column in (
                    ("Black/Hispanic", "Percent Black / Hispanic"),
                    ("White", "Percent White"),
                    ("Asian", "Percent Asian"),
                )
            ],
            AnalyticalObligation(
                type=ObligationType.COVERAGE,
                description="Only matched schools with recorded test and offer counts are analyzed",
                check="eligible_rows_nonempty",
                expected={
                    "required_non_null": [
                        "City",
                        "Number of students who took test",
                        "Number of students who received offer",
                    ]
                },
            ),
            AnalyticalObligation(
                type=ObligationType.JOIN,
                description="Offer records align with School Explorer demographics",
                check="join_coverage",
                expected={
                    "left_key": "School DBN",
                    "right_key": "Location Code",
                    "minimum_coverage": 0.8,
                },
            ),
            AnalyticalObligation(
                type=ObligationType.STATISTICAL,
                description="At least one complete percentage is available for each mean",
                check="complete_value_count",
                expected={"minimum": 1},
            ),
            AnalyticalObligation(
                type=ObligationType.EVIDENCE,
                description="Every reported mean links to an executed artifact",
                check="claim_artifact_linkage",
            ),
        ]
        return AnalyticalContract(
            question=question,
            task_family=SHSAT_OFFER_DEMOGRAPHICS_FAMILY,
            search_terms=[
                "SHSAT",
                "students received offer",
                "School DBN",
                "School Category",
            ],
            obligations=obligations,
        )

    def _unsupported_contract(self, question: str) -> AnalyticalContract:
        return AnalyticalContract(
            question=question,
            task_family="unsupported",
            search_terms=self._fallback_terms(question),
            obligations=[
                AnalyticalObligation(
                    type=ObligationType.MEASURE,
                    description="An executable analysis adapter for the requested measure",
                    check="registered_analysis_adapter",
                    expected={"task_family": "supported"},
                ),
                AnalyticalObligation(
                    type=ObligationType.EVIDENCE,
                    description="Every quantitative report claim links to an executed artifact",
                    check="claim_artifact_linkage",
                ),
            ],
        )

    @staticmethod
    def _fallback_terms(question: str) -> list[str]:
        stopwords = {
            "a",
            "an",
            "and",
            "are",
            "for",
            "from",
            "in",
            "is",
            "of",
            "the",
            "to",
            "what",
            "which",
            "with",
        }
        tokens = re.findall(r"[a-zA-Z0-9]+", question.lower())
        return [token for token in tokens if token not in stopwords and len(token) > 2][:12]
