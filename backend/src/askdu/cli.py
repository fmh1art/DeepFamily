from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer

from askdu.application.orchestrator import RunService
from askdu.bootstrap import build_catalog, build_run_service
from askdu.config import get_settings

app = typer.Typer(no_args_is_help=True, help="Ask, Don't Upload developer CLI")
PROVIDER_SMOKE_QUESTION = (
    "What are the Pearson correlation coefficients between the number of students who took "
    "the SHSAT and the percentage of Asian, Black/Hispanic, and White students for Grade 8 "
    "in 2016, using SHSAT registration and tester data that includes grade level information?"
)


def _service() -> RunService:
    return build_run_service(get_settings())


@app.command()
def doctor() -> None:
    """Validate the local pilot environment without calling an LLM."""

    settings = get_settings()
    catalog = build_catalog(settings)
    assets = catalog.index()
    typer.echo(f"environment_id={settings.environment_id}")
    typer.echo(f"data_root={settings.data_root}")
    typer.echo(f"csv_assets={len(assets)}")
    typer.echo(f"planner_mode={settings.planner_mode}")
    typer.echo(f"provenance_registered={str(catalog.catalog_provenance is not None).lower()}")
    typer.echo(f"llm_configured={str(settings.llm_configured).lower()}")
    if not assets:
        raise typer.Exit(code=1)


@app.command("provider-smoke")
def provider_smoke() -> None:
    """Run one fixed non-held-out question through the configured model provider."""

    settings = get_settings()
    if settings.planner_mode != "model" or not settings.llm_configured:
        typer.echo(
            "ERROR: configure the server-side model provider and set "
            "ASKDU_PLANNER_MODE=model first",
            err=True,
        )
        raise typer.Exit(code=2)
    if settings.environment_id != "coda-community-43":
        typer.echo(
            "ERROR: provider-smoke is locked to the public coda-community-43 environment",
            err=True,
        )
        raise typer.Exit(code=2)

    state = _service().run(PROVIDER_SMOKE_QUESTION)
    if state.status.value != "completed" or state.report is None or state.contract is None:
        diagnosis = state.diagnosis.kind.value if state.diagnosis is not None else None
        typer.echo(
            f"ERROR: provider smoke did not complete (status={state.status.value}, "
            f"diagnosis={diagnosis or 'none'})",
            err=True,
        )
        raise typer.Exit(code=1)
    if state.contract.compilation.kind != "model":
        typer.echo("ERROR: provider smoke did not use the model compiler", err=True)
        raise typer.Exit(code=1)
    serialized = state.model_dump_json()
    if settings.llm_api_key and settings.llm_api_key in serialized:
        typer.echo("ERROR: provider credential leaked into persisted run state", err=True)
        raise typer.Exit(code=1)

    summary = {
        "status": state.status.value,
        "environment_id": state.environment_id,
        "planner_mode": state.contract.compilation.kind,
        "run_id": state.run_id,
        "compilation_attempts": state.contract.compilation.attempts,
        "plan_schema_version": state.contract.compilation.plan_schema_version,
        "selected_sources": len(state.assets),
        "repair_edges": sum(event.edge_kind.value == "repair" for event in state.events),
        "artifacts": len(state.artifacts),
        "claims": len(state.report.claims),
    }
    typer.echo(json.dumps(summary, indent=2))


@app.command("run")
def run_question(
    question: Annotated[
        str,
        typer.Option("--question", "-q", help="The only task-level input."),
    ],
    output: Annotated[
        Path | None,
        typer.Option(help="Optional path for the complete run JSON."),
    ] = None,
) -> None:
    """Run the synchronous pilot lifecycle."""

    state = _service().run(question)
    payload = state.model_dump(mode="json")
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        typer.echo(str(output))
    else:
        typer.echo(json.dumps(payload, indent=2))
    if state.status.value == "failed":
        raise typer.Exit(code=1)
