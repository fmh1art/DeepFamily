from __future__ import annotations

import json
import runpy
from pathlib import Path
from typing import Any

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MODULE: dict[str, Any] = runpy.run_path(str(PROJECT_ROOT / "scripts/benchmark_demo_path.py"))
VERIFIER: dict[str, Any] = runpy.run_path(str(PROJECT_ROOT / "scripts/verify_demo_latency.py"))


def test_base_url_requires_https_away_from_loopback() -> None:
    normalize_base_url = MODULE["normalize_base_url"]

    assert normalize_base_url("http://127.0.0.1:8080/") == "http://127.0.0.1:8080"
    assert normalize_base_url("https://demo.example") == "https://demo.example"
    with pytest.raises(ValueError, match="must use HTTPS"):
        normalize_base_url("http://demo.example")
    with pytest.raises(ValueError, match="must not contain credentials"):
        normalize_base_url("https://user:secret@demo.example")
    with pytest.raises(ValueError, match="without a path"):
        normalize_base_url("https://demo.example/hidden")


def test_latency_summary_uses_nearest_rank_p95() -> None:
    summarize = MODULE["summarize"]

    assert summarize([1.0, 2.0, 3.0, 4.0, 100.0]) == {
        "count": 5,
        "min": 1.0,
        "median": 3.0,
        "p95": 100.0,
        "max": 100.0,
    }


def test_result_validation_enforces_terminal_and_repair_boundary() -> None:
    scenarios = MODULE["SCENARIOS"]
    validate_result = MODULE["validate_result"]
    join_repair = scenarios[0]
    payload = {
        "status": "completed",
        "diagnosis": None,
        "report": {"report_id": "report_1"},
        "events": [{"edge_kind": "repair"}],
    }

    assert validate_result(join_repair, payload) == 1
    payload["events"] = []
    with pytest.raises(RuntimeError, match="expected at least 1"):
        validate_result(join_repair, payload)


def test_checked_latency_evidence_recomputes_and_rejects_tampering() -> None:
    evidence_path = VERIFIER["EVIDENCE_PATH"]
    validate_evidence = VERIFIER["validate_evidence"]
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))

    assert validate_evidence(evidence) == {
        "count": 40,
        "min": 7.285,
        "median": 21.475,
        "p95": 57.882,
        "max": 58.374,
    }
    evidence["scenarios"][0]["samples_ms"][0] = 999.0
    with pytest.raises(ValueError, match="task 959 latency summary"):
        validate_evidence(evidence)
