"""Opt-in evaluation receipts. Never record HTTP bodies, headers, URLs or error messages.

Uses the SDK's public custom-http-client boundary, not its private implementation.
Receipts are observations, not invoices: a dispatched request may outlive this process.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections import Counter
from collections.abc import Iterator, Mapping
from contextlib import contextmanager, nullcontext
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from askdu.adapters.llm import ChatModelError
from askdu.application.ports import ChatModel
from askdu.heldout_integrity import atomic_write_json

METER_SCHEMA = "askdu.model-usage/1"
TOKEN_FIELDS = (
    "prompt_tokens",
    "completion_tokens",
    "total_tokens",
    "cached_prompt_tokens",
    "cache_write_prompt_tokens",
    "reasoning_completion_tokens",
)


class MeteringError(RuntimeError):
    """Stop inference when a durable measurement boundary cannot be maintained."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def usage_receipt(body: Any) -> dict[str, Any]:
    """Retain an integer allowlist without coercing absent or malformed values to zero."""
    usage = body.get("usage") if isinstance(body, dict) else None
    if usage is None:
        return {"usage_status": "absent", "tokens": {}}
    if not isinstance(usage, dict):
        return {"usage_status": "invalid", "tokens": {}, "usage_issue": "not_an_object"}
    tokens: dict[str, int] = {}
    invalid = False
    for target, container, key in (
        ("prompt_tokens", usage, "prompt_tokens"),
        ("completion_tokens", usage, "completion_tokens"),
        ("total_tokens", usage, "total_tokens"),
        ("cached_prompt_tokens", usage.get("prompt_tokens_details"), "cached_tokens"),
        ("cache_write_prompt_tokens", usage.get("prompt_tokens_details"), "cache_write_tokens"),
        ("reasoning_completion_tokens", usage.get("completion_tokens_details"), "reasoning_tokens"),
    ):
        if container is None:
            continue
        if not isinstance(container, dict):
            invalid = True
            continue
        value = container.get(key)
        if value is None:
            continue
        if type(value) is not int or value < 0:
            invalid = True
        else:
            tokens[target] = value
    complete = all(field in tokens for field in TOKEN_FIELDS[:3])
    if complete and tokens["total_tokens"] != tokens["prompt_tokens"] + tokens["completion_tokens"]:
        invalid = True
    for detail, total in (
        ("cached_prompt_tokens", "prompt_tokens"),
        ("cache_write_prompt_tokens", "prompt_tokens"),
        ("reasoning_completion_tokens", "completion_tokens"),
    ):
        if detail in tokens and total in tokens and tokens[detail] > tokens[total]:
            invalid = True
    result: dict[str, Any] = {
        "usage_status": "invalid" if invalid else "reported" if complete else "partial",
        "tokens": tokens,
    }
    if invalid:
        result["usage_issue"] = "malformed_or_inconsistent_counts"
    return result


def summarize_calls(calls: list[dict[str, Any]]) -> dict[str, Any]:
    for call in calls:
        if call["status"] not in {"started", "completed", "failed"}:
            raise ValueError("Invalid logical-call state")
    attempts = [attempt for call in calls for attempt in call.get("http_attempts", [])]
    for attempt in attempts:
        if attempt["status"] not in {"started", "response", "error", "not_sent"}:
            raise ValueError("Invalid HTTP-attempt state")
        if attempt.get("usage_status") not in {
            "unavailable",
            "absent",
            "partial",
            "reported",
            "invalid",
        }:
            raise ValueError("Invalid usage state")
        if any(
            field not in TOKEN_FIELDS or type(value) is not int or value < 0
            for field, value in attempt.get("tokens", {}).items()
        ):
            raise ValueError("Invalid persisted token counts")
    dispatched = [attempt for attempt in attempts if attempt["status"] != "not_sent"]
    receipts = [a for a in dispatched if a.get("usage_status") in {"reported", "partial"}]
    token_totals = {}
    for field in TOKEN_FIELDS:
        values = [a["tokens"][field] for a in receipts if field in a["tokens"]]
        token_totals[field] = {
            "observed_total": sum(values) if values else None,
            "attempts_with_value": len(values),
            "attempts_without_value": len(dispatched) - len(values),
        }
    return {
        "logical_calls": len(calls),
        "logical_status_counts": dict(Counter(call["status"] for call in calls)),
        "unresolved_logical_calls": sum(call["status"] == "started" for call in calls),
        "calls_without_http_observer": sum(not call.get("http_observed", False) for call in calls),
        "http_attempts_started": len(dispatched),
        "http_attempts_not_sent": len(attempts) - len(dispatched),
        "unresolved_http_attempts": sum(a["status"] == "started" for a in dispatched),
        "additional_http_attempts": sum(
            max(0, sum(a["status"] != "not_sent" for a in c.get("http_attempts", [])) - 1)
            for c in calls
        ),
        "http_status_counts": dict(
            Counter(str(a["http_status"]) for a in dispatched if "http_status" in a)
        ),
        "usage_status_counts": dict(
            Counter(a.get("usage_status", "unavailable") for a in dispatched)
        ),
        "tokens": token_totals,
    }


def read_usage_summary(path: Path) -> dict[str, Any]:
    """Reconstruct crash/timeout observations from the last durable call journal."""
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        return {"availability": "missing", "logical_calls": None, "http_attempts_started": None}
    except OSError:
        return {"availability": "unreadable", "logical_calls": None, "http_attempts_started": None}
    try:
        document = json.loads(raw)
        if document["schema_version"] != METER_SCHEMA or not isinstance(document["calls"], list):
            raise ValueError("Unsupported call journal")
        return {
            "availability": "available",
            "journal_sha256": hashlib.sha256(raw).hexdigest(),
            "persistence_error_type": document.get("persistence_error_type"),
            **summarize_calls(document["calls"]),
        }
    except (AttributeError, KeyError, TypeError, ValueError):
        return {"availability": "invalid", "logical_calls": None, "http_attempts_started": None}


class MeteredHttpClient(httpx.Client):
    """Observe each SDK send, including retries, within an explicit logical-call context."""

    def __init__(self, *, timeout: float, transport: httpx.BaseTransport | None = None) -> None:
        super().__init__(
            timeout=timeout, transport=transport, follow_redirects=False, trust_env=False
        )
        self._observation: ContextVar[tuple[MeteredChatModel, dict[str, Any]] | None] = ContextVar(
            "provider_meter_observation", default=None
        )

    @contextmanager
    def observe(self, meter: MeteredChatModel, call: dict[str, Any]) -> Iterator[None]:
        token = self._observation.set((meter, call))
        try:
            yield
        finally:
            self._observation.reset(token)

    def send(self, request: httpx.Request, **kwargs: Any) -> httpx.Response:
        observation = self._observation.get()
        if observation is None:
            raise MeteringError("Evaluation HTTP requests require a logical-call context")
        meter, call = observation
        meter.assert_healthy()
        if kwargs.get("stream") or kwargs.get("follow_redirects") is True:
            raise MeteringError("Evaluation metering requires non-streaming, no-redirect requests")
        attempt: dict[str, Any] = {
            "number": len(call["http_attempts"]) + 1,
            "started_at": _now(),
            "status": "started",
            "usage_status": "unavailable",
        }
        call["http_attempts"].append(attempt)
        meter.persist_quietly()
        if meter.persistence_error_type is not None:
            attempt["status"] = "not_sent"
            meter.assert_healthy()
        started = time.perf_counter()
        try:
            response = super().send(request, **kwargs)
            attempt.update(status="response", http_status=response.status_code)
            if len(response.content) > 8_000_000:
                attempt.update(usage_status="unavailable", usage_issue="response_too_large")
            else:
                try:
                    attempt.update(usage_receipt(response.json()))
                except Exception:
                    # Receipt extraction must not turn a received response into an
                    # SDK transport error and thereby trigger another request.
                    attempt.update(usage_status="unavailable", usage_issue="unreadable_usage")
            return response
        except Exception as exc:
            attempt.update(status="error", error_type=type(exc).__name__)
            raise
        finally:
            attempt["duration_seconds"] = time.perf_counter() - started
            # Do not raise a telemetry write error inside SDK send: it could retry a
            # completed, billable response. Latch it, block further sends, and raise
            # outside the SDK when the enclosing logical call returns.
            meter.persist_quietly()


class MeteredChatModel(ChatModel):
    """Durable per-call cap and usage receipts; the passed HTTP client is caller-owned."""

    def __init__(
        self,
        model: ChatModel,
        output: Path,
        cap: int = 68,
        *,
        http_client: MeteredHttpClient | None = None,
        phases: Mapping[str, str] | None = None,
    ) -> None:
        if cap < 1:
            raise ValueError("The logical-call cap must be positive")
        if output.exists() or output.is_symlink():
            raise MeteringError("An existing call journal must never be overwritten")
        self.model, self.output, self.cap = model, output, cap
        self.http_client, self.phases = http_client, phases or {}
        self.calls: list[dict[str, Any]] = []
        self.persistence_error_type: str | None = None
        self.persist_quietly()
        self.assert_healthy()

    def assert_healthy(self) -> None:
        if self.persistence_error_type is not None:
            raise MeteringError("Call journal persistence failed; no further requests allowed")

    def persist_quietly(self) -> None:
        try:
            atomic_write_json(
                self.output,
                {
                    "schema_version": METER_SCHEMA,
                    "calls": self.calls,
                    "persistence_error_type": self.persistence_error_type,
                    "summary": summarize_calls(self.calls),
                    "interpretation": (
                        "Provider-reported tokens, not invoice cost. Missing values are unknown. "
                        "Started attempts do not prove provider receipt or cancellation. "
                        "Cached/reasoning counts are components, not extra total tokens."
                    ),
                },
            )
        except Exception as exc:
            self.persistence_error_type = type(exc).__name__

    def complete(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int = 2000,
        temperature: float = 0.0,
    ) -> str:
        self.assert_healthy()
        if len(self.calls) >= self.cap:
            raise ChatModelError("Evaluation completion budget exhausted")
        record: dict[str, Any] = {
            "phase": self.phases.get(system, "unknown"),
            "started_at": _now(),
            "input_characters": len(system) + len(user),
            "request_sha256": hashlib.sha256((system + "\0" + user).encode()).hexdigest(),
            "requested_output_token_cap": max_tokens,
            "status": "started",
            "http_observed": self.http_client is not None,
            "http_attempts": [],
        }
        self.calls.append(record)
        self.persist_quietly()
        self.assert_healthy()
        started = time.perf_counter()
        observation = self.http_client.observe(self, record) if self.http_client else nullcontext()
        try:
            with observation:
                answer = self.model.complete(
                    system=system, user=user, max_tokens=max_tokens, temperature=temperature
                )
            record.update(
                status="completed",
                output_characters=len(answer),
                response_sha256=hashlib.sha256(answer.encode()).hexdigest(),
            )
            return answer
        except Exception as exc:
            record.update(status="failed", error_type=type(exc).__name__)
            raise
        finally:
            record["duration_seconds"] = time.perf_counter() - started
            self.persist_quietly()
            self.assert_healthy()
