from __future__ import annotations

import json
from typing import Any

from askdu.application.report_writer import REPORT_SYSTEM_PROMPT, ModelReportWriter
from askdu.domain import (
    AgentTurnStatus,
    AnalysisArtifact,
    DataAsset,
    DeclarativeAnalysisPlan,
    MaterializedState,
)


class StaticChatModel:
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
        return self.responses.pop(0)


def _inputs() -> tuple[
    DeclarativeAnalysisPlan,
    list[DataAsset],
    MaterializedState,
    list[AnalysisArtifact],
]:
    asset_id = "asset_0123456789abcdef"
    plan = DeclarativeAnalysisPlan.model_validate(
        {
            "summary": "Compare candidate countries across executed quality and cost metrics.",
            "search_terms": ["country", "quality", "cost"],
            "sources": [
                {
                    "alias": "countries",
                    "asset_id": asset_id,
                    "required_columns": ["country", "quality", "cost"],
                    "purpose": "Country comparison",
                }
            ],
            "analyses": [
                {
                    "type": "rows",
                    "name": "quality_ranking",
                    "table": "countries",
                    "columns": ["country", "quality"],
                },
                {
                    "type": "rows",
                    "name": "cost_ranking",
                    "table": "countries",
                    "columns": ["country", "cost"],
                },
            ],
            "primary_table": "countries",
            "report_title": "Country comparison",
        }
    )
    assets = [
        DataAsset(
            asset_id=asset_id,
            relative_path="community_1/countries.csv",
            name="countries.csv",
            columns=["country", "quality", "cost"],
            byte_size=128,
            row_count=2,
        )
    ]
    state = MaterializedState(
        state_id="state_country",
        iteration=0,
        source_ids=[asset_id],
        row_count=2,
        columns=["country", "quality", "cost"],
        column_schema={"country": "object", "quality": "float64", "cost": "float64"},
        preview_rows=[{"country": "A", "quality": 8.0, "cost": 4.0}],
    )
    artifacts = [
        AnalysisArtifact(
            artifact_id="artifact_quality",
            kind="table",
            name="quality_ranking",
            value=[{"country": "A", "quality": 8.0}],
            source_state_ids=[state.state_id],
        ),
        AnalysisArtifact(
            artifact_id="artifact_cost",
            kind="table",
            name="cost_ranking",
            value=[{"country": "B", "cost": 3.0}],
            source_state_ids=[state.state_id],
        ),
    ]
    return plan, assets, state, artifacts


def test_report_writer_accepts_a_multidimensional_grounded_report() -> None:
    plan, assets, state, artifacts = _inputs()
    model = StaticChatModel(
        [
            json.dumps(
                {
                    "title": "移民候选国家比较",
                    "executive_summary": "A 的质量指标较高, B 的成本指标较低。",
                    "executive_artifact_refs": ["artifact_quality", "artifact_cost"],
                    "sections": [
                        {
                            "title": "生活质量",
                            "narrative": "执行结果中 A 的质量指标为 8.0。",
                            "artifact_refs": ["artifact_quality"],
                        },
                        {
                            "title": "成本",
                            "narrative": "执行结果中 B 的成本指标为 3.0。",
                            "artifact_refs": ["artifact_cost"],
                        },
                    ],
                    "conclusion": "两个维度指向不同候选国, 最终选择取决于权重。",
                    "conclusion_artifact_refs": ["artifact_quality", "artifact_cost"],
                    "limitations": ["没有用户指定的维度权重。"],
                },
                ensure_ascii=False,
            )
        ]
    )

    composition = ModelReportWriter(model=model).compose(
        question="最适合移民的国家是哪一个?",
        plan=plan,
        assets=assets,
        state=state,
        artifacts=artifacts,
    )

    assert composition.used_fallback is False
    assert [section.title for section in composition.narrative.sections] == ["生活质量", "成本"]
    assert composition.traces[-1].status == AgentTurnStatus.ACCEPTED
    assert model.calls[0]["system"] == REPORT_SYSTEM_PROMPT
    request = json.loads(model.calls[0]["user"])
    assert request["evidence_packet"]["prepared_data"]["schema"]["cost"] == "float64"
    assert request["evidence_packet"]["artifacts"][0]["value"][0]["country"] == "A"
    assert [item["name"] for item in request["evidence_packet"]["executed_method"]["analyses"]] == [
        "quality_ranking",
        "cost_ranking",
    ]


def test_report_writer_rejects_unknown_references_and_falls_back() -> None:
    plan, assets, state, artifacts = _inputs()
    invalid = json.dumps(
        {
            "title": "Unsupported report",
            "executive_summary": "Unsupported summary.",
            "executive_artifact_refs": ["artifact_unknown"],
            "sections": [
                {
                    "title": "Unsupported",
                    "narrative": "Unsupported narrative.",
                    "artifact_refs": ["artifact_unknown"],
                }
            ],
            "conclusion": "Unsupported conclusion.",
            "conclusion_artifact_refs": ["artifact_unknown"],
            "limitations": ["Unknown."],
        }
    )
    model = StaticChatModel([invalid, invalid])

    composition = ModelReportWriter(model=model).compose(
        question="Which country is best?",
        plan=plan,
        assets=assets,
        state=state,
        artifacts=artifacts,
    )

    assert composition.used_fallback is True
    assert len(composition.traces) == 2
    assert {trace.status for trace in composition.traces} == {AgentTurnStatus.REJECTED}
    section_refs = {
        ref for section in composition.narrative.sections for ref in section.artifact_refs
    }
    assert section_refs == {"artifact_quality", "artifact_cost"}
    assert "beyond the executed metrics" in composition.narrative.conclusion


def test_report_fallback_preserves_the_question_language() -> None:
    plan, assets, state, artifacts = _inputs()
    model = StaticChatModel(["{}", "{}"])

    composition = ModelReportWriter(model=model).compose(
        question="最适合移民的国家是哪一个?",
        plan=plan,
        assets=assets,
        state=state,
        artifacts=artifacts,
    )

    assert composition.used_fallback is True
    assert composition.narrative.executive_summary.startswith("系统完成了")
    assert composition.narrative.conclusion.startswith("现有证据支持")
