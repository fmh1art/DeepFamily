from __future__ import annotations

import argparse
import json
import math
import os
import platform
import statistics
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = PROJECT_ROOT / "experiments/results/demo-path-latency.json"
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
USER_AGENT = "AskDU-Demo-Latency/0.4"


@dataclass(frozen=True)
class Scenario:
    task_id: int
    label: str
    expected_status: str
    expected_diagnosis: str | None
    minimum_repair_edges: int
    expect_report: bool


SCENARIOS = (
    Scenario(959, "Join repair", "completed", None, 1, True),
    Scenario(960, "Coverage repair", "completed", None, 1, True),
    Scenario(176, "Direct answer", "completed", None, 0, True),
    Scenario(179, "Honest data gap", "insufficient", "data_gap", 0, False),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Measure the four registered demo scenarios through the production HTTP path."
        )
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8080")
    parser.add_argument("--repetitions", type=int, default=10)
    parser.add_argument(
        "--interval-seconds",
        type=float,
        default=2.05,
        help="Pacing between POSTs; 2.05 seconds respects the default 30/minute limit.",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--trust-env-proxy",
        action="store_true",
        help="Opt in to HTTP(S)_PROXY for a remote HTTPS deployment.",
    )
    args = parser.parse_args()
    if not 1 <= args.repetitions <= 100:
        parser.error("--repetitions must be between 1 and 100")
    if not 0 <= args.interval_seconds <= 60:
        parser.error("--interval-seconds must be between 0 and 60")
    return args


def normalize_base_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or parsed.hostname is None:
        raise ValueError("base URL must be an absolute HTTP(S) origin")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("base URL must not contain credentials")
    if parsed.path not in {"", "/"} or parsed.params or parsed.query or parsed.fragment:
        raise ValueError(
            "base URL must be an origin without a path, query, or fragment"
        )
    loopback_hosts = {"127.0.0.1", "::1", "localhost"}
    if parsed.scheme == "http" and parsed.hostname.lower() not in loopback_hosts:
        raise ValueError("non-loopback benchmark targets must use HTTPS")
    return value.rstrip("/")


def summarize(samples: list[float]) -> dict[str, float | int]:
    if not samples:
        raise ValueError("at least one latency sample is required")
    ordered = sorted(samples)
    p95_rank = max(1, math.ceil(0.95 * len(ordered)))
    return {
        "count": len(ordered),
        "min": round(ordered[0], 3),
        "median": round(statistics.median(ordered), 3),
        "p95": round(ordered[p95_rank - 1], 3),
        "max": round(ordered[-1], 3),
    }


def request_json(
    opener: urllib.request.OpenerDirector,
    method: str,
    url: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        method=method,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
        },
    )
    try:
        with opener.open(request, timeout=30) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
            if len(raw) > MAX_RESPONSE_BYTES:
                raise RuntimeError(f"response exceeded {MAX_RESPONSE_BYTES} bytes")
            if response.status not in {200, 201}:
                raise RuntimeError(f"unexpected HTTP {response.status} for {url}")
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code} for {url}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"could not reach {url}: {exc.reason}") from exc
    decoded = json.loads(raw)
    if not isinstance(decoded, dict):
        raise TypeError(f"expected a JSON object from {url}")
    return decoded


def validate_result(scenario: Scenario, payload: dict[str, Any]) -> int:
    status = payload.get("status")
    if status != scenario.expected_status:
        raise RuntimeError(
            f"task {scenario.task_id} returned {status!r}, expected "
            f"{scenario.expected_status!r}"
        )
    diagnosis = payload.get("diagnosis")
    diagnosis_kind = diagnosis.get("kind") if isinstance(diagnosis, dict) else None
    if diagnosis_kind != scenario.expected_diagnosis:
        raise RuntimeError(
            f"task {scenario.task_id} diagnosis was {diagnosis_kind!r}, expected "
            f"{scenario.expected_diagnosis!r}"
        )
    if (payload.get("report") is not None) != scenario.expect_report:
        raise RuntimeError(
            f"task {scenario.task_id} violated its report/diagnosis boundary"
        )
    events = payload.get("events")
    if not isinstance(events, list):
        raise TypeError(f"task {scenario.task_id} returned no lifecycle events")
    repair_edges = sum(
        isinstance(event, dict) and event.get("edge_kind") == "repair"
        for event in events
    )
    if repair_edges < scenario.minimum_repair_edges:
        raise RuntimeError(
            f"task {scenario.task_id} exposed {repair_edges} repair edge(s), expected at least "
            f"{scenario.minimum_repair_edges}"
        )
    return repair_edges


def cpu_model() -> str | None:
    cpuinfo = Path("/proc/cpuinfo")
    if not cpuinfo.is_file():
        return platform.processor() or None
    for line in cpuinfo.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.lower().startswith("model name") and ":" in line:
            return line.split(":", 1)[1].strip()
    return platform.processor() or None


def pause(seconds: float) -> None:
    if seconds > 0:
        time.sleep(seconds)


def main() -> None:
    args = parse_args()
    try:
        base_url = normalize_base_url(args.base_url)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    opener = (
        urllib.request.build_opener()
        if args.trust_env_proxy
        else urllib.request.build_opener(urllib.request.ProxyHandler({}))
    )

    readiness = request_json(opener, "GET", f"{base_url}/readyz")
    environment = request_json(
        opener,
        "GET",
        f"{base_url}/api/v1/environments/current",
    )
    if readiness.get("status") != "ready":
        raise SystemExit("service did not report ready")
    if environment.get("planner_mode") != "registry":
        raise SystemExit(
            "this benchmark is locked to the deterministic registry planner"
        )
    examples = environment.get("example_questions")
    if not isinstance(examples, list):
        raise SystemExit("environment did not publish registered demo questions")
    questions = {
        item.get("task_id"): item.get("question")
        for item in examples
        if isinstance(item, dict)
    }
    missing = [
        scenario.task_id for scenario in SCENARIOS if scenario.task_id not in questions
    ]
    if missing:
        raise SystemExit(f"environment is missing registered demo task(s): {missing}")

    started_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    samples: dict[int, list[float]] = {scenario.task_id: [] for scenario in SCENARIOS}
    repair_edges: dict[int, set[int]] = {
        scenario.task_id: set() for scenario in SCENARIOS
    }

    print("Warming all four registered scenarios...", flush=True)
    for scenario in SCENARIOS:
        payload = request_json(
            opener,
            "POST",
            f"{base_url}/api/v1/runs",
            {"question": questions[scenario.task_id]},
        )
        validate_result(scenario, payload)
        pause(args.interval_seconds)

    for repetition in range(1, args.repetitions + 1):
        for scenario in SCENARIOS:
            started = time.perf_counter_ns()
            payload = request_json(
                opener,
                "POST",
                f"{base_url}/api/v1/runs",
                {"question": questions[scenario.task_id]},
            )
            elapsed_ms = (time.perf_counter_ns() - started) / 1_000_000
            repair_edges[scenario.task_id].add(validate_result(scenario, payload))
            samples[scenario.task_id].append(elapsed_ms)
            pause(args.interval_seconds)
        print(
            f"Completed measured repetition {repetition}/{args.repetitions}.",
            flush=True,
        )

    scenario_records = []
    published_samples: dict[int, list[float]] = {}
    for scenario in SCENARIOS:
        task_samples = [round(sample, 3) for sample in samples[scenario.task_id]]
        published_samples[scenario.task_id] = task_samples
        record = {
            "task_id": scenario.task_id,
            "label": scenario.label,
            "terminal_status": scenario.expected_status,
            "diagnosis_kind": scenario.expected_diagnosis,
            "observed_repair_edges": sorted(repair_edges[scenario.task_id]),
            "latency_ms": summarize(task_samples),
            "samples_ms": task_samples,
        }
        scenario_records.append(record)

    all_samples = [sample for values in published_samples.values() for sample in values]
    result = {
        "schema_version": "1.0",
        "recorded_at_utc": started_at,
        "scope": "steady-state serial production-HTTP demo-path responsiveness",
        "service": {
            "version": readiness.get("version"),
            "environment_id": environment.get("environment_id"),
            "planner_mode": environment.get("planner_mode"),
            "csv_assets": environment.get("csv_assets"),
        },
        "protocol": {
            "base_url": base_url,
            "route": "Nginx -> FastAPI POST /api/v1/runs",
            "warmups_per_scenario": 1,
            "repetitions_per_scenario": args.repetitions,
            "request_order": "four scenarios in task-id order, repeated serially",
            "interval_seconds": args.interval_seconds,
            "percentile_definition": "nearest-rank P95",
            "proxy_environment_inherited": args.trust_env_proxy,
        },
        "machine": {
            "platform": platform.platform(),
            "architecture": platform.machine(),
            "logical_cpus": os.cpu_count(),
            "cpu_model": cpu_model(),
            "python": platform.python_version(),
        },
        "overall_latency_ms": summarize(all_samples),
        "scenarios": scenario_records,
        "limitations": [
            "This is descriptive rehearsal evidence on one host, not a cross-system benchmark.",
            "It excludes image build, container startup, TLS, WAN, browser rendering, and model calls.",
            "Warm-ups remove first-request effects; host filesystem and OS page caches are not flushed.",
            "Requests are serial and paced to respect the deployed per-IP run limit.",
        ],
    }

    output = args.output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(
        f"PASS: {len(all_samples)} measured HTTP runs; overall median "
        f"{result['overall_latency_ms']['median']:.3f} ms, P95 "
        f"{result['overall_latency_ms']['p95']:.3f} ms.",
        flush=True,
    )
    for record in scenario_records:
        print(
            f"  task {record['task_id']} ({record['label']}): median "
            f"{record['latency_ms']['median']:.3f} ms, P95 "
            f"{record['latency_ms']['p95']:.3f} ms",
            flush=True,
        )
    print(f"Wrote {output}", flush=True)


if __name__ == "__main__":
    main()
