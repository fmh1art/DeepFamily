from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from askdu.adapters.catalog import FileCatalog
from askdu.adapters.repository import FileRunRepository
from askdu.application.agentic_pipeline import (
    DISCOVERY_SYSTEM_PROMPT,
    PREPARATION_SYSTEM_PROMPT,
    TREE_ACTION_ADAPTER,
    _json_request,
)
from askdu.application.orchestrator import RunService
from askdu.application.report_writer import REPORT_SYSTEM_PROMPT
from askdu.domain import AgentRole, AnalysisNotebookPhase, RunStatus


def test_operator_protocol_is_not_truncated_with_untrusted_observations() -> None:
    schema = TREE_ACTION_ADAPTER.json_schema()
    request = json.loads(
        _json_request(
            {
                "action_schema": schema,
                "observations": [{"cell": "x" * 900}],
            },
            500_000,
        )
    )
    assert request["action_schema"] == schema
    assert "[depth limit]" not in json.dumps(request["action_schema"])
    assert len(request["observations"][0]["cell"]) == 300


@pytest.mark.parametrize(
    ("scenario", "expected"),
    [
        ("discovery_budget", "budget_exhausted"),
        ("reported_data_gap", "data_gap"),
        ("preparation_capability", "capability_gap"),
        ("preparation_budget", "budget_exhausted"),
        ("repair_discovery_budget", "budget_exhausted"),
    ],
)
def test_agentic_stop_preserves_the_actual_failure_category(
    tmp_path: Path,
    scenario: str,
    expected: str,
) -> None:
    root = _environment(tmp_path)
    source_id = _plan(root)["sources"][0]["asset_id"]
    browse = {"action": "list_directory"}
    insufficient = {"action": "insufficient", "reason": "Required capability is unavailable."}
    actions = [
        {"action": "inspect_asset", "asset_id": source_id},
        {"action": "select_sources", "asset_ids": [source_id], "reason": "Inspected input."},
    ]
    if scenario == "discovery_budget":
        actions = [browse, browse]
    elif scenario == "reported_data_gap":
        actions = [{"action": "insufficient", "reason": "Required source is absent."}]
    elif scenario == "preparation_budget":
        actions += [{"action": "not_a_tool"}, {"action": "not_a_tool"}]
    else:
        actions += [insufficient]
        if scenario == "repair_discovery_budget":
            actions += [browse, browse]
    model = SequenceChatModel([json.dumps(action) for action in actions])
    runtime = tmp_path / "runtime"
    repository = FileRunRepository(runtime / "state")
    service = RunService(
        environment_id="synthetic-sales",
        data_root=root,
        runtime_root=runtime,
        repository=repository,
        agentic_model=model,
        discovery_max_turns=2,
        preparation_max_turns=2,
        max_repair_rounds=1 if scenario == "repair_discovery_budget" else 0,
    )
    state = service.run("Which customer tier earned the most completed-order revenue?")
    assert state.status == RunStatus.INSUFFICIENT
    assert state.report is None
    assert state.diagnosis is not None
    assert state.diagnosis.kind.value == expected
    persisted = repository.get(state.run_id)
    assert persisted is not None and persisted.diagnosis is not None
    assert persisted.diagnosis.kind == state.diagnosis.kind
    if scenario == "repair_discovery_budget":
        assert state.repair_goals[-1].status.value == "failed"
        assert len(state.discovery_hops) == 6


class SequenceChatModel:
    def __init__(self, responses: list[str]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def complete(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int = 2_000,
        temperature: float = 0.0,
    ) -> str:
        self.calls.append(
            {
                "system": system,
                "user": user,
                "max_tokens": max_tokens,
                "temperature": temperature,
            }
        )
        if system == REPORT_SYSTEM_PROMPT:
            request = json.loads(user)
            packet = request["evidence_packet"]
            artifacts = packet["artifacts"]
            refs = [artifact["artifact_id"] for artifact in artifacts]
            return json.dumps(
                {
                    "title": packet["planned_title"],
                    "executive_summary": "Enterprise has the highest completed-order revenue.",
                    "executive_artifact_refs": refs,
                    "sections": [
                        {
                            "title": "Revenue comparison",
                            "narrative": "The executed ranking places enterprise first.",
                            "artifact_refs": refs,
                        }
                    ],
                    "conclusion": "Enterprise leads within the completed orders in scope.",
                    "conclusion_artifact_refs": refs,
                    "limitations": ["The result covers only the supplied order records."],
                }
            )
        return self.responses.pop(0)


def _environment(tmp_path: Path) -> Path:
    root = tmp_path / "full_community"
    root.mkdir()
    pd.DataFrame(
        {
            "customer_id": [1, 2, 1, 3],
            "status": ["complete", "complete", "cancelled", "complete"],
            "revenue": [100, 10, 999, 150],
        }
    ).to_csv(root / "orders.csv", index=False)
    pd.DataFrame(
        {
            "id": [1, 2, 3],
            "tier": ["standard", "standard", "enterprise"],
        }
    ).to_csv(root / "customers.csv", index=False)
    pd.DataFrame({"weather": ["sunny"]}).to_csv(root / "noise.csv", index=False)
    return root


def _plan(root: Path) -> dict[str, Any]:
    by_name = {asset.name: asset for asset in FileCatalog(root).index().values()}
    return {
        "schema_version": "1.0",
        "summary": "Find the tier with the largest completed-order revenue.",
        "search_terms": ["orders", "customers", "revenue", "tier"],
        "sources": [
            {
                "alias": "orders",
                "asset_id": by_name["orders.csv"].asset_id,
                "required_columns": ["customer_id", "status", "revenue"],
                "purpose": "Completed order revenue",
            },
            {
                "alias": "customers",
                "asset_id": by_name["customers.csv"].asset_id,
                "required_columns": ["id", "tier"],
                "purpose": "Customer tier lookup",
            },
        ],
        "preparation": [
            {
                "type": "filter",
                "input_table": "orders",
                "output_table": "completed",
                "predicates": [
                    {
                        "column": "status",
                        "operator": "eq",
                        "value": "complete",
                        "case_sensitive": False,
                    }
                ],
                "combine": "all",
            },
            {
                "type": "join",
                "left_table": "completed",
                "right_table": "customers",
                "output_table": "enriched",
                "left_on": ["customer_id"],
                "right_on": ["id"],
                "how": "inner",
                "suffixes": ["order", "customer"],
            },
        ],
        "analyses": [
            {
                "type": "group_aggregate",
                "name": "top_tier_by_revenue",
                "table": "enriched",
                "group_by": ["tier"],
                "function": "sum",
                "column": "revenue",
                "sort_direction": "descending",
                "limit": 1,
                "unit": "USD",
                "display_precision": 2,
            }
        ],
        "primary_table": "enriched",
        "report_title": "Completed revenue by tier",
    }


def test_agentic_run_uses_one_model_for_discovery_and_tree_execution(tmp_path: Path) -> None:
    root = _environment(tmp_path)
    plan = _plan(root)
    orders_id = plan["sources"][0]["asset_id"]
    customers_id = plan["sources"][1]["asset_id"]
    responses = [
        json.dumps(
            {
                "action": "search_catalog",
                "terms": ["orders", "customers", "revenue", "tier"],
                "limit": 10,
            }
        ),
        json.dumps({"action": "inspect_asset", "asset_id": orders_id}),
        json.dumps({"action": "inspect_asset", "asset_id": customers_id}),
        json.dumps(
            {
                "action": "select_sources",
                "asset_ids": [orders_id, customers_id],
                "reason": "Orders provide the measure and customers provide the grouping key.",
            }
        ),
        json.dumps(
            {
                "action": "expand",
                "parent_candidate_id": None,
                "reason": "Filter completed orders, join tiers, and aggregate revenue.",
                "plan": plan,
            }
        ),
        json.dumps(
            {
                "action": "finish",
                "candidate_id": "candidate_1",
                "reason": "The executed result directly answers the question.",
            }
        ),
    ]
    model = SequenceChatModel(responses)
    runtime = tmp_path / "runtime"
    service = RunService(
        environment_id="synthetic-sales",
        data_root=root,
        runtime_root=runtime,
        repository=FileRunRepository(runtime / "state"),
        agentic_model=model,
        discovery_max_turns=8,
        preparation_max_turns=4,
    )

    state = service.run("Which customer tier earned the most completed-order revenue?")

    assert state.status == RunStatus.COMPLETED, state.error
    assert service.planner_mode == "agentic"
    assert len(model.calls) == 7
    assert {call["system"] for call in model.calls[:4]} == {DISCOVERY_SYSTEM_PROMPT}
    assert [json.loads(call["user"])["remaining_turns"] for call in model.calls[:4]] == [8, 7, 6, 5]
    assert {call["system"] for call in model.calls[4:6]} == {PREPARATION_SYSTEM_PROMPT}
    assert model.calls[-1]["system"] == REPORT_SYSTEM_PROMPT
    assert all(call["temperature"] == 0.0 for call in model.calls)
    assert [trace.agent for trace in state.agent_traces].count(AgentRole.DISCOVERY) == 4
    assert [trace.agent for trace in state.agent_traces].count(AgentRole.PREPARATION) == 2
    assert [hop.action for hop in state.discovery_hops] == [
        "environment_root",
        "search_catalog",
        "inspect_asset",
        "inspect_asset",
        "select_sources",
    ]
    assert state.discovery_hops[-1].selected_asset_ids == [orders_id, customers_id]
    assert len(state.preparation_attempts) == 1
    assert state.preparation_attempts[0].status.value == "selected"
    assert [operator.operator_type for operator in state.preparation_attempts[0].operators] == [
        "Filter",
        "Join",
        "Terminate",
    ]
    assert state.preparation_attempts[0].operators[0].output_rows == 3
    assert len(state.materialized_states) == 1
    assert state.materialized_states[0].parent_state_ids == []
    assert state.materialized_states[0].column_schema["tier"] == "object"
    assert state.materialized_states[0].preview_rows[0]["tier"] == "standard"
    assert state.artifacts[0].value == [{"tier": "enterprise", "value": 150}]
    assert state.report is not None
    assert "enterprise" in state.report.markdown
    assert state.contract is not None
    assert state.contract.compilation.kind == "model"
    assert [step.phase for step in state.analysis_notebook] == [
        AnalysisNotebookPhase.ANALYZE,
        AnalysisNotebookPhase.UNDERSTAND,
        AnalysisNotebookPhase.CODE,
        AnalysisNotebookPhase.EXECUTE,
        AnalysisNotebookPhase.ANALYZE,
        AnalysisNotebookPhase.ANSWER,
        AnalysisNotebookPhase.REPORT,
    ]
    code_step = state.analysis_notebook[2]
    assert code_step.language == "sql"
    assert code_step.source_code is not None and "GROUP BY" in code_step.source_code
    assert state.analysis_notebook[3].artifact_refs == [state.artifacts[0].artifact_id]
    assert state.analysis_notebook[3].duration_ms is not None
    assert state.report.executive_summary.startswith("Enterprise")
    assert state.report.sections[0].artifact_refs == [state.artifacts[0].artifact_id]
    assert any(
        trace.agent == AgentRole.ANALYSIS and trace.action == "finish_report"
        for trace in state.agent_traces
    )


def test_analysis_notebook_records_a_real_debug_fallback(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    root = _environment(tmp_path)
    plan = _plan(root)
    orders_id = plan["sources"][0]["asset_id"]
    customers_id = plan["sources"][1]["asset_id"]
    actions = [
        {
            "action": "search_catalog",
            "terms": ["orders", "customers", "revenue", "tier"],
            "limit": 10,
        },
        {"action": "inspect_asset", "asset_id": orders_id},
        {"action": "inspect_asset", "asset_id": customers_id},
        {
            "action": "select_sources",
            "asset_ids": [orders_id, customers_id],
            "reason": "Both inspected tables are required.",
        },
        {
            "action": "expand",
            "parent_candidate_id": None,
            "reason": "Execute the preparation plan.",
            "plan": plan,
        },
        {
            "action": "finish",
            "candidate_id": "candidate_1",
            "reason": "The bounded candidate is valid.",
        },
    ]
    model = SequenceChatModel([json.dumps(action) for action in actions])

    def reject_compiled_cell(*_args: Any, **_kwargs: Any) -> Any:
        raise RuntimeError("simulated SQL runtime mismatch")

    monkeypatch.setattr(
        "askdu.application.orchestrator.execute_analysis_cell",
        reject_compiled_cell,
    )
    runtime = tmp_path / "runtime"
    service = RunService(
        environment_id="synthetic-sales",
        data_root=root,
        runtime_root=runtime,
        repository=FileRunRepository(runtime / "state"),
        agentic_model=model,
        discovery_max_turns=8,
        preparation_max_turns=4,
    )

    state = service.run("Which customer tier earned the most completed-order revenue?")

    assert state.status == RunStatus.COMPLETED, state.error
    debug = next(
        step for step in state.analysis_notebook if step.phase == AnalysisNotebookPhase.DEBUG
    )
    execute = next(
        step for step in state.analysis_notebook if step.phase == AnalysisNotebookPhase.EXECUTE
    )
    assert debug.status.value == "failed"
    assert debug.output == "RuntimeError: verification failed"
    assert execute.runtime == "bounded_dataframe_fallback"
    assert execute.output == [{"tier": "enterprise", "value": 150}]
    assert execute.duration_ms is not None


def test_discovery_rejects_uninspected_selection(tmp_path: Path) -> None:
    root = _environment(tmp_path)
    plan = _plan(root)
    orders_id = plan["sources"][0]["asset_id"]
    model = SequenceChatModel(
        [
            json.dumps(
                {
                    "action": "select_sources",
                    "asset_ids": [orders_id],
                    "reason": "Guess without inspecting.",
                }
            ),
            json.dumps(
                {
                    "action": "insufficient",
                    "reason": "No inspected source was established within the budget.",
                }
            ),
        ]
    )
    runtime = tmp_path / "runtime"
    service = RunService(
        environment_id="synthetic-sales",
        data_root=root,
        runtime_root=runtime,
        repository=FileRunRepository(runtime / "state"),
        agentic_model=model,
        discovery_max_turns=2,
        preparation_max_turns=2,
    )

    state = service.run("Which customer tier earned the most completed-order revenue?")

    assert state.status == RunStatus.INSUFFICIENT
    assert state.report is None
    assert state.diagnosis is not None
    assert state.diagnosis.kind.value == "data_gap"
    assert state.discovery_hops[-2].status.value == "rejected"
    assert "inspected" in (state.discovery_hops[-2].error or "")


def test_preparation_can_backtrack_from_an_observed_candidate(tmp_path: Path) -> None:
    root = _environment(tmp_path)
    corrected = _plan(root)
    unfiltered = json.loads(json.dumps(corrected))
    unfiltered["summary"] = "Aggregate before checking whether cancelled orders distort the result."
    unfiltered["preparation"] = [unfiltered["preparation"][1]]
    unfiltered["preparation"][0]["left_table"] = "orders"
    orders_id = corrected["sources"][0]["asset_id"]
    customers_id = corrected["sources"][1]["asset_id"]
    actions = [
        {
            "action": "search_catalog",
            "terms": ["orders", "customers", "revenue", "tier"],
            "limit": 10,
        },
        {"action": "inspect_asset", "asset_id": orders_id},
        {"action": "inspect_asset", "asset_id": customers_id},
        {
            "action": "select_sources",
            "asset_ids": [orders_id, customers_id],
            "reason": "Both inspected tables are required.",
        },
        {
            "action": "expand",
            "parent_candidate_id": None,
            "reason": "Inspect an initial aggregation branch.",
            "plan": unfiltered,
        },
        {
            "action": "expand",
            "parent_candidate_id": "candidate_1",
            "reason": "Backtrack and exclude cancelled orders before aggregation.",
            "plan": corrected,
        },
        {
            "action": "finish",
            "candidate_id": "candidate_2",
            "reason": "The corrected executed branch matches the question.",
        },
    ]
    model = SequenceChatModel([json.dumps(action) for action in actions])
    runtime = tmp_path / "runtime"
    service = RunService(
        environment_id="synthetic-sales",
        data_root=root,
        runtime_root=runtime,
        repository=FileRunRepository(runtime / "state"),
        agentic_model=model,
        discovery_max_turns=8,
        preparation_max_turns=5,
    )

    state = service.run("Which customer tier earned the most completed-order revenue?")

    assert state.status == RunStatus.COMPLETED, state.error
    assert len(state.materialized_states) == 2
    assert state.materialized_states[1].parent_state_ids == [state.materialized_states[0].state_id]
    assert state.artifacts[0].value == [{"tier": "enterprise", "value": 150}]
    assert [attempt.status.value for attempt in state.preparation_attempts] == [
        "materialized",
        "selected",
    ]
    assert state.preparation_attempts[1].parent_candidate_id == "candidate_1"


def test_preparation_feedback_can_reopen_discovery_and_replay(tmp_path: Path) -> None:
    root = _environment(tmp_path)
    plan = _plan(root)
    orders_id = plan["sources"][0]["asset_id"]
    customers_id = plan["sources"][1]["asset_id"]
    actions = [
        {
            "action": "search_catalog",
            "terms": ["orders", "revenue"],
            "limit": 10,
        },
        {"action": "inspect_asset", "asset_id": orders_id},
        {
            "action": "select_sources",
            "asset_ids": [orders_id],
            "reason": "Start with the transaction table.",
        },
        {
            "action": "insufficient",
            "reason": "The selected table has no customer tier dimension.",
        },
        {
            "action": "search_catalog",
            "terms": ["customers", "tier"],
            "limit": 10,
        },
        {"action": "inspect_asset", "asset_id": customers_id},
        {
            "action": "select_sources",
            "asset_ids": [orders_id, customers_id],
            "reason": "Add the inspected tier lookup requested by preparation feedback.",
        },
        {
            "action": "expand",
            "parent_candidate_id": None,
            "reason": "Execute the repaired two-source preparation plan.",
            "plan": plan,
        },
        {
            "action": "finish",
            "candidate_id": "candidate_1",
            "reason": "The repaired branch answers the question.",
        },
    ]
    model = SequenceChatModel([json.dumps(action) for action in actions])
    runtime = tmp_path / "runtime"
    service = RunService(
        environment_id="synthetic-sales",
        data_root=root,
        runtime_root=runtime,
        repository=FileRunRepository(runtime / "state"),
        max_repair_rounds=2,
        agentic_model=model,
        discovery_max_turns=6,
        preparation_max_turns=3,
    )

    state = service.run("Which customer tier earned the most completed-order revenue?")

    assert state.status == RunStatus.COMPLETED, state.error
    assert len(state.source_decisions) == 2
    assert state.source_decisions[1].newly_selected_source_ids == [customers_id]
    assert len(state.violations) == 1
    assert state.violations[0].resolved is True
    assert len(state.repair_goals) == 1
    assert state.repair_goals[0].status.value == "completed"
    assert state.artifacts[0].value == [{"tier": "enterprise", "value": 150}]
