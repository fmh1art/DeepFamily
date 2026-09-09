from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SYSTEM_VERSION = "0.4.0"
CODA_REVISION = "63828a2b652e26a9770555a0cc41e6c8aafdb5d9"
PYTHON_VERSION = "3.10.20"
PANDAS_VERSION = "2.3.3"
UNSUPPORTED_PAPER_CLAIMS = (
    "reopen Discovery or Preparation",
    "repair an upstream source or preparation decision",
    "targeted backward edges to Discovery or Preparation",
    "automatic source and preparation repair",
    "source/preparation repair",
)

COMMUNITY43_TASK_IDS = [
    175,
    176,
    177,
    178,
    179,
    180,
    955,
    956,
    957,
    958,
    959,
    960,
    961,
    962,
    963,
]
COMMUNITY43_TASK_CLASSES = {
    "cross_source_repair": [175, 955, 959, 960],
    "data_gap": [179],
    "no_repair": [176, 177, 178, 180, 956, 957, 958, 961, 962, 963],
}
COMMUNITY43_MODES = ("linear", "static_retry", "closed_loop", "full_profile")
COMMUNITY43_MODE_DEFINITIONS = {
    "linear": "Progressive discovery with no downstream-to-upstream repair.",
    "static_retry": (
        "Progressive discovery with two repair rounds that reuse the unchanged "
        "initial search terms instead of violation-conditioned terms."
    ),
    "closed_loop": "Progressive discovery with up to two typed repair rounds.",
    "full_profile": (
        "Content-profiles every authorized CSV before analysis and performs no repair."
    ),
}
COMMUNITY43_AGGREGATE = {
    "linear": {
        "tasks": 15,
        "reports_completed": 10,
        "exact_matches": 10,
        "correct_abstentions": 1,
        "resolved": 11,
        "repair_edges": 0,
        "logical_source_profiles": 14,
        "verified_source_profiles": 14,
        "logical_profile_bytes": 4_989_475,
        "mean_source_precision": 1,
        "mean_source_recall": 0.857143,
        "mandatory_human_interventions": 0,
    },
    "static_retry": {
        "tasks": 15,
        "reports_completed": 12,
        "exact_matches": 12,
        "correct_abstentions": 1,
        "resolved": 13,
        "repair_edges": 7,
        "logical_source_profiles": 21,
        "verified_source_profiles": 21,
        "logical_profile_bytes": 11_008_557,
        "mean_source_precision": 0.880952,
        "mean_source_recall": 0.928571,
        "mandatory_human_interventions": 0,
    },
    "closed_loop": {
        "tasks": 15,
        "reports_completed": 14,
        "exact_matches": 14,
        "correct_abstentions": 1,
        "resolved": 15,
        "repair_edges": 4,
        "logical_source_profiles": 18,
        "verified_source_profiles": 18,
        "logical_profile_bytes": 7_476_177,
        "mean_source_precision": 1,
        "mean_source_recall": 1,
        "mandatory_human_interventions": 0,
    },
    "full_profile": {
        "tasks": 15,
        "reports_completed": 14,
        "exact_matches": 14,
        "correct_abstentions": 1,
        "resolved": 15,
        "repair_edges": 0,
        "logical_source_profiles": 150,
        "verified_source_profiles": 150,
        "logical_profile_bytes": 1_355_590_320,
        "mean_source_precision": 0.128571,
        "mean_source_recall": 1,
        "mandatory_human_interventions": 0,
    },
}
COMMUNITY52_AGGREGATE = {
    "tasks": 2,
    "reports_completed": 2,
    "exact_matches": 2,
    "expected_sources_selected": 2,
    "repair_edges": 0,
    "logical_source_profiles": 2,
    "verified_source_profiles": 2,
    "logical_profile_bytes": 292_948,
    "mandatory_human_interventions": 0,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Assert that generated results and paper claims match reported evidence."
    )
    parser.add_argument(
        "--community43",
        type=Path,
        default=PROJECT_ROOT / "experiments/results/coda-community43/summary.json",
    )
    parser.add_argument(
        "--community52",
        type=Path,
        default=PROJECT_ROOT
        / "experiments/results/coda-community52-transfer/summary.json",
    )
    parser.add_argument("--paper", type=Path, default=PROJECT_ROOT / "paper/main.tex")
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise SystemExit(f"Missing generated result: {path}")
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise SystemExit(f"Expected a JSON object: {path}")
    return document


def expect(failures: list[str], label: str, actual: object, expected: object) -> None:
    if actual != expected:
        failures.append(f"{label}: expected {expected!r}, got {actual!r}")


def verify_common(failures: list[str], label: str, summary: dict[str, Any]) -> None:
    expect(
        failures,
        f"{label}.system_version",
        summary.get("system_version"),
        SYSTEM_VERSION,
    )
    expect(
        failures, f"{label}.coda_revision", summary.get("coda_revision"), CODA_REVISION
    )
    expect(failures, f"{label}.python", summary.get("python"), PYTHON_VERSION)
    expect(failures, f"{label}.pandas", summary.get("pandas"), PANDAS_VERSION)


def verify_community43(failures: list[str], summary: dict[str, Any]) -> None:
    verify_common(failures, "community43", summary)
    expect(
        failures, "community43.task_ids", summary.get("task_ids"), COMMUNITY43_TASK_IDS
    )
    expect(
        failures,
        "community43.task_classes",
        summary.get("task_classes"),
        COMMUNITY43_TASK_CLASSES,
    )
    expect(
        failures,
        "community43.mode_definitions",
        summary.get("mode_definitions"),
        COMMUNITY43_MODE_DEFINITIONS,
    )
    expect(
        failures,
        "community43.aggregate",
        summary.get("aggregate"),
        COMMUNITY43_AGGREGATE,
    )

    results = summary.get("results")
    if not isinstance(results, list):
        failures.append("community43.results: expected a list")
        return
    keyed = {
        (row.get("task_id"), row.get("mode")): row
        for row in results
        if isinstance(row, dict)
    }
    expected_keys = {
        (task_id, mode)
        for task_id in COMMUNITY43_TASK_IDS
        for mode in COMMUNITY43_MODES
    }
    expect(failures, "community43 result count", len(results), 60)
    expect(failures, "community43 unique result keys", set(keyed), expected_keys)

    for mode in COMMUNITY43_MODES:
        mode_rows = [row for row in results if row.get("mode") == mode]
        precisions = [
            float(row["source_precision"])
            for row in mode_rows
            if row.get("source_precision") is not None
        ]
        recalls = [
            float(row["source_recall"])
            for row in mode_rows
            if row.get("source_recall") is not None
        ]
        recomputed = {
            "tasks": len(mode_rows),
            "reports_completed": sum(
                row.get("status") == "completed" for row in mode_rows
            ),
            "exact_matches": sum(bool(row.get("exact_match")) for row in mode_rows),
            "correct_abstentions": sum(
                bool(row.get("correct_abstention")) for row in mode_rows
            ),
            "resolved": sum(bool(row.get("resolved")) for row in mode_rows),
            "repair_edges": sum(int(row.get("repair_edges", 0)) for row in mode_rows),
            "logical_source_profiles": sum(
                int(row.get("logical_source_profiles", 0)) for row in mode_rows
            ),
            "verified_source_profiles": sum(
                int(row.get("verified_source_profiles", 0)) for row in mode_rows
            ),
            "logical_profile_bytes": sum(
                int(row.get("logical_profile_bytes", 0)) for row in mode_rows
            ),
            "mean_source_precision": round(statistics.fmean(precisions), 6),
            "mean_source_recall": round(statistics.fmean(recalls), 6),
            "mandatory_human_interventions": sum(
                int(row.get("mandatory_human_interventions", 0)) for row in mode_rows
            ),
        }
        expect(
            failures,
            f"community43.{mode} independently recomputed aggregate",
            summary.get("aggregate", {}).get(mode),
            recomputed,
        )

    repair_tasks = set(COMMUNITY43_TASK_CLASSES["cross_source_repair"])
    linear_unresolved = {
        task_id
        for (task_id, mode), row in keyed.items()
        if mode == "linear" and not row.get("resolved")
    }
    expect(
        failures, "community43 linear unresolved tasks", linear_unresolved, repair_tasks
    )
    static_unresolved = {
        task_id
        for (task_id, mode), row in keyed.items()
        if mode == "static_retry" and not row.get("resolved")
    }
    expect(
        failures,
        "community43 static-retry unresolved tasks",
        static_unresolved,
        {175, 959},
    )

    for task_id in COMMUNITY43_TASK_IDS:
        for mode in ("closed_loop", "full_profile"):
            row = keyed.get((task_id, mode), {})
            expect(
                failures, f"task {task_id} {mode} resolved", row.get("resolved"), True
            )
        repair_row = keyed.get((task_id, "closed_loop"), {})
        expect(
            failures,
            f"task {task_id} closed_loop repair_edges",
            repair_row.get("repair_edges"),
            1 if task_id in repair_tasks else 0,
        )
        static_row = keyed.get((task_id, "static_retry"), {})
        expected_static_edges = {175: 2, 955: 2, 959: 2, 960: 1}.get(task_id, 0)
        expect(
            failures,
            f"task {task_id} static-retry repair_edges",
            static_row.get("repair_edges"),
            expected_static_edges,
        )

    for mode in COMMUNITY43_MODES:
        gap_row = keyed.get((179, mode), {})
        expect(
            failures,
            f"task 179 {mode} correct_abstention",
            gap_row.get("correct_abstention"),
            True,
        )
        expect(
            failures,
            f"task 179 {mode} diagnosis_kind",
            gap_row.get("diagnosis_kind"),
            "data_gap",
        )

    verify_task959_scenario(failures, keyed.get((959, "closed_loop"), {}))
    verify_static_retry_scenario(failures, keyed.get((959, "static_retry"), {}))


def verify_task959_scenario(failures: list[str], result: dict[str, Any]) -> None:
    raw_state_path = result.get("run_state")
    if not isinstance(raw_state_path, str):
        failures.append("task 959 closed_loop: missing run_state path")
        return
    state_path = (PROJECT_ROOT / raw_state_path).resolve()
    if not state_path.is_relative_to(PROJECT_ROOT) or not state_path.is_file():
        failures.append("task 959 closed_loop: run_state path is absent or unsafe")
        return
    state = load_json(state_path)

    assets = state.get("assets")
    if not isinstance(assets, dict):
        failures.append("task 959 closed_loop: assets must be an object")
        return
    asset_rows = {
        asset.get("name"): asset.get("row_count")
        for asset in assets.values()
        if isinstance(asset, dict)
    }
    expect(
        failures,
        "task 959 source rows",
        asset_rows,
        {
            "D5 SHSAT Registrations and Testers.csv": 140,
            "2016 School Explorer.csv": 1272,
        },
    )

    states = state.get("materialized_states")
    if not isinstance(states, list) or not states:
        failures.append("task 959 closed_loop: materialized states are missing")
        return
    state_objects = [item for item in states if isinstance(item, dict)]
    if not state_objects:
        failures.append("task 959 closed_loop: materialized states are malformed")
        return
    final_state = max(
        state_objects,
        key=lambda item: int(item.get("iteration", -1)),
    )
    expect(failures, "task 959 final rows", final_state.get("row_count"), 21)
    metrics = final_state.get("metrics", {})
    expect(failures, "task 959 join left rows", metrics.get("join_left_rows"), 21)
    expect(failures, "task 959 join matched rows", metrics.get("join_matched_rows"), 21)
    expect(failures, "task 959 join coverage", metrics.get("join_coverage"), 1.0)
    expect(
        failures,
        "task 959 join keys",
        metrics.get("join_keys"),
        ["DBN", "Location Code"],
    )

    artifacts = state.get("artifacts")
    if not isinstance(artifacts, list):
        failures.append("task 959 closed_loop: artifacts must be a list")
        return
    artifact_values = {
        artifact.get("name"): round(float(artifact["value"]), 6)
        for artifact in artifacts
        if isinstance(artifact, dict) and artifact.get("value") is not None
    }
    expect(
        failures,
        "task 959 correlation artifacts",
        artifact_values,
        {
            "pearson_percent_asian": 0.434725,
            "pearson_percent_black_hispanic": -0.513048,
            "pearson_percent_white": 0.586734,
        },
    )

    report = state.get("report")
    claims = report.get("claims") if isinstance(report, dict) else None
    if not isinstance(claims, list):
        failures.append("task 959 closed_loop: report claims are missing")
        return
    artifact_ids = {
        artifact.get("artifact_id")
        for artifact in artifacts
        if isinstance(artifact, dict)
    }
    for index, claim in enumerate(claims):
        if not isinstance(claim, dict):
            failures.append(f"task 959 claim {index}: expected an object")
            continue
        refs = claim.get("artifact_refs")
        evidence_refs = claim.get("evidence_refs")
        if not isinstance(refs, list) or len(refs) != 1 or refs[0] not in artifact_ids:
            failures.append(f"task 959 claim {index}: invalid artifact lineage")
        if not isinstance(evidence_refs, list) or not evidence_refs:
            failures.append(f"task 959 claim {index}: missing executable evidence")

    violations = state.get("violations")
    repairs = state.get("repair_goals")
    if not isinstance(violations, list) or len(violations) != 1:
        failures.append("task 959 closed_loop: expected one typed violation")
    else:
        violation = violations[0]
        expect(
            failures,
            "task 959 violation route",
            (
                violation.get("type"),
                violation.get("detected_stage"),
                violation.get("responsible_stage"),
                violation.get("resolved"),
            ),
            ("missing_analytical_columns", "analysis", "discovery", True),
        )
    if not isinstance(repairs, list) or len(repairs) != 1:
        failures.append("task 959 closed_loop: expected one repair goal")
    else:
        repair = repairs[0]
        expect(
            failures,
            "task 959 repair goal",
            (repair.get("target_stage"), repair.get("status")),
            ("discovery", "completed"),
        )


def verify_static_retry_scenario(failures: list[str], result: dict[str, Any]) -> None:
    expect(
        failures, "task 959 static-retry status", result.get("status"), "insufficient"
    )
    expect(
        failures,
        "task 959 static-retry diagnosis",
        result.get("diagnosis_kind"),
        "budget_exhausted",
    )
    raw_state_path = result.get("run_state")
    if not isinstance(raw_state_path, str):
        failures.append("task 959 static-retry: missing run_state path")
        return
    state_path = (PROJECT_ROOT / raw_state_path).resolve()
    if not state_path.is_relative_to(PROJECT_ROOT) or not state_path.is_file():
        failures.append("task 959 static-retry: run_state path is absent or unsafe")
        return
    state = load_json(state_path)
    contract = state.get("contract")
    repair_goals = state.get("repair_goals")
    if not isinstance(contract, dict) or not isinstance(repair_goals, list):
        failures.append("task 959 static-retry: contract or repair goals are malformed")
        return
    initial_terms = contract.get("search_terms")
    expect(
        failures,
        "task 959 static-retry goal terms",
        [goal.get("search_terms") for goal in repair_goals if isinstance(goal, dict)],
        [initial_terms, initial_terms],
    )
    assets = state.get("assets")
    if not isinstance(assets, dict):
        failures.append("task 959 static-retry: assets must be an object")
        return
    expect(
        failures,
        "task 959 static-retry selected sources",
        [asset.get("name") for asset in assets.values() if isinstance(asset, dict)],
        [
            "D5 SHSAT Registrations and Testers.csv",
            "2017-2018 SHSAT Admissions Test Offers By Sending School.csv",
            "2010-2016-school-safety-report.csv",
        ],
    )
    source_decisions = state.get("source_decisions")
    if not isinstance(source_decisions, list) or len(source_decisions) != 3:
        failures.append("task 959 static-retry: expected three source decisions")
        return
    expect(
        failures,
        "task 959 static-retry decision reasons",
        [
            "unchanged initial question terms" in str(decision.get("reason", ""))
            for decision in source_decisions[1:]
            if isinstance(decision, dict)
        ],
        [True, True],
    )


def verify_community52(failures: list[str], summary: dict[str, Any]) -> None:
    verify_common(failures, "community52", summary)
    expect(failures, "community52.task_ids", summary.get("task_ids"), [590, 591])
    expect(
        failures,
        "community52.aggregate",
        summary.get("aggregate"),
        COMMUNITY52_AGGREGATE,
    )
    results = summary.get("results")
    if not isinstance(results, list):
        failures.append("community52.results: expected a list")
        return
    keyed = {row.get("task_id"): row for row in results if isinstance(row, dict)}
    expect(failures, "community52 result count", len(results), 2)
    expect(failures, "community52 unique task IDs", set(keyed), {590, 591})
    recomputed = {
        "tasks": len(results),
        "reports_completed": sum(row.get("status") == "completed" for row in results),
        "exact_matches": sum(bool(row.get("exact_match")) for row in results),
        "expected_sources_selected": sum(
            bool(row.get("expected_source_selected")) for row in results
        ),
        "repair_edges": sum(int(row.get("repair_edges", 0)) for row in results),
        "logical_source_profiles": sum(
            int(row.get("logical_source_profiles", 0)) for row in results
        ),
        "verified_source_profiles": sum(
            int(row.get("verified_source_profiles", 0)) for row in results
        ),
        "logical_profile_bytes": sum(
            int(row.get("logical_profile_bytes", 0)) for row in results
        ),
        "mandatory_human_interventions": sum(
            int(row.get("mandatory_human_interventions", 0)) for row in results
        ),
    }
    expect(
        failures,
        "community52 independently recomputed aggregate",
        summary.get("aggregate"),
        recomputed,
    )
    for task_id in (590, 591):
        row = keyed.get(task_id, {})
        expect(failures, f"task {task_id} exact_match", row.get("exact_match"), True)
        expect(
            failures,
            f"task {task_id} expected_source_selected",
            row.get("expected_source_selected"),
            True,
        )


def verify_paper(failures: list[str], path: Path) -> None:
    if not path.is_file():
        failures.append(f"paper: missing {path}")
        return
    normalized = " ".join(path.read_text(encoding="utf-8").split())
    required_fragments = [
        "typed repair goal can reopen Discovery and trigger downstream rematerialization",
        "repair an upstream source decision, then replay preparation and analysis",
        "typed violations create targeted backward edges to Discovery followed by downstream rematerialization",
        "closed-loop execution produces 14 exact reports and the correct local data-gap diagnosis",
        "Linear execution resolves 11/15 terminal outcomes",
        "same-budget static retry that ignores violation-specific search terms resolves 13/15",
        "typed repair resolves 15/15 with 18 profiles and four repairs",
        "Linear & 11/15 & 0 & 14",
        "Static retry & 13/15 & 7 & 21",
        "Closed loop & 15/15 & 4 & 18",
        "Full profile & 15/15 & 0 & 150",
        "Static retry recovers two of the four linear failures",
        r"logically exposes 1.356\,GB versus 7.48\,MB",
        r"match 2/2 answers",
        "Discovery first selects a 140-row SHSAT registration table",
        "adds a 1,272-row School Explorer table",
        "All 21 left-side records match",
        r"correlations $0.434725$, $-0.513048$, and $0.586734$",
    ]
    for fragment in required_fragments:
        if fragment not in normalized:
            failures.append(f"paper claim missing or drifted: {fragment!r}")
    for fragment in UNSUPPORTED_PAPER_CLAIMS:
        if fragment in normalized:
            failures.append(
                "paper claim exceeds the implemented Discovery-targeted repair "
                f"surface: {fragment!r}"
            )


def main() -> None:
    args = parse_args()
    failures: list[str] = []
    verify_community43(failures, load_json(args.community43))
    verify_community52(failures, load_json(args.community52))
    verify_paper(failures, args.paper)
    if failures:
        for failure in failures:
            print(f"ERROR: {failure}")
        raise SystemExit(f"FAILED: {len(failures)} reported-evidence assertion(s)")
    print(
        "PASS: reported evidence matches version 0.4.0 "
        "(60 community-43 mode runs, 2 community-52 runs, synchronized paper claims)."
    )


if __name__ == "__main__":
    main()
