from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from askdu.api.redaction import PUBLIC_RUN_FAILURE
from askdu.application.examples import demo_questions_for_environment
from askdu.application.orchestrator import RunCapacityError
from askdu.domain import RunState, RunStatus
from deployment.api import (
    _public_run_state,
    create_app,
    get_run_service,
)
from deployment.config import DeploymentSettings
from deployment.repository import ManagedFileRunRepository
from tests.conftest import PILOT_QUESTION, write_test_provenance_manifest


def test_health_and_run_api(sample_environment: Path, tmp_path: Path) -> None:
    settings = DeploymentSettings(
        environment_id="test-community",
        data_root=sample_environment,
        runtime_root=tmp_path / "runtime",
    )
    client = TestClient(create_app(settings))

    health = client.get("/healthz")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"

    readiness = client.get("/readyz")
    assert readiness.status_code == 200
    assert readiness.json() == {
        "status": "ready",
        "version": health.json()["version"],
        "environment_id": "test-community",
        "csv_assets": 4,
    }

    environment = client.get("/api/v1/environments/current")
    assert environment.status_code == 200
    environment_payload = environment.json()
    assert environment_payload["environment_id"] == "test-community"
    assert environment_payload["available"] is True
    assert environment_payload["csv_assets"] == 4
    assert environment_payload["planner_mode"] == "registry"
    assert environment_payload["run_retention_hours"] == 0
    assert environment_payload["run_deletion_supported"] is True
    assert environment_payload["catalog_provenance"] is None
    assert [example["task_id"] for example in environment_payload["example_questions"]] == [
        959,
        960,
        176,
        179,
    ]

    created = client.post("/api/v1/runs", json={"question": PILOT_QUESTION})
    assert created.status_code == 201
    assert created.headers["cache-control"] == "no-store"
    body = created.json()
    assert body["status"] == "completed"
    assert body["question"] == PILOT_QUESTION
    assert any(event["edge_kind"] == "repair" for event in body["events"])

    fetched = client.get(f"/api/v1/runs/{body['run_id']}")
    assert fetched.status_code == 200
    assert fetched.headers["cache-control"] == "no-store"
    assert fetched.json()["run_id"] == body["run_id"]

    deleted = client.delete(f"/api/v1/runs/{body['run_id']}")
    assert deleted.status_code == 204
    assert deleted.content == b""
    assert deleted.headers["cache-control"] == "no-store"
    assert not (settings.runtime_root / "state" / f"{body['run_id']}.json").exists()
    assert not (settings.runtime_root / "runs" / body["run_id"]).exists()
    assert client.get(f"/api/v1/runs/{body['run_id']}").status_code == 404
    assert client.delete(f"/api/v1/runs/{body['run_id']}").status_code == 404


def test_background_run_returns_immediately_and_is_pollable(
    sample_environment: Path,
    tmp_path: Path,
) -> None:
    settings = DeploymentSettings(
        environment_id="test-community",
        data_root=sample_environment,
        runtime_root=tmp_path / "runtime",
    )
    client = TestClient(create_app(settings))

    submitted = client.post(
        "/api/v1/runs?background=true",
        json={"question": PILOT_QUESTION},
    )

    assert submitted.status_code == 202
    body = submitted.json()
    assert body["status"] in {"pending", "running", "completed"}
    terminal = body
    for _ in range(100):
        terminal = client.get(f"/api/v1/runs/{body['run_id']}").json()
        if terminal["status"] not in {"pending", "running"}:
            break
        time.sleep(0.01)
    assert terminal["status"] == "completed"
    assert terminal["report"] is not None


def test_readiness_sweeps_expired_runs_when_retention_is_enabled(
    sample_environment: Path,
    tmp_path: Path,
) -> None:
    runtime_root = tmp_path / "runtime"
    repository = ManagedFileRunRepository(runtime_root / "state", runtime_root / "runs")
    timestamp = datetime.now(timezone.utc) - timedelta(hours=2)
    expired = RunState(
        environment_id="test-community",
        question="How many sufficiently old records should this deployment remove?",
        status=RunStatus.COMPLETED,
        created_at=timestamp,
        updated_at=timestamp,
    )
    repository.save(expired)
    active = RunState(
        environment_id="test-community",
        question=(
            "How many old active records must remain until execution reaches a terminal state?"
        ),
        status=RunStatus.RUNNING,
        created_at=timestamp,
        updated_at=timestamp,
    )
    repository.save(active)
    report = runtime_root / "runs" / expired.run_id / "reports" / "report.md"
    report.parent.mkdir(parents=True)
    report.write_text("expired report", encoding="utf-8")
    settings = DeploymentSettings(
        environment_id="test-community",
        data_root=sample_environment,
        runtime_root=runtime_root,
        run_retention_hours=1,
    )
    client = TestClient(create_app(settings))

    readiness = client.get("/readyz")

    assert readiness.status_code == 200
    assert not (runtime_root / "state" / f"{expired.run_id}.json").exists()
    assert not (runtime_root / "runs" / expired.run_id).exists()
    assert (runtime_root / "state" / f"{active.run_id}.json").is_file()
    active_delete = client.delete(f"/api/v1/runs/{active.run_id}")
    assert active_delete.status_code == 409
    assert active_delete.json() == {"detail": "Run is still active"}
    assert (runtime_root / "state" / f"{active.run_id}.json").is_file()
    environment = client.get("/api/v1/environments/current").json()
    assert environment["run_retention_hours"] == 1
    assert environment["run_deletion_supported"] is True


def test_run_payload_rejects_dataset_hints(sample_environment: Path, tmp_path: Path) -> None:
    settings = DeploymentSettings(
        environment_id="test-community",
        data_root=sample_environment,
        runtime_root=tmp_path / "runtime",
    )
    client = TestClient(create_app(settings))

    response = client.post(
        "/api/v1/runs",
        json={"question": PILOT_QUESTION, "filename": "oracle.csv"},
    )

    assert response.status_code == 422


def test_environment_examples_follow_the_configured_community(
    sample_environment: Path,
    tmp_path: Path,
) -> None:
    settings = DeploymentSettings(
        environment_id="coda-community-52",
        data_root=sample_environment,
        provenance_manifest=None,
        runtime_root=tmp_path / "runtime",
    )
    client = TestClient(create_app(settings))

    response = client.get("/api/v1/environments/current")

    assert response.status_code == 200
    assert [example["task_id"] for example in response.json()["example_questions"]] == [
        590,
        591,
    ]


def test_registered_environment_publishes_provenance_not_data_downloads(
    sample_environment: Path,
    tmp_path: Path,
) -> None:
    manifest_path = write_test_provenance_manifest(sample_environment, tmp_path)
    settings = DeploymentSettings(
        environment_id="coda-community-43",
        data_root=sample_environment,
        provenance_manifest=manifest_path,
        runtime_root=tmp_path / "runtime",
    )
    client = TestClient(create_app(settings))

    environment = client.get("/api/v1/environments/current").json()
    provenance = environment["catalog_provenance"]
    assert provenance["revision"] == "63828a2b652e26a9770555a0cc41e6c8aafdb5d9"
    assert provenance["data_access_policy"] == "download_only"
    assert provenance["source_data_bundled"] is False
    assert provenance["csv_asset_count"] == 4

    paths = client.get("/openapi.json").json()["paths"]
    assert not any("download" in path or "/assets/" in path for path in paths)


def test_tampered_registered_source_fails_closed_with_a_redacted_error(
    sample_environment: Path,
    tmp_path: Path,
) -> None:
    manifest_path = write_test_provenance_manifest(
        sample_environment,
        tmp_path,
        tamper_relative_path=(
            "data_science_for_good/source/D5 SHSAT Registrations and Testers.csv"
        ),
    )
    settings = DeploymentSettings(
        environment_id="coda-community-43",
        data_root=sample_environment,
        provenance_manifest=manifest_path,
        runtime_root=tmp_path / "runtime",
    )
    client = TestClient(create_app(settings))

    created = client.post("/api/v1/runs", json={"question": PILOT_QUESTION})

    assert created.status_code == 201
    body = created.json()
    assert body["status"] == "failed"
    assert body["error"] == PUBLIC_RUN_FAILURE
    assert body["report"] is None
    assert "checksum" not in created.text.lower()
    assert str(sample_environment) not in created.text

    fetched = client.get(f"/api/v1/runs/{body['run_id']}")
    assert fetched.status_code == 200
    assert fetched.json()["error"] == PUBLIC_RUN_FAILURE
    assert "checksum" not in fetched.text.lower()


def test_model_planner_environment_does_not_publish_registered_examples() -> None:
    assert demo_questions_for_environment("custom-environment", "model") == ()


def test_untrusted_host_is_rejected(sample_environment: Path, tmp_path: Path) -> None:
    settings = DeploymentSettings(
        data_root=sample_environment,
        runtime_root=tmp_path / "runtime",
    )
    client = TestClient(create_app(settings))

    response = client.get("/healthz", headers={"host": "attacker.example"})

    assert response.status_code == 400
    assert response.text == "Invalid host header"


def test_failed_run_error_is_redacted_without_changing_private_state() -> None:
    private = RunState(
        environment_id="test-community",
        question="Why did this sufficiently long analytical request fail?",
        status=RunStatus.FAILED,
        error="RuntimeError: /private/runtime/path and provider detail",
    )

    public = _public_run_state(private)

    assert public.error == PUBLIC_RUN_FAILURE
    assert private.error == "RuntimeError: /private/runtime/path and provider detail"


def test_provider_failure_exposes_only_safe_actionable_status() -> None:
    private = RunState(
        environment_id="test-community",
        question="Why did this sufficiently long analytical request fail?",
        status=RunStatus.FAILED,
        error="ChatModelError: Provider request failed with HTTP 400",
    )

    public = _public_run_state(private)

    assert public.error is not None
    assert "HTTP 400" in public.error
    assert "gateway profile" in public.error
    assert public.error != private.error


def test_busy_run_capacity_maps_to_retryable_503(
    sample_environment: Path,
    tmp_path: Path,
) -> None:
    class BusyService:
        def run(self, question: str) -> RunState:
            raise RunCapacityError("private capacity detail")

    settings = DeploymentSettings(
        data_root=sample_environment,
        runtime_root=tmp_path / "runtime",
    )
    application = create_app(settings)
    application.dependency_overrides[get_run_service] = lambda: BusyService()
    client = TestClient(application)

    response = client.post("/api/v1/runs", json={"question": PILOT_QUESTION})

    assert response.status_code == 503
    assert response.headers["retry-after"] == "5"
    assert response.json() == {"detail": "Run capacity is busy; retry shortly."}
    assert "private capacity detail" not in response.text
