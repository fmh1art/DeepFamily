from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from typing import Any, cast

import httpx
import pytest
from fastapi.testclient import TestClient

from askdu.adapters.catalog import FileCatalog
from askdu.adapters.llm import ChatModelError, DirectChatCompletionsModel
from deployment.api import create_app
from deployment.config import DeploymentSettings

ProviderResponse = tuple[int, dict[str, Any], dict[str, str]]


class _ProviderServer(ThreadingHTTPServer):
    def __init__(self, responses: list[ProviderResponse]) -> None:
        super().__init__(("127.0.0.1", 0), _ProviderHandler)
        self.responses = list(responses)
        self.requests: list[dict[str, Any]] = []


class _ProviderHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_POST(self) -> None:
        server = cast(_ProviderServer, self.server)
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length).decode("utf-8"))
        server.requests.append(
            {
                "path": self.path,
                "payload": payload,
                "authorization": self.headers.get("Authorization"),
                "api_key": self.headers.get("api-key"),
            }
        )
        status, response_payload, headers = server.responses.pop(0)
        encoded = json.dumps(response_payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        for name, value in headers.items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, format: str, *args: object) -> None:
        return


@contextmanager
def _provider(responses: list[ProviderResponse]) -> Iterator[_ProviderServer]:
    server = _ProviderServer(responses)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def _completion(content: str) -> dict[str, Any]:
    return {
        "id": "chatcmpl-contract-test",
        "object": "chat.completion",
        "created": 0,
        "model": "contract-test-model",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
    }


def _single_source_plan(root: Path) -> dict[str, Any]:
    assets = FileCatalog(root).index()
    registration = next(
        asset for asset in assets.values() if asset.name == "D5 SHSAT Registrations and Testers.csv"
    )
    return {
        "schema_version": "1.0",
        "summary": "Count Grade 8 SHSAT registration rows in 2016.",
        "search_terms": ["SHSAT", "Grade level", "2016"],
        "sources": [
            {
                "alias": "registrations",
                "asset_id": registration.asset_id,
                "required_columns": ["Year of SHST", "Grade level"],
                "purpose": "Grade-level SHSAT registration records",
            }
        ],
        "preparation": [
            {
                "type": "filter",
                "input_table": "registrations",
                "output_table": "grade8_2016",
                "predicates": [
                    {"column": "Year of SHST", "operator": "eq", "value": 2016},
                    {"column": "Grade level", "operator": "eq", "value": 8},
                ],
                "combine": "all",
            }
        ],
        "analyses": [
            {
                "type": "aggregate",
                "name": "grade8_2016_rows",
                "table": "grade8_2016",
                "function": "count_rows",
                "unit": "rows",
                "display_precision": 0,
            }
        ],
        "primary_table": "grade8_2016",
        "report_title": "Grade 8 SHSAT registrations in 2016",
    }


def test_azure_gateway_contract_retries_and_runs_end_to_end(
    sample_environment: Path,
    tmp_path: Path,
) -> None:
    question = "How many Grade 8 SHSAT registration rows are present in 2016?"
    plan = json.dumps(_single_source_plan(sample_environment))
    responses: list[ProviderResponse] = [
        (429, {"error": {"message": "retry later"}}, {"Retry-After": "0"}),
        (200, _completion(plan), {}),
    ]

    with _provider(responses) as provider:
        host, port = provider.server_address
        endpoint = (
            f"http://{host}:{port}/api/modelhub/online/v2/crawl?api-version=2024-03-01-preview"
        )
        runtime = tmp_path / "runtime"
        settings = DeploymentSettings(
            environment_id="provider-contract",
            data_root=sample_environment,
            runtime_root=runtime,
            planner_mode="model",
            planner_max_attempts=1,
            llm_base_url=endpoint,
            llm_model="contract-test-model",
            llm_api_key="test-secret",
            llm_api_style="azure_chat",
            llm_auth_scheme="api_key",
            llm_token_field="max_completion_tokens",
            llm_timeout_seconds=2,
            llm_max_retries=1,
            llm_allow_test_provider=True,
        )
        client = TestClient(create_app(settings))

        response = client.post("/api/v1/runs", json={"question": question})
        environment = client.get("/api/v1/environments/current")

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "completed", body.get("error")
    assert body["artifacts"][0]["name"] == "grade8_2016_rows"
    assert body["artifacts"][0]["value"] == 4
    assert body["contract"]["compilation"]["kind"] == "model"
    assert environment.json()["planner_mode"] == "model"
    assert environment.json()["example_questions"] == []
    assert "test-secret" not in response.text
    assert "test-secret" not in (runtime / "state" / f"{body['run_id']}.json").read_text()

    assert len(provider.requests) == 2
    expected_path = (
        "/api/modelhub/online/v2/crawl/openai/deployments/contract-test-model/"
        "chat/completions?api-version=2024-03-01-preview"
    )
    assert {request["path"] for request in provider.requests} == {expected_path}
    request = provider.requests[-1]
    assert request["authorization"] is None
    assert request["api_key"] == "test-secret"
    assert request["payload"]["model"] == "contract-test-model"
    assert request["payload"]["max_completion_tokens"] == 8_000
    assert "max_tokens" not in request["payload"]
    assert "temperature" not in request["payload"]
    assert [message["role"] for message in request["payload"]["messages"]] == [
        "system",
        "user",
    ]


def test_direct_endpoint_error_does_not_echo_provider_body() -> None:
    responses: list[ProviderResponse] = [
        (401, {"error": {"message": "private upstream detail"}}, {}),
    ]
    with _provider(responses) as provider:
        host, port = provider.server_address
        with httpx.Client(timeout=2, trust_env=False) as client:
            model = DirectChatCompletionsModel(
                endpoint=f"http://{host}:{port}/complete",
                api_key="test-secret",
                model="contract-test-model",
                max_retries=0,
                client=client,
            )
            with pytest.raises(ChatModelError) as captured:
                model.complete(system="System instruction", user="Analytical question")

    assert str(captured.value) == "Provider request failed with HTTP 401"
    assert "private upstream detail" not in str(captured.value)


def test_agentic_stages_share_one_exact_provider_endpoint(
    sample_environment: Path,
    tmp_path: Path,
) -> None:
    question = "How many Grade 8 SHSAT registration rows are present in 2016?"
    plan = _single_source_plan(sample_environment)
    source_id = plan["sources"][0]["asset_id"]
    actions = [
        {
            "action": "search_catalog",
            "terms": ["SHSAT", "registrations", "Grade level", "2016"],
            "limit": 10,
        },
        {"action": "inspect_asset", "asset_id": source_id},
        {
            "action": "select_sources",
            "asset_ids": [source_id],
            "reason": "The inspected registration table contains year and grade fields.",
        },
        {
            "action": "expand",
            "parent_candidate_id": None,
            "reason": "Filter the inspected table and count the resulting rows.",
            "plan": plan,
        },
        {
            "action": "finish",
            "candidate_id": "candidate_1",
            "reason": "The executed count answers the question.",
        },
    ]
    responses: list[ProviderResponse] = [
        *((200, _completion(json.dumps(action)), {}) for action in actions),
        (200, _completion("{}"), {}),
        (200, _completion("{}"), {}),
    ]

    with _provider(responses) as provider:
        host, port = provider.server_address
        endpoint = (
            f"http://{host}:{port}/api/modelhub/online/v2/crawl?api-version=2024-03-01-preview"
        )
        runtime = tmp_path / "runtime"
        settings = DeploymentSettings(
            environment_id="provider-agentic-contract",
            data_root=sample_environment,
            runtime_root=runtime,
            planner_mode="agentic",
            discovery_max_turns=5,
            preparation_max_turns=4,
            llm_base_url=endpoint,
            llm_model="contract-test-model",
            llm_api_key="test-secret",
            llm_api_style="azure_chat",
            llm_auth_scheme="api_key",
            llm_token_field="max_completion_tokens",
            llm_timeout_seconds=2,
            llm_max_retries=0,
            llm_allow_test_provider=True,
        )
        client = TestClient(create_app(settings))

        response = client.post("/api/v1/runs", json={"question": question})

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "completed", body.get("error")
    assert len(body["agent_traces"]) == 7
    assert {trace["agent"] for trace in body["agent_traces"]} == {
        "discovery",
        "preparation",
        "analysis",
    }
    assert body["report"]["sections"][0]["artifact_refs"] == [body["artifacts"][0]["artifact_id"]]
    assert len(provider.requests) == 7
    expected_path = (
        "/api/modelhub/online/v2/crawl/openai/deployments/contract-test-model/"
        "chat/completions?api-version=2024-03-01-preview"
    )
    assert {request["path"] for request in provider.requests} == {expected_path}
    assert {request["api_key"] for request in provider.requests} == {"test-secret"}
    assert {request["authorization"] for request in provider.requests} == {None}
    assert {request["payload"]["model"] for request in provider.requests} == {"contract-test-model"}
    assert all("temperature" not in request["payload"] for request in provider.requests)
    assert "test-secret" not in response.text
    persisted = runtime / "state" / f"{body['run_id']}.json"
    assert "test-secret" not in persisted.read_text(encoding="utf-8")
