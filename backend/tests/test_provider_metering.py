from __future__ import annotations

import json
import multiprocessing
import os
import signal
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from pathlib import Path
from threading import Barrier
from typing import Any

import httpx
import pytest

from askdu.adapters import provider_metering as metering
from askdu.adapters.llm import ChatModelError
from askdu.adapters.provider_metering import (
    MeteredChatModel,
    MeteredHttpClient,
    MeteringError,
    read_usage_summary,
    usage_receipt,
)
from askdu.bootstrap import build_chat_model
from askdu.config import PROJECT_LLM_MODEL, Settings

USAGE = {
    "prompt_tokens": 13,
    "completion_tokens": 7,
    "total_tokens": 20,
    "prompt_tokens_details": {"cached_tokens": 5, "cache_write_tokens": 2},
    "completion_tokens_details": {"reasoning_tokens": 3},
    "unknown_private_field": "PRIVATE_RESPONSE",
}


def completion(usage: Any = USAGE, *, content: str = "PRIVATE_ANSWER") -> dict[str, Any]:
    return {
        "id": "PRIVATE_COMPLETION_ID",
        "object": "chat.completion",
        "created": 123,
        "model": PROJECT_LLM_MODEL,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": usage,
    }


@pytest.fixture
def meter_factory(tmp_path: Path) -> Iterator[Callable[..., MeteredChatModel]]:
    with ExitStack() as stack:

        def make(
            handler: Callable[[httpx.Request], httpx.Response],
            *,
            cap: int = 1,
            retries: int = 2,
            name: str = "calls",
            client: MeteredHttpClient | None = None,
        ) -> MeteredChatModel:
            if client is None:
                client = stack.enter_context(
                    MeteredHttpClient(
                        timeout=1,
                        transport=httpx.MockTransport(handler),
                    )
                )
            settings = Settings(
                _env_file=None,
                llm_base_url="https://private-gateway.invalid/api?api-version=test",
                llm_api_key="PRIVATE_FAKE_KEY",
                llm_model=PROJECT_LLM_MODEL,
                llm_api_style="azure_chat",
                llm_auth_scheme="api_key",
                llm_token_field="max_completion_tokens",
                llm_allow_test_provider=True,
                llm_max_retries=retries,
            )
            return MeteredChatModel(
                build_chat_model(settings, http_client=client),
                tmp_path / f"{name}.json",
                cap,
                http_client=client,
                phases={"PRIVATE_SYSTEM": "discovery"},
            )

        yield make


def test_success_receipt_uses_allowlisted_counts_and_preserves_logical_cap(
    meter_factory: Callable[..., MeteredChatModel],
) -> None:
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["model"] == PROJECT_LLM_MODEL
        assert body["max_completion_tokens"] == 321
        assert "temperature" not in body
        assert request.headers["api-key"] == "PRIVATE_FAKE_KEY"
        requests.append(request)
        return httpx.Response(200, json=completion(), headers={"x-request-id": "PRIVATE_HEADER"})

    meter = meter_factory(handler)
    assert (
        meter.complete(system="PRIVATE_SYSTEM", user="PRIVATE_INPUT", max_tokens=321)
        == "PRIVATE_ANSWER"
    )
    with pytest.raises(ChatModelError, match="budget"):
        meter.complete(system="x", user="x")
    assert len(requests) == 1
    journal = json.loads(meter.output.read_text())
    assert "PRIVATE" not in meter.output.read_text()
    assert "private-gateway" not in meter.output.read_text()
    assert journal["calls"][0]["phase"] == "discovery"
    usage = read_usage_summary(meter.output)
    assert usage["logical_calls"] == usage["http_attempts_started"] == 1
    assert usage["tokens"]["total_tokens"]["observed_total"] == 20
    assert usage["tokens"]["cached_prompt_tokens"]["observed_total"] == 5
    assert usage["tokens"]["reasoning_completion_tokens"]["observed_total"] == 3
    assert usage["usage_status_counts"] == {"reported": 1}


def test_sdk_retries_are_distinct_attempts_not_extra_logical_calls(
    meter_factory: Callable[..., MeteredChatModel],
) -> None:
    statuses = iter([429, 500, 200])

    def handler(request: httpx.Request) -> httpx.Response:
        status = next(statuses)
        body = completion() if status == 200 else {"error": {"message": "PRIVATE_ERROR"}}
        return httpx.Response(status, json=body, headers={"retry-after": "0"})

    meter = meter_factory(handler)
    meter.complete(system="PRIVATE_SYSTEM", user="PRIVATE_INPUT")
    summary = read_usage_summary(meter.output)
    assert summary["logical_calls"] == 1
    assert summary["http_attempts_started"] == 3
    assert summary["additional_http_attempts"] == 2
    assert summary["http_status_counts"] == {"429": 1, "500": 1, "200": 1}
    assert summary["tokens"]["total_tokens"] == {
        "observed_total": 20,
        "attempts_with_value": 1,
        "attempts_without_value": 2,
    }
    assert "PRIVATE" not in meter.output.read_text()


@pytest.mark.parametrize(
    "usage,status,observed",
    [
        (None, "absent", None),
        ({"prompt_tokens": 13}, "partial", None),
        ({"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}, "reported", 0),
        ({"prompt_tokens": True, "completion_tokens": 7, "total_tokens": 8}, "invalid", None),
        ({"prompt_tokens": 13, "completion_tokens": 7, "total_tokens": 99}, "invalid", None),
    ],
)
def test_missing_partial_and_invalid_usage_never_become_zero_cost(
    meter_factory: Callable[..., MeteredChatModel],
    usage: Any,
    status: str,
    observed: int | None,
) -> None:
    meter = meter_factory(lambda request: httpx.Response(200, json=completion(usage)))
    meter.complete(system="x", user="x")
    summary = read_usage_summary(meter.output)
    assert summary["usage_status_counts"] == {status: 1}
    assert summary["tokens"]["total_tokens"]["observed_total"] == observed
    if status == "partial":
        assert summary["tokens"]["prompt_tokens"]["observed_total"] == 13


@pytest.mark.parametrize("invalid", [-1, True, 2.5, "13"])
def test_receipt_parser_does_not_coerce_invalid_token_counts(invalid: Any) -> None:
    receipt = usage_receipt({"usage": {"prompt_tokens": invalid}})
    assert receipt["usage_status"] == "invalid"
    assert receipt["tokens"] == {}


def test_optional_token_breakdowns_are_components_not_additional_totals() -> None:
    assert (
        usage_receipt({"usage": {**USAGE, "prompt_tokens_details": {"cached_tokens": 14}}})[
            "usage_status"
        ]
        == "invalid"
    )
    assert (
        usage_receipt({"usage": {**USAGE, "completion_tokens_details": "PRIVATE"}})["usage_status"]
        == "invalid"
    )
    assert usage_receipt({"usage": "PRIVATE"})["tokens"] == {}


@pytest.mark.parametrize("empty_content", [False, True])
def test_usage_is_retained_when_a_response_does_not_produce_a_completion(
    meter_factory: Callable[..., MeteredChatModel],
    empty_content: bool,
) -> None:
    meter = meter_factory(
        lambda request: httpx.Response(
            200 if empty_content else 400,
            json=completion(content=""),
        )
    )
    with pytest.raises(ChatModelError):
        meter.complete(system="x", user="x")
    summary = read_usage_summary(meter.output)
    assert summary["logical_status_counts"] == {"failed": 1}
    assert summary["http_attempts_started"] == 1
    assert summary["tokens"]["total_tokens"]["observed_total"] == 20


def test_transport_timeouts_retain_attempts_without_leaking_exception_messages(
    meter_factory: Callable[..., MeteredChatModel],
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("PRIVATE_PROVIDER_ERROR", request=request)

    meter = meter_factory(handler)
    with pytest.raises(ChatModelError):
        meter.complete(system="x", user="x")
    summary = read_usage_summary(meter.output)
    assert summary["logical_status_counts"] == {"failed": 1}
    assert summary["http_attempts_started"] == 3
    assert summary["tokens"]["total_tokens"]["observed_total"] is None
    assert "PRIVATE" not in meter.output.read_text()


def test_interrupted_call_remains_unresolved_and_cannot_be_overwritten(
    meter_factory: Callable[..., MeteredChatModel],
    tmp_path: Path,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise SystemExit("PRIVATE_INTERRUPTION")

    meter = meter_factory(handler)
    with pytest.raises(SystemExit):
        meter.complete(system="x", user="x")
    summary = read_usage_summary(meter.output)
    assert summary["unresolved_logical_calls"] == summary["unresolved_http_attempts"] == 1
    assert summary["tokens"]["total_tokens"]["observed_total"] is None
    original = meter.output.read_bytes()
    with pytest.raises(MeteringError, match="overwritten"):
        meter_factory(handler)
    assert meter.output.read_bytes() == original
    assert read_usage_summary(tmp_path / "missing.json")["logical_calls"] is None


def test_initialized_zero_calls_and_invalid_journals_are_distinguishable(
    meter_factory: Callable[..., MeteredChatModel],
    tmp_path: Path,
) -> None:
    meter = meter_factory(lambda request: pytest.fail("Unexpected HTTP request"))
    assert read_usage_summary(meter.output)["logical_calls"] == 0
    invalid = tmp_path / "invalid.json"
    invalid.write_text("{partial")
    assert read_usage_summary(invalid)["availability"] == "invalid"
    invalid.write_text(
        json.dumps(
            {
                "schema_version": metering.METER_SCHEMA,
                "calls": [
                    {
                        "status": "completed",
                        "http_attempts": [
                            {
                                "status": "response",
                                "usage_status": "reported",
                                "tokens": {"total_tokens": -1},
                            }
                        ],
                    }
                ],
            }
        )
    )
    assert read_usage_summary(invalid)["availability"] == "invalid"


def test_hard_killed_worker_leaves_a_durable_unresolved_attempt(
    meter_factory: Callable[..., MeteredChatModel],
    tmp_path: Path,
) -> None:
    def worker() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            os.kill(os.getpid(), signal.SIGKILL)
            raise AssertionError("Killed worker continued")

        meter = meter_factory(handler, name="killed")
        meter.complete(system="x", user="x")

    process = multiprocessing.get_context("fork").Process(target=worker)
    process.start()
    try:
        process.join(5)
        assert not process.is_alive()
        assert process.exitcode == -signal.SIGKILL
        summary = read_usage_summary(tmp_path / "killed.json")
        assert summary["unresolved_logical_calls"] == summary["unresolved_http_attempts"] == 1
        assert summary["tokens"]["total_tokens"]["observed_total"] is None
    finally:
        if process.is_alive():
            process.terminate()
            process.join(5)


@pytest.mark.parametrize(
    "fail_write,status,expected_requests",
    [(1, 200, 0), (2, 200, 0), (3, 200, 0), (4, 200, 1), (4, 429, 1), (5, 200, 1)],
)
def test_journal_failure_cannot_trigger_extra_provider_requests(
    meter_factory: Callable[..., MeteredChatModel],
    monkeypatch: Any,
    fail_write: int,
    status: int,
    expected_requests: int,
) -> None:
    writes = requests = 0
    original = metering.atomic_write_json

    def write(path: Path, payload: Any) -> None:
        nonlocal writes
        writes += 1
        if writes == fail_write:
            raise OSError("PRIVATE_DISK_ERROR")
        original(path, payload)

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal requests
        requests += 1
        return httpx.Response(status, json=completion(), headers={"retry-after": "0"})

    monkeypatch.setattr(metering, "atomic_write_json", write)
    if fail_write == 1:
        with pytest.raises(MeteringError):
            meter_factory(handler)
    else:
        meter = meter_factory(handler)
        with pytest.raises(MeteringError):
            meter.complete(system="x", user="x")
        with pytest.raises(MeteringError):
            meter.complete(system="x", user="x")
        assert "PRIVATE" not in meter.output.read_text()
        if fail_write == 3:
            assert read_usage_summary(meter.output)["http_attempts_not_sent"] == 1
    assert requests == expected_requests


def test_custom_http_client_refuses_unmetered_requests() -> None:
    with (
        MeteredHttpClient(
            timeout=1,
            transport=httpx.MockTransport(
                lambda request: pytest.fail("Unexpected HTTP request"),
            ),
        ) as client,
        pytest.raises(MeteringError, match="logical-call context"),
    ):
        client.get("https://not-called.invalid")


def test_receipt_extraction_failure_does_not_retry_a_completed_response(
    meter_factory: Callable[..., MeteredChatModel],
    monkeypatch: Any,
) -> None:
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=completion())

    def bad_parser(body: Any) -> dict[str, Any]:
        raise RuntimeError("PRIVATE_PARSER_ERROR")

    monkeypatch.setattr(metering, "usage_receipt", bad_parser)
    meter = meter_factory(handler)
    assert meter.complete(system="x", user="x") == "PRIVATE_ANSWER"
    assert len(requests) == 1
    assert read_usage_summary(meter.output)["usage_status_counts"] == {"unavailable": 1}
    assert "PRIVATE" not in meter.output.read_text()


def test_shared_http_client_keeps_concurrent_call_contexts_separate(
    meter_factory: Callable[..., MeteredChatModel],
) -> None:
    barrier = Barrier(2)

    def handler(request: httpx.Request) -> httpx.Response:
        count = int(json.loads(request.content)["messages"][-1]["content"])
        barrier.wait(timeout=5)
        return httpx.Response(
            200,
            json=completion(
                {
                    "prompt_tokens": count,
                    "completion_tokens": 1,
                    "total_tokens": count + 1,
                }
            ),
        )

    with MeteredHttpClient(timeout=1, transport=httpx.MockTransport(handler)) as client:
        left = meter_factory(handler, client=client, name="left")
        right = meter_factory(handler, client=client, name="right")
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [
                pool.submit(m.complete, system="x", user=str(n))
                for m, n in [(left, 13), (right, 29)]
            ]
            for future in futures:
                future.result(timeout=10)
        assert read_usage_summary(left.output)["tokens"]["prompt_tokens"]["observed_total"] == 13
        assert read_usage_summary(right.output)["tokens"]["prompt_tokens"]["observed_total"] == 29
