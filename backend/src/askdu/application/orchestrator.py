from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any, Literal

from askdu.adapters.catalog import FileCatalog
from askdu.adapters.coda_pilot import CodaPilotEngine
from askdu.adapters.declarative import DeclarativeEngine
from askdu.adapters.shsat_pilot import mark_analysis_obligations_satisfied
from askdu.application.agentic_pipeline import (
    AgenticPlanningError,
    DiscoveryResult,
    ModelDiscoveryAgent,
    PreparationTreeAgent,
)
from askdu.application.analysis_notebook import (
    CompiledAnalysisCell,
    compile_analysis_cell,
    execute_analysis_cell,
    values_equivalent,
)
from askdu.application.compiler import (
    DECLARATIVE_TASK_FAMILY,
    SUPPORTED_TASK_FAMILIES,
    QuestionCompiler,
)
from askdu.application.model_compiler import ModelQuestionCompiler, PlannerCompilationError
from askdu.application.ports import ChatModel, QuestionCompilerPort, RunRepository
from askdu.application.report_writer import ModelReportWriter
from askdu.domain import (
    AgentTrace,
    AnalysisArtifact,
    AnalysisNotebookPhase,
    AnalysisNotebookStatus,
    AnalysisNotebookStep,
    DataAsset,
    DiagnosisKind,
    DiscoveryHop,
    DiscoveryMode,
    EdgeKind,
    EvidenceRef,
    InsufficiencyDiagnosis,
    MaterializedState,
    ObligationStatus,
    ObligationType,
    PreparationAttempt,
    RepairGoal,
    RepairGuidance,
    RepairStatus,
    RunState,
    RunStatus,
    SourceDecision,
    Stage,
    SufficiencyViolation,
)


class RunCapacityError(RuntimeError):
    """Raised when a bounded single-node deployment cannot admit another run."""


class RunService:
    """Coordinates discovery, preparation, analysis, repair, and reporting."""

    def __init__(
        self,
        environment_id: str,
        data_root: Path,
        runtime_root: Path,
        repository: RunRepository,
        max_repair_rounds: int = 3,
        max_concurrent_runs: int = 2,
        discovery_mode: DiscoveryMode = DiscoveryMode.PROGRESSIVE,
        repair_guidance: RepairGuidance = RepairGuidance.VIOLATION,
        compiler: QuestionCompilerPort | None = None,
        catalog: FileCatalog | None = None,
        agentic_model: ChatModel | None = None,
        discovery_max_turns: int = 16,
        preparation_max_turns: int = 6,
    ):
        if max_concurrent_runs < 1:
            raise ValueError("max_concurrent_runs must be positive")
        self.environment_id = environment_id
        self.catalog = catalog or FileCatalog(data_root)
        self.engine = CodaPilotEngine(self.catalog, runtime_root)
        self.declarative_engine = DeclarativeEngine(self.catalog, runtime_root)
        self.repository = repository
        if agentic_model is not None and compiler is not None:
            raise ValueError("agentic_model and a standalone compiler are mutually exclusive")
        self.compiler = compiler or QuestionCompiler()
        self.agentic_model = agentic_model
        self.discovery_agent = (
            ModelDiscoveryAgent(
                model=agentic_model,
                catalog=self.catalog,
                max_turns=discovery_max_turns,
            )
            if agentic_model is not None
            else None
        )
        self.preparation_agent = (
            PreparationTreeAgent(
                model=agentic_model,
                catalog=self.catalog,
                engine=self.declarative_engine,
                max_turns=preparation_max_turns,
            )
            if agentic_model is not None
            else None
        )
        self.report_writer = (
            ModelReportWriter(model=agentic_model) if agentic_model is not None else None
        )
        self.planner_mode: Literal["registry", "model", "agentic"] = (
            "agentic"
            if agentic_model is not None
            else "model"
            if isinstance(self.compiler, ModelQuestionCompiler)
            else "registry"
        )
        self.max_repair_rounds = max_repair_rounds
        self.max_concurrent_runs = max_concurrent_runs
        self._run_slots = threading.BoundedSemaphore(max_concurrent_runs)
        self._background_lock = threading.Lock()
        self._background_runs: dict[str, threading.Thread] = {}
        self.discovery_mode = discovery_mode
        self.repair_guidance = repair_guidance

    def run(self, question: str) -> RunState:
        if not self._run_slots.acquire(blocking=False):
            raise RunCapacityError(
                f"All {self.max_concurrent_runs} run slot(s) are currently occupied"
            )
        try:
            return self._execute_admitted(self._new_state(question))
        finally:
            self._run_slots.release()

    def submit(self, question: str) -> RunState:
        """Create a run immediately and execute it on a bounded background worker."""

        if not self._run_slots.acquire(blocking=False):
            raise RunCapacityError(
                f"All {self.max_concurrent_runs} run slot(s) are currently occupied"
            )
        state = self._new_state(question)
        worker = threading.Thread(
            target=self._run_background,
            args=(state,),
            name=f"askdu-{state.run_id}",
            daemon=True,
        )
        with self._background_lock:
            self._background_runs[state.run_id] = worker
        try:
            worker.start()
        except Exception:
            with self._background_lock:
                self._background_runs.pop(state.run_id, None)
            self._run_slots.release()
            raise
        return state

    def _new_state(self, question: str) -> RunState:
        state = RunState(environment_id=self.environment_id, question=question.strip())
        self.repository.save(state)
        return state

    def _run_background(self, state: RunState) -> None:
        try:
            self._execute_admitted(state)
        finally:
            self._run_slots.release()
            with self._background_lock:
                self._background_runs.pop(state.run_id, None)

    def _execute_admitted(self, state: RunState) -> RunState:
        try:
            state.status = RunStatus.RUNNING
            self.repository.save(state)
            if self.discovery_agent is not None and self.preparation_agent is not None:
                return self._run_agentic(state)
            try:
                state.contract = self.compiler.compile(state.question)
            except PlannerCompilationError as exc:
                return self._finish_insufficient(
                    state,
                    f"The model planner could not produce a safe executable plan: {exc}",
                    DiagnosisKind.CAPABILITY_GAP,
                )
            state.add_event(
                Stage.QUESTION,
                Stage.DISCOVERY,
                EdgeKind.FORWARD,
                "Compiled the analytical question into typed sufficiency obligations.",
                [state.contract.contract_id],
            )
            self.repository.save(state)

            if state.contract.task_family not in SUPPORTED_TASK_FAMILIES:
                return self._finish_insufficient(
                    state,
                    "The initial prototype has no executable analysis adapter for this question.",
                    DiagnosisKind.CAPABILITY_GAP,
                )

            selected: list[DataAsset] = []
            excluded_ids: set[str] = set()
            search_terms = list(state.contract.search_terms)
            initial_search_terms = list(search_terms)
            triggering_violation: SufficiencyViolation | None = None
            active_repair: RepairGoal | None = None
            parent_state_ids: list[str] = []

            for iteration in range(self.max_repair_rounds + 1):
                if self.discovery_mode == DiscoveryMode.FULL_CATALOG and iteration == 0:
                    newly_selected = self._select_all_sources(state)
                else:
                    chosen = self._select_source(
                        state=state,
                        iteration=iteration,
                        search_terms=search_terms,
                        selected=selected,
                        excluded_ids=excluded_ids,
                        triggering_violation=triggering_violation,
                    )
                    newly_selected = [chosen] if chosen is not None else []
                if not newly_selected:
                    if active_repair is not None:
                        active_repair.status = RepairStatus.FAILED
                    return self._finish_insufficient(
                        state,
                        "No additional source matched the unresolved analytical obligations.",
                        DiagnosisKind.DATA_GAP,
                    )
                selected.extend(newly_selected)
                excluded_ids.update(asset.asset_id for asset in newly_selected)
                if active_repair is not None:
                    active_repair.status = RepairStatus.COMPLETED
                    active_repair.selected_source_ids.extend(
                        asset.asset_id for asset in newly_selected
                    )

                state.add_event(
                    Stage.DISCOVERY,
                    Stage.PREPARATION,
                    EdgeKind.FORWARD,
                    f"Materializing iteration {iteration} from {len(selected)} selected source(s).",
                    [asset.asset_id for asset in newly_selected],
                )
                active_engine = (
                    self.declarative_engine
                    if state.contract.task_family == DECLARATIVE_TASK_FAMILY
                    else self.engine
                )
                bundle = active_engine.prepare(
                    run_id=state.run_id,
                    iteration=iteration,
                    assets=selected,
                    contract=state.contract,
                    parent_state_ids=parent_state_ids,
                )
                self._register_evidence(state, bundle.evidence)
                state.materialized_states.append(bundle.state)
                parent_state_ids = [bundle.state.state_id]
                state.add_event(
                    Stage.PREPARATION,
                    Stage.ANALYSIS,
                    EdgeKind.FORWARD,
                    "Executing the analysis against the materialized state.",
                    [bundle.state.state_id],
                )

                preparation_violation = self._join_violation(state, bundle.state)
                outcome = (
                    active_engine.analyze(state.run_id, bundle, state.contract)
                    if preparation_violation is None
                    else None
                )
                violation = preparation_violation or (outcome.violation if outcome else None)
                if violation is not None:
                    state.violations.append(violation)
                    self._mark_violated_obligations(state, violation)
                    if iteration >= self.max_repair_rounds:
                        exhausted_all_sources = self.discovery_mode == DiscoveryMode.FULL_CATALOG
                        return self._finish_insufficient(
                            state,
                            (
                                "All cataloged sources were inspected, but required obligations "
                                "remain unresolved."
                                if exhausted_all_sources
                                else "The repair budget was exhausted with required obligations "
                                "unresolved."
                            ),
                            (
                                DiagnosisKind.DATA_GAP
                                if exhausted_all_sources
                                else DiagnosisKind.BUDGET_EXHAUSTED
                            ),
                        )
                    active_repair = self._build_repair_goal(violation)
                    if self.repair_guidance == RepairGuidance.STATIC_QUERY:
                        active_repair.search_terms = list(initial_search_terms)
                        active_repair.instruction = (
                            f"{active_repair.instruction} Static-retry ablation: reuse the "
                            "unchanged initial discovery terms instead of violation evidence."
                        )
                    state.repair_goals.append(active_repair)
                    state.add_event(
                        violation.detected_stage,
                        active_repair.target_stage,
                        EdgeKind.REPAIR,
                        active_repair.instruction,
                        [violation.violation_id, active_repair.repair_goal_id],
                    )
                    search_terms = list(active_repair.search_terms)
                    triggering_violation = violation
                    self.repository.save(state)
                    continue

                if outcome is None:  # pragma: no cover - defensive invariant
                    raise RuntimeError("Analysis produced neither artifacts nor a violation")
                self._register_evidence(state, outcome.evidence)
                state.artifacts.extend(outcome.artifacts)
                for previous_violation in state.violations:
                    previous_violation.resolved = True
                mark_analysis_obligations_satisfied(state.contract, bundle.state)
                self._assert_contract_satisfied(state)

                state.add_event(
                    Stage.ANALYSIS,
                    Stage.VALIDATION,
                    EdgeKind.FORWARD,
                    "Validated coverage, join, statistical, and artifact-link obligations.",
                    [artifact.artifact_id for artifact in outcome.artifacts],
                )
                state.add_event(
                    Stage.VALIDATION,
                    Stage.REPORT,
                    EdgeKind.FORWARD,
                    "Rendering an evidence-grounded report.",
                )
                report, report_evidence = active_engine.render_report(
                    state.run_id,
                    state.question,
                    selected,
                    bundle.state,
                    outcome.artifacts,
                    state.contract,
                )
                self._register_evidence(state, [report_evidence])
                state.report = report
                self._assert_claim_lineage(state)
                state.status = RunStatus.COMPLETED
                state.add_event(
                    Stage.REPORT,
                    Stage.STOPPED,
                    EdgeKind.TERMINAL,
                    "Completed with an evidence-grounded report.",
                    [report.report_id],
                )
                self.repository.save(state)
                return state

            raise RuntimeError("Lifecycle loop ended without a terminal state")  # pragma: no cover
        except Exception as exc:
            state.status = RunStatus.FAILED
            state.error = f"{type(exc).__name__}: {exc}"
            if state.current_stage != Stage.STOPPED:
                state.add_event(
                    state.current_stage,
                    Stage.STOPPED,
                    EdgeKind.TERMINAL,
                    "The run failed before producing a report or insufficiency diagnosis.",
                )
            self.repository.save(state)
            return state

    def _run_agentic(self, state: RunState) -> RunState:
        assert self.discovery_agent is not None
        assert self.preparation_agent is not None
        state.add_event(
            Stage.QUESTION,
            Stage.DISCOVERY,
            EdgeKind.FORWARD,
            "Started question-only, tool-mediated discovery in the authorized environment.",
        )
        self.repository.save(state)
        try:
            discovery = self.discovery_agent.discover(
                state.question,
                iteration=0,
                on_progress=lambda trace, hop: self._record_discovery_progress(
                    state,
                    trace,
                    hop,
                ),
            )
        except AgenticPlanningError as exc:
            self._merge_agent_traces(state, exc.traces)
            self._merge_discovery_hops(state, exc.discovery_hops)
            return self._finish_insufficient(
                state,
                f"Discovery could not identify sufficient authorized sources: {exc}",
                exc.diagnosis_kind,
            )

        selected = discovery.selected
        self._record_agentic_discovery(
            state,
            discovery,
            iteration=0,
            selected=selected,
            newly_selected=selected,
        )
        state.add_event(
            Stage.DISCOVERY,
            Stage.PREPARATION,
            EdgeKind.FORWARD,
            (
                "Discovery selected inspected sources; starting bounded tree-based "
                "preparation planning."
            ),
            [asset.asset_id for asset in selected],
        )
        self.repository.save(state)

        tree = None
        for repair_round in range(self.max_repair_rounds + 1):
            try:
                tree = self.preparation_agent.plan(
                    run_id=state.run_id,
                    question=state.question,
                    discovered=selected,
                    on_progress=lambda trace, attempt: self._record_preparation_progress(
                        state,
                        trace,
                        attempt,
                    ),
                )
                break
            except AgenticPlanningError as exc:
                self._merge_agent_traces(state, exc.traces)
                self._merge_preparation_attempts(state, exc.preparation_attempts)
                if repair_round >= self.max_repair_rounds:
                    return self._finish_insufficient(
                        state,
                        f"Preparation could not finalize an executable bounded plan: {exc}",
                        exc.diagnosis_kind,
                    )
                violation = SufficiencyViolation(
                    obligation_ids=[],
                    type="agentic_preparation_unresolved",
                    observed={"bounded_feedback": str(exc)[:500]},
                    expected={"additional_source_or_alternative_plan": True},
                    detected_stage=Stage.PREPARATION,
                    responsible_stage=Stage.DISCOVERY,
                    evidence_refs=list(state.evidence),
                )
                state.violations.append(violation)
                repair = RepairGoal(
                    violation_id=violation.violation_id,
                    target_stage=Stage.DISCOVERY,
                    instruction=(
                        "Preparation could not finalize an executed branch; reopen Discovery "
                        "with bounded execution feedback."
                    ),
                    search_terms=[],
                )
                state.repair_goals.append(repair)
                state.add_event(
                    Stage.PREPARATION,
                    Stage.DISCOVERY,
                    EdgeKind.REPAIR,
                    repair.instruction,
                    [violation.violation_id, repair.repair_goal_id],
                )
                self.repository.save(state)
                try:
                    repaired = self.discovery_agent.discover(
                        state.question,
                        repair_context=str(exc)[:500],
                        previously_selected=selected,
                        iteration=repair_round + 1,
                        on_progress=lambda trace, hop: self._record_discovery_progress(
                            state,
                            trace,
                            hop,
                        ),
                    )
                except AgenticPlanningError as discovery_exc:
                    self._merge_agent_traces(state, discovery_exc.traces)
                    self._merge_discovery_hops(state, discovery_exc.discovery_hops)
                    repair.status = RepairStatus.FAILED
                    return self._finish_insufficient(
                        state,
                        f"Discovery repair could not add sufficient sources: {discovery_exc}",
                        discovery_exc.diagnosis_kind,
                    )
                selected_by_id = {asset.asset_id: asset for asset in selected}
                newly_selected = tuple(
                    asset for asset in repaired.selected if asset.asset_id not in selected_by_id
                )
                selected_by_id.update({asset.asset_id: asset for asset in repaired.selected})
                if not newly_selected:
                    repair.status = RepairStatus.FAILED
                    return self._finish_insufficient(
                        state,
                        "Discovery repair returned no new inspected source.",
                        DiagnosisKind.DATA_GAP,
                    )
                selected = tuple(selected_by_id.values())
                scopes = {
                    scope
                    for asset in selected
                    if (scope := self.catalog.selection_scope(asset)) is not None
                }
                if len(scopes) > 1:
                    repair.status = RepairStatus.FAILED
                    return self._finish_insufficient(
                        state,
                        "Discovery repair crossed the selected CoDA community boundary.",
                        DiagnosisKind.CAPABILITY_GAP,
                    )
                repair.status = RepairStatus.COMPLETED
                repair.selected_source_ids = [asset.asset_id for asset in newly_selected]
                violation.resolved = True
                self._record_agentic_discovery(
                    state,
                    repaired,
                    iteration=repair_round + 1,
                    selected=selected,
                    newly_selected=newly_selected,
                    trigger_violation_id=violation.violation_id,
                )
                state.add_event(
                    Stage.DISCOVERY,
                    Stage.PREPARATION,
                    EdgeKind.FORWARD,
                    "Discovery added inspected sources and replayed tree-based preparation.",
                    [asset.asset_id for asset in newly_selected],
                )
                self.repository.save(state)

        if tree is None:  # pragma: no cover - bounded loop invariant
            raise RuntimeError("Agentic preparation ended without a result")

        self._merge_agent_traces(state, tree.traces)
        self._merge_preparation_attempts(state, tree.attempts)
        contract = tree.chosen.contract
        if contract.analysis_plan is None:  # pragma: no cover - agentic construction invariant
            raise RuntimeError("Selected preparation branch has no analysis plan")
        analysis_plan = contract.analysis_plan
        state.contract = contract
        for candidate in tree.candidates:
            self._register_evidence(state, candidate.bundle.evidence)
            self._register_evidence(state, candidate.outcome.evidence)
            state.materialized_states.append(candidate.bundle.state)
        state.add_event(
            Stage.PREPARATION,
            Stage.ANALYSIS,
            EdgeKind.FORWARD,
            (
                "Selected an execution-observed preparation branch; starting the "
                "DeepAnalyze-style code and execution loop."
            ),
            [tree.chosen.bundle.state.state_id],
        )
        self._start_analysis_notebook(state, tree.chosen.bundle.state)

        compiled_cells: dict[str, CompiledAnalysisCell] = {}
        analysis_started: dict[str, float] = {}

        def observe_analysis(
            event: str,
            analysis: Any,
            value: Any,
            computed: dict[str, Any],
        ) -> None:
            turn = next(
                index
                for index, planned in enumerate(analysis_plan.analyses, start=1)
                if planned.name == analysis.name
            )
            if event == "before":
                analysis_started[analysis.name] = time.perf_counter()
                cell = compile_analysis_cell(analysis)
                compiled_cells[analysis.name] = cell
                self._append_analysis_step(
                    state,
                    turn=turn,
                    phase=AnalysisNotebookPhase.CODE,
                    status=AnalysisNotebookStatus.COMPLETED,
                    title=f"Code · {analysis.name}",
                    summary=(
                        "Compiled the validated analysis specification into a bounded "
                        f"{cell.language.upper()} cell."
                    ),
                    analysis_name=analysis.name,
                    language=cell.language,
                    source_code=cell.source,
                    parameters=cell.parameters,
                    runtime=cell.runtime,
                    state_refs=[tree.chosen.bundle.state.state_id],
                )
                return
            if event == "error":
                self._append_analysis_step(
                    state,
                    turn=turn,
                    phase=AnalysisNotebookPhase.DEBUG,
                    status=AnalysisNotebookStatus.FAILED,
                    title=f"Debug · {analysis.name}",
                    summary=(
                        "Execution feedback rejected this analysis cell; the bounded reason "
                        "was retained for repair."
                    ),
                    analysis_name=analysis.name,
                    language="text",
                    output=str(value)[:800],
                    runtime="bounded_dataframe",
                    duration_ms=self._elapsed_ms(analysis_started.pop(analysis.name, None)),
                    state_refs=[tree.chosen.bundle.state.state_id],
                )
                return

            cell = compiled_cells[analysis.name]
            prior = dict(computed)
            prior.pop(analysis.name, None)
            try:
                observed = execute_analysis_cell(
                    cell,
                    analysis,
                    tree.chosen.bundle.tables[analysis.table],
                    prior,
                    fallback=lambda: self.declarative_engine._execute_analysis(
                        analysis,
                        tree.chosen.bundle.tables,
                        prior,
                    ),
                )
                if not values_equivalent(observed, value):
                    raise ValueError("compiled-cell result differed from bounded executor")
                execution_runtime = cell.runtime
                execution_summary = (
                    f"Executed the {cell.language.upper()} cell and matched the bounded "
                    "dataframe result."
                )
            except Exception as exc:
                self._append_analysis_step(
                    state,
                    turn=turn,
                    phase=AnalysisNotebookPhase.DEBUG,
                    status=AnalysisNotebookStatus.FAILED,
                    title=f"Debug · {analysis.name}",
                    summary=(
                        "The compiled cell did not pass execution verification; the system "
                        "kept the validated dataframe result and recorded the fallback."
                    ),
                    analysis_name=analysis.name,
                    language="text",
                    output=f"{type(exc).__name__}: verification failed",
                    runtime=cell.runtime,
                    state_refs=[tree.chosen.bundle.state.state_id],
                )
                observed = value
                execution_runtime = "bounded_dataframe_fallback"
                execution_summary = "Re-executed through the validated dataframe fallback."
            self._append_analysis_step(
                state,
                turn=turn,
                phase=AnalysisNotebookPhase.EXECUTE,
                status=AnalysisNotebookStatus.COMPLETED,
                title=f"Execute · {analysis.name}",
                summary=execution_summary,
                analysis_name=analysis.name,
                language="json",
                output=observed,
                runtime=execution_runtime,
                duration_ms=self._elapsed_ms(analysis_started.pop(analysis.name, None)),
                state_refs=[tree.chosen.bundle.state.state_id],
            )

        outcome = self.declarative_engine.analyze(
            state.run_id,
            tree.chosen.bundle,
            contract,
            observer=observe_analysis,
        )
        if outcome.violation is not None:  # pragma: no cover - selected branch was prevalidated
            raise RuntimeError("Finalized tree candidate failed deterministic analysis replay")
        self._register_evidence(state, outcome.evidence)
        state.artifacts.extend(outcome.artifacts)
        self._link_notebook_artifacts(state, outcome.artifacts)
        mark_analysis_obligations_satisfied(contract, tree.chosen.bundle.state)
        self._assert_contract_satisfied(state)
        state.add_event(
            Stage.ANALYSIS,
            Stage.VALIDATION,
            EdgeKind.FORWARD,
            "Validated the chosen branch against the analytical contract.",
            [artifact.artifact_id for artifact in outcome.artifacts],
        )
        state.add_event(
            Stage.VALIDATION,
            Stage.REPORT,
            EdgeKind.FORWARD,
            "Rendering an evidence-grounded report from executed artifacts.",
        )
        if self.report_writer is None:  # pragma: no cover - agentic construction invariant
            raise RuntimeError("Agentic execution has no report writer")
        composition = self.report_writer.compose(
            question=state.question,
            plan=analysis_plan,
            assets=list(tree.selected),
            state=tree.chosen.bundle.state,
            artifacts=outcome.artifacts,
        )
        self._merge_agent_traces(state, composition.traces)
        self._append_analysis_step(
            state,
            turn=len(analysis_plan.analyses) + 1,
            phase=AnalysisNotebookPhase.ANALYZE,
            status=AnalysisNotebookStatus.COMPLETED,
            title="Analyze · cross-dimensional synthesis",
            summary=(
                "Synthesized every executed dimension into one bounded report draft."
                if not composition.used_fallback
                else "Used the deterministic grounded report fallback after draft validation."
            ),
            language="json",
            output={
                "sections": [section.title for section in composition.narrative.sections],
                "artifact_refs": composition.narrative.executive_artifact_refs,
                "fallback": composition.used_fallback,
            },
            state_refs=[tree.chosen.bundle.state.state_id],
            artifact_refs=[artifact.artifact_id for artifact in outcome.artifacts],
            evidence_refs=sorted(
                {
                    evidence_ref
                    for artifact in outcome.artifacts
                    for evidence_ref in artifact.evidence_refs
                }
            ),
        )
        report, report_evidence = self.declarative_engine.render_report(
            state.run_id,
            state.question,
            list(tree.selected),
            tree.chosen.bundle.state,
            outcome.artifacts,
            contract,
            composition.narrative,
        )
        self._register_evidence(state, [report_evidence])
        state.report = report
        self._finish_analysis_notebook(state, report.report_id, report_evidence.ref_id)
        self._assert_claim_lineage(state)
        state.status = RunStatus.COMPLETED
        state.add_event(
            Stage.REPORT,
            Stage.STOPPED,
            EdgeKind.TERMINAL,
            "Completed the agentic run with an evidence-grounded report.",
            [report.report_id],
        )
        self.repository.save(state)
        return state

    def _start_analysis_notebook(
        self,
        state: RunState,
        materialized_state: MaterializedState,
    ) -> None:
        if state.contract is None or state.contract.analysis_plan is None:
            raise RuntimeError("Cannot start analysis notebook without a validated plan")
        plan = state.contract.analysis_plan
        self._append_analysis_step(
            state,
            turn=1,
            phase=AnalysisNotebookPhase.ANALYZE,
            status=AnalysisNotebookStatus.COMPLETED,
            title="Analyze · task decomposition",
            summary=plan.summary,
            language="markdown",
            output={
                "analyses": [
                    {"name": analysis.name, "type": analysis.type, "table": analysis.table}
                    for analysis in plan.analyses
                ]
            },
            state_refs=[materialized_state.state_id],
        )
        table_profiles = materialized_state.metrics.get("table_profiles", {})
        primary_profile = (
            table_profiles.get(plan.primary_table, {}) if isinstance(table_profiles, dict) else {}
        )
        self._append_analysis_step(
            state,
            turn=1,
            phase=AnalysisNotebookPhase.UNDERSTAND,
            status=AnalysisNotebookStatus.COMPLETED,
            title="Understand · prepared table",
            summary=(
                f"Inspected {plan.primary_table}: {materialized_state.row_count} rows and "
                f"{len(materialized_state.columns)} columns before writing analysis code."
            ),
            language="json",
            output={
                "table": plan.primary_table,
                "rows": materialized_state.row_count,
                "columns": materialized_state.columns,
                "profile": primary_profile,
                "source_ids": materialized_state.source_ids,
            },
            state_refs=[materialized_state.state_id],
            evidence_refs=list(materialized_state.evidence_refs),
        )

    def _append_analysis_step(
        self,
        state: RunState,
        *,
        turn: int,
        phase: AnalysisNotebookPhase,
        status: AnalysisNotebookStatus,
        title: str,
        summary: str,
        analysis_name: str | None = None,
        language: Literal["markdown", "python", "sql", "json", "text"] = "text",
        source_code: str | None = None,
        parameters: dict[str, Any] | None = None,
        output: Any = None,
        runtime: str | None = None,
        duration_ms: float | None = None,
        state_refs: list[str] | None = None,
        artifact_refs: list[str] | None = None,
        evidence_refs: list[str] | None = None,
    ) -> AnalysisNotebookStep:
        step = AnalysisNotebookStep(
            sequence=len(state.analysis_notebook) + 1,
            turn=turn,
            phase=phase,
            status=status,
            title=title,
            summary=summary[:1_000],
            analysis_name=analysis_name,
            language=language,
            source_code=source_code,
            parameters=parameters or {},
            output=output,
            runtime=runtime,
            duration_ms=duration_ms,
            state_refs=state_refs or [],
            artifact_refs=artifact_refs or [],
            evidence_refs=evidence_refs or [],
        )
        state.analysis_notebook.append(step)
        self.repository.save(state)
        return step

    @staticmethod
    def _elapsed_ms(started_at: float | None) -> float | None:
        if started_at is None:
            return None
        return round(max(0.0, (time.perf_counter() - started_at) * 1_000), 3)

    def _link_notebook_artifacts(
        self,
        state: RunState,
        artifacts: list[AnalysisArtifact],
    ) -> None:
        by_name = {artifact.name: artifact for artifact in artifacts}
        for index, step in enumerate(state.analysis_notebook):
            if step.phase != AnalysisNotebookPhase.EXECUTE or step.analysis_name is None:
                continue
            artifact = by_name.get(step.analysis_name)
            if artifact is None:
                continue
            state.analysis_notebook[index] = step.model_copy(
                update={
                    "artifact_refs": [artifact.artifact_id],
                    "evidence_refs": list(artifact.evidence_refs),
                }
            )
        self.repository.save(state)

    def _finish_analysis_notebook(
        self,
        state: RunState,
        report_id: str,
        report_evidence_id: str,
    ) -> None:
        if state.report is None:
            raise RuntimeError("Cannot finish analysis notebook without a report")
        artifact_refs = [artifact.artifact_id for artifact in state.artifacts]
        evidence_refs = sorted(
            {
                evidence_ref
                for artifact in state.artifacts
                for evidence_ref in artifact.evidence_refs
            }
        )
        self._append_analysis_step(
            state,
            turn=max(1, len(artifact_refs)),
            phase=AnalysisNotebookPhase.ANSWER,
            status=AnalysisNotebookStatus.COMPLETED,
            title="Answer · grounded findings",
            summary="Accepted only claims linked to executed analysis artifacts.",
            language="markdown",
            output=[claim.text for claim in state.report.claims],
            artifact_refs=artifact_refs,
            evidence_refs=evidence_refs,
        )
        self._append_analysis_step(
            state,
            turn=max(1, len(artifact_refs)),
            phase=AnalysisNotebookPhase.REPORT,
            status=AnalysisNotebookStatus.COMPLETED,
            title="Report · Markdown release",
            summary=(
                "Rendered the executive summary, dimensional findings, integrated conclusion, "
                "and limitations after contract and lineage validation."
            ),
            language="markdown",
            output={
                "report_id": report_id,
                "title": state.report.title,
                "executive_summary": state.report.executive_summary,
                "sections": [
                    {
                        "title": section.title,
                        "narrative": section.narrative,
                        "artifact_refs": section.artifact_refs,
                    }
                    for section in state.report.sections
                ],
                "conclusion": state.report.conclusion,
                "limitations": state.report.limitations,
                "claims": len(state.report.claims),
            },
            artifact_refs=artifact_refs,
            evidence_refs=[report_evidence_id],
        )

    def _record_discovery_progress(
        self,
        state: RunState,
        trace: AgentTrace | None,
        hop: DiscoveryHop,
    ) -> None:
        if trace is not None:
            self._merge_agent_traces(state, (trace,))
        self._merge_discovery_hops(state, (hop,))
        self.repository.save(state)

    def _record_preparation_progress(
        self,
        state: RunState,
        trace: AgentTrace,
        attempt: PreparationAttempt | None,
    ) -> None:
        self._merge_agent_traces(state, (trace,))
        if attempt is not None:
            self._merge_preparation_attempts(state, (attempt,))
        self.repository.save(state)

    @staticmethod
    def _merge_agent_traces(state: RunState, traces: tuple[AgentTrace, ...]) -> None:
        known = {trace.trace_id for trace in state.agent_traces}
        state.agent_traces.extend(trace for trace in traces if trace.trace_id not in known)

    @staticmethod
    def _merge_discovery_hops(state: RunState, hops: tuple[DiscoveryHop, ...]) -> None:
        by_id = {hop.hop_id: index for index, hop in enumerate(state.discovery_hops)}
        for hop in hops:
            existing = by_id.get(hop.hop_id)
            if existing is None:
                by_id[hop.hop_id] = len(state.discovery_hops)
                state.discovery_hops.append(hop)
            else:
                state.discovery_hops[existing] = hop

    @staticmethod
    def _merge_preparation_attempts(
        state: RunState,
        attempts: tuple[PreparationAttempt, ...],
    ) -> None:
        by_id = {
            attempt.attempt_id: index for index, attempt in enumerate(state.preparation_attempts)
        }
        for attempt in attempts:
            existing = by_id.get(attempt.attempt_id)
            if existing is None:
                by_id[attempt.attempt_id] = len(state.preparation_attempts)
                state.preparation_attempts.append(attempt)
            else:
                state.preparation_attempts[existing] = attempt

    def _record_agentic_discovery(
        self,
        state: RunState,
        discovery: DiscoveryResult,
        *,
        iteration: int,
        selected: tuple[DataAsset, ...],
        newly_selected: tuple[DataAsset, ...],
        trigger_violation_id: str | None = None,
    ) -> None:
        self._merge_agent_traces(state, discovery.traces)
        self._merge_discovery_hops(state, discovery.hops)
        evidence_refs: list[str] = []
        for asset in newly_selected:
            state.assets[asset.asset_id] = asset
            evidence = EvidenceRef(
                kind="source_inspection",
                locator=f"data://{asset.relative_path}",
                sha256=asset.sha256 or asset.expected_sha256,
                description=(
                    f"Discovery inspected a {asset.file_format} source with "
                    f"{len(asset.columns)} columns"
                ),
            )
            self._register_evidence(state, [evidence])
            evidence_refs.append(evidence.ref_id)
        state.source_decisions.append(
            SourceDecision(
                iteration=iteration,
                selected_source_ids=[asset.asset_id for asset in selected],
                newly_selected_source_ids=[asset.asset_id for asset in newly_selected],
                candidate_scores=discovery.candidate_scores,
                reason=discovery.reason,
                trigger_violation_id=trigger_violation_id,
                evidence_refs=evidence_refs,
            )
        )

    def get(self, run_id: str) -> RunState | None:
        return self.repository.get(run_id)

    def _select_source(
        self,
        state: RunState,
        iteration: int,
        search_terms: list[str],
        selected: list[DataAsset],
        excluded_ids: set[str],
        triggering_violation: SufficiencyViolation | None,
    ) -> DataAsset | None:
        ranking = self.catalog.rank(search_terms, excluded_ids)
        planned_asset = self._next_planned_asset(state, excluded_ids)
        if planned_asset is not None:
            chosen = self.catalog.profile(planned_asset.asset_id)
            ranking = [
                (planned_asset, max([score for _, score in ranking], default=0.0) + 1.0),
                *(item for item in ranking if item[0].asset_id != planned_asset.asset_id),
            ]
        elif ranking:
            chosen = self.catalog.profile(ranking[0][0].asset_id)
        else:
            return None
        state.assets[chosen.asset_id] = chosen
        evidence = EvidenceRef(
            kind="source_profile",
            locator=f"data://{chosen.relative_path}",
            sha256=chosen.sha256,
            description=f"Profiled {chosen.row_count} rows and {len(chosen.columns)} columns",
        )
        self._register_evidence(state, [evidence])
        selected_ids = [asset.asset_id for asset in selected] + [chosen.asset_id]
        if planned_asset is not None:
            decision_reason = "Selected the next source named by the validated declarative plan."
        elif triggering_violation is None:
            decision_reason = "Selected the highest-ranked source for the initial question."
        elif self.repair_guidance == RepairGuidance.STATIC_QUERY:
            decision_reason = (
                "Retried discovery with the unchanged initial question terms for the "
                "static-retry ablation."
            )
        else:
            decision_reason = (
                "Selected a new source targeted at the downstream sufficiency violation."
            )
        decision = SourceDecision(
            iteration=iteration,
            selected_source_ids=selected_ids,
            newly_selected_source_ids=[chosen.asset_id],
            candidate_scores={asset.relative_path: score for asset, score in ranking[:5]},
            reason=decision_reason,
            trigger_violation_id=(
                triggering_violation.violation_id if triggering_violation else None
            ),
            evidence_refs=[evidence.ref_id],
        )
        state.source_decisions.append(decision)
        return chosen

    def _next_planned_asset(
        self,
        state: RunState,
        excluded_ids: set[str],
    ) -> DataAsset | None:
        if state.contract is None or state.contract.analysis_plan is None:
            return None
        indexed = self.catalog.index()
        return next(
            (
                indexed[source.asset_id]
                for source in state.contract.analysis_plan.sources
                if source.asset_id not in excluded_ids and source.asset_id in indexed
            ),
            None,
        )

    def _select_all_sources(self, state: RunState) -> list[DataAsset]:
        profiled: list[DataAsset] = []
        evidence_refs: list[str] = []
        for indexed in self.catalog.index().values():
            asset = self.catalog.profile(indexed.asset_id)
            state.assets[asset.asset_id] = asset
            evidence = EvidenceRef(
                kind="source_profile",
                locator=f"data://{asset.relative_path}",
                sha256=asset.sha256,
                description=f"Profiled {asset.row_count} rows and {len(asset.columns)} columns",
            )
            self._register_evidence(state, [evidence])
            evidence_refs.append(evidence.ref_id)
            profiled.append(asset)
        if profiled:
            state.source_decisions.append(
                SourceDecision(
                    iteration=0,
                    selected_source_ids=[asset.asset_id for asset in profiled],
                    newly_selected_source_ids=[asset.asset_id for asset in profiled],
                    candidate_scores={asset.relative_path: 0.0 for asset in profiled},
                    reason="Profiled the complete authorized catalog for the full-scan baseline.",
                    evidence_refs=evidence_refs,
                )
            )
        return profiled

    @staticmethod
    def _build_repair_goal(violation: SufficiencyViolation) -> RepairGoal:
        required_columns = [str(value) for value in violation.expected.get("required_columns", [])]
        if violation.type == "missing_analytical_columns":
            return RepairGoal(
                violation_id=violation.violation_id,
                target_stage=Stage.DISCOVERY,
                instruction=(
                    "Analysis is missing required variables; reopen Data Discovery and add a "
                    "source containing them."
                ),
                search_terms=required_columns,
            )
        if violation.type == "missing_category_coverage":
            return RepairGoal(
                violation_id=violation.violation_id,
                target_stage=Stage.DISCOVERY,
                instruction=(
                    "The selected data does not cover every requested category; reopen "
                    "Data Discovery and add a complementary source."
                ),
                search_terms=[str(value) for value in violation.expected.get("search_terms", [])],
            )
        if violation.type == "missing_planned_sources":
            return RepairGoal(
                violation_id=violation.violation_id,
                target_stage=Stage.DISCOVERY,
                instruction=(
                    "The validated plan requires another catalog source; reopen Data Discovery "
                    "and materialize it before executing the plan."
                ),
                search_terms=[str(value) for value in violation.expected.get("search_terms", [])],
            )
        if violation.type == "low_join_coverage":
            return RepairGoal(
                violation_id=violation.violation_id,
                target_stage=Stage.DISCOVERY,
                instruction=(
                    "Join coverage is below the contract threshold; discover an alternative "
                    "source with compatible school identifiers."
                ),
                search_terms=["school", "DBN", "Location Code", "demographics"],
            )
        return RepairGoal(
            violation_id=violation.violation_id,
            target_stage=violation.responsible_stage,
            instruction="Reopen the responsible lifecycle stage to satisfy the failed obligation.",
            search_terms=required_columns,
        )

    @staticmethod
    def _join_violation(
        state: RunState, materialized_state: MaterializedState
    ) -> SufficiencyViolation | None:
        if state.contract is None or "join_coverage" not in materialized_state.metrics:
            return None
        join_obligation = next(
            obligation
            for obligation in state.contract.obligations
            if obligation.type == ObligationType.JOIN
        )
        observed = float(materialized_state.metrics["join_coverage"])
        expected = float(join_obligation.expected["minimum_coverage"])
        if observed >= expected:
            return None
        return SufficiencyViolation(
            obligation_ids=[join_obligation.obligation_id],
            type="low_join_coverage",
            observed={"join_coverage": observed},
            expected={"minimum_coverage": expected},
            detected_stage=Stage.PREPARATION,
            responsible_stage=Stage.DISCOVERY,
            evidence_refs=list(materialized_state.evidence_refs),
        )

    @staticmethod
    def _mark_violated_obligations(state: RunState, violation: SufficiencyViolation) -> None:
        if state.contract is None:
            return
        violated = set(violation.obligation_ids)
        for obligation in state.contract.obligations:
            if obligation.obligation_id in violated:
                obligation.status = ObligationStatus.VIOLATED
                obligation.evidence_refs.extend(violation.evidence_refs)

    @staticmethod
    def _register_evidence(state: RunState, evidence: list[EvidenceRef]) -> None:
        for item in evidence:
            state.evidence[item.ref_id] = item

    @staticmethod
    def _assert_contract_satisfied(state: RunState) -> None:
        if state.contract is None:
            raise RuntimeError("Run has no analytical contract")
        unresolved = [
            obligation.obligation_id
            for obligation in state.contract.obligations
            if obligation.required and obligation.status != ObligationStatus.SATISFIED
        ]
        if unresolved:
            raise RuntimeError(f"Required obligations remain unresolved: {unresolved}")

    @staticmethod
    def _assert_claim_lineage(state: RunState) -> None:
        if state.report is None:
            raise RuntimeError("Run has no report")
        artifact_ids = {artifact.artifact_id for artifact in state.artifacts}
        evidence_ids = set(state.evidence)
        for claim in state.report.claims:
            if not claim.artifact_refs or not set(claim.artifact_refs).issubset(artifact_ids):
                raise RuntimeError(f"Claim {claim.claim_id} has invalid artifact lineage")
            if not claim.evidence_refs or not set(claim.evidence_refs).issubset(evidence_ids):
                raise RuntimeError(f"Claim {claim.claim_id} has invalid evidence lineage")

    def _finish_insufficient(
        self,
        state: RunState,
        summary: str,
        kind: DiagnosisKind,
    ) -> RunState:
        unresolved = []
        if state.contract is not None:
            unresolved = [
                obligation.obligation_id
                for obligation in state.contract.obligations
                if obligation.required and obligation.status != ObligationStatus.SATISFIED
            ]
        state.diagnosis = InsufficiencyDiagnosis(
            kind=kind,
            summary=summary,
            unresolved_obligation_ids=unresolved,
            attempted_repairs=[goal.repair_goal_id for goal in state.repair_goals],
            evidence_refs=list(state.evidence),
        )
        state.status = RunStatus.INSUFFICIENT
        state.add_event(
            state.current_stage,
            Stage.STOPPED,
            EdgeKind.TERMINAL,
            f"Stopped with an explicit {kind.value.replace('_', ' ')} diagnosis.",
            [state.diagnosis.diagnosis_id],
        )
        self.repository.save(state)
        return state
