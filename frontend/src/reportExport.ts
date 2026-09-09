import type { CatalogProvenance, RunState } from "./types";

export const EVIDENCE_BUNDLE_SCHEMA = "askdu.evidence-bundle/1.1" as const;

function byIdentifier<T extends Record<string, unknown>>(field: keyof T) {
  return (left: T, right: T) => String(left[field]).localeCompare(String(right[field]));
}

/**
 * Build a portable proof object from the already-public RunState response.
 *
 * This is deliberately a top-level allowlist instead of a spread of the API
 * object: a future top-level server field cannot silently enter the browser
 * export. Analysis result values are retained because they are the claims being
 * audited. The UI receives a bounded prepared-table preview, but that preview,
 * complete source rows, and provider credentials are deliberately omitted here.
 */
export function buildEvidenceBundle(
  run: RunState,
  catalogProvenance: CatalogProvenance | null,
) {
  if (run.status !== "completed" || run.report === null) {
    throw new Error("Evidence bundles are available only for completed reports.");
  }

  const assets = Object.values(run.assets)
    .map((asset) => ({
      asset_id: asset.asset_id,
      relative_path: asset.relative_path,
      name: asset.name,
      columns: asset.columns,
      byte_size: asset.byte_size,
      row_count: asset.row_count,
      sha256: asset.sha256,
      expected_sha256: asset.expected_sha256,
      integrity_status: asset.integrity_status,
      provenance: asset.provenance,
    }))
    .sort(byIdentifier("asset_id"));
  const evidence = Object.values(run.evidence)
    .map((item) => ({
      ref_id: item.ref_id,
      kind: item.kind,
      locator: item.locator,
      sha256: item.sha256,
      description: item.description,
    }))
    .sort(byIdentifier("ref_id"));

  return {
    schema_version: EVIDENCE_BUNDLE_SCHEMA,
    export_manifest: {
      source_rows: "excluded",
      server_credentials: "excluded",
      analysis_outputs: "included",
      construction: "client-side allowlist from the public RunState response",
    },
    catalog_provenance: catalogProvenance,
    run: {
      run_id: run.run_id,
      environment_id: run.environment_id,
      question: run.question,
      status: run.status,
      current_stage: run.current_stage,
      contract: run.contract,
      assets,
      agent_traces: run.agent_traces.map((trace) => ({
        trace_id: trace.trace_id,
        agent: trace.agent,
        turn: trace.turn,
        action: trace.action,
        status: trace.status,
        request_sha256: trace.request_sha256,
        response_sha256: trace.response_sha256,
        summary: trace.summary,
        parent_state_ids: trace.parent_state_ids,
      })),
      discovery_hops: run.discovery_hops.map((hop) => ({
        hop_id: hop.hop_id,
        iteration: hop.iteration,
        turn: hop.turn,
        parent_hop_id: hop.parent_hop_id,
        action: hop.action,
        status: hop.status,
        scope: hop.scope,
        destination: hop.destination,
        query_terms: hop.query_terms,
        candidates: hop.candidates.map((candidate) => ({
          asset_id: candidate.asset_id,
          relative_path: candidate.relative_path,
          name: candidate.name,
          kind: candidate.kind,
          community: candidate.community,
          file_format: candidate.file_format,
          byte_size: candidate.byte_size,
          score: candidate.score,
        })),
        inspected_asset_id: hop.inspected_asset_id,
        inspected_path: hop.inspected_path,
        inspected_schema: hop.inspected_schema,
        selected_asset_ids: hop.selected_asset_ids,
        summary: hop.summary,
        error: hop.error,
      })),
      preparation_attempts: run.preparation_attempts.map((attempt) => ({
        attempt_id: attempt.attempt_id,
        turn: attempt.turn,
        candidate_id: attempt.candidate_id,
        parent_candidate_id: attempt.parent_candidate_id,
        status: attempt.status,
        reason: attempt.reason,
        source_aliases: attempt.source_aliases,
        operators: attempt.operators.map((operator) => ({
          operator_id: operator.operator_id,
          position: operator.position,
          operator_type: operator.operator_type,
          operator_family: operator.operator_family,
          input_tables: operator.input_tables,
          output_table: operator.output_table,
          parameters: operator.parameters,
          input_rows: operator.input_rows,
          output_rows: operator.output_rows,
          output_columns: operator.output_columns,
          added_columns: operator.added_columns,
          removed_columns: operator.removed_columns,
          summary: operator.summary,
        })),
        state_id: attempt.state_id,
        output_table: attempt.output_table,
        output_rows: attempt.output_rows,
        output_columns: attempt.output_columns,
        observation: attempt.observation,
        violation_type: attempt.violation_type,
        error: attempt.error,
        request_sha256: attempt.request_sha256,
        response_sha256: attempt.response_sha256,
      })),
      analysis_notebook: run.analysis_notebook.map((step) => ({
        step_id: step.step_id,
        sequence: step.sequence,
        turn: step.turn,
        phase: step.phase,
        status: step.status,
        title: step.title,
        summary: step.summary,
        analysis_name: step.analysis_name,
        language: step.language,
        source_code: step.source_code,
        parameters: step.parameters,
        output: step.output,
        runtime: step.runtime,
        duration_ms: step.duration_ms,
        state_refs: step.state_refs,
        artifact_refs: step.artifact_refs,
        evidence_refs: step.evidence_refs,
      })),
      source_decisions: run.source_decisions.map((decision) => ({
        decision_id: decision.decision_id,
        iteration: decision.iteration,
        selected_source_ids: decision.selected_source_ids,
        newly_selected_source_ids: decision.newly_selected_source_ids,
        candidate_scores: decision.candidate_scores,
        reason: decision.reason,
        trigger_violation_id: decision.trigger_violation_id,
        evidence_refs: decision.evidence_refs,
      })),
      materialized_states: run.materialized_states.map((state) => ({
        state_id: state.state_id,
        iteration: state.iteration,
        parent_state_ids: state.parent_state_ids,
        source_ids: state.source_ids,
        row_count: state.row_count,
        columns: state.columns,
        schema: state.schema,
        metrics: state.metrics,
        evidence_refs: state.evidence_refs,
      })),
      artifacts: run.artifacts.map((artifact) => ({
        artifact_id: artifact.artifact_id,
        kind: artifact.kind,
        name: artifact.name,
        value: artifact.value,
        unit: artifact.unit,
        display_precision: artifact.display_precision,
        source_state_ids: artifact.source_state_ids,
        evidence_refs: artifact.evidence_refs,
      })),
      violations: run.violations.map((violation) => ({
        violation_id: violation.violation_id,
        obligation_ids: violation.obligation_ids,
        type: violation.type,
        observed: violation.observed,
        expected: violation.expected,
        detected_stage: violation.detected_stage,
        responsible_stage: violation.responsible_stage,
        evidence_refs: violation.evidence_refs,
        resolved: violation.resolved,
      })),
      repair_goals: run.repair_goals.map((goal) => ({
        repair_goal_id: goal.repair_goal_id,
        violation_id: goal.violation_id,
        target_stage: goal.target_stage,
        instruction: goal.instruction,
        search_terms: goal.search_terms,
        status: goal.status,
        selected_source_ids: goal.selected_source_ids,
      })),
      lifecycle_events: run.events.map((event) => ({
        event_id: event.event_id,
        sequence: event.sequence,
        from_stage: event.from_stage,
        to_stage: event.to_stage,
        edge_kind: event.edge_kind,
        summary: event.summary,
        object_refs: event.object_refs,
      })),
      report: {
        report_id: run.report.report_id,
        title: run.report.title,
        markdown: run.report.markdown,
        claims: run.report.claims.map((claim) => ({
          claim_id: claim.claim_id,
          text: claim.text,
          value: claim.value,
          artifact_refs: claim.artifact_refs,
          evidence_refs: claim.evidence_refs,
        })),
        evidence_refs: run.report.evidence_refs,
        executive_summary: run.report.executive_summary,
        executive_artifact_refs: run.report.executive_artifact_refs,
        sections: run.report.sections,
        conclusion: run.report.conclusion,
        conclusion_artifact_refs: run.report.conclusion_artifact_refs,
        limitations: run.report.limitations,
      },
      evidence,
    },
  };
}

function downloadText(filename: string, contents: string, mediaType: string) {
  const url = URL.createObjectURL(new Blob([contents], { type: mediaType }));
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.hidden = true;
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
}

export function downloadReportMarkdown(run: RunState) {
  if (run.status !== "completed" || run.report === null) {
    throw new Error("A completed report is required for export.");
  }
  downloadText(
    `askdu-${run.run_id}-report.md`,
    run.report.markdown,
    "text/markdown;charset=utf-8",
  );
}

export function downloadEvidenceBundle(
  run: RunState,
  catalogProvenance: CatalogProvenance | null,
) {
  const bundle = buildEvidenceBundle(run, catalogProvenance);
  downloadText(
    `askdu-${run.run_id}-evidence.json`,
    `${JSON.stringify(bundle, null, 2)}\n`,
    "application/json;charset=utf-8",
  );
}
